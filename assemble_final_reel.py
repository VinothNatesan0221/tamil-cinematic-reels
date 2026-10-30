
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts
from gtts import gTTS

ROOT = Path(__file__).resolve().parent

VOICES = {
    "male": "ta-IN-ValluvarNeural",
    "female": "ta-IN-PallaviNeural",
}


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    value = subprocess.check_output(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(value)


def tempo_filter(speed):
    filters = []

    while speed > 2.0:
        filters.append("atempo=2.0")
        speed /= 2.0

    while speed < 0.5:
        filters.append("atempo=0.5")
        speed /= 0.5

    filters.append(f"atempo={speed:.6f}")
    return ",".join(filters)


def srt_stamp(seconds):
    total_ms = round(seconds * 1000)

    hours, rem = divmod(total_ms, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, millis = divmod(rem, 1000)

    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def wrap_subtitle(value, width=34):
    lines = []
    current = ""

    for word in str(value).split():
        candidate = (current + " " + word).strip()

        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)

    return "\n".join(lines[:2])


async def generate_tamil_audio(
    narration_text,
    voice,
    raw,
    scene_number,
):
    last_error = None

    # Primary provider: Microsoft Edge TTS
    for attempt in range(1, 5):
        try:
            if raw.exists():
                raw.unlink()

            print(
                f"Edge TTS: scene {scene_number}, "
                f"voice {voice}, attempt {attempt}/4"
            )

            await edge_tts.Communicate(
                text=narration_text,
                voice=voice,
                rate="+0%",
                volume="+0%",
            ).save(str(raw))

            if raw.exists() and raw.stat().st_size > 1000:
                print(
                    f"SUCCESS: Edge TTS generated scene {scene_number}"
                )
                return

            raise RuntimeError(
                "Edge TTS returned an empty or unusually small audio file."
            )

        except Exception as exc:
            last_error = exc

            print(
                f"Edge TTS attempt {attempt} failed: "
                f"{type(exc).__name__}: {exc}"
            )

            if raw.exists():
                raw.unlink()

            if attempt < 4:
                await asyncio.sleep(3 * attempt)

    # Secondary provider: Google gTTS
    print(
        f"Edge TTS unavailable for scene {scene_number}. "
        "Trying Google gTTS fallback."
    )

    try:
        if raw.exists():
            raw.unlink()

        await asyncio.to_thread(
            lambda: gTTS(
                text=narration_text,
                lang="ta",
                slow=False,
            ).save(str(raw))
        )

        if not raw.exists() or raw.stat().st_size <= 1000:
            raise RuntimeError(
                "Google gTTS returned empty or unusually small audio."
            )

        print(
            f"SUCCESS: Google gTTS generated scene {scene_number}"
        )

    except Exception as fallback_error:
        raise RuntimeError(
            f"Tamil audio generation failed for scene {scene_number}. "
            f"Edge TTS error: {last_error}. "
            f"Google gTTS error: {fallback_error}"
        ) from fallback_error


async def main():
    story_file = ROOT / "story.json"

    if not story_file.is_file():
        raise FileNotFoundError(
            "story.json is missing from the repository root."
        )

    story = json.loads(
        story_file.read_text(encoding="utf-8")
    )

    scenes = story.get("scenes", [])

    if not scenes:
        raise ValueError(
            "story.json must contain a non-empty scenes array."
        )

    # Find the original rendered video.
    mp4_files = [
        p for p in ROOT.rglob("*.mp4")
        if p.name != "final_reel.mp4"
        and "voice_work" not in p.parts
        and "publishing_package" not in p.parts
    ]

    if not mp4_files:
        raise FileNotFoundError(
            "No source MP4 found in downloaded artifact."
        )

    video = max(
        mp4_files,
        key=lambda p: p.stat().st_size,
    )

    video_length = duration(video)

    # Calculate scene timing.
    scene_lengths = [
        float(scene.get("duration_seconds", 6))
        for scene in scenes
    ]

    if any(length <= 0 for length in scene_lengths):
        raise ValueError(
            "Scene durations must be greater than zero."
        )

    total = sum(scene_lengths)

    scene_lengths = [
        length * video_length / total
        for length in scene_lengths
    ]

    work_dir = ROOT / "voice_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    voice_parts = []

    # Generate Tamil narration scene by scene.
    for index, scene in enumerate(scenes):
        scene_number = index + 1

        narration_text = str(
            scene.get("tamil_narration", "")
        ).strip()

        gender = str(
            scene.get("speaker_gender", "male")
        ).lower().strip()

        if not narration_text:
            raise ValueError(
                f"Scene {scene_number} is missing tamil_narration."
            )

        if gender not in VOICES:
            raise ValueError(
                f"Scene {scene_number}: "
                "speaker_gender must be male or female."
            )

        raw = (
            work_dir / f"raw_{scene_number:02}.mp3"
        ).resolve()

        fitted = (
            work_dir / f"fit_{scene_number:02}.mp3"
        ).resolve()

        await generate_tamil_audio(
            narration_text=narration_text,
            voice=VOICES[gender],
            raw=raw,
            scene_number=scene_number,
        )

        # Fit narration to scene duration.
        speed = duration(raw) / scene_lengths[index]

        run([
            "ffmpeg",
            "-y",
            "-i", str(raw),
            "-af", tempo_filter(speed),
            "-t", f"{scene_lengths[index]:.3f}",
            "-ar", "44100",
            "-ac", "2",
            str(fitted),
        ])

        if not fitted.is_file():
            raise FileNotFoundError(
                f"Voice clip was not created: {fitted}"
            )

        voice_parts.append(fitted)

    # Combine all Tamil narration clips.
    concat_list = (
        work_dir / "concat.txt"
    ).resolve()

    concat_list.write_text(
        "".join(
            f"file '{part.as_posix()}'\n"
            for part in voice_parts
        ),
        encoding="utf-8",
    )

    narration = ROOT / "tamil_narration.mp3"

    run([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(narration),
    ])

    # Generate English subtitles.
    subtitle_entries = []
    elapsed = 0.0

    for index, scene in enumerate(scenes):
        subtitle = str(
            scene.get("english_subtitle", "")
        ).strip()

        if subtitle:
            subtitle_entries.append(
                f"{len(subtitle_entries) + 1}\n"
                f"{srt_stamp(elapsed)} --> "
                f"{srt_stamp(elapsed + scene_lengths[index])}\n"
                f"{wrap_subtitle(subtitle)}\n"
            )

        elapsed += scene_lengths[index]

    subtitle_file = ROOT / "english_subtitles.srt"

    subtitle_file.write_text(
        "\n".join(subtitle_entries),
        encoding="utf-8",
    )

    # Assemble final video with Tamil narration and English subtitles.
    final_video = ROOT / "final_reel.mp4"

    subtitle_filter = (
        "subtitles=english_subtitles.srt:"
        "force_style='FontName=DejaVu Sans,FontSize=18,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=70'"
    )

    run([
        "ffmpeg",
        "-y",
        "-i", str(video),
        "-i", str(narration),
        "-vf", subtitle_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "160k",
        "-t", f"{video_length:.3f}",
        "-movflags", "+faststart",
        str(final_video),
    ])

    # Generate cover image from existing video.
    cover = ROOT / "reel_cover.jpg"

    cover_time = min(
        1.0,
        max(0.0, video_length * 0.08),
    )

    run([
        "ffmpeg",
        "-y",
        "-ss", f"{cover_time:.3f}",
        "-i", str(video),
        "-frames:v", "1",
        "-vf",
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920",
        "-q:v", "2",
        str(cover),
    ])

    # Generate Instagram caption.
    hashtags = story.get("hashtags", [])

    if isinstance(hashtags, str):
        hashtags = hashtags.split()

    hashtag_line = " ".join(
        tag if str(tag).startswith("#")
        else "#" + str(tag).replace(" ", "")
        for tag in hashtags
    )

    caption_lines = [
        str(story.get("caption_tamil", "")).strip(),
        "",
        str(story.get("caption_english", "")).strip(),
        "",
        hashtag_line,
    ]

    caption_file = ROOT / "instagram_caption.txt"

    caption_file.write_text(
        "\n".join(caption_lines).strip() + "\n",
        encoding="utf-8",
    )

    # Create publishing package.
    package_dir = ROOT / "publishing_package"
    package_dir.mkdir(exist_ok=True)

    for item in [
        final_video,
        cover,
        caption_file,
        subtitle_file,
    ]:
        target = package_dir / item.name
        target.write_bytes(item.read_bytes())

    print("\nSUCCESS: Publishing package created:")

    for item in sorted(package_dir.iterdir()):
        print(
            f"- {item.name} "
            f"({item.stat().st_size} bytes)"
        )


if __name__ == "__main__":
    asyncio.run(main())

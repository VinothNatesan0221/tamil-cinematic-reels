"""Assemble the render artifact into a review-ready Instagram package.

Expected inputs in this directory:
  cinematic_reel.mp4  - silent 30-second visual render (Tamil hook may be burned in)
  story.json          - the exact story bundled with that render
  ambience.wav        - original ambience stem from render_reel.py
  sfx.wav             - generated clock/shutter/flash cue stem from render_reel.py

Outputs in publishing_package/:
  final_reel.mp4, reel_cover.jpg, instagram_caption.txt, english_subtitles.srt
"""
import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts
from gtts import gTTS

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "publishing_package"
WORK = ROOT / "voice_work"
VOICES = {"male": "ta-IN-ValluvarNeural", "female": "ta-IN-PallaviNeural"}
MAX_SPEED = 1.25


def run(cmd):
    subprocess.run(cmd, check=True)


def probe_duration(path):
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(value)


def tempo_filter(speed):
    # FFmpeg atempo supports 0.5..2.0 per filter.
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.6f}")
    return ",".join(parts)


def srt_stamp(seconds):
    ms = round(seconds * 1000)
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def wrap_subtitle(value, width=34):
    lines, current = [], ""
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


async def generate_tamil_audio(text, voice, output, scene_number):
    last_error = None
    for attempt in range(1, 5):
        try:
            output.unlink(missing_ok=True)
            print(f"Edge TTS scene {scene_number}: {voice}, attempt {attempt}/4")
            await edge_tts.Communicate(
                text=text, voice=voice, rate="+0%", volume="+0%"
            ).save(str(output))
            if output.is_file() and output.stat().st_size > 1000:
                return
            raise RuntimeError("TTS output was empty or unexpectedly small")
        except Exception as exc:
            last_error = exc
            output.unlink(missing_ok=True)
            if attempt < 4:
                await asyncio.sleep(3 * attempt)

    # Fallback does not provide gender-specific voice selection. Log this clearly.
    print(f"WARNING: Edge TTS failed for scene {scene_number}; using gTTS fallback (voice gender not selectable).")
    try:
        await asyncio.to_thread(lambda: gTTS(text=text, lang="ta", slow=False).save(str(output)))
        if not output.is_file() or output.stat().st_size <= 1000:
            raise RuntimeError("gTTS output was empty or unexpectedly small")
    except Exception as fallback_error:
        raise RuntimeError(
            f"Tamil narration failed for scene {scene_number}; Edge TTS: {last_error}; gTTS: {fallback_error}"
        ) from fallback_error


async def main():
    story_path = ROOT / "story.json"
    video = ROOT / "cinematic_reel.mp4"
    ambience = ROOT / "ambience.wav"
    sfx = ROOT / "sfx.wav"
    if not story_path.is_file():
        raise FileNotFoundError("Matching story.json is missing from downloaded render artifact")
    if not video.is_file() or video.stat().st_size == 0:
        raise FileNotFoundError("cinematic_reel.mp4 is missing or empty")

    story = json.loads(story_path.read_text(encoding="utf-8"))
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("story.json must contain exactly five scenes")

    video_length = probe_duration(video)
    if video_length <= 0:
        raise ValueError("Source video has invalid duration")

    requested = [float(s.get("duration_seconds", 6)) for s in scenes]
    if any(x <= 0 for x in requested):
        raise ValueError("Every scene duration_seconds must be positive")
    # The renderer scales the same five duration weights to 30 seconds.
    scene_lengths = [x * video_length / sum(requested) for x in requested]

    WORK.mkdir(parents=True, exist_ok=True)
    PACKAGE.mkdir(parents=True, exist_ok=True)
    voice_parts = []
    elapsed = 0.0
    srt_entries = []

    for idx, scene in enumerate(scenes, start=1):
        narration = str(scene.get("tamil_narration", "")).strip()
        gender = str(scene.get("speaker_gender", "")).strip().lower()
        subtitle = str(scene.get("english_subtitle", "")).strip()
        if not narration:
            raise ValueError(f"Scene {idx} is missing tamil_narration")
        if gender not in VOICES:
            raise ValueError(f"Scene {idx}: speaker_gender must be male or female")
        if not subtitle:
            raise ValueError(f"Scene {idx} is missing english_subtitle")

        raw = WORK / f"raw_{idx:02}.mp3"
        fitted = WORK / f"fit_{idx:02}.wav"
        await generate_tamil_audio(narration, VOICES[gender], raw, idx)
        raw_duration = probe_duration(raw)
        target = scene_lengths[idx - 1]
        required_speed = raw_duration / target
        if required_speed > MAX_SPEED:
            raise ValueError(
                f"Scene {idx} narration is too long ({raw_duration:.1f}s for {target:.1f}s). "
                f"Shorten tamil_narration; maximum automatic speed-up is {MAX_SPEED:.2f}x."
            )
        speed = max(0.85, required_speed)  # do not unnaturally slow short lines
        # Pad short lines with silence; never cut speech at a scene boundary.
        run([
            "ffmpeg", "-y", "-i", str(raw), "-af",
            f"{tempo_filter(speed)},apad,atrim=duration={target:.3f},asetpts=PTS-STARTPTS",
            "-ar", "44100", "-ac", "2", str(fitted)
        ])
        if not fitted.is_file() or fitted.stat().st_size == 0:
            raise RuntimeError(f"Narration audio was not created for scene {idx}")
        voice_parts.append(fitted)

        srt_entries.append(
            f"{idx}\n{srt_stamp(elapsed)} --> {srt_stamp(elapsed + target)}\n"
            f"{wrap_subtitle(subtitle)}\n"
        )
        elapsed += target

    concat_list = WORK / "voice_concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in voice_parts),
        encoding="utf-8"
    )
    narration_file = WORK / "tamil_narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(narration_file)])

    srt_file = PACKAGE / "english_subtitles.srt"
    srt_file.write_text("\n".join(srt_entries), encoding="utf-8")

    # Mix the original ambience under narration. Narration remains dominant.
    final_video = PACKAGE / "final_reel.mp4"
    audio_inputs = ["-i", str(narration_file)]
    mix_parts = ["[1:a]volume=1.0[narr]"]
    mix_labels = ["[narr]"]
    input_index = 2
    if ambience.is_file() and ambience.stat().st_size > 0:
        audio_inputs += ["-i", str(ambience)]
        mix_parts.append(f"[{input_index}:a]volume=0.18[amb]")
        mix_labels.append("[amb]")
        input_index += 1
    else:
        print("WARNING: ambience.wav not found; omitting ambience stem")
    if sfx.is_file() and sfx.stat().st_size > 0:
        audio_inputs += ["-i", str(sfx)]
        mix_parts.append(f"[{input_index}:a]volume=0.55[sfx]")
        mix_labels.append("[sfx]")
    else:
        print("WARNING: sfx.wav not found; omitting sound-effect stem")
    mix_parts.append(
        "".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=2,"
        "alimiter=limit=0.95[aout]"
    )
    audio_map = [
        *audio_inputs,
        "-filter_complex", ";".join(mix_parts),
        "-map", "0:v:0", "-map", "[aout]"
    ]

    subtitle_filter = (
        f"subtitles={srt_file.as_posix()}:"
        "force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=70'"
    )
    run([
        "ffmpeg", "-y", "-i", str(video), *audio_map,
        "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{video_length:.3f}", "-movflags", "+faststart", str(final_video)
    ])

    cover = PACKAGE / "reel_cover.jpg"
    cover_time = min(1.0, max(0.0, video_length * 0.08))
    run(["ffmpeg", "-y", "-ss", f"{cover_time:.3f}", "-i", str(video),
         "-frames:v", "1", "-vf",
         "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
         "-q:v", "2", str(cover)])

    hashtags = story.get("hashtags", [])
    if isinstance(hashtags, str):
        hashtags = hashtags.split()
    hashtag_line = " ".join(
        str(tag) if str(tag).startswith("#") else "#" + str(tag).replace(" ", "")
        for tag in hashtags
    )
    caption = "\n\n".join(filter(None, [
        str(story.get("caption_tamil", "")).strip(),
        str(story.get("caption_english", "")).strip(),
        hashtag_line
    ])) + "\n"
    (PACKAGE / "instagram_caption.txt").write_text(caption, encoding="utf-8")

    # Validate actual output streams and duration before declaring package ready.
    final_duration = probe_duration(final_video)
    if abs(final_duration - video_length) > 0.75:
        raise RuntimeError(f"Final video duration mismatch: source={video_length:.2f}s final={final_duration:.2f}s")
    for name in ("final_reel.mp4", "reel_cover.jpg", "instagram_caption.txt", "english_subtitles.srt"):
        path = PACKAGE / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Publishing package file missing or empty: {name}")
    print("SUCCESS: review-ready publishing package created. Nothing was posted to Instagram.")


if __name__ == "__main__":
    asyncio.run(main())

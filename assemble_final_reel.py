import asyncio
import json
import subprocess
from pathlib import Path
import edge_tts

ROOT = Path(__file__).resolve().parent
VOICES = {"male": "ta-IN-ValluvarNeural", "female": "ta-IN-PallaviNeural"}

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(path):
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
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

async def main():
    story_file = ROOT / "story.json"
    if not story_file.is_file():
        raise FileNotFoundError(f"Missing story JSON: {story_file}")
    story = json.loads(story_file.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if not scenes:
        raise ValueError("story.json must contain a non-empty scenes array.")

    mp4_files = [
        p for p in ROOT.rglob("*.mp4")
        if p.name != "final_reel.mp4" and "voice_work" not in p.parts
    ]
    if not mp4_files:
        raise FileNotFoundError("No source MP4 found in downloaded artifact.")
    video = max(mp4_files, key=lambda p: p.stat().st_size)
    video_length = duration(video)

    scene_lengths = [float(s.get("duration_seconds", 6)) for s in scenes]
    if any(x <= 0 for x in scene_lengths):
        raise ValueError("Every scene duration_seconds must be greater than zero.")
    total = sum(scene_lengths)
    scene_lengths = [x * video_length / total for x in scene_lengths]

    work_dir = ROOT / "voice_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    voice_parts = []

    for index, scene in enumerate(scenes):
        text = str(scene.get("tamil_narration", "")).strip()
        gender = str(scene.get("speaker_gender", "male")).lower().strip()
        if not text:
            raise ValueError(f"Scene {index + 1} is missing tamil_narration.")
        if gender not in VOICES:
            raise ValueError(f"Scene {index + 1}: speaker_gender must be male or female.")

        raw = (work_dir / f"raw_{index + 1:02}.mp3").resolve()
        fitted = (work_dir / f"fit_{index + 1:02}.mp3").resolve()
        await edge_tts.Communicate(text=text, voice=VOICES[gender]).save(str(raw))

        raw_length = duration(raw)
        target_length = scene_lengths[index]
        run([
            "ffmpeg", "-y", "-i", str(raw),
            "-af", tempo_filter(raw_length / target_length),
            "-t", f"{target_length:.3f}", "-ar", "44100", "-ac", "2", str(fitted)
        ])
        if not fitted.is_file():
            raise FileNotFoundError(f"FFmpeg did not create voice clip: {fitted}")
        voice_parts.append(fitted)

    # Use an absolute concat-list path and absolute clip paths to avoid cwd/path errors.
    concat_list = (work_dir / "concat.txt").resolve()
    concat_text = "".join(f"file '{part.as_posix()}'\n" for part in voice_parts)
    concat_list.write_text(concat_text, encoding="utf-8")
    if not concat_list.is_file():
        raise FileNotFoundError(f"Concat list was not created: {concat_list}")
    print(f"Created concat list: {concat_list}")
    print(concat_list.read_text(encoding="utf-8"))

    narration = ROOT / "tamil_narration.mp3"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "128k", str(narration)
    ])

    subtitle_entries = []
    elapsed = 0.0
    for index, scene in enumerate(scenes):
        subtitle = str(scene.get("english_subtitle", "")).strip()
        if subtitle:
            subtitle_entries.append(
                f"{len(subtitle_entries) + 1}\n"
                f"{srt_stamp(elapsed)} --> {srt_stamp(elapsed + scene_lengths[index])}\n"
                f"{wrap_subtitle(subtitle)}\n"
            )
        elapsed += scene_lengths[index]

    subtitle_file = ROOT / "english_subtitles.srt"
    subtitle_file.write_text("\n".join(subtitle_entries), encoding="utf-8")

    final_video = ROOT / "final_reel.mp4"
    subtitle_filter = (
        "subtitles=english_subtitles.srt:"
        "force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=70'"
    )
    run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(narration),
        "-vf", subtitle_filter, "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "160k", "-t", f"{video_length:.3f}",
        "-movflags", "+faststart", str(final_video)
    ])
    print(f"SUCCESS: Created {final_video}")

if __name__ == "__main__":
    asyncio.run(main())

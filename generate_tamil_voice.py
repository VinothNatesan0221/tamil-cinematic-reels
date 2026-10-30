import asyncio
import json
import os
import pathlib
import subprocess
import sys

import edge_tts

ROOT = pathlib.Path("voice_work")
ROOT.mkdir(exist_ok=True)

with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
    event = json.load(f)

draft = json.loads(event["inputs"]["draft_json"])
scenes = draft.get("scenes", [])
if len(scenes) != 5:
    raise SystemExit("Expected exactly five scenes.")

VOICE = "ta-IN-ValluvarNeural"  # Tamil male voice
RATE = "+0%"
VOLUME = "+0%"

async def make_line(text, index):
    if not text.strip():
        raise ValueError(f"Scene {index} has empty Tamil narration.")
    raw = ROOT / f"line_{index}.mp3"
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=RATE, volume=VOLUME)
    await communicate.save(str(raw))

    # Fit the spoken line into its six-second scene slot without cutting words.
    duration_text = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(raw)],
        text=True
    ).strip()
    duration = float(duration_text)
    target = 5.75
    speed = max(1.0, duration / target)
    if speed > 1.35:
        print(f"Warning: Scene {index} narration is long ({duration:.1f}s); "
              "audio will be sped up by {speed:.2f}x. Consider shortening the line.")

    # atempo supports 0.5–2.0; this script only speeds up and never slows speech.
    fitted = ROOT / f"fitted_{index}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw), "-filter:a", f"atempo={speed:.4f}",
         "-ac", "1", "-ar", "44100", str(fitted)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    # Pad each scene slot to exactly six seconds so narration aligns to the reel.
    slot = ROOT / f"slot_{index}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(fitted), "-af",
         "apad=pad_dur=6,atrim=duration=6,afade=t=in:st=0:d=0.12,afade=t=out:st=5.65:d=0.25",
         "-ac", "1", "-ar", "44100", str(slot)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    print(f"Scene {index}: Tamil narration generated.")

async def main():
    for i, scene in enumerate(scenes, 1):
        await make_line(str(scene.get("tamil_narration", "")), i)

asyncio.run(main())

concat = ROOT / "voice_concat.txt"
concat.write_text("".join(f"file '{(ROOT / f'slot_{i}.wav').resolve()}'\n"
                          for i in range(1, 6)), encoding="utf-8")
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
     "-c:a", "libmp3lame", "-b:a", "128k", "tamil_narration.mp3"],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
)
print("SUCCESS: tamil_narration.mp3 created (30 seconds, five scene-aligned slots).")

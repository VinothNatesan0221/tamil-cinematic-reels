import asyncio
import json
import os
import pathlib
import subprocess
import edge_tts

WORK = pathlib.Path("voice_work")
WORK.mkdir(exist_ok=True)

VOICES = {
    "male": "ta-IN-ValluvarNeural",
    "female": "ta-IN-PallaviNeural",
}

with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
    event = json.load(f)

draft = json.loads(event["inputs"]["draft_json"])
scenes = draft.get("scenes", [])
if len(scenes) != 5:
    raise SystemExit("Expected exactly five scenes.")

def atempo_chain(speed):
    # FFmpeg atempo accepts 0.5–2.0 per filter; chain filters for longer lines.
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    parts.append(f"atempo={speed:.4f}")
    return ",".join(parts)

async def make_scene(scene, index):
    text = str(scene.get("tamil_narration", "")).strip()
    gender = str(scene.get("speaker_gender", "")).strip().lower()

    if not text:
        raise ValueError(f"Scene {index}: tamil_narration is empty.")
    if gender not in VOICES:
        raise ValueError(
            f"Scene {index}: add speaker_gender as 'male' or 'female' "
            "to the scene JSON. Voice is not guessed."
        )

    voice = VOICES[gender]
    raw = WORK / f"line_{index}.mp3"
    await edge_tts.Communicate(
        text=text, voice=voice, rate="+0%", volume="+0%"
    ).save(str(raw))

    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(raw)],
        text=True
    ).strip())

    target_seconds = 5.75
    speed = max(1.0, duration / target_seconds)
    if speed > 1.35:
        print(
            f"Warning: Scene {index} is {duration:.1f}s; speeding up "
            f"{gender} voice by {speed:.2f}x. Consider shortening the line."
        )

    fitted = WORK / f"fitted_{index}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw), "-filter:a", atempo_chain(speed),
         "-ac", "1", "-ar", "44100", str(fitted)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    slot = WORK / f"slot_{index}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(fitted), "-af",
         "apad=pad_dur=6,atrim=duration=6,"
         "afade=t=in:st=0:d=0.12,afade=t=out:st=5.65:d=0.25",
         "-ac", "1", "-ar", "44100", str(slot)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    print(f"Scene {index}: {gender} voice ({voice}) generated.")

async def main():
    for index, scene in enumerate(scenes, 1):
        await make_scene(scene, index)

asyncio.run(main())

concat = WORK / "concat.txt"
concat.write_text(
    "".join(
        f"file '{(WORK / f'slot_{i}.wav').resolve()}'\n"
        for i in range(1, 6)
    ),
    encoding="utf-8"
)
subprocess.run(
    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
     "-c:a", "libmp3lame", "-b:a", "128k", "tamil_narration.mp3"],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
)
print("SUCCESS: tamil_narration.mp3 created with scene-by-scene character voices.")
print("Male = ta-IN-ValluvarNeural | Female = ta-IN-PallaviNeural")
print("Narration only: no images, video, or background music are generated.")

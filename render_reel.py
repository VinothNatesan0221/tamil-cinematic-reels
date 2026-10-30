import json, os, pathlib, subprocess, time, urllib.request, urllib.error
import wave, math, random, struct, textwrap

ROOT = pathlib.Path("work")
ROOT.mkdir(exist_ok=True)
API_URL = "https://oai.endpoints.kepler.ai.cloud.ovh.net/api/stable-diffusion-xl-base-v10/text2image"

event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
draft = json.loads(event["inputs"]["draft_json"])
scenes = draft.get("scenes", [])
if len(scenes) != 5:
    raise SystemExit("The story must contain exactly five scenes.")

ANCHOR = (
    "Character identity continuity: Kavin, the same 28-year-old South Indian "
    "man in every scene, oval face, medium-brown skin, expressive dark eyes, "
    "short slightly wavy black hair, thin wire-rimmed round glasses, light "
    "stubble, faded charcoal linen shirt. Preserve the same facial structure, "
    "age, glasses, hairstyle, skin tone and clothing. Photorealistic cinematic "
    "film still, realistic anatomy. Do not force a frontal portrait when the "
    "scene calls for a rear view, profile or silhouette. Vertical 9:16."
)
NEGATIVE = (
    "different person, different face, different glasses, different clothes, "
    "duplicate person, blurry, low quality, distorted face, deformed hands, "
    "extra fingers, bad anatomy, watermark, text, logo, cartoon"
)

def generate(prompt, number):
    body = json.dumps({
        "prompt": prompt + " " + ANCHOR,
        "negative_prompt": NEGATIVE
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Accept": "application/octet-stream"},
        method="POST"
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                data = response.read()
            if len(data) < 5000:
                raise RuntimeError("Image response was unexpectedly small.")
            ext = "png" if data.startswith(b"\x89PNG") else (
                "jpg" if data.startswith(b"\xff\xd8") else None)
            if not ext:
                raise RuntimeError("Endpoint did not return PNG or JPEG data.")
            path = ROOT / f"scene{number}.{ext}"
            path.write_bytes(data)
            print(f"Scene {number}: image generated.")
            return path
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"Image API error {exc.code}: {detail}")
            wait = 50 * (attempt + 1)
            print(f"Temporary API error {exc.code}; retrying in {wait}s.")
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"Could not generate scene {number}.")

images = []
for i, scene in enumerate(scenes, 1):
    prompt = scene.get("visual_prompt", "").strip()
    if not prompt:
        raise SystemExit(f"Scene {i} has no visual_prompt.")
    images.append(generate(prompt, i))
    if i < 5:
        time.sleep(35)

def ass_time(seconds):
    cs = int(round(seconds * 100))
    return f"{cs//360000}:{(cs//6000)%60:02d}:{(cs//100)%60:02d}.{cs%100:02d}"

def ass_escape(s):
    return str(s or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")

# ASS/libass subtitle rendering supports Tamil shaping; drawtext does not reliably do so.
ass = [
    "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
    "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    "Style: English,DejaVu Sans,40,&H00FFFFFF,&H000000FF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,3,2,1,2,100,100,205,1",
    "Style: Tamil,Noto Sans Tamil,48,&H00FFFFFF,&H000000FF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,3,2,1,8,90,90,135,1",
    "", "[Events]",
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
]
hook = draft.get("hook", "").strip()
if hook:
    ass.append(f"Dialogue: 1,0:00:00.00,0:00:03.50,Tamil,,0,0,0,,{ass_escape(hook)}")
for i, scene in enumerate(scenes):
    subtitle = "\n".join(textwrap.wrap(scene.get("english_subtitle", ""), width=34))
    ass.append(
        f"Dialogue: 0,{ass_time(i*6)},{ass_time((i+1)*6)},English,,0,0,0,,"
        f"{ass_escape(subtitle)}"
    )
ass_path = ROOT / "subtitles.ass"
ass_path.write_text("\n".join(ass) + "\n", encoding="utf-8")

# Original synthesized 30-second horror ambience: low drone, tape hiss and clicks.
sr, duration = 44100, 30
rng = random.Random(20261030)
audio_path = ROOT / "ambience.wav"
with wave.open(str(audio_path), "wb") as wav:
    wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sr)
    chunk = 4410
    for base in range(0, sr*duration, chunk):
        frames = []
        for n in range(base, min(base+chunk, sr*duration)):
            t = n / sr
            swell = 0.25 + 0.45*t/duration
            drone = (0.12*math.sin(2*math.pi*48*t)
                     + 0.07*math.sin(2*math.pi*73*t)
                     + 0.035*math.sin(2*math.pi*110*t))*swell
            hiss = rng.uniform(-1, 1)*0.018
            click = 0.0
            if any(abs(t-p)<0.025 for p in (5.8, 11.8, 17.8, 23.8)):
                click = rng.uniform(-0.12, 0.12)
            if 27 < t < 29.8:
                env = min(1, (t-27)/0.5)*min(1, (29.8-t)/0.4)
                click += env*(0.10*math.sin(2*math.pi*190*t)+rng.uniform(-0.1,0.1))
            fade = min(1,t/1.2)*min(1,(duration-t)/1.0)
            sample = max(-0.85,min(0.85,(drone+hiss+click)*fade))
            v = int(sample*32767)
            frames.append(struct.pack("<hh",v,int(v*0.96)))
        wav.writeframes(b"".join(frames))

clips = []
for i, image_path in enumerate(images, 1):
    out = ROOT / f"clip{i}.mp4"
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0007,1.12)':d=180:s=1080x1920:fps=30,"
        "setsar=1"
    )
    subprocess.run(
        ["ffmpeg","-y","-loop","1","-i",str(image_path),"-t","6",
         "-vf",vf,"-r","30","-c:v","libx264","-preset","veryfast",
         "-pix_fmt","yuv420p","-an",str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    clips.append(out)
    print(f"Scene {i}: video clip rendered.")

concat = ROOT / "concat.txt"
concat.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
silent = ROOT / "silent_reel.mp4"
subprocess.run(
    ["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
     "-c","copy","-movflags","+faststart",str(silent)],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
)
subprocess.run(
    ["ffmpeg","-y","-i",str(silent),"-i",str(audio_path),
     "-vf",f"subtitles={ass_path.as_posix()}:fontsdir=/usr/share/fonts/truetype/noto",
     "-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p","-c:a","aac",
     "-b:a","160k","-shortest","-movflags","+faststart","cinematic_reel.mp4"],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
)
print("SUCCESS: Created cinematic_reel.mp4 with shaped subtitles and original ambience.")
print("NOTE: This adds atmospheric sound effects, not spoken Tamil narration.")

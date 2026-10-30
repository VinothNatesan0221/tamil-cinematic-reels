
import json
import os
import pathlib
import subprocess
import time
import urllib.request
import urllib.error
import textwrap

ROOT = pathlib.Path("work")
ROOT.mkdir(exist_ok=True)

API_URL = (
    "https://oai.endpoints.kepler.ai.cloud.ovh.net"
    "/api/stable-diffusion-xl-base-v10/text2image"
)

# Read the GitHub Actions workflow input
event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
inputs = event.get("inputs", {})

try:
    draft = json.loads(inputs["draft_json"])
except Exception as exc:
    raise SystemExit(f"Could not read draft JSON: {exc}")

scenes = draft.get("scenes", [])

if len(scenes) != 5:
    raise SystemExit("The story must contain exactly five scenes.")

for i, scene in enumerate(scenes, 1):
    if not scene.get("visual_prompt"):
        raise SystemExit(f"Scene {i} has no visual_prompt.")

# Generate one image per scene using the OVHcloud endpoint
def generate_image(prompt, scene_number):
    payload = json.dumps({
        "prompt": prompt,
        "negative_prompt": (
            "blurry, low quality, distorted face, extra fingers, "
            "bad anatomy, watermark, text, logo"
        )
    }).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/octet-stream"
        },
        method="POST"
    )

    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = response.read()

            if len(data) < 5000:
                raise RuntimeError("Image response was unexpectedly small.")

            if data.startswith(b"\x89PNG"):
                extension = "png"
            elif data.startswith(b"\xff\xd8"):
                extension = "jpg"
            else:
                raise RuntimeError(
                    "The endpoint did not return a PNG or JPEG image."
                )

            path = ROOT / f"scene{scene_number}.{extension}"
            path.write_bytes(data)
            print(f"Scene {scene_number}: image generated.")
            return path

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(
                    f"Image API error {exc.code}: {detail}"
                )
            wait = 45 * (attempt + 1)
            print(f"Temporary API error {exc.code}; retrying in {wait}s.")
            time.sleep(wait)

        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                raise
            wait = 30 * (attempt + 1)
            print(f"Connection issue; retrying in {wait}s: {exc}")
            time.sleep(wait)

    raise RuntimeError(f"Could not generate scene {scene_number}.")

images = []
for i, scene in enumerate(scenes, 1):
    images.append(generate_image(scene["visual_prompt"], i))
    if i < 5:
        # Space requests out to reduce the chance of rate limiting
        time.sleep(35)

# Escape text for FFmpeg
def esc(value):
    value = str(value or "")
    return (
        value.replace("\\", "\\\\")
             .replace("'", "\\'")
             .replace(":", "\\:")
             .replace("%", "\\%")
             .replace(",", "\\,")
             .replace("[", "\\[")
             .replace("]", "\\]")
             .replace("\n", " ")
    )

def find_font(font_name, fallback):
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", font_name],
            capture_output=True, text=True, check=True
        )
        if result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return fallback

english_font = find_font(
    "DejaVu Sans",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
)
tamil_font = find_font(
    "Noto Sans Tamil",
    english_font
)

clips = []

for i, (scene, image_path) in enumerate(zip(scenes, images), 1):
    subtitle = "\n".join(
        textwrap.wrap(scene.get("english_subtitle", ""), width=38)
    )
    subtitle = esc(subtitle)

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0007,1.12)':"
        "d=180:s=1080x1920:fps=30,"
        "drawbox=x=0:y=1430:w=1080:h=490:"
        "color=black@0.48:t=fill,"
        f"drawtext=fontfile='{english_font}':text='{subtitle}':"
        "fontcolor=white:fontsize=43:line_spacing=12:"
        "x=(w-text_w)/2:y=1530:"
        "shadowcolor=black@0.9:shadowx=2:shadowy=2"
    )

    if i == 1 and draft.get("hook"):
        hook = esc(draft["hook"])
        vf += (
            f",drawtext=fontfile='{tamil_font}':text='{hook}':"
            "fontcolor=white:fontsize=48:"
            "x=(w-text_w)/2:y=250:"
            "box=1:boxcolor=black@0.48:boxborderw=20:"
            "enable='between(t,0,3)'"
        )

    output = ROOT / f"clip{i}.mp4"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-t", "6",
            "-vf", vf,
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output)
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )

    clips.append(output)
    print(f"Scene {i}: video clip rendered.")

concat_file = ROOT / "concat.txt"
concat_file.write_text(
    "".join(f"file '{clip.resolve()}'\n" for clip in clips),
    encoding="utf-8"
)

final_video = "cinematic_reel.mp4"

subprocess.run(
    [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        "-movflags", "+faststart",
        final_video
    ],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE
)

print(f"SUCCESS: Created {final_video}")

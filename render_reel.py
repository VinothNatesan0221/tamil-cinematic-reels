import json, os, subprocess, urllib.request, re, pathlib

ROOT = pathlib.Path('work')
ROOT.mkdir(exist_ok=True)
event = json.load(open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8'))
inputs = event.get('inputs', {})
try:
    draft = json.loads(inputs['draft_json'])
except Exception as e:
    raise SystemExit(f'Invalid draft_json input: {e}')
urls = [inputs.get(f'scene{i}_url','').strip() for i in range(1,6)]
if any(not u.startswith(('https://','http://')) for u in urls):
    raise SystemExit('Provide five publicly accessible HTTPS image URLs in the sheet.')

# Download images. For Google Drive, use a direct download URL; raw.githubusercontent.com also works.
for i, url in enumerate(urls, 1):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 5000:
        raise SystemExit(f'Scene {i} download is too small; check that the image URL is public and direct.')
    (ROOT / f'scene{i}.img').write_bytes(data)

# Escape text for FFmpeg drawtext. Use Noto fonts installed by the workflow.
def esc(s):
    s = str(s or '').replace('\\','\\\\').replace("'", "\\'").replace(':','\\:').replace('%','\\%').replace('\n',' ')
    return s

scenes = draft.get('scenes', [])
if len(scenes) != 5:
    raise SystemExit('Draft must contain exactly five scenes.')
clips=[]
for i, scene in enumerate(scenes, 1):
    text = esc(scene.get('english_subtitle',''))
    hook = esc(draft.get('hook','')) if i == 1 else ''
    vf = (
      "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
      "zoompan=z='min(zoom+0.0007,1.12)':d=180:s=1080x1920:fps=30,"
      "drawbox=x=0:y=1450:w=1080:h=470:color=black@0.42:t=fill,"
      f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='{text}':"
      "fontcolor=white:fontsize=48:line_spacing=10:x=(w-text_w)/2:y=1570:"
      "box=0:shadowcolor=black@0.8:shadowx=2:shadowy=2"
    )
    if hook:
      vf += f",drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='{hook}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=250:box=1:boxcolor=black@0.45:boxborderw=22:enable='between(t,0,2.5)'"
    out = ROOT / f'clip{i}.mp4'
    subprocess.run(['ffmpeg','-y','-loop','1','-i',str(ROOT/f'scene{i}.img'),'-t','6','-vf',vf,'-r','30','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-an',str(out)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    clips.append(out)

concat = ROOT / 'concat.txt'
concat.write_text(''.join(f"file '{p.resolve()}'\n" for p in clips), encoding='utf-8')
outfile = 'cinematic_reel.mp4'
subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',outfile], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
print(f'Created {outfile}')

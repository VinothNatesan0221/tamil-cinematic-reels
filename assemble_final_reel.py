import asyncio, json, subprocess
from pathlib import Path
import edge_tts

ROOT=Path.cwd()
VOICES={"male":"ta-IN-ValluvarNeural","female":"ta-IN-PallaviNeural"}
def run(cmd): subprocess.run(cmd,check=True)
def duration(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],text=True).strip())
def tempo(speed):
    f=[]
    while speed>2: f.append("atempo=2"); speed/=2
    while speed<0.5: f.append("atempo=0.5"); speed/=0.5
    f.append(f"atempo={speed:.6f}")
    return ",".join(f)
def stamp(t):
    n=round(t*1000); h,n=divmod(n,3600000); m,n=divmod(n,60000); s,ms=divmod(n,1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
def wrap(s,width=34):
    out=[]; line=""
    for w in str(s).split():
        if line and len(line+" "+w)>width: out.append(line); line=w
        else: line=(line+" "+w).strip()
    if line: out.append(line)
    return "\n".join(out[:2])
async def main():
    story=json.loads(Path("story.json").read_text(encoding="utf-8"))
    scenes=story.get("scenes",[])
    if not scenes: raise ValueError("story.json needs a scenes array")
    vids=[p for p in Path(".").rglob("*.mp4") if p.name!="final_reel.mp4"]
    if not vids: raise FileNotFoundError("No MP4 found in downloaded artifact")
    video=max(vids,key=lambda p:p.stat().st_size); vd=duration(video)
    ds=[float(s.get("duration_seconds",6)) for s in scenes]; total=sum(ds)
    ds=[x*vd/total for x in ds]
    work=Path("voice_work"); work.mkdir(exist_ok=True); parts=[]
    for i,sc in enumerate(scenes):
        text=str(sc.get("tamil_narration","")).strip()
        gender=str(sc.get("speaker_gender","male")).lower().strip()
        if not text: raise ValueError(f"Scene {i+1} missing tamil_narration")
        if gender not in VOICES: raise ValueError(f"Scene {i+1}: speaker_gender must be male or female")
        raw=work/f"raw{i}.mp3"; fit=work/f"fit{i}.mp3"
        await edge_tts.Communicate(text=text,voice=VOICES[gender]).save(str(raw))
        target=ds[i]; speed=duration(raw)/target
        run(["ffmpeg","-y","-i",str(raw),"-af",tempo(speed),"-t",f"{target:.3f}","-ar","44100","-ac","2",str(fit)])
        parts.append(fit)
    listing=work/"concat.txt"
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\\n" for p in parts))
    narration=Path("tamil_narration.mp3")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listing),"-c:a","libmp3lame","-b:a","128k",str(narration)])
    entries=[]; t=0
    for i,sc in enumerate(scenes):
        sub=str(sc.get("english_subtitle","")).strip()
        if sub: entries.append(f"{len(entries)+1}\n{stamp(t)} --> {stamp(t+ds[i])}\n{wrap(sub)}\n")
        t+=ds[i]
    Path("english_subtitles.srt").write_text("\n".join(entries),encoding="utf-8")
    vf="subtitles=english_subtitles.srt:force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=70'"
    run(["ffmpeg","-y","-i",str(video),"-i",str(narration),"-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","160k","-t",f"{vd:.3f}","-movflags","+faststart","final_reel.mp4"])
    print("Created final_reel.mp4")
if __name__=="__main__": asyncio.run(main())

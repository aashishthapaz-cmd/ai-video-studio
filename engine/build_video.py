from __future__ import annotations
import json, re, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
W,H=1080,1920
OVERLAY_OPACITY=0.15
DEFAULT_OVERLAY_NAME='default_overlay.mp4'

def run(cmd):
    return subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)

def audio_fx_filter():
    # Warm acoustic broadcast mastering: clean sub-rumble, subtle de-essing, warm voice body, and transparent loudness
    return (
        "highpass=f=45,"
        "lowpass=f=16000,"
        "equalizer=f=200:t=q:w=1.0:g=1.0,"
        "equalizer=f=5500:t=q:w=1.5:g=-1.8,"
        "acompressor=threshold=0.25:ratio=1.35:attack=25:release=220:makeup=1.05,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )

def mastered_audio(source):
    if not source.exists():
        return source
    target=source.with_name('narration_mastered.wav')
    r=run(['ffmpeg','-y','-i',str(source),'-af',audio_fx_filter(),'-ar','48000','-ac','1','-c:a','pcm_s16le',str(target)])
    return target if r.returncode==0 and target.exists() else source

def title_output_path(data):
    title=str(data.get('title') or 'untitled video').strip()
    # Keep the script title readable while removing Windows-invalid filename
    # characters. Do not convert spaces to underscores or use the project slug.
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    safe=re.sub(r'\s+', ' ', safe).strip(' .') or 'untitled video'
    out_dir=ROOT/'Output'; out_dir.mkdir(parents=True,exist_ok=True)
    return out_dir/(safe+'.mp4')

def export_title_copy(rendered, data):
    target=title_output_path(data)
    shutil.copy2(str(rendered),str(target))
    return target

def is_nepali(data):
    lang=str(data.get('language','')).lower(); typ=str(data.get('content_type','')).lower()
    return lang in {'ne','nepali'} or typ in {'poetry_nepali','news_nepali','explainer_nepali'} or any('\u0900'<=c<='\u097f' for s in data.get('scenes',[]) for c in str(s.get('narration','')))

def placeholder(path,label):
    from PIL import Image,ImageDraw
    path.parent.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(W,H),(18,24,38)); d=ImageDraw.Draw(im); d.text((70,900),label[:100],fill=(190,210,225)); im.save(path)

def scene_assets(project_dir,data):
    assets=[]
    for i,s in enumerate(data.get('scenes',[]),1):
        sid=s.get('id',f'scene_{i:03d}')
        found=None
        for ext in ('.png','.jpg','.jpeg','.webp'):
            p=project_dir/'assets'/(sid+ext)
            if p.exists(): found=p; break
        if found is None:
            found=project_dir/'frames'/(sid+'.png'); placeholder(found,str(s.get('narration','')))
        assets.append(found)
    return assets

def _word_tokens(text):
    return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?", str(text or ''))

def _norm_token(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or '').lower())

def _audio_duration(path):
    try:
        r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if r.returncode==0:
            return max(1.0,float(r.stdout.strip()))
    except Exception:
        pass
    return 1.0

def _caption_timing_weight(text):
    words=max(1,len(_word_tokens(text)))
    weight=max(1.0,words**0.92)
    stripped=str(text or '').strip()
    if stripped.endswith(('.', '?', '!')): weight+=0.55
    if stripped.endswith(('...',)): weight+=0.85
    if any(x in stripped for x in (',',';',':')): weight+=0.18
    return weight

def _word_timing_weight(word):
    clean=str(word or '').strip()
    core=_norm_token(clean)
    if not core:
        return 0.4
    weight=max(0.55,min(2.4,len(core)**0.62))
    if core in {'a','an','the','to','of','in','on','at','and','or','but','is','are','was','were','be','me','you','it'}:
        weight*=0.72
    if clean.endswith((',', ';', ':')):
        weight+=0.18
    if clean.endswith(('.', '?', '!')):
        weight+=0.34
    return weight

def _word_durations_for_text(text,start,end):
    words=_word_tokens(text)
    if not words:
        return tuple()
    total=max(0.25,float(end)-float(start))
    weights=[_word_timing_weight(word) for word in words]
    scale=total/max(0.01,sum(weights))
    raw=[max(0.08,min(0.85,weight*scale)) for weight in weights]
    diff=total-sum(raw)
    if raw:
        adjust=diff/len(raw)
        raw=[max(0.08,value+adjust) for value in raw]
    return tuple(raw)

def _weighted_scene_captions(project_dir, data, TimedCaption):
    audio=project_dir/'audio'/'narration.wav'
    rows=[str(s.get('narration','')).strip() for s in data.get('scenes',[]) if str(s.get('narration','')).strip()]
    if not rows:
        return []
    total=_audio_duration(audio) if audio.exists() else sum(max(1.0,float(s.get('duration',5))) for s in data.get('scenes',[]))
    weights=[_caption_timing_weight(row) for row in rows]
    gap_count=max(0,len(rows)-1)
    gap=min(0.62,max(0.24,total*0.035)) if gap_count else 0.0
    speech_total=max(1.0,total-(gap*gap_count))
    scale=speech_total/max(1.0,sum(weights))
    captions=[]; cursor=0.0
    for index,row in enumerate(rows):
        end=total if index==len(rows)-1 else min(total,cursor+weights[index]*scale)
        captions.append(TimedCaption(cursor,end,row,_word_durations_for_text(row,cursor,end)))
        cursor=end+gap
    return captions

def _find_word_window(words, cursor, target_tokens):
    normalized=[_norm_token(w.get('word','')) for w in words]
    target=[_norm_token(t) for t in target_tokens]
    target=[t for t in target if t]
    if not target:
        return cursor, cursor
    limit=min(len(words),cursor+8)
    first=target[0]
    start=cursor
    for i in range(cursor,limit):
        if normalized[i]==first:
            start=i
            break
    end=start
    matches=0
    for token in target:
        found=False
        scan_limit=min(len(words),end+6)
        for j in range(end,scan_limit):
            if normalized[j]==token:
                end=j+1
                matches+=1
                found=True
                break
        if not found:
            end=min(len(words),end+1)
    if matches < max(1,min(3,len(target)//2)):
        start=cursor
        end=min(len(words),cursor+len(target))
    return start,end

def _timed_scene_captions(project_dir, data, TimedCaption):
    timestamps=project_dir/'timestamps.json'
    try:
        payload=json.loads(timestamps.read_text(encoding='utf-8-sig'))
        words=[w for row in payload if isinstance(row,dict) for w in row.get('words',[]) if isinstance(w,dict) and str(w.get('word','')).strip()]
    except Exception:
        words=[]
    if not words:
        return _weighted_scene_captions(project_dir,data,TimedCaption)
    captions=[]; cursor=0
    for scene in data.get('scenes',[]):
        text=str(scene.get('narration','')).strip()
        pieces=[p.strip() for p in re.split(r'(?<=[.!?,;:])\s+',text) if p.strip()]
        if not pieces: pieces=[text]
        for piece in pieces:
            tokens=_word_tokens(piece)
            if not piece or not tokens or cursor >= len(words): continue
            start_i,end_i=_find_word_window(words,cursor,tokens)
            chunk=words[start_i:end_i]
            if not chunk: continue
            start=max(0.0,float(chunk[0].get('start',0.0)))
            end=max(start+0.35,float(chunk[-1].get('end',start+0.35))+0.18)
            durations=tuple(max(0.08,float(w.get('end',0))-float(w.get('start',0))) for w in chunk)
            captions.append(TimedCaption(start,end,piece,durations)); cursor=max(end_i,cursor+1)
    return captions

def write_simple_ass(data,path):
    # Nepali remains caption-free by design; English captions use the saved
    # Whisper word timestamps so their on-screen duration follows the narration.
    path.parent.mkdir(parents=True,exist_ok=True)
    nep=is_nepali(data)
    if nep:
        path.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans Devanagari,68,&H00FFFFFF,&H00FFFFFF,&HCC000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,5,80,80,0,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n',encoding='utf-8')
        return False
    try:
        sys.path.insert(0,str(ROOT/'reference_system'))
        from vox_content.captions import TimedCaption, write_timed_ass
        rows=_timed_scene_captions(path.parent,data,TimedCaption)
        if not rows:
            t=0.0
            for s in data.get('scenes',[]):
                dur=max(1.0,float(s.get('duration',5))); text=str(s.get('narration','')).strip()
                if text: rows.append(TimedCaption(t,min(t+dur,9999),text))
                t+=dur
        write_timed_ass(rows,path,preset='poetry_reference',caption_style='reference_cursive',video_format='portrait',signature_enabled=False)
        return True
    except Exception:
        return False

def calculate_speech_aligned_durations(project_dir: Path, data: dict, total_audio_dur: float) -> list[float]:
    timestamps_path = project_dir / 'timestamps.json'
    scenes = data.get('scenes', [])
    if not scenes:
        return []
    
    words = []
    if timestamps_path.exists():
        try:
            payload = json.loads(timestamps_path.read_text(encoding='utf-8-sig'))
            for row in payload:
                if isinstance(row, dict):
                    for w in row.get('words', []):
                        if isinstance(w, dict) and str(w.get('word', '')).strip():
                            words.append(w)
        except Exception:
            words = []

    if not words or len(scenes) <= 1:
        if total_audio_dur > 0 and len(scenes) > 0:
            return [max(3.0, total_audio_dur / len(scenes)) for _ in scenes]
        return [max(3.0, min(6.0, float(s.get('duration', 5)))) for s in scenes]

    scene_starts = []
    cursor = 0
    norm_words = [_norm_token(w.get('word', '')) for w in words]

    for s in scenes:
        narration = str(s.get('narration', '')).strip()
        tokens = [_norm_token(t) for t in _word_tokens(narration) if _norm_token(t)]
        if not tokens:
            scene_starts.append(float(words[cursor].get('start', 0.0)) if cursor < len(words) else 0.0)
            continue
        
        found_idx = cursor
        first_token = tokens[0]
        scan_limit = min(len(words), cursor + max(12, len(tokens) + 4))
        for i in range(cursor, scan_limit):
            if norm_words[i] == first_token:
                found_idx = i
                break
        
        scene_starts.append(float(words[found_idx].get('start', 0.0)))
        cursor = min(len(words) - 1, found_idx + len(tokens))

    durations = []
    for i in range(len(scenes)):
        start = scene_starts[i]
        if i + 1 < len(scenes):
            nxt_start = scene_starts[i + 1]
            dur = max(2.5, nxt_start - start)
        else:
            dur = max(2.5, total_audio_dur - start)
        durations.append(dur)

    sum_dur = sum(durations)
    if total_audio_dur > 0 and sum_dur > 0:
        scale = total_audio_dur / sum_dur
        durations = [round(max(2.0, d * scale), 3) for d in durations]

    return durations

def main(project):
    project=Path(project); data=json.loads((project/'project.json').read_text(encoding='utf-8-sig'))
    frames=project/'frames'; frames.mkdir(exist_ok=True)
    assets=scene_assets(project,data)
    audio=project/'audio'/'narration.wav'; render_audio=mastered_audio(audio)
    total_audio=_audio_duration(render_audio) if render_audio.exists() else 0.0
    durations=calculate_speech_aligned_durations(project, data, total_audio)
    if not durations:
        durations=[max(3.0,min(6.0,float(s.get('duration',5)))) for s in data.get('scenes',[])]
    captions=project/'captions.ass'; visible=write_simple_ass(data,captions)
    output=project/'final_voxcpm_match.mp4'
    titled_output=title_output_path(data)
    # Use the copied production renderer for every profile so the same smooth
    # 2.5D motion treatment is applied consistently. Nepali still receives an
    # empty caption track, and the low-VRAM fallback remains below this block.
    try:
        sys.path.insert(0,str(ROOT/'reference_system'))
        from vox_content.models import VisualAsset
        from vox_content.render import render as reference_render
        music=None
        music_root=ROOT/'assets'/'Whispr Bg music'
        exact_music=music_root/'audio [music] whisper background music.mp3'
        if exact_music.is_file(): music=exact_music
        elif music_root.is_file(): music=music_root
        elif music_root.is_dir():
            files=sorted(p for p in music_root.iterdir() if p.suffix.lower() in {'.wav','.mp3','.m4a','.aac','.flac'})
            music=files[0] if files else None
        overlay_dir=ROOT/'assets'/'overlays'
        overlay_files=sorted(p for p in overlay_dir.glob('*') if p.is_file() and p.suffix.lower() in {'.mp4','.mov','.webm'}) if overlay_dir.exists() else []
        preferred_overlay=overlay_dir/DEFAULT_OVERLAY_NAME
        overlay=preferred_overlay if preferred_overlay.is_file() else (overlay_files[0] if overlay_files else None)
        result=reference_render([VisualAsset(path=p) for p in assets],render_audio,captions,output,target_duration=sum(durations),preset='modern' if is_nepali(data) else 'poetry_reference',scene_durations=durations,video_format='portrait',overlay_path=overlay,overlay_opacity=OVERLAY_OPACITY if overlay else 0.0,music_path=music,music_volume=0.22 if music else 0.0,music_fade_seconds=3.0,motion_style='parallax_2_5d')
        exported=export_title_copy(result,data)
        return {'output':str(exported),'project_output':str(result),'scenes':len(assets),'caption_visible':visible,'renderer':'Nepali TTS reference system 2.5D' if is_nepali(data) else 'Nepali TTS reference system'}
    except Exception as e:
        (project/'production_render_error.txt').write_text(str(e),encoding='utf-8')
    # Stable fallback path for Nepali and missing optional source dependencies.
    if render_audio.exists() and sum(durations) > 0:
        scale=_audio_duration(render_audio)/sum(durations)
        durations=[max(1.0,d*scale) for d in durations]
    clips=[]
    for i,(image,dur) in enumerate(zip(assets,durations),1):
        clip=frames/f'{i:03d}.mp4'; vf='scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p'
        r=run(['ffmpeg','-y','-loop','1','-i',str(image),'-t',str(dur),'-vf',vf,'-an','-c:v','libx264','-preset','veryfast','-crf','22',str(clip)])
        if r.returncode: raise RuntimeError(r.stderr[-1200:])
        clips.append(clip)
    concat=frames/'concat.txt'; concat.write_text(''.join(f"file '{p.resolve().as_posix()}'\n" for p in clips),encoding='utf-8')
    silent=project/'final_silent.mp4'; r=run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(silent)])
    if r.returncode: raise RuntimeError(r.stderr[-1200:])
    args=['ffmpeg','-y','-i',str(silent)]
    if render_audio.exists(): args+=['-i',str(render_audio)]
    args+=['-c:v','libx264','-preset','veryfast','-crf','22']
    if render_audio.exists(): args+=['-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','192k','-shortest']
    args+=[str(output)]
    r=run(args)
    if r.returncode: raise RuntimeError(r.stderr[-1200:])
    exported=export_title_copy(output,data)
    return {'output':str(exported),'project_output':str(output),'scenes':len(assets),'caption_visible':visible,'renderer':'stable fallback'}

if __name__=='__main__': print(json.dumps(main(sys.argv[1]),ensure_ascii=False))

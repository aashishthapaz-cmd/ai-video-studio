import json, mimetypes, os, subprocess, threading, time, uuid, shutil, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re, hashlib, base64, io, importlib
from urllib.parse import quote_plus
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from bulk_poem import parse_bulk, make_project
from ltx_bridge import generate_clip
from news_sources import download_related
from artwork_prompts import generate_plan

ROOT=Path(__file__).resolve().parent; WORKSPACES=ROOT/'runtime'/'jobs'; WEB=ROOT/'web'; LOGS=ROOT/'logs'; PORT=int(os.environ.get('AI_VIDEO_PORT','18765'))
DEFAULT={'ollama_url':'http://127.0.0.1:11434','ollama_model':'llama3.2:3b','ollama_vision_model':'gemma3:4b','comfyui_url':'http://127.0.0.1:8188','comfyui_launch_path':'','comfyui_launch_args':'','comfyui_workdir':'','comfyui_python':'','tts':'windows','whisper_model':'small','image_workflow':'workflows/txt2img_api.json'}
SETTINGS=ROOT/'settings.json'
MUSIC_EXTS={'.mp3','.wav','.m4a','.aac','.flac','.ogg'}
VOICE_REFERENCE_DIR=ROOT/'assets'/'reference_voice'
POETRY_MUSIC_PATH=ROOT/'assets'/'Whispr Bg music'
ENGLISH_POETRY_REFERENCE=ROOT/'assets'/'reference_voice'/'whishper.wav'

def music_files():
    if POETRY_MUSIC_PATH.is_file(): return [POETRY_MUSIC_PATH]
    if POETRY_MUSIC_PATH.is_dir(): return sorted([p for p in POETRY_MUSIC_PATH.iterdir() if p.suffix.lower() in MUSIC_EXTS])
    return sorted([p for p in (ROOT/'assets').rglob('*') if p.is_file() and p.suffix.lower() in MUSIC_EXTS and 'music' in str(p).lower()])

def voice_reference_files():
    if not VOICE_REFERENCE_DIR.exists(): return []
    return sorted([p for p in VOICE_REFERENCE_DIR.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXTS], key=lambda p:p.name.lower())

JOBS={}
RESULTS={}
BATCHES={}
JOB_DIRS={}
# Heavy TTS/Whisper/ComfyUI/FFmpeg work must be serialized on an 8 GB GPU.
# Waiting jobs stay queued without starting competing model processes.
PIPELINE_LOCK=threading.Lock()
PROFILES={
 'documentary':{'voice_tone':'calm, intimate, natural documentary narration','pacing':'slow reflective pacing with 0.8 second pauses','image_style':'cinematic lo-fi painterly realism, atmospheric light, restrained color','animation_style':'subtle handheld drift and slow push-in'},
 'poetry':{'voice_tone':'warm, deep, emotional spoken-word delivery','pacing':'deliberate phrasing with a pause after each line','image_style':'lo-fi retro 90s aesthetic anime illustration, Studio Ghibli and Makoto Shinkai inspired, atmospheric digital painting, rich moody color palette, warm amber and deep midnight navy blue, subtle film grain, vertical 9:16','animation_style':'smooth meditative 3-5 second Ken Burns motion, slow push-in or lateral drift, subtle grain and gentle cross-fade, no jitter or morphing'},
 'reference_25d_parallax':{'voice_tone':'warm, intimate, reflective spoken-word delivery','pacing':'deliberate line-by-line pacing with quiet pauses','image_style':'minimalist hand-painted storybook illustration with visible ink and canvas grain, cinematic color pop, no text or logo','animation_style':'smooth 2.5D parallax-style drift, slow push-in, layered depth, subtle grain, no jitter'},
 'poetry_nepali':{'voice_tone':'warm, emotional Nepali spoken poetry with natural breaths and dramatic emphasis','pacing':'slow expressive line-by-line pacing with natural pauses','image_style':'lo-fi retro 90s aesthetic anime illustration, Studio Ghibli and Makoto Shinkai inspired, atmospheric digital painting, rich moody color palette, warm amber and deep midnight navy blue, subtle film grain, vertical 9:16','animation_style':'smooth 3-5 second meditative push-in or lateral drift, gentle grain, no jitter or morphing'},
 'news_nepali':{'voice_tone':'clear, confident Nepali news presentation','pacing':'fast but intelligible headline pacing with short pauses','image_style':'relevant editorial documentary photography or cinematic news illustration, clear subject, no text/logo/watermark','animation_style':'fast clean editorial push-ins, lateral movement, controlled cross-fades, no jitter'},
 'explainer_nepali':{'voice_tone':'शान्त, स्पष्ट र शिक्षाप्रद नेपाली व्याख्यात्मक आवाज','pacing':'स्पष्ट वाक्यगत गति र विषयअनुसार प्राकृतिक विराम','image_style':'cinematic explanatory hand-painted illustration, layered depth, strong subject clarity, rich but natural color, no text/logo/stamp','animation_style':'smooth explanatory push-in, gentle lateral drift, clean transitions, no jitter'},
 'story':{'voice_tone':'natural cinematic English storytelling','pacing':'clear conversational pacing with emotional pauses','image_style':'cinematic painterly illustration, expressive light, no text/logo','animation_style':'smooth slow push-in and cross-fade'},
 'motivational':{'voice_tone':'confident warm English motivational narration','pacing':'energetic but controlled emphasis with short pauses','image_style':'colorful cinematic painting, human-centered composition, no text/logo','animation_style':'smooth uplifting push-in and lateral drift'}
}
FORMATS={'portrait':(1080,1920),'landscape':(1920,1080)}

def estimate_project(data):
    scenes=len(data.get('scenes',[])); duration=sum(float(s.get('duration',5)) for s in data.get('scenes',[]))
    bypass=bool(data.get('bypass_i2v',False) or data.get('reference_25d_parallax',False))
    seconds=35+scenes*(24 if bypass else 42)+duration*(1.5 if bypass else 2.2)
    return {'scenes':scenes,'duration_seconds':round(duration,1),'estimated_seconds':round(seconds,0),'estimated_minutes':round(seconds/60,1)}

def stale_visual_prompt(prompt):
    text=str(prompt or '').strip().lower()
    if not text or text in {'.','no text','no watermark'}:
        return True
    required_markers=(
        'no text',
    )
    if any(marker not in text for marker in required_markers):
        return True
    stale_markers=(
        'same storefront layout',
        'same balcony',
        'may good things',
    )
    return any(marker in text for marker in stale_markers)

def apply_profile(data):
    profile=PROFILES.get(data.get('content_type','poetry'),PROFILES['poetry'])
    if any(stale_visual_prompt(s.get('prompt','')) for s in data.get('scenes',[])):
        try:
            orig_scenes=data.get('scenes',[])
            script=data.get('script') or '\n'.join(str(s.get('narration','')) for s in orig_scenes if str(s.get('narration','')).strip())
            planned=ollama_plan({**data,'script':script})
            if planned.get('scenes'):
                # STRICTLY preserve the user's original narration line for each scene
                for idx, ps in enumerate(planned['scenes']):
                    if idx < len(orig_scenes) and str(orig_scenes[idx].get('narration','')).strip():
                        ps['narration']=orig_scenes[idx]['narration']
                data.update({k:v for k,v in planned.items() if k!='scenes'})
                data['scenes']=planned['scenes']
        except Exception as e:
            log(data.get('name') or data.get('title') or 'project','Prompt planning fallback failed: '+str(e))
    data['voice_tone']=profile['voice_tone']; data['pacing']=profile['pacing']; data['image_style']=profile['image_style']; data['animation_style']=profile['animation_style']
    # Current reference-production mode: bypass LTX for every one-click render.
    # Re-enable later by setting use_i2v=True and removing bypass_i2v/reference_25d_parallax.
    data['use_i2v']=False
    data['bypass_i2v']=True
    data['reference_25d_parallax']=True
    project_key=str(data.get('name') or data.get('title') or time.time())
    for i,s in enumerate(data.get('scenes',[]),1):
        base=str(s.get('prompt','')).strip()
        if not base:
            base='soulful poetic atmospheric scene matching this line: '+str(s.get('narration','')).strip()
        low=base.lower()
        if 'lo-fi retro 90s' not in low and 'atmospheric digital painting' not in low and 'anime' not in low:
            base=base.rstrip(' .')+'. '+data['image_style']
        if not s.get('seed'):
            seed_src=f"{project_key}|{i}|{s.get('narration','')}|{time.time_ns()}"
            s['seed']=int(hashlib.sha256(seed_src.encode('utf-8','ignore')).hexdigest()[:12],16) % 1000000000
        guard='Atmospheric mood, cinematic color grading, deeply evocative composition with poetic negative space, professional fine-art quality. No text, no writing, no signs, no labels, no logos, no watermark.'
        s['prompt']=(base.rstrip(' .')+'. '+guard).strip(); s['animation_prompt']=data['animation_style']+'. Preserve the composition and mood; no flicker, no black frames.'
    return data
VOX_ROOT=Path(r'D:\VoxCPM Content Factory')
VOX_PY=VOX_ROOT/'.venv'/'Scripts'/'python.exe'
WHISPER_PY_CANDIDATES=[
    Path(r'D:\Nepali TTS\.venv\Scripts\python.exe'),
    Path(r'D:\Captionize\.venv\Scripts\python.exe'),
]
WHISPER_SITE_PACKAGES=[
    Path(r'D:\Nepali TTS\.venv\Lib\site-packages'),
    Path(r'D:\Captionize\.venv\Lib\site-packages'),
]

def set_progress(name,stage,percent,state='running',detail=''):
    key=Path(name).name; now=time.time(); old=JOBS.get(key,{})
    started=old.get('started',now); estimate=old.get('estimate',estimate_project(project(key)).get('estimated_seconds',90))
    JOBS[key]={'stage':stage,'percent':percent,'state':state,'detail':detail,'updated':now,'started':started,'estimate':estimate,'elapsed':round(now-started,1),'remaining':0 if state in ('done','error') else round(max(0,estimate-(now-started)),1)}

def start_job(name):
    key=Path(name).name; JOBS[key]={'stage':'starting','percent':0,'state':'running','detail':'Preparing automatic profile','updated':time.time(),'started':time.time(),'estimate':estimate_project(project(key)).get('estimated_seconds',90)}

def workspace(name):
    key=Path(name).name
    return JOB_DIRS.get(key, WORKSPACES/key)


def settings():
    try:return {**DEFAULT,**json.loads(SETTINGS.read_text(encoding='utf-8-sig'))}
    except:return DEFAULT.copy()
def req(url,method='GET',data=None,timeout=8,retries=2):
    body=json.dumps(data).encode() if data is not None else None
    last=None
    for attempt in range(retries+1):
        try:
            r=Request(url,data=body,method=method,headers={'Content-Type':'application/json'})
            with urlopen(r,timeout=timeout) as x:return json.loads(x.read().decode())
        except Exception as e:
            last=e
            if attempt>=retries: break
            time.sleep(0.5*(attempt+1))
    raise last
def comfyui_online():
    try:
        s=settings()
        req(s['comfyui_url']+'/system_stats',timeout=3,retries=0)
        return True
    except Exception:
        return False
def launch_comfyui_background():
    s=settings()
    launch_path=str(s.get('comfyui_launch_path','')).strip()
    launch_args=str(s.get('comfyui_launch_args','')).strip()
    workdir=str(s.get('comfyui_workdir','')).strip()
    if not launch_path:
        return False, 'No ComfyUI launch path configured'
    path=Path(launch_path)
    if not path.exists():
        return False, f'ComfyUI launch path not found: {path}'
    cwd=str(Path(workdir)) if workdir else str(path.parent if path.is_file() else path)
    args=[]
    if path.is_dir():
        main_py=path/'main.py'
        if not main_py.exists():
            return False, f'ComfyUI main.py not found in: {path}'
        python_exe=str(s.get('comfyui_python','')).strip()
        if not python_exe:
            for candidate in (
                path/'python_embeded'/'python.exe',
                path/'python'/'python.exe',
                path/'venv'/'Scripts'/'python.exe',
            ):
                if candidate.exists():
                    python_exe=str(candidate)
                    break
        if not python_exe:
            python_exe=os.environ.get('PYTHON','python')
        args=[python_exe,str(main_py)]
    elif path.suffix.lower() == '.bat':
        args=['cmd','/c',str(path)]
    else:
        args=[str(path)]
    if launch_args:
        args.extend(launch_args.split())
    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    subprocess.Popen(args,cwd=cwd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,creationflags=creationflags)
    return True, 'ComfyUI started in the background'
def ensure_comfyui_ready():
    if comfyui_online():
        return {'online':True,'started':False,'message':'ComfyUI already online'}
    started=False; message='ComfyUI was offline'
    try:
        started,message=launch_comfyui_background()
    except Exception as e:
        return {'online':False,'started':False,'message':str(e)}
    if not started:
        return {'online':False,'started':False,'message':message}
    for _ in range(60):
        if comfyui_online():
            return {'online':True,'started':True,'message':'ComfyUI is ready'}
        time.sleep(2)
    return {'online':False,'started':True,'message':'ComfyUI did not become ready in time'}
def save_json(path,obj):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(path)

def projects():
    WORKSPACES.mkdir(parents=True, exist_ok=True); return sorted(p.name for p in WORKSPACES.iterdir() if p.is_dir())
def output_files():
    out=ROOT/'Output'; out.mkdir(parents=True,exist_ok=True)
    return [{'filename':p.name,'output':str(p),'size':p.stat().st_size} for p in sorted(out.glob('*.mp4'),key=lambda x:x.stat().st_mtime,reverse=True)]

def unload_ollama(url=None):
    base = url or settings().get('ollama_url', 'http://127.0.0.1:11434')
    try:
        req = Request(f"{base.rstrip('/')}/api/ps")
        with urlopen(req, timeout=2) as r:
            running = json.loads(r.read().decode()).get('models', [])
        for m in running:
            name = m.get('name') or m.get('model')
            if name:
                req_data = json.dumps({'model': name, 'keep_alive': 0}).encode()
                gen_req = Request(f"{base.rstrip('/')}/api/generate", data=req_data, headers={'Content-Type': 'application/json'})
                with urlopen(gen_req, timeout=2) as res:
                    pass
    except Exception:
        pass

def free_comfyui_vram(url=None):
    base = url or settings().get('comfyui_url', 'http://127.0.0.1:8188')
    try:
        req = Request(f"{base.rstrip('/')}/free", data=json.dumps({'unload_models': True, 'free_memory': True}).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=2) as res:
            pass
    except Exception:
        pass

def project(name):
    p=workspace(name)/'project.json'
    try:return json.loads(p.read_text(encoding='utf-8-sig'))
    except:return {'title':Path(name).name,'scenes':[]}
def log(name,text):
    LOGS.mkdir(exist_ok=True); (LOGS/(Path(name).name+'.log')).open('a',encoding='utf8').write(text+'\n')
def ps_tts(text,out,language='auto',reference_audio='',style_instruction='',payload_path=None):
    bridge=ROOT/'voxcpm_bridge.py'
    out_path = Path(out)
    payload = Path(payload_path) if payload_path else (out_path.parent.parent/'voxcpm_request.json' if out_path.parent.name=='audio' else ROOT/'logs'/'voxcpm_request.json')
    request={'text':text,'output':str(out_path),'language':language}
    if reference_audio and Path(reference_audio).exists(): request['reference_audio']=str(reference_audio)
    if style_instruction: request['style_instruction']=style_instruction
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps(request,ensure_ascii=False),encoding='utf8')
    py=VOX_PY if VOX_PY.exists() else None
    if py:
        unload_ollama()
        free_comfyui_vram()
        return subprocess.run([str(py),str(bridge),str(payload)],capture_output=True,text=True,timeout=900)
    script=f"Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile('{str(out_path).replace(chr(39),chr(39)+chr(39))}'); $s.Speak('{text.replace(chr(39),chr(39)+chr(39))}'); $s.Dispose()"
    return subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],capture_output=True,text=True)
def ollama_plan(data):
    # Reload the local planner so prompt/style changes apply without stale
    # in-memory modules after the manager has been running for a long time.
    import artwork_prompts as planner
    planner = importlib.reload(planner)
    plan = planner.generate_plan(data, settings())
    try: unload_ollama()
    except Exception: pass
    return plan

def replace_workflow(x,prompt,seed):
    if isinstance(x,dict):return {k:replace_workflow(v,prompt,seed) for k,v in x.items()}
    if isinstance(x,list):return [replace_workflow(v,prompt,seed) for v in x]
    if isinstance(x,str):
        if '__PROMPT__' in x:return x.replace('__PROMPT__',prompt)
        if '__SEED__' in x:return x.replace('__SEED__',str(seed))
    return x
def retry_call(fn, attempts=3, delay=1.0):
    last=None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last=e
            if i+1<attempts:
                time.sleep(delay*(i+1))
    raise last
def schedule_shutdown():
    if os.name != 'nt':
        raise RuntimeError('Automatic shutdown is only supported on Windows')
    try:
        subprocess.Popen(['shutdown','/s','/t','60','/c','AI Video Factory finished all queued jobs'])
        return True
    except Exception as e:
        raise RuntimeError(f'Could not schedule shutdown: {e}')
def comfy_image(scene,name):
    s=settings(); wf=ROOT/s['image_workflow']
    if not wf.exists():raise FileNotFoundError(f'Missing workflow: {wf}')
    payload=replace_workflow(json.loads(wf.read_text(encoding='utf-8-sig')),scene.get('prompt',''),scene.get('seed',int(time.time())))
    q=req(s['comfyui_url']+'/prompt','POST',{'prompt':payload,'client_id':'ai-video-factory-'+uuid.uuid4().hex},20); pid=q['prompt_id']
    def fetch_image():
        for _ in range(240):
            time.sleep(1)
            h=req(s['comfyui_url']+'/history/'+pid,timeout=10)
            if pid not in h:continue
            outputs=h[pid].get('outputs',{})
            for node in outputs.values():
                for im in node.get('images',[]):
                    u=s['comfyui_url']+'/view?filename='+im['filename']+'&subfolder='+im.get('subfolder','')+'&type='+im.get('type','output')
                    raw=urlopen(u,timeout=30).read(); out=workspace(name)/'assets'; out.mkdir(parents=True,exist_ok=True)
                    target=out/(scene['id']+'.png'); target.write_bytes(raw); return str(target)
        raise TimeoutError('ComfyUI image generation timed out')
    return retry_call(fetch_image, attempts=3, delay=2.0)
def generate_all(name):
    data=project(name); made=[]
    for scene in data.get('scenes',[]):
        made.append(comfy_image(scene,name)); log(name,'ComfyUI generated '+scene.get('id','scene'))
    try: free_comfyui_vram()
    except Exception: pass
    return {'ok':True,'images':made}

def generate_i2v_all(name):
    data=project(name); s=settings(); wf=ROOT/'workflows'/'ltx25_i2v_api.json'; out=workspace(name)/'clips'; clips=[]
    if not wf.exists(): raise FileNotFoundError(f'Missing LTX workflow: {wf}')
    for i,scene in enumerate(data.get('scenes',[]),1):
        image=workspace(name)/'assets'/(scene.get('id','scene')+'.png')
        if not image.exists(): image=workspace(name)/'assets'/(scene.get('id','scene')+'.jpg')
        if not image.exists(): raise FileNotFoundError(f'Missing scene image: {image}')
        clips.append(generate_clip(s['comfyui_url'],wf,image,scene.get('animation_prompt',scene.get('prompt','')),out,float(scene.get('duration',5)),int(scene.get('seed',i))))
        log(name,'LTX generated '+scene.get('id','scene'))
    try: free_comfyui_vram()
    except Exception: pass
    return {'ok':True,'clips':clips}

def nepali_lines(script):
    return [x.strip() for x in re.split(r'(?<=[.!?।॥])\s+|\n+', script or '') if x.strip()]
def ollama_vision_relevance(image_path, headline):
    s=settings(); model=s.get('ollama_vision_model') or s.get('ollama_model','gemma3:4b')
    try:
        image_b64=base64.b64encode(Path(image_path).read_bytes()).decode('ascii')
        prompt='''Evaluate whether this image is visually relevant to the news headline. Return JSON only: {"score":0.0,"reason":"short reason","subjects":["..."]}. Score 1.0 when the image clearly depicts the headline topic, location, people, event, or named object; score 0.0 when unrelated, decorative, corrupted, or not a real news/editorial image. Do not infer facts not visible in the image. HEADLINE: '''+headline
        r=req(s['ollama_url']+'/api/generate','POST',{'model':model,'prompt':prompt,'images':[image_b64],'stream':False,'format':'json','options':{'temperature':0}},90)
        raw=r.get('response','{}'); out=json.loads(raw); out['status']='checked'; return {'score':float(out.get('score',0.0)),'reason':out.get('reason',''),'status':'checked','subjects':out.get('subjects',[])}
    except Exception as e:
        log('news_vision','Vision check unavailable: '+str(e)); return {'score':0.55,'status':'unavailable','reason':str(e)}

def create_content_project(name, title, script, content_type):
    slug=re.sub(r'[^a-z0-9]+','_',name.lower()).strip('_') or 'nepali_content'
    q=WORKSPACES/slug
    JOB_DIRS[slug]=q
    for folder in ('assets','audio','frames','outputs','sources'): (q/folder).mkdir(parents=True,exist_ok=True)
    lines=nepali_lines(script); scenes=[]
    for i,line in enumerate(lines,1):
        scenes.append({'id':f'scene_{i:03d}','duration':max(3.0,min(5.0,round(max(3.0,len(line.split())/2.2),2))),'narration':line,'prompt':'','motion':'slow_push_in','image_query':(title or line)[:180] if content_type=='news_nepali' else line[:180]})
    data={'title':title or slug,'language':'ne','content_type':content_type,'caption_style':'reference_yellow_center_pop','use_i2v':False,'bypass_i2v':True,'reference_25d_parallax':True,'scenes':scenes}
    save_json(q/'project.json',data); return data

def wikimedia_image(query, target):
    api='https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=1&gsrsearch='+quote_plus(query)+'&prop=imageinfo&iiprop=url|mime&iiurlwidth=1600&format=json'
    request=Request(api,headers={'User-Agent':'AI-Video-Factory/1.0'})
    with urlopen(request,timeout=30) as r: data=json.loads(r.read().decode('utf-8','replace'))
    pages=data.get('query',{}).get('pages',{}); page=next(iter(pages.values()),None)
    info=(page or {}).get('imageinfo',[{}])[0]; url=info.get('thumburl') or info.get('url')
    source='Wikimedia Commons'; title=(page or {}).get('title','')
    if not url:
        ov='https://api.openverse.org/v1/images/?q='+quote_plus(query)+'&page_size=1'
        with urlopen(Request(ov,headers={'User-Agent':'AI-Video-Factory/1.0'}),timeout=30) as r: od=json.loads(r.read().decode('utf-8','replace'))
        item=(od.get('results') or [{}])[0]; url=item.get('thumbnail') or item.get('url'); source='Openverse'; title=item.get('title','')
    if not url: raise FileNotFoundError('No openly licensed image found for: '+query)
    raw=urlopen(Request(url,headers={'User-Agent':'AI-Video-Factory/1.0'}),timeout=45).read(); target.write_bytes(raw)
    return {'query':query,'url':url,'title':title,'source':source,'license':item.get('license') if source=='Openverse' else 'see source URL','local_file':str(target)}

def download_news_images(name):
    data=project(name); q=workspace(name); sources=[]; used_hashes=set(); failures=[]
    for index,scene in enumerate(data.get('scenes',[])):
        headline=(data.get('headline') or data.get('title') or '').strip()
        query=(scene.get('news_query') or headline or scene.get('image_query') or scene.get('narration','')[:160]).strip()
        target=q/'assets'/(scene.get('id','scene')+'.jpg')
        try:
            record=download_related(query,target,used_hashes,index,lambda path,qry: ollama_vision_relevance(path, headline or qry))
            sources.append(record); scene['source_type']=record.get('source'); scene['image_source_url']=record.get('url'); scene['image_source_license']=record.get('license')
        except Exception as e:
            scene['image_download_error']=str(e); failures.append({'scene':scene.get('id'), 'query':query, 'error':str(e)}); log(name,'News image failed: '+str(e))
    save_json(q/'project.json',data); save_json(q/'sources'/'image_sources.json',sources); save_json(q/'sources'/'image_failures.json',failures)
    return {'ok':len(failures)==0,'downloaded':len(sources),'failed':len(failures),'sources':sources,'failures':failures}

def transcribe(name):
    s=settings(); q=workspace(name); audio=q/'audio'/'narration.wav'
    if not audio.exists(): raise FileNotFoundError(f'Missing narration file: {audio}')
    rows=[]
    try:
        for site in WHISPER_SITE_PACKAGES:
            if site.exists() and str(site) not in sys.path:
                sys.path.insert(0,str(site))
        from faster_whisper import WhisperModel
        model=WhisperModel(s.get('whisper_model','small'), device='cpu', compute_type='int8', cpu_threads=4)
        segments,_=model.transcribe(str(audio), word_timestamps=True, vad_filter=False, beam_size=3)
        for seg in segments:
            rows.append({'start':seg.start,'end':seg.end,'text':seg.text.strip(),'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (seg.words or []) if str(w.word).strip()]})
    except Exception as local_error:
        out=q/'timestamps.json'
        bridge=ROOT/'whisper_bridge.py'
        for py in WHISPER_PY_CANDIDATES:
            if not py.exists(): continue
            r=subprocess.run([str(py),str(bridge),str(audio),str(out),s.get('whisper_model','small')],capture_output=True,text=True,timeout=900)
            if r.returncode==0 and out.exists():
                rows=json.loads(out.read_text(encoding='utf-8-sig'))
                break
        if not rows:
            raise RuntimeError('Whisper unavailable: '+str(local_error))
    srt=[]
    for i,row in enumerate(rows,1):
        text=str(row.get('text','')).strip()
        def ts(v):
            ms=int(round(v*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); sec,ms=divmod(ms,1000); return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'
        srt.append(f'{i}\n{ts(float(row.get("start",0)))} --> {ts(float(row.get("end",0)))}\n{text}\n')
    (q/'timestamps.json').write_text(json.dumps(rows,indent=2),encoding='utf8'); (q/'subtitles.srt').write_text('\n'.join(srt),encoding='utf8'); return {'ok':True,'segments':len(rows),'timestamps':str(q/'timestamps.json')}

def cleanup_project(name):
    q=workspace(name); removed=[]
    for folder in ('frames','raw','temp','tmp','intermediates'):
        p=q/folder
        if p.exists():
            import shutil
            shutil.rmtree(p,ignore_errors=True); removed.append(folder)
    for p in q.rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.tmp','.part','.bak'):
            try:p.unlink(); removed.append(str(p.relative_to(q)))
            except:pass
    return removed

def build(name):
    projectdir=workspace(name); renderer=ROOT/'engine'/'build_video.py'
    if not renderer.exists():renderer=ROOT/'build_video.py'
    if not renderer.exists():renderer=ROOT/'build_video.py'
    if not renderer.exists():raise FileNotFoundError('Renderer missing')
    with (LOGS/(Path(name).name+'.log')).open('a',encoding='utf8') as f:
        proc=subprocess.Popen(['python',str(renderer),str(projectdir)],cwd=str(ROOT),stdout=f,stderr=subprocess.STDOUT)
    return proc

def run_pipeline(name, auto_shutdown=False):
    acquired=False
    try:
        set_progress(name,'queued',5,'running','Waiting for the shared GPU pipeline slot')
        PIPELINE_LOCK.acquire(); acquired=True
        data=apply_profile(project(name)); save_json(workspace(name)/'project.json',data)
        lines=[str(s.get('narration','')).strip() for s in data.get('scenes',[]) if str(s.get('narration','')).strip()]
        text='\n'.join(line if line.endswith(('.', '!', '?', '...')) else line + '...' for line in lines)
        set_progress(name,'voice generation',10,'running','Generating optimized VoxCPM narration')
        q=workspace(name)/'audio'; q.mkdir(parents=True,exist_ok=True)
        reference=str(ENGLISH_POETRY_REFERENCE) if data.get('content_type')=='poetry' and data.get('language','en') not in ('ne','nepali') else ''
        payload_file=workspace(name)/'voxcpm_request.json'
        r=ps_tts(text,q/'narration.wav',data.get('language','auto'),reference,'slow intimate emotional spoken-word poetry, natural breaths, deliberate line pauses, gentle emphasis, reflective and warm',payload_path=payload_file)
        if r.returncode!=0 or not (q/'narration.wav').exists() or (q/'narration.wav').stat().st_size<1000:
            err_msg=''
            try:
                parsed=json.loads((r.stdout or '').strip())
                if not parsed.get('ok') and parsed.get('error'): err_msg=parsed['error']
            except Exception: pass
            if not err_msg:
                for line in (r.stderr or '').splitlines():
                    line=line.strip()
                    if line.startswith('{') and 'error' in line:
                        try:
                            parsed=json.loads(line)
                            if parsed.get('error'): err_msg=parsed['error']; break
                        except Exception: pass
            if not err_msg:
                clean_lines=[l for l in (r.stderr or '').splitlines() if 'FutureWarning' not in l and 'Running on device' not in l and 'Loading AudioVAE' not in l and 'voxcpm_model_path' not in l and 'WeightNorm' not in l]
                err_msg='\n'.join(clean_lines[-6:]).strip() or (r.stderr[-300:].strip() if r.stderr else 'Voice synthesis process failed')
            raise RuntimeError(f"Voice generation failed: {err_msg}")
        set_progress(name,'voice generation',25,'done','Narration ready'); set_progress(name,'Whisper timing',30,'running','Creating word timings')
        try: transcribe(name); timing_detail='Word timings ready'
        except Exception as timing_error:
            timing_detail='Whisper unavailable; using scene timing fallback: '+str(timing_error)
            elapsed=0.0; rows=[]
            for s in data.get('scenes',[]):
                dur=float(s.get('duration',5)); rows.append({'start':elapsed,'end':elapsed+dur,'text':s.get('narration',''),'words':[]}); elapsed+=dur
            (workspace(name)/'timestamps.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
        set_progress(name,'Whisper timing',40,'done',timing_detail)
        set_progress(name,'image generation',45,'running','Using downloaded news images' if data.get('content_type')=='news_nepali' else 'Generating scene images with ComfyUI')
        if data.get('content_type')!='news_nepali': generate_all(name)
        else:
            existing=sum(1 for s in data.get('scenes',[]) if any((workspace(name)/'assets'/(s.get('id','scene')+ext)).exists() for ext in ('.jpg','.jpeg','.png')))
            if existing<len(data.get('scenes',[])): raise FileNotFoundError('News images missing; run Download news images first')
        set_progress(name,'image generation',70,'done','Images ready')
        if data.get('use_i2v',False): set_progress(name,'image-to-video',78,'running','LTX is animating scene images'); generate_i2v_all(name); set_progress(name,'image-to-video',84,'done','Animated clips ready')
        set_progress(name,'rendering',85,'running','FFmpeg is rendering captions and audio')
        proc=build(name); code=proc.wait()
        if code!=0: raise RuntimeError('FFmpeg render exited with code '+str(code))
        if auto_shutdown:
            try: schedule_shutdown()
            except Exception as shutdown_error: log(name,'Shutdown scheduling failed: '+str(shutdown_error))
        set_progress(name,'complete',100,'done','Final video exported to Output')
        return True
    except Exception as e:
        set_progress(name,'error',100,'error',str(e)); log(name,'ERROR: '+str(e)); return False
    finally:
        if acquired: PIPELINE_LOCK.release()
        # Keep failed workspaces for inspection; successful jobs can be cleaned up.
        if JOBS.get(Path(name).name,{}).get('state') == 'done':
            try: shutil.rmtree(workspace(name),ignore_errors=True)
            except Exception: pass

def run_bulk_entries(entries):
    for entry in entries:
        work=make_project(entry,WORKSPACES); name=Path(work).name; JOB_DIRS[name]=work; start_job(name)
        run_pipeline(name)
def run_bulk_batch(entries, auto_shutdown=False):
    failures=0
    last_name=''
    for entry in entries:
        try:
            work=make_project(entry,WORKSPACES)
            name=Path(work).name
            JOB_DIRS[name]=work
            start_job(name)
            last_name=name
            run_pipeline(name)
        except Exception as e:
            failures+=1
            log(entry.get('title','batch'),'BATCH ERROR: '+str(e))
    if auto_shutdown:
        try:
            schedule_shutdown()
        except Exception as e:
            log(last_name or 'batch', 'Shutdown scheduling failed: ' + str(e))
    return failures

def service_status():
    s=settings(); out={'settings':s,'ollama':{'online':False},'comfyui':{'online':False},'whisper':{'available':False},'tts':{'available':False}}
    try:
        r=req(s['ollama_url']+'/api/tags',timeout=2,retries=0)
        out['ollama']={'online':True,'models':[x.get('name') for x in r.get('models',[])]}
    except Exception as e:out['ollama']['error']=str(e)
    try:
        r=req(s['comfyui_url']+'/system_stats',timeout=2,retries=0)
        out['comfyui']={'online':True,'version':r.get('system',{}).get('comfyui_version'),'devices':r.get('devices',[])}
    except Exception as e:out['comfyui']['error']=str(e)
    try:
        import importlib.util
        ok=importlib.util.find_spec('faster_whisper') is not None
        out['whisper']={'available':ok,'engine':'faster-whisper' if ok else None}
    except Exception as e:out['whisper']['error']=str(e)
    out['tts']={'available':os.name=='nt','engine':'Windows SpeechSynthesizer'}
    return out

class H(BaseHTTPRequestHandler):
    def j(self,x,status=200):
        b=json.dumps(x).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/api/music':return self.j({'default':str(music_files()[0]) if music_files() else '', 'files':[{'name':x.name,'path':str(x)} for x in music_files()]})
        if p=='/api/voice-references':return self.j({'files':[{'name':x.name,'path':str(x)} for x in voice_reference_files()]})
        if p=='/api/projects':return self.j({'projects':projects()})
        if p=='/api/status':
            recent_logs = sorted(LOGS.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True)[:10] if LOGS.exists() else []
            return self.j({'projects':projects(),'services':service_status(),'progress':JOBS,'results':RESULTS,'outputs':output_files(),'logs':[{'name':x.stem,'log':x.read_text(encoding='utf8',errors='ignore')[-3000:]} for x in recent_logs]})
        if p=='/api/settings':return self.j(settings())
        if p.startswith('/api/project/'):return self.j(project(p.split('/')[-1]))
        if p.startswith('/api/video/'):
            f=ROOT/'Output'/(Path(p.split('/')[-1]).name+'.mp4')
            if f.exists():
                b=f.read_bytes();self.send_response(200);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        f=WEB/('index.html' if p in ('','/') else p.lstrip('/'))
        if f.exists():
            b=f.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'text/plain');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        self.send_error(404)
    def do_POST(self):
        p=urlparse(self.path).path; n=int(self.headers.get('Content-Length','0')); d=json.loads(self.rfile.read(n) or '{}')
        try:
            if p=='/api/settings':SETTINGS.write_text(json.dumps({**settings(),**d},indent=2),encoding='utf8');return self.j({'ok':True})
            if p=='/api/render-bulk':
                text=str(d.get('text','')).strip(); entries=parse_bulk(text); auto_shutdown=bool(d.get('auto_shutdown',False))
                names=[]
                used=set()
                for entry in entries:
                    base_slug=re.sub(r'[^a-z0-9]+','_',entry['title'].lower()).strip('_') or f"poem_{entry['number']:03d}"
                    slug=base_slug
                    suffix=2
                    while slug in used or (WORKSPACES/slug).exists():
                        slug=f"{base_slug}_{suffix:02d}"
                        suffix+=1
                    used.add(slug)
                    names.append(slug)
                def run_batch():
                    run_bulk_batch(entries, auto_shutdown=auto_shutdown)
                threading.Thread(target=run_batch,daemon=True).start()
                return self.j({'ok':True,'names':names,'count':len(names),'started':True,'message':'Batch started in background'})
            if p=='/api/bulk':
                text=d.get('text',''); rows=parse_bulk(text); made=[str(make_project(x,WORKSPACES)) for x in rows]; return self.j({'ok':True,'projects':made,'count':len(made)})
            if p=='/api/profile':
                typ=d.get('content_type','poetry'); return self.j({'content_type':typ,**PROFILES.get(typ,PROFILES['poetry'])})
            if p=='/api/news/create':
                name=Path(d.get('name','nepali_news')).name; data=create_content_project(name,d.get('title','Nepali News'),d.get('script',''),'news_nepali'); return self.j({'ok':True,'name':name,'project':data,'next':'POST /api/news/download-images'})
            if p=='/api/news/download-images':
                r=download_news_images(d['name']); return self.j(r)
            if p=='/api/explainer/create':
                name=Path(d.get('name','nepali_explainer')).name; data=create_content_project(name,d.get('title','Nepali Explainer'),d.get('script',''),'explainer_nepali'); return self.j({'ok':True,'name':name,'project':data,'next':'POST /api/explainer/plan'})
            if p=='/api/explainer/plan':
                name=Path(d.get('name','nepali_explainer')).name; base=project(name); plan=ollama_plan({'content_type':'explainer_nepali','language':'ne','script':d.get('script') or ' '.join(x.get('narration','') for x in base.get('scenes',[]))}); base.update(plan); base['content_type']='explainer_nepali'; base['language']='ne'; base['use_i2v']=False; base['bypass_i2v']=True; base['reference_25d_parallax']=True
                for s in base.get('scenes',[]):
                    if not str(s.get('prompt','')).strip(): s['prompt']='cinematic visual interpretation of '+s.get('narration','')+', clear subject, layered depth, expressive lighting, portrait 9:16, no text'
                q=workspace(name); JOB_DIRS[name]=q; save_json(q/'project.json',base); return self.j({'ok':True,'name':name,'project':base})
            if p=='/api/cleanup':
                removed=cleanup_project(d['name']); return self.j({'ok':True,'removed':removed,'count':len(removed)})
            if p=='/api/estimate':
                return self.j({'ok':True,**estimate_project(project(d['name']))})
            if p=='/api/render-one-click':
                name=Path(d['name']).name
                auto_shutdown=bool(d.get('auto_shutdown',False))
                comfy_ready=ensure_comfyui_ready()
                if not comfy_ready.get('online'):
                    return self.j({'ok':False,'error':'ComfyUI is not available: '+comfy_ready.get('message','unknown error')},503)
                if JOBS.get(name,{}).get('state')=='running': return self.j({'ok':False,'busy':True,'error':'This project is already rendering'},409)
                start_job(name)
                threading.Thread(target=lambda: run_pipeline(name, auto_shutdown=auto_shutdown),daemon=True).start()
                return self.j({'ok':True,'estimate':estimate_project(project(name))})
            if p=='/api/batch-status':
                return self.j(BATCHES.get(str(d.get('batch_id','')),{'state':'unknown'}))
            if p=='/api/project':
                name=Path(d.get('name','new_project')).name; q=workspace(name); JOB_DIRS[name]=q; (q/'assets').mkdir(parents=True,exist_ok=True);(q/'audio').mkdir(exist_ok=True);(q/'outputs').mkdir(exist_ok=True);save_json(q/'project.json',d.get('project',{'title':name,'scenes':[]}));return self.j({'ok':True,'name':name})
            if p=='/api/save':
                q=workspace(d['name']); JOB_DIRS[Path(d['name']).name]=q; q.mkdir(parents=True,exist_ok=True);save_json(q/'project.json',d['project']);return self.j({'ok':True})
            if p=='/api/build':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); start_job(name); set_progress(name,'rendering',85,'running','FFmpeg is rendering the final video'); build(name); return self.j({'ok':True,'started':True,'message':'Render started in background'})
            if p=='/api/plan':
                name=Path(d.get('name','current')).name
                if JOBS.get(name,{}).get('state')=='running': return self.j({'ok':False,'busy':True,'error':f'{JOBS[name].get("stage","A pipeline job")} is active'},409)
                JOB_DIRS.setdefault(name, workspace(name)); start_job(name); set_progress(name,'script planning',10,'running','Ollama is analyzing the script')
                def plan_job():
                    try:
                        r=ollama_plan(d); RESULTS[name]=r; set_progress(name,'script planning',20,'done','Scene plan ready')
                    except Exception as e:set_progress(name,'script planning',100,'error',str(e))
                threading.Thread(target=plan_job,daemon=True).start(); return self.j({'ok':True,'started':True,'message':'Planning started in background'})
            if p=='/api/tts':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); set_progress(name,'voice generation',35,'running','VoxCPM is generating narration')
                q=workspace(name)/'audio';q.mkdir(parents=True,exist_ok=True);r=ps_tts(d.get('text',''),q/'narration.wav',d.get('language','auto')); ok=r.returncode==0;set_progress(name,'voice generation',45,'done' if ok else 'error',r.stderr[-500:]);return self.j({'ok':ok,'error':r.stderr})
            if p=='/api/whisper':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); set_progress(name,'Whisper timing',55,'running','Transcribing narration'); r=transcribe(name); set_progress(name,'Whisper timing',60,'done','Timestamps ready'); return self.j(r)
            if p=='/api/comfy/generate':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); return self.j({'ok':True,'image':comfy_image(d['scene'],name)})
            if p=='/api/comfy/generate-all':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); comfy_ready=ensure_comfyui_ready()
                if not comfy_ready.get('online'): return self.j({'ok':False,'error':'ComfyUI is not available: '+comfy_ready.get('message','unknown error')},503)
                set_progress(name,'image generation',65,'running','ComfyUI is generating scene images'); r=generate_all(name); set_progress(name,'image generation',75,'done','Scene images ready'); return self.j(r)
            if p=='/api/comfy/generate-i2v':
                name=Path(d['name']).name; JOB_DIRS.setdefault(name, workspace(name)); comfy_ready=ensure_comfyui_ready()
                if not comfy_ready.get('online'): return self.j({'ok':False,'error':'ComfyUI is not available: '+comfy_ready.get('message','unknown error')},503)
                set_progress(name,'image-to-video',78,'running','LTX is animating scene images'); r=generate_i2v_all(name); set_progress(name,'image-to-video',84,'done','Animated clips ready'); return self.j(r)
        except Exception as e:return self.j({'error':str(e)},500)
        self.send_error(404)
    def log_message(self,*a):pass

if __name__=='__main__': print(f'AI Video Factory: http://127.0.0.1:{PORT}');ThreadingHTTPServer(('127.0.0.1',PORT),H).serve_forever()


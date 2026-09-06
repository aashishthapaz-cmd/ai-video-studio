import json, mimetypes, time, uuid, subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def post_json(url, data, timeout=30):
    b=json.dumps(data).encode(); r=Request(url,data=b,method='POST',headers={'Content-Type':'application/json'})
    try:
        with urlopen(r,timeout=timeout) as x:return json.loads(x.read().decode())
    except HTTPError as e:
        detail=e.read().decode('utf-8','replace')
        raise RuntimeError(f'ComfyUI HTTP {e.code}: {detail}') from e


def upload_image(base, image):
    image=Path(image); boundary='----AIVideo'+uuid.uuid4().hex
    raw=image.read_bytes(); name=image.name
    head=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: {mimetypes.guess_type(name)[0] or "image/png"}\r\n\r\n').encode()
    body=head+raw+f'\r\n--{boundary}--\r\n'.encode()
    req=Request(base+'/upload/image',data=body,method='POST',headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    with urlopen(req,timeout=60) as x:return json.loads(x.read().decode())


def patch(obj, image_name=None, motion=None, prefix=None, seed=None):
    if isinstance(obj,dict):return {k:patch(v,image_name,motion,prefix,seed) for k,v in obj.items()}
    if isinstance(obj,list):return [patch(v,image_name,motion,prefix,seed) for v in obj]
    if isinstance(obj,str):
        if image_name and obj=='__IMAGE__': return image_name
        if motion and obj=='__ANIMATION_PROMPT__': return motion
        if prefix and obj=='__OUTPUT_PREFIX__': return prefix
        if seed is not None and obj=='__SEED__': return str(seed)
    return obj


def generate_clip(base, workflow_path, image, motion, out_dir, duration=5, seed=42):
    uploaded=upload_image(base,image); image_name=uploaded.get('name') or Path(image).name
    wf=json.loads(Path(workflow_path).read_text(encoding='utf-8-sig'))
    wf=patch(wf,image_name,motion,Path(out_dir).name,seed)
    if '395' in wf: wf['395'].setdefault('inputs',{})['image']=image_name
    if '398:376' in wf: wf['398:376'].setdefault('inputs',{})['value']=motion
    if '398:362' in wf: wf['398:362'].setdefault('inputs',{})['value']=max(3,min(5,int(round(duration))))
    if '398:338' in wf: wf['398:338'].setdefault('inputs',{})['noise_seed']=seed
    if '75' in wf: wf['75'].setdefault('inputs',{})['filename_prefix']='ai_video_factory/ltx'
    q=post_json(base+'/prompt',{'prompt':wf,'client_id':'ai-video-factory-'+uuid.uuid4().hex},60); pid=q['prompt_id']
    for _ in range(900):
        time.sleep(1)
        req=Request(base+'/history/'+pid)
        with urlopen(req,timeout=15) as x:h=json.loads(x.read().decode())
        if pid not in h:continue
        for node in h[pid].get('outputs',{}).values():
            records=[]; records.extend(node.get('videos',[])); records.extend(node.get('images',[]))
            for v in records:
                filename=v.get('filename'); sub=v.get('subfolder',''); typ=v.get('type','output')
                if not filename or not filename.lower().endswith(('.mp4','.webm','.mov','.mkv','.gif')): continue
                raw=urlopen(base+'/view?filename='+filename+'&subfolder='+sub+'&type='+typ,timeout=120).read()
                out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); raw_target=out/(Path(image).stem+'_ltx_raw.mp4'); target=out/(Path(image).stem+'_ltx.mp4'); raw_target.write_bytes(raw)
                clip_duration=max(3.0,min(5.0,float(duration)))
                subprocess.run(['ffmpeg','-y','-stream_loop','-1','-i',str(raw_target),'-t',str(clip_duration),'-c','copy',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try: raw_target.unlink()
                except OSError: pass
                return str(target)
    raise TimeoutError('LTX image-to-video timed out')

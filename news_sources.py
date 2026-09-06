import hashlib
import json
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

UA = 'AI-Video-Factory/1.0'

def _get_json(url, timeout=30):
    req = Request(url, headers={'User-Agent': UA})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))

def _download(url, target, timeout=45):
    req = Request(url, headers={'User-Agent': UA})
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if len(raw) < 1024:
        raise RuntimeError('Downloaded image is too small')
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(raw)
    return raw

def _candidates(query):
    out=[]
    try:
        data=_get_json('https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=5&gsrsearch='+quote_plus(query)+'&prop=imageinfo&iiprop=url|mime&iiurlwidth=1600&format=json')
        for page in (data.get('query',{}).get('pages',{}) or {}).values():
            info=(page.get('imageinfo') or [{}])[0]
            url=info.get('thumburl') or info.get('url')
            if url: out.append({'url':url,'title':page.get('title',''),'source':'Wikimedia Commons','license':'see source URL'})
    except Exception: pass
    try:
        data=_get_json('https://api.openverse.org/v1/images/?q='+quote_plus(query)+'&page_size=5')
        for item in data.get('results',[]) or []:
            url=item.get('thumbnail') or item.get('url')
            if url: out.append({'url':url,'title':item.get('title',''),'source':'Openverse','license':item.get('license','')})
    except Exception: pass
    return out

def download_related(query, target, used_hashes=None, index=0, vision_callback=None):
    used_hashes = used_hashes if used_hashes is not None else set()
    errors=[]
    for candidate in _candidates((query or '').strip()):
        try:
            raw=_download(candidate['url'], target)
            digest=hashlib.sha256(raw).hexdigest()
            if digest in used_hashes: continue
            if vision_callback:
                verdict=vision_callback(target, query or '') or {}
                if float(verdict.get('score', 0.0)) < 0.35: continue
                candidate['vision']=verdict
            used_hashes.add(digest)
            candidate.update({'query':query,'url':candidate['url'],'local_file':str(target)})
            return candidate
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError('No relevant image found for '+str(query)+(': '+'; '.join(errors[-2:]) if errors else ''))

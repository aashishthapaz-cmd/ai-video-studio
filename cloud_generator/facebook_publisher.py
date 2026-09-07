import os
import sys
import json
import time
import mimetypes
import logging
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from .config import load_settings, save_settings, BASE_DIR
except ImportError:
    from config import load_settings, save_settings, BASE_DIR

GRAPH_API_VERSION = "v20.0"
HISTORY_FILE = BASE_DIR / "facebook_history.json"
logger = logging.getLogger("FacebookPublisher")

def test_page_token(page_id: str, access_token: str) -> dict:
    """
    Validates a Facebook Page ID and Page Access Token via Graph API.
    Returns page metadata (id, name, link, category) or detailed diagnostic error.
    """
    if not page_id or not access_token:
        return {"ok": False, "error": "Page ID and Access Token must not be empty."}
    
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}?fields=id,name,link,category,fan_count,is_published&access_token={urllib.parse.quote(access_token)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AI-Video-Publisher/2.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "ok": True,
                "page_id": data.get("id"),
                "page_name": data.get("name"),
                "link": data.get("link", f"https://facebook.com/{page_id}"),
                "category": data.get("category", "General"),
                "fan_count": data.get("fan_count", 0),
                "is_published": data.get("is_published", True)
            }
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            err_msg = err_data.get("error", {}).get("message", str(e))
            return {"ok": False, "error": f"Facebook Error ({e.code}): {err_msg}"}
        except Exception:
            return {"ok": False, "error": f"HTTP Error {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Connection Error: {str(e)}"}

def _build_multipart_payload(fields: dict, file_field: str, file_path: Path):
    """Encodes multipart/form-data for Facebook Video upload."""
    boundary = f"----FacebookVideoBoundary{int(time.time()*1000)}"
    body = bytearray()
    
    # 1. Text fields
    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{v}\r\n".encode("utf-8"))
        
    # 2. Video file
    filename = file_path.name
    mime_type = mimetypes.guess_type(str(file_path))[0] or "video/mp4"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "User-Agent": "AI-Video-Publisher/2.0"
    }
    return headers, bytes(body)

def format_typewriter_facebook_caption(title: str, poem_text: str = None, custom_hashtags: str = None) -> str:
    """
    Formats clean, high-engagement Facebook post caption using EXACT poem title only (no poem body):
    {Exact Title} 🌿 💛 #love #poetry #lovequotes #soulmates #foryou
    """
    import re
    clean_title = str(title or "").strip()
    clean_title = re.sub(r'^(?:#?\d+[\.\)\-:]\s*|title:\s*)', '', clean_title, flags=re.IGNORECASE).strip()
    
    if not clean_title or clean_title.lower() in ("untitled", "cloud video", "poem", "quick post"):
        if poem_text:
            lines = [l.strip() for l in str(poem_text).splitlines() if l.strip()]
            if lines:
                clean_title = re.sub(r'^(?:#?\d+[\.\)\-:]\s*|title:\s*)', '', lines[0], flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = "Maybe Slowly, Maybe Imperfectly"

    emojis = "🌿 💛"

    # Max 5 relevant hashtags
    if custom_hashtags:
        tags = [t.strip() for t in custom_hashtags.split() if t.startswith("#")][:5]
    else:
        tags = ["#love", "#poetry", "#lovequotes", "#soulmates", "#foryou"]
    tags_str = " ".join(tags[:5])

    return f"{clean_title} {emojis} {tags_str}".strip()

def format_niche_facebook_caption(title: str, poem_text: str = None, niche = None) -> str:
    """
    Formats evocative Facebook post caption using EXACT poem title only (no poem body):
    {Exact Title} 🌿 💛 #love #poetry #lovequotes #soulmates #foryou
    """
    import re
    clean_title = str(title or "").strip()
    clean_title = re.sub(r'^(?:#?\d+[\.\)\-:]\s*|title:\s*)', '', clean_title, flags=re.IGNORECASE).strip()
    
    if not clean_title or clean_title.lower() in ("untitled", "cloud video", "poem", "quick post"):
        if poem_text:
            lines = [l.strip() for l in str(poem_text).splitlines() if l.strip()]
            if lines:
                clean_title = re.sub(r'^(?:#?\d+[\.\)\-:]\s*|title:\s*)', '', lines[0], flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = "Maybe Slowly, Maybe Imperfectly"

    emojis = "🌿 💛"
    if niche and hasattr(niche, "copy") and getattr(niche.copy, "hook_emojis", ""):
        hook_em = niche.copy.hook_emojis.strip()
        if hook_em:
            emojis = hook_em

    tags = ["#love", "#poetry", "#lovequotes", "#soulmates", "#foryou"]
    if niche and hasattr(niche, "copy") and getattr(niche.copy, "default_hashtags", ""):
        custom_tags = [t.strip() for t in niche.copy.default_hashtags.split() if t.startswith("#")]
        if custom_tags:
            tags = custom_tags[:5]
    tags_str = " ".join(tags[:5])

    return f"{clean_title} {emojis} {tags_str}".strip()

def publish_video_to_facebook_page(
    video_path: Path,
    title: str,
    description: str,
    page_id: str,
    access_token: str,
    as_reel: bool = True,
    hashtags: str = "",
    retries: int = 3
) -> dict:
    """
    Self-healing video publisher:
    Uploads 9:16 portrait videos directly to the specified Facebook Page.
    Automatically retries with exponential backoff on transient network / rate-limit glitches.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return {"ok": False, "page_id": page_id, "error": f"Video file not found: {video_path}"}
        
    full_description = description.strip()
    if hashtags and "#" not in full_description:
        full_description += " " + hashtags.strip()
        
    fields = {
        "access_token": access_token,
        "title": title,
        "description": full_description
    }
    
    url = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}/{page_id}/videos"
    
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            headers, body_data = _build_multipart_payload(fields, "source", video_path)
            req = urllib.request.Request(url, data=body_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                video_id = data.get("id")
                return {
                    "ok": True,
                    "page_id": page_id,
                    "video_id": video_id,
                    "post_url": f"https://facebook.com/{video_id}" if video_id else f"https://facebook.com/{page_id}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "attempts": attempt
                }
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                err_msg = err_data.get("error", {}).get("message", str(e))
                err_code = err_data.get("error", {}).get("code", e.code)
            except Exception:
                err_msg = str(e.reason)
                err_code = e.code
                
            last_err = f"Facebook Error ({err_code}): {err_msg}"
            
            # If token expired / permission denied (code 190, 10, 200), don't retry fruitlessly
            if err_code in (190, 10, 200, 401):
                break
                
            # Exponential backoff on rate limits / server errors
            backoff = attempt * 5
            logger.warning(f"Facebook upload attempt {attempt} failed ({last_err}). Retrying in {backoff}s...")
            time.sleep(backoff)
            
        except Exception as e:
            last_err = f"Network Error: {str(e)}"
            backoff = attempt * 5
            time.sleep(backoff)
            
    return {"ok": False, "page_id": page_id, "error": last_err or "Upload failed after retries"}

def publish_to_all_enabled_pages(video_path: Path, title: str, description: str, hashtags: str = None, target_page_ids: list = None) -> list:
    """
    Publishes to target Facebook Pages (or all enabled pages).
    Isolated execution: Failure or token error on one page never blocks other pages.
    """
    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    hashtags = hashtags or cfg.get("default_hashtags", "#poetry #anime #ghibli #reels #art #nepali")
    
    # Filter target pages
    if target_page_ids and "all" not in target_page_ids:
        pages = [p for p in pages if (p.get("id") in target_page_ids or p.get("page_id") in target_page_ids)]
        
    results = []
    for page in pages:
        if not page.get("enabled", True):
            continue
            
        page_id = str(page.get("id") or page.get("page_id") or "").strip()
        access_token = str(page.get("access_token", "")).strip()
        page_name = page.get("name") or page.get("page_name") or page_id
        page_hashtags = page.get("default_hashtags") or hashtags
        
        if not page_id or not access_token or page_id in ("YOUR_PAGE_ID", "test_page_id") or "YOUR_PAGE_ACCESS_TOKEN" in access_token or access_token.startswith("YOUR_"):
            print(f"ℹ️ [Facebook] Skipping '{page_name}' ({page_id}): Placeholder credentials detected. Set real Page ID and Access Token in FACEBOOK_PAGES_JSON secret to publish.", flush=True)
            results.append({
                "page_name": page_name,
                "page_id": page_id,
                "ok": False,
                "error": "Placeholder credentials configured. Real Page Access Token required."
            })
            continue
            
        res = publish_video_to_facebook_page(
            video_path=video_path,
            title=title,
            description=description,
            page_id=page_id,
            access_token=access_token,
            as_reel=page.get("as_reel", True),
            hashtags=page_hashtags
        )
        res["page_name"] = page_name
        results.append(res)
        
        # Record history
        _record_history({
            "title": title,
            "video_path": str(video_path),
            "page_name": page_name,
            "page_id": page_id,
            "success": res.get("ok", False),
            "video_id": res.get("video_id", ""),
            "post_url": res.get("post_url", ""),
            "error": res.get("error", ""),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        
        time.sleep(2.0)
        
    return results

def save_or_update_facebook_page(page_dict: dict) -> dict:
    """Adds or updates a Facebook Page configuration including posting time slots."""
    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    
    page_id = str(page_dict.get("page_id") or page_dict.get("id") or "").strip()
    if not page_id:
        return {"ok": False, "error": "Page ID is required"}
        
    # Test token
    access_token = str(page_dict.get("access_token", "")).strip()
    test_res = test_page_token(page_id, access_token) if access_token else {"ok": False, "error": "No token"}
    
    entry = {
        "id": page_id,
        "page_id": page_id,
        "name": page_dict.get("page_name") or page_dict.get("name") or test_res.get("page_name") or f"Page {page_id}",
        "access_token": access_token,
        "enabled": bool(page_dict.get("enabled", True)),
        "schedule_type": page_dict.get("schedule_type", "time_slots"), # "time_slots" or "interval"
        "niche_id": page_dict.get("niche_id", "typewriters_voice_nostalgia"),
        "timezone": page_dict.get("timezone", "America/New_York"),
        "time_slots": page_dict.get("time_slots", ["08:30", "13:00", "20:30"]),
        "usa_time_slots": page_dict.get("usa_time_slots", page_dict.get("time_slots", ["08:30", "13:00", "20:30"])),
        "interval_hours": int(page_dict.get("interval_hours", 4)),
        "target_vibe": page_dict.get("target_vibe", "typewriters_voice_nostalgia"),
        "default_hashtags": page_dict.get("default_hashtags", "#typewriter #poetry #aesthetic #reels"),
        "status": "CONNECTED" if test_res.get("ok") else "TOKEN_ERROR",
        "category": test_res.get("category", "General"),
        "fan_count": test_res.get("fan_count", 0),
        "last_error": test_res.get("error") if not test_res.get("ok") else None,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Update existing or append
    found = False
    for i, p in enumerate(pages):
        if str(p.get("id") or p.get("page_id")) == page_id:
            pages[i] = entry
            found = True
            break
    if not found:
        pages.append(entry)
        
    cfg["facebook_pages"] = pages
    save_settings(cfg)
    return {"ok": True, "page": entry, "token_valid": test_res.get("ok", False)}

def delete_facebook_page(page_id: str) -> bool:
    """Removes a page from configuration."""
    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    new_pages = [p for p in pages if str(p.get("id") or p.get("page_id")) != str(page_id)]
    if len(new_pages) != len(pages):
        cfg["facebook_pages"] = new_pages
        save_settings(cfg)
        return True
    return False

def _record_history(entry: dict):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.insert(0, entry)
    history = history[:100]
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

def get_publication_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
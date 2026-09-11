import os
import time
import json
import requests
from pathlib import Path
import sys

CURR_DIR = Path(__file__).resolve().parent
if str(CURR_DIR) not in sys.path:
    sys.path.insert(0, str(CURR_DIR))

from config import load_settings

def send_telegram_message(message: str, bot_token: str = None, chat_id: str = None) -> dict:
    cfg = load_settings()
    token = (bot_token or cfg.get('telegram_bot_token', '')).strip()
    chat = (chat_id or cfg.get('telegram_chat_id', '')).strip()
    if not token or not chat:
        return {'ok': False, 'error': 'Telegram bot token or chat ID is missing'}
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    
    # 1. First attempt with Markdown formatting
    payload = {'chat_id': chat, 'text': message, 'parse_mode': 'Markdown', 'disable_web_page_preview': False}
    try:
        r = requests.post(url, json=payload, timeout=15)
        data = r.json()
        if data.get('ok'):
            return {'ok': True, 'result': data}
        
        # 2. If Markdown parsing fails (e.g. unclosed entities, brackets, or code errors), fallback to plain text
        err_desc = str(data.get('description', ''))
        if 'parse entities' in err_desc.lower() or 'bad request' in err_desc.lower():
            plain_payload = {'chat_id': chat, 'text': message, 'disable_web_page_preview': False}
            r_plain = requests.post(url, json=plain_payload, timeout=15)
            data_plain = r_plain.json()
            if data_plain.get('ok'):
                return {'ok': True, 'result': data_plain}
            return {'ok': False, 'error': data_plain.get('description', r_plain.text)}

        return {'ok': False, 'error': err_desc}
    except Exception as e:
        # Fallback to plain text on any request error
        try:
            plain_payload = {'chat_id': chat, 'text': message, 'disable_web_page_preview': False}
            r_plain = requests.post(url, json=plain_payload, timeout=15)
            data_plain = r_plain.json()
            if data_plain.get('ok'):
                return {'ok': True, 'result': data_plain}
        except Exception:
            pass
        return {'ok': False, 'error': str(e)}

def send_whatsapp_message(message: str, phone: str = None, apikey: str = None) -> dict:
    cfg = load_settings()
    phone_num = (phone or cfg.get('whatsapp_phone', '')).strip()
    key = (apikey or cfg.get('whatsapp_apikey', '')).strip()
    if not phone_num or not key:
        return {'ok': False, 'error': 'WhatsApp phone number or API key missing'}
    url = 'https://api.callmebot.com/whatsapp.php'
    params = {'phone': phone_num, 'text': message, 'apikey': key}
    try:
        r = requests.get(url, params=params, timeout=4)
        if r.status_code == 200:
            return {'ok': True}
        return {'ok': False, 'error': f'HTTP {r.status_code}: {r.text}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def dispatch_alert(message: str) -> dict:
    cfg = load_settings()
    results = {}
    if cfg.get('enable_telegram', False) and cfg.get('telegram_bot_token'):
        results['telegram'] = send_telegram_message(message)
    if cfg.get('enable_whatsapp', False) and cfg.get('whatsapp_apikey'):
        results['whatsapp'] = send_whatsapp_message(message)
    if not results:
        results['status'] = 'Notifications not enabled or credentials not configured'
    return results

def notify_job_start(job: dict):
    title = job.get('title', 'Untitled Video')
    sched_time = job.get('scheduled_time', 'Immediate')
    msg = (
        f"[Video Production Started]\n\n"
        f"Title: {title}\n"
        f"Scheduled Time: {sched_time}\n"
        f"Voice: {job.get('voice', 'Default')}\n"
        f"Visual World: {job.get('theme', 'Auto Dynamic')}\n"
        f"Status: Generating audio, 2.5D visual scenes and parallax motion..."
    )
    return dispatch_alert(msg)

def send_telegram_video(video_path: str, caption: str = "") -> dict:
    cfg = load_settings()
    token = cfg.get('telegram_bot_token', '').strip()
    chat = cfg.get('telegram_chat_id', '').strip()
    if not token or not chat:
        return {'ok': False, 'error': 'Telegram bot token or chat ID is missing'}
    p = Path(video_path)
    if not p.exists():
        return {'ok': False, 'error': f'Video file not found: {video_path}'}
    url = f'https://api.telegram.org/bot{token}/sendVideo'
    try:
        with open(p, 'rb') as f:
            r = requests.post(
                url,
                data={'chat_id': chat, 'caption': caption[:1024], 'parse_mode': 'Markdown'},
                files={'video': f},
                timeout=90
            )
        data = r.json()
        if data.get('ok'):
            return {'ok': True, 'result': data}
            
        # Retry without Markdown if caption entity parsing failed
        err_desc = str(data.get('description', ''))
        if 'parse entities' in err_desc.lower() or 'bad request' in err_desc.lower():
            with open(p, 'rb') as f:
                r_plain = requests.post(
                    url,
                    data={'chat_id': chat, 'caption': caption[:1024]},
                    files={'video': f},
                    timeout=90
                )
            data_plain = r_plain.json()
            if data_plain.get('ok'):
                return {'ok': True, 'result': data_plain}
            return {'ok': False, 'error': data_plain.get('description', r_plain.text)}

        return {'ok': False, 'error': err_desc}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def notify_job_success(job: dict, fb_results: list, render_time: float, video_path: str = None):
    title = job.get('title', 'Untitled Video')
    lines = [
        f"🎬 *Video Rendered & Ready!*\n\n",
        f"📌 *Title:* {title}\n",
        f"⚡ *Render Time:* {render_time:.1f}s\n\n",
        f"📱 *Facebook Publishing Results:*\n"
    ]
    if not fb_results:
        lines.append("No Facebook pages were enabled for auto-posting.\n")
    else:
        for res in fb_results:
            page_name = res.get('page_name', res.get('page_id', 'Facebook Page'))
            is_ok = bool(res.get('ok') or res.get('success'))
            if is_ok:
                post_id = res.get('video_id') or res.get('post_id', 'N/A')
                url = res.get('post_url') or (f'https://facebook.com/{post_id}' if post_id != 'N/A' else 'Published')
                lines.append(f"  ✅ *{page_name}*: Posted Successfully!\n")
                if post_id and post_id != 'N/A':
                    lines.append(f"     Video ID: `{post_id}`\n")
                lines.append(f"     Link: {url}\n")
            else:
                err = res.get('error', 'Unknown error')
                lines.append(f"  ❌ *{page_name}*: FAILED\n")
                lines.append(f"     Error: `{err}`\n")
    
    caption_text = ''.join(lines)
    # Deliver playable MP4 video directly to Telegram!
    if video_path and Path(video_path).exists():
        res_tg = send_telegram_video(video_path, caption=caption_text)
        if res_tg.get('ok'):
            return res_tg
            
    return dispatch_alert(caption_text)

def notify_job_failure(job: dict, error_msg: str, stage: str = 'Video Generation'):
    title = job.get('title', 'Untitled Video')
    msg = (
        f"[Video Production Failed]\n\n"
        f"Title: {title}\n"
        f"Failed Stage: {stage}\n"
        f"Error Details: {error_msg}\n\n"
        f"Troubleshooting Tips:\n"
        f"  1. Check your API tokens and internet connection.\n"
        f"  2. You can click 'Run Now' on the dashboard to retry this job immediately."
    )
    return dispatch_alert(msg)

def notify_local_sync(pulled_files: list):
    count = len(pulled_files)
    if count == 0:
        return {}
    file_list = '\n'.join([f"  - {Path(f).name}" for f in pulled_files[:10]])
    msg = (
        f"[Local PC Auto-Sync Completed]\n\n"
        f"Local PC turned ON and connected!\n"
        f"Successfully transferred: {count} video(s) to D:\\Auto video Generator\\Output\\\n\n"
        f"{file_list}\n\n"
        f"Cloud storage cleaned up: 0 MB remaining on cloud."
    )
    return dispatch_alert(msg)

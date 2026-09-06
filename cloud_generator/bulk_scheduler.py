import os
import json
import time
import uuid
import re
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import sys

CURR_DIR = Path(__file__).resolve().parent
if str(CURR_DIR) not in sys.path:
    sys.path.insert(0, str(CURR_DIR))

from config import JOBS_QUEUE_FILE, load_settings
from pipeline import run_cloud_pipeline
from cloud_storage import store_video_in_cloud_buffer
from notifier import notify_job_start, notify_job_success, notify_job_failure
from niche_profiles import get_niche, detect_niche_from_text, NICHE_REGISTRY

_SCHEDULER_THREAD = None
_SCHEDULER_LOCK = threading.Lock()
_RUNNING = False

def load_queue() -> list:
    with _SCHEDULER_LOCK:
        if not JOBS_QUEUE_FILE.exists():
            return []
        try:
            return json.loads(JOBS_QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

def save_queue(queue: list):
    with _SCHEDULER_LOCK:
        JOBS_QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")

def compute_next_time_slots(
    count: int, 
    target_page_id: str = None, 
    start_time_str: str = None, 
    interval_minutes: int = 120,
    timezone_str: str = "America/New_York",
    custom_daily_slots: list = None
) -> list:
    """
    Computes upcoming schedule timestamps strictly localized to the target USA timezone (e.g. America/New_York).
    Aligns to daily peak engagement slots (e.g. 08:30, 13:00, 20:30 EST/EDT) or interval spacing.
    Returns a list of dicts with:
      - scheduled_time: "YYYY-MM-DD HH:MM"
      - scheduled_time_usa: "YYYY-MM-DD HH:MM EST"
      - epoch: Unix timestamp (int) for bulletproof timezone-independent comparison
      - timezone: "America/New_York"
    """
    try:
        tz = ZoneInfo(timezone_str or "America/New_York")
    except Exception:
        tz = ZoneInfo("America/New_York")

    now_tz = datetime.now(tz)

    if start_time_str:
        cleaned_start = start_time_str.strip()
        # Remove any timezone name like "EST", "EDT", "UTC" if present at end
        cleaned_start = re.sub(r'\s+[A-Za-z/_-]+$', '', cleaned_start)
        try:
            naive_dt = datetime.strptime(cleaned_start, "%Y-%m-%d %H:%M")
            base_time = naive_dt.replace(tzinfo=tz)
        except Exception:
            try:
                naive_dt = datetime.strptime(cleaned_start, "%Y-%m-%d")
                base_time = naive_dt.replace(hour=8, minute=30, tzinfo=tz)
            except Exception:
                base_time = now_tz + timedelta(minutes=5)
    else:
        base_time = now_tz + timedelta(minutes=5)

    # Ensure base_time is not in the past relative to current USA time
    if base_time < now_tz:
        base_time = now_tz + timedelta(minutes=2)

    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    matched_page = next((p for p in pages if str(p.get("id") or p.get("page_id")) == str(target_page_id)), None)

    # Resolve daily slots
    daily_slots = custom_daily_slots
    if not daily_slots and matched_page:
        daily_slots = matched_page.get("usa_time_slots") or matched_page.get("time_slots")
    if not daily_slots:
        daily_slots = ["08:30", "13:00", "20:30"]

    daily_slots = sorted(list(set(daily_slots)))

    slots = []
    use_interval = (matched_page and matched_page.get("schedule_type") == "interval") or (interval_minutes != 120 and not matched_page)

    if not use_interval and daily_slots:
        # Calculate next occurrences of configured daily USA time slots
        curr_day = base_time.date()
        max_days = max(365, count * 2)
        day_count = 0
        while len(slots) < count and day_count < max_days:
            for s in daily_slots:
                try:
                    parts = s.split(":")
                    h, m = int(parts[0]), int(parts[1])
                    slot_dt = datetime(curr_day.year, curr_day.month, curr_day.day, h, m, tzinfo=tz)
                    if slot_dt >= base_time and len(slots) < count:
                        epoch = int(slot_dt.timestamp())
                        slots.append({
                            "scheduled_time": slot_dt.strftime("%Y-%m-%d %H:%M"),
                            "scheduled_time_usa": slot_dt.strftime("%Y-%m-%d %H:%M %Z"),
                            "epoch": epoch,
                            "timezone": str(tz)
                        })
                except Exception:
                    continue
            curr_day += timedelta(days=1)
            day_count += 1
    else:
        # Interval spacing from base_time
        for i in range(count):
            slot_dt = base_time + timedelta(minutes=i * interval_minutes)
            epoch = int(slot_dt.timestamp())
            slots.append({
                "scheduled_time": slot_dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_time_usa": slot_dt.strftime("%Y-%m-%d %H:%M %Z"),
                "epoch": epoch,
                "timezone": str(tz)
            })

    return slots

def parse_bulk_scripts(
    raw_text: str, 
    start_time_str: str = None, 
    interval_minutes: int = 120, 
    default_voice: str = None, 
    default_theme: str = None,
    default_page_ids: list = None,
    default_niche: str = None,
    timezone_str: str = "America/New_York",
    auto_distribute_pages: bool = False
) -> list:
    """
    Parses bulk poetry submissions and maps each poem to:
    1. Assigned Facebook Page(s)
    2. Assigned Poetry Niche (Art, Voice, Typography, Copywriting)
    3. Exact USA-based posting slot (Timestamp + Epoch)
    """
    text = raw_text.strip()
    if not text:
        return []

    # Smart chunk splitting: numbered items (1. , 2. ), separator lines (---), or double linebreaks
    if re.search(r'(?:^|\n)\s*\d+[\.\)]\s+', text):
        chunks = re.split(r'(?=(?:^|\n)\s*\d+[\.\)]\s+)', text)
    elif re.search(r'\n\s*(?:---+|===+|###+)\s*\n', text):
        chunks = re.split(r'\n\s*(?:---+|===+|###+)\s*\n', text)
    else:
        chunks = re.split(r'\n\s*\n+', text)

    cfg = load_settings()
    available_pages = cfg.get("facebook_pages", [])
    enabled_pages = [p for p in available_pages if p.get("enabled", True)]

    raw_items = []
    
    for chunk in chunks:
        c_text = chunk.strip()
        if not c_text:
            continue
            
        title = None
        custom_time = None
        niche_specified = default_niche
        voice = default_voice
        theme = default_theme
        target_pages = list(default_page_ids) if default_page_ids else []
        script_lines = []
        
        in_script = False
        lines = [l.strip() for l in c_text.split("\n") if l.strip()]
        if not lines:
            continue

        first_line = lines[0]
        m = re.match(r'^(?:#?\d+[\.\)\-:]\s*|title:\s*)(.*)$', first_line, re.IGNORECASE)
        if m and len(lines) > 1:
            title = m.group(1).strip()
            body_lines = lines[1:]
        else:
            title = None
            body_lines = lines

        for line in body_lines:
            line_str = line.strip()
            if not in_script:
                if line_str.lower().startswith("title:"):
                    title = line_str[6:].strip()
                    continue
                elif line_str.lower().startswith("time:"):
                    custom_time = line_str[5:].strip()
                    continue
                elif line_str.lower().startswith("niche:"):
                    niche_specified = line_str[6:].strip()
                    continue
                elif line_str.lower().startswith("voice:"):
                    voice = line_str[6:].strip()
                    continue
                elif line_str.lower().startswith("theme:") or line_str.lower().startswith("vibe:"):
                    theme = line_str[6:].strip()
                    continue
                elif line_str.lower().startswith("page:") or line_str.lower().startswith("pages:"):
                    val = line_str.split(":", 1)[1].strip()
                    target_pages = [p.strip() for p in val.split(",") if p.strip()]
                    continue
                elif line_str.lower().startswith("script:"):
                    in_script = True
                    remainder = line_str[7:].strip()
                    if remainder:
                        script_lines.append(remainder)
                    continue
            script_lines.append(line)
            
        script_text = "\n".join(script_lines).strip()
        if not script_text:
            continue
            
        if not title:
            first_l = script_lines[0].strip() if script_lines else "Poetic Reflection"
            title = first_l[:40].rstrip(".,!? ")

        raw_items.append({
            "title": title,
            "script_text": script_text,
            "niche": niche_specified,
            "voice": voice,
            "theme": theme,
            "custom_time": custom_time,
            "target_pages": target_pages
        })

    # Compute scheduled times in USA timezone
    first_page_id = default_page_ids[0] if (default_page_ids and isinstance(default_page_ids, list) and len(default_page_ids) > 0) else None
    computed_slots = compute_next_time_slots(
        len(raw_items), 
        target_page_id=first_page_id, 
        start_time_str=start_time_str, 
        interval_minutes=interval_minutes,
        timezone_str=timezone_str
    )

    jobs = []
    for idx, item in enumerate(raw_items):
        slot_info = computed_slots[idx] if idx < len(computed_slots) else {}
        
        # Handle custom time override if provided
        if item["custom_time"]:
            sched_time_str = item["custom_time"]
            sched_epoch = None
            sched_usa = sched_time_str
        else:
            sched_time_str = slot_info.get("scheduled_time")
            sched_epoch = slot_info.get("epoch")
            sched_usa = slot_info.get("scheduled_time_usa")

        # Multi-page auto-distribution
        assigned_pages = item["target_pages"]
        if auto_distribute_pages and enabled_pages:
            assigned_page = enabled_pages[idx % len(enabled_pages)]
            assigned_pages = [str(assigned_page.get("id") or assigned_page.get("page_id"))]

        # Resolve niche
        chosen_niche_id = item["niche"]
        if not chosen_niche_id and assigned_pages:
            matched_p = next((p for p in available_pages if str(p.get("id") or p.get("page_id")) in assigned_pages), None)
            if matched_p and matched_p.get("niche_id"):
                chosen_niche_id = matched_p.get("niche_id")

        if not chosen_niche_id:
            chosen_niche_id = detect_niche_from_text(item["title"], item["script_text"])

        niche = get_niche(chosen_niche_id)

        job = {
            "id": f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            "title": item["title"],
            "script_text": item["script_text"],
            "niche_id": niche.niche_id,
            "niche_name": niche.name,
            "voice": item["voice"] or niche.voice.voice_id,
            "theme": item["theme"] or niche.art.vibe_id,
            "target_page_ids": assigned_pages,
            "scheduled_time": sched_time_str,
            "scheduled_time_usa": sched_usa,
            "scheduled_epoch": sched_epoch,
            "timezone": timezone_str,
            "status": "PENDING",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "render_time": None,
            "output_file": None,
            "facebook_results": None,
            "error": None,
            "synced_to_local": False
        }
        jobs.append(job)
        
    return jobs

def enqueue_bulk_jobs(jobs: list) -> list:
    q = load_queue()
    for job in jobs:
        q.append(job)
    save_queue(q)
    return jobs

def delete_job(job_id: str) -> bool:
    q = load_queue()
    initial_len = len(q)
    q = [j for j in q if j.get("id") != job_id]
    if len(q) != initial_len:
        save_queue(q)
        return True
    return False

def update_job(job_id: str, updates: dict):
    q = load_queue()
    for j in q:
        if j.get("id") == job_id:
            j.update(updates)
            break
    save_queue(q)

def reorder_queue(job_ids_order: list) -> list:
    q = load_queue()
    id_map = {j["id"]: j for j in q if "id" in j}
    new_q = []
    for jid in job_ids_order:
        if jid in id_map:
            new_q.append(id_map.pop(jid))
    for remaining in id_map.values():
        new_q.append(remaining)
    save_queue(new_q)
    return new_q

def retry_job(job_id: str) -> dict:
    q = load_queue()
    job = next((j for j in q if j.get("id") == job_id), None)
    if not job:
        return {"ok": False, "error": f"Job {job_id} not found"}
        
    now_dt = datetime.now()
    now_str = (now_dt + timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M")
    now_epoch = int(time.time() + 5)
    update_job(job_id, {
        "status": "PENDING",
        "scheduled_time": now_str,
        "scheduled_epoch": now_epoch,
        "error": None
    })
    return {"ok": True, "job_id": job_id, "scheduled_time": now_str}

def clear_completed_jobs() -> int:
    q = load_queue()
    initial_len = len(q)
    new_q = [j for j in q if j.get("status") in ("PENDING", "RENDERING")]
    removed = initial_len - len(new_q)
    if removed > 0:
        save_queue(new_q)
    return removed

def execute_single_job(job_id: str) -> dict:
    q = load_queue()
    job = next((j for j in q if j.get("id") == job_id), None)
    if not job:
        return {"ok": False, "error": f"Job {job_id} not found in queue"}
        
    update_job(job_id, {"status": "RENDERING", "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    notify_job_start(job)
    
    t0 = time.time()
    try:
        cfg = load_settings()
        res = run_cloud_pipeline(
            title=job["title"],
            script_text=job["script_text"],
            custom_vibe=job.get("theme", "auto"),
            auto_publish_fb=True,
            target_page_ids=job.get("target_page_ids"),
            niche_id=job.get("niche_id")
        )
        total_time = time.time() - t0
        output_file = res.get("output_file")
        fb_res = res.get("facebook_published", [])
        
        # Buffer video in temporary cloud storage
        if output_file:
            store_video_in_cloud_buffer(job_id, output_file, job["title"])
            
        update_job(job_id, {
            "status": "PUBLISHED",
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "render_time": round(total_time, 1),
            "output_file": output_file,
            "facebook_results": fb_res,
            "error": None
        })
        
        notify_job_success(job, fb_res, total_time, output_file)
        return {
            "ok": True, 
            "status": "COMPLETED", 
            "job_id": job_id, 
            "render_time": total_time, 
            "output_file": output_file,
            "facebook_results": fb_res
        }
    except Exception as e:
        err_msg = str(e)
        update_job(job_id, {
            "status": "FAILED",
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": err_msg
        })
        notify_job_failure(job, err_msg)
        return {"ok": False, "status": "FAILED", "job_id": job_id, "error": err_msg}

def _scheduler_loop():
    global _RUNNING
    while _RUNNING:
        try:
            q = load_queue()
            now_epoch = time.time()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            for job in q:
                if job.get("status") == "PENDING":
                    epoch = job.get("scheduled_epoch")
                    triggered = False
                    if epoch and isinstance(epoch, (int, float)):
                        if now_epoch >= epoch:
                            triggered = True
                    else:
                        sched_str = job.get("scheduled_time")
                        if sched_str:
                            try:
                                sched_dt = datetime.strptime(sched_str.strip(), "%Y-%m-%d %H:%M")
                                if datetime.now() >= sched_dt:
                                    triggered = True
                            except Exception:
                                pass
                    if triggered:
                        print(f"[TRIGGER] Scheduled job: {job.get('title')} ({job.get('id')}) | Niche: {job.get('niche_id')}")
                        execute_single_job(job.get("id"))
        except Exception as e:
            print(f"Scheduler loop exception: {e}")
        time.sleep(15)

def start_scheduler():
    global _SCHEDULER_THREAD, _RUNNING
    if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
        return
    _RUNNING = True
    _SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True, name="BulkSchedulerDaemon")
    _SCHEDULER_THREAD.start()
    print("[OK] Autonomous Bulk Video Scheduler daemon with USA Timezones started successfully.")

import os
import json
import time
import uuid
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
import sys

CURR_DIR = Path(__file__).resolve().parent
if str(CURR_DIR) not in sys.path:
    sys.path.insert(0, str(CURR_DIR))

from config import JOBS_QUEUE_FILE, load_settings
from pipeline import run_cloud_pipeline
from cloud_storage import store_video_in_cloud_buffer
from notifier import notify_job_start, notify_job_success, notify_job_failure

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

def compute_next_time_slots(count: int, target_page_id: str = None, start_time_str: str = None, interval_minutes: int = 120) -> list:
    """
    Computes upcoming schedule timestamps.
    If target_page_id has defined daily time_slots (e.g. 09:00, 15:00, 21:00), calculates next matching calendar slots.
    Otherwise spaces out by interval_minutes.
    """
    now = datetime.now()
    if start_time_str:
        try:
            base_time = datetime.strptime(start_time_str.strip(), "%Y-%m-%d %H:%M")
        except Exception:
            base_time = now + timedelta(minutes=5)
    else:
        base_time = now + timedelta(minutes=5)

    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    matched_page = next((p for p in pages if str(p.get("id") or p.get("page_id")) == str(target_page_id)), None)

    slots = []
    if matched_page and matched_page.get("schedule_type") == "time_slots" and matched_page.get("time_slots"):
        # Calculate next occurrences of configured daily time slots
        daily_slots = sorted(matched_page.get("time_slots", [])) # e.g. ["09:00", "15:00", "21:00"]
        curr_day = base_time.date()
        while len(slots) < count:
            for s in daily_slots:
                try:
                    h, m = map(int, s.split(":"))
                    slot_dt = datetime(curr_day.year, curr_day.month, curr_day.day, h, m)
                    if slot_dt >= base_time and len(slots) < count:
                        slots.append(slot_dt.strftime("%Y-%m-%d %H:%M"))
                except Exception:
                    continue
            curr_day += timedelta(days=1)
    else:
        # Interval spacing
        for i in range(count):
            slot_dt = base_time + timedelta(minutes=i * interval_minutes)
            slots.append(slot_dt.strftime("%Y-%m-%d %H:%M"))

    return slots

def parse_bulk_scripts(
    raw_text: str, 
    start_time_str: str = None, 
    interval_minutes: int = 120, 
    default_voice: str = "cloud_cloning", 
    default_theme: str = "auto",
    default_page_ids: list = None
) -> list:
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

    raw_items = []
    
    for chunk in chunks:
        c_text = chunk.strip()
        if not c_text:
            continue
            
        title = None
        custom_time = None
        voice = default_voice
        theme = default_theme
        target_pages = default_page_ids or []
        script_lines = []
        
        in_script = False
        lines = [l.strip() for l in c_text.split("\n") if l.strip()]
        if not lines:
            continue

        first_line = lines[0]
        # Match "1. Title" or "1) Title" or "#1 Title" or "Title: ..."
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
            "voice": voice,
            "theme": theme,
            "custom_time": custom_time,
            "target_pages": target_pages
        })

    # Compute scheduled times
    first_page_id = default_page_ids[0] if (default_page_ids and isinstance(default_page_ids, list) and len(default_page_ids) > 0) else None
    computed_slots = compute_next_time_slots(len(raw_items), target_page_id=first_page_id, start_time_str=start_time_str, interval_minutes=interval_minutes)

    jobs = []
    for idx, item in enumerate(raw_items):
        sched_time_str = item["custom_time"] if item["custom_time"] else (computed_slots[idx] if idx < len(computed_slots) else None)
        
        job = {
            "id": f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            "title": item["title"],
            "script_text": item["script_text"],
            "voice": item["voice"],
            "theme": item["theme"],
            "target_page_ids": item["target_pages"],
            "scheduled_time": sched_time_str,
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
    """Re-orders the pending / overall queue according to specified array of IDs."""
    q = load_queue()
    id_map = {j["id"]: j for j in q if "id" in j}
    new_q = []
    
    # Place ordered ones first
    for jid in job_ids_order:
        if jid in id_map:
            new_q.append(id_map.pop(jid))
            
    # Append any remaining jobs
    for remaining in id_map.values():
        new_q.append(remaining)
        
    save_queue(new_q)
    return new_q

def retry_job(job_id: str) -> dict:
    """Resets a FAILED or INTERRUPTED job to PENDING so the scheduler picks it up immediately."""
    q = load_queue()
    job = next((j for j in q if j.get("id") == job_id), None)
    if not job:
        return {"ok": False, "error": f"Job {job_id} not found"}
        
    now_str = (datetime.now() + timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M")
    update_job(job_id, {
        "status": "PENDING",
        "scheduled_time": now_str,
        "error": None
    })
    return {"ok": True, "job_id": job_id, "scheduled_time": now_str}

def clear_completed_jobs() -> int:
    """Removes all PUBLISHED or FAILED jobs from the queue."""
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
            target_page_ids=job.get("target_page_ids")
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
        return {"ok": True, "job_id": job_id, "render_time": total_time, "facebook_results": fb_res}
    except Exception as e:
        err_msg = str(e)
        update_job(job_id, {
            "status": "FAILED",
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": err_msg
        })
        notify_job_failure(job, err_msg)
        return {"ok": False, "job_id": job_id, "error": err_msg}

def _scheduler_loop():
    global _RUNNING
    while _RUNNING:
        try:
            q = load_queue()
            now = datetime.now()
            for job in q:
                if job.get("status") == "PENDING":
                    sched_str = job.get("scheduled_time")
                    if sched_str:
                        try:
                            sched_dt = datetime.strptime(sched_str.strip(), "%Y-%m-%d %H:%M")
                            if now >= sched_dt:
                                print(f"[TRIGGER] Scheduled job: {job.get('title')} ({job.get('id')})")
                                execute_single_job(job.get("id"))
                        except Exception as parse_err:
                            print(f"Error parsing date for job {job.get('id')}: {parse_err}")
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
    print("[OK] Autonomous Bulk Video Scheduler daemon started successfully.")

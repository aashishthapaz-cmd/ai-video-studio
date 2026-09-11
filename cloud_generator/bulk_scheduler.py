import os
import json
import time
import uuid
import re
import threading
import subprocess
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


def _commit_queue_to_git(message: str = "🤖 Live queue sync [skip ci]"):
    """
    Immediately commits and pushes the updated jobs_queue.json to the remote repo
    so the Live Cloud Queue web UI reflects the change without waiting for the
    GitHub Actions final step to run.
    Only runs when executed inside a GitHub Actions environment.
    """
    if not os.environ.get("GITHUB_ACTIONS"):
        return  # skip when running locally
    try:
        repo_root = CURR_DIR.parent
        cmds = [
            ["git", "config", "--global", "user.name", "Autonomous Studio Bot"],
            ["git", "config", "--global", "user.email", "bot@autovideostudio.internal"],
            ["git", "-C", str(repo_root), "add", str(JOBS_QUEUE_FILE)],
        ]
        for cmd in cmds:
            subprocess.run(cmd, check=False, capture_output=True)

        # Only commit if there are staged changes
        diff = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--staged", "--quiet"],
            capture_output=True
        )
        if diff.returncode != 0:  # staged changes exist
            subprocess.run(
                ["git", "-C", str(repo_root), "commit", "-m", message],
                check=False, capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "pull", "--rebase", "origin", "main"],
                check=False, capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "push", "origin", "HEAD:main"],
                check=False, capture_output=True
            )
            print(f"[Queue Sync] Committed updated queue to GitHub: {message}", flush=True)
        else:
            print("[Queue Sync] No queue changes to commit.", flush=True)
    except Exception as e:
        print(f"[Queue Sync] Warning: git commit failed (non-fatal): {e}", flush=True)


def compute_next_time_slots(
    count: int, 
    target_page_id: str = None, 
    start_time_str: str = None, 
    interval_minutes: int = 120,
    timezone_str: str = "Asia/Kathmandu",
    custom_daily_slots: list = None,
    available_pages: list = None
) -> list:
    """
    Computes upcoming schedule timestamps localized to Nepal time (Asia/Kathmandu) and USA timezone.
    Aligns to interval spacing or daily peak slots.
    Returns a list of dicts with:
      - scheduled_time: "YYYY-MM-DD HH:MM" (Nepal Time)
      - scheduled_time_nepal: "YYYY-MM-DD HH:MM NPT"
      - scheduled_time_usa: "YYYY-MM-DD HH:MM EDT/EST"
      - epoch: Unix timestamp (int) for bulletproof universal execution
      - timezone: "Asia/Kathmandu"
    """
    try:
        tz_npt = ZoneInfo("Asia/Kathmandu")
    except Exception:
        tz_npt = ZoneInfo("UTC")
    try:
        tz_usa = ZoneInfo("America/New_York")
    except Exception:
        tz_usa = ZoneInfo("UTC")

    now_npt = datetime.now(tz_npt)

    if start_time_str:
        cleaned_start = start_time_str.strip()
        cleaned_start = re.sub(r'\s+[A-Za-z/_-]+$', '', cleaned_start)
        try:
            naive_dt = datetime.strptime(cleaned_start, "%Y-%m-%d %H:%M")
            base_time = naive_dt.replace(tzinfo=tz_npt)
        except Exception:
            try:
                naive_dt = datetime.strptime(cleaned_start, "%Y-%m-%d")
                base_time = naive_dt.replace(hour=now_npt.hour, minute=now_npt.minute, tzinfo=tz_npt)
            except Exception:
                base_time = now_npt + timedelta(minutes=2)
    else:
        base_time = now_npt + timedelta(minutes=2)

    # If base_time is in the past, push forward by 2 minutes
    if base_time < now_npt:
        base_time = now_npt + timedelta(minutes=2)

    pages = available_pages if (available_pages is not None) else load_settings().get("facebook_pages", [])
    matched_page = next((p for p in pages if str(p.get("id") or p.get("page_id")) == str(target_page_id)), None)

    slots = []
    # Generate sequential interval slots from base_time
    for i in range(count):
        slot_dt = base_time + timedelta(minutes=i * interval_minutes)
        epoch = int(slot_dt.timestamp())
        npt_dt = datetime.fromtimestamp(epoch, tz=tz_npt)
        usa_dt = datetime.fromtimestamp(epoch, tz=tz_usa)
        slots.append({
            "scheduled_time": npt_dt.strftime("%Y-%m-%d %H:%M"),
            "scheduled_time_nepal": npt_dt.strftime("%Y-%m-%d %H:%M NPT"),
            "scheduled_time_usa": usa_dt.strftime("%Y-%m-%d %H:%M %Z"),
            "epoch": epoch,
            "timezone": "Asia/Kathmandu"
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
    timezone_str: str = "Asia/Kathmandu",
    auto_distribute_pages: bool = False,
    available_pages: list = None
) -> list:
    """
    Parses bulk poetry submissions and maps each poem to:
    1. Assigned Facebook Page(s) across all connected pages
    2. Assigned Poetry Niche (Art, Voice, Typography, Copywriting)
    3. Exact Nepal & USA posting slot (Timestamp + Epoch)
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

    pages = available_pages if (available_pages is not None) else load_settings().get("facebook_pages", [])
    enabled_pages = [p for p in pages if p.get("enabled", True)]

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

    # Compute scheduled times in Nepal timezone
    first_page_id = default_page_ids[0] if (default_page_ids and isinstance(default_page_ids, list) and len(default_page_ids) > 0) else None
    computed_slots = compute_next_time_slots(
        len(raw_items), 
        target_page_id=first_page_id, 
        start_time_str=start_time_str, 
        interval_minutes=interval_minutes,
        timezone_str=timezone_str,
        available_pages=enabled_pages
    )

    jobs = []
    for idx, item in enumerate(raw_items):
        slot_info = computed_slots[idx] if idx < len(computed_slots) else {}
        
        # Handle custom time override if provided
        if item["custom_time"]:
            sched_time_str = item["custom_time"]
            sched_epoch = None
            sched_nepal = sched_time_str
            sched_usa = sched_time_str
        else:
            sched_time_str = slot_info.get("scheduled_time")
            sched_epoch = slot_info.get("epoch")
            sched_nepal = slot_info.get("scheduled_time_nepal")
            sched_usa = slot_info.get("scheduled_time_usa")

        # Multi-page assignment: round-robin if auto_distribute_pages or target_pages empty
        assigned_pages = item["target_pages"]
        if (auto_distribute_pages or not assigned_pages) and enabled_pages:
            assigned_page = enabled_pages[idx % len(enabled_pages)]
            assigned_pages = [str(assigned_page.get("id") or assigned_page.get("page_id"))]
        elif not assigned_pages and default_page_ids:
            assigned_pages = list(default_page_ids)

        # Resolve niche
        chosen_niche_id = item["niche"]
        if not chosen_niche_id and assigned_pages:
            matched_p = next((p for p in pages if str(p.get("id") or p.get("page_id")) in assigned_pages), None)
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
            "scheduled_time_nepal": sched_nepal,
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

def resolve_schedule_collisions(
    queue: list = None,
    min_gap_seconds: int = 1800,
    auto_align_past: bool = True
) -> tuple:
    """
    Detects and automatically resolves schedule collisions among PENDING jobs.
    Guarantees that no two jobs are scheduled within min_gap_seconds (default 30 minutes / 1800s) of each other.

    - Sorts all pending jobs by scheduled epoch.
    - If job[i].epoch < job[i-1].epoch + min_gap_seconds, offsets job[i] to job[i-1].epoch + min_gap_seconds (+30 min).
    - If multiple jobs are in the past:
        * The earliest pending job remains due NOW (ready for immediate execution).
        * Subsequent overdue jobs are automatically aligned into upcoming 30-minute intervals
          (now + 30m, now + 60m, etc.) so they never pile up or appear stuck/expired in the UI.
    - Automatically recomputes human-readable timestamps for Nepal (Asia/Kathmandu) and USA (America/New_York).
    - Saves the updated queue and syncs to Git if changes were made.

    Returns:
        (adjusted_count, updated_queue)
    """
    q = list(queue) if (queue is not None) else load_queue()
    if not q:
        return 0, q

    try:
        tz_npt = ZoneInfo("Asia/Kathmandu")
    except Exception:
        tz_npt = ZoneInfo("UTC")
    try:
        tz_usa = ZoneInfo("America/New_York")
    except Exception:
        tz_usa = ZoneInfo("UTC")

    now_epoch = int(time.time())

    # Separate pending jobs from non-pending
    pending_jobs = []
    other_jobs = []
    for j in q:
        if j.get("status") == "PENDING":
            # Ensure scheduled_epoch is valid
            epoch = j.get("scheduled_epoch")
            if not epoch or not isinstance(epoch, (int, float)):
                sched_str = j.get("scheduled_time", "")
                if sched_str:
                    try:
                        clean_str = re.sub(r'\s+[A-Za-z/_-]+$', '', sched_str.strip())
                        dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz_npt)
                        epoch = int(dt.timestamp())
                    except Exception:
                        epoch = now_epoch + 120
                else:
                    epoch = now_epoch + 120
                j["scheduled_epoch"] = epoch
            pending_jobs.append(j)
        else:
            other_jobs.append(j)

    if not pending_jobs:
        return 0, q

    # Sort pending jobs by scheduled_epoch ascending
    pending_jobs.sort(key=lambda x: x.get("scheduled_epoch", 0))

    adjusted_count = 0

    for i in range(len(pending_jobs)):
        curr_epoch = pending_jobs[i].get("scheduled_epoch", 0)
        target_epoch = curr_epoch

        if i == 0:
            # First job: if in past, keep it due now.
            pass
        else:
            prev_epoch = pending_jobs[i - 1].get("scheduled_epoch", 0)
            min_allowed = prev_epoch + min_gap_seconds

            # If auto_align_past is True and previous job was in the past / due now,
            # ensure subsequent job is pushed into the future (now + min_gap_seconds)
            if auto_align_past and (prev_epoch <= now_epoch):
                min_allowed = max(min_allowed, now_epoch + min_gap_seconds)

            if curr_epoch < min_allowed:
                target_epoch = min_allowed

        if target_epoch != curr_epoch:
            adjusted_count += 1
            pending_jobs[i]["scheduled_epoch"] = int(target_epoch)
            npt_dt = datetime.fromtimestamp(target_epoch, tz=tz_npt)
            usa_dt = datetime.fromtimestamp(target_epoch, tz=tz_usa)
            pending_jobs[i]["scheduled_time"] = npt_dt.strftime("%Y-%m-%d %H:%M")
            pending_jobs[i]["scheduled_time_nepal"] = npt_dt.strftime("%Y-%m-%d %H:%M NPT")
            pending_jobs[i]["scheduled_time_usa"] = usa_dt.strftime("%Y-%m-%d %H:%M %Z")

    # Combine back into a single list
    new_q = pending_jobs + other_jobs

    if adjusted_count > 0:
        save_queue(new_q)
        print(f"[Queue Collision Resolver] Auto-adjusted {adjusted_count} job(s) with >={min_gap_seconds//60}m spacing.", flush=True)
        _commit_queue_to_git(f"🤖 Queue: auto-spaced {adjusted_count} colliding jobs (+30m difference) [skip ci]")

    return adjusted_count, new_q

def enqueue_bulk_jobs(jobs: list) -> list:
    q = load_queue()
    for job in jobs:
        q.append(job)
    save_queue(q)
    # Immediately resolve schedule collisions across entire queue (including newly enqueued jobs)
    resolve_schedule_collisions(min_gap_seconds=1800, auto_align_past=True)
    _commit_queue_to_git(f"🤖 Queue: enqueued {len(jobs)} bulk jobs & verified 30m spacing [skip ci]")
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


def expire_stale_jobs(max_age_hours: int = 72) -> int:
    """
    Removes PENDING jobs whose scheduled_epoch is more than max_age_hours in the past.
    Posts older than 72 hours are too stale to publish — followers would see wrong timing.
    Returns the number of jobs removed.
    """
    q = load_queue()
    cutoff = time.time() - (max_age_hours * 3600)
    kept = []
    removed_count = 0
    try:
        tz_npt = ZoneInfo("Asia/Kathmandu")
    except Exception:
        tz_npt = ZoneInfo("UTC")

    for j in q:
        status = j.get("status", "PENDING")
        if status == "PENDING":
            epoch = j.get("scheduled_epoch")
            if not epoch or not isinstance(epoch, (int, float)):
                sched_str = j.get("scheduled_time", "")
                if sched_str:
                    try:
                        clean_str = re.sub(r'\s+[A-Za-z/_-]+$', '', sched_str.strip())
                        dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz_npt)
                        epoch = int(dt.timestamp())
                        j["scheduled_epoch"] = epoch
                    except Exception:
                        epoch = None
            if epoch and epoch < cutoff:
                removed_count += 1
                print(f"[Queue] Expired & removed stale job: '{j.get('title')}' (was scheduled {j.get('scheduled_time')})", flush=True)
                continue
        kept.append(j)
    if removed_count > 0:
        save_queue(kept)
        print(f"[Queue] Cleaned {removed_count} expired stale jobs.", flush=True)
    return removed_count


def reset_stuck_rendering(max_rendering_hours: int = 2) -> int:
    """
    Resets jobs stuck in RENDERING status back to PENDING.
    This happens when GitHub Actions runner times out mid-job (45min limit).
    Jobs stuck in RENDERING for more than max_rendering_hours are considered crashed.
    Returns the number of jobs reset or removed.
    """
    q = load_queue()
    now = datetime.now()
    now_epoch = time.time()
    cutoff_24h = now_epoch - 86400  # jobs scheduled >24h ago are stale

    kept = []
    reset_count = 0
    for j in q:
        if j.get("status") == "RENDERING":
            started_at_str = j.get("started_at", "")
            scheduled_epoch = j.get("scheduled_epoch", 0) or 0
            try:
                started_at = datetime.strptime(started_at_str, "%Y-%m-%d %H:%M:%S")
                age_hours = (now - started_at).total_seconds() / 3600
                if age_hours > max_rendering_hours:
                    # If the original scheduled time is expired (>24h past),
                    # DELETE the job — don't reset to PENDING (avoids infinite loop!)
                    if scheduled_epoch and scheduled_epoch < cutoff_24h:
                        print(f"[Queue] DELETED expired RENDERING job: '{j.get('title')}' (stuck {age_hours:.1f}h, scheduled {j.get('scheduled_time')})", flush=True)
                        reset_count += 1
                        # Don't append to kept → effectively deletes it
                        continue
                    else:
                        # Recent job that timed out — reset to PENDING so it retries
                        j["status"] = "PENDING"
                        j["error"] = f"Reset: stuck in RENDERING for {age_hours:.1f}h (runner timeout)"
                        j.pop("started_at", None)
                        reset_count += 1
                        print(f"[Queue] Reset stuck RENDERING job: '{j.get('title')}' (stuck {age_hours:.1f}h)", flush=True)
                        kept.append(j)
                        continue
            except Exception:
                # Can't parse started_at — if epoch is expired, delete; else reset
                if scheduled_epoch and scheduled_epoch < cutoff_24h:
                    print(f"[Queue] DELETED unparseable RENDERING job: '{j.get('title')}'", flush=True)
                    reset_count += 1
                    continue
                else:
                    j["status"] = "PENDING"
                    j.pop("started_at", None)
                    reset_count += 1
                    kept.append(j)
                    continue
        kept.append(j)

    if reset_count > 0:
        save_queue(kept)
        print(f"[Queue] Handled {reset_count} stuck RENDERING jobs.", flush=True)
    return reset_count


def deduplicate_queue() -> int:
    """
    Removes duplicate PENDING jobs for the same (title + page) combination.
    Keeps only the earliest scheduled instance to prevent double-posting.
    Returns the number of duplicates removed.
    """
    q = load_queue()
    seen = {}  # (title_lower, page_id) -> first job encountered
    kept = []
    removed_count = 0
    for j in q:
        if j.get("status") != "PENDING":
            kept.append(j)
            continue
        title_key = (j.get("title", "").strip().lower(), str(j.get("target_page_ids", [])))
        if title_key in seen:
            removed_count += 1
            print(f"[Queue] Removed duplicate: '{j.get('title')}' for page {j.get('target_page_ids')}", flush=True)
        else:
            seen[title_key] = True
            kept.append(j)
    if removed_count > 0:
        save_queue(kept)
        print(f"[Queue] Removed {removed_count} duplicate jobs.", flush=True)
    return removed_count


def run_queue_housekeeping() -> dict:
    """
    Runs all queue maintenance tasks at the start of every GitHub Actions run:
    1. Reset RENDERING jobs stuck > 2hrs (runner timeout recovery)
    2. Remove PENDING jobs expired > 72hrs (avoid posting stale content)
    3. Remove duplicate (title + page) entries
    4. Auto-resolve schedule collisions (enforce >=30m spacing across queue)
    Returns summary dict of what was cleaned.
    """
    reset = reset_stuck_rendering(max_rendering_hours=2)
    expired = expire_stale_jobs(max_age_hours=72)
    dupes = deduplicate_queue()
    collisions_adjusted, _ = resolve_schedule_collisions(min_gap_seconds=1800, auto_align_past=True)
    if reset or expired or dupes or collisions_adjusted:
        _commit_queue_to_git("🤖 Queue: housekeeping — reset/expire/dedup/spacing [skip ci]")
    return {
        "reset_rendering": reset,
        "expired": expired,
        "duplicates_removed": dupes,
        "collisions_adjusted": collisions_adjusted
    }


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
            
        # Automatically delete the job from scheduled queue list so it is immediately removed
        delete_job(job_id)
        # Immediately push updated queue to GitHub so web UI reflects the change
        _commit_queue_to_git(f"🤖 Queue: completed '{job.get('title', job_id)}' [skip ci]")
        
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
        # Delete from scheduled queue list so failed jobs do not block future scheduled queue runs
        delete_job(job_id)
        # Immediately push updated queue to GitHub so web UI reflects the change
        _commit_queue_to_git(f"🤖 Queue: removed failed job '{job.get('title', job_id)}' [skip ci]")
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

import os
import sys
import json
import time
import shutil
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

CURR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURR_DIR.parent
if str(CURR_DIR) not in sys.path:
    sys.path.insert(0, str(CURR_DIR))

from config import JOBS_QUEUE_FILE, WORKSPACE_DIR, OUTPUT_DIR, BASE_DIR, load_settings, save_settings

logger = logging.getLogger("SelfHealingEngine")

_WATCHDOG_THREAD = None
_WATCHDOG_RUNNING = False
_WATCHDOG_LOCK = threading.Lock()

HEALING_EVENTS = []
MAX_HEALING_EVENTS = 50

def log_healing_event(component: str, action: str, details: str, status: str = "HEALED"):
    """Records a self-healing event in the system audit log."""
    event = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "component": component,
        "action": action,
        "details": details,
        "status": status
    }
    HEALING_EVENTS.insert(0, event)
    if len(HEALING_EVENTS) > MAX_HEALING_EVENTS:
        HEALING_EVENTS.pop()
    print(f"[{status}] [{component}] {action}: {details}")

def recover_crashed_jobs() -> int:
    """
    Scans jobs_queue.json upon boot or watchdog cycle.
    Safely recovers any jobs interrupted in RENDERING/PROCESSING state.
    """
    if not JOBS_QUEUE_FILE.exists():
        return 0
        
    recovered = 0
    try:
        with _WATCHDOG_LOCK:
            queue = json.loads(JOBS_QUEUE_FILE.read_text(encoding="utf-8"))
            modified = False
            for job in queue:
                status = job.get("status", "")
                if status in ("RENDERING", "PROCESSING", "GENERATING"):
                    job_id = job.get("id", "unknown")
                    job["status"] = "PENDING"
                    job["error"] = f"Auto-recovered from unexpected process restart (was {status})"
                    job["recovered_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    modified = True
                    recovered += 1
                    log_healing_event(
                        "QueueWatchdog",
                        "Job Crash Recovery",
                        f"Reset job '{job.get('title')}' ({job_id}) from {status} back to PENDING for retry."
                    )
            if modified:
                JOBS_QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error during job crash recovery: {e}")
        
    return recovered

def purge_stale_temporary_files(max_age_hours: int = 24) -> dict:
    """Cleans up old intermediate workspace directories to prevent disk overflow."""
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    purged_bytes = 0
    purged_dirs = 0
    
    if WORKSPACE_DIR.exists():
        for item in WORKSPACE_DIR.iterdir():
            try:
                if item.is_dir() and item.name.startswith(("cloud_job_", "job_", "temp_", "test_")):
                    mtime = item.stat().st_mtime
                    if mtime < cutoff:
                        dir_size = sum(f.stat().st_size for f in item.glob("**/*") if f.is_file())
                        shutil.rmtree(item, ignore_errors=True)
                        purged_bytes += dir_size
                        purged_dirs += 1
            except Exception:
                pass
                
    temp_store = BASE_DIR / "temp_cloud_store"
    if temp_store.exists():
        for f in temp_store.glob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < (now - (48 * 3600)):
                    purged_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
            except Exception:
                pass

    purged_mb = round(purged_bytes / (1024 * 1024), 2)
    if purged_dirs > 0 or purged_mb > 5.0:
        log_healing_event("DiskCleaner", "Storage Maintenance", f"Purged {purged_dirs} stale workspaces ({purged_mb} MB reclaimed).")
        
    return {"purged_dirs": purged_dirs, "reclaimed_mb": purged_mb}

def check_facebook_pages_health() -> list:
    """Probes all configured Facebook pages with Graph API to detect token validity."""
    from facebook_publisher import test_page_token
    cfg = load_settings()
    pages = cfg.get("facebook_pages", [])
    updated = False
    
    health_results = []
    for p in pages:
        p_id = p.get("id") or p.get("page_id")
        p_token = p.get("access_token")
        p_name = p.get("name") or p.get("page_name") or "Page"
        
        if not p.get("enabled", True):
            health_results.append({
                "page_id": p_id,
                "name": p_name,
                "status": "DISABLED",
                "message": "Page is paused by user."
            })
            continue
            
        test_res = test_page_token(p_id, p_token)
        if test_res.get("ok"):
            p["status"] = "CONNECTED"
            health_results.append({
                "page_id": p_id,
                "name": p_name,
                "status": "HEALTHY",
                "message": "Token valid & ready for publishing."
            })
        else:
            p["status"] = "TOKEN_ERROR"
            err_msg = test_res.get("error", "Unknown Graph API error")
            p["last_error"] = err_msg
            updated = True
            log_healing_event(
                "FacebookAuth",
                "Token Diagnostic",
                f"Page '{p_name}' ({p_id}) token issue: {err_msg}",
                status="WARNING"
            )
            health_results.append({
                "page_id": p_id,
                "name": p_name,
                "status": "ERROR",
                "message": err_msg
            })
            
    if updated:
        save_settings(cfg)
        
    return health_results

def check_image_providers_health() -> dict:
    """Tests availability of image generation engines."""
    cfg = load_settings()
    results = {}
    
    # Pollinations
    try:
        import urllib.request
        req = urllib.request.Request("https://image.pollinations.ai/prompt/ping", headers={"User-Agent": "HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            results["pollinations"] = {"status": "ONLINE" if resp.status == 200 else "DEGRADED"}
    except Exception as e:
        results["pollinations"] = {"status": "DEGRADED", "fallback": "Turbo/Cloudflare ready"}
        
    cf_acc = cfg.get("cloudflare_account_id")
    cf_tok = cfg.get("cloudflare_api_token")
    results["cloudflare"] = {"status": "CONFIGURED" if (cf_acc and cf_tok) else "STANDBY"}
    
    hf_tok = cfg.get("huggingface_token")
    results["huggingface"] = {"status": "CONFIGURED" if hf_tok else "STANDBY"}
    
    return results

def get_system_health() -> dict:
    """Returns a full real-time telemetry report for the Mission Control dashboard."""
    disk_usage = shutil.disk_usage(str(BASE_DIR))
    free_gb = round(disk_usage.free / (1024**3), 2)
    total_gb = round(disk_usage.total / (1024**3), 2)
    
    cfg = load_settings()
    pages_count = len(cfg.get("facebook_pages", []))
    active_pages = sum(1 for p in cfg.get("facebook_pages", []) if p.get("enabled", True))
    
    pending_count = 0
    published_count = 0
    failed_count = 0
    if JOBS_QUEUE_FILE.exists():
        try:
            q = json.loads(JOBS_QUEUE_FILE.read_text(encoding="utf-8"))
            pending_count = sum(1 for j in q if j.get("status") == "PENDING")
            published_count = sum(1 for j in q if j.get("status") == "PUBLISHED")
            failed_count = sum(1 for j in q if j.get("status") == "FAILED")
        except Exception:
            pass

    return {
        "status": "OPERATIONAL",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "watchdog": {
            "active": bool(_WATCHDOG_THREAD and _WATCHDOG_THREAD.is_alive()),
            "self_healing_enabled": True
        },
        "storage": {
            "free_gb": free_gb,
            "total_gb": total_gb,
            "percent_free": round((disk_usage.free / disk_usage.total) * 100, 1)
        },
        "queue": {
            "pending": pending_count,
            "published": published_count,
            "failed": failed_count,
            "total": pending_count + published_count + failed_count
        },
        "facebook_pages": {
            "total": pages_count,
            "active": active_pages
        },
        "providers": check_image_providers_health(),
        "recent_healing_events": HEALING_EVENTS[:15]
    }

def run_self_repair() -> dict:
    """Triggers an immediate complete system self-repair & diagnostics pass."""
    log_healing_event("SelfRepair", "Manual Trigger", "Initiated complete system self-healing diagnostics pass.")
    recovered_jobs = recover_crashed_jobs()
    purge_info = purge_stale_temporary_files(max_age_hours=12)
    fb_health = check_facebook_pages_health()
    
    return {
        "ok": True,
        "recovered_jobs": recovered_jobs,
        "purged_storage": purge_info,
        "facebook_pages_health": fb_health,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def _watchdog_loop():
    """Continuous background watchdog thread."""
    global _WATCHDOG_RUNNING
    logger.info("Watchdog daemon background loop active.")
    
    recover_crashed_jobs()
    
    cycle = 0
    while _WATCHDOG_RUNNING:
        try:
            recover_crashed_jobs()
            if cycle % 10 == 0:
                purge_stale_temporary_files(max_age_hours=24)
            cycle += 1
        except Exception as e:
            logger.error(f"Watchdog cycle error: {e}")
        time.sleep(60)

def start_watchdog():
    """Starts the Self-Healing Watchdog daemon thread."""
    global _WATCHDOG_THREAD, _WATCHDOG_RUNNING
    if _WATCHDOG_THREAD and _WATCHDOG_THREAD.is_alive():
        return
    _WATCHDOG_RUNNING = True
    _WATCHDOG_THREAD = threading.Thread(target=_watchdog_loop, daemon=True, name="SelfHealingWatchdog")
    _WATCHDOG_THREAD.start()
    log_healing_event("Watchdog", "Startup", "Autonomous Self-Healing Watchdog daemon initialized.")

# Convenience aliases
recover_interrupted_jobs = recover_crashed_jobs
purge_old_workspaces = purge_stale_temporary_files
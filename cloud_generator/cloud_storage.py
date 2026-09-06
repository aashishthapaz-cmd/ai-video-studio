import os
import json
import shutil
import time
from pathlib import Path
import sys

CURR_DIR = Path(__file__).resolve().parent
if str(CURR_DIR) not in sys.path:
    sys.path.insert(0, str(CURR_DIR))

from config import TEMP_CLOUD_DIR, JOBS_QUEUE_FILE, load_settings
from notifier import notify_local_sync

def get_storage_stats() -> dict:
    if not TEMP_CLOUD_DIR.exists():
        return {"total_files": 0, "total_size_mb": 0.0}
    files = list(TEMP_CLOUD_DIR.glob("*.mp4"))
    total_bytes = sum(f.stat().st_size for f in files if f.is_file())
    return {
        "total_files": len(files),
        "total_size_mb": round(total_bytes / (1024 * 1024), 2)
    }

def store_video_in_cloud_buffer(job_id: str, source_video_path: str, title: str) -> dict:
    TEMP_CLOUD_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(source_video_path)
    if not src.exists():
        return {"ok": False, "error": f"Source video {source_video_path} does not exist"}
        
    dest = TEMP_CLOUD_DIR / f"{job_id}.mp4"
    try:
        shutil.copy2(str(src), str(dest))
        meta_file = TEMP_CLOUD_DIR / f"{job_id}.json"
        meta = {
            "job_id": job_id,
            "title": title,
            "file_name": dest.name,
            "original_filename": src.name,
            "size_bytes": dest.stat().st_size,
            "created_at": time.time(),
            "synced_to_local": False
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {"ok": True, "dest_path": str(dest), "meta": meta}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_video_file_for_job(job_id: str) -> Path:
    target = TEMP_CLOUD_DIR / f"{job_id}.mp4"
    if target.exists():
        return target
    return None

def get_pending_sync_list() -> list:
    if not TEMP_CLOUD_DIR.exists():
        return []
    meta_files = list(TEMP_CLOUD_DIR.glob("*.json"))
    pending = []
    for mf in meta_files:
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            if not data.get("synced_to_local", False):
                video_file = TEMP_CLOUD_DIR / data.get("file_name", f"{data.get('job_id')}.mp4")
                if video_file.exists():
                    data["file_size_mb"] = round(video_file.stat().st_size / (1024 * 1024), 2)
                    pending.append(data)
        except Exception:
            continue
    return pending

def confirm_sync_and_delete(job_id: str) -> dict:
    cfg = load_settings()
    video_file = TEMP_CLOUD_DIR / f"{job_id}.mp4"
    meta_file = TEMP_CLOUD_DIR / f"{job_id}.json"
    
    if not video_file.exists() and not meta_file.exists():
        return {"ok": False, "error": f"Job {job_id} not found in cloud storage"}
        
    title = job_id
    filename = f"{job_id}.mp4"
    if meta_file.exists():
        try:
            mdata = json.loads(meta_file.read_text(encoding="utf-8"))
            title = mdata.get("title", job_id)
            filename = mdata.get("original_filename", f"{job_id}.mp4")
        except Exception:
            pass
            
    # Delete file from cloud buffer if auto delete enabled
    should_delete = cfg.get("cloud_auto_delete_after_sync", True)
    if should_delete:
        try:
            if video_file.exists():
                video_file.unlink()
            if meta_file.exists():
                meta_file.unlink()
        except Exception as e:
            return {"ok": False, "error": f"Failed to delete cloud buffer file: {e}"}
    else:
        if meta_file.exists():
            try:
                mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                mdata["synced_to_local"] = True
                meta_file.write_text(json.dumps(mdata, indent=2), encoding="utf-8")
            except Exception:
                pass
                
    stats = get_storage_stats()
    return {
        "ok": True,
        "job_id": job_id,
        "title": title,
        "cleaned_filename": filename,
        "remaining_cloud_files": stats["total_files"],
        "remaining_cloud_mb": stats["total_size_mb"]
    }

import os
import sys
import time
import argparse
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Add cloud_generator to path for notifier
sys.path.insert(0, str(PROJECT_ROOT / "cloud_generator"))
try:
    from notifier import notify_local_sync
except Exception:
    def notify_local_sync(files): pass

def run_sync_cycle(server_url: str = "http://127.0.0.1:8190") -> list:
    server_url = server_url.rstrip("/")
    print(f"[SYNC] Checking cloud sync endpoint at: {server_url}/api/sync/pending...")
    
    try:
        r = requests.get(f"{server_url}/api/sync/pending", timeout=10)
        if r.status_code != 200:
            print(f"[WARNING] Server returned status {r.status_code}: {r.text}")
            return []
        data = r.json()
        pending = data.get("pending_jobs", [])
    except Exception as e:
        print(f"[INFO] Cloud server not reachable ({e}). Will check again when PC is connected.")
        return []
        
    if not pending:
        print("[OK] Cloud buffer is empty (0 pending videos). All synced!")
        return []
        
    print(f"[FOUND] {len(pending)} video(s) ready to download to local PC...")
    downloaded_files = []
    
    for item in pending:
        job_id = item.get("job_id")
        title = item.get("title", job_id)
        filename = item.get("original_filename") or f"{title}.mp4"
        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-()").strip()
        if not safe_name.endswith(".mp4"):
            safe_name += ".mp4"
            
        target_path = OUTPUT_DIR / safe_name
        # Avoid overwriting existing files with same name
        counter = 1
        base_stem = target_path.stem
        while target_path.exists() and target_path.stat().st_size > 0:
            target_path = OUTPUT_DIR / f"{base_stem}_{counter}.mp4"
            counter += 1
            
        print(f"[DOWNLOADING] '{title}' ({item.get('file_size_mb', 0)} MB)...")
        download_url = f"{server_url}/api/sync/download/{job_id}"
        
        try:
            with requests.get(download_url, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            
            if target_path.exists() and target_path.stat().st_size > 0:
                print(f"[SAVED] {target_path} ({round(target_path.stat().st_size / (1024*1024), 2)} MB)")
                downloaded_files.append(str(target_path))
                
                # Confirm download to trigger cloud cleanup
                conf_res = requests.post(f"{server_url}/api/sync/confirm", json={"job_id": job_id}, timeout=10)
                if conf_res.status_code == 200:
                    cdata = conf_res.json()
                    print(f"[CLEANUP] Cloud file deleted for '{title}'. Remaining cloud MB: {cdata.get('remaining_cloud_mb', 0)}")
                else:
                    print(f"[WARNING] Cleanup confirmation response: {conf_res.text}")
        except Exception as err:
            print(f"[ERROR] Failed to download job {job_id}: {err}")
            
    if downloaded_files:
        print("=" * 60)
        print(f"[SUCCESS] {len(downloaded_files)} video(s) transferred to:")
        print(f"Folder: {OUTPUT_DIR}")
        print("=" * 60)
        notify_local_sync(downloaded_files)
        
    return downloaded_files

def main():
    parser = argparse.ArgumentParser(description="Local PC Video Auto-Sync Daemon")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:8190", help="Cloud Video Studio Server URL")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds (default: 60s)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("  AI Video Studio - Local PC Auto-Sync Daemon")
    print(f"  Target Output Folder: {OUTPUT_DIR}")
    print(f"  Cloud Server URL:     {args.server}")
    print("=" * 60)
    
    if args.once:
        run_sync_cycle(args.server)
        return
        
    print(f"[DAEMON] Running background polling loop every {args.interval}s (Press Ctrl+C to stop)...")
    while True:
        try:
            run_sync_cycle(args.server)
        except KeyboardInterrupt:
            print("\n[STOPPED] Auto-Sync Daemon stopped by user.")
            break
        except Exception as e:
            print(f"[LOOP ERROR] {e}")
        time.sleep(args.interval)

if __name__ == "__main__":
    main()

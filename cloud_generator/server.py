import os
import sys
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from cloud_generator.config import load_settings, save_settings, OUTPUT_DIR, TEMP_CLOUD_DIR
    from cloud_generator.pipeline import run_cloud_pipeline
    from cloud_generator.facebook_publisher import (
        test_page_token, 
        publish_to_all_enabled_pages, 
        get_publication_history, 
        publish_video_to_facebook_page,
        save_or_update_facebook_page,
        delete_facebook_page
    )
    from cloud_generator.bulk_scheduler import (
        parse_bulk_scripts, 
        enqueue_bulk_jobs, 
        load_queue, 
        delete_job, 
        execute_single_job, 
        start_scheduler,
        reorder_queue,
        retry_job,
        clear_completed_jobs
    )
    from cloud_generator.self_healing import start_watchdog, get_system_health, run_self_repair
    from cloud_generator.cloud_storage import get_pending_sync_list, get_video_file_for_job, confirm_sync_and_delete, get_storage_stats
    from cloud_generator.notifier import dispatch_alert, send_telegram_message, send_whatsapp_message
except ImportError:
    from config import load_settings, save_settings, OUTPUT_DIR, TEMP_CLOUD_DIR
    from pipeline import run_cloud_pipeline
    from facebook_publisher import (
        test_page_token, 
        publish_to_all_enabled_pages, 
        get_publication_history, 
        publish_video_to_facebook_page,
        save_or_update_facebook_page,
        delete_facebook_page
    )
    from bulk_scheduler import (
        parse_bulk_scripts, 
        enqueue_bulk_jobs, 
        load_queue, 
        delete_job, 
        execute_single_job, 
        start_scheduler,
        reorder_queue,
        retry_job,
        clear_completed_jobs
    )
    from self_healing import start_watchdog, get_system_health, run_self_repair
    from cloud_storage import get_pending_sync_list, get_video_file_for_job, confirm_sync_and_delete, get_storage_stats
    from notifier import dispatch_alert, send_telegram_message, send_whatsapp_message

WEB_DIR = Path(__file__).resolve().parent / "web"
PORT = int(os.getenv("PORT", os.getenv("APP_PORT", 8190)))

ACTIVE_JOB = {
    "running": False,
    "progress": 0,
    "status": "Ready",
    "title": "",
    "output_file": "",
    "facebook_results": [],
    "logs": []
}

def log_event(msg: str):
    ts = time.strftime("%H:%M:%S")
    ACTIVE_JOB["logs"].append(f"[{ts}] {msg}")
    if len(ACTIVE_JOB["logs"]) > 100:
        ACTIVE_JOB["logs"].pop(0)

def bg_generate(title: str, script: str, custom_vibe: str = "", auto_publish_fb: bool = False, target_page_ids: list = None):
    ACTIVE_JOB["running"] = True
    ACTIVE_JOB["progress"] = 5
    ACTIVE_JOB["status"] = "Starting generation..."
    ACTIVE_JOB["title"] = title
    ACTIVE_JOB["output_file"] = ""
    ACTIVE_JOB["facebook_results"] = []
    ACTIVE_JOB["logs"] = []
    
    def on_prog(pct, msg):
        ACTIVE_JOB["progress"] = pct
        ACTIVE_JOB["status"] = msg
        log_event(msg)
        
    try:
        res = run_cloud_pipeline(
            title=title, 
            script_text=script, 
            custom_vibe=custom_vibe,
            progress_callback=on_prog, 
            auto_publish_fb=auto_publish_fb,
            target_page_ids=target_page_ids
        )
        ACTIVE_JOB["output_file"] = res.get("output_file", "")
        ACTIVE_JOB["facebook_results"] = res.get("facebook_published", [])
        ACTIVE_JOB["status"] = "Completed successfully!"
        ACTIVE_JOB["progress"] = 100
        log_event(f"Finished rendering: {res.get('output_file')}")
        if res.get("facebook_published"):
            for fb in res.get("facebook_published"):
                status = "SUCCESS" if fb.get("ok") else f"FAILED ({fb.get('error')})"
                log_event(f"Facebook [{fb.get('page_name')}]: {status}")
    except Exception as e:
        ACTIVE_JOB["status"] = f"Error: {str(e)}"
        log_event(f"ERROR: {str(e)}")
    finally:
        ACTIVE_JOB["running"] = False

class CloudStudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ACTIVE_JOB).encode("utf-8"))
            return
            
        elif path == "/api/system/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_system_health()).encode("utf-8"))
            return
            
        elif path == "/api/settings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(load_settings()).encode("utf-8"))
            return

        elif path == "/api/bulk/queue":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"queue": load_queue()}).encode("utf-8"))
            return

        elif path == "/api/sync/pending":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            pending = get_pending_sync_list()
            stats = get_storage_stats()
            self.wfile.write(json.dumps({"pending_jobs": pending, "stats": stats}).encode("utf-8"))
            return

        elif path.startswith("/api/sync/download/"):
            job_id = path[len("/api/sync/download/"):]
            vfile = get_video_file_for_job(job_id)
            if not vfile or not vfile.exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Video for job {job_id} not found"}).encode("utf-8"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Disposition", f'attachment; filename="{vfile.name}"')
            self.send_header("Content-Length", str(vfile.stat().st_size))
            self.end_headers()
            with open(vfile, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
            return
            
        elif path.startswith("/outputs/") or path.startswith("/api/video/view/"):
            vname = path.replace("/outputs/", "").replace("/api/video/view/", "")
            vfile = OUTPUT_DIR / vname
            if not vfile.exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Video file not found"}).encode("utf-8"))
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(vfile.stat().st_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(vfile, "rb") as f:
                while chunk := f.read(65536):
                    self.wfile.write(chunk)
            return

        elif path == "/api/facebook/history":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_publication_history()).encode("utf-8"))
            return
            
        elif path == "/api/outputs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            files = []
            for p in sorted(OUTPUT_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)[:30]:
                files.append({
                    "name": p.name,
                    "path": str(p),
                    "url": f"/outputs/{p.name}",
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
                })
            self.wfile.write(json.dumps(files).encode("utf-8"))
            return
            
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        path = parsed.path
        
        if path == "/api/generate":
            if ACTIVE_JOB["running"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "A generation job is already active."}).encode("utf-8"))
                return
                
            payload = json.loads(post_body)
            title = payload.get("title", "Poetic Reflection")
            script = payload.get("script", "").strip()
            theme = payload.get("theme", "auto")
            auto_fb = payload.get("auto_publish_fb", False)
            target_pages = payload.get("target_page_ids", [])
            
            if not script:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Script text cannot be empty."}).encode("utf-8"))
                return
                
            t = threading.Thread(target=bg_generate, args=(title, script, theme, auto_fb, target_pages), daemon=True)
            t.start()
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": "Generation started"}).encode("utf-8"))
            return

        elif path == "/api/system/repair":
            report = run_self_repair()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "repair_report": report}).encode("utf-8"))
            return

        elif path == "/api/bulk/create":
            payload = json.loads(post_body)
            raw_text = payload.get("raw_text", "").strip()
            start_time = payload.get("start_time")
            interval = int(payload.get("interval_minutes", 120))
            voice = payload.get("voice", "cloud_cloning")
            theme = payload.get("theme", "auto")
            target_pages = payload.get("target_page_ids", [])
            
            if not raw_text:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Bulk script text cannot be empty"}).encode("utf-8"))
                return
                
            jobs = parse_bulk_scripts(
                raw_text, 
                start_time_str=start_time, 
                interval_minutes=interval, 
                default_voice=voice, 
                default_theme=theme,
                default_page_ids=target_pages
            )
            enqueued = enqueue_bulk_jobs(jobs)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "added_jobs": len(enqueued), "jobs": enqueued}).encode("utf-8"))
            return

        elif path == "/api/bulk/delete":
            payload = json.loads(post_body)
            job_id = payload.get("job_id", "")
            success = delete_job(job_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": success, "job_id": job_id}).encode("utf-8"))
            return

        elif path == "/api/bulk/run_now":
            payload = json.loads(post_body)
            job_id = payload.get("job_id", "")
            t = threading.Thread(target=execute_single_job, args=(job_id,), daemon=True)
            t.start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "message": f"Execution started for {job_id}"}).encode("utf-8"))
            return

        elif path == "/api/bulk/retry":
            payload = json.loads(post_body)
            job_id = payload.get("job_id", "")
            res = retry_job(job_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif path == "/api/bulk/reorder":
            payload = json.loads(post_body)
            order = payload.get("order", [])
            new_q = reorder_queue(order)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "queue": new_q}).encode("utf-8"))
            return

        elif path == "/api/bulk/clear_completed":
            removed = clear_completed_jobs()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "removed": removed}).encode("utf-8"))
            return

        elif path == "/api/facebook/page/save":
            payload = json.loads(post_body)
            res = save_or_update_facebook_page(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif path == "/api/facebook/page/delete":
            payload = json.loads(post_body)
            page_id = payload.get("page_id", "")
            success = delete_facebook_page(page_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": success, "page_id": page_id}).encode("utf-8"))
            return

        elif path == "/api/notify/test":
            payload = json.loads(post_body)
            msg = payload.get("message", "🔔 Test notification from AI Video Factory!")
            res = dispatch_alert(msg)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "results": res}).encode("utf-8"))
            return

        elif path == "/api/sync/confirm":
            payload = json.loads(post_body)
            job_id = payload.get("job_id", "")
            res = confirm_sync_and_delete(job_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
            
        elif path == "/api/settings":
            payload = json.loads(post_body)
            save_settings(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "settings": load_settings()}).encode("utf-8"))
            return

        elif path in ("/api/facebook/test", "/api/facebook/page/test"):
            payload = json.loads(post_body)
            page_id = payload.get("page_id", "")
            token = payload.get("access_token", "")
            res = test_page_token(page_id, token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif path == "/api/facebook/publish":
            payload = json.loads(post_body)
            video_name = payload.get("video_name", "")
            video_path = OUTPUT_DIR / video_name
            if not video_path.exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Video not found: {video_name}"}).encode("utf-8"))
                return
                
            title = payload.get("title", video_path.stem)
            description = payload.get("description", title)
            target_page_ids = payload.get("target_page_ids")
            results = publish_to_all_enabled_pages(video_path, title, description, target_page_ids=target_page_ids)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "results": results}).encode("utf-8"))
            return

def start_server():
    start_watchdog()
    start_scheduler()
    server = HTTPServer(("0.0.0.0", PORT), CloudStudioHandler)
    print(f"\n=======================================================")
    print(f"  AI Autonomous Video Factory & Multi-Page Studio is LIVE!")
    print(f"  URL: http://127.0.0.1:{PORT}")
    print(f"=======================================================\n")
    server.serve_forever()

if __name__ == "__main__":
    start_server()

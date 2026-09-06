import os
import sys
import io
import json
import time
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from cloud_generator.config import load_settings, save_settings, OUTPUT_DIR
    from cloud_generator.pipeline import run_cloud_pipeline
    from cloud_generator.bulk_scheduler import load_queue, save_queue, execute_single_job
    from cloud_generator.notifier import dispatch_alert, send_telegram_message, notify_job_success, notify_job_failure
    from cloud_generator.self_healing import run_self_repair
except ImportError:
    from config import load_settings, save_settings, OUTPUT_DIR
    from pipeline import run_cloud_pipeline
    from bulk_scheduler import load_queue, save_queue, execute_single_job
    from notifier import dispatch_alert, send_telegram_message, notify_job_success, notify_job_failure
    from self_healing import run_self_repair

def run():
    parser = argparse.ArgumentParser(description="Autonomous GitHub Actions Video Factory & Auto Publisher")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "direct", "queue"], help="Execution mode")
    parser.add_argument("--title", type=str, default="", help="Video Title")
    parser.add_argument("--script", type=str, default="", help="Poem or script text")
    parser.add_argument("--script-file", type=str, default="", help="Path to text script file")
    parser.add_argument("--vibe", type=str, default="", help="Visual aesthetic / art style")
    parser.add_argument("--publish-fb", type=str, default="true", help="Auto-publish to Facebook (true/false)")
    args = parser.parse_args()

    publish_fb = str(args.publish_fb).lower() in ("true", "1", "yes")

    print("=" * 70, flush=True)
    print("  🚀 GITHUB ACTIONS AUTONOMOUS VIDEO FACTORY & AUTO-POSTER", flush=True)
    print("=" * 70, flush=True)

    try:
        run_self_repair()
    except Exception as e:
        print(f"[Warning] Self-repair notice: {e}", flush=True)

    script_content = args.script.strip() or os.environ.get("SCRIPT_INPUT", "").strip()
    if not script_content and args.script_file:
        p = Path(args.script_file)
        if p.exists():
            script_content = p.read_text(encoding="utf-8").strip()

    # Mode 1: Direct Script Execution
    if script_content:
        title = args.title.strip() or os.environ.get("TITLE_INPUT", "").strip() or "Poetic Whispers"
        vibe = args.vibe.strip() or os.environ.get("VIBE_INPUT", "").strip()
        if vibe in ("Auto-Detect (Adaptive Multi-World)", "Typewriters Voice Nostalgia", ""):
            vibe = "typewriters_voice_nostalgia"

        print(f"\n[Mode: Direct] Starting generation for: '{title}'", flush=True)
        print(f"Aesthetic Vibe: {vibe or 'Adaptive Multi-World'}", flush=True)
        print(f"Auto-Publish Facebook: {publish_fb}", flush=True)

        def on_prog(pct, msg):
            print(f"[{pct}%] {msg}", flush=True)

        t0 = time.time()
        try:
            res = run_cloud_pipeline(
                title=title,
                script_text=script_content,
                custom_vibe=vibe,
                progress_callback=on_prog,
                auto_publish_fb=publish_fb
            )
            render_time = round(time.time() - t0, 2)
            out_file = res.get("output_file", "")
            fb_res = res.get("facebook_published", [])

            print(f"\n✅ Video generated successfully in {render_time}s!", flush=True)
            print(f"   Output: {out_file}", flush=True)
            print(f"   Duration: {res.get('duration')}s | Scenes: {res.get('scenes')}", flush=True)

            notify_job_success(
                job={"title": title},
                fb_results=fb_res,
                render_time=render_time,
                video_path=out_file
            )

        except Exception as err:
            print(f"\n❌ Error during video generation: {err}", flush=True)
            notify_job_failure(
                job={"title": title},
                error_msg=str(err)
            )
            sys.exit(1)

    # Mode 2: Queue Processor
    else:
        print("\n[Mode: Queue] Checking scheduled jobs queue...", flush=True)
        queue = load_queue()
        now_str = time.strftime("%Y-%m-%d %H:%M")

        pending_jobs = [j for j in queue if j.get("status") == "PENDING"]
        if not pending_jobs:
            print("ℹ️ No pending jobs found in queue. All caught up!", flush=True)
            return

        target_job = None
        for j in pending_jobs:
            sched = j.get("scheduled_time", "")
            if not sched or sched <= now_str:
                target_job = j
                break
        
        if not target_job:
            target_job = pending_jobs[0]

        job_id = target_job.get("id")
        job_title = target_job.get("title", "Scheduled Post")
        print(f"🎯 Processing queued job: '{job_title}' (ID: {job_id})...", flush=True)

        try:
            res = execute_single_job(job_id)
            if res.get("status") == "COMPLETED":
                print(f"\n✅ Queued Job '{job_title}' COMPLETED!", flush=True)
                print(f"   Output: {res.get('output_file')}", flush=True)
            else:
                print(f"\n⚠️ Job finished with status: {res.get('status')} - Error: {res.get('error')}", flush=True)
                sys.exit(1)
        except Exception as err:
            print(f"\n❌ Failed to process job {job_id}: {err}", flush=True)
            sys.exit(1)

    print("\n" + "=" * 70, flush=True)
    print("  AUTONOMOUS GITHUB RUNNER FINISHED SUCCESSFULLY", flush=True)
    print("=" * 70, flush=True)

if __name__ == "__main__":
    run()

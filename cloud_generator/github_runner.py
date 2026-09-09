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
    from cloud_generator.bulk_scheduler import (
        load_queue, save_queue, execute_single_job,
        parse_bulk_scripts, enqueue_bulk_jobs
    )
    from cloud_generator.notifier import dispatch_alert, send_telegram_message, notify_job_success, notify_job_failure
    from cloud_generator.self_healing import run_self_repair
except ImportError:
    from config import load_settings, save_settings, OUTPUT_DIR
    from pipeline import run_cloud_pipeline
    from bulk_scheduler import (
        load_queue, save_queue, execute_single_job,
        parse_bulk_scripts, enqueue_bulk_jobs
    )
    from notifier import dispatch_alert, send_telegram_message, notify_job_success, notify_job_failure
    from self_healing import run_self_repair


def _inject_fb_pages_from_env(cfg: dict) -> dict:
    """Inject FACEBOOK_PAGES_JSON env var or DISPATCH_PAYLOAD into settings."""
    pages_json = os.environ.get("FACEBOOK_PAGES_JSON", "").strip()

    # Check if dispatch payload has pages
    dispatch_payload_str = os.environ.get("DISPATCH_PAYLOAD", "").strip()
    if dispatch_payload_str and dispatch_payload_str != "null":
        try:
            d_payload = json.loads(dispatch_payload_str)
            if isinstance(d_payload, dict) and "facebook_pages" in d_payload:
                d_pages = d_payload["facebook_pages"]
                if isinstance(d_pages, list) and d_pages:
                    pages_json = json.dumps(d_pages)
        except Exception:
            pass

    if not pages_json:
        return cfg
    try:
        pages = json.loads(pages_json)
        if isinstance(pages, list) and pages:
            # Skip placeholder entries
            real_pages = []
            for p in pages:
                pid = str(p.get("page_id") or p.get("id") or "")
                tok = str(p.get("access_token") or "")
                if pid and "YOUR_" not in pid and tok and "YOUR_" not in tok:
                    real_pages.append(p)
            if real_pages:
                cfg["facebook_pages"] = real_pages
                cfg["auto_publish_facebook"] = True
                print(f"[FB] Loaded {len(real_pages)} Facebook page(s) successfully.", flush=True)
                for p in real_pages:
                    tok_preview = (p.get('access_token') or '')[:12] + '••••••••'
                    print(f"     - {p.get('name', 'Unknown')} | Page ID: {p.get('page_id') or p.get('id')} | Token: {tok_preview} | Niche: {p.get('niche_id', 'auto')}", flush=True)
    except Exception as e:
        print(f"[FB] Warning: Failed to parse FACEBOOK_PAGES_JSON: {e}", flush=True)
    return cfg


def _resolve_target_page_ids(target_page_input: str, all_pages: list) -> list:
    """Resolve target page IDs from workflow input string."""
    if not target_page_input or target_page_input in ("ALL Pages", "ALL", "all", ""):
        return []  # Empty = all enabled pages
    # Extract page_id from format "Page Name (PAGE_ID)"
    import re
    m = re.search(r'\((\d+)\)', target_page_input)
    if m:
        return [m.group(1)]
    if target_page_input.strip().isdigit():
        return [target_page_input.strip()]
    # Try matching by name
    for p in all_pages:
        p_name = p.get("name", "")
        if p_name and (p_name.lower() in target_page_input.lower() or target_page_input.lower() in p_name.lower()):
            return [str(p.get("page_id") or p.get("id"))]
    return []


def run():
    parser = argparse.ArgumentParser(description="Autonomous GitHub Actions Video Factory & Auto Publisher")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "direct", "queue", "bulk"], help="Execution mode")
    parser.add_argument("--title", type=str, default="", help="Video Title")
    parser.add_argument("--script", type=str, default="", help="Poem or script text")
    parser.add_argument("--script-file", type=str, default="", help="Path to text script file")
    parser.add_argument("--vibe", type=str, default="", help="Visual aesthetic / art style")
    parser.add_argument("--niche", type=str, default="", help="Poetry Niche")
    parser.add_argument("--publish-fb", type=str, default="true", help="Auto-publish to Facebook (true/false)")
    parser.add_argument("--target-page", type=str, default="", help="Target page ID(s), comma-separated")
    args = parser.parse_args()

    publish_fb = str(args.publish_fb).lower() in ("true", "1", "yes")

    print("=" * 70, flush=True)
    print("  🚀 GITHUB ACTIONS AUTONOMOUS VIDEO FACTORY & AUTO-POSTER", flush=True)
    print("=" * 70, flush=True)

    try:
        run_self_repair()
    except Exception as e:
        print(f"[Warning] Self-repair notice: {e}", flush=True)

    # Load settings and inject FB pages from environment
    cfg = load_settings()
    cfg = _inject_fb_pages_from_env(cfg)
    all_pages = cfg.get("facebook_pages", [])
    enabled_pages = [p for p in all_pages if p.get("enabled", True)]

    # Resolve inputs from env (GitHub Actions workflow_dispatch)
    script_content = args.script.strip() or os.environ.get("SCRIPT_INPUT", "").strip()
    if not script_content and args.script_file:
        p = Path(args.script_file)
        if p.exists():
            script_content = p.read_text(encoding="utf-8").strip()

    bulk_poems = os.environ.get("BULK_POEMS_INPUT", "").strip()
    bulk_start_time = os.environ.get("BULK_START_TIME_INPUT", "").strip()
    target_page_input = args.target_page.strip() or os.environ.get("TARGET_PAGE_INPUT", "").strip()
    publish_fb_env = os.environ.get("PUBLISH_FB_INPUT", "").strip().lower()
    if publish_fb_env in ("true", "1", "yes", "false", "0", "no"):
        publish_fb = publish_fb_env in ("true", "1", "yes")

    # Check for repository_dispatch payload
    dispatch_payload_str = os.environ.get("DISPATCH_PAYLOAD", "").strip()
    dispatch_payload = {}
    if dispatch_payload_str and dispatch_payload_str != "null":
        try:
            dispatch_payload = json.loads(dispatch_payload_str)
        except Exception:
            pass

    # Merge dispatch payload into inputs
    if dispatch_payload:
        if not script_content:
            script_content = dispatch_payload.get("script_text", dispatch_payload.get("script", "")).strip()
        if not bulk_poems:
            bulk_poems = dispatch_payload.get("bulk_poems", "").strip()

    # Resolve target page IDs
    target_page_ids = _resolve_target_page_ids(target_page_input, all_pages)

    print(f"\n[Config] Enabled FB pages: {len(enabled_pages)}", flush=True)
    for p in enabled_pages:
        print(f"         → {p.get('name')} | ID: {p.get('page_id') or p.get('id')} | Niche: {p.get('niche_id','auto')} | Slots: {p.get('usa_time_slots', ['08:30','13:00','20:30'])}", flush=True)
    if target_page_ids:
        print(f"[Config] Targeting specific page(s): {target_page_ids}", flush=True)
    else:
        print(f"[Config] Targeting: ALL enabled pages", flush=True)

    # ─── MODE: BULK SCHEDULE ─────────────────────────────────────────────
    if bulk_poems:
        bulk_interval_str = os.environ.get("BULK_INTERVAL_INPUT", "").strip()
        interval_minutes = 120
        if bulk_interval_str:
            if bulk_interval_str in ("60", "1h", "1"):
                interval_minutes = 60
            elif bulk_interval_str in ("120", "2h", "2"):
                interval_minutes = 120
            elif bulk_interval_str in ("180", "3h", "3"):
                interval_minutes = 180
            elif bulk_interval_str in ("240", "4h", "4"):
                interval_minutes = 240
            elif bulk_interval_str in ("360", "6h", "6"):
                interval_minutes = 360
            elif bulk_interval_str in ("720", "12h", "12"):
                interval_minutes = 720
            elif bulk_interval_str in ("1440", "24h", "24", "1d"):
                interval_minutes = 1440
            elif bulk_interval_str.isdigit():
                interval_minutes = int(bulk_interval_str)

        print(f"\n[Mode: Bulk Schedule] Parsing poem batch with {interval_minutes}m interval...", flush=True)

        page_ids_for_bulk = target_page_ids if target_page_ids else []
        is_auto_distribute = (not target_page_ids or len(target_page_ids) == 0 or target_page_input in ("ALL Pages", "ALL", "all", ""))

        jobs = parse_bulk_scripts(
            raw_text=bulk_poems,
            start_time_str=bulk_start_time or None,
            interval_minutes=interval_minutes,
            default_page_ids=page_ids_for_bulk,
            auto_distribute_pages=is_auto_distribute,
            available_pages=enabled_pages,
            timezone_str="Asia/Kathmandu"
        )

        if not jobs:
            print("⚠️ No valid poems found in bulk input.", flush=True)
            return

        enqueue_bulk_jobs(jobs)
        print(f"\n✅ Enqueued {len(jobs)} poem jobs across {len(enabled_pages)} Facebook Page(s)!", flush=True)
        for j in jobs:
            sched_str = j.get('scheduled_time_nepal', j.get('scheduled_time_usa', j.get('scheduled_time', 'ASAP')))
            print(f"   📅 '{j['title']}' → {sched_str} | Page(s): {j.get('target_page_ids', 'ALL')} | Niche: {j.get('niche_id')}", flush=True)
        return

    # ─── MODE: DIRECT SCRIPT ─────────────────────────────────────────────
    if script_content:
        title = args.title.strip() or os.environ.get("TITLE_INPUT", "").strip() or "Poetic Whispers"
        vibe = args.vibe.strip() or os.environ.get("VIBE_INPUT", "").strip()
        if vibe in ("Auto-Detect (Adaptive Multi-World)", "Typewriters Voice Nostalgia", ""):
            vibe = "typewriters_voice_nostalgia"

        niche_in = args.niche.strip() or os.environ.get("NICHE_INPUT", "").strip()
        if niche_in in ("Auto-Detect from Poem", ""):
            niche_in = ""

        print(f"\n[Mode: Direct] Starting generation for: '{title}'", flush=True)
        print(f"Aesthetic Vibe: {vibe or 'Adaptive Multi-World'}", flush=True)
        print(f"Poetry Niche: {niche_in or 'Auto-Detect'}", flush=True)
        print(f"Auto-Publish Facebook: {publish_fb}", flush=True)
        if target_page_ids:
            print(f"Target Page IDs: {target_page_ids}", flush=True)

        def on_prog(pct, msg):
            print(f"[{pct}%] {msg}", flush=True)

        t0 = time.time()
        try:
            res = run_cloud_pipeline(
                title=title,
                script_text=script_content,
                custom_vibe=vibe,
                progress_callback=on_prog,
                auto_publish_fb=publish_fb,
                niche_id=niche_in,
                target_page_ids=target_page_ids if target_page_ids else None
            )
            render_time = round(time.time() - t0, 2)
            out_file = res.get("output_file", "")
            fb_res = res.get("facebook_published", [])

            print(f"\n✅ Video generated successfully in {render_time}s!", flush=True)
            print(f"   Output: {out_file}", flush=True)
            print(f"   Duration: {res.get('duration')}s | Scenes: {res.get('scenes')}", flush=True)

            if fb_res:
                print(f"\n📘 Facebook Publishing Results ({len(fb_res)} page(s)):", flush=True)
                for r in fb_res:
                    status_icon = "✅" if (r.get("ok") or r.get("success")) else "❌"
                    post_id = r.get("video_id") or r.get("post_id") or r.get("error", "unknown")
                    print(f"   {status_icon} {r.get('page_name', r.get('page_id', '?'))}: {post_id}", flush=True)

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

    # ─── MODE: QUEUE PROCESSOR ───────────────────────────────────────────
    else:
        print("\n[Mode: Queue] Checking scheduled jobs queue...", flush=True)
        queue = load_queue()
        now_str = time.strftime("%Y-%m-%d %H:%M")

        pending_jobs = [j for j in queue if j.get("status") == "PENDING"]
        if not pending_jobs:
            print("ℹ️ No pending jobs found in queue. All caught up!", flush=True)
            return

        # Filter to target page if specified
        if target_page_ids:
            page_pending = [
                j for j in pending_jobs
                if any(pid in (j.get("target_page_ids") or []) for pid in target_page_ids)
            ]
            if page_pending:
                pending_jobs = page_pending
                print(f"[Queue] Filtered to {len(pending_jobs)} jobs for page(s): {target_page_ids}", flush=True)

        # Collect ALL jobs that are due now (not just the first one)
        now_epoch = time.time()
        due_jobs = []
        overdue_fallback = None  # fallback: oldest job if nothing is due yet
        for j in pending_jobs:
            epoch = j.get("scheduled_epoch")
            sched = j.get("scheduled_time", "")
            if epoch and isinstance(epoch, (int, float)):
                if now_epoch >= epoch:
                    due_jobs.append(j)
                elif overdue_fallback is None:
                    overdue_fallback = j
            elif not sched or sched <= now_str:
                due_jobs.append(j)
            elif overdue_fallback is None:
                overdue_fallback = j

        if not due_jobs:
            # No posts are due yet — process the oldest one anyway so no post is lost
            if overdue_fallback:
                due_jobs = [overdue_fallback]
                print(f"[Queue] No posts due yet. Processing next queued job: '{overdue_fallback.get('title')}' as fallback.", flush=True)
            else:
                print("ℹ️ No jobs due yet and no fallback available.", flush=True)
                return

        print(f"\n🚀 Processing {len(due_jobs)} due job(s) this run...", flush=True)

        overall_ok = True
        for idx, target_job in enumerate(due_jobs):
            job_id = target_job.get("id")
            job_title = target_job.get("title", "Scheduled Post")
            print(f"\n[{idx+1}/{len(due_jobs)}] 🎯 Processing: '{job_title}' (ID: {job_id}) | Niche: {target_job.get('niche_id')} | Page(s): {target_job.get('target_page_ids', 'ALL')}", flush=True)

            try:
                res = execute_single_job(job_id)
                if res.get("ok") or res.get("status") == "COMPLETED":
                    print(f"\n✅ Job '{job_title}' COMPLETED!", flush=True)
                    print(f"   Output: {res.get('output_file')}", flush=True)

                    fb_res = res.get("facebook_results", [])
                    if fb_res:
                        print(f"\n📘 Facebook Publishing Results ({len(fb_res)} page(s)):", flush=True)
                        for r in fb_res:
                            status_icon = "✅" if (r.get("ok") or r.get("success")) else "❌"
                            post_id = r.get("video_id") or r.get("post_id") or r.get("error", "unknown")
                            print(f"   {status_icon} {r.get('page_name', r.get('page_id', '?'))}: {post_id}", flush=True)
                else:
                    print(f"\n⚠️ Job '{job_title}' finished with status: {res.get('status')} - Error: {res.get('error')}", flush=True)
                    overall_ok = False
            except Exception as err:
                print(f"\n❌ Failed to process job {job_id} ('{job_title}'): {err}", flush=True)
                overall_ok = False

        if not overall_ok:
            sys.exit(1)


    print("\n" + "=" * 70, flush=True)
    print("  AUTONOMOUS GITHUB RUNNER FINISHED SUCCESSFULLY", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    run()

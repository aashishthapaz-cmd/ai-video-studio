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
        parse_bulk_scripts, enqueue_bulk_jobs,
        run_queue_housekeeping, _commit_queue_to_git
    )
    from cloud_generator.notifier import (
        dispatch_alert, send_telegram_message,
        notify_job_start, notify_job_success, notify_job_failure
    )
    from cloud_generator.self_healing import run_self_repair
    from cloud_generator.facebook_publisher import is_already_published_to_page
except ImportError:
    from config import load_settings, save_settings, OUTPUT_DIR
    from pipeline import run_cloud_pipeline
    from bulk_scheduler import (
        load_queue, save_queue, execute_single_job,
        parse_bulk_scripts, enqueue_bulk_jobs,
        run_queue_housekeeping, _commit_queue_to_git
    )
    from notifier import (
        dispatch_alert, send_telegram_message,
        notify_job_start, notify_job_success, notify_job_failure
    )
    from self_healing import run_self_repair
    from facebook_publisher import is_already_published_to_page


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
                pid = str(p.get("page_id") or p.get("id") or "").strip()
                tok = str(p.get("access_token") or p.get("token") or "").strip()
                if pid and "YOUR_" not in pid and tok and "YOUR_" not in tok:
                    p["page_id"] = pid
                    p["id"] = pid
                    p["access_token"] = tok
                    real_pages.append(p)
            if real_pages:
                cfg["facebook_pages"] = real_pages
                cfg["auto_publish_facebook"] = True
                save_settings(cfg)
                print(f"[FB] Loaded {len(real_pages)} Facebook page(s) successfully.", flush=True)
                for p in real_pages:
                    tok_preview = (p.get('access_token') or '')[:12] + '••••••••'
                    print(f"     - {p.get('name') or p.get('page_name', 'Unknown')} | Page ID: {p.get('page_id')} | Token: {tok_preview} | Niche: {p.get('niche_id', 'auto')}", flush=True)
    except Exception as e:
        print(f"[FB] Warning: Failed to parse FACEBOOK_PAGES_JSON: {e}", flush=True)
    return cfg


def _resolve_target_page_ids(target_page_input: str, all_pages: list) -> list:
    """Resolve target page IDs from workflow input string."""
    clean_in = str(target_page_input or "").strip()
    if not clean_in or clean_in in ("ALL Pages", "ALL", "all"):
        return []  # Empty = all enabled pages
    # Extract page_id from format "Page Name (PAGE_ID)"
    import re
    m = re.search(r'\((\d+)\)', clean_in)
    if m:
        return [m.group(1)]
    if clean_in.isdigit():
        return [clean_in]
    def _norm_name(s: str) -> str:
        s = s.lower().replace("whishper", "whisper")
        return re.sub(r'[^a-z0-9]', '', s)

    norm_in = _norm_name(clean_in)
    # Try matching by name
    for p in all_pages:
        p_name = str(p.get("name") or p.get("page_name") or "")
        norm_p = _norm_name(p_name)
        if norm_p and (norm_p in norm_in or norm_in in norm_p):
            pid = str(p.get("page_id") or p.get("id") or "").strip()
            if pid:
                return [pid]
    # If a specific target was given but not resolved by name, preserve raw input
    # so downstream never defaults back to "all pages"
    return [clean_in]


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

        # ── Strict Deduplication Guard: Check if already published before generating ──
        clean_title_check = title.strip().lower()
        if publish_fb and clean_title_check and clean_title_check not in ("poetic whispers", "untitled", "test"):
            try:
                pages_to_check = target_page_ids if target_page_ids else [str(p.get('id') or p.get('page_id')) for p in enabled_pages]
                pages_already_done = []
                for pid in pages_to_check:
                    p_tok = next((p.get("access_token") for p in enabled_pages if str(p.get("id") or p.get("page_id")) == str(pid)), None)
                    is_dup, reason = is_already_published_to_page(title, str(pid), access_token=p_tok, max_age_hours=24)
                    if is_dup:
                        pages_already_done.append((pid, reason))

                if pages_to_check and len(pages_already_done) == len(pages_to_check):
                    print(f"\n🛑 [Deduplication Guard] '{title}' was already successfully published to target page(s) recently! Skipping redundant generation & upload.", flush=True)
                    for pid, reason in pages_already_done:
                        print(f"   → Target {pid}: {reason}", flush=True)
                    # Clean up matching pending item from jobs_queue.json if present
                    try:
                        q = load_queue()
                        init_len = len(q)
                        q = [j for j in q if j.get("title", "").strip().lower() != clean_title_check]
                        if len(q) < init_len:
                            save_queue(q)
                            _commit_queue_to_git(f"🤖 Queue: auto-removed duplicate job '{title}' [skip ci]")
                    except Exception:
                        pass
                    return
            except Exception as e:
                print(f"[Deduplication] Early check notice: {e}", flush=True)

        # Notify Telegram & alerts that video production has started
        try:
            notify_job_start({
                "title": title,
                "scheduled_time": "Now (Immediate Run)",
                "target_page_ids": target_page_ids,
                "theme": vibe or "Anime / Poetic Parallax"
            })
        except Exception as e:
            print(f"[Warning] Failed to send start alert: {e}", flush=True)

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

            # Auto-remove matching queued job from jobs_queue.json so it never lingers
            try:
                q = load_queue()
                init_len = len(q)
                clean_title = title.strip().lower()
                q = [j for j in q if j.get("title", "").strip().lower() != clean_title]
                if len(q) < init_len:
                    save_queue(q)
                    print(f"[Queue] Removed dispatched job '{title}' from scheduled queue.", flush=True)
                    _commit_queue_to_git(f"🤖 Queue: auto-removed dispatched job '{title}' [skip ci]")
            except Exception as e:
                print(f"[Queue] Note on queue sync: {e}", flush=True)

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

        # ── STEP 1: Housekeeping — run at start of EVERY queue run ──────────
        # Fixes stuck RENDERING jobs, removes expired stale posts, deduplicates
        hk = run_queue_housekeeping()
        if any(hk.values()):
            print(f"[Queue] Housekeeping: reset={hk['reset_rendering']}, expired={hk['expired']}, dupes={hk['duplicates_removed']}", flush=True)

        queue = load_queue()
        now_epoch = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M")

        pending_jobs = [j for j in queue if j.get("status") == "PENDING"]
        if not pending_jobs:
            print("ℹ️ No pending jobs found in queue. All caught up!", flush=True)
            return

        # Filter to target page if specified
        if target_page_ids:
            target_ids_set = {str(x).strip().lower() for x in target_page_ids if str(x).strip()}
            def _matches_target(j):
                job_pages = [str(x).strip().lower() for x in (j.get("target_page_ids") or [])]
                return any(t in job_pages for t in target_ids_set)
            page_pending = [j for j in pending_jobs if _matches_target(j)]
            if page_pending:
                pending_jobs = page_pending
                print(f"[Queue] Filtered to {len(pending_jobs)} jobs for page(s): {target_page_ids}", flush=True)
            else:
                print(f"ℹ️ [Queue] No pending jobs found matching target page(s) {target_page_ids}. Halting cleanly to avoid unintended cross-posting.", flush=True)
                return

        # ── STEP 2: Collect DUE or NEAR-DUE jobs (Early Trigger Window: +-5 minutes) ──
        # If post time is coming up in next 5 minutes (300s) OR already due in past,
        # trigger generation early so 3-5min video rendering finishes right on target!
        EARLY_TRIGGER_WINDOW_SEC = 300  # 5 minutes buffer
        due_jobs = []
        for j in pending_jobs:
            epoch = j.get("scheduled_epoch")
            sched = j.get("scheduled_time", "")
            is_due = False

            if epoch and isinstance(epoch, (int, float)):
                diff_sec = epoch - now_epoch
                # Due if overdue (diff_sec <= 0) OR coming up within next 5 mins (0 < diff_sec <= 300)
                if diff_sec <= EARLY_TRIGGER_WINDOW_SEC:
                    is_due = True
                    if diff_sec > 0:
                        print(f"[Queue] ⏰ Early Trigger: '{j.get('title')}' is due in {diff_sec/60:.1f}m (<={EARLY_TRIGGER_WINDOW_SEC/60:.0f}m) -> Starting early generation!", flush=True)
                    elif diff_sec >= -300:
                        print(f"[Queue] 🎯 Target Post Window: '{j.get('title')}' is scheduled now ({abs(diff_sec)/60:.1f}m past target) -> Generating!", flush=True)
                    else:
                        print(f"[Queue] ⚡ Catch-Up: '{j.get('title')}' is overdue by {abs(diff_sec)/60:.1f}m -> Generating immediately!", flush=True)
            elif sched:
                try:
                    clean_sched = re.sub(r'\s+[A-Za-z/_-]+$', '', sched.strip())
                    sched_dt = datetime.strptime(clean_sched, "%Y-%m-%d %H:%M")
                    from zoneinfo import ZoneInfo
                    sched_epoch_val = sched_dt.replace(tzinfo=ZoneInfo("Asia/Kathmandu")).timestamp()
                    diff_sec = sched_epoch_val - now_epoch
                    if diff_sec <= EARLY_TRIGGER_WINDOW_SEC:
                        is_due = True
                except Exception:
                    if sched <= now_str:
                        is_due = True

            if is_due:
                due_jobs.append(j)

        # ── STEP 2.5: Strict Deduplication against Publication History ────
        filtered_due_jobs = []
        for j in due_jobs:
            j_title = j.get("title", "")
            j_targets = j.get("target_page_ids") or []
            if not j_targets:
                j_targets = [str(p.get('id') or p.get('page_id')) for p in enabled_pages]

            try:
                all_published = True
                for pid in j_targets:
                    p_tok = next((p.get("access_token") for p in enabled_pages if str(p.get("id") or p.get("page_id")) == str(pid)), None)
                    is_dup, reason = is_already_published_to_page(j_title, str(pid), access_token=p_tok, max_age_hours=24)
                    if not is_dup:
                        all_published = False
                        break
                if all_published and j_targets:
                    print(f"🛑 [Queue Deduplication] Job '{j_title}' was already successfully published to target page(s). Auto-removing from queue.", flush=True)
                    q = load_queue()
                    q = [x for x in q if x.get("id") != j.get("id")]
                    save_queue(q)
                    _commit_queue_to_git(f"🤖 Queue: auto-removed already published job '{j_title}' [skip ci]")
                    continue
            except Exception as e:
                pass
            filtered_due_jobs.append(j)
        due_jobs = filtered_due_jobs

        if not due_jobs:
            next_job = pending_jobs[0] if pending_jobs else None
            if next_job:
                next_time = next_job.get("scheduled_time", "unknown")
                next_ep = next_job.get("scheduled_epoch", 0)
                diff_m = (next_ep - now_epoch) / 60.0 if next_ep else 0
                print(f"ℹ️ No jobs due yet. Next scheduled: '{next_job.get('title')}' at {next_time} (in {diff_m:.1f}m)", flush=True)
            else:
                print("ℹ️ No jobs due yet.", flush=True)
            return

        # ── STEP 3: Process max 1 job per run (GitHub Actions = 45min limit) ─
        # Each video generation takes 5-30min. Processing more than 1 per run
        # risks timeout, which leaves jobs stuck in RENDERING state.
        # The hourly cron means multiple due jobs will each get their own run.
        MAX_JOBS_PER_RUN = 1
        if len(due_jobs) > MAX_JOBS_PER_RUN:
            print(f"[Queue] {len(due_jobs)} jobs due. Processing {MAX_JOBS_PER_RUN} this run (hourly cron will handle the rest).", flush=True)
            due_jobs = due_jobs[:MAX_JOBS_PER_RUN]

        print(f"\n🚀 Processing {len(due_jobs)} job(s) this run...", flush=True)

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
                    # Check if more due/near-due jobs remain and dispatch next runner sequentially
                    _trigger_next_workflow_run_if_due()
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


def _trigger_next_workflow_run_if_due():
    """
    If there are more due or near-due jobs waiting in the queue,
    trigger the next GitHub Actions workflow run immediately via repository dispatch
    so subsequent jobs don't have to wait for the next cron cycle.
    """
    try:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not token or not repo:
            return
        q = load_queue()
        now_ep = time.time()
        EARLY_TRIGGER_WINDOW_SEC = 300
        remaining_due = [
            j for j in q
            if j.get("status") == "PENDING" and (j.get("scheduled_epoch", 0) - now_ep) <= EARLY_TRIGGER_WINDOW_SEC
        ]
        if remaining_due:
            next_j = remaining_due[0]
            diff_m = (next_j.get("scheduled_epoch", 0) - now_ep) / 60.0
            print(f"\n[Queue Chaining] 🚀 Found {len(remaining_due)} more due/near-due job(s) in queue! Next: '{next_j.get('title')}' (in {diff_m:.1f}m).", flush=True)
            print(f"[Queue Chaining] Dispatching next GitHub Actions runner immediately...", flush=True)
            import requests
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json"
            }
            res = requests.post(
                f"https://api.github.com/repos/{repo}/actions/workflows/auto_video_poster.yml/dispatches",
                headers=headers,
                json={"ref": os.environ.get("GITHUB_REF_NAME", "main")}
            )
            if res.status_code in (200, 204):
                print(f"[Queue Chaining] ✅ Successfully triggered next runner run for '{next_j.get('title')}'!", flush=True)
            else:
                print(f"[Queue Chaining] Note: Dispatch response {res.status_code}: {res.text}", flush=True)
    except Exception as e:
        print(f"[Queue Chaining] Note: Chaining dispatch notice: {e}", flush=True)


if __name__ == "__main__":
    run()

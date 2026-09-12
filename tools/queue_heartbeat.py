"""
Queue Heartbeat Daemon
----------------------
Runs lightweight local checks every 60 seconds.
If a post is due (or coming up within 5 minutes) and GitHub Actions isn't already running,
it triggers the GitHub workflow dispatch API immediately with zero cron delays.
"""

import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
REPO = "aashishthapaz-cmd/ai-video-studio"
WORKFLOW_FILE = "auto_video_poster.yml"
EARLY_WINDOW_SEC = 300  # Trigger 5 minutes before scheduled time for rendering buffer

# Read GitHub token from environment or local .env
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GH_TOKEN="):
                TOKEN = line.split("=", 1)[1].strip()
                break

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Autonomous-Studio-Heartbeat"
}


def is_action_currently_running():
    """Check if any run of auto_video_poster is currently in_progress or queued."""
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=5"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for run in r.json().get("workflow_runs", []):
                if run.get("status") in ["queued", "in_progress"]:
                    return True, run.get("id"), run.get("status")
        return False, None, None
    except Exception as e:
        print(f"[Heartbeat] Warning checking action status: {e}")
        return False, None, None


def trigger_workflow_dispatch():
    """Trigger the GitHub workflow dispatch API."""
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": "main"}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        if r.status_code in [204, 201]:
            print(f"[Heartbeat] 🚀 Successfully dispatched '{WORKFLOW_FILE}' on GitHub Actions!")
            return True
        else:
            print(f"[Heartbeat] ❌ Dispatch failed ({r.status_code}): {r.text}")
            return False
    except Exception as e:
        print(f"[Heartbeat] ❌ Dispatch error: {e}")
        return False


def check_and_pulse():
    now_epoch = time.time()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load local queue
    try:
        from cloud_generator.github_runner import load_queue
        q = load_queue()
    except Exception:
        q = []

    pending = [x for x in q if x.get("status") == "PENDING"]
    if not pending:
        print(f"[{now_str}] ℹ️ Heartbeat: Queue empty (0 pending jobs).")
        return

    # Find earliest job
    pending_sorted = sorted(pending, key=lambda x: x.get("scheduled_epoch", 0))
    first_job = pending_sorted[0]
    ep = first_job.get("scheduled_epoch", 0)
    title = first_job.get("title", "Untitled")
    st = first_job.get("scheduled_time", "N/A")
    diff_sec = ep - now_epoch
    diff_min = diff_sec / 60.0

    print(f"[{now_str}] 🔎 Next: '{title}' at {st} (in {diff_min:.1f}m)")

    # If within early window (5m) or overdue
    if diff_sec <= EARLY_WINDOW_SEC:
        running, run_id, status = is_action_currently_running()
        if running:
            print(f"[{now_str}] ⏳ Post '{title}' is ready/overdue, but GitHub Action #{run_id} is already {status}. Waiting.")
        else:
            print(f"[{now_str}] ⚡ Post '{title}' is ready/overdue ({diff_min:.1f}m)! Triggering GitHub Actions NOW...")
            trigger_workflow_dispatch()


def main():
    print("=" * 65)
    print("  Autonomous AI Video Studio - Precision Heartbeat Daemon")
    print(f"  Target: {REPO} | Early Window: {EARLY_WINDOW_SEC // 60} min")
    print("=" * 65)

    while True:
        try:
            check_and_pulse()
        except Exception as err:
            print(f"[Heartbeat] Error during check: {err}")
        time.sleep(60)


if __name__ == "__main__":
    main()

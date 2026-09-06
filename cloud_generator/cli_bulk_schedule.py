"""
CLI Bulk Poetry Scheduler with USA Timings & Multi-Page Niches
--------------------------------------------------------------
Usage:
    python cloud_generator/cli_bulk_schedule.py --file scripts.txt --start "2026-09-08 08:30" --timezone "America/New_York"
    python cloud_generator/cli_bulk_schedule.py --list-niches
    python cloud_generator/cli_bulk_schedule.py --list-pages
    python cloud_generator/cli_bulk_schedule.py --list-queue
"""

import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloud_generator.config import load_settings
from cloud_generator.niche_profiles import list_niches, get_niche
from cloud_generator.bulk_scheduler import parse_bulk_scripts, enqueue_bulk_jobs, load_queue

def main():
    parser = argparse.ArgumentParser(description="Autonomous Poetry Bulk Scheduler & Niche Publisher")
    parser.add_argument("--file", type=str, help="Path to text file containing poems/scripts")
    parser.add_argument("--text", type=str, help="Raw poems string")
    parser.add_argument("--start", type=str, default="", help="Exact scheduling start time (e.g. '2026-09-08 08:30')")
    parser.add_argument("--timezone", type=str, default="America/New_York", help="USA timezone (e.g. America/New_York, America/Chicago, America/Los_Angeles)")
    parser.add_argument("--interval", type=int, default=120, help="Interval in minutes if not using daily slots")
    parser.add_argument("--niche", type=str, default="", help="Specific niche ID (or leave empty for auto-detection)")
    parser.add_argument("--page", type=str, default="", help="Specific Facebook Page ID to target")
    parser.add_argument("--distribute", action="store_true", help="Auto-distribute poems evenly across all connected Facebook Pages")
    parser.add_argument("--list-niches", action="store_true", help="List all available poetry niches")
    parser.add_argument("--list-pages", action="store_true", help="List all configured Facebook Pages")
    parser.add_argument("--list-queue", action="store_true", help="View current scheduled queue")

    args = parser.parse_args()

    if args.list_niches:
        print("\n=== AVAILABLE POETRY NICHES ===")
        for n in list_niches():
            print(f"\n* {n['name']} (ID: {n['id']})")
            print(f"  Tagline:  {n['tagline']}")
            print(f"  Medium:   {n['art_style']}")
            print(f"  Voice:    {n['voice_tone']}")
            print(f"  Font:     {n['caption_font']}")
            print(f"  USA Peak: {', '.join(n['daily_slots'])} ({n['timezone']})")
        return

    if args.list_pages:
        cfg = load_settings()
        pages = cfg.get("facebook_pages", [])
        print(f"\n=== CONFIGURED FACEBOOK PAGES ({len(pages)}) ===")
        for p in pages:
            status = p.get("status", "UNKNOWN")
            niche_id = p.get("niche_id", "typewriters_voice_nostalgia")
            tz = p.get("timezone", "America/New_York")
            slots = p.get("usa_time_slots") or p.get("time_slots", ["08:30", "13:00", "20:30"])
            print(f"\n* {p.get('name')} (ID: {p.get('id')})")
            print(f"  Status:   {status} | Enabled: {p.get('enabled', True)}")
            print(f"  Niche:    {niche_id}")
            print(f"  Timezone: {tz}")
            print(f"  Slots:    {', '.join(slots)}")
        return

    if args.list_queue:
        q = load_queue()
        print(f"\n=== SCHEDULED JOBS QUEUE ({len(q)}) ===")
        for j in q:
            sched = j.get("scheduled_time_usa") or j.get("scheduled_time")
            print(f"[{j.get('status')}] {sched} | {j.get('title')} | Niche: {j.get('niche_id')} | Pages: {j.get('target_page_ids')}")
        return

    raw_text = ""
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"Error: File not found at {p}")
            sys.exit(1)
        raw_text = p.read_text(encoding="utf-8")
    elif args.text:
        raw_text = args.text
    else:
        print("Error: Please provide --file <path> or --text <content> or use --list-niches / --list-pages / --list-queue")
        sys.exit(1)

    pages_list = [args.page.strip()] if args.page.strip() else None

    print(f"\nScheduling bulk poems with USA Timezone: {args.timezone}...")
    jobs = parse_bulk_scripts(
        raw_text=raw_text,
        start_time_str=args.start,
        interval_minutes=args.interval,
        default_niche=args.niche if args.niche else None,
        default_page_ids=pages_list,
        timezone_str=args.timezone,
        auto_distribute_pages=args.distribute
    )

    if not jobs:
        print("No valid poems could be parsed from input.")
        return

    enqueued = enqueue_bulk_jobs(jobs)
    print(f"\nSuccessfully queued {len(enqueued)} poems:")
    for j in enqueued:
        print(f"  * [{j['status']}] {j['scheduled_time_usa']} -> '{j['title']}' | Niche: {j['niche_name']} | Pages: {j['target_page_ids']}")

if __name__ == "__main__":
    main()

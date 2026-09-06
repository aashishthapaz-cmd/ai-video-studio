import os
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cloud_generator.pipeline import run_cloud_pipeline

def main():
    parser = argparse.ArgumentParser(description="Zero-Cost Cloud Video Generator Batch Runner & Auto FB Publisher")
    parser.add_argument("--script", type=str, help="Path to text script or poem file")
    parser.add_argument("--title", type=str, default="", help="Video Title")
    parser.add_argument("--text", type=str, default="", help="Raw script text directly from CLI")
    parser.add_argument("--dir", type=str, help="Directory containing multiple .txt script files for batch render")
    parser.add_argument("--publish-fb", action="store_true", help="Auto-publish rendered videos to configured Facebook Pages")
    args = parser.parse_args()

    if args.dir:
        input_dir = Path(args.dir)
        if not input_dir.exists():
            print(f"Directory not found: {input_dir}")
            return
        files = sorted(p for p in input_dir.glob("*.txt") if p.is_file())
        print(f"Found {len(files)} scripts in {input_dir} for batch cloud render.")
        
        for i, file_path in enumerate(files, 1):
            title = file_path.stem.replace("_", " ").title()
            text = file_path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            print(f"\n==========================================")
            print(f"[{i}/{len(files)}] Processing: {title}")
            print(f"==========================================")
            try:
                res = run_cloud_pipeline(title, text, auto_publish_fb=args.publish_fb)
                print(f"SUCCESS: Rendered {title} -> {res['output_file']}")
                if args.publish_fb and res.get("facebook_published"):
                    print("Facebook Status:", res.get("facebook_published"))
            except Exception as e:
                print(f"FAILED {title}: {e}")

    elif args.script:
        file_path = Path(args.script)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return
        title = args.title or file_path.stem.replace("_", " ").title()
        text = file_path.read_text(encoding="utf-8").strip()
        res = run_cloud_pipeline(title, text, auto_publish_fb=args.publish_fb)
        print(f"\nSUCCESS: Output saved to {res['output_file']}")
        if args.publish_fb and res.get("facebook_published"):
            print("Facebook Status:", res.get("facebook_published"))
        
    elif args.text:
        title = args.title or "Cloud Poem"
        res = run_cloud_pipeline(title, args.text, auto_publish_fb=args.publish_fb)
        print(f"\nSUCCESS: Output saved to {res['output_file']}")
        if args.publish_fb and res.get("facebook_published"):
            print("Facebook Status:", res.get("facebook_published"))
        
    else:
        print("Please provide --script, --text, or --dir. Run with --help for details.")

if __name__ == "__main__":
    main()

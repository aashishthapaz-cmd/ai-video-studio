"""Import a local Facebook Pages JSON file into the ignored local settings file."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cloud_generator"))

from config import load_settings, save_settings


def normalize_pages(raw) -> list[dict]:
    pages = raw if isinstance(raw, list) else raw.get("facebook_pages", []) if isinstance(raw, dict) else []
    if not isinstance(pages, list):
        raise ValueError("Expected a JSON list of Facebook pages or an object with a facebook_pages list.")

    normalized = []
    for item in pages:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or item.get("id") or "").strip()
        token = str(item.get("access_token") or item.get("token") or "").strip()
        if not page_id or not token:
            continue
        normalized.append({
            **item,
            "id": page_id,
            "page_id": page_id,
            "access_token": token,
            "enabled": bool(item.get("enabled", True)),
            "as_reel": bool(item.get("as_reel", True)),
        })
    if not normalized:
        raise ValueError("No Facebook pages with both a Page ID and Page Access Token were found.")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Import local Facebook Page credentials.")
    parser.add_argument("source", type=Path, help="Path to the supplied facebook_pages.json file")
    args = parser.parse_args()
    raw = json.loads(args.source.read_text(encoding="utf-8-sig"))
    pages = normalize_pages(raw)
    config = load_settings()
    config["facebook_pages"] = pages
    config["auto_publish_facebook"] = True
    save_settings(config)
    print(f"Imported {len(pages)} Facebook page configuration(s) into local-only settings.")


if __name__ == "__main__":
    main()

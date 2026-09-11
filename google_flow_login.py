"""
Interactive Google Account Login Helper for Google Flow & ImageFX
Opens a real Chrome window for you to log in to your Google Account once.
Saves the session state to 'cloud_generator/google_session_state.json' and
prints the GitHub Secret value so GitHub Actions can generate images autonomously.
"""

import os
import sys
import json
import base64
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_FILE = PROJECT_ROOT / "cloud_generator" / "google_session_state.json"
USER_DATA_DIR = PROJECT_ROOT / "cloud_generator" / "google_profile"

def main():
    print("=" * 68)
    print("  🔐 GOOGLE ACCOUNT LOGIN FOR GOOGLE FLOW (IMAGEFX / NANO BANANA)")
    print("=" * 68)
    print("  1. A real Chrome window will open.")
    print("  2. Please log in to your Google Account.")
    print("  3. Navigate to Google Flow: https://labs.google/fx/tools/flow")
    print("  4. Once logged in, return to this terminal and press ENTER.")
    print("=" * 68)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n❌ Error: Playwright is not installed.")
        print("Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("\n🌐 Launching Chrome window...")
        # Use persistent context so cookies and Google login are saved
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",  # Uses real Chrome if installed, else chromium
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ],
            viewport={"width": 1280, "height": 850}
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://labs.google/fx/tools/flow")

        input("\n👉 Press ENTER in this terminal once you have logged in to your Google Account... ")

        # Extract and save storage state (cookies + localStorage)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))

        print(f"\n✅ Successfully saved Google session to:")
        print(f"   {SESSION_FILE}")

        # Create base64 export for GitHub Actions Secrets
        state_json = SESSION_FILE.read_text(encoding="utf-8")
        b64_session = base64.b64encode(state_json.encode("utf-8")).decode("utf-8")

        print("\n" + "=" * 68)
        print("  🚀 GITHUB ACTIONS INTEGRATION (FOR GITHUB VIDEO STUDIO)")
        print("=" * 68)
        print("  To enable Google Flow inside your GitHub Actions pipeline:")
        print("  1. Go to your GitHub repo Settings -> Secrets and variables -> Actions")
        print("  2. Click 'New repository secret'")
        print("  3. Name: GOOGLE_FLOW_SESSION")
        print("  4. Value (copy the string below):")
        print("-" * 68)
        print(b64_session)
        print("-" * 68)
        print("  Once added, GitHub Actions will generate poem images directly")
        print("  from Google Flow using your logged-in Google Account!")
        print("=" * 68)

        context.close()

if __name__ == "__main__":
    main()

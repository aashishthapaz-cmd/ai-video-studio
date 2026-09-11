"""
Google Flow (labs.google/fx/tools/flow) & ImageFX Browser-like Image Engine
Automates Google Flow using Playwright with an authenticated Google Account session.
Produces 1080x1920 portrait images using Google's official Nano Banana / Imagen models.
"""

import os
import io
import time
import json
import base64
import logging
import urllib.request
from pathlib import Path
from PIL import Image

logger = logging.getLogger("GoogleFlowEngine")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = Path(__file__).resolve().parent.parent / "google_session_state.json"
USER_DATA_DIR = Path(__file__).resolve().parent.parent / "google_profile"


def _crop_fill(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale and center-crop to fill target_w×target_h with zero letterbox bars."""
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _ensure_session_restored():
    """Restores session from GOOGLE_FLOW_SESSION env var if present (e.g. in GitHub Actions)."""
    env_session = os.environ.get("GOOGLE_FLOW_SESSION", "").strip()
    if env_session:
        try:
            if env_session.startswith("{"):
                session_data = json.loads(env_session)
            else:
                session_data = json.loads(base64.b64decode(env_session).decode("utf-8"))
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
            logger.info("Restored Google Flow session from GOOGLE_FLOW_SESSION secret.")
        except Exception as e:
            logger.warning(f"Failed to restore GOOGLE_FLOW_SESSION env var: {e}")


def is_google_flow_configured() -> bool:
    """Checks if a valid Google session exists locally or via environment variables."""
    _ensure_session_restored()
    return SESSION_FILE.exists() or os.environ.get("GOOGLE_FLOW_SESSION", "").strip() != "" or USER_DATA_DIR.exists()


def generate_google_flow_image(
    prompt: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    timeout_sec: int = 90,
    headless: bool = True,
) -> str:
    """
    Generates an image via Google Flow / ImageFX using Playwright browser automation.
    Requires an authenticated Google session (created via `python google_flow_login.py`).
    """
    _ensure_session_restored()

    if not is_google_flow_configured():
        raise ValueError(
            "Google Flow is not authenticated. Run 'python google_flow_login.py' locally "
            "to log in to your Google Account, or set the GOOGLE_FLOW_SESSION secret in GitHub."
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright is required. Run: pip install playwright && playwright install chromium")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Google Flow] Launching browser to generate image: '{prompt[:50]}...'")

    with sync_playwright() as p:
        # Browser launch args with anti-bot evasion
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--window-size=1280,800",
        ]

        storage_state = str(SESSION_FILE) if SESSION_FILE.exists() else None

        browser = p.chromium.launch(
            headless=headless,
            args=args,
        )

        context = browser.new_context(
            storage_state=storage_state,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        page = context.new_page()

        # Remove navigator.webdriver detection
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        flow_urls = [
            "https://labs.google/fx/tools/flow",
            "https://aitestkitchen.withgoogle.com/tools/image-fx"
        ]

        target_image_bytes = None
        last_error = None

        for target_url in flow_urls:
            try:
                logger.info(f"[Google Flow] Navigating to: {target_url}")
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)

                # Check if redirected to Google sign-in
                if "accounts.google.com" in page.url:
                    logger.warning("[Google Flow] Redirected to Google sign-in. Session expired or invalid.")
                    continue

                # Locate the prompt input box
                # Google Flow & ImageFX use role='textbox' or textarea
                prompt_input = None
                for selector in [
                    "textarea",
                    "[contenteditable='true']",
                    "input[type='text']",
                    "role=textbox"
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=3000):
                            prompt_input = el
                            break
                    except Exception:
                        pass

                if not prompt_input:
                    logger.warning(f"[Google Flow] Could not locate prompt box on {target_url}")
                    continue

                # Type prompt into input
                logger.info(f"[Google Flow] Entering prompt: '{prompt[:40]}...'")
                prompt_input.click()
                prompt_input.fill(prompt)
                page.wait_for_timeout(1000)

                # Look for Create / Generate button or press Enter
                clicked = False
                for btn_text in ["Create", "Generate", "Draw", "Go"]:
                    try:
                        btn = page.get_by_role("button", name=btn_text, exact=False).first
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            clicked = True
                            logger.info(f"[Google Flow] Clicked button: {btn_text}")
                            break
                    except Exception:
                        pass

                if not clicked:
                    # Try pressing Enter
                    prompt_input.press("Enter")
                    logger.info("[Google Flow] Pressed Enter to submit prompt")

                # Wait for generated image to appear
                logger.info("[Google Flow] Waiting for generated image...")
                img_locator = page.locator(
                    "img[src*='googleusercontent.com'], img[src*='blob:'], img[src*='aisandbox']"
                ).first

                img_locator.wait_for(state="visible", timeout=timeout_sec * 1000)
                img_src = img_locator.get_attribute("src")

                if img_src:
                    logger.info(f"[Google Flow] Found generated image: {img_src[:60]}...")
                    if img_src.startswith("http"):
                        req = urllib.request.Request(img_src, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        })
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            target_image_bytes = resp.read()
                    elif img_src.startswith("data:image/"):
                        b64 = img_src.split(",", 1)[1]
                        target_image_bytes = base64.b64decode(b64)
                    else:
                        # Take screenshot of the image element directly
                        target_image_bytes = img_locator.screenshot()

                    if target_image_bytes:
                        break

            except Exception as e:
                last_error = e
                logger.warning(f"[Google Flow] Error on {target_url}: {e}")

        browser.close()

        if target_image_bytes:
            img = Image.open(io.BytesIO(target_image_bytes))
            img = _crop_fill(img, width, height)
            img.save(output_path, "PNG", optimize=False)
            logger.info(f"[Google Flow] Image successfully saved to: {output_path}")
            return str(output_path)

        raise RuntimeError(f"Google Flow failed to generate image. Last error: {last_error}")

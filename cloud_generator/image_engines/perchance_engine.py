"""
Perchance AI Image Generation Engine.
Automates Perchance's free, unlimited AI image generator via direct DrissionPage automation.
Requires no API token or account sign-up.
Outputs borderless edge-to-edge 1080x1920 vertical portraits.
Includes:
- Dynamic Chrome/Chromium auto-discovery (Playwright cache, Linux system bins, Windows registry).
- Virtual Display (xvfb) headful execution to defeat bot detection and Cloudflare Turnstile blocks.
- Direct DOM control of the generator iframe and nested result iframes for instant extraction.
- Automatic image scaling and cropping to fill 1080x1920 without letterboxing.
- Circuit breaker pattern to immediately fail over without blocking pipeline.
"""

import os
import io
import re
import json
import sys
import time
import base64
import shutil
import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger("PerchanceEngine")

_PAGE = None
_PERCHANCE_DISABLED = False
_PERCHANCE_DISABLE_REASON = ""
_FAIL_COUNT = 0
MAX_CONSECUTIVE_FAILS = 4


def find_chromium_path() -> str | None:
    """
    Scans the system for a usable Chrome or Chromium executable.
    Supports system PATH, standard Linux packages, and Playwright cached binaries.
    """
    # 1. Check DrissionPage internal locator
    try:
        import DrissionPage._functions.browser as dp_b
        p = dp_b.get_chrome_path(None)
        if p and Path(p).exists():
            return str(Path(p).resolve())
    except Exception:
        pass

    # 2. Check standard system PATH binaries
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"]:
        p = shutil.which(name)
        if p and Path(p).is_file():
            return str(Path(p).resolve())

    # 3. Check Linux standard installations
    linux_candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/opt/google/chrome/google-chrome",
    ]
    for b in linux_candidates:
        if Path(b).is_file():
            return b

    # 4. Check Playwright cached browser binaries (standard in GitHub Actions)
    pw_cache = Path.home() / ".cache" / "ms-playwright"
    if pw_cache.exists():
        for ch in pw_cache.glob("chromium-*/**/chrome"):
            if ch.is_file() and os.access(str(ch), os.X_OK):
                return str(ch)
        for ch in pw_cache.glob("chromium_headless_shell-*/**/headless_shell"):
            if ch.is_file() and os.access(str(ch), os.X_OK):
                return str(ch)

    return None


def is_perchance_available() -> bool:
    """Returns True if Perchance is enabled and a browser is available."""
    global _PERCHANCE_DISABLED, _FAIL_COUNT
    if _PERCHANCE_DISABLED and _FAIL_COUNT >= MAX_CONSECUTIVE_FAILS:
        return False
    if sys.platform != "win32" and not find_chromium_path():
        return False
    return True


def enable_perchance():
    """Resets circuit breaker and re-enables Perchance."""
    global _PERCHANCE_DISABLED, _PERCHANCE_DISABLE_REASON, _FAIL_COUNT
    _PERCHANCE_DISABLED = False
    _PERCHANCE_DISABLE_REASON = ""
    _FAIL_COUNT = 0
    logger.info("[Perchance] Engine re-enabled and self-healed.")


def disable_perchance(reason: str = ""):
    """Temporarily disables Perchance after repeated consecutive failures."""
    global _PERCHANCE_DISABLED, _PERCHANCE_DISABLE_REASON
    _PERCHANCE_DISABLED = True
    _PERCHANCE_DISABLE_REASON = reason
    logger.warning(f"[Perchance] Engine paused. Reason: {reason}")
    _close_client()


def _get_browser_page():
    """Lazily initializes and reuses a ChromiumPage browser instance."""
    global _PAGE
    if _PAGE is not None:
        try:
            _ = _PAGE.tabs_count
            return _PAGE
        except Exception:
            _close_client()

    from DrissionPage import ChromiumPage, ChromiumOptions

    options = ChromiumOptions()
    detected_chrome = find_chromium_path()
    if detected_chrome:
        options.set_browser_path(detected_chrome)
        logger.info(f"[Perchance] Using browser binary: {detected_chrome}")

    has_display = bool(os.environ.get("DISPLAY"))
    # In Linux CI with xvfb-run, DISPLAY is set. On Windows desktop, platform is win32.
    # Running headful on xvfb or Windows desktop bypasses Cloudflare bot flags completely!
    if has_display or sys.platform == "win32":
        options.headless(False)
    else:
        options.headless(True)
        options.set_argument("--headless=new")

    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--no-sandbox")
    options.set_argument("--disable-dev-shm-usage")
    options.set_argument("--mute-audio")
    options.set_argument("--window-size=1280,720")
    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        if sys.platform != "win32"
        else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    options.set_argument(f"--user-agent={ua}")

    _PAGE = ChromiumPage(options)
    logger.info("[Perchance] Initialized persistent ChromiumPage instance.")
    return _PAGE


def _close_client():
    """Safely closes the active browser page instance."""
    global _PAGE
    if _PAGE is not None:
        try:
            _PAGE.quit()
        except Exception:
            pass
        _PAGE = None


def auto_heal_perchance_client() -> bool:
    """Restarts browser session and clears state to recover from timeouts or dead processes."""
    global _PAGE
    logger.info("[Perchance] Auto-healing: resetting Chromium browser session...")
    _close_client()
    time.sleep(1.0)
    try:
        _PAGE = _get_browser_page()
        logger.info("[Perchance] Auto-heal succeeded: fresh browser session ready.")
        return True
    except Exception as e:
        logger.warning(f"[Perchance] Auto-heal browser reset warning: {e}")
        return False


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


def generate_perchance_image(
    prompt: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    style: str = "Painted Anime",
    time_for_image: int = 45,
) -> str:
    """
    Generates an artistic anime portrait image via Perchance AI Text-to-Image Generator.
    Uses direct DOM control of generator iframe and nested result iframes for instant extraction.
    Returns the absolute path of the generated 1080x1920 image file.
    """
    global _FAIL_COUNT

    if not is_perchance_available():
        enable_perchance()
        if not is_perchance_available():
            raise RuntimeError(f"Perchance is unavailable: {_PERCHANCE_DISABLE_REASON or 'Engine offline'}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean prompt: strip border negatives since positive cues work best in Perchance
    clean_prompt = prompt
    for m in ["no white border", "no borders", "no frame", "edge-to-edge full bleed", "no watermark"]:
        if m.lower() in clean_prompt.lower():
            idx = clean_prompt.lower().find(m.lower())
            clean_prompt = clean_prompt[:idx].strip().rstrip(",. ")
    clean_prompt = " ".join(clean_prompt.split()).strip()
    if len(clean_prompt) > 320:
        clean_prompt = clean_prompt[:320].rsplit(" ", 1)[0]

    # Scenic artwork & poem-related subject prompt tuning
    # Preserve environmental landscape prompts while ensuring Studio Ghibli/Shinkai aesthetic
    if "ghibli" not in clean_prompt.lower() and "anime" not in clean_prompt.lower() and "scenic" not in clean_prompt.lower():
        clean_prompt = (
            f"Breathtaking wide scenic landscape illustration, Studio Ghibli background art aesthetic, "
            f"{clean_prompt}, Makoto Shinkai atmospheric lighting, pure scenery, wide angle vista, "
            f"no close-up face, no giant character portrait, no big anime character"
        )

    logger.info(f"[Perchance] Generating scenic visual (style={style}) for prompt: '{clean_prompt[:75]}...'")

    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        if sys.platform != "win32"
        else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    last_error = None
    for attempt in range(2):
        tab = None
        try:
            page = _get_browser_page()
            tab = page.new_tab("https://perchance.org/ai-text-to-image-generator")

            # Wait up to 10 seconds for generator iframe to load
            gen_frame = None
            t_start = time.time()
            while time.time() - t_start < 10:
                gen_frame = tab.get_frame("@src:ai-text-to-image-generator")
                if gen_frame:
                    break
                time.sleep(0.5)

            if not gen_frame:
                raise RuntimeError("Could not locate generator frame '@src:ai-text-to-image-generator'")

            # Configure Art Style (Painted Anime) & Shape (Portrait 512x768)
            style_val = "ref:optionKeyName:Painted Anime" if "anime" in str(style).lower() else "ref:optionKeyName:Cinematic"
            gen_frame.run_js(f"""
                let selects = document.querySelectorAll('select');
                if (selects.length >= 2) {{
                    selects[0].value = '{style_val}';
                    selects[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                    selects[1].value = '512x768';
                    selects[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)

            # Target prompt textarea (the prompt input is the last textarea on the page)
            tas = gen_frame.eles("tag:textarea")
            if not tas:
                raise RuntimeError("Prompt textarea not found in generator frame")
            prompt_ta = tas[-1]
            prompt_ta.input(clean_prompt, clear=True)

            # Click Generate Button
            btn = gen_frame.ele("#generateButtonEl") or gen_frame.ele("text=✨ generate")
            if not btn:
                raise RuntimeError("Generate button not found in generator frame")
            btn.click()

            # Poll for generated image in nested iframes
            t_poll = time.time()
            result_img_bytes = None
            while time.time() - t_poll < time_for_image:
                time.sleep(1.0)
                nested_frames = gen_frame.eles("tag:iframe")
                for nf in nested_frames:
                    try:
                        n_fr = gen_frame.get_frame(nf)
                        img = n_fr.ele("#resultImgEl")
                        if img:
                            src = img.attr("src") or ""
                            if src.startswith("data:image/"):
                                b64 = src.split(",", 1)[1]
                                raw = base64.b64decode(b64)
                                if len(raw) > 5000:
                                    result_img_bytes = raw
                                    break
                            elif src.startswith("http"):
                                import urllib.request
                                req = urllib.request.Request(src, headers={"User-Agent": ua})
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    raw = resp.read()
                                    if len(raw) > 5000:
                                        result_img_bytes = raw
                                        break
                    except Exception:
                        pass
                if result_img_bytes:
                    break

            try:
                tab.close()
                tab = None
            except Exception:
                pass

            if result_img_bytes and len(result_img_bytes) > 5000:
                img = Image.open(io.BytesIO(result_img_bytes))
                cropped = _crop_fill(img, width, height)
                cropped.save(str(output_path), "PNG")
                _FAIL_COUNT = 0
                logger.info(f"[Perchance] Successfully generated image: {output_path} ({width}x{height})")
                return str(output_path.resolve())

            raise RuntimeError(f"Perchance generation timed out after {time_for_image}s (no image in embed frame)")

        except Exception as err:
            last_error = err
            logger.warning(f"[Perchance] Attempt {attempt+1} failed: {err}")
            if tab:
                try:
                    tab.close()
                except Exception:
                    pass
            auto_heal_perchance_client()

    _FAIL_COUNT += 1
    if _FAIL_COUNT >= MAX_CONSECUTIVE_FAILS:
        disable_perchance(f"Repeated failures ({_FAIL_COUNT}): {last_error}")
    raise RuntimeError(f"Perchance image generation failed: {last_error}")

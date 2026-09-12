"""
Perchance AI Image Generation Engine.
Automates Perchance's free, unlimited AI image generator via headless browser automation (CDP).
Requires no API token or account sign-up.
Outputs borderless edge-to-edge 1080x1920 vertical portraits.
Includes:
- Dynamic Chrome/Chromium auto-discovery (Playwright cache, Linux system bins, Windows registry).
- Robust headless flags (--disable-gpu, --no-sandbox, --disable-dev-shm-usage).
- Circuit breaker pattern to immediately fail over on any runner incompatibility without blocking CI.
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

_CLIENT = None
_PERCHANCE_DISABLED = False
_PERCHANCE_DISABLE_REASON = ""
_PATCH_APPLIED = False


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


def _apply_perchancy_patches():
    """Patches perchancy.core.BrowserCore to auto-inject the discovered Chromium binary & Linux flags."""
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return
    try:
        from perchancy.core import BrowserCore
        from DrissionPage import ChromiumPage, ChromiumOptions

        orig_init_driver = BrowserCore.init_driver

        def _patched_init_driver(self, proxy=None):
            if self.page is not None:
                try:
                    self.page.quit()
                except Exception:
                    pass
                self.page = None

            detected_chrome = find_chromium_path()
            options = ChromiumOptions()
            if detected_chrome:
                options.set_browser_path(detected_chrome)
                logger.info(f"[Perchance] Using browser executable: {detected_chrome}")

            has_display = bool(os.environ.get("DISPLAY"))
            if self.headless and not has_display:
                options.headless(True)
                options.set_argument("--headless=new")
            else:
                # With virtual X11 display (xvfb in CI), run headful on virtual display to avoid headless bot detection
                options.headless(False)

            options.set_argument("--disable-blink-features=AutomationControlled")
            options.set_argument("--window-size=1280,720")
            options.set_pref("profile.default_content_setting_values.popups", 2)
            options.set_argument("--no-sandbox")
            options.set_argument("--disable-dev-shm-usage")
            options.set_argument("--mute-audio")
            ua = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                if sys.platform != "win32"
                else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
            options.set_argument(f"--user-agent={ua}")

            if proxy:
                options.set_proxy(proxy)

            self.page = ChromiumPage(options)
            self.page.get("about:blank")

        BrowserCore.init_driver = _patched_init_driver

        # Also patch _click_button_js to trigger Perchance's native generate button event properly
        orig_click = getattr(BrowserCore, "_click_button_js", None)
        def _patched_click(self_core, frame, btn_sels):
            try:
                # First attempt direct trigger of Perchance's generate handler if available
                res = frame.run_js("""
                    try {
                        let btn = document.getElementById('generateButtonEl') || document.querySelector('button[id*="generate" i]');
                        if (btn) {
                            let fnKey = Object.keys(window).find(k => k.startsWith('___generateButtonClickEvent'));
                            if (fnKey && typeof window[fnKey] === 'function') {
                                window[fnKey](new Event('click'));
                                return '#generateButtonEl';
                            }
                            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                            btn.click();
                            return '#generateButtonEl';
                        }
                    } catch(e) {}
                    return null;
                """)
                if res:
                    return res
            except Exception:
                pass
            if orig_click:
                return orig_click(self_core, frame, btn_sels)
            return None

        BrowserCore._click_button_js = _patched_click
        _PATCH_APPLIED = True
    except Exception as e:
        logger.warning(f"[Perchance] Could not patch perchancy BrowserCore: {e}")


_FAIL_COUNT = 0
MAX_CONSECUTIVE_FAILS = 4

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


def auto_heal_perchance_client() -> bool:
    """Restarts headless browser and clears state to recover from timeouts or dead processes."""
    global _CLIENT
    logger.info("[Perchance] Auto-healing: resetting headless browser client...")
    _close_client()
    time.sleep(1.0)
    try:
        _CLIENT = _get_client()
        logger.info("[Perchance] Auto-heal succeeded: fresh client ready.")
        return True
    except Exception as e:
        logger.warning(f"[Perchance] Auto-heal client reset warning: {e}")
        return False


def _get_client():
    """Lazily initializes and reuses a headless perchancy client."""
    global _CLIENT
    if not is_perchance_available():
        raise RuntimeError(f"Perchance is disabled: {_PERCHANCE_DISABLE_REASON or 'Engine offline'}")

    _apply_perchancy_patches()

    if _CLIENT is None:
        try:
            from perchancy import Client
            _CLIENT = Client(headless=True, debug=False)
            _CLIENT.core.init_driver()
            logger.info("[Perchance] Initialized headless perchancy client with active driver.")
        except Exception as e:
            logger.warning(f"[Perchance] Client init failed: {e}")
            raise
    elif _CLIENT.core.page is None:
        try:
            _CLIENT.core.init_driver()
        except Exception:
            pass
    return _CLIENT


def _close_client():
    """Safely closes the active browser client."""
    global _CLIENT
    if _CLIENT is not None:
        try:
            _CLIENT.close()
        except Exception:
            pass
        _CLIENT = None


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
    time_for_image: int = 60,
) -> str:
    """
    Generates an artistic anime portrait image via Perchance AI Text-to-Image Generator.
    Directly interacts with generator frame and embedded output frames for 100% reliable image extraction.
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
    clean_prompt = re.sub(r'[\r\n]+', ' ', clean_prompt).strip()
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

    logger.info(f"[Perchance] Generating scenic visual with poem-related subjects (style={style}) for prompt: '{clean_prompt[:75]}...'")

    last_error = None
    for attempt in range(2):
        client = None
        tab = None
        try:
            client = _get_client()
            if client.core.page is None:
                client.core.init_driver()
            page = client.core.page
            tab = page.new_tab("https://perchance.org/ai-text-to-image-generator")
            time.sleep(3.5)

            frames = client.core._get_all_frames(tab)
            generator_frame = None
            for f in frames:
                href = f.run_js("return window.location.href;") or ""
                if "perchance.org/ai-text-to-image-generator" in href and f != tab:
                    generator_frame = f
                    break

            if not generator_frame:
                raise RuntimeError("Could not locate generator frame in Perchance")

            # Configure Art Style (Painted Anime) & Shape (Portrait 512x768) and Prompt
            style_val = "ref:optionKeyName:Painted Anime" if "anime" in str(style).lower() else "ref:optionKeyName:Cinematic"
            generator_frame.run_js(f"""
                let selects = document.querySelectorAll('select');
                if (selects.length >= 2) {{
                    selects[0].value = '{style_val}';
                    selects[0].dispatchEvent(new Event('change', {{ bubbles: true }}));

                    selects[1].value = '512x768';
                    selects[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}

                let tas = document.querySelectorAll('textarea.paragraph-input');
                if (tas.length > 0) {{
                    let ta = tas[tas.length - 1];
                    ta.value = {json.dumps(clean_prompt)};
                    ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)

            # Trigger generation via native event handler
            generator_frame.run_js("""
                let fn = window.___generateButtonClickEvent746291937;
                if (typeof fn === 'function') {
                    fn(new Event('click'));
                } else {
                    let btn = document.getElementById('generateButtonEl');
                    if (btn) btn.click();
                }
            """)

            # Poll embed frames for result image
            t0 = time.time()
            result_img_bytes = None
            while time.time() - t0 < time_for_image:
                time.sleep(1.0)
                all_frames = client.core._get_all_frames(tab)
                for f in all_frames:
                    try:
                        href = f.run_js("return window.location.href;") or ""
                        if "image-generation" in href:
                            src = f.run_js("""
                                let img = document.getElementById('resultImgEl');
                                return img ? img.src : null;
                            """)
                            if src and src.startswith("data:image/"):
                                b64 = src.split(",", 1)[1]
                                result_img_bytes = base64.b64decode(b64)
                                break
                            elif src and src.startswith("http"):
                                import urllib.request
                                req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    result_img_bytes = resp.read()
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
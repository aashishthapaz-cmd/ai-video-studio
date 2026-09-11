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
        for ch in pw_cache.glob("chromium-*/chrome-linux/chrome"):
            if ch.is_file() and os.access(str(ch), os.X_OK):
                return str(ch)
        for ch in pw_cache.glob("chromium_headless_shell-*/chrome-linux/headless_shell"):
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

            if self.headless:
                options.headless(True)
                options.set_argument("--headless=new")
                # On Linux without GPU (CI), --disable-gpu prevents swiftshader/angle crashes
                options.set_argument("--disable-gpu")
                options.set_argument("--use-gl=angle")
                options.set_argument("--use-angle=swiftshader")
                options.set_argument("--enable-webgl")
                options.set_argument(
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )

            options.set_argument("--disable-blink-features=AutomationControlled")
            options.set_argument("--window-size=1920,1080")
            options.set_pref("profile.default_content_setting_values.popups", 2)
            options.set_argument("--no-sandbox")
            options.set_argument("--disable-dev-shm-usage")
            options.set_argument("--disable-software-rasterizer")
            options.set_argument("--mute-audio")

            if proxy:
                options.set_proxy(proxy)

            self.page = ChromiumPage(options)
            self.page.get("about:blank")

        BrowserCore.init_driver = _patched_init_driver
        _PATCH_APPLIED = True
    except Exception as e:
        logger.warning(f"[Perchance] Could not patch perchancy BrowserCore: {e}")


def is_perchance_available() -> bool:
    """Returns True if Perchance has not tripped the circuit breaker and a browser is available."""
    global _PERCHANCE_DISABLED
    if _PERCHANCE_DISABLED:
        return False
    # Quick probe: if no chromium path found and not Windows, it won't work
    if sys.platform != "win32" and not find_chromium_path():
        return False
    return True


def disable_perchance(reason: str = ""):
    """Trips the circuit breaker for Perchance in this process to prevent repeated timeouts."""
    global _PERCHANCE_DISABLED, _PERCHANCE_DISABLE_REASON
    _PERCHANCE_DISABLED = True
    _PERCHANCE_DISABLE_REASON = reason
    logger.warning(f"[Perchance] Engine disabled for this run. Reason: {reason}")
    _close_client()


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
            logger.info("[Perchance] Initialized headless perchancy client.")
        except Exception as e:
            disable_perchance(f"Client init failed: {e}")
            raise
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
    style: str = "Anime",
    time_for_image: int = 25,
) -> str:
    """
    Generates an image via Perchance AI Text-to-Image Generator.
    Defaults to 'Anime' art style. Returns the absolute path of the generated 1080x1920 image file.
    Trips circuit breaker on failure to ensure zero delay on subsequent scenes.
    """
    if not is_perchance_available():
        raise RuntimeError(f"Perchance is unavailable: {_PERCHANCE_DISABLE_REASON or 'Engine offline'}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean prompt: strip border negatives since Perchance interprets positive cues best
    clean_prompt = prompt.split("no white border")[0].split("no borders")[0].strip().rstrip(",. ")
    if len(clean_prompt) > 350:
        clean_prompt = clean_prompt[:350].rsplit(" ", 1)[0]

    # Ensure Anime aesthetic cues
    if "anime" not in clean_prompt.lower():
        clean_prompt = f"anime art of {clean_prompt}, world-class masterpiece, breathtaking painterly anime style, beautiful lighting, high quality"

    logger.info(f"[Perchance] Generating image (style={style}) for prompt: '{clean_prompt[:70]}...'")

    try:
        client = _get_client()
        res = client.images.generate(
            model="ai-text-to-image-generator",
            prompt=clean_prompt,
            extra_params={"style": style} if style else None,
            time_for_image=time_for_image,
        )

        if isinstance(res, dict) and res.get("data"):
            data_item = res["data"][0]
            raw_url = data_item.get("url", "")

            img_bytes = None
            if raw_url.startswith("data:image/"):
                b64_data = raw_url.split(",", 1)[1]
                img_bytes = base64.b64decode(b64_data)
            elif raw_url.startswith("http"):
                import urllib.request
                req = urllib.request.Request(raw_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    img_bytes = r.read()
            elif len(raw_url) > 1000:
                img_bytes = base64.b64decode(raw_url)

            if img_bytes:
                img = Image.open(io.BytesIO(img_bytes))
                if img.size != (width, height):
                    img = _crop_fill(img, width, height)
                img.save(output_path, "PNG", optimize=False)
                logger.info(f"[Perchance] Successfully generated image: {output_path} ({width}x{height})")
                return str(output_path)

        error_msg = res.get("error") if isinstance(res, dict) else str(res)
        raise RuntimeError(f"Perchance returned no image data: {error_msg}")

    except Exception as e:
        logger.warning(f"[Perchance] Generation failed: {e}")
        # Trip the circuit breaker so subsequent scenes instantly failover to secondary engine
        disable_perchance(f"Perchance generation failed: {e}")
        raise RuntimeError(f"Perchance image generation failed: {e}")
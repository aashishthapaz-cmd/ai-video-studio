"""
Perchance AI Image Generation Engine.
Automates Perchance's free, unlimited AI image generator via headless browser automation (CDP).
Requires no API token or account sign-up.
Outputs borderless edge-to-edge 1080x1920 vertical portraits.
"""

import os
import io
import time
import base64
import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

_CLIENT = None


def _get_client():
    """Lazily initializes and reuses a headless perchancy client."""
    global _CLIENT
    if _CLIENT is None:
        try:
            from perchancy import Client
            _CLIENT = Client(headless=True, debug=False)
            logger.info("[Perchance] Initialized headless perchancy client.")
        except Exception as e:
            logger.error(f"[Perchance] Failed to initialize perchancy client: {e}")
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
    """
    Scale the image so it fills target_w×target_h with NO letterbox or pillarbox bars,
    then center-crop to exact size. Guarantees edge-to-edge coverage.
    """
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
    time_for_image: int = 50,
) -> str:
    """
    Generates an image via Perchance AI Text-to-Image Generator.
    Returns the absolute path of the generated 1080x1920 image file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean prompt: strip border negatives since Perchance interprets positive cues best
    clean_prompt = prompt.split("no white border")[0].split("no borders")[0].strip().rstrip(",. ")
    if len(clean_prompt) > 400:
        clean_prompt = clean_prompt[:400].rsplit(" ", 1)[0]

    # Ensure poetry style cues
    if "poetry" not in clean_prompt.lower() and "cinematic" not in clean_prompt.lower():
        clean_prompt = f"{clean_prompt}, cinematic atmosphere, poetry aesthetic, masterpiece"

    logger.info(f"[Perchance] Generating image for prompt: '{clean_prompt[:80]}...'")

    last_error = None
    for attempt in range(2):
        try:
            client = _get_client()
            res = client.images.generate(
                model="ai-text-to-image-generator",
                prompt=clean_prompt,
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
                    with urllib.request.urlopen(req, timeout=30) as r:
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
            last_error = f"Perchance returned no data: {error_msg}"
            logger.warning(f"[Perchance] Attempt {attempt+1} failed: {last_error}")
            _close_client()
            time.sleep(2)
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[Perchance] Attempt {attempt+1} encountered exception: {e}")
            _close_client()
            time.sleep(2)

    raise RuntimeError(f"Perchance image generation failed: {last_error}")
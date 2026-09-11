"""
Puter.com Nano Banana (Pro, 2, 2 Lite) & Imagen Image Engine
Provides access to Google's Nano Banana models (Gemini 3.1 Flash Image,
Gemini 3 Pro Image, Gemini 3.1 Flash Lite Image, Imagen 4) via Puter.com API.
"""

import io
import json
import time
import base64
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from PIL import Image

logger = logging.getLogger("PuterEngine")

# Models supported by Puter for Nano Banana / Google Image Generation
PUTER_NANO_BANANA_CASCADE = [
    "gemini-3.1-flash-image-preview",      # Nano Banana 2 (Gemini 3.1 Flash) - Pro quality, Flash speed
    "gemini-3-pro-image-preview",          # Nano Banana Pro (Gemini 3 Pro) - sharp typography, deep reasoning
    "google/gemini-3.1-flash-lite-image",  # Nano Banana 2 Lite - fast, batch processing
    "google/gemini-2.5-flash-image",       # Nano Banana (Gemini 2.5 Flash)
    "google/imagen-4.0-fast",              # Imagen 4.0 Fast
    "google/imagen-4.0",                   # Imagen 4.0
]


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
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def _save_image_data(raw_data: bytes, output_path: Path, target_w: int, target_h: int) -> str:
    """Decode bytes, crop-fill to exact dimensions, and save as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(raw_data))
    if img.size != (target_w, target_h):
        img = _crop_fill(img, target_w, target_h)
    img.save(output_path, "PNG", optimize=False)
    return str(output_path)


_PUTER_EXHAUSTED = False


def generate_puter_image(
    prompt: str,
    output_path: Path,
    auth_token: str,
    model: str = "gemini-3.1-flash-image-preview",
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    retries: int = 2,
    timeout: int = 60,
) -> str:
    """
    Generates an image using Puter.com's Nano Banana API.
    Uses 'api.puter.com/drivers/call' with interface 'puter-image-generation' and driver 'ai-image'.
    """
    global _PUTER_EXHAUSTED
    if _PUTER_EXHAUSTED:
        raise RuntimeError("Puter credits previously exhausted (HTTP 402). Skipping Puter to fail fast.")

    if not auth_token:
        raise ValueError("Puter Auth Token is required. Get one free at puter.com/dashboard#account")

    # Cascade order: requested model first, then fallback models
    models_to_try = [model] + [m for m in PUTER_NANO_BANANA_CASCADE if m != model]
    url = "https://api.puter.com/drivers/call"

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "User-Agent": "AutoVideoStudio/1.0",
        "Origin": "https://puter.com",
        "Referer": "https://puter.com/",
    }

    last_error = None
    for cur_model in models_to_try:
        args_payload = {
            "prompt": prompt,
            "model": cur_model,
        }
        if width and height:
            args_payload["width"] = width
            args_payload["height"] = height
        if seed is not None:
            args_payload["seed"] = seed

        payload = {
            "interface": "puter-image-generation",
            "driver": "ai-image",
            "test_mode": False,
            "method": "generate",
            "args": args_payload,
            "auth_token": auth_token,
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    raw = resp.read()

                    if status == 200:
                        # Case 1: Direct binary image response
                        if (
                            "image" in content_type
                            or raw.startswith(b"\x89PNG")
                            or raw.startswith(b"\xff\xd8")
                            or raw.startswith(b"RIFF")
                        ):
                            logger.info(f"[Puter] Successfully generated image with model: {cur_model}")
                            return _save_image_data(raw, output_path, width, height)

                        # Case 2: JSON response with image URL or base64
                        try:
                            parsed = json.loads(raw.decode("utf-8"))
                            # If wrapped in result
                            res = parsed.get("result", parsed)
                            
                            # Subcase 2a: data URI (data:image/png;base64,...)
                            if isinstance(res, str) and res.startswith("data:image/"):
                                b64_str = res.split(",", 1)[1]
                                img_bytes = base64.b64decode(b64_str)
                                return _save_image_data(img_bytes, output_path, width, height)
                            
                            # Subcase 2b: direct base64 image in dict
                            if isinstance(res, dict) and "image" in res:
                                img_val = res["image"]
                                if img_val.startswith("data:image/"):
                                    img_val = img_val.split(",", 1)[1]
                                img_bytes = base64.b64decode(img_val)
                                return _save_image_data(img_bytes, output_path, width, height)

                            # Subcase 2c: URL to image
                            if isinstance(res, str) and res.startswith("http"):
                                img_req = urllib.request.Request(res, headers={"User-Agent": "AutoVideoStudio/1.0"})
                                with urllib.request.urlopen(img_req, timeout=30) as img_resp:
                                    img_bytes = img_resp.read()
                                    return _save_image_data(img_bytes, output_path, width, height)

                            # Subcase 2d: dict with url or src
                            if isinstance(res, dict):
                                img_url = res.get("url") or res.get("src") or res.get("image_url")
                                if img_url:
                                    if img_url.startswith("data:image/"):
                                        img_bytes = base64.b64decode(img_url.split(",", 1)[1])
                                        return _save_image_data(img_bytes, output_path, width, height)
                                    img_req = urllib.request.Request(img_url, headers={"User-Agent": "AutoVideoStudio/1.0"})
                                    with urllib.request.urlopen(img_req, timeout=30) as img_resp:
                                        img_bytes = img_resp.read()
                                        return _save_image_data(img_bytes, output_path, width, height)

                        except Exception as parse_err:
                            logger.warning(f"[Puter] JSON parsing response warning: {parse_err}")

                        # If raw bytes are substantial, try opening with PIL directly
                        if len(raw) > 5000:
                            try:
                                return _save_image_data(raw, output_path, width, height)
                            except Exception:
                                pass

            except urllib.error.HTTPError as http_err:
                last_error = http_err
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass

                logger.warning(f"[Puter] HTTP {http_err.code} for model {cur_model}: {err_body}")

                # 402 Insufficient Funds / Credits exhausted: fail fast immediately across all models and scenes
                if http_err.code == 402:
                    _PUTER_EXHAUSTED = True
                    logger.warning(f"[Puter] Token credits exhausted (HTTP 402). Disabling Puter engine for remaining scenes.")
                    raise RuntimeError(f"Puter credits exhausted (HTTP 402): {err_body}")

                # 401 or auth failure: don't retry same model
                if http_err.code == 401:
                    raise RuntimeError(f"Puter authentication failed: {err_body}")
                # 404/400 model not available on this plan: try next model in cascade
                elif http_err.code in (404, 400, 422):
                    break
                else:
                    if attempt < retries - 1:
                        time.sleep(2.0 * (attempt + 1))
            except Exception as e:
                last_error = e
                logger.warning(f"[Puter] Attempt {attempt+1} error for {cur_model}: {e}")
                if attempt < retries - 1:
                    time.sleep(2.0 * (attempt + 1))

    raise RuntimeError(f"All Puter Nano Banana models failed. Last error: {last_error}")

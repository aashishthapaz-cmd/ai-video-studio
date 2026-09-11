import io
import json
import base64
import logging
import urllib.request
from pathlib import Path
from PIL import Image

logger = logging.getLogger("CloudflareEngine")

# Supported models on Cloudflare Workers AI in priority order
CLOUDFLARE_MODELS_CASCADE = [
    "@cf/black-forest-labs/flux-1-schnell",
    "@cf/stabilityai/stable-diffusion-xl-base-1.0",
    "@cf/bytedance/stable-diffusion-xl-lightning",
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
    """Decode bytes, crop-fill to exact target dimensions (1080x1920), and save as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(raw_data))
    if img.size != (target_w, target_h):
        img = _crop_fill(img, target_w, target_h)
    img.save(output_path, "PNG", optimize=False)
    return str(output_path)


def generate_cloudflare_image(
    prompt: str,
    output_path: Path,
    account_id: str,
    api_token: str,
    model: str = "@cf/black-forest-labs/flux-1-schnell",
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    timeout: int = 60,
) -> str:
    """
    Generates an image via Cloudflare Workers AI (10,000 free Neurons/day).
    Uses model cascade: FLUX.1-schnell -> SDXL Base -> SDXL Lightning.
    NOTE: Cloudflare Workers AI schema rejects 'width', 'height', and 'num_steps'.
    We request standard dimensions and scale/crop to exact target_w×target_h (1080x1920).
    """
    if not account_id or not api_token:
        raise ValueError("Cloudflare Account ID and API Token must be provided in settings.")

    models_to_try = [model] + [m for m in CLOUDFLARE_MODELS_CASCADE if m != model]
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "AutoVideoStudio/1.0",
    }

    # Clean prompt: keep under 500 chars for Workers AI limits
    clean_prompt = prompt.strip()
    if len(clean_prompt) > 800:
        clean_prompt = clean_prompt[:800].rsplit(" ", 1)[0]

    last_error = None
    for cur_model in models_to_try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{cur_model}"

        # CRITICAL: FLUX schema rejects 'seed', 'width', 'height'. SDXL supports 'seed'.
        payload = {"prompt": clean_prompt}
        if "flux" not in cur_model and seed is not None and isinstance(seed, int):
            payload["seed"] = seed

        data = json.dumps(payload).encode("utf-8")

        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    raw_resp = resp.read()

                    # Case 1: Direct binary image response
                    if "image" in content_type or raw_resp.startswith(b"\x89PNG") or raw_resp.startswith(b"\xff\xd8"):
                        logger.info(f"[Cloudflare] Success with model: {cur_model}")
                        return _save_image_data(raw_resp, output_path, width, height)

                    # Case 2: JSON response with base64 result
                    try:
                        parsed = json.loads(raw_resp.decode("utf-8"))
                        if "result" in parsed and "image" in parsed["result"]:
                            img_data = base64.b64decode(parsed["result"]["image"])
                            logger.info(f"[Cloudflare] Success (base64) with model: {cur_model}")
                            return _save_image_data(img_data, output_path, width, height)
                    except Exception:
                        pass

                    if len(raw_resp) > 5000:
                        return _save_image_data(raw_resp, output_path, width, height)

            except urllib.error.HTTPError as http_err:
                last_error = http_err
                err_body = ""
                try:
                    err_body = http_err.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass
                logger.warning(f"[Cloudflare] HTTP {http_err.code} for {cur_model}: {err_body[:200]}")
                # If model not found or invalid on this account, try next model
                if http_err.code in (404, 400, 422):
                    break
            except Exception as e:
                last_error = e
                logger.warning(f"[Cloudflare] Attempt {attempt+1} error for {cur_model}: {e}")

    raise RuntimeError(f"All Cloudflare Workers AI models failed. Last error: {last_error}")

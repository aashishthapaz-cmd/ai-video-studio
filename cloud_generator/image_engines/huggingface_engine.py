import time
import json
import io
import urllib.request
from pathlib import Path
from PIL import Image, ImageOps

# Models tried in order — each is free-tier on HuggingFace Serverless Inference
# FLUX.1-schnell supports native non-square sizes natively
HF_MODELS_CASCADE = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
]

# FLUX.1-schnell supports native portrait sizes. Cap other models at 1024x1024.
NATIVE_PORTRAIT_MODELS = {"black-forest-labs/FLUX.1-schnell"}


def _crop_fill(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """
    Scale the image so it fills target_w×target_h with NO letterbox or pillarbox bars,
    then center-crop to exact size. This guarantees edge-to-edge coverage.
    """
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def _save_image(img: Image.Image, output_path: Path, target_w: int, target_h: int) -> str:
    """Crop-fill to exact target, save as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if img.size != (target_w, target_h):
        img = _crop_fill(img, target_w, target_h)
    img.save(output_path, "PNG", optimize=False)
    return str(output_path)


def _save_image_bytes(raw: bytes, output_path: Path, target_w: int, target_h: int) -> str:
    """Decode raw bytes, crop-fill to exact target, save as PNG."""
    img = Image.open(io.BytesIO(raw))
    return _save_image(img, output_path, target_w, target_h)


def generate_huggingface_image(
    prompt: str,
    output_path: Path,
    hf_token: str,
    model: str = "black-forest-labs/FLUX.1-schnell",
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    retries: int = 6,
) -> str:
    """
    Generates an image via Hugging Face Serverless Inference API.
    - Requests native portrait dimensions when the model supports it (FLUX.1-schnell)
    - Falls back through HF_MODELS_CASCADE if the requested model fails
    - Always outputs at exact (width, height) via crop-fill — NEVER letterboxes or pillarboxes
    """
    if not hf_token:
        raise ValueError("Hugging Face API token required. Get one free at huggingface.co/settings/tokens")

    # Build cascade: requested model first, then the rest
    cascade = [model] + [m for m in HF_MODELS_CASCADE if m != model]

    last_error = None
    for current_model in cascade:
        # For models that support native portrait, use full 768x1024 or 1080x1920 partial;
        # FLUX.1-schnell can handle up to 1024 on each axis — use 768x1024 for portrait ratio
        if current_model in NATIVE_PORTRAIT_MODELS:
            gen_w, gen_h = 768, 1024   # 3:4 portrait — closest free-tier supported ratio to 9:16
        else:
            gen_w, gen_h = 512, 768    # Landscape-capable models: use portrait 2:3 ratio

        # ── 1. Try huggingface_hub InferenceClient (fastest) ──────────────
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(api_key=hf_token, timeout=120)
            gen_kwargs = dict(
                prompt=prompt,
                model=current_model,
                width=gen_w,
                height=gen_h,
            )
            if seed is not None:
                gen_kwargs["seed"] = seed
            img = client.text_to_image(**gen_kwargs)
            if img:
                return _save_image(img, output_path, width, height)
        except Exception as e:
            last_error = e

        # ── 2. Direct HTTP fallback ────────────────────────────────────────
        url = f"https://router.huggingface.co/hf-inference/models/{current_model}"
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
            "User-Agent": "AutoVideoStudio/1.0",
        }
        payload: dict = {
            "inputs": prompt,
            "parameters": {"width": gen_w, "height": gen_h},
        }
        if seed is not None:
            payload["parameters"]["seed"] = seed

        data = json.dumps(payload).encode("utf-8")
        model_failed = False
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read()
                    if resp.status == 200 and len(raw) > 5000:
                        return _save_image_bytes(raw, output_path, width, height)
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    try:
                        wait = min(json.loads(e.read().decode()).get("estimated_time", 12.0), 30.0)
                    except Exception:
                        wait = 12.0
                    time.sleep(wait)
                    continue
                elif e.code in (404, 400):
                    last_error = e
                    model_failed = True
                    break  # this model not available, try next in cascade
                else:
                    if attempt < retries - 1:
                        time.sleep(3.0 * (attempt + 1))
                    else:
                        last_error = e
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    time.sleep(3.0 * (attempt + 1))

        if model_failed:
            continue

    raise RuntimeError(f"All HuggingFace models failed. Last error: {last_error}")

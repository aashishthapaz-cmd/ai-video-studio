import time
import json
import io
import urllib.request
from pathlib import Path
from PIL import Image, ImageOps

# Models tried in order — fastest reliable models first
# FLUX.1-schnell: fast, portrait-capable, free tier
# SDXL: slower but better quality
# SD v1.5: last resort, available on free tier
HF_MODELS_CASCADE = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
]

# FLUX.1-schnell supports native portrait sizes. Use portrait ratio for all.
NATIVE_PORTRAIT_MODELS = {"black-forest-labs/FLUX.1-schnell"}

# Per-model max timeout in seconds — keep tight to avoid burning the 45min GH limit
MODEL_TIMEOUT = {
    "black-forest-labs/FLUX.1-schnell": 45,   # Fast — should respond in <30s
    "stabilityai/stable-diffusion-xl-base-1.0": 60,
    "runwayml/stable-diffusion-v1-5": 45,
}


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


def _save_image(img: Image.Image, output_path: Path, target_w: int, target_h: int) -> str:
    """Crop-fill to exact target size, save as PNG."""
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
    retries: int = 2,   # REDUCED from 6 → 2: fail fast, move to Pollinations quickly
) -> str:
    """
    Generates an image via HuggingFace Serverless Inference API.
    - FAST FAIL design: 2 retries max, then raises so image_router moves to next engine
    - Portrait dimensions: 768x1024 for FLUX, 512x768 for others
    - Always outputs at exact (width, height) via crop-fill — NO letterbox bars
    """
    if not hf_token:
        raise ValueError("HuggingFace token required")

    # Build cascade: requested model first, then the rest
    cascade = [model] + [m for m in HF_MODELS_CASCADE if m != model]

    last_error = None
    for current_model in cascade:
        timeout = MODEL_TIMEOUT.get(current_model, 45)

        # Portrait dimensions: FLUX supports native portrait, others get 2:3 ratio
        if current_model in NATIVE_PORTRAIT_MODELS:
            gen_w, gen_h = 768, 1024   # 3:4 portrait ratio
        else:
            gen_w, gen_h = 512, 768    # 2:3 portrait ratio

        # ── 1. Try huggingface_hub InferenceClient (recommended path) ────────
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(api_key=hf_token, timeout=timeout)
            gen_kwargs = dict(prompt=prompt, model=current_model, width=gen_w, height=gen_h)
            if seed is not None:
                gen_kwargs["seed"] = seed
            img = client.text_to_image(**gen_kwargs)
            if img:
                print(f"  [HF] Success via InferenceClient: {current_model}", flush=True)
                return _save_image(img, output_path, width, height)
        except Exception as e:
            last_error = e
            print(f"  [HF] InferenceClient failed for {current_model}: {type(e).__name__}", flush=True)

        # ── 2. Direct HTTP fallback ────────────────────────────────────────
        url = f"https://router.huggingface.co/hf-inference/models/{current_model}"
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
            "User-Agent": "AutoVideoStudio/1.0",
        }
        payload: dict = {"inputs": prompt, "parameters": {"width": gen_w, "height": gen_h}}
        if seed is not None:
            payload["parameters"]["seed"] = seed

        data = json.dumps(payload).encode("utf-8")
        model_failed = False
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    if resp.status == 200 and len(raw) > 5000:
                        print(f"  [HF] Success via HTTP: {current_model} (attempt {attempt+1})", flush=True)
                        return _save_image_bytes(raw, output_path, width, height)
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    # Model loading — wait briefly then retry once
                    try:
                        body = e.read().decode()
                        wait = min(json.loads(body).get("estimated_time", 8.0), 15.0)
                    except Exception:
                        wait = 8.0
                    print(f"  [HF] 503 loading {current_model}, waiting {wait:.0f}s...", flush=True)
                    time.sleep(wait)
                    continue
                elif e.code in (404, 400, 422):
                    last_error = e
                    model_failed = True
                    print(f"  [HF] {e.code} for {current_model} — skipping model", flush=True)
                    break
                else:
                    last_error = e
                    if attempt < retries - 1:
                        time.sleep(3.0)
            except Exception as e:
                last_error = e
                print(f"  [HF] HTTP attempt {attempt+1} failed: {type(e).__name__}", flush=True)
                if attempt < retries - 1:
                    time.sleep(3.0)

        if model_failed:
            continue

    raise RuntimeError(f"All HuggingFace models failed. Last error: {last_error}")

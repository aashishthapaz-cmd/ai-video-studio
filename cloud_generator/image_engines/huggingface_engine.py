import time
import json
import io
import urllib.request
from pathlib import Path
from PIL import Image

# Models tried in order — each is free-tier on HuggingFace Serverless Inference
HF_MODELS_CASCADE = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
]

def _save_image_bytes(raw: bytes, output_path: Path, target_w: int, target_h: int) -> str:
    """Decode raw bytes, resize to exact target, save as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if img.size != (target_w, target_h):
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img.save(output_path, "PNG", optimize=False)
    return str(output_path)


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
    Falls back through HF_MODELS_CASCADE if the requested model fails.
    Always outputs at the exact (width, height) specified.
    """
    if not hf_token:
        raise ValueError("Hugging Face API token required. Get one free at huggingface.co/settings/tokens")

    # Build full cascade: requested model first, then the rest
    cascade = [model] + [m for m in HF_MODELS_CASCADE if m != model]

    last_error = None
    for current_model in cascade:
        # Cap at 1024 for generation then upscale — most HF models top out at 1024
        gen_w = min(width, 1024)
        gen_h = min(height, 1024)

        # ── 1. Try huggingface_hub InferenceClient (fastest) ──────────────
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(api_key=hf_token, timeout=90)
            img = client.text_to_image(
                prompt=prompt,
                model=current_model,
                width=gen_w,
                height=gen_h,
                **({"seed": seed} if seed is not None else {}),
            )
            if img:
                img = img.convert("RGB")
                if img.size != (width, height):
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(output_path, "PNG", optimize=False)
                return str(output_path)
        except Exception as e:
            last_error = e

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
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=90) as resp:
                    raw = resp.read()
                    if resp.status == 200 and len(raw) > 5000:
                        return _save_image_bytes(raw, output_path, width, height)
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    try:
                        wait = min(json.loads(e.read().decode()).get("estimated_time", 10.0), 25.0)
                    except Exception:
                        wait = 10.0
                    time.sleep(wait)
                    continue
                elif e.code in (404, 400):
                    last_error = e
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

    raise RuntimeError(f"All HuggingFace models failed. Last error: {last_error}")

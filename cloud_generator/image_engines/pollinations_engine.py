import io
import time
import urllib.request
import urllib.parse
import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger("PollinationsEngine")

POLLINATIONS_MODELS = ["flux", "turbo", "midjourney"]


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


def _save_image_data(raw_data: bytes, output_path: Path, target_w: int, target_h: int) -> str:
    """Decode bytes, crop-fill to exact target dimensions, and save as PNG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(raw_data))
    if img.size != (target_w, target_h):
        img = _crop_fill(img, target_w, target_h)
    img.save(output_path, "PNG", optimize=False)
    return str(output_path)


def generate_pollinations_image(
    prompt: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    seed: int = None,
    model: str = "flux",
    api_key: str = "",
    retries: int = 2
) -> str:
    """
    Downloads a high-quality image from Pollinations.ai with multi-model fallback.
    If 'flux' is overloaded (HTTP 500), automatically fails over to 'turbo' or 'midjourney'.
    """
    if seed is None:
        seed = int(time.time() * 1000) % 1000000

    clean_prompt = prompt.replace("|", " ").strip()
    clean_prompt = " ".join(clean_prompt.split())
    # Keep prompt concise for URL encoding
    if len(clean_prompt) > 800:
        clean_prompt = clean_prompt[:800].rsplit(" ", 1)[0]
    encoded_prompt = urllib.parse.quote(clean_prompt)

    # Model cascade: requested model first, then remaining models
    models_to_try = [model] + [m for m in POLLINATIONS_MODELS if m != model]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_err = None
    for cur_model in models_to_try:
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={cur_model}&nologo=true&enhance=false&seed={seed}"
        if api_key:
            url += f"&token={api_key}"

        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=40) as resp:
                    if resp.status == 200:
                        data = resp.read()
                        if len(data) > 5000:  # Valid image check
                            return _save_image_data(data, output_path, width, height)
                        else:
                            raise ValueError(f"Received empty or corrupted image payload ({len(data)} bytes)")
            except urllib.error.HTTPError as e:
                last_err = e
                logger.warning(f"[Pollinations] HTTP {e.code} for model {cur_model}: {e.reason}")
                if e.code in (500, 502, 503, 504):
                    # Server overload on this model cluster: break immediately to try next model!
                    break
                elif e.code == 429:
                    time.sleep(2.0 * (attempt + 1))
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"Pollinations generation failed across all models ({', '.join(models_to_try)}): {last_err}")

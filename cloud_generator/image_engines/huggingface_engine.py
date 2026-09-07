import time
import json
import io
import urllib.request
from pathlib import Path
from PIL import Image

def generate_huggingface_image(prompt: str, output_path: Path, hf_token: str, model: str = "black-forest-labs/FLUX.1-schnell", width: int = 1080, height: int = 1920, seed: int = None, retries: int = 3) -> str:
    """
    Generates an image via Hugging Face Serverless Inference API (Free tier).
    Supports FLUX.1-schnell, SDXL, OpenJourney, etc.
    """
    if not hf_token:
        raise ValueError("Hugging Face API token is required. Get one for free at huggingface.co/settings/tokens")
    
    # 1. Try Hugging Face Hub InferenceClient (Primary)
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=hf_token, timeout=60)
        img = client.text_to_image(
            prompt=prompt,
            model=model,
            width=min(width, 1024),
            height=min(height, 1024),
            seed=seed
        )
        if img:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # If aspect ratio requires resizing to exact output resolution:
            if img.size != (width, height):
                img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
                img_resized.save(output_path, "PNG", quality=95)
            else:
                img.save(output_path, "PNG")
            return str(output_path)
    except Exception as e:
        logger_err = str(e)
    
    # 2. Direct HTTP Fallback
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": min(width, 1024),
            "height": min(height, 1024)
        }
    }
    if seed is not None:
        payload["parameters"]["seed"] = seed

    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                if resp.status == 200 and len(raw) > 5000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(raw)
                    return str(output_path)
        except urllib.error.HTTPError as e:
            if e.code == 503:
                try:
                    err_json = json.loads(e.read().decode("utf-8"))
                    wait_time = min(err_json.get("estimated_time", 10.0), 20.0)
                    time.sleep(wait_time)
                    continue
                except Exception:
                    time.sleep(5.0)
            elif attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
            else:
                raise
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
            else:
                raise e
    
    raise RuntimeError(f"Hugging Face generation failed: {logger_err}")

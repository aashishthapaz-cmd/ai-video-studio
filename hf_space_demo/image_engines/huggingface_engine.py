import time
import json
import urllib.request
from pathlib import Path

def generate_huggingface_image(prompt: str, output_path: Path, hf_token: str, model: str = "black-forest-labs/FLUX.1-schnell", width: int = 1080, height: int = 1920, seed: int = None, retries: int = 3) -> str:
    """
    Generates an image via Hugging Face Serverless Inference API (Free tier).
    Requires a free Hugging Face User Access Token (hf_...).
    """
    if not hf_token:
        raise ValueError("Hugging Face API token is required. Get one for free at huggingface.co/settings/tokens")
    
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": width,
            "height": height
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
            # Model loading 503
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
    
    raise RuntimeError("Hugging Face generation failed.")

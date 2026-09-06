import json
import base64
import urllib.request
from pathlib import Path

def generate_cloudflare_image(prompt: str, output_path: Path, account_id: str, api_token: str, model: str = "@cf/black-forest-labs/flux-1-schnell", width: int = 1080, height: int = 1920, seed: int = None) -> str:
    """
    Generates an image via Cloudflare Workers AI (10,000 free Neurons/day).
    Requires Cloudflare Account ID & API Token (Free tier, no credit card required).
    """
    if not account_id or not api_token:
        raise ValueError("Cloudflare Account ID and API Token must be provided in settings.")
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "num_steps": 4 if "schnell" in model or "lightning" in model else 20,
        "width": width,
        "height": height
    }
    if seed is not None:
        payload["seed"] = seed

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw_resp = resp.read()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if "image" in content_type or raw_resp.startswith(b'\x89PNG') or raw_resp.startswith(b'\xff\xd8'):
            output_path.write_bytes(raw_resp)
            return str(output_path)
        
        # In case returned as JSON base64
        try:
            parsed = json.loads(raw_resp.decode("utf-8"))
            if "result" in parsed and "image" in parsed["result"]:
                img_data = base64.b64decode(parsed["result"]["image"])
                output_path.write_bytes(img_data)
                return str(output_path)
        except Exception:
            pass
        
        if len(raw_resp) > 5000:
            output_path.write_bytes(raw_resp)
            return str(output_path)
        raise RuntimeError("Cloudflare did not return a valid image.")

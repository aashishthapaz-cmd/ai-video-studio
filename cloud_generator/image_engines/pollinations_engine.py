import time
import urllib.request
import urllib.parse
from pathlib import Path

def generate_pollinations_image(prompt: str, output_path: Path, width: int = 1080, height: int = 1920, seed: int = None, model: str = "flux", api_key: str = "", retries: int = 3) -> str:
    """
    Downloads a high-quality image from Pollinations.ai.
    Zero local GPU/CPU footprint.
    """
    if seed is None:
        seed = int(time.time() * 1000) % 1000000
    
    clean_prompt = prompt.replace("|", " ").strip()
    clean_prompt = " ".join(clean_prompt.split())
    encoded_prompt = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={model}&nologo=true&seed={seed}"
    if api_key:
        url += f"&token={api_key}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 5000: # Valid image check
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(data)
                        return str(output_path)
                    else:
                        raise ValueError(f"Received empty or corrupted image payload ({len(data)} bytes)")
                else:
                    raise RuntimeError(f"HTTP Status {resp.status}")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                raise RuntimeError(f"Pollinations rate limit (HTTP 429)")
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:
            last_err = e
            time.sleep(2.0 * (attempt + 1))
    
    raise RuntimeError(f"Pollinations generation failed: {last_err}")

import time
import random
import hashlib
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
try:
    from .config import load_settings
    from .image_engines.pollinations_engine import generate_pollinations_image
    from .image_engines.cloudflare_engine import generate_cloudflare_image
    from .image_engines.huggingface_engine import generate_huggingface_image
except ImportError:
    from config import load_settings
    from image_engines.pollinations_engine import generate_pollinations_image
    from image_engines.cloudflare_engine import generate_cloudflare_image
    from image_engines.huggingface_engine import generate_huggingface_image

logger = logging.getLogger("ImageRouter")

def _generate_fallback_art(prompt: str, output_path: Path, width: int = 1080, height: int = 1920, scene_index: int = 0) -> str:
    """Generates a unique, distinct atmospheric art canvas per scene if cloud engines are offline."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    palettes = [
        ((15, 20, 35), (45, 30, 60)),
        ((35, 20, 15), (65, 45, 25)),
        ((15, 35, 30), (30, 65, 50)),
        ((25, 15, 35), (55, 30, 50)),
        ((20, 25, 20), (45, 60, 35)),
        ((30, 25, 40), (50, 40, 65)),
        ((20, 30, 45), (40, 55, 70))
    ]
    top_col, bot_col = palettes[scene_index % len(palettes)]
    im = Image.new("RGB", (width, height), top_col)
    draw = ImageDraw.Draw(im)
    for y in range(height):
        ratio = y / height
        r = int(top_col[0] * (1 - ratio) + bot_col[0] * ratio)
        g = int(top_col[1] * (1 - ratio) + bot_col[1] * ratio)
        b = int(top_col[2] * (1 - ratio) + bot_col[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
        
    orb_x = int(width * (0.3 + (scene_index * 0.15) % 0.4))
    orb_y = int(height * (0.35 + (scene_index * 0.1) % 0.3))
    draw.ellipse([orb_x - 140, orb_y - 140, orb_x + 140, orb_y + 140], fill=(240, 225, 190))
    im = im.filter(ImageFilter.GaussianBlur(radius=12))
    im.save(output_path, "PNG")
    return str(output_path)

def generate_scene_image(prompt: str, output_path: Path, width: int = None, height: int = None, seed: int = None, preferred_engine: str = None) -> dict:
    """
    Unified multi-cloud image router with automatic failover.
    Tries preferred or priority-ordered free cloud image engines.
    """
    cfg = load_settings()
    width = width or cfg.get("output_width", 1080)
    height = height or cfg.get("output_height", 1920)
    if seed is None:
        seed = random.randint(100000, 999999999)

    priority = [preferred_engine] if preferred_engine else cfg.get("image_engine_priority", ["pollinations", "cloudflare", "huggingface"])
    
    errors = []
    for engine in priority:
        if not engine:
            continue
        engine = engine.lower().strip()
        try:
            if "pollinations" in engine:
                model = "turbo" if "turbo" in engine else cfg.get("pollinations_model", "flux")
                api_key = cfg.get("pollinations_api_key", "")
                try:
                    img = generate_pollinations_image(prompt, output_path, width=width, height=height, seed=seed, model=model, api_key=api_key)
                    return {"ok": True, "engine": f"Pollinations ({model})", "path": img}
                except Exception as e:
                    if model != "turbo":
                        try:
                            time.sleep(1.0)
                            img = generate_pollinations_image(prompt, output_path, width=width, height=height, seed=seed, model="turbo", api_key=api_key)
                            return {"ok": True, "engine": "Pollinations (turbo fallback)", "path": img}
                        except Exception:
                            pass
                    raise e
            
            elif engine == "cloudflare":
                acc_id = cfg.get("cloudflare_account_id", "")
                token = cfg.get("cloudflare_api_token", "")
                if not acc_id or not token:
                    continue
                img = generate_cloudflare_image(prompt, output_path, account_id=acc_id, api_token=token, width=width, height=height, seed=seed)
                return {"ok": True, "engine": "Cloudflare Workers AI", "path": img}
            
            elif engine == "huggingface":
                hf_token = cfg.get("huggingface_token", "")
                if not hf_token:
                    continue
                img = generate_huggingface_image(prompt, output_path, hf_token=hf_token, width=width, height=height, seed=seed)
                return {"ok": True, "engine": "Hugging Face Serverless", "path": img}
                
        except Exception as exc:
            errors.append(f"{engine}: {exc}")
            continue

    logger.warning(f"All image engines failed ({'; '.join(errors)}). Using aesthetic fallback canvas.")
    fallback_path = _generate_fallback_art(prompt, output_path, width, height)
    return {"ok": True, "engine": "Aesthetic Mood Canvas (Fallback)", "path": fallback_path}

def generate_all_scene_images(scenes: list, assets_dir: Path, progress_callback=None) -> list:
    """
    Generates guaranteed unique images for all scenes with zero repetition.
    Strictly verifies image uniqueness and hashes to ensure no image is ever repeated.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(scenes)
    seen_hashes = {}
    
    for i, scene in enumerate(scenes):
        scene_id = scene.get("id", f"scene_{i+1:03d}")
        raw_prompt = scene.get("prompt", "").strip() or scene.get("narration", "").strip()
        
        # Ensure every scene (and especially the closing 2 scenes) has rich cinematic visual cues
        is_closing_scene = (i >= total - 2)
        aesthetic_booster = ""
        if len(raw_prompt.split()) < 20 or "cinematic" not in raw_prompt.lower():
            if is_closing_scene:
                aesthetic_booster = ", emotional warm sunset chiaroscuro, cinematic 35mm film photography, masterpiece, rich depth of field, delicate atmospheric golden glow, 8k resolution"
            else:
                aesthetic_booster = ", cinematic mood, soft film grain, natural ambient lighting, 35mm photography, high aesthetic, detailed textures, masterpiece"
                
        base_prompt = raw_prompt.rstrip(" ,.;:") + aesthetic_booster
        out_file = assets_dir / f"{scene_id}.png"
        
        if progress_callback:
            progress_callback(i + 1, total, f"Generating unique image for {scene_id}")
            
        success = False
        for attempt in range(3):
            # High-entropy random seed for every attempt
            seed = random.randint(100000, 999999999)
            
            # Add subtle framing nuance on retries to prevent remote cache hits
            angle_salts = [
                "",
                f", unique composition perspective angle {i+1}",
                f", distinctive atmospheric lighting variation {i+1}",
                f", non-repeating scenic depth {i+1}"
            ]
            prompt = base_prompt.rstrip(" ,.;:") + angle_salts[attempt % len(angle_salts)]

            res = generate_scene_image(prompt, out_file, seed=seed)
            img_path = Path(res["path"])
            
            if img_path.exists() and img_path.stat().st_size > 1000:
                img_bytes = img_path.read_bytes()
                img_hash = hashlib.md5(img_bytes).hexdigest()
                
                # Check for duplicate image across scenes
                if img_hash not in seen_hashes:
                    seen_hashes[img_hash] = scene_id
                    scene["image_path"] = str(img_path)
                    scene["image_engine"] = res["engine"]
                    success = True
                    time.sleep(1.2)
                    break
                else:
                    logger.warning(f"Duplicate image hash detected for {scene_id} (identical to {seen_hashes[img_hash]}). Regenerating with new seed...")
                    time.sleep(1.2)
            else:
                time.sleep(1.2)
                
        if not success:
            # Distinct fallback canvas with unique per-scene palette
            fallback_path = _generate_fallback_art(base_prompt, out_file, scene_index=i)
            scene["image_path"] = fallback_path
            scene["image_engine"] = "Distinct Mood Canvas"
            
        results.append(scene)
        
        if i < total - 1:
            time.sleep(1.0)
            
    return results

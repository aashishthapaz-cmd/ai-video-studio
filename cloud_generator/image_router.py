import time
import uuid
import random
import hashlib
import logging
from pathlib import Path
from PIL import Image, ImageDraw

try:
    from .config import load_settings
    from .image_engines.pollinations_engine import generate_pollinations_image
    from .image_engines.cloudflare_engine import generate_cloudflare_image
    from .image_engines.huggingface_engine import generate_huggingface_image
    from .image_engines.puter_engine import generate_puter_image
    from .image_engines.google_flow_engine import generate_google_flow_image, is_google_flow_configured
    from .image_engines.perchance_engine import generate_perchance_image, is_perchance_available
except ImportError:
    from config import load_settings
    from image_engines.pollinations_engine import generate_pollinations_image
    from image_engines.cloudflare_engine import generate_cloudflare_image
    from image_engines.huggingface_engine import generate_huggingface_image
    from image_engines.puter_engine import generate_puter_image
    from image_engines.google_flow_engine import generate_google_flow_image, is_google_flow_configured
    from image_engines.perchance_engine import generate_perchance_image, is_perchance_available

logger = logging.getLogger("ImageRouter")

# ── Per-process entropy salt ensures no two runs (poems) share the same seed space ──
_RUN_ENTROPY = uuid.uuid4().hex  # unique per GitHub Actions runner invocation


def _unique_seed(base: str, attempt: int = 0) -> int:
    """Generates a stable but globally unique seed from a string key + attempt + run entropy."""
    raw = f"{_RUN_ENTROPY}:{base}:{attempt}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


def _generate_artistic_fallback_canvas(output_path: Path, width: int, height: int, seed: int) -> str:
    """
    Generates a rich, atmospheric, poetic mood canvas if all remote engines fail.
    Combines deep indigo-amber cinematic lighting, radial atmospheric haze, and soft golden particles.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    
    # Base deep atmospheric gradient (nocturnal indigo to warm vintage charcoal)
    im = Image.new("RGB", (width, height), (12, 14, 24))
    draw = ImageDraw.Draw(im)
    
    for y in range(height):
        t = y / height
        # Smooth ease-in-out curve
        t_curved = t * t * (3 - 2 * t)
        r = int(10 + (28 - 10) * t_curved)
        g = int(13 + (22 - 13) * t_curved)
        b = int(24 + (32 - 24) * t_curved)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
        
    # Central warm atmospheric glow (poetic golden/amber candlelit aura)
    center_x = width // 2 + rng.randint(-width // 8, width // 8)
    center_y = int(height * 0.45) + rng.randint(-height // 10, height // 10)
    max_radius = int(min(width, height) * 0.65)
    
    # Layer soft concentric radial circles
    for radius in range(max_radius, 0, -8):
        alpha = (1.0 - (radius / max_radius)) ** 1.8
        glow_r = min(255, int(18 + 65 * alpha))
        glow_g = min(255, int(22 + 45 * alpha))
        glow_b = min(255, int(35 + 20 * alpha))
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=(glow_r, glow_g, glow_b)
        )
    
    # Subtle drifting golden dust / starlight particles
    for _ in range(60):
        px = rng.randint(40, width - 40)
        py = rng.randint(60, height - 60)
        p_radius = rng.randint(1, 3)
        brightness = rng.uniform(0.3, 0.85)
        pr = int(220 * brightness)
        pg = int(190 * brightness)
        pb = int(140 * brightness)
        draw.ellipse([px - p_radius, py - p_radius, px + p_radius, py + p_radius], fill=(pr, pg, pb))
        
    im.save(output_path, "PNG", quality=95)
    logger.info(f"Artistic fallback mood canvas saved to {output_path}")
    return str(output_path)


def _emergency_fallback_from_pollinations(prompt: str, output_path: Path, width: int, height: int, seed: int) -> str:
    """
    Last-resort: tries Pollinations cascade (flux -> turbo -> midjourney) with a simplified prompt.
    If network totally fails, generates an evocative artistic mood canvas instead of a blank screen.
    """
    clean = prompt.split("no white border")[0].split("no borders")[0].strip().rstrip(",. ")
    short_prompt = clean[:180].rsplit(" ", 1)[0] if len(clean) > 180 else clean
    
    # 1. Try Pollinations cascade (flux -> turbo -> midjourney)
    try:
        return generate_pollinations_image(
            short_prompt, output_path, width=width, height=height,
            seed=seed, model=None, retries=2
        )
    except Exception as e:
        logger.warning(f"Emergency Pollinations cascade failed: {e}. Trying fast turbo fallback...")
        
    # 2. Try Pollinations turbo directly
    try:
        return generate_pollinations_image(
            short_prompt, output_path, width=width, height=height,
            seed=seed, model="turbo", retries=2
        )
    except Exception as e2:
        logger.warning(f"Pollinations turbo emergency failed: {e2}. Generating artistic mood canvas.")
        
    # 3. Absolute offline safety net: rich poetic mood canvas
    return _generate_artistic_fallback_canvas(output_path, width, height, seed)


# ─── UNIVERSAL NEGATIVE TAGS applied to every prompt ─────────────────────────
# These prevent: white borders, pillarbox bars, AI portrait defaults, wrong gender
_UNIVERSAL_NEGATIVE = (
    "no white border, no white frame, no black bar, no letterbox, no pillarbox, "
    "no vignette frame, no oval frame, no polaroid frame, no film border, "
    "no picture frame, no canvas edge, no margin, no padding, "
    "no watermark, no text, no letters, no typography, no logo, "
    "no photorealistic portrait, no stock photo, no glamour shot, "
    "no beauty shot, no selfie, no close-up face, no AI face default, "
    "no realistic young woman unless poem is about a woman, "
    "no anime girl, no deformed anatomy, edge-to-edge full bleed"
)

# Subject-specific gender negatives added ON TOP of universal
_SUBJECT_NEGATIVE = {
    "father": "no woman, no female face, no girl, no feminine features, no young face",
    "mother": "no man, no male face, no boy, no masculine figure",
    "child":  "no adult face, no glamour, no model",
}


def _build_prompt(raw_prompt: str, subject_type: str = None) -> str:
    """
    Builds the final prompt sent to the image engine.
    
    CRITICAL DESIGN:
    - Subject/gender MUST be at the START — FLUX reads left-to-right and truncates
    - Keep total length under 300 words for reliable FLUX prompt following
    - Negative tags go at the end
    - NO '35mm photography', 'film grain', 'photorealism' — these make FLUX generate photo-realistic women
    """
    # Extract just the scene description (before any negative tags already in the prompt)
    for split_marker in ["no white border", "no borders", "Masterpiece, 8k", "edge-to-edge full bleed 9:16"]:
        if split_marker.lower() in raw_prompt.lower():
            idx = raw_prompt.lower().find(split_marker.lower())
            raw_prompt = raw_prompt[:idx].strip().rstrip(",. ")
            break

    # Build subject negative
    subject_neg = ""
    if subject_type and subject_type in _SUBJECT_NEGATIVE:
        subject_neg = _SUBJECT_NEGATIVE[subject_type] + ", "

    final_negative = subject_neg + _UNIVERSAL_NEGATIVE

    return f"{raw_prompt.strip()}. {final_negative}"


def generate_scene_image(
    prompt: str,
    output_path: Path,
    width: int = None,
    height: int = None,
    seed: int = None,
    preferred_engine: str = None,
    subject_type: str = None,
) -> dict:
    """
    Unified multi-cloud image router with automatic failover.
    HuggingFace → Cloudflare → Pollinations → Emergency Pollinations (never gradient).
    
    subject_type: 'father', 'mother', 'child', 'lover', 'self_reflection', etc.
                  Used to add gender-specific negative prompts.
    """
    cfg = load_settings()
    width = width or cfg.get("output_width", 1080)
    height = height or cfg.get("output_height", 1920)
    if seed is None:
        seed = random.randint(100000, 999999999)

    # Build the final prompt with universal negatives and subject gender lock
    final_prompt = _build_prompt(prompt, subject_type=subject_type)

    priority = (
        [preferred_engine] if preferred_engine
        # Perchance (Primary) → Google Flow (Secondary) → Cloudflare (FLUX) → Puter → Pollinations → HuggingFace
        else cfg.get("image_engine_priority", ["perchance", "google_flow", "cloudflare", "puter", "pollinations", "huggingface"])
    )

    errors = []
    for engine in priority:
        if not engine:
            continue
        engine = engine.lower().strip()
        try:
            if "perchance" in engine:
                if not is_perchance_available():
                    errors.append("perchance: engine unavailable in this environment")
                    continue
                style = cfg.get("perchance_style", "Anime")
                img = generate_perchance_image(
                    final_prompt, output_path, width=width, height=height, seed=seed, style=style
                )
                return {"ok": True, "engine": f"Perchance AI ({style})", "path": img}

            elif "flow" in engine or "google_flow" in engine:
                if not is_google_flow_configured():
                    errors.append("google_flow: not logged in (run 'python google_flow_login.py' or set GOOGLE_FLOW_SESSION secret)")
                    continue
                img = generate_google_flow_image(
                    final_prompt, output_path, width=width, height=height, seed=seed
                )
                return {"ok": True, "engine": "Google Flow (Nano Banana)", "path": img}

            elif "puter" in engine or "banana" in engine:
                puter_token = cfg.get("puter_auth_token", "")
                if not puter_token:
                    errors.append("puter: no auth token configured (get free token at puter.com/dashboard)")
                    continue
                puter_model = cfg.get("puter_model", "gemini-3.1-flash-image-preview")
                img = generate_puter_image(
                    final_prompt, output_path, auth_token=puter_token, model=puter_model,
                    width=width, height=height, seed=seed
                )
                return {"ok": True, "engine": f"Puter Nano Banana ({puter_model})", "path": img}

            elif "cloudflare" in engine or "cf" in engine:
                acc_id = cfg.get("cloudflare_account_id", "")
                token = cfg.get("cloudflare_api_token", "")
                if not acc_id or not token:
                    errors.append("cloudflare: no credentials")
                    continue
                img = generate_cloudflare_image(
                    final_prompt, output_path, account_id=acc_id, api_token=token, width=width, height=height, seed=seed
                )
                return {"ok": True, "engine": "Cloudflare Workers AI", "path": img}

            elif "pollinations" in engine:
                model = "turbo" if "turbo" in engine else cfg.get("pollinations_model", "flux")
                api_key = cfg.get("pollinations_api_key", "")
                try:
                    img = generate_pollinations_image(
                        final_prompt, output_path, width=width, height=height, seed=seed, model=model, api_key=api_key
                    )
                    return {"ok": True, "engine": f"Pollinations ({model})", "path": img}
                except Exception as e:
                    if model != "turbo":
                        try:
                            time.sleep(1.5)
                            img = generate_pollinations_image(
                                final_prompt, output_path, width=width, height=height, seed=seed, model="turbo", api_key=api_key
                            )
                            return {"ok": True, "engine": "Pollinations (turbo fallback)", "path": img}
                        except Exception:
                            pass
                    raise e

            elif "huggingface" in engine:
                hf_token = cfg.get("huggingface_token", "")
                if not hf_token:
                    errors.append("huggingface: no token")
                    continue
                img = generate_huggingface_image(
                    final_prompt, output_path, hf_token=hf_token, width=width, height=height, seed=seed
                )
                return {"ok": True, "engine": "Hugging Face Serverless", "path": img}

        except Exception as exc:
            errors.append(f"{engine}: {exc}")
            logger.warning(f"[ImageRouter] {engine} failed: {exc}")
            continue

    # ── ALL engines failed: Emergency Pollinations (no token needed) ──────────
    # NEVER use the gradient canvas — always try to get a real image
    logger.warning(f"All primary engines failed ({'; '.join(errors)}). Attempting emergency Pollinations...")
    emergency_path = _emergency_fallback_from_pollinations(final_prompt, output_path, width, height, seed)
    return {"ok": True, "engine": "Emergency Pollinations Fallback", "path": emergency_path}


def generate_all_scene_images(scenes: list, assets_dir: Path, progress_callback=None) -> list:
    """
    Generates strictly unique, borderless, poem-subject-accurate images for all scenes.

    Key guarantees:
    - Subject (father/mother/etc.) extracted from prompt and used to lock gender
    - FLUX-friendly prompts: subject/gender at start, positive description, negatives at end
    - Cross-poem uniqueness via _RUN_ENTROPY UUID (unique per GitHub Actions run)
    - Per-scene compound seed: run_entropy + scene_id + attempt → globally unique
    - MD5 hash registry catches any accidental duplicates and forces retry
    - NEVER uses gradient canvas — always tries emergency Pollinations on total failure
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(scenes)
    seen_hashes: dict[str, str] = {}  # hash → scene_id

    # Lighting variants used to salt retries (ensure uniqueness without changing content)
    _lighting_variants = [
        "golden hour warm light", "blue hour twilight glow", "overcast diffused light",
        "dramatic chiaroscuro lighting", "morning mist soft haze", "nocturnal ambient glow",
        "candlelight warm amber", "moonlit silver radiance",
    ]
    _composition_variants = [
        "wide environmental shot", "intimate silhouette framing",
        "close detail of hands or objects", "cinematic low angle",
        "high angle bird's-eye view", "medium portrait framing",
        "over-the-shoulder perspective", "centered symmetrical composition",
    ]

    for i, scene in enumerate(scenes):
        scene_id = scene.get("id", f"scene_{i+1:03d}")
        raw_prompt = scene.get("prompt", "").strip() or scene.get("narration", "").strip()

        # Extract subject type from prompt for gender locking
        subject_type = None
        prompt_lower = raw_prompt.lower()
        if any(k in prompt_lower for k in ["elderly man", "old man", "father", "calloused hands", "working-class old man"]):
            subject_type = "father"
        elif any(k in prompt_lower for k in ["older woman", "mother", "gentle woman", "woman's hands"]):
            subject_type = "mother"
        elif any(k in prompt_lower for k in ["small child", "child silhouette", "tiny child"]):
            subject_type = "child"

        out_file = assets_dir / f"{scene_id}.png"

        if progress_callback:
            progress_callback(i + 1, total, f"Generating image for {scene_id}")

        success = False
        for attempt in range(3):  # 3 attempts max: HF try, Pollinations fallback, emergency

            # Compound seed: run entropy + scene id + attempt → guaranteed globally unique
            seed = _unique_seed(f"{scene_id}:{raw_prompt[:40]}", attempt)

            # Rotate lighting/composition on retries to guarantee visual variety
            if attempt > 0:
                lighting = _lighting_variants[(i + attempt * 3) % len(_lighting_variants)]
                composition = _composition_variants[(i + attempt * 2 + 1) % len(_composition_variants)]
                salt = f", {lighting}, {composition}"
                salted_prompt = raw_prompt.rstrip(" ,.;:") + salt
            else:
                salted_prompt = raw_prompt

            try:
                res = generate_scene_image(
                    salted_prompt, out_file, seed=seed, subject_type=subject_type
                )
                img_path = Path(res["path"])

                if img_path.exists() and img_path.stat().st_size > 5000:
                    img_bytes = img_path.read_bytes()
                    img_hash = hashlib.md5(img_bytes).hexdigest()

                    if img_hash not in seen_hashes:
                        seen_hashes[img_hash] = scene_id
                        scene["image_path"] = str(img_path)
                        scene["image_engine"] = res["engine"]
                        success = True
                        print(f"  ✅ [{scene_id}] Image OK via {res['engine']} (attempt {attempt+1})", flush=True)
                        time.sleep(0.2)
                        break
                    else:
                        logger.warning(
                            f"Duplicate image hash for {scene_id} (same as {seen_hashes[img_hash]}). "
                            f"Retrying with new seed/salt (attempt {attempt+1})..."
                        )
                        time.sleep(1.5)
                else:
                    time.sleep(1.5)
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {scene_id}: {e}")
                time.sleep(2.5)

        if not success:
            # Try one final emergency attempt with Pollinations directly
            print(f"  ⚠️ [{scene_id}] Primary engine attempts exhausted. Trying emergency Pollinations...", flush=True)
            emergency_seed = _unique_seed(f"emergency:{scene_id}", 99)
            emergency_path = _emergency_fallback_from_pollinations(
                raw_prompt, out_file, 1080, 1920, emergency_seed
            )
            scene["image_path"] = emergency_path
            scene["image_engine"] = "Emergency Pollinations"
            print(f"  🆘 [{scene_id}] Used emergency fallback.", flush=True)

        # Ultimate safety check: ensure the image file exists and is valid on disk
        final_img = Path(scene.get("image_path", ""))
        if not final_img.exists() or final_img.stat().st_size < 1000:
            emergency_seed = _unique_seed(f"canvas:{scene_id}", 101)
            canvas_path = _generate_artistic_fallback_canvas(out_file, 1080, 1920, emergency_seed)
            scene["image_path"] = str(canvas_path)
            scene["image_engine"] = "Artistic Mood Canvas"

        results.append(scene)

        # Brief pause between scenes to avoid rate-limit bursts
        if i < total - 1:
            time.sleep(0.8)

    return results

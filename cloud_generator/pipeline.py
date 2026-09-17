import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import json
import re
import logging
from pathlib import Path
try:
    from .config import WORKSPACE_DIR, load_settings
    from .prompt_engine import plan_scenes_for_poem
    from .voice_engine import synthesize_project_audio
    from .image_router import generate_all_scene_images
    from .video_compiler import compile_cloud_video, sanitize_title
    from .facebook_publisher import publish_to_all_enabled_pages, format_typewriter_facebook_caption
    from .niche_profiles import get_niche, detect_niche_from_text
except ImportError:
    from config import WORKSPACE_DIR, load_settings
    from prompt_engine import plan_scenes_for_poem
    from voice_engine import synthesize_project_audio
    from image_router import generate_all_scene_images
    from video_compiler import compile_cloud_video, sanitize_title
    from facebook_publisher import publish_to_all_enabled_pages, format_typewriter_facebook_caption
    from niche_profiles import get_niche, detect_niche_from_text

logger = logging.getLogger("CloudPipeline")

def run_cloud_pipeline(title: str, script_text: str, custom_vibe: str = "", progress_callback = None, auto_publish_fb: bool = None, target_page_ids: list = None, niche_id: str = None, preferred_image_engine: str = None, **kwargs) -> dict:
    """
    Executes end-to-end zero-cost video generation tuned to the assigned poetry niche:
    1. Poetry Niche Resolution & Aesthetic Stanza Planning
    2. Niche-Tuned Voice Synthesis (Reference whisper clone / Edge Neural models)
    3. Multi-Engine Image Generation (Local ComfyUI / Perchance / Pollinations)
    4. Niche Typography 2.5D Parallax Video Render (Cursive, Serif, Minimalist Bold)
    5. Autonomous Facebook Publishing with Niche-Tuned Copy & Emojis
    """
    t0 = time.time()
    cfg = load_settings()
    if auto_publish_fb is None:
        auto_publish_fb = cfg.get("auto_publish_facebook", False)
        
    raw_slug = sanitize_title(title).lower().replace(" ", "_")
    safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '', raw_slug) or f"job_{int(time.time())}"
    job_dir = WORKSPACE_DIR / f"{safe_slug}_{int(time.time())}"
    job_dir.mkdir(parents=True, exist_ok=True)
    
    audio_dir = job_dir / "audio"
    assets_dir = job_dir / "assets"
    
    def report(pct: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass
        try:
            print(f"[{pct}%] {msg}", flush=True)
        except Exception:
            try:
                safe = msg.encode("ascii", errors="replace").decode("ascii")
                print(f"[{pct}%] {safe}", flush=True)
            except Exception:
                pass

    # Resolve Poetry Niche
    resolved_niche_id = niche_id
    if not resolved_niche_id and target_page_ids:
        pages = cfg.get("facebook_pages", [])
        matched = next((p for p in pages if (p.get("id") in target_page_ids or p.get("page_id") in target_page_ids)), None)
        if matched and matched.get("niche_id"):
            resolved_niche_id = matched.get("niche_id")

    if not resolved_niche_id:
        if custom_vibe and custom_vibe.lower().replace(" ", "_") in ("typewriters_voice_nostalgia", "dark_romantic_academia", "romantic_devotion", "healing_self_worth", "cosmic_philosophy"):
            resolved_niche_id = custom_vibe.lower().replace(" ", "_")
        else:
            resolved_niche_id = detect_niche_from_text(title, script_text)

    niche = get_niche(resolved_niche_id)
    report(5, f"Step 1/6: Poetry Niche '{niche.name}' | Medium: {niche.art.display_name}")

    # 1. Script & Scene Planning
    effective_vibe = custom_vibe if (custom_vibe and custom_vibe not in ("auto", "Adaptive Multi-World", "Auto-Detect (Adaptive Multi-World)")) else niche.art.vibe_id
    report(12, f"Step 1/6: Analyzing poetic cadence & planning visual scenes ({effective_vibe})...")
    scenes = plan_scenes_for_poem(title, script_text, effective_vibe)
    
    if not scenes:
        raise ValueError("Could not extract any valid scenes from the script.")
        
    for s in scenes:
        s["caption_style"] = niche.caption.style_name

    # 2. Voice Generation
    report(22, f"Step 2/6: Synthesizing voiceover ({len(scenes)} scenes via {niche.voice.tone_description})...")
    scenes = synthesize_project_audio(
        scenes, 
        audio_dir,
        voice_override=niche.voice.voice_id,
        rate_override=niche.voice.rate,
        pitch_override=niche.voice.pitch,
        engine_override=niche.voice.engine
    )
    report(40, "Step 2/6: Voiceover audio mastered & acoustically synchronized.")
    
    # Save intermediate plan
    job_plan = {
        "title": title,
        "script": script_text,
        "niche_id": niche.niche_id,
        "niche_name": niche.name,
        "scenes": scenes,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    (job_dir / "job_plan.json").write_text(json.dumps(job_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. Image Generation via Multi-Engine Router (ComfyUI / Perchance / Pollinations)
    engine_name = (preferred_image_engine or "Local ComfyUI").upper()
    report(45, f"Step 3/6: Generating {len(scenes)} scene image(s) via {engine_name}...")
    
    def img_prog(curr, total, text):
        step_pct = 45 + int((curr / max(1, total)) * 32)
        report(step_pct, f"Step 3/6: [{curr}/{total}] {text}")
        
    scenes = generate_all_scene_images(scenes, assets_dir, progress_callback=img_prog, preferred_engine=preferred_image_engine)
    report(78, f"Step 3/6: All {len(scenes)} artistic scene visuals generated and verified!")
    
    # 4. Final Video Compilation
    caption_style_map = {
        "ReferenceCursive": "reference_cursive",
        "DarkAcademiaSerif": "dark_academia_serif",
        "RomanticScript": "romantic_script",
        "StoicMinimal": "stoic_minimal",
        "CosmicSerif": "cosmic_serif",
        "TypewriterMono": "typewriter_mono"
    }
    cap_style = caption_style_map.get(niche.caption.style_name, "reference_cursive")
    report(82, f"Step 4/6: Aligning karaoke typography ({cap_style} on {niche.caption.font_name})...")
    report(86, "Step 5/6: Compiling 1080x1920 MP4 with 2.5D quintic parallax & film grain...")
    render_result = compile_cloud_video(scenes, title, job_dir, caption_style=cap_style)
    final_output = Path(render_result["output"])
    
    # 5. Autonomous Facebook Multi-Page Publishing
    fb_results = []
    if auto_publish_fb:
        report(94, f"Step 6/6: Auto-publishing video to Facebook Page(s) for niche '{niche.name}'...")
        try:
            from .facebook_publisher import format_niche_facebook_caption
            fb_desc = format_niche_facebook_caption(title, script_text, niche)
        except Exception:
            fb_desc = format_typewriter_facebook_caption(title, script_text, niche.copy.default_hashtags)
        try:
            fb_results = publish_to_all_enabled_pages(
                video_path=final_output,
                title=title,
                description=fb_desc,
                target_page_ids=target_page_ids
            )
            success_count = sum(1 for r in fb_results if r.get("ok"))
            report(98, f"Step 6/6: Published to {success_count}/{len(fb_results)} Facebook Page(s)")
        except Exception as e:
            logger.error(f"Facebook auto-publish failed: {e}")
            fb_results = [{"ok": False, "error": str(e)}]
    else:
        report(96, "Step 6/6: Render Only mode — video saved to Outputs & Artifacts.")
    
    total_time = round(time.time() - t0, 2)
    report(100, f"Step 6/6: Completed successfully! Video ready: {final_output.name} ({total_time}s)")
    
    return {
        "ok": True,
        "title": title,
        "output_file": render_result["output"],
        "duration": render_result.get("duration", 0.0),
        "scenes": len(scenes),
        "total_render_time_seconds": total_time,
        "facebook_published": fb_results,
        "job_dir": str(job_dir)
    }

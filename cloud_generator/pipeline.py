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
    from .facebook_publisher import publish_to_all_enabled_pages
except ImportError:
    from config import WORKSPACE_DIR, load_settings
    from prompt_engine import plan_scenes_for_poem
    from voice_engine import synthesize_project_audio
    from image_router import generate_all_scene_images
    from video_compiler import compile_cloud_video, sanitize_title
    from facebook_publisher import publish_to_all_enabled_pages

logger = logging.getLogger("CloudPipeline")

def run_cloud_pipeline(title: str, script_text: str, custom_vibe: str = "", progress_callback = None, auto_publish_fb: bool = None, target_page_ids: list = None) -> dict:
    """
    Executes end-to-end zero-cost cloud video generation.
    1. Script Stanza Planning & Aesthetics
    2. Edge Neural TTS Voice Synthesis (0 MB VRAM)
    3. Multi-Cloud Image Generation (Pollinations / Cloudflare / HuggingFace)
    4. 2.5D Parallax Video Render
    5. Autonomous Multi-Page Facebook Publishing (if enabled)
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
            progress_callback(pct, msg)
        print(f"[{pct}%] {msg}")

    # 1. Script & Scene Planning
    report(10, "Analyzing script and generating aesthetic scene prompts...")
    scenes = plan_scenes_for_poem(title, script_text, custom_vibe)
    
    if not scenes:
        raise ValueError("Could not extract any valid scenes from the script.")
        
    # 2. Voice Generation (Edge Neural TTS)
    report(30, f"Synthesizing {len(scenes)} lines via Edge Neural Cloud TTS...")
    scenes = synthesize_project_audio(scenes, audio_dir)
    
    # Save intermediate plan
    job_plan = {
        "title": title,
        "script": script_text,
        "scenes": scenes,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    (job_dir / "job_plan.json").write_text(json.dumps(job_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 3. Image Generation via Multi-Cloud Router
    report(55, f"Generating {len(scenes)} scene images via Multi-Cloud Router...")
    
    def img_prog(curr, total, text):
        step_pct = 55 + int((curr / max(1, total)) * 25)
        report(step_pct, f"Images [{curr}/{total}]: {text}")
        
    scenes = generate_all_scene_images(scenes, assets_dir, progress_callback=img_prog)
    
    # 4. Final Video Compilation
    report(85, "Rendering final 1080x1920 video with 2.5D parallax and transitions...")
    render_result = compile_cloud_video(scenes, title, job_dir)
    final_output = Path(render_result["output"])
    
    # 5. Autonomous Facebook Multi-Page Publishing
    fb_results = []
    if auto_publish_fb:
        report(92, "Auto-publishing video to configured Facebook Pages...")
        try:
            fb_results = publish_to_all_enabled_pages(
                video_path=final_output,
                title=title,
                description=script_text,
                target_page_ids=target_page_ids
            )
            success_count = sum(1 for r in fb_results if r.get("ok"))
            report(96, f"Published to {success_count}/{len(fb_results)} Facebook Page(s)")
        except Exception as e:
            logger.error(f"Facebook auto-publish failed: {e}")
            fb_results = [{"ok": False, "error": str(e)}]
    
    total_time = round(time.time() - t0, 2)
    report(100, f"Video complete! Ready at {render_result['output']} in {total_time}s")
    
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

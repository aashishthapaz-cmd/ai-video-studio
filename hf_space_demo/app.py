import os
import sys
import json
import time
from pathlib import Path
import gradio as gr

# Ensure local imports work in Hugging Face Space
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import load_settings, save_settings, OUTPUT_DIR
from pipeline import run_cloud_pipeline
from facebook_publisher import test_page_token, publish_to_all_enabled_pages

def generate_video_action(title, script, voice, image_engine, auto_publish_fb, progress=gr.Progress()):
    if not script.strip():
        return None, "Error: Script / poem text cannot be empty.", ""
        
    title = title.strip() or "Cloud Video"
    
    def on_prog(pct, msg):
        progress(pct / 100.0, desc=msg)
        
    try:
        res = run_cloud_pipeline(
            title=title,
            script_text=script,
            progress_callback=on_prog,
            auto_publish_fb=auto_publish_fb
        )
        video_path = res["output_file"]
        status_msg = f"✅ Video generated successfully in {res['total_render_time_seconds']}s!\nDuration: {res['duration']}s | Scenes: {res['scenes']}"
        
        fb_msg = ""
        if res.get("facebook_published"):
            fb_msg = "\n\n📱 Facebook Publication Results:\n" + json.dumps(res["facebook_published"], indent=2)
            
        return video_path, status_msg + fb_msg, video_path
    except Exception as e:
        return None, f"❌ Generation Failed: {str(e)}", None

def test_fb_token_action(page_id, token):
    if not page_id or not token:
        return "⚠️ Please provide both Page ID and Page Access Token."
    res = test_page_token(page_id.strip(), token.strip())
    if res.get("ok"):
        return f"✅ SUCCESS: Connected to Facebook Page '{res.get('page_name')}' (ID: {res.get('page_id')}, Category: {res.get('category')})"
    else:
        return f"❌ Connection Failed: {res.get('error')}"

def save_fb_settings_action(page_name, page_id, token, as_reel):
    if not page_id or not token:
        return "⚠️ Page ID and Access Token are required."
    cfg = load_settings()
    if not cfg.get("facebook_pages"):
        cfg["facebook_pages"] = []
    
    # Update or add page
    existing = next((p for p in cfg["facebook_pages"] if p.get("id") == page_id.strip()), None)
    if existing:
        existing["name"] = page_name.strip() or existing.get("name", "Facebook Page")
        existing["access_token"] = token.strip()
        existing["as_reel"] = as_reel
    else:
        cfg["facebook_pages"].append({
            "name": page_name.strip() or "Facebook Page",
            "id": page_id.strip(),
            "access_token": token.strip(),
            "enabled": True,
            "as_reel": as_reel
        })
    save_settings(cfg)
    return f"✅ Page '{page_name or page_id}' saved successfully! ({len(cfg['facebook_pages'])} page(s) configured)"

# Build Gradio UI
theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    neutral_hue="slate"
)

with gr.Blocks(theme=theme, title="AI Video Factory & Auto Facebook Publisher") as demo:
    gr.Markdown("""
    # 🎬 Zero-Cost AI Video Studio & Auto Facebook Publisher
    ### Generate 1080x1920 Cinematic Videos with Human Voice Cloning, 2.5D Parallax, and Auto Facebook Distribution
    """)

    with gr.Tabs():
        with gr.TabItem("🎥 Video Generator"):
            with gr.Row():
                with gr.Column(scale=5):
                    title_input = gr.Textbox(
                        label="Video Title",
                        placeholder="e.g. Whispers of the Ancient Mist",
                        value="The Path to Inner Peace"
                    )
                    script_input = gr.Textbox(
                        label="Script / Poem (English or Nepali)",
                        placeholder="Enter or paste your poem / script here...",
                        lines=7,
                        value="Sometimes the best way to heal is to stop giving your energy to what hurt you.\nWalk away. Breathe. Let peace return to your heart.\nEventually, you will realize their actions no longer have the power to disturb your soul.\nYou do not need revenge when you have found peace."
                    )
                    
                    with gr.Row():
                        voice_choice = gr.Dropdown(
                            label="Voice Engine & Narration Style",
                            choices=[
                                ("Human Voice Clone (Whisper Reference - Deep & Warm)", "cloud_cloning"),
                                ("Cloud Voice: English Christopher (Deep Poetic)", "en-US-ChristopherNeural"),
                                ("Cloud Voice: English Guy (Warm & Expressive)", "en-US-GuyNeural"),
                                ("Nepali Voice: Sagar (Male)", "ne-NP-SagarNeural"),
                                ("Nepali Voice: Hemkala (Female)", "ne-NP-HemkalaNeural"),
                                ("ElevenLabs Cloud API", "elevenlabs"),
                                ("Fish Audio Cloud API", "fish_audio")
                            ],
                            value="cloud_cloning"
                        )
                        image_choice = gr.Dropdown(
                            label="Primary Image Generator",
                            choices=[
                                ("Pollinations FLUX (Fast & Free)", "pollinations"),
                                ("Pollinations Turbo (Ultra Fast ~2s)", "pollinations_turbo"),
                                ("Cloudflare Workers AI (10K Neurons/Day)", "cloudflare"),
                                ("Hugging Face Serverless (FLUX.1-schnell)", "huggingface")
                            ],
                            value="pollinations"
                        )
                    
                    auto_fb_check = gr.Checkbox(
                        label="📱 Auto-publish video to configured Facebook Pages upon completion",
                        value=False
                    )
                    
                    generate_btn = gr.Button("🚀 Generate Full Video & Publish", variant="primary", size="lg")

                with gr.Column(scale=5):
                    video_output = gr.Video(label="Generated 1080x1920 Video Output", height=450)
                    status_output = gr.Textbox(label="Status & Production Log", lines=4, interactive=False)
                    download_output = gr.File(label="Download MP4 Video File")

            generate_btn.click(
                fn=generate_video_action,
                inputs=[title_input, script_input, voice_choice, image_choice, auto_fb_check],
                outputs=[video_output, status_output, download_output]
            )

        with gr.TabItem("📱 Facebook Pages Manager"):
            gr.Markdown("""
            ### Connect your Facebook Pages for 1-Click Auto-Publishing
            Requires a **Page Access Token** with `pages_manage_posts`, `pages_read_engagement`, and `pages_show_list`.
            """)
            with gr.Row():
                with gr.Column():
                    fb_page_name = gr.Textbox(label="Page Name / Label", placeholder="e.g. Poetic Horizons")
                    fb_page_id = gr.Textbox(label="Numeric Page ID", placeholder="e.g. 104829381920")
                    fb_token = gr.Textbox(label="Page Access Token (EAA...)", placeholder="Paste token here", type="password")
                    fb_as_reel = gr.Checkbox(label="Publish as Facebook Reel (9:16 Vertical)", value=True)
                    
                    with gr.Row():
                        test_fb_btn = gr.Button("🔍 Test Connection", variant="secondary")
                        save_fb_btn = gr.Button("💾 Save Page Configuration", variant="primary")
                
                with gr.Column():
                    fb_test_result = gr.Textbox(label="Connection Status & Validation Result", lines=6, interactive=False)
                    
            test_fb_btn.click(
                fn=test_fb_token_action,
                inputs=[fb_page_id, fb_token],
                outputs=[fb_test_result]
            )
            save_fb_btn.click(
                fn=save_fb_settings_action,
                inputs=[fb_page_name, fb_page_id, fb_token, fb_as_reel],
                outputs=[fb_test_result]
            )

        with gr.TabItem("🎨 25+ Aesthetic World Showcase"):
            gr.Markdown("""
            ### Built-in Anti-Repetition Fine-Art Worlds Engine
            Every poem generation automatically selects a distinct, non-repeating aesthetic universe:
            * **Ghibli Lush Watercolor**: Mossy shrines, rolling misty meadows, blooming sakura, vibrant hand-painted gouache.
            * **Makoto Shinkai Twilight**: Radiant cumulus clouds, celestial sunset twilight, hyper-detailed lens flares.
            * **Ukiyo-e Woodblock**: Hokusai wave dynamics, muted indigo, sumi-e ink wash, Japanese minimalism.
            * **Bioluminescent Deep Forest**: Glowing spores, luminescent fungi, starry velvet night.
            * **Cyber-Pastel Solitude**: Neon rain reflections, foggy futuristic pagoda, retro-futuristic mood.
            * **Ethereal Astral Void**: Floating stone gateways, nebula starlight, cosmic contemplation.
            """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=8190)

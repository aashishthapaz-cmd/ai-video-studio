import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "cloud_settings.json"
OUTPUT_DIR = PROJECT_ROOT / "Output"
WORKSPACE_DIR = BASE_DIR / "workspaces"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "image_engine_priority": ["huggingface", "cloudflare", "pollinations"],
    "pollinations_model": "flux",
    "voice_engine": "voxcpm_reference",
    "english_voice": "en-US-ChristopherNeural",
    "nepali_voice": "ne-NP-SagarNeural",
    "voice_rate": "-8%",
    "voice_pitch": "-2Hz",
    "output_width": 1080,
    "output_height": 1920,
    "video_transition": "dip_to_black",
    "transition_duration": 0.5,
    "motion_style": "parallax_2_5d",
    "huggingface_token": os.getenv("HF_TOKEN", ""),
    "cloudflare_account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
    "cloudflare_api_token": os.getenv("CLOUDFLARE_API_TOKEN", ""),
    "pollinations_api_key": os.getenv("POLLINATIONS_API_KEY", ""),
    "auto_publish_facebook": False,
    "default_hashtags": "#typewriter #typewritersvoice #poetry #spokenword #healing #mentalhealth #aesthetic #reels #quotes #love",
    "facebook_pages": []
}

def load_settings():
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        return merged
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(data):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

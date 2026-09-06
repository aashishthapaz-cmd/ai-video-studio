import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SETTINGS_FILE = BASE_DIR / "cloud_settings.json"
OUTPUT_DIR = PROJECT_ROOT / "Output"
WORKSPACE_DIR = BASE_DIR / "workspaces"
TEMP_CLOUD_DIR = BASE_DIR / "temp_cloud_store"
JOBS_QUEUE_FILE = BASE_DIR / "jobs_queue.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_CLOUD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "image_engine_priority": ["pollinations", "cloudflare", "huggingface"],
    "pollinations_model": "flux",
    "voice_engine": "voxcpm_reference",
    "reference_voice_path": "assets/reference_voice/whishper.wav",
    "english_voice": "en-US-ChristopherNeural",
    "nepali_voice": "ne-NP-SagarNeural",
    "voice_rate": "-4%",
    "voice_pitch": "+0Hz",
    "output_width": 1080,
    "output_height": 1920,
    "video_transition": "dip_to_black",
    "transition_duration": 0.5,
    "motion_style": "parallax_2_5d",
    "overlay_opacity": 0.15,
    "music_volume": 0.22,
    "huggingface_token": os.getenv("HF_TOKEN", ""),
    "cloudflare_account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
    "cloudflare_api_token": os.getenv("CLOUDFLARE_API_TOKEN", ""),
    "pollinations_api_key": os.getenv("POLLINATIONS_API_KEY", ""),
    "auto_publish_facebook": False,
    "default_hashtags": "#poetry #anime #ghibli #reels #art #aesthetic #nepalipoetry",
    "facebook_pages": [],
    # Notification Settings
    "enable_telegram": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "enable_whatsapp": False,
    "whatsapp_phone": "",
    "whatsapp_apikey": "",
    # Sync Settings
    "cloud_auto_delete_after_sync": True
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

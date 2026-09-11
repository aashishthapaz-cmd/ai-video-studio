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

# Auto-load .env from project root or base dir
for env_candidate in [PROJECT_ROOT / ".env", BASE_DIR / ".env"]:
    if env_candidate.is_file():
        try:
            for line in env_candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_CLOUD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    "image_engine_priority": ["puter", "huggingface", "cloudflare", "pollinations"],
    "pollinations_model": "flux",
    "puter_model": "gemini-3.1-flash-image-preview",
    "puter_auth_token": os.getenv("PUTER_AUTH_TOKEN", ""),
    "voice_engine": "voxcpm_reference",
    "reference_voice_path": "assets/reference_voice/whishper.wav",
    "english_voice": "en-US-ChristopherNeural",
    "nepali_voice": "ne-NP-SagarNeural",
    "default_vibe": "typewriters_voice_nostalgia",
    "voice_rate": "-8%",
    "voice_pitch": "-2Hz",
    "output_width": 1080,
    "output_height": 1920,
    "video_transition": "dip_to_black",
    "transition_duration": 0.5,
    "motion_style": "parallax_2_5d",
    "overlay_opacity": 0.15,
    "music_volume": 0.48,
    "huggingface_token": os.getenv("HF_TOKEN", ""),
    "cloudflare_account_id": os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
    "cloudflare_api_token": os.getenv("CLOUDFLARE_API_TOKEN", ""),
    "pollinations_api_key": os.getenv("POLLINATIONS_API_KEY", ""),
    "auto_publish_facebook": False,
    "default_hashtags": "#typewriter #typewritersvoice #poetry #spokenword #healing #mentalhealth #aesthetic #reels #quotes #love",
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
    merged = DEFAULT_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged.update(data)
        except Exception:
            pass

    # Secure GitHub Secrets & Environment Variable Overrides
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        merged["telegram_bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
        merged["enable_telegram"] = True
    if os.getenv("TELEGRAM_CHAT_ID"):
        merged["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("HF_TOKEN"):
        merged["huggingface_token"] = os.getenv("HF_TOKEN")
    if os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        merged["cloudflare_account_id"] = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if os.getenv("CLOUDFLARE_API_TOKEN"):
        merged["cloudflare_api_token"] = os.getenv("CLOUDFLARE_API_TOKEN")
    if os.getenv("POLLINATIONS_API_KEY"):
        merged["pollinations_api_key"] = os.getenv("POLLINATIONS_API_KEY")
    if os.getenv("PUTER_AUTH_TOKEN"):
        merged["puter_auth_token"] = os.getenv("PUTER_AUTH_TOKEN")
    if os.getenv("PUTER_MODEL"):
        merged["puter_model"] = os.getenv("PUTER_MODEL")
    if os.getenv("FACEBOOK_PAGES_JSON"):
        try:
            pages = json.loads(os.getenv("FACEBOOK_PAGES_JSON"))
            if isinstance(pages, list):
                # Filter out placeholder/dummy entries
                real_pages = [
                    p for p in pages
                    if p.get("page_id") and "YOUR_" not in str(p.get("page_id", ""))
                    and p.get("access_token") and "YOUR_" not in str(p.get("access_token", ""))
                ]
                merged["facebook_pages"] = real_pages
                if real_pages:
                    merged["auto_publish_facebook"] = True
        except Exception:
            pass

    return merged

def save_settings(data):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

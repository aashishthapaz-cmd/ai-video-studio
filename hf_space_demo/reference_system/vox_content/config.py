from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT / "projects"
OUTPUTS_DIR = ROOT / "outputs"
ASSETS_DIR = ROOT / "assets"
LOGS_DIR = ROOT / "logs"
QUEUE_DIR = ROOT / "queue"

load_dotenv(ROOT / ".env")


class Settings:
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "auto")
    artwork_prompt_model: str = os.getenv("ARTWORK_PROMPT_MODEL", "auto")
    artwork_prompt_model_order: str = os.getenv(
        "ARTWORK_PROMPT_MODEL_ORDER",
        "gemma3:4b,gemma2:9b,gemma2:2b,gemma:7b,qwen3:8b,qwen2.5:7b,qwen2.5:3b,deepseek-r1:8b,deepseek-r1:7b,llama3.1:8b,dolphin3.0",
    )
    voxcpm_model: str = os.getenv("VOXCPM_MODEL", "openbmb/VoxCPM2")
    voxcpm_device: str = os.getenv("VOXCPM_DEVICE", "cuda")
    voxcpm_reference_audio: str = os.getenv("VOXCPM_REFERENCE_AUDIO", "")
    voxcpm_reference_text: str = os.getenv("VOXCPM_REFERENCE_TEXT", "")
    voxcpm_pause_style: str = os.getenv("VOXCPM_PAUSE_STYLE", "poetry")
    voxcpm_timeout_seconds: int = int(os.getenv("VOXCPM_TIMEOUT_SECONDS", "420"))
    voxcpm_cfg_value: float = float(os.getenv("VOXCPM_CFG_VALUE", "2.0"))
    voxcpm_inference_timesteps: int = int(os.getenv("VOXCPM_INFERENCE_TIMESTEPS", "14"))
    voxcpm_postprocess_voice: bool = os.getenv("VOXCPM_POSTPROCESS_VOICE", "1").strip().lower() not in {"0", "false", "no", "off"}
    voice_engine: str = os.getenv("VOICE_ENGINE", "auto")
    chatterbox_python: str = os.getenv("CHATTERBOX_PYTHON", str(ROOT / "engines" / "chatterbox" / ".venv" / "Scripts" / "python.exe"))
    parler_model: str = os.getenv("PARLER_MODEL", "ai4bharat/indic-parler-tts")
    parler_description: str = os.getenv(
        "PARLER_DESCRIPTION",
        "A native Nepali documentary narrator speaks in a warm, clear, grounded human voice. "
        "The delivery is conversational and natural at a measured pace, with short realistic breaths, "
        "clean Devanagari pronunciation, subtle emphasis on important words, gentle pitch movement, "
        "and medium pauses at commas and sentence endings. Do not sing, chant, or sound like poetry; "
        "do not use long empty pauses, clipped words, or a robotic announcer tone.",
    )
    parler_timeout_seconds: int = int(os.getenv("PARLER_TIMEOUT_SECONDS", "900"))
    parler_quality: str = os.getenv("PARLER_QUALITY", "best")
    chatterbox_nepali_repo: str = os.getenv("CHATTERBOX_NEPALI_REPO", "officialuser/chatterbox-nepali")
    chatterbox_nepali_weights: str = os.getenv("CHATTERBOX_NEPALI_WEIGHTS", "t3_nepali_epoch_20.pt")
    chatterbox_nepali_exaggeration: float = float(os.getenv("CHATTERBOX_NEPALI_EXAGGERATION", "0.72"))
    chatterbox_nepali_temperature: float = float(os.getenv("CHATTERBOX_NEPALI_TEMPERATURE", "0.58"))
    chatterbox_nepali_cfg_weight: float = float(os.getenv("CHATTERBOX_NEPALI_CFG_WEIGHT", "0.34"))
    chatterbox_nepali_timeout_seconds: int = int(os.getenv("CHATTERBOX_NEPALI_TIMEOUT_SECONDS", "1200"))
    audio_format: str = os.getenv("AUDIO_FORMAT", "wav")
    audio_sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "48000"))
    audio_loudness: float = float(os.getenv("AUDIO_LOUDNESS", "-16.0"))
    audio_speed: float = float(os.getenv("AUDIO_SPEED", "1.0"))
    audio_target_wpm: float = float(os.getenv("AUDIO_TARGET_WPM", "99.2"))
    audio_match_reference_pacing: bool = os.getenv("AUDIO_MATCH_REFERENCE_PACING", "1").strip().lower() not in {"0", "false", "no", "off"}
    prosody_style: str = os.getenv("PROSODY_STYLE", "reference_documentary")
    prosody_breaths: bool = os.getenv("PROSODY_BREATHS", "1").strip().lower() not in {"0", "false", "no", "off"}
    prosody_dramatic_emphasis: bool = os.getenv("PROSODY_DRAMATIC_EMPHASIS", "1").strip().lower() not in {"0", "false", "no", "off"}
    prosody_variation: float = float(os.getenv("PROSODY_VARIATION", "0.10"))
    audio_trim_silence: bool = os.getenv("AUDIO_TRIM_SILENCE", "0").strip().lower() in {"1", "true", "yes", "on"}
    default_overlay_path: str = os.getenv("DEFAULT_OVERLAY_PATH", str(ASSETS_DIR / "overlays" / "default_overlay.mp4"))
    default_overlay_opacity: float = float(os.getenv("DEFAULT_OVERLAY_OPACITY", "0.35"))
    default_music_path: str = os.getenv("DEFAULT_MUSIC_PATH", "")
    default_music_volume: float = float(os.getenv("DEFAULT_MUSIC_VOLUME", "0.16"))
    default_music_fade_seconds: float = float(os.getenv("DEFAULT_MUSIC_FADE_SECONDS", "2.5"))
    default_motion_style: str = os.getenv("DEFAULT_MOTION_STYLE", "parallax_2_5d")
    cleanup_on_startup: bool = os.getenv("CLEANUP_ON_STARTUP", "1").strip().lower() not in {"0", "false", "no", "off"}
    cleanup_project_hours: int = int(os.getenv("CLEANUP_PROJECT_HOURS", "12"))
    cleanup_log_days: int = int(os.getenv("CLEANUP_LOG_DAYS", "30"))
    render_encoder: str = os.getenv("RENDER_ENCODER", "auto")
    render_background_priority: bool = os.getenv("RENDER_BACKGROUND_PRIORITY", "1").strip().lower() not in {"0", "false", "no", "off"}
    render_threads: int = int(os.getenv("RENDER_THREADS", "4"))
    render_grain: bool = os.getenv("RENDER_GRAIN", "0").strip().lower() in {"1", "true", "yes", "on"}
    render_timeout_seconds: int = int(os.getenv("RENDER_TIMEOUT_SECONDS", "900"))
    pixabay_api_key: str = os.getenv("PIXABAY_API_KEY", "")
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "")


settings = Settings()

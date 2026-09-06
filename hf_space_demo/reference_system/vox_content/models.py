from pathlib import Path

from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    topic: str = Field(min_length=2)
    style: str = "cinematic educational short"
    duration_seconds: int = Field(default=0, ge=0, le=0)
    image_count: int = Field(default=0, ge=0, le=24)
    platform: str = "shorts"
    video_format: str = "portrait"
    preset: str = "poetry_reference"
    caption_mode: str = "audio_timed"
    caption_style: str = "karaoke_line"
    signature_enabled: bool = True
    signature_text: str = "@whispers"
    output_mode: str = "audio"
    narration_text: str = ""
    auto_images: bool = True
    image_kind: str = "poems"
    image_folder: str = ""
    voice_engine: str = "auto"
    voice_style: str = "poetry"
    reference_audio: str = ""
    overlay_path: str = ""
    overlay_opacity: float = Field(default=0.35, ge=0.0, le=1.0)
    music_path: str = ""
    music_volume: float = Field(default=0.16, ge=0.0, le=1.0)
    music_fade_seconds: float = Field(default=2.5, ge=0.0, le=10.0)
    motion_style: str = "parallax_2_5d"
    audio_format: str = "wav"
    audio_sample_rate: int = Field(default=48000, ge=16000, le=96000)
    audio_loudness: float = Field(default=-16.0, ge=-24.0, le=-9.0)
    audio_speed: float = Field(default=1.0, ge=0.75, le=1.25)
    audio_target_wpm: float = Field(default=99.2, ge=60.0, le=160.0)
    audio_match_reference_pacing: bool = True
    prosody_style: str = "reference_documentary"
    prosody_breaths: bool = True
    prosody_dramatic_emphasis: bool = True
    prosody_variation: float = Field(default=0.10, ge=0.0, le=0.35)
    audio_trim_silence: bool = False


class ScriptPlan(BaseModel):
    title: str
    hook: str
    narration: str
    visual_queries: list[str]
    caption_phrases: list[str]
    description: str
    tags: list[str]


class VisualAsset(BaseModel):
    path: Path
    source_url: str = ""
    credit: str = ""


class ProjectResult(BaseModel):
    project_dir: Path
    final_video: Path | None = None
    final_audio: Path | None = None
    voiceover: Path | None = None
    script_json: Path | None = None
    captions: Path | None = None
    metadata: Path | None = None
    assets: list[VisualAsset]
    output_kind: str = "poems"
    audio_duration_seconds: float = 0.0
    audio_format: str = "wav"
    audio_sample_rate: int = 48000
    engine: str = ""

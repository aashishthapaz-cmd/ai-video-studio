from __future__ import annotations

from pathlib import Path
from secrets import SystemRandom

from .config import ASSETS_DIR


OVERLAY_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def media_folder(content_kind: str, media_type: str) -> Path:
    kind = "motivation" if content_kind == "motivation" else "poems"
    return ASSETS_DIR / kind / media_type


def random_overlay(content_kind: str) -> Path | None:
    return _random_file(media_folder(content_kind, "overlays"), OVERLAY_EXTENSIONS)


def random_music(content_kind: str) -> Path | None:
    return _random_file(media_folder(content_kind, "music"), MUSIC_EXTENSIONS)


def resolve_overlay(value: str, content_kind: str) -> Path | None:
    value = value.strip()
    if not value or value.lower() == "auto":
        return random_overlay(content_kind)
    path = Path(value)
    return path if path.exists() else None


def resolve_music(value: str, content_kind: str) -> Path | None:
    value = value.strip()
    if not value or value.lower() == "auto":
        return random_music(content_kind)
    path = Path(value)
    return path if path.exists() else None


def _random_file(folder: Path, extensions: set[str]) -> Path | None:
    if not folder.exists():
        return None
    files = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in extensions]
    if not files:
        return None
    return SystemRandom().choice(files)

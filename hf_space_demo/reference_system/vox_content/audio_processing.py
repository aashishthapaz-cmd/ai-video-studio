from __future__ import annotations

from pathlib import Path
import json
import re
import subprocess
import wave

from .voice_voxcpm import _background_creationflags


SUPPORTED_FORMATS = {"wav", "flac", "mp3"}


def finalize_audio(
    source: Path,
    destination: Path,
    *,
    sample_rate: int = 48000,
    loudness: float = -16.0,
    speed: float = 1.0,
    trim_silence: bool = False,
) -> Path:
    """Master a generated voice track without changing its natural pitch.

    The neural model remains responsible for expressiveness and pronunciation;
    this stage only performs transparent cleanup, loudness normalization, safe
    peak limiting, optional pitch-preserving speed adjustment, and delivery
    encoding.
    """
    if not source.exists():
        raise FileNotFoundError(f"Generated source audio is missing: {source}")
    fmt = destination.suffix.lower().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported audio format: {fmt or 'none'}. Use WAV, FLAC, or MP3.")
    if not 16000 <= int(sample_rate) <= 96000:
        raise ValueError("Audio sample rate must be between 16,000 and 96,000 Hz.")
    if not 0.75 <= float(speed) <= 1.25:
        raise ValueError("Audio speed must be between 0.75x and 1.25x.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    filters = ["highpass=f=65", "lowpass=f=16000"]
    if trim_silence:
        filters.append(
            "silenceremove=start_periods=1:start_duration=0.08:start_threshold=-50dB:"
            "stop_periods=1:stop_duration=0.20:stop_threshold=-50dB"
        )
    if abs(float(speed) - 1.0) > 0.001:
        filters.extend(_atempo_filters(float(speed)))
    filters.extend([f"loudnorm=I={float(loudness):.1f}:TP=-1.5:LRA=11", "alimiter=limit=0.95"])

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-af",
        ",".join(filters),
        "-ar",
        str(int(sample_rate)),
        "-ac",
        "1",
    ]
    if fmt == "wav":
        command.extend(["-c:a", "pcm_s24le"])
    elif fmt == "flac":
        command.extend(["-c:a", "flac", "-compression_level", "8"])
    else:
        command.extend(["-c:a", "libmp3lame", "-b:a", "320k", "-write_xing", "1"])
    command.append(str(destination))

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        creationflags=_background_creationflags(),
    )
    if completed.returncode != 0 or not destination.exists() or destination.stat().st_size < 1024:
        detail = (completed.stderr or completed.stdout or "FFmpeg failed to master the audio.").strip()
        raise RuntimeError(detail[-1600:])
    return destination


def audio_duration_seconds(path: Path) -> float:
    """Return duration for PCM WAV files, with ffprobe fallback for other formats."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                return round(handle.getnframes() / float(handle.getframerate()), 3)
        except (OSError, wave.Error):
            pass
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=_background_creationflags(),
    )
    try:
        return round(float(completed.stdout.strip()), 3)
    except (TypeError, ValueError):
        return 0.0


def nepali_word_count(text: str) -> int:
    return len(re.findall(r"[\w\u0900-\u097f]+", text, flags=re.UNICODE))


def speed_for_target_wpm(text: str, duration_seconds: float, target_wpm: float) -> float:
    """Return a safe pitch-preserving speed multiplier for reference pacing."""
    if duration_seconds <= 0 or target_wpm <= 0:
        return 1.0
    current_wpm = nepali_word_count(text) / duration_seconds * 60.0
    if current_wpm <= 0:
        return 1.0
    # atempo > 1.0 makes speech faster; to reach target WPM, use target/current.
    return max(0.75, min(1.25, float(target_wpm) / current_wpm))


def write_audio_manifest(path: Path, *, text: str, output: Path, engine: str, sample_rate: int, loudness: float, speed: float, duration: float, target_wpm: float = 0.0) -> Path:
    manifest = path.with_suffix(".json")
    manifest.write_text(
        json.dumps(
            {
                "text": text,
                "output": str(output),
                "engine": engine,
                "sample_rate_hz": int(sample_rate),
                "target_loudness_lufs": float(loudness),
                "speed": float(speed),
                "target_reference_wpm": float(target_wpm),
                "duration_seconds": float(duration),
                "open_source_pipeline": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def _atempo_filters(speed: float) -> list[str]:
    # FFmpeg accepts 0.5..2.0 per atempo filter; one filter is enough for the UI range.
    return [f"atempo={speed:.3f}"]

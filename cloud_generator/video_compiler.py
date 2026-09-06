import os
import re
import sys
import shutil
import subprocess
from pathlib import Path
try:
    from .config import load_settings, OUTPUT_DIR, PROJECT_ROOT
except ImportError:
    from config import load_settings, OUTPUT_DIR, PROJECT_ROOT

# Insert reference_system to sys.path
sys.path.insert(0, str(PROJECT_ROOT / "reference_system"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "reference_system"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference_system"))
from vox_content.models import VisualAsset
from vox_content.render import render as reference_render
from vox_content.captions import TimedCaption, write_timed_ass

def run_cmd(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)

def sanitize_title(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(title or 'untitled_video'))
    safe = re.sub(r'\s+', ' ', safe).strip(' .')
    return safe or 'cloud_video'

def audio_fx_filter():
    """Warm acoustic broadcast mastering for poetic human voice."""
    return (
        "highpass=f=45,"
        "lowpass=f=16000,"
        "equalizer=f=200:t=q:w=1.0:g=1.0,"
        "equalizer=f=5500:t=q:w=1.5:g=-1.8,"
        "acompressor=threshold=0.25:ratio=1.35:attack=25:release=220:makeup=1.05,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )

def master_audio_file(source_audio: Path, target_audio: Path) -> Path:
    """Applies acoustic mastering to narration audio."""
    target_audio.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_audio),
        "-af", audio_fx_filter(),
        "-ar", "48000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(target_audio)
    ]
    r = run_cmd(cmd)
    return target_audio if r.returncode == 0 and target_audio.exists() else source_audio

def compile_cloud_video(scenes: list, title: str, workspace_dir: Path, captions_file: Path = None) -> dict:
    """
    Renders the exact production video matching the reference system:
    1. 2.5D Quintic Smootherstep Parallax Animation
    2. Video Dust & Grain Overlay (default_overlay.mp4 at 0.15 opacity)
    3. Whisper Background Music (at 0.22 volume with 3s fade)
    4. Film Grain, Vignette, and Color Grading
    5. Cursive Poetic Subtitle Typography
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Identify Master Audio & Exact Per-Scene Durations
    audio_files = [Path(s["audio_path"]) for s in scenes if "audio_path" in s and Path(s["audio_path"]).exists()]
    if not audio_files:
        raise FileNotFoundError("No audio files found for scenes.")
        
    master_raw = audio_files[0]
    if len(audio_files) > 1 and not (workspace_dir / "narration.wav").exists():
        master_raw = workspace_dir / "master_raw.wav"
        concat_file = workspace_dir / "audio_concat.txt"
        concat_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in audio_files), encoding="utf-8")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(master_raw)]
        run_cmd(cmd)
    elif (workspace_dir / "audio" / "narration.wav").exists():
        master_raw = workspace_dir / "audio" / "narration.wav"
    elif (workspace_dir / "narration.wav").exists():
        master_raw = workspace_dir / "narration.wav"
        
    master_audio = master_audio_file(master_raw, workspace_dir / "narration_mastered.wav")

    # 2. Extract Assets & Measured Durations
    assets = [VisualAsset(path=Path(s["image_path"])) for s in scenes if "image_path" in s and Path(s["image_path"]).exists()]
    
    # Measure exact duration from individual audio files to eliminate any drift
    durations = []
    for s in scenes:
        audio_p = Path(s.get("audio_path", ""))
        if audio_p.exists():
            try:
                res = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(audio_p)],
                    capture_output=True, text=True, check=True
                )
                durations.append(max(1.5, float(res.stdout.strip())))
            except Exception:
                durations.append(float(s.get("duration", 4.5)))
        else:
            durations.append(float(s.get("duration", 4.5)))
    
    if not assets:
        raise FileNotFoundError("No image assets found to render video.")
        
    total_dur = sum(durations)
    
    # 3. Generate Timed Cursive Poetic Captions (Exact Timing with Fading)
    if not captions_file or not captions_file.exists():
        captions_file = workspace_dir / "captions.ass"
        rows = []
        curr_t = 0.0
        for s, dur in zip(scenes, durations):
            text = str(s.get("narration", "")).strip()
            if text:
                sub_end = curr_t + dur - 0.04
                word_durs = tuple(s.get("word_durations", ()))
                rows.append(TimedCaption(curr_t, sub_end, text, word_durations=word_durs))
            curr_t += dur
            
        write_timed_ass(
            captions=rows,
            output=captions_file,
            preset="poetry_reference",
            caption_style="reference_cursive",
            video_format="portrait",
            signature_enabled=False
        )

    # 4. Reference Overlay & Ambient Music Assets
    overlay_path = None
    default_ov = PROJECT_ROOT / "assets" / "overlays" / "default_overlay.mp4"
    if default_ov.is_file():
        overlay_path = default_ov
    else:
        ov_dir = PROJECT_ROOT / "assets" / "overlays"
        if ov_dir.exists():
            files = sorted(p for p in ov_dir.glob("*") if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".webm"})
            if files:
                overlay_path = files[0]

    music_path = None
    default_music = PROJECT_ROOT / "assets" / "Whispr Bg music" / "audio [music] whisper background music.mp3"
    if default_music.is_file():
        music_path = default_music
    else:
        music_dir = PROJECT_ROOT / "assets" / "Whispr Bg music"
        if music_dir.exists():
            files = sorted(p for p in music_dir.glob("*") if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"})
            if files:
                music_path = files[0]

    final_output_name = sanitize_title(title) + ".mp4"
    final_output = OUTPUT_DIR / final_output_name
    workspace_output = workspace_dir / "final_reference_render.mp4"

    # 5. Execute Exact Reference 2.5D Parallax Render
    rendered = reference_render(
        assets=assets,
        audio=master_audio,
        captions=captions_file,
        output=workspace_output,
        target_duration=total_dur,
        preset="poetry_reference",
        scene_durations=durations,
        video_format="portrait",
        overlay_path=overlay_path,
        overlay_opacity=0.15 if overlay_path else 0.0,
        music_path=music_path,
        music_volume=0.22 if music_path else 0.0,
        music_fade_seconds=3.0,
        motion_style="parallax_2_5d"
    )

    shutil.copy2(str(rendered), str(final_output))
    return {
        "ok": True,
        "output": str(final_output),
        "workspace_output": str(rendered),
        "scenes_rendered": len(assets),
        "duration": round(total_dur, 2),
        "renderer": "Exact 2.5D Parallax Reference Engine"
    }

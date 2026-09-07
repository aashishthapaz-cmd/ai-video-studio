from __future__ import annotations

from pathlib import Path
import json
import random
import re
import shutil
import subprocess

from .config import ASSETS_DIR, settings
from .layout import frame_size
from .models import VisualAsset

END_FADE_SECONDS = 3.0


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
        creationflags=_background_creationflags(),
    )
    return max(1.0, float(result.stdout.strip()))


def render(
    assets: list[VisualAsset],
    audio: Path,
    captions: Path,
    output: Path,
    target_duration: float | None = None,
    preset: str = "modern",
    scene_durations: list[float] | None = None,
    video_format: str = "portrait",
    overlay_path: Path | None = None,
    overlay_opacity: float = 0.0,
    music_path: Path | None = None,
    music_volume: float = 0.0,
    music_fade_seconds: float = 2.5,
    motion_style: str = "ken_burns",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    narration_total = duration(audio)
    total = narration_total + END_FADE_SECONDS
    clips = []
    duration_scale = 1.0
    if scene_durations:
        requested_total = sum(max(0.01, float(value)) for value in scene_durations[:len(assets)])
        duration_scale = narration_total / requested_total if requested_total > 0 else 1.0
    clip_tasks = []
    for index, asset in enumerate(assets, start=1):
        clip = output.parent / f"clip_{index}.mp4"
        if scene_durations and index - 1 < len(scene_durations):
            seconds = max(0.25, float(scene_durations[index - 1]) * duration_scale)
            if index == len(assets):
                seconds += END_FADE_SECONDS
        else:
            seconds = total / max(1, len(assets))
        clip_tasks.append((asset.path, clip, max(1.0, seconds), preset, index, video_format, motion_style))
        clips.append(clip)

    import concurrent.futures
    def _render_task(t):
        img_p, clp_p, sec, pr, var, vf, mot = t
        _clip(img_p, clp_p, sec, preset=pr, variant=var, video_format=vf, motion_style=mot)
        return clp_p

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(clip_tasks)))) as executor:
        list(executor.map(_render_task, clip_tasks))

    concat = output.parent / "concat.txt"
    concat.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    cap = str(captions).replace("\\", "/").replace(":", "\\:")
    native_captions = _native_caption_items(captions)
    overlay = overlay_path if overlay_path and overlay_path.exists() and overlay_opacity > 0 else None
    music = music_path if music_path and music_path.exists() and music_volume > 0 else None
    if music:
        music = _trim_starting_silence(music, output.parent)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-i",
        str(audio),
    ]
    if overlay:
        command.extend(["-stream_loop", "-1", "-i", str(overlay)])
    if music:
        command.extend(["-stream_loop", "-1", "-i", str(music)])
    for item in native_captions:
        command.extend(["-loop", "1", "-i", item["image"]])

    if overlay or music or native_captions:
        command.extend(
            [
                "-filter_complex",
                _filter_complex(
                    cap,
                    preset,
                    overlay_opacity,
                    narration_total,
                    total,
                    music_volume,
                    music_fade_seconds,
                    video_format,
                    has_overlay=bool(overlay),
                    has_music=bool(music),
                    native_captions=native_captions,
                ),
            ]
        )
        video_map = "[vout]"
        audio_map = "[aout]"
    else:
        command.extend(["-vf", _video_filter(cap, preset, narration_total, total)])
        video_map = "0:v:0"
        audio_map = "1:a:0"
    command.extend(
        [
            "-map",
            video_map,
            "-map",
            audio_map,
            *_video_encoder_args(),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-t",
            f"{total:.2f}",
            str(output),
        ]
    )
    completed = _run_background(command, timeout=_render_timeout(total))
    if completed.returncode != 0:
        if _valid_video(output):
            _cleanup_render_temps(clips, concat, captions)
            return output
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Final render failed: {detail[-1200:]}")
    _cleanup_render_temps(clips, concat, captions)
    return output


def _video_filter(captions_path: str, preset: str, narration_total: float, total: float) -> str:
    subtitles = _subtitles_filter(captions_path)
    fade = _video_fade_filter(narration_total, total)
    if preset == "poetry_reference":
        return (
            f"{_grain_filter(12)}"
            "eq=contrast=1.02:saturation=0.92:brightness=-0.01:gamma=1.02,"
            f"{subtitles},"
            f"{fade}"
        )
    return (
        f"{_grain_filter(9)}"
        "eq=contrast=1.05:saturation=0.92:brightness=-0.01,"
        f"{subtitles},"
        f"{fade}"
    )


def _video_filter_complex(captions_path: str, preset: str, overlay_opacity: float) -> str:
    return _filter_complex(
        captions_path,
        preset,
        overlay_opacity,
        narration_total=1.0,
        total=1.0,
        music_volume=0.0,
        music_fade_seconds=0.0,
        video_format="portrait",
        has_overlay=True,
        has_music=False,
    )


def _filter_complex(
    captions_path: str,
    preset: str,
    overlay_opacity: float,
    narration_total: float,
    total: float,
    music_volume: float,
    music_fade_seconds: float,
    video_format: str,
    has_overlay: bool,
    has_music: bool,
    native_captions: list[dict] | None = None,
) -> str:
    opacity = max(0.0, min(1.0, overlay_opacity))
    width, height = frame_size(video_format)
    base = _base_grade(preset)
    video_fade = _video_fade_filter(narration_total, total)
    parts = [f"[0:v]{base}[base]"]
    video_in = "[base]"
    if has_overlay:
        parts.append(
            f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"format=rgba,colorchannelmixer=aa={opacity:.3f}[ov]"
        )
        parts.append(f"{video_in}[ov]overlay=0:0:shortest=0[vblend]")
        video_in = "[vblend]"
    parts.append(f"{video_in}{_subtitles_filter(captions_path)}[subbed]")
    video_in = "[subbed]"
    native_captions = native_captions or []
    native_start_index = 2 + int(has_overlay) + int(has_music)
    for index, item in enumerate(native_captions):
        input_index = native_start_index + index
        label = f"[native{index}]"
        start = float(item["start"])
        end = float(item["end"])
        parts.append(
            f"{video_in}[{input_index}:v]overlay=0:0:format=auto:enable='between(t,{start:.3f},{end:.3f})'{label}"
        )
        video_in = label
    parts.append(f"{video_in}{video_fade}[vout]")

    parts.append(f"[1:a]atrim=0:{narration_total:.3f},asetpts=PTS-STARTPTS[narr]")
    if has_music:
        music_index = 3 if has_overlay else 2
        volume = max(0.0, min(1.0, music_volume))
        music_chain = f"[{music_index}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={volume:.3f}"
        music_tail = max(0.0, total - narration_total)
        if music_tail > 0:
            music_chain += f",afade=t=out:st={narration_total:.3f}:d={music_tail:.3f}"
        music_chain += "[music]"
        parts.append(music_chain)
        parts.append("[narr][music]amix=inputs=2:duration=longest:dropout_transition=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[aout]")
    else:
        parts.append("[narr]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[aout]")
    return ";".join(parts)


def _native_caption_items(captions: Path) -> list[dict]:
    manifest = captions.with_suffix(".native_nepali.json")
    if not manifest.exists():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        items = []
        for item in data.get("items", []):
            image = Path(str(item.get("image", "")))
            if image.exists():
                items.append({"image": str(image), "start": float(item["start"]), "end": float(item["end"])})
        return items
    except Exception:
        return []


def _cleanup_render_temps(clips: list[Path], concat: Path, captions: Path) -> None:
    for clip in clips:
        clip.unlink(missing_ok=True)
    concat.unlink(missing_ok=True)
    native_manifest = captions.with_suffix(".native_nepali.json")
    native_dir = captions.with_suffix("").parent / f"{captions.stem}_native_nepali"
    native_manifest.unlink(missing_ok=True)
    if native_dir.exists():
        shutil.rmtree(native_dir, ignore_errors=True)
    for path in captions.parent.glob("music_trimmed_*.wav"):
        path.unlink(missing_ok=True)
    for path in captions.parent.glob("parallax_*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def _subtitles_filter(captions_path: str) -> str:
    fonts_dir = str(ASSETS_DIR / "fonts").replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{captions_path}':fontsdir='{fonts_dir}'"


def _base_grade(preset: str) -> str:
    if preset == "poetry_reference":
        return f"{_grain_filter(12)}eq=contrast=1.02:saturation=0.92:brightness=-0.01:gamma=1.02"
    return f"{_grain_filter(9)}eq=contrast=1.05:saturation=0.92:brightness=-0.01"


def _grain_filter(strength: int) -> str:
    if not settings.render_grain:
        return ""
    return f"noise=alls={strength}:allf=t+u,"


def _video_fade_filter(narration_total: float, total: float) -> str:
    # Video and music begin fading together immediately after narration ends.
    # The final video tail remains visible long enough for both fades to finish.
    fade_start = max(0.0, narration_total)
    fade = max(0.0, total - fade_start)
    return f"fade=t=out:st={fade_start:.3f}:d={fade:.3f}"


def _trim_starting_silence(source: Path, work_dir: Path) -> Path:
    offset = _detect_leading_silence(source)
    if offset < 0.12:
        return source
    target = work_dir / f"music_trimmed_{source.stem[:36]}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{offset:.3f}",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    completed = _run_background(command)
    if completed.returncode != 0 or not target.exists():
        return source
    return target


def _detect_leading_silence(source: Path) -> float:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(source),
        "-af",
        "silencedetect=noise=-50dB:d=0.12",
        "-f",
        "null",
        "-",
    ]
    completed = _run_background(command)
    log = f"{completed.stderr or ''}\n{completed.stdout or ''}"
    start_match = re.search(r"silence_start:\s*([0-9.]+)", log)
    if not start_match:
        return 0.0
    try:
        silence_start = float(start_match.group(1))
    except ValueError:
        return 0.0
    if silence_start > 0.05:
        return 0.0
    end_match = re.search(r"silence_end:\s*([0-9.]+)", log)
    if not end_match:
        return 0.0
    try:
        return max(0.0, float(end_match.group(1)))
    except ValueError:
        return 0.0


def _valid_video(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_background_creationflags(),
        )
        return completed.returncode == 0 and float(completed.stdout.strip() or "0") > 0.5
    except Exception:
        return False


def _clip(
    image: Path,
    output: Path,
    seconds: float,
    preset: str = "modern",
    variant: int = 1,
    video_format: str = "portrait",
    motion_style: str = "ken_burns",
) -> None:
    style = (motion_style or "ken_burns").strip().lower()
    if style in {"parallax", "parallax_2_5d", "2.5d", "2_5d"}:
        try:
            return _clip_parallax(image, output, seconds, preset=preset, variant=variant, video_format=video_format)
        except Exception:
            # If a particular image cannot be separated safely, keep the batch moving.
            return _clip_ken_burns(image, output, seconds, preset=preset, variant=variant, video_format=video_format)
    return _clip_ken_burns(image, output, seconds, preset=preset, variant=variant, video_format=video_format)


def _clip_ken_burns(image: Path, output: Path, seconds: float, preset: str = "modern", variant: int = 1, video_format: str = "portrait") -> None:
    width, height = frame_size(video_format)
    canvas_w = max(width + 180, int(width * 1.16))
    canvas_h = max(height + 180, int(height * 1.16))
    zoom = _motion_filter(image, seconds, preset, variant, video_format)
    # Cinematic 0.5s dip-to-black transition: 0.25s fade-in from black at start, 0.25s fade-out to black at end
    fade_out_st = max(0.0, seconds - 0.25)
    fade_filter = f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out_st:.3f}:d=0.25"
    command = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            f"{seconds:.2f}",
            "-i",
            str(image),
            "-vf",
            f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},{zoom},{fade_filter},setsar=1,trim=duration={seconds:.2f},setpts=PTS-STARTPTS",
            "-an",
            *_video_encoder_args(intermediate=True),
            "-pix_fmt",
            "yuv420p",
            str(output),
    ]
    completed = _run_background(command)
    if completed.returncode != 0:
        fallback_cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            f"{seconds:.2f}",
            "-i",
            str(image),
            "-vf",
            f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},{zoom},{fade_filter},setsar=1,trim=duration={seconds:.2f},setpts=PTS-STARTPTS",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
        completed = _run_background(fallback_cmd)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Scene motion render failed for {image.name}: {detail[-1200:]}")


def _clip_parallax(image: Path, output: Path, seconds: float, preset: str = "modern", variant: int = 1, video_format: str = "portrait") -> None:
    width, height = frame_size(video_format)
    bg, fg = _parallax_layers(image, output.parent, width, height, variant)
    bg_motion = _motion_filter(bg, seconds, preset, variant * 10 + 1, video_format, max_zoom=1.038 if preset == "poetry_reference" else 1.032)
    rng = random.Random(f"parallax-{image.resolve()}-{variant}")
    seconds = max(1.0, seconds)
    travel_x = int(width * rng.choice([-0.018, -0.014, 0.014, 0.018]))
    travel_y = int(height * rng.choice([-0.012, -0.009, 0.009, 0.012]))
    start_x = -travel_x
    start_y = -travel_y
    parallax_progress = f"(t/{seconds:.3f})"
    parallax_eased = f"(({parallax_progress})*({parallax_progress})*({parallax_progress})*(({parallax_progress})*(({parallax_progress})*6-15)+10))"
    overlay_x = f"{start_x}+({travel_x - start_x})*{parallax_eased}"
    overlay_y = f"{start_y}+({travel_y - start_y})*{parallax_eased}"
    # Cinematic 0.5s dip-to-black transition
    fade_out_st = max(0.0, seconds - 0.25)
    fade_filter = f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out_st:.3f}:d=0.25"
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        f"{seconds:.2f}",
        "-i",
        str(bg),
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        f"{seconds:.2f}",
        "-i",
        str(fg),
        "-filter_complex",
        (
            f"[0:v]{bg_motion},setsar=1[bg];"
            f"[1:v]format=rgba[fg];"
            f"[bg][fg]overlay=x='{overlay_x}':y='{overlay_y}':format=auto:shortest=1,"
            f"{fade_filter},trim=duration={seconds:.2f},setpts=PTS-STARTPTS[v]"
        ),
        "-map",
        "[v]",
        "-an",
        *_video_encoder_args(intermediate=True),
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    completed = _run_background(command)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"2.5D parallax render failed for {image.name}: {detail[-1200:]}")


def _parallax_layers(image: Path, work_dir: Path, width: int, height: int, variant: int) -> tuple[Path, Path]:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

    work_dir.mkdir(parents=True, exist_ok=True)
    bg_path = work_dir / f"parallax_{variant:03d}_bg.jpg"
    fg_path = work_dir / f"parallax_{variant:03d}_fg.png"
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    base = Image.open(image).convert("RGB")
    fitted = ImageOps.fit(base, (width, height), method=resampling, centering=(0.5, 0.5))

    background = fitted.filter(ImageFilter.GaussianBlur(radius=8))
    background = ImageEnhance.Color(background).enhance(0.82)
    background = ImageEnhance.Contrast(background).enhance(0.94)
    background.save(bg_path, quality=95)

    foreground = ImageEnhance.Sharpness(fitted).enhance(1.18).convert("RGBA")
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    if width >= height:
        bbox = (int(width * 0.02), int(height * 0.02), int(width * 0.98), int(height * 0.98))
    else:
        bbox = (int(width * -0.10), int(height * 0.08), int(width * 1.10), int(height * 0.96))
    draw.ellipse(bbox, fill=220)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(32, int(min(width, height) * 0.08))))
    foreground.putalpha(mask)
    foreground.save(fg_path)
    return bg_path, fg_path


def _motion_filter(
    image: Path,
    seconds: float,
    preset: str,
    variant: int,
    video_format: str,
    max_zoom: float | None = None,
) -> str:
    rng = random.Random(f"{image.resolve()}-{variant}")
    frames = max(1, int(seconds * 30))
    width, height = frame_size(video_format)
    motion_frames = max(1, frames - 1)
    
    # High-order quintic smootherstep easing: zero acceleration at boundaries
    progress = f"(on/{motion_frames})"
    eased = f"(({progress})*({progress})*({progress})*(({progress})*(({progress})*6-15)+10))"
    
    min_zoom = 1.0000
    zoom_span = rng.uniform(0.045, 0.065) if max_zoom is None else (max_zoom - min_zoom)
    max_zoom_val = min_zoom + zoom_span

    # Randomized smooth camera animation effects
    styles = [
        "slow_zoom_in",
        "slow_zoom_out",
        "slow_pan_left",
        "slow_pan_right",
        "slow_drift_up",
        "slow_drift_down",
        "slow_diagonal_drift"
    ]
    chosen_style = styles[(variant - 1) % len(styles)]

    if chosen_style == "slow_zoom_in":
        z = f"min({min_zoom:.5f}+({zoom_span:.5f})*{eased},{max_zoom_val:.5f})"
        start_x, end_x = rng.choice([(0.50, 0.50), (0.45, 0.55), (0.55, 0.45)])
        start_y, end_y = rng.choice([(0.50, 0.50), (0.40, 0.48), (0.48, 0.40)])
    elif chosen_style == "slow_zoom_out":
        z = f"max({max_zoom_val:.5f}-({zoom_span:.5f})*{eased},{min_zoom:.5f})"
        start_x, end_x = rng.choice([(0.50, 0.50), (0.55, 0.45), (0.45, 0.55)])
        start_y, end_y = rng.choice([(0.45, 0.50), (0.40, 0.50), (0.50, 0.45)])
    elif chosen_style == "slow_pan_left":
        base_zoom = min_zoom + zoom_span * 0.8
        z = f"{base_zoom:.5f}"
        start_x, end_x = 0.68, 0.32
        start_y, end_y = 0.50, 0.50
    elif chosen_style == "slow_pan_right":
        base_zoom = min_zoom + zoom_span * 0.8
        z = f"{base_zoom:.5f}"
        start_x, end_x = 0.32, 0.68
        start_y, end_y = 0.50, 0.50
    elif chosen_style == "slow_drift_up":
        z = f"min({min_zoom:.5f}+({zoom_span*0.7:.5f})*{eased},{min_zoom+zoom_span*0.7:.5f})"
        start_x, end_x = 0.50, 0.50
        start_y, end_y = 0.62, 0.38
    elif chosen_style == "slow_drift_down":
        z = f"min({min_zoom:.5f}+({zoom_span*0.7:.5f})*{eased},{min_zoom+zoom_span*0.7:.5f})"
        start_x, end_x = 0.50, 0.50
        start_y, end_y = 0.38, 0.62
    else: # slow_diagonal_drift
        z = f"min({min_zoom:.5f}+({zoom_span:.5f})*{eased},{max_zoom_val:.5f})"
        start_x, end_x = rng.choice([(0.38, 0.62), (0.62, 0.38)])
        start_y, end_y = rng.choice([(0.38, 0.62), (0.62, 0.38)])

    x_factor = f"({start_x:.3f}+({end_x:.3f}-{start_x:.3f})*{eased})"
    y_factor = f"({start_y:.3f}+({end_y:.3f}-{start_y:.3f})*{eased})"
    x = f"max(iw-{width}/zoom,0)*{x_factor}"
    y = f"max(ih-{height}/zoom,0)*{y_factor}"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={width}x{height}:fps=30"


def _video_encoder_args(intermediate: bool = False) -> list[str]:
    encoder = settings.render_encoder.lower()
    if encoder == "auto":
        encoder = "h264_nvenc" if _has_encoder("h264_nvenc") else "libx264"
    if encoder in {"nvenc", "h264_nvenc"}:
        quality = "p4" if intermediate else "p5"
        cq = "24" if intermediate else "22"
        return ["-c:v", "h264_nvenc", "-preset", quality, "-tune", "hq", "-rc", "vbr", "-cq", cq, "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-threads", str(max(1, settings.render_threads))]


def _has_encoder(name: str) -> bool:
    if name in {"h264_nvenc", "nvenc"}:
        try:
            completed = subprocess.run(
                ["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.04", "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=_background_creationflags(),
            )
            return completed.returncode == 0
        except Exception:
            return False
    try:
        completed = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=_background_creationflags(),
        )
        return completed.returncode == 0 and name in completed.stdout
    except Exception:
        return False


def _render_timeout(total: float) -> int:
    configured = max(60, int(settings.render_timeout_seconds))
    expected = max(180, int(total * 12))
    return min(configured, expected)


def _run_background(command: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    creationflags = _background_creationflags()
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, creationflags=creationflags)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\nTimed out after {timeout} seconds.",
        )


def _background_creationflags() -> int:
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW
    if settings.render_background_priority and hasattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS"):
        creationflags |= subprocess.BELOW_NORMAL_PRIORITY_CLASS
    return creationflags

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from .captions import TimedCaption
from .layout import frame_size


def write_native_nepali_overlays(
    captions: list[TimedCaption],
    ass_path: Path,
    video_format: str,
    caption_style: str,
    preset: str,
) -> Path | None:
    nepali = [caption for caption in captions if _contains_devanagari(caption.text)]
    if not nepali:
        return None
    width, height = frame_size(video_format)
    y = _caption_y(height, video_format, caption_style, preset)
    font_size = _font_size(video_format, caption_style)
    out_dir = ass_path.with_suffix("").parent / f"{ass_path.stem}_native_nepali"
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    overlay_index = 1
    for caption in nepali:
        for piece in _caption_pieces(caption):
            image = out_dir / f"caption_{overlay_index:04d}.png"
            items.append(
                {
                    "start": piece.start,
                    "end": piece.end,
                    "text": piece.text,
                    "image": str(image),
                }
            )
            overlay_index += 1
    manifest = {
        "width": width,
        "height": height,
        "y": y,
        "fontSize": font_size,
        "items": items,
    }
    manifest_path = ass_path.with_suffix(".native_nepali.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _render_with_windows_text(manifest_path)
    return manifest_path


def _render_with_windows_text(manifest: Path) -> None:
    script = r'''
param([string]$ManifestPath)
Add-Type -AssemblyName System.Drawing
$data = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $data.items) {
  $bmp = New-Object System.Drawing.Bitmap([int]$data.width, [int]$data.height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.Clear([System.Drawing.Color]::Transparent)
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $font = New-Object System.Drawing.Font("Nirmala UI", [float]$data.fontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
  $format = New-Object System.Drawing.StringFormat
  $format.Alignment = [System.Drawing.StringAlignment]::Center
  $format.LineAlignment = [System.Drawing.StringAlignment]::Center
  if (-not ([string]$item.text).Contains("`n")) {
    $format.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap
  }
  $rect = New-Object System.Drawing.RectangleF(80, ([float]$data.y - 140), ([float]$data.width - 160), 280)
  $outline = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black)
  $fill = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
  foreach ($dx in -3..3) {
    foreach ($dy in -3..3) {
      if ($dx -ne 0 -or $dy -ne 0) {
        $r = New-Object System.Drawing.RectangleF(($rect.X + $dx), ($rect.Y + $dy), $rect.Width, $rect.Height)
        $g.DrawString([string]$item.text, $font, $outline, $r, $format)
      }
    }
  }
  $g.DrawString([string]$item.text, $font, $fill, $rect, $format)
  $bmp.Save([string]$item.image, [System.Drawing.Imaging.ImageFormat]::Png)
  $fill.Dispose(); $outline.Dispose(); $format.Dispose(); $font.Dispose(); $g.Dispose(); $bmp.Dispose()
}
'''
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), str(manifest)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            _render_with_pillow(manifest)
    except Exception:
        _render_with_pillow(manifest)
    finally:
        script_path.unlink(missing_ok=True)


def _render_with_pillow(manifest_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from .config import ASSETS_DIR
    
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    font_path = ASSETS_DIR / "fonts" / "NotoSansDevanagari-Bold.ttf"
    font_size = int(data.get("fontSize", 58))
    try:
        font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        font = ImageFont.load_default()

    width = int(data.get("width", 1080))
    height = int(data.get("height", 1920))
    center_y = float(data.get("y", height * 0.52))

    for item in data.get("items", []):
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        text = str(item.get("text", ""))

        # Center multiline text
        lines = text.split("\n")
        line_heights = [draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]
        total_text_h = sum(line_heights) + (len(lines) - 1) * 12
        start_y = center_y - (total_text_h / 2.0)

        cur_y = start_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            cur_x = (width - line_w) / 2.0
            
            # Thick black outline / glow
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    if dx != 0 or dy != 0:
                        draw.text((cur_x + dx, cur_y + dy), line, font=font, fill=(0, 0, 0, 200))
            # Primary white text
            draw.text((cur_x, cur_y), line, font=font, fill=(255, 255, 255, 255))
            cur_y += (bbox[3] - bbox[1]) + 12

        target_img = Path(item["image"])
        target_img.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(target_img), "PNG")


def _caption_y(height: int, video_format: str, caption_style: str, preset: str) -> int:
    if caption_style == "reference_cursive":
        return int(height * (0.52 if video_format == "landscape" else 0.495))
    if preset == "poetry_reference":
        return int(height * (0.72 if video_format == "landscape" else 0.555))
    return int(height * 0.56)


def _font_size(video_format: str, caption_style: str) -> int:
    if video_format == "landscape":
        return 46
    return 60 if caption_style == "reference_cursive" else 56


def _wrap_text(text: str) -> str:
    words = text.split()
    if len(words) <= 4 and len(text) <= 34:
        return text
    if len(words) <= 2:
        return text
    midpoint = max(2, min(len(words) - 2, round(len(words) * 0.5)))
    return " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])


def _caption_pieces(caption: TimedCaption) -> list[TimedCaption]:
    words = caption.text.split()
    if len(words) <= 6:
        return [TimedCaption(caption.start, caption.end, _wrap_text(caption.text), caption.word_durations)]
    groups = _word_groups(words)
    total = max(0.3, caption.end - caption.start)
    groups = _merge_fast_groups(groups, total)
    weights = _group_timing_weights(groups, caption.word_durations)
    spoken_total = sum(caption.word_durations) if caption.word_durations else total
    spoken_total = max(0.3, min(total, spoken_total))
    pieces: list[TimedCaption] = []
    cursor = caption.start
    for index, group in enumerate(groups):
        target = spoken_total * weights[index] / max(1.0, sum(weights))
        min_hold = 0.65 if len(groups) > 1 else 0.0
        end = caption.end if index == len(groups) - 1 else min(caption.end, cursor + max(min_hold, target))
        pieces.append(TimedCaption(cursor, end, _wrap_text(" ".join(group)), tuple()))
        cursor = end
    return pieces


def _word_groups(words: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    cursor = 0
    while cursor < len(words):
        remaining = len(words) - cursor
        if remaining <= 4:
            groups.append(words[cursor:])
            break
        size = 4
        if remaining == 5:
            size = 3
        groups.append(words[cursor : cursor + size])
        cursor += size
    return groups


def _merge_fast_groups(groups: list[list[str]], total: float, min_hold: float = 0.65) -> list[list[str]]:
    groups = [list(group) for group in groups]
    while len(groups) > 1 and total / len(groups) < min_hold:
        groups[-2].extend(groups[-1])
        groups.pop()
    return groups


def _group_timing_weights(groups: list[list[str]], word_durations: tuple[float, ...]) -> list[float]:
    if not word_durations:
        return [max(1.0, len(group)) for group in groups]
    weights: list[float] = []
    cursor = 0
    durations = list(word_durations)
    for group in groups:
        count = len(group)
        chunk = durations[cursor : cursor + count]
        weights.append(max(0.5, sum(chunk) if chunk else float(count)))
        cursor += count
    return weights


def _contains_devanagari(value: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in value)

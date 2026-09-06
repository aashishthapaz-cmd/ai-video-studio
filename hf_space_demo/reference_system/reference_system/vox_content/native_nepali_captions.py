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
        words = caption.text.split()
        if not words:
            continue
            
        total_time = max(0.5, caption.end - caption.start)
        durs = list(caption.word_durations[:len(words)])
        
        # If durations not provided or incomplete, compute acoustic syllable distribution
        if len(durs) < len(words):
            spoken_dur = max(0.4, total_time * 0.88 if len(words) > 3 else total_time * 0.92)
            weights = [_word_weight(w) for w in words]
            w_sum = sum(weights) or 1.0
            durs = [max(0.10, round((w / w_sum) * spoken_dur, 3)) for w in weights]
            
        curr_t = caption.start
        for w_idx in range(len(words)):
            w_dur = durs[w_idx]
            w_end = min(caption.end, curr_t + w_dur)
            image = out_dir / f"caption_{overlay_index:04d}.png"
            items.append({
                "start": round(curr_t, 3),
                "end": round(w_end, 3),
                "text": caption.text,
                "active_word_index": w_idx,
                "image": str(image)
            })
            overlay_index += 1
            curr_t = w_end
            
        # Hold state after last word finishes speaking until slide ends
        if caption.end > curr_t + 0.04:
            image = out_dir / f"caption_{overlay_index:04d}.png"
            items.append({
                "start": round(curr_t, 3),
                "end": round(caption.end, 3),
                "text": caption.text,
                "active_word_index": len(words), # all completed in white
                "image": str(image)
            })
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
    _render_with_pillow(manifest_path)
    return manifest_path


def _word_weight(word: str) -> float:
    w = word.strip(".,!?;:।॥\"'()[]{}—")
    if not w:
        return 1.0
    aksharas = sum(1 for ch in w if ("\u0904" <= ch <= "\u0939" or "\u0958" <= ch <= "\u0961") and ch != "\u094d")
    base = max(1, aksharas) * 1.5 + len(w) * 0.3
    if word.endswith(("।", "॥", ".", "?", "!")):
        base += 1.2
    elif word.endswith((",", ";", ":")):
        base += 0.8
    return base


def _render_with_pillow(manifest_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from .config import ASSETS_DIR
    
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    
    font_candidates = [
        ASSETS_DIR / "fonts" / "NotoSansDevanagari-Bold.ttf",
        Path("C:/Windows/Fonts/NirmalaB.ttf"),
        Path("C:/Windows/Fonts/Nirmala.ttf"),
        Path("C:/Windows/Fonts/arial.ttf")
    ]
    font_path = next((p for p in font_candidates if p.exists()), None)
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
        text = str(item.get("text", "")).strip()
        act_idx = int(item.get("active_word_index", -1))
        words = text.split()

        # Word layout (single line or balanced 2-line wrap)
        if len(words) > 6 or len(text) > 36:
            mid = max(2, min(len(words) - 2, round(len(words) * 0.5)))
            lines_words = [words[:mid], words[mid:]]
        else:
            lines_words = [words]

        space_w = draw.textbbox((0, 0), " ", font=font)[2]
        sample_bb = draw.textbbox((0, 0), "मनका", font=font)
        line_h = sample_bb[3] - sample_bb[1]
        
        total_h = len(lines_words) * line_h + (len(lines_words) - 1) * 16
        start_y = center_y - (total_h / 2.0)
        
        global_w_idx = 0
        cur_y = start_y
        
        for lw in lines_words:
            w_bboxes = [draw.textbbox((0, 0), w, font=font) for w in lw]
            w_widths = [bb[2] - bb[0] for bb in w_bboxes]
            total_w = sum(w_widths) + (len(lw) - 1) * space_w
            cur_x = (width - total_w) / 2.0
            
            for w, w_w in zip(lw, w_widths):
                if act_idx >= len(words) or global_w_idx < act_idx:
                    # Completed / Past word: Bright Pure White
                    fill_col = (255, 255, 255, 255)
                    out_col = (0, 0, 0, 230)
                elif global_w_idx == act_idx:
                    # Active spoken word: Glowing Luminous Amber Gold!
                    fill_col = (251, 191, 36, 255)
                    out_col = (25, 15, 0, 250)
                else:
                    # Upcoming word: Subtle Translucent Silver White
                    fill_col = (205, 215, 230, 160)
                    out_col = (0, 0, 0, 150)
                    
                # Outline & Drop Shadow
                for dx in range(-3, 4):
                    for dy in range(-3, 4):
                        if dx != 0 or dy != 0:
                            draw.text((cur_x + dx, cur_y + dy), w, font=font, fill=out_col)
                # Fill
                draw.text((cur_x, cur_y), w, font=font, fill=fill_col)
                
                cur_x += w_w + space_w
                global_w_idx += 1
                
            cur_y += line_h + 16

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


def _contains_devanagari(value: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in value)

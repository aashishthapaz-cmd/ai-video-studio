from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from secrets import SystemRandom
import random

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import ASSETS_DIR
from .layout import frame_size
from .models import VisualAsset


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "VoxCPM-ContentFactory/1.0"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def collect_visuals(
    queries: list[str],
    out_dir: Path,
    count: int,
    preset: str = "modern",
    content_kind: str = "auto",
    image_folder: str = "",
    video_format: str = "portrait",
) -> list[VisualAsset]:
    out_dir.mkdir(parents=True, exist_ok=True)
    custom = _custom_folder_visuals(out_dir, count, image_folder, video_format)
    if custom:
        return custom
    dropped = _drop_folder_visuals(out_dir, count, _resolve_kind(queries, preset, content_kind), video_format)
    if dropped:
        return dropped

    if preset == "poetry_reference":
        return _poetry_visuals(queries, out_dir, count, video_format)

    assets: list[VisualAsset] = []
    for query in queries:
        if len(assets) >= count:
            break
        asset = _commons(query, out_dir, len(assets) + 1, video_format)
        if asset:
            assets.append(asset)
    while len(assets) < count:
        path = out_dir / f"generated_{len(assets) + 1}.jpg"
        _fallback(path, queries[0] if queries else "Story", video_format)
        assets.append(VisualAsset(path=path, credit="Generated local cinematic fallback"))
    return assets


def _custom_folder_visuals(out_dir: Path, count: int, folder_value: str, video_format: str) -> list[VisualAsset]:
    folder_value = folder_value.strip()
    if not folder_value or folder_value.lower() == "auto":
        return []
    folder = Path(folder_value)
    files = _image_files(folder)
    if not files:
        return []
    files = files[:]
    SystemRandom().shuffle(files)
    assets: list[VisualAsset] = []
    for index in range(count):
        source = files[index % len(files)]
        target = out_dir / f"custom_drop_{index + 1}.jpg"
        _prepare_template(source, target, index, video_format)
        assets.append(
            VisualAsset(
                path=target,
                source_url=str(source),
                credit=f"Custom image folder: {source.name}",
            )
        )
    return assets


def _resolve_kind(queries: list[str], preset: str, content_kind: str) -> str:
    if content_kind in {"poems", "motivation"}:
        return content_kind
    text = " ".join(queries).lower()
    if preset == "poetry_reference" or any(word in text for word in ("poem", "poetry", "love", "grateful", "heart", "romantic", "soul")):
        return "poems"
    if any(word in text for word in ("motivation", "discipline", "success", "focus", "habit", "grind", "mindset", "goal")):
        return "motivation"
    return "poems"


def _drop_folder_visuals(out_dir: Path, count: int, kind: str, video_format: str) -> list[VisualAsset]:
    folder = ASSETS_DIR / "image_drop" / kind
    files = _image_files(folder)
    if not files:
        return []
    files = files[:]
    SystemRandom().shuffle(files)
    assets: list[VisualAsset] = []
    for index in range(count):
        source = files[index % len(files)]
        target = out_dir / f"{kind}_drop_{index + 1}.jpg"
        _prepare_template(source, target, index, video_format)
        assets.append(
            VisualAsset(
                path=target,
                source_url=str(source),
                credit=f"User image drop: {kind}/{source.name}",
            )
        )
    return assets


def _image_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _poetry_visuals(queries: list[str], out_dir: Path, count: int, video_format: str) -> list[VisualAsset]:
    assets: list[VisualAsset] = []
    templates = sorted((ASSETS_DIR / "poetry_templates").glob("*.*"))
    if templates:
        templates = templates[:]
        SystemRandom().shuffle(templates)
        for index in range(count):
            source = templates[index % len(templates)]
            path = out_dir / f"poetry_template_{index + 1}.jpg"
            _prepare_template(source, path, index, video_format)
            assets.append(
                VisualAsset(
                    path=path,
                    source_url="local://ai-generated-poetry-template",
                    credit=f"Generated artistic poetry template: {source.name}",
                )
            )
        return assets

    seed_text = " ".join(queries) or "quiet poetic gratitude"
    for index in range(count):
        path = out_dir / f"poetry_scene_{index + 1}.jpg"
        _poetry_scene(path, seed_text, index, video_format)
        assets.append(
            VisualAsset(
                path=path,
                source_url="local://generated-poetry-reference-style",
                credit="Generated local reference-style illustration",
            )
        )
    return assets


def _prepare_template(source: Path, target: Path, index: int, video_format: str) -> None:
    size = frame_size(video_format)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image = image.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80))
        _add_soft_texture(image, index)
        image.save(target, quality=94)


def _poetry_scene(path: Path, seed_text: str, index: int, video_format: str) -> None:
    random.seed(f"{seed_text}:{index}")
    width, height = frame_size(video_format)
    image = Image.new("RGB", (width, height), "#070912")
    draw = ImageDraw.Draw(image, "RGBA")
    palettes = [
        ((12, 18, 37), (42, 52, 85), (242, 165, 104)),
        ((8, 12, 25), (31, 46, 75), (224, 194, 142)),
        ((16, 19, 30), (53, 68, 91), (202, 122, 86)),
        ((6, 10, 20), (37, 47, 65), (238, 218, 174)),
    ]
    top, mid, glow = palettes[index % len(palettes)]
    for y in range(height):
        t = y / max(1, height - 1)
        base = tuple(int(top[c] * (1 - t) + mid[c] * t) for c in range(3))
        draw.line((0, y, width, y), fill=(*base, 255))

    for _ in range(150):
        x = random.randint(20, max(21, width - 20))
        y = random.randint(60, max(61, int(height * 0.52)))
        alpha = random.randint(45, 130)
        draw.ellipse((x, y, x + 2, y + 2), fill=(255, 245, 220, alpha))

    if video_format == "landscape":
        _draw_landscape_scene(draw, glow, width, height, index)
    else:
        scene = index % 4
        if scene == 0:
            _draw_sunset_hill(draw, glow)
        elif scene == 1:
            _draw_window_scene(draw, glow)
        elif scene == 2:
            _draw_boat_scene(draw, glow)
        else:
            _draw_lamp_stairs(draw, glow)

    image = image.filter(ImageFilter.GaussianBlur(radius=0.35))
    _add_soft_texture(image, index)
    image.save(path, quality=94)


def _draw_sunset_hill(draw: ImageDraw.ImageDraw, glow: tuple[int, int, int]) -> None:
    draw.ellipse((250, 420, 830, 1000), fill=(*glow, 65))
    draw.polygon([(0, 1320), (280, 1180), (620, 1250), (1080, 1120), (1080, 1920), (0, 1920)], fill=(7, 9, 16, 235))
    _draw_person(draw, 470, 1125, 1.0)
    _draw_person(draw, 575, 1128, 0.95)
    draw.line((510, 1275, 565, 1270), fill=(245, 224, 193, 125), width=5)


def _draw_window_scene(draw: ImageDraw.ImageDraw, glow: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((175, 360, 905, 1260), radius=28, outline=(*glow, 105), width=8)
    draw.line((540, 370, 540, 1250), fill=(*glow, 60), width=5)
    draw.line((185, 800, 895, 800), fill=(*glow, 55), width=5)
    draw.ellipse((680, 460, 810, 590), fill=(240, 232, 198, 165))
    draw.rectangle((0, 1260, 1080, 1920), fill=(6, 8, 14, 225))
    _draw_person(draw, 510, 1140, 1.12)


def _draw_boat_scene(draw: ImageDraw.ImageDraw, glow: tuple[int, int, int]) -> None:
    for y in range(1180, 1920, 38):
        draw.arc((-120, y - 70, 1200, y + 90), 8, 172, fill=(*glow, 35), width=2)
    draw.ellipse((400, 520, 680, 800), fill=(240, 232, 198, 115))
    draw.polygon([(260, 1200), (820, 1200), (700, 1310), (380, 1310)], fill=(8, 10, 18, 235))
    draw.line((540, 760, 540, 1200), fill=(235, 218, 186, 120), width=5)
    draw.polygon([(545, 785), (545, 1160), (725, 1138)], fill=(238, 219, 184, 52))


def _draw_lamp_stairs(draw: ImageDraw.ImageDraw, glow: tuple[int, int, int]) -> None:
    for i in range(12):
        y = 980 + i * 70
        draw.polygon([(130, y), (950, y - 30), (1010, y + 24), (90, y + 58)], fill=(12, 15, 24, 185))
    draw.line((270, 580, 270, 1220), fill=(11, 12, 17, 230), width=16)
    draw.ellipse((205, 500, 335, 640), fill=(*glow, 95))
    draw.ellipse((238, 536, 302, 600), fill=(245, 225, 180, 165))
    _draw_person(draw, 640, 1018, 0.9)


def _draw_person(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float) -> None:
    head = 26 * scale
    body = 86 * scale
    draw.ellipse((x - head, y - 155 * scale, x + head, y - 103 * scale), fill=(3, 5, 10, 240))
    draw.rounded_rectangle((x - 34 * scale, y - 108 * scale, x + 34 * scale, y + body), radius=int(28 * scale), fill=(3, 5, 10, 240))


def _draw_landscape_scene(draw: ImageDraw.ImageDraw, glow: tuple[int, int, int], width: int, height: int, index: int) -> None:
    draw.ellipse((int(width * 0.58), int(height * 0.10), int(width * 0.84), int(height * 0.56)), fill=(*glow, 70))
    horizon = int(height * 0.72)
    draw.polygon(
        [
            (0, horizon + 36),
            (int(width * 0.18), int(height * 0.60)),
            (int(width * 0.42), int(height * 0.66)),
            (int(width * 0.68), int(height * 0.57)),
            (width, int(height * 0.63)),
            (width, height),
            (0, height),
        ],
        fill=(7, 9, 16, 235),
    )
    if index % 2 == 0:
        _draw_person(draw, int(width * 0.34), int(height * 0.67), 0.92)
        _draw_person(draw, int(width * 0.41), int(height * 0.67), 0.88)
        draw.line((int(width * 0.35), int(height * 0.73), int(width * 0.40), int(height * 0.73)), fill=(245, 224, 193, 125), width=4)
    else:
        _draw_person(draw, int(width * 0.50), int(height * 0.64), 1.0)


def _add_soft_texture(image: Image.Image, index: int) -> None:
    random.seed(index + 99)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    for _ in range(2400):
        x = random.randint(0, image.width - 1)
        y = random.randint(0, image.height - 1)
        value = random.choice((255, 0))
        alpha = random.randint(3, 16)
        draw.point((x, y), fill=(value, value, value, alpha))
    base = image.convert("RGBA")
    base.alpha_composite(overlay)
    image.paste(base.convert("RGB"))


def _commons(query: str, out_dir: Path, index: int, video_format: str) -> VisualAsset | None:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 10,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1600,
        "origin": "*",
    }
    try:
        response = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None
    pages = response.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url") or ""
        if not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        try:
            image_data = requests.get(url, headers=HEADERS, timeout=20)
            image_data.raise_for_status()
            source = out_dir / f"source_{index}.img"
            source.write_bytes(image_data.content)
            target = out_dir / f"visual_{index}.jpg"
            _prepare(source, target, video_format)
            return VisualAsset(path=target, source_url=info.get("descriptionurl", url), credit=_credit(page, info))
        except Exception:
            continue
    return None


def _prepare(source: Path, target: Path, video_format: str) -> None:
    size = frame_size(video_format)
    with Image.open(source) as image:
        image = image.convert("RGB")
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110))
        image.save(target, quality=94)


def _fallback(path: Path, title: str, video_format: str) -> None:
    width, height = frame_size(video_format)
    image = Image.new("RGB", (width, height), "#050816")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        draw.line((0, y, width, y), fill=(5 + y // 120, 8 + y // 80, 22 + y // 60))
    for i in range(14):
        x = int(width * 0.08) + i * max(42, int(width * 0.055))
        draw.line((x, 0, x - int(width * 0.48), height), fill=(20, 184, 220), width=1)
    top = int(height * 0.68)
    bottom = min(height - 40, top + int(height * 0.16))
    draw.rectangle((int(width * 0.08), top, int(width * 0.92), bottom), outline=(125, 211, 252), width=3)
    font = ImageFont.load_default()
    draw.multiline_text((int(width * 0.12), top + int(height * 0.04)), _wrap(title.upper(), 28 if video_format == "landscape" else 24), fill="#f8fafc", font=font, spacing=18)
    image.save(path, quality=94)


def _wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)


def _credit(page: dict, info: dict) -> str:
    meta = info.get("extmetadata", {})
    title = str(page.get("title", "")).replace("File:", "")
    artist = _strip(meta.get("Artist", {}).get("value", ""))
    license_name = _strip(meta.get("LicenseShortName", {}).get("value", ""))
    return " / ".join(part for part in (title, artist, license_name) if part)


def _strip(value: str) -> str:
    return value.replace("<span>", "").replace("</span>", "").replace("<bdi>", "").replace("</bdi>", "")

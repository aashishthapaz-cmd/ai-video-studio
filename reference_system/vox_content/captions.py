from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import unicodedata

from .layout import frame_center, frame_size

HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ProCaption,Arial,72,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,3,3,0,2,70,70,210,1
Style: PoetrySmall,Cormorant Garamond,46,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,0,1,0,0,88,100,0,0,1,1.7,0,5,70,70,0,1
Style: ReferenceCursive,Segoe Print,78,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,0,1,0,0,96,100,0,0,1,2.5,2.0,5,90,90,0,1
Style: ReferenceMark,Segoe Script,22,&H00FFFFFF,&H60FFFFFF,&HAA000000,&H00000000,0,1,0,0,88,100,0,0,1,0.7,1.0,5,40,40,0,1
Style: DarkAcademiaSerif,Cormorant Garamond,82,&H00C0C0FF,&H50FFFFFF,&H00080808,&H90000000,0,1,0,0,94,100,0,0,1,2.2,2.2,5,90,90,0,1
Style: RomanticScript,Segoe Script,74,&H0033CCFF,&H60FFFFFF,&H00181008,&H90000000,0,1,0,0,96,100,0,0,1,2.4,1.8,5,90,90,0,1
Style: StoicMinimal,Montserrat,70,&H00D0FFD0,&H60FFFFFF,&H00111811,&H90000000,-1,0,0,0,96,100,0,0,1,2.6,2.0,5,90,90,0,1
Style: CosmicSerif,Cinzel,74,&H00EEEEEE,&H50FFFFFF,&H000B0B14,&H90000000,-1,0,0,0,96,100,0,0,1,2.5,2.5,5,90,90,0,1
Style: TypewriterMono,Courier New,72,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,-1,0,0,0,92,100,0,0,1,2.4,2.0,5,90,90,0,1
Style: NepaliReference,Noto Sans Devanagari,68,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,1,2.5,2.0,5,90,90,0,1
Style: NepaliCaption,Noto Sans Devanagari,58,&H0000D7FF,&H60FFFFFF,&H00111111,&H90000000,-1,0,0,0,100,100,0,0,1,2.0,1.5,5,70,70,0,1
Style: CreativeScript,Cormorant Garamond,58,&H0000D7FF,&H60FFFFFF,&HD0000000,&H00000000,0,1,0,0,100,100,0,0,1,0.45,2.1,5,60,60,0,1
Style: CreativeBold,Arial,42,&H0000D7FF,&H60FFFFFF,&HE0000000,&H00000000,0,0,0,0,92,100,0,0,1,1.55,3.1,5,60,60,0,1
Style: CreativeYellow,Arial,78,&H0000D7FF,&H60FFFFFF,&HE0000000,&H00000000,-1,0,0,0,90,100,0,0,1,2.0,4.0,5,60,60,0,1
Style: CreativeTiny,Arial,32,&H0000D7FF,&H60FFFFFF,&HE0000000,&H00000000,0,0,0,0,90,100,0,0,1,1.3,2.7,5,60,60,0,1
Style: TinyCredit,Arial,26,&H99FFFFFF,&H00000000,&H55000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,1,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

@dataclass(frozen=True)
class TimedCaption:
    start: float
    end: float
    text: str
    word_durations: tuple[float, ...] = ()


def write_ass(
    phrases: list[str],
    duration: float,
    output: Path,
    preset: str = "modern",
    caption_style: str = "karaoke_line",
    video_format: str = "portrait",
    signature_enabled: bool = True,
    signature_text: str = "@whispers",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    clean = [_clean(phrase) for phrase in phrases if _clean(phrase)]
    if not clean:
        clean = ["Your story starts with one clear idea."]
    slot = max(1.15, duration / len(clean))
    timed = []
    for index, phrase in enumerate(clean):
        start = index * slot
        end = min(duration, start + slot + 0.15)
        timed.append(TimedCaption(start=start, end=end, text=phrase))
    return write_timed_ass(
        timed,
        output,
        preset=preset,
        caption_style=caption_style,
        video_format=video_format,
        signature_enabled=signature_enabled,
        signature_text=signature_text,
    )


def write_timed_ass(
    captions: list[TimedCaption],
    output: Path,
    preset: str = "modern",
    caption_style: str = "karaoke_line",
    video_format: str = "portrait",
    signature_enabled: bool = True,
    signature_text: str = "@whispers",
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = frame_size(video_format)
    center_x, _center_y = frame_center(video_format)
    poetry_y = int(height * (0.72 if video_format == "landscape" else 0.555))
    reference_y = int(height * (0.52 if video_format == "landscape" else 0.495))
    reference_mark_y = int(height * (0.775 if video_format == "landscape" else 0.765))
    events: list[str] = [HEADER_TEMPLATE.format(width=width, height=height)]
    if caption_style == "reference_cursive" and signature_enabled and signature_text.strip():
        start = 0.0
        end = max((caption.end for caption in captions), default=0.0) + 4.0
        events.append(
            f"Dialogue: 0,{_stamp(start)},{_stamp(end)},ReferenceMark,,0,0,0,,"
            f"{{\\pos({center_x},{reference_mark_y})\\blur0.2}}{_escape_ass(signature_text.strip())}\n"
        )
    native_nepali: list[TimedCaption] = []
    for caption in captions:
        if _contains_devanagari(caption.text):
            native_nepali.append(caption)
            continue
        if caption_style.startswith("creative_"):
            events.extend(_creative_caption_events(caption, caption_style=caption_style, video_format=video_format))
            continue
        NICHE_CAPTION_STYLES = {
            "reference_cursive": "ReferenceCursive",
            "dark_academia_serif": "DarkAcademiaSerif",
            "romantic_script": "RomanticScript",
            "stoic_minimal": "StoicMinimal",
            "cosmic_serif": "CosmicSerif",
            "typewriter_mono": "TypewriterMono"
        }
        if caption_style in NICHE_CAPTION_STYLES:
            text = _reference_caption_text(caption)
            is_nepali = _contains_devanagari(caption.text)
            style = "NepaliReference" if is_nepali else NICHE_CAPTION_STYLES[caption_style]
            override = f"\\pos({center_x},{reference_y})\\fad(180,200)\\blur0.3"
            events.append(
                f"Dialogue: 1,{_stamp(caption.start)},{_stamp(caption.end)},{style},,0,0,0,,"
                f"{{{override}}}{text}\n"
            )
            continue
        if preset == "poetry_reference":
            is_nepali = _contains_devanagari(caption.text)
            text = _escape_ass(_clean(caption.text)) if is_nepali else _poetry_caption_text(caption)
            style = "NepaliCaption" if is_nepali else "PoetrySmall"
            override = f"\\pos({center_x},{poetry_y})\\fad(180,200)\\blur0.3"
            events.append(
                f"Dialogue: 0,{_stamp(caption.start)},{_stamp(caption.end)},{style},,0,0,0,,"
                f"{{{override}}}{text}\n"
            )
        else:
            text = _caption_text(caption.text, preset)
            style = "NepaliCaption" if _contains_devanagari(caption.text) else "ProCaption"
            events.append(
                f"Dialogue: 0,{_stamp(caption.start)},{_stamp(caption.end)},{style},,0,0,0,,"
                f"{{\\fad(100,120)\\t(0,220,\\fscx104\\fscy104)\\t(220,420,\\fscx100\\fscy100)}}{text}\n"
            )
    output.write_text("".join(events), encoding="utf-8")
    if native_nepali:
        from .native_nepali_captions import write_native_nepali_overlays

        write_native_nepali_overlays(native_nepali, output, video_format, caption_style, preset)
    return output


def phrases_from_narration(narration: str, words_per_caption: int = 5) -> list[str]:
    words = _words(narration)
    phrases: list[str] = []
    for index in range(0, len(words), words_per_caption):
        phrase = " ".join(words[index : index + words_per_caption]).strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def phrases_from_audio(audio_path: Path) -> list[str]:
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return []
    try:
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), vad_filter=False, beam_size=3)
        phrases = []
        for segment in segments:
            text = _clean(segment.text)
            if text:
                phrases.extend(phrases_from_narration(text, words_per_caption=5))
        return phrases
    except Exception:
        return []


def timed_captions_from_audio(audio_path: Path, max_words: int = 5) -> list[TimedCaption]:
    words = _audio_words(audio_path)
    if not words:
        return []
    captions: list[TimedCaption] = []
    group = []
    for index, word in enumerate(words):
        previous_gap = word.start - group[-1].end if group else 0.0
        next_word = words[index + 1] if index + 1 < len(words) else None
        next_text = _word_text(next_word) if next_word else ""
        current_text = _word_text(word)
        group_texts = [_word_text(item) for item in group]
        should_break = bool(group) and (
            previous_gap > 0.70
            or _should_end_caption(group_texts, current_text, next_text, len(group) + 1, max_words)
        )
        if should_break:
            _append_caption(captions, _group_caption(group))
            group = []
        group.append(word)
    if group:
        _append_caption(captions, _group_caption(group))
    captions = _merge_orphan_captions(captions)
    return _hold_captions_during_pauses(captions)


def timed_captions_from_script_rows_and_audio(audio_path: Path, script: str) -> list[TimedCaption]:
    rows = _caption_rows(script)
    if not rows:
        return timed_captions_from_audio(audio_path)
    if _contains_devanagari(script):
        return _timed_captions_from_script_rows_even(audio_path, script)
    words = _audio_words(audio_path)
    if not words:
        return []

    captions: list[TimedCaption] = []
    cursor = 0
    for row in rows:
        count = max(1, _word_count(row))
        start_index = min(cursor, len(words) - 1)
        end_index = min(len(words) - 1, cursor + count - 1)
        phrase_words = words[start_index : end_index + 1]
        start = max(0.0, phrase_words[0].start)
        end = phrase_words[-1].end + 0.32
        durations = tuple(max(0.08, word.end - word.start) for word in phrase_words)
        _append_caption(captions, TimedCaption(start=start, end=end, text=_clean(row), word_durations=durations))
        cursor = end_index + 1
        if cursor >= len(words):
            break
    return _hold_captions_during_pauses(captions)


def timed_captions_from_script_and_audio(audio_path: Path, script: str, preset: str = "modern") -> list[TimedCaption]:
    if _contains_devanagari(script):
        return _timed_captions_from_script_rows_even(audio_path, script)
    phrases = _script_phrases(script, preset=preset)
    if not phrases:
        return timed_captions_from_audio(audio_path)
    words = _audio_words(audio_path)
    if not words:
        return []

    captions: list[TimedCaption] = []
    cursor = 0
    for phrase in phrases:
        count = max(1, len(_words(phrase)))
        start_index = min(cursor, len(words) - 1)
        end_index = min(len(words) - 1, cursor + count - 1)
        phrase_words = words[start_index : end_index + 1]
        start = max(0.0, phrase_words[0].start)
        end = phrase_words[-1].end + 0.30
        durations = tuple(max(0.08, word.end - word.start) for word in phrase_words)
        _append_caption(captions, TimedCaption(start=start, end=end, text=_clean(phrase), word_durations=durations))
        cursor = end_index + 1
        if cursor >= len(words):
            break
    return _hold_captions_during_pauses(captions)


def _audio_words(audio_path: Path):
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return []
    try:
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=False, beam_size=3)
        words = []
        for segment in segments:
            words.extend([word for word in (segment.words or []) if word.word.strip()])
        return words
    except Exception:
        return []


def _script_phrases(script: str, preset: str = "modern") -> list[str]:
    raw = script.replace("\r\n", "\n").replace("\r", "\n")
    if not _clean(raw):
        return []
    raw = re.sub(r"\n+", ". ", raw)
    cleaned = _clean(raw)
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?।॥])\s+", cleaned) if chunk.strip()]
    phrases: list[str] = []
    max_words = 6 if preset == "poetry_reference" else 6
    for chunk in chunks:
        words = chunk.split()
        if len(words) <= max_words:
            phrases.append(chunk)
            continue
        for index in range(0, len(words), max_words):
            phrase = " ".join(words[index : index + max_words]).strip()
            if phrase:
                phrases.append(phrase)
    return phrases


def significant_caption_starts(captions: list[TimedCaption]) -> list[float]:
    starts = _sentence_starts(captions)
    if starts:
        return starts
    starts = []
    for caption in captions:
        if _word_count(caption.text) <= 3:
            continue
        starts.append(caption.start)
    return starts


def _sentence_starts(captions: list[TimedCaption]) -> list[float]:
    starts: list[float] = []
    sentence_start: float | None = None
    sentence_words = 0
    for caption in captions:
        if sentence_start is None:
            sentence_start = caption.start
        sentence_words += _word_count(caption.text)
        if _ends_sentence(caption.text):
            if sentence_words > 3:
                starts.append(sentence_start)
            sentence_start = None
            sentence_words = 0
    if sentence_start is not None and sentence_words > 3:
        starts.append(sentence_start)
    return starts


def _ends_sentence(text: str) -> bool:
    text = text.strip()
    return text.endswith((".", "!", "?", "...", "।", "॥"))


def _script_rows(script: str) -> list[str]:
    rows: list[str] = []
    for line in script.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        clean = _clean(line)
        if clean:
            rows.append(clean)
    return rows


def _caption_rows(script: str) -> list[str]:
    line_rows = _script_rows(script)
    if len(line_rows) >= 3:
        return _poem_caption_rows(line_rows)

    raw_rows = _punctuation_rows(script)
    merged: list[str] = []
    index = 0
    while index < len(raw_rows):
        row = raw_rows[index]
        words = row.split()
        first = _display_word(words[0]).lower() if words else ""
        previous_last = _display_word(merged[-1].split()[-1]).lower() if merged else ""
        if len(words) <= 1 and first:
            if first == "for" and merged and _sticks_to_previous(previous_last, first):
                merged[-1] = _clean(f"{merged[-1]} {row}")
                index += 1
                continue
            if first in _LEADING_CONNECTORS and index + 1 < len(raw_rows):
                merged.append(_clean(f"{row} {raw_rows[index + 1]}"))
                index += 2
                continue
            if first in _TRAILING_CONNECTORS and index + 1 < len(raw_rows):
                merged.append(_clean(f"{row} {raw_rows[index + 1]}"))
                index += 2
                continue
        merged.extend(_split_caption_row(row, max_words=10))
        index += 1
    return [row for row in merged if row]


def _poem_caption_rows(line_rows: list[str]) -> list[str]:
    rows: list[str] = []
    index = 0
    while index < len(line_rows):
        row = line_rows[index]
        words = row.split()
        first = _display_word(words[0]).lower() if words else ""
        if len(words) == 1 and first in (_LEADING_CONNECTORS | _TRAILING_CONNECTORS):
            if rows:
                rows[-1] = _clean(f"{rows[-1]} {row}")
            elif index + 1 < len(line_rows):
                rows.append(_clean(f"{row} {line_rows[index + 1]}"))
                index += 1
            index += 1
            continue
        rows.extend(_split_caption_row(row, max_words=10))
        index += 1
    return _merge_short_poem_rows([row for row in rows if row])


def _merge_short_poem_rows(rows: list[str], min_words: int = 4, max_words: int = 10) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(rows):
        row = rows[index]
        words = _word_count(row)
        if _contains_devanagari(row) and _ends_sentence(row):
            merged.append(row)
            index += 1
            continue
        if words >= min_words:
            merged.append(row)
            index += 1
            continue
        if _short_row_should_attach_forward(row) and index + 1 < len(rows) and words + _word_count(rows[index + 1]) <= max_words:
            merged.append(_clean(f"{row} {rows[index + 1]}"))
            index += 2
            continue
        if merged and _word_count(merged[-1]) + words <= max_words:
            merged[-1] = _clean(f"{merged[-1]} {row}")
            index += 1
            continue
        if index + 1 < len(rows) and words + _word_count(rows[index + 1]) <= max_words:
            merged.append(_clean(f"{row} {rows[index + 1]}"))
            index += 2
            continue
        merged.append(row)
        index += 1
    return merged


def _short_row_should_attach_forward(row: str) -> bool:
    text = row.strip()
    return text.endswith((",", ";", ":", "..."))


def _punctuation_rows(script: str) -> list[str]:
    text = script.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\.{3,}", "...", text)
    text = re.sub(r"(?<![,.!?;:])\n+", " ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[,.!?।॥])\s+", text) if part.strip()]
    rows: list[str] = []
    for part in parts:
        cleaned = _clean(part)
        if cleaned:
            rows.extend(_split_caption_row(cleaned, max_words=10))
    return rows


def _split_caption_row(row: str, max_words: int = 10) -> list[str]:
    words = row.split()
    if len(words) <= max_words:
        return [_clean(row)]
    chunks: list[str] = []
    group: list[str] = []
    for index, word in enumerate(words):
        current = _display_word(word).lower()
        next_word = _display_word(words[index + 1]).lower() if index + 1 < len(words) else ""
        if group and _should_end_caption(group, current, next_word, len(group) + 1, max_words):
            chunks.append(_clean(" ".join(group)))
            group = []
        group.append(word)
    if group:
        chunks.append(_clean(" ".join(group)))
    if len(chunks) > 1 and _word_count(chunks[-1]) <= 1:
        chunks[-2] = _clean(f"{chunks[-2]} {chunks[-1]}")
        chunks.pop()
    return chunks


def _word_count(value: str) -> int:
    return len(_words(value))


def _word_text(word) -> str:
    if word is None:
        return ""
    return _display_word(str(getattr(word, "word", ""))).lower()


def _should_end_caption(group: list[str], current: str, next_word: str, size_after_current: int, max_words: int) -> bool:
    if not group:
        return False
    if current in _LEADING_CONNECTORS and not _sticks_to_previous(group[-1], current):
        return True
    if len(group) >= 3 and current in _PHRASE_STARTERS and not _sticks_to_previous(group[-1], current):
        return True
    if group[-1] in _TRAILING_CONNECTORS:
        return False
    if size_after_current < 3:
        return False
    if size_after_current >= max_words and next_word in _LEADING_CONNECTORS:
        return False
    if size_after_current >= max_words:
        return True
    if size_after_current >= 4 and next_word in _PHRASE_STARTERS:
        return True
    return False


def _group_caption(words) -> TimedCaption:
    text = " ".join(word.word.strip() for word in words)
    durations = tuple(max(0.08, word.end - word.start) for word in words)
    return TimedCaption(start=max(0.0, words[0].start), end=words[-1].end + 0.30, text=_clean(text), word_durations=durations)


def _append_caption(captions: list[TimedCaption], caption: TimedCaption) -> None:
    if not caption.text:
        return
    if captions and caption.text.lower() == captions[-1].text.lower():
        return
    start = caption.start
    end = caption.end
    if captions and start < captions[-1].end - 0.05:
        previous = captions[-1]
        previous_end = max(previous.start + 0.28, start - 0.04)
        captions[-1] = TimedCaption(
            start=previous.start,
            end=previous_end,
            text=previous.text,
            word_durations=previous.word_durations,
        )
    if end <= start + 0.25:
        return
    captions.append(TimedCaption(start=start, end=end, text=caption.text, word_durations=caption.word_durations))


def _merge_orphan_captions(captions: list[TimedCaption]) -> list[TimedCaption]:
    if len(captions) < 2:
        return captions
    merged: list[TimedCaption] = []
    for caption in captions:
        if merged and _word_count(caption.text) <= 1:
            previous = merged[-1]
            text = f"{previous.text} {caption.text}".strip()
            merged[-1] = TimedCaption(
                start=previous.start,
                end=caption.end,
                text=_clean(text),
                word_durations=previous.word_durations + caption.word_durations,
            )
        else:
            merged.append(caption)
    return merged


def _hold_captions_during_pauses(captions: list[TimedCaption]) -> list[TimedCaption]:
    if not captions:
        return captions
    held: list[TimedCaption] = []
    for index, caption in enumerate(captions):
        end = caption.end
        if index + 1 < len(captions):
            next_start = captions[index + 1].start
            gap = next_start - end
            if gap > 0.08:
                end = max(end, next_start - 0.04)
        else:
            end += 0.35
        held.append(TimedCaption(caption.start, end, caption.text, caption.word_durations))
    return held


def _syllable_count(word: str) -> int:
    """Estimates syllables in an English or Devanagari word."""
    w = word.lower().strip(".,!?;:\"'()[]{}—")
    if not w:
        return 1
    # Devanagari aksharas
    if any("\u0900" <= ch <= "\u097f" for ch in w):
        aksharas = sum(1 for ch in w if ("\u0904" <= ch <= "\u0939" or "\u0958" <= ch <= "\u0961") and ch != "\u094d")
        return max(1, aksharas)
    
    # English syllable heuristic
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if w.endswith("e") and len(w) > 2 and not w.endswith("le") and not w.endswith("ee"):
        count = max(1, count - 1)
    if w.endswith("ed") and len(w) > 3 and count > 1:
        count = max(1, count - 1)
    return max(1, count)


def _word_timing_weight(word: str) -> float:
    raw = word.strip()
    clean_w = raw.lower().strip(".,!?;:\"'()[]{}—")
    if not clean_w:
        return 1.0
    sylls = _syllable_count(clean_w)
    length = len(clean_w)
    
    # Quick short function words get shorter duration weights
    short_stops = {
        "the", "a", "an", "in", "on", "at", "to", "of", "and", "or", "by", "for", "with",
        "is", "my", "your", "its", "her", "his", "our", "their", "so", "as", "if", "be", "no", "it",
        "म", "त", "र", "वा", "ले", "मा", "को", "का", "की", "बाट", "लाई"
    }
    if clean_w in short_stops:
        base = max(0.5, length * 0.25)
    else:
        base = sylls * 1.6 + length * 0.35

    # Natural speech pauses for punctuation
    if raw.endswith((",", ";", ":", "—")):
        base += 1.1
    elif raw.endswith((".", "!", "?", "...", "।", "॥")):
        base += 1.6
    return base


def _karaoke_line(words: list[str], durations: list[float]) -> str:
    parts: list[str] = []
    for index, word in enumerate(words):
        if index:
            parts.append(" ")
        centis = max(8, int(round(durations[index] * 100)))
        parts.append(f"{{\\kf{centis}}}{_escape_ass(_display_word(word))}")
    return "".join(parts)


def _caption_words_and_durations(caption: TimedCaption):
    words = _clean(caption.text).split()
    if not words:
        return [], []
    durations = list(caption.word_durations[: len(words)])
    if len(durations) < len(words):
        total_time = max(0.5, caption.end - caption.start)
        # Natural spoken time accounts for ~88-92% of the scene duration, leaving quiet breath pause
        spoken_time = max(0.4, min(total_time, total_time * 0.90 if len(words) > 3 else total_time * 0.94))
        weights = [_word_timing_weight(w) for w in words]
        w_sum = sum(weights) or 1.0
        durations = [max(0.10, round((w / w_sum) * spoken_time, 3)) for w in weights]
    return words, durations


def _poetry_caption_text(caption: TimedCaption) -> str:
    words, durations = _caption_words_and_durations(caption)
    if not words:
        return ""
    if len(words) <= 6:
        return _karaoke_line(words, durations)
        
    midpoint = max(1, min(len(words) - 1, round(len(words) * 0.52)))
    l1_words, l1_durs = words[:midpoint], durations[:midpoint]
    l2_words, l2_durs = words[midpoint:], durations[midpoint:]

    # Line 1 renders from t=0 of the event
    line1_text = _karaoke_line(l1_words, l1_durs)
    
    # Line 2 MUST wait until Line 1 finishes to eliminate double-speed premature highlighting
    line1_total_centis = sum(max(8, int(round(d * 100))) for d in l1_durs)
    line2_parts = [f"{{\\k{line1_total_centis}}}"]
    for idx, w in enumerate(l2_words):
        centis = max(8, int(round(l2_durs[idx] * 100)))
        line2_parts.append(f"{{\\kf{centis}}}{_escape_ass(_display_word(w))}")
    line2_text = " ".join(line2_parts)
    
    return line1_text + r"\N" + line2_text


def _reference_caption_text(caption: TimedCaption) -> str:
    return _poetry_caption_text(caption)


def _creative_caption_events(caption: TimedCaption, caption_style: str = "creative_stack", video_format: str = "portrait") -> list[str]:
    words = [_display_word(word) for word in _clean(caption.text).split() if _display_word(word)]
    if not words:
        return []
    if caption_style == "creative_stack":
        return _creative_stack_events(caption, words, video_format)
        rows = _creative_rows(words, caption_style)
        if len(rows) > 2:
            rows = [rows[0], (rows[1][0], " ".join(text for _style, text in rows[1:]))]
        y_start = _creative_y_start(rows, caption_style, video_format)
    center_x, _ = frame_center(video_format)
    events: list[str] = []
    groups = [text for _style, text in rows]
    starts = _progressive_line_starts(caption, groups, minimum_hold=1.05)
    for index, (style, text) in enumerate(rows):
        gap = _creative_gap(caption_style, video_format)
        y = y_start + index * gap
        scale = _fit_scale(text, _creative_scale(caption_style, index), style)
        events.append(
            f"Dialogue: 1,{_stamp(starts[index])},{_stamp(caption.end)},{style},,0,0,0,,"
            f"{{\\pos({center_x},{y})\\fad(80,100)\\t(0,180,\\fscx{scale}\\fscy{scale})}}{_escape_ass(text)}\n"
        )
    return events


def _creative_stack_events(caption: TimedCaption, words: list[str], video_format: str) -> list[str]:
    groups = _spoken_two_line_groups(words)
    events: list[str] = []
    width, height = frame_size(video_format)
    center_x = width // 2
    base_y = int(height * (0.76 if video_format == "landscape" else 0.597))
    second_gap = int(height * (0.048 if video_format == "landscape" else 0.0375))
    entries = [
        ("CreativeScript", groups[0], center_x, base_y, 100),
        ("CreativeYellow", groups[1], center_x, base_y + second_gap, 106),
    ]
    starts = _progressive_line_starts(caption, groups, minimum_hold=1.25)
    for index, (style, text, x, y, scale) in enumerate(entries):
        if not text:
            continue
        start = starts[index]
        end = caption.end
        jitter = _transition_jitter(text)
        blur = 5 + jitter
        fit_scale = _fit_scale(text, scale, style)
        events.append(
            f"Dialogue: 1,{_stamp(start)},{_stamp(end)},{style},,0,0,0,,"
            f"{{\\pos({x},{y})\\fad(80,100)\\blur{blur}\\t(0,170,\\blur0.25\\fscx{fit_scale}\\fscy{fit_scale})"
            f"\\t({max(180, int((end - start) * 1000) - 150)},{max(260, int((end - start) * 1000))},\\blur{blur + 1})}}"
            f"{_escape_ass(text.lower())}\n"
        )
    return events


def _spoken_two_line_groups(words: list[str]) -> list[str]:
    lowered = [word.lower() for word in words]
    if not lowered:
        return ["", ""]
    if len(lowered) == 1:
        return [lowered[0], ""]
    midpoint = max(1, min(len(lowered) - 1, round(len(lowered) * 0.52)))
    return [" ".join(lowered[:midpoint]), " ".join(lowered[midpoint:])]


def _three_line_breaks(words: list[str]) -> tuple[int, int]:
    total = len(words)
    if total <= 4:
        return 1, 2
    if total <= 7:
        return 2, 4
    first = max(2, round(total * 0.30))
    second = max(first + 1, round(total * 0.56))
    return min(first, total - 2), min(second, total - 1)


def _line_durations(caption: TimedCaption, groups: list[str]) -> list[float]:
    word_durations = list(caption.word_durations)
    if not word_durations:
        total = max(0.3, caption.end - caption.start)
        counts = [max(1, _word_count(group)) for group in groups]
        count_sum = sum(counts)
        return [total * count / count_sum for count in counts]
    durations: list[float] = []
    cursor = 0
    for group in groups:
        count = max(1, _word_count(group))
        chunk = word_durations[cursor : cursor + count]
        durations.append(sum(chunk) if chunk else 0.35 * count)
        cursor += count
    return durations


def _progressive_line_starts(caption: TimedCaption, groups: list[str], minimum_hold: float) -> list[float]:
    durations = _line_durations(caption, groups)
    starts: list[float] = []
    cursor = caption.start
    latest_start = max(caption.start, caption.end - minimum_hold)
    for index, group in enumerate(groups):
        if not group:
            starts.append(caption.start)
            continue
        starts.append(min(cursor, latest_start))
        cursor += durations[index]
    return starts


def _transition_jitter(text: str) -> int:
    return sum(ord(ch) for ch in text) % 3


def _stack_groups(words: list[str]) -> dict[str, str]:
    lowered = [word.lower() for word in words]
    hero_index = _stack_emphasis_index(lowered)
    connector_words = {"of", "to", "for", "in", "at", "with", "and"}
    connector = ""
    tail = lowered[hero_index + 1 :]
    if tail and tail[0] in connector_words:
        connector = tail[0]
        tail = tail[1:]
    before = lowered[:hero_index]
    script = before[0] if before else lowered[0]
    lead = " ".join(before[1:]) if before else ""
    if not tail and hero_index + 1 < len(lowered):
        tail = lowered[hero_index + 1 :]
    if len(tail) >= 2:
        tail_top = " ".join(tail[:-1])
        tail_bottom = tail[-1]
    else:
        tail_top = " ".join(tail)
        tail_bottom = ""
    return {
        "script": script,
        "lead": lead,
        "hero": lowered[hero_index],
        "connector": connector,
        "tail_top": tail_top,
        "tail_bottom": tail_bottom,
    }


def _stack_emphasis_index(words: list[str]) -> int:
    for phrase_word in ("end", "love", "heart", "home", "you", "enough", "peace", "stay", "found"):
        if phrase_word in words:
            return words.index(phrase_word)
    return _emphasis_index(words)


def _creative_rows(words: list[str], caption_style: str = "creative_stack") -> list[tuple[str, str]]:
    if caption_style == "creative_compact":
        return _creative_compact_rows(words)
    if caption_style == "creative_bigword":
        return _creative_bigword_rows(words)
    if caption_style == "creative_script":
        return _creative_script_rows(words)
    if caption_style == "creative_quote":
        return _creative_quote_rows(words)
    return _creative_stack_rows(words)


def _creative_stack_rows(words: list[str]) -> list[tuple[str, str]]:
    if len(words) == 1:
        return [("CreativeYellow", words[0].lower())]
    if len(words) == 2:
        return [("CreativeScript", words[0].lower()), ("CreativeYellow", words[1].lower())]
    emphasis = _emphasis_index(words)
    before = words[:emphasis]
    after = words[emphasis + 1 :]
    rows: list[tuple[str, str]] = []
    if before:
        rows.append(("CreativeScript", " ".join(before[:2]).lower()))
    if len(before) > 2:
        rows.append(("CreativeBold", " ".join(before[2:]).lower()))
    rows.append(("CreativeYellow", words[emphasis].lower()))
    if after:
        tail = " ".join(after).lower()
        rows.append(("CreativeBold", tail))
    return rows[:4]


def _creative_bigword_rows(words: list[str]) -> list[tuple[str, str]]:
    emphasis = _emphasis_index(words)
    before = " ".join(words[:emphasis]).lower()
    after = " ".join(words[emphasis + 1 :]).lower()
    rows: list[tuple[str, str]] = []
    if before:
        rows.append(("CreativeBold", before))
    rows.append(("CreativeYellow", words[emphasis].lower()))
    if after:
        rows.append(("CreativeBold", after))
    return rows[:3]


def _creative_script_rows(words: list[str]) -> list[tuple[str, str]]:
    text = " ".join(words).lower()
    if len(words) <= 3:
        return [("CreativeScript", text)]
    return [("CreativeScript", " ".join(words[:2]).lower()), ("CreativeBold", " ".join(words[2:]).lower())]


def _creative_quote_rows(words: list[str]) -> list[tuple[str, str]]:
    emphasis = _emphasis_index(words)
    lead = " ".join(words[:emphasis]).lower()
    rows: list[tuple[str, str]] = []
    if lead:
        rows.append(("CreativeTiny", lead))
    rows.append(("CreativeYellow", words[emphasis].lower()))
    tail = " ".join(words[emphasis + 1 :]).lower()
    if tail:
        rows.append(("CreativeTiny", tail))
    return rows[:3]


def _creative_compact_rows(words: list[str]) -> list[tuple[str, str]]:
    emphasis = _emphasis_index(words)
    before = " ".join(words[:emphasis]).lower()
    after = " ".join(words[emphasis + 1 :]).lower()
    tail = " ".join(part for part in (words[emphasis].lower(), after) if part)
    rows: list[tuple[str, str]] = []
    if before:
        rows.append(("CreativeBold", before))
    rows.append(("CreativeYellow", tail))
    return rows


def _creative_y_start(rows: list[tuple[str, str]], caption_style: str, video_format: str) -> int:
    _width, height = frame_size(video_format)
    if caption_style == "creative_quote":
        return int(height * 0.50) - (len(rows) - 1) * int(height * 0.022)
    if caption_style == "creative_compact":
        return int(height * 0.545) - (len(rows) - 1) * int(height * 0.013)
    return int(height * 0.535) - (len(rows) - 1) * int(height * 0.016)


def _creative_gap(caption_style: str, video_format: str) -> int:
    _width, height = frame_size(video_format)
    if caption_style == "creative_quote":
        return int(height * 0.035)
    if caption_style == "creative_compact":
        return int(height * 0.022)
    return int(height * 0.026)


def _creative_scale(caption_style: str, index: int) -> int:
    if caption_style == "creative_quote":
        return 96 if index == 1 else 90
    return 104 if index == 0 else 100


def _fit_scale(text: str, base_scale: int, style: str) -> int:
    length = len(text)
    if style == "CreativeYellow":
        if length > 18:
            return min(base_scale, 76)
        if length > 13:
            return min(base_scale, 88)
    if style in {"CreativeBold", "CreativeTiny"} and length > 28:
        return min(base_scale, 82)
    if style == "CreativeScript" and length > 24:
        return min(base_scale, 84)
    return base_scale


def _emphasis_index(words: list[str]) -> int:
    skip = {"a", "an", "and", "at", "but", "for", "in", "is", "it", "of", "or", "the", "to", "with", "your", "my", "our"}
    for index in range(len(words) - 1, -1, -1):
        if words[index].lower() not in skip:
            return index
    return max(0, len(words) - 1)


def _caption_text(value: str, preset: str = "modern") -> str:
    words = value.split()
    if len(words) > 7:
        midpoint = len(words) // 2
        value = " ".join(words[:midpoint]) + r"\N" + " ".join(words[midpoint:])
    return value.upper()


def _reference_caption_text(caption: TimedCaption) -> str:
    words, durations = _caption_words_and_durations(caption)
    if not words:
        return ""
    if len(words) <= 7:
        return _karaoke_line(words, durations)
    midpoint = max(1, min(len(words) - 1, round(len(words) * 0.52)))
    line_1 = _karaoke_line(words[:midpoint], durations[:midpoint])
    line_2 = _karaoke_line(words[midpoint:], durations[midpoint:])
    return f"{line_1}\\N{line_2}"


def _escape_ass(value: str) -> str:
    return value.replace("{", "").replace("}", "")


def _display_word(value: str) -> str:
    return value.rstrip(".,!?;:।॥")


def _sticks_to_previous(previous: str, current: str) -> bool:
    return (previous, current) in _STICKY_CONNECTOR_PAIRS


_LEADING_CONNECTORS = {
    "to",
    "for",
    "of",
    "in",
    "on",
    "at",
    "with",
    "without",
    "from",
    "into",
    "through",
    "because",
    "that",
}

_TRAILING_CONNECTORS = {"the", "a", "an", "your", "my", "our", "their", "his", "her", "its", "this", "that"}

_PHRASE_STARTERS = {
    "to",
    "for",
    "because",
    "when",
    "while",
    "until",
    "before",
    "after",
    "and",
    "but",
    "so",
    "is",
    "are",
    "was",
    "were",
}

_STICKY_CONNECTOR_PAIRS = {
    ("searching", "for"),
    ("looking", "for"),
    ("waiting", "for"),
    ("asking", "for"),
    ("hoping", "for"),
    ("praying", "for"),
    ("made", "of"),
    ("part", "of"),
    ("full", "of"),
    ("believe", "in"),
}


def _clean(value: str) -> str:
    value = "".join(ch for ch in value if ch in "\n\t " or not unicodedata.category(ch).startswith("C"))
    return re.sub(r"\s+", " ", value).strip()


def _timed_captions_from_script_rows_even(audio_path: Path, script: str) -> list[TimedCaption]:
    chunk_captions = _timed_captions_from_tts_chunks(audio_path)
    if chunk_captions:
        return chunk_captions
    rows = _caption_rows(script)
    if not rows:
        return []
    total = _audio_duration(audio_path)
    weights = [_caption_timing_weight(row) for row in rows]
    scale = total / max(1.0, sum(weights))
    captions: list[TimedCaption] = []
    cursor = 0.0
    for index, row in enumerate(rows):
        end = total if index == len(rows) - 1 else min(total, cursor + weights[index] * scale)
        word_count = max(1, _word_count(row))
        word_slot = max(0.08, (end - cursor) / word_count)
        captions.append(TimedCaption(cursor, end, row, tuple([word_slot] * word_count)))
        cursor = end
    return captions


def _timed_captions_from_tts_chunks(audio_path: Path) -> list[TimedCaption]:
    manifest = audio_path.with_suffix(".chunks.json")
    if not manifest.exists():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return []
    captions: list[TimedCaption] = []
    for item in data.get("items", []):
        text = _clean(str(item.get("text", "")))
        if not text:
            continue
        try:
            start = max(0.0, float(item["start"]))
            end = max(start + 0.25, float(item["end"]))
        except Exception:
            continue
        speech_words = max(1, _word_count(str(item.get("speech_text") or text)))
        slot = max(0.08, (end - start) / speech_words)
        captions.append(TimedCaption(start=start, end=end, text=text, word_durations=tuple([slot] * max(1, _word_count(text)))))
    return _hold_captions_during_pauses(captions)


def _audio_duration(path: Path) -> float:
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
        if completed.returncode == 0:
            return max(1.0, float(completed.stdout.strip()))
    except Exception:
        pass
    return 1.0


def _caption_timing_weight(row: str) -> float:
    words = max(1, _word_count(row))
    weight = max(1.0, words ** 0.92)
    stripped = row.strip()
    if stripped.endswith(("।", "॥", ".", "?", "!")):
        weight += 0.55
    if stripped.endswith(("…", "...")):
        weight += 0.85
    if "," in stripped or ";" in stripped or ":" in stripped:
        weight += 0.18
    return weight


def _contains_devanagari(value: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in value)


def _words(value: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", _clean(value)):
        token = raw.strip(" \t\r\n.,!?;:।॥\"'()[]{}<>“”‘’")
        if token and any(ch.isalnum() or "\u0900" <= ch <= "\u097f" for ch in token):
            tokens.append(token)
    return tokens


def _stamp(seconds: float) -> str:
    total = int(seconds)
    centis = int((seconds - total) * 100)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"

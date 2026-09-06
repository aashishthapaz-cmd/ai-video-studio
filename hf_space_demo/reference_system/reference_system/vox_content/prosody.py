from __future__ import annotations

import re


REFERENCE_STYLE = "reference_documentary"

# Words and phrases that tend to carry narrative weight in the supplied
# documentary-style reference. They drive subtle per-chunk expressiveness;
# they are never altered in the visible text.
DRAMATIC_TERMS = frozenset(
    {
        "अलौकिक",
        "अदृश्य",
        "गहिरो",
        "रहस्य",
        "गौरवपूर्ण",
        "विश्वविजेता",
        "शक्तिशाली",
        "वास्तविक",
        "विशाल",
        "जीवित",
        "अझै",
        "विडम्बना",
        "अद्भुत",
        "वीरता",
        "प्रतीक्षा",
        "इतिहास",
        "सोध्छ",
    }
)

# Discourse turns in the reference commonly receive a small breath before
# the next thought rather than a large dramatic silence.
BREATH_BEFORE = (
    "तर विडम्बना",
    "तर",
    "अझै पनि",
    "यहीँबाट",
    "जब तपाईं",
    "संसारभर",
)


def prepare_reference_prosody(text: str, *, style: str = REFERENCE_STYLE, breaths: bool = True) -> str:
    """Shape input punctuation for natural documentary narration.

    This function intentionally makes only punctuation/whitespace changes. The
    editor and captions continue to use the original canonical text, while the
    hidden model input receives controlled breath cues.
    """
    value = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"[ \t]+", " ", value)
    if style in {"plain", "neutral", "verbatim", "verbatim_narration"} or not breaths:
        return value

    # Preserve paragraph boundaries as a slightly longer breath cue.
    value = re.sub(r"\n{2,}", " … … ", value)
    # An em dash in the source is a rhetorical turn, not a literal dash for
    # the tokenizer; map it to the reference-style low-energy pause.
    value = re.sub(r"\s*—\s*", " … ", value)
    value = re.sub(r"\n", " ", value)

    # A short ellipsis before a discourse turn is closer to the supplied
    # narration than inserting a full stop or a long synthetic silence.
    for phrase in BREATH_BEFORE:
        value = re.sub(
            rf"(?<=[।!?])\s+(?={re.escape(phrase)})",
            " … ",
            value,
        )

    # Normalize spacing around the punctuation the Nepali model understands.
    value = re.sub(r"\s+([।॥.!?,;:])", r"\1", value)
    value = re.sub(r"([।॥.!?,;:])(?=[^\s])", r"\1 ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def chunk_is_dramatic(text: str) -> bool:
    """Return whether a chunk contains reference-like narrative emphasis."""
    words = set(re.findall(r"[\w\u0900-\u097f]+", text, flags=re.UNICODE))
    return bool(words & DRAMATIC_TERMS) or text.rstrip().endswith(("?", "!"))


def chunk_is_soft_transition(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith((",", ";", ":", "…")) or stripped.startswith(("तर", "अझै"))

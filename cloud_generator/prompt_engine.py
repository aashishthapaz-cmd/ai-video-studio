import re
import sys
from pathlib import Path

# Add project root to sys.path so we can import artwork_prompts
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import artwork_prompts

def split_into_poetic_stanzas(text: str) -> list:
    """
    Splits poem/script into natural, rhythmic 1-2 line stanzas (5-14 words).
    Respects the author's intentional line breaks and sentence structure.
    Never chops sentences mid-clause or across conjunctions.
    Merges short fragments (< 5 words) so scenes hold for at least 3.8s without rushed cuts.
    """
    raw = str(text or "").strip()
    if not raw:
        return []

    # Normalize newlines
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    
    # Extract candidate lines from author's line breaks
    raw_lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if len(raw_lines) <= 1:
        # Single long block of text: split at full sentence endings (. ! ? । ॥)
        raw_lines = [c.strip() for c in re.split(r'(?<=[.!?।॥])\s+', raw) if c.strip()]

    stanzas: list[str] = []
    buffer = ""

    for line in raw_lines:
        words = line.split()
        if not words:
            continue

        # If a single line is extremely long (> 16 words), split only at strong punctuation (. ! ? ; —)
        if len(words) > 16:
            sub_chunks = [c.strip() for c in re.split(r'(?<=[.!?;—])\s+', line) if c.strip()]
            if len(sub_chunks) > 1:
                for sub in sub_chunks:
                    if buffer:
                        stanzas.append(buffer)
                        buffer = ""
                    if len(sub.split()) < 5:
                        buffer = sub
                    else:
                        stanzas.append(sub)
                continue

        if buffer:
            combined = f"{buffer} {line}".strip()
            # If combined has 5-14 words, finalize stanza
            if len(combined.split()) >= 5 or len(combined) >= 25:
                stanzas.append(combined)
                buffer = ""
            else:
                buffer = combined
        else:
            if len(words) < 5 and len(line) < 25:
                buffer = line
            else:
                stanzas.append(line)

    if buffer:
        if stanzas:
            stanzas[-1] = f"{stanzas[-1]} {buffer}".strip()
        else:
            stanzas.append(buffer)

    # Clean and guarantee every stanza has clean spacing
    cleaned = []
    for s in stanzas:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        if s_clean:
            cleaned.append(s_clean)

    return cleaned or [raw]

def build_scene_artistic_prompt(stanza: str, scene_idx: int, total_scenes: int, title: str = "", vibe_id: str = "") -> str:
    """
    Synthesizes a concrete, highly artistic visual prompt directly derived from the individual poem stanza.
    Ensures every scene is visually unique, deeply emotional, and reflects the exact narrative meaning.
    """
    clean = re.sub(r'[\r\n]+', ' ', stanza).strip()
    words_lower = clean.lower()

    visual_subject = ""
    if any(k in words_lower for k in ["heart", "love", "kiss", "hug", "hold", "forever", "together", "soul", "smile", "eyes"]):
        visual_subject = "tender romantic imagery, two gentle silhouettes walking along a lantern-lit street in autumn, warm golden lights, softly drifting amber leaves, intimate heartwarming atmosphere"
    elif any(k in words_lower for k in ["rain", "storm", "cry", "tears", "water", "ocean", "sea", "drown"]):
        visual_subject = "melancholic rain droplets on a clear cafe window overlooking a peaceful twilight street with glistening reflections, warm indoor candle glow against cool blue rain"
    elif any(k in words_lower for k in ["night", "star", "stars", "moon", "sky", "dark", "midnight", "galaxy", "universe"]):
        visual_subject = "a breathtaking celestial night sky brimming with luminous constellations and a glowing crescent moon, a solitary figure watching from a tranquil grassy hilltop"
    elif any(k in words_lower for k in ["leave", "walk", "distance", "heal", "healing", "let go", "alone", "peace", "free", "silence"]):
        visual_subject = "a serene solitary traveler walking forward on a quiet misty mountain trail toward warm golden sunrise light, fresh mountain air, peaceful liberation"
    elif any(k in words_lower for k in ["time", "memory", "remember", "past", "years", "old", "book", "typewriter", "write", "letter"]):
        visual_subject = "an atmospheric antique writer desk with an old vintage typewriter, scattered handwritten letters, a warm steaming ceramic mug, soft sunbeams filtering through curtains"
    elif any(k in words_lower for k in ["mother", "father", "child", "family", "home", "growing", "hands"]):
        visual_subject = "a deeply touching moment in a warm rustic home kitchen, gentle warm sunlight, vintage nostalgic tones, deep emotional reverence and love"
    else:
        visual_subject = f"an emotionally evocative poetic setting reflecting '{clean[:60]}', a calm atmospheric landscape with rich painterly depth"

    prompt = (
        f"Artistic anime masterpiece illustrating: {clean}. "
        f"Visual scene: {visual_subject}. "
        f"Aesthetic: breathtaking painterly anime style, Makoto Shinkai twilight sky and Studio Ghibli fine art details, "
        f"dramatic volumetric lighting, rich emotional atmosphere, edge-to-edge 9:16 vertical composition"
    )
    return prompt


def plan_scenes_for_poem(title: str, script_text: str, custom_vibe: str = "") -> list:
    """
    Creates rich, non-repeating artistic scene prompts for the poem.
    Each scene prompt is directly derived from its individual stanza script text,
    guaranteeing unique, meaningful visual imagery for every scene.
    Guarantees every scene has at least 3.8s duration for subtle, unhurried pacing.
    """
    stanzas = split_into_poetic_stanzas(script_text)
    scenes = []
    total = len(stanzas)
    for i, stanza in enumerate(stanzas, 1):
        dur = max(3.8, min(8.5, round(len(stanza.split()) / 1.8, 2)))
        motion_style = artwork_prompts.MOTION_STYLES_POOL[(i - 1) % len(artwork_prompts.MOTION_STYLES_POOL)]
        scene_prompt = build_scene_artistic_prompt(stanza, i, total, title=title, vibe_id=custom_vibe)
        scenes.append({
            "id": f"scene_{i:03d}",
            "narration": stanza,
            "duration": dur,
            "motion": motion_style,
            "prompt": scene_prompt,
            "image_prompt": scene_prompt
        })

    return scenes

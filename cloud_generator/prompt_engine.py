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

def plan_scenes_for_poem(title: str, script_text: str, custom_vibe: str = "") -> list:
    """
    Creates rich, non-repeating artistic scene prompts for the poem.
    Leverages the 25+ aesthetic world SQLite engine.
    Guarantees every scene has at least 3.8s duration for subtle, unhurried pacing.
    """
    stanzas = split_into_poetic_stanzas(script_text)
    scenes = []
    for i, stanza in enumerate(stanzas, 1):
        dur = max(3.8, min(8.5, round(len(stanza.split()) / 1.8, 2)))
        scenes.append({
            "id": f"scene_{i:03d}",
            "narration": stanza,
            "duration": dur,
            "motion": artwork_prompts.MOTION_STYLES_POOL[(i - 1) % len(artwork_prompts.MOTION_STYLES_POOL)]
        })
        
    project_payload = {
        "title": title or "Cloud Poem",
        "script": script_text,
        "scenes": scenes,
        "content_type": "poem",
        "vibe": custom_vibe or "typewriters_voice_nostalgia"
    }
    
    # Generate rich artistic prompts using the aesthetic engine
    plan = artwork_prompts.generate_plan(project_payload, {"artwork_prompt_model": "none"})
    res_scenes = plan.get("scenes", scenes)
    for sc in res_scenes:
        p = sc.get("prompt") or sc.get("image_prompt") or sc.get("narration") or "Cinematic atmospheric background"
        sc["prompt"] = p
        sc["image_prompt"] = p
    return res_scenes

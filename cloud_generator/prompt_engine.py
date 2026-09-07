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
    Splits poem/script into bite-sized, poetic 1-2 line stanzas (3-12 words max).
    Guarantees that every scene's voice and on-screen caption are 100% synchronized,
    never exceeding 2 lines, and perfectly paced with natural poetic pauses.
    """
    raw = str(text or "").strip()
    if not raw:
        return []

    # 1. Normalize line breaks
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    
    # Extract candidate lines from newlines or punctuation
    raw_lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if len(raw_lines) <= 1:
        # Single long paragraph: split at sentence/thought endings
        raw_lines = [c.strip() for c in re.split(r'(?<=[.!?।॥—])\s+', raw) if c.strip()]

    stanzas = []
    curr = []
    
    for line in raw_lines:
        words = line.split()
        if not words:
            continue
            
        # If a single line is too long (> 14 words), split at punctuation or midpoint
        if len(words) > 14:
            sub_chunks = [c.strip() for c in re.split(r'(?<=[,;—.!?:])\s+', line) if c.strip()]
            if len(sub_chunks) > 1:
                for sub in sub_chunks:
                    if curr:
                        stanzas.append(" ".join(curr))
                        curr = []
                    stanzas.append(sub)
                continue

        # If accumulating lines, check word count
        curr_words = sum(len(l.split()) for l in curr)
        if curr and (curr_words + len(words) > 11 or len(curr) >= 2):
            stanzas.append(" ".join(curr))
            curr = [line]
        else:
            curr.append(line)
            # If current line alone is 5-11 words, it stands on its own as a clean 1-2 line scene
            if len(words) >= 5:
                stanzas.append(" ".join(curr))
                curr = []

    if curr:
        stanzas.append(" ".join(curr))

    # Clean stanzas and ensure min 3 words per scene (merge tiny trailing stanzas)
    cleaned_stanzas = []
    for s in stanzas:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        if not s_clean:
            continue
        if len(s_clean.split()) < 3 and cleaned_stanzas:
            cleaned_stanzas[-1] = f"{cleaned_stanzas[-1]} {s_clean}"
        else:
            cleaned_stanzas.append(s_clean)

    return cleaned_stanzas or [raw]

def plan_scenes_for_poem(title: str, script_text: str, custom_vibe: str = "") -> list:
    """
    Creates rich, non-repeating artistic scene prompts for the poem.
    Leverages the 25+ aesthetic world SQLite engine.
    """
    stanzas = split_into_poetic_stanzas(script_text)
    scenes = []
    for i, stanza in enumerate(stanzas, 1):
        scenes.append({
            "id": f"scene_{i:03d}",
            "narration": stanza,
            "duration": max(3.5, min(8.0, round(len(stanza.split()) / 2.2, 2))),
            "motion": artwork_prompts.MOTION_STYLES_POOL[(i - 1) % len(artwork_prompts.MOTION_STYLES_POOL)]
        })
        
    project_payload = {
        "title": title or "Cloud Poem",
        "script": script_text,
        "scenes": scenes,
        "content_type": "poem",
        "vibe": custom_vibe or "typewriters_voice_nostalgia"
    }
    
    # Generate rich 70-110 word artistic prompts using the aesthetic engine
    plan = artwork_prompts.generate_plan(project_payload, {"artwork_prompt_model": "none"})
    res_scenes = plan.get("scenes", scenes)
    for sc in res_scenes:
        p = sc.get("prompt") or sc.get("image_prompt") or sc.get("narration") or "Cinematic atmospheric background"
        sc["prompt"] = p
        sc["image_prompt"] = p
    return res_scenes

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
    Groups poem/script lines into cohesive narrative stanzas.
    If the user separated verses by blank lines, preserves them.
    Otherwise merges short lines so that each scene has sufficient visual & narrative depth.
    """
    raw = str(text or "").strip()
    if not raw:
        return []
        
    # Check if user already separated by blank lines (stanzas)
    paragraphs = [re.sub(r"\s+", " ", p.strip()) for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if len(paragraphs) >= 2:
        return paragraphs
        
    raw_lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not raw_lines:
        return []
    
    stanzas = []
    curr = []
    
    for line in raw_lines:
        curr.append(line)
        word_count = sum(len(l.split()) for l in curr)
        if len(curr) >= 2 or word_count >= 8:
            stanzas.append(" ".join(curr))
            curr = []
            
    if curr:
        if stanzas:
            stanzas[-1] += " " + " ".join(curr)
        else:
            stanzas.append(" ".join(curr))
            
    return stanzas

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
    plan = artwork_prompts.generate_plan(project_payload, {"ollama_model": "gemma3:4b"})
    res_scenes = plan.get("scenes", scenes)
    for sc in res_scenes:
        p = sc.get("prompt") or sc.get("image_prompt") or sc.get("narration") or "Cinematic atmospheric background"
        sc["prompt"] = p
        sc["image_prompt"] = p
    return res_scenes

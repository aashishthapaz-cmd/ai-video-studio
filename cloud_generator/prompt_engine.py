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
    Synthesizes a concrete, highly artistic SCENIC visual prompt directly derived from the individual poem stanza.
    Focuses entirely on sweeping landscapes, evocative environments, atmospheric weather, and poetic natural vistas.
    Strictly avoids big anime character faces or close-ups, ensuring rich poetic feelings are expressed
    through environmental storytelling and breathtaking landscape scenery.
    """
    clean = re.sub(r'[\r\n]+', ' ', stanza).strip()
    words_lower = clean.lower()

    # Time-of-day progression across scenes to create a natural poetic visual journey
    # e.g., dawn / morning -> afternoon / sunlight -> golden hour -> twilight / starlight
    progress = (scene_idx - 1) / max(1, total_scenes - 1)
    if progress < 0.28:
        lighting_prog = "soft warm golden morning dawn, gentle rising sun rays cutting through light mist"
    elif progress < 0.58:
        lighting_prog = "warm radiant afternoon sunlight, crystal clear sky with soft drifting white clouds"
    elif progress < 0.85:
        lighting_prog = "breathtaking golden hour sunset glow, warm amber and apricot light washing over the horizon"
    else:
        lighting_prog = "enchanting twilight blue hour, deep indigo sky with soft violet and amber horizon glow, quiet starlight"

    # Semantic Emotion & Theme Analysis to Scenic Landscape Mapping
    # 1. Living honestly, self-respect, not impressing others, boundaries, choosing peace, integrity
    if any(k in words_lower for k in ["disappoint", "honest", "boundaries", "choose your peace", "peace", "impress", "criticism", "misunderstood", "real", "mask", "myself", "truth"]):
        scenic_envs = [
            "a solitary traveler in the distance seen from behind walking along a peaceful diverging mountain path at sunrise, golden god rays piercing through misty pines and wildflowers, vast alpine horizon, choosing one's honest path",
            "a serene reflective figure resting peacefully beneath a majestic ancient cedar tree on a quiet coastal cliff, gazing at a calm glass-like ocean at golden hour, safe unshakeable sanctuary",
            "a gentle wanderer standing in an expansive rolling wildflower meadow at golden hour, looking up at soft pastel clouds with a deep sense of relief and inner peace",
            "a solitary lighthouse keeper standing on the open balcony of an ancient stone cliffside lighthouse at dawn, watching the calm endless sea in tranquil self-reliance"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "quiet self-reclamation, honest integrity, and choosing one's peaceful path"

    # 2. People-pleasing, draining, burdens, letting go, release, healing, silence
    elif any(k in words_lower for k in ["people-pleasing", "drain", "save you", "burden", "heavy", "tired", "let go", "heal", "healing", "silence", "free", "release", "surrender", "alone"]):
        scenic_envs = [
            "a solitary reflective figure sitting quietly by a twilight lakeside, watching glowing amber and crimson leaves drift gently across calm reflective water, releasing heavy burdens into the wind",
            "a lone wanderer walking beside a tranquil winding river in a misty valley after soft rain, mist rising from cool waters, profound calm and gentle emotional release",
            "a peaceful figure standing on a breezy grassy hilltop at dusk, watching hundreds of glowing dandelion seeds drift away into an expansive pastel twilight sky",
            "a weary traveler resting beside a secluded mossy forest pool, dipping hands into the crystal-clear healing water under soft dappled sunbeams"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "releasing heavy burdens into the wind, emotional catharsis, and gentle healing"

    # 3. Pride, belief, encouragement, dreams, worth, rising, soaring
    elif any(k in words_lower for k in ["proud", "believe", "dreams", "achieve", "worth", "stumble", "succeed", "capable", "small", "rise", "shine", "fly", "courage"]):
        scenic_envs = [
            "a distant wanderer standing atop a sunlit mountain summit with open arms, gazing at the golden sunrise breaking over rolling cloud waves, soaring belief and boundless potential",
            "a traveler walking along a sun-drenched coastal path lined with blooming jacaranda trees, overlooking a sparkling azure sea at dawn, radiant optimism and quiet pride",
            "a gentle figure looking across a crystal-clear alpine lake reflecting towering sunlit snow peaks, fresh mountain breeze, deep inspiring courage",
            "a lone climber pausing on an awe-inspiring panoramic cliff overlook to watch the first golden dawn rays illuminate the world below"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "unwavering belief, quiet pride, and radiant uplifting hope"

    # 4. Father, mother, family, sacrifice, roots, heritage, generations
    elif any(k in words_lower for k in ["father", "mother", "child", "family", "held me", "arms", "gave up", "remember", "home", "growing", "hands", "parent"]):
        scenic_envs = [
            "a loving father and young child holding hands, seen from behind walking together down a sunlit autumn country lane beneath towering golden oak trees, deep quiet gratitude",
            "a warm rustic wooden porch of a countryside farmhouse at sunset, a glowing amber lantern hanging beside empty weathered rocking chairs looking over quiet golden hills",
            "an ancient weathered stone bridge over a quiet flowing forest stream, two generations walking side by side across fallen autumn leaves in soft warm sunbeams",
            "a peaceful cottage garden bathed in warm late-afternoon golden glow, blooming hydrangeas along a white picket fence, timeless nostalgic warmth and roots"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "deep quiet gratitude, enduring protective strength, and timeless nostalgic warmth"

    # 5. Rain, tears, grief, heartache, sadness, pain
    elif any(k in words_lower for k in ["rain", "crying", "tears", "pain", "hurt", "broken", "loss", "mourn", "storm", "drown", "water"]):
        scenic_envs = [
            "a solitary figure holding an umbrella walking down a quiet rain-washed historic cobblestone street at blue hour dusk, glowing streetlamps casting amber reflections on wet stone",
            "a lone reflective figure standing at the end of a wooden dock over a calm misty lake during gentle rainfall, ripples expanding in cool blue and slate grey tones",
            "a moody windswept coastal bluff with sea spray under dramatic storm clouds parting to reveal soft slivers of pale silver sunlight, peaceful quiet sorrow",
            "a quiet figure sitting under a sheltered wooden garden arbor watching gentle rain drops fall onto lush green leaves and water lilies in a pond"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "cleansing melancholic sorrow, quiet reflection, and poignant beauty"

    # 6. Night, stars, moon, galaxy, celestial wonder
    elif any(k in words_lower for k in ["night", "star", "stars", "moon", "sky", "dark", "midnight", "galaxy", "universe", "cosmos"]):
        scenic_envs = [
            "a solitary stargazer sitting on a grassy knoll beneath a magnificent celestial night sky brimming with the luminous Milky Way, looking up at shooting stars",
            "a lone traveler camping beside a calm alpine mirror lake reflecting a glowing crescent moon and twinkling constellations, serene pine silhouettes",
            "a peaceful wanderer in a field of night-blooming flowers under an ethereal violet aurora borealis and dazzling starlight",
            "an open wooden observatory deck on a mountain peak under an infinite expanse of glowing stars and purple nebulae"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "infinite cosmic wonder, comforting solitude, and quiet starlight solace"

    # 7. Time, memories, typewriter, vintage nostalgia, letters
    elif any(k in words_lower for k in ["time", "memory", "remember", "past", "years", "old", "book", "typewriter", "write", "letter", "story"]):
        scenic_envs = [
            "an atmospheric sun-drenched vintage writer's study with tall arched windows, an antique typewriter, scattered handwritten letters, a warm steaming ceramic mug overlooking an autumn garden",
            "a quiet vintage railway platform at dusk, warm station lamps glowing in evening mist, empty tracks curving toward distant twilight countryside",
            "an antique wooden desk beside an open bay window overlooking rolling green hills at golden hour, a solitary writer looking out in gentle contemplation",
            "a weathered stone bench under an ancient weeping willow in an old botanical garden, sunbeams illuminating floating golden dust motes"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "bittersweet nostalgia, passage of time, and enduring quiet memories"

    # 8. Love, romance, soul connection, devotion, warmth
    elif any(k in words_lower for k in ["heart", "love", "kiss", "hug", "hold", "forever", "together", "soul", "smile", "eyes", "cherish"]):
        scenic_envs = [
            "two gentle silhouettes sitting side-by-side on a wooden riverbank dock beneath weeping willows, watching glowing paper lanterns drift over calm water at twilight",
            "a couple seen from behind walking hand-in-hand along a quiet garden path illuminated by soft fairy lights and blooming night jasmine under stars",
            "two figures standing on a scenic sunset terrace overlooking a tranquil coastal bay, warm golden light washing over blooming bougainvillea",
            "a peaceful pair resting in a sunlit meadow at golden hour surrounded by swaying wildflowers and floating dandelion seeds"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "intimate warmth, tender devotion, and heartwarming harmony"

    # 9. General contemplative / philosophical poetry
    else:
        scenic_envs = [
            f"a solitary wanderer in the distance standing on a scenic mountain ridge overlooking rolling valleys under dramatic clouds, golden god rays illuminating the landscape",
            f"a peaceful traveler walking along a secluded forest glade path beside a gentle winding brook, sunlight filtering through emerald leaves",
            f"a lone figure walking along rolling green coastal bluffs above a peaceful sparkling sea at late afternoon, fresh coastal breeze",
            f"a reflective wanderer sitting on a tranquil hilltop looking out toward endless misty horizons at golden sunrise"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = f"contemplative poetic stillness reflecting '{clean[:45]}'"

    prompt = (
        f"Breathtaking wide scenic landscape illustration capturing the feeling: '{feeling_theme}'. "
        f"Scenic environment with poem-related subject: {chosen_env}. "
        f"Atmosphere & Lighting: {lighting_prog}, rich atmospheric depth, cinematic volumetric illumination. "
        f"Artistic Style: Masterpiece Studio Ghibli background scenic art and Makoto Shinkai environmental aesthetic, "
        f"rich painterly fine art, expansive 9:16 vertical environmental composition, "
        f"pure scenery, wide shot landscape, vast nature vista, no close-up face, no giant character portrait, no big anime character"
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

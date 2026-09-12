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
            "a serene diverging mountain trail at dawn, golden morning god rays piercing through misty pine trees and wild flowers, calm tranquil atmosphere, vast alpine horizon",
            "a majestic ancient cedar tree standing proudly on a tranquil coastal cliff overlooking a calm glass-like ocean at golden hour, warm god rays filtering through lush branches, safe sanctuary",
            "an expansive rolling wildflower meadow bathed in warm golden sunlight, soft distant mountains under pastel clouds, radiant warmth and peaceful solitude",
            "a solitary ancient stone lighthouse standing firm on a rugged misty cliff above a calm vast ocean at dawn, gentle sea fog illuminated by morning light, tranquil strength"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "quiet self-reclamation, honest integrity, and choosing one's peaceful path"

    # 2. People-pleasing, draining, burdens, letting go, release, healing, silence
    elif any(k in words_lower for k in ["people-pleasing", "drain", "save you", "burden", "heavy", "tired", "let go", "heal", "healing", "silence", "free", "release", "surrender", "alone"]):
        scenic_envs = [
            "a serene autumn lakeside at twilight, gentle evening breeze carrying glowing amber and crimson leaves across calm reflective water, soft dusky lavender and indigo horizon",
            "a peaceful river winding through a quiet misty valley after a gentle rain, soft pastel sunset glow behind rolling distant hills, profound calm and stillness",
            "a tranquil grassy hilltop where delicate white dandelion seeds drift softly into the twilight breeze across an expansive pastel evening sky, boundless openness",
            "a secluded mossy forest clearing with a crystal-clear natural spring pool, gentle sunbeams dancing on still water, deep quiet restoration"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "releasing heavy burdens into the wind, emotional catharsis, and gentle healing"

    # 3. Pride, belief, encouragement, dreams, worth, rising, soaring
    elif any(k in words_lower for k in ["proud", "believe", "dreams", "achieve", "worth", "stumble", "succeed", "capable", "small", "rise", "shine", "fly", "courage"]):
        scenic_envs = [
            "a breathtaking sunrise breaking over majestic mountain peaks with golden alpenglow, light cascading into a vast green valley below, soaring rays of dawn, boundless openness",
            "a sun-drenched hillside path bordered by blooming jacaranda trees and wildflowers overlooking a sparkling panoramic valley at sunrise, fresh morning breeze, radiant optimism",
            "a peaceful alpine meadow surrounded by towering sunlit peaks, crystal-clear mountain stream reflecting warm morning light, vast inspiring beauty",
            "an awe-inspiring panoramic cliffside lookout bathed in the first triumphant rays of morning sun over an endless sea of rolling clouds"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "unwavering belief, quiet pride, and radiant uplifting hope"

    # 4. Father, mother, family, sacrifice, roots, heritage, generations
    elif any(k in words_lower for k in ["father", "mother", "child", "family", "held me", "arms", "gave up", "remember", "home", "growing", "hands", "parent"]):
        scenic_envs = [
            "a majestic deeply-rooted ancient oak tree standing proudly in a golden harvest field at late afternoon, warm amber sunlight filtering through sprawling canopy, timeless enduring strength",
            "a warm rustic wooden porch of a countryside home at sunset, soft warm lantern light glowing beside weathered rocking chairs overlooking quiet golden hills",
            "an ancient weathered stone bridge spanning a quiet flowing stream in an autumn forest, golden leaves resting on weathered stone, soft sunbeams, timeless presence",
            "a tranquil country garden bathed in warm late-afternoon golden glow, blooming hydrangeas along a white picket fence, peaceful nostalgic sanctuary"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "deep quiet gratitude, enduring protective strength, and timeless nostalgic warmth"

    # 5. Rain, tears, grief, heartache, sadness, pain
    elif any(k in words_lower for k in ["rain", "crying", "tears", "pain", "hurt", "broken", "loss", "mourn", "storm", "drown", "water"]):
        scenic_envs = [
            "a quiet rain-washed historic cobblestone street at blue hour dusk, glowing streetlamps casting liquid amber reflections across wet stone, soft rainfall ripples in puddles",
            "a solitary wooden jetty reaching into a calm misty lake during a quiet gentle rain, soft blue and slate grey tones, tranquil stillness and deep reflection",
            "a moody coastal cliff with distant sea spray under dramatic storm clouds breaking into soft slivers of pale silver sunlight, peaceful quiet sorrow",
            "a peaceful garden terrace after a summer shower, dewdrops clinging to dark green leaves, soft cool mist rising in the evening air"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "cleansing melancholic sorrow, quiet reflection, and poignant beauty"

    # 6. Night, stars, moon, galaxy, celestial wonder
    elif any(k in words_lower for k in ["night", "star", "stars", "moon", "sky", "dark", "midnight", "galaxy", "universe", "cosmos"]):
        scenic_envs = [
            "a breathtaking celestial night sky brimming with the luminous Milky Way and glowing constellations over a calm mirror-like alpine lake, silhouettes of distant pine ridges",
            "a radiant crescent moon hanging low over a misty valley, soft silver moonlight illuminating rolling hills and a quiet winding river, deep peaceful wonder",
            "a tranquil field of blooming night flowers under a vast indigo sky filled with shooting stars and ethereal aurora borealis glow",
            "a peaceful hilltop observatory overlook beneath a dazzling canopy of starlight, vast cosmic expanse"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "infinite cosmic wonder, comforting solitude, and quiet starlight solace"

    # 7. Time, memories, typewriter, vintage nostalgia, letters
    elif any(k in words_lower for k in ["time", "memory", "remember", "past", "years", "old", "book", "typewriter", "write", "letter", "story"]):
        scenic_envs = [
            "an atmospheric sun-drenched vintage library room with tall arched windows, soft sunbeams illuminating floating dust motes, wooden shelves of antique books overlooking a quiet autumn garden",
            "a quiet vintage train platform at dusk, warm station lamps glowing softly in the evening mist, empty railway tracks curving into distant twilight countryside",
            "an antique wooden desk beside an open bay window overlooking rolling green meadows at sunset, scattered handwritten papers and warm golden amber glow",
            "a weathered stone garden bench under an ancient weeping willow, golden late-afternoon sunbeams piercing through foliage"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "bittersweet nostalgia, passage of time, and enduring quiet memories"

    # 8. Love, romance, soul connection, devotion, warmth
    elif any(k in words_lower for k in ["heart", "love", "kiss", "hug", "hold", "forever", "together", "soul", "smile", "eyes", "cherish"]):
        scenic_envs = [
            "a romantic twilight riverbank with glowing paper lanterns floating gently across calm reflective water under weeping willow trees, warm candle glow against indigo ripples",
            "a peaceful garden path lined with warm fairy lights and blooming night-jasmine under a canopy of starlight, soft warm bokeh, enchanting atmosphere",
            "a breathtaking sunset terrace overlooking a tranquil coastal bay, warm golden glow washing over blooming bougainvillea, peaceful romantic evening",
            "a secluded blooming meadow at golden hour with wildflowers swaying in a gentle breeze, soft amber sunlight illuminating drifting dandelion fluff"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = "intimate warmth, tender devotion, and heartwarming harmony"

    # 9. General contemplative / philosophical poetry
    else:
        scenic_envs = [
            f"an expansive scenic mountain vista overlooking rolling valleys under dramatic atmospheric clouds, soft golden god rays illuminating lush slopes, calm and serene",
            f"a tranquil secluded forest glade with sunlight filtering through emerald leaves, gentle winding brook, pristine nature scenery",
            f"a quiet coastal path winding along rolling green bluffs above a peaceful sparkling sea at late afternoon, fresh coastal breeze",
            f"a panoramic view from a tranquil hilltop looking out toward endless misty horizons at sunrise, majestic stillness"
        ]
        chosen_env = scenic_envs[(scene_idx - 1) % len(scenic_envs)]
        feeling_theme = f"contemplative poetic stillness reflecting '{clean[:45]}'"

    prompt = (
        f"Breathtaking wide scenic landscape illustration capturing the feeling: '{feeling_theme}'. "
        f"Scenic environment: {chosen_env}. "
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

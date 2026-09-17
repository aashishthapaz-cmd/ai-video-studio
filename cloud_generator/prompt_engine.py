import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import re
from pathlib import Path

# Add project root to sys.path so we can import artwork_prompts
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import artwork_prompts

# =========================================================================
# ARTISTIC WORLD STYLES REGISTRY (POETRY NICHE ALIGNED)
# =========================================================================
ARTISTIC_STYLES_MAP = {
    "typewriters_voice_nostalgia": (
        "Masterpiece vertical 9:16 borderless edge-to-edge full bleed fine art painting in the atmospheric visual style of Typewriters Voice nostalgia. Clean black ink line art with delicate cross-hatch shading and fine horizontal ripple textures, flat gouache color blocking, deep nocturnal indigo navy and slate blue sky with fine ink line hatching, high-contrast radiant warm golden amber and cadmium yellow lantern glow, saturated accents of mustard yellow and crimson red, full canvas bleed, no borders, no frames.",
        "flat gouache color blocking, fine ink hatching, midnight navy and warm golden amber, borderless"
    ),
    "makoto_shinkai_twilight": (
        "Masterpiece vertical 9:16 anime background scenic art in the breathtaking aesthetic of Makoto Shinkai. Expansive cosmic twilight sky, radiant volumetric god rays piercing towering painterly cumulonimbus clouds, sparkling evening starlight and glowing horizon, deep ultramarine blue, violet dusk and apricot golden hour reflections.",
        "Makoto Shinkai anime scenic art, vibrant twilight sky, volumetric god rays, hyper-detailed clouds"
    ),
    "studio_ghibli_meadow": (
        "Masterpiece vertical 9:16 hand-painted background scenic art in the lush naturalism style of Studio Ghibli and Hayao Miyazaki. Painterly gouache and watercolor textures, vibrant summer meadow of swaying wildflowers and dandelion seeds, ancient gnarled mossy trees, soft gentle breeze, warm radiant afternoon sunlight, peaceful pastoral wonder.",
        "Studio Ghibli painterly gouache, lush green meadow, watercolor foliage, warm natural sunlight"
    ),
    "himalayan_mist_serenity": (
        "Masterpiece vertical 9:16 spiritual alpine landscape of the majestic Himalayas. Sacred snow-capped peaks towering above rolling seas of morning mist, vibrant colorful Buddhist prayer flags fluttering in mountain wind, ancient stone chorten shrine, serene quiet atmosphere, soft golden dawn rays touching sacred glaciers.",
        "majestic Himalayan peaks, sea of mist, Buddhist prayer flags, serene high-altitude sunrise"
    ),
    "dark_romantic_academia": (
        "Masterpiece vertical 9:16 classical oil painting with dramatic Baroque chiaroscuro lighting in the style of Caravaggio and Rembrandt. Heavy dark espresso and charcoal shadows, rich burgundy undertones, warm flickering candlelight casting amber glow across antique mahogany and aged parchment, stormy twilight through arched stone windows, poignant melancholy.",
        "Baroque chiaroscuro oil painting, deep mahogany shadows, flickering candlelight, moody romantic atmosphere"
    ),
    "claude_monet_impressionism": (
        "Masterpiece vertical 9:16 French Impressionist oil painting in the plein-air style of Claude Monet. Soft textured impasto brushstrokes, shimmering light dappling on water and weeping willows, pastel palette of lavender, pale rose, sage green, and golden yellow, ethereal luminous atmospheric haze.",
        "Claude Monet impressionism, textured oil brushwork, pastel palette, shimmering light on water"
    ),
    "cyberpunk_rain_reflections": (
        "Masterpiece vertical 9:16 atmospheric 90s lo-fi cyberpunk aesthetic. Quiet rain-washed city street under gentle drizzle, vibrant cyan and amber neon signs reflecting on wet asphalt and puddles, moody nocturnal mist, lone figure with umbrella in the distance, nostalgic cinematic retro-futurism.",
        "90s lo-fi cyberpunk, wet asphalt reflections, glowing neon mist, rain-drenched cinematic mood"
    ),
    "van_gogh_starry_canvas": (
        "Masterpiece vertical 9:16 post-impressionist oil painting in the expressive style of Vincent van Gogh. Dynamic swirling impasto brushstrokes, glowing golden stars and crescent moon swirling in a deep Prussian blue night sky, dark cypress silhouette reaching upward, rich tactile paint texture and luminous emotional energy.",
        "Van Gogh swirling impasto brushstrokes, starry night sky, rich Prussian blue and vibrant gold"
    ),
    "ink_wash_zen_landscape": (
        "Masterpiece vertical 9:16 traditional East Asian Sumi-e ink wash landscape painting (Shan Shui). Delicate black ink gradients on aged rice paper, majestic misty mountain peaks fading into vast quiet negative space, gnarled pine tree clinging to ancient cliff, serene tranquil Zen stillness.",
        "traditional Sumi-e ink wash painting, delicate black ink gradients, misty mountain peaks, zen stillness"
    ),
    "romantic_devotion": (
        "Masterpiece vertical 9:16 romantic watercolor and dreamy 35mm film photography aesthetic. Warm radiant golden hour rim lighting, soft honey and blush tones, glowing rim light, gentle atmospheric bokeh, tender emotional warmth and serene harmonious intimacy.",
        "soft ethereal watercolor and 35mm film grain, radiant golden hour rim lighting, warm honey blush tones"
    ),
    "healing_self_worth": (
        "Masterpiece vertical 9:16 serene nature sanctuary. Deep emerald mossy forest glade, gentle crystal-clear stream with morning mist rising, golden sunbeams piercing the forest canopy, peaceful solitary haven of unshakeable self-worth and quiet stoic resilience.",
        "serene forest glade, crystal stream, golden sunbeams, peaceful natural sanctuary"
    ),
    "cosmic_philosophical": (
        "Masterpiece vertical 9:16 cosmic philosophical vista. Vast deep space panorama with glowing violet and sapphire nebulae, millions of distant stars and swirling galaxies, a solitary silhouette standing on an ancient cliff gazing at the infinite universe, awe-inspiring perspective and eternal wonder.",
        "deep space nebula, glowing cosmic dust, starry infinity, contemplative stargazer silhouette"
    )
}

def resolve_vibe_style(vibe_name: str) -> tuple:
    if not vibe_name:
        return ARTISTIC_STYLES_MAP["typewriters_voice_nostalgia"]
    norm = vibe_name.lower().strip()
    norm = re.sub(r'[^a-z0-9]', '_', norm)
    norm = re.sub(r'_+', '_', norm).strip('_')

    for k in ARTISTIC_STYLES_MAP:
        if k in norm or norm in k:
            return ARTISTIC_STYLES_MAP[k]

    if "shinkai" in norm or "twilight" in norm:
        return ARTISTIC_STYLES_MAP["makoto_shinkai_twilight"]
    if "ghibli" in norm or "meadow" in norm:
        return ARTISTIC_STYLES_MAP["studio_ghibli_meadow"]
    if "himalaya" in norm or "mist" in norm or "zen" in norm:
        return ARTISTIC_STYLES_MAP["himalayan_mist_serenity"]
    if "academia" in norm or "dark" in norm or "baroque" in norm:
        return ARTISTIC_STYLES_MAP["dark_romantic_academia"]
    if "monet" in norm or "impression" in norm:
        return ARTISTIC_STYLES_MAP["claude_monet_impressionism"]
    if "cyber" in norm or "rain" in norm:
        return ARTISTIC_STYLES_MAP["cyberpunk_rain_reflections"]
    if "gogh" in norm or "starry" in norm:
        return ARTISTIC_STYLES_MAP["van_gogh_starry_canvas"]
    if "ink" in norm or "wash" in norm:
        return ARTISTIC_STYLES_MAP["ink_wash_zen_landscape"]
    if "romance" in norm or "devotion" in norm or "soulmate" in norm:
        return ARTISTIC_STYLES_MAP["romantic_devotion"]
    if "heal" in norm or "stoic" in norm or "solace" in norm:
        return ARTISTIC_STYLES_MAP["healing_self_worth"]
    if "cosmic" in norm or "philosophy" in norm:
        return ARTISTIC_STYLES_MAP["cosmic_philosophical"]

    return ARTISTIC_STYLES_MAP["typewriters_voice_nostalgia"]

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

    style_desc, medium_tags = resolve_vibe_style(vibe_id)

    prompt = (
        f"{style_desc} "
        f"Poetic essence: '{feeling_theme}'. "
        f"Scenic environment: {chosen_env}. "
        f"Atmosphere & Lighting: {lighting_prog}, rich atmospheric depth, cinematic volumetric illumination. "
        f"Medium details: {medium_tags}. "
        f"Composition: Expansive 9:16 vertical full bleed, wide shot landscape scenery, vast nature vista, "
        f"no close-up face, no giant character portrait, no character zoom, no cropped face"
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

"""
Poetry Niche Profiles Registry
-----------------------------
Defines highly-tuned artistic profiles for Facebook Pages in distinct poetry niches.
Each niche configures:
1. Artistic Image Engine (medium, palette, lighting, motifs, negative prompts)
2. Voice Model & Cadence (F5-TTS whisper / Edge Neural, pacing, pitch, tone)
3. Captions Typography & Karaoke (font family, size, highlight color, alignment)
4. Social Media Copywriting (hook style, emojis, reflection text, hashtags)
5. USA-Based Schedule (peak engagement time slots in US Eastern/Central/Pacific)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path

@dataclass
class ArtisticVibeConfig:
    vibe_id: str
    display_name: str
    medium: str
    palette: str
    lighting: str
    motifs: List[str]
    prompt_prefix: str
    negative_prompt: str = "text, watermark, logo, blurry, extra limbs, ugly, oversaturated, deformed"

@dataclass
class VoiceConfig:
    engine: str  # 'f5_cloning' or 'edge_tts'
    voice_id: str # file path or Edge TTS voice name
    rate: str = "0.82" # or '-10%'
    pitch: str = "-2Hz"
    nfe_step: int = 32
    tone_description: str = "Calm, breathy, poetic cadence"

@dataclass
class CaptionConfig:
    style_name: str
    font_name: str
    font_size: int = 76
    primary_color: str = "&H0000D7FF"   # ASS BGR format (e.g. &H0000D7FF is Amber Gold)
    secondary_color: str = "&H60FFFFFF" # Semi-transparent white inactive text
    outline_color: str = "&H00111111"   # Deep ink outline
    back_color: str = "&H90000000"      # Shadow
    bold: int = 0                       # -1 for true, 0 for false
    italic: int = 1                     # 1 for italic
    outline: float = 2.5
    shadow: float = 2.0
    alignment: int = 5                  # 5 is middle-center
    margin_v: int = 0

@dataclass
class CopyConfig:
    hook_emojis: str
    call_to_action: str
    default_hashtags: str

@dataclass
class ScheduleConfig:
    timezone: str = "America/New_York"
    daily_slots: List[str] = field(default_factory=lambda: ["08:30", "13:00", "20:30"])
    min_interval_hours: int = 4

@dataclass
class PoetryNiche:
    niche_id: str
    name: str
    tagline: str
    description: str
    art: ArtisticVibeConfig
    voice: VoiceConfig
    caption: CaptionConfig
    copy: CopyConfig
    schedule: ScheduleConfig

    def to_dict(self) -> dict:
        return asdict(self)


# =========================================================================
# PRE-TUNED HIGH-PERFORMANCE POETRY NICHES
# =========================================================================

NICHE_REGISTRY: Dict[str, PoetryNiche] = {
    # ---------------------------------------------------------------------
    # Niche 1: Signature Typewriters Voice Nostalgia
    # ---------------------------------------------------------------------
    "typewriters_voice_nostalgia": PoetryNiche(
        niche_id="typewriters_voice_nostalgia",
        name="Typewriters Voice Nostalgia",
        tagline="Bittersweet reflections, vintage storybook art, and quiet resilience",
        description="Editorial linocut / woodblock print with fine ink cross-hatching, deep nocturnal navy skies, glowing amber lanterns, and breathy whisper voice.",
        art=ArtisticVibeConfig(
            vibe_id="typewriters_voice_nostalgia",
            display_name="Editorial Linocut & Woodblock Print",
            medium="editorial linocut, woodblock print, scratchboard engraving, textured gouache",
            palette="deep midnight navy, slate blue, warm glowing amber, cadmium yellow, ochre lanterns",
            lighting="high contrast warm amber and cadmium yellow glow radiating against dark midnight slate sky",
            motifs=[
                "curved windswept bonsai tree on a snowy hill under fine ink cross-hatched night sky",
                "giant surreal stone monolith rising between ancient European canal townhouses",
                "bonsai tree floating in a wooden rowboat on split crimson and amber reflective water",
                "glowing arched wooden shopfront with warm lanterns casting golden light across wet cobblestones",
                "solitary wanderer in a yellow trenchcoat holding a bright umbrella on a misty bridge"
            ],
            prompt_prefix=(
                "Masterpiece vertical 9:16 editorial storybook illustration, fine linocut and woodblock print, "
                "scratchboard engraving texture, deep midnight navy and slate blue sky with fine ink line hatching, "
                "high-contrast radiant warm amber and cadmium yellow lantern glow. Clean composition with spacious center for typography, "
                "pure evocative artwork, no text, no words, no letters, no typography, no watermarks."
            )
        ),
        voice=VoiceConfig(
            engine="f5_cloning",
            voice_id="assets/reference_voice/whishper_prompt.wav",
            rate="0.82",
            pitch="-2Hz",
            nfe_step=32,
            tone_description="Intimate, breathy, calm whisper with slow poetic cadence"
        ),
        caption=CaptionConfig(
            style_name="ReferenceCursive",
            font_name="Segoe Print",
            font_size=78,
            primary_color="&H0000D7FF",  # Radiant Amber Gold
            secondary_color="&H60FFFFFF",
            outline_color="&H00111111",
            bold=0,
            italic=1,
            outline=2.5,
            shadow=2.0
        ),
        copy=CopyConfig(
            hook_emojis="🍂✨📜🕯️",
            call_to_action="Save this for the days you need a gentle reminder. 📜🕯️\nTag someone who needs to hear this today.",
            default_hashtags="#typewriter #typewritersvoice #poetry #spokenword #healing #mentalhealth #aesthetic #reels #quotes #love #heartbreak #peace"
        ),
        schedule=ScheduleConfig(
            timezone="America/New_York",
            daily_slots=["08:30", "13:00", "20:30"],
            min_interval_hours=4
        )
    ),

    # ---------------------------------------------------------------------
    # Niche 2: Dark Romantic Academia & Melancholy
    # ---------------------------------------------------------------------
    "dark_romantic_academia": PoetryNiche(
        niche_id="dark_romantic_academia",
        name="Dark Romantic Academia",
        tagline="Late-night sorrow, antique libraries, unsaid words, and quiet rain",
        description="Baroque chiaroscuro oil painting, deep mahogany and wine-red undertones, flickering candlelight, melancholy deep male whisper voice, and Cormorant Garamond serif italic typography.",
        art=ArtisticVibeConfig(
            vibe_id="dark_romantic_academia",
            display_name="Baroque Chiaroscuro & Antique Oil",
            medium="classical oil painting, chiaroscuro lighting, dramatic Caravaggio shadows, textured antique canvas",
            palette="deep burgundy, espresso brown, charcoal slate, antique parchment, warm flickering tallow candle gold",
            lighting="dramatic chiaroscuro lighting, single beam of dim window moonlight cutting through dust motes, warm flickering candle",
            motifs=[
                "solitary figure reading near an arched gothic window covered in heavy rain droplets",
                "towering antique mahogany bookshelves in a silent shadowy library with spiral staircases",
                "a withered dark red rose resting on aged parchment sheets beside a glass inkwell",
                "fog-drenched cobblestone street at 2 AM with a single Victorian gas lamp glowing dimly",
                "an antique violin resting on velvet in a shadowy corner with drifting dust particles"
            ],
            prompt_prefix=(
                "Exquisite vertical 9:16 baroque oil painting, dramatic chiaroscuro lighting, heavy dark tones, "
                "deep espresso, charcoal, and aged burgundy colors, soft flickering candlelight and shadowy atmosphere. "
                "Clean open center for poetic subtitles, romantic melancholy aesthetic, no text, no watermark."
            )
        ),
        voice=VoiceConfig(
            engine="edge_tts",
            voice_id="en-US-ChristopherNeural",
            rate="-14%",
            pitch="-3Hz",
            nfe_step=32,
            tone_description="Deep, sorrowful, contemplative male voice with slow emotional breath"
        ),
        caption=CaptionConfig(
            style_name="DarkAcademiaSerif",
            font_name="Cormorant Garamond",
            font_size=82,
            primary_color="&H00C0C0FF",  # Muted Antique Rose / Soft Parchment
            secondary_color="&H50FFFFFF",
            outline_color="&H00080808",
            bold=0,
            italic=1,
            outline=2.2,
            shadow=2.2
        ),
        copy=CopyConfig(
            hook_emojis="🌧️🥀🖤📜",
            call_to_action="For the thoughts that only visit at 2 AM. 🥀🖤\nShare with someone whose silence speaks volumes.",
            default_hashtags="#darkacademia #melancholy #poetry #sadness #grief #unsaidwords #latehours #rain #deepthoughts #solitude #reels"
        ),
        schedule=ScheduleConfig(
            timezone="America/New_York",
            daily_slots=["09:00", "15:00", "22:30"],
            min_interval_hours=4
        )
    ),

    # ---------------------------------------------------------------------
    # Niche 3: Romantic Devotion & Soulmates
    # ---------------------------------------------------------------------
    "romantic_devotion": PoetryNiche(
        niche_id="romantic_devotion",
        name="Romantic Devotion & Soulmates",
        tagline="Unconditional love, soft warmth, intimate vows, and forever promises",
        description="Warm golden hour sunlight, soft ethereal watercolor and 35mm film grain, glowing cherry blossoms, gentle intimate voice, and Segoe Script typography in warm peach-gold.",
        art=ArtisticVibeConfig(
            vibe_id="romantic_devotion",
            display_name="Golden Hour Ethereal Watercolor & Film",
            medium="soft ethereal watercolor, dreamy 35mm film photography, gentle pastel oil wash",
            palette="warm honey gold, blush rose, soft cream, lavender dusk, warm apricot sunlight",
            lighting="radiant golden hour rim lighting, soft diffused lens flare, gentle atmospheric bokeh",
            motifs=[
                "two silhouetted figures holding hands on a flower-covered grassy hill under glowing sunset sky",
                "a warm sunlit breakfast table with two steaming mugs and wild lavender in a clay vase",
                "a solitary couple walking beneath an arch of blossoming pink cherry trees in golden sunlight",
                "warm ocean shore at twilight with bioluminescent golden ripples lapping against the sand",
                "intertwined hands resting peacefully on a linen blanket under dappled sunbeams"
            ],
            prompt_prefix=(
                "Breathtaking vertical 9:16 romantic watercolor and dreamy 35mm film aesthetic, "
                "soft golden hour sunlight, warm honey and blush tones, glowing rim light, emotional intimacy, "
                "spacious atmospheric composition with clean center, pure art, no text, no watermark."
            )
        ),
        voice=VoiceConfig(
            engine="edge_tts",
            voice_id="en-US-JennyNeural",
            rate="-8%",
            pitch="-1Hz",
            nfe_step=32,
            tone_description="Soft, tender, warmly affectionate voice with gentle smile and slow cadence"
        ),
        caption=CaptionConfig(
            style_name="RomanticScript",
            font_name="Segoe Script",
            font_size=74,
            primary_color="&H0033CCFF",  # Warm Peach Gold
            secondary_color="&H60FFFFFF",
            outline_color="&H00181008",
            bold=0,
            italic=1,
            outline=2.4,
            shadow=1.8
        ),
        copy=CopyConfig(
            hook_emojis="❤️🕊️✨💍",
            call_to_action="Send this to the one who makes everywhere feel like home. ❤️🕊️\nComment their initial below.",
            default_hashtags="#love #soulmate #romanticpoetry #relationshipgoals #devotion #forever #lovequotes #healinglove #softaesthetic #reels"
        ),
        schedule=ScheduleConfig(
            timezone="America/New_York",
            daily_slots=["08:00", "12:30", "18:30", "21:30"],
            min_interval_hours=3
        )
    ),

    # ---------------------------------------------------------------------
    # Niche 4: Healing, Self-Worth & Stoic Solace
    # ---------------------------------------------------------------------
    "healing_self_worth": PoetryNiche(
        niche_id="healing_self_worth",
        name="Healing, Self-Worth & Stoic Solace",
        tagline="Quiet strength, letting go, inner peace, and gentle self-compassion",
        description="Minimalist Zen landscape, misty mountain dawns, serene lake reflections, grounded reassuring mentor voice, and clean modern bold typography in soft sage-mint.",
        art=ArtisticVibeConfig(
            vibe_id="healing_self_worth",
            display_name="Minimalist Zen Landscape & Misty Dawn",
            medium="minimalist ink wash, contemporary matte digital painting, misty atmospheric landscape",
            palette="soft sage green, slate grey, misty white, morning dawn lavender, pale dawn gold",
            lighting="soft diffused morning dawn light breaking through mountain mist, calm serene luminescence",
            motifs=[
                "solitary pine tree standing tall on a misty mountain ridge overlooking a sea of fog",
                "gentle concentric ripples on a glassy mountain lake with stones resting beneath clear water",
                "a peaceful wanderer standing atop a green cliff looking at the sunrise breaking through clouds",
                "a single green sprout emerging through cracked earth bathed in warm morning light",
                "bamboo grove in the morning mist with soft rays of light filtering between tall green stalks"
            ],
            prompt_prefix=(
                "Masterpiece vertical 9:16 minimalist Zen landscape painting, tranquil morning mist, "
                "soft sage green, pale dawn light, expansive serene horizon, meditative calmness, "
                "open clean center for clarity of thought, no text, no watermark, no distraction."
            )
        ),
        voice=VoiceConfig(
            engine="edge_tts",
            voice_id="en-US-GuyNeural",
            rate="-11%",
            pitch="-2Hz",
            nfe_step=32,
            tone_description="Grounded, calm, reassuring mentor cadence that feels like a steady anchor"
        ),
        caption=CaptionConfig(
            style_name="StoicMinimal",
            font_name="Montserrat",
            font_size=70,
            primary_color="&H00D0FFD0",  # Soft Healing Sage / Pale Mint Glow
            secondary_color="&H60FFFFFF",
            outline_color="&H00111811",
            bold=-1,
            italic=0,
            outline=2.6,
            shadow=2.0
        ),
        copy=CopyConfig(
            hook_emojis="🌱🌊🤍✨",
            call_to_action="Read this twice. Breathe in, let it go. 🌱🤍\nSave this for whenever you start doubting your worth.",
            default_hashtags="#healing #selfworth #mentalhealth #stoic #innerpeace #lettinggo #selflove #mindfulness #resilience #gentlereminder #reels"
        ),
        schedule=ScheduleConfig(
            timezone="America/New_York",
            daily_slots=["07:30", "12:00", "19:00"],
            min_interval_hours=4
        )
    ),

    # ---------------------------------------------------------------------
    # Niche 5: Cosmic & Philosophical Poetry
    # ---------------------------------------------------------------------
    "cosmic_philosophy": PoetryNiche(
        niche_id="cosmic_philosophy",
        name="Cosmic & Philosophical Reflections",
        tagline="Eternity, starlight, destiny, passage of time, and human wonder",
        description="Deep celestial oil canvas, swirling nebulas, ancient stone arches beneath the Milky Way, resonant contemplative voice, and Cinzel serif in starlight silver.",
        art=ArtisticVibeConfig(
            vibe_id="cosmic_philosophy",
            display_name="Celestial Starlight Canvas & Ancient Stones",
            medium="luminous cosmic oil painting, celestial astronomical art, atmospheric fantasy realism",
            palette="deep space navy, cosmic violet, sapphire blue, radiant starlight silver, pale nebula gold",
            lighting="radiant starlight and glowing nebula gas illuminating ancient obsidian stones and quiet sands",
            motifs=[
                "ancient towering stone circle standing under a vibrant, swirling Milky Way galaxy",
                "a giant astronomical brass clock floating in deep space amidst stardust and constellations",
                "a solitary stargazer sitting on a high cliff edge gazing into the cosmic infinite horizon",
                "an hourglass resting on starlit desert dunes where the sand grains glow like distant galaxies",
                "an ancient doorway standing open in a midnight field revealing a swirling starlight portal"
            ],
            prompt_prefix=(
                "Epic vertical 9:16 cosmic oil painting, luminous starry sky, deep sapphire and violet cosmos, "
                "swirling nebula dust, awe-inspiring ancient monument, mysterious existential beauty, "
                "spacious clean center for profound text, no text, no watermark."
            )
        ),
        voice=VoiceConfig(
            engine="edge_tts",
            voice_id="en-US-EricNeural",
            rate="-10%",
            pitch="-3Hz",
            nfe_step=32,
            tone_description="Deep, resonant, philosophical storyteller voice with slow cinematic cadence"
        ),
        caption=CaptionConfig(
            style_name="CosmicSerif",
            font_name="Cinzel",
            font_size=74,
            primary_color="&H00EEEEEE",  # Radiant Starlight Silver
            secondary_color="&H50FFFFFF",
            outline_color="&H000B0B14",
            bold=-1,
            italic=0,
            outline=2.5,
            shadow=2.5
        ),
        copy=CopyConfig(
            hook_emojis="🌌🪐⏳✨",
            call_to_action="We are just stardust trying to make sense of eternity. 🌌⏳\nSave this for your late-night contemplation.",
            default_hashtags="#philosophy #universe #cosmos #stardust #eternity #destiny #existential #deepthoughts #spaceaesthetic #poetry #reels"
        ),
        schedule=ScheduleConfig(
            timezone="America/New_York",
            daily_slots=["10:00", "16:00", "23:00"],
            min_interval_hours=4
        )
    )
}

def get_niche(niche_id: str) -> PoetryNiche:
    clean_id = (niche_id or "").strip().lower().replace(" ", "_")
    return NICHE_REGISTRY.get(clean_id) or NICHE_REGISTRY["typewriters_voice_nostalgia"]

def list_niches() -> List[dict]:
    return [
        {
            "id": n.niche_id,
            "name": n.name,
            "tagline": n.tagline,
            "description": n.description,
            "art_style": n.art.display_name,
            "voice_tone": n.voice.tone_description,
            "caption_font": f"{n.caption.font_name} ({n.caption.style_name})",
            "daily_slots": n.schedule.daily_slots,
            "timezone": n.schedule.timezone
        }
        for n in NICHE_REGISTRY.values()
    ]

def detect_niche_from_text(title: str, script_text: str) -> str:
    combined = (f"{title} {script_text}").lower()
    scores = {k: 0 for k in NICHE_REGISTRY.keys()}
    
    tw_words = ["typewriter", "paper", "habit", "bad days", "stay", "messy", "remember", "nostalgia", "autumn", "leaves", "raincoat", "bookstore"]
    for w in tw_words:
        if w in combined: scores["typewriters_voice_nostalgia"] += 2

    da_words = ["sorrow", "grief", "pain", "darkness", "tear", "alone", "unsaid", "silence", "shadow", "bleed", "ghost", "ashes", "midnight", "grave"]
    for w in da_words:
        if w in combined: scores["dark_romantic_academia"] += 2

    rom_words = ["love", "soul", "heart", "forever", "hold", "kiss", "eyes", "darling", "beloved", "home", "marry", "cherish", "devotion", "softly"]
    for w in rom_words:
        if w in combined: scores["romantic_devotion"] += 2

    heal_words = ["heal", "breathe", "let go", "worthy", "strength", "peace", "rise", "forgive", "growth", "survive", "calm", "enough", "patience"]
    for w in heal_words:
        if w in combined: scores["healing_self_worth"] += 2

    cos_words = ["stars", "universe", "galaxy", "eternity", "time", "cosmos", "infinite", "stardust", "destiny", "clock", "orbit", "sky", "wander"]
    for w in cos_words:
        if w in combined: scores["cosmic_philosophy"] += 2

    best_niche = max(scores, key=scores.get)
    if scores[best_niche] == 0:
        return "typewriters_voice_nostalgia"
    return best_niche

from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_ORDER = (
    "qwen2.5:7b",
    "gemma3:4b",
    "qwen3:8b",
    "deepseek-r1:8b",
    "llama3.1:8b",
    "gemma2:9b",
    "gemma2:2b",
    "dolphin3.0",
)

DB_PATH = Path(__file__).resolve().parent / "runtime" / "artistic_factory.db"

# =========================================================================
# PERSISTENT SQLITE DATABASE ENGINE (ANTI-REPETITION & NOVELTY ROTATION)
# =========================================================================

class ArtisticDatabase:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS poem_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poem_title TEXT NOT NULL,
                    poem_hash TEXT NOT NULL,
                    topic_category TEXT NOT NULL,
                    vibe_id TEXT NOT NULL,
                    color_palette TEXT DEFAULT '',
                    lighting_style TEXT DEFAULT '',
                    prompt_summary TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS used_elements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    element_hash TEXT NOT NULL,
                    element_text TEXT NOT NULL,
                    topic_category TEXT DEFAULT '',
                    vibe_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scene_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER,
                    scene_number INTEGER,
                    prompt_hash TEXT NOT NULL,
                    full_prompt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_gen_topic ON poem_generations(topic_category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_gen_vibe ON poem_generations(vibe_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_used_elem ON used_elements(category, element_hash)")
            conn.commit()

    def record_generation(self, title: str, poem_text: str, topic: str, vibe_id: str, color: str, lighting: str, summary: str = "") -> int:
        p_hash = hashlib.sha256(poem_text.strip().encode('utf-8')).hexdigest()[:16]
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO poem_generations (poem_title, poem_hash, topic_category, vibe_id, color_palette, lighting_style, prompt_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, p_hash, topic, vibe_id, color, lighting, summary, now))
            gen_id = cursor.lastrowid
            conn.commit()
            return gen_id

    def record_used_element(self, category: str, text: str, topic: str = "", vibe_id: str = ""):
        e_hash = hashlib.sha256(text.strip().encode('utf-8')).hexdigest()[:16]
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO used_elements (category, element_hash, element_text, topic_category, vibe_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (category, e_hash, text, topic, vibe_id, now))
            conn.commit()

    def get_recent_vibes(self, topic: str = "", limit: int = 12) -> list[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if topic:
                cursor.execute("SELECT vibe_id FROM poem_generations WHERE topic_category = ? ORDER BY id DESC LIMIT ?", (topic, limit))
            else:
                cursor.execute("SELECT vibe_id FROM poem_generations ORDER BY id DESC LIMIT ?", (limit,))
            return [row["vibe_id"] for row in cursor.fetchall()]

    def get_recent_used_element_hashes(self, category: str, limit: int = 120) -> set[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT element_hash FROM used_elements WHERE category = ? ORDER BY id DESC LIMIT ?", (category, limit))
            return {row["element_hash"] for row in cursor.fetchall()}

    def pick_novel_vibe(self, topic: str, candidate_vibes: list[str]) -> str:
        recent_for_topic = set(self.get_recent_vibes(topic=topic, limit=8))
        recent_global = set(self.get_recent_vibes(limit=14))
        
        # 1st priority: Unused in this topic AND globally
        tier1 = [v for v in candidate_vibes if v not in recent_for_topic and v not in recent_global]
        if tier1:
            return random.choice(tier1)
        
        # 2nd priority: Unused in this topic
        tier2 = [v for v in candidate_vibes if v not in recent_for_topic]
        if tier2:
            return random.choice(tier2)
            
        # 3rd priority: Random pick
        return random.choice(candidate_vibes)

    def pick_novel_environment(self, pool: list[str], vibe_id: str = "") -> str:
        used_hashes = self.get_recent_used_element_hashes("environment", limit=120)
        candidates = []
        for env in pool:
            h = hashlib.sha256(env.strip().encode('utf-8')).hexdigest()[:16]
            if h not in used_hashes:
                candidates.append(env)
        
        chosen = random.choice(candidates if candidates else pool)
        self.record_used_element("environment", chosen, vibe_id=vibe_id)
        return chosen

db = ArtisticDatabase()

# =========================================================================
# 25+ DISTINCT ARTISTIC AESTHETIC WORLDS (NO BOILERPLATE VIBE REPETITION!)
# =========================================================================

ARTISTIC_VIBES = {
    "typewriters_voice_nostalgia": {
        "name": "Typewriters Voice Nostalgic Nocturne",
        "medium_suffix": "Ligne claire storybook illustration, Typewriters Voice aesthetic, fine ink cross-hatching and textured gouache, high contrast warm amber and cadmium orange light pooling against deep indigo and slate blue night, cozy nocturnal sanctuary, vertical 9:16 portrait composition, photorealistic storybook art, no text, no letters, no words",
        "palettes": [
            "deep midnight navy, warm glowing amber, cadmium orange lantern, slate blue, aged book cream",
            "rain-slicked slate indigo, golden lamplight ochre, warm terracotta brick, dark charcoal, soft candlelight",
            "nocturnal Prussian blue, luminous honey yellow, burnt sienna, cozy bookshop amber, starlit navy",
            "foggy river slate, glowing gaslamp gold, antique timber walnut, deep ocean midnight, soft candle cream"
        ],
        "lighting": [
            "warm golden amber interior light spilling from shop windows onto textured dark cobblestones in evening drizzle",
            "soft glowing vintage streetlamps and candle flames casting warm amber reflections across dark rippling water",
            "intimate warm lantern glow cutting through quiet misty night beneath a luminous crescent moon and stars",
            "warm orange light radiating from cozy cottage windows into deep midnight indigo countryside"
        ],
        "particles": ["fine white diagonal rain hatch lines in dark sky", "delicate twinkling stars and soft golden dust particles", "gentle chimney smoke rising into deep indigo midnight heavens"],
        "environments": [
            "an illuminated arched wooden bookstore facade with warm amber bookshelves and paper prints on a dark cobblestone lane",
            "a solitary cozy red brick cottage with glowing warm amber windows and smoking stone chimney under a starlit midnight sky",
            "an ancient stone arch bridge over a quiet canal with glowing gas lanterns casting long golden amber reflections on dark water",
            "a solitary weathered stone lighthouse atop a dramatic coastal cliff beaming a bright warm golden light ray across dark ocean waves",
            "a cozy European corner bistro with warm amber light glowing from the dining terrace and a solitary coffee cup on round table",
            "a quaint Parisian bookstall kiosk along the stone riverwall illuminated by a glowing hanging lantern at dusk",
            "a rustic wooden A-frame cabin nestled in quiet pine woods with warm golden light glowing through the front glass facade",
            "a solitary wooden boat dock with a single lantern extending into a calm misty midnight lake beneath glowing crescent moon",
            "a vintage illuminated railway carriage window with warm amber glow looking out into dark passing countryside hills",
            "a solitary giant ancient oak tree with glowing amber autumn foliage on a quiet grassy knoll beneath starry midnight cosmos"
        ]
    },
    "ghibli_lush_countryside": {
        "name": "Studio Ghibli Lush Naturalism",
        "medium_suffix": "Studio Ghibli fine-art animation background, hand-painted gouache landscape, vibrant lush nature, whimsical atmospheric storytelling, soft hand-drawn linework, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "sunlit meadow emerald green, dandelion yellow, clear cerulean sky, soft cottage cream",
            "summer clover green, cornflower blue, sunflower gold, warm terracotta tile",
            "dappled forest olive, river turquoise, peach blossom glow, dewy morning jade"
        ],
        "lighting": [
            "dappled warm afternoon sunlight filtering through rustling tree leaves with gentle sunbeams",
            "radiant golden hour sun grazing across lush wildflower hills and quiet country paths",
            "soft gentle morning haze illuminating dewy green meadows under open blue skies"
        ],
        "particles": ["floating golden dandelion seeds in sunbeams", "gentle summer pollen and drifting white petals", "tiny dancing fireflies in evening grass"],
        "environments": [
            "a rustic hilltop wooden windmill overlooking rolling emerald meadows dotted with yellow buttercups at golden hour",
            "a secluded moss-covered stone well with blooming morning glories nestled deep inside a sunlit ancient forest",
            "a tranquil coastal railway platform where calm turquoise ocean waves gently lap against stone tracks",
            "an overgrown greenhouse conservatory with shattered stained glass where lush tropical ferns flourish",
            "a quiet wooden veranda of an old countryside tea house during gentle summer breeze with wind chimes",
            "a sun-dappled cobblestone path winding through a terraced hillside village with blooming roses and sea views",
            "an intimate countryside train interior looking out a sunlit window as green hills and wildflowers drift past",
            "a solitary weathered bench resting beneath a giant flowering cherry blossom tree in full pink bloom",
            "a flower-lined wooden boardwalk stretching through coastal marshland toward a serene sunrise horizon",
            "a calm hidden cove surrounded by weathered coastal rocks with gentle waves lapping fine white sand"
        ]
    },
    "shinkai_celestial_twilight": {
        "name": "Makoto Shinkai Cosmic Twilight",
        "medium_suffix": "Makoto Shinkai inspired celestial anime digital painting, hyper-detailed twilight sky, glowing comet dust trails, breathtaking cloudscapes, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "deep cosmic violet, magenta twilight gradient, starlit cyan, brilliant comet gold",
            "lapis lazuli blue, radiant amethyst purple, glowing horizon amber, diamond star clusters",
            "twilight indigo, neon lavender, soft peach horizon, celestial stardust teal"
        ],
        "lighting": [
            "dramatic magic-hour sunset rim light outlining towering clouds against deep starry heavens",
            "brilliant starlight and glowing comet dust illuminating the vast dark landscape with celestial glow",
            "vibrant sunset gradient from crimson coral to deep violet with city lights beginning to twinkle"
        ],
        "particles": ["glowing stardust and faint comet dust particles in cosmic sky", "soft evening mist reflecting twilight colors", "twinkling distant stars across Milky Way"],
        "environments": [
            "a vast open grassy hilltop at dusk where the deep indigo sky is dramatically illuminated by a brilliant splitting comet",
            "an apartment rooftop with a round water tank under an expansive midnight cosmos sparkling with millions of stars",
            "a pedestrian railway overpass at twilight with glowing amber streetlights overlooking multiple train tracks",
            "a quiet sunlit classroom after school with warm golden sunset light streaming through open windows and curtains",
            "a towering summer thunderhead cumulonimbus cloud catching the vibrant magenta and orange glow of setting sun",
            "an empty railway carriage on an elevated train looking down onto the twinkling evening lights of a vast metropolis",
            "a high mountain peak overlook bathed in surreal violet and crimson gradients of the magic twilight hour",
            "a quiet bridge over an urban canal at midnight with full moon and soft streetlights reflecting on water",
            "a solitary figure silhouette standing on an elevated observation deck gazing at a dramatic celestial eclipse",
            "a winding mountain road at dusk illuminated by trailing light streaks of vehicles under starry purple sky"
        ]
    },
    "lofi_90s_neon_rain": {
        "name": "90s Retro Lo-Fi Cyberpunk Nocturne",
        "medium_suffix": "lo-fi retro 90s aesthetic anime illustration, textured ink and watercolor cel-shading, vintage anime aesthetic, moody rain atmosphere, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "deep midnight navy, neon cyan reflections, warm sodium-vapor amber, rain-slicked charcoal",
            "rainy indigo blue, electric magenta, soft streetlamp gold, reflective wet asphalt",
            "dark slate teal, warm orange neon glow, misty lavender, deep midnight shadow"
        ],
        "lighting": [
            "warm glowing streetlamps and neon signs reflecting across wet asphalt puddles in evening drizzle",
            "soft cozy sodium-vapor lamplight cutting through misty rain-slicked midnight alleyways",
            "rain-streaked window reflections blurring distant colorful city lights into soft cinematic bokeh"
        ],
        "particles": ["gentle steady evening rain creating delicate water rings in puddles", "soft rain mist glowing in streetlamp beams", "rain streaks running down window glass"],
        "environments": [
            "a cozy midnight 24-hour laundromat with warm neon signs glowing on rows of spinning machines and rain on windows",
            "a solitary midnight ramen cart under a glowing paper lantern sitting under sheltering eaves of a rainy alley",
            "a nostalgic corner coffee shop window counter at dusk with a steaming ceramic mug and streetlamps blurring into bokeh",
            "an apartment fire escape balcony at midnight wrapped in a warm blanket looking over a softly glowing city skyline",
            "a lone red public bus stop shelter standing beside a quiet countryside highway at blue-hour twilight with rain",
            "a peaceful attic bedroom nook with an open dormer window, warm fairy lights, and deep twilight rainy sky",
            "a solitary bench on an empty midnight subway platform with warm overhead lights reflecting on polished floor",
            "a cozy desk setup by a rain-streaked window with an open journal, brass lamp, and twilight city views",
            "an empty vintage arcade storefront glowing with warm neon cyan accents on a quiet rain-soaked evening street",
            "a quiet bookstore aisle bathed in warm lamp glow while rain taps gently on the large glass facade"
        ]
    },
    "shin_hanga_woodblock": {
        "name": "Modern Shin-Hanga Woodblock Print",
        "medium_suffix": "Japanese Shin-Hanga woodblock print style, Hasui Kawase inspired fine art, delicate ink contours, traditional handmade washi paper texture, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "deep indigo blue, vermilion red accents, misty moonlight silver, aged parchment ochre",
            "prussian blue, soft pine green, lantern amber, mountain mist white, faded crimson",
            "twilight cobalt, cherry blossom pink, ink black, pale bamboo yellow, tea brown"
        ],
        "lighting": [
            "ethereal moonbeams casting silver ripples across calm misty lake with silhouette pagoda",
            "soft glowing paper lantern warmth illuminating wooden eaves and wet stone steps in evening fog",
            "early dawn first light washing over snow-covered pine branches and ancient temples"
        ],
        "particles": ["delicate swirling snow flurries in quiet evening air", "soft undulating lake mist rising into moonlight", "floating cherry blossom petals drifting across water"],
        "environments": [
            "an ancient wooden pagoda standing beside a calm misty lake under a brilliant glowing crescent moon",
            "a stone lantern beside a snowy bamboo path illuminated by warm flickering interior glow",
            "a wooden arch bridge over a reflective canal lined with weeping willows and floating paper lanterns",
            "a quiet coastal torii gate at high tide with silver moonbeams rippling across calm dark waters",
            "a secluded mountain temple stone staircase winding through misty pine trees at blue hour",
            "a peaceful wooden tea pavilion overlooking a mirror-like garden pond with autumn maple leaves",
            "a solitary fisherman wooden boat moored beside reeds under a vast starry midnight indigo sky",
            "a quiet village street lined with traditional wooden latticework houses in gentle evening snowfall"
        ]
    },
    "edward_hopper_solitude": {
        "name": "Edward Hopper Atmospheric Solitude",
        "medium_suffix": "Edward Hopper inspired atmospheric oil painting, bold cinematic light beams, expressive painterly brushwork, profound emotional solitude, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "warm cadmium amber, deep Prussian blue shadows, muted olive, rich mahogany wood",
            "sunlit ochre, cool slate gray, seafoam green, deep terracotta brown",
            "early morning cream, shadow indigo, warm wood honey, dusty rose dusk"
        ],
        "lighting": [
            "single dramatic diagonal shaft of golden morning sunlight piercing through open doorway into quiet room",
            "high-contrast chiaroscuro with warm glowing interior lamps against deep twilight blue exterior",
            "late afternoon low-angled amber sunlight casting long geometric architectural shadows"
        ],
        "particles": ["fine dust motes floating peacefully in a strong diagonal sunbeam", "gentle sea breeze stirring sheer white curtains", "quiet stillness with crisp light edges"],
        "environments": [
            "a solitary wooden porch rocking chair overlooking quiet coastal sand dunes at golden hour sunset",
            "an empty corner diner counter by a large plate-glass window looking out onto quiet dusk street",
            "a sunlit wooden staircase in an empty house with dust motes and an open window showing blue sky",
            "a quiet room with morning sunlight streaming across polished hardwood floors and an open door",
            "a solitary wooden dock at blue hour with calm water and a single lamppost glowing against dusk",
            "a peaceful lighthouse keeper cottage perched on an open grassy cliff overlooking the ocean horizon",
            "an empty sunlit library reading hall with long oak tables and sunlight beams through arched windows"
        ]
    },
    "monet_pastel_impressionism": {
        "name": "Claude Monet Pastel Impressionism",
        "medium_suffix": "Claude Monet inspired impressionist oil painting, textured palette knife strokes, dewy morning luminescence, atmospheric color vibration, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "pastel lavender, dewy peach, water lily jade green, soft rose quartz, morning cream",
            "pale lilac, soft buttercup yellow, pond turquoise, dewy leaf sage, coral blush",
            "morning mist silver, pale wisteria violet, soft apricot, moss green, water lily white"
        ],
        "lighting": [
            "soft diffused sunrise mist breaking into gentle pastel light over still reflective waters",
            "dappled morning sunlight shimmering on lily pads and dancing across calm water ripples",
            "ethereal pastel golden hour with soft pink and lavender clouds reflecting in water mirror"
        ],
        "particles": ["translucent morning dew and rising lake mist", "floating water lily petals on calm ripples", "soft pastel sunbeams filtering through weeping willows"],
        "environments": [
            "a serene water lily pond with weeping willow reflections and floating delicate pink water blooms",
            "a sunlit poppy and chamomile meadow in gentle morning fog with rolling green hills in distance",
            "a tranquil apple orchard in late spring with white blossoms drifting softly across lush grass",
            "a coastal cliff path dotted with wild sea thrift flowers overlooking a calm pastel ocean at dawn",
            "a secluded garden path lined with towering blooming purple irises and dewy morning foliage",
            "a quiet arched wooden Japanese footbridge draped in wisteria blossoms over a reflective pond"
        ]
    },
    "dark_academia_chiaroscuro": {
        "name": "Dark Academia & Baroque Chiaroscuro",
        "medium_suffix": "Dark academia fine-art digital painting, Caravaggio chiaroscuro lighting, textured oil glaze, rich romantic mystery, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "antique brass gold, rich mahogany brown, deep burgundy, shadow black, parchment cream",
            "aged copper green, leather brown, candle amber, velvet midnight blue, bone white",
            "dark walnut, warm beeswax yellow, deep forest green, gilded gold leaf, charcoal shadow"
        ],
        "lighting": [
            "warm flickering candlelight casting long dramatic amber shadows on dark antique bookshelves",
            "single dramatic beam of golden afternoon light illuminating antique brass instruments on oak desk",
            "soft fireplace embers casting warm flickering orange highlights across dark wood-paneled walls"
        ],
        "particles": ["glowing candlelight dust motes floating in dark air", "faint wisps of fragrant tea steam catching warm light", "soft fireplace embers rising into chimney"],
        "environments": [
            "a towering library hall with arched stained glass windows and dust motes dancing in sunbeams",
            "an antique mahogany desk with a lit candle, crystal prism catching rainbow light, and open journal",
            "a secluded conservatory with vintage brass astronomy telescope overlooking starlit night sky",
            "a quiet reading nook in front of a glowing stone fireplace with dark leather armchair and books",
            "an ancient stone cloister courtyard with archways and morning ivy bathed in soft autumn light",
            "a vintage violin resting on aged velvet beside an open window overlooking twilight rain"
        ]
    },
    "wabi_sabi_zen_mist": {
        "name": "Wabi-Sabi Zen Ink Wash & Kintsugi",
        "medium_suffix": "Wabi-sabi fine art illustration, minimalist Japanese sumi-e ink wash painting, flowing mountain mist, gold leaf kintsugi veins, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "mineral black ink, flowing misty white, raw silk beige, radiant molten gold accents",
            "charcoal slate, fog gray, bamboo green wash, shimmering kintsugi gold, muted ivory",
            "deep indigo ink, washed stone gray, warm tea stain, metallic gold leaf veins"
        ],
        "lighting": [
            "subtle ethereal dawn illumination highlighting shimmering gold kintsugi seams on dark slate",
            "soft diffused light breaking through thick mountain mist revealing ancient pine silhouettes",
            "gentle moonbeams catching gold leaf details on textured handmade washi paper background"
        ],
        "particles": ["flowing undulating layers of translucent mountain mist", "tiny floating golden leaf specks in quiet air", "single water drop creating ripple in stone basin"],
        "environments": [
            "a broken ceramic bowl mended with radiant molten golden kintsugi seams resting on weathered slate",
            "a solitary ancient pine tree rooted on a misty mountain crag overlooking sea of clouds",
            "a tranquil zen rock garden with raked white gravel ripples and a single red autumn leaf",
            "a path of illuminated stepping stones crossing a calm misty pond with floating bamboo leaf",
            "an ancient mossy stone water basin catching single falling water drops in bamboo forest",
            "a minimalist wooden tearoom veranda looking out onto mountain peaks emerging from morning mist"
        ]
    },
    "nordic_fog_hygge": {
        "name": "Nordic Fog & Scandinavian Hygge",
        "medium_suffix": "Nordic atmospheric digital painting, Scandinavian folk aesthetic, serene misty wilderness, cozy hygge stillness, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "slate blue, silver mist gray, pine needle green, warm hearth fire amber, wool cream",
            "arctic fjord teal, birch bark white, copper lantern glow, muted moss, twilight gray",
            "ice blue, weathered timber brown, warm candle gold, pale lichen green, cloud gray"
        ],
        "lighting": [
            "warm glowing cabin window light spilling out onto quiet snow-dusted pine forest at twilight",
            "soft silver morning mist rolling across mirror-calm fjord water with distant pine ridges",
            "gentle hearth firelight illuminating cozy rustic wooden interior with woolen blankets"
        ],
        "particles": ["soft gentle snowflakes drifting down in quiet twilight", "delicate silver mist undulating over still lake", "cozy smoke rising from stone chimney into cold air"],
        "environments": [
            "a rustic wooden cabin porch in quiet pine forest with a warm glowing lantern and falling snow",
            "a solitary wooden jetty extending into a mirror-calm misty fjord reflecting pine mountains",
            "snow-covered birch trees along a quiet mountain creek with ice crystals catching dawn light",
            "a cozy attic dormer window overlooking a foggy pine valley with a warm wool blanket and tea",
            "a secluded wooden sauna dock beside a calm northern lake under soft violet twilight sky",
            "a solitary reindeer silhouette standing on a misty tundra ridge at first light of dawn"
        ]
    },
    "bioluminescent_wonderland": {
        "name": "Celestial Bioluminescent Wonderland",
        "medium_suffix": "ethereal fantasy concept art, glowing bioluminescent fine art, deep oceanic dreamscape, magical atmospheric radiance, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "ultramarine blue, glowing neon turquoise, electric cyan, iridescent violet, coral embers",
            "deep ocean indigo, phosphorescent emerald, starlight blue, glowing lilac, pearl aqua",
            "midnight sapphire, neon aqua green, celestial purple, glowing amber coral"
        ],
        "lighting": [
            "magical glowing blue and emerald bioluminescence illuminating tranquil tide pools at night",
            "ethereal neon cyan light radiating from floating jellyfish lanterns drifting in evening mist",
            "glowing crystalline reflections sparkling in dark still water under a canopy of stars"
        ],
        "particles": ["glowing blue bioluminescent spores floating gently in dark air", "shimmering turquoise water ripples with starlight reflections", "iridescent light bubbles drifting upward"],
        "environments": [
            "a hidden coastal cove where glowing bioluminescent blue waves lap against dark volcanic rocks",
            "an enchanted forest clearing with floating luminous spores and glowing teal mushroom caps",
            "a shallow starlit lagoon with floating glowing water lanterns drifting into midnight mist",
            "an ancient stone cavern with bioluminescent crystals reflecting in a mirror-still pool",
            "a solitary wooden rowboat floating on an ocean of glowing blue bioluminescent algae at midnight",
            "a magical mangrove waterway with glowing roots and illuminated water blossoms under starry sky"
        ]
    },
    "vintage_70s_film": {
        "name": "Vintage 70s Analog Film Travel",
        "medium_suffix": "vintage 1970s 35mm film photograph aesthetic, warm Kodak Portra tones, soft organic grain, nostalgic golden hour flares, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "burnt sienna, golden ochre, dusty denim blue, sun-baked terracotta, warm honey",
            "vintage mustard yellow, faded avocado green, warm leather brown, cream white, desert sand",
            "warm amber sunset, rustic tobacco, dusty turquoise, faded coral, sepia tone"
        ],
        "lighting": [
            "hazy golden hour sunset with warm lens flare grazing across vintage textures and landscape",
            "warm retro sunbeams cutting through dusty air on a peaceful scenic coastal overlook",
            "soft late-afternoon amber glow illuminating open highway and rolling desert hills"
        ],
        "particles": ["warm golden dust motes in sunflare", "authentic 35mm film grain and subtle halation", "breeze carrying dry summer grass blades"],
        "environments": [
            "a vintage retro camper van parked on a coastal cliff overlook at sunset with headlights on grass",
            "a solitary acoustic guitar leaning against a sun-drenched wooden porch in golden hour light",
            "a rustic mountain dirt road winding into golden rolling hills under expansive warm sky",
            "a wildflower meadow with an old wooden split-rail fence and golden late-afternoon sunbeams",
            "a quiet coastal diner parking lot at sunset overlooking ocean swells with retro aesthetic",
            "a vintage bicycle with front woven basket resting against a sunlit stone wall in countryside"
        ]
    },
    "surrealist_dreamscape": {
        "name": "Surrealist Metaphorical Fine Art",
        "medium_suffix": "surrealist fine art painting, René Magritte inspired poetic metaphor, dreamy atmospheric stillness, evocative symbolism, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "cerulean blue sky, velvet midnight navy, floating emerald green, luminous gold",
            "twilight lapis, pearl cloud white, floating rose red, starry cosmos indigo, gold leaf",
            "dreamy turquoise, desert peach, glowing amber lantern, deep horizon violet"
        ],
        "lighting": [
            "impossible poetic dual lighting with daytime clouds floating above a tranquil starry night scene",
            "luminous celestial radiance emanating from floating lanterns and open doorway into universe",
            "soft dreamlike ambient luminescence casting gentle surreal shadows across landscape"
        ],
        "particles": ["floating golden key and feather particles drifting in sky", "glowing stars falling like gentle rain", "translucent floating water spheres reflecting galaxies"],
        "environments": [
            "a solitary glowing red doorframe standing freely in the middle of a vast rolling grassy plain",
            "a giant glowing crescent moon resting gently in a quiet sunlit forest clearing among flowers",
            "an ancient stone staircase spiraling upward through clouds toward a glowing golden celestial doorway",
            "a tranquil shallow water mirror reflecting an infinite sky of floating glowing paper lanterns",
            "a solitary wooden swing hanging from a massive ancient oak tree overlooking a sea of clouds",
            "an open window frame floating above ocean waves showing a view into a starlit galaxy"
        ]
    },
    "autumn_ginkgo_sanctuary": {
        "name": "Autumn Ginkgo & Maple Sanctuary",
        "medium_suffix": "atmospheric autumn fine-art digital painting, rich textured foliage brushwork, poetic seasonal nostalgia, warm golden haze, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "vibrant ginkgo yellow, crimson maple red, warm amber, moss green, wet stone charcoal",
            "burnt orange, golden honey, deep burgundy, fog gray, weathered wood brown",
            "warm ochre, copper bronze, soft peach mist, dark river slate, crimson foliage"
        ],
        "lighting": [
            "crisp golden morning sunlight piercing through canopy of falling autumn leaves with soft mist",
            "warm late-afternoon amber glow illuminating carpet of golden leaves on quiet temple courtyard",
            "soft twilight overcast with vibrant red maple leaves glowing against dark reflective wet stones"
        ],
        "particles": ["whimsical swirling golden ginkgo and maple leaves falling in slow breeze", "gentle autumn rain on wet cobblestones", "soft morning mist weaving through colored trees"],
        "environments": [
            "an ancient temple courtyard blanketed in golden ginkgo leaves with stone lanterns and wooden gate",
            "a crimson arched bridge spanning a gentle river with floating fallen red maple leaves",
            "a quiet wooden bench under a giant ancient golden oak tree in morning autumn mist",
            "a rain-washed cobblestone lane carpeted in yellow leaves with glowing amber streetlamps",
            "a secluded wooden tea pavilion surrounded by fiery red maple trees reflected in calm pond",
            "a quiet mountain crossroads where paths are covered in thick layers of golden and bronze leaves"
        ]
    },
    "mediterranean_golden_coast": {
        "name": "Mediterranean Sun-Drenched Coastline",
        "medium_suffix": "Mediterranean plein-air gouache painting, vibrant sun-kissed textures, coastal romance, warm breezy atmosphere, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "terracotta orange, deep Mediterranean azure sea, lemon yellow, blooming bougainvillea pink, chalk white",
            "sun-baked ochre, turquoise bay, olive green, warm stone beige, vibrant floral coral",
            "golden hour saffron, cobalt ocean, rustic clay brown, pastel lavender sky, linen cream"
        ],
        "lighting": [
            "brilliant warm golden hour sunlight reflecting across sparkling ocean waves and stone cliffs",
            "soft morning sea breeze carrying warm golden sunlight into open balcony with white curtains",
            "late-afternoon amber sun casting warm golden highlights on terracotta roofs and sea horizon"
        ],
        "particles": ["sparkling sun glints across sea waves", "bougainvillea petals floating on coastal breeze", "warm golden sun haze over ocean horizon"],
        "environments": [
            "a cliffside garden terrace overlooking deep turquoise sea with terracotta pots and olive trees",
            "a sunlit balcony with billowing white linen curtains overlooking a quiet coastal fishing bay",
            "a picturesque cobblestone alleyway draped with cascading pink bougainvillea and blue sea view",
            "a quiet wooden boat bobbing in a sunlit crystal-clear turquoise cove beside white rocks",
            "a shaded rustic pergola covered in blooming grapevines overlooking rolling coastal vineyards",
            "a solitary stone bench on high coastal bluff overlooking vast Mediterranean sunset horizon"
        ]
    },
    "celtic_misty_highlands": {
        "name": "Celtic Highlands & Heather Moors",
        "medium_suffix": "moody Scottish highland landscape painting, atmospheric silver fog, rugged romantic realism, sweeping poetic scale, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "heather violet, wild moor copper, slate gray, muted sage olive, stormy indigo",
            "wild bracken gold, misty loch silver, highland pine green, dark peat brown, heather purple",
            "storm cloud charcoal, copper bracken, pale dawn lavender, moss emerald, river white"
        ],
        "lighting": [
            "dramatic single sunbeam breaking through stormy purple clouds onto rolling highland hills",
            "soft silver morning mist rolling across calm highland loch with dark mountain reflections",
            "golden sunset glow highlighting heather-covered ridges against deep indigo storm clouds"
        ],
        "particles": ["fine Scottish mist drifting in rolling wind", "delicate water spray from mountain waterfall", "soft purple heather blossoms swaying in breeze"],
        "environments": [
            "ancient standing stones on a heather-covered ridge in morning mist with distant mountains",
            "a rustic stone cottage with smoking chimney beside a calm highland loch reflecting clouds",
            "a windswept coastal headland with crashing ocean surf and dramatic green cliffs",
            "a secluded rocky waterfall cascading into a crystal-clear pool in a deep pine glen",
            "a winding gravel path across wide open moorland under vast dramatic stormy sky",
            "a solitary stag silhouette standing on high rocky mountain ridge in morning fog"
        ]
    },
    "cozy_midnight_coffee_vinyl": {
        "name": "Cozy Midnight Coffee & Vinyl Solitude",
        "medium_suffix": "nostalgic cafe interior illustration, warm ambient lamplight, rich wood textures, cozy solitary comfort, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "espresso dark brown, warm brass amber, cream ceramic, soft rain blue, roasted caramel",
            "warm mahogany, vinyl black, glowing tungsten gold, deep navy dusk, coffee crema",
            "aged teak wood, warm candle amber, soft heather grey, rain-slicked slate, honey glow"
        ],
        "lighting": [
            "warm tungsten Edison bulb glow casting soft golden halos on steamed rain-slicked window",
            "cozy brass desk lamp illuminating open book and ceramic coffee mug in quiet corner",
            "soft twilight streetlamp glow filtering through rain streaks into dark cozy room"
        ],
        "particles": ["steam gently rising from fresh hot ceramic coffee mug", "warm dust motes dancing in tungsten bulb glow", "delicate rain droplets sliding down windowpane"],
        "environments": [
            "a corner cafe wooden table with a steaming ceramic cup and rain falling on the street window",
            "a vinyl record shop corner with tall mahogany shelves packed with albums and warm brass lamp",
            "a cozy reading armchair beside towering wooden bookshelf with soft wool blanket and book",
            "a quiet vintage cafe bar before opening in early morning with warm pastry case glow and coffee steam",
            "a solitary wooden window seat in an attic studio with coffee mug and rain-slicked city view",
            "a retro turntable spinning an album on a walnut credenza with warm amplifier glow"
        ]
    },
    "coastal_lighthouse_solitude": {
        "name": "Coastal Lighthouse & Ocean Solitude",
        "medium_suffix": "cinematic maritime fine-art painting, dramatic coastal atmosphere, textured sea foam, heroic solitary beacon, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "stormy ocean navy, seafoam turquoise, weathered lighthouse white, warm amber beam, granite gray",
            "twilight lapis blue, coastal grass gold, beacon yellow, deep water teal, misty silver",
            "sunset crimson coral, ocean cobalt, salt-bleached wood, wave crest white, dark cliff"
        ],
        "lighting": [
            "powerful warm golden lighthouse beam cutting through dense blue-hour twilight sea fog",
            "dramatic golden hour sunset casting warm rim light on rugged granite cliffs and crashing waves",
            "soft morning dawn breaking over calm glassy ocean with lighthouse silhouette on headland"
        ],
        "particles": ["fine ocean sea spray catching warm golden sunset rays", "rolling sea fog undulating across coastal headland", "white seafoam swirling against dark rocks"],
        "environments": [
            "a lone white lighthouse on a rugged granite cliff cutting through ocean sea fog at dusk with warm beam",
            "a weathered wooden dinghy pulled up on a quiet pebbled beach with gentle ocean waves",
            "an ancient ocean pier with barnacle-covered pilings standing resolute in calm twilight waters",
            "quiet coastal dunes covered in swaying sea grass overlooking vast sunset ocean horizon",
            "a secluded stone lookout perch with brass telescope overlooking endless turquoise sea",
            "a rocky tidal pool reflecting the golden beam of distant lighthouse in starry midnight water"
        ]
    },
    "misty_bamboo_zen": {
        "name": "Misty Bamboo Forest & Stone Shrines",
        "medium_suffix": "Japanese zen landscape painting, towering green bamboo grove, atmospheric morning mist, meditative serene peace, vertical 9:16 composition, no text, no writing",
        "palettes": [
            "fresh bamboo green, misty pale jade, wet moss emerald, slate stone gray, lantern gold",
            "deep forest teal, bamboo stalk yellow-green, stone charcoal, morning mist white, amber glow",
            "dewy leaf jade, mountain fog silver, wet earth brown, stone lantern vermilion"
        ],
        "lighting": [
            "soft diffuse morning light filtering down through towering bamboo stalks onto wet stone path",
            "warm glowing stone lantern illuminating mossy pathway in dense bamboo morning fog",
            "gentle sunbeams piercing through green bamboo leaves creating dappled light patterns"
        ],
        "particles": ["translucent morning mist drifting between bamboo stalks", "single dew drops falling from bamboo leaves into stone basin", "gentle breeze rustling green bamboo leaves"],
        "environments": [
            "a stone pathway winding through towering green bamboo forest with stone lanterns in morning mist",
            "a secluded wooden tea pavilion overlooking a tranquil koi pond with floating water lilies",
            "an ancient moss-covered stone shrine nestled beside a babbling mountain brook in bamboo woods",
            "a traditional wooden water fountain clicking on stone surrounded by lush ferns and bamboo",
            "a quiet clearing in bamboo forest where a stone bridge crosses a crystal-clear spring",
            "a peaceful bamboo veranda with tatami mats overlooking misty mountain garden at dawn"
        ]
    }
}

# =========================================================================
# TOPIC-TO-VIBE MULTI-MATRIX (DIVERSE VIBE POOLS PER TOPIC)
# =========================================================================

TOPIC_VIBE_POOLS = {
    "heartbreak_departure": [
        "typewriters_voice_nostalgia", "lofi_90s_neon_rain", "shin_hanga_woodblock", "edward_hopper_solitude", "shinkai_celestial_twilight",
        "cozy_midnight_coffee_vinyl", "celtic_misty_highlands", "coastal_lighthouse_solitude", "wabi_sabi_zen_mist"
    ],
    "healing_restoration": [
        "typewriters_voice_nostalgia", "ghibli_lush_countryside", "monet_pastel_impressionism", "wabi_sabi_zen_mist", "nordic_fog_hygge",
        "misty_bamboo_zen", "autumn_ginkgo_sanctuary", "mediterranean_golden_coast", "bioluminescent_wonderland"
    ],
    "father_family_legacy": [
        "typewriters_voice_nostalgia", "dark_academia_chiaroscuro", "vintage_70s_film", "autumn_ginkgo_sanctuary", "edward_hopper_solitude",
        "ghibli_lush_countryside", "cozy_midnight_coffee_vinyl", "celtic_misty_highlands"
    ],
    "destiny_faith_universe": [
        "typewriters_voice_nostalgia", "shinkai_celestial_twilight", "surrealist_dreamscape", "bioluminescent_wonderland", "coastal_lighthouse_solitude",
        "wabi_sabi_zen_mist", "shin_hanga_woodblock", "ghibli_lush_countryside"
    ],
    "mind_wisdom_clarity": [
        "typewriters_voice_nostalgia", "dark_academia_chiaroscuro", "wabi_sabi_zen_mist", "misty_bamboo_zen", "edward_hopper_solitude",
        "shinkai_celestial_twilight", "cozy_midnight_coffee_vinyl", "shin_hanga_woodblock"
    ],
    "solitude_night_reflection": [
        "typewriters_voice_nostalgia", "lofi_90s_neon_rain", "cozy_midnight_coffee_vinyl", "shinkai_celestial_twilight", "edward_hopper_solitude",
        "shin_hanga_woodblock", "nordic_fog_hygge", "coastal_lighthouse_solitude"
    ],
    "love_devotion_connection": [
        "typewriters_voice_nostalgia", "monet_pastel_impressionism", "ghibli_lush_countryside", "autumn_ginkgo_sanctuary", "mediterranean_golden_coast",
        "shinkai_celestial_twilight", "vintage_70s_film", "bioluminescent_wonderland"
    ],
    "courage_resilience_strength": [
        "typewriters_voice_nostalgia", "celtic_misty_highlands", "coastal_lighthouse_solitude", "wabi_sabi_zen_mist", "shinkai_celestial_twilight",
        "nordic_fog_hygge", "autumn_ginkgo_sanctuary"
    ],
    "time_impermanence_memory": [
        "typewriters_voice_nostalgia", "autumn_ginkgo_sanctuary", "vintage_70s_film", "shin_hanga_woodblock", "wabi_sabi_zen_mist",
        "dark_academia_chiaroscuro", "edward_hopper_solitude", "celtic_misty_highlands"
    ],
    "general_poetic_odyssey": [
        "typewriters_voice_nostalgia", "ghibli_lush_countryside", "shinkai_celestial_twilight", "lofi_90s_neon_rain", "shin_hanga_woodblock",
        "edward_hopper_solitude", "monet_pastel_impressionism", "dark_academia_chiaroscuro", "wabi_sabi_zen_mist",
        "nordic_fog_hygge", "bioluminescent_wonderland", "vintage_70s_film", "surrealist_dreamscape",
        "autumn_ginkgo_sanctuary", "mediterranean_golden_coast", "celtic_misty_highlands", "cozy_midnight_coffee_vinyl"
    ]
}

NEGATIVE_PROMPT = (
    "realistic portrait, female portrait, realistic girl, realistic woman, photorealistic human face, face close-up, selfie, glamour photo, model photo, "
    "text, words, letters, numbers, quotation, caption, typography, logo, watermark, sign, label, poster, menu, "
    "readable book cover, readable book spine, license plate, road lettering, writing-like symbols, blank text area, "
    "ugly, deformed hands, bad anatomy, extra limbs, blurry, low resolution, stock photo, 3D CGI render, photorealism artifact, gore, blood, clutter"
)

# =========================================================================
# TOPIC CLASSIFIER (ANALYZES POEM TOPIC)
# =========================================================================

def _classify_poem_topic(title: str, lines: list[str]) -> str:
    full = f"{title} {' '.join(lines)}".lower()
    
    if any(k in full for k in ["leave", "tears", "fights", "hurt", "loss", "goodbye", "alone", "lonely", "miss", "break", "leaving", "heartbreak"]):
        return "heartbreak_departure"
    if any(k in full for k in ["heal", "peace", "calm", "breathe", "rest", "soul", "forgive", "freedom", "gratitude", "soft", "light", "bloom"]):
        return "healing_restoration"
    if any(k in full for k in ["father", "dad", "mother", "mom", "child", "held me", "arms", "family", "remember", "hardest day", "gave up", "parents"]):
        return "father_family_legacy"
    if any(k in full for k in ["trust", "story", "written", "script", "detour", "meant to be", "destiny", "fate", "stars", "universe", "plan"]):
        return "destiny_faith_universe"
    if any(k in full for k in ["intelligent", "mind", "lies", "patterns", "game", "recognize", "thoughts", "thinking", "silence", "truth", "illusion"]):
        return "mind_wisdom_clarity"
    if any(k in full for k in ["midnight", "2am", "2 am", "night", "darkness", "quiet", "solitude", "empty", "sleepless", "overthinking"]):
        return "solitude_night_reflection"
    if any(k in full for k in ["love", "heart", "stay", "cherish", "together", "connection", "devotion", "forever", "embrace", "tender"]):
        return "love_devotion_connection"
    if any(k in full for k in ["courage", "strong", "strength", "survive", "warrior", "battle", "rise", "stand", "overcome", "endure"]):
        return "courage_resilience_strength"
    if any(k in full for k in ["time", "years", "seasons", "autumn", "aging", "clock", "memories", "yesterday", "passed", "fleeting"]):
        return "time_impermanence_memory"
    
    return "general_poetic_odyssey"

# =========================================================================
# POETIC SEMANTIC PARSER & MOTIF EXTRACTOR (ENGLISH & NEPALI/DEVANAGARI)
# =========================================================================

MOTION_STYLES_POOL = [
    "slow_zoom_in",
    "slow_zoom_out",
    "slow_pan_left",
    "slow_pan_right",
    "slow_drift_up",
    "slow_drift_down",
"slow_diagonal_drift"
]

def _extract_poetic_motifs(line: str, topic: str = "") -> dict:
    """
    Deep semantic poem analyzer.
    Extracts the HUMAN SUBJECT, emotional meaning, relationship, action/gesture,
    and setting from the actual poem line — so that generated images directly
    portray what the poem is about, not generic landscapes.
    Works on English and Nepali / Devanagari text.
    """
    lower = line.lower()

    # ── 1. HUMAN SUBJECT DETECTION (highest priority) ──────────────────────
    # Identifies the actual person/relationship the poem is about
    human_subject = None

    if any(k in lower for k in ["father", "dad", "papa", "बुबा", "बाबा", "पिता", "my old man"]):
        human_subject = "father"
    elif any(k in lower for k in ["mother", "mom", "mama", "आमा", "माता", "mum"]):
        human_subject = "mother"
    elif any(k in lower for k in ["child", "son", "daughter", "baby", "little one", "छोरा", "छोरी", "बच्चा", "सन्तान"]):
        human_subject = "child"
    elif any(k in lower for k in ["lover", "beloved", "darling", "sweetheart", "partner", "husband", "wife",
                                   "प्रेमी", "प्रेमिका", "साथी", "श्रीमान", "श्रीमती"]):
        human_subject = "lover"
    elif any(k in lower for k in ["friend", "friendship", "साथी", "मित्र", "दोस्त"]):
        human_subject = "friend"
    elif any(k in lower for k in ["self", "myself", "i am", "i was", "i have", "i've", "i'm", "i kept", "i'm proud", "you kept", "you were", "you felt", "you looked"]):
        human_subject = "self_reflection"
    elif any(k in lower for k in ["stranger", "someone", "person", "figure", "soul", "अर्को", "कोही"]):
        human_subject = "anonymous_figure"

    # ── 2. EMOTIONAL CORE ──────────────────────────────────────────────────
    emotion = "quiet contemplation"
    if any(k in lower for k in ["sacrifice", "gave up", "gave everything", "worked", "struggled", "hardship", "suffering", "tired", "worn", "burden"]):
        emotion = "sacrifice and silent struggle"
    elif any(k in lower for k in ["proud", "pride", "admire", "strength", "resilience", "kept going", "didn't give up", "persevere"]):
        emotion = "quiet pride and resilience"
    elif any(k in lower for k in ["love", "tenderness", "devotion", "cherish", "hold", "embrace", "माया", "स्नेह"]):
        emotion = "tender love and devotion"
    elif any(k in lower for k in ["grief", "loss", "miss", "gone", "tears", "hurt", "pain", "ache", "broken", "दुःख", "पीडा"]):
        emotion = "deep grief and longing"
    elif any(k in lower for k in ["heal", "peace", "calm", "breathe", "rest", "freedom", "hope", "better", "bloom"]):
        emotion = "healing and gentle hope"
    elif any(k in lower for k in ["alone", "lonely", "empty", "silence", "dark", "midnight", "lost", "एक्लो", "सन्नाटा"]):
        emotion = "solitude and introspection"
    elif any(k in lower for k in ["joy", "happy", "smile", "laugh", "celebrate", "beautiful", "wonderful"]):
        emotion = "warmth and quiet joy"

    # ── 3. KEY ACTION / GESTURE ────────────────────────────────────────────
    action = None
    if any(k in lower for k in ["working", "worked hard", "working hard", "labor", "build", "built", "carry", "carried", "lift", "lifted"]):
        action = "toiling with weathered hands in humble labor"
    elif any(k in lower for k in ["walking", "walked", "journey", "path", "road", "moving forward", "kept going"]):
        action = "walking a long road alone at dusk"
    elif any(k in lower for k in ["sitting", "sat", "rest", "resting", "waiting", "alone in"]):
        action = "sitting quietly in still solitude"
    elif any(k in lower for k in ["holding", "held", "embrace", "hug", "arms", "touch", "hand"]):
        action = "holding with quiet protective tenderness"
    elif any(k in lower for k in ["looking", "watching", "staring", "gazing", "seeing", "saw"]):
        action = "gazing into the distance with quiet reflection"
    elif any(k in lower for k in ["crying", "cried", "tears", "weeping", "wept"]):
        action = "standing still with tears unseen"
    elif any(k in lower for k in ["sleeping", "asleep", "dreaming", "dream"]):
        action = "resting in quiet dreamlike stillness"

    # ── 4. WEATHER & ATMOSPHERE ────────────────────────────────────────────
    weather = "crisp atmospheric clarity with subtle floating dust motes"
    if any(k in lower for k in ["rain", "rainy", "storm", "drizzle", "puddle", "पानी", "झरी", "बर्षा"]):
        weather = "gentle cinematic rainfall creating delicate concentric rings on wet cobblestones"
    elif any(k in lower for k in ["snow", "winter", "frost", "cold", "हिउँ", "चिसो"]):
        weather = "soft delicate snowflakes drifting in quiet winter stillness"
    elif any(k in lower for k in ["mist", "fog", "haze", "कुहिरो", "हुस्सु"]):
        weather = "ethereal swirling mist and low-hanging atmospheric fog"
    elif any(k in lower for k in ["sun", "sunlight", "warm", "golden", "घाम", "उज्यालो"]):
        weather = "radiant golden sunbeams casting long warm shadows"
    elif any(k in lower for k in ["wind", "breeze", "हावा", "बतास"]):
        weather = "a gentle rustling breeze carrying fallen leaves"

    # ── 5. TIME OF DAY ─────────────────────────────────────────────────────
    time_of_day = "under dramatic atmospheric lighting with rich layered depth"
    if any(k in lower for k in ["star", "galaxy", "constellation", "cosmos", "तारा", "आकाश"]):
        time_of_day = "under an expansive starry midnight sky"
    elif any(k in lower for k in ["moon", "moonlight", "lunar", "चन्द्रमा", "जून"]):
        time_of_day = "bathed in the silver luminescence of a full moon"
    elif any(k in lower for k in ["night", "midnight", "dark", "2am", "रात", "अँध्यारो"]):
        time_of_day = "in the deep quiet of a nocturnal midnight"
    elif any(k in lower for k in ["sunset", "twilight", "evening", "साँझ", "क्षितिज"]):
        time_of_day = "during breathtaking magic-hour golden twilight"
    elif any(k in lower for k in ["morning", "dawn", "sunrise", "बिहानी", "उषा"]):
        time_of_day = "at peaceful early dawn with soft pastel light"

    # ── 6. SETTING / SCENERY ───────────────────────────────────────────────
    scenery_parts = []
    if any(k in lower for k in ["field", "farm", "crops", "harvest", "soil", "खेत", "माटो"]):
        scenery_parts.append("a humble rural field with dark soil and golden crops")
    if any(k in lower for k in ["home", "house", "room", "kitchen", "door", "घर", "कोठा", "ढोका"]):
        scenery_parts.append("a modest weathered home with warm amber window light")
    if any(k in lower for k in ["road", "path", "street", "alley", "बाटो", "सडक", "गल्ली"]):
        scenery_parts.append("a long empty road stretching toward a dim horizon")
    if any(k in lower for k in ["mountain", "hill", "valley", "पहाड", "हिमाल", "डाँडा"]):
        scenery_parts.append("vast mountain silhouettes shrouded in evening mist")
    if any(k in lower for k in ["water", "river", "lake", "ocean", "नदी", "ताल", "समुद्र"]):
        scenery_parts.append("calm reflective water mirroring the heavy sky above")
    if any(k in lower for k in ["tree", "forest", "wood", "रुख", "वन", "जङ्गल"]):
        scenery_parts.append("ancient trees standing in quiet mossy stillness")
    if any(k in lower for k in ["bench", "chair", "table", "light", "lamp", "candle"]):
        scenery_parts.append("a single dim lamp casting warm amber light across worn surfaces")
    if not scenery_parts:
        scenery_parts = ["a quiet timeless setting with rich atmospheric depth"]

    scenery = random.choice(scenery_parts)

    return {
        "human_subject": human_subject,
        "emotion": emotion,
        "action": action,
        "weather": weather,
        "time_of_day": time_of_day,
        "scenery": scenery,
        "raw_line": line
    }

# =========================================================================
# PROMPT SYNTHESIS & PLANNING ENGINE
# =========================================================================

def _procedural_scene_prompt(line: str, scene_idx: int, total_scenes: int, vibe: dict) -> str:
    """
    Generates a fine-art image prompt that is semantically locked to the poem's
    actual subject, emotional meaning, and human relationships.
    - Explicitly genders subjects (father = old man, mother = woman)
    - Forces Typewriters Voice / Guy Billout editorial linocut style
    - Hard-bans: AI portrait defaults, white borders, photorealistic faces, frames
    """
    vibe_id = vibe.get("id", "") or ""
    vibe_name = vibe.get("name", "") or ""
    is_typewriter_vibe = "typewriter" in vibe_id.lower() or "typewriter" in vibe_name.lower()

    motifs = _extract_poetic_motifs(line)
    human_subject = motifs.get("human_subject")
    emotion = motifs.get("emotion", "quiet contemplation")
    action = motifs.get("action")
    weather = motifs.get("weather", "crisp atmospheric clarity")
    time_of_day = motifs.get("time_of_day", "under soft atmospheric lighting")
    scenery = motifs.get("scenery", "a quiet timeless setting with rich atmospheric depth")

    # ── STRICT ART STYLE: Guy Billout editorial illustration ─────────────────
    # This style description MUST appear at the front so AI models prioritize it
    if is_typewriter_vibe:
        art_style = (
            "Editorial linocut woodblock illustration, Guy Billout style, Typewriters Voice aesthetic. "
            "Flat bold ink shapes with fine cross-hatch shading, gouache paint texture, "
            "high contrast deep navy and slate blue shadows with warm amber and mustard yellow light accents. "
            "Bold graphic composition, slightly abstracted, NO photorealism"
        )
        atm_variants = [
            "moody deep midnight navy and slate blue tones with fine cross-hatch woodcut texture throughout",
            "deep dark starlit night with fine horizontal hatch lines and glinting amber lantern glow",
            "quiet rainy evening with fine textural cross-hatching and warm amber glow on dark wet surfaces",
            "high contrast chiaroscuro with bright warm golden light pooling against deep charcoal shadows",
            "peaceful nocturnal mist with soft amber lantern light and deep indigo background",
        ]
    else:
        art_style = (
            "Fine art painterly illustration, oil painting style, Rembrandt chiaroscuro lighting. "
            "Rich paint textures, expressive brushwork, emotionally charged atmosphere. "
            "NOT photorealistic, NOT a photograph, NOT digital render"
        )
        atm_variants = [
            "warm painterly golden hour light with long dramatic shadows and rich impasto texture",
            "cool blue-hour twilight with soft diffused ambient glow and loose brushwork",
            "dramatic overcast light with rich muted tones and heavy emotional atmosphere",
            "soft morning mist with hazy diffused pastel light and gentle painterly strokes",
            "warm candlelit amber light contrasting against deep velvety darkness",
        ]

    # Per-line seeded atmosphere selection for variety
    poem_seed = int(hashlib.md5(f"{line}:{scene_idx}".encode()).hexdigest()[:8], 16)
    rng = random.Random(poem_seed)
    shuffled_atms = atm_variants[:]
    rng.shuffle(shuffled_atms)
    atmosphere = shuffled_atms[scene_idx % len(shuffled_atms)]

    # ── SUBJECT-DRIVEN SCENE (explicitly gendered to prevent AI face defaults) ───

    # Negative suffix per subject type to explicitly ban wrong gender/style
    SUBJECT_NEGATIVE = {
        "father": "no woman, no female face, no girl, no young face, no glamour portrait",
        "mother": "no man, no male face, no boy, no military figure",
        "child": "no adult face, no glamour, no model",
        "lover": "no violence, no explicit content",
        "self_reflection": "no crowd, no multiple figures",
        "friend": "no violence",
        "anonymous_figure": "no specific face",
    }

    # Full subject scene templates — EXPLICIT gender language prevents AI from defaulting to young women
    SUBJECT_SCENE_TEMPLATES = {
        "father": [
            # Always: old man, weathered, calloused, heavy shoulders — NEVER generic "figure"
            "a lone elderly man — weathered face, grey stubble, heavy stooped shoulders — "
            "{action_phrase} at {scenery}, {time_of_day}. "
            "His roughened calloused hands and worn simple clothing tell decades of silent sacrifice. "
            "Seen from behind or in silhouette, conveying {emotion}",

            "close painterly view of an old man's rough calloused hands resting on a table or tool, "
            "{scenery} dimly behind him, {time_of_day}. "
            "No face shown — only the hands that carried a family's weight. Emotion: {emotion}",

            "a tired old man in simple worn clothes {action_phrase}, "
            "small and solitary against {scenery}, {time_of_day}. "
            "His bent posture and heavy steps show years of sacrifice. Feeling: {emotion}",

            "silhouette of a working-class old man standing alone at {scenery}, {time_of_day}, "
            "facing away from viewer toward the horizon, his coat worn, his figure humble and strong. "
            "The weight of {emotion} is in every line of his shape",
        ],
        "mother": [
            "a gentle older woman in simple house clothes {action_phrase} at {scenery}, {time_of_day}. "
            "Her silhouette seen from behind, soft and protective, the atmosphere carrying {emotion}",

            "close painterly view of a woman's gentle hands — folded quietly or reaching — "
            "with {scenery} warm and soft behind her, {time_of_day}. "
            "Her presence carries {emotion}",

            "a lone older woman standing quietly at {scenery}, {time_of_day}, "
            "her posture carrying quiet strength and {emotion}",
        ],
        "child": [
            "a small child silhouette standing in {scenery}, {time_of_day}, "
            "tiny and alone in a vast quiet world filled with {emotion}",

            "a child sitting quietly with small hands resting still, "
            "{scenery} behind them, {time_of_day}. The atmosphere holds {emotion}",
        ],
        "lover": [
            "two distant silhouettes — a man and a woman — standing apart at {scenery}, {time_of_day}. "
            "The space between them is charged with {emotion}",

            "a lone figure standing at {scenery}, {time_of_day}, {action_phrase}. "
            "The mood of {emotion} woven through every shadow",
        ],
        "friend": [
            "two human figures walking side by side through {scenery}, {time_of_day}. "
            "The quiet companionship of {emotion} in their shared pace",

            "a solitary figure sitting at {scenery}, {time_of_day}, "
            "lost in the memory of {emotion}",
        ],
        "self_reflection": [
            "a lone human figure — back to viewer — standing small at {scenery}, {time_of_day}. "
            "{action_phrase}. The composition is saturated with {emotion}",

            "wide shot: a single small figure dwarfed by {scenery}, {time_of_day}. "
            "Their posture carries the weight and grace of {emotion}",

            "a solitary silhouette at {scenery}, {time_of_day}, "
            "turned inward. A quiet painting of {emotion} and honest self-reflection",
        ],
        "anonymous_figure": [
            "a solitary anonymous human figure at {scenery}, {time_of_day}, {action_phrase}. "
            "Identity undefined — only the feeling of {emotion} matters",
        ],
    }

    LANDSCAPE_TEMPLATES = [
        "A vast emotionally charged scene: {scenery}, {time_of_day}, {weather}. "
        "Every shadow and light carries the feeling of {emotion}. "
        "No human faces, wide cinematic composition",

        "A fine-art landscape: {scenery} under {time_of_day}, {weather}. "
        "{emotion} infuses every corner of the frame through color, light, and texture",

        "{scenery}, {time_of_day}. {weather}. "
        "The overwhelming feeling is {emotion} — captured through atmosphere not faces",
    ]

    action_phrase = action if action else "standing in quiet still contemplation"

    if human_subject and human_subject in SUBJECT_SCENE_TEMPLATES:
        templates = SUBJECT_SCENE_TEMPLATES[human_subject]
        shuffled_templates = templates[:]
        rng.shuffle(shuffled_templates)
        template = shuffled_templates[scene_idx % len(shuffled_templates)]
        scene_description = template.format(
            action_phrase=action_phrase,
            scenery=scenery,
            time_of_day=time_of_day,
            emotion=emotion,
        )
        subject_negative = SUBJECT_NEGATIVE.get(human_subject, "")
    else:
        template = LANDSCAPE_TEMPLATES[scene_idx % len(LANDSCAPE_TEMPLATES)]
        scene_description = template.format(
            scenery=scenery,
            time_of_day=time_of_day,
            weather=weather,
            emotion=emotion,
        )
        subject_negative = ""

    # ── UNIVERSAL STRICT NEGATIVE TAGS (appended to every prompt) ────────────
    # These prevent ALL the bad outputs seen in the screenshots
    universal_negative = (
        "no white border, no white frame, no black bar, no letterbox, no pillarbox, "
        "no vignette frame, no oval frame, no polaroid border, no film border, "
        "no picture frame, no canvas edge, no margin, no padding, no watermark, "
        "no text, no words, no letters, no typography, no logo, "
        "no photorealistic portrait, no stock photo, no AI face default, "
        "no glamour, no fashion photo, no beauty shot, no selfie, no close-up face, "
        "no anime girl, no realistic woman unless mother poem, no deformed anatomy"
    )

    if subject_negative:
        universal_negative = subject_negative + ", " + universal_negative

    # ── FINAL PROMPT ASSEMBLY ────────────────────────────────────────────────
    prompt = (
        f"{art_style}. "
        f"{scene_description}. "
        f"{atmosphere}. {weather}. "
        f"Masterpiece, 8k, edge-to-edge full bleed 9:16 portrait, "
        f"no borders, no frames, no white background. "
        f"{universal_negative}"
    )
    return prompt






def _normalize_prompt(prompt: str, suffix: str = "") -> str:
    prompt = re.sub(r"\s+", " ", prompt.replace("\n", " ")).strip(" \"'")
    prompt = re.sub(r"^(prompt|visual query|image prompt)\s*:\s*", "", prompt, flags=re.I)
    for marker in ("Animation_prompt:", "animation_prompt:", "Motion:", "motion:"):
        if marker in prompt:
            prompt = prompt.split(marker, 1)[0].rstrip(" ,.;:")
    
    if " | " in prompt:
        scene, _, existing_suffix = prompt.partition(" | ")
        suffix = suffix or existing_suffix
    else:
        scene = prompt
        suffix = suffix or "fine art aesthetic anime illustration, vertical 9:16 composition, no text, no writing"

    words = scene.split()
    if len(words) > 130:
        words = words[:130]
        while len(words) > 10 and _fragment(words):
            words.pop()
        scene = " ".join(words).rstrip(" ,.;:")

    if "no text" not in suffix.lower():
        suffix = suffix.rstrip(" ,.;:") + ", no text, no writing"

    return scene.strip() + " | " + suffix.strip()


def _fragment(words: list[str]) -> bool:
    if not words:
        return True
    last = re.sub(r"[^a-z-']", "", words[-1].lower())
    return last.endswith("'s") or last in {
        "a", "an", "the", "and", "or", "with", "to", "of", "for", "from", "under", "over",
        "toward", "through", "into", "beside", "beneath", "above", "below", "gently", "softly",
        "distant", "winding", "reaching", "holding", "waiting", "stretching", "trailing", "fading"
    }


def generate_plan(data: dict, settings: dict | None = None) -> dict:
    settings = settings or _load_settings()
    script = str(data.get("script") or "").strip()
    lines = _lines(script)
    title = str(data.get("title") or data.get("name") or "Poetic Story").strip()
    if not lines:
        return _fallback_plan(title, lines)

    # 1. Classify Topic & Vibe
    explicit_vibe = str(data.get("vibe") or data.get("custom_vibe") or "").strip().lower()
    topic_category = _classify_poem_topic(title, lines)
    
    chosen_vibe_id = None
    if explicit_vibe:
        norm_exp = explicit_vibe.replace("_", " ").strip()
        for vid in ARTISTIC_VIBES:
            norm_vid = vid.replace("_", " ").strip()
            norm_name = ARTISTIC_VIBES[vid].get("name", "").lower()
            if (
                norm_vid in norm_exp
                or norm_exp in norm_vid
                or ("typewriter" in norm_exp and "typewriter" in norm_vid)
                or norm_exp in norm_name
                or norm_name in norm_exp
            ):
                chosen_vibe_id = vid
                break
                
    if not chosen_vibe_id:
        candidate_vibes = TOPIC_VIBE_POOLS.get(topic_category, TOPIC_VIBE_POOLS["general_poetic_odyssey"])
        chosen_vibe_id = db.pick_novel_vibe(topic_category, candidate_vibes)
        
    vibe = ARTISTIC_VIBES.get(chosen_vibe_id, ARTISTIC_VIBES["typewriters_voice_nostalgia"])
    vibe["id"] = chosen_vibe_id or "typewriters_voice_nostalgia"

    # 3. Try Ollama Planning
    models = _candidate_models(settings)
    prompt = _build_llm_prompt(title, lines, topic_category, vibe)

    for model in models:
        try:
            raw = _ollama_generate(settings["ollama_url"], model, prompt, vibe)
            candidate = _parse_json(raw)
            normalized = _normalize_plan(candidate, title, lines, topic_category, vibe)
            if _valid_plan(normalized, len(lines)):
                normalized["model"] = model
                db.record_generation(title, script, topic_category, chosen_vibe_id, str(vibe["palettes"][0]), str(vibe["lighting"][0]), "Ollama Plan")
                return normalized
        except Exception:
            continue

    # 4. High-Entropy Procedural Fallback
    plan = _fallback_plan(title, lines, topic_category, vibe)
    db.record_generation(title, script, topic_category, chosen_vibe_id, str(vibe["palettes"][0]), str(vibe["lighting"][0]), "Procedural Plan")
    return plan


def _build_llm_prompt(title: str, lines: list[str], topic: str, vibe: dict) -> str:
    numbered = "\n".join(f"Line {i + 1}: {line}" for i, line in enumerate(lines))
    sample_envs = "\n- ".join(vibe["environments"][:4])
    
    return f"""POEM TITLE: {title}
TOPIC CATEGORY: {topic.replace('_', ' ').title()}
CHOSEN ARTISTIC VIBE & AESTHETIC: {vibe['name']}
MEDIUM & STYLE DIRECTION: {vibe['medium_suffix']}
COLOR PALETTES: {', '.join(vibe['palettes'])}

SAMPLE ENVIRONMENT MOTIFS FOR INSPIRATION:
- {sample_envs}

POEM LINES:
{numbered}

TASK:
1. Create a cohesive, stunning visual story for this poem in the style of '{vibe['name']}'.
2. For each line, write a full 70-110 word prompt that visually embodies the emotion of that line.
3. Every single scene must have a completely unique environment, camera angle, and lighting condition.
4. Keep each 'narration' field exactly identical to its line.
5. End every prompt with: | {vibe['medium_suffix']}
6. Output JSON only.
"""


def _normalize_plan(candidate: dict, title: str, lines: list[str], topic: str, vibe: dict) -> dict:
    raw_scenes = candidate.get("scenes") if isinstance(candidate, dict) else []
    if not isinstance(raw_scenes, list):
        raw_scenes = []
    
    scenes = []
    total = len(lines)
    for index, line in enumerate(lines):
        raw = raw_scenes[index] if index < len(raw_scenes) and isinstance(raw_scenes[index], dict) else {}
        raw_prompt = str(raw.get("prompt") or raw.get("image_prompt") or raw.get("visual_prompt") or "").strip()
        
        if raw_prompt and len(raw_prompt.split()) >= 20 and not _is_portrait_leak(raw_prompt):
            prompt = _normalize_prompt(raw_prompt, vibe["medium_suffix"])
        else:
            prompt = _procedural_scene_prompt(line, index, total, vibe)

        # Assign diverse motion style
        motion = raw.get("motion")
        if motion not in MOTION_STYLES_POOL:
            motion = MOTION_STYLES_POOL[index % len(MOTION_STYLES_POOL)]

        scenes.append({
            "id": f"scene_{index + 1:03d}",
            "duration": max(3.0, min(6.0, float(raw.get("duration", 4.0) or 4.0))),
            "narration": line,
            "prompt": prompt,
            "motion": motion,
        })

    bible = candidate.get("style_bible") if isinstance(candidate, dict) else {}
    if not isinstance(bible, dict):
        bible = {}
    bible["topic"] = topic
    bible["artistic_vibe"] = vibe["name"]
    bible["negative_prompt"] = NEGATIVE_PROMPT

    return {"title": title, "style_bible": bible, "scenes": scenes}


def _fallback_plan(title: str, lines: list[str], topic: str = "", vibe: dict | None = None) -> dict:
    topic = topic or _classify_poem_topic(title, lines)
    if not vibe:
        candidate_vibes = TOPIC_VIBE_POOLS.get(topic, TOPIC_VIBE_POOLS["general_poetic_odyssey"])
        chosen_vibe_id = db.pick_novel_vibe(topic, candidate_vibes)
        vibe = ARTISTIC_VIBES.get(chosen_vibe_id, ARTISTIC_VIBES["ghibli_lush_countryside"])
        vibe["id"] = chosen_vibe_id

    scenes = []
    total = len(lines)
    for index, line in enumerate(lines):
        prompt = _procedural_scene_prompt(line, index, total, vibe)
        motion = MOTION_STYLES_POOL[index % len(MOTION_STYLES_POOL)]
        scenes.append({
            "id": f"scene_{index + 1:03d}",
            "duration": 4.0,
            "narration": line,
            "prompt": prompt,
            "motion": motion,
        })
    return {
        "title": title,
        "style_bible": {
            "topic": topic,
            "artistic_vibe": vibe["name"],
            "negative_prompt": NEGATIVE_PROMPT,
        },
        "scenes": scenes,
        "model": "database-multi-vibe-director",
    }


def _is_portrait_leak(prompt: str) -> bool:
    lower = prompt.lower()
    return any(p in lower for p in [
        "girl with blonde hair", "scandinavian woman", "young woman in", "curvy feminine",
        "nordic woman", "beautiful woman", "female portrait", "face close-up", "bikini",
        "cleavage", "model pose", "glamour shot"
    ])


def _valid_prompt(prompt: str) -> bool:
    lower = prompt.lower()
    if _is_portrait_leak(lower):
        return False
    if any(x in lower for x in ("stock photo", "logo", "watermark", "robot", "gore", "blood", "typography")):
        return False
    scene = re.split(r"\s[|—]\s", prompt, maxsplit=1)[0]
    words = scene.split()
    return 15 <= len(words) <= 150


def _valid_plan(plan: dict, expected: int) -> bool:
    scenes = plan.get("scenes", [])
    return len(scenes) == expected and all(_valid_prompt(str(x.get("prompt", ""))) for x in scenes)


def _lines(script: str) -> list[str]:
    raw = str(script or '').replace('\r\n', '\n').replace('\r', '\n')
    line_rows = [x.strip() for x in raw.split('\n') if x.strip()]
    if len(line_rows) < 2:
        line_rows = [x.strip() for x in re.split(r"(?<=[.!?।॥])\s+|\n+", raw) if x.strip()]
    if not line_rows:
        return []

    stanzas: list[str] = []
    buffer = ""
    for line in line_rows:
        words = line.split()
        if buffer:
            buffer = f"{buffer} {line}".strip()
            if len(buffer.split()) >= 4 or len(buffer) >= 20:
                stanzas.append(buffer)
                buffer = ""
        else:
            if len(words) < 4 and len(line) < 20:
                buffer = line
            else:
                stanzas.append(line)

    if buffer:
        if stanzas:
            stanzas[-1] = f"{stanzas[-1]} {buffer}".strip()
        else:
            stanzas.append(buffer)

    return stanzas


def _load_settings() -> dict:
    path = Path(__file__).resolve().parent / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {"ollama_url": "http://127.0.0.1:11434", "ollama_model": "auto"}


def _ollama_generate(base_url: str, model: str, prompt: str, vibe: dict) -> str:
    system_prompt = f"""You are a fine-art visual director and poetic visual storyteller.
Your task is to create image generation prompts in the specific art aesthetic: '{vibe['name']}'.
Style Medium: {vibe['medium_suffix']}

STRICT RULES:
1. Absolutely ZERO realistic portraits, female face close-ups, selfies, or glamour shots. Focus on landscapes, nature, architecture, atmospheric light, celestial skies, and tiny silhouettes in expansive negative space.
2. Every scene must have a completely DIFFERENT visual setting, camera framing, light direction, and atmospheric particles.
3. Absolutely ZERO text, words, letters, quotes, captions, signs, logos, or typography inside the prompt.
4. Return JSON ONLY with the exact structure required.
"""
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.85, "top_p": 0.95, "repeat_penalty": 1.18, "num_predict": 2400},
    }
    request = Request(
        base_url.rstrip("/") + "/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8", "replace")).get("response", "")


def _candidate_models(settings: dict) -> list[str]:
    configured = str(settings.get("artwork_prompt_model", "auto")).strip()
    if configured.lower() in ("none", "disabled", "procedural", "false"):
        return []
    try:
        request = Request(settings.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/tags")
        with urlopen(request, timeout=1.5) as response:
            installed = [str(x.get("name", "")).strip() for x in json.loads(response.read().decode("utf-8", "replace")).get("models", [])]
    except Exception:
        return []
    installed = [x for x in installed if x and "embed" not in x.lower()]
    order = [x.strip() for x in str(settings.get("artwork_prompt_model_order", ",".join(DEFAULT_ORDER))).split(",") if x.strip()]
    result: list[str] = []
    if configured and configured.lower() != "auto":
        match = next((actual for actual in installed if _model_matches(configured, actual)), None)
        if match:
            result.append(match)
    for wanted in order:
        match = next((actual for actual in installed if _model_matches(wanted, actual)), None)
        if match and match not in result:
            result.append(match)
    if not result and installed:
        result.append(installed[0])
    return result


def _model_matches(wanted: str, installed: str) -> bool:
    wanted = wanted.lower().strip()
    installed = installed.lower().strip()
    return wanted == installed or installed.startswith(wanted + ":") or installed.startswith(wanted + "-") or wanted in installed


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(raw[start:])
        return value

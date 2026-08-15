"""The planning agent.

Reads the author's own words, extracts intent, and emits a sequenced action
plan with each item routed to either an agent or a human via Terac. Pricing is
order-level (flat tariff), not per item — `price_order` builds the live quote
and `trim_order` shrinks an order to fit a budget. This is a direct port of
the logic that ran client-side in index_1.html.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bookit.content import PRICE

# Ordered on purpose: the first key found in the text wins, exactly like the
# original `for (const k in map)` lookup.
LANGS = {
    "german": "German", "spanish": "Spanish", "french": "French",
    "japanese": "Japanese", "mandarin": "Mandarin", "chinese": "Mandarin",
    "portuguese": "Portuguese", "italian": "Italian", "korean": "Korean",
    "arabic": "Arabic", "dutch": "Dutch", "polish": "Polish", "hindi": "Hindi",
    "swedish": "Swedish", "turkish": "Turkish", "russian": "Russian",
}

GENRES = {
    "fantasy": "fantasy", "sci-fi": "science fiction",
    "science fiction": "science fiction", "romance": "romance",
    "thriller": "thriller", "mystery": "mystery", "horror": "horror",
    "memoir": "memoir", "self-help": "self-help", "poetry": "poetry",
    "young adult": "YA", "ya": "YA", "children": "children's",
    "literary": "literary fiction", "business": "business",
    "cookbook": "cookbook", "history": "history",
    "non-fiction": "non-fiction", "nonfiction": "non-fiction",
    "crime": "crime", "picture book": "picture book",
}

PLATFORMS = {
    "amazon": "Amazon KDP", "kdp": "Amazon KDP", "kobo": "Kobo",
    "apple": "Apple Books", "ingram": "IngramSpark", "audible": "Audible",
    "barnes": "Barnes & Noble Press",
}

CAP = 11        # hard ceiling on plan length — a plan nobody reads is not a plan
MAX_COVERS = 8  # stepper bounds for the order form
MAX_LANGS = 5


@dataclass
class Reading:
    """What the agent understood from the manuscript and the description."""

    genre: str = "general"
    langs: list[str] = field(default_factory=list)
    platform: str | None = None
    budget: int | None = None
    words: str | None = None
    title: str = "Your Manuscript"
    debut: bool = False
    audiobook: bool = False
    series: bool = False
    deadline: bool = False
    audience: str | None = None


@dataclass
class PlanItem:
    """One action item: what it is, who does it, which line item covers it."""

    phase: int
    title: str
    why: str
    owner: str    # "agent" | "human"
    covered: str  # which tariff line pays for it, e.g. "Publishing"

    @property
    def is_human(self) -> bool:
        return self.owner == "human"


def _find(text: str, table: dict[str, str]) -> str | None:
    for key, value in table.items():
        if key in text:
            return value
    return None


def read_context(txt: str) -> Reading:
    """Pull structured intent out of a free-text description."""
    t = (txt or "").lower()

    langs: list[str] = []
    for key, value in LANGS.items():
        if key in t and value not in langs:
            langs.append(value)

    budget_m = re.search(r"\$\s?([\d,]+)", t)
    words_m = re.search(r"([\d,]{3,})[\s-]*(?:word|words)", t)
    title_m = re.search(r"called\s+([A-Z][^.,\n]{2,45})", txt or "")
    audience_m = re.search(r"for ([a-z\s]{4,28}?)(?: readers| audience|\.|,)", t)

    return Reading(
        genre=_find(t, GENRES) or "general",
        langs=langs,
        platform=_find(t, PLATFORMS),
        budget=int(budget_m.group(1).replace(",", "")) if budget_m else None,
        words=words_m.group(1) if words_m else None,
        title=title_m.group(1).strip() if title_m else "Your Manuscript",
        debut=bool(re.search(
            r"first book|debut|no contacts|don'?t know anyone|never published|first novel", t)),
        audiobook=bool(re.search(r"audiobook|audible|narrat", t)),
        series=bool(re.search(r"series|trilogy|sequel|book (one|1|two|2)", t)),
        deadline=bool(re.search(r"within a month|next month|by \w+|deadline|asap|urgent|weeks", t)),
        audience=audience_m.group(1) if audience_m else None,
    )


# ── the tariff ────────────────────────────────────────────────────────
def price_order(services: set[str], covers: int, langs: int,
                lang_names: list[str] | None = None) -> tuple[list[dict], int]:
    """The live quote: one line per tariff item, plus the total."""
    lines: list[dict] = []
    if "publish" in services:
        lines.append({"k": "Publishing & cover design",
                      "d": "Interior, EPUB, metadata, front matter, cover testing",
                      "v": PRICE["publish"]})
        lines.append({"k": f"Cover directions × {covers}",
                      "d": f"${PRICE['per_cover']} per design",
                      "v": PRICE["per_cover"] * covers})
    if "translate" in services:
        names = ", ".join((lang_names or [])[:langs])
        lines.append({"k": f"Translation × {langs} {'language' if langs == 1 else 'languages'}",
                      "d": (names + " — " if names else "")
                           + "glossary, translation, native-speaker review",
                      "v": PRICE["per_language"] * langs})
    if "market" in services:
        lines.append({"k": "Marketing",
                      "d": "Blurb and title testing, keywords, launch sequence, pricing survey",
                      "v": PRICE["market"]})
    return lines, sum(x["v"] for x in lines)


def trim_order(budget: int, services: set[str], covers: int,
               langs: int) -> tuple[set[str], int, int, list[str]]:
    """Shrink an order until it fits the budget, cheapest sacrifice first.

    Returns the trimmed (services, covers, langs) plus the names of any
    services that had to be dropped entirely — so the app can always say what
    it could not do rather than silently failing.
    """
    services = set(services)
    dropped: list[str] = []
    for _ in range(40):
        if price_order(services, covers, langs)[1] <= budget:
            break
        if covers > 1:
            covers -= 1
        elif langs > 1:
            langs -= 1
        elif "market" in services:
            services.discard("market")
            dropped.append("Marketing")
        elif "translate" in services:
            services.discard("translate")
            dropped.append("Translation")
        else:
            break
    return services, covers, langs, dropped


def make_plan(r: Reading, services: set[str], covers: int = 4) -> list[PlanItem]:
    """Build a plan for *this* book, not a checklist."""
    lang = r.langs[0] if r.langs else "your target language"
    plat = r.platform or "Amazon KDP"
    genre_or_yours = "your genre" if r.genre == "general" else r.genre
    typeset_conv = "trade fiction" if r.genre == "general" else r.genre
    in_your_genre = "in your genre" if r.genre == "general" else r.genre

    always = [
        PlanItem(0, "Extract and clean the manuscript",
                 f"Parses your {r.words + '-word ' if r.words else ''}file, repairs broken "
                 "paragraphs, normalises quotes and dashes, and detects chapter boundaries. "
                 "Everything downstream depends on this being right.", "agent", "Publishing"),
    ]

    covers_why = (
        f"{covers} genuinely different approaches for {genre_or_yours} — typographic, "
        "illustrated, photographic and a deliberately conventional control — so the reader "
        "panel has a real choice to rank."
        if covers > 1 else
        f"One cover direction for {genre_or_yours}. Ordering more gives the reader panel "
        "something to compare against, which is where the useful signal comes from.")

    bucket: dict[str, list[PlanItem]] = {
        "translate": [
            PlanItem(1, f"Build a {lang} translation glossary",
                     f"Extracts every character, place and invented term from your {r.genre} "
                     f"manuscript and locks a single {lang} rendering for each — so chapter 40 "
                     "doesn't rename your protagonist.", "agent", "Translation"),
            PlanItem(3, f"Native {lang} speaker reviews the sample",
                     "A fluent reader marks anything that sounds machine-written and rewrites "
                     "the worst passages. Bookit feeds their corrections back before "
                     "translating the rest.", "human", "Translation"),
            PlanItem(2, f"Translate a sample chapter into {lang}",
                     "A full-book translation before you've checked quality is how money gets "
                     "wasted. One chapter first, glossary-locked, so a human can judge it.",
                     "agent", "Translation"),
            PlanItem(3, f"Localise the title and blurb for the {lang} market",
                     "Literal title translations regularly land badly. Three localised options, "
                     "tested with real readers rather than chosen by a model.",
                     "human", "Translation"),
        ],
        "publish": [
            PlanItem(1, "Typeset a print-ready interior",
                     f"Applies {typeset_conv} conventions — running heads, drop caps, correct "
                     "gutters and bleed — and outputs a press-ready PDF plus a reflowable EPUB "
                     "that passes store validation.", "agent", "Publishing"),
            PlanItem(3, "Cover test with real readers",
                     "The one thing an agent cannot do. Real people pick which cover they'd take "
                     "off a shelf. Bookit ships their answer, not the model's.",
                     "human", "Publishing"),
            PlanItem(2, f"Generate {covers} cover direction{'' if covers == 1 else 's'}",
                     covers_why, "agent", "Covers"),
            PlanItem(4, f"Write {plat} metadata, categories and keywords",
                     "Category placement decides whether anyone finds your book. Builds the "
                     "description, seven backend keywords, and the two categories with the best "
                     "rank-to-competition ratio.", "agent", "Publishing"),
            PlanItem(4, "Assemble front and back matter",
                     "Copyright page, title page, dedication, also-by, and an author bio drafted "
                     "from your own description.", "agent", "Publishing"),
        ],
        "market": [
            PlanItem(3, "Blurb test with target readers",
                     f"Three back-cover blurbs, ranked by people who actually read {in_your_genre}. "
                     "The blurb is the highest-leverage 150 words in the whole book.",
                     "human", "Marketing"),
            PlanItem(4, f"Build the {plat} launch sequence",
                     "A five-post launch run, an author bio, three ad angles derived from what "
                     "test readers actually said, and a twelve-week calendar.",
                     "agent", "Marketing"),
            PlanItem(3, "Title test",
                     "Your title, plus two alternatives the agent thinks are stronger, put in "
                     "front of readers cold. Occasionally humbling.", "human", "Marketing"),
            PlanItem(3, "Price-point survey",
                     f"Asks readers in your genre what they'd expect to pay. Debut {r.genre} "
                     "pricing is guessed far more often than it's measured.",
                     "human", "Marketing"),
        ],
    }

    extras: list[PlanItem] = []
    if r.debut:
        extras.append(PlanItem(
            4, "Author positioning one-pager",
            "You mentioned this is your first book with no publishing contacts, so Bookit writes "
            "the thing you'd otherwise need an agent for: a one-page pitch with comparable titles "
            "and your audience.", "agent", "Publishing"))
    if r.series:
        extras.append(PlanItem(
            1, "Series bible",
            "Locks names, timeline and terminology across books so book two doesn't contradict "
            "book one — and so translators stay consistent.", "agent", "Publishing"))
    if r.audiobook:
        extras.append(PlanItem(
            4, "Audiobook readiness pass",
            "Flags footnotes, tables and visual jokes that break in audio, and outputs a "
            "narration-ready script.", "agent", "Publishing"))

    # Round-robin across the services the author actually chose, so every
    # selected service is represented even when the cap bites.
    active = [k for k in ("publish", "translate", "market") if k in services]
    plan = list(always)

    def room() -> int:
        return CAP - len(plan) - (1 if extras else 0)

    i = 0
    while room() > 0:
        took = False
        for key in active:
            if room() <= 0:
                break
            if i < len(bucket[key]):
                plan.append(bucket[key][i])
                took = True
        if not took:
            break
        i += 1

    if extras and len(plan) < CAP:
        plan.append(extras[0])

    plan.sort(key=lambda x: x.phase)  # stable: preserves the order above
    return plan[:CAP]

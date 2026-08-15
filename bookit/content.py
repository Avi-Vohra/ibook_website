"""Copy and configuration.

Everything a non-engineer might need to edit lives in this file.
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════
# TERAC RESULTS — paste the real numbers here, then set live = True.
# Everything on the "Human results" page reads from this dict.
# ══════════════════════════════════════════════════════════════════════
TERAC = {
    "live": False,           # ← flip to True once you have real responses
    "n": 40,                 # number of real respondents
    "launched_at": "1:30pm",  # when the opportunity went live
    "agent_pick": {
        "key": "B",
        "label": "Cover B",
        "pct": 11,
        "notes": [
            "Model ranked it #1 on composition and contrast",
            "Only 11% of readers would pick it up",
            "Most-cited word in the open responses: “template”",
        ],
    },
    "human_pick": {
        "key": "D",
        "label": "Cover D",
        "pct": 58,
        "notes": [
            "58% would pick it up in a bookstore",
            "71% said it looked most professionally published",
            "Bookit re-rendered the book with this cover automatically",
        ],
    },
    "quote": "Cover D looks like a real book. B looks like something generated.",
    "quote_by": "Terac respondent, general reader panel",
    "extra": "Blurb test: the agent ranked our third blurb last. "
             "Readers ranked it first, 2 to 1. Bookit swapped it.",
}

SAMPLE_CTX = (
    "I've written a 62,000-word fantasy novel called The Salt Road, aimed at young adult "
    "readers who liked Piranesi and Uprooted. It's my first book and I have no contacts in "
    "publishing. About half of my early readers are German so I'd really like a German "
    "edition. I want to sell it on Amazon as an ebook and paperback. My budget is around "
    "$200 and I'd like to launch within a month."
)

SAMPLE_FILE = {
    "name": "the-salt-road-manuscript.pdf",
    "size": 1_240_000,
    "detail": "62,000 words · 41 chapters detected",
}

SERVICES = [
    {
        "key": "publish",
        "icon": "📕",
        "name": "Publishing & Cover",
        "blurb": "Typesetting, print-ready interior, EPUB, cover design, store metadata",
    },
    {
        "key": "translate",
        "icon": "🌍",
        "name": "Translation",
        "blurb": "Glossary-consistent translation with native-speaker review",
    },
    {
        "key": "market",
        "icon": "📣",
        "name": "Marketing",
        "blurb": "Blurb and title testing, keywords, launch sequence, pricing",
    },
]

THINK = [
    "Parsing manuscript structure and chapter boundaries",
    "Reading your description for intent, language and budget",
    "Extracting named entities and recurring terminology",
    "Matching against genre conventions and store requirements",
    "Deciding which steps need a human eye",
    "Pricing and sequencing the plan",
]

GLOSSARY = {
    "fantasy": [
        "Aerith Vale", "the Salt Road", "Thornhold", "Sunder-glass", "the Marrowmere",
        "Keeper Ivane", "tidewright", "the Ninefold Court", "Grey Verge", "saltbinding",
        "House Calloway", "the Unwritten Hours",
    ],
    "general": [
        "the Northgate", "Marion Reyes", "Halloway & Sons", "the Chandler Building",
        "Verity Lane", "Ash Combe", "the Quarterly", "Dr. Osei", "Pellam Street",
        "the Long Field",
    ],
}

SAMPLE_BLURB = (
    "Every hundred years the salt road opens, and every hundred years it takes someone who "
    "did not mean to go. Aerith Vale has spent her life keeping the ledger of the taken — "
    "until the newest name written in her own hand is her sister's. To cross the road is to "
    "be unwritten. To leave it closed is to lose her anyway. A debut about the price of "
    "memory, and who gets to decide what's worth remembering."
)

# ── page copy ─────────────────────────────────────────────────────────

JUDGES_REAL = [
    "The planning agent genuinely reads your context and generates a different plan for "
    "different books — try it with two different inputs.",
    "The four cover directions are generated from your title and genre.",
    "The human verdict in **Human results** is **real data from real people** recruited "
    "through Terac today.",
]

JUDGES_STAGED = [
    "The pipeline runs locally, so timings are compressed — a real run takes hours, not seconds.",
    "Translation shows one sample chapter, not a full book.",
    "We'd rather tell you this than have you find it.",
]

PROBLEM_CARDS = [
    ("Traditional publisher",
     "12–18 months. Takes 70–85% of royalties. You need an agent to get in the door. "
     "Most manuscripts never get read.", False),
    ("Self-publishing alone",
     "Fast and cheap, but you're guessing. No cover testing, no blurb testing, no "
     "native-speaker review. Books die on page 40 of search results.", False),
    ("Bookit",
     "Days, not months. Agents do the mechanical work. Real readers make the taste calls. "
     "You keep your rights and your royalties.", True),
]

HOW_STEPS = [
    ("You upload, and you talk",
     "Drop in a PDF and tell Bookit about your book in plain language — genre, who it's for, "
     "what you want, what you can spend, what language you want it in. The more specific you "
     "are, the more specific the plan."),
    ("An agent writes your publishing plan",
     "Not a checklist. A plan built for <em>your</em> book, as a set of action items — each one "
     "priced, timed, and labelled with who does it: Agent or Human via Terac. You pick what "
     "you want. Nothing runs without your approval."),
    ("Agents do the mechanical work",
     "Text extraction, a named-entity glossary so translations stay consistent, print-ready "
     "typesetting, a reflowable EPUB, store metadata and keywords, cover directions, launch "
     "copy. This is the part that used to cost you months."),
    ("Then it hires humans for the taste calls",
     "Bookit posts the judgement calls to <strong>Terac</strong>, a network of 180,000+ people. "
     "Real readers rank your covers, your blurbs, your titles. Native speakers check your "
     "translation. Bookit ships what they chose — <em>not</em> what the model preferred."),
]

STACK = [
    ("Terac MCP",
     "Recruits and pays the human panel. Bookit's agent creates a project, launches an "
     "opportunity with screening questions targeted at general readers, then polls for "
     "results and acts on them. This is the only part of the system that has taste."),
    ("Planning agent",
     "Reads the manuscript and the author's own words, extracts intent (language, platform, "
     "genre, audience, budget), and emits a priced, sequenced action plan with each item "
     "routed to either an agent or a human."),
    ("Production agents",
     "Text extraction, named-entity glossary, typesetting, EPUB generation, cover synthesis, "
     "metadata and keyword research, launch copy."),
    ("Stripe",
     "The agent invoices the author directly with a payment link. No human on Bookit's side "
     "sends an invoice."),
    ("Replay",
     "Automated QA. Explores the app, finds bugs, reports root causes — our test suite, "
     "written by nobody."),
]

TERAC_QUESTIONS = [
    "Which of these four covers would you actually pick up in a bookstore?",
    "Which one looks most professionally published?",
    "Which of these three back-cover blurbs makes you most likely to read the book?",
    "In your own words — what made you pick that one?",
]

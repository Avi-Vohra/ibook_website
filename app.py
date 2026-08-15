"""Bookit — the publishing house with zero employees.

Streamlit port of the original single-page demo. Run it with:

    streamlit run app.py
"""

from __future__ import annotations

import time

import streamlit as st

from bookit import content, covers, planner, theme
from bookit.theme import badge, chips, html, label, note

PAGES = ["Home", "How it works", "Try it", "Human results", "The stack"]
WIZARD_STEPS = ["Manuscript", "Plan", "Approve", "Results"]
STEP_INDEX = {"input": 0, "thinking": 1, "plan": 2, "running": 3, "results": 3}
TERAC = content.TERAC

st.set_page_config(
    page_title="Bookit — the publishing house with zero employees",
    page_icon="📕",
    layout="centered",
    initial_sidebar_state="expanded",
)
theme.inject()

DEFAULTS = {
    "nav": "Home",
    "step": "input",
    "sample_file": False,
    "ctx_input": "",
    "reading": None,
    "plan": [],
    "services": set(),
    "chosen": [],
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


# ── navigation ────────────────────────────────────────────────────────
def go(page: str) -> None:
    st.session_state.nav = page


def use_sample_file() -> None:
    st.session_state.sample_file = True


def use_sample_context() -> None:
    st.session_state.ctx_input = content.SAMPLE_CTX


def start_over() -> None:
    for key in ("uploader", "ctx_input", "sample_file", "reading", "plan", "services", "chosen"):
        st.session_state.pop(key, None)
    for svc in content.SERVICES:
        st.session_state.pop(f"svc_{svc['key']}", None)
    for i in range(planner.CAP):
        st.session_state.pop(f"item_{i}", None)
    st.session_state.step = "input"
    st.session_state.nav = "Try it"


with st.sidebar:
    html('<div class="brand">Book<i>it</i></div>'
         '<p class="brandsub">Upload a manuscript. Agents do the work. '
         'Humans make the taste calls.</p>')
    st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    html('<p style="font-size:12.5px;color:var(--ink3);margin:0">'
         'Built at the Zero Human Company Hackathon by Terac · Humanmade, San Francisco'
         '</p>')


# ── shared pieces ─────────────────────────────────────────────────────
def section(kicker: str, heading: str, lead: str = "") -> None:
    html(label(kicker) + f'<h2 class="sec serif">{heading}</h2>'
         + (f'<p class="lead">{lead}</p>' if lead else ""))


def footer() -> None:
    html('<div class="foot"><p style="margin:0 0 6px"><b>Bookit</b> — publish, translate and '
         'market your book without a publisher.</p>'
         '<p style="margin:0">Built at the Zero Human Company Hackathon by Terac · '
         'Humanmade, San Francisco · August 15, 2026</p>'
         '<p style="margin:8px 0 0">Tracks: Best Overall Project · Terac · '
         'Best use of Replay</p></div>')


# ── home ──────────────────────────────────────────────────────────────
def page_home() -> None:
    html('<div class="hero">'
         '<div class="eyebrow"><span class="dot"></span>Built at the Zero Human Company '
         'Hackathon</div>'
         '<h1 class="serif">The publishing house<br>with zero employees.</h1>'
         '<p class="sub">Upload your manuscript. AI agents write your publishing plan, do the '
         'work, and hire <strong>real humans</strong> for the parts that need taste. Weeks '
         'instead of years. Hundreds instead of thousands.</p></div>')

    left, right = st.columns(2)
    left.button("Publish my book →", type="primary", use_container_width=True,
                on_click=go, args=("Try it",))
    right.button(f"See what {TERAC['n']} humans decided", use_container_width=True,
                 on_click=go, args=("Human results",))

    st.write("")
    with st.container(border=True):
        html(label("Read this first — 30 seconds")
             + '<h2 class="sec serif" style="font-size:24px">What this is, and what\'s real</h2>'
             '<p class="lead">Bookit is an agentic publishing house. A traditional publisher '
             'takes 18 months and 70% of your royalties. Bookit reads your manuscript, produces '
             'a publishing plan tailored to <em>your</em> book, and executes it — but it does '
             '<strong>not pretend to have taste</strong>. When a decision needs a human eye '
             '(which cover sells, which blurb hooks, does this translation read naturally), it '
             'hires real people through <strong>Terac</strong> and ships what they chose.</p>')
        real, staged = st.columns(2)
        with real:
            html(label("Real, in this app"))
            for item in content.JUDGES_REAL:
                st.markdown(f"- {item}")
        with staged:
            html(label("Staged for this demo"))
            for item in content.JUDGES_STAGED:
                st.markdown(f"- {item}")

    st.write("")
    section("The problem", "Publishing is a taste business with a formatting problem.",
            "Most of what a publisher does is mechanical: extract, typeset, generate metadata, "
            "build keyword lists, produce an EPUB, localise a glossary. Software has been able "
            "to do all of it for years.")
    html('<p class="muted">The part that <em>isn\'t</em> mechanical is judgement. Which cover '
         'makes someone stop scrolling. Whether a blurb lands. Whether a translated sentence '
         'sounds like a person wrote it. That\'s why publishers charge what they charge — '
         'you\'re paying for taste, bundled with a lot of formatting.</p>'
         '<p class="muted"><strong>Bookit unbundles it.</strong> Agents do the formatting for '
         'near-zero cost. Taste gets bought by the question, from real readers, through an '
         'API.</p>')

    st.write("")
    for col, (title, body, _) in zip(st.columns(3), content.PROBLEM_CARDS):
        with col, st.container(border=True):
            html(label(title) + f'<p class="muted" style="font-size:14.6px;margin:0">{body}</p>')


# ── how it works ──────────────────────────────────────────────────────
def page_how() -> None:
    section("How it works", "Four steps, and one honest admission.")
    with st.container(border=True):
        html("".join(
            f'<div class="step"><div class="num">{i}</div>'
            f'<div><h4>{title}</h4><p>{body}</p></div></div>'
            for i, (title, body) in enumerate(content.HOW_STEPS, start=1)))

    html(note('<b>The honest admission:</b> a model can generate a hundred covers, but it '
              'cannot tell you which one a human would pick up in a bookstore. Anyone who says '
              'otherwise is selling you a guess. Bookit\'s whole design is built around that '
              'limit rather than hiding it — which is why the interesting number in this app is '
              'on the Human results page, not in the demo.'))
    st.button("See the human verdict →", on_click=go, args=("Human results",))


# ── the demo ──────────────────────────────────────────────────────────
def stepbar(step: str) -> None:
    active = STEP_INDEX[step]
    cells = "".join(
        f'<div class="{"on" if i <= active else ""}"><span>{name}</span></div>'
        for i, name in enumerate(WIZARD_STEPS))
    html(f'<div class="stepbar">{cells}</div><div style="height:14px"></div>')


def current_file() -> dict | None:
    upload = st.session_state.get("uploader")
    if upload is not None:
        return {"name": upload.name,
                "meta": f"{upload.size / 1024 / 1024:.1f} MB · parsing…"}
    if st.session_state.get("sample_file"):
        sample = content.SAMPLE_FILE
        return {"name": sample["name"],
                "meta": f"{sample['size'] / 1024 / 1024:.1f} MB · {sample['detail']}"}
    return None


def demo_input() -> None:
    html('<h3 class="serif" style="font-size:24px;margin:0 0 4px">Let\'s get your book '
         'published.</h3><p class="muted">Three things and Bookit can start: the manuscript, '
         'what you want done, and who you are.</p>')

    st.file_uploader(
        "Drop your manuscript here",
        type=["pdf", "docx", "epub", "txt"],
        key="uploader",
        help="PDF, DOCX, EPUB or TXT · nothing leaves your machine in this demo",
    )
    st.button("or use our sample manuscript instead", on_click=use_sample_file)

    book = current_file()
    if book:
        st.success(f"**{book['name']}** — {book['meta']}")

    st.write("")
    html('<label style="font-weight:650;font-size:14px">What do you need?</label>'
         '<p class="muted" style="font-size:13.5px;margin:2px 0 10px">Pick as many as you like. '
         'The plan changes based on what you choose.</p>')
    for col, svc in zip(st.columns(3), content.SERVICES):
        with col, st.container(border=True):
            html(f'<div style="font-size:21px;line-height:1">{svc["icon"]}</div>'
                 f'<b style="font-size:15.5px">{svc["name"]}</b>'
                 f'<p class="muted" style="font-size:13px;margin:4px 0 8px;line-height:1.45">'
                 f'{svc["blurb"]}</p>')
            st.checkbox("Include", key=f"svc_{svc['key']}")
    services = {s["key"] for s in content.SERVICES if st.session_state.get(f"svc_{s['key']}")}

    st.write("")
    st.text_area(
        "Tell us about you and your book",
        key="ctx_input",
        height=150,
        placeholder="e.g. I've written a 60,000-word fantasy novel for young adults. It's my "
                    "first book and I don't know anyone in publishing. I'd love a German "
                    "edition because half my early readers are German. I want to sell it on "
                    "Amazon and I can spend about $200.",
        help="Genre, who it's for, what you're trying to achieve, your budget, target "
             "languages, deadlines. Write like you're talking to a person.",
    )
    st.button("load the sample author's description", on_click=use_sample_context)

    ctx = st.session_state.ctx_input.strip()
    ready = bool(book) and bool(services)
    if not book:
        hint = "Add a manuscript and pick at least one service."
    elif not services:
        hint = "Pick at least one service."
    elif len(ctx) < 40:
        hint = "Ready — though the more you tell us, the better the plan."
    else:
        hint = "Ready. The agent has plenty to work with."

    st.write("")
    with st.container(border=True):
        text_col, btn_col = st.columns([0.58, 0.42])
        text_col.markdown(f'<p class="muted" style="margin:8px 0 0">{hint}</p>',
                          unsafe_allow_html=True)
        if btn_col.button("Build my publishing plan →", type="primary",
                          disabled=not ready, use_container_width=True):
            reading = planner.read_context(ctx)
            st.session_state.reading = reading
            st.session_state.services = services
            st.session_state.plan = planner.make_plan(reading, services)
            st.session_state.step = "thinking"
            st.rerun()


def demo_thinking() -> None:
    html('<h3 class="serif" style="font-size:23px;margin:0 0 2px">Reading your book.</h3>'
         '<p class="muted">The planning agent is working through your manuscript and your '
         'description.</p>')
    slot = st.empty()
    for i in range(len(content.THINK) + 1):
        rows = []
        for j, line in enumerate(content.THINK):
            if j < i:
                rows.append(f'<div class="thk done"><span class="mk">✓</span>{line}</div>')
            elif j == i:
                rows.append(f'<div class="thk now"><span class="mk">◐</span>{line}</div>')
            else:
                rows.append(f'<div class="thk"><span class="mk">○</span>{line}</div>')
        slot.markdown("".join(rows), unsafe_allow_html=True)
        time.sleep(0.42)
    st.session_state.step = "plan"
    st.rerun()


def demo_plan() -> None:
    reading = st.session_state.reading
    plan = st.session_state.plan

    facts = [("Genre", reading.genre)]
    if reading.words:
        facts.append(("Length", f"{reading.words} words"))
    if reading.langs:
        facts.append(("Translate to", ", ".join(reading.langs)))
    if reading.platform:
        facts.append(("Selling on", reading.platform))
    if reading.budget:
        facts.append(("Budget", f"${reading.budget}"))
    if reading.debut:
        facts.append(("Author", "first-time, no contacts"))
    if reading.deadline:
        facts.append(("Timing", "wants to move fast"))
    if reading.audiobook:
        facts.append(("Also", "audiobook interest"))
    if reading.series:
        facts.append(("Also", "part of a series"))

    html('<div class="readout">' + label("What the agent understood")
         + chips([f"{k}: <b>{v}</b>" for k, v in facts]) + "</div>")

    humans = sum(1 for item in plan if item.is_human)
    budget_line = f" Kept under your ${reading.budget} budget." if reading.budget else ""
    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Your publishing plan</h3>'
         f'<p class="muted">{len(plan)} action items — <strong>{len(plan) - humans}</strong> the '
         f'agents handle themselves, <strong>{humans}</strong> that need real people. Untick '
         f'anything you don\'t want.{budget_line}</p>')

    for i, item in enumerate(plan):
        with st.container(border=True):
            tick, body = st.columns([0.07, 0.93])
            with tick:
                st.checkbox("Include", key=f"item_{i}", value=True,
                            label_visibility="collapsed")
            with body:
                html(f'<div class="ai-title">{item.title} {badge(item.owner)}</div>'
                     f'<p class="ai-why">{item.why}</p>'
                     f'<div class="meta"><span>Cost <b>{item.cost_label}</b></span>'
                     f'<span>ETA <b>{item.eta_label}</b></span></div>')

    selected = [i for i in range(len(plan)) if st.session_state.get(f"item_{i}", True)]
    cost = sum(plan[i].cost for i in selected)
    hours = sum(plan[i].hours for i in selected)
    hours_label = f"{round(hours * 60)} min" if hours < 1 else f"{hours:.1f} hrs"

    st.write("")
    with st.container(border=True):
        total_col, back_col, run_col = st.columns([0.5, 0.2, 0.3])
        total_col.markdown(
            f'<p class="muted" style="margin:8px 0 0"><b>{len(selected)}</b> selected · '
            f'<b>${cost}</b> · about <b>{hours_label}</b> of work</p>',
            unsafe_allow_html=True)
        if back_col.button("← Edit", use_container_width=True):
            st.session_state.step = "input"
            st.rerun()
        if run_col.button("Run it →", type="primary", disabled=not selected,
                          use_container_width=True):
            st.session_state.chosen = selected
            st.session_state.step = "running"
            st.rerun()


def demo_running() -> None:
    plan = st.session_state.plan
    chosen = [plan[i] for i in st.session_state.chosen]
    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Bookit is publishing your '
         'book.</h3><p class="muted">Agents run the mechanical work. Human tasks get posted to '
         'Terac and wait for real people.</p>')

    slot = st.empty()
    for done in range(len(chosen) + 1):
        rows = []
        for j, item in enumerate(chosen):
            if j < done:
                status = ("Opportunity live on Terac · panel recruiting · results feed back "
                          "automatically") if item.is_human else "Done"
                rows.append(f'<div class="run ok"><div class="st">✓</div>'
                            f'<div><b>{item.title}</b><small>{status}</small></div></div>')
            elif j == done:
                status = ("Posting to Terac and recruiting a panel…" if item.is_human
                          else "Running…")
                rows.append(f'<div class="run now"><div class="st"></div>'
                            f'<div><b>{item.title}</b><small>{status}</small></div></div>')
            else:
                rows.append(f'<div class="run idle"><div class="st"></div>'
                            f'<div><b>{item.title}</b><small>Queued</small></div></div>')
        slot.markdown("".join(rows), unsafe_allow_html=True)
        time.sleep(0.5)

    st.session_state.step = "results"
    st.rerun()


def demo_results() -> None:
    reading = st.session_state.reading
    services = st.session_state.services
    plan = st.session_state.plan
    chosen = [plan[i] for i in st.session_state.chosen]

    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Your book is '
         'published.</h3>')
    for item in chosen:
        status = ("Opportunity live on Terac · panel recruiting · results feed back "
                  "automatically") if item.is_human else "Done"
        html(f'<div class="run ok"><div class="st">✓</div>'
             f'<div><b>{item.title}</b><small>{status}</small></div></div>')

    title = "The Salt Road" if reading.title == "Your Manuscript" else reading.title
    author = "A. Author"

    st.write("")
    html(label("Cover directions")
         + '<p class="muted">Four directions generated for your genre. Bookit does '
         '<strong>not</strong> pick the winner — real readers do.</p>')
    for col, kind in zip(st.columns(4), covers.DIRECTIONS):
        with col:
            classes, crown, caption = "cover", "", f"Direction {kind}"
            if TERAC["live"] and kind == TERAC["human_pick"]["key"]:
                classes = "cover win"
                crown = f'<span class="wb">Chosen by {TERAC["n"]} readers</span>'
                caption = f'Direction {kind} — {TERAC["human_pick"]["pct"]}% of readers'
            elif TERAC["live"] and kind == TERAC["agent_pick"]["key"]:
                caption = (f'Direction {kind} — the agent\'s pick, '
                           f'{TERAC["agent_pick"]["pct"]}%')
            html(f'<div class="{classes}">{crown}'
                 f'<img src="{covers.cover_data_uri(kind, title, author)}" alt="Cover {kind}">'
                 f'<div class="cap">{caption}</div></div>')

    st.button("See the human verdict →", type="primary", on_click=go, args=("Human results",))

    if "translate" in services:
        terms = content.GLOSSARY.get(reading.genre, content.GLOSSARY["general"])
        html('<div class="out">' + label("Translation glossary")
             + '<p style="margin:-4px 0 10px;font-size:13.5px;color:var(--ink3)">Named entities '
               'extracted so every chapter translates consistently.</p>'
             + chips(terms) + "</div>")

    blurb = content.SAMPLE_BLURB if reading.genre in ("fantasy", "general") else (
        f"A {reading.genre} book that knows exactly who it's for. "
        + (f"Written for {reading.audience}. " if reading.audience else "")
        + "Blurb drafted from your own description, then tested with real readers before it "
          "ships.")
    html('<div class="out">' + label("Back-cover blurb")
         + f'<p class="serif">{blurb}</p></div>')

    if "market" in services:
        platform = reading.platform or "Amazon KDP"
        html('<div class="out">' + label("Launch assets")
             + f'<p style="margin:0 0 9px"><strong>{platform} keywords:</strong> '
               f'{reading.genre} debut, slow-burn {reading.genre}, lyrical fantasy, portal '
               'fantasy standalone, books like Piranesi, YA crossover fantasy, literary '
               'fantasy</p>'
               '<p style="margin:0 0 9px"><strong>Categories:</strong> Fantasy → Myths &amp; '
               'Legends · Coming of Age Fantasy <span style="color:var(--ink3)">(picked for '
               'rank-to-competition ratio, not volume)</span></p>'
               '<p style="margin:0"><strong>Launch run:</strong> 5 posts over 9 days, three ad '
               'angles written from what test readers actually said, plus a 12-week '
               'calendar.</p></div>')

    files = []
    if "publish" in services:
        files += ["<b>interior-print.pdf</b> (press-ready, 6×9, bleed)",
                  "<b>ebook.epub</b> (store-validated)",
                  "<b>cover-D.png</b> (2560×1600)", "<b>metadata.json</b>"]
    if "translate" in services:
        lang = (reading.langs[0] if reading.langs else "target").lower()
        files += [f"<b>chapter-01-{lang}.docx</b>", "<b>glossary.csv</b>"]
    if "market" in services:
        files += ["<b>launch-plan.md</b>", "<b>keywords.csv</b>"]
    html('<div class="out">' + label("Files ready")
         + f'<p style="margin:0">{" · ".join(files)}</p></div>')

    html(note('<b>Two human tasks are now live on Terac.</b> Bookit posted your cover test and '
              'blurb test to a panel of real readers. When results come back, Bookit swaps in '
              'whatever they picked and re-renders your book — no human on our side touches '
              'it.'))
    st.button("Start over", on_click=start_over)


def page_demo() -> None:
    section("Try it", "Publish a book, right now.",
            "This is the live product. Use your own file or load our sample author — then "
            "change the context and watch the plan change with it.")
    step = st.session_state.step
    if step != "input" and not st.session_state.plan:
        step = st.session_state.step = "input"
    stepbar(step)
    {"input": demo_input, "thinking": demo_thinking, "plan": demo_plan,
     "running": demo_running, "results": demo_results}[step]()


# ── human results ─────────────────────────────────────────────────────
def page_terac() -> None:
    section("Human results — powered by Terac",
            "The agent guessed. Then we asked real people.",
            "Bookit generated four covers for our sample book and ranked them. Then it hired a "
            "panel of readers through the Terac MCP and asked them the only question that "
            "matters: <em>which of these would you actually pick up?</em>")

    if TERAC["live"]:
        agent, human = TERAC["agent_pick"], TERAC["human_pick"]
        agent_notes = "".join(f"<li>{n}</li>" for n in agent["notes"])
        human_notes = "".join(f"<li>{n}</li>" for n in human["notes"])
        html(f'<div class="ba"><div class="before"><h6>What the agent picked</h6>'
             f'<div class="pick">{agent["label"]}</div>'
             f'<div class="pct">{agent["pct"]}% of readers would pick it up</div>'
             f'<ul>{agent_notes}</ul></div>'
             f'<div class="after"><h6>What real people picked</h6>'
             f'<div class="pick">{human["label"]}</div>'
             f'<div class="pct">{human["pct"]}% of readers would pick it up</div>'
             f'<ul>{human_notes}</ul></div></div>'
             f'<blockquote class="quote">&ldquo;{TERAC["quote"]}&rdquo;'
             f'<cite>— {TERAC["quote_by"]}</cite></blockquote>'
             f'<p style="font-size:14px;color:var(--ink3);margin-top:18px"><strong>Method:</strong> '
             f'{TERAC["n"]} respondents recruited through the Terac MCP, general reader panel, '
             f'launched {TERAC["launched_at"]} today. Four cover directions and three blurbs, '
             f'shown cold with no context. {TERAC["extra"]}</p>')

        st.write("")
        left, right = st.columns(2)
        for col, kind in ((left, agent["key"]), (right, human["key"])):
            with col:
                win = " win" if kind == human["key"] else ""
                who = "Real readers" if kind == human["key"] else "The agent"
                html(f'<div class="cover{win}">'
                     f'<img src="{covers.cover_data_uri(kind, "The Salt Road", "A. Author")}" '
                     f'alt="Cover {kind}"><div class="cap">{who} chose {kind}</div></div>')
    else:
        html('<div class="pending"><p style="margin:0 0 8px"><b>Live Terac results land '
             'here.</b> The study is recruiting right now. As soon as responses are in, the '
             'real numbers replace this box.</p>'
             '<p style="margin:0;font-size:13.5px">Editing note for the team: open '
             '<code>bookit/content.py</code>, paste the real numbers into the <code>TERAC</code> '
             'dict at the top and set <code>"live": True</code>. This page switches itself on. '
             'Nothing else needs to change.</p></div>')

    st.write("")
    asked, why = st.columns(2)
    with asked, st.container(border=True):
        html(label("What we asked"))
        for i, question in enumerate(content.TERAC_QUESTIONS, start=1):
            st.markdown(f"{i}. {question}")
    with why, st.container(border=True):
        html(label("Why this changes the product")
             + '<p class="muted" style="font-size:14.6px;margin:0">Bookit\'s cover ranking is a '
               'model\'s aesthetic preference. A reader\'s choice is a purchase signal. When '
               'those two disagree — and they did — the reader wins and the book ships '
               'differently. That gap <em>is</em> the product: it\'s the difference between a '
               'book that looks generated and a book that looks published.</p>')


# ── the stack ─────────────────────────────────────────────────────────
def page_stack() -> None:
    section("How it's built", "The stack.")
    rows = "".join(f'<tr><td class="layer"><strong>{layer}</strong></td><td>{body}</td></tr>'
                   for layer, body in content.STACK)
    html(f'<table class="stack"><tr><th>Layer</th><th>What it does</th></tr>{rows}</table>')
    html(note('<b>Why this is a "zero human company":</b> nobody at Bookit reads your '
              'manuscript, designs your cover, writes your blurb, or sends your invoice. Humans '
              'are still essential — but they enter as a <em>priced, on-demand input</em> the '
              'agent buys when it hits the edge of its own judgement, not as staff. That\'s the '
              'bet: the company has no employees, and still has 180,000 people working for it.'))


PAGE_RENDERERS = {
    "Home": page_home,
    "How it works": page_how,
    "Try it": page_demo,
    "Human results": page_terac,
    "The stack": page_stack,
}

PAGE_RENDERERS[st.session_state.nav]()
footer()

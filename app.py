"""Bookit — the publishing house with zero employees.

Streamlit port of the original single-page demo. Run it with:

    streamlit run app.py
"""

from __future__ import annotations

import time

import streamlit as st

from bookit import action_planner, content, covers, orchestrator as orch, planner, theme
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
    "plan": None,        # ActionPlan from Pioneer
    "services": set(),
    "chosen": [],
    "run": None,         # orchestrator Run, once "Run it" is pressed
    "plan_error": "",
    "live_terac": False,
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
    for key in ("uploader", "ctx_input", "sample_file", "reading", "plan", "services",
                "chosen", "run", "plan_error"):
        st.session_state.pop(key, None)
    for svc in content.SERVICES:
        st.session_state.pop(f"svc_{svc['key']}", None)
    for i in range(planner.CAP):
        st.session_state.pop(f"item_{i}", None)
    for key in [k for k in st.session_state if str(k).startswith(("act_", "answer_"))]:
        st.session_state.pop(key, None)
    st.session_state.step = "input"
    st.session_state.nav = "Try it"


# ── the real backend ──────────────────────────────────────────────────
STEP_OWNER_CLASS = {"ai": "ai", "expert": "expert", "author": "author"}
STEP_OWNER_TEXT = {"ai": "Agent", "expert": "Terac", "author": "You"}


def get_orchestrator() -> orch.Orchestrator:
    """One orchestrator per session. Terac is stubbed unless explicitly enabled.

    The stub is the default here for the same reason it is on the CLI: a click
    in a demo must not be able to spend money by accident.
    """
    if st.session_state.get("_offline_plan"):     # test seam, see tests/test_app.py
        return _offline_orchestrator()
    terac = None
    if st.session_state.get("live_terac"):
        from bookit.terac import TeracClient
        terac = TeracClient()
    return orch.Orchestrator(orch.RunStore(".bookit_runs"), terac=terac)


def _offline_orchestrator() -> orch.Orchestrator:
    """Used only by the smoke tests — no Pioneer call, no Terac call."""
    from bookit.pioneer import Route

    o = orch.Orchestrator(orch.RunStore(".bookit_runs"))
    o._pioneer_text = lambda system, user: ("Offline test output.", Route(model="offline"))
    return o


def build_plan() -> None:
    """Generate the plan through Pioneer, or record why it failed."""
    if canned := st.session_state.get("_offline_plan"):   # test seam
        st.session_state.plan = action_planner.parse_plan(canned)
        st.session_state.plan_error = ""
        return
    request = action_planner.request_from_frontend(
        ctx_text=st.session_state.ctx_input,
        services=st.session_state.services,
        book_file=current_file(),
    )
    try:
        st.session_state.plan = action_planner.create_action_plan(request)
        st.session_state.plan_error = ""
    except Exception as exc:  # noqa: BLE001 - shown to the author, not raised
        st.session_state.plan = None
        st.session_state.plan_error = str(exc)


with st.sidebar:
    html('<div class="brand">Book<i>it</i></div>'
         '<p class="brandsub">Upload a manuscript. Agents do the work. '
         'Humans make the taste calls.</p>')
    st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    st.checkbox("Post to Terac for real", key="live_terac",
                help="Off: opportunities are simulated and nothing is charged. On: Bookit "
                     "asks Terac for a real price, and only launches after you approve it.")
    if st.session_state.live_terac:
        st.caption("Real quotes. Nothing launches without your approval.")
    else:
        st.caption("Terac simulated — no money can move.")
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

    if error := st.session_state.get("plan_error"):
        st.error(f"The planning agent could not finish: {error}")
        st.caption("Check PIONEER_API_KEY is set, then try again.")

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
            st.session_state.reading = planner.read_context(ctx)
            st.session_state.services = services
            st.session_state.step = "thinking"
            st.rerun()


def demo_thinking() -> None:
    html('<h3 class="serif" style="font-size:23px;margin:0 0 2px">Reading your book.</h3>'
         '<p class="muted">The planning agent is working through your manuscript and your '
         'description. This is a real model call — it takes about a minute.</p>')
    html("".join(f'<div class="thk"><span class="mk">○</span>{line}</div>'
                 for line in content.THINK))
    with st.spinner("Planning…"):
        build_plan()
    st.session_state.step = "input" if st.session_state.plan_error else "plan"
    st.rerun()


def demo_plan() -> None:
    plan = st.session_state.plan
    summary = plan.book_summary

    facts = [("Title", summary.title), ("Genre", summary.genre),
             ("Language", summary.current_language), ("Audience", summary.target_audience)]
    html('<div class="readout">' + label("What the agent understood")
         + chips([f"{k}: <b>{v}</b>" for k, v in facts if v]) + "</div>")

    humans = len(plan.human_actions)
    decisions = len(plan.author_decisions)
    tail = f" <strong>{decisions}</strong> need a decision from you." if decisions else ""
    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Your publishing plan</h3>'
         f'<p class="muted">{plan.plan_summary}</p>'
         f'<p class="muted">{len(plan.actions)} action items — '
         f'<strong>{len(plan.ai_actions)}</strong> the agents handle themselves, '
         f'<strong>{humans}</strong> that need real people.{tail} Untick anything you '
         'don\'t want.</p>')

    for action in plan.actions:
        with st.container(border=True):
            tick, body = st.columns([0.07, 0.93])
            with tick:
                st.checkbox("Include", key=f"act_{action.id}", value=True,
                            label_visibility="collapsed")
            with body:
                html(f'<div class="ai-title">{action.title} {badge(action.owner)}</div>'
                     + (f'<p class="prod">Delivers <b>{action.product.name}</b></p>'
                        if action.product.name else "")
                     + (f'<p class="ai-why">{action.reason}</p>' if action.reason else ""))
                if action.steps:
                    with st.expander(f"How this gets done · {len(action.steps)} steps"):
                        html("".join(
                            f'<div class="stepline">'
                            f'<span class="who {STEP_OWNER_CLASS.get(s.owner, "ai")}">'
                            f'{STEP_OWNER_TEXT.get(s.owner, "Agent")}</span>'
                            f'<span>{s.step}</span></div>'
                            for s in action.steps))
                        if opportunity := action.terac_opportunity:
                            html(note(
                                f'<b>Terac:</b> {opportunity.expert_count} × '
                                f'{opportunity.expert_role}, {opportunity.timeline_hours}h. '
                                f'Priced by Terac before anything is charged.'))

    selected = [a.id for a in plan.actions if st.session_state.get(f"act_{a.id}", True)]

    if plan.warnings:
        with st.expander(f"Planner notes ({len(plan.warnings)})"):
            for warning in plan.warnings:
                st.markdown(f"- {warning}")

    st.write("")
    with st.container(border=True):
        total_col, back_col, run_col = st.columns([0.5, 0.2, 0.3])
        route = plan.route
        routed = f" · planned by {route.model}" if route else ""
        total_col.markdown(
            f'<p class="muted" style="margin:8px 0 0"><b>{len(selected)}</b> selected{routed}</p>',
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
    """Start the run. Real model calls, real Terac quotes — so it can be slow."""
    plan = st.session_state.plan.subset(st.session_state.chosen)
    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Bookit is publishing your '
         'book.</h3><p class="muted">Agents run the mechanical work. Anything needing a person '
         'is priced by Terac and waits for your approval.</p>')
    html("".join(f'<div class="run idle"><div class="st"></div>'
                 f'<div><b>{a.title}</b><small>Queued</small></div></div>'
                 for a in plan.actions))

    orchestrator = get_orchestrator()
    with st.spinner("Running the plan…"):
        run = orchestrator.start(plan)
        run = orchestrator.tick(run, plan)
    st.session_state.run = run
    st.session_state.step = "results"
    st.rerun()


STATUS_TEXT = {
    orch.DONE: ("ok", "✓", "Done"),
    orch.FAILED: ("idle", "✗", "Failed"),
    orch.QUOTED: ("now", "$", "Priced by Terac — needs your approval"),
    orch.LAUNCHED: ("now", "→", "Live on Terac · panel recruiting"),
    orch.COLLECTING: ("now", "◐", "Responses coming in"),
    orch.AWAITING_AUTHOR: ("now", "?", "Waiting on your decision"),
    orch.PENDING: ("idle", "·", "Queued"),
    orch.RUNNING: ("now", "◐", "Running"),
}


def advance_run() -> None:
    """Re-tick the run after the author approves or answers something."""
    plan = st.session_state.plan.subset(st.session_state.chosen)
    st.session_state.run = get_orchestrator().tick(st.session_state.run, plan)


def demo_results() -> None:
    reading = st.session_state.reading
    run: orch.Run = st.session_state.run
    plan = st.session_state.plan
    orchestrator = get_orchestrator()

    heading = ("Your book is published." if run.is_finished
               else "Bookit is working on your book.")
    html(f'<h3 class="serif" style="font-size:23px;margin:0 0 4px">{heading}</h3>')

    for task in run.tasks.values():
        css, mark, status = STATUS_TEXT.get(task.status, ("idle", "·", task.status))
        detail = task.error if task.status == orch.FAILED else status
        if task.status in (orch.LAUNCHED, orch.COLLECTING) and task.submissions_in:
            detail = f"{status} · {task.submissions_in} responses in"
        html(f'<div class="run {css}"><div class="st">{mark}</div>'
             f'<div><b>{task.title}</b><small>{detail}</small></div></div>')

    # ── the spend gate: real prices, the author decides ───────────────
    for task in run.pending_approvals():
        with st.container(border=True):
            html(label("Terac needs your approval")
                 + f'<p style="margin:0 0 2px"><b>{task.title}</b></p>'
                 f'<p class="muted" style="margin:0">{task.quote_label}</p>')
            yes, no = st.columns(2)
            if yes.button(f"Approve ${task.quote_cost:.2f}", key=f"ok_{task.action_id}",
                          type="primary", use_container_width=True):
                # Pass the spec so an hour-old quote is re-priced, not rejected.
                action = next((a for a in plan.actions if a.id == task.action_id), None)
                try:
                    orchestrator.approve(
                        run, task.action_id,
                        action.terac_opportunity if action else None)
                    advance_run()
                except Exception as exc:  # noqa: BLE001 - shown, not raised
                    st.error(f"Terac refused the launch: {exc}")
                st.rerun()
            if no.button("Not this one", key=f"no_{task.action_id}",
                         use_container_width=True):
                orchestrator.decline(run, task.action_id)
                advance_run()
                st.rerun()

    # ── decisions only the author can make ────────────────────────────
    for task in run.open_questions():
        with st.container(border=True):
            html(label("Your call") + f'<p style="margin:0 0 6px">{task.question}</p>')
            st.text_input("Your answer", key=f"answer_{task.action_id}",
                          label_visibility="collapsed")
            if st.button("Submit", key=f"sub_{task.action_id}", type="primary"):
                answer = st.session_state.get(f"answer_{task.action_id}", "").strip()
                if answer:
                    orchestrator.answer(run, task.action_id, answer)
                    advance_run()
                    st.rerun()

    if not run.is_finished:
        left, right = st.columns([0.7, 0.3])
        left.markdown(
            f'<p class="muted" style="margin:8px 0 0">Spent so far <b>${run.spent_usd:.2f}</b>. '
            'Human work takes at least 72 hours — this run is saved and you can come back '
            'to it.</p>', unsafe_allow_html=True)
        if right.button("Check for updates", use_container_width=True):
            advance_run()
            st.rerun()

    # ── what the agents actually produced ─────────────────────────────
    finished = [t for t in run.tasks.values() if t.status == orch.DONE and t.output]
    if finished:
        st.write("")
        html(label("What the agents produced"))
        for task in finished:
            with st.expander(f"{task.title} · {task.model}"):
                st.markdown(task.output)

    title = plan.book_summary.title or (
        "The Salt Road" if reading.title == "Your Manuscript" else reading.title)
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

    delivered = [t for t in run.tasks.values() if t.status == orch.DONE]
    if delivered:
        html('<div class="out">' + label("Delivered")
             + chips([t.title for t in delivered]) + "</div>")

    live = [t for t in run.tasks.values()
            if t.status in (orch.LAUNCHED, orch.COLLECTING)]
    if live:
        rows = "".join(
            f'<li>{t.title} — {t.submissions_in} of the panel in'
            + (f' · <a href="{t.dashboard_url}">dashboard</a>' if t.dashboard_url else "")
            + "</li>"
            for t in live)
        html(note(f'<b>{len(live)} human task(s) live on Terac.</b> Real people are working on '
                  f'these now. Terac\'s minimum turnaround is 72 hours, so results arrive after '
                  f'you have closed this tab — the run is saved and picks up where it left '
                  f'off.<ul style="margin:8px 0 0">{rows}</ul>'))

    if not st.session_state.live_terac:
        html(note('<b>Terac is simulated in this run.</b> Prices and responses are placeholders '
                  'and nothing was charged. Turn on <em>Post to Terac for real</em> in the '
                  'sidebar to get genuine quotes.'))
    st.button("Start over", on_click=start_over)


def page_demo() -> None:
    section("Try it", "Publish a book, right now.",
            "This is the live product. Use your own file or load our sample author — then "
            "change the context and watch the plan change with it.")
    step = st.session_state.step
    if step not in ("input", "thinking") and st.session_state.plan is None:
        step = st.session_state.step = "input"
    if step == "results" and st.session_state.run is None:
        step = st.session_state.step = "plan"
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

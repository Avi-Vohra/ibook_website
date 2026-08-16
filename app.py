"""Bookit — the publishing house with zero employees.

Streamlit port of the original single-page demo (index_1.html), wired to a
real Stripe Checkout Session for the invoice step. Run it with:

    streamlit run app.py

Payment status is confirmed by polling the Stripe API directly (store.py
persists the Checkout Session so the invoice page can re-check it on rerun).
"""

from __future__ import annotations

import random
import time
from datetime import date

import stripe
import streamlit as st

import store
from bookit import action_planner, content, covers, orchestrator as orch, planner, theme
from bookit.theme import badge, chips, html, label, note

stripe.api_key = st.secrets.get("STRIPE_SECRET_KEY", "")
STRIPE_CURRENCY = "usd"
SUCCESS_URL = "https://dashboard.stripe.com/workbench/blueprints/one-time-payment/checkout-chapter?confirmation-redirect=create-checkout-session"
CANCEL_URL = SUCCESS_URL

PAGES = ["Home", "How it works", "Pricing", "Try it", "Human results", "The stack"]
WIZARD_STEPS = ["Manuscript", "Plan", "Approve", "Results", "Invoice"]
STEP_INDEX = {"input": 0, "thinking": 1, "plan": 2, "running": 3, "results": 3, "invoice": 4}
TERAC = content.TERAC
PRICE = content.PRICE

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
    "covers_n": 4,
    "langs_n": 1,
    "budget_in": 0,
    "reading": None,
    "plan": None,        # ActionPlan from Pioneer
    "services": set(),
    "chosen": [],
    "run": None,          # orchestrator Run, once "Run it" is pressed
    "plan_error": "",
    "live_terac": False,
    "order_lines": [],
    "order_total": 0,
    "invoice_no": None,
    "trim_msg": None,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)
for _svc in content.SERVICES:
    st.session_state.setdefault(f"svc_{_svc['key']}", False)


def money(n: int) -> str:
    return content.PAY["currency"] + f"{n:,}"


def get_or_create_checkout_session(invoice_no: str, total: int) -> dict | None:
    """One Stripe Checkout Session per invoice, priced from the live order total."""
    if not stripe.api_key:
        return None
    cached = st.session_state.get("stripe_session")
    if cached and cached["invoice_no"] == invoice_no and cached["amount"] == total:
        return cached
    session = stripe.checkout.Session.create(
        line_items=[{
            "price_data": {
                "currency": STRIPE_CURRENCY,
                "unit_amount": total * 100,
                "product_data": {"name": f"Bookit order {invoice_no}"},
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=SUCCESS_URL,
        cancel_url=CANCEL_URL,
    )
    store.save_checkout_session(session.id, invoice_no, session.url)
    cached = {"invoice_no": invoice_no, "amount": total, "id": session.id, "url": session.url}
    st.session_state.stripe_session = cached
    return cached


def sync_payment_status(session_id: str) -> dict | None:
    if not stripe.api_key:
        return None
    s = stripe.checkout.Session.retrieve(session_id)
    if s.status == "complete":
        email = getattr(s.customer_details, "email", None)
        store.mark_session_completed(s.id, s.payment_status, s.amount_total, s.currency, email)
    return {"status": s.status, "payment_status": s.payment_status}


# ── navigation ────────────────────────────────────────────────────────
def go(page: str) -> None:
    st.session_state.nav = page


def use_sample_file() -> None:
    st.session_state.sample_file = True


def use_sample_context() -> None:
    st.session_state.ctx_input = content.SAMPLE_CTX


def start_over() -> None:
    for key in ("uploader", "ctx_input", "sample_file", "reading", "plan", "services",
                "chosen", "run", "plan_error", "covers_n", "langs_n", "budget_in",
                "order_lines", "order_total", "invoice_no", "trim_msg", "stripe_session"):
        st.session_state.pop(key, None)
    for svc in content.SERVICES:
        st.session_state.pop(f"svc_{svc['key']}", None)
    for key in [k for k in st.session_state if str(k).startswith(("act_", "answer_"))]:
        st.session_state.pop(key, None)
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
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
        # No key on this machine is not a crash: fall back to the stub and say so,
        # so the demo still runs. With TERAC_API_KEY set, this is the real client.
        from bookit.terac import TeracClient, TeracError
        try:
            terac = TeracClient()
        except TeracError as exc:
            st.warning(f"Terac stays simulated — {exc}")
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
         'work, and hire <strong>real humans</strong> for the parts that need taste.</p>'
         f'<p style="color:var(--ink3);font-size:14px;margin:0 0 8px">'
         f'<b style="color:var(--amber)">{money(PRICE["publish"])}</b> to publish · '
         f'<b style="color:var(--amber)">{money(PRICE["per_language"])}</b> per language · '
         f'<b style="color:var(--amber)">{money(PRICE["per_cover"])}</b> per cover design. '
         'Set a budget and Bookit keeps the plan inside it.</p></div>')

    left, right = st.columns(2)
    left.button("Publish my book →", type="primary", use_container_width=True,
                on_click=go, args=("Try it",))
    right.button("The tariff", use_container_width=True, on_click=go, args=("Pricing",))

    st.write("")
    with st.container(border=True):
        html(label("Read this first — 30 seconds")
             + '<h2 class="sec serif" style="font-size:24px">What this is, and what\'s real</h2>'
             '<p class="lead">Bookit is an agentic publishing house. A traditional publisher '
             'takes 18 months and most of your royalties. Bookit reads your manuscript, '
             'produces a publishing plan tailored to <em>your</em> book, prices it against '
             'your budget, and executes it — but it does <strong>not pretend to have '
             'taste</strong>. When a decision needs a human eye (which cover sells, which '
             'blurb hooks, does this translation read naturally), it hires real people '
             'through <strong>Terac</strong> and ships what they chose.</p>')
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


# ── pricing ───────────────────────────────────────────────────────────
def page_pricing() -> None:
    section("The tariff", "Flat prices. No royalty share.",
            "You keep your rights and 100% of your royalties. Human testing is paid for out of "
            "these prices — when Bookit hires readers on Terac, that's already included.")
    for row in (content.PRICING_CARDS[:2], content.PRICING_CARDS[2:]):
        for col, (name, amount, per, bullets) in zip(st.columns(2), row):
            with col, st.container(border=True):
                html(f'<b style="font-size:16px">{name}</b>'
                     f'<div class="serif" style="font-size:40px;font-weight:700;'
                     f'letter-spacing:-.04em;margin:6px 0 0">{money(amount)}</div>'
                     f'<p style="font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;'
                     f'color:var(--ink3);margin:0 0 8px">{per}</p>')
                for b in bullets:
                    st.markdown(f"- {b}")
    html(note('<b>Set a budget and Bookit respects it.</b> Enter what you can spend in the '
              'order form and the total is checked live. Go over and Bookit says so — and '
              'offers to trim the order down to fit rather than quietly dropping things.'))
    st.button("Set my book in type →", type="primary", on_click=go, args=("Try it",))


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


def selected_services() -> set[str]:
    return {s["key"] for s in content.SERVICES if st.session_state.get(f"svc_{s['key']}")}


def apply_trim(budget: int) -> None:
    """Trim the order to fit the budget, and always say what changed."""
    services = selected_services()
    before_covers, before_langs = st.session_state.covers_n, st.session_state.langs_n
    services, cov, lng, dropped = planner.trim_order(
        budget, services, before_covers, before_langs)
    st.session_state.covers_n, st.session_state.langs_n = cov, lng
    for svc in content.SERVICES:
        st.session_state[f"svc_{svc['key']}"] = svc["key"] in services

    changed = []
    if cov != before_covers:
        changed.append(f"cover directions {before_covers} → {cov}")
    if lng != before_langs:
        changed.append(f"languages {before_langs} → {lng}")
    if dropped:
        changed.append(f"removed {' and '.join(dropped)}")

    total = planner.price_order(services, cov, lng)[1]
    if total > budget:
        floor = PRICE["publish"] + PRICE["per_cover"]
        st.session_state.trim_msg = ("over",
            f"**Trimmed as far as it goes.** Publishing on its own is {money(floor)} — one "
            f"cover included — so {money(budget)} can't cover a full publish. Raise your "
            f"budget to {money(floor)}, or untick Publishing and run Marketing "
            f"({money(PRICE['market'])}) or Translation ({money(PRICE['per_language'])}) "
            "on its own.")
    elif changed:
        st.session_state.trim_msg = ("ok",
            f"✓ Trimmed to fit {money(budget)} — now {money(total)}, "
            f"**{money(budget - total)}** left over. Changed: {'; '.join(changed)}. "
            "Put anything back and Bookit will flag it again.")
    else:
        st.session_state.trim_msg = None


def demo_input() -> None:
    html('<h3 class="serif" style="font-size:24px;margin:0 0 4px">Let\'s get your book '
         'published.</h3><p class="muted">Four things and Bookit can start: the manuscript, '
         'what you want done, your budget, and who you are.</p>')

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
         'The plan and the price change based on what you choose.</p>')
    for col, svc in zip(st.columns(3), content.SERVICES):
        with col, st.container(border=True):
            html(f'<div style="font-size:21px;line-height:1">{svc["icon"]}</div>'
                 f'<b style="font-size:15.5px">{svc["name"]}</b>'
                 f'<div style="font-size:11.5px;font-weight:700;letter-spacing:.08em;'
                 f'text-transform:uppercase;color:var(--amber);margin:2px 0 4px">'
                 f'{svc["cost"]}</div>'
                 f'<p class="muted" style="font-size:13px;margin:0 0 8px;line-height:1.45">'
                 f'{svc["blurb"]}</p>')
            st.checkbox("Include", key=f"svc_{svc['key']}")
    services = selected_services()

    ctx = st.session_state.ctx_input.strip()
    reading = planner.read_context(ctx)

    # keep language count sensible against what we detected
    if ("translate" in services and len(reading.langs) > 1
            and st.session_state.langs_n == 1):
        st.session_state.langs_n = min(len(reading.langs), planner.MAX_LANGS)

    if "publish" in services:
        st.write("")
        html('<label style="font-weight:650;font-size:14px">How many cover directions?</label>'
             f'<p class="muted" style="font-size:13.5px;margin:2px 0 8px">'
             f'{money(PRICE["per_cover"])} each. Four gives readers a real choice to rank — '
             "that's what makes the cover test worth running.</p>")
        cov_col, cov_price = st.columns([0.7, 0.3])
        cov_col.number_input("Cover directions", 1, planner.MAX_COVERS, key="covers_n",
                             label_visibility="collapsed")
        cov_price.markdown(
            f'<p style="text-align:right;font-weight:700;margin:8px 0 0">'
            f'{money(PRICE["per_cover"] * st.session_state.covers_n)}</p>',
            unsafe_allow_html=True)

    if "translate" in services:
        st.write("")
        detected = ("Detected in your description: " + ", ".join(reading.langs)
                    if reading.langs
                    else "Bookit picks up target languages from your description")
        html('<label style="font-weight:650;font-size:14px">How many languages?</label>'
             f'<p class="muted" style="font-size:13.5px;margin:2px 0 8px">'
             f'{money(PRICE["per_language"])} each, including a native-speaker review. '
             f'{detected}.</p>')
        lg_col, lg_price = st.columns([0.7, 0.3])
        lg_col.number_input("Languages", 1, planner.MAX_LANGS, key="langs_n",
                            label_visibility="collapsed")
        lg_price.markdown(
            f'<p style="text-align:right;font-weight:700;margin:8px 0 0">'
            f'{money(PRICE["per_language"] * st.session_state.langs_n)}</p>',
            unsafe_allow_html=True)

    st.write("")
    budget = st.number_input(
        "Your budget (optional)", min_value=0, step=5, key="budget_in",
        help="Bookit checks the total against this live, and will offer to trim the order "
             "if you go over.")
    budget = budget or reading.budget or None  # 0 means "not set"; fall back to the description

    lines, total = planner.price_order(
        services, st.session_state.covers_n, st.session_state.langs_n, reading.langs)
    st.session_state.order_lines, st.session_state.order_total = lines, total

    # the live quote
    with st.container(border=True):
        if not lines:
            html('<p class="muted" style="margin:0">Nothing selected yet.</p>')
        for line in lines:
            k_col, v_col = st.columns([0.75, 0.25])
            k_col.markdown(
                f'{line["k"]}<br><span style="font-size:12.5px;color:var(--ink3)">'
                f'{line["d"]}</span>', unsafe_allow_html=True)
            v_col.markdown(f'<p style="text-align:right;font-weight:700;margin:0">'
                           f'{money(line["v"])}</p>', unsafe_allow_html=True)
        html(f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
             f'border-top:2px solid var(--ink);margin-top:8px;padding-top:10px">'
             f'<span style="font-size:11.5px;font-weight:700;letter-spacing:.14em;'
             f'text-transform:uppercase;color:var(--ink3)">Total</span>'
             f'<span class="serif" style="font-size:34px;font-weight:700">{money(total)}</span>'
             '</div>')

        trim = st.session_state.trim_msg
        if trim:
            (st.success if trim[0] == "ok" else st.error)(trim[1])
        elif not lines:
            st.info("Pick a service to see your price.")
        elif budget is None:
            st.info("No budget set. Add one above and Bookit will keep the order inside it.")
        elif total <= budget:
            st.success(f"✓ Within your {money(budget)} budget — "
                       f"**{money(budget - total)}** left over.")
        else:
            st.error(f"Over budget by **{money(total - budget)}**. Your budget is "
                     f"{money(budget)}, this order is {money(total)}.")
            st.button("Trim to fit", on_click=apply_trim, args=(budget,))
    if st.session_state.trim_msg:
        st.session_state.trim_msg = None

    st.write("")
    st.text_area(
        "Tell us about you and your book",
        key="ctx_input",
        height=150,
        placeholder="e.g. I've written a 60,000-word fantasy novel for young adults. It's my "
                    "first book and I don't know anyone in publishing. I'd love a German "
                    "edition because half my early readers are German. I want to sell it on "
                    "Amazon.",
        help="Genre, who it's for, what you're trying to achieve, target languages, "
             "deadlines. Write like you're talking to a person.",
    )
    st.button("load the sample author's description", on_click=use_sample_context)

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
            st.session_state.reading = reading
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
    reading = st.session_state.reading
    plan = st.session_state.plan
    summary = plan.book_summary
    total = st.session_state.order_total

    facts = [("Title", summary.title), ("Genre", summary.genre),
             ("Language", summary.current_language), ("Audience", summary.target_audience),
             ("Order total", money(total))]
    if reading.debut:
        facts.append(("Author", "first-time, no contacts"))
    if reading.deadline:
        facts.append(("Timing", "wants to move fast"))

    html('<div class="readout">' + label("What the agent understood")
         + chips([f"{k}: <b>{v}</b>" for k, v in facts if v]) + "</div>")

    humans = len(plan.human_actions)
    decisions = len(plan.author_decisions)
    tail = f" <strong>{decisions}</strong> need a decision from you." if decisions else ""
    html('<h3 class="serif" style="font-size:23px;margin:0 0 4px">Your publishing plan</h3>'
         f'<p class="muted">{plan.plan_summary}</p>'
         f'<p class="muted">{len(plan.actions)} action items — '
         f'<strong>{len(plan.ai_actions)}</strong> the agents handle themselves, '
         f'<strong>{humans}</strong> that need real people.{tail} It\'s all covered by your '
         f'{money(total)} order; unticking items doesn\'t change the price, it changes what '
         'gets done.</p>')

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
            f'<p class="muted" style="margin:8px 0 0"><b>{len(selected)}</b> of '
            f'{len(plan.actions)} selected{routed} · order total <b>{money(total)}</b></p>',
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
    services = st.session_state.services
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
    n_covers = st.session_state.covers_n if "publish" in services else 4

    st.write("")
    html(label("Cover directions · proof sheet")
         + '<p class="muted">Generated for your genre. Bookit does <strong>not</strong> pick '
         'the winner — real readers do.</p>')
    cols = st.columns(min(n_covers, 4))
    for i in range(n_covers):
        letter = chr(65 + i)
        kind = covers.DIRECTIONS[i % 4]
        with cols[i % len(cols)]:
            classes, crown, caption = "cover", "", f"Direction {letter}"
            if TERAC["live"] and letter == TERAC["human_pick"]["key"]:
                classes = "cover win"
                crown = f'<span class="wb">Chosen by {TERAC["n"]} readers</span>'
                caption = f'Direction {letter} — {TERAC["human_pick"]["pct"]}% of readers'
            elif TERAC["live"] and letter == TERAC["agent_pick"]["key"]:
                caption = (f'Direction {letter} — the agent\'s pick, '
                           f'{TERAC["agent_pick"]["pct"]}%')
            html(f'<div class="{classes}">{crown}'
                 f'<img src="{covers.cover_data_uri(kind, title, author)}" alt="Cover {letter}">'
                 f'<div class="cap">{caption}</div></div>')

    st.button("See the human verdict →", on_click=go, args=("Human results",))

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

    inv_col, again_col = st.columns(2)
    if inv_col.button("Get my invoice →", type="primary", use_container_width=True):
        st.session_state.step = "invoice"
        st.rerun()
    again_col.button("Start over", on_click=start_over, use_container_width=True)


def demo_invoice() -> None:
    plan = st.session_state.plan
    lines = st.session_state.order_lines
    total = st.session_state.order_total
    if st.session_state.invoice_no is None:
        st.session_state.invoice_no = f"BK-{random.randint(1000, 9999)}"

    head, meta = st.columns([0.65, 0.35])
    with head:
        html(label("Invoice")
             + '<h3 class="serif" style="font-size:23px;margin:0 0 4px">Bookit sent you a '
               'bill.</h3>'
               '<p class="muted" style="font-size:14.5px;margin:0">No one on our side wrote '
               'this. The agent priced the work it did, added the human testing it bought on '
               'your behalf, and issued the invoice itself.</p>')
    with meta:
        html(f'<p style="text-align:right;font-size:11.5px;letter-spacing:.1em;'
             f'text-transform:uppercase;color:var(--ink3);line-height:2;margin:0">'
             f'Docket <b style="color:var(--ink)">{st.session_state.invoice_no}</b><br>'
             f'Dated <b style="color:var(--ink)">{date.today():%b %d, %Y}</b><br>'
             f'Terms <b style="color:var(--ink)">Due on receipt</b></p>')

    with st.container(border=True):
        for line in lines:
            k_col, v_col = st.columns([0.75, 0.25])
            k_col.markdown(
                f'**{line["k"]}**<br><span style="font-size:12.5px;color:var(--ink3)">'
                f'{line["d"]}</span>', unsafe_allow_html=True)
            v_col.markdown(f'<p style="text-align:right;font-weight:700;margin:0">'
                           f'{money(line["v"])}</p>', unsafe_allow_html=True)
        humans = len(plan.human_actions)
        if humans:
            k_col, v_col = st.columns([0.75, 0.25])
            k_col.markdown(
                f'**Human testing on Terac — {humans} '
                f'{"task" if humans == 1 else "tasks"}**<br>'
                '<span style="font-size:12.5px;color:var(--ink3)">Paid to the people who do '
                'the work. Already included in the prices above, shown so you can see it.'
                '</span>', unsafe_allow_html=True)
            v_col.markdown('<p style="text-align:right;color:var(--ink3);margin:0">included'
                           '</p>', unsafe_allow_html=True)
        html(f'<div style="display:flex;justify-content:space-between;align-items:flex-end;'
             f'border-top:2px solid var(--ink);margin-top:8px;padding-top:12px">'
             f'<span style="font-size:11.5px;font-weight:700;letter-spacing:.14em;'
             f'text-transform:uppercase;color:var(--ink3)">Total due<br>'
             f'<span style="font-weight:400">One-time · no subscription · no royalty share'
             f'</span></span>'
             f'<span class="serif" style="font-size:44px;font-weight:700">{money(total)}</span>'
             '</div>')

    if not stripe.api_key:
        html('<div class="pending"><p style="margin:0 0 6px"><b>Stripe is not configured.</b> '
             'This is the only setup step left.</p>'
             '<p style="margin:0;font-size:13.5px">Add <code>STRIPE_SECRET_KEY</code> to '
             '<code>.streamlit/secrets.toml</code> (from '
             '<a href="https://dashboard.stripe.com/apikeys" target="_blank">the Stripe '
             'dashboard</a>) and restart. Then this becomes a working checkout button.</p></div>')
    else:
        checkout = get_or_create_checkout_session(st.session_state.invoice_no, total)
        st.link_button(f"Pay {money(total)} with Stripe →", checkout["url"],
                       type="primary", use_container_width=True)
        html('<p style="font-size:13px;color:var(--ink3);text-align:center;margin:8px 0 0">'
             'Opens Stripe\'s hosted checkout. Bookit never sees your card details. '
             f'The amount ({money(total)}) is already set on the session.</p>')

        st.write("")
        status = sync_payment_status(checkout["id"])
        if status and status["status"] == "complete":
            st.success(f"✓ Payment received — status: **{status['payment_status']}**.")
        else:
            st.info("Payment not received yet.")
            st.button("Check payment status")

    html(note('<b>What happens after you pay:</b> the human tasks on this invoice go live on '
              'Terac immediately, your files stay available in this project, and Bookit '
              're-renders the book once the panel\'s verdict comes back. If a panel never '
              'reaches quota, that portion is refunded automatically.'))

    back_col, again_col = st.columns(2)
    if back_col.button("← Back to results", use_container_width=True):
        st.session_state.step = "results"
        st.rerun()
    again_col.button("Start over", on_click=start_over, use_container_width=True)


def page_demo() -> None:
    section("Try it", "Publish a book, right now.",
            "This is the live product. Use your own file or load our sample author — then "
            "change the context and watch the plan and the price change with it.")
    step = st.session_state.step
    if step not in ("input", "thinking") and st.session_state.plan is None:
        step = st.session_state.step = "input"
    if step == "results" and st.session_state.run is None:
        step = st.session_state.step = "plan"
    stepbar(step)
    {"input": demo_input, "thinking": demo_thinking, "plan": demo_plan,
     "running": demo_running, "results": demo_results, "invoice": demo_invoice}[step]()


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
    "Pricing": page_pricing,
    "Try it": page_demo,
    "Human results": page_terac,
    "The stack": page_stack,
}

PAGE_RENDERERS[st.session_state.nav]()
footer()

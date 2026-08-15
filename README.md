# Bookit — Streamlit edition

The publishing house with zero employees. This is the [original single-file
demo](index.html) rebuilt as a Streamlit app, with the planning logic moved out of
client-side JavaScript into Python.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate   # skip if .venv already exists
pip install -r requirements.txt
streamlit run app.py
```

Opens on <http://localhost:8501>.

### Stripe (invoice step)

The invoice step creates a real Stripe Checkout Session sized to the live order
total. Keys live in `.env` (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` — get
them from [the Stripe dashboard](https://dashboard.stripe.com/apikeys); not
committed). Pay with test card `4242 4242 4242 4242`, any future expiry, any
CVC — the invoice page confirms payment by polling the Stripe API directly, no
webhook receiver required.

A minimal, standalone Checkout demo (`streamlit_app.py`, a fixed $20 product) is
included too, for sanity-checking the Stripe wiring in isolation.

## Layout

| File | What's in it |
| --- | --- |
| `app.py` | Every page and the four-step demo wizard |
| `bookit/action_planner.py` | **Action Item creation** — folds the frontend inputs into the planner prompt, calls Pioneer, validates the plan |
| `bookit/pioneer.py` | The Pioneer client: model routing, JSON recovery, route/savings telemetry |
| `bookit/planner.py` | The offline planning agent — regex intent reader, priced demo plan |
| `bookit/covers.py` | The four cover directions, generated as SVG from the title |
| `bookit/content.py` | All copy, the sample author, and the `TERAC` results block |
| `bookit/theme.py` | The letterpress palette and the HTML fragments that use it |
| `store.py` | Shared SQLite persistence for Stripe IDs (imported, not run directly) |
| `streamlit_app.py` | Minimal standalone Checkout demo (fixed $20 product) |
| `stripe_store.db` | SQLite database, created automatically on first run |
| `tests/test_app.py` | Smoke tests: every page renders, the wizard runs end to end |
| `tests/test_action_planner.py` | Payload building, plan validation, JSON recovery (offline) |
| `scripts/plan_demo.py` | Generate one real plan through Pioneer and print it |
| `index.html` | The original page, kept for reference |

## Action Item creation

`bookit/action_planner.py` turns what the author gave the frontend into a concrete,
sequenced execution plan. Each action is routed to `AI_AUTOMATED`, `TERAC_EXPERT`,
`AI_WITH_EXPERT_REVIEW` or `AUTHOR_DECISION`, and every action that needs a human
carries a fully-scoped Terac opportunity ready to post.

```python
from bookit.action_planner import create_action_plan, request_from_frontend

request = request_from_frontend(
    ctx_text=st.session_state.ctx_input,     # the author's own description
    services=st.session_state.services,      # {"publish", "translate", "market"}
    book_file=current_file(),                # {"name", "size", "meta"}
    book_content=extracted_text,             # optional; sampled to ~4k words
)
plan = create_action_plan(request)

plan.actions             # ordered, dependency-respecting
plan.artifacts           # every product the plan creates, in build order
plan.human_actions       # the ones Terac gets
plan.opportunities       # ready-to-post job specs
plan.non_atomic_actions  # actions still bundling more than one product
plan.route               # which model served this, and what routing saved
plan.warnings            # anything repaired or flagged during validation
```

### One action, one product

Every action produces exactly **one** named artifact — something that did not exist before it ran
and can be opened or shipped on its own:

```python
action.artifact.name     # "glossary-en-de.csv"
action.artifact.format   # "CSV"
action.is_atomic         # False if it bundles more than one product
```

Without this rule the model happily emits *"Format English ebook (EPUB) and paperback (print
PDF)"* — two files, one action, and nothing downstream can execute it as a unit. The prompt now
forbids joined titles and requires a filename-shaped `artifact.name`, and `parse_plan()` checks
it: a title containing `and` / `&` / `+` / `/`, more than one `deliverables` entry, or an artifact
named `"files"` all raise a warning naming the offending action.

`AUTHOR_DECISION` is exempt from the title check on purpose — several questions answered on one
decision record is still one artifact, and splitting them would mean interrupting the author four
separate times.

Set the key first — environment or `.streamlit/secrets.toml`:

```bash
export PIONEER_API_KEY=pio_sk_...
python scripts/plan_demo.py                       # one real call, printed
python scripts/plan_demo.py --json > plan.json    # raw JSON
```

### Why Pioneer

[Pioneer](https://pioneer.ai) (Fastino Labs) is an OpenAI-compatible endpoint with a
**model router** in front of ~200 models. Send `pioneer/auto` and it predicts which
models can handle the request, then serves the cheapest one that clears the quality bar.
The response carries an `x_pioneer` block naming the model it picked and the rate
difference against a frontier baseline — surfaced here as `plan.route`.

That is the same trade Bookit makes with labour: buy the expensive option only where it
changes the outcome. The router does for models what the planner does for tasks, so the
cost argument on the pitch page holds one layer further down.

Two constraints the endpoint imposes, both handled in `bookit/pioneer.py`:

- **No structured-output mode.** `response_format` with `json_object` (400) and
  `json_schema` (503) both fail, so JSON is requested in the prompt and parsed
  defensively — fences stripped, surrounding prose ignored, braces inside strings
  respected — with a repair round-trip that hands the model its own bad output back.
- **Routed models may reason before answering,** and reasoning tokens bill against
  `max_tokens` alongside the output. Too tight a budget returns an *empty* message
  rather than a short one; a merely insufficient budget truncates the JSON mid-object.
  A full plan — a dozen actions, each carrying a complete Terac opportunity — runs past
  8k, so the default is 16k and a truncated response is retried at double the budget
  rather than sent back for "repair" (re-asking truncates again at the same place).

Pin a model instead of routing with `PIONEER_MODEL=claude-opus-5` or
`PioneerClient(model=...)` — useful when comparing plan quality against the router.

## Pasting in the Terac results

Open `bookit/content.py`, fill in the `TERAC` dict at the top with the real numbers and
set `"live": True`. The **Human results** page switches itself on — the pending box is
replaced by the before/after panel, and the winning cover gets its badge on the demo's
results step. Nothing else needs to change.

## Tests

```bash
python tests/test_app.py     # or: pytest tests
```

Covers all five pages, the sample author's plan ($145, 9 items, 3 human tasks), budget
trimming, and a full wizard run from upload through to the published files.

## What changed from the HTML version

Same copy, same plan logic, same covers. The differences are structural:

- The planning agent is Python now (`bookit/planner.py`), so the pipeline can be moved
  server-side or wired to the real Terac MCP without a rewrite.
- Anchor-link navigation became a sidebar; the demo's panes became `st.session_state`
  steps (`input → thinking → plan → running → results`).
- The `TERAC` config moved from a `<script>` block to `bookit/content.py`.
- Dark mode is gone — the Streamlit theme in `.streamlit/config.toml` pins the light
  palette.

## Fork status

`upstream` points at `Avi-Vohra/ibook_website`. To publish this as your own fork:

```bash
gh repo create <your-name>/ibook_website --public --source . --remote origin --push
# or, without the gh CLI: create the empty repo on github.com, then
git remote add origin git@github.com:<your-name>/ibook_website.git
git push -u origin streamlit
```

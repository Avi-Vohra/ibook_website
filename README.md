# Bookit — Streamlit edition

The publishing house with zero employees. An author uploads a manuscript and says what
they want. An agent writes a publishing plan for *that* book, does the mechanical work
itself, and hires real people through Terac for the parts that need human judgement.

## What exists today

The UI is wired to the real pipeline. Plan → execute → wait for humans → resume, driven by
Pioneer for model work and Terac for human work, with durable state and a spend gate.

```
author input ──▶ action_planner ──▶ ActionPlan ──▶ orchestrator ──┬─▶ Pioneer  (AI work)
                 (Pioneer)          3–7 actions   (durable run)   ├─▶ Terac    (human work)
                                                                   └─▶ author  (decisions)
```

Pressing **Build my publishing plan** makes a real Pioneer call (~1 min). Each action shows
its product and a collapsible step list. **Run it** starts a real run: agents do their work,
human tasks get a real Terac quote, and the run stops and asks before anything is charged.

Terac is **simulated by default**. The sidebar toggle *Post to Terac for real* switches to
live quotes; even then nothing launches until you press Approve.

## Run it

```bash
pip install -r requirements.txt

# the app
streamlit run app.py

# the real pipeline, cheap models, no money can move
BOOKIT_BUDGET=1 python scripts/run_pipeline.py --auto-approve 50

# walk it all the way to the end (expert responses are SIMULATED)
BOOKIT_BUDGET=1 python scripts/run_pipeline.py --auto-approve 50 --simulate-experts

# resume later — human work outlives the process
python scripts/run_pipeline.py --resume run-1786835884
python scripts/run_pipeline.py --resume run-… --approve A3
python scripts/run_pipeline.py --resume run-… --answer A1 "Use informal du."
```

`--simulate-experts` exists because Terac's real minimum is 72 hours: without it a launched
task never completes and the run has no reachable end state while you're developing. The
responses it returns are labelled `SIMULATED` in the data itself — never show them as real
panel results.

Keys live in `.streamlit/secrets.toml` (`TERAC_API_KEY`) and the environment
(`PIONEER_API_KEY`). Both are gitignored.

## Layout

| File | What's in it |
| --- | --- |
| **Backend pipeline** | |
| `bookit/action_planner.py` | **Action Item creation** — folds frontend input into the planner prompt, calls Pioneer, validates the plan |
| `bookit/orchestrator.py` | **The execution agent** — durable state machine, spend gate, resume |
| `bookit/terac.py` | Terac REST client (quote → launch → poll) plus an offline stub |
| `bookit/pioneer.py` | Pioneer client: routing, JSON recovery, tool calls, savings telemetry |
| **Frontend** | |
| `app.py` | Every page and the wizard, wired to the pipeline |
| `bookit/planner.py` | The old regex intent reader; still used for the sample-author readout |
| `bookit/covers.py` | The four cover directions, generated as SVG from the title |
| `bookit/content.py` | All copy, the sample author, and the `TERAC` results block |
| `bookit/theme.py` | The cream-and-amber palette and the HTML fragments that use it |
| **Scripts and tests** | |
| `scripts/run_pipeline.py` | Plan → execute → report, end to end |
| `scripts/plan_demo.py` | Generate one plan and print it |
| `tests/test_action_planner.py` | Payload building, plan shape, JSON recovery (offline) |
| `tests/test_orchestrator.py` | State machine, spend gate, durability (offline) |
| `tests/test_app.py` | Smoke tests: every page renders, the wizard runs |
| `index.html` | The original page, kept for reference |

## The execution agent

Terac's minimum turnaround is **72 hours**, so nothing here can run to completion inside a
request. The orchestrator is therefore not a loop — it is durable state plus a `tick()`
that advances whatever is ready and returns:

```python
from bookit.orchestrator import Orchestrator, RunStore

orch = Orchestrator(RunStore())        # Terac stubbed unless you pass a real client
run = orch.start(plan)
run = orch.tick(run, plan)             # safe to call repeatedly, never blocks

run.pending_approvals()                # Terac quotes waiting on the author
run.open_questions()                   # AUTHOR_DECISION tasks
orch.approve(run, "A3")                # the only call that spends money
orch.answer(run, "A1", "Use informal du.")
```

Per action:

```
AI_AUTOMATED     PENDING → RUNNING → DONE
TERAC_EXPERT     PENDING → QUOTED → (author approves) → LAUNCHED → COLLECTING → DONE
AUTHOR_DECISION  PENDING → AWAITING_AUTHOR → DONE
```

**The gap between QUOTED and LAUNCHED is the whole point.** Terac prices a job for free and
charges on launch, so the author's approval sits exactly there. `Orchestrator` defaults to
`StubTeracClient`, so a dev loop cannot spend money by accident — you have to pass a real
`TeracClient` deliberately.

Runs are one JSON file each under `.bookit_runs/`, written with write-then-rename so a
crash mid-write leaves the previous state intact. A run survives a restart, which it has
to: human work outlives the process that started it.

## Terac

[Terac](https://terac.com) operates a verified expert panel and sells on-demand access.
Bookit uses it for every judgement an agent cannot make: which cover a reader picks up,
whether a translated sentence sounds native, whether a blurb lands.

`bookit/terac.py` wraps the REST API at `https://terac.com/api/external/v2`
(`Authorization: Bearer …`, key in `.streamlit/secrets.toml`):

```
POST /quotes                 taskDescription, panelDescription,     → quoteId, totalCost,
                             submissionCount 1–999,                   costPerParticipant
                             timelineHours 72–720
POST /quotes/{id}/launch     name, projectId                        → opportunityId   ← charges
GET  /opportunities/{id}     draft|active|fulfilled|paused|stopped|completed
GET  /opportunities/{id}/submissions
```

Three constraints that shaped the design, all found by probing the live API rather than
reading marketing copy:

- **72-hour minimum.** `timelineHours` will not accept less, so human results cannot land
  inside a demo. The planner is clamped to the same bounds so it never promises the author
  a faster turnaround than Terac can deliver.
- **Pricing is a round trip.** You describe the task; Terac prices it. The old UI's `$58`
  and `$42` are invented numbers — real cost only exists after a quote.
- **Quote is free, launch charges.** Which is exactly where the author's approval sits.

There is also an [Agent MCP](https://terac.com/mcp) at `https://terac.com/api/mcp`
(`terac_request_feasibility` → `terac_launch_draft_opportunity` → `terac_get_submissions`).
It authenticates via OAuth on first connect, which is awkward from a server process, so the
app uses REST. Add it to Claude Code for manual exploration:

```bash
claude mcp add --transport http terac https://terac.com/api/mcp
```

## Cheap models while testing

`BOOKIT_BUDGET=1` pins `gpt-5-nano` instead of letting the router choose. Measured on the
same plan:

| Model | Plan cost | Notes |
| --- | --- | --- |
| `claude-opus-4-7` (router's pick) | $0.228 | what `pioneer/auto` selects for planning |
| `gpt-5-nano` (`BOOKIT_BUDGET=1`) | $0.0034 | ~67× cheaper, correct plan shape |

`PIONEER_MODEL=<id>` overrides both. If a pinned model returns 5xx the client falls back to
`pioneer/auto` once and records it on `client.fell_back_from` — `deepseek-ai/DeepSeek-V4-Flash`
was the original budget pick and started 500-ing on every request, including two-word
prompts, which is what the fallback exists for.

**Budget mode is for plumbing, not for the demo.** `gpt-5-nano` follows the plan rules loosely
and varies run to run: it has split one product across two actions, and once produced a plan
with *no human tasks at all* — which deletes Bookit's central claim. `parse_plan()` now warns
on that, but the fix is to plan with a better model. Use `pioneer/auto` (or pin
`claude-sonnet-5`) for anything you show a judge.

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

plan.actions             # 3-7 author-facing actions, dependency-ordered
plan.products            # what the author receives, in delivery order
plan.human_actions       # the ones Terac gets
plan.opportunities       # ready-to-post job specs
plan.malformed_actions   # actions without a clear product or step preview
plan.route               # which model served this, and what routing saved
plan.warnings            # anything repaired or flagged during validation
```

### Author-facing actions, with the detail collapsed underneath

An action is what the **author** reads and approves — one outcome they would recognise and pay
for. "Translate the book into German" is one action. Building a glossary, translating a sample
chapter, running QA, and having a native speaker revise it are *steps inside it*, not actions:

```python
action.title             # "Translate the book into German"
action.product.name      # "German edition of the manuscript"
action.steps             # 2-6 short lines for the collapsed detail view
action.steps[0].owner    # "ai" | "expert" | "author"
action.expert_steps      # the steps a real person does
```

This matters because the first version got it backwards. Pushed toward maximum granularity, the
planner produced a **23-action, 12,387-token engineering backlog** — including author-facing items
like *"Translate a sample chapter into German"*, which is a risk-management tactic, not something
an author should have to approve. The coarse rewrite brings it to 5 actions with the tactics
pushed down into `steps`, where the orchestrator decides the real sequence at execution time.

`parse_plan()` enforces the shape: more than 7 actions warns about an engineering backlog, more
than 6 steps warns that the author view is too detailed, and a product named `"files"` is rejected
as a category rather than a deliverable.

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

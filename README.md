# Bookit — Streamlit edition

The publishing house with zero employees. This is the [original single-file
demo](index.html) rebuilt as a Streamlit app, with the planning logic moved out of
client-side JavaScript into Python.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens on <http://localhost:8501>.

## Layout

| File | What's in it |
| --- | --- |
| `app.py` | Every page and the four-step demo wizard |
| `bookit/planner.py` | The planning agent — reads the author's description, emits a priced, sequenced plan |
| `bookit/covers.py` | The four cover directions, generated as SVG from the title |
| `bookit/content.py` | All copy, the sample author, and the `TERAC` results block |
| `bookit/theme.py` | The cream-and-amber palette and the HTML fragments that use it |
| `tests/test_app.py` | Smoke tests: every page renders, the wizard runs end to end |
| `index.html` | The original page, kept for reference |

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

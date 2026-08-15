"""Look and feel — the letterpress galley-proof design from index_1.html,
ported onto Streamlit, plus the small HTML fragments (badges, chips, notes)
the app uses. Class names match what app.py already emits, so no wiring
changes were needed to bring the new look over.
"""

from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT,WONK@9..144,300..900,0..100,0..1&family=Newsreader:opsz,wght@6..72,200..700&family=Space+Mono:wght@400;700&display=swap');

:root{
  --bg:#f1eee4; --panel:#fbf9f2; --panel2:#fbf9f2; --ink:#171610; --ink2:#3b382b; --ink3:#5c5847;
  --line:#cfc9b6; --amber:#9d2915; --green:#173d56; --red:#9d2915; --stamp:#e8d27a;
  --shadow:4px 4px 0 rgba(23,22,16,.13);
  --display:'Fraunces','Iowan Old Style',Georgia,serif;
  --read:'Newsreader',Georgia,'Times New Roman',serif;
  --mono:'Space Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
}

html, body, [data-testid="stAppViewContainer"]{ background:var(--bg) !important; }
[data-testid="stAppViewContainer"]{
  background-image:repeating-linear-gradient(0deg,rgba(23,22,16,.021) 0 1px,transparent 1px 3px),
    radial-gradient(circle at 16% 4%,rgba(157,41,21,.035),transparent 42%);
}
body, [data-testid="stMarkdownContainer"] p, [data-testid="stText"]{
  font-family:var(--read); color:var(--ink2);
}
.block-container, [data-testid="stMainBlockContainer"]{
  max-width:1000px; padding-top:2.4rem; padding-bottom:4rem;
}
[data-testid="stSidebar"]{ background:var(--panel2); border-right:1.5px solid var(--ink); }
[data-testid="stSidebar"] *{ font-family:var(--read); }
::selection{ background:var(--stamp); color:var(--ink); }

.serif{font-family:var(--display); font-variation-settings:'SOFT' 30,'WONK' 1;}

/* ── headings ─────────────────────────────────────────────────── */
h1, h2, h3, h4{font-family:var(--display); font-weight:600; letter-spacing:-.03em; color:var(--ink);}

/* ── hero ─────────────────────────────────────────────────────── */
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:9.5px;
  font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:var(--ink);
  background:var(--stamp);border:0;padding:6px 13px;margin-bottom:22px}
.eyebrow .dot{width:5px;height:5px;background:var(--ink);border-radius:0}
.hero{text-align:center;padding:14px 0 6px}
.hero h1{font-family:var(--display);font-size:clamp(34px,5.6vw,58px);line-height:1.02;
  letter-spacing:-.04em;margin:0 0 18px;font-weight:600;color:var(--ink);
  font-variation-settings:'SOFT' 30,'WONK' 1}
.hero .sub{font-family:var(--read);font-size:clamp(16px,2.2vw,19.5px);color:var(--ink2);
  max-width:620px;margin:0 auto 26px}

/* brand bar */
.brand{display:flex;align-items:center;gap:10px;font-family:var(--display);font-weight:600;
  font-size:22px;letter-spacing:-.03em;color:var(--ink);margin-bottom:2px}
.brand i{font-style:normal;color:var(--amber)}
.brandsub{color:var(--ink3);font-size:12.5px;margin:0 0 18px;font-family:var(--read)}

.lbl{font-family:var(--mono);font-size:10.5px;font-weight:700;letter-spacing:.2em;
  text-transform:uppercase;color:var(--amber);margin:0 0 10px}
.lbl.muted{color:var(--ink3)}
h2.sec{font-family:var(--display);font-size:clamp(24px,3.4vw,40px);line-height:1.05;
  letter-spacing:-.035em;margin:0 0 10px;font-weight:600;color:var(--ink);
  font-variation-settings:'SOFT' 30,'WONK' 1}
p.lead{font-family:var(--read);font-size:18px;color:var(--ink);line-height:1.55}
.muted{color:var(--ink2)}

/* ── badges + chips ───────────────────────────────────────────── */
.badge{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:9.5px;
  font-weight:700;letter-spacing:.12em;text-transform:uppercase;padding:3px 8px;
  border:1px solid currentColor;border-radius:0;white-space:nowrap;vertical-align:middle}
.badge .dot{width:4px;height:4px;border-radius:0;background:currentColor}
.badge.ag{background:rgba(157,41,21,.07);color:var(--amber)}
.badge.hu{background:rgba(23,61,86,.07);color:var(--green)}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  padding:4px 9px;background:var(--bg);border:1px solid var(--line);color:var(--ink2)}
.chip b{color:var(--ink)}

/* ── boxes ────────────────────────────────────────────────────── */
.note{background:var(--panel);border:1px solid var(--ink);border-left:5px solid var(--amber);
  border-radius:0;padding:16px 19px;margin:16px 0;color:var(--ink2);font-size:14.6px}
.note b{color:var(--ink)}
.readout{border-top:1px solid var(--ink);border-bottom:1px solid var(--ink);
  padding:14px 0;margin:0 0 18px;background:transparent}
.out{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--ink);
  padding:17px 19px;margin:14px 0;color:var(--ink2);font-size:15.5px}
.out .serif{color:var(--ink);font-size:17.5px;line-height:1.58;font-family:var(--display)}
.pending{background:rgba(157,41,21,.06);border:1.5px dashed var(--amber);
  border-radius:0;padding:15px 17px;font-size:14.5px;color:var(--ink2)}
.pending b{color:var(--amber)}

/* ── numbered steps ───────────────────────────────────────────── */
.step{display:flex;gap:20px;padding:20px 0;border-bottom:1px solid var(--line)}
.step:last-child{border:0}
.step .num{flex:0 0 48px;font-family:var(--display);font-size:44px;line-height:.8;
  font-weight:600;color:var(--amber);opacity:.34;letter-spacing:-.04em;background:none;
  border:0;height:auto;display:block;text-align:left}
.step h4{margin:2px 0 5px;font-size:20px;letter-spacing:-.02em;color:var(--ink);
  font-family:var(--display);font-weight:600}
.step p{margin:0;font-size:15.5px;color:var(--ink2)}

/* ── wizard progress ──────────────────────────────────────────── */
.stepbar{display:flex;gap:0;margin:4px 0 26px;border:1px solid var(--ink)}
.stepbar div{flex:1;height:auto;border-radius:0;background:var(--panel);position:relative;
  padding:9px 8px 8px;border-right:1px solid var(--ink)}
.stepbar div:last-child{border-right:0}
.stepbar div.on{background:var(--ink)}
.stepbar span{position:static;display:block;font-family:var(--mono);font-size:9.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink3);font-weight:700;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.stepbar div.on span{color:var(--bg)}

/* ── plan items ───────────────────────────────────────────────── */
.ai-title{font-family:var(--display);font-size:18px;font-weight:600;letter-spacing:-.02em;
  color:var(--ink);margin:0 0 6px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ai-why{margin:0 0 9px;font-size:15px;line-height:1.5;color:var(--ink2)}
.meta{display:flex;gap:14px;font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink3);flex-wrap:wrap}
.meta b{color:var(--ink);font-weight:700}

/* ── run list ─────────────────────────────────────────────────── */
.run{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line)}
.run:last-child{border:0}
.run.idle{opacity:.4}
.run .st{flex:0 0 19px;height:19px;border-radius:0;border:1.5px solid var(--line);
  margin-top:2px;display:grid;place-items:center;font-size:11px;font-weight:700;
  font-family:var(--mono)}
.run.now .st{border-color:var(--amber);background:rgba(157,41,21,.1)}
.run.ok .st{border-color:var(--ink);background:var(--ink);color:var(--stamp)}
.run b{display:block;font-family:var(--display);font-size:16px;color:var(--ink);
  margin-bottom:1px;font-weight:600}
.run small{color:var(--ink3);font-size:12.5px;font-family:var(--mono);letter-spacing:.05em}

/* ── thinking ─────────────────────────────────────────────────── */
.thk{display:flex;gap:11px;align-items:center;padding:6px 0;font-size:14.5px;color:var(--ink3)}
.thk.now{color:var(--ink2)}
.thk.done{color:var(--ink2)}
.thk .mk{width:16px;text-align:center;font-family:var(--mono)}
.thk.done .mk{color:var(--green);font-weight:700}

/* ── covers ───────────────────────────────────────────────────── */
.cover{position:relative;padding-top:4px}
.cover img{width:100%;height:auto;border-radius:0;border:1px solid var(--ink);
  box-shadow:3px 3px 0 rgba(23,22,16,.11);display:block}
.cover.win img{box-shadow:0 0 0 3px var(--stamp),3px 3px 0 rgba(23,22,16,.11)}
.cover .cap{text-align:center;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink3);margin-top:9px;font-weight:600}
.cover.win .cap{color:var(--ink);font-weight:700}
.cover .wb{display:block;text-align:center;background:var(--ink);color:var(--stamp);
  font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.12em;
  text-transform:uppercase;padding:4px 8px;border-radius:0;margin:0 auto 8px;width:fit-content}

/* ── before / after ───────────────────────────────────────────── */
.ba{display:grid;grid-template-columns:1fr 1fr;border:1.5px solid var(--ink);
  border-radius:0;background:var(--panel);box-shadow:var(--shadow)}
@media(max-width:640px){.ba{grid-template-columns:1fr}}
.ba > div{padding:22px}
.ba .before{background:repeating-linear-gradient(-45deg,transparent 0 7px,rgba(23,22,16,.028) 7px 14px);
  border-right:1.5px solid var(--ink)}
.ba h6{margin:0 0 6px;font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink3)}
.ba .after h6{color:var(--green)}
.ba .pick{font-family:var(--display);font-size:32px;font-weight:600;letter-spacing:-.03em;margin:6px 0 3px}
.ba .before .pick{color:var(--ink3);text-decoration:line-through;text-decoration-color:var(--amber)}
.ba .after .pick{color:var(--green)}
.ba .pct{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink3)}
.ba ul{margin:14px 0 0;padding-left:17px;font-size:14.5px;color:var(--ink2)}
blockquote.quote{border:0;border-left:5px solid var(--green);padding:6px 0 6px 18px;margin:20px 0 0;
  font-family:var(--display);font-size:21px;line-height:1.4;color:var(--ink);
  font-variation-settings:'SOFT' 40,'WONK' 1}
blockquote.quote cite{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink3);font-style:normal;margin-top:7px}

/* ── stack table ──────────────────────────────────────────────── */
table.stack{width:100%;border-collapse:collapse;font-size:15px;margin:16px 0;
  border-top:2px solid var(--ink);border-bottom:2px solid var(--ink)}
table.stack th{text-align:left;padding:10px 12px 10px 0;border-bottom:1px solid var(--ink);
  font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ink3);font-weight:700}
table.stack td{text-align:left;padding:14px 12px 14px 0;border-bottom:1px dotted var(--line);
  vertical-align:top;color:var(--ink2)}
table.stack td.layer{white-space:nowrap;color:var(--ink);font-family:var(--mono);
  font-size:11px;letter-spacing:.06em}
table.stack tr:last-child td{border-bottom:0}

.foot{border-top:3px solid var(--ink);margin-top:44px;padding:26px 0 10px;
  color:var(--ink3);font-size:11.5px;font-family:var(--mono);letter-spacing:.08em;
  text-transform:uppercase;text-align:center;line-height:2}
.foot b{color:var(--ink);font-family:var(--display);letter-spacing:0;text-transform:none;
  font-size:14px}

/* ── streamlit widgets, reskinned as press hardware ──────────────── */
[data-testid="stButton"] button, [data-testid="stLinkButton"] a, [data-testid="stFormSubmitButton"] button{
  font-family:var(--mono) !important;font-size:11px !important;font-weight:700 !important;
  letter-spacing:.14em !important;text-transform:uppercase;border-radius:0 !important;
  border:1.5px solid var(--ink) !important;box-shadow:3px 3px 0 rgba(23,22,16,.11);
  transition:none !important;
}
[data-testid="stButton"] button:hover, [data-testid="stLinkButton"] a:hover{
  background:var(--amber) !important;border-color:var(--amber) !important;color:var(--bg) !important;
}
[data-testid="stButton"] button:active{ box-shadow:none !important; transform:translate(3px,3px); }
[data-testid="stBaseButton-primary"], button[kind="primary"]{
  background:var(--ink) !important;color:var(--bg) !important;
}
[data-testid="stBaseButton-secondary"], button[kind="secondary"]{
  background:var(--panel) !important;color:var(--ink) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]{
  border:1.5px solid var(--ink) !important;border-radius:0 !important;
  background:var(--panel);box-shadow:var(--shadow);
}
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input{
  font-family:var(--read) !important;border-radius:0 !important;border:1.5px solid var(--ink) !important;
  background:var(--panel) !important;color:var(--ink) !important;
}
[data-testid="stNumberInput"] input{font-family:var(--mono) !important;font-weight:700 !important}
[data-testid="stFileUploaderDropzone"]{
  border:1.5px dashed var(--ink) !important;border-radius:0 !important;background:var(--bg) !important;
}
[data-testid="stCheckbox"] label span[role="checkbox"], [data-testid="stCheckbox"] svg{
  border-radius:0 !important;
}
hr, [data-testid="stDivider"]{ border-color:var(--ink) !important; }
[data-testid="stAlert"]{ border-radius:0 !important; border:1.5px solid var(--ink) !important; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def label(text: str) -> str:
    return f'<div class="lbl">{escape(text)}</div>'


def badge(owner: str) -> str:
    if owner == "human":
        return '<span class="badge hu"><span class="dot"></span>Human via Terac</span>'
    return '<span class="badge ag"><span class="dot"></span>Agent</span>'


def chips(items: list[str]) -> str:
    inner = "".join(f'<span class="chip">{c}</span>' for c in items)
    return f'<div class="chips">{inner}</div>'


def note(markup: str) -> str:
    return f'<div class="note">{markup}</div>'

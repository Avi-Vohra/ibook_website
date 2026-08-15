"""Look and feel — the cream-and-amber palette from the original page,
plus the small HTML fragments (badges, chips, notes) it used.
"""

from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
:root{
  --bg:#faf7f2; --panel:#fff; --panel2:#f4efe6; --ink:#191510; --ink2:#544b40; --ink3:#8b8175;
  --line:#e4dbcd; --amber:#b3591a; --green:#1d6b57; --red:#9c2b1e;
  --shadow:0 1px 2px rgba(25,21,16,.05),0 8px 24px -12px rgba(25,21,16,.16);
}
.block-container, [data-testid="stMainBlockContainer"]{
  max-width:1000px; padding-top:2.4rem; padding-bottom:4rem;
}
[data-testid="stSidebar"]{ background:var(--panel2); border-right:1px solid var(--line); }

.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}

/* hero */
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:600;
  letter-spacing:.08em;text-transform:uppercase;color:var(--amber);background:var(--panel);
  border:1px solid var(--line);padding:6px 14px;border-radius:30px;margin-bottom:22px}
.eyebrow .dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.hero{text-align:center;padding:14px 0 6px}
.hero h1{font-size:clamp(34px,5.6vw,58px);line-height:1.05;letter-spacing:-.035em;
  margin:0 0 18px;font-weight:600;color:var(--ink)}
.hero .sub{font-size:clamp(16px,2.2vw,20px);color:var(--ink2);max-width:620px;margin:0 auto 26px}

/* brand bar */
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:21px;
  letter-spacing:-.03em;color:var(--ink);margin-bottom:2px}
.brand i{font-style:normal;color:var(--amber)}
.brandsub{color:var(--ink3);font-size:12.5px;margin:0 0 18px}

.lbl{font-size:11.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;
  color:var(--amber);margin:0 0 10px}
.lbl.muted{color:var(--ink3)}
h2.sec{font-size:clamp(24px,3.4vw,34px);line-height:1.15;letter-spacing:-.03em;
  margin:0 0 10px;font-weight:600;color:var(--ink)}
p.lead{font-size:18px;color:var(--ink);line-height:1.6}
.muted{color:var(--ink2)}

/* badges + chips */
.badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;
  letter-spacing:.05em;text-transform:uppercase;padding:3.5px 9px;border-radius:20px;
  white-space:nowrap;vertical-align:middle}
.badge .dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.badge.ag{background:rgba(179,89,26,.15);color:var(--amber)}
.badge.hu{background:rgba(29,107,87,.16);color:var(--green)}
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{font-size:12.5px;padding:4px 10px;border-radius:20px;background:var(--panel);
  border:1px solid var(--line);color:var(--ink2)}
.chip b{color:var(--ink)}

/* boxes */
.note{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--amber);
  border-radius:0 12px 12px 0;padding:15px 18px;margin:16px 0;color:var(--ink2);font-size:14.6px}
.note b{color:var(--ink)}
.readout{background:var(--panel2);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px;margin:0 0 18px}
.out{background:var(--panel2);border:1px solid var(--line);border-radius:12px;
  padding:16px 17px;margin:13px 0;color:var(--ink2);font-size:14.7px}
.out .serif{color:var(--ink);font-size:16px;line-height:1.6}
.pending{background:rgba(156,43,30,.08);border:1px dashed rgba(156,43,30,.45);
  border-radius:12px;padding:14px 16px;font-size:14px;color:var(--ink2)}
.pending b{color:var(--red)}

/* numbered steps */
.step{display:flex;gap:15px;padding:14px 0;border-bottom:1px solid var(--line)}
.step:last-child{border:0}
.step .num{flex:0 0 34px;height:34px;border-radius:50%;background:var(--panel2);
  border:1px solid var(--line);display:grid;place-items:center;font-weight:700;
  font-size:14px;color:var(--amber)}
.step h4{margin:3px 0 4px;font-size:17px;letter-spacing:-.01em;color:var(--ink)}
.step p{margin:0;font-size:15px;color:var(--ink2)}

/* wizard progress */
.stepbar{display:flex;gap:6px;margin:4px 0 26px}
.stepbar div{flex:1;height:4px;border-radius:4px;background:var(--line);position:relative}
.stepbar div.on{background:var(--amber)}
.stepbar span{position:absolute;top:9px;left:0;font-size:10.5px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink3);font-weight:600;white-space:nowrap}
.stepbar div.on span{color:var(--amber)}

/* plan items */
.ai-title{font-size:16px;font-weight:650;letter-spacing:-.01em;color:var(--ink);
  margin:0 0 5px;display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.ai-why{margin:0 0 8px;font-size:14.3px;line-height:1.5;color:var(--ink2)}
.meta{display:flex;gap:14px;font-size:12.5px;color:var(--ink3);flex-wrap:wrap}
.meta b{color:var(--ink);font-weight:650}

/* run list */
.run{display:flex;gap:12px;align-items:flex-start;padding:10px 0;
  border-bottom:1px solid var(--line)}
.run:last-child{border:0}
.run.idle{opacity:.35}
.run .st{flex:0 0 19px;height:19px;border-radius:50%;border:2px solid var(--line);
  margin-top:2px;display:grid;place-items:center;font-size:11px;font-weight:800}
.run.now .st{border-color:var(--amber)}
.run.ok .st{border-color:var(--green);color:var(--green)}
.run b{display:block;font-size:15px;color:var(--ink);margin-bottom:1px}
.run small{color:var(--ink3);font-size:13px}

/* thinking */
.thk{display:flex;gap:11px;align-items:center;padding:6px 0;font-size:14.5px;color:var(--ink3)}
.thk.now{color:var(--ink2)}
.thk.done{color:var(--ink2)}
.thk .mk{width:16px;text-align:center}
.thk.done .mk{color:var(--green);font-weight:800}

/* covers */
.cover img{width:100%;height:auto;border-radius:7px;border:1px solid var(--line);
  box-shadow:var(--shadow);display:block}
.cover.win img{outline:2.5px solid var(--green);outline-offset:3px}
.cover .cap{text-align:center;font-size:12.5px;color:var(--ink3);margin-top:7px;font-weight:600}
.cover.win .cap{color:var(--green)}
.cover .wb{display:block;text-align:center;background:var(--green);color:#fff;font-size:10px;
  font-weight:800;letter-spacing:.07em;text-transform:uppercase;padding:3px 9px;
  border-radius:20px;margin:0 auto 8px;width:fit-content}

/* before / after */
.ba{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);
  border-radius:15px;overflow:hidden;background:var(--panel)}
@media(max-width:640px){.ba{grid-template-columns:1fr}}
.ba > div{padding:22px}
.ba .before{background:var(--panel2);border-right:1px solid var(--line)}
.ba h6{margin:0 0 4px;font-size:11.5px;font-weight:700;letter-spacing:.13em;
  text-transform:uppercase;color:var(--ink3)}
.ba .after h6{color:var(--green)}
.ba .pick{font-size:30px;font-weight:700;letter-spacing:-.03em;margin:6px 0 3px}
.ba .before .pick{color:var(--ink2)}
.ba .after .pick{color:var(--green)}
.ba .pct{font-size:14px;color:var(--ink3)}
.ba ul{margin:14px 0 0;padding-left:17px;font-size:14px;color:var(--ink2)}
.quote{border-left:3px solid var(--green);padding:4px 0 4px 16px;margin:20px 0 0;
  font-size:17px;line-height:1.5;color:var(--ink)}
.quote cite{display:block;font-size:13px;color:var(--ink3);font-style:normal;margin-top:7px}

/* stack table */
table.stack{width:100%;border-collapse:collapse;font-size:14.5px;margin:14px 0}
table.stack th{text-align:left;padding:10px 11px;border-bottom:1px solid var(--line);
  font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3);font-weight:700}
table.stack td{text-align:left;padding:10px 11px;border-bottom:1px solid var(--line);
  vertical-align:top;color:var(--ink2)}
table.stack td.layer{white-space:nowrap;color:var(--ink)}

.foot{border-top:1px solid var(--line);margin-top:44px;padding:26px 0 10px;
  color:var(--ink3);font-size:13.5px;text-align:center}
.foot b{color:var(--ink)}
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

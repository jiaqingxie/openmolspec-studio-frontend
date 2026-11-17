from __future__ import annotations

import html


APP_CSS = """
<style>

:root { --ink:#17231f; --muted:#66736d; --green:#176b5b; --lime:#c9ef78; --paper:#f6f8f4; --line:#dce4dc; }
.stApp { background: radial-gradient(circle at 88% 2%, rgba(201,239,120,.22), transparent 25%), var(--paper); }
html, body, [class*="css"] { font-family: Arial, sans-serif; color:var(--ink); }
[data-testid="stSidebar"] { background:#14231f; border-right:0; }
[data-testid="stSidebar"] * { color:#eef6ef; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding:.55rem .7rem; border-radius:10px; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:#25453c; }
[data-testid="stMainBlockContainer"], .block-container {
  max-width:1280px;
  padding-top:5.25rem !important;
  padding-bottom:5rem;
}
.startup-card { background:#fff; border:1px solid var(--line); border-radius:20px; padding:2rem 2.2rem; margin:.5rem 0 1rem; box-shadow:0 18px 48px rgba(23,35,31,.07); }
.startup-title { font-size:clamp(1.65rem,3vw,2.5rem); font-weight:700; letter-spacing:-.04em; margin:.7rem 0 .65rem; }
.startup-copy { color:var(--muted); font-size:1rem; line-height:1.7; max-width:780px; }
.startup-models { color:var(--green); font-family:Arial,sans-serif; font-size:.78rem; margin-top:1.25rem; }
[data-testid="stSpinner"] { min-height:2.5rem; overflow:visible !important; }
[data-testid="stSpinner"] p { white-space:normal !important; overflow:visible !important; text-overflow:clip !important; line-height:1.5 !important; }
.brand { font-size:.78rem; letter-spacing:.16em; text-transform:uppercase; color:#a8c3b8; margin-bottom:.5rem; }
.brand-title { font-size:1.45rem; font-weight:700; color:white; line-height:1.1; margin-bottom:2rem; }
.hero { padding-top:.75rem; }
.eyebrow { display:block; color:var(--green); font-family:Arial,sans-serif; font-size:.78rem; line-height:1.5; letter-spacing:.13em; text-transform:uppercase; margin:0 0 .45rem; }
.hero h1 { font-size:clamp(1.65rem,2.5vw,2.6rem); line-height:1.2; letter-spacing:-.025em; max-width:none; margin:.65rem 0 .8rem; white-space:nowrap; }
.hero p { color:var(--muted); font-size:.95rem; max-width:none; line-height:1.6; white-space:nowrap; }
.step { font-family:Arial,sans-serif; color:var(--green); font-size:.78rem; margin-bottom:.35rem; }
.panel-title { font-size:1.2rem; font-weight:650; margin-bottom:.2rem; }
.panel-sub { color:var(--muted); font-size:.9rem; margin-bottom:1rem; }
.metric-card { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1.15rem 1.25rem; height:132px; box-sizing:border-box; display:flex; flex-direction:column; }
.metric-label { color:var(--muted); font-size:.74rem; line-height:1.35; letter-spacing:.05em; text-transform:uppercase; }
.metric-value { font-size:1.75rem; font-weight:650; letter-spacing:-.04em; margin-top:.45rem; }
.metric-detail { color:var(--muted); font-size:.8rem; line-height:1.35; margin-top:auto; }
.model-note { background:#edf4ec; border-left:3px solid var(--green); padding:.85rem 1rem; border-radius:0 10px 10px 0; color:#415149; font-size:.86rem; }
.status-row { display:flex; justify-content:space-between; gap:.5rem; font-size:.73rem; padding:.42rem 0; border-bottom:1px solid rgba(255,255,255,.09); }
.status-ok { color:#c9ef78 !important; }
.status-bad { color:#ffb7a8 !important; }
.candidate { background:#fff; border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem; margin:.6rem 0; }
.candidate code { white-space:normal; word-break:break-all; color:#174b40; }
.candidate-smiles { font-size:1.02rem; margin:.65rem 0; }
.candidate-smiles code { white-space:normal; overflow-wrap:anywhere; color:#174b40; }
.candidate-meta { color:var(--muted); font-size:.82rem; line-height:1.55; overflow-wrap:anywhere; }
.stButton > button, .stDownloadButton > button { border-radius:10px; min-height:2.75rem; font-weight:600; }
.stButton > button[kind="primary"] { background:var(--green); border-color:var(--green); }
[data-testid="stFileUploaderDropzone"] { background:#fff; border:1px dashed #9eb2a8; border-radius:14px; }
div[data-testid="stVerticalBlockBorderWrapper"] { background:rgba(255,255,255,.65); border-color:var(--line); border-radius:18px; }
code { font-family:Arial,sans-serif; }
@media (max-width:1100px) {
  .hero h1, .hero p { white-space:normal; }
}
@media (max-width:640px) {
  [data-testid="stMainBlockContainer"], .block-container { padding-top:4.75rem !important; }
  .hero { padding-top:.5rem; }
  .hero h1 { font-size:1.65rem; line-height:1.25; letter-spacing:-.02em; }
  .hero p { font-size:.92rem; }
}
</style>
"""


def metric_card(label: str, value: str, detail: str = "") -> str:
    detail_html = (
        f'<div class="metric-detail">{html.escape(detail)}</div>'
        if detail
        else ""
    )
    return (
        '<div class="metric-card">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div>{detail_html}</div>'
    )


def page_hero(eyebrow: str, title: str, description: str) -> str:
    return (
        '<div class="hero">'
        f'<div class="eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1>{title}</h1><p>{html.escape(description)}</p></div>'
    )

"""Generate a single-file SHARE.html — the "show this to mentors" page.

Embeds every screenshot inline as base64 so the file is fully portable: WhatsApp,
email, USB, anywhere. No external assets, no broken links, works offline.

Run:
    python scripts/build_share_page.py
Outputs:
    SHARE.html (root)
"""

from __future__ import annotations
import base64
import io
import sys
from datetime import datetime
from pathlib import Path

import qrcode

REPO = Path(__file__).resolve().parent.parent
SHOTS = REPO / "eval" / "screenshots"

APP_URL = "https://rx-helper-7474644161560453.aws.databricksapps.com"
DEMO_URL = f"{APP_URL}/?demo=1&session=demo-patient-001"


def b64_image(path: Path, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def make_qr(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


SHOTS_META = [
    ("01_home.png",       "Home dashboard",
     "Patient profile (Rina Devi), next-dose card with countdown, refill alert when paracetamol is running low. Tri-lingual UI (English / Hindi / Malayalam)."),
    ("02_ask_answer.png", "Multilingual chatbot",
     "Tap a question chip → grounded answer drawn from CDSCO + NLEM + drug-food tables. Auto-disclaimer; refuses fabricated doses; second LLM pass for hallucination check."),
    ("03_home_full.png",  "Support cards expanded",
     "Save money (Jan Aushadhi), nearest pharmacy, govt schemes, food/alcohol warnings — all collapsed by default; lazy-loaded; demo-cached so demo never hangs."),
    ("04_scan_result.png","Prescription scanner — trust check",
     "Vision LLM extracts drugs from a printed Rx. CDSCO trust check fires per drug. Cefixime batch CXM2509A flagged red as not-of-standard-quality. Drug-pair interactions analysed."),
    ("05_timetable.png",  "My medicines / dosage timetable",
     "Auto-built schedule from prescription. Tap a med → set reminder call (Bolna India outbound — DLT-ready voice agent)."),
    ("06_checkin.png",    "Periodic side-effect check-in",
     "Hindi voice or text → LLM classifies symptom + severity → empathetic Hindi reply, with urgent flag escalating to SOS."),
    ("07_sos.png",        "SOS — double-tap to confirm",
     "Geolocation-tagged SMS + call to a pre-registered emergency contact. Double-tap-to-confirm prevents accidental triggers."),
    ("08_lang_ml.png",    "Page-wide Malayalam translation",
     "Single dropdown in the header switches the entire UI to Malayalam (മല). All chip answers, food warnings, scheme details, and care card adapt. Cached — zero Sarvam calls during demo."),
    ("09_lang_hi.png",    "Page-wide Hindi translation",
     "Same UI in Hindi (हिं). 50+ UI strings cached for the demo; any new dynamic text falls back to Sarvam at runtime."),
    ("10_lang_en.png",    "Clean English mode",
     "Full English UI for the mentor / judge audience. Default if browser locale isn't Hindi or Malayalam."),
]


def screenshots_html() -> str:
    blocks = []
    for fname, title, caption in SHOTS_META:
        path = SHOTS / fname
        if not path.exists():
            continue
        src = b64_image(path)
        blocks.append(f"""
<figure class="shot">
  <img src="{src}" alt="{title}">
  <figcaption>
    <strong>{title}</strong>
    <span>{caption}</span>
  </figcaption>
</figure>""")
    return "\n".join(blocks)


def feature_table_rows() -> str:
    rows = [
        ("Page-wide translation",       "EN / हिं / മല dropdown in the header — translates every UI string in real time, demo-cached"),
        ("Prescription OCR",            "Vision LLM extracts drugs/dose/freq from a Rx photo"),
        ("Drug-label OCR",              "Read a medicine strip directly to verify what's been dispensed"),
        ("CDSCO trust check",           "Approved · banned · NSQ-flagged batches; data-grounded verdict"),
        ("Bilingual voice explanation", "Sarvam Bulbul TTS in Hindi, browser TTS for English; full-pipeline cached"),
        ("Drug-drug interactions",      "Hard FDC blocks (CDSCO ban list) + LLM-soft pairwise reasoning"),
        ("Bilingual Q&A chatbot",       "RAG-grounded — every claim cites a Delta row; refuses on low evidence"),
        ("Refill alerts",               "Auto-flagged when a medicine has < 3 days of supply left"),
        ("Food / alcohol warnings",     "Curated drug-food interactions per medicine on file"),
        ("Govt scheme finder",          "Ayushman Bharat + state schemes by diagnosis"),
        ("Jan Aushadhi pharmacy locator","Haversine SQL over store coordinates"),
        ("Monthly savings summary",     "Per-drug PMBJP generic vs branded; ₹/month savings"),
        ("Printable care card",         "Bilingual one-page handout for caregivers"),
        ("Side-effect check-in chat",   "LLM classifies severity; logs to Delta; auto-escalates urgent"),
        ("SOS",                         "Geo-tagged SMS + call; double-tap to confirm"),
        ("Reminder calls",              "Bolna India voice-agent; dryrun until demo-time"),
    ]
    return "\n".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)


def databricks_features_html() -> str:
    items = [
        "Delta Lake (16 tables)",
        "Unity Catalog (3-level namespace)",
        "UC Volumes (data + audio_cache)",
        "UC Secrets",
        "Databricks SQL (serverless warehouse)",
        "Vector Search",
        "Model Serving — vision (Llama-4-Maverick)",
        "Model Serving — reasoning (Llama-3.3-70B)",
        "Model Serving — embeddings (gte-large-en)",
        "Databricks Apps (FastAPI hosting)",
        "Databricks Jobs",
        "Databricks Asset Bundles",
        "Change Data Feed",
        "MLflow-style audit (inference_log Delta)",
    ]
    return "\n".join(f"<li>{x}</li>" for x in items)


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bharosa — Project share</title>
<style>
  :root {
    --bg: #f8fafc; --card: #ffffff; --text: #0f172a; --muted: #64748b;
    --primary: #1565c0; --safe: #2e7d32; --danger: #c62828; --warn: #f57c00;
    --border: #e2e8f0; --radius: 16px;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0b1220; --card: #111a2e; --text: #f1f5f9; --muted: #94a3b8; --border: #1e2a44; }
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: 'Inter', 'Helvetica Neue', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.55;
    padding: clamp(16px, 4vw, 48px);
    max-width: 1100px; margin: 0 auto;
  }
  h1 { font-size: clamp(2rem, 6vw, 3rem); margin: 0 0 8px; letter-spacing: -0.02em; }
  h2 { font-size: 1.5rem; margin: 32px 0 12px; color: var(--primary); border-bottom: 2px solid var(--primary); padding-bottom: 6px; }
  h3 { margin: 16px 0 8px; }
  .muted { color: var(--muted); }
  .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.85em; font-weight: 600; }
  .badge.ok { background: #dcfce7; color: #166534; }
  .badge.warn { background: #fff4d6; color: #92400e; }
  .grid {
    display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px;
  }
  .card h3 { margin-top: 0; }
  .hero {
    display: grid; gap: 24px; align-items: center;
    grid-template-columns: 2fr 1fr; padding: 24px 0;
  }
  @media (max-width: 700px) { .hero { grid-template-columns: 1fr; } }
  .qr {
    text-align: center; padding: 16px;
    background: white; border: 1px solid var(--border); border-radius: var(--radius);
  }
  .qr img { width: 100%; max-width: 220px; height: auto; }
  .pill-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
  .pill {
    padding: 4px 12px; border-radius: 999px; font-size: 0.85em;
    background: rgba(21,101,192,0.12); color: var(--primary); font-weight: 600;
  }
  .url-row { font-family: ui-monospace, monospace; font-size: 0.85em; word-break: break-all; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  td { padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
  td:first-child { font-weight: 600; min-width: 180px; }
  ul { margin: 12px 0; padding-left: 20px; }
  ul li { padding: 4px 0; }
  .shots { display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin-top: 16px; }
  figure.shot {
    margin: 0; background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
  }
  figure.shot img {
    display: block; width: 100%; height: auto;
    border-bottom: 1px solid var(--border);
    background: #f1f5f9;
  }
  figure.shot figcaption {
    padding: 14px; display: flex; flex-direction: column; gap: 6px;
  }
  figure.shot figcaption strong { color: var(--primary); }
  figure.shot figcaption span { color: var(--muted); font-size: 0.92em; }
  .stats { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin: 16px 0; }
  .stat {
    text-align: center; padding: 16px;
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  }
  .stat .num { font-size: 2rem; font-weight: 700; color: var(--primary); }
  .stat .lbl { color: var(--muted); font-size: 0.9em; }
  .footer {
    margin-top: 48px; padding-top: 24px;
    border-top: 1px solid var(--border); color: var(--muted);
    font-size: 0.85em;
  }
  pre {
    background: rgba(15,23,42,0.04); padding: 12px; border-radius: 8px;
    font-size: 0.85em; overflow-x: auto;
  }
  @media (prefers-color-scheme: dark) { pre { background: rgba(255,255,255,0.04); } }
</style>
</head>
<body>

<header class="hero">
  <div>
    <span class="badge ok">Live · Databricks Apps</span>
    <h1>💊 Bharosa</h1>
    <p style="font-size:1.2em;color:var(--muted);margin:8px 0 16px">
      A voice-first prescription companion for low-literacy patients in rural India.
      Scans a prescription, cross-checks every drug against CDSCO's approved / banned / quality registries,
      explains it in Hindi or English by voice, and supports reminders, side-effect check-ins, and SOS — all on Databricks.
    </p>
    <div class="pill-row">
      <span class="pill">16 features</span>
      <span class="pill">14 Databricks primitives</span>
      <span class="pill">EN · हिं · മല</span>
      <span class="pill">PWA installable</span>
      <span class="pill">24/25 UI tests pass</span>
      <span class="pill">14/16 eval cases pass</span>
    </div>
  </div>
  <div class="qr">
    <img src="{qr_demo}" alt="QR to live demo">
    <div class="muted" style="font-size:0.85em;margin-top:8px">Scan → live cached demo</div>
  </div>
</header>

<section class="card">
  <h3>Live URL</h3>
  <p class="url-row"><a href="{demo_url}">{demo_url}</a></p>
  <p class="muted" style="font-size:0.9em">
    Demo mode is forced via <code>?demo=1</code> — every API call resolves from a cached fixture so the demo
    never hangs. Reach the same URL without it for the live backend (requires Databricks workspace SSO).
  </p>
  <p style="margin-top:12px">Tap the <strong>🎬</strong> icon in the header to toggle cached demo on/off; <strong>🔥</strong> warms the pipeline cache.</p>
</section>

<h2>Screenshots</h2>
<div class="shots">
{screenshots}
</div>

<h2>What it does — full feature inventory</h2>
<div class="card">
  <table>
    {feature_rows}
  </table>
</div>

<h2>Stats</h2>
<div class="stats">
  <div class="stat"><div class="num">16</div><div class="lbl">user-facing features</div></div>
  <div class="stat"><div class="num">14</div><div class="lbl">Databricks primitives</div></div>
  <div class="stat"><div class="num">16</div><div class="lbl">Delta tables</div></div>
  <div class="stat"><div class="num">3</div><div class="lbl">languages live (EN · HI · ML)</div></div>
  <div class="stat"><div class="num">14</div><div class="lbl">guardrails layered</div></div>
  <div class="stat"><div class="num">24/25</div><div class="lbl">UI tests pass</div></div>
</div>

<h2>Databricks features used</h2>
<div class="card">
  <ul>{databricks_features}</ul>
</div>

<h2>Architecture</h2>
<div class="card">
<pre>
┌────────────────────────────────────────────────────────────┐
│  Browser / Phone — voice-first HTML+CSS, PWA, en/hi auto   │
└────────────────────┬───────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼───────────────────────────────────────┐
│             Databricks App  (FastAPI)                      │
│   main.py — pages + 21 API endpoints, all guard-wrapped    │
│   guards.py — input validation + LLM safety + grounding    │
│   audit.py  — every inference → inference_log Delta        │
│   agent.py  — 7-branch intent router (langgraph-equiv)     │
│   rag.py    — multi-source citations across 7 Delta tables │
└──┬───────┬─────────────┬──────────────┬───────────┬────────┘
   │       │             │              │           │
   ▼       ▼             ▼              ▼           ▼
 Vision  Llama-3.3   Vector Search   Delta Lake   Sarvam
 (OCR)   (reason)    (gte-large)     16 tables    (translate
                                                   /TTS/ASR)
                                                   Bolna
                                                   (calls)
</pre>
</div>

<h2>Anti-hallucination guardrails (14 layered)</h2>
<div class="card">
  <ul>
    <li><strong>Image / audio MIME &amp; size caps</strong> — 8 MB / 6 MB</li>
    <li><strong>Drug-name regex</strong> — character allowlist, length cap</li>
    <li><strong>Language allowlist</strong> — 9 supported codes only</li>
    <li><strong>Phone E.164 regex</strong> — for SOS / reminder endpoints</li>
    <li><strong>Prompt-injection phrase block</strong> — utterances are screened</li>
    <li><strong>LLM-output JSON schema enforcement</strong> — strict parse with required keys</li>
    <li><strong>Refusal of model-invented dose</strong> — numeric tokens must trace to source</li>
    <li><strong>Refusal of substitution language</strong> — model can't recommend a different drug</li>
    <li><strong>Banned-drug hard override</strong> — replaces output with the ban notice</li>
    <li><strong>RAG confidence floor (0.45)</strong> — refuses with safe template if evidence too thin</li>
    <li><strong>Drug-token grounding</strong> — every drug-shaped token must appear in citations</li>
    <li><strong>Bilingual auto-disclaimer</strong> — appended to every patient-facing answer</li>
    <li><strong>Per-session rate limit</strong> — 30/min default, 5/min for outbound calls</li>
    <li><strong>PII hashing in audit logs</strong> — phone / name / email never stored cleartext</li>
  </ul>
</div>

<h2>Quick test for mentors</h2>
<div class="card">
  <p>Open the demo URL → tap the 🎬 icon (turns red, "DEMO MODE" badge appears) → try these:</p>
  <ol>
    <li><strong>Scan</strong> → upload <em>any</em> photo → 3-drug demo result with red NSQ alert on cefixime batch CXM2509A</li>
    <li><strong>Ask</strong> chip <em>"Para + Metformin?"</em> → grounded answer with disclaimer</li>
    <li><strong>Ask</strong> chip in <em>हिन्दी</em> → answer in Devanagari</li>
    <li><strong>Save money</strong> card → ₹231/month savings breakdown via Jan Aushadhi</li>
    <li><strong>Find a Jan Aushadhi pharmacy</strong> → 5 nearest, sorted by Haversine distance</li>
    <li><strong>Govt schemes</strong> → Ayushman Bharat eligibility</li>
    <li><strong>Care Card</strong> → printable bilingual handout</li>
    <li><strong>SOS</strong> page → double-tap-to-confirm flow</li>
  </ol>
</div>

<h2>Mentor questions we want feedback on</h2>
<div class="card">
  <ol>
    <li>Is the trust-check + NSQ-batch story compelling enough as the lead pitch?</li>
    <li>Does the bilingual UI feel right for an actual rural patient (not a tech demo)?</li>
    <li>Are 14 guardrails overkill or about right for healthcare AI?</li>
    <li>Should we ship the agent / langgraph router as a primary surface, or keep buttons primary?</li>
    <li>Is the cached demo mode a smart fallback or does it hide too much complexity?</li>
    <li>What other Indian govt-data sources should we wire in next? (we have CDSCO, NLEM, PMBJP, schemes already)</li>
  </ol>
</div>

<div class="footer">
  Built on Databricks · {generated_at} IST · single-file share, embedded screenshots, fully offline.
  <br>
  ⚠ Information only — not a substitute for a doctor.
</div>

</body>
</html>
"""


def main():
    if not SHOTS.exists():
        print("ERROR: no screenshots dir; run eval/ui_test.py first", file=sys.stderr)
        sys.exit(1)

    qr_demo = make_qr(DEMO_URL)
    # Plain string replace — avoids the `.format()` CSS-brace conflict
    html = HTML
    for k, v in [
        ("{qr_demo}", qr_demo),
        ("{demo_url}", DEMO_URL),
        ("{screenshots}", screenshots_html()),
        ("{feature_rows}", feature_table_rows()),
        ("{databricks_features}", databricks_features_html()),
        ("{generated_at}", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]:
        html = html.replace(k, v)
    out = REPO / "SHARE.html"
    out.write_text(html, encoding="utf-8")
    size_kb = len(html.encode()) / 1024
    print(f"wrote {out} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()

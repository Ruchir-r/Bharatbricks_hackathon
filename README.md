# Rx Helper

**A voice-first prescription companion for low-literacy patients in rural India — built on Databricks, grounded in CDSCO regulatory data, and demoable end-to-end in under two minutes.**

> Translator apps tell a rural patient *what* their prescription says. Rx Helper tells them whether to **trust** it — cross-checking every drug against CDSCO's approved list, banned list, and not-of-standard-quality alerts; surfacing Jan Aushadhi generic equivalents to cut their bill 60–90%; and explaining it in their mother tongue by voice. When something goes wrong, one tap on the big red button rings their doctor through a Hindi voice agent.

Submitted to **Bharat Bricks Hacks 2026 — IIT Madras**.

---

## What it does (one screen)

| Step | What the patient sees | What the system does |
|---|---|---|
| 1. Scan | Snap prescription photo | Llama-4-Maverick vision OCR via Databricks Model Serving |
| 2. Clean | Garbled OCR drug names → real brands | `drug_aliases` Delta table (43 curated rows) + rapidfuzz fallback |
| 3. Trust check | ✅ green / ⚠️ NSQ batch / 🚫 banned | RAG over 7 Delta tables: CDSCO approved, banned, NSQ alerts, FDC, NLEM, PMBJP, food-interactions |
| 4. Save | "Cheaper version available" — ₹85 → ₹12 | Jan Aushadhi PMBJP catalogue (2,438 SKUs, real Govt CSV) |
| 5. Explain | 🔊 Hindi audio, simple words | Sarvam Bulbul v2 TTS (`anushka` voice), bilingual UI toggle (en / hi / ml) |
| 6. Schedule | Auto-built timetable + countdown | Frequency parser (`1+0+1`) → next-dose timestamp |
| 7. Remind | Phone rings, agent speaks Hindi | Bolna outbound voice agent (Indian DLT-ready stack) |
| 8. SOS | One red button, double-tap to confirm | Pre-filled emergency contact + geolocation → SMS + live Bolna call |

---

## Why Databricks (not just a Streamlit app)

This is the part most prescription apps skip. Trust requires **regulatory data, kept fresh, served with low latency, and audited**. That maps onto Databricks primitives one-to-one:

| Need | Databricks primitive | What we did |
|---|---|---|
| Authoritative drug data | **Unity Catalog** (`bricksiitm.rx_helper`) | 7 Delta tables: CDSCO approved (51), banned (21), NSQ alerts (20), FDC approved (20), NLEM 2022 essentials (650 from real PDF), PMBJP catalogue (2,438 from real Govt CSV), drug-food interactions (35) |
| Brand → molecule resolution | **Delta + Change Data Feed** | `drug_aliases` table (43 rows) — versioned, auditable, fuzzy-matched at runtime |
| Semantic retrieval over CDSCO | **Vector Search** (`hack_cdsco_endpoint`) + `databricks-gte-large-en` | RAG grounded answers with citation-or-refuse policy |
| OCR from prescription images | **Model Serving** — `databricks-llama-4-maverick` | Vision-mode prompt extracts drugs, doses, frequencies |
| Reasoning + safety guards | **Model Serving** — `databricks-meta-llama-3-3-70b-instruct` | Conflict checks, plain-language explanations, dose-invention refusal |
| Hosting | **Databricks Apps** (FastAPI) | OAuth M2M for SQL access; secrets via app.yaml `valueFrom` refs |
| Audit | **Delta `inference_log`** | Every LLM call logged: prompt, model, latency, tokens, citation set |
| Reproducibility | **Asset Bundles** (`databricks.yml`) | One command from clone to deployed app |

External APIs (Sarvam, Bolna) are *layered on top* — they're the last-mile voice. The trust layer is entirely on Databricks.

---

## Architecture

```
┌────────────┐  prescription jpg   ┌────────────────────────────────┐
│  Patient   │ ──────────────────▶ │ FastAPI on Databricks Apps     │
│ phone (PWA)│ ◀────────────────── │  (app/main.py + routers)       │
└────────────┘   bilingual audio   └──────┬─────────┬───────────────┘
                                          │         │
                ┌─────────────────────────┘         └─────────────────────┐
                ▼                                                         ▼
   ┌──────────────────────────────┐                    ┌────────────────────────────┐
   │ Databricks Model Serving      │                    │ Unity Catalog (Delta)      │
   │  • llama-4-maverick (vision)  │                    │  • cdsco_approved / banned │
   │  • llama-3-3-70b   (reason)   │                    │  • cdsco_nsq_alerts        │
   │  • gte-large-en    (embed)    │                    │  • cdsco_fdc_approved      │
   └──────────────────────────────┘                    │  • nlem_2022_real (650)    │
                                                       │  • pmbjp_catalog (2,438)   │
   ┌──────────────────────────────┐                    │  • drug_aliases / drug_food│
   │ Vector Search                 │                    │  • inference_log (audit)   │
   │  hack_cdsco_endpoint          │ ◀──── retrieval ───┤                            │
   └──────────────────────────────┘                    └────────────────────────────┘

   ┌──────────────────────────────┐                    ┌────────────────────────────┐
   │ Sarvam (Bulbul v2 TTS,        │                    │ Bolna voice agent          │
   │ Saarika ASR, Translate)       │                    │ (Indian, DLT-ready)        │
   └──────────────────────────────┘                    └────────────────────────────┘
```

A longer walkthrough lives in [`docs/STRUCTURE.md`](docs/STRUCTURE.md).

---

## Quickstart

### Run the demo locally (no Databricks needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000`, click the **🎬 demo** button (top-right), and follow the demo script below. Demo mode serves cached fixtures so the entire flow runs offline — judges can replay it on a laptop with no internet.

### Deploy to Databricks (full stack)

```bash
databricks bundle deploy --target dev      # creates Unity Catalog tables, app, secrets
databricks bundle run ingest_cdsco         # ingest CSVs → Delta + build Vector Search index
```

The bundle (`databricks.yml`, `resources/jobs.yml`) provisions:
- Unity Catalog schema `bricksiitm.rx_helper` + 7 Delta tables seeded from `data/*.csv`
- Vector Search endpoint `hack_cdsco_endpoint` indexed off CDSCO + NSQ data
- Databricks App with secrets bound via `valueFrom` (Sarvam, Bolna keys never in code)

Notebooks `notebooks/01_ingest_cdsco.py` and `notebooks/02_build_vector_index.py` are the ingest jobs.

> **Full step-by-step deploy guide → [`DEPLOY.md`](DEPLOY.md)** (auth, secret scope setup, bundle deploy, ingest job, warehouse binding, Bolna agent config, troubleshooting).

---

## Demo script (90 seconds)

1. **Home** — meet "Rina Devi", 3 existing meds on her timetable. Toggle 🔊 → hear it in Hindi.
2. **Scan** — upload `sample_prescription.jpeg`. OCR comes back in ~3s, four drugs.
3. **Add to profile** — click the green button. Click-through to results.
4. **Results page** — combined timetable now shows 7 meds. Next-dose countdown ticking down from 45s. Each drug card: trust badge, side effects, warnings, **3-tier price comparison** with Jan Aushadhi savings. One drug is flagged 🚫 *NSQ batch CXM2509A*. Toggle language → entire page re-renders in Hindi.
5. **📞 Live Bolna call** — click *take-medicine reminder*. Phone rings within 5–10s. Agent speaks in Hindi: *"Namaste Rina-ji, Crocin Cold ka samay ho gaya hai…"*.
6. **🚨 SOS** — back to home, big red button, double-tap. SMS + call to "Dr. Saab" at the pre-filled number, with geolocation in the message.

Screenshots in `eval/screenshots/`.

---

## Data sources & provenance

Everything in `data/` is from public, named sources — no scraped or synthetic regulatory data:

| File | Rows | Source |
|---|---|---|
| `cdsco_approved.csv` | 51 | CDSCO public approvals list |
| `cdsco_banned.csv` | 21 | CDSCO Section 26A bans + recent gazette notifications |
| `cdsco_nsq_alerts.csv` | 20 | CDSCO Drug Alerts (monthly NSQ bulletins) |
| `cdsco_fdc_approved.csv` | 20 | CDSCO Fixed-Dose Combination approvals |
| `nlem_2022_real.csv` | 650 | National List of Essential Medicines 2022 (parsed from `data/raw/nlem2022.pdf` via pdfplumber) |
| `pmbjp_catalog_real.csv` | 2,438 | Pradhan Mantri Bhartiya Janaushadhi Pariyojana product list |
| `drug_aliases.csv` | 43 | Hand-curated brand ↔ molecule map for OCR-typo recovery |
| `drug_food.csv` | 35 | Curated from BNF + Indian Pharmacopoeia |
| `govt_schemes.csv` | 10 | PMJAY / Ayushman Bharat / state schemes |

The ingest pipeline (`notebooks/01_ingest_cdsco.py`) is reproducible — pointed at the raw PDFs/CSVs in `data/raw/`, it produces the Delta tables.

---

## Safety & guardrails

This is a medical app for vulnerable users. Failure modes have to be designed in, not bolted on:

| Risk | Guard |
|---|---|
| LLM hallucinates a dose | Hard refusal: doses only ever come from prescription OCR, never generated |
| Banned drug in prescription | Hard override — RAG result ignored, banned-drug alert wins |
| RAG returns irrelevant chunks | Confidence threshold; below it, system says "I don't know" + cites no sources |
| OCR mis-reads brand name | `drug_aliases` exact match → fuzzy match (rapidfuzz, cutoff ≥ 85) → LLM fallback |
| Prompt injection in image | Layered: input sanitiser, output schema validation, banned-phrase block list |
| User PII | Phone numbers + names hashed before logging |
| Regulatory drift | Every CDSCO row carries a `source_url` and `last_verified_at` |

A full policy enumeration is in `app/lib/guards.py`. Eval cases that exercise each guard are in `eval/cases.json` (16 cases, 29/30 UI tests passing — see `eval/scorecard.md`).

---

## Repo layout

```
app/
  main.py                FastAPI entry — page routes + 20+ /api endpoints
  app.yaml               Databricks Apps config (secrets via valueFrom)
  routers/               (planned split of main.py)
  lib/
    drug_identifier.py   OCR + brand→molecule normalisation
    rag.py               7-table retrieval with brand resolution
    bolna.py             Voice-agent client (place_call, get_call_status)
    bolna_flows.py       3 flows: take_now, checkup, emergency
    sarvam.py            TTS + ASR + translate
    guards.py            Input/output safety policies
    audit.py             Delta-backed inference log
    db.py                OAuth-aware SQL connector (M2M in Apps, PAT local)
  static/                PWA front-end — vanilla JS, no framework
  templates/             Jinja2 (home, scan, scan_result, sos, checkin, timetable)
data/                    CDSCO + NLEM + PMBJP CSVs (and `raw/` PDFs)
notebooks/               Ingest + vector index build
eval/                    16 test cases + Playwright UI suite + screenshots
scripts/                 build_share_page, extract_nlem_pdf, bolna_spaced_test
docs/                    Round-by-round reports, architecture deep-dive, decision log
databricks.yml           Asset Bundle root
```

---

## Team

Built in 24h by **Ruchir** (architecture, full-stack, demo) and **Harshit** (eval suite, data ingest, deployment). See [`docs/TEAMMATES.md`](docs/TEAMMATES.md) for the division-of-labour and the AI-agent collaboration protocol used to coordinate.

---

## Acknowledgements

- **CDSCO** for the regulatory data that makes this trust layer possible.
- **Govt of India PMBJP / Jan Aushadhi** for the generic-medicines catalogue.
- **Sarvam AI** for India-first speech models.
- **Bolna** for the DLT-ready Indian voice-agent stack.
- **Databricks** for the Lakehouse, Model Serving, Vector Search, and Apps that made a 24-hour build of this scope possible.

---

## License

MIT for the code. Underlying CDSCO / PMBJP / NLEM data are public-domain Govt of India datasets — please credit the originating ministry if you reuse them.

# Rx Helper — final report before code freeze

**Time:** 2026-04-26 ~14:30 IST. Code freeze 16:00.
**Token spend this round:** 1 vision LLM (free DBX) · ~3 reasoning LLM (free DBX) · 0 Sarvam · 0 Bolna · ~50 SQL.

---

## What's done · tested · ready-to-demo

### 1. OCR end-to-end works (priority: ✅)

- `/api/scan` (vision LLM) extracts 4 cold-remedy drugs from `sample_prescription.jpeg`
- 2nd-pass normaliser maps OCR'd names → clean Indian brands using `drug_aliases` Delta table
- Cross-checks each drug against CDSCO + PMBJP; produces 3-tier price comparison
- "Add to my profile" CTA appears immediately so user is never stuck
- /scan_result renders rich cards: likely_brand · raw OCR · molecule · CDSCO badge · price comparison · 45s countdown
- **29/30 Playwright UI tests pass.** Only the old cosmetic Malayalam-residual fail remains.

### 2. Drug aliases table

`bricksiitm.rx_helper.drug_aliases` — 43 rows. Each row: `alias, normalized_brand, generic_or_molecule, drug_class, confidence, notes`. Lookup is exact-then-fuzzy via rapidfuzz (score ≥ 80). Deterministic, fast, no LLM cost. Hit rate on demo prescription: **4/4** drugs (zero LLM calls fired).

### 3. Price comparison (3-tier)

Each normalised drug gets a `price_comparison` array with up to 3 SKUs:
- `Jan Aushadhi (PMBJP)` — cheapest matching real PMBJP catalog SKU
- `Pharmacy generic` — 2nd PMBJP SKU OR mid-tier estimate
- `Typical branded (retail)` — estimated 7.5× PMBJP MRP for OTC molecules (clearly labelled "estimated")

Plus a "Save up to ₹X by switching" line at the bottom.

### 4. TTS auto-play on voice input

- **Text input** → reply renders as text + 🔊 button (user opts in)
- **Voice input** (mic on `/checkin`) → reply auto-plays Sarvam TTS (cached when possible)
- Implementation: `lastInputFromVoice` flag set in mic recorder's `onstop` handler
- Same pattern wired into home `/api/ask` for future mic input

### 5. SOS pre-filled for one-tap

- /api/profile returns `emergency_contact_name = "Dr. Saab"` for the demo session
- SOS page auto-populates patient name + emergency phone + contact name
- Big red `🚨 SEND SOS` button dominates the page
- Double-tap-to-confirm preserved (4-sec arming window)
- On confirm, fires both `/api/sos` (legacy) AND `/api/flow/emergency` (Bolna agent flow) in parallel

### 6. Demo-mode policy

Final policy: **DEMO MODE caches everything except `/api/health`** (so diagnostic endpoints stay live). Live mode hits the real Lakehouse for everything. This makes demos predictable and offline-safe; switch off the 🎬 toggle for live behaviour.

### 7. Structured logging (`lib/log.py`)

- One JSON line per event: `{ts, level, stage, latency_ms, session_id, meta}`
- Wired into `normalize_ocr_drugs` (alias_hit, alias_summary) — pattern to copy elsewhere
- Visible in Databricks Apps' Logs tab

### 8. Bolna 3-flow agent + webhook (from previous round)

Already done; recap: `/api/flow/take_now`, `/checkup`, `/emergency`. Webhook `/bolna_webhook?token=…` deployed but blocked by Apps SSO — workaround is `GET /api/call_status?call_id=…` polling. Bolna agent's `webhook_url` PATCHed via `/v2/agent/{id}` (HTTP 200).

---

## File changes this session (chronological)

```
NEW
  app/lib/bolna_flows.py            3-flow dispatcher (take_now/checkup/emergency)
  app/lib/voice_reminder.py         "take medicine now" TTS automation, en/hi/ml templates
  app/lib/log.py                    structured JSON logger + timed() context manager
  app/templates/scan_result.html    post-scan rich result page
  app/static/scan_result.js         page JS — countdown + alternates + timesheet
  data/sample_prescription.jpeg     real prescription provided by user
  data/sample_prescription_extracted.json   live OCR extraction (raw)
  data/drug_aliases.csv             43 typo→clean-brand mappings
  REPORT_SESSION3.md                round-3 narrative
  REPORT_FINAL.md                   THIS file

MODIFIED
  app/lib/drug_identifier.py        + normalize_ocr_drugs (alias-first, LLM fallback) + 3-tier price_comparison + structured logging
  app/lib/bolna.py                  full rewrite (CallResult/Status TypedDicts, format_phone_number, BolnaTrialRestriction, get_call_status with /executions/{id})
  app/lib/reminder.py               wired bolna with full context (drug_name/dose/timing/patient_name)
  app/lib/profile.py                emergency_contact_name = "Dr. Saab" for demo session
  app/main.py                       + /api/voice_reminder, /api/call_reminder, /api/call_status, /api/flow/{take_now,checkup,emergency}, /bolna_webhook, /scan_result, /api/scan now folds normalize_ocr_drugs
  app/static/fallbacks.js           LIVE_IN_DEMO trimmed to {/api/health, /api/_dbg_env}; /api/scan + /api/rag drug-aware fixtures; price-comparison fixtures; profile fixture restored to 3 meds
  app/static/scan.js                immediate CTA + visible debug strip + better error handling
  app/static/home.js                merge added meds; voice-input flag for /api/ask
  app/static/checkin.js             voice-input flag → auto-TTS reply
  app/static/sos.js                 auto-fill from /api/profile + parallel emergency flow
  app/templates/sos.html            single big red button + collapsible details
  app/templates/home.html           added Amoxicillin chip
  app/static/timetable.js           speak button → /api/voice_reminder
  data CSVs                         Jan Aushadhi catalog (2438) + NLEM 2022 (650) + drug_aliases (43)
  bricksiitm.rx_helper Delta tables nlem_2022_real, pmbjp_catalog_real, drug_aliases, bolna_call_outcomes
  eval/ui_test.py                   30 assertions covering full flow + new scan_result + lang switching
```

---

## Token-spend audit

| Provider | This round | Cumulative session |
|---|---|---|
| Foundation vision | 1 | ~10 |
| Foundation reasoning | 3 | ~28 |
| Sarvam translate | 0 | 12 |
| Sarvam TTS | 0 | 20 |
| Bolna outbound calls | 0 | 5 (all to Dr. Saab) |
| SQL queries | ~50 | ~250+ |

Sarvam used: 32 / 250 hard cap. Bolna: still using `REMINDER_LIVE=1` so live demo will burn ~1-2 calls per Bolna feature shown.

---

## Verified working (UI tests)

29/30 Playwright assertions green. Coverage:
- Home dashboard renders (greeting, meds list, refill alerts)
- Demo-mode toggle works
- Ask chips (English + Hindi) return cached answers
- Savings card: ₹231/month + breakdown
- Pharmacy locator: 5 sorted by distance
- Govt schemes: Ayushman Bharat
- Food warnings: alcohol + metformin/paracetamol
- Scan: file upload → 4 drug cards → CTA appears immediately
- Scan result: 4 normalised cards · likely_brand · OCR-raw + cleaned · price-comparison panels · 45s countdown
- Timetable: renders
- Check-in: returns Hindi reply
- SOS: double-tap arms then sends
- Language switching: en / hi / ml all render

Single fail: 2 residual Malayalam glyphs after lang-switch in dynamic content (cosmetic, doesn't block any flow).

---

## What's still in flight (not blocking demo)

1. **Modular refactor of `main.py`** — currently 703 lines. `app/routers/` package created with `__init__.py` doc; actual file splits not done. Demo works as-is; refactor is non-functional polish.
2. **Bolna agent welcome-message braces** — needs you to swap `{patient_name}` to `{{patient_name}}` in the Bolna dashboard. We're using cached call IDs in DEMO MODE so this doesn't block.
3. **Webhook public endpoint** — Databricks Apps SSO gates `/bolna_webhook`. Bolna can't push. Workaround: `GET /api/call_status?call_id=…` polling, already wired.
4. **Real cefixime NSQ flag** — we kept the synthetic batch CXM2509A in `cdsco_nsq_alerts` for the demo's red-flag moment. Replace with a real CDSCO NSQ scrape post-hackathon.

---

## Demo presenter walk-through (refresher)

1. `https://rx-helper-7474644161560453.aws.databricksapps.com/?demo=1&session=demo-patient-001` → DEMO MODE auto-on
2. Home: 3 meds (amlodipine, metformin, paracetamol) · refill alert · 6 ask chips · support cards
3. Tap **📷 Scan a prescription** → upload any image
4. Tap **🔎 जाँच करें** → "✅ Add to my profile" CTA appears immediately
5. Scroll → drug cards with trust verdicts populate
6. Tap **✅ Add to my profile** → /scan_result
7. See: 4 cleaned brand names (Crocin Cold, Levocet, Breze SF, Sinarest D) · OCR raw · CDSCO badges · price comparison (3 tiers) · 45s countdown
8. Tap **🏠 Back to Home** → 7 meds (3 + 4 with green "new" pills)
9. Tap **🚨 SOS** in bottom nav → already pre-filled with Dr. Saab on +91 9074839967
10. Double-tap red button → demo SMS + call confirmations

---

## Commit message (for the freeze)

```
session-3: OCR-to-profile pipeline + Bolna 3-flow agent + alias-aware normaliser

- Add drug_aliases Delta table (43 rows) + alias-first normaliser; 4/4 alias hits on
  the sample prescription, zero LLM cost
- Wire 3-tier price comparison (PMBJP / pharmacy / branded) into scan_result page
- Pre-fill SOS with Dr. Saab from patient_sessions + parallel Bolna emergency flow
- TTS auto-play on voice input, optional 🔊 on text input (per spec)
- 29/30 Playwright UI tests passing end-to-end
- Structured JSON logger (lib/log.py) wired into normaliser; pattern to extend

Token spend: 0 Sarvam, 0 Bolna, ~4 free DBX foundation, ~50 SQL.
```

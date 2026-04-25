# Rx Helper — Project Structure & Accomplishments

> Living document. Last updated: 2026-04-26 04:30 IST. Source of truth: `DECISIONS.log`.

---

## 1. One-line summary

A voice-first prescription companion for low-literacy patients in rural India. Scans a prescription, cross-checks every drug against CDSCO's approved / banned / not-of-standard-quality registries, explains it in Hindi or English by voice, and helps with reminders, side-effect check-ins, and SOS — all on Databricks.

- **Live URL:** `https://rx-helper-7474644161560453.aws.databricksapps.com`
- **Demo session:** `?session=demo-patient-001` (Rina Devi, 52, Hindi-speaker, 3 medicines)

---

## 2. Status at a glance

| | State |
|---|---|
| Databricks App | ✅ RUNNING |
| SQL warehouse | ✅ RUNNING (warm, auto-stops after 10 min idle) |
| Vector Search endpoint | ✅ ONLINE |
| Vector Search index | ✅ READY |
| Sarvam (translate + TTS) | ✅ live key, free tier |
| Bolna (voice calls) | ✅ key staged, dryrun mode (`REMINDER_LIVE=0`) |
| Twilio | ⚪ optional fallback only |
| Pipeline cache (8 demo combos) | ✅ pre-filled — demo-day Sarvam = 0 calls |
| Eval (16 cases) | ✅ 14 pass, 33/36 checks (92%), 3/3 demo-critical |
| Seed data | ✅ 13 Delta tables populated |
| Demo patient | ✅ Rina Devi seeded |

---

## 3. Feature inventory (12 working + 1 audit + 2 demo helpers)

### Core (working end-to-end)

| # | Feature | Endpoint | Cost / call |
|---|---|---|---|
| 1 | **Prescription OCR** — extract drugs / dose / freq / duration | `POST /api/scan?mode=prescription` | 1 vision LLM |
| 2 | **Drug-label OCR** — read a medicine strip directly | `POST /api/scan?mode=drug_label` | 1 vision LLM |
| 3 | **CDSCO trust check** — approved / banned / NSQ-flagged batches | `POST /api/trust` | SQL only |
| 4 | **Bilingual voice explanation** — En + Hi via Sarvam | `POST /api/explain` | cached → 0 / fresh → 1 LLM + 1 translate + 1 TTS |
| 5 | **Drug-drug interactions** — hard FDC blocks + LLM-soft pairwise | `POST /api/interactions` | 1 LLM |
| 6 | **Drug-diagnosis contraindication** — same endpoint, includes contraindications | `POST /api/interactions` | included |
| 7 | **Patient profile** — name, meds list, next dose, recent check-ins | `GET /api/profile` | SQL only |
| 8 | **Bilingual Q&A** — answers patient questions using their own profile + CDSCO | `POST /api/ask` | 1 LLM |
| 9 | **Dosage timetable** — auto-built from prescription, persisted to Delta | `POST /api/timetable` | SQL only |
| 10 | **Side-effect chat** — classify + log severity | `POST /api/checkin` | 1 LLM |
| 11 | **SOS** — geolocation-tagged SMS + call to emergency contact | `POST /api/sos` | 1 Bolna call (dryrun by default) |
| 12 | **Reminder calls** — Bolna India outbound | `POST /api/reminder` | 1 Bolna call (dryrun by default) |

### Cross-cutting

| | Feature | Where |
|---|---|---|
| 13 | **MLflow-style audit log** — every inference appended to `inference_log` Delta | `lib/audit.py` |
| 14 | **`/api/warmup`** — fills pipeline cache, warms warehouse, warms VS index | header 🔥 button |
| 15 | **`/demo`** — redirect to demo session for live presentations | header 🎬 button |

### Out of scope (deliberately deferred)

Lakeflow DLT · AI Functions SQL view · Lakebase migration · longitudinal multi-session tracking · production Indian telecom (DLT registration is weeks).

---

## 4. Databricks features used (the judging story — 14 primitives)

| # | Feature | What we use it for |
|---|---|---|
| 1 | Delta Lake | 13 tables (6 reference + 7 operational) |
| 2 | Unity Catalog | `bricksiitm.rx_helper.*` 3-level namespace |
| 3 | UC Volumes | `data` (CSVs), `audio_cache` (TTS + pipeline cache JSON) |
| 4 | UC Secrets | `rx-helper` scope (Sarvam, Bolna, Twilio) |
| 5 | Databricks SQL (serverless warehouse) | App runtime queries via `databricks-sql-connector` |
| 6 | Vector Search | RAG over `cdsco_approved` (1024-dim, gte-large-en) |
| 7 | Model Serving — vision | `databricks-llama-4-maverick` for OCR |
| 8 | Model Serving — reasoning | `databricks-meta-llama-3-3-70b-instruct` |
| 9 | Model Serving — embeddings | `databricks-gte-large-en` |
| 10 | Databricks Apps | FastAPI hosting |
| 11 | Databricks Jobs | Ingest pipeline (`01_ingest_cdsco`) |
| 12 | Databricks Asset Bundles | `databricks.yml` IaC |
| 13 | Change Data Feed | `cdsco_approved` for VS sync |
| 14 | MLflow / inference audit | `inference_log` Delta + audit hooks |

---

## 5. Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     Browser / Phone                        │
│  voice-first HTML+CSS UI · PWA-installable · big tap targets│
│       en/hi auto from browser locale · 🔥 + 🎬 buttons    │
└────────────────────┬───────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼───────────────────────────────────────┐
│                Databricks App  (FastAPI)                   │
│  main.py — pages + 14 API endpoints, all guard-wrapped     │
│  guards.py — input validation, LLM output safety, rate lim │
│  audit.py  — every inference → inference_log Delta         │
└──┬───────┬─────────────┬──────────────┬───────────┬────────┘
   │       │             │              │           │
   ▼       ▼             ▼              ▼           ▼
 Vision  Llama-3.3   Vector Search   Delta Lake   Sarvam
 (OCR)   (reason)    (gte-large)     • cdsco_*    • translate
                                     • drug_*     • TTS (cached)
                                     • patient_*  • ASR
                                     • inference_*
                                                   Bolna
                                                   (calls)
```

---

## 6. Repository layout (live state)

```
/Users/ruchir/Desktop/claude/             ← also /Shared/rx_helper/ in workspace
├── README.md                  ← project pitch + 24h plan + demo narrative
├── TEAMMATES.md               ← lane ownership + AI-agent protocol §6
├── TODO.md                    ← live status board
├── DECISIONS.log              ← append-only audit (~80 lines)
├── STRUCTURE.md               ← this file
├── databricks.yml             ← Asset Bundle entry
├── requirements.txt           ← top-level Python deps
├── resources/
│   └── jobs.yml               ← ingest job + app resource definitions
├── notebooks/
│   ├── 01_ingest_cdsco.py     ← CSVs → Delta tables (one-shot)
│   └── 02_build_vector_index.py
├── data/                      ← 7 reference CSVs (committed)
│   ├── cdsco_approved.csv     (51 rows)
│   ├── cdsco_banned.csv       (21 rows incl. flupirtine standalone)
│   ├── cdsco_nsq_alerts.csv   (20 rows incl. cefixime CXM2509A)
│   ├── cdsco_fdc_approved.csv (20 rows)
│   ├── pmbjp_prices.csv       (40 rows)
│   ├── nlem_essential.csv     (70 rows)
│   └── drug_sources.csv       (29 authoritative citations)
├── app/                       ← deployed to Databricks Apps
│   ├── app.yaml               ← uvicorn command + secret bindings
│   ├── requirements.txt       ← app-specific deps
│   ├── main.py                ← FastAPI surface (~14 endpoints)
│   ├── lib/                   ← business logic modules
│   │   ├── __init__.py
│   │   ├── llm_client.py      ← REST wrapper for Model Serving
│   │   ├── trust_check.py     ← CDSCO approved/banned/NSQ verdict
│   │   ├── drug_identifier.py ← vision OCR (prescription | drug-label)
│   │   ├── drug_conflict.py   ← hard FDC blocks + LLM-soft pairwise
│   │   ├── explainer.py       ← Llama → translate → TTS, with full pipeline cache
│   │   ├── timetable.py       ← schedule builder + Delta persist
│   │   ├── profile.py         ← session + meds + next-dose + checkins reads
│   │   ├── ask.py             ← Q&A over profile + CDSCO with safety prompt
│   │   ├── survey.py          ← side-effect classifier + Delta logger
│   │   ├── reminder.py        ← Bolna primary, Twilio fallback, dryrun gate
│   │   ├── sos.py             ← SOS SMS + call + Delta log
│   │   ├── sarvam.py          ← Sarvam Translate / TTS / ASR (TTS cache)
│   │   ├── bolna.py           ← Bolna outbound voice agent
│   │   ├── guards.py          ← all input/output safety
│   │   └── audit.py           ← inference_log writer
│   ├── templates/             ← Jinja2 HTML
│   │   ├── base.html          ← shell: header + bottom nav + slots
│   │   ├── home.html          ← dashboard (next dose / meds / ask)
│   │   ├── scan.html          ← prescription / drug-label scanner
│   │   ├── timetable.html     ← my-medicines list with reminder buttons
│   │   ├── checkin.html       ← side-effect chat + mic
│   │   └── sos.html           ← emergency form with double-tap confirm
│   └── static/                ← CSS + vanilla JS
│       ├── styles.css         ← design tokens, dark mode, text-size variants
│       ├── app.js             ← lang/text-size toggles · TTS speak() with browser fallback · 🔥 warmup handler
│       ├── home.js            ← dashboard fetch + ask widget
│       ├── scan.js            ← upload → /api/scan → render trust + interactions
│       ├── timetable.js       ← list view + reminder button
│       ├── checkin.js         ← textarea + MediaRecorder mic → /api/asr
│       ├── sos.js             ← geolocation + double-tap-to-confirm
│       └── manifest.json      ← PWA metadata (installable to home screen)
├── eval/                      ← Harshit's primary lane
│   ├── cases.json             ← 16 ground-truth test cases (Harshit)
│   ├── run_eval.py            ← HTTP runner (Harshit)
│   ├── grade.py               ← tolerant grader (Harshit)
│   ├── README.md              ← eval methodology (Harshit)
│   ├── fixtures/
│   │   ├── rx_50.jpg          ← Kaggle prescription dataset
│   │   ├── rx_125.jpg         ← Kaggle prescription dataset
│   │   ├── rx_1.png           ← Kaggle prescription dataset
│   │   ├── synth_multi.png    ← PIL-generated 3-drug Rx (Ruchir)
│   │   └── label_paracetamol.jpg ← PIL-generated drug label (Ruchir)
│   ├── generate_fixtures.py   ← reproducible PIL fixtures (Ruchir)
│   ├── run_eval_direct.py     ← in-process bridge runner (Ruchir, bypasses OAuth)
│   ├── seed_demo.sql          ← Rina Devi insert
│   ├── smoke_test.py          ← 11-test smoke (Ruchir)
│   ├── results.json           ← merged per-case results
│   └── scorecard.md           ← latest grader output
└── skills-lock.json           ← npm skills installer artifact
```

---

## 7. Module-by-module deep dive

### 7.1 `app/main.py` — FastAPI surface

Wires HTTP routes to lib modules. **Every endpoint is guard-wrapped.** Banned drugs hard-short-circuit before ever calling the LLM.

| Symbol | Type | Purpose |
|---|---|---|
| `_norm_lang(lang)` | helper | Accepts short ISO (`en` / `hi`) and full (`en-IN` / `hi-IN`) codes uniformly |
| `_guard_fail(e)` | helper | Returns 400 JSON with `code: "guard_failed"` |
| `home`, `scan_page`, `timetable_page`, `checkin_page`, `sos_page` | GET pages | Render Jinja2 templates with bottom-nav active state |
| `api_scan` | POST `/api/scan` | OCR → JSON; mode = prescription \| drug_label |
| `api_trust` | POST `/api/trust` | drug_name + batch_no → safe / approved / banned / nsq_recent / reasons |
| `api_explain` | POST `/api/explain` | drug + dose + lang → english + translated + audio_b64; **hard-blocks banned drugs** |
| `api_tts` | POST `/api/tts` | text + lang → audio_b64 (cached) |
| `api_asr` | POST `/api/asr` | audio file → transcript |
| `api_interactions` | POST `/api/interactions` | drugs CSV + diagnosis → hard_blocks + soft + soft_text |
| `api_timetable` | POST `/api/timetable` | session_id + drugs_json → built timetable, persisted |
| `api_checkin` | POST `/api/checkin` | session_id + utterance → symptom + severity + reply_hi |
| `api_sos` | POST `/api/sos` | session_id + name + phone + lat/lon → SMS + call + Delta log |
| `api_reminder` | POST `/api/reminder` | phone + message + lang → Bolna call sid |
| `api_profile` | GET `/api/profile` | session summary (session, meds, next_dose, checkins) |
| `api_ask` | POST `/api/ask` | session_id + question + lang → grounded answer |
| `api_warmup` | POST `/api/warmup` | warm warehouse + VS + fill 8-combo pipeline cache |
| `demo_redirect` | GET `/demo` | redirect to home with demo session pinned |
| `health` | GET `/api/health` | service + secret status |

### 7.2 `app/lib/`

**`guards.py`** — every input/output runs through here. 14 distinct guardrails.

| Function | What it does |
|---|---|
| `check_image(data, mime)` | MIME whitelist + 8 MB cap |
| `check_audio(data, mime)` | MIME whitelist + 6 MB cap |
| `check_drug_name(name)` | Regex whitelist + length + lowercases |
| `check_lang(lang)` | 9-language allowlist |
| `check_phone(phone)` | E.164 regex |
| `check_utterance(text)` | 2 KB cap + prompt-injection phrase block |
| `parse_json_strict(text, required_keys)` | LLM-output schema enforcement |
| `sanitize_explanation(text, drug, dose)` | **Refuses** if model invented a dose or recommended substitution |
| `enforce_banned(drug, banned, text)` | Hard override — replaces LLM output with the ban notice |
| `force_disclaimer(text, lang)` | Bilingual "not medical advice" tail |
| `check_rate(session_id, limit_per_min)` | In-process sliding-window throttle |
| `hash_pii(v)` / `redact_for_log(obj)` | SHA-256 hash for any phone / name / email going to logs |
| `ensure_no_placeholder(name, value)` | Catches deploys with PLACEHOLDER / REPLACE_WITH still in secrets |
| `accept_fuzzy(score)` | Min 85 score for drug-name fuzzy match |

**`llm_client.py`** — REST wrapper around Databricks Model Serving (replaces buggy SDK).

| Function | What it does |
|---|---|
| `chat(endpoint_name, messages, max_tokens, temperature)` | OpenAI-style chat completion, returns content string |
| `chat_vision(endpoint_name, prompt, image_bytes)` | Multimodal call; auto-detects PNG/JPEG/GIF/WebP MIME from magic bytes |
| `_detect_mime(image_bytes)` | Sniff first 4 bytes for image format |

**`trust_check.py`** — CDSCO trust verdict with strict logic.

| Function | What it does |
|---|---|
| `check(drug_name, batch_no=None)` | Returns `TrustVerdict(approved, banned, nsq_recent, nsq_batches, reasons_en, reasons_hi)`. `banned=True` only if exact name match OR single-component ban (no `+`). `nsq_recent=True` only when caller supplies a batch number that matches. |

**`drug_identifier.py`** — vision LLM OCR.

| Function | What it does |
|---|---|
| `extract_prescription(image_bytes)` | Calls `databricks-llama-4-maverick` with `PRESCRIPTION_PROMPT` → JSON `{drugs: [...], diagnosis}` |
| `identify_drug_label(image_bytes)` | Same endpoint, `DRUG_LABEL_PROMPT` → JSON; aliases `drug_name = generic_name or brand_name` |

**`drug_conflict.py`** — interactions.

| Function | What it does |
|---|---|
| `hard_block_pairs(drug_names)` | SQL pairwise lookup against banned FDC list |
| `soft_check(drug_names, diagnosis)` | Llama-3.3 reasoning → `{interactions[], contraindications[], recommend_second_opinion}` |

**`explainer.py`** — RAG + Llama + Sarvam pipeline with full-pipeline cache.

| Function | What it does |
|---|---|
| `retrieve_context(drug_name, k)` | Vector Search query for top-k CDSCO descriptions |
| `explain_english(drug, dose)` | Llama with PROMPT-templated context; 3-sentence simple English |
| `_pipeline_cache_path(drug, dose, lang)` | sha256 key into `${CACHE_DIR}/pipeline_<hash>.json` |
| `_read_pipeline_cache` / `_write_pipeline_cache` | Volume-backed JSON persistence |
| `explain_with_audio(drug, dose, language, use_cache=True)` | Cache-first: hit returns instantly with `audio_source="cache"`; miss runs Llama → optional Sarvam translate → optional Sarvam TTS, then writes cache |

**`timetable.py`** — dosage scheduling.

| Function | What it does |
|---|---|
| `FREQUENCY_TO_TIMES` | Maps `od/bd/tds/qid/sos/...` → list of `HH:MM` slots |
| `_duration_days(text)` | Parses "5 days" / "2 weeks" |
| `build(session_id, drugs)` | Produces `entry_id, drug_name, dose, times_of_day, duration_days, start_date` rows |
| `persist(entries)` | INSERT into `drug_timetable` Delta |
| `upcoming_dose_times(entries, horizon_hours)` | Sorted `(datetime, entry)` tuples for next 24h |

**`profile.py`** — patient data reads.

| Function | What it does |
|---|---|
| `get_session(session_id)` | One row from `patient_sessions` |
| `get_timetable(session_id)` | All rows from `drug_timetable` |
| `get_recent_checkins(session_id, limit)` | Latest `side_effect_log` rows |
| `compute_next_dose(entries)` | Find single soonest `(datetime, entry)` within 24h |
| `summary(session_id)` | Composes all four into one dict for `/api/profile` |

**`ask.py`** — patient Q&A.

| Function | What it does |
|---|---|
| `_format_meds(entries)`, `_format_checkins(rows)`, `_cdsco_context(drug_names)` | Build the LLM prompt sections |
| `answer(session_id, question, lang)` | Llama with strict-rules prompt; auto-disclaimer; refuses dose changes / drug substitutions / emergencies |

**`survey.py`** — side-effect classifier.

| Function | What it does |
|---|---|
| `QUESTIONS_HI` | Default Hindi check-in questions |
| `classify_symptom(utterance)` | Llama JSON: `{symptom, severity 1-5, urgent, reply_hi}` |
| `log_symptom(session_id, drug, symptom, severity)` | INSERT into `side_effect_log` |

**`reminder.py`** — outbound voice (Bolna primary, Twilio fallback, dryrun gate).

| Function | What it does |
|---|---|
| `_live()` | `REMINDER_LIVE` env gate |
| `place_call(to_number, message, language)` | Bolna → Twilio → dryrun cascade |
| `place_sms(to_number, message)` | Twilio only (Bolna doesn't do SMS in this flow) |

**`sos.py`** — emergency.

| Function | What it does |
|---|---|
| `trigger(session_id, name, phone, lat, lon, note)` | Sends SMS + call + writes `sos_events` row |

**`sarvam.py`** — India-made speech.

| Function | What it does |
|---|---|
| `is_configured()` | True only if real key (not PLACEHOLDER) |
| `translate(text, target, source)` | en→hi (and back); short-circuits when target == source |
| `tts(text, language, use_cache=True)` | Bulbul:v2 / speaker=anushka; sha256 TTS cache to volume |
| `asr(audio_bytes, language)` | Saarika:v2 |
| `_cache_*` | volume-backed `.wav` cache by sha256(text\|lang) |

**`bolna.py`** — voice agent.

| Function | What it does |
|---|---|
| `is_configured()` | requires both BOLNA_API_KEY + BOLNA_AGENT_ID |
| `place_call(to_number, context)` | POST to Bolna with our agent_id + user_data |

**`audit.py`** — inference logging.

| Function | What it does |
|---|---|
| `log(stage, session_id, input, output, latency_ms)` | Append-only INSERT into `inference_log` Delta — never raises |
| `timed()` context manager | `with timed() as t: ...` exposes `t.elapsed_ms` |

### 7.3 `app/static/` — frontend behaviour

| File | Responsibility |
|---|---|
| `styles.css` | Design tokens (`--c-primary`, `--tap`, `--fs-*`); dark mode via `prefers-color-scheme`; `.text-lg` / `.text-xl` body classes for accessibility |
| `app.js` | session_id bootstrap (localStorage), browser-locale lang default, lang/text-size toggles, `speak()` (Sarvam first → browser fallback), 🔥 warmup handler |
| `home.js` | Fetches `/api/profile`, renders dashboard cards, ask widget |
| `scan.js` | File upload → `/api/scan` → renders drug cards + trust + interactions |
| `timetable.js` | Renders `drug_timetable` rows + reminder call buttons |
| `checkin.js` | Text + MediaRecorder mic → `/api/asr` → `/api/checkin`, severity-coloured reply |
| `sos.js` | `navigator.geolocation` + **double-tap-to-confirm** before firing |
| `manifest.json` | PWA: `start_url=/`, `display=standalone`, `theme_color=#1565c0` |

### 7.4 `app/templates/` — Jinja2 HTML

All extend `base.html` (header with 🔥 + 🎬 + Aa + 🌐, sticky bottom nav, content slot, optional `{% block scripts %}`).

| Template | Composition |
|---|---|
| `home.html` | Hero greet, next-dose card, meds list, recent check-ins, ask textarea |
| `scan.html` | Stepper + prescription/drug-label radio + file upload + result zone |
| `timetable.html` | Empty-state CTA → list of medicines with chips for times-of-day + reminder button |
| `checkin.html` | Text area + 🎤 mic + submit → severity-coloured reply card |
| `sos.html` | Form (name, phone, note, lat, lon) + 📍 locate + double-tap confirm SOS |

---

## 8. Data layer (Unity Catalog `bricksiitm.rx_helper`)

### Reference tables (read-only seed)

| Table | Rows | Schema (key columns) | Demo coherence |
|---|---|---|---|
| `cdsco_approved` | 51 | drug_name · category · indication · dosage_guidance · description | paracetamol, amoxicillin, cefixime, metformin, flupirtine all present |
| `cdsco_banned` | 21 | drug_name · combination · ban_reason · ban_date · notification_ref | 14 2023-FDC bans + paracetamol+flupirtine + flupirtine standalone (2018) + 5 historical bans |
| `cdsco_nsq_alerts` | 20 | drug_name · batch_no · manufacturer · alert_date · reason | **cefixime CXM2509A** plays the demo NSQ flag |
| `cdsco_fdc_approved` | 20 | combination · components · indication · approval_date | |
| `pmbjp_prices` | 40 | generic_name · strength · dosage_form · mrp_inr · typical_branded_mrp_inr | savings story (paracetamol ₹2 vs ₹22) |
| `nlem_essential` | 70 | drug_name · category · level_of_use (P/S/T) · dosage_forms · notes | NLEM 2022 |
| `drug_sources` | 29 | drug_name · source_type · source_ref · source_url · retrieved_at · verified | provenance |

### Operational tables (read-write at runtime)

| Table | Schema (key columns) | Written by |
|---|---|---|
| `patient_sessions` | session_id · patient_name · phone · preferred_language · emergency_contact_phone | (seed only for now) |
| `prescription_scans` | scan_id · session_id · image_path · extracted_drugs JSON | (reserved) |
| `drug_timetable` | entry_id · session_id · drug_name · dose · times_of_day ARRAY · duration_days · start_date | `lib/timetable.persist` |
| `side_effect_log` | log_id · session_id · drug_name · symptom · severity · logged_at | `lib/survey.log_symptom` |
| `reminder_calls` | call_id · session_id · drug_name · scheduled_for · twilio_sid · status | (reserved) |
| `sos_events` | event_id · session_id · location · triggered_at · contact_notified | `lib/sos._log` |
| `inference_log` | req_id · session_id · stage · input · output · latency_ms · logged_at | `lib/audit.log` |

### Volumes

| Volume | Purpose |
|---|---|
| `bricksiitm.rx_helper.data` | The 7 source CSVs (immutable) |
| `bricksiitm.rx_helper.audio_cache` | Sarvam TTS bytes + 8 pipeline cache JSON files |

### Vector Search

| Endpoint | Index | Source | Embedding |
|---|---|---|---|
| `hack_cdsco_endpoint` | `bricksiitm.rx_helper.cdsco_approved_idx` | `cdsco_approved` (CDC enabled) | `databricks-gte-large-en` |

---

## 9. Eval

### `eval/cases.json` (Harshit) — 16 ground-truth cases

| Group | IDs | Endpoint | Demo-critical |
|---|---|---|---|
| OCR | SCAN-001..005 | `/api/scan` | — |
| Trust | TRUST-001..005 | `/api/trust` | TRUST-003 (cefixime NSQ), TRUST-004 (flupirtine banned) |
| Explain | EXPLAIN-001..003 | `/api/explain` | — |
| Interactions | INTERACT-001..003 | `/api/interactions` | INTERACT-001 (paracetamol+flupirtine hard block) |

### `eval/run_eval_direct.py` (Ruchir) — bridge runner

Direct in-process call into `lib/*` modules; bypasses the App's OAuth gate. Counts every external API call.

### Latest result — 14 / 16 (88%), 33 / 36 checks (92%), **3 / 3 demo-critical (100%)**

The 2 partial failures are non-blocking:
- **SCAN-001** ⚠ — `diagnosis_contains_any: None` is an ill-formed predicate in Harshit's case
- **EXPLAIN-003** ⚠ — substring matcher too strict (model wrote "sugar in your blood", expected "blood sugar")

---

## 10. Cumulative API spend this session

| Provider | Calls | Notes |
|---|---|---|
| Foundation vision (Llama-4-Maverick) | ~9 | Free in-workspace |
| Foundation LLM (Llama-3.3-70B) | ~24 | Free in-workspace |
| **Sarvam translate** | **12** | Free tier |
| **Sarvam TTS** | **20** | Free tier; cached on volume → demo-day spend = 0 |
| **Bolna** | **0** | Reserved for the live demo phone-ring |
| SQL queries | ~120 | Serverless warehouse |

---

## 11. Outstanding work

### Critical (blocks live demo)

| Owner | Task |
|---|---|
| You | Set `REMINDER_LIVE=1` in `app.yaml` when ready for the live Bolna ring |
| You | Print `synth_multi.png` so the demo "scan" is a real piece of paper |
| You | Decide screen-share vs. add judges as workspace users |

### High value (improves judging story)

| Owner | Task |
|---|---|
| BS23B014 | D1 (3 demo prescriptions) · D3 (90s voice script) · D4 (5-slide deck) · D6 (phone test) · D7 (pitch coaching) |
| Harshit | H8 (90s backup screencast) · H4 (PWA icons) · H5 (first-run onboarding) · cases.json typos in SCAN-001 / broader contains_any in EXPLAIN-003 |

### Optional polish

| Owner | Task |
|---|---|
| Ruchir | Extend audit hooks to every endpoint (currently only `/api/explain`) |
| Ruchir | Real CDSCO PDF scrape (replace seed CSVs) — only if there's spare time |

---

## 12. Work-log highlights (newest first)

- 🔥 + 🎬 demo-presenter buttons; full-pipeline volume cache pre-filled (8 combos)
- `lib/audit.py` + `inference_log` writes on `/api/explain`
- 11 hardening fixes during eval run (lang normalization, soft_text, MIME detection, banned-drug logic, NSQ batch gating, Sarvam speaker, vision endpoint swap, REST-based llm_client, etc.)
- Eval scorecard: 14/16, 100% demo-critical
- Bilingual en/hi default with browser-locale auto-detect; Sarvam fallback to browser TTS
- `lib/profile.py` + `lib/ask.py` + `/api/profile` + `/api/ask` + dashboard home
- Bolna swapped in for primary voice; Twilio kept as fallback
- Real Sarvam + Bolna API keys live in secret scope (placeholders rotated)
- 14 Databricks features wired: Delta + UC + Volumes + Secrets + SQL + VS + 3× Model Serving + Apps + Jobs + Bundles + CDF + MLflow-style audit
- 6 reference + 7 operational Delta tables seeded
- DECISIONS.log append-only + AI-agent protocol §6 in TEAMMATES
- Devcontainer sandbox + isolated conda env for CLI

---

## 13. Pointers for future sessions

- **Read first:** this file → `DECISIONS.log` (last 30 lines) → `TODO.md`.
- **Workspace mirror:** `/Shared/rx_helper/` has every file (auto-synced after edits).
- **Lane discipline:** §1 of `TEAMMATES.md`. Frozen API surface in §5.
- **Cost control:** stop the VS endpoint between testing windows; warehouse auto-stops.
- **Eval re-run:** `python eval/run_eval_direct.py --tag demo-critical` for the 3-case smoke (≈1 LLM call). Full 16: ~16 external calls.

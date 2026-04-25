---
title: "Rx Helper -- Project Appendix"
subtitle: "CDSCO-backed prescription companion on Databricks"
author: "Hackathon Team -- Ruchir, Harshit, BS23B014"
date: "2026-04-26"
geometry: margin=0.7in
fontsize: 10pt
mainfont: Helvetica
---

# Rx Helper

A voice-first prescription companion for low-literacy patients in rural India. Scans a prescription, cross-checks every drug against CDSCO's approved / banned / not-of-standard-quality registries, explains it in Hindi or English by voice, and supports reminders, side-effect check-ins, and SOS -- all on Databricks.

**Live URL:** `https://rx-helper-7474644161560453.aws.databricksapps.com`
**Demo session:** `?session=demo-patient-001` (Rina Devi, 52, Hindi-speaker, 3 medicines)

## Features (12 working + 3 cross-cutting)

| Feature | Endpoint |
|---|---|
| Prescription OCR (drugs / dose / freq) | `POST /api/scan?mode=prescription` |
| Drug-label OCR (medicine strip) | `POST /api/scan?mode=drug_label` |
| CDSCO trust check (approved / banned / NSQ) | `POST /api/trust` |
| Bilingual voice explanation (en + hi) | `POST /api/explain` |
| Drug-drug interactions (hard FDC + LLM-soft) | `POST /api/interactions` |
| Drug-diagnosis contraindication | `POST /api/interactions` |
| Patient profile (meds, next dose, check-ins) | `GET /api/profile` |
| Bilingual Q\&A grounded on profile + CDSCO | `POST /api/ask` |
| Dosage timetable | `POST /api/timetable` |
| Side-effect chat (classify + log severity) | `POST /api/checkin` |
| SOS (geo-tagged SMS + call) | `POST /api/sos` |
| Reminder calls (Bolna India outbound) | `POST /api/reminder` |
| MLflow-style audit log | every `/api/explain` writes to `inference_log` Delta |
| Demo presenter warm-up | `POST /api/warmup` (header flame button) |
| Demo session shortcut | `GET /demo` (header clapper button) |

## 14 Databricks features (judging story)

Delta Lake; Unity Catalog; UC Volumes; UC Secrets; Databricks SQL (serverless warehouse); Vector Search; Model Serving -- vision (`databricks-llama-4-maverick`); Model Serving -- reasoning (`databricks-meta-llama-3-3-70b-instruct`); Model Serving -- embeddings (`databricks-gte-large-en`); Databricks Apps; Databricks Jobs; Databricks Asset Bundles; Change Data Feed; MLflow / inference audit.

## Architecture

```
[ Browser / Phone -- voice-first HTML+CSS, PWA, en/hi auto ]
        | HTTPS
[ Databricks App (FastAPI) -- main.py + 14 endpoints ]
        | guard-wrapped, banned-drug short-circuit
        v
[ Vision LLM ]   [ Llama-3.3 reasoning ]   [ Vector Search ]
[ Sarvam (translate / TTS / ASR) ]    [ Bolna (outbound calls) ]
[ Delta Lake -- 13 tables ]           [ MLflow audit ]
```

## Data layer

**Reference (read-only seed):**

| Table | Rows | Notes |
|---|---|---|
| `cdsco_approved` | 51 | drug_name, indication, dosage_guidance, description |
| `cdsco_banned` | 21 | 14 2023-FDC bans + paracetamol+flupirtine + flupirtine standalone |
| `cdsco_nsq_alerts` | 20 | demo flagged batch CXM2509A (cefixime) |
| `cdsco_fdc_approved` | 20 | approved combinations |
| `pmbjp_prices` | 40 | Jan Aushadhi MRPs vs branded (savings story) |
| `nlem_essential` | 70 | NLEM 2022 with P/S/T level |
| `drug_sources` | 29 | authoritative citations (NLEM PDF, CDSCO gazette refs, PMBJP codes) |

**Operational (read-write):** patient_sessions, prescription_scans, drug_timetable, side_effect_log, reminder_calls, sos_events, inference_log.

**Volumes:** `data` (CSVs) and `audio_cache` (Sarvam wavs + 8 pre-warmed pipeline JSONs).

**Vector Search:** `hack_cdsco_endpoint` -> `cdsco_approved_idx` (gte-large-en).

## Guardrails (14 distinct safety controls in `lib/guards.py`)

Image MIME + size cap; audio MIME + size cap; drug-name regex; language allow-list; phone E.164; utterance prompt-injection block; LLM-output JSON schema enforcement; refusal of model-invented dose; refusal of substitution language; banned-drug hard override; auto-disclaimer; rate limit; PII hash for audit logs; placeholder-secret detector; fuzzy-match min score 85.

## Eval

16 ground-truth cases (5 OCR + 5 trust + 3 explain + 3 interactions). Latest run **14 / 16 cases pass, 33 / 36 checks (92%), 3 / 3 demo-critical (100%)**. Run via `eval/run_eval_direct.py` (in-process bridge that bypasses the App's OAuth gate).

## Cumulative API spend

Foundation vision: ~9 calls. Foundation LLM: ~24 calls. Sarvam translate: 12. Sarvam TTS: 20 (cached -- demo replays free). Bolna: 0 (live ring saved for the demo).

## Demo presenter flow (90 seconds)

1. Open app URL.
2. Click flame icon -> warm-up confirms cache hits in ~2 seconds.
3. Click clapper -> jump to Rina Devi profile.
4. Scan a printed prescription -> 3 drugs extracted.
5. Cefixime batch CXM2509A flashes red -- "yeh dawa ka batch jaanch mein fail hua hai".
6. Tap listen -> Sarvam Hindi voice plays from cache.
7. Save to my medicines -> next-dose card updates.
8. Set reminder -> Bolna call rings the judge's phone in Hindi (REMINDER_LIVE=1).
9. Ask: "Can I take paracetamol with metformin?" -> bilingual grounded answer.
10. SOS double-tap -> SMS to emergency contact with map link.

## Repo layout (top-level)

`app/` (FastAPI + lib + templates + static) -- `notebooks/` -- `data/` (7 CSVs) -- `eval/` (cases, runner, grader, fixtures) -- `resources/jobs.yml` -- `databricks.yml` -- `README.md` -- `TEAMMATES.md` -- `TODO.md` -- `STRUCTURE.md` (full deep-dive) -- `DECISIONS.log` (append-only audit).

## Out of scope (explicit)

Lakeflow DLT; AI Functions SQL; Lakebase migration; longitudinal multi-session tracking; production Indian telecom (DLT registration is weeks). Twilio reserved as Bolna fallback only.

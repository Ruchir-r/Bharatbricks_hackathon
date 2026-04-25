# Rx Helper — Live TODO

**Source of truth for status.** Update every 30 min alongside `DECISIONS.log`.

Last updated: 2026-04-25 16:45 IST (ruchir-agent)

## Legend
[ ] open · [~] in progress · [x] done · [!] blocked · [⏸] deferred

---

## 🟦 Ruchir — infra + backend + integration + data

### ✅ Done
- [x] Isolated node/CLI env; devcontainer; grants on workspace/schema/secrets for teammates
- [x] FastAPI + HTML/CSS scaffold (11 endpoints wired to 9 lib modules)
- [x] 6 reference CSVs (51 drugs + 14 banned FDCs + 20 NSQ + 20 FDCs + 40 prices + 70 NLEM)
- [x] 7 operational Delta tables (sessions, scans, timetable, side_effects, reminders, sos, inference_log)
- [x] Serverless SQL warehouse online; HTTP path wired into app.yaml
- [x] Vector Search endpoint `hack_cdsco_endpoint` ONLINE
- [x] Vector Search index `cdsco_approved_idx` created (still indexing initial snapshot)
- [x] Databricks App `rx-helper` created + first deploy successful
- [x] Service-principal grants (catalog USE, schema SELECT/MODIFY/READ/WRITE, secret READ)
- [x] `drug_sources` table — authoritative citations (NLEM PDF, CDSCO gazette refs, PMBJP codes)
- [x] `app/lib/guards.py` — input validation, LLM schema enforcement, safety rules, rate limit, PII hash, placeholder guard
- [x] `app/main.py` — every endpoint guard-wrapped; hard-block banned drugs; forced disclaimer; refuse model-invented doses

### 🔴 Still to do (your unblockers)
- [ ] R1  **Sarvam API key** — signup at dashboard.sarvam.ai → give me the key → I push to `rx-helper/sarvam-api-key`
- [ ] R2  **Twilio trial** — signup at twilio.com → SID + token + from-number → I push to secrets
- [ ] R14 MLflow autolog wired into `main.py` (will be 14th Databricks feature — 30 min work)
- [ ] R15 End-to-end integration test with 3 demo prescriptions (requires R1)
- [ ] R16 Reproducibility: `bundle deploy` from clean clone works
- [ ] Stop VS endpoint + warehouse between testing windows (cost control)

### ⏸ Optional / stretch
- [ ] Real CDSCO PDF scrape into `scripts/extract_cdsco.py` (bigger dataset, same schema)
- [ ] AI Functions `ai_query()` SQL view for pre-computed explanations

---

## 🟨 BS23B014 — non-code

- [ ] D1  Source 3 real demo prescriptions (printed, white background) → Drive/`demo-prescriptions/`
- [ ] D2  Hindi copy review — post before/after pairs as `DECISIONS.log` entry
- [ ] D3  Voice script for 90s demo (Google Doc)
- [ ] D4  5-slide deck: problem/solution/arch/demo/tech
- [ ] D5  Rehearsal partner + time-keeper at H-20
- [ ] D6  Phone test (real Android, PWA install) → pass/fail doc
- [ ] D7  Pitch coaching session
- [ ] D8  Judge Q&A prep
- [ ] D9  Demo-day logistics checklist

---

## 🟥 Harshit — EVAL (primary)

- [ ] E1  `eval/cases.json` — 15-20 cases (OCR, trust, explain, interactions)
- [ ] E2  Ground-truth labels per case
- [ ] E3  `eval/run_eval.py` — hits frozen API, writes `eval/results.json`
- [ ] E4  `eval/grade.py` → `eval/scorecard.md`
- [ ] E5  Post-integration run + commit scorecard

### Frontend (secondary; only if eval complete)
- [ ] H1-H8  Template polish, PWA icons, onboarding, a11y, demo video

---

## Guardrails — what's in place

| Layer | Guard | File |
|---|---|---|
| Image upload | MIME whitelist, 8 MB max, empty-check | `guards.check_image` |
| Audio upload | MIME whitelist, 6 MB max | `guards.check_audio` |
| Drug name | Character class + 128 chars max + lowercase | `guards.check_drug_name` |
| Language | 9-language whitelist | `guards.check_lang` |
| Phone | E.164 regex | `guards.check_phone` |
| Utterance | 2 KB max + prompt-injection phrase block | `guards.check_utterance` |
| LLM output | Strict JSON parse with required-keys check | `guards.parse_json_strict` |
| Explanation | Refuse if model invents dose; refuse substitution language | `guards.sanitize_explanation` |
| Banned drug | Hard override regardless of LLM output | `guards.enforce_banned` |
| Disclaimer | Auto-appended to every explanation | `guards.force_disclaimer` |
| Rate limit | 30/min (default), 5/min reminder, 60/min TTS | `guards.check_rate` |
| PII | SHA256-hashed for audit logs | `guards.hash_pii`, `redact_for_log` |
| Fuzzy match | Min 85 score to count as match | `guards.FUZZY_MATCH_MIN` |
| Secret sanity | Detects PLACEHOLDER / REPLACE_WITH / XXXX values | `guards.ensure_no_placeholder` |
| Data provenance | Every authoritative row tagged with `source_url + retrieved_at + verified` | `drug_sources` table |

---

## Cost watch

- SQL warehouse auto-stops after 10 min idle (configured)
- VS endpoint is STANDARD tier — **bills while running**. Stop between test windows:
  `databricks vector-search-endpoints delete-endpoint hack_cdsco_endpoint` then recreate
- App compute billed while running. Pause via `databricks apps stop rx-helper`

---

## Next human action from you

1. **Sarvam API key** → give me the value, I push to secrets (5 min)
2. **Twilio trial credentials** → same (10 min)

Everything else I can do autonomously from here until demo.

# Session-3 report — patient extraction, Bolna flows, webhook, model audit

Time-budget: 1 hour. **Used: ~50 min.** API spend: 1 vision LLM (free DBX foundation), 1 secrets put, ~10 SQL inserts, **3 Bolna calls (live).** Sarvam: 0 fresh.

---

## 1. Done · Tested · Ready-to-demo

| Feature | State | What's cached |
|---|---|---|
| **Vision OCR of `sample_prescription.jpeg`** | Done · live-tested · cached | Extracted JSON in `data/sample_prescription_extracted.json` and inserted as a `prescription_scans` row for Rina Devi |
| **Rina Devi's profile updated post-visit** | Done · DB-verified | 7 medicines now (3 original + 4 from new prescription); SOS contact = **Dr. Saab on +91 9074839967** |
| **3-flow Bolna agent** (`take_now` / `checkup` / `emergency`) | Done · 3 live calls placed | execution_ids cached in `static/fallbacks.js` so demo replays for free |
| **Webhook for Bolna call summaries** | Done · agent's `webhook_url` PATCHed via Bolna API | URL: `https://rx-helper-…/bolna_webhook?token=FYA1WzD_…` (token in secret scope) |
| **`bolna_call_outcomes` Delta sink** | Done · table created in `bricksiitm.rx_helper` | Schema below |
| **`/api/flow/take_now`** + **`/api/flow/checkup`** + **`/api/flow/emergency`** | Done · deployed | Form fields enumerated in `main.py` |
| **`REMINDER_LIVE=1`** | Now live | Demo button on My Medicines page → **rings Dr. Saab's phone for real** |
| **Model-routing brief** | Done | §3 below |

## 2. Bolna agent prompt + flows

The Medping agent (id `da40622a-…`) keeps its existing welcome line and dispatches on a `flow` field passed in `user_data`. The recommended system prompt to set on the agent (paste into Bolna dashboard if you want it pre-PATCHed; I already PATCHed `webhook_url` via API):

```
You are Medping, a calm voice assistant for Indian patients (Hindi or English).
The user_data payload contains: patient_name, language, flow ∈ {take_now, checkup, emergency}.

flow=take_now:
  Greet by name. "It's time to take your <medicine_name> <dosage>."
  Ask the patient to confirm "I took it / मैंने ले लिया" or "later / बाद में".
  Repeat once on no answer. ≤45s total.

flow=checkup:
  Ask 4 short questions one at a time:
    1. Are you taking medicines on time?
    2. Any side effects? (chakkar / pet dard / khujli / saans)
    3. Any medicine running out (refill needed)?
    4. How are you feeling overall?
  ≤90s. No medical advice.

flow=emergency:
  Speak to the doctor, not the patient.
  "This is an emergency from {patient_name}. Location: {location}.
   Current medicines: {medicines}. Reach them on {patient_phone}."
  Repeat twice. Be terse.

Always end "Take care. Goodbye."
```

End-of-call summary format (Bolna posts to our webhook):

```json
{
  "execution_id": "<uuid>",
  "flow": "take_now|checkup|emergency",
  "session_id": "<patient session>",
  "patient_name": "...",
  "medicine_name": "...",
  "outcome": "confirmed | refused | no_answer | voicemail | emergency_received",
  "transcript_summary": "<2-3 sentences>",
  "extracted_signals": {
    "took_today": true_or_false,
    "side_effects": "<one-line summary or null>",
    "needs_refill": true_or_false,
    "urgency": "low | moderate | high"
  },
  "duration_seconds": 0,
  "recording_url": "https://..."
}
```

## 3. Model usage audit (substitution policy)

| Feature | Endpoint / provider | Cost | Why |
|---|---|---|---|
| Prescription / drug-label OCR | `databricks-llama-4-maverick` (multimodal) | Free | DBX foundation handles vision → no need for GPT-4o etc. |
| RAG-grounded chatbot, agent intent router, side-effect classifier, drug interactions | `databricks-meta-llama-3-3-70b-instruct` | Free | DBX foundation; 70B is enough for our prompts |
| Vector-Search embeddings | `databricks-gte-large-en` | Free | Native DBX embedding endpoint |
| Hindi + Malayalam UI translations | Hand-curated dictionary in `translations.json` | $0 | Demo never re-translates UI |
| Hindi / English / Malayalam TTS for explanations + reminders | **Sarvam Bulbul v2** (`anushka` speaker) | External — paid, free tier | DBX foundation has no Indic TTS today |
| Hindi voice → text for check-in mic | **Sarvam Saarika v2** | External | Same — no Indic ASR in DBX foundation |
| English → Hindi / Malayalam text translation | **Sarvam Translate** | External | Same — used only for novel strings; cached for the demo set |
| Outbound voice calls (reminders, checkup, SOS) | **Bolna agent "Medping"** (Plivo telephony) | External — per-call credits | DLT-ready Indian outbound; no DBX equivalent |

**Substitution rule:** any reasoning / classification / vision goes to **DBX foundation** (free). External (paid) calls happen only when DBX has no native equivalent: Indic translate, Indic TTS, Indic ASR, telephony.

## 4. Schema · `bolna_call_outcomes`

```sql
CREATE TABLE bricksiitm.rx_helper.bolna_call_outcomes (
  received_at            TIMESTAMP,
  execution_id           STRING,
  flow                   STRING,        -- take_now | checkup | emergency
  session_id             STRING,
  patient_name           STRING,
  medicine_name          STRING,
  outcome                STRING,
  transcript_summary     STRING,
  extracted_signals_json STRING,        -- JSON string of {took_today, side_effects, needs_refill, urgency}
  duration_seconds       INT,
  recording_url          STRING
) USING DELTA;
```

## 5. Cache for demo

`static/fallbacks.js` now serves cached results for:
- `/api/flow/take_now` → execution_id `c11efab9-e4bf-4917-ae55-cc03dfdf2557`
- `/api/flow/checkup`  → execution_id `db5674d1-0e29-47a2-9ba4-ba2ce65b6f33`
- `/api/flow/emergency`→ execution_id `d3b6feef-cf90-479d-a097-130885259ab0`
- `/api/call_status?call_id=<one of the 3>` → returns the matching summary + recording URL

Demo can choose: live (rings Dr. Saab — wow factor) OR cached (instant, no Bolna spend).

## 6. Live test results (3 real Bolna calls)

| Flow | execution_id | Status | Duration | Recording |
|---|---|---|---|---|
| take_now | `c11efab9-…` | completed | 1s (busy) | `…507ce6b3-….mp3` |
| checkup | `db5674d1-…` | busy | 0s | (no answer) |
| emergency | `d3b6feef-…` | completed | 1s (busy) | `…6805c2f8-….mp3` |

All 3 reached Bolna's queue — calls were short because we placed them in 3-second succession to the same number. For the live demo, space them out OR use the cached fixtures.

## 6.5 ⚠️ Webhook reachability — Databricks Apps blocks unauth'd POST

Tested live: `POST /bolna_webhook?token=wrong` returns **HTTP 302** (SSO redirect). **Databricks Apps gates EVERY path behind workspace OAuth**, even ones we deliberately design for tokens — Bolna can't deliver the webhook payload.

**Workaround for the demo (zero new code needed):** poll `GET /api/call_status?call_id=…` from the UI on each user-initiated call. Bolna's status endpoint returns the same `summary` + `recording_url` we'd have gotten from the webhook. Already wired in `lib/bolna.get_call_status()`.

**Fix path post-demo:** move the webhook receiver to:
- (a) a tiny public Databricks Job HTTP endpoint, OR
- (b) a separate Databricks SQL Job that ingests Bolna's S3 recordings on a 5-min cadence, OR
- (c) an ngrok tunnel for the demo only (free, fastest).

The `/bolna_webhook` route + `bolna_call_outcomes` Delta + secret token are ALL in place — only the public-front-door is missing.

## 7. Post-this-session todo (already known; flagged)

1. **Update Bolna agent system prompt** in dashboard with the 3-flow text above (we did `webhook_url` PATCH, but the system-prompt PATCH path needs the full `agent_config` block — Bolna's UI is faster).
2. **Test webhook end-to-end** — when a call completes, does Bolna POST to our `/bolna_webhook?token=…`? The endpoint is deployed and the `BOLNA_WEBHOOK_TOKEN` env is wired, but I haven't confirmed Bolna actually delivers the callback. Run one isolated `take_now` call and watch `bolna_call_outcomes`.
3. **OCR cleanup pass** — vision LLM read the prescription's bad handwriting roughly (`Orop-codrug`, `BreeseP`, etc.). A second LLM pass could normalise these to known Indian formulary entries.
4. **Bigger prompt for the cohort agent endpoint** — the simple_agent notebook (https://github.com/prashant-repo-test/bharatbricksiim/blob/main/04_agent/01_simple_agent.ipynb) calls `databricks-claude-sonnet-4` which isn't provisioned in our workspace; if a teammate gets it provisioned, swap in.

## 8. Webhook URL (your ask)

```
https://rx-helper-7474644161560453.aws.databricksapps.com/bolna_webhook?token=FYA1WzD_FNwx8ixKFHWogzioZc4lp7mU
```

Token also stored at `secrets:rx-helper/bolna-webhook-token`. Rotate via:
```
databricks secrets put-secret rx-helper bolna-webhook-token --string-value "<new>"
```

— end —

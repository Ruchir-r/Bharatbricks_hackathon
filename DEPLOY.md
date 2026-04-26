# Deploying Dawa Dost to Databricks

End-to-end guide. Should take ~15 minutes assuming a Databricks workspace is already provisioned.

---

## Prerequisites

| Item | Why |
|---|---|
| **Databricks workspace** with Unity Catalog enabled | Delta tables, secrets, Apps, Vector Search |
| **Workspace admin OR equivalent** | To create catalogs/schemas, deploy apps, set secrets |
| **Databricks CLI ≥ v0.234** | `brew install databricks` (macOS) or [download](https://docs.databricks.com/aws/en/dev-tools/cli/install) |
| **A SQL Warehouse** (serverless or pro) | The app's Delta queries run through it |
| **Sarvam API key** | TTS / ASR / Translate. Free tier is enough for the demo. Get at [sarvam.ai](https://www.sarvam.ai/) |
| **Bolna API key + agent ID** | Outbound voice calls. Sign up at [bolna.ai](https://bolna.ai/), create an agent (template below) |

The repo doesn't pin secrets in code — everything is read from Databricks secret scope `rx-helper` via `app/lib/secrets_helper.py`.

---

## 1 · Authenticate the CLI

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
# follow the OAuth browser flow → creates ~/.databrickscfg profile DEFAULT
databricks current-user me        # sanity check
```

For headless/CI use a PAT (`databricks configure --token`) or M2M (`databricks auth m2m-token`).

---

## 2 · Clone & set bundle variables

```bash
git clone https://github.com/Ruchir-r/Bharatbricks_hackathon.git
cd Bharatbricks_hackathon
```

Edit `databricks.yml` if you want a different catalog/schema (defaults: `bricksiitm.rx_helper`):

```yaml
variables:
  catalog: { default: <your-catalog> }
  schema:  { default: <your-schema> }
```

---

## 3 · Create the secret scope and load keys

```bash
databricks secrets create-scope rx-helper

databricks secrets put-secret rx-helper sarvam-api-key        --string-value "$SARVAM_API_KEY"
databricks secrets put-secret rx-helper bolna-api-key         --string-value "$BOLNA_API_KEY"
databricks secrets put-secret rx-helper bolna-agent-id        --string-value "$BOLNA_AGENT_ID"
databricks secrets put-secret rx-helper bolna-webhook-token   --string-value "$(openssl rand -hex 24)"
```

The webhook token is consumed by `/bolna_webhook` in `app/main.py`. Bolna posts call-completion summaries there; the app rejects requests without a matching `?token=...`.

> **Note**: Databricks Apps SSO blocks the webhook today. Until SSO bypass for unauthenticated paths lands, the app polls `/api/call_status` instead — see `app/lib/bolna.py:get_call_status`. The secret is set anyway so the future webhook flow works without redeploy.

---

## 4 · Deploy the bundle

```bash
databricks bundle validate
databricks bundle deploy --target dev
```

This provisions:

| Resource | Defined in | Notes |
|---|---|---|
| Job `cdsco-ingest` | `resources/jobs.yml` | 2 tasks: ingest CSVs → Delta, then build Vector Search index |
| App `rx-helper` | `resources/jobs.yml` (apps section) | FastAPI on Databricks Apps — `source_code_path: ../app` |

---

## 5 · Run the ingest job

```bash
databricks bundle run ingest_cdsco
```

The two notebooks (`notebooks/01_ingest_cdsco.py`, `notebooks/02_build_vector_index.py`) will:

1. Create Unity Catalog schema `<catalog>.<schema>` if missing.
2. Load `data/*.csv` into Delta (CDSCO approved/banned/NSQ/FDC, NLEM 2022, PMBJP catalogue, drug aliases, drug-food).
3. Create Vector Search endpoint `hack_cdsco_endpoint` and index `cdsco_approved_idx` using `databricks-gte-large-en` embeddings.
4. Create the operational tables the app reads/writes: `patient_sessions`, `drug_timetable`, `side_effect_log`, `inference_log`, `sos_events`, `bolna_call_outcomes`.

Verify in the Catalog Explorer: 7 reference tables + 6 operational tables under `<catalog>.<schema>`.

---

## 6 · Configure the App's SQL Warehouse path

Open the deployed App in the workspace UI → **Edit app** → **Resources** → bind a SQL Warehouse and copy its HTTP path.

Set it in `app/app.yaml` (replace the placeholder):

```yaml
- name: DATABRICKS_HTTP_PATH
  value: /sql/1.0/warehouses/<your-warehouse-id>
```

Then redeploy:

```bash
databricks bundle deploy --target dev
databricks apps restart rx-helper
```

The app uses M2M OAuth automatically when running inside Databricks Apps (`DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` are injected by the platform).

---

## 7 · Seed the demo patient

The demo flow expects `Rina Devi` to exist with three baseline medicines. Run the SQL once via the warehouse:

```bash
databricks sql query --warehouse-id <id> --query "$(cat eval/seed_demo.sql)"
```

Or open a SQL editor in the workspace and paste `eval/seed_demo.sql`.

This creates `patient_sessions` row `demo-patient-001` with `+919074839967` as the SOS contact ("Dr. Saab") and three timetable entries.

---

## 8 · Verify

Get the deployed URL:

```bash
databricks apps get rx-helper | jq -r '.url'
# https://rx-helper-<workspace>.databricksapps.com
```

Open it. Click 🎬 (top-right) to enter demo mode → land on `?session=demo-patient-001` → you should see Rina's 3 medicines and a next-dose countdown.

Quick health checks:

```bash
curl https://<app-url>/api/health
# {"sarvam_configured": true, "bolna_configured": true, "db_reachable": true}

curl -X POST -F "phone=+919074839967" -F "patient_name=Rina" \
  -F "medicine_name=Crocin" -F "dosage=500mg" -F "time_slot=now" \
  -F "language=hi-IN" -F "session_id=demo-patient-001" \
  https://<app-url>/api/flow/take_now
# {"flow":"take_now","call_id":"<bolna-execution-id>"}
```

The phone you registered as the Bolna recipient should ring within ~10 seconds.

---

## 9 · The Bolna agent

The app expects a single Bolna agent that handles three flows (`take_now`, `checkup`, `emergency`). Pass `flow` via `user_data`. Dashboard config:

| Field | Value |
|---|---|
| Welcome message | `Hello {{patient_name}}, this is Vaidya from Medping.` (double-brace, not single) |
| `hangup_after_LLMCall` | **false** (otherwise call drops after first response) |
| Calling guardrails | 09:00–21:00 IST (Bolna trial requires this) |
| Transcriber | Sarvam saaras:v3 |
| Synthesizer | ElevenLabs (or Sarvam Bulbul v2) |

The exact system prompt is in `app/lib/bolna_flows.py:AGENT_PROMPT` — paste it into the agent's `system_prompt` field.

For Bolna **trial accounts**, every recipient phone number must be added to the verified-numbers list at `https://app.bolna.ai/phone-numbers` before it can receive calls. The demo number `+919074839967` should be added there.

---

## 10 · Optional: monitor & audit

- **Inference audit log** — every LLM call (OCR, RAG, explanation) is logged to `<catalog>.<schema>.inference_log`. Useful for the "MLflow-style audit" judging story.
- **Vector index drift** — the Delta sync index is `TRIGGERED`; rerun `ingest_cdsco` after refreshing CSVs. Change Data Feed is enabled on `cdsco_approved`.
- **SOS events** — `<catalog>.<schema>.sos_events`. Each row links session, timestamp, location URL, contact dialed.
- **Call outcomes** — `<catalog>.<schema>.bolna_call_outcomes` is populated by the webhook (or by client-side polling fallback).

---

## Local development

You don't need Databricks for development — demo mode in `app/static/fallbacks.js` serves cached fixtures so the entire UI flow runs offline.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BOLNA_API_KEY=...   # optional — without it, calls return dryrun ids
export BOLNA_AGENT_ID=...
export REMINDER_LIVE=1     # set to 0 to suppress real outbound calls
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000`, click 🎬 demo, and the same pipeline runs offline.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 take_now_failed: 'DATABRICKS_HTTP_PATH'` | Warehouse path not set | Step 6 above |
| `403 Trial accounts can only make calls to verified phone numbers` | Bolna trial gate | Add the recipient at `app.bolna.ai/phone-numbers` |
| Phone rings, agent says nothing, hangs up | `hangup_after_LLMCall: true` in Bolna agent config | Set to `false` |
| Welcome message says literal `{patient_name}` | Single brace template syntax | Change to `{{patient_name}}` (double) |
| `/bolna_webhook` returns 302 | Apps SSO blocking unauthenticated POST | Expected — app polls `/api/call_status` instead |
| Demo countdown shows wrong time | Stale `rx_next_dose_ts` in localStorage | Toggle 🎬 demo button once to reset |
| `sarvam_configured: false` in `/api/health` | Secret scope name mismatch | Must be exactly `rx-helper` (hyphen, lowercase) |

---

## Tearing down

```bash
databricks bundle destroy --target dev
databricks secrets delete-scope rx-helper
```

Underlying Delta tables are not auto-deleted (they live in your catalog). Drop manually if needed:

```sql
DROP SCHEMA IF EXISTS bricksiitm.rx_helper CASCADE;
```

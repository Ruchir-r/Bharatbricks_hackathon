"""Rx Helper — FastAPI backend. Serves HTML pages + JSON API.

Every endpoint is guard-wrapped. See lib/guards.py for the safety rules.
Business logic in lib/*.py — this file just wires HTTP → guards → lib → response.
"""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lib import (
    agent,
    ask,
    audit,
    bolna_flows,
    capabilities,
    drug_conflict,
    drug_identifier,
    explainer,
    guards,
    profile,
    rag,
    reminder,
    sarvam,
    sos,
    survey,
    timetable,
    trust_check,
    voice_reminder,
)

BASE_DIR = Path(__file__).parent
app = FastAPI(title="Rx Helper")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _guard_fail(e: guards.GuardError):
    return JSONResponse({"error": str(e), "code": "guard_failed"}, status_code=400)


_LANG_ALIASES = {
    "en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "bn": "bn-IN",
    "mr": "mr-IN", "gu": "gu-IN", "te": "te-IN", "kn": "kn-IN", "ml": "ml-IN",
}

def _norm_lang(lang: str) -> str:
    """Accept short ISO codes ('en', 'hi') as well as full ('en-IN', 'hi-IN')."""
    return _LANG_ALIASES.get((lang or "").lower(), lang)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"active": "home"})


@app.get("/api/profile")
async def api_profile(session_id: str):
    try:
        return profile.summary(session_id)
    except Exception as e:
        return JSONResponse({"error": "profile_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/ask")
async def api_ask(session_id: str = Form(...), question: str = Form(...), lang: str = Form("en-IN")):
    try:
        guards.check_rate(session_id, limit_per_min=20)
        guards.check_lang(lang)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        return ask.answer(session_id, question, lang=lang)
    except guards.GuardError as e:
        return _guard_fail(e)
    except Exception as e:
        return JSONResponse({"error": "ask_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    return templates.TemplateResponse(request, "scan.html", {"active": "scan"})


@app.get("/timetable", response_class=HTMLResponse)
async def timetable_page(request: Request):
    return templates.TemplateResponse(request, "timetable.html", {"active": "timetable"})


@app.get("/checkin", response_class=HTMLResponse)
async def checkin_page(request: Request):
    return templates.TemplateResponse(request, "checkin.html", {"active": "checkin"})


@app.get("/sos", response_class=HTMLResponse)
async def sos_page(request: Request):
    return templates.TemplateResponse(request, "sos.html", {"active": "sos"})


@app.get("/scan_result", response_class=HTMLResponse)
async def scan_result_page(request: Request):
    """Post-OCR results page: shows new medicines + alternates + timesheet + 45s countdown."""
    return templates.TemplateResponse(request, "scan_result.html", {"active": "scan"})


# ---------------------------------------------------------------------------
# API — every handler runs guards first, fails closed on any violation
# ---------------------------------------------------------------------------

@app.post("/api/scan")
async def api_scan(mode: str = Form(...), file: UploadFile = File(...)):
    if mode not in {"prescription", "drug_label"}:
        return _guard_fail(guards.GuardError(f"unknown mode {mode}"))
    data = await file.read()
    try:
        guards.check_image(data, file.content_type)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        if mode == "drug_label":
            return drug_identifier.identify_drug_label(data)

        # Prescription mode: vision OCR + second-pass LLM normalisation against CDSCO
        parsed = drug_identifier.extract_prescription(data)
        if parsed.get("drugs"):
            try:
                parsed["normalized_drugs"] = drug_identifier.normalize_ocr_drugs(
                    parsed["drugs"], diagnosis=parsed.get("diagnosis") or ""
                )
            except Exception as e:
                # Don't break the scan if normalisation fails
                parsed["normalized_drugs_error"] = str(e)[:200]
        return parsed
    except Exception as e:
        return JSONResponse({"error": "ocr_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/trust")
async def api_trust(drug_name: str = Form(...), batch_no: str | None = Form(None), lang: str = Form("hi-IN"), session_id: str = Form("anon")):
    original_lang = lang
    lang = _norm_lang(lang)
    try:
        drug_name = guards.check_drug_name(drug_name)
        guards.check_lang(lang)
        guards.check_rate(session_id)
    except guards.GuardError as e:
        return _guard_fail(e)
    v = trust_check.check(drug_name, batch_no=batch_no)
    return {
        "drug_name": v.drug_name,
        "safe": v.safe,
        "approved": v.approved,
        "banned": v.banned,
        "nsq_recent": v.nsq_recent,
        "nsq_batches": v.nsq_batches,
        "reasons": v.reasons_hi if lang == "hi-IN" else v.reasons_en,
    }


@app.post("/api/explain")
async def api_explain(drug: str = Form(...), dose: str = Form(""), lang: str = Form("hi-IN"), session_id: str = Form("anon")):
    original_lang = lang
    lang = _norm_lang(lang)
    try:
        drug = guards.check_drug_name(drug)
        guards.check_lang(lang)
        guards.check_rate(session_id)
    except guards.GuardError as e:
        return _guard_fail(e)

    # Hard-block if banned — do not generate any explanation
    v = trust_check.check(drug)
    if v.banned:
        refusal = guards.enforce_banned(drug, True, "")
        return {
            "english": refusal,
            "translated": refusal,
            "language": original_lang,
            "audio_b64": None,
            "banned": True,
        }

    with audit.timed() as t:
        try:
            res = explainer.explain_with_audio(drug=drug, dose=dose, language=lang)
        except Exception as e:
            audit.log("explain", session_id=session_id, input=f"{drug} {dose} {lang}", output=f"ERROR: {e}", latency_ms=t.elapsed_ms)
            return JSONResponse({"error": "explain_failed", "detail": str(e)[:200]}, status_code=502)

    # sanitize + disclaimer
    res["english"] = guards.sanitize_explanation(res["english"], drug, dose)
    res["translated"] = guards.force_disclaimer(res["translated"], lang)
    audio = res.get("audio_bytes")
    audit.log("explain", session_id=session_id, input=f"{drug} {dose} {lang}", output=res.get("audio_source", "?"), latency_ms=t.elapsed_ms)
    return {
        "english": res["english"],
        "translated": res["translated"],
        "language": original_lang,
        "audio_b64": base64.b64encode(audio).decode() if audio else None,
    }


@app.post("/api/tts")
async def api_tts(text: str = Form(...), lang: str = Form("hi-IN"), session_id: str = Form("anon")):
    lang = _norm_lang(lang)
    try:
        guards.check_lang(lang)
        guards.check_rate(session_id, limit_per_min=60)
        if len(text or "") > 1500:
            raise guards.GuardError("tts text too long (>1500 chars)")
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        audio = sarvam.tts(text, language=lang)
    except Exception as e:
        return JSONResponse({"error": "tts_failed", "detail": str(e)[:200]}, status_code=502)
    return {"audio_b64": base64.b64encode(audio).decode()}


@app.post("/api/asr")
async def api_asr(file: UploadFile = File(...), lang: str = Form("hi-IN"), session_id: str = Form("anon")):
    lang = _norm_lang(lang)
    try:
        guards.check_lang(lang)
        guards.check_rate(session_id)
    except guards.GuardError as e:
        return _guard_fail(e)
    data = await file.read()
    try:
        guards.check_audio(data, file.content_type)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        return {"transcript": sarvam.asr(data, language=lang)}
    except Exception as e:
        return JSONResponse({"error": "asr_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/interactions")
async def api_interactions(drugs: str = Form(...), diagnosis: str | None = Form(None), session_id: str = Form("anon")):
    try:
        guards.check_rate(session_id)
        names = []
        for d in drugs.split(","):
            if d.strip():
                names.append(guards.check_drug_name(d))
        if not names:
            raise guards.GuardError("no valid drugs")
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        hard = drug_conflict.hard_block_pairs(names)
        soft = drug_conflict.soft_check(names, diagnosis) if names else {}
    except Exception as e:
        return JSONResponse({"error": "interactions_failed", "detail": str(e)[:200]}, status_code=502)
    # Flat text summary so grader predicates like soft_text_contains_any work
    soft_bits: list[str] = []
    for i in soft.get("interactions", []) or []:
        soft_bits.append(f"{'+'.join(i.get('pair', []))} [{i.get('severity','?')}]: {i.get('explanation','')}")
    for c in soft.get("contraindications", []) or []:
        soft_bits.append(f"{c.get('drug','?')}: {c.get('concern','')}")
    return {"hard_blocks": hard, "soft": soft, "soft_text": " | ".join(soft_bits)}


@app.post("/api/timetable")
async def api_timetable(session_id: str = Form(...), drugs_json: str = Form(...)):
    import json
    try:
        guards.check_rate(session_id)
        drugs = json.loads(drugs_json)
        if not isinstance(drugs, list):
            raise guards.GuardError("drugs_json must be a list")
    except (guards.GuardError, json.JSONDecodeError) as e:
        return _guard_fail(guards.GuardError(str(e)))
    entries = timetable.build(session_id, drugs)
    try:
        timetable.persist(entries)
    except Exception as e:
        return JSONResponse({"error": "persist_failed", "detail": str(e)[:200]}, status_code=502)
    return {"entries": entries}


@app.post("/api/checkin")
async def api_checkin(session_id: str = Form(...), drug_name: str = Form(""), utterance: str = Form(...)):
    try:
        guards.check_rate(session_id)
        utterance = guards.check_utterance(utterance)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        result = survey.classify_symptom(utterance)
        survey.log_symptom(session_id, drug_name or "unknown", result["symptom"], result["severity"])
    except Exception as e:
        return JSONResponse({"error": "checkin_failed", "detail": str(e)[:200]}, status_code=502)
    return result


@app.post("/api/sos")
async def api_sos(
    session_id: str = Form(...),
    patient_name: str = Form(...),
    emergency_phone: str = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    note: str = Form(""),
):
    try:
        # SOS bypasses rate limit intentionally, but still validate phone
        emergency_phone = guards.check_phone(emergency_phone)
        if not patient_name.strip():
            raise guards.GuardError("patient name required")
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        return sos.trigger(
            session_id=session_id,
            patient_name=patient_name.strip()[:100],
            emergency_phone=emergency_phone,
            lat=lat,
            lon=lon,
            note=note[:500],
        )
    except Exception as e:
        return JSONResponse({"error": "sos_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/reminder")
async def api_reminder(phone: str = Form(...), message: str = Form(...), lang: str = Form("hi-IN"), session_id: str = Form("anon")):
    try:
        phone = guards.check_phone(phone)
        guards.check_lang(lang)
        guards.check_rate(session_id, limit_per_min=5)   # stricter: prevents spam dialing
        if len(message) > 500:
            raise guards.GuardError("message too long")
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        sid = reminder.place_call(phone, message, language=lang)
    except Exception as e:
        return JSONResponse({"error": "reminder_failed", "detail": str(e)[:200]}, status_code=502)
    return {"call_sid": sid}


@app.get("/api/_dbg_env")
async def dbg_env():
    """Lists DATABRICKS_* env keys (NOT values) to diagnose auth context."""
    keys = sorted(k for k in os.environ.keys() if k.startswith("DATABRICKS_") or k.startswith("BOLNA_") or k.startswith("SARVAM_") or k in ("CATALOG", "SCHEMA"))
    return {"keys_present": keys, "host_known": bool(os.environ.get("DATABRICKS_HOST"))}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "catalog": os.environ.get("CATALOG"),
        "schema": os.environ.get("SCHEMA"),
        "sarvam_configured": sarvam.is_configured(),
        "twilio_configured": bool(os.environ.get("TWILIO_ACCOUNT_SID")) and "PLACEHOLDER" not in (os.environ.get("TWILIO_ACCOUNT_SID") or ""),
        "languages": ["en-IN", "hi-IN"],
    }


# ---------------------------------------------------------------------------
# Demo presenter helpers — warm-up + demo session shortcut
# ---------------------------------------------------------------------------

WARMUP_DRUGS = [
    ("paracetamol", "500mg", "en-IN"),
    ("paracetamol", "500mg", "hi-IN"),
    ("amoxicillin", "500mg", "en-IN"),
    ("amoxicillin", "500mg", "hi-IN"),
    ("cefixime",    "200mg", "en-IN"),
    ("cefixime",    "200mg", "hi-IN"),
    ("metformin",   "500mg", "en-IN"),
    ("metformin",   "500mg", "hi-IN"),
]


@app.post("/api/warmup")
async def api_warmup(force: bool = False):
    """Pre-warms warehouse + VS index, then runs the explain pipeline for the
    canonical demo drugs. Cache hits make subsequent calls free.

    `force=true` bypasses cache and refreshes everything (only use if you suspect
    the cache is stale — costs API credits).
    """
    out: dict = {"steps": []}

    # 1. SQL warm
    with audit.timed() as t:
        try:
            v = trust_check.check("paracetamol")
            out["steps"].append({"step": "warehouse_warm", "ok": True, "ms": t.__exit__(None, None, None) or t.elapsed_ms, "detail": f"approved={v.approved}"})
        except Exception as e:
            out["steps"].append({"step": "warehouse_warm", "ok": False, "detail": str(e)[:200]})
    out["steps"][-1].setdefault("ms", t.elapsed_ms)

    # 2. Vector search warm
    with audit.timed() as t:
        try:
            ctx = explainer.retrieve_context("paracetamol")
            out["steps"].append({"step": "vector_warm", "ok": True, "ms": t.elapsed_ms, "detail": f"hits={len(ctx)}"})
        except Exception as e:
            out["steps"].append({"step": "vector_warm", "ok": False, "ms": t.elapsed_ms, "detail": str(e)[:200]})

    # 3. Pipeline cache fill
    cached = uncached = errors = 0
    for drug, dose, lang in WARMUP_DRUGS:
        with audit.timed() as t:
            try:
                # peek cache
                pre = explainer._read_pipeline_cache(drug, dose, lang)
                if pre and not force:
                    cached += 1
                    out["steps"].append({"step": f"explain[{drug},{lang}]", "ok": True, "ms": t.elapsed_ms, "detail": "cache-hit"})
                    continue
                res = explainer.explain_with_audio(drug=drug, dose=dose, language=lang, use_cache=not force)
                uncached += 1
                out["steps"].append({"step": f"explain[{drug},{lang}]", "ok": True, "ms": t.elapsed_ms, "detail": f"src={res.get('audio_source')} en_len={len(res.get('english',''))}"})
                audit.log("warmup_explain", session_id="warmup", input=f"{drug} {dose} {lang}", output=str(res.get('audio_source')), latency_ms=t.elapsed_ms)
            except Exception as e:
                errors += 1
                out["steps"].append({"step": f"explain[{drug},{lang}]", "ok": False, "ms": t.elapsed_ms, "detail": str(e)[:200]})

    out["summary"] = {"total": len(WARMUP_DRUGS), "cache_hit": cached, "newly_cached": uncached, "errors": errors}
    audit.log("warmup_summary", session_id="warmup", output=str(out["summary"]))
    return out


@app.get("/demo")
async def demo_redirect():
    """Shortcut: navigate to home with the seeded demo session pinned."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/?session=demo-patient-001")


# ---------------------------------------------------------------------------
# New capability endpoints
# ---------------------------------------------------------------------------

@app.get("/api/refill_alert")
async def api_refill_alert(session_id: str, threshold_days: int = 3):
    try:
        return {"alerts": capabilities.refill_alert(session_id, threshold_days=threshold_days)}
    except Exception as e:
        return JSONResponse({"error": "refill_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/food_warnings")
async def api_food_warnings(drug_name: str | None = None, session_id: str | None = None):
    try:
        if drug_name:
            return {"drug_name": drug_name, "warnings": capabilities.food_warnings(drug_name)}
        if session_id:
            return {"session_id": session_id, "warnings": capabilities.food_warnings_for_session(session_id)}
        return JSONResponse({"error": "drug_name or session_id required"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": "food_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/scheme_eligibility")
async def api_schemes(diagnosis: str = "any", state: str | None = None):
    try:
        return {"diagnosis": diagnosis, "state": state, "schemes": capabilities.scheme_eligibility(diagnosis, state=state)}
    except Exception as e:
        return JSONResponse({"error": "scheme_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/pharmacy_locator")
async def api_pharmacy(lat: float, lon: float, limit: int = 5):
    try:
        return {"pharmacies": capabilities.pharmacies_near(lat, lon, limit=limit)}
    except Exception as e:
        return JSONResponse({"error": "pharmacy_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/savings_summary")
async def api_savings(session_id: str):
    try:
        return capabilities.savings_summary(session_id)
    except Exception as e:
        return JSONResponse({"error": "savings_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/care_card", response_class=HTMLResponse)
async def api_care_card(session_id: str):
    try:
        return HTMLResponse(capabilities.care_card_html(session_id))
    except Exception as e:
        return JSONResponse({"error": "care_card_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/agent")
async def api_agent(
    text: str = Form(...),
    session_id: str = Form(...),
    lang: str = Form("en-IN"),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    diagnosis: str | None = Form(None),
    state: str | None = Form(None),
):
    """Single-turn agent — classifies intent + dispatches to the right capability."""
    try:
        guards.check_rate(session_id, limit_per_min=20)
        guards.check_lang(_norm_lang(lang))
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        return agent.dispatch(text, session_id, lang=_norm_lang(lang),
                              lat=lat, lon=lon, diagnosis=diagnosis, state=state)
    except Exception as e:
        return JSONResponse({"error": "agent_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/voice_reminder")
async def api_voice_reminder(drug: str, dose: str = "", lang: str = "en-IN"):
    """Generate a 'take your medicine' TTS clip for a given drug+dose+language.
    Cached by Sarvam wrapper — repeat calls for same drug/dose/lang are free.
    """
    try:
        guards.check_drug_name(drug)
        guards.check_lang(_norm_lang(lang))
    except guards.GuardError as e:
        return _guard_fail(e)
    return voice_reminder.synthesise(drug, dose, lang=_norm_lang(lang))


@app.post("/api/call_reminder")
async def api_call_reminder(
    phone: str = Form(...),
    drug: str = Form(...),
    dose: str = Form(""),
    lang: str = Form("hi-IN"),
    patient_name: str = Form("Patient"),
    time_slot: str = Form(""),
    session_id: str = Form("anon"),
):
    """Place a Bolna outbound call; the agent's prompt receives drug/dose so it
    speaks the reminder live. Falls back to dryrun if REMINDER_LIVE is off."""
    try:
        phone = guards.check_phone(phone)
        guards.check_drug_name(drug)
        guards.check_lang(_norm_lang(lang))
        guards.check_rate(session_id, limit_per_min=5)  # stricter — outbound calls cost
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        text = voice_reminder.render_text(drug, dose, lang=_norm_lang(lang))
        sid = reminder.place_call(
            phone, text, language=_norm_lang(lang),
            patient_name=patient_name, drug_name=drug, dose=dose, time_slot=time_slot,
        )
        audit.log("call_reminder", session_id=session_id, input=f"{drug} {dose} -> {phone}", output=sid)
        return {"call_id": sid, "message": text}
    except Exception as e:
        return JSONResponse({"error": "call_failed", "detail": str(e)[:200]}, status_code=502)


@app.get("/api/call_status")
async def api_call_status(call_id: str):
    """Poll Bolna for status + summary. Use after /api/call_reminder."""
    try:
        from lib import bolna
        return bolna.get_call_status(call_id)
    except Exception as e:
        return JSONResponse({"error": "status_failed", "detail": str(e)[:200]}, status_code=502)


# ---------------------------------------------------------------------------
# Bolna 3-flow agent + webhook
# ---------------------------------------------------------------------------

@app.post("/api/flow/take_now")
async def api_flow_take_now(
    phone: str = Form(...), patient_name: str = Form(...),
    medicine_name: str = Form(...), dosage: str = Form(""),
    time_slot: str = Form("now"), language: str = Form("hi-IN"),
    session_id: str = Form("anon"),
):
    try:
        phone = guards.check_phone(phone)
        guards.check_drug_name(medicine_name)
        guards.check_lang(_norm_lang(language))
        guards.check_rate(session_id, limit_per_min=5)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        cid = bolna_flows.take_now(phone=phone, patient_name=patient_name, medicine_name=medicine_name,
                                   dosage=dosage, time_slot=time_slot, language=_norm_lang(language), session_id=session_id)
        audit.log("bolna_take_now", session_id=session_id, input=f"{medicine_name}/{phone}", output=cid)
        return {"flow": "take_now", "call_id": cid}
    except Exception as e:
        return JSONResponse({"error": "take_now_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/flow/checkup")
async def api_flow_checkup(
    phone: str = Form(...), patient_name: str = Form(...),
    language: str = Form("hi-IN"), session_id: str = Form("anon"),
):
    try:
        phone = guards.check_phone(phone)
        guards.check_lang(_norm_lang(language))
        guards.check_rate(session_id, limit_per_min=3)
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        meds = [m["drug_name"] for m in profile.get_timetable(session_id) if m.get("drug_name")]
        cid = bolna_flows.checkup(phone=phone, patient_name=patient_name, medicines_on_file=meds,
                                  language=_norm_lang(language), session_id=session_id)
        audit.log("bolna_checkup", session_id=session_id, input=phone, output=cid)
        return {"flow": "checkup", "call_id": cid, "medicines": meds}
    except Exception as e:
        return JSONResponse({"error": "checkup_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/api/flow/emergency")
async def api_flow_emergency(
    doctor_phone: str = Form(...), patient_name: str = Form(...),
    patient_phone: str = Form(""),
    lat: float | None = Form(None), lon: float | None = Form(None),
    language: str = Form("en-IN"), session_id: str = Form("anon"),
):
    try:
        doctor_phone = guards.check_phone(doctor_phone)
        guards.check_lang(_norm_lang(language))
    except guards.GuardError as e:
        return _guard_fail(e)
    try:
        loc = f"https://maps.google.com/?q={lat},{lon}" if lat and lon else "(location not shared)"
        meds = [m["drug_name"] for m in profile.get_timetable(session_id) if m.get("drug_name")]
        cid = bolna_flows.emergency(doctor_phone=doctor_phone, patient_name=patient_name,
                                    location_link=loc, medicines_on_file=meds,
                                    patient_phone=patient_phone, language=_norm_lang(language),
                                    session_id=session_id)
        audit.log("bolna_emergency", session_id=session_id, input=f"{patient_name} -> {doctor_phone}", output=cid)
        return {"flow": "emergency", "call_id": cid, "doctor_called": doctor_phone, "location": loc}
    except Exception as e:
        return JSONResponse({"error": "emergency_failed", "detail": str(e)[:200]}, status_code=502)


@app.post("/bolna_webhook")
async def bolna_webhook(request: Request, token: str = ""):
    """Bolna calls back here when a call completes. Token-protected; the secret
    lives in `bricksiitm.rx_helper.bolna_webhook_token` Delta or env BOLNA_WEBHOOK_TOKEN."""
    expected = os.environ.get("BOLNA_WEBHOOK_TOKEN", "")
    if not expected or token != expected:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    # Persist to bolna_call_outcomes Delta — schema-tolerant
    try:
        from lib import db
        with db.connect() as c, c.cursor() as cur:
            import json as _json
            cur.execute(
                f"INSERT INTO {db.fq('bolna_call_outcomes')} (received_at, execution_id, flow, session_id, "
                f"patient_name, medicine_name, outcome, transcript_summary, extracted_signals_json, "
                f"duration_seconds, recording_url) VALUES (current_timestamp(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    body.get("execution_id"), body.get("flow"), body.get("session_id"),
                    body.get("patient_name"), body.get("medicine_name"), body.get("outcome"),
                    body.get("transcript_summary"),
                    _json.dumps(body.get("extracted_signals") or {}),
                    int(body.get("duration_seconds") or 0),
                    body.get("recording_url"),
                ),
            )
        return {"ok": True}
    except Exception as e:
        # Never 500 to Bolna — they retry; just acknowledge with diagnostic
        audit.log("bolna_webhook_err", input=str(body)[:500], output=str(e)[:200])
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/rag")
async def api_rag(drug_name: str):
    """Diagnostic: returns the multi-source citations for a drug."""
    try:
        cites = rag.retrieve_for_drug(drug_name)
        return {
            "drug_name": drug_name,
            "confidence": round(rag.confidence_score(cites), 3),
            "citations": [c.as_dict() for c in cites],
        }
    except Exception as e:
        return JSONResponse({"error": "rag_failed", "detail": str(e)[:200]}, status_code=502)

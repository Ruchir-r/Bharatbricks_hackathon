"""Reminder + SOS voice calls.

Primary backend: Bolna (Indian voice-agent; DLT-ready).
Fallback: Twilio (if configured — US trial).
Shared API: `place_call(phone, message, language)` → call_sid.

For demo cost control, REMINDER_LIVE=0 (default) disables real outbound calls and
returns a dry-run id. Flip to 1 for the actual demo.
"""

from __future__ import annotations
import os
import uuid
from . import bolna


def _live() -> bool:
    return os.environ.get("REMINDER_LIVE", "0") in {"1", "true", "yes"}


def place_call(to_number: str, message: str, language: str = "hi-IN", *,
               patient_name: str = "", drug_name: str = "", dose: str = "", time_slot: str = "") -> str:
    """Returns a call id (Bolna id, Twilio SID, or dry-run uuid).

    Bolna agent receives `user_data` with: medicine_name, dosage, timing, time_slot,
    patient_name, message, language — matching the TS VoiceAgentService convention.
    """
    if not _live():
        return f"dryrun-{uuid.uuid4().hex[:12]}"

    if bolna.is_configured():
        ctx = {
            "medicine_name": drug_name,
            "dosage": dose,
            "timing": time_slot,
            "time_slot": time_slot,
            "message": message,
            "language": language,
        }
        try:
            res = bolna.place_call(to_number, ctx, patient_name=patient_name)
        except bolna.BolnaTrialRestriction as e:
            raise RuntimeError(f"Bolna trial restriction: {e}")
        return res["call_id"]

    # Twilio fallback (only if SID+token env set)
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    if sid and "PLACEHOLDER" not in sid:
        from twilio.rest import Client
        c = Client(sid, os.environ["TWILIO_AUTH_TOKEN"])
        twiml = f'<Response><Say voice="Polly.Aditi" language="{language}">{message}</Say></Response>'
        call = c.calls.create(to=to_number, from_=os.environ["TWILIO_FROM"], twiml=twiml)
        return call.sid

    raise RuntimeError("No voice backend configured (Bolna or Twilio).")


def place_sms(to_number: str, message: str) -> str:
    """Bolna doesn't provide SMS in the same flow; use Twilio if available.
    Falls back to a dry-run id."""
    if not _live():
        return f"dryrun-sms-{uuid.uuid4().hex[:12]}"
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    if sid and "PLACEHOLDER" not in sid:
        from twilio.rest import Client
        c = Client(sid, os.environ["TWILIO_AUTH_TOKEN"])
        msg = c.messages.create(to=to_number, from_=os.environ["TWILIO_FROM"], body=message)
        return msg.sid
    return f"sms-unavailable-{uuid.uuid4().hex[:8]}"

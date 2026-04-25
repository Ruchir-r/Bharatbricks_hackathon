"""Bolna wrapper — outbound voice calls for reminders + SOS.

Bolna is an Indian voice-agent platform with DLT-ready outbound calling.
Fits our rural-India audience better than Twilio (which requires DLT registration
for production Indian outbound).

Graceful degrade when BOLNA_API_KEY missing: raises BolnaUnavailable so
callers can surface a clear "voice not configured" error instead of crashing.
"""

from __future__ import annotations
import os
import re
import requests
from typing import TypedDict

BASE = "https://api.bolna.ai"
PLACEHOLDER_MARKERS = ("PLACEHOLDER", "REPLACE_WITH", "XXXX", "your-key-here", "CHANGEME")

# Keywords that indicate the patient confirmed taking the medicine
# Mirrors the smart confirmation logic in the TS getCallStatus method
SUCCESS_KEYWORDS = ["took", "taken", "confirmed", "yes", "agreed", "done"]
FAILURE_KEYWORDS = ["refused", "missed", "later", "no", "busy", "voicemail"]


class CallResult(TypedDict):
    success: bool
    call_id: str
    status: str


class CallStatus(TypedDict):
    status: str
    completed: bool
    confirmed: bool
    summary: str | None
    raw: dict


class BolnaUnavailable(RuntimeError):
    pass


class BolnaTrialRestriction(RuntimeError):
    """Raised when Bolna returns 403 due to unverified phone numbers on a trial account."""
    pass


def _resolve_key() -> str | None:
    from . import secrets_helper
    return secrets_helper.get("BOLNA_API_KEY", scope="rx-helper", key="bolna-api-key")


def _resolve_agent() -> str | None:
    from . import secrets_helper
    return secrets_helper.get("BOLNA_AGENT_ID", scope="rx-helper", key="bolna-agent-id")


def is_configured() -> bool:
    key = _resolve_key() or ""
    agent = _resolve_agent() or ""
    if not key or not agent:
        return False
    return not any(m in key for m in PLACEHOLDER_MARKERS)


def _headers() -> dict:
    key = _resolve_key()
    if not key or not _resolve_agent():
        raise BolnaUnavailable("BOLNA_API_KEY / BOLNA_AGENT_ID not set")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def format_phone_number(phone: str) -> str:
    """Normalise a phone number to E.164 format.

    Handles Indian numbers that arrive as:
      - "9876543210"     → "+919876543210"  (no country code, no leading 0)
      - "09876543210"    → "+919876543210"  (with leading 0, Indian STD style)
      - "+91 98765 43210"→ "+919876543210"  (spaces)
      - "+919876543210"  → "+919876543210"  (already correct, pass-through)

    Mirrors formatPhoneNumber() in the TS VoiceAgentService.
    """
    cleaned = re.sub(r"[\s()\-]", "", phone.strip())
    cleaned = cleaned.lstrip("0")
    if cleaned.startswith("+"):
        return cleaned
    # If 10-digit, assume Indian and prepend +91
    if len(cleaned) == 10 and cleaned.isdigit():
        return "+91" + cleaned
    return f"+{cleaned}"


def place_call(
    to_number: str,
    context: dict | None = None,
    patient_name: str = "",
) -> CallResult:
    """Start an outbound call via a pre-configured Bolna agent.

    `context` is injected as user_data the agent uses for prompt variables.
    Expected keys (mirrors TS Medicine type): medicine_name, dosage, timing,
    time_slot, patient_name.

    Returns a CallResult dict with success, call_id, and status.
    Raises BolnaTrialRestriction when the account needs phone verification.
    """
    formatted_number = format_phone_number(to_number)

    user_data = {
        "patient_name": patient_name,
        **(context or {}),
    }

    payload = {
        "agent_id": _resolve_agent(),
        "recipient_phone_number": formatted_number,
        "user_data": user_data,
    }

    r = requests.post(f"{BASE}/call", headers=_headers(), json=payload, timeout=30)

    if not r.ok:
        try:
            body = r.json()
        except Exception:
            body = {}
        raw_message = (body.get("message") or body.get("detail") or "").lower()
        if "verified phone numbers" in raw_message or r.status_code == 403:
            raise BolnaTrialRestriction(
                "TRIAL_RESTRICTION: Phone number not verified on Bolna dashboard. "
                "Add the number at https://app.bolna.ai/phone-numbers"
            )
        r.raise_for_status()

    body = r.json()
    # Bolna's actual response shape: {status, message, execution_id, run_id}
    call_id = (
        body.get("execution_id")
        or body.get("run_id")
        or body.get("call_id")
        or body.get("id")
        or "unknown"
    )

    return CallResult(
        success=True,
        call_id=call_id,
        status=body.get("status") or "initiated",
    )


def get_call_status(call_id: str) -> CallStatus:
    """Poll the status of a Bolna call and parse the adherence outcome.

    Returns a CallStatus dict:
      - status:    Bolna status string (queued/initiated/in-progress/completed/failed)
      - completed: True once the call is in a terminal state
      - confirmed: True if completed AND a success keyword was found
      - summary:   Raw Bolna summary string (useful for Delta Silver table logging)
      - raw:       Full Bolna response body
    """
    if not call_id or len(call_id) < 5:
        return CallStatus(
            status="invalid_id", completed=False, confirmed=False, summary=None, raw={},
        )

    # Bolna's status endpoint is /executions/{execution_id}, not /call/{id}
    try:
        r = requests.get(f"{BASE}/executions/{call_id}", headers=_headers(), timeout=30)
    except requests.RequestException:
        return CallStatus(status="error", completed=False, confirmed=False, summary=None, raw={})

    if not r.ok:
        return CallStatus(status="not_found", completed=False, confirmed=False, summary=None, raw={})

    data = r.json()
    current_status = (
        data.get("status") or data.get("call_status")
        or data.get("conversation_status") or "unknown"
    ).lower()
    is_terminal = current_status in ("completed", "failed", "cancelled", "no-answer", "noanswer")

    summary = (data.get("summary") or data.get("agent_summary") or "").lower()
    transcript = " ".join(str(t) for t in (data.get("transcript") or [])).lower() if isinstance(data.get("transcript"), list) else (data.get("transcript") or "").lower()

    has_success = any(kw in summary or kw in transcript for kw in SUCCESS_KEYWORDS)
    has_failure = any(kw in summary or kw in transcript for kw in FAILURE_KEYWORDS)

    is_confirmed = is_terminal and current_status == "completed" and has_success and not has_failure

    return CallStatus(
        status=current_status,
        completed=is_terminal,
        confirmed=is_confirmed,
        summary=data.get("summary"),
        raw=data,
    )

"""Three-flow Bolna agent dispatcher.

We use the existing Medping agent (welcome message: "Hello {patient_name}, I'm
calling from Medping") and pass everything through `user_data`. The agent prompt
interprets the `flow` field and dispatches:

  - take_now      : "Reminder to take {medicine_name} {dosage} now"
  - checkup       : "General check-in — ask about adherence, side effects, refill"
  - emergency     : "SOS — patient needs help. Speak to {patient_name}'s doctor."

The webhook on call completion (`/bolna_webhook?token=...`) writes a structured
row to `bolna_call_outcomes` Delta. Schema is the spec we hand to Bolna.

Format Bolna should send to our webhook:
  {
    "execution_id":   "<uuid>",
    "flow":           "take_now" | "checkup" | "emergency",
    "session_id":     "<patient session>",
    "patient_name":   "...",
    "medicine_name":  "..." (take_now/checkup),
    "outcome":        "confirmed" | "refused" | "no_answer" | "voicemail" | "emergency_received",
    "transcript_summary": "<2-3 sentences from Bolna's LLM summary>",
    "extracted_signals": {                # optional, agent-derived
      "took_today": true_or_false,
      "side_effects": "...",
      "needs_refill": true_or_false,
      "urgency":     "low" | "moderate" | "high"
    },
    "duration_seconds": 0,
    "recording_url":   "https://..."
  }
"""

from __future__ import annotations
from typing import Any
from . import bolna


# ---- agent prompt (recommended; user can paste this into Bolna dashboard if they want PATCHing) ----

AGENT_PROMPT = """You are Medping — a calm, kind voice assistant for Indian patients in Hindi or
English depending on the user's preferred_language.

You will receive a `user_data` payload with at minimum: patient_name, language, flow.
flow ∈ {take_now, checkup, emergency}.

If flow == "take_now":
  Greet by patient_name. Tell them: "It is time to take your <medicine_name>
  <dosage>." Ask them to confirm by saying "I took it" / "मैंने ले लिया" /
  "later" / "बाद में". Repeat once if no answer. Keep call ≤ 45 seconds.

If flow == "checkup":
  Greet warmly. Ask 4 short questions one at a time:
    1. Are you taking your medicines on time?
    2. Any side effects? (chakkar / pet dard / khujli / saans?)
    3. Are your medicines about to run out (refill needed?)
    4. How are you feeling overall — okay / not okay?
  Keep call ≤ 90 seconds. Be kind. Do not give medical advice.

If flow == "emergency":
  Speak ONLY to the doctor (recipient is the doctor, not the patient).
  Say: "This is an emergency call from {patient_name}'s Medping app. They have
  triggered SOS. Their location is {location}. Their current medicines:
  {medicines}. Please call them on {patient_phone}."
  Repeat the message twice. Be terse and clear.

ABSOLUTE RULES:
  - Never invent doses or recommend drug changes.
  - If the patient says "doctor", "hospital", or sounds in pain → tell them to
    use the SOS button immediately.
  - Always end with "Take care. Goodbye."

After the call, the platform will request a JSON summary. Return:
{
  "outcome": "confirmed" | "refused" | "no_answer" | "voicemail" | "emergency_received",
  "transcript_summary": "<2-3 sentences>",
  "extracted_signals": {
    "took_today": true_or_false,
    "side_effects": "<one-line summary or null>",
    "needs_refill": true_or_false,
    "urgency": "low" | "moderate" | "high"
  }
}
"""


# ---- public flow helpers ----

def take_now(*, phone: str, patient_name: str, medicine_name: str, dosage: str,
             time_slot: str, language: str = "hi-IN", session_id: str = "anon") -> str:
    """Place a 'reminder to take medicine now' Bolna call. Returns execution_id."""
    res = bolna.place_call(
        phone,
        context={
            "flow": "take_now",
            "session_id": session_id,
            "language": language,
            "medicine_name": medicine_name,
            "dosage": dosage,
            "timing": time_slot,
            "time_slot": time_slot,
        },
        patient_name=patient_name,
    )
    return res["call_id"]


def checkup(*, phone: str, patient_name: str, medicines_on_file: list[str],
            language: str = "hi-IN", session_id: str = "anon") -> str:
    """Place a periodic general-checkup call. Returns execution_id."""
    res = bolna.place_call(
        phone,
        context={
            "flow": "checkup",
            "session_id": session_id,
            "language": language,
            "medicines_on_file": ", ".join(medicines_on_file[:5]),
        },
        patient_name=patient_name,
    )
    return res["call_id"]


def emergency(*, doctor_phone: str, patient_name: str, location_link: str,
              medicines_on_file: list[str], patient_phone: str = "",
              language: str = "en-IN", session_id: str = "anon") -> str:
    """SOS call to the doctor (Dr. Saab). Returns execution_id."""
    res = bolna.place_call(
        doctor_phone,
        context={
            "flow": "emergency",
            "session_id": session_id,
            "language": language,
            "patient_name": patient_name,
            "location": location_link or "location not shared",
            "patient_phone": patient_phone,
            "medicines": ", ".join(medicines_on_file[:5]),
        },
        patient_name="Doctor",   # the recipient is the doctor
    )
    return res["call_id"]

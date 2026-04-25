"""Lightweight intent-router agent (LangGraph-equivalent, dependency-free).

Single entry: agent.dispatch(user_text, session_id, lang) → {action, payload, ...}
Decides which sub-feature should handle the user's natural-language request and
calls it. Each branch is a guarded, RAG-grounded micro-flow.

Why not LangGraph? Adding a 50 MB dependency for a 5-branch state machine is
overkill in 24 hours. This stays explicit and auditable.

Branches:
  - ASK_GENERAL        → ask.answer(...)
  - REFILL_CHECK       → capabilities.refill_alert
  - FOOD_WARNINGS      → capabilities.food_warnings
  - PHARMACY           → capabilities.pharmacies_near (needs lat/lon — deferred)
  - SCHEME             → capabilities.scheme_eligibility
  - SAVINGS            → capabilities.savings_summary
  - CARE_CARD          → capabilities.care_card_html
  - SOS_REDIRECT       → returns hint to UI
"""

from __future__ import annotations
import json
from . import ask, capabilities, guards, llm_client, profile


CLASSIFIER_PROMPT = """Classify the user's request into ONE of the labels below. Reply JSON only.
Labels (pick exactly one):
- ASK_GENERAL — generic medicine question
- REFILL_CHECK — when does my prescription run out / do I need a refill
- FOOD_WARNINGS — can I eat / drink X with my medicine; alcohol; food
- PHARMACY — find / nearest pharmacy / Jan Aushadhi
- SCHEME — government scheme / Ayushman / free medicine / financial help
- SAVINGS — how much can I save / cheaper generic
- CARE_CARD — share with family / print / caregiver / take to doctor
- SOS_REDIRECT — emergency / chest pain / unconscious / bleeding

Reply: {{"label": "...", "why": "<10 words"}}

User text: "{user}"
"""


def classify(user_text: str) -> str:
    """Returns the chosen label string. Defaults to ASK_GENERAL on parse failure."""
    user_text = guards.check_utterance(user_text)
    try:
        raw = llm_client.chat(
            "databricks-meta-llama-3-3-70b-instruct",
            [{"role": "user", "content": CLASSIFIER_PROMPT.format(user=user_text[:300])}],
            max_tokens=80,
            temperature=0.0,
        )
        obj = guards.parse_json_strict(raw, ["label"])
        label = (obj.get("label") or "ASK_GENERAL").upper()
        valid = {"ASK_GENERAL","REFILL_CHECK","FOOD_WARNINGS","PHARMACY","SCHEME","SAVINGS","CARE_CARD","SOS_REDIRECT"}
        return label if label in valid else "ASK_GENERAL"
    except Exception:
        return "ASK_GENERAL"


def dispatch(user_text: str, session_id: str, lang: str = "en-IN", *,
             lat: float | None = None, lon: float | None = None,
             diagnosis: str | None = None, state: str | None = None) -> dict:
    label = classify(user_text)

    if label == "REFILL_CHECK":
        return {"action": label, "result": capabilities.refill_alert(session_id)}

    if label == "FOOD_WARNINGS":
        # Try to pull a drug name from the question; else aggregate over profile
        from .ask import _drugs_mentioned
        meds = profile.get_timetable(session_id)
        drugs = _drugs_mentioned(user_text, [{"drug_name": m["drug_name"]} for m in meds])
        if drugs:
            return {"action": label, "drug_name": drugs[0],
                    "result": capabilities.food_warnings(drugs[0])}
        return {"action": label, "result": capabilities.food_warnings_for_session(session_id)}

    if label == "PHARMACY":
        if lat is None or lon is None:
            return {"action": label, "needs_location": True,
                    "result": [], "hint": "Please share location to find nearest Jan Aushadhi."}
        return {"action": label, "result": capabilities.pharmacies_near(lat, lon)}

    if label == "SCHEME":
        diag = diagnosis or "any"
        return {"action": label, "diagnosis": diag,
                "result": capabilities.scheme_eligibility(diag, state=state)}

    if label == "SAVINGS":
        return {"action": label, "result": capabilities.savings_summary(session_id)}

    if label == "CARE_CARD":
        return {"action": label, "html_url": "/api/care_card?session_id=" + session_id}

    if label == "SOS_REDIRECT":
        return {"action": label, "redirect": "/sos",
                "hint": "This sounds urgent. Please use the SOS button."}

    # Default → grounded LLM Q&A
    return {"action": "ASK_GENERAL", "result": ask.answer(session_id, user_text, lang=lang)}

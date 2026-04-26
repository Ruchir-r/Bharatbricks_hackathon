"""Safety guardrails for Dawa Dost.

Philosophy: fail-closed on anything touching medical information. Never hallucinate
dose, substitutions, or diagnoses. Never override CDSCO-banned status. Always disclose
source and confidence. Never log patient PII in cleartext.
"""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
import re
import time
from collections import defaultdict, deque
from typing import Any

# -----------------------------------------------------------------------------
# Input validation
# -----------------------------------------------------------------------------

MAX_IMAGE_BYTES = 8 * 1024 * 1024          # 8 MB
MAX_AUDIO_BYTES = 6 * 1024 * 1024          # 6 MB
MAX_DRUG_NAME_LEN = 128
MAX_UTTERANCE_LEN = 2000
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_AUDIO_MIME = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/webm", "audio/ogg"}
LANG_WHITELIST = {"hi-IN", "ta-IN", "bn-IN", "mr-IN", "gu-IN", "te-IN", "kn-IN", "ml-IN", "en-IN"}
PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # E.164
DRUG_NAME_RE = re.compile(r"^[A-Za-z0-9\s\-\+\.'/]{1,128}$")  # conservative


class GuardError(ValueError):
    """Raised when input fails safety/validation."""


def check_image(data: bytes, mime: str | None) -> None:
    if not data:
        raise GuardError("empty file")
    if len(data) > MAX_IMAGE_BYTES:
        raise GuardError(f"image too large ({len(data)} > {MAX_IMAGE_BYTES})")
    if mime and mime.lower() not in ALLOWED_IMAGE_MIME:
        raise GuardError(f"unsupported image type: {mime}")


def check_audio(data: bytes, mime: str | None) -> None:
    if not data:
        raise GuardError("empty file")
    if len(data) > MAX_AUDIO_BYTES:
        raise GuardError(f"audio too large ({len(data)} > {MAX_AUDIO_BYTES})")
    if mime and mime.lower() not in ALLOWED_AUDIO_MIME:
        raise GuardError(f"unsupported audio type: {mime}")


def check_drug_name(name: str) -> str:
    if not name or not name.strip():
        raise GuardError("empty drug name")
    name = name.strip().lower()
    if len(name) > MAX_DRUG_NAME_LEN:
        raise GuardError("drug name too long")
    if not DRUG_NAME_RE.match(name):
        raise GuardError("drug name has invalid characters")
    return name


def check_lang(lang: str) -> str:
    if lang not in LANG_WHITELIST:
        raise GuardError(f"unsupported language: {lang}")
    return lang


def check_phone(phone: str) -> str:
    phone = (phone or "").replace(" ", "").replace("-", "")
    if not PHONE_RE.match(phone):
        raise GuardError("invalid phone (must be E.164, e.g. +91XXXXXXXXXX)")
    return phone


def check_utterance(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise GuardError("empty utterance")
    if len(text) > MAX_UTTERANCE_LEN:
        raise GuardError("utterance too long")
    # basic prompt-injection defusal: reject instructions that look like attempts
    lower = text.lower()
    banned = ("ignore previous", "system prompt", "you are now", "disregard the above")
    for b in banned:
        if b in lower:
            raise GuardError("utterance rejected by content guard")
    return text


# -----------------------------------------------------------------------------
# LLM output schema enforcement
# -----------------------------------------------------------------------------

def parse_json_strict(text: str, required_keys: list[str]) -> dict:
    """Extract the first {...} block and verify required keys exist."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        raise GuardError("model returned no JSON")
    try:
        obj = json.loads(text[start:end])
    except json.JSONDecodeError as e:
        raise GuardError(f"model returned invalid JSON: {e}")
    missing = [k for k in required_keys if k not in obj]
    if missing:
        raise GuardError(f"model output missing keys: {missing}")
    return obj


# -----------------------------------------------------------------------------
# Safety rules (hard fail-closed on medical content)
# -----------------------------------------------------------------------------

HARD_REFUSAL = {
    "suggest_new_dose": "I cannot suggest a different dose. Follow your doctor's prescription and ask a pharmacist if unsure.",
    "diagnose": "I cannot diagnose. Please see a doctor.",
    "substitute_class": "I cannot substitute a drug for a different molecule. Only a doctor or pharmacist can do that.",
}


def sanitize_explanation(text: str, drug_name: str, prescribed_dose: str) -> str:
    """Post-process LLM explanations. Refuses if model invented a dose or recommended substitution."""
    lower = text.lower()
    # detect dose-numeric patterns that weren't in the prescription
    dose_tokens = re.findall(r"\d+\s*(mg|mcg|g|ml|iu)", lower)
    prescribed_tokens = re.findall(r"\d+\s*(mg|mcg|g|ml|iu)", (prescribed_dose or "").lower())
    for d in dose_tokens:
        if d not in prescribed_tokens:
            # dose mentioned in output that isn't in the prescription — refuse
            return (
                f"{drug_name}: Follow the dose written on your prescription. "
                f"If unsure, ask your pharmacist. (Safety guard: model suggested an alternate dose.)"
            )
    # detect substitution language
    for bad in ("instead", "replace with", "better to take", "try taking"):
        if bad in lower:
            return f"{drug_name}: " + HARD_REFUSAL["substitute_class"]
    return text


def force_disclaimer(text: str, lang: str) -> str:
    disc_hi = "\n\n⚠ यह जानकारी केवल मदद के लिए है। डॉक्टर की सलाह ज़रूरी है।"
    disc_en = "\n\n⚠ Information only — not a substitute for a doctor."
    tail = disc_hi if lang.startswith("hi") or lang.startswith("ta") else disc_en
    return text.rstrip() + tail


def enforce_banned(drug_name: str, banned: bool, text: str) -> str:
    """If CDSCO banned, force a hard refusal regardless of what the LLM said."""
    if banned:
        return (
            f"⛔ {drug_name}: यह दवा सरकार द्वारा प्रतिबंधित है। न लें। "
            f"This drug is banned by CDSCO — do not take."
        )
    return text


# -----------------------------------------------------------------------------
# Rate limiting (in-process — swap to Redis/KV if you scale)
# -----------------------------------------------------------------------------

_rate_window: dict[str, deque] = defaultdict(lambda: deque(maxlen=120))


def check_rate(session_id: str, limit_per_min: int = 30) -> None:
    """Simple sliding window. Raises on throttle."""
    now = time.time()
    q = _rate_window[session_id]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit_per_min:
        raise GuardError(f"rate limit: {limit_per_min}/min exceeded for session")
    q.append(now)


# -----------------------------------------------------------------------------
# PII hygiene
# -----------------------------------------------------------------------------

def hash_pii(v: str) -> str:
    """One-way hash for audit logs. Never store raw phone or name."""
    return "sha256:" + hashlib.sha256((v or "").encode()).hexdigest()[:16]


def redact_for_log(obj: Any) -> Any:
    """Walk a dict/list and hash anything that smells like PII."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower()
            if any(p in kl for p in ("phone", "email", "name", "emergency")):
                out[k] = hash_pii(str(v))
            else:
                out[k] = redact_for_log(v)
        return out
    if isinstance(obj, list):
        return [redact_for_log(x) for x in obj]
    return obj


# -----------------------------------------------------------------------------
# Confidence thresholds for fuzzy match (drug name normalization)
# -----------------------------------------------------------------------------

FUZZY_MATCH_MIN = 85  # rapidfuzz ratio (0-100). Below this, don't match.


def accept_fuzzy(score: int) -> bool:
    return score >= FUZZY_MATCH_MIN


# -----------------------------------------------------------------------------
# Secret sanity (prevent deploying with placeholders)
# -----------------------------------------------------------------------------

PLACEHOLDER_MARKERS = ("PLACEHOLDER", "REPLACE_WITH", "XXXX", "your-key-here", "CHANGEME")


def ensure_no_placeholder(name: str, value: str | None) -> None:
    if not value:
        raise GuardError(f"secret {name} not set")
    for m in PLACEHOLDER_MARKERS:
        if m in value:
            raise GuardError(f"secret {name} still has placeholder value ({m})")


# -----------------------------------------------------------------------------
# Anti-hallucination: grounding, numeric guards, refusal thresholds
# -----------------------------------------------------------------------------

CONFIDENCE_REFUSAL_THRESHOLD = 0.45  # below this → refuse drug-specific Qs

def confidence_refuse(score: float) -> bool:
    """Return True iff retrieval confidence too low to answer reliably."""
    return score < CONFIDENCE_REFUSAL_THRESHOLD


_DRUG_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-\+]{3,}")
_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|microgram|milligram|gram|g|ml|millilitre|iu|tablet|tablets|capsule|capsules|times)\b", re.I)


def verify_grounded(answer: str, citations_text: str, *, allow_words: list[str] | None = None) -> tuple[bool, str]:
    """Check that every drug-shaped token in `answer` appears in citations_text or the
    allow_words list. Returns (ok, reason). ok=False means hallucination suspected.

    Allow-words normally include drug names that are explicitly in the user's query
    or profile so the model can refer to them.
    """
    citations_low = (citations_text or "").lower()
    allow = {w.lower() for w in (allow_words or [])}
    suspicious: list[str] = []
    for match in _DRUG_TOKEN_RE.findall(answer):
        token = match.lower()
        if token in allow:
            continue
        if token in citations_low:
            continue
        # Common English words / connectives are fine — only flag pharma-shaped tokens
        if len(token) >= 6 and (token.endswith(("cillin", "mycin", "olol", "pril", "sartan", "azole", "afenac", "feron", "tatin", "formin", "pram", "azepam", "olamine", "cetin", "cillin", "etamol", "pirtine"))):
            suspicious.append(token)
    if suspicious:
        return (False, f"suspected ungrounded drug tokens: {sorted(set(suspicious))[:5]}")
    return (True, "ok")


def verify_no_invented_numbers(answer: str, allowed_text: str) -> tuple[bool, str]:
    """Numbers with units (e.g. '500mg') in the answer must appear in the allowed_text
    (which is `prescribed_dose + retrieved citations + user_question`). Anything else
    is a fabricated dose."""
    allowed_low = (allowed_text or "").lower().replace(" ", "")
    bad: list[str] = []
    for num, unit in _NUMERIC_RE.findall(answer):
        token = (num + unit).lower().replace(" ", "")
        if token not in allowed_low:
            bad.append(f"{num}{unit}")
    if bad:
        return (False, f"answer mentions doses not in source: {sorted(set(bad))[:5]}")
    return (True, "ok")


def redact_or_refuse(answer: str, *, citations_text: str = "", allowed_text: str = "",
                     allow_words: list[str] | None = None,
                     refuse_template: str = "I don't have reliable information on that. Please ask your doctor or pharmacist.") -> tuple[str, list[str]]:
    """Run grounding + numeric guards; if either fails, return refusal text.
    Returns (final_answer, list_of_violations)."""
    violations: list[str] = []

    grounded_ok, why = verify_grounded(answer, citations_text, allow_words=allow_words)
    if not grounded_ok:
        violations.append(f"GROUNDING: {why}")

    numbers_ok, why = verify_no_invented_numbers(answer, allowed_text)
    if not numbers_ok:
        violations.append(f"NUMBERS: {why}")

    if violations:
        return (refuse_template, violations)
    return (answer, [])


def self_check_prompt(answer: str, citations_text: str, question: str) -> str:
    """Build a self-consistency prompt. Caller fires it through llm_client.chat
    and parses the JSON {grounded:bool, why:str}."""
    return f"""You are a fact-checker. Decide if the ANSWER is fully supported by the CONTEXT.
Return JSON only: {{"grounded": true_or_false, "why": "one short sentence"}}

QUESTION: {question}

CONTEXT (retrieved evidence):
{citations_text}

ANSWER:
{answer}
"""

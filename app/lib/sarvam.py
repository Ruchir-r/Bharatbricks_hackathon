"""Sarvam AI wrapper — ASR + Translate + TTS.

Caching (important for free-tier): TTS outputs are cached by sha256(text|lang) under
the UC Volume /Volumes/<catalog>/<schema>/audio_cache/. A repeated demo play is free.

Graceful degrade: `is_configured()` returns False when key is missing or still a
placeholder, so explainer/main can fall back to browser TTS.
"""

from __future__ import annotations
import base64
import hashlib
import os
import requests


BASE = "https://api.sarvam.ai"
PLACEHOLDER_MARKERS = ("PLACEHOLDER", "REPLACE_WITH", "XXXX", "your-key-here", "CHANGEME")


class SarvamUnavailable(RuntimeError):
    pass


def _resolve_key() -> str | None:
    from . import secrets_helper
    return secrets_helper.get("SARVAM_API_KEY", scope="rx-helper", key="sarvam-api-key")


def is_configured() -> bool:
    key = _resolve_key() or ""
    if not key:
        return False
    return not any(m in key for m in PLACEHOLDER_MARKERS)


def _headers():
    key = _resolve_key()
    if not key:
        raise SarvamUnavailable("SARVAM_API_KEY not set")
    return {"api-subscription-key": key}


def translate(text: str, target: str = "hi-IN", source: str = "en-IN") -> str:
    if target == source:
        return text
    r = requests.post(
        f"{BASE}/translate",
        headers=_headers(),
        json={
            "input": text,
            "source_language_code": source,
            "target_language_code": target,
            "speaker_gender": "Female",
            "mode": "formal",
            "enable_preprocessing": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("translated_text", text)


# ---------------------------------------------------------------------------
# TTS with UC-Volume cache. Key: sha256(text|lang).
# ---------------------------------------------------------------------------

def _cache_key(text: str, lang: str) -> str:
    return hashlib.sha256(f"{lang}|{text}".encode("utf-8")).hexdigest()


def _cache_path(key: str) -> str:
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    return f"/Volumes/{catalog}/{schema}/audio_cache/{key}.wav"


def _read_cache(key: str) -> bytes | None:
    p = _cache_path(key)
    try:
        with open(p, "rb") as f:
            return f.read()
    except Exception:
        return None


def _write_cache(key: str, data: bytes) -> None:
    try:
        p = _cache_path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    except Exception:
        # cache-miss write failure is non-fatal
        pass


def tts(text: str, language: str = "hi-IN", use_cache: bool = True) -> bytes:
    key = _cache_key(text, language)
    if use_cache:
        cached = _read_cache(key)
        if cached:
            return cached
    r = requests.post(
        f"{BASE}/text-to-speech",
        headers=_headers(),
        json={
            "inputs": [text],
            "target_language_code": language,
            "speaker": "anushka",
            "model": "bulbul:v2",
        },
        timeout=60,
    )
    r.raise_for_status()
    audio = base64.b64decode(r.json()["audios"][0])
    if use_cache:
        _write_cache(key, audio)
    return audio


def asr(audio_bytes: bytes, language: str = "hi-IN") -> str:
    r = requests.post(
        f"{BASE}/speech-to-text",
        headers=_headers(),
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"language_code": language, "model": "saarika:v2"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("transcript", "")

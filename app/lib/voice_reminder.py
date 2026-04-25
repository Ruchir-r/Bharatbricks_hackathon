"""Simple TTS automation: generate a 'take your medicine' voice clip on demand.

The clip can be played in-app (browser audio) AND queued as the message body
for a Bolna call. Cached on the UC volume by sha256(text|lang) so repeated
plays / repeated reminders cost zero Sarvam.

Three supported languages with hand-curated templates so the message is
natural-sounding (not awkward Sarvam-translation output).
"""

from __future__ import annotations
import base64
from . import sarvam


# Hand-curated reminder templates per language. {drug} and {dose} are interpolated.
TEMPLATES = {
    "en-IN": "Hello, this is your medicine reminder. It is time to take your {drug} {dose}. Please take it with water now. Thank you.",
    "hi-IN": "नमस्ते, यह आपकी दवाई की याददाश्त है। आपकी {drug} {dose} लेने का समय हो गया है। अभी पानी के साथ लीजिए। धन्यवाद।",
    "ml-IN": "നമസ്കാരം, ഇത് നിങ്ങളുടെ മരുന്ന് ഓർമ്മപ്പെടുത്തലാണ്. നിങ്ങളുടെ {drug} {dose} കഴിക്കാനുള്ള സമയമായി. ഇപ്പോൾ വെള്ളത്തോടൊപ്പം കഴിക്കുക. നന്ദി.",
}

DEFAULT_LANG = "en-IN"


def render_text(drug: str, dose: str, lang: str = DEFAULT_LANG) -> str:
    tmpl = TEMPLATES.get(lang) or TEMPLATES[DEFAULT_LANG]
    return tmpl.format(drug=(drug or "your medicine").strip(), dose=(dose or "").strip()).replace("  ", " ")


def synthesise(drug: str, dose: str, lang: str = DEFAULT_LANG) -> dict:
    """Returns {text, audio_b64, language, audio_source}.

    audio_source ∈ {sarvam (fresh API call or cache hit), none (no Sarvam configured)}.
    """
    text = render_text(drug, dose, lang=lang)
    if not sarvam.is_configured():
        return {"text": text, "audio_b64": None, "language": lang, "audio_source": "none"}
    try:
        # sarvam.tts already volume-caches by sha256(text|lang)
        audio = sarvam.tts(text, language=lang)
        return {
            "text": text,
            "audio_b64": base64.b64encode(audio).decode(),
            "language": lang,
            "audio_source": "sarvam",
        }
    except Exception as e:
        return {"text": text, "audio_b64": None, "language": lang,
                "audio_source": "none", "error": str(e)[:200]}

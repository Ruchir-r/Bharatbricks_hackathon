"""Plain-language drug explanation pipeline.

Flow: vector retrieval over CDSCO approved → Llama on Model Serving → optional Sarvam
translate + TTS. Gracefully degrades to text-only / English when Sarvam is unavailable.
"""

from databricks.vector_search.client import VectorSearchClient
from . import sarvam, llm_client
import os


def retrieve_context(drug_name: str, k: int = 3) -> list[str]:
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    try:
        vsc = VectorSearchClient()
        index = vsc.get_index(
            endpoint_name="hack_cdsco_endpoint",
            index_name=f"{catalog}.{schema}.cdsco_approved_idx",
        )
        res = index.similarity_search(
            query_text=drug_name,
            columns=["drug_name", "description", "indication", "dosage_guidance"],
            num_results=k,
        )
        rows = res.get("result", {}).get("data_array", []) or []
        return [f"{r[0]}: {r[1]} Indication: {r[2]}. Dosage guidance: {r[3]}." for r in rows if r and len(r) >= 4]
    except Exception:
        return []


PROMPT = """You are explaining a medicine to a rural Indian patient who may not read well.
Write MAXIMUM 3 short sentences in simple English:
1. What the medicine is for (plain words)
2. How to take it (with/without food, how many times)
3. One thing to watch for (side effect or caution)

Do not use medical jargon. Do not invent doses. Do not recommend alternate medicines.

Context from CDSCO:
{context}

Drug: {drug}
Patient's prescribed dose: {dose}
"""


def explain_english(drug: str, dose: str) -> str:
    context = "\n".join(retrieve_context(drug)) or "(no CDSCO context retrieved)"
    text = llm_client.chat(
        "databricks-meta-llama-3-3-70b-instruct",
        [{"role": "user", "content": PROMPT.format(context=context, drug=drug, dose=dose)}],
        max_tokens=220,
        temperature=0.2,
    )
    return text.strip()


def _pipeline_cache_path(drug: str, dose: str, language: str) -> str:
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    base = os.environ.get("CACHE_DIR", f"/Volumes/{catalog}/{schema}/audio_cache")
    import hashlib
    key = hashlib.sha256(f"{drug.lower().strip()}|{dose.lower().strip()}|{language}".encode()).hexdigest()
    return f"{base}/pipeline_{key}.json"


def _read_pipeline_cache(drug: str, dose: str, language: str) -> dict | None:
    import base64, json
    path = _pipeline_cache_path(drug, dose, language)
    try:
        with open(path) as f:
            obj = json.load(f)
        if "audio_b64" in obj and obj["audio_b64"]:
            obj["audio_bytes"] = base64.b64decode(obj["audio_b64"])
        else:
            obj["audio_bytes"] = None
        obj["audio_source"] = "cache"
        return obj
    except Exception:
        return None


def _write_pipeline_cache(drug: str, dose: str, language: str, payload: dict) -> None:
    import base64, json
    path = _pipeline_cache_path(drug, dose, language)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = {
            "english": payload["english"],
            "translated": payload["translated"],
            "language": payload["language"],
            "audio_b64": base64.b64encode(payload["audio_bytes"]).decode() if payload.get("audio_bytes") else None,
        }
        with open(path, "w") as f:
            json.dump(out, f)
    except Exception:
        pass


def explain_with_audio(drug: str, dose: str, language: str = "hi-IN", *, use_cache: bool = True) -> dict:
    """Full pipeline cache: cache hit returns instantly with zero external calls.

    audio_source ∈ {"cache", "sarvam", "browser"}.
    """
    if use_cache:
        cached = _read_pipeline_cache(drug, dose, language)
        if cached:
            return cached

    en = explain_english(drug, dose)

    if language == "en-IN":
        translated = en
    elif sarvam.is_configured():
        try:
            translated = sarvam.translate(en, target=language, source="en-IN")
        except Exception:
            translated = en
    else:
        translated = en

    audio: bytes | None = None
    source = "browser"
    if sarvam.is_configured():
        try:
            audio = sarvam.tts(translated, language=language)
            source = "sarvam"
        except Exception:
            audio = None
            source = "browser"

    payload = {
        "english": en,
        "translated": translated,
        "audio_bytes": audio,
        "audio_source": source,
        "language": language,
    }
    if use_cache:
        _write_pipeline_cache(drug, dose, language, payload)
    return payload

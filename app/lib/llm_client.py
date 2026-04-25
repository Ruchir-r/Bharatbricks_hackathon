"""Thin REST wrapper around Databricks Model Serving.

Bypasses databricks-sdk.WorkspaceClient.serving_endpoints.query() which has a
deserialisation bug ('dict' object has no attribute 'as_dict') on some SDK versions.

Direct REST is more reliable and the response shape is documented as OpenAI-style.
"""

from __future__ import annotations
import base64
import os
import requests


def _base_url() -> str:
    host = (os.environ.get("DATABRICKS_HOST") or "").rstrip("/")
    if not host:
        raise RuntimeError("DATABRICKS_HOST not set")
    return host


def _auth_header() -> dict:
    """Use SDK Config — works for PAT (local) AND OAuth (Apps SP) automatically."""
    try:
        from databricks.sdk.core import Config
        cfg = Config()
        h: dict = {}
        cfg.authenticate(h)
        return h
    except Exception:
        # last-ditch fallback: raw DATABRICKS_TOKEN
        tok = os.environ.get("DATABRICKS_TOKEN")
        return {"Authorization": f"Bearer {tok}"} if tok else {}


def chat(endpoint_name: str, messages: list[dict], *, max_tokens: int = 300, temperature: float = 0.2) -> str:
    """OpenAI-style chat completion against a Databricks serving endpoint.
    Returns the content string of the first choice.
    """
    url = f"{_base_url()}/serving-endpoints/{endpoint_name}/invocations"
    headers = _auth_header()
    headers["Content-Type"] = "application/json"
    r = requests.post(
        url,
        headers=headers,
        json={"messages": messages, "max_tokens": max_tokens, "temperature": temperature},
        timeout=90,
    )
    r.raise_for_status()
    body = r.json()
    return body["choices"][0]["message"]["content"]


def _detect_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # best-effort default


def chat_vision(endpoint_name: str, prompt: str, image_bytes: bytes, *, max_tokens: int = 1024) -> str:
    """Send a prompt + one image to a multimodal serving endpoint."""
    mime = _detect_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }
    ]
    return chat(endpoint_name, messages, max_tokens=max_tokens, temperature=0.0)

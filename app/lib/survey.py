"""Periodic chat-style check-in: asks patient how they're feeling, logs symptoms, flags severity."""

import os
import uuid
from datetime import datetime
from . import db, llm_client
import json


QUESTIONS_HI = [
    "क्या आपको दवा लेने के बाद चक्कर आया?",
    "क्या पेट में दर्द या जलन है?",
    "क्या कोई चकत्ते या खुजली है?",
    "क्या सांस लेने में दिक्कत है?",
]


def classify_symptom(patient_utterance: str) -> dict:
    """Returns {symptom, severity: 1-5, urgent: bool}."""
    prompt = f"""Classify this patient statement (Hindi or English) about how they feel after taking medicine.
Return JSON only:
{{"symptom":"one-word","severity":1_to_5,"urgent":true_or_false,"reply_hi":"one short empathetic Hindi sentence"}}

Statement: "{patient_utterance}"
"""
    text = llm_client.chat(
        "databricks-meta-llama-3-3-70b-instruct",
        [{"role": "user", "content": prompt}],
        max_tokens=160,
        temperature=0.0,
    )
    start, end = text.find("{"), text.rfind("}") + 1
    return json.loads(text[start:end])


def log_symptom(session_id: str, drug_name: str, symptom: str, severity: int) -> None:
    catalog = os.environ.get("CATALOG", "hack_cdsco")
    schema = os.environ.get("SCHEMA", "core")
    with db.connect() as c, c.cursor() as cur:
        cur.execute(
            f"INSERT INTO {catalog}.{schema}.side_effect_log VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, drug_name, symptom, severity, datetime.now()),
        )

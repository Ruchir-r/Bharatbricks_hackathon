"""Pairwise drug-drug interaction check + drug-diagnosis contraindication check.

Uses CDSCO FDC banned-combination list for hard blocks, then Llama for softer clinical reasoning.
"""

from itertools import combinations
from . import db, llm_client
import os
import json


def _conn():
    return db.connect()


def hard_block_pairs(drug_names: list[str]) -> list[dict]:
    """Returns pairs of drugs that appear together in CDSCO banned FDCs."""
    catalog = os.environ.get("CATALOG", "hack_cdsco")
    schema = os.environ.get("SCHEMA", "core")
    hits = []
    with _conn() as c, c.cursor() as cur:
        for a, b in combinations(drug_names, 2):
            cur.execute(
                f"""
                SELECT combination, ban_reason FROM {catalog}.{schema}.cdsco_banned
                WHERE lower(combination) LIKE lower(?) AND lower(combination) LIKE lower(?)
                LIMIT 1
                """,
                (f"%{a}%", f"%{b}%"),
            )
            row = cur.fetchone()
            if row:
                hits.append({"pair": [a, b], "combination": row[0], "reason": row[1]})
    return hits


def soft_check(drug_names: list[str], diagnosis: str | None) -> dict:
    """Returns LLM-reasoned clinical interaction + diagnosis-contraindication findings."""
    prompt = f"""You are a clinical-pharmacy assistant for rural Indian patients.
Given drugs: {drug_names}
Diagnosis (may be empty): {diagnosis or 'unknown'}

Respond JSON only:
{{
  "interactions": [
    {{"pair": ["drugA","drugB"], "severity": "low|moderate|high", "explanation": "one short sentence"}}
  ],
  "contraindications": [
    {{"drug": "...", "concern": "one short sentence"}}
  ],
  "recommend_second_opinion": true_or_false
}}"""
    text = llm_client.chat(
        "databricks-meta-llama-3-3-70b-instruct",
        [{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.1,
    )
    start, end = text.find("{"), text.rfind("}") + 1
    return json.loads(text[start:end])

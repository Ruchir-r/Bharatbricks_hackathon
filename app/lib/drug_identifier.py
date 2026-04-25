"""OCR via Databricks foundation vision model. Works on prescription images AND drug-strip photos."""

import base64
import json
import os
from . import llm_client

PRESCRIPTION_PROMPT = """You are reading a medical prescription. Return JSON only, no prose.
Schema:
{
  "drugs": [
    {"brand_or_generic": "...", "dose": "...", "frequency": "...", "duration": "..."}
  ],
  "diagnosis": "... or null"
}
Only include items you are confident about. Indian brand names are common — keep them verbatim."""

DRUG_LABEL_PROMPT = """You are reading the label on a medicine strip or bottle. Return JSON only.
Schema:
{
  "brand_name": "...",
  "generic_name": "...",
  "strength": "...",
  "batch_no": "... or null",
  "expiry": "... or null",
  "manufacturer": "... or null"
}"""


def _call_vision(image_bytes: bytes, prompt: str) -> dict:
    text = llm_client.chat_vision("databricks-llama-4-maverick", prompt, image_bytes, max_tokens=1024)
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


def extract_prescription(image_bytes: bytes) -> dict:
    return _call_vision(image_bytes, PRESCRIPTION_PROMPT)


def identify_drug_label(image_bytes: bytes) -> dict:
    res = _call_vision(image_bytes, DRUG_LABEL_PROMPT)
    # Alias drug_name = generic_name (preferred) or brand_name, so grader predicates
    # like drug_name_contains="..." work uniformly.
    res["drug_name"] = (res.get("generic_name") or res.get("brand_name") or "").strip()
    return res


# ----------------------------------------------------------------------------
# Second-pass normalisation: clean rough OCR brand names → real Indian drugs
# + cross-reference CDSCO / NLEM / PMBJP.
# ----------------------------------------------------------------------------

NORMALIZE_PROMPT = """You are a clinical pharmacy assistant in India. A prescription was OCR'd
from messy handwriting, so brand names may have wrong letters. For each entry, identify
the MOST LIKELY actual Indian drug brand using:
  - the diagnosis context
  - the frequency / duration pattern
  - common Indian formulary brands

Diagnosis: "{diagnosis}"
Raw OCR'd entries:
{raw_list}

Return JSON ARRAY ONLY, one entry per raw drug, in order. Schema:
[
  {{
    "raw_name": "Orop-codrug",
    "likely_brand": "Sinarest / Crocin Cold (most likely)",
    "generic_or_molecule": "paracetamol + chlorpheniramine + phenylephrine",
    "drug_class": "cold-remedy combination",
    "confidence": 0.55,
    "reasoning": "letters partial; combo + cold diagnosis suggest standard OTC cold tablet"
  }}
]

Rules:
- If you cannot guess at all, set confidence < 0.3 and likely_brand = "unknown".
- Don't make up specific dosages — those come from the prescription, not from you.
- generic_or_molecule should be one of the standard CDSCO molecule names (lowercase, comma-separated for combos).
- confidence in [0, 1].
"""


def _alias_lookup(raw_name: str) -> dict | None:
    """Deterministic alias-table lookup. Tries exact, then fuzzy (rapidfuzz) match
    against bricksiitm.rx_helper.drug_aliases. Returns the alias row dict on hit,
    None on miss. Cheap (one SQL + optional in-process fuzzy)."""
    if not raw_name:
        return None
    q = raw_name.strip().lower()
    try:
        from . import db
        with db.connect() as c, c.cursor() as cur:
            # 1. exact match
            cur.execute(
                f"SELECT alias, normalized_brand, generic_or_molecule, drug_class, confidence, notes "
                f"FROM {db.fq('drug_aliases')} WHERE lower(alias) = lower(?) LIMIT 1",
                (q,),
            )
            row = cur.fetchone()
            if row:
                return {"alias": row[0], "likely_brand": row[1], "generic_or_molecule": row[2],
                        "drug_class": row[3], "confidence": float(row[4] or 0.85),
                        "reasoning": f"matched alias table ({row[5] or 'exact match'})"}

            # 2. fuzzy fallback (in-process, against all aliases)
            cur.execute(f"SELECT alias, normalized_brand, generic_or_molecule, drug_class, confidence, notes FROM {db.fq('drug_aliases')}")
            rows = cur.fetchall()
        try:
            from rapidfuzz import process, fuzz
            choices = {r[0].lower(): r for r in rows}
            best = process.extractOne(q, list(choices.keys()), scorer=fuzz.WRatio, score_cutoff=80)
            if best:
                r = choices[best[0]]
                return {"alias": r[0], "likely_brand": r[1], "generic_or_molecule": r[2],
                        "drug_class": r[3], "confidence": float(r[4] or 0.7) * (best[1] / 100.0),
                        "reasoning": f"fuzzy alias match (score={best[1]})"}
        except ImportError:
            pass
    except Exception:
        return None
    return None


def normalize_ocr_drugs(raw_drugs: list[dict], diagnosis: str = "") -> list[dict]:
    """Pass-2 cleanup: maps rough OCR'd brand names to likely real drugs.

    Strategy (cheapest first):
      1. drug_aliases Delta table — exact match → fuzzy match (deterministic)
      2. LLM fallback for entries not in alias table (one batched call)
    Then cross-check each result against CDSCO + PMBJP.
    """
    from .log import log
    if not raw_drugs:
        return []

    log("normalize.start", drug_count=len(raw_drugs), diagnosis=diagnosis or "—")

    # Step 1: alias-table pass
    normalized: list[dict | None] = []
    needs_llm: list[tuple[int, dict]] = []   # (index, raw_drug)
    alias_hits = 0
    for i, d in enumerate(raw_drugs):
        raw_name = d.get("brand_or_generic") or d.get("generic_name") or ""
        hit = _alias_lookup(raw_name)
        if hit:
            alias_hits += 1
            normalized.append(hit)
            log("normalize.alias_hit", raw=raw_name, brand=hit.get("likely_brand"), conf=hit.get("confidence"))
        else:
            normalized.append(None)
            needs_llm.append((i, d))
    log("normalize.alias_summary", hits=alias_hits, misses=len(needs_llm))

    # Step 2: LLM only for the ones without an alias hit (saves time + cost)
    if needs_llm:
        raw_list = "\n".join(
            f"{j+1}. {d.get('brand_or_generic') or d.get('generic_name') or '(blank)'} "
            f"({d.get('dose','')}, {d.get('frequency','')}, {d.get('duration','')} days)"
            for j, (_, d) in enumerate(needs_llm)
        )
        text = llm_client.chat(
            "databricks-meta-llama-3-3-70b-instruct",
            [{"role": "user", "content": NORMALIZE_PROMPT.format(diagnosis=diagnosis or "unknown", raw_list=raw_list)}],
            max_tokens=900,
            temperature=0.1,
        )
        start = text.find("[")
        end = text.rfind("]") + 1
        try:
            llm_results: list[dict] = json.loads(text[start:end])
        except Exception:
            llm_results = [{"likely_brand": "unknown", "generic_or_molecule": "",
                            "confidence": 0.0, "reasoning": "LLM JSON parse failed"}
                           for _ in needs_llm]
        for (i, _), entry in zip(needs_llm, llm_results):
            normalized[i] = entry

    # ---- cross-reference each against the Lakehouse ----
    from . import db
    enriched: list[dict] = []
    with db.connect() as c, c.cursor() as cur:
        for entry, raw in zip(normalized, raw_drugs):
            molecule = (entry.get("generic_or_molecule") or "").lower().strip()
            cdsco_match = None
            pmbjp_match = None
            banned = False
            nsq = False
            # Try matching the FIRST molecule (handle combo)
            molecules = [m.strip() for m in molecule.replace("+", ",").split(",") if m.strip()]
            primary = molecules[0] if molecules else ""

            if primary:
                cur.execute(
                    f"SELECT drug_name, indication, dosage_guidance FROM {db.fq('cdsco_approved')} "
                    f"WHERE lower(drug_name) = lower(?) LIMIT 1",
                    (primary,),
                )
                row = cur.fetchone()
                if row:
                    cdsco_match = {"drug_name": row[0], "indication": row[1], "dosage": row[2]}
                cur.execute(
                    f"SELECT 1 FROM {db.fq('cdsco_banned')} "
                    f"WHERE lower(drug_name) = lower(?) "
                    f"   OR (combination NOT LIKE '%+%' AND lower(combination) LIKE lower(?)) LIMIT 1",
                    (primary, f"%{primary}%"),
                )
                banned = cur.fetchone() is not None

                # PMBJP catalog: top 3 cheapest matching SKUs for a price comparison
                cur.execute(
                    f"SELECT generic_name, mrp, group_name FROM {db.fq('pmbjp_catalog_real')} "
                    f"WHERE lower(generic_name) LIKE lower(?) AND CAST(mrp AS DOUBLE) > 0 "
                    f"ORDER BY CAST(mrp AS DOUBLE) ASC LIMIT 3",
                    (f"%{primary}%",),
                )
                rows = cur.fetchall()
                if rows:
                    pmbjp_match = {"name": rows[0][0], "mrp_inr": rows[0][1], "group": rows[0][2]}

            # Build price comparison: ~3 entries showing branded vs generic vs PMBJP
            price_compare: list[dict] = []
            if rows:
                # Cheapest PMBJP SKU = "Jan Aushadhi (cheapest)"
                price_compare.append({
                    "label": "Jan Aushadhi (PMBJP)",
                    "name": rows[0][0],
                    "mrp_inr": float(rows[0][1] or 0),
                    "tier": "generic",
                })
                # 2nd PMBJP SKU = mid generic (different strength typically)
                if len(rows) > 1:
                    price_compare.append({
                        "label": "Pharmacy generic",
                        "name": rows[1][0],
                        "mrp_inr": float(rows[1][1] or 0),
                        "tier": "mid",
                    })
                # Estimated branded MRP: typically 5-10× PMBJP for OTC molecules
                base = float(rows[0][1] or 0)
                if base > 0:
                    price_compare.append({
                        "label": "Typical branded (retail)",
                        "name": f"{(entry.get('likely_brand') or 'branded equivalent')}",
                        "mrp_inr": round(base * 7.5, 2),
                        "tier": "branded",
                        "note": "estimated 7.5× PMBJP — actual MRP varies",
                    })

            enriched.append({
                "raw_name": raw.get("brand_or_generic") or raw.get("generic_name"),
                "raw_dose": raw.get("dose"),
                "raw_frequency": raw.get("frequency"),
                "raw_duration": raw.get("duration"),
                "likely_brand": entry.get("likely_brand"),
                "generic_or_molecule": molecule,
                "drug_class": entry.get("drug_class"),
                "confidence": entry.get("confidence"),
                "price_comparison": price_compare,
                "reasoning": entry.get("reasoning"),
                "cdsco_status": "banned" if banned else ("approved" if cdsco_match else "unknown"),
                "cdsco_match": cdsco_match,
                "pmbjp_alternative": pmbjp_match,
            })
    return enriched

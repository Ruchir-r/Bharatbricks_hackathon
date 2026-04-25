"""Multi-source retrieval for grounded answers.

Pulls evidence from EVERY relevant Delta table for a drug and returns it as a list
of structured citations:
    [{table, row_pk, snippet, score}]

The downstream LLM is required to ground every claim against this list (see
guards.verify_grounded). Anything that can't be cited is redacted.

Data sources (in order of priority):
  1. cdsco_approved      — official approval, indication, dosage_guidance
  2. cdsco_banned        — gov ban / withdrawal records
  3. cdsco_nsq_alerts    — recent batch quality failures
  4. drug_sources        — provenance citations (NLEM, gazette, PMBJP)
  5. nlem_essential      — essentiality + level of use
  6. pmbjp_prices        — Jan Aushadhi generic + savings
  7. drug_food           — food/alcohol/lactation interactions  (NEW)
  8. govt_schemes        — Ayushman / PMJAY-relevant entries     (NEW)
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
from . import db


@dataclass
class Citation:
    table: str
    row_pk: str
    snippet: str
    score: float = 1.0  # 0.0–1.0; SQL exact match is 1.0; VS retrieved gets its actual score

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_brand_to_molecule(drug_name: str, cur) -> tuple[str, list[str]]:
    """Brand name → primary molecule using drug_aliases. Returns (primary_molecule, all_brands_with_same_molecule).

    If `drug_name` is already a generic molecule (no alias hit), returns (drug_name, []).
    Falls back gracefully if drug_aliases table is missing.
    """
    drug = (drug_name or "").strip().lower()
    if not drug:
        return ("", [])
    try:
        cur.execute(
            f"SELECT generic_or_molecule, normalized_brand FROM {db.fq('drug_aliases')} "
            f"WHERE lower(alias) = lower(?) OR lower(normalized_brand) = lower(?) LIMIT 1",
            (drug, drug),
        )
        row = cur.fetchone()
    except Exception:
        return (drug, [])
    if not row:
        return (drug, [])
    molecule = (row[0] or drug).split("+")[0].strip().lower()
    # Find other brand names with the same molecule
    try:
        cur.execute(
            f"SELECT DISTINCT normalized_brand FROM {db.fq('drug_aliases')} "
            f"WHERE lower(generic_or_molecule) LIKE lower(?) ORDER BY normalized_brand LIMIT 8",
            (f"%{molecule}%",),
        )
        sibling_brands = [r[0] for r in cur.fetchall() if r[0] and r[0].lower() != drug]
    except Exception:
        sibling_brands = []
    return (molecule, sibling_brands)


def retrieve_for_drug(drug_name: str, *, limit_per_table: int = 3) -> list[Citation]:
    """Returns evidence rows from every table that mentions this drug.

    Step 0: brand → molecule translation via drug_aliases (so "Crocin Cold" → "paracetamol")
    Steps 1-7: query each Delta table for the molecule.
    """
    drug_in = (drug_name or "").strip().lower()
    if not drug_in:
        return []

    cites: list[Citation] = []
    with db.connect() as c, c.cursor() as cur:
        # Step 0: brand → molecule
        molecule, sibling_brands = _resolve_brand_to_molecule(drug_in, cur)
        # Use the resolved molecule for all subsequent queries
        drug = molecule or drug_in
        if molecule and molecule != drug_in:
            cites.append(Citation("drug_aliases", drug_in,
                f"Brand '{drug_in}' resolved to molecule '{molecule}'. Equivalent brands: {', '.join(sibling_brands[:5]) or '(none in alias table)'}.",
                0.95))
        # 1. CDSCO approved
        cur.execute(
            f"SELECT drug_name, indication, dosage_guidance, description "
            f"FROM {db.fq('cdsco_approved')} WHERE lower(drug_name) = lower(?) LIMIT ?",
            (drug, limit_per_table),
        )
        for r in cur.fetchall():
            cites.append(Citation("cdsco_approved", r[0],
                f"Indication: {r[1]}. Dosage: {r[2]}. {r[3] or ''}".strip(), 1.0))

        # 2. CDSCO banned (exact OR single-component combination)
        cur.execute(
            f"SELECT drug_name, combination, ban_reason, ban_date FROM {db.fq('cdsco_banned')} "
            f"WHERE lower(drug_name) = lower(?) OR (combination NOT LIKE '%+%' AND lower(combination) LIKE lower(?)) "
            f"LIMIT ?",
            (drug, f"%{drug}%", limit_per_table),
        )
        for r in cur.fetchall():
            cites.append(Citation("cdsco_banned", r[0],
                f"BANNED: {r[1] or r[0]}. Reason: {r[2]}. Date: {r[3]}.", 1.0))

        # 3. NSQ recent batches (any in last 12mo, not gated by batch_no for context)
        cur.execute(
            f"SELECT batch_no, manufacturer, alert_date, reason FROM {db.fq('cdsco_nsq_alerts')} "
            f"WHERE lower(drug_name) = lower(?) AND alert_date >= current_date() - INTERVAL 12 MONTHS "
            f"LIMIT ?",
            (drug, limit_per_table),
        )
        for r in cur.fetchall():
            cites.append(Citation("cdsco_nsq_alerts", str(r[0]),
                f"NSQ batch {r[0]} from {r[1]} on {r[2]}: {r[3]}.", 0.9))

        # 4. drug_sources (provenance / authoritative citations)
        cur.execute(
            f"SELECT drug_name, source_type, source_ref, source_url, verified "
            f"FROM {db.fq('drug_sources')} WHERE lower(drug_name) = lower(?) LIMIT ?",
            (drug, limit_per_table),
        )
        for r in cur.fetchall():
            cites.append(Citation("drug_sources", r[0],
                f"{r[1]} ref: {r[2]}. URL: {r[3]}. Verified: {r[4]}.", 0.95 if r[4] == 'yes' else 0.6))

        # 5. NLEM essentiality — try real-extract table first, fall back to curated
        nlem_hit = False
        try:
            cur.execute(
                f"SELECT section, drug_name, level_p, level_s, level_t, dosage_forms "
                f"FROM {db.fq('nlem_2022_real')} WHERE lower(drug_name) LIKE lower(?) LIMIT ?",
                (f"%{drug}%", limit_per_table),
            )
            for r in cur.fetchall():
                lvls = ",".join(x for x, on in [("P", r[2]), ("S", r[3]), ("T", r[4])] if str(on).lower() in ("true","1","yes"))
                cites.append(Citation("nlem_2022_real", f"{r[0]}/{r[1]}",
                    f"NLEM 2022 §{r[0]} {r[1]} (level {lvls or '?'}). Forms: {r[5]}.", 0.95))
                nlem_hit = True
        except Exception:
            pass
        if not nlem_hit:
            cur.execute(
                f"SELECT drug_name, category, level_of_use, dosage_forms, notes "
                f"FROM {db.fq('nlem_essential')} WHERE lower(drug_name) = lower(?) LIMIT ?",
                (drug, limit_per_table),
            )
            for r in cur.fetchall():
                cites.append(Citation("nlem_essential", r[0],
                    f"NLEM essential. Category: {r[1]}. Level: {r[2]}. Forms: {r[3]}. {r[4] or ''}".strip(), 0.9))

        # 6. PMBJP price — try real catalog (2438 entries) first, fall back to synthetic
        pmbjp_hit = False
        try:
            cur.execute(
                f"SELECT drug_code, generic_name, unit_size, mrp, group_name "
                f"FROM {db.fq('pmbjp_catalog_real')} WHERE lower(generic_name) LIKE lower(?) "
                f"ORDER BY mrp ASC LIMIT ?",
                (f"%{drug}%", limit_per_table),
            )
            for r in cur.fetchall():
                cites.append(Citation("pmbjp_catalog_real", str(r[0]),
                    f"Jan Aushadhi: {r[1]} ({r[2]}): MRP Rs.{r[3]}. Group: {r[4]}. (real PMBJP catalog code {r[0]})", 0.95))
                pmbjp_hit = True
        except Exception:
            pass
        if not pmbjp_hit:
            cur.execute(
                f"SELECT generic_name, strength, mrp_inr, typical_branded_mrp_inr, pmbjp_code "
                f"FROM {db.fq('pmbjp_prices')} WHERE lower(generic_name) = lower(?) LIMIT ?",
                (drug, limit_per_table),
            )
            for r in cur.fetchall():
                cites.append(Citation("pmbjp_prices", r[4],
                    f"Jan Aushadhi generic {r[0]} {r[1]}: MRP Rs.{r[2]} vs branded Rs.{r[3]} (code {r[4]}).", 0.85))

        # 7. drug_food (new — soft-fail if table missing)
        try:
            cur.execute(
                f"SELECT drug_name, food_or_substance, recommendation, severity "
                f"FROM {db.fq('drug_food')} WHERE lower(drug_name) = lower(?) LIMIT ?",
                (drug, limit_per_table),
            )
            for r in cur.fetchall():
                cites.append(Citation("drug_food", f"{r[0]}|{r[1]}",
                    f"Food/substance interaction with {r[1]}: {r[2]} (severity {r[3]}).", 0.8))
        except Exception:
            pass

    return cites


def retrieve_for_drugs(drug_names: list[str], *, limit_per_table: int = 2) -> dict[str, list[Citation]]:
    """Bulk version. Returns drug_name → citations. Cheap in SQL (one connection)."""
    out: dict[str, list[Citation]] = {}
    for d in drug_names:
        out[d] = retrieve_for_drug(d, limit_per_table=limit_per_table)
    return out


def confidence_score(citations: list[Citation]) -> float:
    """0.0 (no evidence) → 1.0 (high-quality CDSCO citations). Used for refusal threshold."""
    if not citations:
        return 0.0
    # Top citation's score, scaled by how many corroborating sources we have
    top = max(c.score for c in citations)
    diversity = min(len({c.table for c in citations}) / 4.0, 1.0)
    return min(1.0, top * (0.6 + 0.4 * diversity))


def fmt_for_prompt(citations: list[Citation]) -> str:
    """Render the citations into prompt context the LLM can ground against."""
    if not citations:
        return "(no evidence retrieved — refuse to answer drug-specific questions)"
    lines = []
    for i, c in enumerate(citations, 1):
        lines.append(f"[E{i}] ({c.table}/{c.row_pk}, score={c.score:.2f}) {c.snippet}")
    return "\n".join(lines)


def schemes_for(diagnosis: str, state: str | None = None) -> list[Citation]:
    """Return govt-scheme rows that could cover this diagnosis."""
    diag = (diagnosis or "").strip().lower()
    if not diag:
        return []
    cites: list[Citation] = []
    try:
        with db.connect() as c, c.cursor() as cur:
            cur.execute(
                f"SELECT scheme_name, eligibility, benefits, applicable_states, source_url "
                f"FROM {db.fq('govt_schemes')} "
                f"WHERE lower(covered_conditions) LIKE lower(?) "
                f"   OR lower(covered_conditions) LIKE lower(?) "
                f"LIMIT 5",
                (f"%{diag}%", "%any%"),
            )
            for r in cur.fetchall():
                applicable = (r[3] or "").lower()
                if state and applicable not in ("all-india", "any") and (state.lower() not in applicable):
                    continue
                cites.append(Citation("govt_schemes", r[0],
                    f"{r[0]}. Eligibility: {r[1]}. Benefits: {r[2]}. URL: {r[4]}.", 0.9))
    except Exception:
        pass
    return cites


def pharmacies_near(lat: float, lon: float, *, limit: int = 5) -> list[dict]:
    """Return nearest Jan Aushadhi (PMBJP) stores within ~50km. Pure SQL distance."""
    try:
        with db.connect() as c, c.cursor() as cur:
            # Haversine via SQL — cheap on a small table
            cur.execute(
                f"""
                SELECT name, address, district, state, phone, lat, lon,
                  6371 * 2 * asin(sqrt(
                    pow(sin(radians(lat - ?) / 2), 2)
                    + cos(radians(?)) * cos(radians(lat))
                    * pow(sin(radians(lon - ?) / 2), 2)
                  )) AS distance_km
                FROM {db.fq('pmbjp_locations')}
                ORDER BY distance_km
                LIMIT ?
                """,
                (lat, lat, lon, limit),
            )
            return [
                {"name": r[0], "address": r[1], "district": r[2], "state": r[3],
                 "phone": r[4], "lat": float(r[5]), "lon": float(r[6]),
                 "distance_km": round(float(r[7]), 1)}
                for r in cur.fetchall()
            ]
    except Exception:
        return []

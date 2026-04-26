"""High-value secondary features for the Dawa Dost app.

Each function is intentionally small + composable. The HTTP layer in main.py wires
them to /api/* endpoints; demo fallbacks live in static/fallbacks.js.

Modules covered:
  - refill_alert       : days_remaining computation from drug_timetable
  - food_warnings      : per-drug food/alcohol/dairy interactions
  - scheme_eligibility : Ayushman / RAN / state-scheme finder
  - pharmacy_locator   : nearest Jan Aushadhi by lat/lon
  - care_card          : printable HTML summary for caregivers
  - savings_summary    : how much the patient saves with PMBJP generics
"""

from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Any
from . import db, profile, rag


# -----------------------------------------------------------------------------
# 1. Refill alert
# -----------------------------------------------------------------------------

def refill_alert(session_id: str, *, threshold_days: int = 3) -> list[dict]:
    """For each medicine on file, compute days remaining and flag if <= threshold."""
    entries = profile.get_timetable(session_id)
    today = date.today()
    out: list[dict] = []
    for e in entries:
        try:
            start = datetime.fromisoformat(e["start_date"]).date() if isinstance(e["start_date"], str) else e["start_date"]
        except Exception:
            start = today
        end = start + timedelta(days=int(e.get("duration_days") or 0))
        days_remaining = (end - today).days
        out.append({
            "drug_name": e["drug_name"],
            "dose": e.get("dose"),
            "duration_days": e.get("duration_days"),
            "start_date": str(start),
            "ends_on": str(end),
            "days_remaining": days_remaining,
            "needs_refill": days_remaining <= threshold_days,
        })
    return out


# -----------------------------------------------------------------------------
# 2. Food / alcohol warnings
# -----------------------------------------------------------------------------

def food_warnings(drug_name: str) -> list[dict]:
    drug = (drug_name or "").strip().lower()
    if not drug:
        return []
    rows: list[dict] = []
    try:
        with db.connect() as c, c.cursor() as cur:
            cur.execute(
                f"SELECT food_or_substance, recommendation, severity, note "
                f"FROM {db.fq('drug_food')} WHERE lower(drug_name) = lower(?) "
                f"ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END",
                (drug,),
            )
            for r in cur.fetchall():
                rows.append({
                    "with": r[0], "advice": r[1], "severity": r[2],
                    "note": (r[3] or "").strip() or None,
                })
    except Exception:
        pass
    return rows


def food_warnings_for_session(session_id: str) -> list[dict]:
    """Aggregate warnings across all medicines for a patient."""
    entries = profile.get_timetable(session_id)
    out: list[dict] = []
    for e in entries:
        warnings = food_warnings(e["drug_name"])
        if warnings:
            out.append({"drug_name": e["drug_name"], "warnings": warnings})
    return out


# -----------------------------------------------------------------------------
# 3. Govt-scheme eligibility
# -----------------------------------------------------------------------------

def scheme_eligibility(diagnosis: str, *, state: str | None = None) -> list[dict]:
    cites = rag.schemes_for(diagnosis, state=state)
    out: list[dict] = []
    for c in cites:
        out.append({
            "scheme": c.row_pk,
            "details": c.snippet,
        })
    # Always include PM-JAY as universal fallback if nothing else matched
    if not out:
        try:
            with db.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT scheme_name, eligibility, benefits, helpline, source_url "
                    f"FROM {db.fq('govt_schemes')} WHERE scheme_name = ?",
                    ("Ayushman Bharat PM-JAY",),
                )
                row = cur.fetchone()
                if row:
                    out.append({
                        "scheme": row[0],
                        "details": f"Eligibility: {row[1]}. Benefits: {row[2]}. Helpline: {row[3]}. URL: {row[4]}.",
                    })
        except Exception:
            pass
    return out


# -----------------------------------------------------------------------------
# 4. Pharmacy locator (Jan Aushadhi)
# -----------------------------------------------------------------------------

def pharmacies_near(lat: float, lon: float, *, limit: int = 5) -> list[dict]:
    return rag.pharmacies_near(lat, lon, limit=limit)


# -----------------------------------------------------------------------------
# 5. Savings summary (PMBJP generic vs branded)
# -----------------------------------------------------------------------------

def savings_summary(session_id: str) -> dict:
    """For the patient's medicines, estimate monthly savings if they switch to PMBJP."""
    entries = profile.get_timetable(session_id)
    total_branded = 0.0
    total_generic = 0.0
    breakdown: list[dict] = []

    if not entries:
        return {"breakdown": [], "monthly_branded": 0, "monthly_generic": 0, "monthly_savings": 0}

    drug_names = [e["drug_name"].lower() for e in entries]
    placeholders = ",".join(["?"] * len(drug_names))
    prices: dict[str, dict] = {}
    try:
        with db.connect() as c, c.cursor() as cur:
            cur.execute(
                f"SELECT lower(generic_name), mrp_inr, typical_branded_mrp_inr "
                f"FROM {db.fq('pmbjp_prices')} WHERE lower(generic_name) IN ({placeholders})",
                tuple(drug_names),
            )
            for r in cur.fetchall():
                prices[r[0]] = {"mrp": float(r[1]), "branded": float(r[2])}
    except Exception:
        prices = {}

    for e in entries:
        name = e["drug_name"].lower()
        # rough monthly tablet count: doses-per-day × 30
        dpd = max(len(e.get("times_of_day") or []), 1)
        monthly_tabs = dpd * 30
        p = prices.get(name)
        b = (p or {"branded": 0})["branded"] * monthly_tabs / 10  # MRPs are per-tab so /10 is for strip
        g = (p or {"mrp": 0})["mrp"] * monthly_tabs / 10
        breakdown.append({
            "drug_name": e["drug_name"],
            "monthly_doses": monthly_tabs,
            "branded_per_month": round(b, 2),
            "generic_per_month": round(g, 2),
            "savings": round(b - g, 2),
            "has_pmbjp_match": p is not None,
        })
        total_branded += b
        total_generic += g

    return {
        "breakdown": breakdown,
        "monthly_branded": round(total_branded, 2),
        "monthly_generic": round(total_generic, 2),
        "monthly_savings": round(total_branded - total_generic, 2),
    }


# -----------------------------------------------------------------------------
# 6. Care card (printable HTML)
# -----------------------------------------------------------------------------

CARE_CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Care Card</title>
<style>
 body {{ font-family: 'Noto Sans Devanagari','Helvetica',sans-serif; padding: 20px; max-width: 600px; margin: auto; color: #0f172a; }}
 h1 {{ color: #1565c0; border-bottom: 3px solid #1565c0; padding-bottom: 6px; }}
 h2 {{ color: #2e7d32; margin-top: 18px; }}
 .info {{ background: #e3f2fd; padding: 10px; border-radius: 8px; margin-bottom: 10px; }}
 .med {{ border-left: 4px solid #1565c0; padding: 6px 12px; margin: 8px 0; background: #f5fafd; }}
 .warn {{ border-left: 4px solid #c62828; padding: 6px 12px; margin: 8px 0; background: #ffebee; }}
 .footer {{ margin-top: 28px; font-size: 0.85em; color: #475569; border-top: 1px dashed #ccc; padding-top: 8px; }}
</style></head><body>
<h1>Care Card · देखभाल कार्ड</h1>
<div class="info">
  <strong>{name}</strong><br>
  Phone · फ़ोन: {phone}<br>
  Emergency · आपातकालीन: {emergency}<br>
  Generated · जारी: {today}
</div>

<h2>Medicines · दवाइयाँ</h2>
{meds_html}

{warnings_html}

<h2>Emergency · आपात</h2>
<div class="info">
 If serious — call 108 (ambulance) or 102 (women/child).<br>
 गंभीर हो तो — 108 (एम्बुलेंस) या 102 (महिला/बच्चे) पर कॉल कीजिए।
</div>

<div class="footer">
 ⚠ Information only — not a substitute for a doctor.<br>
 यह जानकारी केवल मदद के लिए है। डॉक्टर की सलाह ज़रूरी है।
</div>
</body></html>"""


def care_card_html(session_id: str) -> str:
    summary = profile.summary(session_id)
    sess = summary["session"] or {}
    meds = summary["medicines"]
    meds_html_parts = []
    warn_parts = []
    for e in meds:
        times = ", ".join(e.get("times_of_day") or ["as needed"]) or "—"
        meds_html_parts.append(
            f'<div class="med"><strong>💊 {e["drug_name"]}</strong> {e.get("dose","")}<br>'
            f'<small>Times: {times} · Duration: {e.get("duration_days") or "?"} days</small></div>'
        )
        for w in food_warnings(e["drug_name"]):
            if w["severity"] == "high":
                warn_parts.append(
                    f'<div class="warn"><strong>⚠ {e["drug_name"]} + {w["with"]}</strong>: {w["advice"]}</div>'
                )
    warnings_html = ("<h2>Important warnings · ज़रूरी सावधानी</h2>" + "\n".join(warn_parts)) if warn_parts else ""
    return CARE_CARD_HTML.format(
        name=sess.get("patient_name") or "Patient",
        phone=sess.get("phone") or "—",
        emergency=sess.get("emergency_contact_phone") or "—",
        today=date.today().isoformat(),
        meds_html="\n".join(meds_html_parts) or "<p>No medicines on file.</p>",
        warnings_html=warnings_html,
    )

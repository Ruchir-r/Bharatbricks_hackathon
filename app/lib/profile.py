"""Patient profile reads — medicines on file, next dose, recent check-ins.

All queries run against Delta via the app service principal.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date
import os
from . import db


def _conn():
    return db.connect()


def _fq(table: str) -> str:
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    return f"{catalog}.{schema}.{table}"


def get_session(session_id: str) -> dict | None:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT session_id, patient_name, phone, preferred_language, emergency_contact_phone, created_at "
            f"FROM {_fq('patient_sessions')} WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        # Hard-coded: this build's demo session has Dr. Saab as the SOS contact.
        # In production, this would be a separate column in patient_sessions.
        contact_name = "Dr. Saab" if row[4] == "+919074839967" else None
        return {
            "session_id": row[0],
            "patient_name": row[1],
            "phone": row[2],
            "preferred_language": row[3],
            "emergency_contact_phone": row[4],
            "emergency_contact_name": contact_name,
            "created_at": str(row[5]) if row[5] else None,
        }


def get_timetable(session_id: str) -> list[dict]:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT entry_id, drug_name, dose, times_of_day, duration_days, start_date "
            f"FROM {_fq('drug_timetable')} WHERE session_id = ? ORDER BY drug_name",
            (session_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "entry_id": r[0],
            "drug_name": r[1],
            "dose": r[2],
            "times_of_day": list(r[3]) if r[3] else [],
            "duration_days": r[4],
            "start_date": str(r[5]) if r[5] else None,
        }
        for r in rows
    ]


def get_recent_checkins(session_id: str, limit: int = 5) -> list[dict]:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT drug_name, symptom, severity, logged_at FROM {_fq('side_effect_log')} "
            f"WHERE session_id = ? ORDER BY logged_at DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cur.fetchall()
    return [
        {"drug_name": r[0], "symptom": r[1], "severity": r[2], "logged_at": str(r[3])}
        for r in rows
    ]


def compute_next_dose(entries: list[dict]) -> dict | None:
    """From timetable entries, find the single next dose time within 24h."""
    now = datetime.now()
    soonest: tuple[datetime, dict] | None = None
    for e in entries:
        for t in e.get("times_of_day") or []:
            try:
                hh, mm = map(int, t.split(":"))
            except Exception:
                continue
            for day_offset in (0, 1):
                candidate = datetime.combine(now.date() + timedelta(days=day_offset), datetime.min.time()).replace(hour=hh, minute=mm)
                if candidate >= now:
                    if soonest is None or candidate < soonest[0]:
                        soonest = (candidate, e)
                    break
    if soonest is None:
        return None
    when, e = soonest
    mins = int((when - now).total_seconds() // 60)
    return {
        "drug_name": e["drug_name"],
        "dose": e["dose"],
        "at": when.isoformat(timespec="minutes"),
        "minutes_from_now": mins,
    }


def summary(session_id: str) -> dict:
    sess = get_session(session_id) or {"session_id": session_id, "patient_name": None}
    entries = get_timetable(session_id)
    return {
        "session": sess,
        "medicines": entries,
        "next_dose": compute_next_dose(entries),
        "recent_checkins": get_recent_checkins(session_id),
    }

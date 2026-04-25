"""Build a take-medicine timetable from extracted prescription rows, persist to Delta."""

import uuid
from datetime import date, datetime, timedelta
from . import db
import os


FREQUENCY_TO_TIMES = {
    "once daily": ["08:00"],
    "od": ["08:00"],
    "twice daily": ["08:00", "20:00"],
    "bd": ["08:00", "20:00"],
    "bid": ["08:00", "20:00"],
    "thrice daily": ["08:00", "14:00", "20:00"],
    "tds": ["08:00", "14:00", "20:00"],
    "tid": ["08:00", "14:00", "20:00"],
    "four times daily": ["08:00", "12:00", "16:00", "20:00"],
    "qid": ["08:00", "12:00", "16:00", "20:00"],
    "sos": [],
    "prn": [],
}


def _duration_days(text: str) -> int:
    text = (text or "").lower()
    if "week" in text:
        num = int("".join(c for c in text if c.isdigit()) or 1)
        return num * 7
    if "day" in text:
        return int("".join(c for c in text if c.isdigit()) or 5)
    return 5


def build(session_id: str, drugs: list[dict]) -> list[dict]:
    entries = []
    for d in drugs:
        freq = (d.get("frequency") or "").lower().strip()
        times = FREQUENCY_TO_TIMES.get(freq, ["08:00", "20:00"])
        entries.append(
            {
                "entry_id": str(uuid.uuid4()),
                "session_id": session_id,
                "drug_name": d.get("brand_or_generic", ""),
                "dose": d.get("dose", ""),
                "times_of_day": times,
                "duration_days": _duration_days(d.get("duration", "")),
                "start_date": date.today().isoformat(),
            }
        )
    return entries


def persist(entries: list[dict]) -> None:
    catalog = os.environ.get("CATALOG", "hack_cdsco")
    schema = os.environ.get("SCHEMA", "core")
    with db.connect() as c, c.cursor() as cur:
        for e in entries:
            cur.execute(
                f"""INSERT INTO {catalog}.{schema}.drug_timetable VALUES (?,?,?,?,?,?,?)""",
                (
                    e["entry_id"],
                    e["session_id"],
                    e["drug_name"],
                    e["dose"],
                    e["times_of_day"],
                    e["duration_days"],
                    e["start_date"],
                ),
            )


def upcoming_dose_times(entries: list[dict], horizon_hours: int = 24) -> list[tuple[datetime, dict]]:
    now = datetime.now()
    horizon = now + timedelta(hours=horizon_hours)
    out = []
    for e in entries:
        for t in e["times_of_day"]:
            hh, mm = map(int, t.split(":"))
            for day_offset in range(0, max(1, horizon_hours // 24 + 1)):
                d = now.date() + timedelta(days=day_offset)
                dt = datetime.combine(d, datetime.min.time()).replace(hour=hh, minute=mm)
                if now <= dt <= horizon:
                    out.append((dt, e))
    return sorted(out, key=lambda x: x[0])

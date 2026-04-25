"""SOS: SMS + call to pre-registered emergency contact with geolocation link."""

import os
import uuid
from datetime import datetime
from . import db, reminder


def trigger(
    session_id: str,
    patient_name: str,
    emergency_phone: str,
    lat: float | None = None,
    lon: float | None = None,
    note: str = "",
) -> dict:
    loc = f"https://maps.google.com/?q={lat},{lon}" if lat and lon else "location unknown"
    body = (
        f"EMERGENCY: {patient_name} needs help. "
        f"{'Note: ' + note + '. ' if note else ''}"
        f"Location: {loc}"
    )
    sms_sid = reminder.place_sms(emergency_phone, body)
    call_sid = reminder.place_call(
        emergency_phone,
        f"Emergency. {patient_name} needs help. Check SMS for location.",
        language="en-IN",
    )

    _log(session_id, loc, emergency_phone)
    return {"sms_sid": sms_sid, "call_sid": call_sid, "location": loc}


def _log(session_id: str, location: str, contact: str) -> None:
    catalog = os.environ.get("CATALOG", "hack_cdsco")
    schema = os.environ.get("SCHEMA", "core")
    with db.connect() as c, c.cursor() as cur:
        cur.execute(
            f"INSERT INTO {catalog}.{schema}.sos_events VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, location, datetime.now(), contact),
        )

"""Spaced Bolna test — runs 3 calls 5 minutes apart so the line isn't busy.

After each call, waits 90s, fetches the full execution payload from Bolna, and
inserts the structured row into bricksiitm.rx_helper.bolna_call_outcomes Delta
(filling the gap left by the un-reachable webhook).

Total wall-clock: ~17 minutes.
"""

from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path("/Users/ruchir/Desktop/claude/app")))
from lib import bolna, bolna_flows, db   # noqa: E402

DRSAAB = "+919074839967"

FLOWS = [
    {
        "name": "take_now",
        "kwargs": {
            "phone": DRSAAB, "patient_name": "Rina Devi",
            "medicine_name": "Metformin", "dosage": "500mg",
            "time_slot": "8 PM", "language": "hi-IN", "session_id": "demo-patient-001",
        },
        "fn": bolna_flows.take_now,
    },
    {
        "name": "checkup",
        "kwargs": {
            "phone": DRSAAB, "patient_name": "Rina Devi",
            "medicines_on_file": ["amlodipine", "metformin", "paracetamol"],
            "language": "hi-IN", "session_id": "demo-patient-001",
        },
        "fn": bolna_flows.checkup,
    },
    {
        "name": "emergency",
        "kwargs": {
            "doctor_phone": DRSAAB, "patient_name": "Rina Devi",
            "location_link": "https://maps.google.com/?q=26.85,80.95",
            "medicines_on_file": ["amlodipine", "metformin", "paracetamol"],
            "patient_phone": "+919999000001", "language": "en-IN",
            "session_id": "demo-patient-001",
        },
        "fn": bolna_flows.emergency,
    },
]

SPACING_SEC = 300   # 5 min between call placements
SETTLE_SEC = 90     # wait this long after a call before fetching


def fetch_status(call_id: str, max_wait: int = SETTLE_SEC) -> dict:
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        s = bolna.get_call_status(call_id)
        last = s
        if s["completed"]:
            return s["raw"]
        time.sleep(10)
    return (last or {}).get("raw") or {}


def persist(flow: str, call_id: str, raw: dict):
    cd = (raw.get("context_details") or {}).get("recipient_data") or {}
    td = raw.get("telephony_data") or {}
    extracted = raw.get("extracted_data") or {}
    with db.connect() as c, c.cursor() as cur:
        cur.execute(
            f"INSERT INTO {db.fq('bolna_call_outcomes')} (received_at, execution_id, flow, session_id, "
            f"patient_name, medicine_name, outcome, transcript_summary, extracted_signals_json, "
            f"duration_seconds, recording_url) VALUES (current_timestamp(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                call_id, flow, cd.get("session_id"),
                cd.get("patient_name") or cd.get("medicines"),
                cd.get("medicine_name"),
                raw.get("status") or "unknown",
                (raw.get("summary") or "")[:1900],
                json.dumps(extracted)[:1900],
                int(float(td.get("duration") or 0)),
                td.get("recording_url"),
            ),
        )


def run():
    log = []
    for i, flow in enumerate(FLOWS):
        if i > 0:
            print(f"[wait] sleeping {SPACING_SEC}s before next call...")
            time.sleep(SPACING_SEC)
        print(f"\n=== [{datetime.now():%H:%M:%S}] placing flow={flow['name']}")
        try:
            cid = flow["fn"](**flow["kwargs"])
        except Exception as e:
            print(f"  PLACE FAILED: {e}")
            log.append({"flow": flow["name"], "error": str(e)})
            continue
        print(f"  call_id: {cid}  — waiting {SETTLE_SEC}s for completion...")
        raw = fetch_status(cid, SETTLE_SEC)
        outcome = {
            "flow": flow["name"],
            "call_id": cid,
            "status": raw.get("status"),
            "duration_s": (raw.get("telephony_data") or {}).get("duration"),
            "summary": (raw.get("summary") or "")[:200],
            "recording_url": (raw.get("telephony_data") or {}).get("recording_url"),
            "hangup_reason": (raw.get("telephony_data") or {}).get("hangup_reason"),
            "extracted": raw.get("extracted_data") or {},
            "carrier": (raw.get("telephony_data") or {}).get("to_number_carrier"),
            "cost": raw.get("total_cost"),
        }
        log.append(outcome)
        try:
            persist(flow["name"], cid, raw)
            print(f"  → persisted to bolna_call_outcomes Delta")
        except Exception as e:
            print(f"  PERSIST FAILED: {e}")

    out = Path("/tmp/bolna_spaced_results.json")
    out.write_text(json.dumps(log, indent=2))
    print(f"\n=== done. Results dumped to {out} ===")
    for r in log:
        print(json.dumps(r, indent=2)[:500])


if __name__ == "__main__":
    run()

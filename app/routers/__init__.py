"""Sub-routers for the Dawa Dost FastAPI app.

Each router groups related endpoints by feature area, keeping main.py thin.
Routers register their own paths via APIRouter and are mounted in main.py
via `app.include_router(...)`.

Layout:
  - pages       : HTML page routes (home, scan, scan_result, timetable, checkin, sos)
  - scanning    : /api/scan + /api/explain + /api/tts + /api/asr
  - profile_ops : /api/profile + /api/refill_alert + /api/food_warnings + /api/scheme_eligibility
                  + /api/pharmacy_locator + /api/savings_summary + /api/care_card
  - voice       : /api/voice_reminder + /api/call_reminder + /api/call_status
                  + /api/flow/* + /bolna_webhook
  - ai          : /api/ask + /api/agent + /api/rag + /api/checkin + /api/interactions
  - safety      : /api/sos + /api/trust + /api/timetable
  - admin       : /api/health + /api/_dbg_env + /api/warmup + /demo
"""

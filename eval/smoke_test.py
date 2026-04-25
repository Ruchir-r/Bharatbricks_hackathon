"""End-to-end smoke test against the deployed Rx Helper app.

Usage:
  APP_URL=https://rx-helper-7474644161560453.aws.databricksapps.com \
  DATABRICKS_TOKEN=<your PAT> \
  python smoke_test.py

Prints a pass/fail table. Exits non-zero on any failure.
"""

from __future__ import annotations
import json
import os
import sys
import time
from typing import Any
import requests


APP = os.environ.get("APP_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("DATABRICKS_TOKEN")
SESSION = "demo-patient-001"

HDR = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
results: list[tuple[str, bool, str]] = []


def post(path: str, **fields) -> tuple[int, Any]:
    r = requests.post(APP + path, data=fields, headers=HDR, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:200]


def get(path: str) -> tuple[int, Any]:
    r = requests.get(APP + path, headers=HDR, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:200]


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}: {detail[:160]}")


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

def t_health():
    s, b = get("/api/health")
    check("health responds 200",        s == 200,                                      f"status={s}")
    check("health has catalog+schema",  s == 200 and b.get("catalog") and b.get("schema"), f"catalog={b.get('catalog')}")
    check("health exposes Sarvam flag", s == 200 and "sarvam_configured" in b,        f"sarvam={b.get('sarvam_configured')}")
    return b if s == 200 else {}


def t_trust_safe():
    s, b = post("/api/trust", drug_name="paracetamol", lang="en-IN", session_id=SESSION)
    check("trust paracetamol 200",      s == 200,                                      f"status={s}")
    check("paracetamol approved=True",  s == 200 and b.get("approved") is True,        f"approved={b.get('approved')}")
    check("paracetamol safe=True",      s == 200 and b.get("safe") is True,            f"safe={b.get('safe')}")


def t_trust_nsq_flag():
    s, b = post("/api/trust", drug_name="cefixime", batch_no="CXM2509A", lang="en-IN", session_id=SESSION)
    check("cefixime NSQ flagged",       s == 200 and b.get("nsq_recent") is True,      f"nsq_batches={b.get('nsq_batches')}")
    check("cefixime reasons non-empty", s == 200 and len(b.get("reasons", [])) > 0,    f"n_reasons={len(b.get('reasons', []))}")


def t_trust_banned():
    s, b = post("/api/trust", drug_name="rosiglitazone", lang="en-IN", session_id=SESSION)
    check("banned drug returns banned=True", s == 200 and b.get("banned") is True,     f"banned={b.get('banned')}")


def t_interactions_hard_block():
    s, b = post("/api/interactions", drugs="paracetamol,flupirtine", session_id=SESSION)
    check("paracetamol+flupirtine hard-block returned",
          s == 200 and len(b.get("hard_blocks", [])) >= 1,
          f"hard_blocks_len={len(b.get('hard_blocks', []))}")


def t_profile_demo_patient():
    s, b = get(f"/api/profile?session_id={SESSION}")
    check("profile loads for demo patient",  s == 200,                                 f"status={s}")
    name = (b.get("session") or {}).get("patient_name") if s == 200 else None
    check("profile patient_name = Rina Devi", name == "Rina Devi",                     f"got={name}")
    meds = b.get("medicines") if s == 200 else []
    check("profile has 3 medicines",         len(meds) == 3,                          f"len={len(meds)}")
    nd = b.get("next_dose") if s == 200 else None
    check("profile computes next_dose",      nd and nd.get("drug_name"),               f"next_dose={nd}")


def t_ask_simple():
    s, b = post("/api/ask", session_id=SESSION, question="Which medicines am I currently taking?", lang="en-IN")
    check("ask /api/ask returns 200",    s == 200,                                     f"status={s}")
    ans = (b.get("answer") or "") if s == 200 else ""
    check("answer mentions metformin",   "metformin" in ans.lower() or "diabetes" in ans.lower(), f"answer_excerpt={ans[:120]}")
    check("answer has disclaimer tail",  "not a substitute" in ans.lower() or "डॉक्टर" in ans,   f"")


def t_ask_dose_refused():
    s, b = post("/api/ask", session_id=SESSION, question="Can I double my metformin dose tonight?", lang="en-IN")
    ans = (b.get("answer") or "") if s == 200 else ""
    check("dose-change question refused / deferred to pharmacist",
          ("pharmacist" in ans.lower() or "doctor" in ans.lower() or "prescription" in ans.lower()),
          f"answer_excerpt={ans[:160]}")


def t_ask_hindi():
    s, b = post("/api/ask", session_id=SESSION, question="क्या पेरासिटामोल और मेटफॉर्मिन साथ ले सकते हैं?", lang="hi-IN")
    check("hindi ask returns 200",       s == 200,                                     f"status={s}")
    ans = (b.get("answer") or "") if s == 200 else ""
    check("hindi answer contains Devanagari", any('ऀ' <= c <= 'ॿ' for c in ans), f"sample={ans[:80]}")


def t_guard_reject_bad_drug():
    s, b = post("/api/trust", drug_name="<script>alert(1)</script>", lang="en-IN", session_id=SESSION)
    check("guard rejects bogus drug name", s == 400,                                   f"status={s}, body={b}")


def t_guard_reject_bad_lang():
    s, b = post("/api/trust", drug_name="paracetamol", lang="xx-XX", session_id=SESSION)
    check("guard rejects non-whitelisted lang", s == 400,                              f"status={s}")


# -------------------------------------------------------------------

def main():
    print(f"Smoke-testing {APP}")
    t_health()
    t_profile_demo_patient()
    t_trust_safe()
    t_trust_nsq_flag()
    t_trust_banned()
    t_interactions_hard_block()
    t_ask_simple()
    t_ask_dose_refused()
    t_ask_hindi()
    t_guard_reject_bad_drug()
    t_guard_reject_bad_lang()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*40}\n{passed}/{total} passed\n{'='*40}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

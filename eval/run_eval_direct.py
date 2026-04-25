"""Direct-library eval runner (alternative to run_eval.py HTTP runner).

Why this exists: the deployed Databricks App requires OAuth; our local CLI only has
a PAT. This adapter imports app/lib/* directly and calls them in-process with PAT
auth, so we can run Harshit's cases.json without setting up OAuth.

Cost: same as the HTTP runner — hits the same Sarvam/foundation endpoints. Calls are
counted and reported.

Usage:
    python eval/run_eval_direct.py --cases eval/cases.json --out eval/results.json
    python eval/run_eval_direct.py --tag demo-critical
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

# Make lib importable
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))

# Env plumbing
os.environ.setdefault("CATALOG", "bricksiitm")
os.environ.setdefault("SCHEMA", "rx_helper")
os.environ.setdefault("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/28945e75b0100312")

# API-call counters
CALLS = {"sarvam_translate": 0, "sarvam_tts": 0, "sarvam_asr": 0, "foundation_llm": 0, "foundation_vision": 0, "sql": 0}


def _count(key: str, n: int = 1):
    CALLS[key] = CALLS.get(key, 0) + n


# Monkey-patch lib wrappers to count calls (best-effort)
import importlib
sarvam = importlib.import_module("lib.sarvam")
_orig_translate = sarvam.translate
_orig_tts = sarvam.tts
def _counted_translate(*a, **kw):
    _count("sarvam_translate")
    return _orig_translate(*a, **kw)
def _counted_tts(*a, **kw):
    _count("sarvam_tts")
    return _orig_tts(*a, **kw)
sarvam.translate = _counted_translate
sarvam.tts = _counted_tts


from lib import (  # noqa: E402
    drug_conflict,
    drug_identifier,
    explainer,
    trust_check,
)
from lib.guards import GuardError  # noqa: E402


# --------------------------------------------------------------------------
# Endpoint shims — mimic what main.py does (normalize_lang, hard-block, etc.)
# --------------------------------------------------------------------------

_LANG_ALIASES = {"en": "en-IN", "hi": "hi-IN", "ta": "ta-IN"}


def _norm_lang(lang: str) -> str:
    return _LANG_ALIASES.get((lang or "").lower(), lang)


def endpoint_scan(inp: dict, repo_root: Path) -> dict:
    mode = inp.get("mode")
    fpath = repo_root / inp["file"]
    if not fpath.exists():
        return {"error": f"fixture missing: {fpath}"}
    data = fpath.read_bytes()
    _count("foundation_vision")
    if mode == "prescription":
        return drug_identifier.extract_prescription(data)
    return drug_identifier.identify_drug_label(data)


def endpoint_trust(inp: dict) -> dict:
    lang_in = inp.get("lang", "en")
    lang = _norm_lang(lang_in)
    _count("sql", 3)  # approved + banned + nsq
    v = trust_check.check(inp["drug_name"], batch_no=inp.get("batch_no"))
    return {
        "drug_name": v.drug_name,
        "safe": v.safe,
        "approved": v.approved,
        "banned": v.banned,
        "nsq_recent": v.nsq_recent,
        "nsq_batches": v.nsq_batches,
        "reasons": v.reasons_hi if lang == "hi-IN" else v.reasons_en,
    }


def endpoint_explain(inp: dict) -> dict:
    original_lang = inp.get("lang", "en")
    lang = _norm_lang(original_lang)
    v = trust_check.check(inp["drug"])
    _count("sql", 3)
    if v.banned:
        return {"english": "banned", "translated": "banned", "language": original_lang, "audio_b64": None, "banned": True}
    _count("foundation_llm")
    res = explainer.explain_with_audio(drug=inp["drug"], dose=inp.get("dose", ""), language=lang)
    audio = res.get("audio_bytes")
    return {
        "english": res["english"],
        "translated": res["translated"],
        "language": original_lang,
        "audio_b64": base64.b64encode(audio).decode() if audio else None,
    }


def endpoint_interactions(inp: dict) -> dict:
    names = [n.strip() for n in inp["drugs"].split(",") if n.strip()]
    _count("sql", 1 + len(names) * (len(names) - 1) // 2)
    hard = drug_conflict.hard_block_pairs(names)
    _count("foundation_llm")
    soft = drug_conflict.soft_check(names, inp.get("diagnosis"))
    soft_bits: list[str] = []
    for i in soft.get("interactions", []) or []:
        soft_bits.append(f"{'+'.join(i.get('pair', []))} [{i.get('severity','?')}]: {i.get('explanation','')}")
    for c in soft.get("contraindications", []) or []:
        soft_bits.append(f"{c.get('drug','?')}: {c.get('concern','')}")
    return {"hard_blocks": hard, "soft": soft, "soft_text": " | ".join(soft_bits)}


DISPATCH = {
    "scan": endpoint_scan,
    "trust": lambda inp, _r: endpoint_trust(inp),
    "explain": lambda inp, _r: endpoint_explain(inp),
    "interactions": lambda inp, _r: endpoint_interactions(inp),
}


def call_case(case: dict, repo_root: Path) -> dict:
    endpoint = case["endpoint"]
    inp = dict(case.get("input", {}))
    t0 = time.time()
    try:
        if endpoint == "scan":
            body = endpoint_scan(inp, repo_root)
        else:
            body = DISPATCH[endpoint](inp, repo_root)
        return {"status_code": 200, "latency_ms": int((time.time() - t0) * 1000), "response": body}
    except GuardError as e:
        return {"status_code": 400, "latency_ms": int((time.time() - t0) * 1000), "response": {"error": str(e)}}
    except Exception as e:
        return {"status_code": 500, "latency_ms": int((time.time() - t0) * 1000), "error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="eval/cases.json")
    ap.add_argument("--out", default="eval/results.json")
    ap.add_argument("--tag", help="only run cases with this tag")
    ap.add_argument("--id", help="only run cases with this id")
    args = ap.parse_args()

    doc = json.loads(Path(args.cases).read_text())
    to_run = []
    for c in doc["cases"]:
        if c.get("skip"):
            continue
        if args.id and c["id"] != args.id:
            continue
        if args.tag and args.tag not in c.get("tags", []):
            continue
        to_run.append(c)

    print(f"Running {len(to_run)} case(s) against Databricks (via direct lib calls)")
    print(f"API-call budget will be reported at the end.")
    results = []
    for i, case in enumerate(to_run, 1):
        print(f"  [{i}/{len(to_run)}] {case['id']:<14} {case['endpoint']:<13}", end=" ", flush=True)
        r = call_case(case, REPO)
        status = (
            "OK" if r.get("status_code") == 200
            else "ERR" if r.get("error")
            else f"HTTP{r.get('status_code')}"
        )
        print(f"{status} ({r.get('latency_ms', 0)}ms)")
        results.append({"id": case["id"], "endpoint": case["endpoint"], "tags": case.get("tags", []), **r})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"base": "direct-lib", "results": results, "api_calls": CALLS}, indent=2))
    print(f"\nWrote {args.out}")

    # Budget report
    print("\n--- API-call budget actually used ---")
    for k, v in CALLS.items():
        if v:
            print(f"  {k:22s} = {v}")
    total = sum(CALLS.values())
    print(f"  TOTAL                  = {total}")


if __name__ == "__main__":
    main()

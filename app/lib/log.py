"""Structured app logger.

One-liner JSON log lines that ship to Databricks Apps stdout (which Apps surfaces
in the workspace UI's Logs tab). Each line carries:
  - ts:        ISO timestamp
  - level:     INFO / WARN / ERROR
  - stage:     short event name (e.g. "scan.start", "rag.hit", "bolna.call")
  - latency_ms: optional
  - meta:      arbitrary key/value dict
  - session_id: when known

Usage:
    from lib.log import log
    log("scan.start", session_id="...", drug_count=4)
    log("rag.hit", level="WARN", drug=name, table="cdsco_banned")
    with timed("scan.full", session_id=sid) as t:
        ...
        t.add(drug_count=len(drugs))
"""

from __future__ import annotations
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any


def log(stage: str, *, level: str = "INFO", session_id: str | None = None,
        latency_ms: int | None = None, **meta: Any) -> None:
    record: dict[str, Any] = {
        "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
        "level": level,
        "stage": stage,
    }
    if session_id:
        record["session_id"] = session_id
    if latency_ms is not None:
        record["latency_ms"] = latency_ms
    if meta:
        record["meta"] = meta
    try:
        print(json.dumps(record, default=str), flush=True, file=sys.stdout)
    except Exception:
        # Logging must NEVER crash the request path
        pass


@contextmanager
def timed(stage: str, *, session_id: str | None = None, **start_meta: Any):
    """Context manager that emits a single log line with elapsed_ms on exit.

    Inside, call `t.add(...)` to attach extra fields known mid-flight."""
    extra: dict[str, Any] = dict(start_meta)
    t0 = time.time()

    class _T:
        def add(self, **kw: Any) -> None:
            extra.update(kw)
        elapsed_ms = 0

    holder = _T()
    log(f"{stage}.start", session_id=session_id, **start_meta)
    try:
        yield holder
        holder.elapsed_ms = int((time.time() - t0) * 1000)
        log(f"{stage}.end", session_id=session_id, latency_ms=holder.elapsed_ms, **extra)
    except Exception as e:
        holder.elapsed_ms = int((time.time() - t0) * 1000)
        log(f"{stage}.error", level="ERROR", session_id=session_id,
            latency_ms=holder.elapsed_ms, error=f"{type(e).__name__}: {e}", **extra)
        raise


def warn(stage: str, **meta: Any) -> None:
    log(stage, level="WARN", **meta)


def error(stage: str, **meta: Any) -> None:
    log(stage, level="ERROR", **meta)

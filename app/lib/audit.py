"""Inference-audit logging — writes to bricksiitm.rx_helper.inference_log Delta table.

Best-effort: never raises into the request path. Used for the "MLflow-style audit"
talking point in the demo (judges see populated audit trail in Catalog → table → history).
"""

from __future__ import annotations
import os
import time
import uuid
from . import db


def _conn():
    return db.connect()


def log(stage: str, *, session_id: str = "anon", input: str = "", output: str = "", latency_ms: int = 0) -> None:
    """Append-only audit row. stage ∈ {scan, trust, explain, ask, interactions, sos, reminder, ...}."""
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute(
                f"INSERT INTO {catalog}.{schema}.inference_log VALUES (?, ?, ?, ?, ?, ?, current_timestamp())",
                (str(uuid.uuid4()), session_id[:64], stage[:32], (input or "")[:2000], (output or "")[:2000], int(latency_ms)),
            )
    except Exception:
        # never raise from audit; logging is non-essential to the user request
        pass


class timed:
    """Context manager: with timed() as t: ... ; t.elapsed_ms"""
    def __enter__(self):
        self._t0 = time.time()
        return self
    def __exit__(self, *a):
        self.elapsed_ms = int((time.time() - self._t0) * 1000)

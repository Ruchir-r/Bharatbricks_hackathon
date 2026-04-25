"""Secret-scope reader with env-var override + in-process cache.

Belt-and-suspenders for the App: if env-injected secrets aren't present (e.g. due
to a misconfigured `valueFrom` in app.yaml), this falls back to reading from the
Databricks secret scope at runtime via the SDK.
"""

from __future__ import annotations
import base64
import os
from typing import Optional


_cache: dict[str, str] = {}


def get(env_name: str, *, scope: str, key: str) -> Optional[str]:
    """Return the secret value, in priority order:
       1. cached value
       2. environment variable `env_name`
       3. Databricks secret scope `<scope>/<key>` via SDK
    Returns None on failure (callers should treat as 'not configured').
    """
    if env_name in _cache:
        return _cache[env_name]

    val = os.environ.get(env_name)
    if val and val.strip() and "PLACEHOLDER" not in val:
        _cache[env_name] = val
        return val

    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        resp = w.secrets.get_secret(scope=scope, key=key)
        decoded = base64.b64decode(resp.value).decode()
        if decoded:
            _cache[env_name] = decoded
            os.environ[env_name] = decoded   # so other libs that read env see it
            return decoded
    except Exception:
        return None
    return None

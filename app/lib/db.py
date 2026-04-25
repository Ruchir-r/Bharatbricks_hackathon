"""Single SQL-connection helper.

Uses databricks-sdk Config + credentials_provider, which transparently mints the
right auth header for whatever credential is on the env:
  - Local PAT (DATABRICKS_TOKEN as a personal access token)
  - Apps OAuth (DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET set by the platform)

databricks-sql-connector's `access_token=...` parameter only accepts PAT, so we
deliberately do NOT use that path.
"""

from __future__ import annotations
import os
from databricks import sql
from databricks.sdk.core import Config


def _host() -> str:
    h = os.environ.get("DATABRICKS_HOST", "")
    return h.replace("https://", "").replace("http://", "").rstrip("/")


def _http_path() -> str:
    return os.environ["DATABRICKS_HTTP_PATH"]


def connect():
    # Apps inject DATABRICKS_CLIENT_ID + _SECRET → force OAuth M2M.
    # Locally we usually have only DATABRICKS_TOKEN as a PAT → use that path.
    if os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"):
        cfg = Config(
            host=os.environ["DATABRICKS_HOST"],
            client_id=os.environ["DATABRICKS_CLIENT_ID"],
            client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
            auth_type="oauth-m2m",
        )
        return sql.connect(
            server_hostname=_host(),
            http_path=_http_path(),
            credentials_provider=lambda: cfg.authenticate,
        )

    # Local PAT
    return sql.connect(
        server_hostname=_host(),
        http_path=_http_path(),
        access_token=os.environ["DATABRICKS_TOKEN"],
    )


def fq(table: str) -> str:
    catalog = os.environ.get("CATALOG", "bricksiitm")
    schema = os.environ.get("SCHEMA", "rx_helper")
    return f"{catalog}.{schema}.{table}"

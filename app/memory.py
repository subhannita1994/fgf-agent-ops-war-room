"""Durable chat history in Lakebase Postgres.

Connection settings come from the app's Lakebase resource:
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE are injected automatically.
  LAKEBASE_ENDPOINT is declared in databricks.yml (config.env, value_from: database) and is used
  to mint short-lived OAuth passwords for the app service principal.

If Lakebase is unreachable, history falls back to process memory so the app
keeps answering (context is then not durable), and the error is logged.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg_pool import ConnectionPool

log = logging.getLogger("memory")

SCHEMA = os.environ.get("MEMORY_SCHEMA", "sales_agent_memory")
TABLE = f"{SCHEMA}.chat_messages"
# Only the most recent messages are resent to the model on each turn.
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "40"))
TOKEN_TTL_SECONDS = 45 * 60  # Lakebase OAuth tokens last about 1 hour

_workspace = WorkspaceClient()
_token_lock = threading.Lock()
_token: dict[str, float | str] = {"value": "", "expires": 0.0}
_pool_lock = threading.Lock()
_pool: ConnectionPool | None = None
_fallback_store: dict[str, list[dict]] = {}


def _password() -> str:
    with _token_lock:
        if time.time() >= float(_token["expires"]):
            cred = _workspace.postgres.generate_database_credential(endpoint=os.environ["LAKEBASE_ENDPOINT"])
            _token["value"] = cred.token
            _token["expires"] = time.time() + TOKEN_TTL_SECONDS
        return str(_token["value"])


class _TokenConnection(psycopg.Connection):
    """Injects a fresh OAuth password every time the pool opens a connection."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs):  # type: ignore[override]
        kwargs["password"] = _password()
        return super().connect(conninfo, **kwargs)


def _get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            pool = ConnectionPool(
                kwargs={
                    "host": os.environ["PGHOST"],
                    "port": int(os.environ.get("PGPORT", "5432")),
                    "dbname": os.environ["PGDATABASE"],
                    "user": os.environ["PGUSER"],
                    "sslmode": os.environ.get("PGSSLMODE", "require"),
                    "autocommit": True,
                },
                connection_class=_TokenConnection,
                min_size=1,
                max_size=5,
                max_lifetime=TOKEN_TTL_SECONDS,  # recycle before the token expires
                open=True,
            )
            try:
                _ensure_table(pool)
            except Exception:
                pool.close()
                raise
            _pool = pool
        return _pool


def _ensure_table(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(f"CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON {TABLE} (session_id, id)")


def load_messages(session_id: str) -> list[dict]:
    try:
        with _get_pool().connection() as conn:
            rows = conn.execute(
                f"""
                SELECT role, content FROM (
                    SELECT id, role, content FROM {TABLE}
                    WHERE session_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) recent
                ORDER BY id
                """,
                (session_id, MAX_HISTORY_MESSAGES),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]
    except Exception:
        log.exception("Lakebase load failed; using in-process history for session %s", session_id)
        return list(_fallback_store.get(session_id, []))[-MAX_HISTORY_MESSAGES:]


def append_message(session_id: str, role: str, content: str) -> None:
    try:
        with _get_pool().connection() as conn:
            conn.execute(
                f"INSERT INTO {TABLE} (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
    except Exception:
        log.exception("Lakebase write failed; keeping message in process memory for session %s", session_id)
        _fallback_store.setdefault(session_id, []).append({"role": role, "content": content})

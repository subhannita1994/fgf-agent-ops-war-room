from __future__ import annotations

import os

import psycopg2


def _connect():
    """Connect to the Lakebase Postgres database.

    The postgres app resource injects standard PG* env vars (PGHOST, PGPORT,
    PGDATABASE, PGUSER, PGSSLMODE, PGPASSWORD). psycopg2 reads them automatically
    when connect() is called with no arguments.
    """
    conn = psycopg2.connect()
    # Ensure the table exists (the app SP owns the schema it creates).
    with conn.cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS agent_memory (
                conversation_id TEXT NOT NULL,
                turn SERIAL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (conversation_id, turn)
            )"""
        )
        conn.commit()
    return conn


def load_messages(session_id: str) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM agent_memory WHERE conversation_id = %s ORDER BY turn",
                (session_id,),
            )
            return [{"role": r[0], "content": r[1]} for r in cur.fetchall()]


def append_message(session_id: str, role: str, content: str) -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_memory (conversation_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
            conn.commit()
            cur.execute(
                "SELECT role, content FROM agent_memory WHERE conversation_id = %s ORDER BY turn",
                (session_id,),
            )
            return [{"role": r[0], "content": r[1]} for r in cur.fetchall()]

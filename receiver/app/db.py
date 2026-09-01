import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from app.errors import StatementConflictError
from app.profile_identity import canonicalize_agent_object

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def check_db_connection():
    config = get_db_config()

    try:
        with psycopg.connect(**config, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except psycopg.Error as exc:
        return {
            "connected": False,
            "host": config["host"],
            "port": config["port"],
            "database": config["dbname"],
            "error": str(exc),
        }

    return {
        "connected": True,
        "host": config["host"],
        "port": config["port"],
        "database": config["dbname"],
    }


def init_db():
    config = get_db_config()

    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS statements (
                    id BIGSERIAL PRIMARY KEY,
                    statement_id TEXT,
                    payload JSONB NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_statements_received_at
                ON statements (received_at)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (migration_path.name,),
                )
                if cur.fetchone() is not None:
                    continue

                cur.execute(migration_path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (migration_path.name,),
                )


def save_statement(payload):
    config = get_db_config()
    projection = _project_statement(payload)

    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            statement_id = payload["id"]
            cur.execute(
                """
                INSERT INTO statements (
                    statement_id,
                    payload,
                    received_at,
                    actor_key,
                    verb_id,
                    activity_id,
                    event_timestamp,
                    score_scaled,
                    success,
                    completion
                )
                SELECT
                    %s,
                    %s,
                    captured_at,
                    %s,
                    %s,
                    %s,
                    COALESCE(%s::TIMESTAMPTZ, captured_at),
                    %s,
                    %s,
                    %s
                FROM (SELECT clock_timestamp() AS captured_at) clock
                ON CONFLICT (statement_id) DO NOTHING
                RETURNING id, statement_id, received_at
                """,
                (
                    statement_id,
                    Jsonb(payload),
                    projection["actor_key"],
                    projection["verb_id"],
                    projection["activity_id"],
                    projection["event_timestamp"],
                    projection["score_scaled"],
                    projection["success"],
                    projection["completion"],
                ),
            )
            row = cur.fetchone()

            if row is None:
                cur.execute(
                    """
                    SELECT id, statement_id, payload, received_at
                    FROM statements
                    WHERE statement_id = %s
                    FOR KEY SHARE
                    """,
                    (statement_id,),
                )
                row = cur.fetchone()
                if row[2] != payload:
                    raise StatementConflictError(
                        f"statement id {statement_id} already exists with different content"
                    )
                created = False
                received_at = row[3]
            else:
                created = True
                received_at = row[2]

    return {
        "id": row[0],
        "statementId": str(row[1]),
        "receivedAt": received_at.isoformat(),
        "created": created,
    }


def list_statements(limit=50):
    config = get_db_config()

    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, statement_id, payload, received_at
                FROM statements
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "statementId": str(row[1]),
            "payload": row[2],
            "receivedAt": row[3].isoformat(),
        }
        for row in rows
    ]


def _project_statement(payload):
    result = payload.get("result") or {}
    score = result.get("score") or {}

    return {
        "actor_key": canonicalize_agent_object(payload["actor"]).owner_key,
        "verb_id": payload["verb"]["id"],
        "activity_id": payload["object"]["id"],
        "event_timestamp": payload.get("timestamp"),
        "score_scaled": score.get("scaled"),
        "success": result.get("success"),
        "completion": result.get("completion"),
    }

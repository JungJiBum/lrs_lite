import os

import psycopg
from psycopg.types.json import Jsonb


def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "ingest"),
        "user": os.getenv("DB_USER", "ingest"),
        "password": os.getenv("DB_PASSWORD", "ingest1!"),
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
                CREATE INDEX IF NOT EXISTS idx_statements_statement_id
                ON statements (statement_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_statements_received_at
                ON statements (received_at)
                """
            )


def save_statement(payload):
    config = get_db_config()

    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO statements (statement_id, payload)
                VALUES (%s, %s)
                RETURNING id, statement_id, received_at
                """,
                (payload.get("id"), Jsonb(payload)),
            )
            row = cur.fetchone()

    return {
        "id": row[0],
        "statementId": row[1],
        "receivedAt": row[2].isoformat(),
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
            "statementId": row[1],
            "payload": row[2],
            "receivedAt": row[3].isoformat(),
        }
        for row in rows
    ]

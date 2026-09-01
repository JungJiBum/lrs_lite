from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import get_db_config, init_db
from app.main import app


@pytest.fixture(autouse=True)
def clean_statements():
    init_db()
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE statements RESTART IDENTITY")
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_generates_and_persists_missing_statement_id(client, valid_statement):
    valid_statement.pop("id")

    response = client.post("/statements", json=valid_statement)

    assert response.status_code == 200
    body = response.json()
    generated_id = body["payload"]["id"]
    assert UUID(generated_id)
    assert body["saved"]["statementId"] == generated_id
    assert body["saved"]["created"] is True
    assert body["idempotent"] is False


def test_same_id_and_payload_is_idempotent(client, valid_statement):
    first = client.post("/statements", json=valid_statement)
    second = client.post("/statements", json=valid_statement)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["saved"]["created"] is False
    assert second.json()["saved"]["id"] == first.json()["saved"]["id"]

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM statements")
            assert cur.fetchone()[0] == 1


def test_same_id_with_different_payload_returns_conflict(client, valid_statement):
    first = client.post("/statements", json=valid_statement)
    valid_statement["verb"]["id"] = "http://adlnet.gov/expapi/verbs/completed"

    second = client.post("/statements", json=valid_statement)

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already exists with different content" in second.json()["detail"]

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM statements")
            assert cur.fetchone()[0] == 1


def test_invalid_statement_is_not_persisted(client, valid_statement):
    valid_statement["id"] = "not-a-uuid"

    response = client.post("/statements", json=valid_statement)

    assert response.status_code == 422
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM statements")
            assert cur.fetchone()[0] == 0


def test_database_enforces_uuid_unique_and_not_null():
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'statements' AND column_name = 'statement_id'
                """
            )
            assert cur.fetchone() == ("uuid", "NO")

            cur.execute(
                """
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE conrelid = 'statements'::regclass
                  AND contype = 'u'
                  AND conname = 'statements_statement_id_key'
                """
            )
            assert cur.fetchone()[0] == 1

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.db import get_db_config, init_db
from app.main import app

AGENT_A = {
    "objectType": "Agent",
    "name": "Agent A",
    "mbox": "mailto:agent.a@EXAMPLE.COM",
}
AGENT_A_QUERY = json.dumps(
    {"objectType": "Agent", "name": "Renamed A", "mbox": "mailto:agent.a@example.com"}
)
AGENT_B = {
    "objectType": "Agent",
    "name": "Agent B",
    "mbox": "mailto:agent.b@example.com",
}

ANSWERED = "http://adlnet.gov/expapi/verbs/answered"
COMPLETED = "http://adlnet.gov/expapi/verbs/completed"
FAILED = "http://adlnet.gov/expapi/verbs/failed"
MATH = "https://example.com/activities/math"
SCIENCE = "https://example.com/activities/science"


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


def make_statement(
    actor,
    verb_id,
    activity_id,
    timestamp,
    *,
    score=None,
    success=None,
    completion=None,
):
    statement = {
        "id": str(uuid4()),
        "actor": deepcopy(actor),
        "verb": {"id": verb_id},
        "object": {"objectType": "Activity", "id": activity_id},
        "timestamp": timestamp,
    }
    result = {}
    if score is not None:
        result["score"] = {"scaled": score}
    if success is not None:
        result["success"] = success
    if completion is not None:
        result["completion"] = completion
    if result:
        statement["result"] = result
    return statement


def seed_summary_statements(client):
    statements = [
        make_statement(
            AGENT_A,
            ANSWERED,
            MATH,
            "2026-01-01T00:00:00+00:00",
            score=0.4,
            success=True,
            completion=False,
        ),
        make_statement(
            AGENT_A,
            ANSWERED,
            MATH,
            "2026-01-02T00:00:00+00:00",
            completion=False,
        ),
        make_statement(
            AGENT_A,
            COMPLETED,
            MATH,
            "2026-01-03T00:00:00+00:00",
            score=0.8,
            success=True,
            completion=True,
        ),
        make_statement(
            AGENT_A,
            FAILED,
            SCIENCE,
            "2026-01-04T00:00:00+00:00",
            score=0.2,
            success=False,
            completion=True,
        ),
        make_statement(
            AGENT_B,
            COMPLETED,
            SCIENCE,
            "2026-02-01T00:00:00+00:00",
            score=1.0,
            success=True,
            completion=True,
        ),
    ]
    for statement in statements:
        response = client.post("/statements", json=statement)
        assert response.status_code == 200
    return statements


def test_agent_summary_aggregates_only_the_requested_agent(client):
    seed_summary_statements(client)

    response = client.get(
        "/extensions/analytics/agent-summary",
        params={"agent": AGENT_A_QUERY},
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["agentKey"] == "mbox:mailto:agent.a@example.com"
    assert summary["totalStatementCount"] == 4
    assert summary["firstActivityAt"] == "2026-01-01T00:00:00+00:00"
    assert summary["lastActivityAt"] == "2026-01-04T00:00:00+00:00"
    assert summary["verbCounts"] == {ANSWERED: 2, COMPLETED: 1, FAILED: 1}
    assert summary["activityCounts"] == {MATH: 3, SCIENCE: 1}
    assert summary["completionCount"] == 2
    assert summary["successCount"] == 2
    assert summary["failureCount"] == 1
    assert summary["averageScoreScaled"] == pytest.approx((0.4 + 0.8 + 0.2) / 3)
    assert summary["highestScoreScaled"] == 0.8


def test_scoreless_statements_are_counted_but_excluded_from_score_metrics(client):
    statement = make_statement(
        AGENT_A,
        ANSWERED,
        MATH,
        "2026-01-02T00:00:00+00:00",
    )
    client.post("/statements", json=statement)

    summary = client.get(
        "/extensions/analytics/agent-summary",
        params={"agent": AGENT_A_QUERY},
    ).json()

    assert summary["totalStatementCount"] == 1
    assert summary["averageScoreScaled"] is None
    assert summary["highestScoreScaled"] is None


def test_idempotent_statement_retry_does_not_inflate_summary(client):
    statement = make_statement(
        AGENT_A,
        COMPLETED,
        MATH,
        "2026-01-03T00:00:00+00:00",
        score=0.8,
        success=True,
        completion=True,
    )

    first = client.post("/statements", json=statement)
    retry = client.post("/statements", json=statement)
    summary = client.get(
        "/extensions/analytics/agent-summary",
        params={"agent": AGENT_A_QUERY},
    ).json()

    assert first.json()["idempotent"] is False
    assert retry.json()["idempotent"] is True
    assert summary["totalStatementCount"] == 1
    assert summary["completionCount"] == 1


def test_raw_jsonb_and_projection_are_consistent(client):
    statement = make_statement(
        AGENT_A,
        FAILED,
        SCIENCE,
        "2026-01-04T00:00:00+09:00",
        score=-0.25,
        success=False,
        completion=True,
    )
    original = deepcopy(statement)

    response = client.post("/statements", json=statement)

    assert response.status_code == 200
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    payload,
                    actor_key,
                    verb_id,
                    activity_id,
                    event_timestamp,
                    score_scaled,
                    success,
                    completion
                FROM statements
                WHERE statement_id = %s
                """,
                (statement["id"],),
            )
            row = cur.fetchone()

    assert row[0] == original
    assert row[1] == "mbox:mailto:agent.a@example.com"
    assert row[2] == FAILED
    assert row[3] == SCIENCE
    assert row[4] == datetime(2026, 1, 3, 15, 0, tzinfo=timezone.utc)
    assert row[5] == -0.25
    assert row[6] is False
    assert row[7] is True


def test_summary_for_agent_without_statements_returns_zero_values(client):
    summary = client.get(
        "/extensions/analytics/agent-summary",
        params={"agent": AGENT_A_QUERY},
    ).json()

    assert summary["totalStatementCount"] == 0
    assert summary["firstActivityAt"] is None
    assert summary["lastActivityAt"] is None
    assert summary["verbCounts"] == {}
    assert summary["activityCounts"] == {}
    assert summary["completionCount"] == 0
    assert summary["successCount"] == 0
    assert summary["failureCount"] == 0
    assert summary["averageScoreScaled"] is None
    assert summary["highestScoreScaled"] is None


def test_projection_migration_backfills_without_mutating_raw_payload():
    schema_name = "analytics_projection_migration_test"
    migration_sql = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "003_statement_projection.sql"
    ).read_text(encoding="utf-8")
    payload = make_statement(
        AGENT_A,
        COMPLETED,
        MATH,
        "2026-03-01T12:30:00+09:00",
        score=0.75,
        success=True,
        completion=True,
    )

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA {schema_name}")
            cur.execute(f"SET search_path TO {schema_name}")
            cur.execute(
                """
                CREATE TABLE statements (
                    id BIGSERIAL PRIMARY KEY,
                    statement_id UUID NOT NULL UNIQUE,
                    payload JSONB NOT NULL,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "INSERT INTO statements (statement_id, payload) VALUES (%s, %s)",
                (payload["id"], Jsonb(payload)),
            )
            cur.execute(migration_sql)
            cur.execute(
                """
                SELECT payload, actor_key, verb_id, activity_id, score_scaled,
                       success, completion
                FROM statements
                """
            )
            row = cur.fetchone()
            cur.execute("SET search_path TO public")
            cur.execute(f"DROP SCHEMA {schema_name} CASCADE")

    assert row[0] == payload
    assert row[1:] == (
        "mbox:mailto:agent.a@example.com",
        COMPLETED,
        MATH,
        0.75,
        True,
        True,
    )

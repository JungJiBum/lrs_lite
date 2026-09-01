from dataclasses import dataclass
from datetime import datetime

import psycopg

from app.db import get_db_config


@dataclass(frozen=True)
class AgentActivitySummary:
    total_statement_count: int
    first_activity_at: datetime | None
    last_activity_at: datetime | None
    verb_counts: dict[str, int]
    activity_counts: dict[str, int]
    completion_count: int
    success_count: int
    failure_count: int
    average_score_scaled: float | None
    highest_score_scaled: float | None


def get_agent_activity_summary(actor_key: str) -> AgentActivitySummary:
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH agent_statements AS MATERIALIZED (
                    SELECT
                        verb_id,
                        activity_id,
                        event_timestamp,
                        score_scaled,
                        success,
                        completion
                    FROM statements
                    WHERE actor_key = %s
                ),
                metrics AS (
                    SELECT
                        COUNT(*) AS total_statement_count,
                        MIN(event_timestamp) AS first_activity_at,
                        MAX(event_timestamp) AS last_activity_at,
                        COUNT(*) FILTER (WHERE completion IS TRUE) AS completion_count,
                        COUNT(*) FILTER (WHERE success IS TRUE) AS success_count,
                        COUNT(*) FILTER (WHERE success IS FALSE) AS failure_count,
                        AVG(score_scaled) AS average_score_scaled,
                        MAX(score_scaled) AS highest_score_scaled
                    FROM agent_statements
                ),
                verbs AS (
                    SELECT COALESCE(
                        jsonb_object_agg(verb_id, statement_count ORDER BY verb_id),
                        '{}'::JSONB
                    ) AS counts
                    FROM (
                        SELECT verb_id, COUNT(*) AS statement_count
                        FROM agent_statements
                        WHERE verb_id IS NOT NULL
                        GROUP BY verb_id
                    ) grouped_verbs
                ),
                activities AS (
                    SELECT COALESCE(
                        jsonb_object_agg(activity_id, statement_count ORDER BY activity_id),
                        '{}'::JSONB
                    ) AS counts
                    FROM (
                        SELECT activity_id, COUNT(*) AS statement_count
                        FROM agent_statements
                        WHERE activity_id IS NOT NULL
                        GROUP BY activity_id
                    ) grouped_activities
                )
                SELECT
                    metrics.total_statement_count,
                    metrics.first_activity_at,
                    metrics.last_activity_at,
                    verbs.counts,
                    activities.counts,
                    metrics.completion_count,
                    metrics.success_count,
                    metrics.failure_count,
                    metrics.average_score_scaled,
                    metrics.highest_score_scaled
                FROM metrics
                CROSS JOIN verbs
                CROSS JOIN activities
                """,
                (actor_key,),
            )
            row = cur.fetchone()

    return AgentActivitySummary(
        total_statement_count=row[0],
        first_activity_at=row[1],
        last_activity_at=row[2],
        verb_counts=row[3],
        activity_counts=row[4],
        completion_count=row[5],
        success_count=row[6],
        failure_count=row[7],
        average_score_scaled=row[8],
        highest_score_scaled=row[9],
    )

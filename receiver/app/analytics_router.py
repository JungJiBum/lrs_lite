from fastapi import APIRouter, HTTPException, Query

from app.analytics_store import get_agent_activity_summary
from app.profile_identity import InvalidProfileOwner, canonicalize_agent

router = APIRouter(prefix="/extensions/analytics", tags=["analytics"])


@router.get("/agent-summary")
def agent_summary(agent: str = Query()):
    try:
        actor_key = canonicalize_agent(agent).owner_key
    except InvalidProfileOwner as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = get_agent_activity_summary(actor_key)
    return {
        "agentKey": actor_key,
        "totalStatementCount": summary.total_statement_count,
        "firstActivityAt": summary.first_activity_at,
        "lastActivityAt": summary.last_activity_at,
        "verbCounts": summary.verb_counts,
        "activityCounts": summary.activity_counts,
        "completionCount": summary.completion_count,
        "successCount": summary.success_count,
        "failureCount": summary.failure_count,
        "averageScoreScaled": summary.average_score_scaled,
        "highestScoreScaled": summary.highest_score_scaled,
    }

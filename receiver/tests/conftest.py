from copy import deepcopy

import pytest


@pytest.fixture
def valid_statement():
    payload = {
        "id": "8f87ccde-bb56-4a31-86bd-90d9f386101c",
        "actor": {
            "objectType": "Agent",
            "name": "김민준",
            "mbox": "mailto:minjun.kim@example.com",
        },
        "verb": {
            "id": "http://adlnet.gov/expapi/verbs/answered",
            "display": {"en-US": "answered", "ko-KR": "응답했다"},
        },
        "object": {
            "objectType": "Activity",
            "id": "https://portfolio.local/quiz/math/questions/1",
            "definition": {
                "name": {"ko-KR": "수학퀴즈"},
                "type": "http://adlnet.gov/expapi/activities/cmi.interaction",
            },
        },
        "context": {
            "platform": "portfolio-sender",
            "language": "ko-KR",
            "extensions": {
                "https://portfolio.local/extensions/sessionId": "demo-session-1"
            },
        },
        "result": {
            "success": True,
            "completion": False,
            "score": {"scaled": 0.8, "raw": 80, "min": 0, "max": 100},
            "response": "A",
        },
        "timestamp": "2026-04-14T12:00:00+00:00",
    }
    return deepcopy(payload)

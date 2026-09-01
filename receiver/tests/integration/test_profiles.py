import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from app.db import get_db_config, init_db
from app.main import app
from app.profile_store import ProfilePreconditionFailed, put_profile_document

AGENT = json.dumps(
    {"objectType": "Agent", "name": "Profile User", "mbox": "mailto:user@EXAMPLE.COM"}
)
SAME_AGENT_DIFFERENT_NAME = json.dumps(
    {"objectType": "Agent", "name": "Renamed User", "mbox": "mailto:user@example.com"}
)
ACTIVITY_ID = "https://example.com/activities/course-1"


@pytest.fixture(autouse=True)
def clean_profile_documents():
    init_db()
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE profile_documents")
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def agent_params(profile_id=None, agent=AGENT):
    params = {"agent": agent}
    if profile_id is not None:
        params["profileId"] = profile_id
    return params


def activity_params(profile_id=None):
    params = {"activityId": ACTIVITY_ID}
    if profile_id is not None:
        params["profileId"] = profile_id
    return params


def create_json_profile(client, path, params, content=None):
    content = content or {"theme": "dark", "nested": {"old": True}}
    return client.put(
        path,
        params=params,
        content=json.dumps(content),
        headers={"Content-Type": "application/json", "If-None-Match": "*"},
    )


def test_agent_profile_put_get_and_content_headers(client):
    content = b'{"theme":"dark"}'

    put_response = client.put(
        "/agents/profile",
        params=agent_params("preferences"),
        content=content,
        headers={"Content-Type": "application/json", "If-None-Match": "*"},
    )
    get_response = client.get(
        "/agents/profile",
        params=agent_params("preferences", SAME_AGENT_DIFFERENT_NAME),
    )

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    assert get_response.content == content
    assert get_response.headers["content-type"] == "application/json"
    assert get_response.headers["etag"] == f'"{hashlib.sha1(content).hexdigest()}"'
    assert "last-modified" in get_response.headers


def test_activity_profile_arbitrary_content_type_round_trip(client):
    content = b"\x00\x01profile-binary\xff"

    put_response = client.put(
        "/activities/profile",
        params=activity_params("binary-document"),
        content=content,
        headers={"Content-Type": "application/x-lrs-demo", "If-None-Match": "*"},
    )
    get_response = client.get(
        "/activities/profile", params=activity_params("binary-document")
    )

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    assert get_response.content == content
    assert get_response.headers["content-type"] == "application/x-lrs-demo"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/agents/profile", agent_params("document")),
        ("/activities/profile", activity_params("document")),
    ],
)
def test_json_post_merges_only_top_level_properties(client, path, params):
    assert create_json_profile(client, path, params).status_code == 204
    current = client.get(path, params=params)

    post_response = client.post(
        path,
        params=params,
        content=json.dumps({"locale": "ko-KR", "nested": {"new": True}}),
        headers={"Content-Type": "application/json", "If-Match": current.headers["etag"]},
    )
    merged = client.get(path, params=params)

    assert post_response.status_code == 204
    assert merged.json() == {
        "theme": "dark",
        "locale": "ko-KR",
        "nested": {"new": True},
    }
    assert merged.headers["etag"] != current.headers["etag"]


def test_post_rejects_non_json_merge_without_changing_document(client):
    params = activity_params("plain")
    original = b"original"
    client.put(
        "/activities/profile",
        params=params,
        content=original,
        headers={"Content-Type": "text/plain", "If-None-Match": "*"},
    )

    response = client.post(
        "/activities/profile",
        params=params,
        content=b"updated",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 400
    assert client.get("/activities/profile", params=params).content == original


def test_put_requires_precondition_and_rejects_stale_etag(client):
    params = agent_params("conditional")
    assert create_json_profile(client, "/agents/profile", params).status_code == 204
    current = client.get("/agents/profile", params=params)

    no_header = client.put(
        "/agents/profile",
        params=params,
        content=b'{"theme":"light"}',
        headers={"Content-Type": "application/json"},
    )
    stale = client.put(
        "/agents/profile",
        params=params,
        content=b'{"theme":"light"}',
        headers={"Content-Type": "application/json", "If-Match": '"stale"'},
    )
    updated = client.put(
        "/agents/profile",
        params=params,
        content=b'{"theme":"light"}',
        headers={"Content-Type": "application/json", "If-Match": current.headers["etag"]},
    )

    assert no_header.status_code == 409
    assert stale.status_code == 412
    assert updated.status_code == 204
    assert client.get("/agents/profile", params=params).json() == {"theme": "light"}


def test_if_none_match_prevents_overwrite(client):
    params = activity_params("create-only")
    assert create_json_profile(client, "/activities/profile", params).status_code == 204

    response = create_json_profile(
        client,
        "/activities/profile",
        params,
        content={"second": True},
    )

    assert response.status_code == 412


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/agents/profile", agent_params("delete-me")),
        ("/activities/profile", activity_params("delete-me")),
    ],
)
def test_delete_with_if_match(path, params, client):
    create_json_profile(client, path, params)
    current = client.get(path, params=params)

    stale = client.delete(path, params=params, headers={"If-Match": '"stale"'})
    deleted = client.delete(path, params=params, headers={"If-Match": current.headers["etag"]})

    assert stale.status_code == 412
    assert deleted.status_code == 204
    assert client.get(path, params=params).status_code == 404


@pytest.mark.parametrize(
    ("path", "first_params", "second_params", "list_params"),
    [
        (
            "/agents/profile",
            agent_params("first"),
            agent_params("second"),
            agent_params(),
        ),
        (
            "/activities/profile",
            activity_params("first"),
            activity_params("second"),
            activity_params(),
        ),
    ],
)
def test_lists_profile_ids_and_filters_since(
    client, path, first_params, second_params, list_params
):
    create_json_profile(client, path, first_params)
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT updated_at FROM profile_documents WHERE profile_id = 'first'"
            )
            first_updated_at = cur.fetchone()[0]

    create_json_profile(client, path, second_params)

    all_profiles = client.get(path, params=list_params)
    recent_profiles = client.get(
        path,
        params={**list_params, "since": first_updated_at.isoformat()},
    )
    future_profiles = client.get(
        path,
        params={
            **list_params,
            "since": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )

    assert all_profiles.json() == ["first", "second"]
    assert "last-modified" in all_profiles.headers
    assert recent_profiles.json() == ["second"]
    assert future_profiles.json() == []
    assert "last-modified" not in future_profiles.headers


def test_database_owner_and_profile_uniqueness():
    values = (
        "agent",
        "mbox:mailto:user@example.com",
        "unique",
        b"{}",
        "application/json",
        hashlib.sha1(b"{}").hexdigest(),
    )
    with pytest.raises(UniqueViolation):
        with psycopg.connect(**get_db_config()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO profile_documents
                        (resource_type, owner_key, profile_id, content, content_type, etag)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    values,
                )
                cur.execute(
                    """
                    INSERT INTO profile_documents
                        (resource_type, owner_key, profile_id, content, content_type, etag)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    values,
                )


def test_concurrent_create_only_requests_are_serialized():
    def create_document():
        try:
            put_profile_document(
                "agent",
                "mbox:mailto:race@example.com",
                "concurrent",
                b"{}",
                "application/json",
                None,
                "*",
            )
            return "created"
        except ProfilePreconditionFailed:
            return "precondition-failed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: create_document(), range(2)))

    assert sorted(outcomes) == ["created", "precondition-failed"]
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM profile_documents WHERE profile_id = 'concurrent'"
            )
            assert cur.fetchone()[0] == 1

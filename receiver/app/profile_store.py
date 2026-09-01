import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

import psycopg

from app.db import get_db_config


class ProfileStoreError(Exception):
    pass


class InvalidProfileRequest(ProfileStoreError):
    pass


class ProfileNotFound(ProfileStoreError):
    pass


class ProfileConflict(ProfileStoreError):
    pass


class ProfilePreconditionFailed(ProfileStoreError):
    pass


@dataclass(frozen=True)
class ProfileDocument:
    content: bytes
    content_type: str
    etag: str
    updated_at: datetime


@dataclass(frozen=True)
class ProfileIdList:
    profile_ids: list[str]
    last_modified: datetime | None


def put_profile_document(
    resource_type: str,
    owner_key: str,
    profile_id: str,
    content: bytes,
    content_type: str,
    if_match: str | None,
    if_none_match: str | None,
) -> None:
    _validate_mutation_headers(if_match, if_none_match)
    _validate_json_document(content, content_type)

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            _lock_document_key(cur, resource_type, owner_key, profile_id)
            current = _select_document(cur, resource_type, owner_key, profile_id)

            if if_match is None and if_none_match is None:
                if current is not None:
                    raise ProfileConflict(
                        "existing profile documents require If-Match or If-None-Match"
                    )
                raise InvalidProfileRequest("PUT requires If-Match or If-None-Match")

            _check_preconditions(current, if_match, if_none_match)
            _upsert_document(
                cur,
                resource_type,
                owner_key,
                profile_id,
                content,
                content_type,
            )


def post_profile_document(
    resource_type: str,
    owner_key: str,
    profile_id: str,
    content: bytes,
    content_type: str,
    if_match: str | None,
    if_none_match: str | None,
) -> None:
    _validate_mutation_headers(if_match, if_none_match)

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            _lock_document_key(cur, resource_type, owner_key, profile_id)
            current = _select_document(cur, resource_type, owner_key, profile_id)
            _check_preconditions(current, if_match, if_none_match)

            if current is None:
                if _base_content_type(content_type) == "application/json":
                    _load_json_object(content, "POST content")
                merged_content = content
                merged_content_type = content_type
            else:
                merged_content = _merge_json_document(current, content, content_type)
                merged_content_type = current.content_type

            _upsert_document(
                cur,
                resource_type,
                owner_key,
                profile_id,
                merged_content,
                merged_content_type,
            )


def get_profile_document(
    resource_type: str, owner_key: str, profile_id: str
) -> ProfileDocument:
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            document = _select_document(cur, resource_type, owner_key, profile_id)

    if document is None:
        raise ProfileNotFound("profile document not found")
    return document


def list_profile_ids(
    resource_type: str, owner_key: str, since: datetime | None
) -> ProfileIdList:
    query = """
        SELECT profile_id, updated_at
        FROM profile_documents
        WHERE resource_type = %s AND owner_key = %s
    """
    params: list[object] = [resource_type, owner_key]
    if since is not None:
        query += " AND updated_at > %s"
        params.append(since)
    query += " ORDER BY profile_id"

    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return ProfileIdList(
        profile_ids=[row[0] for row in rows],
        last_modified=max((row[1] for row in rows), default=None),
    )


def delete_profile_document(
    resource_type: str,
    owner_key: str,
    profile_id: str,
    if_match: str | None,
) -> None:
    with psycopg.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            _lock_document_key(cur, resource_type, owner_key, profile_id)
            current = _select_document(cur, resource_type, owner_key, profile_id)
            if current is None:
                raise ProfileNotFound("profile document not found")
            if if_match is not None and not _etag_matches(if_match, current.etag):
                raise ProfilePreconditionFailed("If-Match does not match the current ETag")

            cur.execute(
                """
                DELETE FROM profile_documents
                WHERE resource_type = %s AND owner_key = %s AND profile_id = %s
                """,
                (resource_type, owner_key, profile_id),
            )


def _lock_document_key(cur, resource_type: str, owner_key: str, profile_id: str) -> None:
    lock_key = "\x1f".join((resource_type, owner_key, profile_id))
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))


def _select_document(cur, resource_type: str, owner_key: str, profile_id: str):
    cur.execute(
        """
        SELECT content, content_type, etag, updated_at
        FROM profile_documents
        WHERE resource_type = %s AND owner_key = %s AND profile_id = %s
        FOR UPDATE
        """,
        (resource_type, owner_key, profile_id),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return ProfileDocument(content=bytes(row[0]), content_type=row[1], etag=row[2], updated_at=row[3])


def _upsert_document(
    cur,
    resource_type: str,
    owner_key: str,
    profile_id: str,
    content: bytes,
    content_type: str,
) -> None:
    etag = hashlib.sha1(content).hexdigest()  # noqa: S324 - required by xAPI 1.0.x
    cur.execute(
        """
        INSERT INTO profile_documents (
            resource_type, owner_key, profile_id, content, content_type, etag
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (resource_type, owner_key, profile_id) DO UPDATE
        SET content = EXCLUDED.content,
            content_type = EXCLUDED.content_type,
            etag = EXCLUDED.etag,
            updated_at = clock_timestamp()
        """,
        (resource_type, owner_key, profile_id, content, content_type, etag),
    )


def _validate_mutation_headers(if_match: str | None, if_none_match: str | None) -> None:
    if if_match is not None and if_none_match is not None:
        raise InvalidProfileRequest("If-Match and If-None-Match cannot be used together")
    if if_none_match is not None and if_none_match.strip() != "*":
        raise InvalidProfileRequest('this xAPI subset supports only If-None-Match: "*"')


def _check_preconditions(
    current: ProfileDocument | None,
    if_match: str | None,
    if_none_match: str | None,
) -> None:
    if if_match is not None:
        if current is None or not _etag_matches(if_match, current.etag):
            raise ProfilePreconditionFailed("If-Match does not match the current ETag")
    if if_none_match is not None and current is not None:
        raise ProfilePreconditionFailed("If-None-Match precondition failed")


def _etag_matches(header_value: str, current_etag: str) -> bool:
    if header_value.strip() == "*":
        return True
    return f'"{current_etag}"' in {tag.strip() for tag in header_value.split(",")}


def _merge_json_document(
    current: ProfileDocument, posted_content: bytes, posted_content_type: str
) -> bytes:
    if (
        _base_content_type(current.content_type) != "application/json"
        or _base_content_type(posted_content_type) != "application/json"
    ):
        raise InvalidProfileRequest(
            "POST merge requires both existing and submitted documents to be application/json"
        )

    existing_object = _load_json_object(current.content, "existing document")
    posted_object = _load_json_object(posted_content, "POST content")
    existing_object.update(posted_object)
    return json.dumps(
        existing_object,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_json_document(content: bytes, content_type: str) -> None:
    if _base_content_type(content_type) != "application/json":
        return
    try:
        json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidProfileRequest("application/json document is not valid JSON") from exc


def _load_json_object(content: bytes, label: str) -> dict:
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidProfileRequest(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise InvalidProfileRequest(f"{label} must be a JSON object for POST merge")
    return value


def _base_content_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()

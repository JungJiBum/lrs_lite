from datetime import datetime, timezone
from email.utils import format_datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.profile_identity import (
    InvalidProfileOwner,
    canonicalize_activity,
    canonicalize_agent,
)
from app.profile_store import (
    InvalidProfileRequest,
    ProfileConflict,
    ProfileNotFound,
    ProfilePreconditionFailed,
    delete_profile_document,
    get_profile_document,
    list_profile_ids,
    post_profile_document,
    put_profile_document,
)

router = APIRouter()


@router.put("/agents/profile", status_code=status.HTTP_204_NO_CONTENT)
async def put_agent_profile(
    request: Request,
    agent: str = Query(),
    profile_id: str = Query(alias="profileId", min_length=1),
    content_type: str = Header(
        default="application/octet-stream", alias="Content-Type"
    ),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    owner_key = _agent_owner_key(agent)
    return await _put(
        request,
        "agent",
        owner_key,
        profile_id,
        content_type,
        if_match,
        if_none_match,
    )


@router.post("/agents/profile", status_code=status.HTTP_204_NO_CONTENT)
async def post_agent_profile(
    request: Request,
    agent: str = Query(),
    profile_id: str = Query(alias="profileId", min_length=1),
    content_type: str = Header(
        default="application/octet-stream", alias="Content-Type"
    ),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    owner_key = _agent_owner_key(agent)
    return await _post(
        request,
        "agent",
        owner_key,
        profile_id,
        content_type,
        if_match,
        if_none_match,
    )


@router.get("/agents/profile")
def get_agent_profile(
    agent: str = Query(),
    profile_id: str | None = Query(default=None, alias="profileId", min_length=1),
    since: datetime | None = Query(default=None),
):
    return _get("agent", _agent_owner_key(agent), profile_id, since)


@router.delete("/agents/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_profile(
    agent: str = Query(),
    profile_id: str = Query(alias="profileId", min_length=1),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    if if_none_match is not None:
        raise HTTPException(
            status_code=400, detail="DELETE supports If-Match, not If-None-Match"
        )
    return _delete("agent", _agent_owner_key(agent), profile_id, if_match)


@router.put("/activities/profile", status_code=status.HTTP_204_NO_CONTENT)
async def put_activity_profile(
    request: Request,
    activity_id: str = Query(alias="activityId"),
    profile_id: str = Query(alias="profileId", min_length=1),
    content_type: str = Header(
        default="application/octet-stream", alias="Content-Type"
    ),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    owner_key = _activity_owner_key(activity_id)
    return await _put(
        request,
        "activity",
        owner_key,
        profile_id,
        content_type,
        if_match,
        if_none_match,
    )


@router.post("/activities/profile", status_code=status.HTTP_204_NO_CONTENT)
async def post_activity_profile(
    request: Request,
    activity_id: str = Query(alias="activityId"),
    profile_id: str = Query(alias="profileId", min_length=1),
    content_type: str = Header(
        default="application/octet-stream", alias="Content-Type"
    ),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    owner_key = _activity_owner_key(activity_id)
    return await _post(
        request,
        "activity",
        owner_key,
        profile_id,
        content_type,
        if_match,
        if_none_match,
    )


@router.get("/activities/profile")
def get_activity_profile(
    activity_id: str = Query(alias="activityId"),
    profile_id: str | None = Query(default=None, alias="profileId", min_length=1),
    since: datetime | None = Query(default=None),
):
    return _get("activity", _activity_owner_key(activity_id), profile_id, since)


@router.delete("/activities/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity_profile(
    activity_id: str = Query(alias="activityId"),
    profile_id: str = Query(alias="profileId", min_length=1),
    if_match: str | None = Header(default=None, alias="If-Match"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    if if_none_match is not None:
        raise HTTPException(
            status_code=400, detail="DELETE supports If-Match, not If-None-Match"
        )
    return _delete("activity", _activity_owner_key(activity_id), profile_id, if_match)


async def _put(
    request: Request,
    resource_type: str,
    owner_key: str,
    profile_id: str,
    content_type: str,
    if_match: str | None,
    if_none_match: str | None,
):
    try:
        put_profile_document(
            resource_type,
            owner_key,
            profile_id,
            await request.body(),
            content_type,
            if_match,
            if_none_match,
        )
    except Exception as exc:
        _raise_profile_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _post(
    request: Request,
    resource_type: str,
    owner_key: str,
    profile_id: str,
    content_type: str,
    if_match: str | None,
    if_none_match: str | None,
):
    try:
        post_profile_document(
            resource_type,
            owner_key,
            profile_id,
            await request.body(),
            content_type,
            if_match,
            if_none_match,
        )
    except Exception as exc:
        _raise_profile_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get(
    resource_type: str,
    owner_key: str,
    profile_id: str | None,
    since: datetime | None,
):
    if profile_id is not None:
        if since is not None:
            raise HTTPException(
                status_code=400, detail="since is valid only when listing profile ids"
            )
        try:
            document = get_profile_document(resource_type, owner_key, profile_id)
        except Exception as exc:
            _raise_profile_http_error(exc)
        return Response(
            content=document.content,
            status_code=200,
            headers={
                "Content-Type": document.content_type,
                "ETag": f'"{document.etag}"',
                "Last-Modified": _http_date(document.updated_at),
            },
        )

    normalized_since = _validate_since(since)
    result = list_profile_ids(resource_type, owner_key, normalized_since)
    headers = {}
    if result.last_modified is not None:
        headers["Last-Modified"] = _http_date(result.last_modified)
    return JSONResponse(content=result.profile_ids, headers=headers)


def _delete(resource_type: str, owner_key: str, profile_id: str, if_match: str | None):
    try:
        delete_profile_document(resource_type, owner_key, profile_id, if_match)
    except Exception as exc:
        _raise_profile_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _agent_owner_key(agent: str) -> str:
    try:
        return canonicalize_agent(agent).owner_key
    except InvalidProfileOwner as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _activity_owner_key(activity_id: str) -> str:
    try:
        return canonicalize_activity(activity_id)
    except InvalidProfileOwner as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_since(since: datetime | None) -> datetime | None:
    if since is not None and since.tzinfo is None:
        raise HTTPException(status_code=400, detail="since must include a timezone")
    return since


def _http_date(value: datetime) -> str:
    return format_datetime(value.astimezone(timezone.utc), usegmt=True)


def _raise_profile_http_error(exc: Exception) -> None:
    if isinstance(exc, InvalidProfileRequest):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ProfileNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProfileConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ProfilePreconditionFailed):
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    raise exc

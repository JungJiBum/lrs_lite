import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from app.db import check_db_connection, init_db, list_statements, save_statement
from app.errors import StatementConflictError
from app.models import Statement

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
def index():
    return {"message": "receiver is running"}


@app.get("/health")
def health():
    db = check_db_connection()

    return {
        "status": "ok" if db["connected"] else "degraded",
        "db": db,
    }


@app.post("/statements")
def create_statement(statement: Statement):
    payload = statement.model_dump(mode="json", by_alias=True, exclude_unset=True)
    payload["id"] = str(statement.id)

    try:
        saved = save_statement(payload)
    except StatementConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("statement storage failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="statement 저장 실패",
        ) from exc

    return {
        "received": True,
        "idempotent": not saved["created"],
        "saved": saved,
        "payload": payload,
    }


@app.get("/statements")
def get_statements(limit: int = 50):
    return {
        "items": list_statements(limit),
    }

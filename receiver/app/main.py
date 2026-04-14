import json

from fastapi import FastAPI, HTTPException

from app.db import check_db_connection, init_db, list_statements, save_statement

app = FastAPI()


@app.on_event("startup")
def startup():
    init_db()


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
def create_statement(payload: dict):
    print(
        f"received xAPI statement: {json.dumps(payload, ensure_ascii=False)}",
        flush=True,
    )

    try:
        saved = save_statement(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"statement 저장 실패: {exc}") from exc

    return {
        "received": True,
        "saved": saved,
        "payload": payload,
    }


@app.get("/statements")
def get_statements(limit: int = 50):
    return {
        "items": list_statements(limit),
    }

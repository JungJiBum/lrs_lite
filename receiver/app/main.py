from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def index():
    return {"message": "receiver is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/statements")
def create_statement(payload: dict):
    return {"received": True, "payload": payload}

import os

import requests
from flask import Flask, render_template

app = Flask(__name__)
RECEIVER_API_URL = os.getenv("RECEIVER_API_URL", "http://localhost:8080")


def fetch_statements():
    response = requests.get(f"{RECEIVER_API_URL}/statements", timeout=5)
    response.raise_for_status()
    return response.json()["items"]


@app.get("/")
def index():
    error = None
    statements = []

    try:
        statements = fetch_statements()
    except requests.RequestException as exc:
        error = str(exc)

    return render_template("index.html", statements=statements, error=error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001)

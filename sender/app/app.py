import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
RECEIVER_BASE_URL = os.getenv("RECEIVER_BASE_URL", "http://localhost:8080")
DUMMY_DATA_PATH = Path(__file__).with_name("dummy.json")


def load_dummy_data():
    with DUMMY_DATA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def build_dummy_statement():
    dummy_data = load_dummy_data()
    now = datetime.now(timezone.utc).isoformat()
    actor = random.choice(dummy_data["actors"])
    verb = random.choice(dummy_data["verbs"])
    quiz = random.choice(dummy_data["objects"])
    statement = {
        "id": str(uuid4()),
        "actor": actor,
        "verb": {
            "id": verb["id"],
            "display": verb["display"],
        },
        "object": {
            "id": f"{quiz['id']}/questions/{random.randint(1, quiz['questionCount'])}",
            "definition": {
                "name": {"ko-KR": quiz["name"]},
                "description": {"ko-KR": quiz["description"]},
                "type": dummy_data["activityType"],
            },
            "objectType": "Activity",
        },
        "context": {
            "platform": "portfolio-sender",
            "language": "ko-KR",
            "extensions": {
                "https://portfolio.local/extensions/sessionId": (
                    f"demo-session-{random.randint(1, dummy_data['sessionCount'])}"
                ),
                "https://portfolio.local/extensions/clientRole": "sender",
                "https://portfolio.local/extensions/quizType": quiz["name"],
            },
        },
        "timestamp": now,
    }

    if verb.get("includeResult"):
        raw_score = random.randint(
            dummy_data["score"]["minGenerated"],
            dummy_data["score"]["maxGenerated"],
        )
        success = raw_score >= dummy_data["score"]["passingScore"] and not verb.get("marksFailure")

        statement["result"] = {
            "success": success,
            "completion": verb.get("completion", False),
            "score": {
                "scaled": round(raw_score / 100, 2),
                "raw": raw_score,
                "min": dummy_data["score"]["min"],
                "max": dummy_data["score"]["max"],
            },
            "response": random.choice(dummy_data["responses"]),
        }

    return statement


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/dummy-statement")
def dummy_statement():
    return jsonify(build_dummy_statement())


@app.post("/send-statement")
def send_statement():
    statement = request.get_json(silent=True)

    if not statement:
        return jsonify({"error": "전송할 JSON payload가 없습니다."}), 400

    try:
        response = requests.post(
            f"{RECEIVER_BASE_URL}/statements",
            json=statement,
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify(
        {
            "sent": True,
            "receiverStatus": response.status_code,
            "receiverResponse": response.json(),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

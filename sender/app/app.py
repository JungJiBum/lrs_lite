from flask import Flask

app = Flask(__name__)


@app.get("/")
def index():
    return "sender is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

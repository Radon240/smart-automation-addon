import json
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)


def load_options() -> dict:
    options_file = Path("/data/options.json")
    if options_file.exists():
        try:
            return json.loads(options_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


@app.get("/")
def index():
    options = load_options()
    message = options.get("message", "Hello from AdaptiveAutomation")
    log_level = options.get("log_level", "info")
    return f"AdaptiveAutomation is running. message='{message}', log_level='{log_level}'"


@app.get("/health")
def health():
    return jsonify(status="ok", addon="AdaptiveAutomation")


@app.get("/api/config")
def config():
    options = load_options()
    return jsonify(
        log_level=options.get("log_level", "info"),
        message=options.get("message", "Hello from AdaptiveAutomation"),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=False)

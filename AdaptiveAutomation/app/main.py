import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request

from user_action_model import ModelStore, UserActionModel, action_events_from_states

app = Flask(__name__)

SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
SUPERVISOR_API_URL = os.getenv("SUPERVISOR_API_URL", "http://supervisor/core/api")

MODEL_STORE = ModelStore("/data/model.json")

last_trained_at = None
last_training_samples = 0


def load_options() -> dict:
    options_file = Path("/data/options.json")
    defaults = {
        "log_level": "info",
        "message": "Hello from AdaptiveAutomation",
        "history_days": 7,
        "min_support": 5,
        "min_confidence": 0.6,
        "prediction_limit": 10,
    }
    if options_file.exists():
        try:
            payload = json.loads(options_file.read_text(encoding="utf-8"))
            defaults.update(payload)
        except Exception:
            pass
    return defaults


def _parse_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _parse_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _build_model_from_options(options: Dict[str, Any]) -> UserActionModel:
    model = MODEL_STORE.load()
    min_support = _parse_int(options.get("min_support", 5), 5, 1, 1000)
    min_confidence = _parse_float(options.get("min_confidence", 0.6), 0.6, 0.0, 1.0)

    if model is None:
        model = UserActionModel(min_support=min_support, min_confidence=min_confidence)
    else:
        model.set_thresholds(min_support=min_support, min_confidence=min_confidence)

    return model


def _flatten_history_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    flattened: List[Dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, list):
            for item in entry:
                if isinstance(item, dict):
                    flattened.append(item)
        elif isinstance(entry, dict):
            flattened.append(entry)
    return flattened


def _fetch_history_from_home_assistant(history_days: int) -> List[Dict[str, Any]]:
    if not SUPERVISOR_TOKEN:
        raise RuntimeError("SUPERVISOR_TOKEN is missing")

    base_url = SUPERVISOR_API_URL.rstrip("/")
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=history_days)

    query = urlencode(
        {
            "start_time": start_time.isoformat() + "Z",
            "end_time": end_time.isoformat() + "Z",
        }
    )
    url = f"{base_url}/history/period?{query}"

    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as e:
        raise RuntimeError(f"Home Assistant API HTTP error: {e.code}") from e
    except URLError as e:
        raise RuntimeError(f"Home Assistant API connection error: {e.reason}") from e

    try:
        payload = json.loads(raw)
    except Exception as e:
        raise RuntimeError("Invalid JSON from Home Assistant history endpoint") from e

    return _flatten_history_payload(payload)


@app.get("/")
def index():
    options = load_options()
    message = options.get("message", "Hello from AdaptiveAutomation")
    return (
        "AdaptiveAutomation is running. "
        f"message='{message}'. Use POST /api/train and GET /api/predict"
    )


@app.get("/health")
def health():
    model = MODEL_STORE.load()
    return jsonify(
        status="ok",
        addon="AdaptiveAutomation",
        model_loaded=bool(model),
        model_stats=model.stats() if model else None,
        last_trained_at=last_trained_at,
        last_training_samples=last_training_samples,
    )


@app.get("/api/config")
def config():
    options = load_options()
    return jsonify(
        log_level=options.get("log_level", "info"),
        message=options.get("message", "Hello from AdaptiveAutomation"),
        history_days=_parse_int(options.get("history_days", 7), 7, 1, 365),
        min_support=_parse_int(options.get("min_support", 5), 5, 1, 1000),
        min_confidence=_parse_float(options.get("min_confidence", 0.6), 0.6, 0.0, 1.0),
        prediction_limit=_parse_int(options.get("prediction_limit", 10), 10, 1, 100),
        last_trained_at=last_trained_at,
        last_training_samples=last_training_samples,
    )


@app.post("/api/train")
def train():
    global last_trained_at, last_training_samples

    options = load_options()
    history_days = _parse_int(options.get("history_days", 7), 7, 1, 365)

    try:
        ha_states = _fetch_history_from_home_assistant(history_days)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    events = action_events_from_states(ha_states)
    model = _build_model_from_options(options)
    model.fit(events)
    MODEL_STORE.save(model)

    last_trained_at = datetime.utcnow().isoformat() + "Z"
    last_training_samples = len(events)

    return jsonify(
        status="ok",
        trained_at=last_trained_at,
        history_states=len(ha_states),
        training_samples=last_training_samples,
        stats=model.stats(),
    )


@app.post("/api/train-from-events")
def train_from_events():
    """
    Local testing helper: accepts JSON array of HA state snapshots.
    """
    global last_trained_at, last_training_samples

    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        return jsonify(status="error", error="Body must be a JSON array of state snapshots"), 400

    options = load_options()
    events = action_events_from_states(payload)
    model = _build_model_from_options(options)
    model.fit(events)
    MODEL_STORE.save(model)

    last_trained_at = datetime.utcnow().isoformat() + "Z"
    last_training_samples = len(events)

    return jsonify(
        status="ok",
        trained_at=last_trained_at,
        training_samples=last_training_samples,
        stats=model.stats(),
    )


@app.route("/api/predict", methods=["GET", "POST"])
def predict():
    options = load_options()
    model = _build_model_from_options(options)

    body = request.get_json(silent=True) if request.method == "POST" else None
    ts_str = None
    if isinstance(body, dict):
        ts_str = body.get("timestamp")

    if ts_str:
        try:
            when = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except Exception:
            return jsonify(status="error", error="Invalid timestamp format"), 400
    else:
        when = datetime.utcnow()

    limit = _parse_int(options.get("prediction_limit", 10), 10, 1, 100)
    if isinstance(body, dict) and "limit" in body:
        limit = _parse_int(body.get("limit"), limit, 1, 100)

    predictions = model.predict(when=when, limit=limit)

    return jsonify(
        status="ok",
        at=when.isoformat(),
        predictions=predictions,
        stats=model.stats(),
        last_trained_at=last_trained_at,
        last_training_samples=last_training_samples,
    )


@app.get("/api/model-info")
def model_info():
    model = MODEL_STORE.load()
    return jsonify(
        status="ok",
        model_loaded=bool(model),
        stats=model.stats() if model else None,
        model_file="/data/model.json",
        last_trained_at=last_trained_at,
        last_training_samples=last_training_samples,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=False)

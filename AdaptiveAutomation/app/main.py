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
    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>AdaptiveAutomation API Console</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 1000px;
      margin: 0 auto;
      padding: 16px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
    }}
    .muted {{
      color: #94a3b8;
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    button {{
      border: 1px solid #334155;
      background: #1e293b;
      color: #e2e8f0;
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      font-size: 14px;
      text-align: left;
    }}
    button:hover {{
      background: #273449;
    }}
    .panel {{
      margin-top: 14px;
      border: 1px solid #334155;
      border-radius: 10px;
      background: #111827;
      padding: 12px;
    }}
    textarea {{
      width: 100%;
      min-height: 120px;
      background: #020617;
      color: #e2e8f0;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      font-family: Consolas, monospace;
      font-size: 13px;
      box-sizing: border-box;
    }}
    pre {{
      margin: 0;
      padding: 12px;
      background: #020617;
      border: 1px solid #334155;
      border-radius: 8px;
      overflow: auto;
      max-height: 50vh;
      font-size: 12px;
      line-height: 1.35;
    }}
    .row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .hint {{
      color: #a5b4fc;
      font-size: 12px;
      margin-bottom: 8px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>AdaptiveAutomation API Console</h1>
    <div class="muted">Message from config: {message}</div>
    <div class="muted">Use this ingress page to call model API endpoints.</div>

    <div class="grid">
      <button id="btn-health">GET /health</button>
      <button id="btn-config">GET /api/config</button>
      <button id="btn-model">GET /api/model-info</button>
      <button id="btn-train">POST /api/train</button>
      <button id="btn-predict-now">GET /api/predict</button>
      <button id="btn-predict-custom">POST /api/predict (custom body)</button>
      <button id="btn-train-events">POST /api/train-from-events (custom body)</button>
    </div>

    <div class="panel">
      <div class="hint">Editable request body for POST endpoints:</div>
      <textarea id="request-body">{{
  "timestamp": "2026-02-19T18:00:00Z",
  "limit": 10
}}</textarea>
      <div class="row">
        <button id="btn-format">Format JSON</button>
      </div>
    </div>

    <div class="panel">
      <div class="hint">Response:</div>
      <pre id="output">Ready.</pre>
    </div>
  </div>

  <script>
    const output = document.getElementById("output");
    const requestBody = document.getElementById("request-body");

    function show(title, payload) {{
      let bodyText = payload;
      if (typeof payload !== "string") {{
        try {{
          bodyText = JSON.stringify(payload, null, 2);
        }} catch (_) {{
          bodyText = String(payload);
        }}
      }}
      output.textContent = title + "\\n\\n" + bodyText;
    }}

    async function callApi(method, url, body = null) {{
      try {{
        show("Request", {{ method, url, body }});
        const res = await fetch(url, {{
          method,
          headers: body ? {{ "Content-Type": "application/json" }} : undefined,
          body: body ? JSON.stringify(body) : undefined
        }});

        const text = await res.text();
        let json;
        try {{
          json = JSON.parse(text);
        }} catch (_) {{
          json = text;
        }}
        show(`${{method}} ${{url}} -> ${{res.status}}`, json);
      }} catch (err) {{
        show("Error", String(err));
      }}
    }}

    function parseBody() {{
      try {{
        return JSON.parse(requestBody.value || "{{}}");
      }} catch (err) {{
        show("Invalid JSON", String(err));
        return null;
      }}
    }}

    document.getElementById("btn-health").onclick = () => callApi("GET", "health");
    document.getElementById("btn-config").onclick = () => callApi("GET", "api/config");
    document.getElementById("btn-model").onclick = () => callApi("GET", "api/model-info");
    document.getElementById("btn-train").onclick = () => callApi("POST", "api/train", {{}});
    document.getElementById("btn-predict-now").onclick = () => callApi("GET", "api/predict");
    document.getElementById("btn-predict-custom").onclick = () => {{
      const body = parseBody();
      if (body !== null) callApi("POST", "api/predict", body);
    }};
    document.getElementById("btn-train-events").onclick = () => {{
      const body = parseBody();
      if (body !== null) callApi("POST", "api/train-from-events", body);
    }};
    document.getElementById("btn-format").onclick = () => {{
      const body = parseBody();
      if (body !== null) requestBody.value = JSON.stringify(body, null, 2);
    }};
  </script>
</body>
</html>
"""
    return html


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

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.error import URLError, HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request

from routine_patterns import build_routine_suggestions
from sequence_patterns import build_sequence_suggestions
from user_action_model import ModelStore, UserActionModel, action_events_from_states

app = Flask(__name__)

MODEL_STORE = ModelStore("/data/model.json")
TRAINABLE_DOMAINS = {
    "light",
    "switch",
    "climate",
    "cover",
    "fan",
    "lock",
    "media_player",
    "input_boolean",
    "script",
    "scene",
}

last_trained_at = None
last_training_samples = 0


def _read_first_existing(paths: List[str]) -> str:
    for path in paths:
        p = Path(path)
        if p.exists():
            try:
                value = p.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except Exception:
                continue
    return ""


def get_supervisor_token() -> str:
    token = (os.getenv("SUPERVISOR_TOKEN") or "").strip()
    if token:
        return token

    token = (os.getenv("HASSIO_TOKEN") or "").strip()
    if token:
        return token

    return _read_first_existing(
        [
            "/run/s6/container_environment/SUPERVISOR_TOKEN",
            "/run/s6/container_environment/HASSIO_TOKEN",
        ]
    )


def get_supervisor_api_url() -> str:
    raw = (
        os.getenv("SUPERVISOR_API_URL")
        or os.getenv("HASSIO_URL")
        or "http://supervisor/core/api"
    ).strip()
    if raw.endswith("/"):
        raw = raw[:-1]
    if not raw.endswith("/api"):
        raw = f"{raw}/api"
    return raw


def load_options() -> dict:
    options_file = Path("/data/options.json")
    defaults = {
        "log_level": "info",
        "message": "Hello from AdaptiveAutomation",
        "history_days": 7,
        "min_support": 5,
        "min_confidence": 0.6,
        "prediction_limit": 10,
        "allow_relaxed_fallback": True,
        "routine_min_support_days": 3,
        "routine_min_confidence": 0.4,
        "arrival_to_door_minutes": 20,
        "door_to_light_minutes": 20,
        "sequence_window_minutes": 30,
        "sequence_min_support_days": 3,
        "sequence_min_confidence": 0.35,
        "sequence_limit": 20,
        "enabled_domains": sorted(TRAINABLE_DOMAINS),
    }
    if options_file.exists():
        try:
            payload = json.loads(options_file.read_text(encoding="utf-8"))
            defaults.update(payload)
        except Exception:
            pass
    return defaults


def save_options(options: Dict[str, Any]) -> None:
    options_file = Path("/data/options.json")
    options_file.parent.mkdir(parents=True, exist_ok=True)
    options_file.write_text(json.dumps(options, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


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


def _fetch_states(base_url: str, supervisor_token: str) -> List[Dict[str, Any]]:
    states_url = f"{base_url}/states"
    req = Request(
        states_url,
        headers={
            "Authorization": f"Bearer {supervisor_token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch entity list from {states_url}: {e}") from e

    if not isinstance(payload, list):
        raise RuntimeError("Invalid /states response format")
    return [item for item in payload if isinstance(item, dict)]


def _collect_domain_counts(states: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        counts[domain] = counts.get(domain, 0) + 1
    return counts


def _resolve_enabled_domains(options: Dict[str, Any], available_domains: Set[str]) -> Set[str]:
    configured = options.get("enabled_domains")
    if isinstance(configured, list):
        values = {
            str(x).strip()
            for x in configured
            if isinstance(x, str) and str(x).strip()
        }
        if values:
            return values & available_domains
    return TRAINABLE_DOMAINS & available_domains


def _fetch_trainable_entity_ids(states: List[Dict[str, Any]], enabled_domains: Set[str]) -> List[str]:
    entity_ids: List[str] = []
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain in enabled_domains:
            entity_ids.append(entity_id)

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for eid in entity_ids:
        if eid in seen:
            continue
        seen.add(eid)
        unique_ids.append(eid)
    return unique_ids


def _fetch_history_from_home_assistant(history_days: int) -> List[Dict[str, Any]]:
    supervisor_token = get_supervisor_token()
    if not supervisor_token:
        raise RuntimeError(
            "Supervisor token is missing. Checked SUPERVISOR_TOKEN, HASSIO_TOKEN "
            "and /run/s6/container_environment/*"
        )

    options = load_options()
    base_url = get_supervisor_api_url().rstrip("/")
    states = _fetch_states(base_url, supervisor_token)
    available_domains = set(_collect_domain_counts(states).keys())
    enabled_domains = _resolve_enabled_domains(options, available_domains)
    entity_ids = _fetch_trainable_entity_ids(states, enabled_domains)
    if not entity_ids:
        raise RuntimeError(
            "No trainable entities found in /states. "
            "Enabled domains: " + ", ".join(sorted(enabled_domains))
        )

    filter_entity_id = ",".join(entity_ids)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=history_days)

    # Use RFC3339 UTC timestamps.
    start_iso = start_time.isoformat().replace("+00:00", "Z")
    end_iso = end_time.isoformat().replace("+00:00", "Z")

    # Different HA/Supervisor versions accept different history URL shapes.
    query_url = (
        f"{base_url}/history/period?"
        f"{urlencode({'start_time': start_iso, 'end_time': end_iso, 'filter_entity_id': filter_entity_id})}"
    )
    path_url = (
        f"{base_url}/history/period/{quote(start_iso, safe='')}?"
        f"{urlencode({'end_time': end_iso, 'filter_entity_id': filter_entity_id})}"
    )
    candidates = [query_url, path_url]

    last_error = "unknown error"
    for url in candidates:
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {supervisor_token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
            return _flatten_history_payload(payload)
        except HTTPError as e:
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            last_error = f"HTTP {e.code} for {url}. body={body[:400]}"
            continue
        except URLError as e:
            last_error = f"Connection error for {url}: {e.reason}"
            continue
        except Exception as e:
            last_error = f"Unexpected error for {url}: {e}"
            continue

    raise RuntimeError(f"Home Assistant history request failed: {last_error}")


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
    .domains-box {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 6px 10px;
      margin-top: 8px;
    }}
    .domains-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      background: #0b1220;
      font-size: 13px;
    }}
    .domains-item label {{
      display: flex;
      gap: 8px;
      align-items: center;
      cursor: pointer;
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
      <button id="btn-domains">GET /api/domains</button>
      <button id="btn-model">GET /api/model-info</button>
      <button id="btn-train">POST /api/train</button>
      <button id="btn-predict-now">GET /api/predict</button>
      <button id="btn-routines">POST /api/routine-suggestions</button>
      <button id="btn-sequences">POST /api/sequence-suggestions</button>
      <button id="btn-predict-custom">POST /api/predict (custom body)</button>
      <button id="btn-train-events">POST /api/train-from-events (custom body)</button>
    </div>

    <div class="panel">
      <div class="hint">Training domains (loaded dynamically from Home Assistant /states):</div>
      <div class="row">
        <button id="btn-domains-refresh">Refresh domains</button>
        <button id="btn-domains-save">Save selected domains</button>
      </div>
      <div id="domains-box" class="domains-box"></div>
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
    const domainsBox = document.getElementById("domains-box");
    let currentDomains = [];

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

    function renderDomains(domains) {{
      currentDomains = Array.isArray(domains) ? domains : [];
      domainsBox.innerHTML = "";
      if (!currentDomains.length) {{
        domainsBox.innerHTML = "<div class='muted'>No domains found.</div>";
        return;
      }}

      currentDomains.forEach((item) => {{
        const wrapper = document.createElement("div");
        wrapper.className = "domains-item";

        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = !!item.enabled;
        checkbox.dataset.domain = item.domain;

        const text = document.createElement("span");
        text.textContent = item.domain + " (" + item.entity_count + ")";
        label.appendChild(checkbox);
        label.appendChild(text);

        const badge = document.createElement("span");
        badge.className = "muted";
        badge.textContent = item.recommended ? "recommended" : "";

        wrapper.appendChild(label);
        wrapper.appendChild(badge);
        domainsBox.appendChild(wrapper);
      }});
    }}

    function collectEnabledDomains() {{
      const checked = domainsBox.querySelectorAll("input[type='checkbox']:checked");
      const values = [];
      checked.forEach((el) => {{
        if (el.dataset && el.dataset.domain) values.push(el.dataset.domain);
      }});
      return values;
    }}

    async function loadDomains() {{
      try {{
        const res = await fetch("api/domains");
        const text = await res.text();
        let json;
        try {{
          json = JSON.parse(text);
        }} catch (_) {{
          json = text;
        }}
        if (res.ok && json && Array.isArray(json.domains)) {{
          renderDomains(json.domains);
        }}
        show("GET api/domains -> " + res.status, json);
      }} catch (err) {{
        show("Error loading domains", String(err));
      }}
    }}

    async function saveDomains() {{
      const enabledDomains = collectEnabledDomains();
      await callApi("POST", "api/domains", {{ enabled_domains: enabledDomains }});
      await loadDomains();
    }}

    document.getElementById("btn-health").onclick = () => callApi("GET", "health");
    document.getElementById("btn-config").onclick = () => callApi("GET", "api/config");
    document.getElementById("btn-domains").onclick = () => callApi("GET", "api/domains");
    document.getElementById("btn-domains-refresh").onclick = () => loadDomains();
    document.getElementById("btn-domains-save").onclick = () => saveDomains();
    document.getElementById("btn-model").onclick = () => callApi("GET", "api/model-info");
    document.getElementById("btn-train").onclick = () => callApi("POST", "api/train", {{}});
    document.getElementById("btn-predict-now").onclick = () => callApi("GET", "api/predict");
    document.getElementById("btn-routines").onclick = () => callApi("POST", "api/routine-suggestions", {{}});
    document.getElementById("btn-sequences").onclick = () => callApi("POST", "api/sequence-suggestions", {{}});
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
    loadDomains();
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
        allow_relaxed_fallback=_parse_bool(options.get("allow_relaxed_fallback", True), True),
        routine_min_support_days=_parse_int(options.get("routine_min_support_days", 3), 3, 1, 365),
        routine_min_confidence=_parse_float(options.get("routine_min_confidence", 0.4), 0.4, 0.0, 1.0),
        arrival_to_door_minutes=_parse_int(options.get("arrival_to_door_minutes", 20), 20, 1, 180),
        door_to_light_minutes=_parse_int(options.get("door_to_light_minutes", 20), 20, 1, 180),
        sequence_window_minutes=_parse_int(options.get("sequence_window_minutes", 30), 30, 1, 180),
        sequence_min_support_days=_parse_int(options.get("sequence_min_support_days", 3), 3, 1, 365),
        sequence_min_confidence=_parse_float(options.get("sequence_min_confidence", 0.35), 0.35, 0.0, 1.0),
        sequence_limit=_parse_int(options.get("sequence_limit", 20), 20, 1, 100),
        enabled_domains=options.get("enabled_domains", sorted(TRAINABLE_DOMAINS)),
        last_trained_at=last_trained_at,
        last_training_samples=last_training_samples,
    )


@app.get("/api/domains")
def get_domains():
    options = load_options()
    supervisor_token = get_supervisor_token()
    if not supervisor_token:
        return jsonify(status="error", error="Supervisor token is missing"), 502

    try:
        base_url = get_supervisor_api_url().rstrip("/")
        states = _fetch_states(base_url, supervisor_token)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    domain_counts = _collect_domain_counts(states)
    available = set(domain_counts.keys())
    enabled = _resolve_enabled_domains(options, available)

    domains = [
        {
            "domain": domain,
            "entity_count": domain_counts[domain],
            "enabled": domain in enabled,
            "recommended": domain in TRAINABLE_DOMAINS,
        }
        for domain in sorted(domain_counts.keys())
    ]
    return jsonify(status="ok", domains=domains, enabled_domains=sorted(enabled))


@app.post("/api/domains")
def update_domains():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(status="error", error="Body must be a JSON object"), 400

    requested = payload.get("enabled_domains")
    if not isinstance(requested, list):
        return jsonify(status="error", error="enabled_domains must be a JSON array"), 400

    requested_domains = {
        str(x).strip()
        for x in requested
        if isinstance(x, str) and str(x).strip()
    }

    supervisor_token = get_supervisor_token()
    if not supervisor_token:
        return jsonify(status="error", error="Supervisor token is missing"), 502

    try:
        base_url = get_supervisor_api_url().rstrip("/")
        states = _fetch_states(base_url, supervisor_token)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    available_domains = set(_collect_domain_counts(states).keys())
    final_domains = sorted(requested_domains & available_domains)

    options = load_options()
    options["enabled_domains"] = final_domains
    save_options(options)

    return jsonify(status="ok", enabled_domains=final_domains)


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

    last_trained_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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

    last_trained_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
        when = datetime.now(timezone.utc)

    limit = _parse_int(options.get("prediction_limit", 10), 10, 1, 100)
    allow_relaxed_fallback = _parse_bool(options.get("allow_relaxed_fallback", True), True)
    if isinstance(body, dict) and "limit" in body:
        limit = _parse_int(body.get("limit"), limit, 1, 100)
    if isinstance(body, dict) and "allow_relaxed_fallback" in body:
        allow_relaxed_fallback = _parse_bool(body.get("allow_relaxed_fallback"), allow_relaxed_fallback)

    predictions = model.predict(
        when=when,
        limit=limit,
        allow_relaxed_fallback=allow_relaxed_fallback,
        one_per_entity=True,
    )

    return jsonify(
        status="ok",
        at=when.isoformat(),
        predictions=predictions,
        stats=model.stats(),
        allow_relaxed_fallback=allow_relaxed_fallback,
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


@app.post("/api/routine-suggestions")
def routine_suggestions():
    options = load_options()
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}

    history_days = _parse_int(body.get("history_days", options.get("history_days", 7)), 7, 1, 365)
    min_support_days = _parse_int(
        body.get("min_support_days", options.get("routine_min_support_days", 3)),
        3,
        1,
        365,
    )
    min_confidence = _parse_float(
        body.get("min_confidence", options.get("routine_min_confidence", 0.4)),
        0.4,
        0.0,
        1.0,
    )
    arrival_to_door = _parse_int(
        body.get("arrival_to_door_minutes", options.get("arrival_to_door_minutes", 20)),
        20,
        1,
        180,
    )
    door_to_light = _parse_int(
        body.get("door_to_light_minutes", options.get("door_to_light_minutes", 20)),
        20,
        1,
        180,
    )

    try:
        ha_states = _fetch_history_from_home_assistant(history_days)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    suggestions = build_routine_suggestions(
        states=ha_states,
        min_support_days=min_support_days,
        min_confidence=min_confidence,
        arrival_to_door_minutes=arrival_to_door,
        door_to_light_minutes=door_to_light,
    )

    return jsonify(
        status="ok",
        history_states=len(ha_states),
        suggestions=suggestions,
        params={
            "history_days": history_days,
            "min_support_days": min_support_days,
            "min_confidence": min_confidence,
            "arrival_to_door_minutes": arrival_to_door,
            "door_to_light_minutes": door_to_light,
        },
    )


@app.post("/api/sequence-suggestions")
def sequence_suggestions():
    options = load_options()
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}

    history_days = _parse_int(body.get("history_days", options.get("history_days", 7)), 7, 1, 365)
    window_minutes = _parse_int(
        body.get("window_minutes", options.get("sequence_window_minutes", 30)),
        30,
        1,
        180,
    )
    min_support_days = _parse_int(
        body.get("min_support_days", options.get("sequence_min_support_days", 3)),
        3,
        1,
        365,
    )
    min_confidence = _parse_float(
        body.get("min_confidence", options.get("sequence_min_confidence", 0.35)),
        0.35,
        0.0,
        1.0,
    )
    limit = _parse_int(body.get("limit", options.get("sequence_limit", 20)), 20, 1, 100)

    try:
        ha_states = _fetch_history_from_home_assistant(history_days)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    suggestions = build_sequence_suggestions(
        states=ha_states,
        window_minutes=window_minutes,
        min_support_days=min_support_days,
        min_confidence=min_confidence,
        limit=limit,
    )

    return jsonify(
        status="ok",
        history_states=len(ha_states),
        suggestions=suggestions,
        params={
            "history_days": history_days,
            "window_minutes": window_minutes,
            "min_support_days": min_support_days,
            "min_confidence": min_confidence,
            "limit": limit,
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=False)

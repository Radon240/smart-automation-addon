from datetime import datetime, timezone
from typing import Any, Dict

from flask import Flask, jsonify, request

from models.routine_detector import build_routine_suggestions
from models.rule_scorer import (
    normalize_routine_rules,
    normalize_sequence_rules,
    normalize_state_rules,
    rank_rules,
)
from models.sequence_miner import build_sequence_suggestions
from models.state_predictor import UserActionModel, action_events_from_states
from services.history_service import (
    collect_domain_counts,
    fetch_history_from_home_assistant,
    fetch_states,
    get_supervisor_api_url,
    get_supervisor_token,
)
from services.policy_service import apply_policy
from storage.options_store import (
    TRAINABLE_DOMAINS,
    load_options,
    parse_bool,
    parse_float,
    parse_int,
    resolve_enabled_domains,
    save_options,
)
from storage.model_store import build_model_store
from ui.ingress_page import render_ingress_page

app = Flask(__name__)

MODEL_STORE = build_model_store("/data/model.json")

last_trained_at = None
last_training_samples = 0


def _build_model_from_options(options: Dict[str, Any]) -> UserActionModel:
    model = MODEL_STORE.load()
    min_support = parse_int(options.get("min_support", 5), 5, 1, 1000)
    min_confidence = parse_float(options.get("min_confidence", 0.6), 0.6, 0.0, 1.0)

    if model is None:
        model = UserActionModel(min_support=min_support, min_confidence=min_confidence)
    else:
        model.set_thresholds(min_support=min_support, min_confidence=min_confidence)
    return model


def _collect_raw_suggestions(options: Dict[str, Any], suggestion_type: str) -> Dict[str, Any]:
    raw: Dict[str, Any] = {"state": [], "routine": [], "sequence": [], "history_states": 0}

    needs_history = suggestion_type in {"all", "routine", "sequence"}
    ha_states = []
    if needs_history:
        history_days = parse_int(options.get("history_days", 7), 7, 1, 365)
        ha_states = fetch_history_from_home_assistant(history_days)
        raw["history_states"] = len(ha_states)

    if suggestion_type in {"all", "state"}:
        model = _build_model_from_options(options)
        limit = parse_int(options.get("prediction_limit", 10), 10, 1, 100)
        allow_relaxed_fallback = parse_bool(options.get("allow_relaxed_fallback", True), True)
        raw["state"] = model.predict(
            when=datetime.now(timezone.utc),
            limit=limit,
            allow_relaxed_fallback=allow_relaxed_fallback,
            one_per_entity=True,
        )

    if suggestion_type in {"all", "routine"}:
        raw["routine"] = build_routine_suggestions(
            states=ha_states,
            min_support_days=parse_int(options.get("routine_min_support_days", 3), 3, 1, 365),
            min_confidence=parse_float(options.get("routine_min_confidence", 0.4), 0.4, 0.0, 1.0),
            arrival_to_door_minutes=parse_int(options.get("arrival_to_door_minutes", 20), 20, 1, 180),
            door_to_light_minutes=parse_int(options.get("door_to_light_minutes", 20), 20, 1, 180),
        )

    if suggestion_type in {"all", "sequence"}:
        raw["sequence"] = build_sequence_suggestions(
            states=ha_states,
            window_minutes=parse_int(options.get("sequence_window_minutes", 30), 30, 1, 180),
            min_support_days=parse_int(options.get("sequence_min_support_days", 3), 3, 1, 365),
            min_confidence=parse_float(options.get("sequence_min_confidence", 0.35), 0.35, 0.0, 1.0),
            limit=parse_int(options.get("sequence_limit", 20), 20, 1, 100),
        )

    return raw


@app.get("/")
def index():
    options = load_options()
    message = str(options.get("message", "Hello from AdaptiveAutomation"))
    return render_ingress_page(message)


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
        history_days=parse_int(options.get("history_days", 7), 7, 1, 365),
        min_support=parse_int(options.get("min_support", 5), 5, 1, 1000),
        min_confidence=parse_float(options.get("min_confidence", 0.6), 0.6, 0.0, 1.0),
        prediction_limit=parse_int(options.get("prediction_limit", 10), 10, 1, 100),
        allow_relaxed_fallback=parse_bool(options.get("allow_relaxed_fallback", True), True),
        routine_min_support_days=parse_int(options.get("routine_min_support_days", 3), 3, 1, 365),
        routine_min_confidence=parse_float(options.get("routine_min_confidence", 0.4), 0.4, 0.0, 1.0),
        arrival_to_door_minutes=parse_int(options.get("arrival_to_door_minutes", 20), 20, 1, 180),
        door_to_light_minutes=parse_int(options.get("door_to_light_minutes", 20), 20, 1, 180),
        sequence_window_minutes=parse_int(options.get("sequence_window_minutes", 30), 30, 1, 180),
        sequence_min_support_days=parse_int(options.get("sequence_min_support_days", 3), 3, 1, 365),
        sequence_min_confidence=parse_float(options.get("sequence_min_confidence", 0.35), 0.35, 0.0, 1.0),
        sequence_limit=parse_int(options.get("sequence_limit", 20), 20, 1, 100),
        policy_domain_allowlist=options.get("policy_domain_allowlist", []),
        policy_domain_denylist=options.get("policy_domain_denylist", []),
        policy_entity_allowlist=options.get("policy_entity_allowlist", []),
        policy_entity_denylist=options.get("policy_entity_denylist", []),
        policy_one_per_entity=parse_bool(options.get("policy_one_per_entity", False), False),
        rules_limit=parse_int(options.get("rules_limit", 50), 50, 1, 500),
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
        states = fetch_states(base_url, supervisor_token)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    domain_counts = collect_domain_counts(states)
    available = set(domain_counts.keys())
    enabled = resolve_enabled_domains(options, available)

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
        states = fetch_states(base_url, supervisor_token)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    available_domains = set(collect_domain_counts(states).keys())
    final_domains = sorted(requested_domains & available_domains)

    options = load_options()
    options["enabled_domains"] = final_domains
    save_options(options)

    return jsonify(status="ok", enabled_domains=final_domains)


@app.post("/api/train")
def train():
    global last_trained_at, last_training_samples

    options = load_options()
    history_days = parse_int(options.get("history_days", 7), 7, 1, 365)

    try:
        ha_states = fetch_history_from_home_assistant(history_days)
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


@app.post("/api/train/all")
def train_all():
    global last_trained_at, last_training_samples

    options = load_options()
    history_days = parse_int(options.get("history_days", 7), 7, 1, 365)

    try:
        ha_states = fetch_history_from_home_assistant(history_days)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    # Train state model.
    events = action_events_from_states(ha_states)
    state_model = _build_model_from_options(options)
    state_model.fit(events)
    MODEL_STORE.save(state_model)

    # Analyze routine + sequence on the same history snapshot.
    routine_rules = build_routine_suggestions(
        states=ha_states,
        min_support_days=parse_int(options.get("routine_min_support_days", 3), 3, 1, 365),
        min_confidence=parse_float(options.get("routine_min_confidence", 0.4), 0.4, 0.0, 1.0),
        arrival_to_door_minutes=parse_int(options.get("arrival_to_door_minutes", 20), 20, 1, 180),
        door_to_light_minutes=parse_int(options.get("door_to_light_minutes", 20), 20, 1, 180),
    )
    sequence_rules = build_sequence_suggestions(
        states=ha_states,
        window_minutes=parse_int(options.get("sequence_window_minutes", 30), 30, 1, 180),
        min_support_days=parse_int(options.get("sequence_min_support_days", 3), 3, 1, 365),
        min_confidence=parse_float(options.get("sequence_min_confidence", 0.35), 0.35, 0.0, 1.0),
        limit=parse_int(options.get("sequence_limit", 20), 20, 1, 100),
    )

    last_trained_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    last_training_samples = len(events)

    return jsonify(
        status="ok",
        trained_at=last_trained_at,
        history_states=len(ha_states),
        state_training_samples=last_training_samples,
        state_stats=state_model.stats(),
        routine_suggestions_found=len(routine_rules),
        sequence_suggestions_found=len(sequence_rules),
    )


@app.post("/api/train-from-events")
def train_from_events():
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
    ts_str = body.get("timestamp") if isinstance(body, dict) else None

    if ts_str:
        try:
            when = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        except Exception:
            return jsonify(status="error", error="Invalid timestamp format"), 400
    else:
        when = datetime.now(timezone.utc)

    limit = parse_int(options.get("prediction_limit", 10), 10, 1, 100)
    allow_relaxed_fallback = parse_bool(options.get("allow_relaxed_fallback", True), True)
    if isinstance(body, dict) and "limit" in body:
        limit = parse_int(body.get("limit"), limit, 1, 100)
    if isinstance(body, dict) and "allow_relaxed_fallback" in body:
        allow_relaxed_fallback = parse_bool(body.get("allow_relaxed_fallback"), allow_relaxed_fallback)

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


@app.get("/api/suggestions")
def suggestions():
    options = load_options()
    suggestion_type = str(request.args.get("type", "all")).strip().lower()
    if suggestion_type not in {"all", "state", "routine", "sequence"}:
        return jsonify(status="error", error="type must be one of: all,state,routine,sequence"), 400

    try:
        raw = _collect_raw_suggestions(options, suggestion_type)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 502

    rules = []
    rules.extend(normalize_state_rules(raw["state"]))
    rules.extend(normalize_routine_rules(raw["routine"]))
    rules.extend(normalize_sequence_rules(raw["sequence"]))

    rules_limit = parse_int(options.get("rules_limit", 50), 50, 1, 500)
    ranked = rank_rules(rules, limit=rules_limit)
    filtered = apply_policy(ranked, options)
    filtered.sort(
        key=lambda x: (float(x.get("score", 0.0)), float(x.get("confidence", 0.0)), int(x.get("support_days", 0))),
        reverse=True,
    )

    return jsonify(
        status="ok",
        type=suggestion_type,
        history_states=raw.get("history_states", 0),
        counts={
            "state": len(raw["state"]),
            "routine": len(raw["routine"]),
            "sequence": len(raw["sequence"]),
            "combined": len(rules),
            "ranked": len(ranked),
            "after_policy": len(filtered),
        },
        rules=filtered,
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

    history_days = parse_int(body.get("history_days", options.get("history_days", 7)), 7, 1, 365)
    min_support_days = parse_int(
        body.get("min_support_days", options.get("routine_min_support_days", 3)),
        3,
        1,
        365,
    )
    min_confidence = parse_float(
        body.get("min_confidence", options.get("routine_min_confidence", 0.4)),
        0.4,
        0.0,
        1.0,
    )
    arrival_to_door = parse_int(
        body.get("arrival_to_door_minutes", options.get("arrival_to_door_minutes", 20)),
        20,
        1,
        180,
    )
    door_to_light = parse_int(
        body.get("door_to_light_minutes", options.get("door_to_light_minutes", 20)),
        20,
        1,
        180,
    )

    try:
        ha_states = fetch_history_from_home_assistant(history_days)
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

    history_days = parse_int(body.get("history_days", options.get("history_days", 7)), 7, 1, 365)
    window_minutes = parse_int(
        body.get("window_minutes", options.get("sequence_window_minutes", 30)),
        30,
        1,
        180,
    )
    min_support_days = parse_int(
        body.get("min_support_days", options.get("sequence_min_support_days", 3)),
        3,
        1,
        365,
    )
    min_confidence = parse_float(
        body.get("min_confidence", options.get("sequence_min_confidence", 0.35)),
        0.35,
        0.0,
        1.0,
    )
    limit = parse_int(body.get("limit", options.get("sequence_limit", 20)), 20, 1, 100)

    try:
        ha_states = fetch_history_from_home_assistant(history_days)
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

import json
from pathlib import Path
from typing import Any, Dict, Set


TRAINABLE_DOMAINS: Set[str] = {
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

OPTIONS_PATH = Path("/data/options.json")

DEFAULT_OPTIONS: Dict[str, Any] = {
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
    "policy_domain_allowlist": [],
    "policy_domain_denylist": [],
    "policy_entity_allowlist": [],
    "policy_entity_denylist": [],
    "policy_one_per_entity": False,
    "rules_limit": 50,
    "enabled_domains": sorted(TRAINABLE_DOMAINS),
}


def load_options() -> Dict[str, Any]:
    options = DEFAULT_OPTIONS.copy()
    if OPTIONS_PATH.exists():
        try:
            payload = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                options.update(payload)
        except Exception:
            pass
    return options


def save_options(options: Dict[str, Any]) -> None:
    OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPTIONS_PATH.write_text(
        json.dumps(options, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def parse_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def parse_bool(value: Any, default: bool) -> bool:
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


def resolve_enabled_domains(options: Dict[str, Any], available_domains: Set[str]) -> Set[str]:
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

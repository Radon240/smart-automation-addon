from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


ACTION_DOMAINS = {
    "light",
    "switch",
    "climate",
    "cover",
    "fan",
    "lock",
    "media_player",
    "input_boolean",
}


@dataclass
class Transition:
    entity_id: str
    domain: str
    from_state: str
    to_state: str
    timestamp: datetime


def _state_str(value: Any) -> str:
    return str(value or "").strip().lower()


def _try_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _parse_ts(raw: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_transitions(states: Iterable[Dict[str, Any]]) -> List[Transition]:
    by_entity: Dict[str, List[Dict[str, Any]]] = {}
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        ts = _parse_ts(item.get("last_changed") or item.get("last_updated"))
        if ts is None:
            continue
        state = _state_str(item.get("state"))
        by_entity.setdefault(entity_id, []).append({"ts": ts, "state": state})

    transitions: List[Transition] = []
    for entity_id, points in by_entity.items():
        points.sort(key=lambda x: x["ts"])
        domain = entity_id.split(".", 1)[0]
        for i in range(1, len(points)):
            prev_s = points[i - 1]["state"]
            curr_s = points[i]["state"]
            if prev_s == curr_s:
                continue
            transitions.append(
                Transition(
                    entity_id=entity_id,
                    domain=domain,
                    from_state=prev_s,
                    to_state=curr_s,
                    timestamp=points[i]["ts"],
                )
            )

    transitions.sort(key=lambda x: x.timestamp)
    return transitions


def _trigger_signature(ev: Transition) -> Optional[Tuple[str, str, str, str]]:
    # Ignore obvious noise states.
    if ev.to_state in {"", "unknown", "unavailable", "none"}:
        return None

    prev_num = _try_float(ev.from_state)
    curr_num = _try_float(ev.to_state)
    if curr_num is not None:
        rounded = round(curr_num)
        if prev_num is not None:
            delta = curr_num - prev_num
            if abs(delta) > 0.01:
                trend = "up" if delta > 0 else "down"
                return (ev.entity_id, "numeric_trend", trend, f"value~{rounded}")
        return (ev.entity_id, "numeric_state", "value", f"value~{rounded}")

    return (ev.entity_id, "state", "to", ev.to_state)


def _action_signature(ev: Transition) -> Optional[Tuple[str, str, str, str]]:
    if ev.domain not in ACTION_DOMAINS:
        return None
    if ev.to_state in {"", "unknown", "unavailable", "none"}:
        return None

    # Special handling for climate numeric target/state.
    if ev.domain == "climate":
        curr_num = _try_float(ev.to_state)
        if curr_num is not None:
            rounded = round(curr_num * 2) / 2.0
            return (ev.entity_id, "set_temperature", "to", f"{rounded:.1f}")

    return (ev.entity_id, "state", "to", ev.to_state)


def _signature_to_text(sig: Tuple[str, str, str, str]) -> Dict[str, str]:
    entity_id, kind, op, value = sig
    if kind == "numeric_trend":
        cond = f"{op} and {value}"
    elif kind == "numeric_state":
        cond = value
    else:
        cond = f"{op} {value}"
    return {"entity_id": entity_id, "kind": kind, "condition": cond, "value": value}


def build_sequence_suggestions(
    states: List[Dict[str, Any]],
    window_minutes: int = 30,
    min_support_days: int = 3,
    min_confidence: float = 0.35,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    transitions = _to_transitions(states)
    if not transitions:
        return []

    window = timedelta(minutes=window_minutes)

    # How often antecedent appears in days (for confidence denominator).
    trigger_days: Dict[Tuple[str, str, str, str], set] = {}
    for ev in transitions:
        trig = _trigger_signature(ev)
        if trig is None:
            continue
        trigger_days.setdefault(trig, set()).add(ev.timestamp.date().isoformat())

    # Pair mining: nearest previous trigger -> current action.
    pair_events: Dict[Tuple[Tuple[str, str, str, str], Tuple[str, str, str, str]], List[Transition]] = {}
    for idx, action_ev in enumerate(transitions):
        action_sig = _action_signature(action_ev)
        if action_sig is None:
            continue

        j = idx - 1
        chosen_trigger: Optional[Tuple[str, str, str, str]] = None
        while j >= 0:
            prev_ev = transitions[j]
            if action_ev.timestamp - prev_ev.timestamp > window:
                break
            trig_sig = _trigger_signature(prev_ev)
            if trig_sig is not None and prev_ev.entity_id != action_ev.entity_id:
                chosen_trigger = trig_sig
                break
            j -= 1

        if chosen_trigger is None:
            continue

        key = (chosen_trigger, action_sig)
        pair_events.setdefault(key, []).append(action_ev)

    suggestions: List[Dict[str, Any]] = []
    for (trigger_sig, action_sig), evs in pair_events.items():
        matched_days = {ev.timestamp.date().isoformat() for ev in evs}
        support_days = len(matched_days)
        if support_days < min_support_days:
            continue

        antecedent_days = len(trigger_days.get(trigger_sig, set()))
        if antecedent_days <= 0:
            continue
        confidence = support_days / antecedent_days
        if confidence < min_confidence:
            continue

        trigger_info = _signature_to_text(trigger_sig)
        action_info = _signature_to_text(action_sig)

        action_entity = action_info["entity_id"]
        action_domain = action_entity.split(".", 1)[0]
        if action_domain == "climate" and action_info["kind"] == "set_temperature":
            service = "climate.set_temperature"
            action_block = (
                "  - service: climate.set_temperature\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
                "    data:\n"
                f"      temperature: {action_info['value']}\n"
            )
        elif action_domain == "light" and action_info["value"] == "on":
            service = "light.turn_on"
            action_block = (
                f"  - service: {service}\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
            )
        elif action_domain == "light" and action_info["value"] == "off":
            service = "light.turn_off"
            action_block = (
                f"  - service: {service}\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
            )
        elif action_domain == "switch" and action_info["value"] == "on":
            service = "switch.turn_on"
            action_block = (
                f"  - service: {service}\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
            )
        elif action_domain == "switch" and action_info["value"] == "off":
            service = "switch.turn_off"
            action_block = (
                f"  - service: {service}\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
            )
        else:
            service = f"homeassistant.turn_on ({action_info['value']})"
            action_block = (
                "  # Manual mapping may be required for this domain/state\n"
                f"  - service: homeassistant.turn_on\n"
                "    target:\n"
                f"      entity_id: {action_entity}\n"
            )

        title = (
            f"When {trigger_info['entity_id']} ({trigger_info['condition']}), "
            f"then {action_entity} -> {action_info['value']}"
        )

        automation_yaml = (
            f'alias: "{title}"\n'
            "trigger:\n"
            "  - platform: state\n"
            f"    entity_id: {trigger_info['entity_id']}\n"
            "condition:\n"
            "  # Refine this condition for production use\n"
            "  - condition: template\n"
            f"    value_template: \"{{{{ states('{trigger_info['entity_id']}') != 'unknown' }}}}\"\n"
            "action:\n"
            f"{action_block}"
            "mode: single\n"
        )

        suggestions.append(
            {
                "type": "sequence_rule",
                "title": title,
                "trigger": trigger_info,
                "action": action_info,
                "support_days": support_days,
                "antecedent_days": antecedent_days,
                "confidence": round(confidence, 4),
                "window_minutes": window_minutes,
                "estimated_service": service,
                "automation_yaml": automation_yaml,
            }
        )

    suggestions.sort(key=lambda x: (x["confidence"], x["support_days"]), reverse=True)
    return suggestions[: max(1, limit)]


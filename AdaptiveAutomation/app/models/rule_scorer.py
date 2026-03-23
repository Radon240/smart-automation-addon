from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Tuple


NOISE_ENTITY_PREFIXES = (
    "sensor.time",
    "sensor.date",
    "sensor.uptime",
)


def _stable_id(payload: str) -> str:
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _domain(entity_id: str) -> str:
    if "." not in entity_id:
        return "unknown"
    return entity_id.split(".", 1)[0]


def _is_noisy_entity(entity_id: str) -> bool:
    eid = (entity_id or "").strip().lower()
    if any(eid.startswith(prefix) for prefix in NOISE_ENTITY_PREFIXES):
        return True
    return False


def normalize_state_rules(predictions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for p in predictions:
        entity_id = str(p.get("entity_id") or "")
        state = str(p.get("state") or "")
        confidence = float(p.get("confidence") or 0.0)
        support = int(p.get("support") or 0)
        source = str(p.get("source") or "state_model")
        title = f"Set {entity_id} to {state}"
        rule_id = _stable_id(f"state|{entity_id}|{state}|{source}")
        rules.append(
            {
                "id": rule_id,
                "type": "state",
                "title": title,
                "entity_id": entity_id,
                "domain": _domain(entity_id),
                "confidence": confidence,
                "support_days": support,
                "explanation": f"State model source: {source}",
                "automation_yaml": "",
                "source": source,
            }
        )
    return rules


def normalize_routine_rules(suggestions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for s in suggestions:
        arrival = str(s.get("arrival_entity") or "")
        door = str(s.get("door_entity") or "")
        light = str(s.get("light_entity") or "")
        confidence = float(s.get("confidence") or 0.0)
        support = int(s.get("support_days") or 0)
        title = str(s.get("title") or f"Routine {arrival} -> {door} -> {light}")
        rule_id = _stable_id(f"routine|{arrival}|{door}|{light}")
        rules.append(
            {
                "id": rule_id,
                "type": "routine",
                "title": title,
                "entity_id": light or door or arrival,
                "domain": _domain(light or door or arrival),
                "confidence": confidence,
                "support_days": support,
                "explanation": (
                    f"Arrival routine: {arrival} -> {door} -> {light}, "
                    f"typical at {s.get('typical_arrival_time', 'N/A')}"
                ),
                "automation_yaml": str(s.get("automation_yaml") or ""),
                "source": "routine_detector",
            }
        )
    return rules


def normalize_sequence_rules(suggestions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    for s in suggestions:
        trigger = s.get("trigger") if isinstance(s.get("trigger"), dict) else {}
        action = s.get("action") if isinstance(s.get("action"), dict) else {}
        trigger_entity = str(trigger.get("entity_id") or "")
        action_entity = str(action.get("entity_id") or "")
        action_value = str(action.get("value") or "")
        confidence = float(s.get("confidence") or 0.0)
        support = int(s.get("support_days") or 0)
        title = str(s.get("title") or f"{trigger_entity} -> {action_entity}:{action_value}")
        rule_id = _stable_id(f"sequence|{trigger_entity}|{action_entity}|{action_value}")
        rules.append(
            {
                "id": rule_id,
                "type": "sequence",
                "title": title,
                "entity_id": action_entity or trigger_entity,
                "domain": _domain(action_entity or trigger_entity),
                "confidence": confidence,
                "support_days": support,
                "explanation": (
                    f"Trigger {trigger_entity} ({trigger.get('condition', 'N/A')}) "
                    f"-> action {action_entity} ({action_value})"
                ),
                "automation_yaml": str(s.get("automation_yaml") or ""),
                "source": "sequence_miner",
            }
        )
    return rules


def _score_rule(rule: Dict[str, Any]) -> float:
    conf = float(rule.get("confidence") or 0.0)
    support = max(0, int(rule.get("support_days") or 0))
    support_norm = min(1.0, support / 14.0)
    base = 0.7 * conf + 0.3 * support_norm

    if rule.get("type") == "routine":
        base += 0.05
    if rule.get("type") == "sequence":
        base += 0.03

    if _is_noisy_entity(str(rule.get("entity_id") or "")):
        base -= 0.15

    return round(max(0.0, min(1.0, base)), 4)


def deduplicate_rules(rules: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rules:
        key = (str(r.get("type") or ""), str(r.get("id") or ""))
        curr = best.get(key)
        if curr is None or float(r.get("score", 0.0)) > float(curr.get("score", 0.0)):
            best[key] = r
    return list(best.values())


def rank_rules(rules: Iterable[Dict[str, Any]], limit: int = 50) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for rule in rules:
        r = dict(rule)
        r["score"] = _score_rule(r)
        scored.append(r)

    dedup = deduplicate_rules(scored)
    dedup.sort(
        key=lambda x: (float(x.get("score", 0.0)), float(x.get("confidence", 0.0)), int(x.get("support_days", 0))),
        reverse=True,
    )
    return dedup[: max(1, limit)]

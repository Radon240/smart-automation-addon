from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


HOME_STATES = {"home", "дом"}
DOOR_OPEN_STATES = {"on", "open", "unlocked"}
LIGHT_ON_STATES = {"on"}


@dataclass
class Event:
    entity_id: str
    domain: str
    state: str
    timestamp: datetime


@dataclass
class ArrivalChain:
    arrival_entity: str
    door_entity: str
    light_entity: str
    arrival_at: datetime
    door_at: datetime
    light_at: datetime


def _state_str(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_ts(raw: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_events(states: Iterable[Dict[str, Any]]) -> List[Event]:
    result: List[Event] = []
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        ts = _parse_ts(item.get("last_changed") or item.get("last_updated"))
        if ts is None:
            continue
        state = _state_str(item.get("state"))
        result.append(Event(entity_id=entity_id, domain=domain, state=state, timestamp=ts))
    result.sort(key=lambda x: x.timestamp)
    return result


def _is_arrival(event: Event) -> bool:
    return event.domain == "device_tracker" and event.state in HOME_STATES


def _is_door_open(event: Event) -> bool:
    if event.domain not in {"binary_sensor", "lock", "sensor"}:
        return False
    if "door" not in event.entity_id and "entry" not in event.entity_id and "front" not in event.entity_id:
        return False
    return event.state in DOOR_OPEN_STATES


def _is_light_on(event: Event) -> bool:
    return event.domain == "light" and event.state in LIGHT_ON_STATES


def _find_first(events: List[Event], start_idx: int, start_ts: datetime, end_ts: datetime, predicate) -> Tuple[Optional[Event], int]:
    idx = start_idx
    while idx < len(events):
        ev = events[idx]
        if ev.timestamp > end_ts:
            return None, idx
        if ev.timestamp >= start_ts and predicate(ev):
            return ev, idx
        idx += 1
    return None, idx


def find_arrival_chains(
    states: List[Dict[str, Any]],
    arrival_to_door_minutes: int = 20,
    door_to_light_minutes: int = 20,
) -> List[ArrivalChain]:
    events = _to_events(states)
    chains: List[ArrivalChain] = []

    for i, ev in enumerate(events):
        if not _is_arrival(ev):
            continue

        door_start = ev.timestamp
        door_end = ev.timestamp + timedelta(minutes=arrival_to_door_minutes)
        door_ev, door_idx = _find_first(events, i, door_start, door_end, _is_door_open)
        if door_ev is None:
            continue

        light_start = door_ev.timestamp
        light_end = door_ev.timestamp + timedelta(minutes=door_to_light_minutes)
        light_ev, _ = _find_first(events, door_idx, light_start, light_end, _is_light_on)
        if light_ev is None:
            continue

        chains.append(
            ArrivalChain(
                arrival_entity=ev.entity_id,
                door_entity=door_ev.entity_id,
                light_entity=light_ev.entity_id,
                arrival_at=ev.timestamp,
                door_at=door_ev.timestamp,
                light_at=light_ev.timestamp,
            )
        )

    return chains


def build_routine_suggestions(
    states: List[Dict[str, Any]],
    min_support_days: int = 3,
    min_confidence: float = 0.4,
    arrival_to_door_minutes: int = 20,
    door_to_light_minutes: int = 20,
) -> List[Dict[str, Any]]:
    chains = find_arrival_chains(
        states=states,
        arrival_to_door_minutes=arrival_to_door_minutes,
        door_to_light_minutes=door_to_light_minutes,
    )

    if not chains:
        return []

    arrival_days_by_tracker: Dict[str, set] = {}
    for chain in chains:
        day_key = chain.arrival_at.date().isoformat()
        arrival_days_by_tracker.setdefault(chain.arrival_entity, set()).add(day_key)

    grouped: Dict[Tuple[str, str, str], List[ArrivalChain]] = {}
    for chain in chains:
        key = (chain.arrival_entity, chain.door_entity, chain.light_entity)
        grouped.setdefault(key, []).append(chain)

    suggestions: List[Dict[str, Any]] = []
    for key, items in grouped.items():
        arrival_entity, door_entity, light_entity = key

        matched_days = {x.arrival_at.date().isoformat() for x in items}
        support = len(matched_days)
        total_arrival_days = len(arrival_days_by_tracker.get(arrival_entity, set()))
        if total_arrival_days <= 0:
            continue
        confidence = support / total_arrival_days

        if support < min_support_days or confidence < min_confidence:
            continue

        minutes = [x.arrival_at.hour * 60 + x.arrival_at.minute for x in items]
        avg_minutes = int(sum(minutes) / len(minutes))
        hh = avg_minutes // 60
        mm = avg_minutes % 60

        alias = f"Auto light when arriving home: {light_entity}"
        automation_yaml = (
            f'alias: "{alias}"\n'
            "trigger:\n"
            "  - platform: state\n"
            f"    entity_id: {arrival_entity}\n"
            "    to: home\n"
            "condition:\n"
            "  - condition: state\n"
            f"    entity_id: {door_entity}\n"
            "    state: 'on'\n"
            "action:\n"
            "  - service: light.turn_on\n"
            "    target:\n"
            f"      entity_id: {light_entity}\n"
            "mode: single\n"
        )

        suggestions.append(
            {
                "title": alias,
                "arrival_entity": arrival_entity,
                "door_entity": door_entity,
                "light_entity": light_entity,
                "typical_arrival_time": f"{hh:02d}:{mm:02d}",
                "support_days": support,
                "arrival_days": total_arrival_days,
                "confidence": round(confidence, 4),
                "automation_yaml": automation_yaml,
                "type": "arrival_door_light_routine",
            }
        )

    suggestions.sort(key=lambda x: (x["confidence"], x["support_days"]), reverse=True)
    return suggestions


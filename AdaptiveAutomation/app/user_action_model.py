from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class ActionEvent:
    entity_id: str
    from_state: str
    to_state: str
    timestamp: datetime


class UserActionModel:
    """
    Learns user behavior from Home Assistant state transitions and predicts
    likely actions for a given weekday/hour slot.
    """

    def __init__(self, min_support: int = 5, min_confidence: float = 0.6) -> None:
        self.min_support = min_support
        self.min_confidence = min_confidence

        self._slot_total_actions: Dict[Tuple[int, int], int] = {}
        self._slot_entity_total_count: Dict[Tuple[int, int], Dict[str, int]] = {}
        self._slot_entity_state_count: Dict[Tuple[int, int], Dict[str, Dict[str, int]]] = {}
        # Day-based pattern stats (less sensitive to noisy event counts)
        self._slot_entity_day_count: Dict[Tuple[int, int], Dict[str, int]] = {}
        self._slot_entity_state_day_count: Dict[Tuple[int, int], Dict[str, Dict[str, int]]] = {}

        self._global_total_actions = 0
        self._global_entity_total_count: Dict[str, int] = {}
        self._global_entity_state_count: Dict[str, Dict[str, int]] = {}
        self._global_entity_day_count: Dict[str, int] = {}
        self._global_entity_state_day_count: Dict[str, Dict[str, int]] = {}

        self._trained_actions = 0
        self._lock = RLock()

    @staticmethod
    def _slot(ts: datetime) -> Tuple[int, int]:
        return ts.weekday(), ts.hour

    @staticmethod
    def _is_relevant_state(state: str) -> bool:
        value = (state or "").strip().lower()
        if not value:
            return False
        if value in {"unknown", "unavailable", "none"}:
            return False
        return True

    def fit(self, events: Iterable[ActionEvent]) -> None:
        with self._lock:
            self._slot_total_actions = {}
            self._slot_entity_total_count = {}
            self._slot_entity_state_count = {}
            self._slot_entity_day_count = {}
            self._slot_entity_state_day_count = {}
            self._global_total_actions = 0
            self._global_entity_total_count = {}
            self._global_entity_state_count = {}
            self._global_entity_day_count = {}
            self._global_entity_state_day_count = {}
            self._trained_actions = 0

            slot_entity_days_seen: Dict[Tuple[int, int], Dict[str, set]] = {}
            slot_entity_state_days_seen: Dict[Tuple[int, int], Dict[str, Dict[str, set]]] = {}
            global_entity_days_seen: Dict[str, set] = {}
            global_entity_state_days_seen: Dict[str, Dict[str, set]] = {}

            for ev in events:
                to_state = (ev.to_state or "").strip().lower()
                if not self._is_relevant_state(to_state):
                    continue

                slot = self._slot(ev.timestamp)
                day_key = ev.timestamp.date().isoformat()
                if slot not in self._slot_total_actions:
                    self._slot_total_actions[slot] = 0
                self._slot_total_actions[slot] += 1

                if slot not in self._slot_entity_total_count:
                    self._slot_entity_total_count[slot] = {}
                if ev.entity_id not in self._slot_entity_total_count[slot]:
                    self._slot_entity_total_count[slot][ev.entity_id] = 0
                self._slot_entity_total_count[slot][ev.entity_id] += 1

                if slot not in self._slot_entity_state_count:
                    self._slot_entity_state_count[slot] = {}
                if ev.entity_id not in self._slot_entity_state_count[slot]:
                    self._slot_entity_state_count[slot][ev.entity_id] = {}
                if to_state not in self._slot_entity_state_count[slot][ev.entity_id]:
                    self._slot_entity_state_count[slot][ev.entity_id][to_state] = 0
                self._slot_entity_state_count[slot][ev.entity_id][to_state] += 1

                if slot not in slot_entity_days_seen:
                    slot_entity_days_seen[slot] = {}
                if ev.entity_id not in slot_entity_days_seen[slot]:
                    slot_entity_days_seen[slot][ev.entity_id] = set()
                slot_entity_days_seen[slot][ev.entity_id].add(day_key)

                if slot not in slot_entity_state_days_seen:
                    slot_entity_state_days_seen[slot] = {}
                if ev.entity_id not in slot_entity_state_days_seen[slot]:
                    slot_entity_state_days_seen[slot][ev.entity_id] = {}
                if to_state not in slot_entity_state_days_seen[slot][ev.entity_id]:
                    slot_entity_state_days_seen[slot][ev.entity_id][to_state] = set()
                slot_entity_state_days_seen[slot][ev.entity_id][to_state].add(day_key)

                if ev.entity_id not in self._global_entity_total_count:
                    self._global_entity_total_count[ev.entity_id] = 0
                self._global_entity_total_count[ev.entity_id] += 1

                if ev.entity_id not in self._global_entity_state_count:
                    self._global_entity_state_count[ev.entity_id] = {}
                if to_state not in self._global_entity_state_count[ev.entity_id]:
                    self._global_entity_state_count[ev.entity_id][to_state] = 0
                self._global_entity_state_count[ev.entity_id][to_state] += 1

                if ev.entity_id not in global_entity_days_seen:
                    global_entity_days_seen[ev.entity_id] = set()
                global_entity_days_seen[ev.entity_id].add(day_key)

                if ev.entity_id not in global_entity_state_days_seen:
                    global_entity_state_days_seen[ev.entity_id] = {}
                if to_state not in global_entity_state_days_seen[ev.entity_id]:
                    global_entity_state_days_seen[ev.entity_id][to_state] = set()
                global_entity_state_days_seen[ev.entity_id][to_state].add(day_key)

                self._global_total_actions += 1
                self._trained_actions += 1

            self._slot_entity_day_count = {
                slot: {entity_id: len(days) for entity_id, days in entity_days.items()}
                for slot, entity_days in slot_entity_days_seen.items()
            }
            self._slot_entity_state_day_count = {
                slot: {
                    entity_id: {state: len(days) for state, days in state_days.items()}
                    for entity_id, state_days in entity_states.items()
                }
                for slot, entity_states in slot_entity_state_days_seen.items()
            }
            self._global_entity_day_count = {
                entity_id: len(days) for entity_id, days in global_entity_days_seen.items()
            }
            self._global_entity_state_day_count = {
                entity_id: {state: len(days) for state, days in state_days.items()}
                for entity_id, state_days in global_entity_state_days_seen.items()
            }

    def predict(
        self,
        when: datetime,
        limit: int = 10,
        min_support: Optional[int] = None,
        min_confidence: Optional[float] = None,
        allow_relaxed_fallback: bool = True,
        one_per_entity: bool = True,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            support_threshold = self.min_support if min_support is None else min_support
            confidence_threshold = self.min_confidence if min_confidence is None else min_confidence

            slot = self._slot(when)
            predictions: List[Dict[str, Any]] = []

            def collect_from_slot(curr_support: int, curr_conf: float, source: str) -> List[Dict[str, Any]]:
                collected: List[Dict[str, Any]] = []
                if slot not in self._slot_entity_state_day_count:
                    return collected

                slot_days_by_entity = self._slot_entity_day_count.get(slot, {})
                for entity_id, states in self._slot_entity_state_day_count[slot].items():
                    entity_total = slot_days_by_entity.get(entity_id, 0)
                    if entity_total <= 0:
                        continue
                    for state, count in states.items():
                        confidence = count / entity_total
                        if count >= curr_support and confidence >= curr_conf:
                            collected.append(
                                {
                                    "entity_id": entity_id,
                                    "state": state,
                                    "support": count,
                                    "confidence": round(confidence, 4),
                                    "source": source,
                                }
                            )
                return collected

            def collect_global(curr_support: int, curr_conf: float, source: str) -> List[Dict[str, Any]]:
                collected: List[Dict[str, Any]] = []
                for entity_id, states in self._global_entity_state_day_count.items():
                    entity_total = self._global_entity_day_count.get(entity_id, 0)
                    if entity_total <= 0:
                        continue
                    for state, count in states.items():
                        confidence = count / entity_total
                        if count >= curr_support and confidence >= curr_conf:
                            collected.append(
                                {
                                    "entity_id": entity_id,
                                    "state": state,
                                    "support": count,
                                    "confidence": round(confidence, 4),
                                    "source": source,
                                }
                            )
                return collected

            # 1) strict slot predictions
            predictions = collect_from_slot(support_threshold, confidence_threshold, "time_slot")
            # 2) relax support if strict is empty
            if not predictions and allow_relaxed_fallback:
                predictions = collect_from_slot(1, confidence_threshold, "time_slot_relaxed_support")
            # 3) fallback to global with strict thresholds
            if not predictions:
                predictions = collect_global(support_threshold, confidence_threshold, "global_fallback")
            # 4) final fallback: global with relaxed support
            if not predictions and allow_relaxed_fallback:
                predictions = collect_global(1, confidence_threshold, "global_fallback_relaxed_support")

            predictions.sort(key=lambda x: (x["confidence"], x["support"]), reverse=True)
            if one_per_entity:
                best_by_entity: Dict[str, Dict[str, Any]] = {}
                for item in predictions:
                    entity_id = item["entity_id"]
                    current = best_by_entity.get(entity_id)
                    if current is None:
                        best_by_entity[entity_id] = item
                        continue

                    item_score = (float(item["confidence"]), int(item["support"]))
                    curr_score = (float(current["confidence"]), int(current["support"]))
                    if item_score > curr_score:
                        best_by_entity[entity_id] = item

                predictions = sorted(
                    best_by_entity.values(),
                    key=lambda x: (x["confidence"], x["support"]),
                    reverse=True,
                )

            return predictions[: max(1, limit)]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "trained_actions": self._trained_actions,
                "slot_count": len(self._slot_total_actions),
                "entity_count": len(self._global_entity_state_count),
                "global_total_actions": self._global_total_actions,
                "min_support": self.min_support,
                "min_confidence": self.min_confidence,
            }

    def set_thresholds(self, min_support: int, min_confidence: float) -> None:
        with self._lock:
            self.min_support = max(1, int(min_support))
            self.min_confidence = max(0.0, min(1.0, float(min_confidence)))

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "min_support": self.min_support,
                "min_confidence": self.min_confidence,
                "slot_total_actions": {
                    f"{k[0]}:{k[1]}": v for k, v in self._slot_total_actions.items()
                },
                "slot_entity_total_count": {
                    f"{k[0]}:{k[1]}": entity_totals
                    for k, entity_totals in self._slot_entity_total_count.items()
                },
                "slot_entity_state_count": {
                    f"{k[0]}:{k[1]}": entity_map
                    for k, entity_map in self._slot_entity_state_count.items()
                },
                "slot_entity_day_count": {
                    f"{k[0]}:{k[1]}": entity_days
                    for k, entity_days in self._slot_entity_day_count.items()
                },
                "slot_entity_state_day_count": {
                    f"{k[0]}:{k[1]}": entity_map
                    for k, entity_map in self._slot_entity_state_day_count.items()
                },
                "global_total_actions": self._global_total_actions,
                "global_entity_total_count": self._global_entity_total_count,
                "global_entity_state_count": self._global_entity_state_count,
                "global_entity_day_count": self._global_entity_day_count,
                "global_entity_state_day_count": self._global_entity_state_day_count,
                "trained_actions": self._trained_actions,
            }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "UserActionModel":
        model = cls(
            min_support=int(payload.get("min_support", 5)),
            min_confidence=float(payload.get("min_confidence", 0.6)),
        )

        slot_totals_raw = payload.get("slot_total_actions", {}) or {}
        slot_entity_totals_raw = payload.get("slot_entity_total_count", {}) or {}
        slot_entity_raw = payload.get("slot_entity_state_count", {}) or {}
        slot_entity_day_raw = payload.get("slot_entity_day_count", {}) or {}
        slot_entity_state_day_raw = payload.get("slot_entity_state_day_count", {}) or {}

        def parse_slot(slot_key: str) -> Tuple[int, int]:
            w, h = slot_key.split(":", 1)
            return int(w), int(h)

        model._slot_total_actions = {
            parse_slot(k): int(v) for k, v in slot_totals_raw.items()
        }
        model._slot_entity_total_count = {
            parse_slot(k): {entity_id: int(cnt) for entity_id, cnt in entity_totals.items()}
            for k, entity_totals in slot_entity_totals_raw.items()
        }
        model._slot_entity_state_count = {
            parse_slot(k): v for k, v in slot_entity_raw.items()
        }
        model._slot_entity_day_count = {
            parse_slot(k): {entity_id: int(cnt) for entity_id, cnt in entity_days.items()}
            for k, entity_days in slot_entity_day_raw.items()
        }
        model._slot_entity_state_day_count = {
            parse_slot(k): {
                entity_id: {state: int(cnt) for state, cnt in states.items()}
                for entity_id, states in entity_map.items()
            }
            for k, entity_map in slot_entity_state_day_raw.items()
        }
        model._global_total_actions = int(payload.get("global_total_actions", 0))
        model._global_entity_total_count = {
            entity_id: int(cnt)
            for entity_id, cnt in (payload.get("global_entity_total_count", {}) or {}).items()
        }
        model._global_entity_state_count = payload.get("global_entity_state_count", {}) or {}
        model._global_entity_day_count = {
            entity_id: int(cnt)
            for entity_id, cnt in (payload.get("global_entity_day_count", {}) or {}).items()
        }
        model._global_entity_state_day_count = {
            entity_id: {state: int(cnt) for state, cnt in states.items()}
            for entity_id, states in (payload.get("global_entity_state_day_count", {}) or {}).items()
        }
        model._trained_actions = int(payload.get("trained_actions", 0))

        # Backward compatibility for models saved before entity totals existed.
        if not model._slot_entity_total_count and model._slot_entity_state_count:
            rebuilt_slot_totals: Dict[Tuple[int, int], Dict[str, int]] = {}
            for slot, entity_map in model._slot_entity_state_count.items():
                rebuilt_slot_totals[slot] = {
                    entity_id: int(sum(states.values()))
                    for entity_id, states in entity_map.items()
                }
            model._slot_entity_total_count = rebuilt_slot_totals

        if not model._global_entity_total_count and model._global_entity_state_count:
            model._global_entity_total_count = {
                entity_id: int(sum(states.values()))
                for entity_id, states in model._global_entity_state_count.items()
            }

        # Build day-based structures for old models that only have event counts.
        if not model._slot_entity_day_count and model._slot_entity_total_count:
            model._slot_entity_day_count = {
                slot: entity_totals.copy()
                for slot, entity_totals in model._slot_entity_total_count.items()
            }
        if not model._slot_entity_state_day_count and model._slot_entity_state_count:
            model._slot_entity_state_day_count = {
                slot: {
                    entity_id: states.copy()
                    for entity_id, states in entity_map.items()
                }
                for slot, entity_map in model._slot_entity_state_count.items()
            }
        if not model._global_entity_day_count and model._global_entity_total_count:
            model._global_entity_day_count = model._global_entity_total_count.copy()
        if not model._global_entity_state_day_count and model._global_entity_state_count:
            model._global_entity_state_day_count = {
                entity_id: states.copy()
                for entity_id, states in model._global_entity_state_count.items()
            }
        return model


class ModelStore:
    def __init__(self, path: str = "/data/model.json") -> None:
        self.path = Path(path)

    def save(self, model: UserActionModel) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(model.to_dict(), ensure_ascii=False), encoding="utf-8")

    def load(self) -> Optional[UserActionModel]:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return UserActionModel.from_dict(payload)
        except Exception:
            return None


def action_events_from_states(ha_states: Iterable[Dict[str, Any]]) -> List[ActionEvent]:
    """
    Converts Home Assistant state snapshots into transition events.

    Expected input: flat list of HA state dictionaries from history endpoint.
    """
    by_entity: Dict[str, List[Dict[str, Any]]] = {}

    for raw in ha_states:
        entity_id = str(raw.get("entity_id") or "").strip()
        if not entity_id or "." not in entity_id:
            continue

        ts_raw = raw.get("last_changed") or raw.get("last_updated") or ""
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except Exception:
            continue

        state = str(raw.get("state") or "").strip()
        if entity_id not in by_entity:
            by_entity[entity_id] = []

        by_entity[entity_id].append({
            "entity_id": entity_id,
            "state": state,
            "timestamp": ts,
        })

    result: List[ActionEvent] = []

    for entity_id, items in by_entity.items():
        items.sort(key=lambda x: x["timestamp"])
        for idx in range(1, len(items)):
            prev_state = str(items[idx - 1].get("state") or "")
            curr_state = str(items[idx].get("state") or "")
            if prev_state == curr_state:
                continue
            result.append(
                ActionEvent(
                    entity_id=entity_id,
                    from_state=prev_state,
                    to_state=curr_state,
                    timestamp=items[idx]["timestamp"],
                )
            )

    return result

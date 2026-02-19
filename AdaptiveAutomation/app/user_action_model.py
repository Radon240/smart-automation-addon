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
        self._slot_entity_state_count: Dict[Tuple[int, int], Dict[str, Dict[str, int]]] = {}

        self._global_total_actions = 0
        self._global_entity_state_count: Dict[str, Dict[str, int]] = {}

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
            self._slot_entity_state_count = {}
            self._global_total_actions = 0
            self._global_entity_state_count = {}
            self._trained_actions = 0

            for ev in events:
                to_state = (ev.to_state or "").strip().lower()
                if not self._is_relevant_state(to_state):
                    continue

                slot = self._slot(ev.timestamp)
                if slot not in self._slot_total_actions:
                    self._slot_total_actions[slot] = 0
                self._slot_total_actions[slot] += 1

                if slot not in self._slot_entity_state_count:
                    self._slot_entity_state_count[slot] = {}
                if ev.entity_id not in self._slot_entity_state_count[slot]:
                    self._slot_entity_state_count[slot][ev.entity_id] = {}
                if to_state not in self._slot_entity_state_count[slot][ev.entity_id]:
                    self._slot_entity_state_count[slot][ev.entity_id][to_state] = 0
                self._slot_entity_state_count[slot][ev.entity_id][to_state] += 1

                if ev.entity_id not in self._global_entity_state_count:
                    self._global_entity_state_count[ev.entity_id] = {}
                if to_state not in self._global_entity_state_count[ev.entity_id]:
                    self._global_entity_state_count[ev.entity_id][to_state] = 0
                self._global_entity_state_count[ev.entity_id][to_state] += 1

                self._global_total_actions += 1
                self._trained_actions += 1

    def predict(
        self,
        when: datetime,
        limit: int = 10,
        min_support: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            support_threshold = self.min_support if min_support is None else min_support
            confidence_threshold = self.min_confidence if min_confidence is None else min_confidence

            slot = self._slot(when)
            slot_total = self._slot_total_actions.get(slot, 0)

            predictions: List[Dict[str, Any]] = []

            if slot_total > 0 and slot in self._slot_entity_state_count:
                for entity_id, states in self._slot_entity_state_count[slot].items():
                    for state, count in states.items():
                        confidence = count / slot_total
                        if count >= support_threshold and confidence >= confidence_threshold:
                            predictions.append(
                                {
                                    "entity_id": entity_id,
                                    "state": state,
                                    "support": count,
                                    "confidence": round(confidence, 4),
                                    "source": "time_slot",
                                }
                            )

            if not predictions and self._global_total_actions > 0:
                for entity_id, states in self._global_entity_state_count.items():
                    for state, count in states.items():
                        confidence = count / self._global_total_actions
                        if count >= support_threshold and confidence >= confidence_threshold:
                            predictions.append(
                                {
                                    "entity_id": entity_id,
                                    "state": state,
                                    "support": count,
                                    "confidence": round(confidence, 4),
                                    "source": "global_fallback",
                                }
                            )

            predictions.sort(key=lambda x: (x["confidence"], x["support"]), reverse=True)
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
                "slot_entity_state_count": {
                    f"{k[0]}:{k[1]}": entity_map
                    for k, entity_map in self._slot_entity_state_count.items()
                },
                "global_total_actions": self._global_total_actions,
                "global_entity_state_count": self._global_entity_state_count,
                "trained_actions": self._trained_actions,
            }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "UserActionModel":
        model = cls(
            min_support=int(payload.get("min_support", 5)),
            min_confidence=float(payload.get("min_confidence", 0.6)),
        )

        slot_totals_raw = payload.get("slot_total_actions", {}) or {}
        slot_entity_raw = payload.get("slot_entity_state_count", {}) or {}

        def parse_slot(slot_key: str) -> Tuple[int, int]:
            w, h = slot_key.split(":", 1)
            return int(w), int(h)

        model._slot_total_actions = {
            parse_slot(k): int(v) for k, v in slot_totals_raw.items()
        }
        model._slot_entity_state_count = {
            parse_slot(k): v for k, v in slot_entity_raw.items()
        }
        model._global_total_actions = int(payload.get("global_total_actions", 0))
        model._global_entity_state_count = payload.get("global_entity_state_count", {}) or {}
        model._trained_actions = int(payload.get("trained_actions", 0))
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

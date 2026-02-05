from __future__ import annotations

"""
Simple habit-based action prediction model for Home Assistant history.

The goal of this module is to provide a small, dependency-free Python "ML core"
that can be called from the .NET addon. It analyses past state change events
and learns, for each controllable entity, how often it is turned on in a given
time window (weekday + hour). Based on this, it can suggest likely actions
for the current moment.

This is intentionally lightweight and interpretable so it can be described
in the diploma text as:
  - time-series aggregation of events,
  - estimation of conditional probability P(action | weekday, hour),
  - thresholding by support and confidence to suggest automations.
"""

from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple, Any, Optional


@dataclass
class Event:
    """Minimal representation of a Home Assistant state change used by the model."""

    entity_id: str
    state: str
    timestamp: datetime


@dataclass
class PredictedAction:
    """Result of the model: one potential action with probability estimate."""

    entity_id: str
    state: str
    probability: float
    support: int


class TimeSlotHabitModel:
    """
    Very simple habit model based on time slots (weekday + hour).

    For each (weekday, hour) pair the model counts how often each entity
    was observed in the specified "active" state (by default: 'on').
    At prediction time for the current (weekday, hour) it returns entities
    whose empirical probability exceeds `min_confidence` and have at least
    `min_support` observations in this slot.
    """

    def __init__(
        self,
        active_state: Optional[str] = None,
        min_support: int = 5,
        min_confidence: float = 0.6,
    ) -> None:
        # If active_state is None the model will consider ALL event labels
        # (transitions, numeric/attribute changes, etc.). Keeping the
        # parameter for backward compatibility.
        self.active_state = active_state
        self.min_support = min_support
        self.min_confidence = min_confidence

        # (weekday, hour) -> entity_id -> label -> count
        self._slot_entity_label_counts: Dict[Tuple[int, int], Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )
        # (weekday, hour) -> total events considered
        self._slot_totals: Dict[Tuple[int, int], int] = defaultdict(int)

    def fit(self, events: Iterable[Event]) -> None:
        """
        Train the model on a sequence of events.

        Only events where `state == active_state` are considered as positive
        actions (e.g. light turned on).
        """
        for ev in events:
            # If an explicit active_state is configured, only that label
            # is considered "positive" as before. Otherwise accept all
            # event labels (transitions, numeric changes, attributes).
            if self.active_state is not None and ev.state != self.active_state:
                continue

            slot = (ev.timestamp.weekday(), ev.timestamp.hour)
            label = ev.state
            self._slot_entity_label_counts[slot][ev.entity_id][label] += 1
            self._slot_totals[slot] += 1

    def predict_for_datetime(self, when: datetime) -> List[PredictedAction]:
        """
        Return a list of probable actions for a given datetime.

        The list is sorted by descending probability and support.
        """
        slot = (when.weekday(), when.hour)
        total = self._slot_totals.get(slot, 0)
        if total == 0:
            return []

        result: List[PredictedAction] = []
        # For each entity and each observed label compute probability
        entity_map = self._slot_entity_label_counts.get(slot, {})
        for entity_id, labels in entity_map.items():
            for label, count in labels.items():
                prob = count / total
                if count >= self.min_support and prob >= self.min_confidence:
                    result.append(
                        PredictedAction(
                            entity_id=entity_id,
                            state=label,
                            probability=prob,
                            support=count,
                        )
                    )

        # Sort most confident and well-supported actions first
        result.sort(key=lambda x: (x.probability, x.support), reverse=True)
        return result


def events_from_ha_states(
    ha_states: Iterable[Dict[str, Any]],
    accepted_domains: Optional[Iterable[str]] = None,
) -> List[Event]:
    """
    Helper: convert raw Home Assistant /api/states entries to Event objects.

    Expects each item to look like one element from REST API /api/states:
      {
        "entity_id": "light.living_room",
        "state": "on",
        "last_changed": "2026-02-05T18:47:32.418320+00:00",
        "attributes": { ... }
      }

    By default this function will include all domains and attempt to
    generate higher-level event labels for the model:
      - transition:off->on (discrete state changes)
      - numeric:state:up / numeric:state:down (when the entity state is numeric)
      - attr:<name>:up / attr:<name>:down for numeric attribute changes

    This keeps the core model agnostic and allows it to learn both
    discrete and numeric patterns.
    """
    # Group raw states by entity and sort chronologically
    by_entity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in ha_states:
        entity_id = str(raw.get("entity_id") or "").strip()
        if not entity_id or "." not in entity_id:
            continue

        ts_raw = raw.get("last_changed") or raw.get("last_updated") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        entry = {
            "entity_id": entity_id,
            "state": str(raw.get("state") or "").strip(),
            "attributes": raw.get("attributes") or {},
            "ts": ts,
        }
        by_entity[entity_id].append(entry)

    result: List[Event] = []

    def _try_float(x: Any) -> Optional[float]:
        try:
            return float(x)
        except Exception:
            return None

    for entity_id, entries in by_entity.items():
        # sort by timestamp ascending
        entries.sort(key=lambda x: x["ts"])
        for i in range(1, len(entries)):
            prev = entries[i - 1]
            curr = entries[i]
            prev_state = prev["state"]
            curr_state = curr["state"]

            # Prefer numeric interpretation of the main state where possible
            prev_num = _try_float(prev_state)
            curr_num = _try_float(curr_state)
            if prev_num is not None and curr_num is not None:
                delta = curr_num - prev_num
                if abs(delta) > 1e-6:
                    direction = "up" if delta > 0 else "down"
                    label = f"numeric:state:{direction}:{round(delta,3)}"
                    result.append(Event(entity_id=entity_id, state=label, timestamp=curr["ts"]))
                # numeric state handled, skip textual transition
            else:
                # Non-numeric state transitions (e.g. off -> on)
                if prev_state != curr_state:
                    label = f"transition:{prev_state}->{curr_state}"
                    result.append(Event(entity_id=entity_id, state=label, timestamp=curr["ts"]))

            # Also check numeric attribute changes (common for thermostats, sensors)
            prev_attrs = prev.get("attributes") or {}
            curr_attrs = curr.get("attributes") or {}
            common_keys = set(prev_attrs.keys()) & set(curr_attrs.keys())
            for key in common_keys:
                pval = _try_float(prev_attrs.get(key))
                cval = _try_float(curr_attrs.get(key))
                if pval is None or cval is None:
                    continue
                delta = cval - pval
                if abs(delta) > 1e-6:
                    direction = "up" if delta > 0 else "down"
                    label = f"attr:{key}:{direction}:{round(delta,3)}"
                    result.append(Event(entity_id=entity_id, state=label, timestamp=curr["ts"]))

    return result


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
from typing import Dict, Iterable, List, Tuple, Any


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
        active_state: str = "on",
        min_support: int = 5,
        min_confidence: float = 0.6,
    ) -> None:
        self.active_state = active_state
        self.min_support = min_support
        self.min_confidence = min_confidence

        # (weekday, hour) -> entity_id -> count
        self._slot_entity_counts: Dict[Tuple[int, int], Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        # (weekday, hour) -> total "active" events
        self._slot_totals: Dict[Tuple[int, int], int] = defaultdict(int)

    def fit(self, events: Iterable[Event]) -> None:
        """
        Train the model on a sequence of events.

        Only events where `state == active_state` are considered as positive
        actions (e.g. light turned on).
        """
        for ev in events:
            if ev.state != self.active_state:
                continue

            slot = (ev.timestamp.weekday(), ev.timestamp.hour)
            self._slot_entity_counts[slot][ev.entity_id] += 1
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
        for entity_id, count in self._slot_entity_counts[slot].items():
            prob = count / total
            if count >= self.min_support and prob >= self.min_confidence:
                result.append(
                    PredictedAction(
                        entity_id=entity_id,
                        state=self.active_state,
                        probability=prob,
                        support=count,
                    )
                )

        # Sort most confident and well-supported actions first
        result.sort(key=lambda x: (x.probability, x.support), reverse=True)
        return result


def events_from_ha_states(
    ha_states: Iterable[Dict[str, Any]],
    accepted_domains: Iterable[str] = ("light", "switch", "climate"),
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

    Only entities whose domain is in `accepted_domains` are kept.
    """
    domains = set(accepted_domains)
    result: List[Event] = []

    for raw in ha_states:
        entity_id = str(raw.get("entity_id") or "").strip()
        if not entity_id or "." not in entity_id:
            continue

        domain = entity_id.split(".", 1)[0]
        if domain not in domains:
            continue

        state = str(raw.get("state") or "").strip()
        ts_raw = raw.get("last_changed") or raw.get("last_updated") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        result.append(Event(entity_id=entity_id, state=state, timestamp=ts))

    return result


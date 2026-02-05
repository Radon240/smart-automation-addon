"""
Correlation and dependency analysis model for Home Assistant automation suggestions.

This module analyzes historical state change events and discovers:
1. Temporal patterns: entities that change at consistent times
2. Sensor correlations: state changes correlated with sensor readings
3. Causal relationships: events that predictably follow other events
4. Automation suggestions: recommended automations based on discovered patterns
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional, Any
from statistics import mean, stdev
import json


@dataclass
class StateChangeEvent:
    """A single state change event with full context."""
    entity_id: str
    old_state: Optional[str]
    new_state: str
    timestamp: datetime
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        """Extract domain from entity_id."""
        return self.entity_id.split(".", 1)[0] if "." in self.entity_id else ""

    @property
    def is_binary_change(self) -> bool:
        """Check if this is a binary on/off change."""
        return self.new_state.lower() in ("on", "off", "open", "close")

    @property
    def is_numeric(self) -> bool:
        """Check if state is numeric."""
        try:
            float(self.new_state)
            return True
        except (ValueError, TypeError):
            return False

    def get_numeric_value(self) -> Optional[float]:
        """Get numeric value if state is numeric."""
        try:
            return float(self.new_state)
        except (ValueError, TypeError):
            return None


@dataclass
class TemporalPattern:
    """A recurring time-based pattern (e.g., light on at 19:30 every day)."""
    entity_id: str
    target_state: str
    weekdays: Set[int]  # 0=Monday, 6=Sunday
    hour: int
    minute: int
    consistency: float  # 0.0-1.0, how often this happens
    occurrences: int

    def to_dict(self) -> Dict:
        return {
            "entity_id": self.entity_id,
            "target_state": self.target_state,
            "weekdays": sorted(list(self.weekdays)),
            "hour": self.hour,
            "minute": self.minute,
            "consistency": round(self.consistency, 3),
            "occurrences": self.occurrences,
            "type": "temporal"
        }


@dataclass
class SensorTrigger:
    """A correlation between sensor state and entity action."""
    trigger_entity: str
    trigger_condition: str  # e.g., "value < 50" or "state == off"
    target_entity: str
    target_action: str
    delay_seconds: float  # average delay between trigger and action
    confidence: float  # 0.0-1.0
    occurrences: int

    def to_dict(self) -> Dict:
        return {
            "trigger_entity": self.trigger_entity,
            "trigger_condition": self.trigger_condition,
            "target_entity": self.target_entity,
            "target_action": self.target_action,
            "delay_seconds": round(self.delay_seconds, 1),
            "confidence": round(self.confidence, 3),
            "occurrences": self.occurrences,
            "type": "sensor_trigger"
        }


@dataclass
class AutomationSuggestion:
    """A suggested automation rule."""
    title: str
    description: str
    trigger_type: str  # "time", "sensor", "state_change"
    trigger_details: Dict[str, Any]
    actions: List[Dict[str, Any]]
    confidence: float
    automation_yaml: str  # YAML representation for easy copy-paste

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "description": self.description,
            "trigger_type": self.trigger_type,
            "trigger_details": self.trigger_details,
            "actions": self.actions,
            "confidence": round(self.confidence, 3),
            "automation_yaml": self.automation_yaml
        }


class CorrelationAnalyzer:
    """
    Analyzes historical events to discover patterns and suggest automations.
    """

    def __init__(self, min_confidence: float = 0.6, min_support: int = 3):
        self.min_confidence = min_confidence
        self.min_support = min_support

        self.events: List[StateChangeEvent] = []
        self.temporal_patterns: List[TemporalPattern] = []
        self.sensor_triggers: List[SensorTrigger] = []
        self.automation_suggestions: List[AutomationSuggestion] = []

    def fit(self, events: List[StateChangeEvent]) -> None:
        """
        Analyze events to discover patterns.
        """
        self.events = sorted(events, key=lambda e: e.timestamp)
        
        # Discover temporal patterns
        self._discover_temporal_patterns()
        
        # Discover sensor-based triggers
        self._discover_sensor_triggers()
        
        # Generate automation suggestions
        self._generate_suggestions()

    def _discover_temporal_patterns(self) -> None:
        """Find recurring time-based patterns."""
        # Group events by entity
        by_entity: Dict[str, List[StateChangeEvent]] = defaultdict(list)
        for event in self.events:
            by_entity[event.entity_id].append(event)

        self.temporal_patterns = []

        for entity_id, entity_events in by_entity.items():
            # Group by target state (on/off) and time of day
            by_state: Dict[str, List[Tuple[int, int, int]]] = defaultdict(list)  # state -> [(weekday, hour, minute), ...]
            
            for event in entity_events:
                if not event.is_binary_change:
                    continue

                state = event.new_state.lower()
                times = (event.timestamp.weekday(), event.timestamp.hour, event.timestamp.minute)
                by_state[state].append(times)

            # Analyze each state for consistency
            for state, times in by_state.items():
                if len(times) < self.min_support:
                    continue

                # Group times by hour (allowing ±15 min variance)
                hour_groups: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
                for weekday, hour, minute in times:
                    hour_groups[hour].append((weekday, minute))

                # Find consistent patterns
                for hour, occurrences in hour_groups.items():
                    if len(occurrences) >= self.min_support:
                        # Check consistency of minute
                        minutes = [m for _, m in occurrences]
                        avg_minute = int(mean(minutes))
                        variance = stdev(minutes) if len(minutes) > 1 else 0

                        # Only consider patterns with <20 min variance
                        if variance < 20:
                            weekdays = set(w for w, _ in occurrences)
                            consistency = len(occurrences) / len(by_state[state])

                            pattern = TemporalPattern(
                                entity_id=entity_id,
                                target_state=state,
                                weekdays=weekdays,
                                hour=hour,
                                minute=avg_minute,
                                consistency=consistency,
                                occurrences=len(occurrences)
                            )
                            self.temporal_patterns.append(pattern)

    def _discover_sensor_triggers(self) -> None:
        """Find correlations between sensor readings and entity state changes."""
        self.sensor_triggers = []

        # Get all sensors (entities with numeric or specific states)
        sensors = set()
        actuators = set()  # light, switch, climate
        
        for event in self.events:
            if event.domain in ("sensor", "climate"):
                sensors.add(event.entity_id)
            elif event.domain in ("light", "switch", "climate"):
                actuators.add(event.entity_id)

        # For each sensor, find correlations with actuators
        for sensor_id in sensors:
            sensor_events = [e for e in self.events if e.entity_id == sensor_id]
            if len(sensor_events) < 3:
                continue

            for actuator_id in actuators:
                if sensor_id == actuator_id:
                    continue

                actuator_events = [e for e in self.events if e.entity_id == actuator_id]
                if len(actuator_events) < 3:
                    continue

                # Find correlations: when sensor changes, does actuator follow?
                for sensor_event in sensor_events:
                    following_events = [
                        e for e in actuator_events
                        if sensor_event.timestamp < e.timestamp
                        and (e.timestamp - sensor_event.timestamp).total_seconds() < 300  # 5 min window
                    ]

                    if following_events:
                        closest = min(following_events, key=lambda e: e.timestamp - sensor_event.timestamp)
                        delay = (closest.timestamp - sensor_event.timestamp).total_seconds()
                        
                        # Record this correlation
                        sensor_value = sensor_event.get_numeric_value() or sensor_event.new_state
                        trigger_cond = f"changed to {sensor_value}"
                        
                        trigger = SensorTrigger(
                            trigger_entity=sensor_id,
                            trigger_condition=trigger_cond,
                            target_entity=actuator_id,
                            target_action=closest.new_state,
                            delay_seconds=delay,
                            confidence=0.5,  # Will be refined
                            occurrences=1
                        )
                        self.sensor_triggers.append(trigger)

        # Aggregate and deduplicate
        aggregated: Dict[Tuple, List[SensorTrigger]] = defaultdict(list)
        for trigger in self.sensor_triggers:
            key = (trigger.trigger_entity, trigger.target_entity, trigger.target_action)
            aggregated[key].append(trigger)

        self.sensor_triggers = []
        for (trig_e, tgt_e, tgt_a), triggers in aggregated.items():
            if len(triggers) >= self.min_support:
                avg_delay = mean([t.delay_seconds for t in triggers])
                confidence = len(triggers) / len(self.events) * 10  # Rough estimation
                confidence = min(confidence, 1.0)

                self.sensor_triggers.append(SensorTrigger(
                    trigger_entity=trig_e,
                    trigger_condition="state_changed",
                    target_entity=tgt_e,
                    target_action=tgt_a,
                    delay_seconds=avg_delay,
                    confidence=confidence,
                    occurrences=len(triggers)
                ))

    def _generate_suggestions(self) -> None:
        """Convert discovered patterns into automation suggestions."""
        self.automation_suggestions = []

        # From temporal patterns
        for pattern in self.temporal_patterns:
            if pattern.consistency >= self.min_confidence:
                weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                days = ", ".join(weekday_names[d] for d in sorted(pattern.weekdays))
                
                title = f"Automate {pattern.entity_id} at {pattern.hour:02d}:{pattern.minute:02d}"
                description = f"Entity {pattern.entity_id} is turned {pattern.target_state} on {days} at ~{pattern.hour:02d}:{pattern.minute:02d} ({pattern.occurrences}x, {pattern.consistency*100:.0f}%)"

                trigger_yaml = f"""
- platform: time
  at: "{pattern.hour:02d}:{pattern.minute:02d}"
"""

                action_yaml = f"""
- service: homeassistant.turn_{pattern.target_state}
  target:
    entity_id: {pattern.entity_id}
"""

                automation_yaml = f"""alias: "{title}"
trigger:{trigger_yaml}action:{action_yaml}"""

                suggestion = AutomationSuggestion(
                    title=title,
                    description=description,
                    trigger_type="time",
                    trigger_details={
                        "at": f"{pattern.hour:02d}:{pattern.minute:02d}",
                        "weekdays": sorted(pattern.weekdays)
                    },
                    actions=[{
                        "service": f"homeassistant.turn_{pattern.target_state}",
                        "entity_id": pattern.entity_id
                    }],
                    confidence=pattern.consistency,
                    automation_yaml=automation_yaml
                )
                self.automation_suggestions.append(suggestion)

        # From sensor triggers
        for trigger in self.sensor_triggers:
            if trigger.confidence >= self.min_confidence:
                title = f"When {trigger.trigger_entity} changes, {trigger.target_entity} → {trigger.target_action}"
                description = f"After {trigger.trigger_entity} changes, {trigger.target_entity} usually turns {trigger.target_action} (~{trigger.delay_seconds:.0f}s delay, {trigger.occurrences}x, {trigger.confidence*100:.0f}% confidence)"

                trigger_yaml = f"""
- platform: state
  entity_id: {trigger.trigger_entity}
"""

                action_yaml = f"""
- delay:
    seconds: {int(trigger.delay_seconds)}
- service: homeassistant.turn_{trigger.target_action}
  target:
    entity_id: {trigger.target_entity}
"""

                automation_yaml = f"""alias: "{title}"
trigger:{trigger_yaml}action:{action_yaml}"""

                suggestion = AutomationSuggestion(
                    title=title,
                    description=description,
                    trigger_type="state",
                    trigger_details={
                        "entity_id": trigger.trigger_entity,
                        "delay_seconds": trigger.delay_seconds
                    },
                    actions=[
                        {"delay_seconds": trigger.delay_seconds},
                        {"service": f"homeassistant.turn_{trigger.target_action}", "entity_id": trigger.target_entity}
                    ],
                    confidence=trigger.confidence,
                    automation_yaml=automation_yaml
                )
                self.automation_suggestions.append(suggestion)

        # Sort by confidence
        self.automation_suggestions.sort(key=lambda s: s.confidence, reverse=True)

    def get_suggestions(self, limit: int = 10) -> List[Dict]:
        """Get top automation suggestions."""
        return [s.to_dict() for s in self.automation_suggestions[:limit]]

    def get_patterns(self) -> List[Dict]:
        """Get all discovered temporal patterns."""
        return [p.to_dict() for p in self.temporal_patterns]

    def get_statistics(self) -> Dict:
        """Get analysis statistics."""
        return {
            "total_events_analyzed": len(self.events),
            "temporal_patterns_found": len(self.temporal_patterns),
            "sensor_triggers_found": len(self.sensor_triggers),
            "automation_suggestions": len(self.automation_suggestions),
            "unique_entities": len(set(e.entity_id for e in self.events))
        }


def events_from_ha_history(
    ha_history: List[Dict[str, Any]]
) -> List[StateChangeEvent]:
    """
    Convert Home Assistant /api/history/period response to StateChangeEvent objects.
    
    HA returns a list of lists, where each inner list is the history for one entity.
    Each item has: entity_id, state, last_changed, attributes, old_state (sometimes)
    """
    events: List[StateChangeEvent] = []

    # Flatten nested list structure
    all_states = []
    for entity_history in ha_history:
        if isinstance(entity_history, list):
            all_states.extend(entity_history)

    # Convert to StateChangeEvent objects
    for state_dict in all_states:
        try:
            entity_id = state_dict.get("entity_id", "")
            if not entity_id or "." not in entity_id:
                continue

            ts_raw = state_dict.get("last_changed") or state_dict.get("last_updated") or ""
            try:
                timestamp = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                continue

            new_state = str(state_dict.get("state") or "").strip()
            old_state = state_dict.get("old_state") or None
            attributes = state_dict.get("attributes") or {}

            event = StateChangeEvent(
                entity_id=entity_id,
                old_state=old_state,
                new_state=new_state,
                timestamp=timestamp,
                attributes=attributes
            )
            events.append(event)
        except Exception:
            continue

    return events

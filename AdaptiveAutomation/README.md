# AdaptiveAutomation addon

Home Assistant addon with a baseline Python model that learns user actions
from device state transitions and predicts likely next actions by time slot.

## Included files

- `config.yaml` - addon metadata and model settings
- `Dockerfile` - container build instructions
- `run.sh` - addon startup script
- `app/main.py` - Flask API for training and prediction
- `app/user_action_model.py` - model logic and persistence
- `app/requirements.txt` - Python dependencies
- `data/options.json` - example addon options

## Model settings

- `history_days` - how many days of HA history are used for training
- `min_support` - minimum number of observations for a prediction
- `min_confidence` - minimum probability threshold
- `prediction_limit` - max number of predictions returned
- `enabled_domains` - list of domains included in training (configurable from ingress UI)

## How The Model Works

The model learns from Home Assistant state transitions and predicts likely user actions
for a specific time slot (`weekday + hour`).

### 1. Training Data

- Source: Home Assistant history API (`/history/period`) via Supervisor API.
- Input records are HA states snapshots (`entity_id`, `state`, `last_changed`).
- The model converts snapshots to transitions per entity:
  - `from_state -> to_state` at timestamp `t`.
- Transitions to noisy values (`unknown`, `unavailable`, empty) are ignored.

### 2. Pattern Units

The model stores statistics in two layers:

- **Time-slot layer**: patterns for exact `(weekday, hour)` bucket.
- **Global layer**: fallback patterns across all time.

And for each layer it tracks:

- how many **distinct days** entity was active in that bucket,
- how many **distinct days** entity transitioned to specific state.

This makes the model depend on repeatability of behavior, not on raw number of devices/events.

### 3. Confidence and Support

For a candidate `(entity_id, state)` in a slot:

- `support` = number of distinct days where this transition happened
- `confidence` = `state_days / entity_days` for that slot

So confidence represents stability of the pattern for that entity at that time.

### 4. Prediction Flow

When calling `GET/POST /api/predict`, model uses this sequence:

1. Slot-level predictions with configured thresholds.
2. Slot-level predictions with relaxed support (`support >= 1`).
3. Global fallback with configured thresholds.
4. Global fallback with relaxed support.

The response is sorted by `(confidence, support)` descending and limited by `prediction_limit`.

## Parameters Explained

- `history_days`
  - More days = better chance to capture recurring habits.
  - Too small value may miss weekly patterns.

- `enabled_domains`
  - Controls which entities are included in training.
  - Recommended: controllable domains like `light`, `switch`, `climate`, `cover`, `fan`, `lock`.

- `min_support`
  - Minimum number of distinct pattern days for a prediction.
  - Higher value = fewer but more proven patterns.

- `min_confidence`
  - Minimum ratio of stable behavior for the entity/time bucket.
  - Higher value = stricter, more deterministic predictions.

- `prediction_limit`
  - Max count of returned predictions.

## Practical Tuning

- If no predictions:
  - Lower `min_support` (e.g. 1-3)
  - Lower `min_confidence` (e.g. 0.2-0.4)
  - Increase `history_days` (e.g. 30+)
  - Verify correct `enabled_domains`

- If too many noisy predictions:
  - Increase `min_support` (e.g. 5-10)
  - Increase `min_confidence` (e.g. 0.6-0.8)
  - Exclude noisy domains from `enabled_domains`

## Endpoints

- `GET /health` - addon and model status
- `GET /api/config` - effective configuration
- `POST /api/train` - train model from Home Assistant history API
- `POST /api/train-from-events` - train model from posted JSON events (local testing)
- `GET/POST /api/predict` - get predictions for now or custom timestamp
- `GET /api/model-info` - model metadata and stats

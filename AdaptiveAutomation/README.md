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

## Endpoints

- `GET /health` - addon and model status
- `GET /api/config` - effective configuration
- `POST /api/train` - train model from Home Assistant history API
- `POST /api/train-from-events` - train model from posted JSON events (local testing)
- `GET/POST /api/predict` - get predictions for now or custom timestamp
- `GET /api/model-info` - model metadata and stats

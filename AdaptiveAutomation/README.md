# AdaptiveAutomation addon

Basic Home Assistant addon template located in the repository root.

## Included files

- `config.yaml` - addon metadata and configuration schema
- `Dockerfile` - container build instructions
- `run.sh` - addon startup script
- `app/main.py` - minimal Flask service
- `app/requirements.txt` - Python dependencies
- `data/options.json` - example addon options

## Endpoints

- `GET /` - quick status text
- `GET /health` - health check
- `GET /api/config` - effective configuration

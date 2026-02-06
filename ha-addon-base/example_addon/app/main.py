from flask import Flask, jsonify, render_template_string, request
import os
import threading
import asyncio
import json
from datetime import datetime

import requests
import aiohttp
    
from ml_correlation import CorrelationAnalyzer, events_from_ha_history
from config import get_config
from time_series_analysis import TimeSeriesAnalyzer, TimeSeriesAnalysisResult
import base64
import io
import matplotlib.pyplot as plt


SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
SUPERVISOR_API_URL = "http://supervisor/core/api"

# Load configuration from file (/data/options.json) or environment
cfg = get_config()
MODEL_MIN_SUPPORT = cfg.get("min_support")
MODEL_MIN_CONFIDENCE = cfg.get("min_confidence")
HISTORY_DAYS = cfg.get("history_days")
TRAIN_HOUR = cfg.get("train_hour")

app = Flask(__name__)

# Храним последние несколько событий для отображения в UI
last_events: list[dict] = []
MAX_EVENTS = 20

# ML модель для анализа корреляций и предсказания автоматизаций
analyzer = CorrelationAnalyzer(min_confidence=MODEL_MIN_CONFIDENCE, min_support=MODEL_MIN_SUPPORT)

# Time Series Analyzer for advanced models
time_series_analyzer = TimeSeriesAnalyzer(forecast_horizon=6)

print(f"[diploma_addon] Configuration: min_support={MODEL_MIN_SUPPORT}, min_confidence={MODEL_MIN_CONFIDENCE}, history_days={HISTORY_DAYS}, train_hour={TRAIN_HOUR}")
print(f"[diploma_addon] Time Series Analyzer initialized. ARIMA available: {time_series_analyzer.get_available_models_info()['arima_available']}")

# Статус обучения
last_trained = None
training_in_progress = False
last_training_samples = 0
training_progress = 0  # 0-100%
training_status_message = "Ready"
training_current_step = ""

@app.route("/")
def index():
    """Main page showing system status, events, and time series analysis information."""
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Adaptive Home Automations</title>
        <style>
            body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 1.5rem; background: #111827; color: #e5e7eb; }
            h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
            h2 { font-size: 1.3rem; margin-bottom: 1rem; color: #f3f4f6; }
            h3 { font-size: 1.1rem; margin-bottom: 0.75rem; color: #d1d5db; }
            .status { margin-bottom: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
            .status span { padding: 0.2rem 0.5rem; border-radius: 999px; font-size: 0.8rem; }
            .status-ok { background: #065f46; }
            .status-bad { background: #7f1d1d; }
            .status-warn { background: #92400e; }
            .status-info { background: #1e40af; }
            .card { background: #1f2937; border-radius: 0.75rem; padding: 1rem 1.25rem; margin-top: 1rem; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; }
            .grid-item { background: #111827; border-radius: 0.5rem; padding: 0.75rem; }
            pre { white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; background: #111827; padding: 0.75rem; border-radius: 0.5rem; }
            .event { margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #374151; }
            .event:last-child { border-bottom: none; }
            .event-header { font-size: 0.9rem; color: #9ca3af; margin-bottom: 0.25rem; }
            .badge { display: inline-block; padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.7rem; background: #111827; color: #e5e7eb; margin-left: 0.25rem; }
            .api-info { font-family: monospace; font-size: 0.8rem; background: #111827; padding: 0.5rem; border-radius: 0.25rem; overflow-x: auto; }
            .model-info { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }
            .model-card { background: #111827; padding: 0.75rem; border-radius: 0.5rem; flex: 1; min-width: 200px; }
            .model-card h4 { margin: 0 0 0.5rem 0; color: #9ca3af; font-size: 0.9rem; }
            .model-card p { margin: 0.25rem 0; font-size: 0.85rem; }
            .visualization { margin-top: 1rem; text-align: center; }
            .visualization img { max-width: 100%; height: auto; border-radius: 0.5rem; }
            .api-endpoints { margin-top: 1rem; }
            .api-endpoint { background: #111827; padding: 0.5rem; margin-bottom: 0.5rem; border-radius: 0.25rem; }
            .api-endpoint-code { font-family: monospace; color: #3b82f6; }
        </style>
    </head>
    <body>
        <h1>Adaptive Home Automations</h1>
        <div class="status">
            <span class="{{ 'status-ok' if supervisor_token_present else 'status-bad' }}">
                SUPERVISOR_TOKEN: {{ 'OK' if supervisor_token_present else 'NOT FOUND' }}
            </span>
            <span class="badge">events: {{ events_count }}</span>
            <span class="{{ 'status-ok' if last_trained else 'status-warn' }}">
                {{ 'TRAINED' if last_trained else 'NOT TRAINED' }}
            </span>
        </div>

        <div class="card">
            <h2>📊 System Overview</h2>
            <div class="grid">
                <div class="grid-item">
                    <h3>🤖 ML Models Status</h3>
                    <div class="model-info">
                        <div class="model-card">
                            <h4>Correlation Analyzer</h4>
                            <p>✅ Available</p>
                            <p>📊 Patterns: {{ statistics.temporal_patterns_found if statistics else 'N/A' }}</p>
                            <p>💡 Suggestions: {{ statistics.automation_suggestions if statistics else 'N/A' }}</p>
                        </div>
                        <div class="model-card">
                            <h4>Time Series (ARIMA)</h4>
                            <p>{{ '✅ Available' if model_info.arima_available else '❌ Not available' }}</p>
                            <p>📈 Models trained: {{ model_info.trained_models|length if model_info else '0' }}</p>
                            <p>🔄 Forecast horizon: 6 hours</p>
                        </div>
                    </div>
                </div>
                <div class="grid-item">
                    <h3>🔧 Configuration</h3>
                    <p><strong>Min Support:</strong> {{ min_support }}</p>
                    <p><strong>Min Confidence:</strong> {{ min_confidence }}</p>
                    <p><strong>History Days:</strong> {{ history_days }}</p>
                    <p><strong>Training Hour:</strong> {{ train_hour }}:00</p>
                    <p><strong>Last Training:</strong> {{ last_trained.isoformat() if last_trained else 'Never' }}</p>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📈 Time Series Analysis</h2>
            {% if time_series_results %}
                <div class="grid">
                    {% for entity_id, result in time_series_results.items() %}
                        <div class="grid-item">
                            <h3>{{ entity_id }}</h3>
                            <p><strong>Model:</strong> {{ result.model_type }}</p>
                            <p><strong>Status:</strong> {{ result.status }}</p>
                            <p><strong>MSE:</strong> {{ "%.4f"|format(result.metrics.mse) if result.metrics else 'N/A' }}</p>
                            <p><strong>RMSE:</strong> {{ "%.4f"|format(result.metrics.rmse) if result.metrics else 'N/A' }}</p>
                            <p><strong>R² Score:</strong> {{ "%.4f"|format(result.metrics.r2_score) if result.metrics else 'N/A' }}</p>
                            {% if result.visualization %}
                                <div class="visualization">
                                    <img src="{{ result.visualization }}" alt="Predictions for {{ entity_id }}">
                                </div>
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <p>No time series analysis results yet. Train models to see predictions.</p>
            {% endif %}
        </div>

        <div class="card">
            <h2>🔄 API Endpoints</h2>
            <div class="api-endpoints">
                <div class="api-endpoint">
                    <span class="api-endpoint-code">POST /api/train</span> - Train correlation analyzer
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">POST /api/train-advanced</span> - Train both correlation and time series models
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">GET /api/automation-suggestions</span> - Get automation suggestions
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">GET /api/patterns</span> - Get discovered temporal patterns
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">POST /api/time-series/analyze</span> - Analyze specific entity time series
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">POST /api/time-series/suggestions</span> - Get time series based suggestions
                </div>
                <div class="api-endpoint">
                    <span class="api-endpoint-code">GET /api/time-series/models</span> - Get models information
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📜 Latest Home Assistant Events</h2>
            {% if events %}
                {% for ev in events %}
                    <div class="event">
                        <div class="event-header">
                            {{ ev.get('event_type', 'event') }}
                            {% if ev.get('entity_id') %}
                                <span class="badge">{{ ev.get('entity_id') }}</span>
                            {% endif %}
                        </div>
                        <pre>{{ ev | tojson(indent=2) }}</pre>
                    </div>
                {% endfor %}
            {% else %}
                <p>No events yet or still connecting to WebSocket API.</p>
            {% endif %}
        </div>
    </body>
    </html>
    """
    # Преобразуем внутренний формат в удобный для шаблона
    events_for_view = []
    for raw in reversed(last_events):
        ev = raw.get("event", {})
        data = ev.get("data", {}) or {}
        entity_id = data.get("entity_id") or data.get("new_state", {}).get("entity_id")
        events_for_view.append(
            {
                "event_type": ev.get("event_type"),
                "entity_id": entity_id,
                "raw": ev,
            }
        )

    # Для отображения в pre используем исходный объект события
    # (jinja2 tojson сам его отформатирует)
    return render_template_string(
        html,
        supervisor_token_present=bool(SUPERVISOR_TOKEN),
        events_count=len(last_events),
        events=[e["raw"] for e in events_for_view],
    )


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Return current model configuration and training status."""
    return jsonify({
        "min_support": MODEL_MIN_SUPPORT,
        "min_confidence": MODEL_MIN_CONFIDENCE,
        "history_days": HISTORY_DAYS,
        "train_hour": TRAIN_HOUR,
        "last_trained": last_trained.isoformat() if last_trained else None,
        "training_in_progress": training_in_progress,
        "training_progress": training_progress,
        "training_status": training_status_message,
        "training_step": training_current_step,
        "last_training_samples": last_training_samples
    }), 200


@app.route("/api/config/reload", methods=["POST"])
def reload_config():
    """Reload configuration from /data/options.json."""
    global MODEL_MIN_SUPPORT, MODEL_MIN_CONFIDENCE, HISTORY_DAYS, TRAIN_HOUR, analyzer
    try:
        cfg.reload()
        MODEL_MIN_SUPPORT = cfg.get("min_support")
        MODEL_MIN_CONFIDENCE = cfg.get("min_confidence")
        HISTORY_DAYS = cfg.get("history_days")
        TRAIN_HOUR = cfg.get("train_hour")
        
        # Recreate analyzer with new parameters
        analyzer = CorrelationAnalyzer(
            min_confidence=MODEL_MIN_CONFIDENCE,
            min_support=MODEL_MIN_SUPPORT
        )
        
        print(f"[diploma_addon] Config reloaded: min_support={MODEL_MIN_SUPPORT}, min_confidence={MODEL_MIN_CONFIDENCE}, history_days={HISTORY_DAYS}, train_hour={TRAIN_HOUR}")
        
        return jsonify({
            "status": "ok",
            "message": "Configuration reloaded successfully",
            "config": {
                "min_support": MODEL_MIN_SUPPORT,
                "min_confidence": MODEL_MIN_CONFIDENCE,
                "history_days": HISTORY_DAYS,
                "train_hour": TRAIN_HOUR,
            }
        }), 200
    except Exception as e:
        print(f"[diploma_addon] Config reload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/automation-suggestions", methods=["GET"])
def get_automation_suggestions():
    """
    Returns automation suggestions based on discovered patterns.
    """
    try:
        global last_trained, training_in_progress

        if training_in_progress:
            return jsonify({"error": "training_in_progress", "status": "busy"}), 503

        if last_trained is None:
            return jsonify({
                "error": "model_not_trained",
                "status": "no_model",
                "hint": "Call POST /api/train or wait for nightly training."
            }), 409

        suggestions = analyzer.get_suggestions(limit=20)
        stats = analyzer.get_statistics()

        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "last_trained": last_trained.isoformat(),
            "suggestions": suggestions,
            "statistics": stats
        }), 200
    except Exception as e:
        print(f"[diploma_addon] Error in automation suggestions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route("/api/patterns", methods=["GET"])
def get_patterns():
    """
    Returns discovered temporal patterns.
    """
    try:
        global last_trained, training_in_progress

        if training_in_progress:
            return jsonify({"error": "training_in_progress", "status": "busy"}), 503

        if last_trained is None:
            return jsonify({
                "error": "model_not_trained",
                "status": "no_model",
                "hint": "Call POST /api/train or wait for nightly training."
            }), 409

        patterns = analyzer.get_patterns()

        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "last_trained": last_trained.isoformat(),
            "patterns": patterns,
            "total": len(patterns)
        }), 200
    except Exception as e:
        print(f"[diploma_addon] Error in patterns: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route("/api/predictions", methods=["POST"])
def get_predictions():
    """
    Возвращает предсказания по последней обученной модели.
    Не выполняет обучение — для этого есть /api/train.
    """
    try:
        now = datetime.now()
        global last_trained, training_in_progress, last_training_samples

        if training_in_progress:
            return jsonify({"error": "training_in_progress", "status": "busy"}), 503

        if last_trained is None:
            return jsonify({"error": "model_not_trained", "status": "no_model", "hint": "Call /api/train or wait for nightly training."}), 409

        # Return automation suggestions instead (same data)
        suggestions = analyzer.get_suggestions(limit=10)

        result = {
            "timestamp": now.isoformat(),
            "suggestions": suggestions,
            "last_trained": last_trained.isoformat(),
            "training_samples": last_training_samples
        }

        return jsonify(result), 200
    except Exception as e:
        print(f"[diploma_addon] Error in predictions endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/time-series/analyze", methods=["POST"])
def analyze_time_series():
    """
    Analyze time series data for a specific entity using ARIMA models.
    """
    try:
        data = request.get_json()
        if not data or 'entity_id' not in data:
            return jsonify({"error": "entity_id is required", "status": "error"}), 400

        entity_id = data['entity_id']
        frequency = data.get('frequency', '1H')  # Resampling frequency

        # Get historical data
        ha_history = _fetch_history_from_ha()
        if not ha_history:
            return jsonify({"error": "No historical data available", "status": "error"}), 404

        # Analyze time series using ARIMA
        result = time_series_analyzer.analyze_entity_timeseries(
            ha_history, entity_id, frequency
        )

        if result is None:
            return jsonify({
                "error": f"Failed to analyze time series for {entity_id}",
                "status": "error",
                "hint": "Check if entity has enough numeric data"
            }), 400

        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "result": result.to_dict()
        }), 200

    except Exception as e:
        print(f"[diploma_addon] Error in time series analysis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/time-series/suggestions", methods=["POST"])
def get_time_series_suggestions():
    """
    Get automation suggestions based on time series predictions.
    """
    try:
        data = request.get_json()
        if not data or 'entity_id' not in data:
            return jsonify({"error": "entity_id is required", "status": "error"}), 400

        entity_id = data['entity_id']
        confidence_threshold = data.get('confidence_threshold', 0.7)

        # Get historical data
        ha_history = _fetch_history_from_ha()
        if not ha_history:
            return jsonify({"error": "No historical data available", "status": "error"}), 404

        # Analyze time series using ARIMA
        result = time_series_analyzer.analyze_entity_timeseries(
            ha_history, entity_id
        )

        if result is None:
            return jsonify({
                "error": f"Failed to analyze time series for {entity_id}",
                "status": "error"
            }), 400

        # Generate suggestions from predictions
        suggestions = time_series_analyzer.get_automation_suggestions_from_predictions(
            result.predictions, confidence_threshold
        )

        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "entity_id": entity_id,
            "suggestions": suggestions,
            "model_info": time_series_analyzer.get_available_models_info()
        }), 200

    except Exception as e:
        print(f"[diploma_addon] Error in time series suggestions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/time-series/models", methods=["GET"])
def get_time_series_models_info():
    """
    Get information about available time series models and their status.
    """
    try:
        model_info = time_series_analyzer.get_available_models_info()
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "models": model_info
        }), 200
    except Exception as e:
        print(f"[diploma_addon] Error getting model info: {e}")
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/train-advanced", methods=["POST"])
def train_advanced_models():
    """
    Train both correlation analyzer and time series models.
    """
    global training_in_progress, last_trained, last_training_samples, analyzer
    global training_progress, training_status_message, training_current_step

    if training_in_progress:
        return jsonify({"status": "busy", "message": "Training already in progress"}), 409

    training_in_progress = True
    training_progress = 0
    training_status_message = "Starting advanced training..."
    training_current_step = "Initialization"
    start = datetime.now()

    try:
        # Train correlation analyzer (existing functionality)
        training_current_step = "Fetching history data"
        training_progress = 10
        training_status_message = "Fetching historical data from Home Assistant"

        ha_history = _fetch_history_from_ha()

        training_current_step = "Processing events"
        training_progress = 20
        training_status_message = "Processing and converting events"

        if last_events:
            for event_data in last_events:
                ev = event_data.get("event", {})
                data = ev.get("data", {}) or {}
                new_state = data.get("new_state")
                if new_state:
                    ha_history.append(new_state)

        events = events_from_ha_history(ha_history)

        training_current_step = "Training correlation analyzer"
        training_progress = 30
        training_status_message = "Training correlation analysis model"

        analyzer = CorrelationAnalyzer(
            min_confidence=MODEL_MIN_CONFIDENCE,
            min_support=MODEL_MIN_SUPPORT
        )

        if events:
            analyzer.fit(events)
            last_training_samples = len(events)
        else:
            last_training_samples = 0

        # Train time series models for all numeric entities using ARIMA
        time_series_results = []
        unique_entities = set(e.get('entity_id') for e in ha_history if 'entity_id' in e)
        total_entities = len(unique_entities)
        entities_processed = 0

        training_current_step = "Training time series models"
        training_progress = 40
        training_status_message = f"Training ARIMA models for {total_entities} entities"

        for i, entity_id in enumerate(unique_entities):
            try:
                training_status_message = f"Training ARIMA model for {entity_id} ({i+1}/{total_entities})"
                training_progress = 40 + int((i / total_entities) * 50)

                # Train ARIMA model
                arima_result = time_series_analyzer.analyze_entity_timeseries(
                    ha_history, entity_id, frequency='1H'
                )

                if arima_result:
                    time_series_results.append({
                        'entity_id': entity_id,
                        'model_type': 'arima',
                        'status': 'success',
                        'metrics': arima_result.training_metrics
                    })
                else:
                    time_series_results.append({
                        'entity_id': entity_id,
                        'model_type': 'arima',
                        'status': 'failed',
                        'reason': 'insufficient_data'
                    })

                entities_processed += 1

            except Exception as e:
                time_series_results.append({
                    'entity_id': entity_id,
                    'model_type': 'arima',
                    'status': 'error',
                    'error': str(e)
                })
                entities_processed += 1

        training_current_step = "Finalizing training"
        training_progress = 95
        training_status_message = "Finalizing training and calculating statistics"

        # Update training status
        last_trained = datetime.now()
        duration = (last_trained - start).total_seconds()
        training_in_progress = False
        training_progress = 100
        training_status_message = "Advanced training completed successfully"
        training_current_step = ""

        # Get statistics from both analyzers
        correlation_stats = analyzer.get_statistics()
        model_info = time_series_analyzer.get_available_models_info()

        return jsonify({
            "status": "ok",
            "trained_at": last_trained.isoformat(),
            "training_samples": last_training_samples,
            "duration_seconds": duration,
            "correlation_analysis": correlation_stats,
            "time_series_analysis": {
                "entities_processed": len(unique_entities),
                "successful_models": len([r for r in time_series_results if r['status'] == 'success']),
                "results": time_series_results
            },
            "model_info": model_info
        }), 200

    except Exception as e:
        training_in_progress = False
        training_progress = 0
        training_status_message = f"Advanced training failed: {str(e)}"
        training_current_step = ""
        print(f"[diploma_addon] Advanced training error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


def _fetch_history_from_ha():
    """
    Получает историю состояний сущностей из Home Assistant REST API.
    Запрашивает последние N дней для всех сущностей (N = HISTORY_DAYS).
    """
    if not SUPERVISOR_TOKEN:
        print("[diploma_addon] SUPERVISOR_TOKEN not set, skipping history fetch")
        return []
    
    try:
        # Используем REST API Home Assistant для получения истории
        # /api/history/period?start_time=...&end_time=...
        from datetime import timedelta
        
        end_time = datetime.now()
        start_time = end_time - timedelta(days=HISTORY_DAYS)
        
        url = f"{SUPERVISOR_API_URL}/history/period?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"
        
        headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}
        
        print(f"[diploma_addon] Fetching history from {start_time.date()} to {end_time.date()} (history_days={HISTORY_DAYS})...")
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"[diploma_addon] Failed to fetch history: {response.status_code}")
            return []
        
        # Home Assistant возвращает список списков (по одному списку на сущность)
        # Каждый элемент - это объект состояния с полями: entity_id, state, last_changed, attributes
        all_history = response.json()
        
        # Сглаживаем структуру - объединяем все состояния из всех сущностей
        flattened = []
        for entity_history in all_history:
            if isinstance(entity_history, list):
                flattened.extend(entity_history)
        
        print(f"[diploma_addon] Fetched {len(flattened)} historical states")
        return flattened
        
    except requests.exceptions.RequestException as e:
        print(f"[diploma_addon] Error fetching history from Home Assistant: {e}")
        return []
    except Exception as e:
        print(f"[diploma_addon] Unexpected error in _fetch_history_from_ha: {e}")
        import traceback
        traceback.print_exc()
        return []


@app.route("/api/train", methods=["POST"])
def train_now():
    """Trigger training immediately: fetch history, analyze correlations."""
    global training_in_progress, last_trained, last_training_samples, analyzer
    global training_progress, training_status_message, training_current_step

    if training_in_progress:
        return jsonify({"status": "busy", "message": "Training already in progress"}), 409

    training_in_progress = True
    training_progress = 0
    training_status_message = "Starting training..."
    training_current_step = "Initialization"
    start = datetime.now()

    try:
        training_current_step = "Fetching history data"
        training_progress = 10
        training_status_message = "Fetching historical data from Home Assistant"

        ha_history = _fetch_history_from_ha()

        training_current_step = "Processing events"
        training_progress = 30
        training_status_message = "Processing and converting events"

        # Add recent WebSocket events to training data
        if last_events:
            for event_data in last_events:
                ev = event_data.get("event", {})
                data = ev.get("data", {}) or {}
                new_state = data.get("new_state")
                if new_state:
                    ha_history.append(new_state)

        # Convert to correlation events
        events = events_from_ha_history(ha_history)

        training_current_step = "Training correlation analyzer"
        training_progress = 60
        training_status_message = "Training correlation analysis model"

        # Create new analyzer and fit
        analyzer = CorrelationAnalyzer(
            min_confidence=MODEL_MIN_CONFIDENCE,
            min_support=MODEL_MIN_SUPPORT
        )

        if events:
            analyzer.fit(events)
            last_training_samples = len(events)
        else:
            last_training_samples = 0

        training_current_step = "Finalizing model"
        training_progress = 90
        training_status_message = "Finalizing training and calculating statistics"

        stats = analyzer.get_statistics()
        last_trained = datetime.now()
        duration = (last_trained - start).total_seconds()

        training_in_progress = False
        training_progress = 100
        training_status_message = "Training completed successfully"
        training_current_step = ""

        return jsonify({
            "status": "ok",
            "trained_at": last_trained.isoformat(),
            "training_samples": last_training_samples,
            "duration_seconds": duration,
            "analysis": stats
        }), 200
    except Exception as e:
        training_in_progress = False
        training_progress = 0
        training_status_message = f"Training failed: {str(e)}"
        training_current_step = ""
        print(f"[diploma_addon] Training error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


def _nightly_trainer_thread():
    """Background thread that runs training once a day at configured hour."""
    import time
    from datetime import timedelta
    print(f"[diploma_addon] Nightly trainer started, will run at hour {TRAIN_HOUR}")
    while True:
        now = datetime.now()
        run_at = now.replace(hour=TRAIN_HOUR, minute=0, second=0, microsecond=0)
        if run_at <= now:
            run_at = run_at + timedelta(days=1)
        wait_seconds = (run_at - now).total_seconds()
        time.sleep(wait_seconds)
        try:
            print("[diploma_addon] Running scheduled training...")
            # perform advanced training with both correlation and time series models
            train_advanced_models()
        except Exception as e:
            print(f"[diploma_addon] Nightly training failed: {e}")


async def _listen_events_loop():
    """Асинхронный цикл подключения к WebSocket Home Assistant."""
    if not SUPERVISOR_TOKEN:
        print("[diploma_addon] SUPERVISOR_TOKEN is not set, cannot listen for events")
        return

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(SUPERVISOR_WS_URL) as ws:
                    print("[diploma_addon] Connected to Home Assistant WebSocket API")

                    # Основной цикл обработки входящих сообщений
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            msg_type = data.get("type")

                            if msg_type == "auth_required":
                                await ws.send_json(
                                    {"type": "auth", "access_token": SUPERVISOR_TOKEN}
                                )
                            elif msg_type == "auth_ok":
                                # Подписываемся на события изменения состояний
                                await ws.send_json(
                                    {
                                        "id": 1,
                                        "type": "subscribe_events",
                                        "event_type": "state_changed",
                                    }
                                )
                                print(
                                    "[diploma_addon] Subscribed to state_changed events"
                                )
                            elif msg_type == "event":
                                # Сохраняем последние N событий
                                last_events.append(data)
                                if len(last_events) > MAX_EVENTS:
                                    del last_events[0 : len(last_events) - MAX_EVENTS]
                        else:
                            # Любой другой тип сообщения/ошибка – пробуем переподключиться
                            break
        except Exception as e:
            print(f"[diploma_addon] WebSocket error: {e}")

        # Небольшая пауза перед попыткой переподключения
        await asyncio.sleep(5)


def start_event_listener_thread():
    """Запускаем отдельный поток с event loop для прослушивания событий."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_listen_events_loop())


if __name__ == "__main__":
    # Стартуем фонового слушателя событий HA
    listener_thread = threading.Thread(
        target=start_event_listener_thread, name="ha-events-listener", daemon=True
    )
    listener_thread.start()

    # Запускаем фоновый ночной тренер (daemon)
    trainer_thread = threading.Thread(target=_nightly_trainer_thread, name="nightly-trainer", daemon=True)
    trainer_thread.start()

    # Flask-приложение для ML API (отдельный порт 5000)
    # .NET приложение запущено на порте 8080 и вызывает этот API
    print("[diploma_addon] Flask ML service starting on 127.0.0.1:5000...")
    app.run(host="127.0.0.1", port=5000, debug=False)

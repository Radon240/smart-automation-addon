from flask import Flask, jsonify, render_template_string, request
import os
import threading
import asyncio
import json
from datetime import datetime

import requests
import aiohttp

from ml_model import TimeSlotHabitModel, events_from_ha_states


SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
SUPERVISOR_API_URL = "http://supervisor/core/api"

app = Flask(__name__)

# Храним последние несколько событий для отображения в UI
last_events: list[dict] = []
MAX_EVENTS = 20

# ML модель для предсказаний
ml_model = TimeSlotHabitModel(min_support=2, min_confidence=0.4)


@app.route("/")
def index():
    """Простая страница для ingress с последними событиями."""
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Diploma Addon</title>
        <style>
            body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 1.5rem; background: #111827; color: #e5e7eb; }
            h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
            .status { margin-bottom: 1rem; }
            .status span { padding: 0.2rem 0.5rem; border-radius: 999px; font-size: 0.8rem; }
            .status-ok { background: #065f46; }
            .status-bad { background: #7f1d1d; }
            .card { background: #1f2937; border-radius: 0.75rem; padding: 1rem 1.25rem; margin-top: 1rem; }
            pre { white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; background: #111827; padding: 0.75rem; border-radius: 0.5rem; }
            .event { margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px solid #374151; }
            .event:last-child { border-bottom: none; }
            .event-header { font-size: 0.9rem; color: #9ca3af; margin-bottom: 0.25rem; }
            .badge { display: inline-block; padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.7rem; background: #111827; color: #e5e7eb; margin-left: 0.25rem; }
        </style>
    </head>
    <body>
        <h1>Diploma Example Addon</h1>
        <div class="status">
            <span class="{{ 'status-ok' if supervisor_token_present else 'status-bad' }}">
                SUPERVISOR_TOKEN: {{ 'OK' if supervisor_token_present else 'NOT FOUND' }}
            </span>
            <span class="badge">events: {{ events_count }}</span>
        </div>

        <div class="card">
            <h2>Последние события Home Assistant</h2>
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
                <p>Событий пока нет или ещё идёт подключение к WebSocket API.</p>
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


@app.route("/api/predictions", methods=["POST"])
def get_predictions():
    """
    API endpoint для получения предсказаний на основе истории событий Home Assistant.
    Вызывается из .NET addon для анализа привычек и предложения автоматизаций.
    """
    try:
        # Получаем текущую дату и время
        now = datetime.now()
        
        # Если у нас есть сохранённые события, тренируем модель на них
        if last_events:
            # Преобразуем события HA в формат для модели
            ha_states = []
            for event_data in last_events:
                ev = event_data.get("event", {})
                data = ev.get("data", {}) or {}
                new_state = data.get("new_state")
                
                if new_state:
                    ha_states.append(new_state)
            
            # Преобразуем в Event объекты
            events = events_from_ha_states(ha_states)
            
            # Тренируем модель
            if events:
                ml_model.fit(events)
        
        # Получаем предсказания для текущего времени
        predictions = ml_model.predict_for_datetime(now)
        
        # Форматируем ответ
        result = {
            "timestamp": now.isoformat(),
            "weekday": now.weekday(),
            "hour": now.hour,
            "predictions": [
                {
                    "entity_id": p.entity_id,
                    "state": p.state,
                    "probability": round(p.probability, 3),
                    "support": p.support
                }
                for p in predictions
            ],
            "total_predictions": len(predictions)
        }
        
        return jsonify(result), 200
    except Exception as e:
        print(f"[diploma_addon] Error in predictions endpoint: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500


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

    # Flask-приложение для ingress
    app.run(host="0.0.0.0", port=8080)

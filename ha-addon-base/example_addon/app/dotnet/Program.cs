using System.Net.Http.Headers;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var builder = WebApplication.CreateBuilder(args);

// HttpClient для общения с Home Assistant Supervisor API и REST API Home Assistant
builder.Services.AddHttpClient("hass", client =>
{
    var baseUrl = Environment.GetEnvironmentVariable("SUPERVISOR_API_URL")
                  ?? "http://supervisor/core/api/";

    // Гарантируем завершающий слэш, чтобы относительные пути корректно конкатенировались (…/api/ + states)
    if (!baseUrl.EndsWith("/"))
    {
        baseUrl += "/";
    }
    var token = Environment.GetEnvironmentVariable("SUPERVISOR_TOKEN");

    client.BaseAddress = new Uri(baseUrl);
    if (!string.IsNullOrWhiteSpace(token))
    {
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
    }
});

// HttpClient для общения с Python ML моделью (локальный Flask сервис)
builder.Services.AddHttpClient("python", client =>
{
    var baseUrl = Environment.GetEnvironmentVariable("PYTHON_API_URL")
                  ?? "http://127.0.0.1:5000/";
    
    if (!baseUrl.EndsWith("/"))
    {
        baseUrl += "/";
    }
    client.BaseAddress = new Uri(baseUrl);
});

var app = builder.Build();

app.Use(async (context, next) =>
{
    if (context.Request.Headers.TryGetValue("X-Ingress-Path", out var ingressPath))
    {
        context.Request.PathBase = ingressPath.ToString();
    }

    await next();
});

// Простая HTML-страница для ingress Home Assistant
app.MapGet("/", async context =>
{
    context.Response.ContentType = "text/html; charset=utf-8";

    const string html = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Adaptive Home Automation - Prototype</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
            :root {
                color-scheme: dark;
            }
            * {
                box-sizing: border-box;
            }
            body {
                margin: 0;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: radial-gradient(circle at top, #1f2937 0, #020617 45%, #000 100%);
                color: #e5e7eb;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 1.5rem;
            }
            .shell {
                width: 100%;
                max-width: 960px;
                background: rgba(15, 23, 42, 0.9);
                border-radius: 1.25rem;
                border: 1px solid rgba(148, 163, 184, 0.2);
                box-shadow:
                    0 40px 80px rgba(0, 0, 0, 0.65),
                    0 0 0 1px rgba(15, 23, 42, 0.9);
                overflow: hidden;
                backdrop-filter: blur(18px);
            }
            .header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 1rem 1.5rem;
                border-bottom: 1px solid rgba(55, 65, 81, 0.8);
                background: linear-gradient(90deg, rgba(15, 23, 42, 0.8), rgba(30, 64, 175, 0.4));
            }
            .title {
                display: flex;
                flex-direction: column;
                gap: 0.1rem;
            }
            .title-main {
                font-size: 1.25rem;
                font-weight: 600;
                letter-spacing: 0.02em;
                display: flex;
                align-items: center;
                gap: 0.4rem;
            }
            .title-sub {
                font-size: 0.8rem;
                color: #9ca3af;
            }
            .pill {
                font-size: 0.7rem;
                padding: 0.15rem 0.6rem;
                border-radius: 999px;
                border: 1px solid rgba(96, 165, 250, 0.7);
                color: #bfdbfe;
                background: rgba(15, 23, 42, 0.9);
            }
            .status-dot {
                width: 0.55rem;
                height: 0.55rem;
                border-radius: 999px;
                background: #22c55e;
                box-shadow: 0 0 0 6px rgba(34, 197, 94, 0.25);
            }
            .status-row {
                display: flex;
                align-items: center;
                gap: 0.4rem;
                font-size: 0.78rem;
                color: #a5b4fc;
            }
            .body {
                display: grid;
                grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.8fr);
                gap: 1.25rem;
                padding: 1.4rem 1.5rem 1.5rem;
            }
            @media (max-width: 768px) {
                .body {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
            .card {
                background: radial-gradient(circle at top left, rgba(37, 99, 235, 0.16), rgba(15, 23, 42, 0.96));
                border-radius: 1rem;
                border: 1px solid rgba(55, 65, 81, 0.9);
                padding: 1.1rem 1.25rem;
            }
            .card h2 {
                font-size: 0.95rem;
                margin: 0 0 0.4rem;
                font-weight: 600;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                color: #9ca3af;
            }
            .hero-title {
                font-size: 1.35rem;
                font-weight: 600;
                margin-bottom: 0.4rem;
            }
            .hero-accent {
                background: linear-gradient(120deg, #22c55e, #38bdf8, #f97316);
                -webkit-background-clip: text;
                color: transparent;
            }
            .hero-text {
                font-size: 0.9rem;
                color: #9ca3af;
                line-height: 1.6;
                margin-bottom: 0.8rem;
            }
            .chips {
                display: flex;
                flex-wrap: wrap;
                gap: 0.4rem;
                margin-bottom: 0.9rem;
            }
            .chip {
                font-size: 0.75rem;
                padding: 0.18rem 0.65rem;
                border-radius: 999px;
                border: 1px solid rgba(75, 85, 99, 0.9);
                background: rgba(15, 23, 42, 0.95);
                color: #d1d5db;
            }
            .primary-button {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 0.35rem;
                padding: 0.5rem 0.9rem;
                border-radius: 999px;
                border: 0;
                background: linear-gradient(115deg, #22c55e, #22c55e, #0ea5e9);
                color: #020617;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                box-shadow:
                    0 14px 40px rgba(34, 197, 94, 0.4),
                    0 0 0 1px rgba(15, 23, 42, 0.7);
                transition: transform 0.08s ease, box-shadow 0.08s ease, filter 0.08s ease;
            }
            .primary-button:hover {
                transform: translateY(-1px);
                filter: brightness(1.05);
                box-shadow:
                    0 18px 50px rgba(34, 197, 94, 0.5),
                    0 0 0 1px rgba(15, 23, 42, 0.9);
            }
            .primary-button:active {
                transform: translateY(0);
                filter: brightness(0.98);
                box-shadow:
                    0 10px 26px rgba(34, 197, 94, 0.55),
                    0 0 0 1px rgba(15, 23, 42, 0.9);
            }
            .primary-button span {
                font-size: 1rem;
            }
            .secondary-info {
                font-size: 0.78rem;
                color: #9ca3af;
                margin-left: 0.6rem;
            }
            .right-card {
                background: radial-gradient(circle at top right, rgba(56, 189, 248, 0.18), rgba(15, 23, 42, 0.96));
            }
            .entities-card {
                margin-top: 1rem;
                background: radial-gradient(circle at top, rgba(34, 197, 94, 0.14), rgba(15, 23, 42, 0.96));
            }
            .metric-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 0.4rem;
                font-size: 0.8rem;
                color: #9ca3af;
            }
            .metric-label {
                display: flex;
                align-items: center;
                gap: 0.35rem;
            }
            .metric-dot {
                width: 0.5rem;
                height: 0.5rem;
                border-radius: 999px;
                background: #38bdf8;
            }
            .metric-value {
                font-weight: 600;
                color: #e5e7eb;
            }
            .timeline {
                margin-top: 0.7rem;
                border-radius: 0.9rem;
                border: 1px solid rgba(55, 65, 81, 0.9);
                background: rgba(15, 23, 42, 0.96);
                padding: 0.7rem 0.8rem;
                font-size: 0.78rem;
            }
            .entities-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.4rem;
            }
            .entities-badge {
                font-size: 0.75rem;
                padding: 0.1rem 0.5rem;
                border-radius: 999px;
                border: 1px solid rgba(52, 211, 153, 0.7);
                color: #bbf7d0;
                background: rgba(6, 78, 59, 0.35);
            }
            .entities-list {
                max-height: 240px;
                overflow: auto;
                margin-top: 0.4rem;
                padding-right: 0.15rem;
            }
            .entities-button {
                background: rgba(15, 23, 42, 0.95);
                border-radius: 999px;
                border: 1px solid rgba(55, 65, 81, 0.9);
                color: #e5e7eb;
                font-size: 0.78rem;
                padding: 0.3rem 0.9rem;
                cursor: pointer;
            }
            .entity-row {
                display: grid;
                grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr);
                gap: 0.4rem;
                padding: 0.3rem 0.15rem;
                border-bottom: 1px solid rgba(31, 41, 55, 0.9);
                font-size: 0.78rem;
            }
            .entity-row:last-child {
                border-bottom: none;
            }
            .entity-id {
                color: #e5e7eb;
                word-break: break-all;
            }
            .entity-domain {
                color: #a5b4fc;
            }
            .entity-state {
                color: #fde68a;
            }
            .entities-error {
                font-size: 0.8rem;
                color: #fecaca;
            }
            code {
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
                font-size: 0.76rem;
                background: rgba(15, 23, 42, 0.9);
                padding: 0.1rem 0.3rem;
                border-radius: 0.3rem;
                border: 1px solid rgba(55, 65, 81, 0.9);
            }
            .predictions-card {
                background: radial-gradient(circle at bottom left, rgba(168, 85, 247, 0.14), rgba(15, 23, 42, 0.96));
            }
            .predictions-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.4rem;
            }
            .predictions-badge {
                font-size: 0.75rem;
                padding: 0.1rem 0.5rem;
                border-radius: 999px;
                border: 1px solid rgba(168, 85, 247, 0.7);
                color: #e9d5ff;
                background: rgba(88, 28, 135, 0.35);
            }
            .predictions-list {
                max-height: 240px;
                overflow: auto;
                margin-top: 0.4rem;
                padding-right: 0.15rem;
            }
            .prediction-row {
                display: grid;
                grid-template-columns: minmax(0, 1.8fr) minmax(0, 0.8fr) minmax(0, 0.6fr);
                gap: 0.4rem;
                padding: 0.3rem 0.15rem;
                border-bottom: 1px solid rgba(31, 41, 55, 0.9);
                font-size: 0.78rem;
            }
            .prediction-row:last-child {
                border-bottom: none;
            }
            .prediction-entity {
                color: #e5e7eb;
                word-break: break-all;
            }
            .prediction-probability {
                color: #d8b4fe;
                font-weight: 600;
            }
            .prediction-support {
                color: #86efac;
                text-align: right;
            }
            .predictions-error {
                font-size: 0.8rem;
                color: #fecaca;
            }
            .predictions-loading {
                font-size: 0.8rem;
                color: #9ca3af;
            }
            @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .spinner {
                display: inline-block;
                width: 0.6rem;
                height: 0.6rem;
                border: 2px solid rgba(168, 85, 247, 0.3);
                border-top-color: rgba(168, 85, 247, 0.8);
                border-radius: 999px;
                animation: spin 1s linear infinite;
            }

            /* Training Status Indicator Styles */
            .training-status {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid rgba(56, 189, 248, 0.7);
                border-radius: 0.75rem;
                padding: 1rem;
                z-index: 1000;
                min-width: 300px;
                box-shadow:
                    0 14px 40px rgba(34, 197, 94, 0.2),
                    0 0 0 1px rgba(15, 23, 42, 0.7);
            }

            .training-progress-bar-container {
                width: 100%;
                height: 6px;
                background: rgba(55, 65, 81, 0.9);
                border-radius: 999px;
                margin-bottom: 0.5rem;
                overflow: hidden;
            }

            .training-progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #38bdf8, #818cf8);
                border-radius: 999px;
                transition: width 0.3s ease;
            }

            .training-progress-text {
                font-size: 0.8rem;
                color: #e5e7eb;
                text-align: center;
                min-height: 1.2rem;
            }
        </style>
    </head>
    <body>
        <main class="shell">
            <header class="header">
                <div class="title">
                    <div class="title-main">
                        <span>Adaptive Home Automations</span>
                        <span class="pill">.NET core · Python ML</span>
                    </div>
                    <div class="title-sub">
                        Intelligent habit-based home automation predictions
                    </div>
                </div>
                <div style="display:flex; gap:1.5rem; align-items:flex-start;">
                    <div style="text-align:right; font-size:0.75rem; color:#9ca3af;">
                        <div id="addon-version" style="margin-bottom:0.3rem;">версия: загрузка...</div>
                        <div id="addon-runtime" style="margin-bottom:0.3rem;">runtime: загрузка...</div>
                        <div id="addon-status" style="display:flex; align-items:center; gap:0.3rem; justify-content:flex-end;">
                            <span class="status-dot" id="addon-status-dot" aria-hidden="true"></span>
                            <span id="addon-status-text">online</span>
                        </div>
                    </div>
                </div>
            </header>
            <section class="body" style="display:block; padding:1.4rem 1.5rem;">
                <!-- Automation Suggestions Card -->
                <section class="card predictions-card" style="max-width:100%;">
                    <h2 style="margin-top:0;">💡 Automation Suggestions</h2>
                    <div style="margin-bottom:1rem; font-size:0.85rem; color:#9ca3af;">
                        Рекомендации по автоматизации на основе анализа паттернов поведения (корреляции и временные закономерности)
                    </div>
                    
            <div style="display:flex; gap:0.5rem; margin-bottom:1rem; flex-wrap:wrap;">
                <button id="suggestions-load-button" type="button" class="entities-button">🔄 Обновить</button>
                <button id="suggestions-train-button" type="button" class="primary-button">🚀 Анализировать историю</button>
                <button id="suggestions-train-advanced-button" type="button" class="primary-button">🤖 Расширенный анализ</button>
                <button id="suggestions-patterns-button" type="button" class="entities-button">📊 Показать паттерны</button>
            </div>

            <!-- Training Status Indicator -->
            <div id="training-status" class="training-status" style="display:none;">
                <div class="training-progress-bar-container">
                    <div class="training-progress-bar" id="training-progress-bar"></div>
                </div>
                <div class="training-progress-text" id="training-progress">Обучение...</div>
            </div>
                    
                    <div class="predictions-header" style="margin-bottom:1rem; padding:0.75rem; background:rgba(15,23,42,0.5); border-radius:0.5rem; border:1px solid rgba(55,65,81,0.5);">
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:0.75rem; font-size:0.75rem;">
                            <div>
                                <div style="color:#9ca3af; margin-bottom:0.2rem;">Статус анализа</div>
                                <div id="suggestions-status" style="color:#e5e7eb; font-weight:600;">Загрузка...</div>
                            </div>
                            <div>
                                <div style="color:#9ca3af; margin-bottom:0.2rem;">Образцов обработано</div>
                                <div id="suggestions-samples" style="color:#e5e7eb; font-weight:600;">-</div>
                            </div>
                            <div>
                                <div style="color:#9ca3af; margin-bottom:0.2rem;">Найдено предложений</div>
                                <div id="suggestions-count" style="color:#e5e7eb; font-weight:600;">-</div>
                            </div>
                            <div>
                                <div style="color:#9ca3af; margin-bottom:0.2rem;">Уникальных сущностей</div>
                                <div id="suggestions-entities" style="color:#e5e7eb; font-weight:600;">-</div>
                            </div>
                        </div>
                    </div>
                    
                    <div style="display:grid; grid-template-columns:minmax(0,3fr) minmax(0,1fr) minmax(0,1.2fr); gap:0.5rem; padding:0.5rem; margin-bottom:0.5rem; background:rgba(55,65,81,0.3); border-radius:0.3rem; font-size:0.75rem; font-weight:600; color:#9ca3af; text-transform:uppercase;">
                        <div>Описание</div>
                        <div>Тип</div>
                        <div text-align="center">Уверенность</div>
                    </div>
                    
                    <div id="suggestions-error" class="predictions-error" style="display:none; padding:0.5rem; margin-bottom:0.5rem;"></div>
                    <div id="suggestions-list" class="predictions-list" style="max-height:500px;">
                        <div class="predictions-loading">Анализируем историю...</div>
                    </div>
                </section>

                <!-- Temporal Patterns Card -->
                <section class="card entities-card" style="max-width:100%; margin-top:1.5rem;">
                    <h2 style="margin-top:0;">⏰ Temporal Patterns</h2>
                    <div style="margin-bottom:1rem; font-size:0.85rem; color:#9ca3af;">
                        Обнаруженные временные паттерны (действия в определённые часы/дни)
                    </div>
                    
                    <div style="display:grid; grid-template-columns:minmax(0,2fr) minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr); gap:0.5rem; padding:0.5rem; margin-bottom:0.5rem; background:rgba(55,65,81,0.3); border-radius:0.3rem; font-size:0.75rem; font-weight:600; color:#9ca3af; text-transform:uppercase;">
                        <div>Сущность → Состояние</div>
                        <div>Время</div>
                        <div>Дни</div>
                        <div>Консистентность</div>
                    </div>
                    
                    <div id="patterns-error" class="predictions-error" style="display:none; padding:0.5rem; margin-bottom:0.5rem;"></div>
                    <div id="patterns-list" class="predictions-list" style="max-height:300px;">
                        <div class="predictions-loading">Паттерны не обнаружены. Нажмите "Анализировать историю"</div>
                    </div>
                </section>
            </section>
        </main>
        <script>
            // Base path for ingress support
            const BASE_PATH = window.location.pathname.endsWith("/")
                ? window.location.pathname
                : window.location.pathname + "/";
            async function loadAddonHealth() {
                try {
                    const resp = await fetch(BASE_PATH + "health", { method: "GET" });
                    if (!resp.ok) {
                        document.getElementById("addon-status-text").textContent = "error";
                        document.getElementById("addon-status-dot").style.background = "#ef4444";
                        return;
                    }

                    const data = await resp.json();
                    document.getElementById("addon-version").textContent = "версия: " + (data.version ?? "0.1");
                    document.getElementById("addon-runtime").textContent = "runtime: " + (data.runtime ?? ".NET 8");
                    document.getElementById("addon-status-text").textContent = data.status ?? "ok";
                    document.getElementById("addon-status-dot").style.background = data.status === "ok" ? "#22c55e" : "#ef4444";
                } catch (err) {
                    document.getElementById("addon-status-text").textContent = "error";
                    document.getElementById("addon-status-dot").style.background = "#ef4444";
                }
            }

            let suggestionsSnapshot = { suggestions: [], statistics: {}, timestamp: "" };
            let patternsSnapshot = { patterns: [] };

            function renderSuggestions() {
                const list = document.getElementById("suggestions-list");
                const errorBox = document.getElementById("suggestions-error");
                if (!list || !errorBox) return;

                const suggestions = Array.isArray(suggestionsSnapshot.suggestions) ? suggestionsSnapshot.suggestions : [];
                const stats = suggestionsSnapshot.statistics || {};

                // Обновляем информационную панель
                document.getElementById("suggestions-count").textContent = suggestions.length + " шт.";
                document.getElementById("suggestions-samples").textContent = (stats.total_events_analyzed ?? 0) + " событий";
                document.getElementById("suggestions-entities").textContent = (stats.unique_entities ?? 0) + " сущностей";

                if (suggestionsSnapshot.timestamp) {
                    const ts = new Date(suggestionsSnapshot.timestamp);
                    const timeStr = ts.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
                    document.getElementById("suggestions-status").textContent = "✓ " + timeStr;
                }

                errorBox.style.display = "none";
                list.innerHTML = "";

                if (suggestions.length === 0) {
                    list.innerHTML = '<div class="predictions-loading">Нет рекомендаций. Нажмите "Анализировать историю"</div>';
                    return;
                }

                for (const sugg of suggestions) {
                    const confidence = (sugg.confidence * 100).toFixed(0) + "%";
                    const typeEmoji = sugg.trigger_type === "time" ? "⏰" : "📊";

                    const row = document.createElement("div");
                    row.style.cssText = "padding:0.6rem 0.5rem; border-bottom:1px solid rgba(31,41,55,0.9); cursor:pointer; transition:background 0.2s;";
                    row.onmouseover = () => row.style.background = "rgba(55,65,81,0.3)";
                    row.onmouseout = () => row.style.background = "transparent";

                    row.innerHTML =
                        '<div style="display:grid; grid-template-columns:minmax(0,3fr) minmax(0,1fr) minmax(0,1.2fr); gap:0.5rem; font-size:0.8rem;">' +
                        '<div style="color:#e5e7eb;"><strong>' + sugg.title + '</strong><br><span style="color:#9ca3af; font-size:0.75rem;">' + sugg.description + '</span></div>' +
                        '<div style="color:#a5b4fc;">' + typeEmoji + ' ' + sugg.trigger_type + '</div>' +
                        '<div style="color:#fbbf24; text-align:right; font-weight:600;">' + confidence + '</div>' +
                        '</div>' +
                        '<div style="margin-top:0.4rem; padding:0.4rem; background:rgba(15,23,42,0.9); border-radius:0.3rem; border:1px solid rgba(55,65,81,0.9); font-family:monospace; font-size:0.7rem; color:#38bdf8; max-height:0; overflow:hidden; transition:max-height 0.2s;" class="yaml-code">' +
                        sugg.automation_yaml.replace(/</g, "<").replace(/>/g, ">") +
                        '</div>';

                    row.addEventListener("click", () => {
                        const yaml = row.querySelector(".yaml-code");
                        const currentHeight = yaml.style.maxHeight;
                        yaml.style.maxHeight = currentHeight === "0px" || !currentHeight ? "400px" : "0px";
                    });

                    list.appendChild(row);
                }
            }

            function renderPatterns() {
                const list = document.getElementById("patterns-list");
                const errorBox = document.getElementById("patterns-error");
                if (!list || !errorBox) return;

                const patterns = Array.isArray(patternsSnapshot.patterns) ? patternsSnapshot.patterns : [];

                errorBox.style.display = "none";
                list.innerHTML = "";

                if (patterns.length === 0) {
                    list.innerHTML = '<div class="predictions-loading">Паттерны не обнаружены</div>';
                    return;
                }

                for (const pattern of patterns) {
                    const time = pattern.hour.toString().padStart(2, "0") + ":" + pattern.minute.toString().padStart(2, "0");
                    const days = (pattern.weekdays || []).map(d => ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"][d]).join(", ");
                    const consistency = (pattern.consistency * 100).toFixed(0) + "%";

                    const row = document.createElement("div");
                    row.className = "prediction-row";
                    row.style.gridTemplateColumns = "minmax(0,2fr) minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr)";
                    row.innerHTML =
                        '<div style="color:#e5e7eb;">' + pattern.entity_id + ' → <strong>' + pattern.target_state + '</strong></div>' +
                        '<div style="color:#38bdf8; font-weight:600;">' + time + '</div>' +
                        '<div style="color:#86efac;">' + days + '</div>' +
                        '<div style="color:#fbbf24; text-align:right;">' + consistency + '</div>';
                    list.appendChild(row);
                }
            }

            async function loadSuggestions() {
                const list = document.getElementById("suggestions-list");
                const errorBox = document.getElementById("suggestions-error");
                if (!list || !errorBox) return;

                try {
                    document.getElementById("suggestions-count").textContent = "загрузка...";
                    errorBox.style.display = "none";

                    const resp = await fetch(BASE_PATH + "api/automation-suggestions", { method: "GET" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        list.innerHTML = "";
                        return;
                    }

                    suggestionsSnapshot = await resp.json();
                    renderSuggestions();
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                    list.innerHTML = "";
                }
            }

            async function loadPatterns() {
                const list = document.getElementById("patterns-list");
                const errorBox = document.getElementById("patterns-error");
                if (!list || !errorBox) return;

                try {
                    list.innerHTML = '<div class="predictions-loading">Загрузка паттернов...</div>';
                    errorBox.style.display = "none";

                    const resp = await fetch(BASE_PATH + "api/patterns", { method: "GET" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        list.innerHTML = "";
                        return;
                    }

                    patternsSnapshot = await resp.json();
                    renderPatterns();
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                    list.innerHTML = "";
                }
            }

            async function trainAndAnalyze() {
                const trainButton = document.getElementById("suggestions-train-button");
                const errorBox = document.getElementById("suggestions-error");
                if (!trainButton || !errorBox) return;

                try {
                    trainButton.disabled = true;
                    trainButton.textContent = "🔄 Анализирование...";
                    errorBox.style.display = "none";

                    const resp = await fetch(BASE_PATH + "api/train", { method: "POST" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        trainButton.textContent = "🚀 Анализировать историю";
                        trainButton.disabled = false;
                        return;
                    }

                    const data = await resp.json();
                    if (data.status === "ok") {
                        // Загружаем рекомендации и паттерны
                        await loadSuggestions();
                        await loadPatterns();
                    } else {
                        errorBox.style.display = "block";
                        errorBox.textContent = "Analysis failed: " + JSON.stringify(data);
                    }
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                } finally {
                    trainButton.textContent = "🚀 Анализировать историю";
                    trainButton.disabled = false;
                }
            }

            async function trainAdvanced() {
                const trainButton = document.getElementById("suggestions-train-advanced-button");
                const errorBox = document.getElementById("suggestions-error");
                if (!trainButton || !errorBox) return;

                try {
                    trainButton.disabled = true;
                    trainButton.textContent = "🔄 Анализирование...";
                    errorBox.style.display = "none";

                    const resp = await fetch(BASE_PATH + "api/train-advanced", { method: "POST" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        trainButton.textContent = "🤖 Расширенный анализ";
                        trainButton.disabled = false;
                        return;
                    }

                    const data = await resp.json();
                    if (data.status === "ok") {
                        // Загружаем рекомендации и паттерны
                        await loadSuggestions();
                        await loadPatterns();
                    } else {
                        errorBox.style.display = "block";
                        errorBox.textContent = "Advanced analysis failed: " + JSON.stringify(data);
                    }
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                } finally {
                    trainButton.textContent = "🤖 Расширенный анализ";
                    trainButton.disabled = false;
                }
            }

            // Function to poll training status
            async function pollTrainingStatus() {
                try {
                    const resp = await fetch(BASE_PATH + "api/config");
                    if (!resp.ok) {
                        return;
                    }

                    const config = await resp.json();
                    const trainingStatus = document.getElementById("training-status");
                    const progressBar = document.getElementById("training-progress-bar");
                    const progressText = document.getElementById("training-progress");

                    if (!trainingStatus || !progressBar || !progressText) return;

                    if (config.training_in_progress) {
                        // Show training indicator
                        trainingStatus.style.display = "block";
                        progressBar.style.width = `${config.training_progress}%`;
                        progressText.textContent = `${config.training_status} (${config.training_progress}%)`;

                        // Update step if available
                        if (config.training_step) {
                            progressText.textContent = `${config.training_step}: ${config.training_status} (${config.training_progress}%)`;
                        }
                    } else {
                        // Hide training indicator if training is not in progress
                        trainingStatus.style.display = "none";
                    }
                } catch (err) {
                    console.error("Error polling training status:", err);
                }
            }

            // Function to update training functions to show initial status
            async function trainAndAnalyze() {
                const trainButton = document.getElementById("suggestions-train-button");
                const errorBox = document.getElementById("suggestions-error");
                if (!trainButton || !errorBox) return;

                try {
                    trainButton.disabled = true;
                    trainButton.textContent = "🔄 Анализирование...";
                    errorBox.style.display = "none";

                    // Show training indicator immediately
                    const trainingStatus = document.getElementById("training-status");
                    if (trainingStatus) {
                        trainingStatus.style.display = "block";
                        document.getElementById("training-progress").textContent = "Запуск обучения...";
                        document.getElementById("training-progress-bar").style.width = "0%";
                    }

                    const resp = await fetch(BASE_PATH + "api/train", { method: "POST" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        trainButton.textContent = "🚀 Анализировать историю";
                        trainButton.disabled = false;
                        return;
                    }

                    const data = await resp.json();
                    if (data.status === "ok") {
                        // Загружаем рекомендации и паттерны
                        await loadSuggestions();
                        await loadPatterns();
                    } else {
                        errorBox.style.display = "block";
                        errorBox.textContent = "Analysis failed: " + JSON.stringify(data);
                    }
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                } finally {
                    trainButton.textContent = "🚀 Анализировать историю";
                    trainButton.disabled = false;
                }
            }

            async function trainAdvanced() {
                const trainButton = document.getElementById("suggestions-train-advanced-button");
                const errorBox = document.getElementById("suggestions-error");
                if (!trainButton || !errorBox) return;

                try {
                    trainButton.disabled = true;
                    trainButton.textContent = "🔄 Анализирование...";
                    errorBox.style.display = "none";

                    // Show training indicator immediately
                    const trainingStatus = document.getElementById("training-status");
                    if (trainingStatus) {
                        trainingStatus.style.display = "block";
                        document.getElementById("training-progress").textContent = "Запуск расширенного обучения...";
                        document.getElementById("training-progress-bar").style.width = "0%";
                    }

                    const resp = await fetch(BASE_PATH + "api/train-advanced", { method: "POST" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed: " + resp.status + " " + text;
                        trainButton.textContent = "🤖 Расширенный анализ";
                        trainButton.disabled = false;
                        return;
                    }

                    const data = await resp.json();
                    if (data.status === "ok") {
                        // Загружаем рекомендации и паттерны
                        await loadSuggestions();
                        await loadPatterns();
                    } else {
                        errorBox.style.display = "block";
                        errorBox.textContent = "Advanced analysis failed: " + JSON.stringify(data);
                    }
                } catch (err) {
                    errorBox.style.display = "block";
                    errorBox.textContent = "Error: " + err;
                } finally {
                    trainButton.textContent = "🤖 Расширенный анализ";
                    trainButton.disabled = false;
                }
            }

            document.addEventListener("DOMContentLoaded", () => {
                const suggestionsLoadBtn = document.getElementById("suggestions-load-button");
                const suggestionsTrainBtn = document.getElementById("suggestions-train-button");
                const suggestionsTrainAdvancedBtn = document.getElementById("suggestions-train-advanced-button");
                const suggestionsPatternsBtn = document.getElementById("suggestions-patterns-button");

                if (suggestionsLoadBtn) {
                    suggestionsLoadBtn.addEventListener("click", loadSuggestions);
                }

                if (suggestionsTrainBtn) {
                    suggestionsTrainBtn.addEventListener("click", trainAndAnalyze);
                }

                if (suggestionsTrainAdvancedBtn) {
                    suggestionsTrainAdvancedBtn.addEventListener("click", trainAdvanced);
                }

                if (suggestionsPatternsBtn) {
                    suggestionsPatternsBtn.addEventListener("click", () => {
                        const patternsCard = document.querySelector(".entities-card");
                        if (patternsCard) {
                            patternsCard.scrollIntoView({ behavior: "smooth" });
                            loadPatterns();
                        }
                    });
                }

                loadAddonHealth();
                // Автообновление здоровья аддона каждые 30 секунд
                setInterval(loadAddonHealth, 30000);

                // Автозагрузка рекомендаций при загрузке страницы
                loadSuggestions();

                // Start polling training status every 2 seconds
                setInterval(pollTrainingStatus, 2000);
            });
    </body>
    </html>
    """;

    await context.Response.WriteAsync(html);
});

// Простейший health-check для интеграции с HA / отладки
app.MapGet("/health", () => Results.Json(new { 
    status = "ok", 
    runtime = ".NET 8",
    version = "0.1.10",
    source = "diploma-addon",
    python_service = "http://127.0.0.1:5000",
    timestamp = DateTime.UtcNow.ToString("o")
}));

// API-эндпоинт для чтения сущностей Home Assistant через Supervisor API
// Логически соответствует /api/states из REST API Home Assistant, но возвращает сжатый список состояний
// GET /api/states?domain=light&limit=50
app.MapGet("/api/states", async (IHttpClientFactory httpClientFactory, string? domain, int? limit) =>
{
    var client = httpClientFactory.CreateClient("hass");

    // Если токен не был установлен, вернём понятную ошибку
    if (client.DefaultRequestHeaders.Authorization is null)
    {
        return Results.Json(
            new
            {
                error = "SUPERVISOR_TOKEN is not configured",
                hint = "Ensure the addon has homeassistant_api/hassio_api enabled and runs under Supervisor."
            },
            statusCode: StatusCodes.Status500InternalServerError
        );
    }

    try
    {
        using var response = await client.GetAsync("states");
        var body = await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            return Results.Json(
                new
                {
                    error = "Failed to query Home Assistant API",
                    status = (int)response.StatusCode,
                    body
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        using var doc = JsonDocument.Parse(body);
        var raw = new List<(string EntityId, string? State, string Domain, string? FriendlyName)>();

        foreach (var element in doc.RootElement.EnumerateArray())
        {
            if (!element.TryGetProperty("entity_id", out var entityIdProp) ||
                entityIdProp.ValueKind != JsonValueKind.String)
            {
                continue;
            }

            var entityId = entityIdProp.GetString() ?? string.Empty;
            if (string.IsNullOrWhiteSpace(entityId))
            {
                continue;
            }

            var dotIndex = entityId.IndexOf('.');
            var entityDomain = dotIndex > 0 ? entityId[..dotIndex] : "other";

            string? state = null;
            if (element.TryGetProperty("state", out var stateProp) &&
                stateProp.ValueKind == JsonValueKind.String)
            {
                state = stateProp.GetString();
            }

            string? friendlyName = null;
            if (element.TryGetProperty("attributes", out var attrsProp) &&
                attrsProp.ValueKind == JsonValueKind.Object &&
                attrsProp.TryGetProperty("friendly_name", out var fnProp) &&
                fnProp.ValueKind == JsonValueKind.String)
            {
                friendlyName = fnProp.GetString();
            }

            raw.Add((entityId, state, entityDomain, friendlyName));
        }

        // Фильтрация по домену (если указан)
        IEnumerable<(string EntityId, string? State, string Domain, string? FriendlyName)> filtered = raw;
        if (!string.IsNullOrWhiteSpace(domain) && !string.Equals(domain, "all", StringComparison.OrdinalIgnoreCase))
        {
            filtered = filtered.Where(e => string.Equals(e.Domain, domain, StringComparison.OrdinalIgnoreCase));
        }

        var filteredList = filtered.ToList();
        var total = filteredList.Count;

        var effectiveLimit = limit.HasValue && limit.Value > 0
            ? Math.Min(limit.Value, 200)
            : 50;

        var limitedItems = filteredList
            .OrderBy(e => e.Domain)
            .ThenBy(e => e.EntityId)
            .Take(effectiveLimit)
            .Select(e => new
            {
                entity_id = e.EntityId,
                state = e.State,
                domain = e.Domain,
                friendly_name = e.FriendlyName
            })
            .ToList();

        return Results.Json(new
        {
            total,
            limit = effectiveLimit,
            items = limitedItems
        });
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Home Assistant API",
                message = ex.Message
            },
            statusCode: StatusCodes.Status500InternalServerError
        );
    }
});

// Proxy endpoint to trigger training on the Python service
app.MapPost("/api/train", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");

        using var response = await pythonClient.PostAsync("api/train",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to trigger training on Python service",
                    status = (int)response.StatusCode,
                    details = errorBody
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        var doc = JsonDocument.Parse(content);
        return Results.Json(doc.RootElement);
    }
    catch (HttpRequestException ex)
    {
        return Results.Json(
            new
            {
                error = "Failed to connect to Python service",
                message = ex.Message,
                hint = "Ensure Python Flask service is running and PYTHON_API_URL is configured"
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python training service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status500InternalServerError
        );
    }
});

// Proxy endpoint для получения рекомендаций по автоматизации из Python сервиса
app.MapGet("/api/automation-suggestions", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        using var response = await pythonClient.GetAsync("api/automation-suggestions");
        
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new { error = "Failed to get suggestions", status = (int)response.StatusCode },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        return Results.Content(content, "application/json");
    }
    catch (Exception ex)
    {
        return Results.Json(
            new { error = ex.Message },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
});

// Proxy endpoint для получения обнаруженных паттернов
app.MapGet("/api/patterns", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        using var response = await pythonClient.GetAsync("api/patterns");

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to get patterns",
                    status = (int)response.StatusCode
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        return Results.Content(content, "application/json");
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python patterns service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
});

// Proxy endpoint для анализа временных рядов
app.MapPost("/api/time-series/analyze", async (IHttpClientFactory httpClientFactory, HttpRequest request) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        var content = await new StreamReader(request.Body).ReadToEndAsync();

        using var response = await pythonClient.PostAsync("api/time-series/analyze",
            new StringContent(content, System.Text.Encoding.UTF8, "application/json"));

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to analyze time series",
                    status = (int)response.StatusCode,
                    details = errorBody
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        return Results.Content(responseContent, "application/json");
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python time series analysis service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
});

// Proxy endpoint для получения предложений на основе временных рядов
app.MapPost("/api/time-series/suggestions", async (IHttpClientFactory httpClientFactory, HttpRequest request) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        var content = await new StreamReader(request.Body).ReadToEndAsync();

        using var response = await pythonClient.PostAsync("api/time-series/suggestions",
            new StringContent(content, System.Text.Encoding.UTF8, "application/json"));

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to get time series suggestions",
                    status = (int)response.StatusCode,
                    details = errorBody
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        return Results.Content(responseContent, "application/json");
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python time series suggestions service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
});

// Proxy endpoint для получения информации о моделях временных рядов
app.MapGet("/api/time-series/models", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        using var response = await pythonClient.GetAsync("api/time-series/models");

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to get time series models info",
                    status = (int)response.StatusCode
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        return Results.Content(content, "application/json");
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python time series models service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
});

// Proxy endpoint для запуска расширенного обучения (корреляции + временные ряды)
app.MapPost("/api/train-advanced", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");

        using var response = await pythonClient.PostAsync("api/train-advanced",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to trigger advanced training on Python service",
                    status = (int)response.StatusCode,
                    details = errorBody
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        var doc = JsonDocument.Parse(content);
        return Results.Json(doc.RootElement);
    }
    catch (HttpRequestException ex)
    {
        return Results.Json(
            new
            {
                error = "Failed to connect to Python service",
                message = ex.Message,
                hint = "Ensure Python Flask service is running and PYTHON_API_URL is configured"
            },
            statusCode: StatusCodes.Status503ServiceUnavailable
        );
    }
    catch (Exception ex)
    {
        return Results.Json(
            new
            {
                error = "Exception while calling Python advanced training service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status500InternalServerError
        );
    }
});

// Явно привязываемся к порту 8080, который уже прокинут в addon config.yaml
app.Run("http://0.0.0.0:8080");



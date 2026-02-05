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
        </style>
    </head>
    <body>
        <main class="shell">
            <header class="header">
                <div class="title">
                    <div class="title-main">
                        <span>Adaptive Home Automations</span>
                        <span class="pill">.NET core · prototype</span>
                    </div>
                    <div class="title-sub">
                        Home Assistant addon shell for intelligent habit-based automations
                    </div>
                </div>
                <div class="status-row">
                    <span class="status-dot" aria-hidden="true"></span>
                    <span>Service online</span>
                </div>
            </header>
            <section class="body">
                <section class="card">
                    <h2>Addon state</h2>
                    <div class="hero-title">
                        Runtime and health
                    </div>
                    <p class="hero-text">
                        This block reflects the current state of the addon runtime and basic configuration.
                        In the future it can include model status, last analysis timestamps and diagnostic
                        information useful for debugging automations.
                    </p>
                    <div class="chips">
                        <span class="chip">.NET 8</span>
                        <span class="chip">Home Assistant Supervisor API</span>
                        <span class="chip">Python models (planned)</span>
                    </div>
                    <div class="timeline" id="addon-health">
                        <div style="font-size:0.8rem; color:#6b7280;">
                            Loading addon health from <code>/health</code>…
                        </div>
                    </div>
                </section>
                <section class="card right-card">
                    <h2>Home Assistant entities</h2>
                    <div class="card entities-card">
                        <div class="entities-header">
                            <h3 style="margin:0; font-size:0.85rem; letter-spacing:0.03em; text-transform:uppercase; color:#9ca3af;">
                                Entities snapshot
                            </h3>
                            <div style="display:flex; align-items:center; gap:0.5rem;">
                                <button id="entities-load-button" type="button" class="entities-button">Отобразить сущности</button>
                                <span id="entities-count" class="entities-badge">idle</span>
                            </div>
                        </div>
                        <div id="entities-error" class="entities-error" style="display:none;"></div>
                        <div id="entities-list" class="entities-list">
                            <div style="font-size:0.8rem; color:#6b7280;">Нажмите &laquo;Отобразить сущности&raquo;, чтобы загрузить данные из Home Assistant.</div>
                        </div>
                    </div>
                </section>
                <section class="card predictions-card">
                    <h2>ML Predictions</h2>
                    <div class="card predictions-card">
                        <div class="predictions-header">
                            <h3 style="margin:0; font-size:0.85rem; letter-spacing:0.03em; text-transform:uppercase; color:#9ca3af;">
                                Predicted actions <span style="font-size:0.7rem; color:#6b7280;">(обновляется каждые 30 сек)</span>
                            </h3>
                            <div style="display:flex; align-items:center; gap:0.5rem;">
                                <button id="predictions-load-button" type="button" class="entities-button">Обновить сейчас</button>
                                <span id="predictions-count" class="predictions-badge">idle</span>
                            </div>
                        </div>
                        <div id="predictions-error" class="predictions-error" style="display:none;"></div>
                        <div id="predictions-list" class="predictions-list">
                            <div class="predictions-loading">Анализируем историю...</div>
                        </div>
                    </div>
                </section>
            </section>
        </main>
        <script>
            async function loadAddonHealth() {
                const container = document.getElementById("addon-health");
                if (!container) return;

                try {
                    const resp = await fetch("./health", { method: "GET" });
                    if (!resp.ok) {
                        container.innerHTML = "<div style='font-size:0.8rem; color:#fecaca;'>Failed to load health: " +
                            resp.status + " " + resp.statusText + "</div>";
                        return;
                    }

                    const data = await resp.json();
                    container.innerHTML = "";

                    const grid = document.createElement("div");
                    grid.style.display = "grid";
                    grid.style.gridTemplateColumns = "minmax(0, 1.1fr) minmax(0, 1.2fr)";
                    grid.style.gap = "0.4rem 0.8rem";

                    const items = [
                        ["status", data.status ?? "unknown"],
                        ["runtime", data.runtime ?? "(none)"],
                        ["source", data.source ?? "(unknown)"],
                    ];

                    for (const [label, value] of items) {
                        const k = document.createElement("div");
                        k.style.color = "#9ca3af";
                        k.style.fontSize = "0.78rem";
                        k.textContent = label;

                        const v = document.createElement("div");
                        v.style.color = "#e5e7eb";
                        v.style.fontSize = "0.85rem";
                        v.textContent = String(value);

                        grid.appendChild(k);
                        grid.appendChild(v);
                    }

                    container.appendChild(grid);
                } catch (err) {
                    container.innerHTML = "<div style='font-size:0.8rem; color:#fecaca;'>Exception while loading health: " +
                        err + "</div>";
                }
            }

            let entitiesSnapshot = { total: 0, limit: 0, items: [] };

            function renderEntities() {
                const list = document.getElementById("entities-list");
                const countBadge = document.getElementById("entities-count");
                const errorBox = document.getElementById("entities-error");
                if (!list || !countBadge || !errorBox) return;

                const items = Array.isArray(entitiesSnapshot.items) ? entitiesSnapshot.items : [];
                const total = typeof entitiesSnapshot.total === "number" ? entitiesSnapshot.total : items.length;

                countBadge.textContent = items.length + " / " + total;
                errorBox.style.display = "none";
                list.innerHTML = "";

                for (const st of items) {
                    const entityId = st.entity_id || "(unknown)";
                    const domain = st.domain || (entityId.includes(".") ? entityId.split(".")[0] : "other");
                    const state = st.state ?? "";

                    const row = document.createElement("div");
                    row.className = "entity-row";
                    row.innerHTML =
                        '<div class="entity-id">' + entityId + '</div>' +
                        '<div class="entity-domain">' + domain + '</div>' +
                        '<div class="entity-state">' + state + '</div>';
                    list.appendChild(row);
                }
            }

            async function loadEntities() {
                const list = document.getElementById("entities-list");
                const countBadge = document.getElementById("entities-count");
                const errorBox = document.getElementById("entities-error");
                if (!list || !countBadge || !errorBox) return;

                try {
                    const params = new URLSearchParams();
                    params.set("limit", "1000");

                    const resp = await fetch("./api/states?" + params.toString(), { method: "GET" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        countBadge.textContent = "error";
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed to load entities: " + resp.status + " " + text;
                        list.innerHTML = "";
                        return;
                    }

                    const data = await resp.json();
                    if (!data || !Array.isArray(data.items)) {
                        countBadge.textContent = "0";
                        errorBox.style.display = "block";
                        errorBox.textContent = "Unexpected response format from Home Assistant API.";
                        list.innerHTML = "";
                        return;
                    }

                    entitiesSnapshot = data;
                    renderEntities();
                } catch (err) {
                    countBadge.textContent = "error";
                    errorBox.style.display = "block";
                    errorBox.textContent = "Exception while loading entities: " + err;
                    list.innerHTML = "";
                }
            }

            let predictionsSnapshot = { predictions: [], timestamp: "", total_predictions: 0 };

            function renderPredictions() {
                const list = document.getElementById("predictions-list");
                const countBadge = document.getElementById("predictions-count");
                const errorBox = document.getElementById("predictions-error");
                if (!list || !countBadge || !errorBox) return;

                const predictions = Array.isArray(predictionsSnapshot.predictions) ? predictionsSnapshot.predictions : [];
                const total = predictionsSnapshot.total_predictions ?? predictions.length;

                countBadge.textContent = total + " действий";
                errorBox.style.display = "none";
                list.innerHTML = "";

                // Показываем информацию об обновлении
                if (predictionsSnapshot.timestamp) {
                    const ts = new Date(predictionsSnapshot.timestamp);
                    const timeStr = ts.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                    const infoDiv = document.createElement("div");
                    infoDiv.style.fontSize = "0.75rem";
                    infoDiv.style.color = "#9ca3af";
                    infoDiv.style.marginBottom = "0.5rem";
                    infoDiv.style.paddingBottom = "0.5rem";
                    infoDiv.style.borderBottom = "1px solid rgba(55, 65, 81, 0.5)";
                    infoDiv.textContent = "⏰ Обновлено в " + timeStr + " | Вероятность выше 40%";
                    list.appendChild(infoDiv);
                }

                if (predictions.length === 0) {
                    list.innerHTML += '<div class="predictions-loading">Нет предсказаний для текущего времени</div>';
                    return;
                }

                for (const pred of predictions) {
                    const entityId = pred.entity_id || "(unknown)";
                    const probability = (pred.probability * 100).toFixed(1) + "%";
                    const support = pred.support ?? "?";

                    const row = document.createElement("div");
                    row.className = "prediction-row";
                    row.innerHTML =
                        '<div class="prediction-entity">' + entityId + '</div>' +
                        '<div class="prediction-probability">' + probability + '</div>' +
                        '<div class="prediction-support">' + support + '</div>';
                    list.appendChild(row);
                }
            }

            async function loadPredictions() {
                const list = document.getElementById("predictions-list");
                const countBadge = document.getElementById("predictions-count");
                const errorBox = document.getElementById("predictions-error");
                if (!list || !countBadge || !errorBox) return;

                try {
                    // Показываем индикатор загрузки
                    const spinner = '<span class="spinner" style="margin-right:0.4rem;"></span>';
                    countBadge.innerHTML = spinner + 'загрузка...';
                    errorBox.style.display = "none";

                    const resp = await fetch("./api/predictions", { method: "POST" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        countBadge.textContent = "error";
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed to load predictions: " + resp.status + " " + text;
                        list.innerHTML = "";
                        return;
                    }

                    const data = await resp.json();
                    predictionsSnapshot = data;
                    renderPredictions();
                } catch (err) {
                    countBadge.textContent = "error";
                    errorBox.style.display = "block";
                    errorBox.textContent = "Exception while loading predictions: " + err;
                    list.innerHTML = "";
                }
            }

            document.addEventListener("DOMContentLoaded", () => {
                const loadButton = document.getElementById("entities-load-button");
                const predictionsButton = document.getElementById("predictions-load-button");

                if (loadButton) {
                    loadButton.addEventListener("click", () => loadEntities());
                }

                if (predictionsButton) {
                    predictionsButton.addEventListener("click", () => loadPredictions());
                }

                loadAddonHealth();
                // автообновление состояния аддона раз в минуту
                setInterval(loadAddonHealth, 60000);

                // Автозагрузка predictions при загрузке страницы
                loadPredictions();

                // Автообновление predictions каждые 30 секунд (в реальном времени)
                setInterval(loadPredictions, 30000);
            });
        </script>
    </body>
    </html>
    """;

    await context.Response.WriteAsync(html);
});

// Простейший health-check для интеграции с HA / отладки
app.MapGet("/health", () => Results.Json(new { status = "ok", runtime = ".NET 8", source = "diploma-addon" }));

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

// API-эндпоинт для получения предсказаний из Python ML модели
// POST /api/predictions - вызывает Python модель для анализа истории и предсказания действий
app.MapPost("/api/predictions", async (IHttpClientFactory httpClientFactory) =>
{
    try
    {
        var pythonClient = httpClientFactory.CreateClient("python");
        
        // Вызываем Python endpoint для получения предсказаний
        using var response = await pythonClient.PostAsync("api/predictions", 
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));
        
        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync();
            return Results.Json(
                new
                {
                    error = "Failed to get predictions from Python service",
                    status = (int)response.StatusCode,
                    details = errorBody
                },
                statusCode: StatusCodes.Status502BadGateway
            );
        }

        var content = await response.Content.ReadAsStringAsync();
        var predictions = JsonDocument.Parse(content);
        
        return Results.Json(predictions.RootElement);
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
                error = "Exception while calling Python predictions service",
                message = ex.Message
            },
            statusCode: StatusCodes.Status500InternalServerError
        );
    }
});

// Явно привязываемся к порту 8080, который уже прокинут в addon config.yaml
app.Run("http://0.0.0.0:8080");


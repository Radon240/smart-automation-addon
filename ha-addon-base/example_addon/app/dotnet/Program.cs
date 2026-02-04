using System.Net.Http.Headers;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var builder = WebApplication.CreateBuilder(args);

// HttpClient для общения с Home Assistant Supervisor API
builder.Services.AddHttpClient("hass", client =>
{
    var baseUrl = Environment.GetEnvironmentVariable("SUPERVISOR_API_URL")
                  ?? "http://supervisor/core/api";
    var token = Environment.GetEnvironmentVariable("SUPERVISOR_TOKEN");

    client.BaseAddress = new Uri(baseUrl);
    if (!string.IsNullOrWhiteSpace(token))
    {
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
    }
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
                grid-template-columns: minmax(0, 3fr) minmax(0, 2.2fr);
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
            .timeline-item {
                display: flex;
                gap: 0.65rem;
                padding: 0.3rem 0;
            }
            .timeline-time {
                width: 3.4rem;
                color: #6b7280;
            }
            .timeline-body {
                flex: 1;
            }
            .timeline-title {
                color: #e5e7eb;
                margin-bottom: 0.1rem;
            }
            .timeline-meta {
                color: #9ca3af;
            }
            .entities-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.4rem;
            }
            .entities-controls {
                display: flex;
                align-items: center;
                gap: 0.4rem;
                flex-wrap: wrap;
                justify-content: flex-end;
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
            .entities-select {
                background: rgba(15, 23, 42, 0.95);
                border-radius: 999px;
                border: 1px solid rgba(75, 85, 99, 0.9);
                color: #e5e7eb;
                font-size: 0.75rem;
                padding: 0.2rem 0.6rem;
            }
            .view-toggle {
                background: rgba(15, 23, 42, 0.95);
                border-radius: 999px;
                border: 1px solid rgba(55, 65, 81, 0.9);
                color: #9ca3af;
                font-size: 0.75rem;
                padding: 0.15rem 0.6rem;
                cursor: pointer;
            }
            .view-toggle-active {
                color: #e5e7eb;
                border-color: rgba(129, 140, 248, 0.9);
                background: rgba(30, 64, 175, 0.5);
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
                    <h2>Overview</h2>
                    <div class="hero-title">
                        Adaptive <span class="hero-accent">suggestions</span> for your everyday routines
                    </div>
                    <p class="hero-text">
                        This .NET service runs inside a Home Assistant addon and will later connect to
                        Python models to analyse event history and detect user habits. For now, this
                        page is a static prototype UI to validate the integration and layout.
                    </p>
                    <div class="chips">
                        <span class="chip">Home Assistant ingress</span>
                        <span class="chip">.NET 8 minimal API</span>
                        <span class="chip">Python models (planned)</span>
                        <span class="chip">Habit mining</span>
                    </div>
                    <button class="primary-button" type="button">
                        <span>⟳</span>
                        <span>Simulate pattern scan</span>
                    </button>
                    <span class="secondary-info">
                        In the next step this will trigger a real analysis of Home Assistant events.
                    </span>
                </section>
                <section class="card right-card">
                    <h2>Prototype status</h2>
                    <div class="metric-row">
                        <div class="metric-label">
                            <span class="metric-dot"></span>
                            <span>.NET web shell</span>
                        </div>
                        <span class="metric-value">Running</span>
                    </div>
                    <div class="metric-row">
                        <div class="metric-label">
                            <span class="metric-dot" style="background:#22c55e;"></span>
                            <span>Addon ingress</span>
                        </div>
                        <span class="metric-value">Configured</span>
                    </div>
                    <div class="metric-row">
                        <div class="metric-label">
                            <span class="metric-dot" style="background:#f59e0b;"></span>
                            <span>Python models</span>
                        </div>
                        <span class="metric-value">Planned</span>
                    </div>
                    <div class="timeline">
                        <div class="timeline-item">
                            <div class="timeline-time">Step 1</div>
                            <div class="timeline-body">
                                <div class="timeline-title">Base .NET addon UI</div>
                                <div class="timeline-meta">You are here — container + minimal web UI.</div>
                            </div>
                        </div>
                        <div class="timeline-item">
                            <div class="timeline-time">Step 2</div>
                            <div class="timeline-body">
                                <div class="timeline-title">Connect to HA events</div>
                                <div class="timeline-meta">Use Supervisor API to read history &amp; state.</div>
                            </div>
                        </div>
                        <div class="timeline-item">
                            <div class="timeline-time">Step 3</div>
                            <div class="timeline-body">
                                <div class="timeline-title">Python habit model</div>
                                <div class="timeline-meta">Delegate pattern mining to Python services.</div>
                            </div>
                        </div>
                        <div class="timeline-item">
                            <div class="timeline-time">Step 4</div>
                            <div class="timeline-body">
                                <div class="timeline-title">Automation suggestions</div>
                                <div class="timeline-meta">Render concrete Home Assistant automations and let the user approve them.</div>
                            </div>
                        </div>
                    </div>
                    <p style="margin-top:0.8rem; font-size:0.78rem; color:#9ca3af;">
                        Health endpoint: <code>/health</code> (JSON). Use it from Home Assistant or scripts to confirm that the addon is online.
                    </p>
                    <div class="card entities-card">
                        <div class="entities-header">
                            <h2 style="margin:0; font-size:0.9rem; letter-spacing:0.03em; text-transform:uppercase; color:#9ca3af;">
                                Home Assistant entities
                            </h2>
                            <div class="entities-controls">
                                <select id="entities-domain" class="entities-select">
                                    <option value="all">All domains</option>
                                    <option value="light">light</option>
                                    <option value="sensor">sensor</option>
                                    <option value="switch">switch</option>
                                    <option value="binary_sensor">binary_sensor</option>
                                    <option value="climate">climate</option>
                                </select>
                                <button id="entities-view-toggle" type="button" class="view-toggle view-toggle-active">Compact</button>
                                <span id="entities-count" class="entities-badge">loading…</span>
                            </div>
                        </div>
                        <div id="entities-error" class="entities-error" style="display:none;"></div>
                        <div id="entities-list" class="entities-list">
                            <div style="font-size:0.8rem; color:#6b7280;">Loading entities from Home Assistant API…</div>
                        </div>
                    </div>
                </section>
            </section>
        </main>
        <script>
            let allEntities = [];
            let viewMode = "compact";

            function renderEntities() {
                const list = document.getElementById("entities-list");
                const countBadge = document.getElementById("entities-count");
                const errorBox = document.getElementById("entities-error");
                const domainSelect = document.getElementById("entities-domain");
                const toggleBtn = document.getElementById("entities-view-toggle");
                if (!list || !countBadge || !errorBox || !domainSelect || !toggleBtn) return;

                const selectedDomain = domainSelect.value || "all";
                const filtered = allEntities.filter(st => {
                    const entityId = st.entity_id || "";
                    const domain = entityId.includes(".") ? entityId.split(".")[0] : "other";
                    return selectedDomain === "all" || domain === selectedDomain;
                });

                const maxItems = 25;
                const items = filtered.slice(0, maxItems);
                countBadge.textContent = items.length + " / " + allEntities.length;
                errorBox.style.display = "none";
                list.innerHTML = "";

                if (viewMode === "json") {
                    const pre = document.createElement("pre");
                    pre.style.fontSize = "0.75rem";
                    pre.textContent = JSON.stringify(items, null, 2);
                    list.appendChild(pre);
                } else {
                    for (const st of items) {
                        const entityId = st.entity_id || "(unknown)";
                        const domain = entityId.includes(".") ? entityId.split(".")[0] : "other";
                        const state = st.state ?? "";

                        const row = document.createElement("div");
                        row.className = "entity-row";
                        row.innerHTML =
                            "<div class=\\"entity-id\\">" + entityId + "</div>" +
                            "<div class=\\"entity-domain\\">" + domain + "</div>" +
                            "<div class=\\"entity-state\\">" + state + "</div>";
                        list.appendChild(row);
                    }
                }

                if (viewMode === "json") {
                    toggleBtn.textContent = "JSON";
                    toggleBtn.classList.add("view-toggle-active");
                } else {
                    toggleBtn.textContent = "Compact";
                    toggleBtn.classList.add("view-toggle-active");
                }
            }

            async function loadEntities() {
                const list = document.getElementById("entities-list");
                const countBadge = document.getElementById("entities-count");
                const errorBox = document.getElementById("entities-error");
                if (!list || !countBadge || !errorBox) return;

                try {
                    const resp = await fetch("./api/entities", { method: "GET" });
                    if (!resp.ok) {
                        const text = await resp.text();
                        countBadge.textContent = "error";
                        errorBox.style.display = "block";
                        errorBox.textContent = "Failed to load entities: " + resp.status + " " + text;
                        list.innerHTML = "";
                        return;
                    }

                    const data = await resp.json();
                    if (!Array.isArray(data)) {
                        countBadge.textContent = "0";
                        errorBox.style.display = "block";
                        errorBox.textContent = "Unexpected response format from Home Assistant API.";
                        list.innerHTML = "";
                        return;
                    }

                    allEntities = data;
                    renderEntities();
                } catch (err) {
                    countBadge.textContent = "error";
                    errorBox.style.display = "block";
                    errorBox.textContent = "Exception while loading entities: " + err;
                    list.innerHTML = "";
                }
            }

            document.addEventListener("DOMContentLoaded", () => {
                const domainSelect = document.getElementById("entities-domain");
                const toggleBtn = document.getElementById("entities-view-toggle");

                if (domainSelect) {
                    domainSelect.addEventListener("change", () => renderEntities());
                }

                if (toggleBtn) {
                    toggleBtn.addEventListener("click", () => {
                        viewMode = viewMode === "compact" ? "json" : "compact";
                        renderEntities();
                    });
                }

                loadEntities();
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
// GET /api/entities -> проксирует запрос к /states и возвращает JSON как есть
app.MapGet("/api/entities", async (IHttpClientFactory httpClientFactory) =>
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

        // Возвращаем "сырой" JSON от HA, не парся его на стороне аддона
        return Results.Content(body, "application/json");
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

// Явно привязываемся к порту 8080, который уже прокинут в addon config.yaml
app.Run("http://0.0.0.0:8080");


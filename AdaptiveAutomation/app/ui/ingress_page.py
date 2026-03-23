def render_ingress_page(message: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>AdaptiveAutomation API Console</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 1000px;
      margin: 0 auto;
      padding: 16px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
    }}
    .muted {{
      color: #94a3b8;
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    button {{
      border: 1px solid #334155;
      background: #1e293b;
      color: #e2e8f0;
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      font-size: 14px;
      text-align: left;
    }}
    button:hover {{
      background: #273449;
    }}
    .panel {{
      margin-top: 14px;
      border: 1px solid #334155;
      border-radius: 10px;
      background: #111827;
      padding: 12px;
    }}
    textarea {{
      width: 100%;
      min-height: 120px;
      background: #020617;
      color: #e2e8f0;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      font-family: Consolas, monospace;
      font-size: 13px;
      box-sizing: border-box;
    }}
    pre {{
      margin: 0;
      padding: 12px;
      background: #020617;
      border: 1px solid #334155;
      border-radius: 8px;
      overflow: auto;
      max-height: 50vh;
      font-size: 12px;
      line-height: 1.35;
    }}
    .row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .hint {{
      color: #a5b4fc;
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .domains-box {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 6px 10px;
      margin-top: 8px;
    }}
    .domains-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      background: #0b1220;
      font-size: 13px;
    }}
    .domains-item label {{
      display: flex;
      gap: 8px;
      align-items: center;
      cursor: pointer;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>AdaptiveAutomation API Console</h1>
    <div class="muted">Message from config: {message}</div>
    <div class="muted">Use this ingress page to call model API endpoints.</div>

    <div class="grid">
      <button id="btn-health">GET /health</button>
      <button id="btn-config">GET /api/config</button>
      <button id="btn-domains">GET /api/domains</button>
      <button id="btn-model">GET /api/model-info</button>
      <button id="btn-train">POST /api/train</button>
      <button id="btn-predict-now">GET /api/predict</button>
      <button id="btn-routines">POST /api/routine-suggestions</button>
      <button id="btn-sequences">POST /api/sequence-suggestions</button>
      <button id="btn-predict-custom">POST /api/predict (custom body)</button>
      <button id="btn-train-events">POST /api/train-from-events (custom body)</button>
    </div>

    <div class="panel">
      <div class="hint">Training domains (loaded dynamically from Home Assistant /states):</div>
      <div class="row">
        <button id="btn-domains-refresh">Refresh domains</button>
        <button id="btn-domains-save">Save selected domains</button>
      </div>
      <div id="domains-box" class="domains-box"></div>
    </div>

    <div class="panel">
      <div class="hint">Editable request body for POST endpoints:</div>
      <textarea id="request-body">{{
  "timestamp": "2026-02-19T18:00:00Z",
  "limit": 10
}}</textarea>
      <div class="row">
        <button id="btn-format">Format JSON</button>
      </div>
    </div>

    <div class="panel">
      <div class="hint">Response:</div>
      <pre id="output">Ready.</pre>
    </div>
  </div>

  <script>
    const output = document.getElementById("output");
    const requestBody = document.getElementById("request-body");
    const domainsBox = document.getElementById("domains-box");
    let currentDomains = [];

    function show(title, payload) {{
      let bodyText = payload;
      if (typeof payload !== "string") {{
        try {{
          bodyText = JSON.stringify(payload, null, 2);
        }} catch (_) {{
          bodyText = String(payload);
        }}
      }}
      output.textContent = title + "\\n\\n" + bodyText;
    }}

    async function callApi(method, url, body = null) {{
      try {{
        show("Request", {{ method, url, body }});
        const res = await fetch(url, {{
          method,
          headers: body ? {{ "Content-Type": "application/json" }} : undefined,
          body: body ? JSON.stringify(body) : undefined
        }});

        const text = await res.text();
        let json;
        try {{
          json = JSON.parse(text);
        }} catch (_) {{
          json = text;
        }}
        show(`${{method}} ${{url}} -> ${{res.status}}`, json);
      }} catch (err) {{
        show("Error", String(err));
      }}
    }}

    function parseBody() {{
      try {{
        return JSON.parse(requestBody.value || "{{}}");
      }} catch (err) {{
        show("Invalid JSON", String(err));
        return null;
      }}
    }}

    function renderDomains(domains) {{
      currentDomains = Array.isArray(domains) ? domains : [];
      domainsBox.innerHTML = "";
      if (!currentDomains.length) {{
        domainsBox.innerHTML = "<div class='muted'>No domains found.</div>";
        return;
      }}

      currentDomains.forEach((item) => {{
        const wrapper = document.createElement("div");
        wrapper.className = "domains-item";

        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = !!item.enabled;
        checkbox.dataset.domain = item.domain;

        const text = document.createElement("span");
        text.textContent = item.domain + " (" + item.entity_count + ")";
        label.appendChild(checkbox);
        label.appendChild(text);

        const badge = document.createElement("span");
        badge.className = "muted";
        badge.textContent = item.recommended ? "recommended" : "";

        wrapper.appendChild(label);
        wrapper.appendChild(badge);
        domainsBox.appendChild(wrapper);
      }});
    }}

    function collectEnabledDomains() {{
      const checked = domainsBox.querySelectorAll("input[type='checkbox']:checked");
      const values = [];
      checked.forEach((el) => {{
        if (el.dataset && el.dataset.domain) values.push(el.dataset.domain);
      }});
      return values;
    }}

    async function loadDomains() {{
      try {{
        const res = await fetch("api/domains");
        const text = await res.text();
        let json;
        try {{
          json = JSON.parse(text);
        }} catch (_) {{
          json = text;
        }}
        if (res.ok && json && Array.isArray(json.domains)) {{
          renderDomains(json.domains);
        }}
        show("GET api/domains -> " + res.status, json);
      }} catch (err) {{
        show("Error loading domains", String(err));
      }}
    }}

    async function saveDomains() {{
      const enabledDomains = collectEnabledDomains();
      await callApi("POST", "api/domains", {{ enabled_domains: enabledDomains }});
      await loadDomains();
    }}

    document.getElementById("btn-health").onclick = () => callApi("GET", "health");
    document.getElementById("btn-config").onclick = () => callApi("GET", "api/config");
    document.getElementById("btn-domains").onclick = () => callApi("GET", "api/domains");
    document.getElementById("btn-domains-refresh").onclick = () => loadDomains();
    document.getElementById("btn-domains-save").onclick = () => saveDomains();
    document.getElementById("btn-model").onclick = () => callApi("GET", "api/model-info");
    document.getElementById("btn-train").onclick = () => callApi("POST", "api/train", {{}});
    document.getElementById("btn-predict-now").onclick = () => callApi("GET", "api/predict");
    document.getElementById("btn-routines").onclick = () => callApi("POST", "api/routine-suggestions", {{}});
    document.getElementById("btn-sequences").onclick = () => callApi("POST", "api/sequence-suggestions", {{}});
    document.getElementById("btn-predict-custom").onclick = () => {{
      const body = parseBody();
      if (body !== null) callApi("POST", "api/predict", body);
    }};
    document.getElementById("btn-train-events").onclick = () => {{
      const body = parseBody();
      if (body !== null) callApi("POST", "api/train-from-events", body);
    }};
    document.getElementById("btn-format").onclick = () => {{
      const body = parseBody();
      if (body !== null) requestBody.value = JSON.stringify(body, null, 2);
    }};
    loadDomains();
  </script>
</body>
</html>
"""

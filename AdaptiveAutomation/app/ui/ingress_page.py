def render_ingress_page(message: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>AdaptiveAutomation Control Center</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
    }}
    .wrap {{
      max-width: 1200px;
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
    .tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .tab-btn {{
      border: 1px solid #334155;
      background: #1e293b;
      color: #e2e8f0;
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 13px;
    }}
    .tab-btn.active {{
      background: #0ea5e9;
      color: #00111a;
      border-color: #0ea5e9;
      font-weight: 700;
    }}
    .tab {{
      display: none;
      margin-top: 12px;
    }}
    .tab.active {{
      display: block;
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
    .kv {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 8px;
    }}
    .field {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .field input, .field select, .field textarea {{
      width: 100%;
      background: #020617;
      color: #e2e8f0;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px;
      box-sizing: border-box;
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid #334155;
      text-align: left;
      padding: 8px;
      vertical-align: top;
    }}
    th {{
      color: #93c5fd;
      font-weight: 700;
    }}
    .small {{
      font-size: 12px;
      color: #94a3b8;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>AdaptiveAutomation Control Center</h1>
    <div class="muted">Message from config: {message}</div>
    <div class="muted">Iteration 3 MVP: Dashboard, Data & Filters, Rules Explorer, Rule Details.</div>

    <div class="tabs">
      <button class="tab-btn active" data-tab="tab-dashboard">Dashboard</button>
      <button class="tab-btn" data-tab="tab-filters">Data & Filters</button>
      <button class="tab-btn" data-tab="tab-rules">Rules Explorer</button>
      <button class="tab-btn" data-tab="tab-details">Rule Details</button>
    </div>

    <section id="tab-dashboard" class="tab active">
      <div class="panel">
        <div class="hint">System status and quick actions</div>
        <div class="grid">
          <button id="btn-refresh-dashboard">Refresh Dashboard</button>
          <button id="btn-train">POST /api/train</button>
          <button id="btn-train-all">POST /api/train/all</button>
          <button id="btn-predict-now">GET /api/predict</button>
        </div>
        <div id="dashboard-cards" class="kv"></div>
      </div>
    </section>

    <section id="tab-filters" class="tab">
      <div class="panel">
        <div class="hint">Domains used for training</div>
        <div class="row">
          <button id="btn-domains-refresh">Refresh domains</button>
          <button id="btn-domains-save">Save selected domains</button>
        </div>
        <div id="domains-box" class="domains-box"></div>
      </div>
      <div class="panel">
        <div class="hint">Core settings and policy filters</div>
        <div class="kv">
          <div class="field"><label>history_days</label><input id="set-history_days" type="number" /></div>
          <div class="field"><label>min_support</label><input id="set-min_support" type="number" /></div>
          <div class="field"><label>min_confidence</label><input id="set-min_confidence" type="number" step="0.01" /></div>
          <div class="field"><label>rules_limit</label><input id="set-rules_limit" type="number" /></div>
          <div class="field"><label>allow_relaxed_fallback</label>
            <select id="set-allow_relaxed_fallback"><option value="true">true</option><option value="false">false</option></select>
          </div>
          <div class="field"><label>policy_one_per_entity</label>
            <select id="set-policy_one_per_entity"><option value="false">false</option><option value="true">true</option></select>
          </div>
          <div class="field"><label>policy_domain_allowlist (comma separated)</label><textarea id="set-policy_domain_allowlist"></textarea></div>
          <div class="field"><label>policy_domain_denylist (comma separated)</label><textarea id="set-policy_domain_denylist"></textarea></div>
          <div class="field"><label>policy_entity_allowlist (comma separated)</label><textarea id="set-policy_entity_allowlist"></textarea></div>
          <div class="field"><label>policy_entity_denylist (comma separated)</label><textarea id="set-policy_entity_denylist"></textarea></div>
        </div>
        <div class="row">
          <button id="btn-settings-refresh">Refresh settings</button>
          <button id="btn-settings-save">Save settings</button>
        </div>
      </div>
    </section>

    <section id="tab-rules" class="tab">
      <div class="panel">
        <div class="hint">Unified rules from /api/suggestions</div>
        <div class="row">
          <select id="rules-type">
            <option value="all">all</option>
            <option value="state">state</option>
            <option value="routine">routine</option>
            <option value="sequence">sequence</option>
          </select>
          <button id="btn-rules-refresh">Refresh rules</button>
        </div>
        <div class="small" id="rules-meta"></div>
        <div style="overflow:auto; margin-top:8px;">
          <table>
            <thead>
              <tr>
                <th>score</th>
                <th>type</th>
                <th>title</th>
                <th>entity</th>
                <th>confidence</th>
                <th>support</th>
                <th>details</th>
              </tr>
            </thead>
            <tbody id="rules-body"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-details" class="tab">
      <div class="panel">
        <div class="hint">Selected rule details</div>
        <pre id="rule-details">Select a rule from Rules Explorer.</pre>
      </div>
      <div class="panel">
        <div class="hint">API console</div>
        <textarea id="request-body">{{
  "timestamp": "2026-02-19T18:00:00Z",
  "limit": 10
}}</textarea>
        <div class="row">
          <button id="btn-config">GET /api/config</button>
          <button id="btn-model">GET /api/model-info</button>
          <button id="btn-health">GET /health</button>
          <button id="btn-routines">POST /api/routine-suggestions</button>
          <button id="btn-sequences">POST /api/sequence-suggestions</button>
          <button id="btn-predict-custom">POST /api/predict</button>
          <button id="btn-train-events">POST /api/train-from-events</button>
          <button id="btn-format">Format JSON</button>
        </div>
        <pre id="output">Ready.</pre>
      </div>
    </section>
  </div>

  <script>
    const output = document.getElementById("output");
    const requestBody = document.getElementById("request-body");
    const domainsBox = document.getElementById("domains-box");
    const rulesBody = document.getElementById("rules-body");
    const rulesMeta = document.getElementById("rules-meta");
    const dashboardCards = document.getElementById("dashboard-cards");
    const ruleDetails = document.getElementById("rule-details");
    let currentDomains = [];
    let lastRulesType = "all";

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

    function setTab(tabId) {{
      document.querySelectorAll(".tab-btn").forEach((btn) => {{
        btn.classList.toggle("active", btn.dataset.tab === tabId);
      }});
      document.querySelectorAll(".tab").forEach((tab) => {{
        tab.classList.toggle("active", tab.id === tabId);
      }});
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

    function csvToList(value) {{
      return (value || "")
        .split(",")
        .map((x) => x.trim())
        .filter((x) => x.length > 0);
    }}

    function listToCsv(value) {{
      return Array.isArray(value) ? value.join(", ") : "";
    }}

    async function loadSettings() {{
      const res = await fetch("api/settings");
      const json = await res.json();
      if (!res.ok || !json.settings) {{
        show("GET api/settings -> " + res.status, json);
        return;
      }}
      const s = json.settings;
      document.getElementById("set-history_days").value = s.history_days ?? 7;
      document.getElementById("set-min_support").value = s.min_support ?? 5;
      document.getElementById("set-min_confidence").value = s.min_confidence ?? 0.6;
      document.getElementById("set-rules_limit").value = s.rules_limit ?? 50;
      document.getElementById("set-allow_relaxed_fallback").value = String(!!s.allow_relaxed_fallback);
      document.getElementById("set-policy_one_per_entity").value = String(!!s.policy_one_per_entity);
      document.getElementById("set-policy_domain_allowlist").value = listToCsv(s.policy_domain_allowlist);
      document.getElementById("set-policy_domain_denylist").value = listToCsv(s.policy_domain_denylist);
      document.getElementById("set-policy_entity_allowlist").value = listToCsv(s.policy_entity_allowlist);
      document.getElementById("set-policy_entity_denylist").value = listToCsv(s.policy_entity_denylist);
      show("GET api/settings -> " + res.status, json);
    }}

    async function saveSettings() {{
      const settings = {{
        history_days: Number(document.getElementById("set-history_days").value),
        min_support: Number(document.getElementById("set-min_support").value),
        min_confidence: Number(document.getElementById("set-min_confidence").value),
        rules_limit: Number(document.getElementById("set-rules_limit").value),
        allow_relaxed_fallback: document.getElementById("set-allow_relaxed_fallback").value === "true",
        policy_one_per_entity: document.getElementById("set-policy_one_per_entity").value === "true",
        policy_domain_allowlist: csvToList(document.getElementById("set-policy_domain_allowlist").value),
        policy_domain_denylist: csvToList(document.getElementById("set-policy_domain_denylist").value),
        policy_entity_allowlist: csvToList(document.getElementById("set-policy_entity_allowlist").value),
        policy_entity_denylist: csvToList(document.getElementById("set-policy_entity_denylist").value),
      }};
      await callApi("POST", "api/settings", {{ settings }});
      await loadSettings();
    }}

    function renderRules(rules) {{
      rulesBody.innerHTML = "";
      if (!Array.isArray(rules) || !rules.length) {{
        rulesBody.innerHTML = "<tr><td colspan='7' class='small'>No rules found</td></tr>";
        return;
      }}
      rules.forEach((rule) => {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${{rule.score ?? 0}}</td>
          <td>${{rule.type ?? ""}}</td>
          <td>${{rule.title ?? ""}}</td>
          <td>${{rule.entity_id ?? ""}}</td>
          <td>${{rule.confidence ?? 0}}</td>
          <td>${{rule.support_days ?? 0}}</td>
          <td><button data-rule-id="${{rule.id}}">View</button></td>
        `;
        tr.querySelector("button").onclick = () => loadRuleDetails(rule.id);
        rulesBody.appendChild(tr);
      }});
    }}

    async function loadRules() {{
      const type = document.getElementById("rules-type").value;
      lastRulesType = type;
      const res = await fetch("api/suggestions?type=" + encodeURIComponent(type));
      const json = await res.json();
      if (!res.ok) {{
        show("GET api/suggestions -> " + res.status, json);
        return;
      }}
      rulesMeta.textContent = JSON.stringify(json.counts || {{}});
      renderRules(json.rules || []);
      show("GET api/suggestions?type=" + type + " -> " + res.status, json);
    }}

    async function loadRuleDetails(ruleId) {{
      const res = await fetch("api/rules/" + encodeURIComponent(ruleId) + "?type=" + encodeURIComponent(lastRulesType));
      const json = await res.json();
      if (!res.ok) {{
        ruleDetails.textContent = JSON.stringify(json, null, 2);
        show("GET /api/rules/{id} -> " + res.status, json);
        return;
      }}
      ruleDetails.textContent = JSON.stringify(json.rule, null, 2);
      setTab("tab-details");
    }}

    async function refreshDashboard() {{
      const [h, c, s] = await Promise.all([
        fetch("health").then((r) => r.json().catch(() => ({{}}))),
        fetch("api/config").then((r) => r.json().catch(() => ({{}}))),
        fetch("api/suggestions?type=all").then((r) => r.json().catch(() => ({{}}))),
      ]);
      dashboardCards.innerHTML = "";
      const cards = [
        ["addon_status", h.status],
        ["model_loaded", String(h.model_loaded)],
        ["last_trained_at", h.last_trained_at || "null"],
        ["history_days", c.history_days],
        ["rules_after_policy", s.counts ? s.counts.after_policy : 0],
        ["rules_ranked", s.counts ? s.counts.ranked : 0],
      ];
      cards.forEach(([k, v]) => {{
        const div = document.createElement("div");
        div.className = "panel";
        div.innerHTML = `<div class="small">${{k}}</div><div>${{v}}</div>`;
        dashboardCards.appendChild(div);
      }});
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

    document.querySelectorAll(".tab-btn").forEach((btn) => {{
      btn.onclick = () => setTab(btn.dataset.tab);
    }});

    document.getElementById("btn-refresh-dashboard").onclick = () => refreshDashboard();
    document.getElementById("btn-health").onclick = () => callApi("GET", "health");
    document.getElementById("btn-config").onclick = () => callApi("GET", "api/config");
    document.getElementById("btn-domains-refresh").onclick = () => loadDomains();
    document.getElementById("btn-domains-save").onclick = () => saveDomains();
    document.getElementById("btn-settings-refresh").onclick = () => loadSettings();
    document.getElementById("btn-settings-save").onclick = () => saveSettings();
    document.getElementById("btn-rules-refresh").onclick = () => loadRules();
    document.getElementById("btn-model").onclick = () => callApi("GET", "api/model-info");
    document.getElementById("btn-train").onclick = () => callApi("POST", "api/train", {{}});
    document.getElementById("btn-train-all").onclick = () => callApi("POST", "api/train/all", {{}});
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
    refreshDashboard();
    loadDomains();
    loadSettings();
    loadRules();
  </script>
</body>
</html>
"""

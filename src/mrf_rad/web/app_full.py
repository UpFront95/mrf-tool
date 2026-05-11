from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from mrf_rad.query import run_query
from mrf_rad.web.presets import default_presets


@dataclass(frozen=True)
class AppConfig:
    parquet_glob: str


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parquet_glob: str | None = None
    service_line: str | None = None
    cpt: str | None = None
    service_category: str | None = None
    payer: str | None = None
    modality: str | None = None
    body_region: str | None = None
    billing_class: str | None = None
    negotiated_type: str | None = None
    benchmark_eligible: bool = False
    min_rate: float | None = None
    max_rate: float | None = None
    group_by: str | None = None
    summary: bool = False
    limit: int = Field(default=100, ge=1, le=10_000)


def _page_html(config: AppConfig) -> str:
    default_glob = escape(config.parquet_glob, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>mrf-rad web</title>
    <style>
      :root {{
        color-scheme: light dark;
        font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      }}
      body {{
        margin: 0;
        background: #f4f6f8;
        color: #14212b;
      }}
      main {{
        max-width: 1800px;
        margin: 0 auto;
        padding: 20px;
      }}
      h1, h2, h3 {{
        margin: 0;
        font-weight: 600;
      }}
      .layout {{
        display: grid;
        grid-template-columns: 320px minmax(0, 1fr);
        gap: 20px;
        align-items: start;
      }}
      .panel {{
        background: #ffffff;
        border: 1px solid #d7dde3;
        border-radius: 8px;
        padding: 16px;
      }}
      .stack {{
        display: grid;
        gap: 12px;
      }}
      .field {{
        display: grid;
        gap: 6px;
      }}
      label {{
        font-size: 12px;
        font-weight: 600;
        color: #51606f;
      }}
      input, select, button, textarea {{
        font: inherit;
      }}
      input, select {{
        width: 100%;
        box-sizing: border-box;
        padding: 8px 10px;
        border: 1px solid #c8d0d9;
        border-radius: 6px;
        background: #fff;
        color: #14212b;
      }}
      button {{
        padding: 9px 12px;
        border: 1px solid #c8d0d9;
        border-radius: 6px;
        background: #f7f9fb;
        color: #14212b;
        cursor: pointer;
        text-align: left;
      }}
      button.primary {{
        background: #1f6feb;
        border-color: #1f6feb;
        color: #fff;
        text-align: center;
      }}
      .preset-list {{
        display: grid;
        gap: 8px;
      }}
      .preset-list button {{
        display: grid;
        gap: 4px;
      }}
      .muted {{
        color: #5a6877;
        font-size: 13px;
      }}
      .results {{
        display: grid;
        gap: 16px;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }}
      th, td {{
        padding: 8px 10px;
        border-bottom: 1px solid #e4e8ed;
        text-align: left;
        vertical-align: top;
        word-break: break-word;
      }}
      th {{
        background: #f8fafc;
        position: sticky;
        top: 0;
      }}
      .table-wrap {{
        overflow: auto;
        max-height: 540px;
        border: 1px solid #e4e8ed;
        border-radius: 6px;
      }}
      .summary-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }}
      .metric {{
        border: 1px solid #e4e8ed;
        border-radius: 6px;
        padding: 12px;
        background: #fbfcfd;
      }}
      .metric .value {{
        font-size: 24px;
        font-weight: 600;
      }}
      .sql {{
        white-space: pre-wrap;
        word-break: break-word;
        font-family: ui-monospace, SFMono-Regular, monospace;
        font-size: 12px;
      }}
      .tabs {{
        display: flex;
        gap: 4px;
        border-bottom: 1px solid #e4e8ed;
        margin-bottom: 12px;
      }}
      .tab-btn {{
        padding: 8px 16px;
        border: 1px solid transparent;
        border-bottom: none;
        border-radius: 6px 6px 0 0;
        background: none;
        cursor: pointer;
        font-weight: 500;
        color: #5a6877;
        margin-bottom: -1px;
      }}
      .tab-btn.active {{
        background: #fff;
        border-color: #e4e8ed;
        color: #14212b;
      }}
      .tab-panel {{ display: none; }}
      .tab-panel.active {{ display: block; }}
      th.sortable {{ cursor: pointer; user-select: none; }}
      th.sortable:hover {{ background: #eef2f7; }}
      th.sort-asc::after {{ content: " ▲"; font-size: 10px; }}
      th.sort-desc::after {{ content: " ▼"; font-size: 10px; }}
      #tab-npi .table-wrap {{ max-height: 600px; }}
      @media (max-width: 980px) {{
        .layout {{
          grid-template-columns: 1fr;
        }}
        .summary-grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="layout">
        <section class="panel stack">
          <div class="stack">
            <h1>mrf-rad web</h1>
            <div class="muted">ABA rates — BSCA</div>
          </div>

          <div class="field">
            <label for="parquet_glob">Parquet glob</label>
            <input id="parquet_glob" value="{default_glob}">
          </div>

          <div class="field">
            <label for="cpt">CPT</label>
            <select id="cpt">
              <option value="">Any</option>
            </select>
          </div>

          <div class="field">
            <label for="modifier">Modifier (plan tabs)</label>
            <select id="modifier">
              <option value="">Any</option>
              <option value="HM">HM — less than bachelor's</option>
              <option value="HN">HN — bachelor's level</option>
              <option value="HO">HO — master's level</option>
            </select>
          </div>

          <div class="field">
            <label for="service_category">Service category</label>
            <input id="service_category" placeholder="Direct Treatment">
          </div>

          <div class="field">
            <label for="payer">Payer</label>
            <select id="payer">
              <option value="">Any</option>
            </select>
          </div>

          <div class="field">
            <label for="billing_class">Billing class</label>
            <select id="billing_class">
              <option value="">Any</option>
              <option value="professional">professional</option>
              <option value="institutional">institutional</option>
            </select>
          </div>

          <div class="field">
            <label for="negotiated_type">Negotiated type</label>
            <select id="negotiated_type">
              <option value="">Any</option>
              <option value="negotiated">negotiated</option>
              <option value="derived">derived</option>
              <option value="fee schedule">fee schedule</option>
              <option value="percentage">percentage</option>
            </select>
          </div>

          <div class="field">
            <label for="group_by">Group by</label>
            <input id="group_by" placeholder="billing_code,service_category">
          </div>

          <div class="field">
            <label for="limit">Limit</label>
            <input id="limit" type="number" min="1" max="10000" value="100">
          </div>

          <div class="field">
            <label for="benchmark_eligible">Benchmark eligible only</label>
            <select id="benchmark_eligible">
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>

          <div class="stack">
            <button class="primary" id="run_summary">Run Summary</button>
            <button class="primary" id="run_rows">Run Rows</button>
            <button class="primary" id="run_npi">Provider Rates</button>
            <button class="primary" id="run_plan_rates">Plan Rates (named plans)</button>
            <button class="primary" id="run_plan_median">Plan Rates Median</button>
          </div>

          <div class="stack">
            <h2>Saved Presets</h2>
            <div id="preset_list" class="preset-list"></div>
          </div>
        </section>

        <section class="results">
          <div class="panel stack">
            <div>
              <h2>Raw vs Benchmark Summary</h2>
              <div class="muted">Runs the same grouped summary twice, with and without benchmark filtering, using the current billing-class and negotiated-type filters.</div>
            </div>
            <div class="summary-grid">
              <div class="metric">
                <div class="muted">Raw groups</div>
                <div class="value" id="raw_group_count">-</div>
              </div>
              <div class="metric">
                <div class="muted">Benchmark groups</div>
                <div class="value" id="bench_group_count">-</div>
              </div>
              <div class="metric">
                <div class="muted">Raw rows in groups</div>
                <div class="value" id="raw_row_total">-</div>
              </div>
              <div class="metric">
                <div class="muted">Benchmark rows in groups</div>
                <div class="value" id="bench_row_total">-</div>
              </div>
            </div>
          </div>

          <div class="panel stack">
            <div class="tabs">
              <button class="tab-btn active" data-tab="results">Results</button>
              <button class="tab-btn" data-tab="npi">Provider Rates</button>
              <button class="tab-btn" data-tab="plan">Plan Rates</button>
              <button class="tab-btn" data-tab="planmedian">Plan Rates Median</button>
            </div>

            <div id="tab-results" class="tab-panel active">
              <div>
                <h2 id="results_title">Results</h2>
                <div class="muted" id="results_meta">No query run yet.</div>
              </div>
              <div class="table-wrap">
                <table id="results_table"></table>
              </div>
            </div>

            <div id="tab-npi" class="tab-panel">
              <div>
                <h2>Provider Rates</h2>
                <div class="muted">professional / fee schedule · deduplicated across network tiers</div>
                <div class="muted" id="npi_meta">Click "Provider Rates" to load.</div>
              </div>
              <div class="table-wrap">
                <table id="npi_table"></table>
              </div>
            </div>

            <div id="tab-planmedian" class="tab-panel">
              <div>
                <h2>Plan Rates Median</h2>
                <div class="muted">professional · fee schedule + per diem · median across named plans · select a CPT to load</div>
                <div class="muted" id="planmedian_meta">Select a CPT and click "Plan Rates Median" to load.</div>
              </div>
              <div class="table-wrap" style="overflow-x:auto;">
                <table id="planmedian_table"></table>
              </div>
            </div>

            <div id="tab-plan" class="tab-panel">
              <div>
                <h2>Plan Rates</h2>
                <div class="muted">professional · fee schedule + per diem · named plans only · select a CPT to load</div>
                <div class="muted" id="plan_meta">Select a CPT and click "Plan Rates (named plans)" to load.</div>
              </div>
              <div class="table-wrap" style="overflow-x:auto;">
                <table id="plan_table"></table>
              </div>
            </div>
          </div>

          <div class="panel stack">
            <h2>SQL</h2>
            <div class="sql" id="sql_text"></div>
          </div>
        </section>
      </div>
    </main>
    <script>
      const state = {{
        presets: [],
      }};

      function el(id) {{
        return document.getElementById(id);
      }}

      function currentFormParams() {{
        return {{
          parquet_glob: el("parquet_glob").value.trim(),
          service_line: "aba",
          cpt: el("cpt").value.trim() || null,
          service_category: el("service_category").value.trim() || null,
          payer: el("payer").value || null,
          billing_class: el("billing_class").value || null,
          negotiated_type: el("negotiated_type").value || null,
          group_by: el("group_by").value.trim() || null,
          benchmark_eligible: el("benchmark_eligible").value === "true",
          limit: parseInt(el("limit").value, 10) || 100,
        }};
      }}

      function applyParams(params) {{
        el("parquet_glob").value = params.parquet_glob || el("parquet_glob").value;
        el("service_category").value = params.service_category || "";
        el("billing_class").value = params.billing_class || "";
        el("negotiated_type").value = params.negotiated_type || "";
        el("group_by").value = params.group_by || "";
        el("benchmark_eligible").value = String(Boolean(params.benchmark_eligible));
        el("limit").value = params.limit || 100;
        if (params.cpt) {{
          const opt = [...el("cpt").options].find(o => o.value === params.cpt);
          if (opt) el("cpt").value = params.cpt;
        }}
        if (params.payer) {{
          const opt = [...el("payer").options].find(o => o.value === params.payer);
          if (opt) el("payer").value = params.payer;
        }}
      }}

      const sortState = {{}};

      function renderTable(tableEl, result, {{sortable = false}} = {{}}) {{
        const cols = result.columns || [];
        let rows = (result.rows || []).slice();
        const key = tableEl.id;
        if (!sortState[key]) sortState[key] = {{col: null, dir: 1}};

        function applySort() {{
          const {{col, dir}} = sortState[key];
          if (!col) return;
          rows.sort((a, b) => {{
            const av = a[col], bv = b[col];
            if (av === null || av === undefined) return 1;
            if (bv === null || bv === undefined) return -1;
            return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
          }});
        }}
        applySort();

        const head = "<thead><tr>" + cols.map((col) => {{
          const cls = sortable ? "sortable" + (sortState[key].col === col ? (sortState[key].dir === 1 ? " sort-asc" : " sort-desc") : "") : "";
          return `<th class="${{cls}}" data-col="${{col}}">${{col}}</th>`;
        }}).join("") + "</tr></thead>";

        const body = "<tbody>" + rows.map((row) => {{
          return "<tr>" + cols.map((col) => {{
            const value = row[col];
            if (value === null || value === undefined) return "<td></td>";
            if (col === "provider_name" && typeof value === "string") {{
              const truncated = value.length > 25 ? value.slice(0, 25) + "…" : value;
              return `<td title="${{value}}">${{truncated}}</td>`;
            }}
            if (col.includes("rate") && typeof value === "number") return `<td>${{value.toFixed(2)}}</td>`;
            return `<td>${{JSON.stringify(value).replace(/^\"|\"$/g, "")}}</td>`;
          }}).join("") + "</tr>";
        }}).join("") + "</tbody>";

        tableEl.innerHTML = head + body;

        if (sortable) {{
          tableEl.querySelectorAll("th.sortable").forEach(th => {{
            th.addEventListener("click", () => {{
              const col = th.dataset.col;
              if (sortState[key].col === col) {{
                sortState[key].dir *= -1;
              }} else {{
                sortState[key] = {{col, dir: 1}};
              }}
              renderTable(tableEl, result, {{sortable}});
            }});
          }});
        }}
      }}

      async function postQuery(params, title) {{
        const response = await fetch("/api/query", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(params),
        }});
        const payload = await response.json();
        if (!response.ok) {{
          throw new Error(payload.detail || "query failed");
        }}
        el("results_title").textContent = title;
        el("results_meta").textContent = `${{payload.row_count}} rows returned`;
        el("sql_text").textContent = payload.sql;
        renderTable(el("results_table"), payload, {{sortable: true}});
        switchTab("results");
        return payload;
      }}

      async function loadNpiSummary() {{
        const glob = el("parquet_glob").value.trim();
        const cpt = el("cpt").value.trim() || null;
        el("npi_meta").textContent = "Loading...";
        switchTab("npi");
        const response = await fetch("/api/npi-summary?" + new URLSearchParams(
          Object.fromEntries(Object.entries({{ glob, cpt }}).filter(([,v]) => v != null))
        ));
        const payload = await response.json();
        if (!response.ok) {{
          el("npi_meta").textContent = "Error: " + (payload.detail || "failed");
          return;
        }}
        el("npi_meta").textContent = `${{payload.row_count}} providers`;
        el("sql_text").textContent = payload.sql || "";
        renderTable(el("npi_table"), payload, {{sortable: true}});
      }}

      async function refreshComparison() {{
        const base = currentFormParams();
        const compareParams = {{
          parquet_glob: base.parquet_glob,
          service_line: "aba",
          cpt: base.cpt,
          service_category: base.service_category,
          payer: base.payer,
          billing_class: base.billing_class,
          negotiated_type: base.negotiated_type,
          group_by: base.group_by || "billing_code,service_category",
          summary: true,
          limit: 100,
        }};
        const [raw, bench] = await Promise.all([
          fetch("/api/query", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ ...compareParams, benchmark_eligible: false }}),
          }}).then((r) => r.json()),
          fetch("/api/query", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ ...compareParams, benchmark_eligible: true }}),
          }}).then((r) => r.json()),
        ]);
        el("raw_group_count").textContent = raw.row_count ?? "-";
        el("bench_group_count").textContent = bench.row_count ?? "-";
        el("raw_row_total").textContent = (raw.rows || []).reduce((sum, row) => sum + (row.row_count || 0), 0);
        el("bench_row_total").textContent = (bench.rows || []).reduce((sum, row) => sum + (row.row_count || 0), 0);
      }}

      async function loadPresets() {{
        const response = await fetch("/api/presets");
        const presets = await response.json();
        state.presets = presets;
        const host = el("preset_list");
        host.innerHTML = "";
        for (const preset of presets) {{
          const button = document.createElement("button");
          button.innerHTML = `<strong>${{preset.label}}</strong><span class="muted">${{preset.description}}</span>`;
          button.addEventListener("click", async () => {{
            const params = {{ ...preset.params, parquet_glob: el("parquet_glob").value.trim() || preset.params.parquet_glob }};
            applyParams(params);
            await postQuery(params, preset.label);
          }});
          host.appendChild(button);
        }}
        if (presets.length > 0) {{
          applyParams(presets[0].params);
        }}
      }}

      async function loadFacets() {{
        const response = await fetch("/api/facets");
        const data = await response.json();
        for (const name of data.payer_names) {{
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          el("payer").appendChild(opt);
        }}
        for (const code of data.cpt_codes) {{
          const opt = document.createElement("option");
          opt.value = code;
          opt.textContent = code;
          el("cpt").appendChild(opt);
        }}
      }}

      function switchTab(name) {{
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
      }}

      document.querySelectorAll(".tab-btn").forEach(btn => {{
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
      }});

      el("run_summary").addEventListener("click", async () => {{
        const params = {{ ...currentFormParams(), summary: true }};
        await postQuery(params, "Summary");
        await refreshComparison();
      }});

      el("run_rows").addEventListener("click", async () => {{
        const params = {{ ...currentFormParams(), summary: false }};
        await postQuery(params, "Rows");
      }});

      function planParams() {{
        const cpt = el("cpt").value;
        const modifier = el("modifier").value;
        const p = {{ cpt }};
        if (modifier) p.modifier = modifier;
        return {{ cpt, params: p }};
      }}

      async function loadPlanRates() {{
        const {{ cpt, params }} = planParams();
        if (!cpt) {{
          el("plan_meta").textContent = "Select a CPT code first.";
          switchTab("plan");
          return;
        }}
        el("plan_meta").textContent = "Loading...";
        switchTab("plan");
        const response = await fetch("/api/plan-rates?" + new URLSearchParams(params));
        const payload = await response.json();
        if (!response.ok) {{
          el("plan_meta").textContent = "Error: " + (payload.detail || "failed");
          return;
        }}
        el("plan_meta").textContent = `${{payload.row_count}} rows · CPT ${{cpt}}`;
        el("sql_text").textContent = payload.sql || "";
        renderTable(el("plan_table"), payload, {{sortable: true}});
      }}

      async function loadPlanMedian() {{
        const {{ cpt, params }} = planParams();
        if (!cpt) {{
          el("planmedian_meta").textContent = "Select a CPT code first.";
          switchTab("planmedian");
          return;
        }}
        el("planmedian_meta").textContent = "Loading...";
        switchTab("planmedian");
        const response = await fetch("/api/plan-rates-median?" + new URLSearchParams(params));
        const payload = await response.json();
        if (!response.ok) {{
          el("planmedian_meta").textContent = "Error: " + (payload.detail || "failed");
          return;
        }}
        el("planmedian_meta").textContent = `${{payload.row_count}} providers · CPT ${{cpt}}`;
        el("sql_text").textContent = payload.sql || "";
        renderTable(el("planmedian_table"), payload, {{sortable: true}});
      }}

      el("run_npi").addEventListener("click", loadNpiSummary);
      el("run_plan_rates").addEventListener("click", loadPlanRates);
      el("run_plan_median").addEventListener("click", loadPlanMedian);

      Promise.all([loadFacets(), loadPresets()]).then(async () => {{
        const preset = state.presets[0];
        if (preset) {{
          await postQuery({{ ...preset.params, parquet_glob: el("parquet_glob").value.trim() }}, preset.label);
        }}
        await refreshComparison();
      }});
    </script>
  </body>
</html>"""


def create_app(default_parquet_glob: str) -> FastAPI:
    app = FastAPI(title="mrf-rad web")
    config = AppConfig(parquet_glob=default_parquet_glob)

    def _con() -> duckdb.DuckDBPyConnection:
        return duckdb.connect()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _page_html(config)

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return asdict(config)

    @app.get("/api/facets")
    def get_facets() -> dict[str, Any]:
        con = _con()
        payers = con.execute(
            "SELECT DISTINCT payer_name FROM read_parquet(?) ORDER BY payer_name",
            [config.parquet_glob],
        ).fetchall()
        cpts = con.execute(
            "SELECT DISTINCT billing_code FROM read_parquet(?) ORDER BY billing_code",
            [config.parquet_glob],
        ).fetchall()
        modifiers = con.execute(
            "SELECT DISTINCT m FROM (SELECT unnest(billing_code_modifiers) AS m FROM read_parquet(?)) ORDER BY m",
            [config.parquet_glob],
        ).fetchall()
        return {
            "payer_names": [r[0] for r in payers if r[0]],
            "cpt_codes": [r[0] for r in cpts if r[0]],
            "modifiers": [r[0] for r in modifiers if r[0]],
        }

    @app.get("/api/npi-summary")
    def get_npi_summary(glob: str | None = None, cpt: str | None = None) -> dict[str, Any]:
        parquet_glob = glob or config.parquet_glob
        cpt_filter = "AND billing_code = ?" if cpt else ""
        params: list[Any] = [parquet_glob]
        if cpt:
            params.append(cpt)
        sql = f"""
            SELECT
                rates.npi,
                COALESCE(
                    n.organization_name,
                    CONCAT_WS(' ', n.first_name, n.last_name)
                ) AS provider_name,
                COUNT(*) AS rate_rows,
                MIN(rates.negotiated_rate) AS min_rate,
                MAX(rates.negotiated_rate) AS max_rate,
                ROUND(AVG(rates.negotiated_rate), 2) AS avg_rate,
                ROUND(MEDIAN(rates.negotiated_rate), 2) AS median_rate
            FROM (
                SELECT DISTINCT npi, billing_code, negotiated_rate, negotiated_type,
                    aba_delivery_mode, aba_provider_role
                FROM (
                    SELECT unnest(provider_npi_list) AS npi, billing_code, negotiated_rate,
                        negotiated_type, aba_delivery_mode, aba_provider_role
                    FROM read_parquet(?)
                    WHERE len(provider_npi_list) > 0
                    AND negotiated_rate IS NOT NULL
                    AND billing_class = 'professional'
                    AND negotiated_type = 'fee schedule'
                    {cpt_filter}
                )
            ) rates
            LEFT JOIN read_parquet('/svr/data/nppes/npi_names.parquet') n ON rates.npi = n.npi
            GROUP BY rates.npi, provider_name
            ORDER BY rate_rows DESC
            LIMIT 500
        """
        con = _con()
        result = con.execute(sql, params).fetchall()
        columns = ["npi", "provider_name", "rate_rows", "min_rate", "max_rate", "avg_rate", "median_rate"]
        rows = [
            {"npi": r[0], "provider_name": r[1], "rate_rows": r[2], "min_rate": r[3],
             "max_rate": r[4], "avg_rate": r[5], "median_rate": r[6]}
            for r in result
        ]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": sql.strip()}

    # Short display names for each named plan file
    _PLAN_LABELS: dict[str, str] = {
        "Blue-Shield-Access-Gold-80-HMO-250-35-Child-Dental": "Access Gold HMO",
        "Blue-Shield-Access-Gold-80-HMO-250-35-Child-Dental-INF": "Access Gold HMO INF",
        "Blue-Shield-Access-Platinum-90-HMO-0-20-Child-Dental-INF": "Access Platinum HMO INF",
        "Blue-Shield-Gold-80-PPO-0-25-Child-Dental": "Gold PPO",
        "Blue-Shield-Gold-80-PPO-350-25-Child-Dental": "Gold PPO (Alt)",
        "Blue-Shield-Platinum-90-Trio-HMO-JAN26": "Platinum Trio HMO",
        "Blue-Shield-Silver-70-HDHP-PPO-2300-30-PCP-Child-Dental-Alt-FAM-INF": "Silver HDHP PPO INF",
        "Blue-Shield-Silver-70-PPO-2000-45-Child-Dental": "Silver PPO",
        "Blue-Shield-Trio-Silver-70-HMO-2250-50-Child-Dental": "Trio Silver HMO",
        "Gold-80-PPO-Jan16": "Gold PPO (Jan16)",
        "Platinum-90-HMO-Trio-AI-AN-Jan18": "Platinum HMO AI/AN",
        "Preferred-PPO-Native-American-Jan14": "Preferred PPO AI/AN",
        "Silver-70-PPO-AI-AN-Jan18": "Silver PPO AI/AN",
    }

    def _modifier_filter(modifier: str | None) -> str:
        if modifier:
            return f"AND list_contains(billing_code_modifiers, '{modifier}')"
        return ""

    @app.get("/api/plan-rates")
    def get_plan_rates(cpt: str, modifier: str | None = None) -> dict[str, Any]:
        import re as _re
        plans = list(_PLAN_LABELS.items())  # (raw_name, label)
        # Build CASE expressions to extract plan name from URL and pivot
        case_exprs = "\n".join(
            f"MAX(CASE WHEN regexp_extract(source_file_url, '\\d{{4}}-\\d{{2}}-\\d{{2}}_\\d+-(.+)_Blue-Shield', 1) = '{raw}'"
            f" THEN negotiated_rate END) AS \"{label}\","
            for raw, label in plans
        )
        sql = f"""
            SELECT
                src.npi,
                COALESCE(n.organization_name, CONCAT_WS(' ', n.first_name, n.last_name)) AS provider_name,
                COALESCE(array_to_string(src.modifiers, ','), '') AS modifiers,
                {case_exprs.rstrip(",")}
            FROM (
                SELECT DISTINCT unnest(provider_npi_list) AS npi, negotiated_rate,
                    source_file_url, billing_code_modifiers AS modifiers
                FROM read_parquet(?)
                WHERE billing_code = ?
                AND billing_class = 'professional'
                AND negotiated_type IN ('fee schedule', 'per diem')
                AND negotiated_rate IS NOT NULL
                AND regexp_extract(source_file_url, '\\d{{4}}-\\d{{2}}-\\d{{2}}_\\d+-(.+)_Blue-Shield', 1)
                    NOT SIMILAR TO '\\d+|Blue-Shield-of-California'
                {_modifier_filter(modifier)}
            ) src
            LEFT JOIN read_parquet('/svr/data/nppes/npi_names.parquet') n ON src.npi = n.npi
            GROUP BY src.npi, provider_name, src.modifiers
            HAVING COUNT(*) > 0
            ORDER BY provider_name NULLS LAST, src.modifiers
            LIMIT 10000
        """
        con = _con()
        result = con.execute(sql, [config.parquet_glob, cpt]).fetchall()
        columns = ["npi", "provider_name", "modifiers"] + [label for _, label in plans]
        rows = [dict(zip(columns, row)) for row in result]
        # Drop rows where all plan columns are null
        rows = [r for r in rows if any(r[c] is not None for c in columns[3:])]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": sql.strip()}

    @app.get("/api/plan-rates-median")
    def get_plan_rates_median(cpt: str, modifier: str | None = None) -> dict[str, Any]:
        sql = f"""
            SELECT
                src.npi,
                COALESCE(n.organization_name, CONCAT_WS(' ', n.first_name, n.last_name)) AS provider_name,
                COALESCE(array_to_string(src.modifiers, ','), '') AS modifiers,
                ROUND(MEDIAN(src.negotiated_rate), 2) AS median_rate,
                MIN(src.negotiated_rate) AS min_rate,
                MAX(src.negotiated_rate) AS max_rate,
                COUNT(DISTINCT src.plan_name) AS plan_count
            FROM (
                SELECT DISTINCT npi, negotiated_rate, modifiers, plan_name
                FROM (
                    SELECT unnest(provider_npi_list) AS npi, negotiated_rate,
                        billing_code_modifiers AS modifiers,
                        regexp_extract(source_file_url, '\\d{{4}}-\\d{{2}}-\\d{{2}}_\\d+-(.+)_Blue-Shield', 1) AS plan_name
                    FROM read_parquet(?)
                    WHERE billing_code = ?
                    AND billing_class = 'professional'
                    AND negotiated_type IN ('fee schedule', 'per diem')
                    AND negotiated_rate IS NOT NULL
                    {_modifier_filter(modifier)}
                )
                WHERE plan_name NOT SIMILAR TO '\\d+|Blue-Shield-of-California'
            ) src
            LEFT JOIN read_parquet('/svr/data/nppes/npi_names.parquet') n ON src.npi = n.npi
            GROUP BY src.npi, provider_name, src.modifiers
            ORDER BY median_rate DESC NULLS LAST, provider_name
            LIMIT 10000
        """
        con = _con()
        result = con.execute(sql, [config.parquet_glob, cpt]).fetchall()
        columns = ["npi", "provider_name", "modifiers", "median_rate", "min_rate", "max_rate", "plan_count"]
        rows = [dict(zip(columns, row)) for row in result]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": sql.strip()}

    @app.get("/api/presets")
    def get_presets() -> list[dict[str, Any]]:
        return [preset.to_dict() for preset in default_presets()]

    @app.post("/api/query")
    def post_query(request: QueryRequest) -> dict[str, Any]:
        parquet_glob = request.parquet_glob or config.parquet_glob
        try:
            result = run_query(
                parquet_glob,
                service_line=request.service_line,
                cpt=request.cpt,
                service_category=request.service_category,
                payer=request.payer,
                modality=request.modality,
                body_region=request.body_region,
                billing_class=request.billing_class,
                negotiated_type=request.negotiated_type,
                benchmark_eligible=request.benchmark_eligible,
                min_rate=request.min_rate,
                max_rate=request.max_rate,
                group_by=request.group_by,
                summary=request.summary,
                limit=request.limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    return app

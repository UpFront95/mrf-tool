from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
from typing import Any

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
        max-width: 1240px;
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
            <div class="muted">Local operator view over parsed Parquet output.</div>
          </div>

          <div class="field">
            <label for="parquet_glob">Parquet glob</label>
            <input id="parquet_glob" value="{default_glob}">
          </div>

          <div class="field">
            <label for="service_line">Service line</label>
            <select id="service_line">
              <option value="">Any</option>
              <option value="aba">ABA</option>
              <option value="radiology">Radiology</option>
            </select>
          </div>

          <div class="field">
            <label for="cpt">CPT</label>
            <input id="cpt" placeholder="97153">
          </div>

          <div class="field">
            <label for="service_category">Service category</label>
            <input id="service_category" placeholder="Direct Treatment">
          </div>

          <div class="field">
            <label for="payer">Payer</label>
            <input id="payer" placeholder="Capital BlueCross">
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
            <div>
              <h2 id="results_title">Results</h2>
              <div class="muted" id="results_meta">No query run yet.</div>
            </div>
            <div class="table-wrap">
              <table id="results_table"></table>
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
          service_line: el("service_line").value || null,
          cpt: el("cpt").value.trim() || null,
          service_category: el("service_category").value.trim() || null,
          payer: el("payer").value.trim() || null,
          billing_class: el("billing_class").value || null,
          negotiated_type: el("negotiated_type").value || null,
          group_by: el("group_by").value.trim() || null,
          benchmark_eligible: el("benchmark_eligible").value === "true",
          limit: parseInt(el("limit").value, 10) || 100,
        }};
      }}

      function applyParams(params) {{
        el("parquet_glob").value = params.parquet_glob || el("parquet_glob").value;
        el("service_line").value = params.service_line || "";
        el("cpt").value = params.cpt || "";
        el("service_category").value = params.service_category || "";
        el("payer").value = params.payer || "";
        el("billing_class").value = params.billing_class || "";
        el("negotiated_type").value = params.negotiated_type || "";
        el("group_by").value = params.group_by || "";
        el("benchmark_eligible").value = String(Boolean(params.benchmark_eligible));
        el("limit").value = params.limit || 100;
      }}

      function renderTable(result) {{
        const table = el("results_table");
        const cols = result.columns || [];
        const rows = result.rows || [];
        const head = "<thead><tr>" + cols.map((col) => `<th>${{col}}</th>`).join("") + "</tr></thead>";
        const body = "<tbody>" + rows.map((row) => {{
          return "<tr>" + cols.map((col) => {{
            const value = row[col];
            return `<td>${{value === null || value === undefined ? "" : JSON.stringify(value).replace(/^\"|\"$/g, "")}}</td>`;
          }}).join("") + "</tr>";
        }}).join("") + "</tbody>";
        table.innerHTML = head + body;
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
        renderTable(payload);
        return payload;
      }}

      async function refreshComparison() {{
        const base = currentFormParams();
        const compareParams = {{
          parquet_glob: base.parquet_glob,
          service_line: base.service_line,
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

      el("run_summary").addEventListener("click", async () => {{
        const params = {{ ...currentFormParams(), summary: true }};
        await postQuery(params, "Summary");
        await refreshComparison();
      }});

      el("run_rows").addEventListener("click", async () => {{
        const params = {{ ...currentFormParams(), summary: false }};
        await postQuery(params, "Rows");
      }});

      loadPresets().then(async () => {{
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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _page_html(config)

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return asdict(config)

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

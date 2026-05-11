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


def _page_html(config: AppConfig) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ABA Rate Explorer</title>
    <style>
      :root {{ color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
      body {{ margin: 0; background: #f4f6f8; color: #14212b; }}
      main {{ max-width: 1800px; margin: 0 auto; padding: 20px; }}
      h1, h2 {{ margin: 0; font-weight: 600; }}
      .layout {{ display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 20px; align-items: start; }}
      .panel {{ background: #fff; border: 1px solid #d7dde3; border-radius: 8px; padding: 16px; }}
      .stack {{ display: grid; gap: 12px; }}
      .field {{ display: grid; gap: 6px; }}
      label {{ font-size: 12px; font-weight: 600; color: #51606f; }}
      input, select, button {{ font: inherit; }}
      select {{ width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid #c8d0d9; border-radius: 6px; background: #fff; color: #14212b; }}
      button.primary {{ width: 100%; padding: 10px 12px; border: none; border-radius: 6px; background: #1f6feb; color: #fff; cursor: pointer; font-weight: 600; font-size: 14px; }}
      button.primary:hover {{ background: #1a60d6; }}
      .muted {{ color: #5a6877; font-size: 13px; }}
      table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
      th, td {{ padding: 8px 10px; border-bottom: 1px solid #e4e8ed; text-align: left; vertical-align: top; white-space: nowrap; }}
      th {{ background: #f8fafc; position: sticky; top: 0; z-index: 1; }}
      th.sortable {{ cursor: pointer; user-select: none; }}
      th.sortable:hover {{ background: #eef2f7; }}
      th.sort-asc::after {{ content: " ▲"; font-size: 10px; }}
      th.sort-desc::after {{ content: " ▼"; font-size: 10px; }}
      .table-wrap {{ overflow: auto; max-height: 75vh; border: 1px solid #e4e8ed; border-radius: 6px; }}
      @media (max-width: 800px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    </style>
  </head>
  <body>
    <main>
      <div class="layout">
        <section class="panel stack">
          <h1>ABA Rate Explorer</h1>
          <div class="muted">BSCA · professional · fee schedule + per diem · named plans</div>

          <div class="field">
            <label for="cpt">CPT Code</label>
            <select id="cpt">
              <option value="">Select CPT…</option>
            </select>
          </div>

          <div class="field">
            <label for="modifier">Modifier</label>
            <select id="modifier">
              <option value="">Any</option>
              <option value="HM">HM — less than bachelor's</option>
              <option value="HN">HN — bachelor's level</option>
              <option value="HO">HO — master's level</option>
            </select>
          </div>

          <button class="primary" id="run_btn">Load Rates</button>

          <div class="muted" id="status">Select a CPT to begin.</div>
        </section>

        <section class="panel stack">
          <div>
            <h2>Plan Rates Median</h2>
            <div class="muted" id="meta">—</div>
          </div>
          <div class="table-wrap">
            <table id="results_table"></table>
          </div>
        </section>
      </div>
    </main>
    <script>
      const sortState = {{ col: null, dir: 1 }};
      let lastResult = null;

      function el(id) {{ return document.getElementById(id); }}

      function renderTable(result) {{
        lastResult = result;
        const cols = result.columns || [];
        let rows = (result.rows || []).slice();
        const tbl = el("results_table");

        if (sortState.col) {{
          rows.sort((a, b) => {{
            const av = a[sortState.col], bv = b[sortState.col];
            if (av == null) return 1;
            if (bv == null) return -1;
            return (av < bv ? -1 : av > bv ? 1 : 0) * sortState.dir;
          }});
        }}

        const head = "<thead><tr>" + cols.map(c => {{
          const active = sortState.col === c;
          const cls = "sortable" + (active ? (sortState.dir === 1 ? " sort-asc" : " sort-desc") : "");
          return `<th class="${{cls}}" data-col="${{c}}">${{c}}</th>`;
        }}).join("") + "</tr></thead>";

        const body = "<tbody>" + rows.map(row => "<tr>" + cols.map(c => {{
          const v = row[c];
          if (v == null) return "<td></td>";
          if (c === "provider_name") {{
            const t = String(v).length > 28 ? String(v).slice(0, 28) + "…" : v;
            return `<td title="${{v}}">${{t}}</td>`;
          }}
          if (["median_rate","min_rate","max_rate"].includes(c) && typeof v === "number")
            return `<td>${{v.toFixed(2)}}</td>`;
          return `<td>${{v}}</td>`;
        }}).join("") + "</tr>").join("") + "</tbody>";

        tbl.innerHTML = head + body;
        tbl.querySelectorAll("th.sortable").forEach(th => {{
          th.addEventListener("click", () => {{
            const c = th.dataset.col;
            if (sortState.col === c) sortState.dir *= -1;
            else {{ sortState.col = c; sortState.dir = 1; }}
            renderTable(lastResult);
          }});
        }});
      }}

      async function load() {{
        const cpt = el("cpt").value;
        const modifier = el("modifier").value;
        if (!cpt) {{ el("status").textContent = "Select a CPT code first."; return; }}
        el("status").textContent = "Loading…";
        const params = {{ cpt }};
        if (modifier) params.modifier = modifier;
        const resp = await fetch("/api/plan-rates-median?" + new URLSearchParams(params));
        const data = await resp.json();
        if (!resp.ok) {{ el("status").textContent = "Error: " + (data.detail || "failed"); return; }}
        el("status").textContent = "";
        el("meta").textContent = `${{data.row_count}} providers · CPT ${{cpt}}${{modifier ? " · " + modifier : ""}}`;
        renderTable(data);
      }}

      async function loadFacets() {{
        const resp = await fetch("/api/facets");
        const data = await resp.json();
        for (const code of data.cpt_codes) {{
          const opt = document.createElement("option");
          opt.value = code; opt.textContent = code;
          el("cpt").appendChild(opt);
        }}
      }}

      el("run_btn").addEventListener("click", load);
      loadFacets();
    </script>
  </body>
</html>"""


def create_app(default_parquet_glob: str) -> FastAPI:
    app = FastAPI(title="ABA Rate Explorer")
    config = AppConfig(parquet_glob=default_parquet_glob)

    def _con() -> duckdb.DuckDBPyConnection:
        return duckdb.connect()

    def _modifier_filter(modifier: str | None) -> str:
        if modifier:
            return f"AND list_contains(billing_code_modifiers, '{modifier}')"
        return ""

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _page_html(config)

    @app.get("/api/facets")
    def get_facets() -> dict[str, Any]:
        con = _con()
        cpts = con.execute(
            "SELECT DISTINCT billing_code FROM read_parquet(?) ORDER BY billing_code",
            [config.parquet_glob],
        ).fetchall()
        return {"cpt_codes": [r[0] for r in cpts if r[0]]}

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

    # Keep full query API available for future use
    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return asdict(config)

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

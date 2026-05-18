from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from mrf_rad.query import run_query


@dataclass(frozen=True)
class AppConfig:
    parquet_glob: str

    @property
    def glob_list(self) -> list[str]:
        """Split comma-separated globs into a list for DuckDB."""
        return [g.strip() for g in self.parquet_glob.split(",") if g.strip()]


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





def _chart_page_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ABA Rate Explorer</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
      :root { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color-scheme: light dark; }
      body { margin: 0; background: #f4f6f8; color: #14212b; }
      main { max-width: 1100px; margin: 0 auto; padding: 24px; }
      h1 { margin: 0 0 4px; font-weight: 600; }
      .controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin: 20px 0; }
      .field { display: grid; gap: 6px; }
      label { font-size: 12px; font-weight: 600; color: #51606f; }
      select, input { padding: 8px 10px; border: 1px solid #c8d0d9; border-radius: 6px; font: inherit; background: #fff; min-width: 160px; }
      button { padding: 9px 20px; background: #1f6feb; color: #fff; border: none; border-radius: 6px; font: inherit; font-weight: 600; cursor: pointer; }
      button:hover { background: #1a60d6; }
      button.secondary { background: #fff; color: #1f6feb; border: 1px solid #1f6feb; }
      button.secondary:hover { background: #f0f4ff; }
      .panel { background: #fff; border: 1px solid #d7dde3; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
      .stats { display: flex; gap: 24px; flex-wrap: wrap; margin-top: 16px; }
      .stat { text-align: center; }
      .stat .val { font-size: 22px; font-weight: 700; }
      .stat .lbl { font-size: 12px; color: #5a6877; }
      .highlight-info { margin-top: 12px; padding: 10px 14px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; font-size: 13px; }
      .muted { color: #5a6877; font-size: 13px; }
      canvas { max-height: 400px; }
      #chart_panel { display: none; }
      #table_panel { display: none; margin-top: 0; }
      .table-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      th, td { padding: 8px 10px; border-bottom: 1px solid #e4e8ed; text-align: left; white-space: nowrap; }
      th { background: #f8fafc; position: sticky; top: 0; z-index: 1; cursor: pointer; user-select: none; }
      th:hover { background: #eef2f7; }
      th.sort-asc::after { content: " ▲"; font-size: 10px; }
      th.sort-desc::after { content: " ▼"; font-size: 10px; }
      .table-wrap { overflow: auto; max-height: 60vh; border: 1px solid #e4e8ed; border-radius: 6px; }
    </style>
  </head>
  <body>
    <main>
      <h1>ABA Rate Explorer</h1>

      <div class="controls">
        <div class="field">
          <label for="cpt">CPT Code</label>
          <select id="cpt"><option value="">Select CPT…</option></select>
        </div>
        <div class="field">
          <label for="payer">Payer</label>
          <select id="payer"><option value="">Any payer</option></select>
        </div>
        <div class="field">
          <label for="modifier">Modifier</label>
          <select id="modifier">
            <option value="" selected>Any</option>
            <option value="HM">HM — less than bachelor's</option>
            <option value="HN">HN — bachelor's level</option>
            <option value="HO">HO — master's level</option>
          </select>
        </div>
        <div class="field">
          <label for="highlight_npi">Highlight NPI</label>
          <input id="highlight_npi" placeholder="e.g. 1134800980" value="1134800980">
        </div>
        <button id="run_btn">Show Chart</button>
      </div>

      <div class="panel" id="chart_panel">
        <canvas id="chart"></canvas>
        <div class="stats" id="stats"></div>
        <div id="highlight_info"></div>
        <div style="margin-top:16px;">
          <button class="secondary" id="show_table_btn">Show Detail Table</button>
        </div>
      </div>

      <div class="panel" id="table_panel">
        <div class="table-toolbar">
          <strong id="table_meta"></strong>
          <span class="muted" id="table_status"></span>
        </div>
        <div class="table-wrap">
          <table id="results_table"></table>
        </div>
      </div>
    </main>
    <script>
      let chartInstance = null;
      const sortState = { col: null, dir: 1 };
      let lastTableResult = null;

      async function loadFacets() {
        const resp = await fetch("/api/facets");
        const data = await resp.json();
        for (const code of data.cpt_codes) {
          const opt = document.createElement("option");
          opt.value = code; opt.textContent = code;
          if (code === "97153") opt.selected = true;
          document.getElementById("cpt").appendChild(opt);
        }
        for (const name of (data.payer_names || [])) {
          const opt = document.createElement("option");
          opt.value = name; opt.textContent = name;
          document.getElementById("payer").appendChild(opt);
        }
      }

      async function loadChart() {
        const cpt = document.getElementById("cpt").value;
        const modifier = document.getElementById("modifier").value;
        const payer = document.getElementById("payer").value;
        const npi = document.getElementById("highlight_npi").value.trim();
        if (!cpt) { alert("Select a CPT code."); return; }

        const params = { cpt };
        if (modifier) params.modifier = modifier;
        if (payer) params.payer = payer;
        if (npi) params.npi = npi;

        const resp = await fetch("/api/rate-distribution?" + new URLSearchParams(params));
        const data = await resp.json();
        if (!resp.ok) { alert("Error: " + (data.detail || "failed")); return; }

        document.getElementById("chart_panel").style.display = "block";
        document.getElementById("table_panel").style.display = "none";
        renderChart(data, cpt, modifier);
        renderStats(data);
        renderHighlight(data);
      }

      async function loadTable() {
        const cpt = document.getElementById("cpt").value;
        const modifier = document.getElementById("modifier").value;
        const payer = document.getElementById("payer").value;
        if (!cpt) return;

        document.getElementById("table_status").textContent = "Loading…";
        document.getElementById("table_panel").style.display = "block";
        document.getElementById("table_panel").scrollIntoView({ behavior: "smooth", block: "start" });

        const params = { cpt };
        if (modifier) params.modifier = modifier;
        if (payer) params.payer = payer;

        const resp = await fetch("/api/plan-rates-median?" + new URLSearchParams(params));
        const data = await resp.json();
        if (!resp.ok) { document.getElementById("table_status").textContent = "Error: " + (data.detail || "failed"); return; }

        document.getElementById("table_status").textContent = "";
        document.getElementById("table_meta").textContent =
          `${data.row_count.toLocaleString()} providers · CPT ${cpt}${modifier ? " · " + modifier : ""}`;
        renderTable(data);
      }

      function renderChart(data, cpt, modifier) {
        const bins = data.bins;
        const highlightRate = data.highlight ? data.highlight.rate : null;
        const labels = bins.map(b => "$" + b.rate.toFixed(2));
        const counts = bins.map(b => b.count);
        const colors = bins.map(b =>
          highlightRate !== null && Math.abs(b.rate - highlightRate) < 0.001 ? "#e6522c" : "#1f6feb"
        );
        if (chartInstance) chartInstance.destroy();
        chartInstance = new Chart(document.getElementById("chart"), {
          type: "bar",
          data: { labels, datasets: [{ label: `Providers (${cpt}${modifier ? " · " + modifier : ""})`, data: counts, backgroundColor: colors, borderRadius: 3 }] },
          options: {
            responsive: true,
            plugins: { legend: { display: false }, tooltip: { callbacks: { title: ctx => "Rate: " + ctx[0].label, label: ctx => ctx.raw + " providers" } } },
            scales: { x: { title: { display: true, text: "Median Rate ($/unit)" } }, y: { title: { display: true, text: "Providers" }, beginAtZero: true } }
          }
        });
      }

      function renderStats(data) {
        const s = data.stats;
        document.getElementById("stats").innerHTML = [
          ["Min", "$" + s.min.toFixed(2)], ["P25", "$" + s.p25.toFixed(2)],
          ["Median", "$" + s.median.toFixed(2)], ["Average", "$" + s.mean.toFixed(2)],
          ["P75", "$" + s.p75.toFixed(2)], ["Max", "$" + s.max.toFixed(2)],
          ["Providers", s.total.toLocaleString()],
        ].map(([lbl, val]) => `<div class="stat"><div class="val">${val}</div><div class="lbl">${lbl}</div></div>`).join("");
      }

      function renderHighlight(data) {
        const h = data.highlight;
        const el = document.getElementById("highlight_info");
        if (!h) { el.innerHTML = ""; return; }
        el.innerHTML = `<div class="highlight-info"><strong>${h.name || h.npi}</strong> (${h.npi}) — median rate <strong>$${h.rate.toFixed(2)}</strong> · ${h.percentile}th percentile</div>`;
      }

      function renderTable(result) {
        lastTableResult = result;
        const cols = result.columns || [];
        let rows = (result.rows || []).slice();
        if (sortState.col) {
          rows.sort((a, b) => {
            const av = a[sortState.col], bv = b[sortState.col];
            if (av == null) return 1; if (bv == null) return -1;
            return (av < bv ? -1 : av > bv ? 1 : 0) * sortState.dir;
          });
        }
        const head = "<thead><tr>" + cols.map(c => {
          const active = sortState.col === c;
          const cls = active ? (sortState.dir === 1 ? " sort-asc" : " sort-desc") : "";
          return `<th class="${cls}" data-col="${c}">${c}</th>`;
        }).join("") + "</tr></thead>";
        const body = "<tbody>" + rows.map(row => "<tr>" + cols.map(c => {
          const v = row[c];
          if (v == null) return "<td></td>";
          if (c === "provider_name") { const t = String(v).length > 28 ? String(v).slice(0,28)+"…" : v; return `<td title="${v}">${t}</td>`; }
          if (["median_rate","min_rate","max_rate"].includes(c) && typeof v === "number") return `<td>${v.toFixed(2)}</td>`;
          return `<td>${v}</td>`;
        }).join("") + "</tr>").join("") + "</tbody>";
        const tbl = document.getElementById("results_table");
        tbl.innerHTML = head + body;
        tbl.querySelectorAll("th").forEach(th => {
          th.addEventListener("click", () => {
            const c = th.dataset.col;
            if (sortState.col === c) sortState.dir *= -1; else { sortState.col = c; sortState.dir = 1; }
            renderTable(lastTableResult);
          });
        });
      }

      document.getElementById("run_btn").addEventListener("click", loadChart);
      document.getElementById("show_table_btn").addEventListener("click", loadTable);
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
        return _chart_page_html()

    @app.get("/api/facets")
    def get_facets() -> dict[str, Any]:
        con = _con()
        cpts = con.execute(
            "SELECT DISTINCT billing_code FROM read_parquet(?) ORDER BY billing_code",
            [config.glob_list],
        ).fetchall()
        payers = con.execute(
            "SELECT DISTINCT payer_name FROM read_parquet(?) WHERE payer_name IS NOT NULL ORDER BY payer_name",
            [config.glob_list],
        ).fetchall()
        return {
            "cpt_codes": [r[0] for r in cpts if r[0]],
            "payer_names": [r[0] for r in payers],
        }

    @app.get("/api/plan-rates-median")
    def get_plan_rates_median(cpt: str, modifier: str | None = None, payer: str | None = None) -> dict[str, Any]:
        payer_filter = f"AND payer_name = '{payer}'" if payer else ""
        sql = f"""
            SELECT
                src.npi,
                COALESCE(n.organization_name, CONCAT_WS(' ', n.first_name, n.last_name)) AS provider_name,
                COALESCE(array_to_string(src.modifiers, ','), '') AS modifiers,
                src.payer_name,
                ROUND(MEDIAN(src.negotiated_rate), 2) AS median_rate,
                MIN(src.negotiated_rate) AS min_rate,
                MAX(src.negotiated_rate) AS max_rate,
                COUNT(*) AS rate_count
            FROM (
                SELECT DISTINCT npi, negotiated_rate, modifiers, payer_name
                FROM (
                    SELECT unnest(provider_npi_list) AS npi, negotiated_rate,
                        billing_code_modifiers AS modifiers,
                        payer_name
                    FROM read_parquet(?)
                    WHERE billing_code = ?
                    AND billing_class = 'professional'
                    AND negotiated_type IN ('fee schedule', 'per diem', 'negotiated')
                    AND negotiated_rate IS NOT NULL
                    {_modifier_filter(modifier)}
                    {payer_filter}
                )
            ) src
            LEFT JOIN read_parquet('/svr/data/nppes/npi_names.parquet') n ON src.npi = n.npi
            GROUP BY src.npi, provider_name, src.modifiers, src.payer_name
            ORDER BY median_rate DESC NULLS LAST, provider_name
            LIMIT 10000
        """
        con = _con()
        result = con.execute(sql, [config.glob_list, cpt]).fetchall()
        columns = ["npi", "provider_name", "modifiers", "payer_name", "median_rate", "min_rate", "max_rate", "rate_count"]
        rows = [dict(zip(columns, row)) for row in result]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": sql.strip()}

    @app.get("/chart", response_class=HTMLResponse)
    def chart_page() -> str:
        return _chart_page_html()

    @app.get("/api/rate-distribution")
    def get_rate_distribution(cpt: str, modifier: str | None = None, payer: str | None = None, npi: str | None = None) -> dict[str, Any]:
        mod_filter = f"AND list_contains(billing_code_modifiers, '{modifier}')" if modifier else ""
        payer_filter = f"AND payer_name = '{payer}'" if payer else ""
        sql = f"""
            SELECT npi, ROUND(MEDIAN(negotiated_rate), 2) AS median_rate
            FROM (
                SELECT DISTINCT npi, negotiated_rate, payer_name
                FROM (
                    SELECT unnest(provider_npi_list) AS npi, negotiated_rate,
                        billing_code_modifiers,
                        payer_name
                    FROM read_parquet(?)
                    WHERE billing_code = ?
                    AND billing_class = 'professional'
                    AND negotiated_type IN ('fee schedule', 'per diem', 'negotiated')
                    AND negotiated_rate IS NOT NULL
                    {mod_filter}
                    {payer_filter}
                )
            )
            GROUP BY npi
            ORDER BY median_rate
        """
        con = _con()
        rows = con.execute(sql, [config.glob_list, cpt]).fetchall()
        if not rows:
            return {"bins": [], "stats": {}, "highlight": None}

        all_rates = [r[1] for r in rows]
        npi_rates = {r[0]: r[1] for r in rows}
        n = len(all_rates)

        sorted_rates = sorted(all_rates)
        stats = {
            "min": sorted_rates[0],
            "p25": sorted_rates[n // 4],
            "median": sorted_rates[n // 2],
            "mean": round(sum(sorted_rates) / n, 2),
            "p75": sorted_rates[3 * n // 4],
            "max": sorted_rates[-1],
            "total": n,
        }

        # Bucket into histogram bins (up to 50) for readable chart
        min_r, max_r = sorted_rates[0], sorted_rates[-1]
        if max_r > min_r:
            num_bins = min(50, len(set(all_rates)))
            bin_width = (max_r - min_r) / num_bins
            buckets: dict[int, int] = {}
            for r in all_rates:
                idx = min(int((r - min_r) / bin_width), num_bins - 1)
                buckets[idx] = buckets.get(idx, 0) + 1
            bins = [
                {"rate": round(min_r + (i + 0.5) * bin_width, 2), "count": cnt}
                for i, cnt in sorted(buckets.items())
            ]
        else:
            bins = [{"rate": min_r, "count": n}]

        # Highlight NPI
        highlight = None
        if npi and npi in npi_rates:
            rate = npi_rates[npi]
            percentile = round(100 * sum(1 for r in sorted_rates if r <= rate) / n)
            name_row = con.execute(
                "SELECT COALESCE(organization_name, first_name || ' ' || last_name) FROM read_parquet('/svr/data/nppes/npi_names.parquet') WHERE npi = ?",
                [npi]
            ).fetchone()
            highlight = {
                "npi": npi,
                "name": name_row[0].strip() if name_row else None,
                "rate": rate,
                "percentile": percentile,
            }

        return {"bins": bins, "stats": stats, "highlight": highlight}

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file
pytest tests/test_parser.py

# Run the CLI
mrf-rad --help
```

## Architecture

`src/mrf_rad/` is a Click CLI (`cli.py:main`) with five subcommands, each backed by a dedicated module:

| Command | Module | What it does |
|---------|--------|--------------|
| `index` | `discovery/` | Fetches a payer table-of-contents JSON, deduplicates `in_network_files` entries, optionally enriches with HTTP HEAD sizes |
| `parse` | `parser/` | Streams a single `.json.gz` in-network MRF with `ijson`, filters by code profile, writes Parquet |
| `batch` | `batch.py` | Iterates an index JSON and calls `parse_file` for each entry, with `--limit`, `--overwrite`, `--max-size-mb` guards |
| `query` | `query/duckdb.py` | Runs a DuckDB query over a Parquet glob with filter/grouping options |
| `web`   | `web/app.py` | FastAPI + uvicorn local UI over a Parquet glob with saved query presets |

### Key data flow

```
payer TOC URL
  → discovery.parse_index() → IndexFile (list of InNetworkFile)
  → parser.parse_file()     → streams ijson → normalize_in_network_item → ParquetRowWriter
  → query.run_query()       → DuckDB reads Parquet glob → QueryResult
```

### Code profiles (`codes/`)

`profiles.py` maps profile names (`"aba"`, `"radiology"`) to a `CodeProfile` dataclass holding a `billing_code` set. `get_profile(name)` is the public accessor used by the parser to decide which `in_network_item` entries to keep.

### Parser streaming

`parser/stream.py` opens local or HTTPS `.json.gz` files transparently. It uses `ijson` for low-memory streaming of large MRFs. `normalize.py` flattens nested `negotiated_rates`/`provider_groups`/`provider_references` into flat rows suitable for Parquet.

### Discovery

`discovery/base.py` defines `IndexSource`, `InNetworkFile`, `IndexFile`, and `ReportingPlan` dataclasses. `parse_index()` deduplicates by URL and merges `reporting_plan` metadata. `bcbsmn.py` holds the BCBSMN-specific TOC URL resolver.

## Payer Investigation Pattern (Standard)

Validated on Blue Shield of California (BSCA), May 2026. Apply to every new payer.

### Step 1 — Index the TOC
```bash
mrf-rad index <toc-url-or-path> --out data/index/<payer>-index.json
```

### Step 2 — Filter to native files only
Inspect `description` values. Exclude: other-payer-named files, PMPM capitated, specialty-only (Chiro/Acu/Dental/Vision), state/plan-labeled shared network files. Keep only generic unlabeled files (`"in-network file"` or equivalent).

### Step 3 — Probe for service-line presence
```bash
mrf-rad probe data/index/<payer>-native.json --profile aba \
  --workers 8 --limit-items 20000 --out data/index/<payer>-probe.jsonl
```
Default stop-on-match is fast. 20k items is the validated threshold — files with ABA hit early; genuine misses exhaust the limit.

### Step 4 — Identify code groups (network tiers)
Parse the filename structure to extract the network tier code. Files sharing a code share the same provider network and therefore identical negotiated rates. Only 1 file per code group is needed.

BSCA result: 1,033 hit files → 148 unique code groups → 84% reduction.

### Step 5 — Confirm rates identical within groups (sample check)
Pick 2 files per group, compare ABA rate combinations per billing code. BSCA: 100% identical within groups.

### Step 6 — Build representative index and batch parse
Pick smallest file per code group (minimize download):
```bash
mrf-rad batch data/index/<payer>-representative.json \
  --profile aba --index-payer <payer> \
  --out-dir /svr/data/mrf-tool/parquet/<payer>-aba \
  --workers 8
```

### Key BSCA reference numbers
| Metric | Value |
|--------|-------|
| Native files | 1,101 |
| ABA probe hits | 1,033 (93.8%) |
| Unique code groups | 148 |
| Compressed download | ~182 GB |
| Parse time (8 workers) | ~18–24 hours |

### Miss patterns to expect
- Chiro/Acu specialty files: tiny, no ABA — exclude before batching
- EPO Exchange plans: 13k+ items scanned, no ABA — genuine exclusion
- PMPM capitated: different billing model, skip

## Workflow

After any material change (new feature, endpoint, data pipeline step, bug fix), ask the user if they'd like to commit before moving on.

## Current State

- Live in production (dixie) — 13 payers: BSCA, Anthem (national + CA), BCBS IL, BCBS MA, BCBS TX, UHC OHBS, UHC BH-P3, Regence WA, Cigna (national-ppo), Health Net CA, Aetna (Life Insurance Company, national PPO), BCBS Arizona. Pipeline also validated on BCBSMN.
- Profiles: `aba` (CPT 97151–97156), `radiology` (CPT 70000–79999).
- ABA benchmark eligibility filtering excludes percentage rates, institutional rows, and extreme outliers.
- Large BSCA index JSON (`2026-05-01_Blue-Shield-of-California_index.json`, ~192 MB) lives at repo root for local testing.
- Parquet outputs go under `data/`.

## Dixie (Production Server)

**dixie** is the production server that runs the mrf-rad web UI. SSH access: `ssh dixie` (configured in `~/.ssh/config` → 192.168.4.90, user `dixie`). You should SSH into dixie proactively whenever tasks involve the running server, parquet data, or service management — don't wait to be told.

### Key paths on dixie
| Path | What it is |
|------|------------|
| `/srv/share/mrf-tool/` | Project root (virtualenv, scripts, .env) |
| `/srv/share/mrf-tool/.venv/bin/mrf-rad` | CLI entrypoint |
| `/srv/share/mrf-tool/.env` | Environment variables (MRF_USER, MRF_PASS, ports, etc.) |
| `/svr/data/mrf-tool/parquet/` | Production parquet data, one `<payer>-aba/` dir per payer |
| `/srv/share/mrf-tool/scripts/start-web.sh` | Server launch wrapper (auto-discovers `*-aba/` dirs) |
| `~/.config/systemd/user/mrf-rad.service` | systemd user service unit |

### Web server management
The web UI runs as a systemd user service (linger enabled — starts at boot without login):
```bash
systemctl --user start|stop|restart|status mrf-rad
journalctl --user -u mrf-rad -f   # live logs
```

**Adding a new payer:** two steps are required —
1. Copy its `<payer>-aba/` parquet dir to `/svr/data/mrf-tool/parquet/`. The start script auto-discovers all `*-aba/` dirs, so no config or script edits are needed for the data to load.
2. Add the payer's exact `payer_name` value (as it appears in the MRF) to the `_COMPLETE_PAYER_NAMES` set in `src/mrf_rad/web/app.py`. **This is mandatory** — the UI payer dropdown and all queries are gated on this allowlist, so a payer whose `payer_name` is missing here is invisible even though its data is loaded.

Then `systemctl --user restart mrf-rad`.

### HTTP Basic Auth
Credentials are read from `MRF_USER` / `MRF_PASS` in `.env`. Both must be set — the app raises at startup if either is missing (there is no insecure fallback default).

## Payer Pipeline (Researched, Not Yet in Production)

Full probe notes at `data/index/payer-probe-notes.md`. These have been investigated and are ready to parse when time allows:

| Payer | Effort | Notes |
|-------|--------|-------|
| **Anthem/Carelon** | High | ~397 native files; dedup by NETWORKCODE before batching; files up to 52 GB |
| **Premera WA** | Blocked | JS portal killed programmatic TOC access as of Jan 2026 |
| **Kaiser NorCal** | TBD | Catalight (ABA network manager) routes through Kaiser — check Kaiser NorCal MRF |

### Aetna — national live; 13 state-HMO entities staged (not deployed)
The national **Aetna Life Insurance Company** PPO is live (1 representative file =
15.6M rows; all 319 ALICFI "Aetna Life" plan files proven rate-identical, so 1 rep
covers them all). 13 smaller state-HMO entities (Aetna Health of CA/PA/FL/etc.) are
parsed and staged at `/svr/data/mrf-tool/aetna-work/parquet-stage/` on dixie but NOT
deployed — they add 13 separate `payer_name`s and have heavy intra-entity file
duplication (dedup to 1 rep/entity before deploying). **Aetna parse gotchas:** the
heavy parser holds 3–8 GB RAM per national file (provider-reference map) and is
GIL-bound — run process-parallel at concurrency ≤2 on the 15 GB box, and set BOTH
`--tmp-dir` and `TMPDIR` to `/svr/data` (sdb1) so downloads + DuckDB scratch never
touch the root SSD (`/tmp` on root filled it once). Re-fetch the TOC via the
3-step HealthSparq dance (brandCode `ALICFI`) for fresh signed URLs each run —
now scripted: `scripts/fetch_healthsparq_toc.py` (login → `v2/mrf/all` →
`latest_metadata.json`, emits a tool-native index). Drives via `curl` because the
HealthSparq host 403s Python's TLS fingerprint (Incapsula).

### BCBS Arizona (AZBlue) — live; HealthSparq, same platform as Aetna
`insurerCode=BCBSAZ_I`, `brandCode=BCBSAZ`, egress `bcbsaz-egress.nophi.kyruushsq.com`;
`payer_name` = `Blue Cross Blue Shield of Arizona`. Full access recipe + data structure
in `data/index/bcbsaz-access-recipe.md`. 1,129 plan entries → 489 unique files; ABA
present in medical files (all 6 codes, `negotiated` type), absent from the 559-ref
`BAZ-ASHN` specialty file and the `BAZ-EYE` vision file (both excluded). 487 medical
files dedup to **13 network tiers** (PP2/PPO/ALN/PRS/PRM/PPP/PMA/PRM/HMO/HPN/ALH/NBR/
STH/HM2 — tier code from the filename; all within-tier rate-identical, confirmed by
3-file ABA fingerprint). Parse the smallest file per tier
(`data/index/bcbsaz-representative.json`, ~8.9 GB). NB: cross-tier ABA-rate coincidences
exist (PPP/PRM/PRS share rates *this month*) but are deliberately **not** merged —
kept per-tier to match the BSCA per-network-tier precedent and stay stable across monthly
refreshes. Files are ~0.5–1.1 GB compressed like Aetna — same `--tmp-dir`/`TMPDIR` +
concurrency ≤2 guidance applies.

## Github

- Do not list claude as a contributor.

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

## Current State

- Pipeline fully operational for BCBSMN and BSCA.
- Profiles: `aba` (CPT 97151–97156), `radiology` (CPT 70000–79999).
- ABA benchmark eligibility filtering excludes percentage rates, institutional rows, and extreme outliers.
- Large BSCA index JSON (`2026-05-01_Blue-Shield-of-California_index.json`, ~192 MB) lives at repo root for local testing.
- Parquet outputs go under `data/`.

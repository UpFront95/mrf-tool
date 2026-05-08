# mrf-rad: CLI tool for service-line rate extraction from Transparency in Coverage MRFs

## One-line description

A focused Python CLI that extracts service-line-specific in-network negotiated rates from payer Transparency in Coverage machine-readable files (MRFs), starting with radiology and ABA therapy, and producing clean Parquet output suitable for downstream analysis.

---

## Why this exists

Payers are required by the federal Transparency in Coverage (TiC) Final Rule to publish monthly machine-readable files containing every in-network negotiated rate. The files conform to the CMS-published JSON schema (currently version 2.0, mandatory as of March 2026) and are posted at predictable URLs on payer websites.

The data is genuinely useful and almost completely underutilized outside a small set of healthcare data startups. The barriers to use are technical, not legal:

Files are massive. A single payer's complete in-network file can be 100GB to 1TB compressed; loading it in memory is not an option. Schema variance across payers is real; everyone follows the spec but the way they structure provider references, file splits, and metadata differs. Domain knowledge matters; understanding professional/technical splits, modifiers, billing class, and the difference between negotiated arrangements is required to produce useful output.

Generic MRF parsers exist but tend to be either too narrow (single payer, single use case) or too broad (complete spec parsers without opinions). A tool focused specifically on a few high-value service lines with the domain-correct handling baked in is more useful for a defined audience than another generic parser.

The other thing generic parsers miss is that radiology rate analysis happens at the modality level, not the code level. Nobody asks "what's the rate for CPT 70551"; they ask "what does an MRI brain typically pay" or "how do CT chest rates compare across payers in this market." The 70551/70552/70553 distinction (without contrast / with contrast / both) matters for billing but is noise for benchmarking. A radiology-specific tool should classify codes into modality and body region by default and let users aggregate at whatever level they actually need.

ABA therapy is a useful second profile because the core code set is much smaller and the analysis questions are service-type oriented rather than imaging-modality oriented. The first ABA slice should focus on CPT 97151-97156, which cover the main adaptive behavior assessment, treatment, supervision/modification, and caregiver guidance services commonly used for ABA rate analysis. Adjacent codes 97157-97158 can be added later as optional group-service extensions.

---

## Goals

Extract in-network negotiated rates for selected service-line billing codes from any Schema 2.0 MRF. Initial bundled profiles are `radiology` (default CPT 70000-79999) and `aba` (default CPT 97151-97156). Classify each rate with profile-specific fields: radiology gets modality, body region, and contrast; ABA gets service category, delivery mode, and likely provider role. Handle technical/professional component splits as first-class concepts where they apply, while keeping non-radiology profiles from inheriting radiology-specific assumptions. Stream-parse files of arbitrary size without loading them into memory. Output clean, normalized Parquet for downstream analysis. Provide a simple CLI that gets a user from "I have a payer URL" to "I have a Parquet file of targeted rates with useful classification" in one command.

## Non-goals

Not a generic MRF parser; out-of-scope codes are dropped at parse time. Not a market analytics tool; output is data, not insights. No opinion layer, no published rate trends, no provider-level commentary in the tool or its documentation. Not a real-time extraction service; parsing remains a batch job. The web view is an inspection and query layer over already-parsed Parquet, not a replacement for the CLI/library. Not an out-of-network allowed-amounts tool in v1; in-network rates only.

---

## Audience

Healthcare finance teams at radiology groups, hospital imaging service lines, ambulatory imaging centers, ABA therapy providers, autism services organizations, and behavioral health groups who want to benchmark contracted rates against published payer rates at the service-line level. Healthcare data analysts at PE funds, advisory firms, and payer-adjacent startups. Researchers and academics studying payer pricing dispersion. Engineers building healthcare data pipelines who want a clean service-line-specific layer rather than building MRF parsing from scratch.

---

## Architecture overview

Three logical layers, all in a single Python package.

The discovery layer takes a payer URL or known payer shortcut and produces a list of downloadable in-network rate files relevant to a target geography or plan. This means parsing the payer's table of contents (an index JSON file), filtering to relevant in-network entries, and resolving any file size and download metadata.

The parser layer takes a single in-network rate file (URL or local path), streams through it, applies the selected service-line code filter at the streaming level so the bulk of the file is discarded without ever being held in memory, normalizes the matching records into a flat row structure, and writes Parquet output. This layer also handles the provider reference resolution pattern (some payers inline provider groups, others reference separate provider files that have to be fetched and joined).

The profile layer defines bundled code sets and classification metadata for each supported service line. Radiology and ABA share the same MRF extraction pipeline but have different classification vocabularies. This avoids hard-coding radiology concepts into every output while preserving stable common columns for cross-profile querying.

The query layer is thin; it provides a simple CLI wrapper around DuckDB queries against the Parquet output, with a few canned queries (rate by CPT, rate by payer, distribution stats) for common use cases. Most data users can still query the Parquet directly.

The web layer is a local-first browser interface over the same Parquet files. It provides faceted filters, sortable result tables, basic distribution charts, saved query presets, and a natural-language query box backed by an LLM call. The web view never sends raw MRF files or full Parquet datasets to the model; it uses deterministic DuckDB queries for data access and gives the model only schema metadata, allowed query dimensions, the user's question, and bounded aggregate query results.

The LLM layer uses OpenRouter as the provider abstraction, with `google/gemma-4-31b-it` as the default model. The first implementation should treat the model as configurable via environment (`OPENROUTER_API_KEY`, `MRF_RAD_LLM_MODEL`) and keep the prompt contract provider-neutral enough to swap models later. The LLM's job is to translate user intent into a constrained query plan, explain returned aggregate results, and suggest follow-up filters; it is not allowed to invent rates, providers, payer coverage, or conclusions that are not present in query results.

---

## CLI design

```
mrf-rad index <payer-url-or-shortcut> [--state STATE] [--out FILE]
    Parse a payer's table of contents and output the list of in-network
    rate files relevant to the specified state (or all states).
    
    Example:
        mrf-rad index bcbsmn --state MN --out bcbsmn-files.json
        mrf-rad index https://mktg.bluecrossmn.com/mrf/2026/2026-05-01_Blue_Cross_and_Blue_Shield_of_Minnesota_index.json

mrf-rad parse <file-url-or-path> [--profile radiology|aba] [--codes FILE] [--modality LIST] [--service-category LIST] [--out FILE] [--include-modifiers]
    Stream-parse a single in-network rate file, filter to the selected
    profile's codes, classify records with profile-specific fields, and
    write Parquet output. Optional --modality flag filters radiology records
    further to specified modalities only
    (e.g. --modality CT,MRI to extract only CT and MRI rates).
    Optional --service-category filters ABA records by assessment, direct
    treatment, supervision/modification, or caregiver guidance.
    
    Example:
        mrf-rad parse https://mktg.bluecrossmn.com/mrf/2026/path/to/innetwork.json.gz --out bcbsmn-rad.parquet
        mrf-rad parse innetwork.json.gz --modality MRI --out bcbsmn-mri.parquet
        mrf-rad parse innetwork.json.gz --profile aba --out bcbsmn-aba.parquet

mrf-rad batch <files-json> [--out-dir DIR]
    Run parse on every file in a list (output of `index`), writing one
    Parquet per file. Useful for processing all of a payer's relevant
    files in one pass.

mrf-rad query <parquet-glob> [--service-line NAME] [--cpt CODE] [--modality NAME] [--body-region NAME] [--service-category NAME] [--payer NAME] [--group-by COLS] [--summary]
    Run common queries against parsed Parquet output. Mostly a
    convenience wrapper around DuckDB. Common patterns:
        --modality MRI --group-by payer        → median MRI rate by payer
        --modality CT --body-region Chest      → CT chest rates
        --cpt 70551 --summary                  → distribution stats for one code
        --service-line aba --group-by billing_code,service_category

mrf-rad web <parquet-glob> [--host HOST] [--port PORT] [--llm-model MODEL]
    Launch a local web view over parsed Parquet output. The web app exposes
    faceted filtering, result tables, charts, and an LLM-assisted query box.
    Default LLM model is google/gemma-4-31b-it via OpenRouter.

mrf-rad ask <parquet-glob> "QUESTION" [--llm-model MODEL]
    CLI version of the LLM-assisted query workflow. Produces the generated
    query plan, executes the approved DuckDB query, and returns a concise
    answer with the supporting result table.

mrf-rad payers
    List known payer shortcuts and their current index URLs.

mrf-rad validate <file>
    Validate a file against Schema 2.0 (wraps the CMS validator).
```

---

## Data model

The Parquet output is intentionally flat and denormalized for ease of downstream querying. One row per (billing_code, billing_class, provider_group, modifier_combination) tuple.

Columns:

`payer_name` (string) — derived from the source file's `reporting_entity_name`.
`reporting_entity_type` (string) — "issuer" or "group health plan".
`source_file_url` (string) — URL the row was parsed from, for provenance.
`last_updated_on` (date) — the file's `last_updated_on` field.
`schema_version` (string) — schema version of the source file.
`billing_code` (string) — CPT/HCPCS code.
`billing_code_type` (string) — typically "CPT" or "HCPCS".
`billing_code_type_version` (string) — version year of the code set.
`name` (string) — payer-provided name for the code.
`description` (string) — payer-provided description.
`service_line` (string) — bundled profile used for extraction, initially "radiology" or "aba".
`service_category` (string) — profile-specific broad class. For radiology this can mirror modality for cross-profile grouping; for ABA this is "Assessment", "Direct Treatment", "Supervision/Protocol Modification", "Caregiver Guidance", or "Other".
`service_subcategory` (string) — profile-specific finer grouping. For radiology this can be body region; for ABA this can distinguish individual, group, technician-administered, or qualified-professional-administered service patterns where known.
`unit_basis` (string) — common billing unit when known from the bundled profile, such as "15 minutes"; null for custom code sets where the tool should not infer units.
`modality` (string) — radiology-only derived classification: "CT", "MRI", "MRA", "X-ray", "Ultrasound", "Mammography", "Nuclear Medicine", "PET", "Fluoroscopy", "Radiation Oncology", "Other"; null for ABA.
`body_region` (string) — radiology-only derived classification: "Brain", "Head/Neck", "Chest", "Spine", "Abdomen/Pelvis", "Extremities", "Cardiac", "Breast", "Vascular", "OB/GYN", "Other"; null for ABA.
`with_contrast` (string) — radiology code-level attribute: "with", "without", "both", or null where not applicable.
`aba_delivery_mode` (string) — ABA-only derived classification: "individual", "group", "family/caregiver", or null.
`aba_provider_role` (string) — ABA-only derived classification: "qualified_professional", "technician", "mixed_or_supervisory", or null.
`negotiation_arrangement` (string) — "ffs", "bundle", or "capitation".
`billing_class` (string) — "professional", "institutional", or "both".
`negotiated_type` (string) — "negotiated", "derived", "fee schedule", "percentage", "per diem".
`negotiated_rate` (decimal) — the rate; null if `negotiated_type` is "percentage" (use `percentage` column).
`percentage` (decimal) — null unless `negotiated_type` is "percentage".
`expiration_date` (date) — rate expiration.
`service_codes` (list of string) — place-of-service codes.
`billing_code_modifiers` (list of string) — modifiers attached to the rate; TC and 26 are first-class.
`is_technical_component` (bool) — true if modifier 'TC' is present.
`is_professional_component` (bool) — true if modifier '26' is present.
`is_global` (bool) — true if neither TC nor 26 is present (global service).
`setting` (string) — payer-published setting when present, such as "outpatient".
`is_benchmark_eligible` (bool) — derived flag for rows that are plausible unit-rate benchmarking inputs for the selected service line. Raw rows are always preserved; this flag is only a convenience filter.
`provider_npi_list` (list of string) — Type 1 and Type 2 NPIs for this rate.
`provider_tin_type` (string) — "ein" or "npi".
`provider_tin_value` (string) — the TIN.
`additional_information` (string) — preserved free-text from the schema's escape hatch.

The TC/PC/global flag columns are derived during parsing rather than left to downstream consumers. They are most meaningful for radiology and may be null or false for service lines where TC/PC modifier semantics do not apply. Profile-specific fields should be null rather than guessed when a user supplies a custom code set.

For ABA, `is_benchmark_eligible` starts with a conservative rule: numeric negotiated rate, non-percentage `negotiated_type`, `billing_class` equal to "professional", and `negotiated_rate <= 1000`. This intentionally excludes institutional rows and extreme published rates that are unlikely to represent a normal 15-minute unit reimbursement. The flag is not a compliance judgment and should not delete the raw data; users can always query without it.

---

## Code set handling

Bundled profiles:

`radiology` — CPT 70000-79999 inclusive. This covers diagnostic radiology (70010-76999), diagnostic ultrasound (76506-76999), radiologic guidance (77001-77022), breast mammography (77046-77067), bone/joint studies (77071-77086), radiation oncology (77261-77799), nuclear medicine (78012-79999).

`aba` — CPT 97151-97156 inclusive for the initial profile. These are the core adaptive behavior assessment and treatment codes most useful for an early ABA rate extraction slice. Adjacent codes 97157-97158 should be modeled as optional group-service extensions after the first pass, not included silently in the default profile.

Users can override with `--codes` pointing to a CSV or JSON file containing the code set they want. This makes the tool reusable for adjacent verticals (cardiology, anesthesia, pathology, physical therapy) without any code changes; only the filter changes. If a custom code set is supplied without a known profile, service-line-specific classification columns should be null.

The streaming filter is applied at the `in_network[].billing_code` level during JSON parsing; non-matching items are skipped before any of their nested data is materialized. This is the key performance optimization that makes 1TB files tractable on a laptop.

---

## Service-line classification

Radiology codes get classified into modality and body region during parsing, with the classification baked into the output Parquet rather than left to downstream consumers. This is the domain layer that makes the tool useful at the level users actually think in.

The radiology taxonomy lives in `codes/radiology.py` as a static lookup. Three dimensions:

`modality` (top level): CT, MRI, MRA, X-ray, Ultrasound, Mammography, Nuclear Medicine, PET, Fluoroscopy, Radiation Oncology, Other. Roughly maps to imaging technique.

`body_region` (second level): Brain, Head/Neck, Chest, Spine, Abdomen/Pelvis, Extremities, Cardiac, Breast, Vascular, OB/GYN, Other. Lets users cut by anatomical region within or across modalities (e.g. "all spine imaging across modalities" or "all MRI excluding brain").

`with_contrast` (code-level attribute, not a procedure modifier): "with", "without", "both", or null. CPT encodes contrast at the code level for radiology; the 70551/70552/70553 family is the canonical example where the same MRI brain study has three codes for three contrast variants. The classification table just records what each code represents. Surfacing it as a column lets users either aggregate across contrast variants or split them as needed, without parsing descriptions.

The taxonomy is opinionated by design. Codes that don't fit cleanly (interventional radiology codes that span modalities, for example) get classified to the modality of the imaging technique used, with the procedural nature surfaced via the description field. Edge cases get documented in `docs/code-classification-notes.md` rather than handled with elaborate logic; transparency about classification choices is more useful to users than algorithmic elegance.

ABA codes get classified into service category, delivery mode, and provider role during parsing. The ABA taxonomy lives in `codes/aba.py` as a static lookup. Initial defaults:

`97151` — service_category "Assessment"; aba_delivery_mode "individual"; aba_provider_role "qualified_professional"; unit_basis "15 minutes".
`97152` — service_category "Assessment"; aba_delivery_mode "individual"; aba_provider_role "technician"; unit_basis "15 minutes".
`97153` — service_category "Direct Treatment"; aba_delivery_mode "individual"; aba_provider_role "technician"; unit_basis "15 minutes".
`97154` — service_category "Direct Treatment"; aba_delivery_mode "group"; aba_provider_role "technician"; unit_basis "15 minutes".
`97155` — service_category "Supervision/Protocol Modification"; aba_delivery_mode "individual"; aba_provider_role "mixed_or_supervisory"; unit_basis "15 minutes".
`97156` — service_category "Caregiver Guidance"; aba_delivery_mode "family/caregiver"; aba_provider_role "qualified_professional"; unit_basis "15 minutes".

The ABA profile should not try to determine medical necessity rules, authorization requirements, telehealth policy, or allowed units from MRF data. Those rules are payer-policy questions and vary outside the negotiated-rate file. The profile only classifies what the code represents for rate comparison.

The classification is bundled with the code set; users overriding `--codes` to use a non-bundled code set get null profile-specific classification columns rather than incorrect classification. Classifications for additional verticals are out of scope for v1 but the same profile pattern should apply when extended.

---

## Engineering specifics

Language: Python 3.11+.

Streaming JSON parser: `ijson` with the yajl2_c backend for performance. The schema is large but the structure is regular, so ijson's prefix-based filtering works well. Specifically, iterate over `in_network.item` and apply the code filter immediately on each item.

Compression: most payer files are served as gzip; some as zip. Stream decompression with the standard library `gzip` module wrapped around an HTTP stream so the file is never written to disk in full.

HTTP: `httpx` with streaming response support and resumable downloads. Files are large enough that resume-on-failure matters.

Output: PyArrow for Parquet writing, with row-group sizes tuned for downstream DuckDB query performance (default 100k rows per group).

DuckDB: optional dependency for the `query` subcommand only. Parquet output is consumable by anything; DuckDB is just a convenience.

Provider reference resolution: when a file uses `provider_references` (separate provider group files referenced by ID), the parser pre-fetches and caches the referenced files before processing the in-network records. Reference cache is keyed by URL and persists across runs in `~/.cache/mrf-rad/provider-refs/`.

Error handling: malformed records are logged and skipped, not fatal. Schema-violating files (failing CMS validator) get a warning, not an abort. The goal is to extract what's extractable, not to enforce schema purity.

Logging: structured logging via `structlog`. Default human-readable output; `--json-logs` for machine consumption.

Performance target: extract a bundled service-line profile from a 100GB compressed in-network file in under 30 minutes on a laptop with a reasonable internet connection. Should be CPU-bound on JSON parsing, not memory-bound.

---

## Web view and LLM querying

The web view is intended for interactive exploration after extraction is complete. It should run locally by default and read one or more Parquet files directly through DuckDB. A hosted mode can come later, but v1 should assume a single analyst running against local files.

Core web screens:

`Files` — loaded Parquet files, row counts, schema version, payer names, source file provenance, and parse timestamps.
`Explore` — filterable table with service line, payer, CPT, service category, modality, body region, contrast, ABA delivery mode, billing class, modifiers, negotiated type, provider TIN, and NPI filters.
`Compare` — grouped summaries such as median, p25, p75, min, max, and count by service line, payer, service category, modality, body region, CPT, billing class, or geography when available.
`Ask` — natural-language query input backed by the LLM query workflow.

The LLM query workflow has three steps:

1. Interpret the user's question into a constrained query plan using a fixed JSON response schema. Allowed operations are filtering, grouping, aggregation, sorting, limiting, and selecting from approved columns only.
2. Validate the query plan server-side, compile it to parameterized DuckDB SQL, and execute it with row and timeout limits.
3. Send only the executed query metadata and bounded result table back to the LLM for a short answer. The answer must cite the filters, aggregation, row count, and source files used.

The LLM must not receive provider-level raw row dumps by default. Provider identifiers can be included only when the user explicitly asks for provider-level output and the result set is capped. The UI should clearly distinguish computed facts from model-written explanation.

Initial LLM provider:

`provider` — OpenRouter.
`default_model` — `google/gemma-4-31b-it`.
`api_base` — `https://openrouter.ai/api/v1`.
`auth` — `OPENROUTER_API_KEY`.
`model_override` — `MRF_RAD_LLM_MODEL` or `--llm-model`.

The model call should use the OpenAI-compatible chat/completions interface exposed by OpenRouter. All LLM calls should be logged with model name, token counts where available, latency, query-plan validation status, and whether the final answer was generated from executed results or rejected.

---

## Known payer support

v1 ships with index URL shortcuts and validated parsing for:

`uhc` — UnitedHealthcare. Index at `https://transparency-in-coverage.uhc.com/`.
`cigna` — Cigna. Index at `https://www.cigna.com/legal/compliance/machine-readable-files`.
`bcbsmn` — Blue Cross Blue Shield Minnesota. Predictable URL pattern: `https://mktg.bluecrossmn.com/mrf/YYYY/YYYY-MM-01_Blue_Cross_and_Blue_Shield_of_Minnesota_index.json`.
`bcbsma` — Blue Cross Blue Shield Massachusetts. Index at `https://transparency-in-coverage.bluecrossma.com/`.
`bcbsnc` — Blue Cross Blue Shield North Carolina. Index at `https://www.bluecrossnc.com/policies-best-practices/machine-readable-files`.
`bcbsmi` — Blue Cross Blue Shield Michigan. Index at `https://www.bcbsm.com/mrf/index/`.

Each shortcut is a thin wrapper around payer-specific parsers that handle the variance in how the table of contents is structured. Adding a new payer is a small amount of wiring once the patterns are understood; the goal is to make this easy via a registration interface.

For ad-hoc payers not in the shortcut list, users can pass any index URL directly.

---

## Project structure

```
mrf-rad/
├── README.md
├── LICENSE                    # MIT
├── pyproject.toml
├── src/
│   └── mrf_rad/
│       ├── __init__.py
│       ├── cli.py             # CLI entrypoint, click-based
│       ├── discovery/
│       │   ├── __init__.py
│       │   ├── base.py        # Base payer index parser
│       │   ├── uhc.py
│       │   ├── cigna.py
│       │   ├── bcbsmn.py
│       │   └── ...
│       ├── parser/
│       │   ├── __init__.py
│       │   ├── stream.py      # ijson streaming parser
│       │   ├── filter.py      # Code set filtering
│       │   ├── normalize.py   # Schema 2.0 to flat rows
│       │   └── refs.py        # Provider reference resolution
│       ├── output/
│       │   ├── __init__.py
│       │   └── parquet.py     # PyArrow writer
│       ├── codes/
│       │   ├── __init__.py
│       │   ├── radiology.py   # Default radiology code set + modality taxonomy
│       │   ├── aba.py         # Default ABA code set + service taxonomy
│       │   ├── profiles.py    # Shared service-line profile registry
│       │   └── classify.py    # Code -> profile-specific classification lookup
│       ├── query/
│       │   ├── __init__.py
│       │   ├── canned.py      # Canned DuckDB queries
│       │   ├── duckdb.py      # Query execution and SQL compilation
│       │   └── plans.py       # Validated query-plan schema
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── openrouter.py  # OpenRouter client
│       │   ├── prompts.py     # Query-planning and answer prompts
│       │   └── schema.py      # Structured LLM response contracts
│       └── web/
│           ├── __init__.py
│           ├── app.py         # FastAPI/Starlette app factory
│           ├── api.py         # Query and ask endpoints
│           └── static/        # Built frontend assets
├── tests/
│   ├── fixtures/              # Small synthetic MRFs for testing
│   ├── test_parser.py
│   ├── test_discovery.py
│   ├── test_normalize.py
│   ├── test_query.py
│   ├── test_llm_plans.py
│   ├── test_web.py
│   └── test_integration.py    # End-to-end with synthetic data
└── docs/
    ├── README.md              # Same as top-level
    ├── usage.md
    ├── web.md
    ├── llm-querying.md
    ├── adding-a-payer.md
    ├── code-classification-notes.md  # Profile taxonomy decisions and edge cases
    └── schema-2.0-notes.md    # Notes on quirks and edge cases
```

---

## Phasing

**Phase 1 (v0.1, 8-10 weeks part-time):** Single payer (BCBS Minnesota, since the URL pattern is the most predictable), Schema 2.0 only, parse subcommand only, no provider reference resolution (skip files using that pattern in v0.1), no batch subcommand, no query subcommand. Include the service-line profile registry from day one with `aba` and `radiology`. ABA is a good first smoke-test profile because the code set is tiny (97151-97156); radiology remains the richer classification target. Goal: end-to-end working extraction on one payer, clean Parquet output with service-line classification, solid README.

**Phase 2 (v0.2, additional 4-6 weeks):** Add 2-3 more payers (UHC and one BCBS regional), add provider reference resolution, add index subcommand, add tests against CMS example files.

**Phase 3 (v0.3, additional 4-6 weeks):** Add batch subcommand, add query subcommand, add CLI for adding custom payers without code changes, add docs site, ship to PyPI.

**Phase 4 (v0.4, additional 4-6 weeks):** Add local web view over Parquet output, including file inventory, faceted exploration, grouped summaries, and chart/table views. Keep the web app read-only in this phase.

**Phase 5 (v0.5, additional 3-5 weeks):** Add LLM-assisted querying in the web view and CLI `ask` command using OpenRouter with `google/gemma-4-31b-it` as the default model. Ship with strict query-plan validation, bounded result sets, prompt tests, and clear answer provenance.

**Phase 6 (v0.6+, ongoing):** Add allowed-amounts file support (out-of-network), add more payer shortcuts based on user requests, performance tuning, and optional hosted deployment patterns.

Total timeline to v0.5 is roughly 23-33 weeks of nights-and-weekends work. Realistic launch target is mid-to-late 2026 if work starts after the index goes live and stabilizes.

---

## Resources and references

CMS Transparency in Coverage technical implementation guide: https://github.com/CMSgov/price-transparency-guide

Schema 2.0 in-network rates schema: https://github.com/CMSgov/price-transparency-guide/tree/master/schemas/in-network-rates

Schema 2.0 example files: https://github.com/CMSgov/price-transparency-guide/tree/master/examples/in-network-rates

CMS validator tool: https://github.com/CMSgov/price-transparency-guide-validator

CMS technical clarifications and FAQ: https://www.cms.gov/healthplan-price-transparency/resources/technical-clarification

OpenRouter Gemma 4 31B model page: https://openrouter.ai/google/gemma-4-31b-it

ABA Coding Coalition billing code overview: https://abacodes.org/codes/

A reasonable starting test file: BCBS Minnesota's table of contents is publicly available at `https://mktg.bluecrossmn.com/mrf/2026/2026-05-01_Blue_Cross_and_Blue_Shield_of_Minnesota_index.json` (URL pattern updates monthly; the day is always `01`). The index is roughly 10MB and parseable in seconds; from there you can navigate to specific in-network rate files of varying sizes for development testing.

For initial development against synthetic data without downloading any real payer file, the CMS example file at `https://github.com/CMSgov/price-transparency-guide/blob/master/examples/in-network-rates/in-network-rates-fee-for-service-single-plan-sample.json` is the right starting point; small enough to hand-read, valid against the schema, exercises the main code paths.

---

## Open design questions

A few things worth thinking through before implementation starts:

The Parquet output schema needs a stable interface contract; downstream users will build queries against it and breaking changes are painful. Worth committing to a schema version in the output and treating column changes as breaking changes that bump the major version.

The "include_modifiers" flag on `parse` defaults to true (rates with modifiers are included as separate rows). The alternative is to default to global rates only and require the flag to opt into modifier rows; that produces smaller output but loses the TC/PC split which is the whole point of the radiology focus. Default-true is right but worth documenting.

Whether TC/PC/global columns should be booleans for all service lines or nullable booleans. Nullable booleans better communicate "not applicable" for ABA, but some downstream tools handle plain booleans more easily. Lean toward nullable booleans plus documented semantics.

Provider reference resolution adds I/O complexity and runtime; some payers' provider reference files are themselves multi-GB. Worth deciding whether to fetch all references or to defer resolution until actually needed (lazy resolution makes the data model harder but saves bandwidth). Probably fetch all in v1 for simplicity.

Whether to support Schema 1.0 at all. Argument for: some users may want to process historical files. Argument against: 1.0 is deprecated as of February 2026, supporting it doubles the parser surface area. Lean toward 2.0 only with a clear error message on 1.0 files.

Whether the web app should be server-rendered, a small static frontend over a JSON API, or a heavier SPA. Lean toward a small FastAPI/Starlette backend plus a minimal frontend because most complexity belongs in DuckDB query planning and validation, not client state.

How strict the LLM query planner should be. The safest approach is to let the model emit only JSON query plans from an allowlisted schema and never raw SQL. Raw SQL generation should stay out of scope unless it is behind an explicit developer mode.

How much data the LLM can see. Lean toward aggregate-only by default, with a hard cap on result rows and explicit user action for provider-level result sets. This reduces cost, latency, and accidental disclosure of large provider/rate tables to the model provider.

Whether to support multiple LLM providers in v0.5. OpenRouter should be the only provider-specific client initially, but the internal interface should be generic enough to add local models or another OpenAI-compatible provider later.

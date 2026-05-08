# mrf-rad

Early implementation of a CLI for service-line-focused extraction from Transparency in Coverage machine-readable files.

Current scope:

- Resolve the Blue Cross Blue Shield of Minnesota table-of-contents URL.
- Parse a table-of-contents JSON file or URL.
- Emit deduplicated in-network rate file references as JSON.
- Define initial service-line code profiles for radiology and ABA therapy.
- Serve a local web and JSON view over parsed Parquet output.

```bash
mrf-rad index bcbsmn --out bcbsmn-files.json
```

Add compressed file sizes to the index with HTTP HEAD requests:

```bash
mrf-rad index bcbsmn --include-sizes --out bcbsmn-files.json
```

Parse a local or HTTPS `.json.gz` in-network file into Parquet:

```bash
mrf-rad parse in-network.json.gz --profile aba --out aba.parquet
```

Batch parse every file listed by an index JSON:

```bash
mrf-rad batch bcbsmn-files.json --profile aba --out-dir parquet/aba
```

Use `--limit N` for smoke tests and `--overwrite` to rebuild existing outputs.
Use `--max-size-mb N` to skip indexed files above a compressed size cap. This
requires an index generated with `--include-sizes`.

Query parsed Parquet output with DuckDB:

```bash
mrf-rad query 'parquet/aba/*.parquet' \
  --service-line aba \
  --group-by billing_code,service_category \
  --summary
```

Use benchmark eligibility to exclude non-benchmarkable raw rows such as
percentage rates, institutional ABA rows, and extreme ABA outliers:

```bash
mrf-rad query 'parquet/aba/*.parquet' \
  --service-line aba \
  --benchmark-eligible \
  --group-by billing_code,service_category \
  --summary
```

Serve a small local web operator view over a Parquet glob:

```bash
mrf-rad web 'parquet/aba/*.parquet'
```

The web view lets you:

- point at a Parquet glob
- run saved query presets
- compare raw vs benchmark-eligible summaries
- drill into raw rows for a CPT such as `97153`

Bundled code profiles currently planned:

- `radiology`: CPT 70000-79999
- `aba`: CPT 97151-97156

Parser v0 handles both inline `provider_groups` and same-file `provider_references`.

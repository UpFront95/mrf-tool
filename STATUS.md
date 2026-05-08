# Status

- Core pipeline is working: `index`, `parse`, `batch`, `query`, and `web`.
- Profiles exist for `aba` and `radiology`.
- ABA benchmark filtering is in place and exposed in the web UI.
- BCBSMN has been tested live end to end.
- BSCA index has been loaded locally from `2026-05-01_Blue-Shield-of-California_index.json`.
- BSCA parses with the existing pipeline.

# Where We Are

- BSCA index shape is standard TiC TOC data with direct `in_network_files.location` URLs.
- BSCA under-`1 MB` ABA batch produced usable rows, but much of the ABA signal appears to overlap shared BC/BS network files rather than obviously payer-unique data.
- Some BSCA-linked dental files failed with remote `403` authorization errors.

# Next

- Add provenance fields so we can separate:
  - index payer
  - source file host
  - reporting entity inside the actual rate file
- Quantify overlap across BC/BS payers instead of inferring it from filenames.
- Decide whether BSCA should be the main working dataset or whether we should keep using shared BC/BS files for ABA benchmarking.

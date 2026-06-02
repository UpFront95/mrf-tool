# Payer Deployment Checklist

## Deployed

- [x] **UHC** — deployed 2026-06-01
  - `uhc-ohbs-aba` (Optum Health Behavioral Services, OHBS) — 20 MB, credential-tiered HM/HN/HO/HP, 2.24M rows
  - `uhc-bh-p3-aba` (Commercial PPO — Behavior Health P3) — 111 MB, provider-specific contracts, 1.43M rows
  - Both appear as `United HealthCare Services, Inc.` in the payer dropdown
  - Contract rate mapped to `UMR` in ContractRatesV2.csv

---

## Pending

- [x] **BCBS Massachusetts** — deployed 2026-06-01
  - 5 networks: Blue Care Elect, PAR Providers, Blue High Performance, HMO Blue Self Insured, New England Managed Care
  - ~200k rows, ~4,610 unique TINs, rate range $1.50–$214.51
  - Parsed from 2026-06-01 MRF
  - Deploy steps: same as UHC below — wrap in `bcbsma-aba/` dir, scp, restart

---

## Deployment steps (reference)

### Step 1 — Rename for production

```bash
cd ~/projects/mrf-tool/data/parquet

mkdir bcbsma-aba
cp bcbsma-aba-smoke/*.parquet bcbsma-aba/
```

### Step 2 — Copy to dixie

```bash
scp -r ~/projects/mrf-tool/data/parquet/bcbsma-aba dixie:/svr/data/mrf-tool/parquet/
```

### Step 3 — Verify files landed

```bash
ssh dixie "ls -lh /svr/data/mrf-tool/parquet/bcbsma-aba/"
```

### Step 4 — Restart the service

```bash
ssh dixie "systemctl --user restart mrf-rad && sleep 3 && systemctl --user status mrf-rad"
```

### Step 5 — Smoke test

```bash
curl -s -u card:p@nto http://192.168.4.90:8000/api/facets | python3 -m json.tool | grep -i bcbs
```

---

## Re-parse note

Parquets are parsed from the **2026-06-01 MRF snapshot**. Payers publish monthly. If more than ~6 weeks pass before deployment, consider re-running the parse against the current month's files. Source URLs are in the parquet metadata (`source_file_url` column).

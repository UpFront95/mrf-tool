#!/usr/bin/env python3
"""Fetch a HealthSparq / Kyruus payer's machine-readable-files table of contents.

HealthSparq-hosted payers (e.g. BCBS Arizona, Aetna) expose their MRF index only
through a small authenticated "dance":

    1. GET  /healthsparq/public/service/login?_=<ms>&insurerCode=..&brandCode=..
       -> sets a session cookie (the service returns HTTP 440 without one).
    2. POST /healthsparq/service/public/v2/mrf/all  {brandCode, insurerCode}
       -> {"url": "https://mrf.healthsparq.com/<egress>/.../latest_metadata.json"}
    3. GET  that url  -> {"files": [{reportingEntityName, reportingPlans, fileSchema,
                                     fileName, filePath}, ...]}

The metadata is camelCase and uses *relative* filePaths, so this script also emits a
tool-native index ({"in_network_files": [{location, description, reporting_plans}]})
whose `location` is the absolute egress URL — ready for `mrf-rad batch`.

Examples
--------
    # BCBS Arizona
    python scripts/fetch_healthsparq_toc.py \
        --host bcbsaz.healthsparq.com --insurer-code BCBSAZ_I --brand-code BCBSAZ \
        --meta-out data/index/bcbsaz-metadata.json \
        --index-out data/index/bcbsaz-index.json

    # Aetna (national)
    python scripts/fetch_healthsparq_toc.py \
        --host bcbsaz.healthsparq.com --insurer-code AETNACVS_I --brand-code ALICFI ...
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

# The HealthSparq service host sits behind Incapsula bot protection, which 403s
# Python's TLS fingerprint (httpx/requests). curl passes it reliably, so the
# authenticated dance is driven through curl with a shared cookie jar.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _curl(args: list[str]) -> bytes:
    out = subprocess.run(["curl", "-sS", "--fail", "-A", UA, *args], capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"curl failed ({out.returncode}): {out.stderr.decode(errors='replace')}")
    return out.stdout


def fetch_metadata(host: str, insurer_code: str, brand_code: str) -> tuple[dict, str]:
    """Run the 3-step dance via curl. Returns (metadata_dict, egress_base_url)."""
    base = f"https://{host}"
    ref = f"{base}/healthsparq/public/"
    with tempfile.TemporaryDirectory() as td:
        jar = str(Path(td) / "jar.txt")
        common = ["-c", jar, "-b", jar, "-H", f"Referer: {ref}", "-H", "Accept: application/json, text/plain, */*"]

        # 1. login -> session cookie
        ts = int(time.time() * 1000)
        _curl([*common, f"{base}/healthsparq/public/service/login?_={ts}&insurerCode={insurer_code}&brandCode={brand_code}"])

        # 2. resolve the metadata URL
        body = json.dumps({"brandCode": brand_code, "insurerCode": insurer_code})
        allr = _curl([*common, "-H", "Content-Type: application/json", "--data", body,
                      f"{base}/healthsparq/service/public/v2/mrf/all"])
        meta_url = json.loads(allr)["url"]

        # 3. fetch the metadata blob from the egress host
        meta = _curl([meta_url])
        egress_base = meta_url.rsplit("/", 1)[0] + "/"  # strip latest_metadata.json
        return json.loads(meta), egress_base


def to_index(metadata: dict, egress_base: str, source: str) -> dict:
    """Convert HealthSparq metadata into the tool-native index format."""
    files = []
    for f in metadata.get("files", []):
        if f.get("fileSchema") != "IN_NETWORK_RATES":
            continue
        plans = [
            {
                "plan_name": p.get("planName"),
                "plan_id_type": p.get("planIdType"),
                "plan_id": p.get("planId"),
                "issuer_name": None,
                "plan_market_type": p.get("planMarketType"),
                "plan_sponsor_name": None,
            }
            for p in f.get("reportingPlans", [])
        ]
        files.append(
            {
                "description": f.get("fileName"),
                "content_length_bytes": None,
                "location": urljoin(egress_base, f["filePath"]),
                "reporting_plan_count": len(plans),
                "reporting_plans": plans,
            }
        )
    # dedupe by location (many plans share one physical file)
    seen: dict[str, dict] = {}
    for f in files:
        if f["location"] in seen:
            seen[f["location"]]["reporting_plan_count"] += f["reporting_plan_count"]
            seen[f["location"]]["reporting_plans"].extend(f["reporting_plans"])
        else:
            seen[f["location"]] = f
    uniq = list(seen.values())
    return {
        "source": source,
        "reporting_entity_name": (metadata.get("files") or [{}])[0].get("reportingEntityName"),
        "reporting_entity_type": None,
        "last_updated_on": (metadata.get("files") or [{}])[0].get("lastUpdatedOn"),
        "version": None,
        "reporting_structure_count": len(metadata.get("files", [])),
        "in_network_file_count": len(uniq),
        "in_network_files": uniq,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True, help="HealthSparq host, e.g. bcbsaz.healthsparq.com")
    ap.add_argument("--insurer-code", required=True)
    ap.add_argument("--brand-code", required=True)
    ap.add_argument("--meta-out", help="write raw HealthSparq metadata JSON here")
    ap.add_argument("--index-out", help="write tool-native index JSON here")
    args = ap.parse_args()

    metadata, egress_base = fetch_metadata(args.host, args.insurer_code, args.brand_code)
    n = len(metadata.get("files", []))
    print(f"fetched metadata: {n} file entries; egress base {egress_base}")

    if args.meta_out:
        with open(args.meta_out, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh)
        print(f"wrote {args.meta_out}")
    if args.index_out:
        idx = to_index(metadata, egress_base, source=f"healthsparq:{args.insurer_code}/{args.brand_code}")
        with open(args.index_out, "w", encoding="utf-8") as fh:
            json.dump(idx, fh, indent=2)
        print(f"wrote {args.index_out}: {idx['in_network_file_count']} unique in-network files")


if __name__ == "__main__":
    main()

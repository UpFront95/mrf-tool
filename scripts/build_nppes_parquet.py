"""Rebuild npi_names.parquet from a raw NPPES CSV, adding primary_taxonomy."""
from __future__ import annotations

import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc
import pyarrow.parquet as pq

OUT = Path("/svr/data/nppes/npi_names.parquet")

TAX_CODE_COLS = [f"Healthcare Provider Taxonomy Code_{i}" for i in range(1, 16)]
TAX_SWITCH_COLS = [f"Healthcare Provider Primary Taxonomy Switch_{i}" for i in range(1, 16)]

KEEP = [
    "NPI",
    "Entity Type Code",
    "Provider Organization Name (Legal Business Name)",
    "Provider Last Name (Legal Name)",
    "Provider First Name",
    *TAX_CODE_COLS,
    *TAX_SWITCH_COLS,
]


def primary_taxonomy(table: pa.Table) -> pa.Array:
    """Return the primary taxonomy code for each row (first where Switch='Y', else first non-empty)."""
    n = len(table)
    result = [""] * n

    # Pass 1: primary-flagged taxonomy
    for code_col, switch_col in zip(TAX_CODE_COLS, TAX_SWITCH_COLS):
        if code_col not in table.schema.names:
            break
        codes = table[code_col].to_pylist()
        switches = table[switch_col].to_pylist()
        for i in range(n):
            if not result[i] and switches[i] == "Y" and codes[i]:
                result[i] = codes[i]

    # Pass 2: fall back to first non-empty
    for code_col in TAX_CODE_COLS:
        if code_col not in table.schema.names:
            break
        codes = table[code_col].to_pylist()
        for i in range(n):
            if not result[i] and codes[i]:
                result[i] = codes[i]

    return pa.array([v or None for v in result], type=pa.string())


def main(csv_path: str) -> None:
    print(f"Reading {csv_path} ...", flush=True)

    read_opts = pacsv.ReadOptions(block_size=128 * 1024 * 1024)
    convert_opts = pacsv.ConvertOptions(
        include_columns=KEEP,
        column_types={c: pa.string() for c in KEEP},
        strings_can_be_null=True,
        null_values=["", "NULL", "<UNAVAIL>"],
    )

    reader = pacsv.open_csv(csv_path, read_options=read_opts, convert_options=convert_opts)

    writer: pq.ParquetWriter | None = None
    total = 0

    for batch in reader:
        t = pa.Table.from_batches([batch])

        out = pa.table(
            {
                "npi": t["NPI"],
                "entity_type_code": t["Entity Type Code"],
                "organization_name": t["Provider Organization Name (Legal Business Name)"],
                "last_name": t["Provider Last Name (Legal Name)"],
                "first_name": t["Provider First Name"],
                "primary_taxonomy": primary_taxonomy(t),
            }
        )

        # Drop rows with no valid NPI
        mask = pc.and_(pc.is_valid(out["npi"]), pc.greater(pc.utf8_length(out["npi"]), pa.scalar(0)))
        out = out.filter(mask)

        if writer is None:
            writer = pq.ParquetWriter(OUT, out.schema, compression="snappy")

        writer.write_table(out)
        total += len(out)
        print(f"  {total:,} rows written", flush=True)

    if writer:
        writer.close()

    print(f"Done — {total:,} NPIs written to {OUT}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: build_nppes_parquet.py <nppes_csv_file>")
        sys.exit(1)
    main(sys.argv[1])

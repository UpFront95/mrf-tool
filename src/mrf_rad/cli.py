from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import uvicorn

from mrf_rad.discovery import IndexSource, parse_index
from mrf_rad.discovery.bcbsmn import current_index_url
from mrf_rad.batch import run_batch
from mrf_rad.parser import parse_file
from mrf_rad.probe import run_probe
from mrf_rad.query import run_query
from mrf_rad.web import create_app


def _resolve_source(value: str) -> str:
    if value.lower() == "bcbsmn":
        return current_index_url()
    return value


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Extract service-line rate data from Transparency in Coverage MRFs."""


@main.command()
@click.argument("payer_url_or_shortcut")
@click.option("--state", "state", help="Reserved for payer-specific state filtering.")
@click.option("--out", "out_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--include-duplicates",
    is_flag=True,
    help="Keep repeated file references across reporting structures.",
)
@click.option(
    "--include-sizes",
    is_flag=True,
    help="Fetch Content-Length for each in-network file with HTTP HEAD.",
)
def index(
    payer_url_or_shortcut: str,
    state: str | None,
    out_path: Path | None,
    include_duplicates: bool,
    include_sizes: bool,
) -> None:
    """Parse a payer table of contents and list in-network rate files."""
    if state:
        click.echo(
            "--state is accepted for CLI compatibility but is not used for BCBSMN yet.",
            err=True,
        )

    source = _resolve_source(payer_url_or_shortcut)
    result = parse_index(
        IndexSource(source),
        dedupe=not include_duplicates,
        include_sizes=include_sizes,
    )
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True)

    if out_path:
        out_path.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")


@main.command()
@click.argument("file_url_or_path")
@click.option(
    "--profile",
    "profile_name",
    default="radiology",
    show_default=True,
    type=click.Choice(["aba", "radiology"]),
)
@click.option("--out", "out_path", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--index-payer", default=None, help="Payer label from the source index (e.g. bsca, bcbsmn).")
def parse(file_url_or_path: str, profile_name: str, out_path: Path, index_payer: str | None) -> None:
    """Parse one in-network rate file into normalized Parquet."""
    result = parse_file(file_url_or_path, profile_name=profile_name, out_path=out_path, index_payer=index_payer)
    sys.stdout.write(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")


@main.command()
@click.argument("files_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--profile",
    "profile_name",
    default="radiology",
    show_default=True,
    type=click.Choice(["aba", "radiology"]),
)
@click.option("--out-dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--limit", type=int, help="Parse at most this many source files.")
@click.option(
    "--max-size-mb",
    type=float,
    help="Skip indexed files with content_length_bytes above this compressed size.",
)
@click.option("--overwrite", is_flag=True, help="Overwrite existing Parquet outputs.")
@click.option("--manifest", "manifest_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--index-payer", default=None, help="Payer label from the source index (e.g. bsca, bcbsmn).")
@click.option("--workers", default=1, show_default=True, type=int, help="Parallel parse workers.")
def batch(
    files_json: Path,
    profile_name: str,
    out_dir: Path,
    limit: int | None,
    max_size_mb: float | None,
    overwrite: bool,
    manifest_path: Path | None,
    index_payer: str | None,
    workers: int,
) -> None:
    """Parse every in-network file listed by an index JSON."""
    result = run_batch(
        files_json,
        profile_name=profile_name,
        out_dir=out_dir,
        index_payer=index_payer,
        workers=workers,
        limit=limit,
        max_size_mb=max_size_mb,
        overwrite=overwrite,
        manifest_path=manifest_path,
    )
    sys.stdout.write(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")


@main.command()
@click.argument("parquet_glob")
@click.option("--service-line")
@click.option("--cpt")
@click.option("--service-category")
@click.option("--payer")
@click.option("--modality")
@click.option("--body-region")
@click.option("--billing-class")
@click.option("--negotiated-type")
@click.option("--benchmark-eligible", is_flag=True)
@click.option("--min-rate", type=float)
@click.option("--max-rate", type=float)
@click.option("--group-by", help="Comma-separated grouping columns.")
@click.option("--summary", is_flag=True, help="Return count and rate distribution stats.")
@click.option("--limit", default=100, show_default=True, type=int)
def query(
    parquet_glob: str,
    service_line: str | None,
    cpt: str | None,
    service_category: str | None,
    payer: str | None,
    modality: str | None,
    body_region: str | None,
    billing_class: str | None,
    negotiated_type: str | None,
    benchmark_eligible: bool,
    min_rate: float | None,
    max_rate: float | None,
    group_by: str | None,
    summary: bool,
    limit: int,
) -> None:
    """Query parsed Parquet output with DuckDB."""
    result = run_query(
        parquet_glob,
        service_line=service_line,
        cpt=cpt,
        service_category=service_category,
        payer=payer,
        modality=modality,
        body_region=body_region,
        billing_class=billing_class,
        negotiated_type=negotiated_type,
        benchmark_eligible=benchmark_eligible,
        min_rate=min_rate,
        max_rate=max_rate,
        group_by=group_by,
        summary=summary,
        limit=limit,
    )
    sys.stdout.write(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n")


@main.command()
@click.argument("parquet_glob")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
def web(parquet_glob: str, host: str, port: int) -> None:
    """Serve a local web and JSON query UI for parsed Parquet output."""
    app = create_app(parquet_glob)
    uvicorn.run(app, host=host, port=port)


@main.command()
@click.argument("index_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--profile",
    "profile_name",
    default="aba",
    show_default=True,
    type=click.Choice(["aba", "radiology"]),
)
@click.option("--out", "out_path", type=click.Path(dir_okay=False, path_type=Path), help="JSONL output file.")
@click.option("--workers", default=8, show_default=True, type=int, help="Parallel download workers.")
@click.option("--limit-items", default=2000, show_default=True, type=int, help="Max in_network items to scan per file.")
@click.option("--full-scan", is_flag=True, help="Scan all limit-items even after a match (collect all codes).")
@click.option("--limit", type=int, help="Cap number of files from the index.")
def probe(
    index_json: Path,
    profile_name: str,
    out_path: Path | None,
    workers: int,
    limit_items: int,
    full_scan: bool,
    limit: int | None,
) -> None:
    """Fast-scan every file in an index to find which ones contain profile codes.

    Streams the first --limit-items in_network items from each file in parallel.
    By default stops at the first match (fast). Use --full-scan to collect all
    unique codes found within the item cap.

    Writes one JSON line per file to --out (or stdout) plus a summary.
    """
    results = run_probe(
        index_json,
        profile_name=profile_name,
        limit_items=limit_items,
        stop_on_match=not full_scan,
        workers=workers,
        limit=limit,
        out_path=out_path,
    )
    hits = sum(1 for r in results if r.has_aba)
    errors = sum(1 for r in results if r.status == "error")
    summary = {
        "total_files": len(results),
        "has_aba": hits,
        "errors": errors,
        "no_aba": len(results) - hits - errors,
    }
    if not out_path:
        for r in results:
            sys.stdout.write(json.dumps(r.to_dict(), sort_keys=True) + "\n")
    sys.stderr.write(json.dumps(summary, sort_keys=True) + "\n")


@main.command()
def payers() -> None:
    """List known payer shortcuts."""
    rows = [{"shortcut": "bcbsmn", "index_url": current_index_url()}]
    sys.stdout.write(json.dumps(rows, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

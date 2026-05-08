from __future__ import annotations

import json

from click.testing import CliRunner

from mrf_rad.cli import main
from mrf_rad.parser import parse_file
from mrf_rad.query import run_query
from tests.test_parser import write_fixture, write_reference_fixture


def write_parquet_outputs(tmp_path):
    fixture_a = write_fixture(tmp_path)
    fixture_b = write_reference_fixture(tmp_path)
    out_a = tmp_path / "a.parquet"
    out_b = tmp_path / "b.parquet"
    parse_file(fixture_a, profile_name="aba", out_path=out_a)
    parse_file(fixture_b, profile_name="aba", out_path=out_b)
    return str(tmp_path / "*.parquet")


def test_run_query_summary_grouped_by_code(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    result = run_query(
        parquet_glob,
        service_line="aba",
        group_by="billing_code,service_category",
        summary=True,
    )

    rows = sorted(result.rows, key=lambda row: row["billing_code"])
    assert [row["billing_code"] for row in rows] == ["97151", "97153"]
    assert rows[0]["row_count"] == 1
    assert rows[1]["median_rate"] == 42.5


def test_run_query_filters_by_cpt(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    result = run_query(parquet_glob, cpt="97153")

    assert len(result.rows) == 1
    assert result.rows[0]["billing_code"] == "97153"


def test_run_query_filters_by_rate_bounds(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    result = run_query(
        parquet_glob,
        summary=True,
        min_rate=40,
        max_rate=50,
    )

    assert result.rows[0]["row_count"] == 1
    assert result.rows[0]["median_rate"] == 42.5


def test_run_query_filters_to_benchmark_eligible_rows(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    result = run_query(
        parquet_glob,
        benchmark_eligible=True,
        group_by="billing_code,is_benchmark_eligible",
        summary=True,
    )

    assert {row["billing_code"] for row in result.rows} == {"97151", "97153"}
    assert all(row["is_benchmark_eligible"] for row in result.rows)


def test_run_query_rejects_unsupported_grouping(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    try:
        run_query(parquet_glob, group_by="not_a_column", summary=True)
    except ValueError as exc:
        assert "unsupported column" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_query_cli_outputs_json(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "query",
            parquet_glob,
            "--service-line",
            "aba",
            "--group-by",
            "billing_code",
            "--summary",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["row_count"] == 2

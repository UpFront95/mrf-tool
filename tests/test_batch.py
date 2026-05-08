from __future__ import annotations

import json

import pyarrow.parquet as pq
from click.testing import CliRunner

from mrf_rad.batch import output_name_for_source, run_batch
from mrf_rad.cli import main
from tests.test_parser import write_fixture, write_reference_fixture


def write_index(tmp_path, locations, sizes=None):
    sizes = sizes or {}
    path = tmp_path / "files.json"
    path.write_text(
        json.dumps(
            {
                "in_network_files": [
                    {
                        "location": location,
                        "description": "fixture",
                        "content_length_bytes": sizes.get(location),
                    }
                    for location in locations
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_output_name_for_source_uses_url_path_without_query():
    assert (
        output_name_for_source(
            "https://example.com/path/in-network-rates.json.gz?Signature=abc",
            "aba",
        )
        == "in-network-rates.aba.parquet"
    )


def test_run_batch_writes_manifest_and_outputs(tmp_path):
    fixture_a = write_fixture(tmp_path)
    fixture_b = write_reference_fixture(tmp_path)
    index_path = write_index(tmp_path, [str(fixture_a), str(fixture_b)])
    out_dir = tmp_path / "parquet"

    result = run_batch(index_path, profile_name="aba", out_dir=out_dir)

    assert result.attempted == 2
    assert result.succeeded == 2
    assert result.failed == 0
    outputs = sorted(out_dir.glob("*.parquet"))
    assert len(outputs) == 2
    assert sum(pq.read_table(path).num_rows for path in outputs) == 2

    events = [
        json.loads(line)
        for line in result.manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["status"] for event in events] == ["succeeded", "succeeded"]


def test_run_batch_skips_existing_outputs(tmp_path):
    fixture = write_fixture(tmp_path)
    index_path = write_index(tmp_path, [str(fixture)])
    out_dir = tmp_path / "parquet"

    first = run_batch(index_path, profile_name="aba", out_dir=out_dir)
    second = run_batch(index_path, profile_name="aba", out_dir=out_dir)

    assert first.succeeded == 1
    assert second.attempted == 0
    assert second.skipped == 1


def test_run_batch_skips_files_above_size_limit(tmp_path):
    small = write_fixture(tmp_path)
    large = write_reference_fixture(tmp_path)
    index_path = write_index(
        tmp_path,
        [str(small), str(large)],
        sizes={str(small): 1_000, str(large): 10_000_000},
    )
    out_dir = tmp_path / "parquet"

    result = run_batch(
        index_path,
        profile_name="aba",
        out_dir=out_dir,
        max_size_mb=1,
    )

    assert result.attempted == 1
    assert result.succeeded == 1
    assert result.skipped == 1
    events = [
        json.loads(line)
        for line in result.manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events[1]["reason"] == "file_too_large"


def test_batch_cli_outputs_summary(tmp_path):
    fixture = write_fixture(tmp_path)
    index_path = write_index(tmp_path, [str(fixture)])
    out_dir = tmp_path / "parquet"

    result = CliRunner().invoke(
        main,
        [
            "batch",
            str(index_path),
            "--profile",
            "aba",
            "--out-dir",
            str(out_dir),
            "--max-size-mb",
            "1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["succeeded"] == 1

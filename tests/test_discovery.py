from __future__ import annotations

import json

from click.testing import CliRunner

from mrf_rad.cli import main
from mrf_rad.discovery import IndexSource, parse_index
from mrf_rad.discovery.bcbsmn import index_url


def write_index(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps(
            {
                "reporting_entity_name": "Example Payer",
                "reporting_entity_type": "Health Insurance Issuer",
                "last_updated_on": "2026-05-01",
                "version": "2.0.0",
                "reporting_structure": [
                    {
                        "reporting_plans": [
                            {
                                "plan_name": "Plan A",
                                "plan_id_type": "ein",
                                "plan_id": "123",
                                "issuer_name": "Example",
                                "plan_market_type": "group",
                            }
                        ],
                        "in_network_files": [
                            {
                                "description": "National In-Network Negotiated Rates File",
                                "location": "https://example.com/rates-a.json.gz",
                                "content_length_bytes": 123,
                            }
                        ],
                    },
                    {
                        "reporting_plans": [
                            {
                                "plan_name": "Plan B",
                                "plan_id_type": "ein",
                                "plan_id": "456",
                                "issuer_name": "Example",
                                "plan_market_type": "group",
                            }
                        ],
                        "in_network_files": [
                            {
                                "description": "National In-Network Negotiated Rates File",
                                "location": "https://example.com/rates-a.json.gz",
                            },
                            {
                                "description": "Regional In-Network Negotiated Rates File",
                                "location": "https://example.com/rates-b.json.gz",
                            },
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_bcbsmn_index_url_matches_live_pattern():
    assert (
        index_url(2026, 5)
        == "https://mktg.bluecrossmn.com/mrf/2026/2026-05-01_Blue_Cross_and_Blue_Shield_of_Minnesota_index.json"
    )


def test_parse_index_dedupes_locations_and_counts_plans(tmp_path):
    path = write_index(tmp_path)

    result = parse_index(IndexSource(str(path)))

    assert result.reporting_entity_name == "Example Payer"
    assert result.reporting_structure_count == 2
    assert result.in_network_file_count == 2
    assert result.in_network_files[0].location == "https://example.com/rates-a.json.gz"
    assert result.in_network_files[0].reporting_plan_count == 2
    assert result.in_network_files[1].reporting_plan_count == 1
    assert result.in_network_files[0].to_dict()["content_length_bytes"] is None


def test_index_cli_writes_json(tmp_path):
    path = write_index(tmp_path)
    out_path = tmp_path / "files.json"

    result = CliRunner().invoke(main, ["index", str(path), "--out", str(out_path)])

    assert result.exit_code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["in_network_file_count"] == 2
    assert "content_length_bytes" in payload["in_network_files"][0]

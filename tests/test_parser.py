from __future__ import annotations

import gzip
import json

import pyarrow.parquet as pq
from click.testing import CliRunner

from mrf_rad.cli import main
from mrf_rad.parser import parse_file


def write_fixture(tmp_path):
    path = tmp_path / "in-network.json.gz"
    payload = {
        "reporting_entity_name": "Example Payer",
        "reporting_entity_type": "Health Insurance Issuer",
        "last_updated_on": "2026-05-01",
        "version": "2.0.0",
        "in_network": [
            {
                "negotiation_arrangement": "ffs",
                "name": "Adaptive behavior treatment by protocol",
                "billing_code_type": "CPT",
                "billing_code_type_version": "2026",
                "billing_code": "97153",
                "description": "Adaptive behavior treatment by protocol",
                "negotiated_rates": [
                    {
                        "provider_groups": [
                            {
                                "npi": [1111111111, 2222222222],
                                "tin": {"type": "ein", "value": "123456789"},
                            }
                        ],
                        "negotiated_prices": [
                            {
                                "negotiated_type": "negotiated",
                                "negotiated_rate": 42.5,
                                "expiration_date": "2026-12-31",
                                "service_code": ["11"],
                                "billing_class": "professional",
                                "setting": "office",
                                "billing_code_modifier": [],
                                "additional_information": "fixture row",
                            }
                        ],
                    }
                ],
            },
            {
                "negotiation_arrangement": "ffs",
                "name": "Office visit",
                "billing_code_type": "CPT",
                "billing_code_type_version": "2026",
                "billing_code": "99213",
                "description": "Office visit",
                "negotiated_rates": [],
            },
        ],
    }
    with gzip.open(path, "wt", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj)
    return path


def write_reference_fixture(tmp_path):
    path = tmp_path / "in-network-refs.json.gz"
    payload = {
        "reporting_entity_name": "Example Payer",
        "reporting_entity_type": "Health Insurance Issuer",
        "last_updated_on": "2026-05-01",
        "version": "2.0.0",
        "provider_references": [
            {
                "provider_group_id": 10,
                "provider_groups": [
                    {
                        "npi": [3333333333],
                        "tin": {"type": "ein", "value": "987654321"},
                    }
                ],
            }
        ],
        "in_network": [
            {
                "negotiation_arrangement": "ffs",
                "name": "Adaptive behavior assessment",
                "billing_code_type": "CPT",
                "billing_code_type_version": "2026",
                "billing_code": "97151",
                "description": "Adaptive behavior assessment",
                "negotiated_rates": [
                    {
                        "provider_references": [10],
                        "negotiated_prices": [
                            {
                                "negotiated_type": "negotiated",
                                "negotiated_rate": 100,
                                "expiration_date": "2026-12-31",
                                "service_code": ["11"],
                                "billing_class": "professional",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    with gzip.open(path, "wt", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj)
    return path


def test_parse_file_filters_profile_and_writes_parquet(tmp_path):
    fixture = write_fixture(tmp_path)
    out_path = tmp_path / "aba.parquet"

    result = parse_file(fixture, profile_name="aba", out_path=out_path)

    assert result.scanned_items == 2
    assert result.matched_items == 1
    assert result.rows_written == 1

    table = pq.read_table(out_path)
    row = table.to_pylist()[0]
    assert row["payer_name"] == "Example Payer"
    assert row["billing_code"] == "97153"
    assert row["service_line"] == "aba"
    assert row["service_category"] == "Direct Treatment"
    assert row["aba_provider_role"] == "technician"
    assert row["negotiated_rate"] == 42.5
    assert row["setting"] == "office"
    assert row["provider_npi_list"] == ["1111111111", "2222222222"]
    assert row["is_global"] is True
    assert row["is_benchmark_eligible"] is True


def test_parse_cli_outputs_summary(tmp_path):
    fixture = write_fixture(tmp_path)
    out_path = tmp_path / "aba.parquet"

    result = CliRunner().invoke(
        main,
        ["parse", str(fixture), "--profile", "aba", "--out", str(out_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows_written"] == 1
    assert out_path.exists()


def test_parse_file_resolves_provider_references(tmp_path):
    fixture = write_reference_fixture(tmp_path)
    out_path = tmp_path / "aba-refs.parquet"

    result = parse_file(fixture, profile_name="aba", out_path=out_path)

    assert result.rows_written == 1
    row = pq.read_table(out_path).to_pylist()[0]
    assert row["billing_code"] == "97151"
    assert row["provider_npi_list"] == ["3333333333"]
    assert row["provider_tin_value"] == "987654321"

from __future__ import annotations

from fastapi.testclient import TestClient

from mrf_rad.parser import parse_file
from mrf_rad.web import create_app
from tests.test_parser import write_fixture, write_reference_fixture


def write_parquet_outputs(tmp_path):
    fixture_a = write_fixture(tmp_path)
    fixture_b = write_reference_fixture(tmp_path)
    out_a = tmp_path / "a.parquet"
    out_b = tmp_path / "b.parquet"
    parse_file(fixture_a, profile_name="aba", out_path=out_a)
    parse_file(fixture_b, profile_name="aba", out_path=out_b)
    return str(tmp_path / "*.parquet")


def test_web_root_renders_default_glob(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)
    client = TestClient(create_app(parquet_glob))

    response = client.get("/")

    assert response.status_code == 200
    assert "mrf-rad web" in response.text
    assert parquet_glob in response.text
    assert 'id="negotiated_type"' in response.text


def test_web_presets_endpoint_lists_saved_queries(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)
    client = TestClient(create_app(parquet_glob))

    response = client.get("/api/presets")

    assert response.status_code == 200
    payload = response.json()
    assert {row["slug"] for row in payload} >= {
        "aba_raw_summary",
        "aba_benchmark_summary",
        "aba_97153_raw_rows",
    }
    assert payload[0]["slug"] == "aba_benchmark_summary"
    assert payload[0]["params"]["billing_class"] == "professional"
    assert payload[0]["params"]["benchmark_eligible"] is True


def test_web_query_endpoint_runs_summary(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)
    client = TestClient(create_app(parquet_glob))

    response = client.post(
        "/api/query",
        json={
            "service_line": "aba",
            "group_by": "billing_code,service_category",
            "summary": True,
            "limit": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 2
    assert {row["billing_code"] for row in payload["rows"]} == {"97151", "97153"}


def test_web_query_endpoint_returns_400_for_bad_grouping(tmp_path):
    parquet_glob = write_parquet_outputs(tmp_path)
    client = TestClient(create_app(parquet_glob))

    response = client.post(
        "/api/query",
        json={
            "group_by": "not_a_column",
            "summary": True,
        },
    )

    assert response.status_code == 400
    assert "unsupported column" in response.json()["detail"]

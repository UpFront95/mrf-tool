from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryPreset:
    slug: str
    label: str
    description: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "description": self.description,
            "params": self.params,
        }


def default_presets() -> list[QueryPreset]:
    return [
        QueryPreset(
            slug="aba_benchmark_summary",
            label="ABA Benchmark Summary",
            description="Grouped ABA summary for professional, benchmark-eligible rows.",
            params={
                "service_line": "aba",
                "billing_class": "professional",
                "benchmark_eligible": True,
                "group_by": "billing_code,service_category",
                "summary": True,
                "limit": 50,
            },
        ),
        QueryPreset(
            slug="aba_raw_summary",
            label="ABA Raw Summary",
            description="Grouped ABA summary across all raw rows.",
            params={
                "service_line": "aba",
                "group_by": "billing_code,service_category,billing_class,negotiated_type",
                "summary": True,
                "limit": 50,
            },
        ),
        QueryPreset(
            slug="aba_97153_raw_rows",
            label="97153 Raw Rows",
            description="Row-level drilldown for CPT 97153 without benchmark filtering.",
            params={
                "service_line": "aba",
                "cpt": "97153",
                "summary": False,
                "limit": 100,
            },
        ),
        QueryPreset(
            slug="aba_97153_benchmark_rows",
            label="97153 Benchmark Rows",
            description="Row-level drilldown for CPT 97153 with benchmark filtering.",
            params={
                "service_line": "aba",
                "cpt": "97153",
                "billing_class": "professional",
                "benchmark_eligible": True,
                "summary": False,
                "limit": 100,
            },
        ),
    ]

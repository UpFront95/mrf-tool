from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class IndexSource:
    location: str

    def read_text(self) -> str:
        parsed = urlparse(self.location)
        if parsed.scheme in {"http", "https"}:
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                response = client.get(self.location)
                response.raise_for_status()
                return response.text
        return Path(self.location).read_text(encoding="utf-8")


@dataclass(frozen=True)
class ReportingPlan:
    plan_name: str | None
    plan_id_type: str | None
    plan_id: str | None
    issuer_name: str | None
    plan_market_type: str | None
    plan_sponsor_name: str | None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ReportingPlan:
        return cls(
            plan_name=data.get("plan_name"),
            plan_id_type=data.get("plan_id_type"),
            plan_id=data.get("plan_id"),
            issuer_name=data.get("issuer_name"),
            plan_market_type=data.get("plan_market_type"),
            plan_sponsor_name=data.get("plan_sponsor_name"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "plan_name": self.plan_name,
            "plan_id_type": self.plan_id_type,
            "plan_id": self.plan_id,
            "issuer_name": self.issuer_name,
            "plan_market_type": self.plan_market_type,
            "plan_sponsor_name": self.plan_sponsor_name,
        }


@dataclass
class InNetworkFile:
    location: str
    description: str | None = None
    content_length_bytes: int | None = None
    reporting_plan_count: int = 0
    reporting_plans: list[ReportingPlan] = field(default_factory=list)

    @classmethod
    def from_json(
        cls,
        data: dict[str, Any],
        reporting_plans: list[ReportingPlan],
        include_plans: bool,
    ) -> InNetworkFile | None:
        location = data.get("location")
        if not isinstance(location, str) or not location:
            return None

        return cls(
            location=location,
            description=data.get("description"),
            reporting_plan_count=len(reporting_plans),
            reporting_plans=reporting_plans if include_plans else [],
        )

    def merge(self, other: InNetworkFile) -> None:
        if self.description is None:
            self.description = other.description
        if self.content_length_bytes is None:
            self.content_length_bytes = other.content_length_bytes
        self.reporting_plan_count += other.reporting_plan_count
        self.reporting_plans.extend(other.reporting_plans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "content_length_bytes": self.content_length_bytes,
            "location": self.location,
            "reporting_plan_count": self.reporting_plan_count,
            "reporting_plans": [plan.to_dict() for plan in self.reporting_plans],
        }


@dataclass(frozen=True)
class IndexFile:
    source: str
    reporting_entity_name: str | None
    reporting_entity_type: str | None
    last_updated_on: str | None
    version: str | None
    reporting_structure_count: int
    in_network_file_count: int
    in_network_files: list[InNetworkFile]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reporting_entity_name": self.reporting_entity_name,
            "reporting_entity_type": self.reporting_entity_type,
            "last_updated_on": self.last_updated_on,
            "version": self.version,
            "reporting_structure_count": self.reporting_structure_count,
            "in_network_file_count": self.in_network_file_count,
            "in_network_files": [file.to_dict() for file in self.in_network_files],
        }


def _fetch_content_length(client: httpx.Client, file_info: InNetworkFile) -> int | None:
    parsed = urlparse(file_info.location)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        response = client.head(file_info.location)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    content_length = response.headers.get("content-length")
    if content_length and content_length.isdigit():
        return int(content_length)
    return None


def enrich_file_sizes(files: list[InNetworkFile], *, workers: int = 16) -> None:
    with httpx.Client(follow_redirects=True, timeout=20.0) as client:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_fetch_content_length, client, file_info): file_info
                for file_info in files
            }
            for future in as_completed(futures):
                content_length = future.result()
                if content_length is not None:
                    futures[future].content_length_bytes = content_length


def parse_index(
    source: IndexSource,
    *,
    dedupe: bool = True,
    include_plans: bool = False,
    include_sizes: bool = False,
) -> IndexFile:
    raw = json.loads(source.read_text())
    structures = raw.get("reporting_structure", [])
    if not isinstance(structures, list):
        raise ValueError("table of contents has no reporting_structure array")

    files: list[InNetworkFile] = []
    by_location: dict[str, InNetworkFile] = {}

    for structure in structures:
        if not isinstance(structure, dict):
            continue

        reporting_plans = [
            ReportingPlan.from_json(plan)
            for plan in structure.get("reporting_plans", [])
            if isinstance(plan, dict)
        ]

        for file_data in structure.get("in_network_files", []):
            if not isinstance(file_data, dict):
                continue
            in_network_file = InNetworkFile.from_json(
                file_data,
                reporting_plans,
                include_plans,
            )
            if in_network_file is None:
                continue

            if dedupe:
                existing = by_location.get(in_network_file.location)
                if existing:
                    existing.merge(in_network_file)
                else:
                    by_location[in_network_file.location] = in_network_file
                    files.append(in_network_file)
            else:
                files.append(in_network_file)

    if include_sizes:
        enrich_file_sizes(files)

    return IndexFile(
        source=source.location,
        reporting_entity_name=raw.get("reporting_entity_name"),
        reporting_entity_type=raw.get("reporting_entity_type"),
        last_updated_on=raw.get("last_updated_on"),
        version=raw.get("version"),
        reporting_structure_count=len(structures),
        in_network_file_count=len(files),
        in_network_files=files,
    )

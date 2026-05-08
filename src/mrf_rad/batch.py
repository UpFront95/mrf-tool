from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mrf_rad.parser import parse_file


@dataclass(frozen=True)
class BatchResult:
    profile: str
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    manifest_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "manifest_path": str(self.manifest_path),
        }


def output_name_for_source(source: str, profile_name: str) -> str:
    path = urlparse(source).path
    name = Path(path).name or "in-network"
    for suffix in (".json.gz", ".json", ".gz"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return f"{name}.{profile_name}.parquet"


def load_index_locations(index_path: str | Path) -> list[str]:
    return [file_info["location"] for file_info in load_index_files(index_path)]


def load_index_files(index_path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(index_path).read_text(encoding="utf-8"))
    files = payload.get("in_network_files", [])
    return [
        file_info
        for file_info in files
        if isinstance(file_info, dict)
        and isinstance(file_info.get("location"), str)
    ]


def run_batch(
    index_path: str | Path,
    *,
    profile_name: str,
    out_dir: str | Path,
    index_payer: str | None = None,
    limit: int | None = None,
    max_size_mb: float | None = None,
    overwrite: bool = False,
    manifest_path: str | Path | None = None,
) -> BatchResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = Path(manifest_path) if manifest_path else out / f"manifest.{profile_name}.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    file_infos = load_index_files(index_path)
    if limit is not None:
        file_infos = file_infos[:limit]
    max_size_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb is not None else None

    attempted = 0
    succeeded = 0
    failed = 0
    skipped = 0

    with manifest.open("a", encoding="utf-8") as manifest_file:
        for file_info in file_infos:
            source = file_info["location"]
            output_path = out / output_name_for_source(source, profile_name)
            content_length = file_info.get("content_length_bytes")
            if (
                max_size_bytes is not None
                and isinstance(content_length, int)
                and content_length > max_size_bytes
            ):
                skipped += 1
                event = {
                    "status": "skipped",
                    "source": source,
                    "out_path": str(output_path),
                    "reason": "file_too_large",
                    "content_length_bytes": content_length,
                    "max_size_bytes": max_size_bytes,
                }
                manifest_file.write(json.dumps(event, sort_keys=True) + "\n")
                manifest_file.flush()
                continue

            if output_path.exists() and not overwrite:
                skipped += 1
                event = {
                    "status": "skipped",
                    "source": source,
                    "out_path": str(output_path),
                    "reason": "output_exists",
                    "content_length_bytes": content_length,
                }
                manifest_file.write(json.dumps(event, sort_keys=True) + "\n")
                manifest_file.flush()
                continue

            attempted += 1
            try:
                result = parse_file(
                    source,
                    profile_name=profile_name,
                    out_path=output_path,
                    index_payer=index_payer,
                )
            except Exception as exc:  # pragma: no cover - exact live failures vary.
                failed += 1
                event = {
                    "status": "failed",
                    "source": source,
                    "out_path": str(output_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            else:
                succeeded += 1
                event = {"status": "succeeded", **result.to_dict()}

            manifest_file.write(json.dumps(event, sort_keys=True) + "\n")
            manifest_file.flush()

    return BatchResult(
        profile=profile_name,
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        manifest_path=manifest,
    )

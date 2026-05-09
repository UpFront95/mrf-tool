from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    workers: int = 1,
    tmp_dir: str | None = None,
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
    lock = threading.Lock()

    def _write_event(manifest_file: Any, event: dict[str, Any]) -> None:
        with lock:
            manifest_file.write(json.dumps(event, sort_keys=True) + "\n")
            manifest_file.flush()

    def _should_skip(file_info: dict[str, Any], output_path: Path) -> dict[str, Any] | None:
        source = file_info["location"]
        content_length = file_info.get("content_length_bytes")
        if (
            max_size_bytes is not None
            and isinstance(content_length, int)
            and content_length > max_size_bytes
        ):
            return {
                "status": "skipped",
                "source": source,
                "out_path": str(output_path),
                "reason": "file_too_large",
                "content_length_bytes": content_length,
                "max_size_bytes": max_size_bytes,
            }
        if output_path.exists() and not overwrite:
            return {
                "status": "skipped",
                "source": source,
                "out_path": str(output_path),
                "reason": "output_exists",
                "content_length_bytes": content_length,
            }
        return None

    def _parse_one(file_info: dict[str, Any]) -> dict[str, Any]:
        source = file_info["location"]
        output_path = out / output_name_for_source(source, profile_name)
        try:
            result = parse_file(
                source,
                profile_name=profile_name,
                out_path=output_path,
                index_payer=index_payer,
                tmp_dir=tmp_dir,
            )
            return {"status": "succeeded", **result.to_dict()}
        except Exception as exc:  # pragma: no cover
            return {
                "status": "failed",
                "source": source,
                "out_path": str(output_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    with manifest.open("a", encoding="utf-8") as manifest_file:
        if workers <= 1:
            for file_info in file_infos:
                output_path = out / output_name_for_source(file_info["location"], profile_name)
                skip_event = _should_skip(file_info, output_path)
                if skip_event:
                    skipped += 1
                    _write_event(manifest_file, skip_event)
                    continue
                attempted += 1
                event = _parse_one(file_info)
                if event["status"] == "succeeded":
                    succeeded += 1
                else:
                    failed += 1
                _write_event(manifest_file, event)
        else:
            to_parse: list[dict[str, Any]] = []
            for file_info in file_infos:
                output_path = out / output_name_for_source(file_info["location"], profile_name)
                skip_event = _should_skip(file_info, output_path)
                if skip_event:
                    skipped += 1
                    _write_event(manifest_file, skip_event)
                else:
                    to_parse.append(file_info)
            attempted = len(to_parse)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_parse_one, fi): fi for fi in to_parse}
                for future in as_completed(futures):
                    event = future.result()
                    if event["status"] == "succeeded":
                        succeeded += 1
                    else:
                        failed += 1
                    _write_event(manifest_file, event)

    return BatchResult(
        profile=profile_name,
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        manifest_path=manifest,
    )

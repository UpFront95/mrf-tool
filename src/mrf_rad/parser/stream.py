from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from urllib.parse import urlparse
from urllib.request import urlopen

import ijson

from mrf_rad.codes import get_profile
from mrf_rad.output.parquet import ParquetRowWriter
from mrf_rad.parser.normalize import normalize_in_network_item


@dataclass(frozen=True)
class ParseResult:
    source: str
    profile: str
    scanned_items: int
    matched_items: int
    rows_written: int
    out_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "profile": self.profile,
            "scanned_items": self.scanned_items,
            "matched_items": self.matched_items,
            "rows_written": self.rows_written,
            "out_path": str(self.out_path),
        }


def _is_url(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def _is_gzip(source: str) -> bool:
    parsed = urlparse(source)
    name = parsed.path if parsed.scheme else source
    return name.endswith(".gz")


def _open_binary(source: str) -> BinaryIO:
    if _is_url(source):
        raw = urlopen(source, timeout=60)
    else:
        raw = Path(source).open("rb")

    if _is_gzip(source):
        return gzip.GzipFile(fileobj=raw)
    return raw


def _metadata(source: str) -> dict[str, Any]:
    wanted = {
        "reporting_entity_name",
        "reporting_entity_type",
        "last_updated_on",
        "version",
    }
    metadata: dict[str, Any] = {}
    with _open_binary(source) as file_obj:
        for prefix, event, value in ijson.parse(file_obj):
            if prefix == "in_network" and event == "start_array":
                break
            if prefix in wanted and event in {"string", "number", "boolean", "null"}:
                metadata[prefix] = value
    return metadata


class _ProviderRefStore:
    """SQLite-backed provider_references lookup — constant memory regardless of file size."""

    def __init__(self, conn: sqlite3.Connection, db_path: str):
        self._conn = conn
        self._db_path = db_path

    def __contains__(self, key: object) -> bool:
        return self._conn.execute("SELECT 1 FROM refs WHERE id=?", (key,)).fetchone() is not None

    def __getitem__(self, key: str) -> list[dict[str, Any]]:
        row = self._conn.execute("SELECT groups_json FROM refs WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def close(self) -> None:
        self._conn.close()
        try:
            os.unlink(self._db_path)
        except OSError:
            pass


def _provider_references(source: str, tmp_dir: str | None = None) -> _ProviderRefStore:
    fd, db_path = tempfile.mkstemp(suffix=".db", dir=tmp_dir)
    os.close(fd)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE refs (id TEXT PRIMARY KEY, groups_json TEXT)")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    batch: list[tuple[str, str]] = []
    with _open_binary(source) as file_obj:
        for reference in ijson.items(file_obj, "provider_references.item"):
            reference_id = reference.get("provider_group_id")
            provider_groups = reference.get("provider_groups", []) or []
            if reference_id is not None:
                batch.append((str(reference_id), json.dumps(provider_groups)))
                if len(batch) >= 1000:
                    conn.executemany("INSERT OR REPLACE INTO refs VALUES (?,?)", batch)
                    batch.clear()
    if batch:
        conn.executemany("INSERT OR REPLACE INTO refs VALUES (?,?)", batch)
    conn.commit()
    return _ProviderRefStore(conn, db_path)


def _in_network_items(source: str) -> Iterator[dict[str, Any]]:
    with _open_binary(source) as file_obj:
        yield from ijson.items(file_obj, "in_network.item")


def _download_to_temp(source: str, tmp_dir: str | None = None) -> str:
    """Download a remote file to a local temp file. Returns the temp file path."""
    suffix = ".json.gz" if _is_gzip(source) else ".json"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=tmp_dir)
    try:
        with urlopen(source, timeout=300) as resp, os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception:
        os.unlink(tmp_path)
        raise
    return tmp_path


def parse_file(
    source: str | Path,
    *,
    profile_name: str,
    out_path: str | Path,
    index_payer: str | None = None,
    tmp_dir: str | None = None,
) -> ParseResult:
    profile = get_profile(profile_name)
    source_name = str(source)
    out = Path(out_path)

    # Download remote files once; re-use local files directly.
    if _is_url(source_name):
        local = _download_to_temp(source_name, tmp_dir=tmp_dir)
        cleanup = True
    else:
        local = source_name
        cleanup = False

    try:
        metadata = _metadata(local)
        provider_references = _provider_references(local, tmp_dir=tmp_dir)
        try:
            scanned_items = 0
            matched_items = 0
            rows_written = 0

            with ParquetRowWriter(out) as writer:
                for item in _in_network_items(local):
                    scanned_items += 1
                    if not profile.contains(str(item.get("billing_code", ""))):
                        continue

                    matched_items += 1
                    rows = normalize_in_network_item(
                        item,
                        profile_name=profile.name,
                        metadata=metadata,
                        source_file_url=source_name,
                        index_payer=index_payer,
                        provider_references=provider_references,
                    )
                    writer.write_rows(rows)
                    rows_written += len(rows)
        finally:
            provider_references.close()
    finally:
        if cleanup:
            os.unlink(local)

    return ParseResult(
        source=source_name,
        profile=profile.name,
        scanned_items=scanned_items,
        matched_items=matched_items,
        rows_written=rows_written,
        out_path=out,
    )

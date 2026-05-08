from __future__ import annotations

import gzip
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse
from urllib.request import urlopen

import ijson

from mrf_rad.codes import get_profile


def _open_binary(source: str) -> BinaryIO:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        raw = urlopen(source, timeout=90)
    else:
        raw = Path(source).open("rb")
    if (parsed.path if parsed.scheme else source).endswith(".gz"):
        return gzip.GzipFile(fileobj=raw)  # type: ignore[return-value]
    return raw


@dataclass
class ProbeResult:
    source: str
    status: str
    items_scanned: int = 0
    has_aba: bool = False
    aba_codes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "items_scanned": self.items_scanned,
            "has_aba": self.has_aba,
            "aba_codes": self.aba_codes,
            "error": self.error,
        }


def probe_file(
    source: str,
    *,
    profile_name: str = "aba",
    limit_items: int = 2000,
    stop_on_match: bool = True,
) -> ProbeResult:
    profile = get_profile(profile_name)
    items_scanned = 0
    aba_codes: set[str] = set()
    try:
        with _open_binary(source) as f:
            for item in ijson.items(f, "in_network.item"):
                items_scanned += 1
                code = str(item.get("billing_code", ""))
                if profile.contains(code):
                    aba_codes.add(code)
                    if stop_on_match:
                        break
                if items_scanned >= limit_items:
                    break
    except Exception as exc:
        return ProbeResult(source=source, status="error", items_scanned=items_scanned, error=str(exc))

    return ProbeResult(
        source=source,
        status="ok",
        items_scanned=items_scanned,
        has_aba=bool(aba_codes),
        aba_codes=sorted(aba_codes),
    )


def run_probe(
    index_path: str | Path,
    *,
    profile_name: str = "aba",
    limit_items: int = 2000,
    stop_on_match: bool = True,
    workers: int = 8,
    limit: int | None = None,
    out_path: str | Path | None = None,
) -> list[ProbeResult]:
    payload = json.loads(Path(index_path).read_text(encoding="utf-8"))
    files = [
        f["location"]
        for f in payload.get("in_network_files", [])
        if isinstance(f, dict) and isinstance(f.get("location"), str)
    ]
    if limit is not None:
        files = files[:limit]

    total = len(files)
    results: list[ProbeResult] = []
    out_file = open(out_path, "w", encoding="utf-8") if out_path else None  # noqa: SIM115

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    probe_file,
                    source,
                    profile_name=profile_name,
                    limit_items=limit_items,
                    stop_on_match=stop_on_match,
                ): source
                for source in files
            }
            done = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                done += 1
                flag = "HIT " if result.has_aba else ("ERR " if result.status == "error" else "    ")
                click_echo = f"[{done:4d}/{total}] {flag} {result.source[:80]}"
                sys.stderr.write(click_echo + "\n")
                sys.stderr.flush()
                if out_file:
                    out_file.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
                    out_file.flush()
    finally:
        if out_file:
            out_file.close()

    return results

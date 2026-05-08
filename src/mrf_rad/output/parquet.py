from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


OUTPUT_SCHEMA = pa.schema(
    [
        ("index_payer", pa.string()),
        ("payer_name", pa.string()),
        ("reporting_entity_type", pa.string()),
        ("source_file_url", pa.string()),
        ("last_updated_on", pa.string()),
        ("schema_version", pa.string()),
        ("billing_code", pa.string()),
        ("billing_code_type", pa.string()),
        ("billing_code_type_version", pa.string()),
        ("name", pa.string()),
        ("description", pa.string()),
        ("service_line", pa.string()),
        ("service_category", pa.string()),
        ("service_subcategory", pa.string()),
        ("unit_basis", pa.string()),
        ("modality", pa.string()),
        ("body_region", pa.string()),
        ("with_contrast", pa.string()),
        ("aba_delivery_mode", pa.string()),
        ("aba_provider_role", pa.string()),
        ("negotiation_arrangement", pa.string()),
        ("billing_class", pa.string()),
        ("setting", pa.string()),
        ("negotiated_type", pa.string()),
        ("negotiated_rate", pa.float64()),
        ("percentage", pa.float64()),
        ("expiration_date", pa.string()),
        ("service_codes", pa.list_(pa.string())),
        ("billing_code_modifiers", pa.list_(pa.string())),
        ("is_technical_component", pa.bool_()),
        ("is_professional_component", pa.bool_()),
        ("is_global", pa.bool_()),
        ("is_benchmark_eligible", pa.bool_()),
        ("provider_npi_list", pa.list_(pa.string())),
        ("provider_tin_type", pa.string()),
        ("provider_tin_value", pa.string()),
        ("additional_information", pa.string()),
    ]
)


class ParquetRowWriter:
    def __init__(self, out_path: str | Path, *, batch_size: int = 100_000) -> None:
        self.out_path = Path(out_path)
        self.batch_size = batch_size
        self._writer: pq.ParquetWriter | None = None
        self._buffer: list[dict[str, Any]] = []

    def __enter__(self) -> ParquetRowWriter:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = pq.ParquetWriter(self.out_path, OUTPUT_SCHEMA)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.flush()
        if self._writer is not None:
            self._writer.close()

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        self._buffer.extend(rows)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        table = pa.Table.from_pylist(self._buffer, schema=OUTPUT_SCHEMA)
        if self._writer is None:
            raise RuntimeError("ParquetRowWriter is not open")
        self._writer.write_table(table)
        self._buffer.clear()

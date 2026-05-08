from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb


FILTER_COLUMNS = {
    "service_line",
    "billing_code",
    "service_category",
    "payer_name",
    "modality",
    "body_region",
    "billing_class",
    "negotiated_type",
    "setting",
}

GROUP_COLUMNS = FILTER_COLUMNS | {
    "service_subcategory",
    "aba_delivery_mode",
    "aba_provider_role",
    "billing_class",
    "negotiated_type",
    "setting",
    "is_benchmark_eligible",
}


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    sql: str
    parameters: list[Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": len(self.rows),
            "sql": self.sql,
            "parameters": self.parameters,
        }


def _split_columns(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _validate_columns(columns: list[str], allowed: set[str]) -> None:
    invalid = sorted(set(columns) - allowed)
    if invalid:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported column(s): {', '.join(invalid)}; allowed: {allowed_text}")


def _read_parquet_expr(parquet_glob: str) -> str:
    escaped = parquet_glob.replace("'", "''")
    return f"read_parquet('{escaped}', union_by_name=true)"


def run_query(
    parquet_glob: str,
    *,
    service_line: str | None = None,
    cpt: str | None = None,
    service_category: str | None = None,
    payer: str | None = None,
    modality: str | None = None,
    body_region: str | None = None,
    billing_class: str | None = None,
    negotiated_type: str | None = None,
    benchmark_eligible: bool = False,
    min_rate: float | None = None,
    max_rate: float | None = None,
    group_by: str | None = None,
    summary: bool = False,
    limit: int = 100,
) -> QueryResult:
    group_columns = _split_columns(group_by)
    _validate_columns(group_columns, GROUP_COLUMNS)

    filters = {
        "service_line": service_line,
        "billing_code": cpt,
        "service_category": service_category,
        "payer_name": payer,
        "modality": modality,
        "body_region": body_region,
        "billing_class": billing_class,
        "negotiated_type": negotiated_type,
    }
    where_parts: list[str] = []
    parameters: list[Any] = []
    for column, value in filters.items():
        if value is not None:
            where_parts.append(f"{column} = ?")
            parameters.append(value)
    if min_rate is not None:
        where_parts.append("negotiated_rate >= ?")
        parameters.append(min_rate)
    if max_rate is not None:
        where_parts.append("negotiated_rate <= ?")
        parameters.append(max_rate)
    if benchmark_eligible:
        where_parts.append("is_benchmark_eligible = true")

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    relation = _read_parquet_expr(parquet_glob)
    safe_limit = max(1, min(limit, 10_000))

    if summary:
        if group_columns:
            select_prefix = ", ".join(group_columns)
            group_sql = f"GROUP BY {select_prefix}"
            order_sql = f"ORDER BY {select_prefix}"
            select_sql = f"{select_prefix}, "
        else:
            group_sql = ""
            order_sql = ""
            select_sql = ""

        sql = f"""
            SELECT
              {select_sql}
              count(*) AS row_count,
              min(negotiated_rate) AS min_rate,
              quantile_cont(negotiated_rate, 0.25) AS p25_rate,
              median(negotiated_rate) AS median_rate,
              quantile_cont(negotiated_rate, 0.75) AS p75_rate,
              max(negotiated_rate) AS max_rate,
              avg(negotiated_rate) AS avg_rate
            FROM {relation}
            {where_sql}
            {group_sql}
            {order_sql}
            LIMIT {safe_limit}
        """
    else:
        columns = group_columns or [
            "payer_name",
            "billing_code",
            "service_category",
            "negotiated_rate",
            "billing_class",
            "setting",
            "negotiated_type",
            "is_benchmark_eligible",
            "provider_tin_value",
        ]
        select_sql = ", ".join(columns)
        sql = f"""
            SELECT {select_sql}
            FROM {relation}
            {where_sql}
            LIMIT {safe_limit}
        """

    with duckdb.connect(database=":memory:") as con:
        result = con.execute(sql, parameters)
        columns = [column[0] for column in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return QueryResult(
        columns=columns,
        rows=rows,
        sql=" ".join(sql.split()),
        parameters=parameters,
    )

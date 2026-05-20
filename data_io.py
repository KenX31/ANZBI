from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import streamlit as st


PARQUET_SUFFIX = ".parquet"
CSV_SUFFIX = ".csv"


def table_path_candidates(relative_path: str) -> list[str]:
    path = Path(relative_path)
    if path.suffix.casefold() != CSV_SUFFIX:
        return [relative_path]
    parquet_path = str(path.with_suffix(PARQUET_SUFFIX)).replace("\\", "/")
    return [parquet_path, relative_path] if parquet_path != relative_path else [relative_path]


def local_table_path_candidates(path: Path) -> list[Path]:
    if path.suffix.casefold() != CSV_SUFFIX:
        return [path]
    parquet_path = path.with_suffix(PARQUET_SUFFIX)
    return [parquet_path, path] if parquet_path != path else [path]


def read_local_table(path: Path, *, csv_dtypes: dict[str, str] | None = None) -> pd.DataFrame:
    for candidate in local_table_path_candidates(path):
        if not candidate.exists():
            continue
        return read_table_path(candidate, csv_dtypes=csv_dtypes)
    raise FileNotFoundError(path)


def read_table_path(path: Path, *, csv_dtypes: dict[str, str] | None = None) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == PARQUET_SUFFIX:
        return _coerce_string_columns(read_parquet_path(path), csv_dtypes)
    if suffix == CSV_SUFFIX:
        return pd.read_csv(path, dtype=csv_dtypes)
    raise ValueError(f"Unsupported table format: {path}")


def read_table_bytes(
    payload: bytes,
    *,
    relative_path: str,
    csv_dtypes: dict[str, str] | None = None,
) -> pd.DataFrame:
    suffix = Path(relative_path).suffix.casefold()
    if suffix == PARQUET_SUFFIX:
        return _coerce_string_columns(read_parquet_bytes(payload), csv_dtypes)
    if suffix == CSV_SUFFIX:
        return pd.read_csv(StringIO(payload.decode("utf-8-sig")), dtype=csv_dtypes)
    raise ValueError(f"Unsupported table format: {relative_path}")


def read_parquet_path(path: Path) -> pd.DataFrame:
    try:
        return duckdb_query_parquet_path(path)
    except Exception:
        table = pq.read_table(path)
        return table.to_pandas()


def read_parquet_bytes(payload: bytes) -> pd.DataFrame:
    table = pq.read_table(BytesIO(payload))
    return table.to_pandas()


@st.cache_resource(show_spinner=False)
def duckdb_connection() -> Any:
    import duckdb

    return duckdb.connect(database=":memory:")


def duckdb_query_parquet_path(
    path: Path,
    *,
    columns: list[str] | None = None,
    where_sql: str = "",
    parameters: tuple[Any, ...] = (),
) -> pd.DataFrame:
    select_sql = ", ".join(_quote_identifier(column) for column in columns) if columns else "*"
    sql = f"select {select_sql} from read_parquet(?)"
    query_parameters: list[Any] = [str(path)]
    if where_sql:
        sql = f"{sql} where {where_sql}"
        query_parameters.extend(parameters)
    return duckdb_connection().execute(sql, query_parameters).df()


def duckdb_parquet_columns(path: Path) -> list[str]:
    rows = duckdb_connection().execute("describe select * from read_parquet(?)", [str(path)]).fetchall()
    return [str(row[0]) for row in rows]


def duckdb_filter_frame(
    frame: pd.DataFrame,
    *,
    where_sql: str,
    parameters: tuple[Any, ...] = (),
) -> pd.DataFrame:
    connection = duckdb_connection()
    connection.register("_filter_frame", frame)
    try:
        return connection.execute(f"select * from _filter_frame where {where_sql}", parameters).df()
    finally:
        connection.unregister("_filter_frame")


def _coerce_string_columns(df: pd.DataFrame, csv_dtypes: dict[str, str] | None) -> pd.DataFrame:
    if not csv_dtypes or df.empty:
        return df
    out = df.copy()
    for column, dtype in csv_dtypes.items():
        if column in out.columns and str(dtype).lower() == "string":
            out[column] = out[column].astype("string")
    return out


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'

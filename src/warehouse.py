from __future__ import annotations

import duckdb

from src.config import db_path


def connect(*, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path = db_path()
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)

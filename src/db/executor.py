"""SqlExecutor -- vypolnyaet SQL-zapros na podklyuchennoy BD i vozvraschaet rezultat.

Primer:
    executor = SqlExecutor("sqlite:///data/demo/sales.sqlite")
    result = executor.run("SELECT SUM(amount) FROM orders WHERE status='paid'")
    print(result.columns)
    print(result.rows)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class QueryResult:
    """Rezultat vypolneniya SQL-zaprosa."""
    columns: list[str]
    rows: list[list]
    row_count: int
    sql: str
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "sql": self.sql,
            "error": self.error,
        }

    def to_markdown_table(self) -> str:
        if self.error:
            return f"Oshibka: {self.error}"
        if not self.rows:
            return "(pustoy rezultat)"
        header = " | ".join(self.columns)
        sep = " | ".join(["---"] * len(self.columns))
        rows = "\n".join(" | ".join(str(v) for v in row) for row in self.rows)
        return f"{header}\n{sep}\n{rows}"


class SqlExecutor:
    """Vypolnyaet SQL na podklyuchennoy BD."""

    MAX_ROWS = 500

    def __init__(self, connection_string: str):
        self.connection_string = connection_string.strip()
        self._db_type = self._detect_type(self.connection_string)

    def run(self, sql: str) -> QueryResult:
        try:
            if self._db_type == "sqlite":
                return self._run_sqlite(sql)
            elif self._db_type == "postgresql":
                return self._run_postgres(sql)
            elif self._db_type == "mysql":
                return self._run_mysql(sql)
            else:
                return QueryResult(columns=[], rows=[], row_count=0, sql=sql,
                                   error=f"Neizvestnyy tip BD: {self._db_type}")
        except Exception as e:
            return QueryResult(columns=[], rows=[], row_count=0, sql=sql, error=str(e))

    def _run_sqlite(self, sql: str) -> QueryResult:
        path = self._safe_sqlite_path(self._sqlite_path())
        conn = sqlite3.connect(str(path))
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in (cur.description or [])]
            rows = [list(r) for r in cur.fetchmany(self.MAX_ROWS)]
            return QueryResult(columns=cols, rows=rows, row_count=len(rows), sql=sql)
        finally:
            conn.close()

    def _run_postgres(self, sql: str) -> QueryResult:
        try:
            import psycopg2  # type: ignore
        except ImportError as e:
            raise ImportError("Ustanovi psycopg2: pip install psycopg2-binary") from e

        conn = psycopg2.connect(self.connection_string)
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in (cur.description or [])]
            rows = [list(r) for r in cur.fetchmany(self.MAX_ROWS)]
            return QueryResult(columns=cols, rows=rows, row_count=len(rows), sql=sql)
        finally:
            conn.close()

    def _run_mysql(self, sql: str) -> QueryResult:
        try:
            import pymysql  # type: ignore
        except ImportError as e:
            raise ImportError("Ustanovi pymysql: pip install pymysql") from e

        parsed = urlparse(self.connection_string)
        conn = pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
        )
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in (cur.description or [])]
            rows = [list(r) for r in cur.fetchmany(self.MAX_ROWS)]
            return QueryResult(columns=cols, rows=rows, row_count=len(rows), sql=sql)
        finally:
            conn.close()

    def _sqlite_path(self) -> Path:
        cs = self.connection_string
        if cs.startswith("sqlite:///"):
            return Path(cs[10:])
        return Path(cs)

    @staticmethod
    def _safe_sqlite_path(path: Path) -> Path:
        import shutil
        import tempfile
        journal = Path(str(path) + "-journal")
        wal = Path(str(path) + "-wal")
        if journal.exists() or wal.exists():
            tmp = Path(tempfile.mktemp(suffix=".sqlite"))
            shutil.copy2(path, tmp)
            return tmp
        return path

    @staticmethod
    def _detect_type(cs: str) -> str:
        if cs.startswith("sqlite") or cs.endswith(".sqlite") or cs.endswith(".db"):
            return "sqlite"
        if cs.startswith("postgresql") or cs.startswith("postgres"):
            return "postgresql"
        if cs.startswith("mysql"):
            return "mysql"
        raise ValueError(f"Ne udalos opredelit tip BD: {cs}")

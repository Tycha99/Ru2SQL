"""SqlExecutor — выполняет SQL-запрос на подключённой БД.

Для SQLite соединение открывается через URI с ``mode=ro&immutable=1`` —
это обеспечивает read-only без копирования файла и режет любые попытки
выполнить DDL/DML на уровне драйвера. Для PostgreSQL/MySQL отдельный
guardrail остаётся на стороне API (см. is_select_only в postprocess.py).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Результат выполнения SQL-запроса."""
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
            return f"Ошибка: {self.error}"
        if not self.rows:
            return "(пустой результат)"
        header = " | ".join(self.columns)
        sep = " | ".join(["---"] * len(self.columns))
        rows = "\n".join(" | ".join(str(v) for v in row) for row in self.rows)
        return f"{header}\n{sep}\n{rows}"


class SqlExecutor:
    """Выполняет SQL на подключённой БД."""

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
                                   error=f"Неизвестный тип БД: {self._db_type}")
        except Exception as e:  # noqa: BLE001
            logger.warning("Ошибка выполнения SQL: %s", e)
            return QueryResult(columns=[], rows=[], row_count=0, sql=sql, error=str(e))

    def _run_sqlite(self, sql: str) -> QueryResult:
        path = self._sqlite_path()
        conn = sqlite3.connect(self._sqlite_uri(path), uri=True)
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
            raise ImportError("Установи psycopg2: pip install psycopg2-binary") from e

        conn = psycopg2.connect(self.connection_string)
        try:
            # Транзакция в режиме READ ONLY — guardrail драйверного уровня.
            conn.set_session(readonly=True, autocommit=False)
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
            raise ImportError("Установи pymysql: pip install pymysql") from e

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
            # MySQL не имеет «глобального» read-only флага в драйвере,
            # но мы можем стартовать read-only-транзакцию.
            cur.execute("START TRANSACTION READ ONLY")
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
    def _sqlite_uri(path: Path) -> str:
        """Read-only URI для SQLite с игнорированием journal/WAL."""
        return f"file:{path}?mode=ro&immutable=1"

    @staticmethod
    def _detect_type(cs: str) -> str:
        if cs.startswith("sqlite") or cs.endswith(".sqlite") or cs.endswith(".db"):
            return "sqlite"
        if cs.startswith("postgresql") or cs.startswith("postgres"):
            return "postgresql"
        if cs.startswith("mysql"):
            return "mysql"
        raise ValueError(f"Не удалось определить тип БД: {cs}")

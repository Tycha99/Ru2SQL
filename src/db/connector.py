"""DbConnector — подключение к произвольной БД и чтение схемы.

Поддерживаемые типы БД:
    SQLite     — путь к файлу: "sqlite:///path/to/db.sqlite" или просто путь
    PostgreSQL — "postgresql://user:pass@host:port/dbname" (требует psycopg2)
    MySQL      — "mysql://user:pass@host:port/dbname"      (требует pymysql)

Пример:
    conn = DbConnector("sqlite:///data/demo/sales.sqlite")
    print(conn.render_schema())
    tables = conn.list_tables()
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    sample_rows: list[tuple] = field(default_factory=list)

    def to_ddl(self) -> str:
        """Генерирует CREATE TABLE statement из метаданных."""
        col_parts = []
        for col in self.columns:
            line = f"    {col.name} {col.type}"
            if col.primary_key:
                line += " PRIMARY KEY"
            if not col.nullable:
                line += " NOT NULL"
            col_parts.append(line)
        return f"CREATE TABLE {self.name} (\n" + ",\n".join(col_parts) + "\n);"


class DbConnector:
    """Универсальный коннектор к БД. Читает схему для подстановки в промпт."""

    def __init__(self, connection_string: str, n_sample_rows: int = 2):
        self.connection_string = self._normalize(connection_string)
        self.n_sample_rows = n_sample_rows
        self._db_type = self._detect_type(self.connection_string)

    def list_tables(self) -> list[str]:
        return [t.name for t in self._get_tables(n_sample_rows=0)]

    def get_schema(self, include_samples: bool = True) -> list[TableInfo]:
        return self._get_tables(n_sample_rows=self.n_sample_rows if include_samples else 0)

    def render_schema(self, include_samples: bool = True) -> str:
        tables = self.get_schema(include_samples=include_samples)
        parts: list[str] = []
        for t in tables:
            parts.append(t.to_ddl())
            if include_samples and t.sample_rows:
                parts.append(f"-- Примеры строк из {t.name}:")
                for row in t.sample_rows:
                    parts.append(f"--   {row}")
            parts.append("")
        return "\n".join(parts).strip()

    def test_connection(self) -> bool:
        try:
            self._get_tables(n_sample_rows=0)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Подключение к БД не удалось: %s", e)
            return False

    def _get_tables(self, n_sample_rows: int) -> list[TableInfo]:
        if self._db_type == "sqlite":
            return self._get_tables_sqlite(n_sample_rows)
        elif self._db_type == "postgresql":
            return self._get_tables_postgres(n_sample_rows)
        elif self._db_type == "mysql":
            return self._get_tables_mysql(n_sample_rows)
        else:
            raise ValueError(f"Неизвестный тип БД: {self._db_type}")

    def _get_tables_sqlite(self, n_sample_rows: int) -> list[TableInfo]:
        """SQLite-подключение в режиме read-only через URI.

        immutable=1 говорит SQLite, что файл не изменяется во время сессии,
        поэтому journal/WAL-файлы можно игнорировать. Это убирает прежнюю
        логику с копированием БД во временную директорию и заодно даёт
        guardrail-уровень безопасности: любая модифицирующая операция
        на таком соединении завершится ошибкой.
        """
        path = self._sqlite_path()
        conn = sqlite3.connect(self._sqlite_uri(path), uri=True)
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            table_names = [r[0] for r in cur.fetchall()]
            tables: list[TableInfo] = []
            for name in table_names:
                cur.execute(f'PRAGMA table_info("{name}")')
                cols = [
                    ColumnInfo(
                        name=row[1],
                        type=row[2] or "TEXT",
                        nullable=not row[3],
                        primary_key=bool(row[5]),
                    )
                    for row in cur.fetchall()
                ]
                samples: list[tuple] = []
                if n_sample_rows > 0:
                    try:
                        cur.execute(f'SELECT * FROM "{name}" LIMIT {n_sample_rows}')
                        samples = cur.fetchall()
                    except sqlite3.Error as e:
                        logger.debug("Не удалось получить sample-строки для %s: %s",
                                     name, e)
                tables.append(TableInfo(name=name, columns=cols, sample_rows=samples))
            return tables
        finally:
            conn.close()

    def _get_tables_postgres(self, n_sample_rows: int) -> list[TableInfo]:
        try:
            import psycopg2  # type: ignore
        except ImportError as e:
            raise ImportError("Установи psycopg2: pip install psycopg2-binary") from e

        conn = psycopg2.connect(self.connection_string)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            )
            table_names = [r[0] for r in cur.fetchall()]
            tables: list[TableInfo] = []
            for name in table_names:
                cur.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_name = %s AND table_schema = 'public' "
                    "ORDER BY ordinal_position",
                    (name,),
                )
                cols = [
                    ColumnInfo(name=r[0], type=r[1], nullable=(r[2] == "YES"))
                    for r in cur.fetchall()
                ]
                samples: list[tuple] = []
                if n_sample_rows > 0:
                    cur.execute(f'SELECT * FROM "{name}" LIMIT {n_sample_rows}')
                    samples = cur.fetchall()
                tables.append(TableInfo(name=name, columns=cols, sample_rows=samples))
            return tables
        finally:
            conn.close()

    def _get_tables_mysql(self, n_sample_rows: int) -> list[TableInfo]:
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
            cur.execute("SHOW TABLES")
            table_names = [r[0] for r in cur.fetchall()]
            tables: list[TableInfo] = []
            for name in table_names:
                cur.execute(f"DESCRIBE `{name}`")
                cols = [
                    ColumnInfo(
                        name=r[0], type=r[1],
                        nullable=(r[2] == "YES"),
                        primary_key=(r[3] == "PRI"),
                    )
                    for r in cur.fetchall()
                ]
                samples: list[tuple] = []
                if n_sample_rows > 0:
                    cur.execute(f"SELECT * FROM `{name}` LIMIT {n_sample_rows}")
                    samples = cur.fetchall()
                tables.append(TableInfo(name=name, columns=cols, sample_rows=samples))
            return tables
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
    def _normalize(cs: str) -> str:
        """Если передан просто путь к файлу — превращаем в sqlite:// URI.

        Если строка уже выглядит как URI (sqlite/postgres/mysql) —
        возвращаем как есть. Без этой проверки сценарий «передали
        корректный sqlite:///path» приводил к двойной нормализации
        и подключению к несуществующему пути.
        """
        cs = cs.strip()
        if cs.startswith(("sqlite:", "postgres", "mysql")):
            return cs
        if cs.endswith(".sqlite") or cs.endswith(".db"):
            return f"sqlite:///{cs}"
        return cs

    @staticmethod
    def _detect_type(cs: str) -> str:
        if cs.startswith("sqlite"):
            return "sqlite"
        if cs.startswith("postgresql") or cs.startswith("postgres"):
            return "postgresql"
        if cs.startswith("mysql"):
            return "mysql"
        raise ValueError(f"Не удалось определить тип БД: {cs}")

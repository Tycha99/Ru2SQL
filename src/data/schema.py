"""SchemaRetriever — извлекает DDL и примеры строк из SQLite-файлов PAUQ/Spider."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TableInfo:
    name: str
    create_sql: str
    sample_rows: list[tuple]


class SchemaRetriever:
    """Читает структуру SQLite-БД для подачи в prompt модели."""

    def __init__(self, databases_dir: Path | str):
        self.databases_dir = Path(databases_dir)

    def db_path(self, db_id: str) -> Path:
        """В Spider/PAUQ каждая БД лежит в databases_dir/{db_id}/{db_id}.sqlite."""
        path = self.databases_dir / db_id / f"{db_id}.sqlite"
        if not path.exists():
            raise FileNotFoundError(f"Database file not found: {path}")
        return path

    def get_tables(self, db_id: str, n_sample_rows: int = 3) -> list[TableInfo]:
        """Возвращает список таблиц с CREATE-SQL и примером строк."""
        path = self.db_path(db_id)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
            cur = conn.cursor()
            cur.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            rows = cur.fetchall()

            tables: list[TableInfo] = []
            for table_name, create_sql in rows:
                if not create_sql:
                    continue
                try:
                    cur.execute(f'SELECT * FROM "{table_name}" LIMIT {n_sample_rows}')
                    samples = cur.fetchall()
                except sqlite3.Error:
                    samples = []
                tables.append(
                    TableInfo(name=table_name, create_sql=create_sql.strip(), sample_rows=samples)
                )
            return tables
        finally:
            conn.close()

    def render_schema(self, db_id: str, include_samples: bool = True) -> str:
        """Текстовое представление схемы для prompt'а."""
        tables = self.get_tables(db_id)
        parts: list[str] = []
        for t in tables:
            parts.append(t.create_sql + ";")
            if include_samples and t.sample_rows:
                parts.append(f"-- Примеры строк из {t.name}:")
                for row in t.sample_rows:
                    parts.append(f"-- {row}")
            parts.append("")
        return "\n".join(parts).strip()

    def list_databases(self) -> list[str]:
        """Список доступных db_id."""
        if not self.databases_dir.exists():
            return []
        return sorted(p.name for p in self.databases_dir.iterdir() if p.is_dir())

"""Единый интерфейс работы со схемами баз данных.

До рефакторинга в проекте существовали две независимые иерархии:

* ``SchemaRetriever`` (``src/data/schema.py``) — читал DDL из SQLite-файлов
  в Spider/PAUQ-структуре ``{databases_dir}/{db_id}/{db_id}.sqlite``.
* ``DbConnector`` (``src/db/connector.py``) — подключался к произвольной БД
  по строке подключения, умел SQLite/PostgreSQL/MySQL.

Они решали одну задачу, но по-разному оформляли результат
(``TableInfo`` в каждом был свой) и не имели общего интерфейса. Этот
модуль вводит единый протокол ``SchemaProvider`` и общий dataclass
``TableSchema``. Старые классы становятся тонкими фасадами поверх
новых реализаций.

Соответствует разделам 3.4 и 4.1 пояснительной записки.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol


@dataclass
class ColumnSchema:
    """Описание колонки таблицы."""

    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


@dataclass
class TableSchema:
    """Унифицированное описание таблицы независимо от источника схемы.

    Поле ``create_sql`` хранит исходный CREATE TABLE statement, если он
    доступен (актуально для SQLite — он его сам отдаёт из ``sqlite_master``).
    Когда источник схемы — PostgreSQL/MySQL, DDL генерируется из
    метаданных через :meth:`to_ddl`.
    """

    name: str
    columns: list[ColumnSchema] = field(default_factory=list)
    sample_rows: list[tuple] = field(default_factory=list)
    create_sql: str | None = None

    def to_ddl(self) -> str:
        """CREATE TABLE для подстановки в промпт.

        Если есть оригинальный ``create_sql`` — возвращаем его, чтобы
        сохранить все нюансы (ограничения, FK, AUTOINCREMENT). Иначе
        собираем из метаданных колонок.
        """
        if self.create_sql:
            return self.create_sql.rstrip(";") + ";"
        col_parts: list[str] = []
        for col in self.columns:
            line = f"    {col.name} {col.type}"
            if col.primary_key:
                line += " PRIMARY KEY"
            if not col.nullable:
                line += " NOT NULL"
            col_parts.append(line)
        return f"CREATE TABLE {self.name} (\n" + ",\n".join(col_parts) + "\n);"


class SchemaProvider(Protocol):
    """Протокол любого источника схемы базы данных.

    Контракт минимальный: уметь перечислить таблицы и отрендерить схему
    в текст для подстановки в промпт. Этого достаточно и для PAUQ-сценария
    (``SpiderSchemaProvider``), и для подключения к боевой БД пользователя
    (``ConnectionSchemaProvider``).
    """

    def list_tables(self) -> list[str]: ...
    def get_tables(self, n_sample_rows: int = 3) -> list[TableSchema]: ...
    def render_schema(self, include_samples: bool = True) -> str: ...


# ──────────────────────────────────────────────────────────────────────
# Утилита рендеринга — общая для всех реализаций
# ──────────────────────────────────────────────────────────────────────

def render_tables(tables: Iterable[TableSchema], include_samples: bool = True) -> str:
    """Собирает текстовое представление списка таблиц для промпта."""
    parts: list[str] = []
    for t in tables:
        parts.append(t.to_ddl())
        if include_samples and t.sample_rows:
            parts.append(f"-- Примеры строк из {t.name}:")
            for row in t.sample_rows:
                parts.append(f"--   {row}")
        parts.append("")
    return "\n".join(parts).strip()


# ──────────────────────────────────────────────────────────────────────
# Реализация 1 — Spider/PAUQ-структура
# ──────────────────────────────────────────────────────────────────────

class SpiderSchemaProvider:
    """SchemaProvider для каталога ``data/databases/{db_id}/{db_id}.sqlite``.

    Используется при работе с PAUQ/Spider: каждая БД лежит в одноимённой
    папке. Один экземпляр SpiderSchemaProvider обслуживает всю коллекцию
    баз — конкретная БД выбирается по ``db_id`` в методах.
    """

    def __init__(self, databases_dir: Path | str):
        self.databases_dir = Path(databases_dir)

    def list_databases(self) -> list[str]:
        if not self.databases_dir.exists():
            return []
        return sorted(p.name for p in self.databases_dir.iterdir() if p.is_dir())

    def db_path(self, db_id: str) -> Path:
        path = self.databases_dir / db_id / f"{db_id}.sqlite"
        if not path.exists():
            raise FileNotFoundError(f"Database file not found: {path}")
        return path

    def for_database(self, db_id: str) -> "ConnectionSchemaProvider":
        """Возвращает SchemaProvider, привязанный к конкретной БД."""
        return ConnectionSchemaProvider(f"sqlite:///{self.db_path(db_id)}")

    # ── Совместимость с предыдущим API SchemaRetriever ────────────────

    def get_tables(self, db_id: str, n_sample_rows: int = 3) -> list[TableSchema]:
        return self.for_database(db_id).get_tables(n_sample_rows=n_sample_rows)

    def render_schema(self, db_id: str, include_samples: bool = True) -> str:
        return self.for_database(db_id).render_schema(include_samples=include_samples)


# ──────────────────────────────────────────────────────────────────────
# Реализация 2 — произвольная БД по connection string
# ──────────────────────────────────────────────────────────────────────

class ConnectionSchemaProvider:
    """SchemaProvider для произвольной БД (SQLite/PostgreSQL/MySQL).

    Делегирует чтение DbConnector'у, но возвращает объекты единого типа
    ``TableSchema``. Это нужно, чтобы один и тот же код в API и Streamlit
    мог работать как с PAUQ-структурой, так и с боевой БД пользователя.
    """

    def __init__(self, connection_string: str, n_sample_rows: int = 2):
        # Импорт здесь, чтобы избежать кольцевой зависимости
        # (db.connector → data.schema_provider в случае фасада).
        from src.db.connector import DbConnector
        self._connector = DbConnector(connection_string, n_sample_rows=n_sample_rows)
        self.connection_string = self._connector.connection_string

    # ── Базовые операции SchemaProvider ───────────────────────────────

    def list_tables(self) -> list[str]:
        return self._connector.list_tables()

    def get_tables(self, n_sample_rows: int = 3) -> list[TableSchema]:
        # DbConnector в текущей реализации использует свой n_sample_rows из ctor;
        # для совместимости с протоколом — игнорируем параметр здесь, доверяя
        # настройке коннектора. При желании можно завести setter.
        raw = self._connector.get_schema(include_samples=n_sample_rows > 0)
        return [
            TableSchema(
                name=t.name,
                columns=[
                    ColumnSchema(
                        name=c.name, type=c.type,
                        nullable=c.nullable, primary_key=c.primary_key,
                    )
                    for c in t.columns
                ],
                sample_rows=list(t.sample_rows),
            )
            for t in raw
        ]

    def render_schema(self, include_samples: bool = True) -> str:
        return render_tables(self.get_tables(n_sample_rows=2 if include_samples else 0),
                             include_samples=include_samples)

    def test_connection(self) -> bool:
        return self._connector.test_connection()

"""Тесты на единый SchemaProvider (раздел 4.2 аудита).

Покрывают обе реализации: SpiderSchemaProvider (структура PAUQ/Spider)
и ConnectionSchemaProvider (произвольное подключение к SQLite-файлу).
"""

import sqlite3
from pathlib import Path

import pytest

from src.data.schema_provider import (
    ColumnSchema,
    ConnectionSchemaProvider,
    SpiderSchemaProvider,
    TableSchema,
    render_tables,
)


# ──────────────────────────────────────────────────────────────────────
# Фикстуры
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def spider_dir(tmp_path: Path) -> Path:
    """data/databases/uni/uni.sqlite + data/databases/sales/sales.sqlite."""
    for db_id in ("uni", "sales"):
        (tmp_path / db_id).mkdir()
        db = tmp_path / db_id / f"{db_id}.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(f"CREATE TABLE {db_id}_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute(f"INSERT INTO {db_id}_t VALUES (1, '{db_id}-row')")
        conn.commit()
        conn.close()
    return tmp_path


@pytest.fixture
def tiny_db(tmp_path: Path) -> Path:
    db = tmp_path / "tiny.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO users VALUES (?, ?)", [(1, "Иван"), (2, "Анна")])
    conn.commit()
    conn.close()
    return db


# ──────────────────────────────────────────────────────────────────────
# TableSchema.to_ddl
# ──────────────────────────────────────────────────────────────────────

def test_table_schema_to_ddl_from_create_sql():
    t = TableSchema(
        name="t",
        create_sql="CREATE TABLE t (id INT PRIMARY KEY, name TEXT)",
    )
    assert t.to_ddl() == "CREATE TABLE t (id INT PRIMARY KEY, name TEXT);"


def test_table_schema_to_ddl_from_columns():
    t = TableSchema(
        name="users",
        columns=[
            ColumnSchema(name="id", type="INTEGER", primary_key=True, nullable=False),
            ColumnSchema(name="email", type="TEXT", nullable=False),
        ],
    )
    ddl = t.to_ddl()
    assert ddl.startswith("CREATE TABLE users")
    assert "id INTEGER PRIMARY KEY NOT NULL" in ddl
    assert "email TEXT NOT NULL" in ddl


# ──────────────────────────────────────────────────────────────────────
# SpiderSchemaProvider
# ──────────────────────────────────────────────────────────────────────

def test_spider_lists_databases(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    assert p.list_databases() == ["sales", "uni"]


def test_spider_db_path_resolves(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    path = p.db_path("uni")
    assert path.exists()
    assert path.name == "uni.sqlite"


def test_spider_db_path_raises_on_missing(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    with pytest.raises(FileNotFoundError):
        p.db_path("nonexistent")


def test_spider_get_tables_returns_tableschema(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    tables = p.get_tables("uni")
    assert len(tables) == 1
    assert isinstance(tables[0], TableSchema)
    assert tables[0].name == "uni_t"


def test_spider_render_schema_has_create(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    text = p.render_schema("uni")
    assert "CREATE TABLE" in text
    assert "uni_t" in text


# ──────────────────────────────────────────────────────────────────────
# ConnectionSchemaProvider
# ──────────────────────────────────────────────────────────────────────

def test_connection_lists_tables(tiny_db: Path):
    p = ConnectionSchemaProvider(str(tiny_db))
    assert p.list_tables() == ["users"]


def test_connection_get_tables_columns(tiny_db: Path):
    p = ConnectionSchemaProvider(str(tiny_db))
    tables = p.get_tables()
    assert len(tables) == 1
    cols = {c.name for c in tables[0].columns}
    assert cols == {"id", "name"}


def test_connection_render_schema_with_samples(tiny_db: Path):
    p = ConnectionSchemaProvider(str(tiny_db))
    text = p.render_schema(include_samples=True)
    assert "CREATE TABLE users" in text
    assert "Иван" in text or "Анна" in text


def test_connection_test_connection(tiny_db: Path):
    p = ConnectionSchemaProvider(str(tiny_db))
    assert p.test_connection() is True


# ──────────────────────────────────────────────────────────────────────
# Цепочка SpiderSchemaProvider.for_database → ConnectionSchemaProvider
# ──────────────────────────────────────────────────────────────────────

def test_spider_for_database_returns_connection_provider(spider_dir: Path):
    p = SpiderSchemaProvider(spider_dir)
    sub = p.for_database("sales")
    assert isinstance(sub, ConnectionSchemaProvider)
    text = sub.render_schema()
    assert "sales_t" in text


# ──────────────────────────────────────────────────────────────────────
# render_tables — общая утилита
# ──────────────────────────────────────────────────────────────────────

def test_render_tables_groups_ddl_and_samples():
    tables = [
        TableSchema(
            name="x",
            columns=[ColumnSchema(name="id", type="INT")],
            sample_rows=[(1,), (2,)],
        ),
    ]
    text = render_tables(tables, include_samples=True)
    assert "CREATE TABLE x" in text
    assert "Примеры строк" in text
    assert "(1," in text and "(2," in text


def test_render_tables_no_samples():
    tables = [
        TableSchema(
            name="x",
            columns=[ColumnSchema(name="id", type="INT")],
            sample_rows=[(1,)],
        ),
    ]
    text = render_tables(tables, include_samples=False)
    assert "CREATE TABLE x" in text
    assert "Примеры строк" not in text

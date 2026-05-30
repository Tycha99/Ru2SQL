"""Тесты на DbConnector и SqlExecutor.

Покрывают чтение схемы SQLite-баз, генерацию DDL и проверку того, что
SQLite-подключение действительно открывается в режиме read-only —
модифицирующие операции должны падать с sqlite3.OperationalError.
"""

import sqlite3
from pathlib import Path

import pytest

from src.db.connector import DbConnector, TableInfo
from src.db.executor import QueryResult, SqlExecutor


@pytest.fixture
def tiny_sqlite(tmp_path: Path) -> Path:
    db = tmp_path / "tiny.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT)"
    )
    conn.executemany(
        "INSERT INTO users (id, name, city) VALUES (?, ?, ?)",
        [(1, "Иван", "Казань"), (2, "Анна", "Москва"), (3, "Олег", "Казань")],
    )
    conn.commit()
    conn.close()
    return db


# ──────────────────────────────────────────────────────────────────────
# DbConnector
# ──────────────────────────────────────────────────────────────────────

def test_connector_lists_tables(tiny_sqlite: Path):
    c = DbConnector(str(tiny_sqlite))
    assert c.list_tables() == ["users"]


def test_connector_reads_columns(tiny_sqlite: Path):
    c = DbConnector(str(tiny_sqlite))
    tables = c.get_schema(include_samples=False)
    assert len(tables) == 1
    table = tables[0]
    assert isinstance(table, TableInfo)
    names = [col.name for col in table.columns]
    assert names == ["id", "name", "city"]
    # id — primary key, name — NOT NULL
    pk = next(col for col in table.columns if col.name == "id")
    assert pk.primary_key is True
    nn = next(col for col in table.columns if col.name == "name")
    assert nn.nullable is False


def test_connector_renders_ddl(tiny_sqlite: Path):
    c = DbConnector(str(tiny_sqlite))
    schema_text = c.render_schema(include_samples=True)
    assert "CREATE TABLE users" in schema_text
    assert "PRIMARY KEY" in schema_text
    # sample-строки прокинуты комментариями
    assert "Иван" in schema_text or "Олег" in schema_text


def test_connector_accepts_sqlite_uri(tiny_sqlite: Path):
    c = DbConnector(f"sqlite:///{tiny_sqlite}")
    assert c.list_tables() == ["users"]


# ──────────────────────────────────────────────────────────────────────
# SqlExecutor
# ──────────────────────────────────────────────────────────────────────

def test_executor_runs_select(tiny_sqlite: Path):
    ex = SqlExecutor(str(tiny_sqlite))
    res = ex.run("SELECT id, name FROM users ORDER BY id")
    assert isinstance(res, QueryResult)
    assert res.success
    assert res.columns == ["id", "name"]
    assert res.row_count == 3
    assert res.rows[0] == [1, "Иван"]


def test_executor_aggregation(tiny_sqlite: Path):
    ex = SqlExecutor(str(tiny_sqlite))
    res = ex.run("SELECT city, COUNT(*) AS cnt FROM users GROUP BY city ORDER BY cnt DESC")
    assert res.success
    assert res.rows[0] == ["Казань", 2]


def test_executor_returns_error_on_bad_sql(tiny_sqlite: Path):
    ex = SqlExecutor(str(tiny_sqlite))
    res = ex.run("SELEC nonsense FROM users")
    assert not res.success
    assert res.error is not None


def test_executor_blocks_modifications(tiny_sqlite: Path):
    """Ключевая проверка: SQLite-соединение открывается в read-only
    режиме (URI mode=ro&immutable=1), модифицирующие операции должны
    падать ошибкой, а не выполняться втихую."""
    ex = SqlExecutor(str(tiny_sqlite))

    res = ex.run("DELETE FROM users WHERE id = 1")
    assert not res.success
    assert res.error is not None
    assert "read" in res.error.lower() or "readonly" in res.error.lower() \
        or "только для чтения" in res.error.lower()

    # Подтверждение, что данные не пострадали
    check = ex.run("SELECT COUNT(*) FROM users")
    assert check.success
    assert check.rows == [[3]]


def test_executor_blocks_drop_table(tiny_sqlite: Path):
    ex = SqlExecutor(str(tiny_sqlite))
    res = ex.run("DROP TABLE users")
    assert not res.success

    # Подтверждение, что таблица на месте
    check = ex.run("SELECT COUNT(*) FROM users")
    assert check.success


def test_queryresult_to_markdown(tiny_sqlite: Path):
    ex = SqlExecutor(str(tiny_sqlite))
    res = ex.run("SELECT id, name FROM users WHERE id = 1")
    md = res.to_markdown_table()
    assert "id" in md and "name" in md
    assert "Иван" in md

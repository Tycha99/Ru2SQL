"""Тесты на SchemaRetriever."""

import sqlite3
from pathlib import Path

import pytest

from src.data.schema import SchemaRetriever


@pytest.fixture
def fake_databases_dir(tmp_path: Path) -> Path:
    """Создаёт структуру databases/uni/uni.sqlite с двумя таблицами."""
    db_id = "uni"
    (tmp_path / db_id).mkdir()
    db_path = tmp_path / db_id / f"{db_id}.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE groups (id INTEGER PRIMARY KEY, faculty TEXT)")
    conn.execute("INSERT INTO students VALUES (1, 'Иван')")
    conn.execute("INSERT INTO groups VALUES (10, 'ПИ')")
    conn.commit()
    conn.close()
    return tmp_path


def test_list_databases(fake_databases_dir: Path):
    r = SchemaRetriever(fake_databases_dir)
    assert r.list_databases() == ["uni"]


def test_get_tables(fake_databases_dir: Path):
    r = SchemaRetriever(fake_databases_dir)
    tables = r.get_tables("uni")
    names = sorted(t.name for t in tables)
    assert names == ["groups", "students"]


def test_render_schema_contains_create(fake_databases_dir: Path):
    r = SchemaRetriever(fake_databases_dir)
    text = r.render_schema("uni")
    assert "CREATE TABLE" in text
    assert "students" in text
    assert "groups" in text

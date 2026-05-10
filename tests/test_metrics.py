"""Тесты на метрики EM и EX."""

import sqlite3
from pathlib import Path

import pytest

from src.evaluation.metrics import exact_match, execution_accuracy


def test_exact_match_simple():
    assert exact_match("SELECT * FROM t", "select * from t")


def test_exact_match_whitespace():
    assert exact_match("SELECT  *  FROM  t", "SELECT * FROM t")


def test_exact_match_negative():
    assert not exact_match("SELECT a FROM t", "SELECT b FROM t")


@pytest.fixture
def tmp_sqlite(tmp_path: Path) -> Path:
    db = tmp_path / "tiny.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE users (id INT, name TEXT)")
    conn.executemany("INSERT INTO users VALUES (?, ?)", [(1, "a"), (2, "b")])
    conn.commit()
    conn.close()
    return db


def test_execution_accuracy_match(tmp_sqlite: Path):
    pred = "SELECT id FROM users ORDER BY id"
    gold = "SELECT id FROM users ORDER BY id"
    assert execution_accuracy(pred, gold, tmp_sqlite)


def test_execution_accuracy_set_equal(tmp_sqlite: Path):
    pred = "SELECT id FROM users ORDER BY id DESC"
    gold = "SELECT id FROM users ORDER BY id ASC"
    # Без ORDER BY проверки — как множества они равны
    assert execution_accuracy(pred, gold, tmp_sqlite)


def test_execution_accuracy_mismatch(tmp_sqlite: Path):
    pred = "SELECT id FROM users WHERE id = 1"
    gold = "SELECT id FROM users WHERE id = 2"
    assert not execution_accuracy(pred, gold, tmp_sqlite)


def test_execution_accuracy_invalid_pred(tmp_sqlite: Path):
    pred = "SELEC bad sql"
    gold = "SELECT id FROM users"
    assert not execution_accuracy(pred, gold, tmp_sqlite)

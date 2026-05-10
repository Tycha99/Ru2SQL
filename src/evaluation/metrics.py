"""Метрики Text-to-SQL: Exact Match и Execution Accuracy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models.postprocess import normalize_sql


def exact_match(predicted: str, gold: str, dialect: str = "sqlite") -> bool:
    """Сравнение нормализованных SQL посимвольно. Грубая, но честная метрика."""
    return normalize_sql(predicted, dialect) == normalize_sql(gold, dialect)


def execution_accuracy(
    predicted_sql: str,
    gold_sql: str,
    db_path: Path | str,
    timeout_seconds: float = 5.0,
) -> bool:
    """Прогон обоих SQL на SQLite. True если результаты совпадают как множества."""
    db_path = Path(db_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout_seconds)
    try:
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        try:
            pred_rows = _run(conn, predicted_sql)
        except sqlite3.Error:
            return False
        try:
            gold_rows = _run(conn, gold_sql)
        except sqlite3.Error:
            return False
        return _rows_equal(pred_rows, gold_rows)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def _rows_equal(a: list[tuple], b: list[tuple]) -> bool:
    """Сравнение как мультимножеств — порядок не важен (если в SQL нет ORDER BY)."""
    if len(a) != len(b):
        return False
    return sorted(map(_row_key, a)) == sorted(map(_row_key, b))


def _row_key(row: tuple) -> tuple:
    return tuple(str(x) for x in row)


def compute_metrics(
    predictions: list[str],
    golds: list[str],
    db_ids: list[str],
    databases_dir: Path | str,
) -> dict:
    """Прогон по всему датасету. Возвращает dict с EM, EX, и счётчиками."""
    databases_dir = Path(databases_dir)
    n = len(predictions)
    assert n == len(golds) == len(db_ids), "Mismatched lengths"

    em_count = 0
    ex_count = 0
    parse_fail = 0

    for pred, gold, db_id in zip(predictions, golds, db_ids):
        if exact_match(pred, gold):
            em_count += 1

        db_path = databases_dir / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            parse_fail += 1
            continue

        if execution_accuracy(pred, gold, db_path):
            ex_count += 1

    return {
        "n": n,
        "exact_match": em_count / n if n else 0.0,
        "execution_accuracy": ex_count / n if n else 0.0,
        "parse_fail": parse_fail,
    }

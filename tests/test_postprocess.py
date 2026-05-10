"""Тесты на постобработку SQL."""

from src.models.postprocess import (
    is_valid_sql,
    normalize_sql,
    postprocess,
    strip_model_artifacts,
)


def test_strip_markdown_block():
    raw = "```sql\nSELECT * FROM users;\n```"
    assert strip_model_artifacts(raw).startswith("SELECT")


def test_strip_sql_prefix():
    raw = "SQL: SELECT 1;"
    assert strip_model_artifacts(raw).startswith("SELECT")


def test_keeps_first_statement():
    raw = "SELECT 1; SELECT 2;"
    out = strip_model_artifacts(raw)
    assert "SELECT 1" in out
    assert "SELECT 2" not in out


def test_valid_sql():
    assert is_valid_sql("SELECT * FROM students WHERE id = 1")


def test_invalid_sql():
    assert not is_valid_sql("SELEC * FRM where")


def test_normalize_em():
    a = "SELECT  *  FROM  Users"
    b = "select * from users"
    assert normalize_sql(a) == normalize_sql(b)


def test_postprocess_full():
    raw = "```sql\nSELECT name FROM students WHERE group_id = 1;\nSELECT 2;\n```"
    out = postprocess(raw)
    assert out.startswith("SELECT name")
    assert "SELECT 2" not in out

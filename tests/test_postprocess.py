"""Тесты на постобработку SQL и связанные функции.

Покрывает раздел 2.5 пояснительной записки: чистку артефактов,
валидацию через sqlglot, нормализацию для Exact Match и AST-уровневый
гвардейл is_select_only.
"""

from src.models.postprocess import (
    is_select_only,
    is_valid_sql,
    normalize_sql,
    postprocess,
    strip_model_artifacts,
)


# ──────────────────────────────────────────────────────────────────────
# strip_model_artifacts
# ──────────────────────────────────────────────────────────────────────

def test_strip_markdown_block_with_lang():
    raw = "```sql\nSELECT * FROM users;\n```"
    assert strip_model_artifacts(raw).upper().startswith("SELECT")


def test_strip_markdown_block_without_lang():
    raw = "```\nSELECT id FROM t;\n```"
    assert strip_model_artifacts(raw).upper().startswith("SELECT")


def test_strip_sql_prefix():
    raw = "SQL: SELECT 1;"
    assert strip_model_artifacts(raw).upper().startswith("SELECT")


def test_strip_russian_prefix():
    raw = "Ответ: SELECT name FROM students;"
    assert strip_model_artifacts(raw).upper().startswith("SELECT")


def test_strip_natural_language_before_select():
    raw = "Вот SQL, который отвечает на вопрос: SELECT * FROM t WHERE id = 1;"
    out = strip_model_artifacts(raw)
    assert out.upper().startswith("SELECT")
    assert "Вот" not in out


def test_keeps_first_statement_of_two():
    raw = "SELECT 1; SELECT 2;"
    out = strip_model_artifacts(raw)
    assert "SELECT 1" in out
    assert "SELECT 2" not in out


def test_with_cte_is_preserved():
    raw = "WITH agg AS (SELECT id FROM t) SELECT * FROM agg"
    out = strip_model_artifacts(raw)
    assert out.upper().startswith("WITH")


def test_strip_returns_empty_on_garbage():
    # Нет ни одного SQL-ключевого слова — обрезать нечего, но и пустого
    # ответа модель ещё не нагенерила: возвращаем как есть, валидация
    # отсеет дальше по пайплайну.
    raw = "просто текст без запроса"
    assert strip_model_artifacts(raw) == "просто текст без запроса"


# ──────────────────────────────────────────────────────────────────────
# is_valid_sql
# ──────────────────────────────────────────────────────────────────────

def test_valid_select():
    assert is_valid_sql("SELECT * FROM students WHERE id = 1")


def test_valid_with_cte():
    assert is_valid_sql("WITH x AS (SELECT id FROM t) SELECT * FROM x")


def test_invalid_garbage():
    assert not is_valid_sql("SELEC * FRM where")


def test_invalid_empty():
    assert not is_valid_sql("")
    assert not is_valid_sql("   ")


# ──────────────────────────────────────────────────────────────────────
# is_select_only — guardrail
# ──────────────────────────────────────────────────────────────────────

def test_select_passes_guardrail():
    assert is_select_only("SELECT id FROM t")


def test_with_cte_passes_guardrail():
    assert is_select_only("WITH x AS (SELECT id FROM t) SELECT * FROM x")


def test_drop_table_blocked():
    assert not is_select_only("DROP TABLE users")


def test_delete_blocked():
    assert not is_select_only("DELETE FROM users WHERE id = 1")


def test_update_blocked():
    assert not is_select_only("UPDATE users SET name = 'a' WHERE id = 1")


def test_insert_blocked():
    assert not is_select_only("INSERT INTO users (id, name) VALUES (1, 'a')")


def test_empty_blocked():
    assert not is_select_only("")
    assert not is_select_only("   ")


def test_invalid_sql_blocked_by_guardrail():
    # На невалидной строке is_select_only должен честно возвращать False,
    # а не падать с исключением.
    assert not is_select_only("not a sql at all")


# ──────────────────────────────────────────────────────────────────────
# normalize_sql
# ──────────────────────────────────────────────────────────────────────

def test_normalize_collapses_whitespace():
    a = "SELECT  *  FROM  Users"
    b = "select * from users"
    assert normalize_sql(a) == normalize_sql(b)


def test_normalize_idempotent():
    sql = "SELECT id FROM t WHERE x = 1"
    assert normalize_sql(normalize_sql(sql)) == normalize_sql(sql)


def test_normalize_fallback_on_invalid():
    # На невалидном SQL функция не должна падать — должен сработать fallback.
    out = normalize_sql("not really sql")
    assert isinstance(out, str)
    assert out.upper() == out  # верхний регистр сохранён


# ──────────────────────────────────────────────────────────────────────
# postprocess — полный pipeline
# ──────────────────────────────────────────────────────────────────────

def test_postprocess_extracts_from_markdown():
    raw = "```sql\nSELECT name FROM students WHERE group_id = 1;\nSELECT 2;\n```"
    out = postprocess(raw)
    assert out.upper().startswith("SELECT NAME") or out.startswith("SELECT name")
    assert "SELECT 2" not in out


def test_postprocess_returns_empty_on_invalid():
    # Текст не содержит валидного SQL — pipeline должен вернуть пустую строку,
    # как описано в разделе 2.5 пояснительной записки.
    raw = "Я не могу сгенерировать SQL для этого вопроса."
    assert postprocess(raw) == ""


def test_postprocess_returns_empty_on_truncated():
    # Модель оборвала генерацию на середине запроса — невалидный синтаксис.
    raw = "SELECT * FROM users WHERE"
    assert postprocess(raw) == ""


def test_postprocess_keeps_valid_with_cte():
    raw = "WITH agg AS (SELECT id FROM t) SELECT * FROM agg"
    out = postprocess(raw)
    assert out.upper().startswith("WITH")

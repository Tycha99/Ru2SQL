"""Постобработка SQL: чистка вывода модели, валидация и нормализация.

Соответствует разделу 2.5 пояснительной записки. Pipeline:
    raw_output  ──► strip_model_artifacts  ──► is_valid_sql  ──► sql | ""

Дополнительно модуль предоставляет:
    is_select_only(sql)  — AST-уровневый гвардейл против DDL/DML
                            перед выполнением сгенерированного запроса;
    normalize_sql(sql)   — каноническая форма для расчёта Exact Match
                            (совместима с evaluate_pauq.py).
"""

from __future__ import annotations

import logging
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)

# Ключевые слова, с которых может начинаться корректный SQL-запрос.
_SQL_START_KEYWORDS = ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
_SQL_START_REGEX = re.compile(
    r"\b(" + "|".join(_SQL_START_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)
_FENCE_REGEX = re.compile(r"```(?:sql)?\s*(.*?)```", flags=re.DOTALL | re.IGNORECASE)
_PREFIX_REGEX = re.compile(r"^\s*(?:SQL|Ответ|Answer)\s*:\s*", flags=re.IGNORECASE)

# Типы AST-узлов, которые мы считаем «осмысленными» SQL-запросами.
# sqlglot — лояльный парсер: 'garbage text' он распарсит как Column/Table.
# Без проверки isinstance такие случаи будут проходить is_valid_sql.
_VALID_ROOT_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Select,
    exp.With,
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Union,
    exp.Intersect,
    exp.Except,
)


def strip_model_artifacts(text: str) -> str:
    """Очищает вывод модели от markdown и пояснений до начала SQL-запроса.

    Шаги:
        1. Если ответ обёрнут в ```sql ... ``` — извлекается содержимое.
        2. Удаляются префиксы вида «SQL:», «Ответ:», «Answer:».
        3. Ищется первое вхождение SQL-ключевого слова, всё до него отбрасывается.
        4. Берётся первый statement до первой точки с запятой включительно.
    """
    fence = _FENCE_REGEX.search(text)
    if fence:
        text = fence.group(1)

    text = _PREFIX_REGEX.sub("", text)

    keyword_match = _SQL_START_REGEX.search(text)
    if keyword_match:
        text = text[keyword_match.start():]

    text = text.strip()
    if ";" in text:
        head, _, _ = text.partition(";")
        text = head.strip() + ";"

    return text.strip()


def is_valid_sql(sql: str, dialect: str = "sqlite") -> bool:
    """Проверяет, что строка — это валидный SQL-запрос.

    Парсится через sqlglot и дополнительно проверяется, что корень AST —
    это один из «осмысленных» типов запроса (SELECT/WITH/INSERT/UPDATE/
    DELETE/UNION). Без проверки типа sqlglot принимает за SQL даже
    случайные идентификаторы, потому что он лояльный парсер.
    """
    if not sql or not sql.strip():
        return False
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except (ParseError, ValueError, TypeError) as e:
        logger.debug("sqlglot не смог разобрать SQL: %s", e)
        return False
    if parsed is None:
        return False
    return isinstance(parsed, _VALID_ROOT_TYPES)


def is_select_only(sql: str, dialect: str = "sqlite") -> bool:
    """Возвращает True, если SQL — это SELECT (в т. ч. внутри WITH-CTE).

    Используется как guardrail перед выполнением сгенерированного запроса
    на реальной базе данных: модель не должна получить возможность вызвать
    DROP/UPDATE/DELETE/INSERT, даже если такие конструкции синтаксически
    корректны.
    """
    if not sql or not sql.strip():
        return False
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
    except (ParseError, ValueError, TypeError):
        return False
    if parsed is None:
        return False
    if isinstance(parsed, exp.Select):
        return True
    if isinstance(parsed, exp.With):
        return isinstance(parsed.this, exp.Select)
    if isinstance(parsed, exp.Subquery):
        return isinstance(parsed.this, exp.Select)
    return False


def normalize_sql(sql: str, dialect: str = "sqlite") -> str:
    """Каноническая форма для расчёта Exact Match.

    Использует sqlglot с флагом ``normalize=True`` — это нормализует регистр
    ключевых слов и идентификаторов. Результат приводится к верхнему регистру,
    чтобы EM считался идентично эталонной реализации в ``evaluate_pauq.py``.
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect)
        return parsed.sql(dialect=dialect, normalize=True).upper()
    except (ParseError, ValueError, TypeError):
        return re.sub(r"\s+", " ", sql.upper()).strip().rstrip(";")


def postprocess(raw_output: str) -> str:
    """Полный pipeline постобработки вывода модели.

    1. Чистка артефактов через :func:`strip_model_artifacts`.
    2. Валидация через :func:`is_valid_sql`.
    3. Возврат пустой строки при провале валидации.

    Соответствует разделу 2.5 пояснительной записки.
    """
    sql = strip_model_artifacts(raw_output)
    if not is_valid_sql(sql):
        logger.warning("postprocess отбросил невалидный SQL: %r", sql[:120])
        return ""
    return sql

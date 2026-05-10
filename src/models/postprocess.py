"""Постобработка SQL: чистка вывода модели и базовая валидация через sqlglot."""

from __future__ import annotations

import re

import sqlglot
from sqlglot.errors import ParseError


def strip_model_artifacts(text: str) -> str:
    """Убирает markdown-блоки, префиксы, лишний текст после SQL."""
    # ```sql ... ```
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1)

    # Убираем "SQL:", "Ответ:" и т.п. в начале
    text = re.sub(r"^\s*(?:SQL|Ответ|Answer)\s*:\s*", "", text, flags=re.IGNORECASE)

    # Если есть несколько SQL — берём первый до точки с запятой
    text = text.strip()
    if ";" in text:
        head, _, _ = text.partition(";")
        text = head.strip() + ";"

    return text.strip()


def is_valid_sql(sql: str, dialect: str = "sqlite") -> bool:
    """Парсится ли SQL через sqlglot."""
    try:
        sqlglot.parse_one(sql, dialect=dialect)
        return True
    except ParseError:
        return False


def normalize_sql(sql: str, dialect: str = "sqlite") -> str:
    """Нормализация для Exact Match: единый регистр ключевых слов, пробелы."""
    try:
        return sqlglot.parse_one(sql, dialect=dialect).sql(dialect=dialect, pretty=False).lower()
    except ParseError:
        # Если не парсится — просто нижний регистр и схлопывание пробелов
        return re.sub(r"\s+", " ", sql.lower()).strip().rstrip(";")


def postprocess(raw_output: str) -> str:
    """Полный pipeline постобработки."""
    return strip_model_artifacts(raw_output)

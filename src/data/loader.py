"""Загрузчик датасета PAUQ.

PAUQ распространяется в JSON-формате с полями question, query, db_id и т.д.
См. https://github.com/ai-forever/pauq
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class PauqExample:
    question: str
    query: str  # gold SQL
    db_id: str
    query_type: str | None = None  # easy/medium/hard/extra если есть
    raw: dict | None = None


def load_pauq_split(path: Path | str) -> list[PauqExample]:
    """Читает train.json / dev.json / test.json из PAUQ."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    examples: list[PauqExample] = []
    for item in raw:
        # PAUQ имеет несколько ревизий формата; пробуем самые частые поля
        question = item.get("question") or item.get("question_ru") or ""
        query = item.get("query") or item.get("sql_query") or item.get("sql") or ""
        db_id = item.get("db_id") or item.get("database") or ""
        if not (question and query and db_id):
            continue
        examples.append(
            PauqExample(
                question=question.strip(),
                query=query.strip(),
                db_id=db_id.strip(),
                query_type=item.get("query_type") or item.get("hardness"),
                raw=item,
            )
        )
    return examples


def iter_pauq_split(path: Path | str) -> Iterator[PauqExample]:
    """Удобно при больших датасетах — генератор."""
    yield from load_pauq_split(path)

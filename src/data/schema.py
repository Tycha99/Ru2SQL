"""SchemaRetriever — фасад над :class:`SpiderSchemaProvider`.

Исторически здесь жила полная реализация чтения PAUQ/Spider-схем. После
рефакторинга (раздел 4.2 аудита) общая логика переехала в
``schema_provider.py``, а ``SchemaRetriever`` оставлен как тонкая
обёртка ради обратной совместимости импортов (``from src.data.schema
import SchemaRetriever``), которые используются в API и тестах.

Новый код стоит писать сразу через :class:`SpiderSchemaProvider`.
"""

from __future__ import annotations

from pathlib import Path

from src.data.schema_provider import SpiderSchemaProvider, TableSchema

# Алиас для совместимости со старыми импортами вида
# ``from src.data.schema import TableInfo``.
TableInfo = TableSchema


class SchemaRetriever(SpiderSchemaProvider):
    """Совместимый алиас :class:`SpiderSchemaProvider`."""

    def __init__(self, databases_dir: Path | str):
        super().__init__(databases_dir)

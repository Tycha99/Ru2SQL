"""Pydantic-модели для FastAPI endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VocabularyPayload(BaseModel):
    """Бизнес-словарь в формате, согласованном с BusinessVocabulary.from_dict.

    Передаётся клиентом опционально в запросе на генерацию SQL. Если поле
    отсутствует — модель работает без специальных бизнес-определений.
    """
    company: str = ""
    terms: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# /generate-sql — старый эндпоинт для PAUQ-структуры (databases_dir + db_id)
# ──────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Вопрос на русском")
    db_id: str = Field(..., min_length=1, description="Идентификатор БД из PAUQ")
    execute: bool = Field(default=False, description="Прогнать сгенерированный SQL на БД")
    vocabulary: VocabularyPayload | None = Field(
        default=None,
        description="Опциональный бизнес-словарь компании (см. раздел 3.6 ВКР)",
    )


class ExecutionResult(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int


class GenerateResponse(BaseModel):
    sql: str
    raw_output: str
    is_valid_sql: bool
    execution: ExecutionResult | None = None
    error: str | None = None


# ──────────────────────────────────────────────────────────────────────
# /query — новый эндпоинт для произвольной БД (connection string)
# ──────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Полный запрос «вопрос на русском → SQL → результат» для произвольной БД.

    В отличие от GenerateRequest, не привязан к PAUQ-структуре: клиент сам
    передаёт connection string (SQLite/PostgreSQL/MySQL). Используется
    Streamlit-интерфейсом и любыми сторонними клиентами.
    """
    question: str = Field(..., min_length=1, max_length=2000)
    connection_string: str = Field(
        ..., min_length=1,
        description="Строка подключения. Пример: sqlite:///data/demo/sales.sqlite",
    )
    execute: bool = Field(default=True)
    vocabulary: VocabularyPayload | None = None


class QueryResponse(BaseModel):
    sql: str
    raw_output: str
    is_valid_sql: bool
    gen_time_seconds: float
    execution: ExecutionResult | None = None
    error: str | None = None


# ──────────────────────────────────────────────────────────────────────
# /schema — отдать схему произвольной БД для подстановки в UI
# ──────────────────────────────────────────────────────────────────────

class SchemaRequest(BaseModel):
    connection_string: str = Field(..., min_length=1)
    include_samples: bool = Field(default=True)


class ColumnPayload(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool


class TablePayload(BaseModel):
    name: str
    columns: list[ColumnPayload]
    sample_rows: list[list]
    ddl: str


class SchemaResponse(BaseModel):
    tables: list[TablePayload]


# ──────────────────────────────────────────────────────────────────────
# Прочее
# ──────────────────────────────────────────────────────────────────────

class DatabaseInfo(BaseModel):
    db_id: str
    tables: list[str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    base_model: str

"""Pydantic-модели для FastAPI endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Вопрос на русском")
    db_id: str = Field(..., min_length=1, description="Идентификатор БД из PAUQ")
    execute: bool = Field(default=False, description="Прогнать сгенерированный SQL на БД")


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


class DatabaseInfo(BaseModel):
    db_id: str
    tables: list[str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    base_model: str

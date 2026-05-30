"""FastAPI приложение.

Запуск:
    uvicorn src.api.main:app --reload
    # Swagger UI: http://127.0.0.1:8000/docs

Эндпоинты:
    GET  /health           — статус сервиса и загруженной модели
    GET  /databases        — список БД из data/databases (PAUQ-структура)
    POST /generate-sql     — генерация SQL по db_id из PAUQ
    POST /schema           — схема произвольной БД по connection string
    POST /query            — полный pipeline для произвольной БД
                              (генерация + опциональное исполнение + guardrail)
"""

from __future__ import annotations

import logging
import sqlite3
import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from src.api.dependencies import get_engine, get_schema_retriever, lifespan
from src.api.schemas import (
    DatabaseInfo,
    ExecutionResult,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SchemaRequest,
    SchemaResponse,
    TablePayload,
    ColumnPayload,
)
from src.business.vocabulary import BusinessVocabulary
from src.config import settings
from src.data.schema import SchemaRetriever
from src.data.schema_provider import ConnectionSchemaProvider
from src.db.executor import SqlExecutor
from src.models.inference import InferenceEngine
from src.models.postprocess import is_select_only, is_valid_sql

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ru2sql",
    description="Преобразование вопросов на русском в SQL-запросы",
    version="0.2.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────────────
# Базовые эндпоинты
# ──────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health(engine: InferenceEngine = Depends(get_engine)):
    return HealthResponse(
        status="ok",
        model_loaded=engine.loaded,
        base_model=engine.base_model_name,
    )


@app.post("/warmup")
async def warmup(engine: InferenceEngine = Depends(get_engine)):
    """Прогревает модель одной короткой генерацией.

    Первый инференс холодной модели на CPU сильно дольше последующих:
    подгружаются LoRA-слои, формируется граф вычислений, заполняется
    KV-кеш. Вызов /warmup делает один маленький проход с минимальным
    max_new_tokens, чтобы боевой /query шёл уже по прогретой модели.
    """
    t0 = time.time()
    schema = "CREATE TABLE t (id INT);"
    await run_in_threadpool(engine.generate, schema, "SELECT id", None, 16)
    return {"warmup_seconds": round(time.time() - t0, 2)}


@app.get("/databases", response_model=list[DatabaseInfo])
def list_databases(retriever: SchemaRetriever = Depends(get_schema_retriever)):
    out: list[DatabaseInfo] = []
    for db_id in retriever.list_databases():
        try:
            tables = [t.name for t in retriever.get_tables(db_id, n_sample_rows=0)]
            out.append(DatabaseInfo(db_id=db_id, tables=tables))
        except FileNotFoundError:
            continue
    return out


# ──────────────────────────────────────────────────────────────────────
# PAUQ-сценарий (старый эндпоинт, оставлен для совместимости)
# ──────────────────────────────────────────────────────────────────────

@app.post("/generate-sql", response_model=GenerateResponse)
async def generate_sql(
    req: GenerateRequest,
    engine: InferenceEngine = Depends(get_engine),
    retriever: SchemaRetriever = Depends(get_schema_retriever),
):
    """Генерация SQL для базы из PAUQ-структуры (data/databases/{db_id})."""
    try:
        schema_text = retriever.render_schema(req.db_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    vocab = (
        BusinessVocabulary.from_dict(req.vocabulary.model_dump())
        if req.vocabulary
        else None
    )

    result = await run_in_threadpool(
        engine.generate, schema_text, req.question, vocab
    )
    valid = is_valid_sql(result.sql)

    response = GenerateResponse(
        sql=result.sql,
        raw_output=result.raw_output,
        is_valid_sql=valid,
    )

    if req.execute and valid:
        if not is_select_only(result.sql):
            response.error = (
                "SQL отклонён гвардейлом: разрешены только запросы SELECT и WITH."
            )
            logger.warning("Guardrail отклонил SQL: %r", result.sql[:120])
            return response
        try:
            response.execution = await run_in_threadpool(
                _execute_sql_pauq, req.db_id, result.sql, retriever
            )
        except sqlite3.Error as e:
            response.error = f"SQL execution error: {e}"

    return response


def _execute_sql_pauq(db_id: str, sql: str, retriever: SchemaRetriever) -> ExecutionResult:
    db_path = retriever.db_path(db_id)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(100)
        cols = [d[0] for d in cur.description] if cur.description else []
        return ExecutionResult(columns=cols, rows=[list(r) for r in rows], row_count=len(rows))
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Произвольная БД по connection string — новый сценарий для Streamlit
# ──────────────────────────────────────────────────────────────────────

@app.post("/schema", response_model=SchemaResponse)
async def get_schema(req: SchemaRequest):
    """Возвращает схему произвольной БД для отображения в клиенте."""
    try:
        provider = ConnectionSchemaProvider(req.connection_string)
        tables = await run_in_threadpool(provider.get_tables, 2 if req.include_samples else 0)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Ошибка чтения схемы: {e}") from e

    payload = [
        TablePayload(
            name=t.name,
            columns=[
                ColumnPayload(
                    name=c.name, type=c.type,
                    nullable=c.nullable, primary_key=c.primary_key,
                )
                for c in t.columns
            ],
            sample_rows=[list(r) for r in t.sample_rows],
            ddl=t.to_ddl(),
        )
        for t in tables
    ]
    return SchemaResponse(tables=payload)


@app.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    engine: InferenceEngine = Depends(get_engine),
):
    """Полный pipeline: вопрос → SQL → опциональное исполнение на БД.

    В отличие от /generate-sql, работает с произвольной БД по connection
    string. Используется Streamlit-клиентом и сторонними интеграциями.
    Перед выполнением SQL проходит проверку is_select_only (раздел 4.4).
    """
    # 1. Схема целевой БД
    try:
        provider = ConnectionSchemaProvider(req.connection_string)
        schema_text = await run_in_threadpool(provider.render_schema, True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Ошибка подключения к БД: {e}") from e

    vocab = (
        BusinessVocabulary.from_dict(req.vocabulary.model_dump())
        if req.vocabulary
        else None
    )

    # 2. Инференс
    t0 = time.time()
    result = await run_in_threadpool(engine.generate, schema_text, req.question, vocab)
    gen_time = time.time() - t0

    valid = is_valid_sql(result.sql)
    response = QueryResponse(
        sql=result.sql,
        raw_output=result.raw_output,
        is_valid_sql=valid,
        gen_time_seconds=round(gen_time, 2),
    )

    # 3. Опциональное исполнение
    if req.execute and valid:
        if not is_select_only(result.sql):
            response.error = (
                "SQL отклонён гвардейлом: разрешены только запросы SELECT и WITH."
            )
            logger.warning("Guardrail отклонил SQL: %r", result.sql[:120])
            return response
        try:
            executor = SqlExecutor(req.connection_string)
            qr = await run_in_threadpool(executor.run, result.sql)
            if qr.success:
                response.execution = ExecutionResult(
                    columns=qr.columns, rows=qr.rows, row_count=qr.row_count,
                )
            else:
                response.error = f"SQL execution error: {qr.error}"
        except Exception as e:  # noqa: BLE001
            response.error = f"SQL execution error: {e}"

    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=settings.api_host, port=settings.api_port, reload=True)

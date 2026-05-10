"""FastAPI приложение.

Запуск:
    uvicorn src.api.main:app --reload
    # Swagger UI: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from src.api.dependencies import get_engine, get_schema_retriever, lifespan
from src.api.schemas import (
    DatabaseInfo,
    ExecutionResult,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
)
from src.config import settings
from src.data.schema import SchemaRetriever
from src.models.inference import InferenceEngine
from src.models.postprocess import is_valid_sql

app = FastAPI(
    title="ru2sql",
    description="Преобразование вопросов на русском в SQL-запросы",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health(engine: InferenceEngine = Depends(get_engine)):
    return HealthResponse(
        status="ok",
        model_loaded=engine._loaded,
        base_model=engine.base_model_name,
    )


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


@app.post("/generate-sql", response_model=GenerateResponse)
async def generate_sql(
    req: GenerateRequest,
    engine: InferenceEngine = Depends(get_engine),
    retriever: SchemaRetriever = Depends(get_schema_retriever),
):
    try:
        schema_text = retriever.render_schema(req.db_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Inference синхронный и тяжёлый — выносим в threadpool
    result = await run_in_threadpool(engine.generate, schema_text, req.question)

    valid = is_valid_sql(result.sql)
    response = GenerateResponse(
        sql=result.sql,
        raw_output=result.raw_output,
        is_valid_sql=valid,
    )

    if req.execute and valid:
        try:
            response.execution = await run_in_threadpool(
                _execute_sql, req.db_id, result.sql, retriever
            )
        except sqlite3.Error as e:
            response.error = f"SQL execution error: {e}"

    return response


def _execute_sql(db_id: str, sql: str, retriever: SchemaRetriever) -> ExecutionResult:
    db_path = retriever.db_path(db_id)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(100)
        cols = [d[0] for d in cur.description] if cur.description else []
        return ExecutionResult(
            columns=cols,
            rows=[list(r) for r in rows],
            row_count=len(rows),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host=settings.api_host, port=settings.api_port, reload=True)

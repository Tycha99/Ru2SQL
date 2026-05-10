"""FastAPI lifespan и DI: загрузка модели один раз при старте."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.data.schema import SchemaRetriever
from src.models.inference import InferenceEngine


class AppState:
    engine: InferenceEngine | None = None
    schema_retriever: SchemaRetriever | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Грузим модель при старте, освобождаем при остановке."""
    state.engine = InferenceEngine()
    state.engine.load()
    state.schema_retriever = SchemaRetriever(settings.databases_dir)
    yield
    state.engine = None
    state.schema_retriever = None


def get_engine() -> InferenceEngine:
    if state.engine is None:
        raise RuntimeError("Inference engine not initialized")
    return state.engine


def get_schema_retriever() -> SchemaRetriever:
    if state.schema_retriever is None:
        raise RuntimeError("SchemaRetriever not initialized")
    return state.schema_retriever

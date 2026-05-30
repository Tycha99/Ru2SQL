"""Локальный smoke-тест работоспособности Ru2SQL.

Прогоняет ключевые слои без поднятия Streamlit/FastAPI как отдельных
процессов. Покрывает: импорты, demo-базу, vocabulary, prompt,
постобработку, guardrail, новый API через FastAPI TestClient и
опционально — короткий инференс реальной модели.

Запуск:
    python scripts/smoke_local.py
    python scripts/smoke_local.py --with-model    # медленно, грузит Qwen
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

results: list[tuple[str, str, str]] = []


def check(name: str):
    def decorator(fn):
        try:
            t0 = time.time()
            fn()
            dt = time.time() - t0
            results.append(("OK", name, f"{dt*1000:.0f} мс"))
        except Exception as e:
            results.append(("FAIL", name, f"{type(e).__name__}: {e}"))
        return fn
    return decorator


# ──────────────────────────────────────────────────────────────────────
# Слой 1 — импорты, конфиг
# ──────────────────────────────────────────────────────────────────────
@check("Импорты ядра")
def _():
    from src.config import settings
    from src.api.schemas import GenerateRequest, QueryRequest, SchemaRequest
    from src.business.vocabulary import BusinessVocabulary
    from src.data.prompt import build_chat_messages, BASE_SYSTEM_PROMPT
    from src.data.schema_provider import (
        SpiderSchemaProvider, ConnectionSchemaProvider, TableSchema,
    )
    from src.db.connector import DbConnector
    from src.db.executor import SqlExecutor
    from src.models.postprocess import postprocess, is_select_only, is_valid_sql
    assert settings.base_model_name.startswith("Qwen")


# ──────────────────────────────────────────────────────────────────────
# Слой 2 — демо-база и read-only guardrail
# ──────────────────────────────────────────────────────────────────────
@check("Демо-база sales.sqlite: подключение и схема")
def _():
    from src.db.connector import DbConnector
    db = ROOT / "data" / "demo" / "sales.sqlite"
    assert db.exists(), f"Не найден файл {db} — запусти data/demo/create_demo_db.py"
    conn = DbConnector(str(db))
    tables = conn.list_tables()
    assert set(tables) == {"customers", "managers", "products", "orders", "order_items"}


@check("Демо-база: реальный SELECT выручки")
def _():
    from src.db.executor import SqlExecutor
    ex = SqlExecutor(str(ROOT / "data" / "demo" / "sales.sqlite"))
    res = ex.run("SELECT SUM(amount) FROM orders WHERE status='paid'")
    assert res.success, res.error
    assert res.rows[0][0] > 0


@check("Read-only guardrail: DELETE отклоняется драйвером")
def _():
    from src.db.executor import SqlExecutor
    ex = SqlExecutor(str(ROOT / "data" / "demo" / "sales.sqlite"))
    res = ex.run("DELETE FROM orders")
    assert not res.success
    assert ex.run("SELECT COUNT(*) FROM orders").rows[0][0] == 120


# ──────────────────────────────────────────────────────────────────────
# Слой 3 — BusinessVocabulary из YAML
# ──────────────────────────────────────────────────────────────────────
@check("BusinessVocabulary из configs/example_vocabulary.yaml")
def _():
    from src.business.vocabulary import BusinessVocabulary
    vocab = BusinessVocabulary.from_yaml(ROOT / "configs" / "example_vocabulary.yaml")
    assert bool(vocab)
    assert "выручка" in vocab.terms
    assert "SUM(orders.amount)" in vocab.render_system_context()


# ──────────────────────────────────────────────────────────────────────
# Слой 4 — PromptBuilder с реальной схемой и словарём
# ──────────────────────────────────────────────────────────────────────
@check("PromptBuilder: vocabulary уходит в system, не в user")
def _():
    from src.business.vocabulary import BusinessVocabulary
    from src.data.prompt import build_chat_messages
    from src.db.connector import DbConnector
    vocab = BusinessVocabulary.from_yaml(ROOT / "configs" / "example_vocabulary.yaml")
    schema = DbConnector(str(ROOT / "data" / "demo" / "sales.sqlite")).render_schema()
    msgs = build_chat_messages(schema, "Какая выручка за 2026 год?", vocabulary=vocab)
    assert "SUM(orders.amount)" in msgs[0]["content"]
    assert "SUM(orders.amount)" not in msgs[1]["content"]


# ──────────────────────────────────────────────────────────────────────
# Слой 5 — постобработка и guardrail
# ──────────────────────────────────────────────────────────────────────
@check("Постобработка: markdown, префиксы, truncated, мусор")
def _():
    from src.models.postprocess import postprocess, is_select_only
    cases = [
        ("```sql\nSELECT 1;\n```", lambda s: s.upper().startswith("SELECT")),
        ("Ответ: SELECT name FROM customers;", lambda s: s.startswith("SELECT name")),
        ("SELECT * FROM orders WHERE", lambda s: s == ""),
        ("просто текст без SQL", lambda s: s == ""),
    ]
    for raw, ok in cases:
        assert ok(postprocess(raw)), f"Сбой на: {raw!r} → {postprocess(raw)!r}"
    assert is_select_only("SELECT 1") is True
    assert is_select_only("DROP TABLE x") is False
    assert is_select_only("DELETE FROM x") is False


# ──────────────────────────────────────────────────────────────────────
# Слой 6 — FastAPI через TestClient с замоканным InferenceEngine
# ──────────────────────────────────────────────────────────────────────
@check("FastAPI: /health, /schema, /query с подменённым engine")
def _():
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        raise AssertionError("Поставь fastapi[all] или httpx — TestClient недоступен")

    from src.api import dependencies as deps
    from src.api.main import app
    from src.models.inference import GenerationResult

    class FakeEngine:
        loaded = True
        base_model_name = "Qwen/Qwen2.5-Coder-3B-Instruct"
        def generate(self, schema, question, vocabulary=None, **kw):
            # Эмулируем валидный SQL — pipeline должен пропустить через guardrail.
            sql = "SELECT SUM(amount) FROM orders WHERE status = 'paid'"
            return GenerationResult(sql=sql, raw_output=sql)

    app.dependency_overrides[deps.get_engine] = lambda: FakeEngine()
    try:
        with TestClient(app) as client:
            # /health
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json()["model_loaded"] is True

            # /schema на реальной demo-базе
            db_path = ROOT / "data" / "demo" / "sales.sqlite"
            r = client.post("/schema", json={
                "connection_string": str(db_path),
                "include_samples": True,
            })
            assert r.status_code == 200, r.text
            tables = r.json()["tables"]
            assert {t["name"] for t in tables} == {
                "customers", "managers", "products", "orders", "order_items"
            }

            # /query на реальной demo-базе, FakeEngine отдаст валидный SELECT
            r = client.post("/query", json={
                "question": "Какая выручка за оплаченные заказы?",
                "connection_string": str(db_path),
                "execute": True,
                "vocabulary": {
                    "company": "Демо",
                    "terms": {"выручка": "SUM(amount) WHERE status='paid'"},
                },
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["is_valid_sql"] is True
            assert body["execution"] is not None
            assert body["execution"]["rows"][0][0] > 0

            # /query с DELETE — должен быть отбит guardrail'ом
            class DropEngine(FakeEngine):
                def generate(self, *a, **kw):
                    return GenerationResult(
                        sql="DELETE FROM orders WHERE id=1",
                        raw_output="DELETE FROM orders WHERE id=1",
                    )
            app.dependency_overrides[deps.get_engine] = lambda: DropEngine()
            r = client.post("/query", json={
                "question": "Удали заказ 1",
                "connection_string": str(db_path),
                "execute": True,
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["execution"] is None
            assert body["error"] and "гвардейл" in body["error"].lower()
    finally:
        app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────────────
# Слой 7 — опциональный инференс реальной модели
# ──────────────────────────────────────────────────────────────────────
def run_model_smoke():
    @check("InferenceEngine: загрузка модели и одна генерация")
    def _():
        from src.business.vocabulary import BusinessVocabulary
        from src.db.connector import DbConnector
        from src.models.inference import InferenceEngine

        engine = InferenceEngine()
        engine.load()
        assert engine.loaded
        schema = DbConnector(str(ROOT / "data" / "demo" / "sales.sqlite")).render_schema()
        vocab = BusinessVocabulary.from_yaml(ROOT / "configs" / "example_vocabulary.yaml")
        res = engine.generate(schema, "Какая суммарная выручка за 2026 год?", vocab)
        assert res.sql and res.sql.upper().startswith("SELECT"), \
            f"Модель вернула: {res.raw_output!r}"


# ──────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-model", action="store_true",
        help="Дополнительно прогнать реальный инференс Qwen (медленно, ~30 сек на CPU)",
    )
    args = parser.parse_args()

    if args.with_model:
        run_model_smoke()

    print()
    print("=" * 64)
    print("Smoke-проверка Ru2SQL")
    print("=" * 64)
    for status, name, info in results:
        color = GREEN if status == "OK" else RED
        mark = "✓" if status == "OK" else "✗"
        print(f"  {color}{mark}{RESET} {name}  {YELLOW}[{info}]{RESET}")
    ok = sum(1 for s, _, _ in results if s == "OK")
    print("=" * 64)
    summary_color = GREEN if ok == len(results) else RED
    print(f"  {summary_color}{ok} / {len(results)} проверок пройдено{RESET}")
    print("=" * 64)
    if ok < len(results):
        print()
        print("Подсказка: запусти 'pytest -v' для подробных диагностик.")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()

---
title: Ru2SQL
emoji: 🗄️
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# ru2sql

Генеративная модель для преобразования вопросов на русском языке в SQL-запросы.
Практическая часть ВКР, направление «Программная инженерия», 4 курс.

**Стек:** Python 3.10+, PyTorch, transformers, PEFT (LoRA), FastAPI, Streamlit, sqlglot.
**Основная модель:** Qwen2.5-Coder-3B-Instruct, дообученная методом QLoRA на датасете PAUQ.
**Сравнение:** ruT5-base baseline + GigaChat API.

См. `plan_VKR_text2sql_ru.md` для полного плана работ.

---

## Архитектура

```
┌─────────────────────┐    HTTP     ┌──────────────────────┐
│  Streamlit-клиент   │ ─────────►  │   FastAPI REST API   │
│  (порт 8501)        │             │   (порт 8000)        │
└─────────────────────┘             └──────────┬───────────┘
                                               │
                            ┌──────────────────┼──────────────────┐
                            ▼                  ▼                  ▼
                  ┌──────────────────┐ ┌──────────────┐ ┌────────────────┐
                  │ InferenceEngine  │ │ SchemaProvi- │ │ BusinessVocab- │
                  │ Qwen + LoRA      │ │ der + Sql-   │ │ ulary (YAML)   │
                  │                  │ │ Executor     │ │                │
                  └──────────────────┘ └──────────────┘ └────────────────┘
```

Streamlit-интерфейс не вызывает модель напрямую — он обращается к REST API
через `httpx`. Это позволяет запускать UI и инференс на разных машинах,
а также подключать к API любых сторонних клиентов.

---

## Быстрый старт

### 1. Установка

```bash
pip install uv
git clone <твой-репо> ru2sql
cd ru2sql
uv venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
uv pip install -e ".[dev]"
```

### 2. Конфигурация

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/Mac
```

Заполни в `.env`:
- `BASE_MODEL_NAME` (по умолчанию Qwen/Qwen2.5-Coder-3B-Instruct),
- `LORA_ADAPTER_PATH` (локальная папка или HF-repo),
- опционально — API-ключ GigaChat для baseline-сравнения.

Если HuggingFace недоступен из вашей сети, добавь:
```
HF_ENDPOINT=https://hf-mirror.com
```

### 3. Тесты

```bash
pytest -v
```

Ожидаемо: 80+ зелёных тестов.

### 4. Smoke-проверка

Быстрая (5 сек, без модели):
```bash
python scripts/smoke_local.py
```

Полная (с загрузкой Qwen, ~5 минут на CPU):
```bash
python scripts/smoke_local.py --with-model
```

### 5. Запуск приложения

Нужны **два процесса** — API и UI:

**Окно 1** — REST API:
```bash
uvicorn src.api.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
```

**Окно 2** — Streamlit-интерфейс:
```bash
streamlit run streamlit_app.py
# UI: http://127.0.0.1:8501
```

При первом запуске модель Qwen2.5-Coder-3B (~6 GB) скачивается из HuggingFace
Hub. На CPU инференс одного запроса занимает 15–30 секунд — это ожидаемо.

Адрес API можно переопределить переменной окружения:
```bash
set RU2SQL_API_URL=http://192.168.1.10:8000     # Windows
# export RU2SQL_API_URL=http://192.168.1.10:8000  # Linux/Mac
```

---

## REST API

### Базовые эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET  | `/health`        | статус сервиса и загруженной модели |
| GET  | `/databases`     | список БД из data/databases (PAUQ-структура) |
| POST | `/generate-sql`  | генерация SQL по db_id из PAUQ |
| POST | `/schema`        | схема произвольной БД по connection string |
| POST | `/query`         | полный pipeline для произвольной БД |

### Пример: запрос к произвольной БД

```bash
curl -X POST http://127.0.0.1:8000/query \
     -H "Content-Type: application/json" \
     -d '{
       "question": "Какая выручка за 2026 год?",
       "connection_string": "sqlite:///data/demo/sales.sqlite",
       "execute": true,
       "vocabulary": {
         "company": "Демо-магазин",
         "terms": {"выручка": "SUM(orders.amount) WHERE status='paid'"}
       }
     }'
```

Ответ содержит `sql`, `raw_output`, `is_valid_sql`, `gen_time_seconds` и
опционально `execution` с результатами выполнения. Перед исполнением
SQL проходит AST-уровневую проверку (см. `is_select_only` в
`src/models/postprocess.py`) — DDL и DML на БД через API невозможны.

### Пример: PAUQ-режим (старый эндпоинт)

```bash
curl -X POST http://127.0.0.1:8000/generate-sql \
     -H "Content-Type: application/json" \
     -d '{"question": "Сколько студентов на факультете ПИ?", "db_id": "university"}'
```

---

## Обучение модели

Тренировка идёт **в Kaggle Notebook** (бесплатный T4 GPU). Локально на CPU/AMD GPU
обучить 3B-модель не получится.

Шаги:
1. Открой `notebooks/kaggle_train_qwen_qlora.ipynb` на kaggle.com.
2. В Settings выбери Accelerator: GPU T4 x1.
3. Add-ons → Secrets → добавь `HF_TOKEN` и `WANDB_API_KEY`.
4. Запусти все ячейки. Тренировка ~4–6 часов.
5. По завершении адаптер пушится на твой приватный HF-репо.
6. Скачай его на десктоп:
   ```bash
   huggingface-cli download your-username/qwen-coder-pauq-lora \
       --local-dir checkpoints/qwen-coder-pauq-lora
   ```

После этого `LORA_ADAPTER_PATH` в `.env` укажет на скачанный адаптер,
и API будет использовать дообученную модель.

---

## Структура проекта

```
ru2sql/
├── pyproject.toml              # зависимости
├── .env.example                # шаблон конфигурации
├── plan_VKR_text2sql_ru.md     # план работ
├── notebooks/
│   └── kaggle_train_qwen_qlora.ipynb
├── scripts/
│   └── smoke_local.py          # локальная проверка работоспособности
├── configs/
│   ├── example_vocabulary.yaml
│   └── sales_vocabulary.yaml
├── src/
│   ├── config.py               # настройки через pydantic-settings
│   ├── data/
│   │   ├── loader.py           # чтение PAUQ JSON
│   │   ├── schema_provider.py  # SchemaProvider — единый интерфейс
│   │   ├── schema.py           # SchemaRetriever (фасад для PAUQ)
│   │   └── prompt.py           # PromptBuilder + chat-template
│   ├── db/
│   │   ├── connector.py        # DbConnector — чтение схем
│   │   └── executor.py         # SqlExecutor с read-only
│   ├── business/
│   │   └── vocabulary.py       # BusinessVocabulary (YAML-конфиг)
│   ├── models/
│   │   ├── inference.py        # InferenceEngine (модель + LoRA)
│   │   └── postprocess.py      # очистка SQL + guardrail
│   ├── evaluation/
│   │   ├── metrics.py          # EM + Execution Accuracy
│   │   └── evaluate.py         # CLI для прогона на split
│   └── api/
│       ├── main.py             # FastAPI app (5 эндпоинтов)
│       ├── schemas.py          # Pydantic-модели
│       └── dependencies.py     # lifespan + DI
├── streamlit_app.py            # UI (HTTPX-клиент к API)
└── tests/                      # 80+ тестов
    ├── test_prompt.py
    ├── test_postprocess.py
    ├── test_metrics.py
    ├── test_schema.py
    ├── test_schema_provider.py
    ├── test_vocabulary.py
    └── test_db.py
```

---

## Прогон оценки

```bash
# Полный прогон на dev split
python -m src.evaluation.evaluate --split dev

# Быстрая проверка на 50 примерах
python -m src.evaluation.evaluate --split dev --limit 50
```

Результат сохраняется в `results/predictions.jsonl`, метрики печатаются в stdout.

---

## Метрики

| Модель | EM | Execution Accuracy |
|---|---|---|
| ruT5-base (baseline) | 25–35 % | 30–40 % |
| **Qwen2.5-Coder-3B + QLoRA** | **40,0 %** | **71,9 %** |
| BRIDGE / RAT-SQL (PAUQ, mono) | 51 / 52 % | 48 / 49 % |

---

## Что НЕ входит в MVP

Сознательно оставлено в раздел «направления дальнейшей работы»:
- Few-shot retrieval похожих примеров.
- Schema linking (автоматический отбор релевантных таблиц).
- Self-correction по ошибкам исполнения SQL.
- Constrained decoding (грамматика SQL).
- Дообучение на синтетических данных.

---

## Лицензия и атрибуция

Учебный проект. Использует:
- PAUQ — Apache 2.0, https://github.com/ai-forever/pauq
- Qwen2.5-Coder — Apache 2.0, https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct
- ruT5 — MIT, https://huggingface.co/ai-forever/ruT5-base

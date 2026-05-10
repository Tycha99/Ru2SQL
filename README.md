---
title: Ru2SQL
emoji: 🗄️
colorFrom: blue
colorTo: purple
sdk: streamlit
sdk_version: 1.35.0
app_file: streamlit_app.py
pinned: false
---

# ru2sql

Генеративная модель для преобразования вопросов на русском языке в SQL-запросы.
Практическая часть ВКР, направление «Программная инженерия», 4 курс.

**Стек:** Python 3.10+, PyTorch, transformers, PEFT (LoRA), FastAPI, sqlglot.
**Основная модель:** Qwen2.5-Coder-3B-Instruct, дообученная методом QLoRA на датасете PAUQ.
**Сравнение:** ruT5-base baseline + GigaChat API.

См. `plan_VKR_text2sql_ru.md` для полного плана работ на месяц.

---

## Быстрый старт (на десктопе)

### 1. Установка

```bash
# Установи uv (https://docs.astral.sh/uv/) если ещё нет
pip install uv

# Клонируй репозиторий и установи зависимости
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

Открой `.env` и заполни ключи (минимум `GIGACHAT_API_KEY` для baseline-сравнения, остальное опционально).

### 3. Скачай PAUQ

```bash
git clone https://github.com/ai-forever/pauq.git data/pauq_repo
# Затем разложи train.json/dev.json/test.json в data/pauq/
# и SQLite-файлы в data/databases/{db_id}/{db_id}.sqlite
```

### 4. Тесты

```bash
pytest -v
```

Тесты для модулей `prompt`, `postprocess`, `metrics`, `schema` должны проходить
без скачивания модели и датасета.

### 5. Запуск API

```bash
uvicorn src.api.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
```

При первом запуске модель Qwen2.5-Coder-3B (~6 GB) скачается из HuggingFace Hub.
На CPU инференс занимает 15–30 секунд на запрос — это ожидаемо.

### 6. Запрос к API

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
2. В Settings выбери Accelerator: GPU T4 x1 (или x2 для скорости).
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
├── pyproject.toml              # зависимости (uv)
├── .env.example                # шаблон конфигурации
├── plan_VKR_text2sql_ru.md     # план работ на месяц
├── notebooks/
│   └── kaggle_train_qwen_qlora.ipynb
├── src/
│   ├── config.py               # настройки через pydantic-settings
│   ├── data/
│   │   ├── loader.py           # чтение PAUQ JSON
│   │   ├── schema.py           # SchemaRetriever (DDL из SQLite)
│   │   └── prompt.py           # PromptBuilder + chat-template
│   ├── models/
│   │   ├── inference.py        # InferenceEngine (модель + LoRA)
│   │   └── postprocess.py      # очистка SQL + sqlglot валидация
│   ├── evaluation/
│   │   ├── metrics.py          # Exact Match + Execution Accuracy
│   │   └── evaluate.py         # CLI для прогона на split'е
│   └── api/
│       ├── main.py             # FastAPI app
│       ├── schemas.py          # Pydantic-модели
│       └── dependencies.py     # lifespan + DI
└── tests/
    ├── test_prompt.py
    ├── test_postprocess.py
    ├── test_metrics.py
    └── test_schema.py
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

## Метрики (планируемые)

| Модель | EM | Execution Accuracy |
|---|---|---|
| ruT5-base (baseline) | 25–35% | 30–40% |
| **Qwen2.5-Coder-3B + QLoRA** | **50–60%** | **55–70%** |
| GigaChat API (zero-shot) | 55–70% | 65–80% |

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

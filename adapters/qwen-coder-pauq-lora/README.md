---
library_name: peft
base_model: Qwen/Qwen2.5-Coder-3B-Instruct
language:
  - ru
tags:
  - text-to-sql
  - qlora
  - russian
  - sql-generation
license: apache-2.0
datasets:
  - ai-forever/PAUQ
---

# qwen-coder-pauq-lora

LoRA-адаптер для модели **Qwen2.5-Coder-3B-Instruct**, обученный методом
**QLoRA** на датасете **PAUQ** для задачи преобразования вопросов на
русском языке в SQL-запросы. Часть выпускной квалификационной работы
по направлению 09.03.04 «Программная инженерия», КНИТУ-КАИ.

## Описание

Адаптер обучает модель отвечать на русскоязычный аналитический вопрос
синтаксически корректным SQL-запросом, учитывая схему конкретной базы
данных, переданную в системном сообщении вместе с примерами строк.

Базовая модель остаётся замороженной, обучаются только LoRA-матрицы
рангом 16, наложенные на все проекционные слои attention и MLP. Это
позволяет хранить и распространять адаптер размером несколько десятков
мегабайт, а не полные веса модели в несколько гигабайт.

## Использование

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base = "Qwen/Qwen2.5-Coder-3B-Instruct"
adapter = "Tyycha/qwen-coder-pauq-lora"

tokenizer = AutoTokenizer.from_pretrained(base)
model = AutoModelForCausalLM.from_pretrained(base, device_map="auto")
model = PeftModel.from_pretrained(model, adapter)
model.eval()

messages = [
    {"role": "system", "content": "Ты — ассистент, который преобразует вопросы на русском языке в SQL..."},
    {"role": "user", "content": "### Schema:\nCREATE TABLE orders (id INT, amount REAL, status TEXT);\n\n### Question:\nКакая суммарная выручка по оплаченным заказам?\n\n### SQL:\n"},
]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
output = model.generate(**inputs, max_new_tokens=256, do_sample=False)
print(tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True))
```

Полный pipeline (формирование промпта, постобработка, исполнение SQL)
реализован в проекте [Ru2SQL](https://github.com/Tyycha/Ru2SQL).

## Данные

- **Датасет:** PAUQ (Bakshandaeva et al., 2022) — первый крупный русскоязычный
  корпус для задачи Text-to-SQL, построенный на основе Spider.
- **Размер:** ~7 тыс. пар (вопрос, SQL) в train, 1076 в dev.
- **Структура примера:** диалог в формате chat-template из трёх сообщений
  (`system` с инструкцией и опциональным бизнес-словарём, `user` со
  схемой и вопросом, `assistant` с эталонным SQL).

## Гиперпараметры обучения

| Параметр | Значение |
|---|---|
| Базовая модель | Qwen/Qwen2.5-Coder-3B-Instruct |
| Метод | QLoRA (NF4, double quantization, compute dtype = bfloat16) |
| LoRA rank `r` | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Эпохи | 2 |
| Размер батча | 1 (на устройство) |
| Накопление градиентов | 8 шагов (эффективный батч 8) |
| Скорость обучения | 2e-4 (cosine, warmup 3 %) |
| Max sequence length | 1024 |
| Точность | bfloat16 |
| Оборудование | NVIDIA Tesla T4 16 GB (Kaggle) |

## Метрики

Оценка на валидационной выборке PAUQ (1076 примеров, 166 баз данных):

| Метрика | Значение |
|---|---|
| Exact Match (EM) | 40.0 % (430 / 1076) |
| Execution Accuracy (EX) | 71.9 % (772 / 1074) |

Для сравнения, опубликованные результаты на той же выборке:

| Модель | EM | EX |
|---|---|---|
| RAT-SQL (PAUQ, mono) | 51 % | 49 % |
| BRIDGE (PAUQ, mono) | 52 % | 48 % |
| **Qwen2.5-Coder-3B + QLoRA (эта работа)** | **40 %** | **71.9 %** |

Высокий разрыв между EM и EX отражает специфику задачи: модель
генерирует семантически корректные запросы, но синтаксически
отличающиеся от эталонных (другой порядок условий, альтернативные
JOIN-стратегии, иные псевдонимы).

## Ограничения

- Модель обучена на схемах PAUQ/Spider. На существенно отличающихся
  предметных областях качество может падать; для адаптации
  предусмотрен механизм бизнес-словаря в основном проекте.
- Наиболее сложные классы запросов — вложенные SELECT, конструкции
  INTERSECT/EXCEPT/UNION, HAVING с несколькими условиями — остаются
  слабым местом.
- При работе на CPU без GPU инференс занимает 15–30 секунд на запрос.
- Адаптер ориентирован на SQLite. Для PostgreSQL/MySQL рекомендуется
  явно указать диалект в промпте.

## Лицензия

Apache 2.0. Базовая модель Qwen2.5-Coder также распространяется под
лицензией Apache 2.0; датасет PAUQ — Apache 2.0.

## Цитирование

```bibtex
@misc{ru2sql-qlora-2026,
  title  = {Ru2SQL: Russian Text-to-SQL via QLoRA on Qwen2.5-Coder},
  author = {Siryazeev, Danis},
  year   = {2026},
  note   = {Bachelor's thesis, Kazan National Research Technical University},
}
```

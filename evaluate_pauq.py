"""
Скрипт прогона метрик Ru2SQL на валидационной выборке PAUQ.

Считает Exact Match (EM) и Execution Accuracy (EX) для дообученной модели
Qwen2.5-Coder-3B + QLoRA. Используется на Kaggle (T4 GPU), результат
сохраняется в eval_results.csv и eval_summary.json.

Источник цифр для раздела 4.3 пояснительной записки.

Использование на Kaggle:
  1. Загрузить проект целиком (через Kaggle Dataset или git clone).
  2. Установить ADAPTER_ID на свой HF-репо.
  3. python evaluate_pauq.py

Постобработка и нормализация SQL импортируются из src/models/postprocess.py,
чтобы метрики локально и на Kaggle оставались сопоставимыми.
"""

import sys
from pathlib import Path

# Делаем пакет src/ импортируемым, когда скрипт запускается из корня.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import csv
import json
import sqlite3

from tqdm import tqdm

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from datasets import load_dataset

from src.models.postprocess import (
    normalize_sql,
    strip_model_artifacts as strip_artifacts,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

BASE_MODEL_ID  = "Qwen/Qwen2.5-Coder-3B-Instruct"
ADAPTER_ID     = "Tyycha/qwen-coder-pauq-lora"
PAUQ_SPLIT     = "validation"   # 1034 примера
MAX_NEW_TOKENS = 256
DEVICE         = "cuda" if torch.cuda.is_available() else "cpu"

# Путь к папке с SQLite-базами PAUQ (Spider databases)
# На Kaggle: скачай https://drive.google.com/uc?id=1iRDVHLr4mX2wQKSgA9VxUUFpj-3-Kj5B
# Или используй датасет: kaggle datasets download -d wikisql/spider
PAUQ_DB_DIR    = Path("./pauq_databases")   # папка, где лежат папки баз данных

# ─── OUTPUT ───────────────────────────────────────────────────────────────────

RESULTS_FILE   = "eval_results.csv"
SUMMARY_FILE   = "eval_summary.json"

# ─── LOAD MODEL ───────────────────────────────────────────────────────────────

print("Loading model...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, trust_remote_code=True)
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)
model = PeftModel.from_pretrained(base_model, ADAPTER_ID)
model.eval()
print(f"Model loaded on {DEVICE}")

# ─── SCHEMA RETRIEVER ─────────────────────────────────────────────────────────

def get_schema(db_id: str) -> str:
    """Extract CREATE TABLE statements from SQLite database."""
    db_path = PAUQ_DB_DIR / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        return f"-- Database {db_id} not found"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    
    schema_parts = []
    for table in tables:
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
        create_sql = cursor.fetchone()
        if create_sql and create_sql[0]:
            schema_parts.append(create_sql[0])
            # Add sample rows
            try:
                cursor.execute(f"SELECT * FROM \"{table}\" LIMIT 3")
                rows = cursor.fetchall()
                cursor.execute(f"PRAGMA table_info(\"{table}\")")
                cols = [col[1] for col in cursor.fetchall()]
                if rows:
                    schema_parts.append(f"-- Sample data for {table}:")
                    schema_parts.append("-- " + " | ".join(cols))
                    for row in rows[:3]:
                        schema_parts.append("-- " + " | ".join(str(v) for v in row))
            except Exception:
                pass
    
    conn.close()
    return "\n\n".join(schema_parts)

# ─── PROMPT BUILDER ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Ты — ассистент, который преобразует вопросы на русском языке в SQL-запросы. "
    "Отвечай ТОЛЬКО SQL-запросом без объяснений, комментариев и markdown-разметки."
)

def build_prompt(question: str, schema: str) -> str:
    user_msg = f"Schema:\n{schema}\n\nQuestion: {question}\n\nSQL:"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_msg},
    ]
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

# ─── SQL POSTPROCESSING ───────────────────────────────────────────────────────
# strip_artifacts и normalize_sql импортируются из src/models/postprocess.py
# для гарантии того, что метрики на Kaggle и в локальных тестах считаются
# по одной и той же логике.

# ─── EXECUTION ────────────────────────────────────────────────────────────────

def execute_sql(sql: str, db_id: str):
    """Execute SQL and return result set as frozenset of tuples."""
    db_path = PAUQ_DB_DIR / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        return None
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return frozenset(tuple(str(v) for v in row) for row in rows)
    except Exception:
        return None

# ─── INFERENCE ────────────────────────────────────────────────────────────────

def generate_sql(question: str, schema: str) -> str:
    prompt = build_prompt(question, schema)
    inputs = tokenizer(prompt, return_tensors="pt").to(DEVICE)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )
    
    generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return strip_artifacts(generated)

# ─── MAIN EVALUATION LOOP ─────────────────────────────────────────────────────

def main():
    print(f"Loading PAUQ {PAUQ_SPLIT} split...")
    dataset = load_dataset("ai-forever/PAUQ", split=PAUQ_SPLIT)
    print(f"Loaded {len(dataset)} examples")
    
    results = []
    em_correct = 0
    ex_correct = 0
    ex_total   = 0  # only count where execution was possible
    
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "idx", "db_id", "question", "gold_sql", "pred_sql",
            "em", "ex", "error"
        ])
        writer.writeheader()
        
        for idx, example in enumerate(tqdm(dataset, desc="Evaluating")):
            question  = example.get("question_ru") or example.get("question", "")
            gold_sql  = example.get("query", "")
            db_id     = example.get("db_id", "")
            
            try:
                schema   = get_schema(db_id)
                pred_sql = generate_sql(question, schema)
                
                # Exact Match
                norm_pred = normalize_sql(pred_sql)
                norm_gold = normalize_sql(gold_sql)
                em = int(norm_pred == norm_gold)
                
                # Execution Accuracy
                pred_result = execute_sql(pred_sql, db_id)
                gold_result = execute_sql(gold_sql, db_id)
                
                if gold_result is not None:
                    ex = int(pred_result == gold_result)
                    ex_correct += ex
                    ex_total   += 1
                else:
                    ex = None
                
                em_correct += em
                error = ""
                
            except Exception as e:
                pred_sql = ""
                em = 0
                ex = None
                error = str(e)[:200]
            
            row = {
                "idx": idx, "db_id": db_id, "question": question,
                "gold_sql": gold_sql, "pred_sql": pred_sql,
                "em": em, "ex": ex, "error": error
            }
            writer.writerow(row)
            results.append(row)
            
            # Progress every 100 examples
            if (idx + 1) % 100 == 0:
                cur_em = em_correct / (idx + 1)
                cur_ex = ex_correct / max(ex_total, 1)
                print(f"[{idx+1}/{len(dataset)}] EM={cur_em:.3f}  EX={cur_ex:.3f}")
    
    # Final summary
    n = len(dataset)
    final_em = em_correct / n
    final_ex = ex_correct / max(ex_total, 1)
    
    summary = {
        "model": ADAPTER_ID,
        "split": PAUQ_SPLIT,
        "n_examples": n,
        "exact_match": round(final_em, 4),
        "execution_accuracy": round(final_ex, 4),
        "em_correct": em_correct,
        "ex_correct": ex_correct,
        "ex_total": ex_total
    }
    
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*50)
    print(f"RESULTS on PAUQ {PAUQ_SPLIT} ({n} examples)")
    print(f"  Exact Match (EM):          {final_em:.1%}  ({em_correct}/{n})")
    print(f"  Execution Accuracy (EX):   {final_ex:.1%}  ({ex_correct}/{ex_total})")
    print(f"\nDetailed results saved to: {RESULTS_FILE}")
    print(f"Summary saved to:          {SUMMARY_FILE}")

if __name__ == "__main__":
    main()

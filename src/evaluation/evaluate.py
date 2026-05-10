"""Скрипт прогона модели на test-сплите PAUQ.

Использование:
    python -m src.evaluation.evaluate --split dev --limit 50
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tqdm import tqdm

from src.config import settings
from src.data.loader import load_pauq_split
from src.data.schema import SchemaRetriever
from src.evaluation.metrics import compute_metrics
from src.models.inference import InferenceEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev", choices=["train", "dev", "test"])
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число примеров")
    parser.add_argument("--output", type=Path, default=Path("results/predictions.jsonl"))
    args = parser.parse_args()

    split_path = settings.pauq_data_dir / f"{args.split}.json"
    examples = load_pauq_split(split_path)
    if args.limit:
        examples = examples[: args.limit]

    schema_ret = SchemaRetriever(settings.databases_dir)
    engine = InferenceEngine()
    engine.load()

    predictions: list[str] = []
    golds: list[str] = []
    db_ids: list[str] = []
    rows = []

    for ex in tqdm(examples, desc="Inference"):
        try:
            schema = schema_ret.render_schema(ex.db_id)
        except FileNotFoundError:
            continue
        result = engine.generate(schema, ex.question)
        predictions.append(result.sql)
        golds.append(ex.query)
        db_ids.append(ex.db_id)
        rows.append(
            {
                "db_id": ex.db_id,
                "question": ex.question,
                "gold": ex.query,
                "pred": result.sql,
                "raw": result.raw_output,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    metrics = compute_metrics(predictions, golds, db_ids, settings.databases_dir)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

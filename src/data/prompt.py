"""PromptBuilder — формирует input для модели в формате chat-template."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "Ты — ассистент, который преобразует вопросы на русском языке в корректные SQL-запросы. "
    "Тебе даётся схема базы данных в виде CREATE TABLE statements и пример нескольких строк. "
    "Сгенерируй один SQL-запрос, который отвечает на вопрос пользователя. "
    "Возвращай ТОЛЬКО SQL без объяснений, без markdown, без префиксов."
)


def build_user_message(schema: str, question: str) -> str:
    return f"### Schema:\n{schema}\n\n### Question:\n{question}\n\n### SQL:\n"


def build_chat_messages(schema: str, question: str) -> list[dict]:
    """Формат для tokenizer.apply_chat_template."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(schema, question)},
    ]


def build_training_example(schema: str, question: str, sql: str) -> list[dict]:
    """Полный диалог для SFT с ответом ассистента."""
    msgs = build_chat_messages(schema, question)
    msgs.append({"role": "assistant", "content": sql.strip()})
    return msgs

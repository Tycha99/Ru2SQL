"""Тесты на PromptBuilder.

Покрывают как базовое формирование chat-template, так и опциональную
интеграцию BusinessVocabulary в системное сообщение (раздел 3.6 ВКР).
"""

from src.business.vocabulary import BusinessVocabulary
from src.data.prompt import (
    BASE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_chat_messages,
    build_system_message,
    build_training_example,
    build_user_message,
)


def test_user_message_contains_parts():
    msg = build_user_message("CREATE TABLE t (id INT);", "Покажи всё")
    assert "Schema:" in msg
    assert "Question:" in msg
    assert "SQL:" in msg
    assert "CREATE TABLE" in msg
    assert "Покажи всё" in msg


def test_chat_messages_have_system_and_user():
    msgs = build_chat_messages("schema", "question")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == BASE_SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"


def test_training_example_has_assistant():
    msgs = build_training_example("schema", "question", "SELECT 1")
    assert len(msgs) == 3
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "SELECT 1"


def test_legacy_system_prompt_alias():
    assert SYSTEM_PROMPT == BASE_SYSTEM_PROMPT


def test_system_message_without_vocabulary():
    assert build_system_message(None) == BASE_SYSTEM_PROMPT


def test_system_message_with_empty_vocabulary():
    vocab = BusinessVocabulary.empty()
    assert build_system_message(vocab) == BASE_SYSTEM_PROMPT


def test_system_message_with_terms():
    vocab = BusinessVocabulary(
        company="ООО Ромашка",
        terms={"выручка": "SUM(orders.amount) WHERE orders.status = 'paid'"},
    )
    msg = build_system_message(vocab)
    assert msg.startswith(BASE_SYSTEM_PROMPT)
    assert "ООО Ромашка" in msg
    assert "выручка" in msg
    assert "SUM(orders.amount)" in msg


def test_chat_messages_with_vocabulary_keeps_user_clean():
    vocab = BusinessVocabulary(
        terms={"выручка": "SUM(amount) WHERE status='paid'"},
    )
    msgs = build_chat_messages("schema", "Какая выручка?", vocabulary=vocab)
    assert msgs[0]["role"] == "system"
    assert "SUM(amount)" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert "SUM(amount)" not in msgs[1]["content"]
    assert "Какая выручка?" in msgs[1]["content"]


def test_training_example_with_vocabulary():
    vocab = BusinessVocabulary(terms={"топ": "ORDER BY x DESC LIMIT 10"})
    msgs = build_training_example(
        "schema", "Топ клиентов", "SELECT 1", vocabulary=vocab
    )
    assert len(msgs) == 3
    assert msgs[0]["role"] == "system"
    assert "ORDER BY x DESC" in msgs[0]["content"]
    assert msgs[2]["role"] == "assistant"

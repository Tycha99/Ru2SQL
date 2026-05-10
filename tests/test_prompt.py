"""Тесты на PromptBuilder."""

from src.data.prompt import (
    SYSTEM_PROMPT,
    build_chat_messages,
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
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"


def test_training_example_has_assistant():
    msgs = build_training_example("schema", "question", "SELECT 1")
    assert len(msgs) == 3
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "SELECT 1"

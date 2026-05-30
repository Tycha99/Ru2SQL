"""PromptBuilder — формирование chat-template input для модели.

Соответствует разделу 2.4 пояснительной записки. Один и тот же билдер
используется при обучении (формирование SFT-примеров) и при инференсе
(формирование запроса к загруженной модели), что гарантирует совпадение
формата train- и inference-time промптов.

Помимо схемы и вопроса, билдер опционально принимает BusinessVocabulary
(раздел 3.6 ВКР). Бизнес-термины подмешиваются в системное сообщение,
а не конкатенируются к пользовательскому вопросу — это согласуется с
тем, как современные instruction-tuned модели интерпретируют роли
сообщений в chat-template.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.business.vocabulary import BusinessVocabulary


BASE_SYSTEM_PROMPT = (
    "Ты — ассистент, который преобразует вопросы на русском языке в корректные SQL-запросы. "
    "Тебе даётся схема базы данных в виде CREATE TABLE statements и пример нескольких строк. "
    "Сгенерируй один SQL-запрос, который отвечает на вопрос пользователя. "
    "Возвращай ТОЛЬКО SQL без объяснений, без markdown, без префиксов."
)


def build_user_message(schema: str, question: str) -> str:
    """Пользовательская часть промпта в формате ``### Schema / ### Question / ### SQL:``."""
    return f"### Schema:\n{schema}\n\n### Question:\n{question}\n\n### SQL:\n"


def build_system_message(vocabulary: "BusinessVocabulary | None" = None) -> str:
    """Собирает системное сообщение.

    Если передан непустой бизнес-словарь, к базовому промпту добавляется
    блок с определениями терминов, фильтрами и правилами компании. Это
    позволяет адаптировать систему к терминологии конкретной организации
    без повторного дообучения модели.
    """
    if vocabulary is None or not vocabulary:
        return BASE_SYSTEM_PROMPT
    context = vocabulary.render_system_context()
    if not context:
        return BASE_SYSTEM_PROMPT
    return BASE_SYSTEM_PROMPT + "\n\n" + context


def build_chat_messages(
    schema: str,
    question: str,
    vocabulary: "BusinessVocabulary | None" = None,
) -> list[dict]:
    """Сообщения для ``tokenizer.apply_chat_template``.

    Параметры
    ---------
    schema : str
        Текстовое представление схемы (CREATE TABLE + sample rows).
    question : str
        Вопрос пользователя на русском языке.
    vocabulary : BusinessVocabulary, optional
        Бизнес-словарь компании. Если передан — добавляется в системное
        сообщение, не нарушая структуры пользовательской реплики.
    """
    return [
        {"role": "system", "content": build_system_message(vocabulary)},
        {"role": "user", "content": build_user_message(schema, question)},
    ]


def build_training_example(
    schema: str,
    question: str,
    sql: str,
    vocabulary: "BusinessVocabulary | None" = None,
) -> list[dict]:
    """Полный диалог с эталонной репликой ассистента для Supervised
    Fine-Tuning (раздел 2.4 ВКР).
    """
    msgs = build_chat_messages(schema, question, vocabulary)
    msgs.append({"role": "assistant", "content": sql.strip()})
    return msgs


# Обратная совместимость. Имя SYSTEM_PROMPT использовалось в старом коде
# и в тестах; сохраняем алиас, чтобы не ломать импорты.
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT

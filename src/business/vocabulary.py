"""BusinessVocabulary — настраиваемый бизнес-словарь компании.

Позволяет аналитику один раз описать бизнес-термины и метрики компании в YAML-файле,
после чего модель правильно интерпретирует их в SQL-запросах.

Пример YAML-конфига (configs/example_vocabulary.yaml):
    company: "ООО Ромашка"
    terms:
      выручка: "SUM(orders.amount) WHERE orders.status = 'paid'"
      активный клиент: "клиент, совершивший покупку за последние 90 дней"
      этот год: "YEAR(order_date) = strftime('%Y', 'now')"
      прошлый месяц: "strftime('%Y-%m', order_date) = strftime('%Y-%m', 'now', '-1 month')"

    filters:
      только_оплаченные: "orders.status = 'paid'"
      без_возвратов: "orders.is_return = 0"

Пример использования:
    vocab = BusinessVocabulary.from_yaml("configs/my_company.yaml")
    enriched_prompt = vocab.enrich_prompt("Какая выручка за январь?")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


@dataclass
class BusinessVocabulary:
    """Хранит бизнес-термины и метрики компании, подставляет их в промпт модели."""

    company: str = ""
    terms: dict[str, str] = field(default_factory=dict)
    filters: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Загрузка
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BusinessVocabulary":
        """Загружает словарь из YAML-файла."""
        if not _YAML_AVAILABLE:
            raise ImportError("Установи PyYAML: pip install pyyaml")
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Файл бизнес-словаря не найден: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            company=data.get("company", ""),
            terms=data.get("terms", {}),
            filters=data.get("filters", {}),
            notes=data.get("notes", []),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessVocabulary":
        """Создаёт словарь из словаря Python (удобно для API и Streamlit)."""
        return cls(
            company=data.get("company", ""),
            terms=data.get("terms", {}),
            filters=data.get("filters", {}),
            notes=data.get("notes", []),
        )

    @classmethod
    def empty(cls) -> "BusinessVocabulary":
        """Пустой словарь — для случая когда компания ещё не настроила термины."""
        return cls()

    # ------------------------------------------------------------------
    # Использование
    # ------------------------------------------------------------------

    def enrich_prompt(self, question: str) -> str:
        """Добавляет к вопросу пользователя контекст из бизнес-словаря.

        Если вопрос содержит известные термины — подставляет их определения.
        Возвращает обогащённый вопрос для подстановки в промпт модели.
        """
        if not self.terms and not self.filters and not self.notes:
            return question

        context_lines: list[str] = []

        # Находим термины которые упоминаются в вопросе
        question_lower = question.lower()
        relevant_terms = {
            term: definition
            for term, definition in self.terms.items()
            if term.lower() in question_lower
        }

        if relevant_terms:
            context_lines.append("Определения терминов компании:")
            for term, definition in relevant_terms.items():
                context_lines.append(f"  - {term}: {definition}")

        if self.filters:
            context_lines.append("Стандартные фильтры компании:")
            for name, condition in self.filters.items():
                context_lines.append(f"  - {name}: {condition}")

        if self.notes:
            context_lines.append("Дополнительные правила:")
            for note in self.notes:
                context_lines.append(f"  - {note}")

        if not context_lines:
            return question

        context = "\n".join(context_lines)
        return f"{question}\n\n[Контекст компании]\n{context}"

    def render_system_context(self) -> str:
        """Текст для системного промпта — описывает все термины компании."""
        if not self.terms and not self.filters and not self.notes:
            return ""

        lines: list[str] = []
        if self.company:
            lines.append(f"Компания: {self.company}")
            lines.append("")

        if self.terms:
            lines.append("Бизнес-термины и метрики:")
            for term, definition in self.terms.items():
                lines.append(f"  - «{term}» означает: {definition}")

        if self.filters:
            lines.append("")
            lines.append("Стандартные условия фильтрации:")
            for name, condition in self.filters.items():
                lines.append(f"  - {name}: {condition}")

        if self.notes:
            lines.append("")
            lines.append("Важные правила:")
            for note in self.notes:
                lines.append(f"  - {note}")

        return "\n".join(lines)

    def to_yaml_string(self) -> str:
        """Сериализует словарь обратно в YAML-строку (для редактора в Streamlit)."""
        if not _YAML_AVAILABLE:
            raise ImportError("Установи PyYAML: pip install pyyaml")
        data = {
            "company": self.company,
            "terms": self.terms,
            "filters": self.filters,
            "notes": self.notes,
        }
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def save_yaml(self, path: str | Path) -> None:
        """Сохраняет словарь в YAML-файл."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_yaml_string())

    def __bool__(self) -> bool:
        return bool(self.terms or self.filters or self.notes)

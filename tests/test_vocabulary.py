"""Тесты на BusinessVocabulary (раздел 3.6 пояснительной записки)."""

from pathlib import Path

import pytest

from src.business.vocabulary import BusinessVocabulary


# ──────────────────────────────────────────────────────────────────────
# Загрузка
# ──────────────────────────────────────────────────────────────────────

def test_empty_vocabulary_is_falsy():
    vocab = BusinessVocabulary.empty()
    assert not vocab
    assert vocab.render_system_context() == ""


def test_from_dict_basic():
    vocab = BusinessVocabulary.from_dict(
        {
            "company": "ООО Тест",
            "terms": {"выручка": "SUM(amount)"},
            "filters": {"paid": "status='paid'"},
            "notes": ["Период: 2025-01-01—2026-04-30"],
        }
    )
    assert bool(vocab)
    assert vocab.company == "ООО Тест"
    assert vocab.terms == {"выручка": "SUM(amount)"}
    assert vocab.filters == {"paid": "status='paid'"}
    assert vocab.notes == ["Период: 2025-01-01—2026-04-30"]


def test_from_yaml_roundtrip(tmp_path: Path):
    original = BusinessVocabulary(
        company="ООО Ромашка",
        terms={"выручка": "SUM(orders.amount)"},
        filters={"paid_only": "orders.status='paid'"},
        notes=["amount только в orders"],
    )
    path = tmp_path / "vocab.yaml"
    original.save_yaml(path)

    loaded = BusinessVocabulary.from_yaml(path)
    assert loaded.company == original.company
    assert loaded.terms == original.terms
    assert loaded.filters == original.filters
    assert loaded.notes == original.notes


def test_from_yaml_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        BusinessVocabulary.from_yaml(tmp_path / "does_not_exist.yaml")


# ──────────────────────────────────────────────────────────────────────
# enrich_prompt — обратная совместимость со старым Streamlit-кодом
# ──────────────────────────────────────────────────────────────────────

def test_enrich_prompt_pass_through_when_empty():
    vocab = BusinessVocabulary.empty()
    assert vocab.enrich_prompt("Какая выручка?") == "Какая выручка?"


def test_enrich_prompt_adds_term_definition():
    vocab = BusinessVocabulary(
        terms={"выручка": "SUM(amount) WHERE status='paid'"},
    )
    enriched = vocab.enrich_prompt("Какая выручка за январь?")
    assert "выручка" in enriched
    assert "SUM(amount)" in enriched
    assert "Какая выручка за январь?" in enriched


def test_enrich_prompt_case_insensitive_match():
    vocab = BusinessVocabulary(terms={"выручка": "SUM(amount)"})
    enriched = vocab.enrich_prompt("ВЫРУЧКА в этом месяце?")
    assert "SUM(amount)" in enriched


def test_enrich_prompt_ignores_unrelated_terms():
    vocab = BusinessVocabulary(
        terms={
            "выручка": "SUM(amount)",
            "топ клиентов": "ORDER BY SUM(amount) DESC",
        },
    )
    enriched = vocab.enrich_prompt("Какая выручка?")
    # Релевантный термин подмешан, посторонний — нет
    assert "SUM(amount)" in enriched
    assert "ORDER BY SUM(amount) DESC" not in enriched


# ──────────────────────────────────────────────────────────────────────
# render_system_context — то, что подмешивается в system-сообщение
# ──────────────────────────────────────────────────────────────────────

def test_render_system_context_empty():
    assert BusinessVocabulary.empty().render_system_context() == ""


def test_render_system_context_with_company():
    vocab = BusinessVocabulary(
        company="ООО Ромашка",
        terms={"выручка": "SUM(amount)"},
    )
    ctx = vocab.render_system_context()
    assert "ООО Ромашка" in ctx
    assert "выручка" in ctx
    assert "SUM(amount)" in ctx


def test_render_system_context_with_filters_and_notes():
    vocab = BusinessVocabulary(
        filters={"только_оплаченные": "orders.status='paid'"},
        notes=["amount только в orders"],
    )
    ctx = vocab.render_system_context()
    assert "только_оплаченные" in ctx
    assert "orders.status='paid'" in ctx
    assert "amount только в orders" in ctx

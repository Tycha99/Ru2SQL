"""Streamlit-интерфейс утилиты Ru2SQL.

Запуск:
    streamlit run streamlit_app.py

Что умеет:
    - Подключиться к любой SQLite/PostgreSQL/MySQL базе данных
    - Загрузить бизнес-словарь компании из YAML-файла или редактировать прямо в браузере
    - Принять вопрос на русском → сгенерировать SQL → выполнить → показать результат
    - Хранить историю запросов в текущей сессии
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

# Путь к src/
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ──────────────────────────────────────────────
# Конфигурация страницы
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Ru2SQL — Natural Language → SQL",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    .sql-box {
        background: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Courier New', monospace;
        font-size: 14px;
        padding: 16px;
        border-radius: 8px;
        border-left: 4px solid #89b4fa;
        white-space: pre-wrap;
        margin: 8px 0;
    }
    .metric-card {
        background: #313244;
        padding: 12px 16px;
        border-radius: 8px;
        text-align: center;
    }
    .status-ok  { color: #a6e3a1; font-weight: bold; }
    .status-err { color: #f38ba8; font-weight: bold; }
    .history-item {
        border-left: 3px solid #89b4fa;
        padding: 8px 12px;
        margin: 6px 0;
        background: #1e1e2e;
        border-radius: 0 6px 6px 0;
    }
    /* Скрыть кнопку Stop */
    button[kind="stop"] {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────
def _default_vocab_yaml() -> str:
    example = ROOT / "configs" / "example_vocabulary.yaml"
    if example.exists():
        return example.read_text(encoding="utf-8")
    return (
        "company: Моя компания\n\n"
        "terms:\n"
        "  выручка: SUM(orders.amount) WHERE status = 'paid'\n\n"
        "filters:\n"
        "  только_оплаченные: orders.status = 'paid'\n\n"
        "notes: []\n"
    )


def _init_state():
    defaults = {
        "history": [],
        "model_loaded": False,
        "engine": None,
        "db_connector": None,
        "db_executor": None,
        "vocabulary": None,
        "db_connection_string": "",
        "vocab_yaml": _default_vocab_yaml(),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────
@st.cache_resource(show_spinner="Загружаю модель… (~30 с на первый раз)")
def _load_engine():
    from src.models.inference import InferenceEngine
    engine = InferenceEngine()
    engine.load()
    return engine


def _connect_db(cs: str):
    from src.db.connector import DbConnector
    from src.db.executor import SqlExecutor
    connector = DbConnector(cs)
    executor = SqlExecutor(cs)
    return connector, executor


def _load_vocab_from_yaml(yaml_text: str):
    import tempfile
    from src.business.vocabulary import BusinessVocabulary
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(yaml_text, encoding="utf-8")
    vocab = BusinessVocabulary.from_yaml(tmp)
    tmp.unlink(missing_ok=True)
    return vocab


# ──────────────────────────────────────────────
# Боковая панель
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Настройки")

    # ── Модель — загружается автоматически при старте ──
    st.subheader("🤖 Модель")
    if not st.session_state.model_loaded:
        with st.spinner("Загружаю модель…"):
            try:
                st.session_state.engine = _load_engine()
                st.session_state.model_loaded = True
            except Exception as e:
                st.error(f"Ошибка загрузки модели: {e}")

    if st.session_state.model_loaded:
        st.markdown('<span class="status-ok">✅ Модель готова</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-err">⚠️ Модель не загружена</span>', unsafe_allow_html=True)

    st.divider()

    # ── База данных ──
    st.subheader("🗄️ База данных")

    db_type = st.radio("Тип подключения", ["SQLite файл", "Строка подключения"],
                       horizontal=True)

    if db_type == "SQLite файл":
        uploaded = st.file_uploader("Загрузить .sqlite файл", type=["sqlite", "db"])
        use_demo = st.checkbox("Использовать демо-базу", value=True)

        if use_demo:
            demo_path = ROOT / "data" / "demo" / "sales.sqlite"
            cs = str(demo_path)
        elif uploaded:
            import tempfile
            tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
            tmp_db.write_bytes(uploaded.read())
            cs = str(tmp_db)
        else:
            cs = ""
    else:
        cs = st.text_input(
            "Строка подключения",
            placeholder="postgresql://user:pass@localhost/mydb",
            value=st.session_state.db_connection_string,
        )

    if cs and st.button("Подключиться к БД", use_container_width=True):
        try:
            connector, executor = _connect_db(cs)
            tables = connector.list_tables()
            st.session_state.db_connector = connector
            st.session_state.db_executor = executor
            st.session_state.db_connection_string = cs
            # Автоматически применяем словарь для демо-базы
            if "sales" in cs and st.session_state.vocabulary is None:
                try:
                    demo_vocab_path = ROOT / "configs" / "example_vocabulary.yaml"
                    if demo_vocab_path.exists():
                        st.session_state.vocabulary = _load_vocab_from_yaml(
                            demo_vocab_path.read_text(encoding="utf-8")
                        )
                except Exception:
                    pass
            st.success(f"Подключено! Таблиц: {len(tables)}")
        except Exception as e:
            st.error(f"Ошибка подключения: {e}")

    if st.session_state.db_connector:
        tables = st.session_state.db_connector.list_tables()
        st.markdown('<span class="status-ok">✅ БД подключена</span>', unsafe_allow_html=True)
        with st.expander("Таблицы"):
            for t in tables:
                st.code(t)

    st.divider()

    # ── Бизнес-словарь ──
    st.subheader("📖 Бизнес-словарь")

    vocab_yaml = st.text_area(
        "YAML-конфигурация",
        value=st.session_state.vocab_yaml,
        height=260,
        help="Определите термины вашей компании — модель будет их учитывать при генерации SQL",
    )
    st.session_state.vocab_yaml = vocab_yaml

    if st.button("Применить словарь", use_container_width=True):
        try:
            st.session_state.vocabulary = _load_vocab_from_yaml(vocab_yaml)
            st.success("Словарь применён!")
        except Exception as e:
            st.error(f"Ошибка в YAML: {e}")

    if st.session_state.vocabulary:
        v = st.session_state.vocabulary
        st.markdown(f'<span class="status-ok">✅ Словарь: {v.company or "загружен"}</span>',
                    unsafe_allow_html=True)
        terms_count = len(v.terms)
        if terms_count:
            st.caption(f"{terms_count} терминов определено")


# ──────────────────────────────────────────────
# Основная область
# ──────────────────────────────────────────────
st.title("🗄️ Ru2SQL — Бизнес-аналитика на русском языке")
st.caption("Задайте вопрос на русском → получите SQL и данные из вашей базы")

tab_query, tab_schema, tab_history = st.tabs(["💬 Запрос", "📐 Схема БД", "🕓 История"])

# ──────────── Вкладка: Запрос ────────────
with tab_query:
    ready = st.session_state.model_loaded and st.session_state.db_connector is not None

    if not ready:
        cols = st.columns(2)
        with cols[0]:
            if not st.session_state.model_loaded:
                st.warning("⚠️ Загрузите модель в левой панели")
        with cols[1]:
            if st.session_state.db_connector is None:
                st.warning("⚠️ Подключитесь к базе данных в левой панели")

    question = st.text_area(
        "Ваш вопрос",
        placeholder="Например: Какая выручка за январь этого года?",
        height=100,
        disabled=not ready,
    )

    col_btn, col_hint = st.columns([1, 4])
    with col_btn:
        run_btn = st.button("▶ Выполнить", type="primary",
                            disabled=not ready or not question.strip(),
                            use_container_width=True)
    with col_hint:
        if ready:
            st.caption("Модель сгенерирует SQL и выполнит его на вашей БД")

    # Быстрые примеры
    if st.session_state.db_connection_string and "sales" in st.session_state.db_connection_string:
        st.caption("💡 Попробуйте:")
        example_cols = st.columns(3)
        examples = [
            "Какая выручка за 2026 год?",
            "Топ-5 клиентов по сумме заказов",
            "Сколько заказов по каждому менеджеру?",
        ]
        for i, ex in enumerate(examples):
            with example_cols[i]:
                if st.button(ex, key=f"ex_{i}", use_container_width=True):
                    question = ex
                    run_btn = True

    if run_btn and question.strip():
        engine = st.session_state.engine
        connector = st.session_state.db_connector
        executor = st.session_state.db_executor
        vocab = st.session_state.vocabulary

        # Обогащаем вопрос бизнес-словарём
        enriched_question = vocab.enrich_prompt(question) if vocab else question

        # Получаем схему
        schema = connector.render_schema(include_samples=True)

        with st.spinner("Генерирую SQL…"):
            t0 = time.time()
            result = engine.generate(schema, enriched_question)
            gen_time = time.time() - t0

        st.subheader("Сгенерированный SQL")
        st.markdown(f'<div class="sql-box">{result.sql}</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        col1.metric("Время генерации", f"{gen_time:.1f} с")

        # Выполняем SQL
        if result.sql.strip():
            with st.spinner("Выполняю запрос…"):
                qr = executor.run(result.sql)

            if qr.success:
                col2.metric("Строк в результате", qr.row_count)
                st.subheader("Результат")
                if qr.rows:
                    import pandas as pd
                    df = pd.DataFrame(qr.rows, columns=qr.columns)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Запрос выполнен успешно, результат пустой")
            else:
                col2.error("Ошибка выполнения")
                st.error(f"SQL ошибка: {qr.error}")

        # Добавляем в историю
        st.session_state.history.append({
            "question": question,
            "sql": result.sql,
            "success": qr.success if result.sql.strip() else False,
            "rows": qr.row_count if result.sql.strip() and qr.success else 0,
            "time": gen_time,
        })

# ──────────── Вкладка: Схема БД ────────────
with tab_schema:
    if st.session_state.db_connector is None:
        st.info("Подключитесь к базе данных в левой панели")
    else:
        connector = st.session_state.db_connector
        st.subheader("Структура базы данных")

        show_samples = st.toggle("Показывать примеры строк", value=True)
        schema_text = connector.render_schema(include_samples=show_samples)

        for table in connector.get_schema(include_samples=show_samples):
            with st.expander(f"📋 {table.name}  ({len(table.columns)} колонок)"):
                st.code(table.to_ddl(), language="sql")
                if show_samples and table.sample_rows:
                    import pandas as pd
                    cols = [c.name for c in table.columns]
                    st.caption("Примеры строк:")
                    st.dataframe(
                        pd.DataFrame(table.sample_rows, columns=cols),
                        use_container_width=True,
                    )

# ──────────── Вкладка: История ────────────
with tab_history:
    history = st.session_state.history
    if not history:
        st.info("История запросов пуста. Задайте первый вопрос на вкладке «Запрос».")
    else:
        st.subheader(f"История запросов ({len(history)})")

        if st.button("Очистить историю"):
            st.session_state.history = []
            st.rerun()

        for i, item in enumerate(reversed(history)):
            status = "✅" if item["success"] else "❌"
            with st.expander(f"{status} {item['question']}", expanded=(i == 0)):
                st.markdown(f'<div class="sql-box">{item["sql"]}</div>', unsafe_allow_html=True)
                cols = st.columns(3)
                cols[0].metric("Время генерации", f"{item['time']:.1f} с")
                cols[1].metric("Строк", item["rows"])
                cols[2].metric("Статус", "OK" if item["success"] else "Ошибка")

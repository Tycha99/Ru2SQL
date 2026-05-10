"""Streamlit-интерфейс утилиты Ru2SQL."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ──────────────────────────────────────────────
# Конфигурация страницы
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Ru2SQL",
    page_icon="assets/favicon.png" if (ROOT / "assets" / "favicon.png").exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Общий фон и типографика ── */
    [data-testid="stAppViewContainer"] {
        background-color: #0f1117;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #21262d;
    }

    /* ── Шапка приложения ── */
    .app-header {
        padding: 28px 0 20px 0;
        border-bottom: 1px solid #21262d;
        margin-bottom: 28px;
    }
    .app-title {
        font-size: 22px;
        font-weight: 700;
        color: #e6edf3;
        letter-spacing: -0.3px;
        margin: 0 0 4px 0;
        line-height: 1.3;
    }
    .app-subtitle {
        font-size: 13px;
        color: #7d8590;
        margin: 0;
        font-weight: 400;
    }

    /* ── Боковая панель ── */
    .sidebar-section-label {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #7d8590;
        padding: 16px 0 8px 0;
        margin: 0;
    }
    .sidebar-divider {
        border: none;
        border-top: 1px solid #21262d;
        margin: 12px 0;
    }

    /* ── Статусы ── */
    .status-ok {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #3fb950;
        font-size: 13px;
        font-weight: 500;
    }
    .status-err {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #f85149;
        font-size: 13px;
        font-weight: 500;
    }
    .status-warn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #d29922;
        font-size: 13px;
        font-weight: 500;
    }

    /* ── SQL-блок ── */
    .sql-box {
        background: #161b22;
        color: #e6edf3;
        font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.6;
        padding: 20px 24px;
        border-radius: 6px;
        border: 1px solid #21262d;
        border-left: 3px solid #388bfd;
        white-space: pre-wrap;
        margin: 12px 0;
    }

    /* ── Результирующая панель метрик ── */
    .result-meta {
        display: flex;
        gap: 24px;
        align-items: center;
        padding: 12px 0;
        border-top: 1px solid #21262d;
        border-bottom: 1px solid #21262d;
        margin: 16px 0;
    }
    .result-meta-item {
        font-size: 12px;
        color: #7d8590;
    }
    .result-meta-value {
        font-size: 14px;
        font-weight: 600;
        color: #e6edf3;
    }

    /* ── История ── */
    .history-entry {
        border: 1px solid #21262d;
        border-radius: 6px;
        padding: 14px 16px;
        margin: 8px 0;
        background: #161b22;
    }
    .history-question {
        font-size: 14px;
        color: #e6edf3;
        font-weight: 500;
        margin-bottom: 6px;
    }
    .history-meta {
        font-size: 12px;
        color: #7d8590;
    }

    /* ── Примеры запросов ── */
    .examples-label {
        font-size: 12px;
        color: #7d8590;
        margin: 16px 0 8px 0;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* ── Вкладки ── */
    [data-testid="stTabs"] button {
        font-size: 13px;
        font-weight: 500;
    }

    /* ── Кнопка Stop ── */
    button[kind="stop"] {
        display: none !important;
    }

    /* ── Убрать лишние отступы в header ── */
    [data-testid="stHeader"] {
        background: transparent;
    }

    /* ── Таблица данных ── */
    [data-testid="stDataFrame"] {
        border: 1px solid #21262d;
        border-radius: 6px;
        overflow: hidden;
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
@st.cache_resource(show_spinner="Инициализация модели…")
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
    st.markdown('<p class="sidebar-section-label">Модель</p>', unsafe_allow_html=True)

    if not st.session_state.model_loaded:
        with st.spinner("Инициализация…"):
            try:
                st.session_state.engine = _load_engine()
                st.session_state.model_loaded = True
            except Exception as e:
                st.error(f"Ошибка загрузки модели: {e}")

    if st.session_state.model_loaded:
        st.markdown(
            '<span class="status-ok">✅ Qwen2.5-Coder-3B + QLoRA</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-err">Модель не загружена</span>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── База данных ──
    st.markdown('<p class="sidebar-section-label">База данных</p>', unsafe_allow_html=True)

    db_type = st.radio(
        "Тип подключения",
        ["SQLite", "PostgreSQL / MySQL"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if db_type == "SQLite":
        use_demo = st.checkbox("Демо-база (sales.sqlite)", value=True)
        if use_demo:
            demo_path = ROOT / "data" / "demo" / "sales.sqlite"
            cs = str(demo_path)
        else:
            uploaded = st.file_uploader(
                "Загрузить файл базы данных",
                type=["sqlite", "db"],
                label_visibility="collapsed",
            )
            if uploaded:
                import tempfile
                tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
                tmp_db.write_bytes(uploaded.read())
                cs = str(tmp_db)
            else:
                cs = ""
                st.caption("Выберите .sqlite или .db файл")
    else:
        cs = st.text_input(
            "Строка подключения",
            placeholder="postgresql://user:pass@host:5432/dbname",
            value=st.session_state.db_connection_string,
            label_visibility="collapsed",
        )
        st.caption("PostgreSQL: postgresql://  |  MySQL: mysql+pymysql://")

    if cs and st.button("Подключиться", use_container_width=True, type="primary"):
        try:
            connector, executor = _connect_db(cs)
            tables = connector.list_tables()
            st.session_state.db_connector = connector
            st.session_state.db_executor = executor
            st.session_state.db_connection_string = cs
            if "sales" in cs and st.session_state.vocabulary is None:
                try:
                    demo_vocab_path = ROOT / "configs" / "example_vocabulary.yaml"
                    if demo_vocab_path.exists():
                        st.session_state.vocabulary = _load_vocab_from_yaml(
                            demo_vocab_path.read_text(encoding="utf-8")
                        )
                except Exception:
                    pass
            st.success(f"Подключено. Таблиц: {len(tables)}")
        except Exception as e:
            st.error(f"Ошибка подключения: {e}")

    if st.session_state.db_connector:
        tables = st.session_state.db_connector.list_tables()
        st.markdown(
            '<span class="status-ok">✅ База данных подключена</span>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Таблицы ({len(tables)})"):
            for t in tables:
                st.code(t, language=None)

    st.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)

    # ── Бизнес-словарь ──
    st.markdown('<p class="sidebar-section-label">Бизнес-словарь</p>', unsafe_allow_html=True)

    vocab_yaml = st.text_area(
        "YAML-конфигурация терминов",
        value=st.session_state.vocab_yaml,
        height=240,
        help=(
            "Опишите термины и правила вашей компании в формате YAML. "
            "Модель будет учитывать их при генерации SQL-запросов."
        ),
        label_visibility="collapsed",
    )
    st.session_state.vocab_yaml = vocab_yaml

    if st.button("Применить словарь", use_container_width=True):
        try:
            st.session_state.vocabulary = _load_vocab_from_yaml(vocab_yaml)
            st.success("Словарь применён.")
        except Exception as e:
            st.error(f"Ошибка синтаксиса YAML: {e}")

    if st.session_state.vocabulary:
        v = st.session_state.vocabulary
        label = v.company if v.company else "Загружен"
        st.markdown(
            f'<span class="status-ok">✅ {label}</span>',
            unsafe_allow_html=True,
        )
        if v.terms:
            st.caption(f"Терминов: {len(v.terms)}")


# ──────────────────────────────────────────────
# Основная область — заголовок
# ──────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <p class="app-title">Ru2SQL — генеративная модель преобразования запросов<br>к базе данных на русском языке в запросы на языке SQL</p>
    <p class="app-subtitle">Qwen2.5-Coder-3B-Instruct &nbsp;·&nbsp; QLoRA fine-tuning на PAUQ &nbsp;·&nbsp; SQLite / PostgreSQL / MySQL</p>
</div>
""", unsafe_allow_html=True)

tab_query, tab_schema, tab_history = st.tabs(["Запрос", "Схема базы данных", "История"])

# ──────────── Вкладка: Запрос ────────────
with tab_query:
    ready = st.session_state.model_loaded and st.session_state.db_connector is not None

    if not ready:
        missing = []
        if not st.session_state.model_loaded:
            missing.append("модель инициализируется")
        if st.session_state.db_connector is None:
            missing.append("база данных не подключена")
        st.warning("Система не готова: " + ", ".join(missing) + ". Используйте панель слева.")

    question = st.text_area(
        "Вопрос на естественном языке",
        placeholder="Например: Какая выручка за январь этого года?",
        height=90,
        disabled=not ready,
        label_visibility="visible",
    )

    col_btn, col_spacer = st.columns([1, 5])
    with col_btn:
        run_btn = st.button(
            "Выполнить",
            type="primary",
            disabled=not ready or not question.strip(),
            use_container_width=True,
        )

    # Примеры для демо-базы
    if st.session_state.db_connection_string and "sales" in st.session_state.db_connection_string:
        st.markdown('<p class="examples-label">Примеры запросов</p>', unsafe_allow_html=True)
        example_cols = st.columns(3)
        examples = [
            "Какая выручка за 2026 год?",
            "Топ-5 клиентов по сумме заказов",
            "Сколько заказов у каждого менеджера?",
        ]
        for i, ex in enumerate(examples):
            with example_cols[i]:
                if st.button(ex, key=f"ex_{i}", use_container_width=True):
                    question = ex
                    run_btn = True

    if run_btn and question.strip():
        engine    = st.session_state.engine
        connector = st.session_state.db_connector
        executor  = st.session_state.db_executor
        vocab     = st.session_state.vocabulary

        enriched_question = vocab.enrich_prompt(question) if vocab else question
        schema = connector.render_schema(include_samples=True)

        with st.spinner("Генерация SQL-запроса…"):
            t0 = time.time()
            result = engine.generate(schema, enriched_question)
            gen_time = time.time() - t0

        st.markdown("**Сгенерированный SQL**")
        st.markdown(f'<div class="sql-box">{result.sql}</div>', unsafe_allow_html=True)

        qr = None
        if result.sql.strip():
            with st.spinner("Выполнение запроса…"):
                qr = executor.run(result.sql)

        # Метрики
        c1, c2, c3 = st.columns(3)
        c1.metric("Время генерации", f"{gen_time:.1f} с")
        if qr:
            c2.metric("Строк получено", qr.row_count if qr.success else "—")
            c3.metric("Статус", "Успешно" if qr.success else "Ошибка")

        if qr and qr.success:
            if qr.rows:
                import pandas as pd
                st.markdown("**Результат**")
                df = pd.DataFrame(qr.rows, columns=qr.columns)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Запрос выполнен. Результат пустой.")
        elif qr and not qr.success:
            st.error(f"Ошибка выполнения SQL: {qr.error}")

        st.session_state.history.append({
            "question": question,
            "sql": result.sql,
            "success": qr.success if qr else False,
            "rows": qr.row_count if qr and qr.success else 0,
            "time": gen_time,
        })

# ──────────── Вкладка: Схема БД ────────────
with tab_schema:
    if st.session_state.db_connector is None:
        st.info("Подключитесь к базе данных через панель слева.")
    else:
        connector = st.session_state.db_connector
        show_samples = st.toggle("Показывать примеры строк", value=True)

        for table in connector.get_schema(include_samples=show_samples):
            with st.expander(f"{table.name}  —  {len(table.columns)} колонок"):
                st.code(table.to_ddl(), language="sql")
                if show_samples and table.sample_rows:
                    import pandas as pd
                    cols = [c.name for c in table.columns]
                    st.caption("Примеры данных:")
                    st.dataframe(
                        pd.DataFrame(table.sample_rows, columns=cols),
                        use_container_width=True,
                    )

# ──────────── Вкладка: История ────────────
with tab_history:
    history = st.session_state.history
    if not history:
        st.info("История пуста. Выполните первый запрос на вкладке «Запрос».")
    else:
        col_h, col_btn_h = st.columns([5, 1])
        with col_h:
            st.markdown(f"**Запросов в сессии: {len(history)}**")
        with col_btn_h:
            if st.button("Очистить", use_container_width=True):
                st.session_state.history = []
                st.rerun()

        for i, item in enumerate(reversed(history)):
            status_icon = "✅" if item["success"] else "❌"
            with st.expander(
                f"{status_icon}  {item['question']}",
                expanded=(i == 0),
            ):
                st.markdown(f'<div class="sql-box">{item["sql"]}</div>', unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                c1.metric("Время генерации", f"{item['time']:.1f} с")
                c2.metric("Строк", item["rows"])
                c3.metric("Статус", "Успешно" if item["success"] else "Ошибка")

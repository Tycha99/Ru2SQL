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
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    /* ── Глобальный шрифт и фон ── */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0d1117;
        font-size: 16px;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    [data-testid="stHeader"] { background: transparent; }

    /* ── Шапка ── */
    .app-header {
        padding: 32px 0 24px 0;
        border-bottom: 1px solid #30363d;
        margin-bottom: 32px;
    }
    .app-title {
        font-size: 26px;
        font-weight: 700;
        color: #e6edf3;
        letter-spacing: -0.4px;
        line-height: 1.35;
        margin: 0 0 8px 0;
    }
    .app-subtitle {
        font-size: 14px;
        color: #7d8590;
        margin: 0;
        font-weight: 400;
        letter-spacing: 0.1px;
    }

    /* ── Сайдбар: секции ── */
    .sb-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        color: #7d8590;
        padding: 20px 0 8px 0;
        margin: 0;
    }
    .sb-divider {
        border: none;
        border-top: 1px solid #30363d;
        margin: 4px 0 0 0;
    }

    /* ── Статусы ── */
    .status-ok  { color: #3fb950; font-size: 13px; font-weight: 600; }
    .status-err { color: #f85149; font-size: 13px; font-weight: 600; }

    /* ── DB-переключатель: стилизуем radio как сегментированные кнопки ── */
    div[data-testid="stRadio"] > label { display: none; }
    div[data-testid="stRadio"] > div {
        display: flex;
        gap: 0;
        border: 1px solid #30363d;
        border-radius: 8px;
        overflow: hidden;
        background: #0d1117;
    }
    div[data-testid="stRadio"] > div > label {
        flex: 1;
        display: flex !important;
        align-items: center;
        justify-content: center;
        padding: 8px 4px;
        font-size: 12px;
        font-weight: 500;
        color: #7d8590;
        cursor: pointer;
        border-right: 1px solid #30363d;
        transition: background 0.15s, color 0.15s;
        text-align: center;
    }
    div[data-testid="stRadio"] > div > label:last-child { border-right: none; }
    div[data-testid="stRadio"] > div > label:has(input:checked) {
        background: #21262d;
        color: #e6edf3;
    }
    div[data-testid="stRadio"] > div > label:hover:not(:has(input:checked)) {
        background: #161b22;
        color: #c9d1d9;
    }
    div[data-testid="stRadio"] > div > label > div:first-child { display: none; }

    /* ── Кнопка словаря ── */
    .vocab-status {
        font-size: 12px;
        color: #7d8590;
        margin-top: 6px;
    }

    /* ── SQL-блок ── */
    .sql-box {
        background: #161b22;
        color: #e6edf3;
        font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Courier New', monospace;
        font-size: 14px;
        line-height: 1.7;
        padding: 20px 24px;
        border-radius: 8px;
        border: 1px solid #30363d;
        border-left: 3px solid #388bfd;
        white-space: pre-wrap;
        margin: 14px 0;
    }

    /* ── Вкладки ── */
    [data-testid="stTabs"] button { font-size: 15px; font-weight: 500; }

    /* ── Примеры запросов ── */
    .examples-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #7d8590;
        margin: 24px 0 10px 0;
    }

    /* ── Поле ввода вопроса ── */
    [data-testid="stTextArea"] textarea {
        font-size: 16px !important;
        line-height: 1.6 !important;
    }

    /* ── Кнопка «Выполнить» ── */
    [data-testid="stButton"] > button[kind="primary"] {
        font-size: 15px;
        padding: 10px 28px;
        border-radius: 8px;
        font-weight: 600;
    }

    /* ── Метрики ── */
    [data-testid="stMetric"] label {
        font-size: 12px !important;
        color: #7d8590 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 22px !important;
        color: #e6edf3 !important;
    }

    /* ── Предупреждение о неготовности ── */
    [data-testid="stAlertContainer"] {
        border-radius: 8px;
        font-size: 14px;
    }

    /* ── Expander схемы ── */
    [data-testid="stExpander"] summary {
        font-size: 15px;
        font-weight: 500;
    }

    /* ── Скрыть кнопку Stop ── */
    button[kind="stop"] { display: none !important; }

    /* ── Модальный диалог словаря ── */
    [data-testid="stDialog"] textarea {
        font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        font-size: 13px !important;
        line-height: 1.6 !important;
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
        "history":              [],
        "model_loaded":         False,
        "engine":               None,
        "db_connector":         None,
        "db_executor":          None,
        "vocabulary":           None,
        "db_connection_string": "",
        "vocab_yaml":           _default_vocab_yaml(),
        "db_mode":              "Демо-база",
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
    return DbConnector(cs), SqlExecutor(cs)


def _load_vocab_from_yaml(yaml_text: str):
    import tempfile
    from src.business.vocabulary import BusinessVocabulary
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(yaml_text, encoding="utf-8")
    vocab = BusinessVocabulary.from_yaml(tmp)
    tmp.unlink(missing_ok=True)
    return vocab


def _auto_connect_demo():
    """Подключить демо-базу и словарь к ней."""
    demo_path = ROOT / "data" / "demo" / "sales.sqlite"
    cs = str(demo_path)
    try:
        connector, executor = _connect_db(cs)
        st.session_state.db_connector         = connector
        st.session_state.db_executor          = executor
        st.session_state.db_connection_string = cs
        if st.session_state.vocabulary is None:
            vocab_path = ROOT / "configs" / "example_vocabulary.yaml"
            if vocab_path.exists():
                st.session_state.vocabulary = _load_vocab_from_yaml(
                    vocab_path.read_text(encoding="utf-8")
                )
    except Exception:
        pass


# ──────────────────────────────────────────────
# Модальный диалог бизнес-словаря
# ──────────────────────────────────────────────
@st.dialog("Бизнес-словарь", width="large")
def vocab_dialog():
    st.caption(
        "Опишите термины, метрики и правила вашей компании в формате YAML. "
        "Модель будет учитывать их при генерации SQL."
    )
    yaml_text = st.text_area(
        "YAML-конфигурация",
        value=st.session_state.vocab_yaml,
        height=480,
        label_visibility="collapsed",
    )
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Применить", type="primary", use_container_width=True):
            try:
                vocab = _load_vocab_from_yaml(yaml_text)
                st.session_state.vocabulary = vocab
                st.session_state.vocab_yaml = yaml_text
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка синтаксиса YAML: {e}")
    with col2:
        if st.button("Отмена", use_container_width=True):
            st.rerun()


# ──────────────────────────────────────────────
# Боковая панель
# ──────────────────────────────────────────────
with st.sidebar:

    # ── Модель ──
    st.markdown('<p class="sb-label">Модель</p>', unsafe_allow_html=True)
    if not st.session_state.model_loaded:
        with st.spinner("Инициализация…"):
            try:
                st.session_state.engine     = _load_engine()
                st.session_state.model_loaded = True
            except Exception as e:
                st.error(f"Ошибка: {e}")

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

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)

    # ── База данных ──
    st.markdown('<p class="sb-label">База данных</p>', unsafe_allow_html=True)

    db_mode = st.radio(
        "db_mode",
        ["Демо-база", "Загрузить файл", "Строка подключения"],
        horizontal=True,
        index=["Демо-база", "Загрузить файл", "Строка подключения"].index(
            st.session_state.db_mode
        ),
    )
    st.session_state.db_mode = db_mode

    cs = ""

    if db_mode == "Демо-база":
        st.caption("Встроенная база: интернет-магазин электроники, 120 заказов.")
        demo_path = ROOT / "data" / "demo" / "sales.sqlite"
        cs = str(demo_path)

    elif db_mode == "Загрузить файл":
        uploaded = st.file_uploader(
            "SQLite-файл базы данных",
            type=["sqlite", "db"],
            label_visibility="collapsed",
        )
        if uploaded:
            import tempfile
            tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
            tmp_db.write_bytes(uploaded.read())
            cs = str(tmp_db)
        else:
            st.caption("Перетащите .sqlite или .db файл сюда")

    else:  # Строка подключения
        cs = st.text_input(
            "Строка подключения",
            placeholder="postgresql://user:pass@host:5432/db",
            value=st.session_state.db_connection_string,
            label_visibility="collapsed",
        )
        st.caption("PostgreSQL · MySQL (mysql+pymysql://) · SQLite (sqlite:///path)")

    if cs and st.button("Подключиться", use_container_width=True, type="primary"):
        try:
            connector, executor = _connect_db(cs)
            tables = connector.list_tables()
            st.session_state.db_connector         = connector
            st.session_state.db_executor          = executor
            st.session_state.db_connection_string = cs
            if "sales" in cs and st.session_state.vocabulary is None:
                vocab_path = ROOT / "configs" / "example_vocabulary.yaml"
                if vocab_path.exists():
                    st.session_state.vocabulary = _load_vocab_from_yaml(
                        vocab_path.read_text(encoding="utf-8")
                    )
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

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)

    # ── Бизнес-словарь ──
    st.markdown('<p class="sb-label">Бизнес-словарь</p>', unsafe_allow_html=True)

    if st.session_state.vocabulary:
        v = st.session_state.vocabulary
        label = v.company if v.company else "Загружен"
        st.markdown(
            f'<span class="status-ok">✅ {label}</span>',
            unsafe_allow_html=True,
        )
        if v.terms:
            st.markdown(
                f'<span class="vocab-status">Терминов: {len(v.terms)}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<span class="vocab-status">Словарь не применён</span>',
            unsafe_allow_html=True,
        )

    if st.button("Редактировать словарь", use_container_width=True):
        vocab_dialog()


# ──────────────────────────────────────────────
# Автоподключение демо-базы при первом запуске
# ──────────────────────────────────────────────
if (
    st.session_state.db_mode == "Демо-база"
    and st.session_state.db_connector is None
):
    _auto_connect_demo()


# ──────────────────────────────────────────────
# Основная область — шапка
# ──────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <p class="app-title">Ru2SQL — генеративная модель преобразования запросов<br>
    к базе данных на русском языке в запросы на языке SQL</p>
    <p class="app-subtitle">
        Qwen2.5-Coder-3B-Instruct &nbsp;·&nbsp; QLoRA fine-tuning на датасете PAUQ
        &nbsp;·&nbsp; SQLite / PostgreSQL / MySQL
    </p>
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
        height=100,
        disabled=not ready,
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
    if (
        st.session_state.db_connection_string
        and "sales" in st.session_state.db_connection_string
    ):
        st.markdown('<p class="examples-label">Примеры запросов</p>', unsafe_allow_html=True)
        ex_cols = st.columns(3)
        examples = [
            "Какая выручка за 2026 год?",
            "Топ-5 клиентов по сумме заказов",
            "Сколько заказов у каждого менеджера?",
        ]
        for i, ex in enumerate(examples):
            with ex_cols[i]:
                if st.button(ex, key=f"ex_{i}", use_container_width=True):
                    question = ex
                    run_btn  = True

    if run_btn and question.strip():
        engine    = st.session_state.engine
        connector = st.session_state.db_connector
        executor  = st.session_state.db_executor
        vocab     = st.session_state.vocabulary

        enriched = vocab.enrich_prompt(question) if vocab else question
        schema   = connector.render_schema(include_samples=True)

        with st.spinner("Генерация SQL-запроса…"):
            t0     = time.time()
            result = engine.generate(schema, enriched)
            gen_time = time.time() - t0

        st.markdown("**Сгенерированный SQL**")
        st.markdown(f'<div class="sql-box">{result.sql}</div>', unsafe_allow_html=True)

        qr = None
        if result.sql.strip():
            with st.spinner("Выполнение запроса…"):
                qr = executor.run(result.sql)

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
                st.info("Запрос выполнен успешно. Результат пустой.")
        elif qr and not qr.success:
            st.error(f"Ошибка выполнения SQL: {qr.error}")

        st.session_state.history.append({
            "question": question,
            "sql":      result.sql,
            "success":  qr.success if qr else False,
            "rows":     qr.row_count if qr and qr.success else 0,
            "time":     gen_time,
        })

# ──────────── Вкладка: Схема БД ────────────
with tab_schema:
    if st.session_state.db_connector is None:
        st.info("Подключитесь к базе данных через панель слева.")
    else:
        connector    = st.session_state.db_connector
        show_samples = st.toggle("Показывать примеры данных", value=True)

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
        col_h, col_clr = st.columns([5, 1])
        with col_h:
            st.markdown(f"**Запросов в сессии: {len(history)}**")
        with col_clr:
            if st.button("Очистить", use_container_width=True):
                st.session_state.history = []
                st.rerun()

        for i, item in enumerate(reversed(history)):
            icon = "✅" if item["success"] else "❌"
            with st.expander(f"{icon}  {item['question']}", expanded=(i == 0)):
                st.markdown(
                    f'<div class="sql-box">{item["sql"]}</div>',
                    unsafe_allow_html=True,
                )
                c1, c2, c3 = st.columns(3)
                c1.metric("Время генерации", f"{item['time']:.1f} с")
                c2.metric("Строк",           item["rows"])
                c3.metric("Статус",          "Успешно" if item["success"] else "Ошибка")

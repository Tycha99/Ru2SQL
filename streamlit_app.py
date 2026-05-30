"""Streamlit-интерфейс утилиты Ru2SQL.

Архитектурно — клиент REST API на FastAPI. Соответствует разделу 3.5
пояснительной записки: все обращения к модели и базе данных идут через
HTTP к ``src.api.main:app``. Запуск двух процессов:

    uvicorn src.api.main:app --reload      # на 127.0.0.1:8000
    streamlit run streamlit_app.py          # на 127.0.0.1:8501
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path

# ──────────────────────────────────────────────
# Глушим шумные warning'и
# ──────────────────────────────────────────────
# Streamlit-watcher ходит по всему пакету transformers (image-processors)
# и спамит ModuleNotFoundError про torchvision. На работу это не влияет —
# Qwen2.5-Coder text-only, torchvision не нужен.
warnings.filterwarnings("ignore", message=".*torchvision.*")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("streamlit.watcher.local_sources_watcher").setLevel(logging.ERROR)

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Бизнес-словарь парсим локально — он не требует обращения к серверу
from src.business.vocabulary import BusinessVocabulary

API_URL = os.environ.get("RU2SQL_API_URL", "http://127.0.0.1:8000")
QUERY_TIMEOUT = 1800.0  # 30 минут — фактически безлимит
SHORT_TIMEOUT = 10.0   # для /health, /schema

# ──────────────────────────────────────────────
# Конфигурация страницы
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Ru2SQL",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# CSS — оформление в стиле тёмной темы GitHub
# ──────────────────────────────────────────────
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0d1117;
        font-size: 16px;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    [data-testid="stHeader"] { background: transparent; }

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
    .status-ok  { color: #3fb950; font-size: 13px; font-weight: 600; }
    .status-err { color: #f85149; font-size: 13px; font-weight: 600; }
    .status-warn { color: #d29922; font-size: 13px; font-weight: 600; }
    .sql-box {
        background: #161b22;
        color: #e6edf3;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 14px;
        line-height: 1.7;
        padding: 20px 24px;
        border-radius: 8px;
        border: 1px solid #30363d;
        border-left: 3px solid #388bfd;
        white-space: pre-wrap;
        margin: 14px 0;
    }
    [data-testid="stTabs"] button { font-size: 15px; font-weight: 500; }
    .examples-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: #7d8590;
        margin: 24px 0 10px 0;
    }
    [data-testid="stTextArea"] textarea {
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
    [data-testid="stButton"] > button[kind="primary"] {
        font-size: 15px;
        padding: 10px 28px;
        border-radius: 8px;
        font-weight: 600;
    }
    [data-testid="stMetric"] label { font-size: 12px !important; color: #7d8590 !important; }
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #e6edf3 !important; }
    [data-testid="stAlertContainer"] { border-radius: 8px; font-size: 14px; }
    [data-testid="stExpander"] summary { font-size: 15px; font-weight: 500; }
    button[kind="stop"] { display: none !important; }
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
    return "company: Моя компания\n\nterms: {}\nfilters: {}\nnotes: []\n"


def _init_state():
    defaults = {
        "history":               [],
        "api_health":            None,      # dict | None
        "api_error":             None,      # str | None
        "connection_string":     "",
        "schema_tables":         None,      # list[TablePayload-like dict] | None
        "schema_error":          None,
        "vocabulary":            None,      # BusinessVocabulary | None
        "vocab_yaml":            _default_vocab_yaml(),
        "db_mode":               None,
        "warmup_done":           False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


# ──────────────────────────────────────────────
# Обёртки над API
# ──────────────────────────────────────────────
def _api_get_health() -> dict | None:
    """GET /health. None если API недоступен."""
    try:
        r = httpx.get(f"{API_URL}/health", timeout=SHORT_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.session_state.api_error = str(e)
        return None


def _api_get_schema(cs: str) -> tuple[list[dict] | None, str | None]:
    """POST /schema. Возвращает (tables, error)."""
    try:
        r = httpx.post(
            f"{API_URL}/schema",
            json={"connection_string": cs, "include_samples": True},
            timeout=SHORT_TIMEOUT,
        )
        if r.status_code != 200:
            try:
                return None, r.json().get("detail", r.text)
            except Exception:
                return None, r.text
        return r.json().get("tables", []), None
    except Exception as e:
        return None, str(e)


def _api_query(question: str, cs: str, vocab: BusinessVocabulary | None) -> dict:
    """POST /query — генерация SQL + опциональное исполнение."""
    payload = {
        "question": question,
        "connection_string": cs,
        "execute": True,
    }
    if vocab is not None and bool(vocab):
        payload["vocabulary"] = {
            "company": vocab.company,
            "terms": vocab.terms,
            "filters": vocab.filters,
            "notes": vocab.notes,
        }
    r = httpx.post(f"{API_URL}/query", json=payload, timeout=QUERY_TIMEOUT)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"API вернул {r.status_code}: {detail}")
    return r.json()



def _api_warmup() -> tuple[bool, str | None]:
    """POST /warmup — короткий прогон для прогрева модели на CPU."""
    try:
        r = httpx.post(f"{API_URL}/warmup", timeout=QUERY_TIMEOUT)
        if r.status_code == 200:
            return True, None
        return False, r.text
    except Exception as e:
        return False, str(e)


def _load_vocab_from_yaml(yaml_text: str) -> BusinessVocabulary:
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".yaml"))
    tmp.write_text(yaml_text, encoding="utf-8")
    try:
        return BusinessVocabulary.from_yaml(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ──────────────────────────────────────────────
# Диалог редактирования бизнес-словаря
# ──────────────────────────────────────────────
@st.dialog("Бизнес-словарь", width="large")
def vocab_dialog():
    st.caption(
        "Опишите термины и метрики компании в формате YAML. "
        "Модель будет учитывать их при генерации SQL."
    )
    yaml_text = st.text_area(
        "YAML-конфигурация",
        value=st.session_state.vocab_yaml,
        height=480,
        label_visibility="collapsed",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Применить", type="primary", width='stretch'):
            try:
                st.session_state.vocabulary = _load_vocab_from_yaml(yaml_text)
                st.session_state.vocab_yaml = yaml_text
                st.rerun()
            except Exception as e:
                st.error(f"Ошибка синтаксиса YAML: {e}")
    with c2:
        if st.button("Отмена", width='stretch'):
            st.rerun()


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:

    # ── API ──
    st.markdown('<p class="sb-label">API</p>', unsafe_allow_html=True)
    health = _api_get_health()
    st.session_state.api_health = health
    if health is None:
        st.markdown('<span class="status-err">API недоступен</span>', unsafe_allow_html=True)
        st.caption(f"Адрес: {API_URL}")
        st.caption("Запусти в отдельной консоли: `uvicorn src.api.main:app --reload`")
        if st.session_state.api_error:
            st.caption(f"Причина: {st.session_state.api_error[:160]}")
    else:
        if health.get("model_loaded"):
            st.markdown(
                f'<span class="status-ok">✅ {health.get("base_model", "модель")}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="status-warn">⏳ Модель ещё загружается</span>',
                unsafe_allow_html=True,
            )
            st.caption("Подождите несколько минут — модель ещё инициализируется.")

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)

    # ── База данных ──
    st.markdown('<p class="sb-label">База данных</p>', unsafe_allow_html=True)

    modes = ["Демо-база", "Загрузить файл", "Строка подключения"]
    prev = st.session_state.db_mode
    db_mode = st.radio(
        "Источник данных", modes,
        index=modes.index(prev) if prev in modes else None,
        label_visibility="collapsed",
    )
    if db_mode != prev:
        st.session_state.schema_tables = None
        st.session_state.connection_string = ""
    st.session_state.db_mode = db_mode

    cs = ""
    if db_mode == "Демо-база":
        st.caption("Встроенная база: интернет-магазин электроники, 120 заказов.")
        cs = str(ROOT / "data" / "demo" / "sales.sqlite")
    elif db_mode == "Загрузить файл":
        uploaded = st.file_uploader(
            "SQLite-файл базы данных", type=["sqlite", "db"],
            label_visibility="collapsed",
        )
        if uploaded:
            import tempfile
            tmp_db = Path(tempfile.mktemp(suffix=".sqlite"))
            tmp_db.write_bytes(uploaded.read())
            cs = str(tmp_db)
        else:
            st.caption("Перетащите .sqlite или .db файл сюда")
    else:
        cs = st.text_input(
            "Строка подключения",
            placeholder="postgresql://user:pass@host:5432/db",
            value=st.session_state.connection_string,
            label_visibility="collapsed",
        )
        st.caption("PostgreSQL · MySQL · SQLite (sqlite:///path)")

    if cs and st.button("Подключиться", width='stretch', type="primary"):
        with st.spinner("Чтение схемы…"):
            tables, err = _api_get_schema(cs)
        if err:
            st.error(f"Ошибка подключения: {err}")
            st.session_state.schema_tables = None
        else:
            st.session_state.schema_tables = tables
            st.session_state.connection_string = cs
            st.session_state.schema_error = None
            if not st.session_state.get("warmup_done", False):
                with st.spinner("Прогрев модели (запускается один раз за сессию)…"):
                    ok, _err = _api_warmup()
                if ok:
                    st.session_state.warmup_done = True
            # Автозагрузка словаря для демо-базы
            if "sales" in cs and st.session_state.vocabulary is None:
                vp = ROOT / "configs" / "example_vocabulary.yaml"
                if vp.exists():
                    try:
                        st.session_state.vocabulary = _load_vocab_from_yaml(
                            vp.read_text(encoding="utf-8")
                        )
                    except Exception:
                        pass
            st.success(f"Подключено. Таблиц: {len(tables)}")

    if st.session_state.schema_tables is not None:
        n = len(st.session_state.schema_tables)
        st.markdown(
            '<span class="status-ok">✅ База данных подключена</span>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Таблицы ({n})"):
            for t in st.session_state.schema_tables:
                st.code(t.get("name", ""), language=None)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)

    # ── Бизнес-словарь ──
    st.markdown('<p class="sb-label">Бизнес-словарь</p>', unsafe_allow_html=True)
    if st.session_state.vocabulary:
        v = st.session_state.vocabulary
        label = v.company if v.company else "Загружен"
        st.markdown(f'<span class="status-ok">✅ {label}</span>', unsafe_allow_html=True)
        if v.terms:
            st.caption(f"Терминов: {len(v.terms)}")
    else:
        st.caption("Словарь не применён")
    if st.button("Редактировать словарь", width='stretch'):
        vocab_dialog()


# ──────────────────────────────────────────────
# Шапка
# ──────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <p class="app-title">Ru2SQL — генеративная модель преобразования запросов<br>
    к базе данных на русском языке в запросы на языке SQL</p>
    <p class="app-subtitle">
        Qwen2.5-Coder-3B-Instruct &nbsp;·&nbsp; QLoRA на PAUQ
        &nbsp;·&nbsp; SQLite / PostgreSQL / MySQL
    </p>
</div>
""", unsafe_allow_html=True)

tab_query, tab_schema, tab_history = st.tabs(["Запрос", "Схема базы данных", "История"])


# ──────────── Tab: Запрос ────────────
with tab_query:
    api_ready = (
        st.session_state.api_health is not None
        and st.session_state.api_health.get("model_loaded", False)
    )
    db_ready = st.session_state.schema_tables is not None
    ready = api_ready and db_ready

    if not ready:
        missing = []
        if not api_ready:
            missing.append("API/модель не готовы")
        if not db_ready:
            missing.append("база данных не подключена")
        st.warning("Система не готова: " + ", ".join(missing) + ". Используйте панель слева.")

    question = st.text_area(
        "Вопрос на естественном языке",
        placeholder="Например: Какая выручка за январь этого года?",
        height=100,
        disabled=not ready,
    )

    col_btn, _ = st.columns([1, 5])
    with col_btn:
        run_btn = st.button(
            "Выполнить",
            type="primary",
            disabled=not ready or not question.strip(),
            width='stretch',
        )

    # Примеры для демо-базы
    if (
        st.session_state.connection_string
        and "sales" in st.session_state.connection_string
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
                if st.button(ex, key=f"ex_{i}", width='stretch'):
                    question = ex
                    run_btn = True

    if run_btn and question.strip():
        cs = st.session_state.connection_string
        vocab = st.session_state.vocabulary

        with st.spinner("Запрос к API. Это может занять несколько минут"):
            try:
                resp = _api_query(question, cs, vocab)
            except Exception as e:
                st.error(f"Ошибка: {e}")
                st.stop()

        st.markdown("**Сгенерированный SQL**")
        st.markdown(f'<div class="sql-box">{resp.get("sql", "")}</div>', unsafe_allow_html=True)

        gen_time = resp.get("gen_time_seconds", 0.0)
        execution = resp.get("execution")
        err = resp.get("error")

        c1, c2, c3 = st.columns(3)
        c1.metric("Время генерации", f"{gen_time:.1f} с")
        if execution:
            c2.metric("Строк получено", execution.get("row_count", 0))
            c3.metric("Статус", "Успешно")
        elif err:
            c2.metric("Строк получено", "—")
            c3.metric("Статус", "Ошибка")

        if execution and execution.get("rows"):
            import pandas as pd
            st.markdown("**Результат**")
            df = pd.DataFrame(execution["rows"], columns=execution["columns"])
            st.dataframe(df, width='stretch')
        elif execution and not execution.get("rows"):
            st.info("Запрос выполнен успешно. Результат пустой.")
        elif err:
            st.error(f"Ошибка выполнения SQL: {err}")

        st.session_state.history.append({
            "question": question,
            "sql":      resp.get("sql", ""),
            "success":  bool(execution),
            "rows":     execution.get("row_count", 0) if execution else 0,
            "time":     gen_time,
        })


# ──────────── Tab: Схема БД ────────────
with tab_schema:
    if st.session_state.schema_tables is None:
        st.info("Подключитесь к базе данных через панель слева.")
    else:
        show_samples = st.toggle("Показывать примеры данных", value=True)
        for t in st.session_state.schema_tables:
            with st.expander(f"{t['name']}  —  {len(t['columns'])} колонок"):
                st.code(t.get("ddl", ""), language="sql")
                if show_samples and t.get("sample_rows"):
                    import pandas as pd
                    cols = [c["name"] for c in t["columns"]]
                    st.caption("Примеры данных:")
                    st.dataframe(
                        pd.DataFrame(t["sample_rows"], columns=cols),
                        width='stretch',
                    )


# ──────────── Tab: История ────────────
with tab_history:
    history = st.session_state.history
    if not history:
        st.info("История пуста. Выполните первый запрос на вкладке «Запрос».")
    else:
        col_h, col_clr = st.columns([5, 1])
        with col_h:
            st.markdown(f"**Запросов в сессии: {len(history)}**")
        with col_clr:
            if st.button("Очистить", width='stretch'):
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

# Образ для HuggingFace Spaces (Docker SDK).
# Запускает оба процесса Ru2SQL в одном контейнере:
#   - FastAPI на 127.0.0.1:8000 (внутренний)
#   - Streamlit на 0.0.0.0:7860 (внешний, HF Spaces читает с этого порта)
# Оркестрирует их scripts/run_app.py.

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим torch с поддержкой CUDA 12.1 — это нужно для T4 Small на HF.
# На CPU-окружении этот же torch автоматически работает через CPU-бэкенд.
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

# Дефолты для HF Spaces. Переписываются Variables/Secrets в настройках Space.
ENV LORA_ADAPTER_PATH=Tyycha/qwen-coder-pauq-lora \
    BASE_MODEL_NAME=Qwen/Qwen2.5-Coder-3B-Instruct \
    DEVICE=cuda \
    API_HOST=127.0.0.1 \
    API_PORT=8000 \
    STREAMLIT_HOST=0.0.0.0 \
    STREAMLIT_PORT=7860 \
    RU2SQL_API_URL=http://127.0.0.1:8000

EXPOSE 7860

# start-period=600s — у первого запуска есть до 10 минут на скачивание модели
# с HuggingFace. Дальше healthcheck опрашивает Streamlit каждые 30 секунд.
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD curl --fail http://localhost:7860/_stcore/health || exit 1

ENTRYPOINT ["python", "scripts/run_app.py"]

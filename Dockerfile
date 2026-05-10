FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install -r requirements.txt

COPY . .

ENV LORA_ADAPTER_PATH=Tyycha/qwen-coder-pauq-lora
ENV BASE_MODEL_NAME=Qwen/Qwen2.5-Coder-3B-Instruct
ENV DEVICE=cpu

EXPOSE 7860

HEALTHCHECK CMD curl --fail http://localhost:7860/_stcore/health

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=7860", "--server.address=0.0.0.0"]
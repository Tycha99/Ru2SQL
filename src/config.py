"""Конфигурация проекта. Читаем из .env через pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Все настройки приложения. Значения берутся из .env, переменных окружения, либо дефолтов."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Модель
    base_model_name: str = "Qwen/Qwen2.5-Coder-3B-Instruct"
    lora_adapter_path: str = str(ROOT_DIR / "checkpoints" / "qwen-coder-pauq-lora")
    device: str = "cpu"  # "cpu" | "cuda" | "mps"

    # Данные
    pauq_data_dir: Path = ROOT_DIR / "data" / "pauq"
    databases_dir: Path = ROOT_DIR / "data" / "databases"

    # API ключи (используется только тот, который заполнен)
    gigachat_api_key: str = ""
    openai_api_key: str = ""
    yandexgpt_api_key: str = ""
    yandexgpt_folder_id: str = ""
    hf_token: str = ""

    # FastAPI
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Inference defaults
    max_new_tokens: int = 256
    temperature: float = 0.0  # для SQL детерминизм лучше
    do_sample: bool = False


# Singleton-инстанс. Импортируется по всему проекту: `from src.config import settings`
settings = Settings()

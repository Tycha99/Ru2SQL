"""Лаунчер двух процессов Ru2SQL: FastAPI + Streamlit.

Запуск:
    python scripts/run_app.py

Скрипт стартует uvicorn в фоне, ждёт пока /health начнёт отвечать
(модель Qwen может качаться 5–10 минут при первом запуске), и
поднимает Streamlit как основной процесс. По Ctrl+C корректно
останавливает оба.

Полезно при разработке и для демо на защите: один Ctrl+C — и оба
процесса завершены, не нужно искать висящий uvicorn в taskmgr.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8000"))
STREAMLIT_PORT = int(os.environ.get("STREAMLIT_PORT", "8501"))
# Streamlit слушает 0.0.0.0 в контейнере (нужен внешний доступ),
# а локально по умолчанию 127.0.0.1 — это управляется отдельной переменной.
STREAMLIT_HOST = os.environ.get("STREAMLIT_HOST", "127.0.0.1")
API_URL = f"http://{API_HOST}:{API_PORT}"
WAIT_API_SECONDS = 600   # модель скачивается долго


def wait_for_api(timeout: int) -> bool:
    """Опрашиваем /health, пока не получим 200 или не выйдет timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_URL}/health", timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def main():
    print(f"[run_app] корень проекта: {ROOT}")
    print(f"[run_app] стартую uvicorn на {API_URL}")

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

    uvicorn_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "src.api.main:app",
            "--host", API_HOST,
            "--port", str(API_PORT),
        ],
        cwd=str(ROOT),
        creationflags=creation_flags,
    )

    try:
        print(f"[run_app] жду готовности API ({WAIT_API_SECONDS} сек макс) — "
              "при первом запуске Qwen качается с HuggingFace")
        if not wait_for_api(WAIT_API_SECONDS):
            print("[run_app] API не поднялся за отведённое время. Проверь логи uvicorn.")
            uvicorn_proc.terminate()
            sys.exit(1)
        print(f"[run_app] API готов, стартую Streamlit на http://{STREAMLIT_HOST}:{STREAMLIT_PORT}")

        env = os.environ.copy()
        env["RU2SQL_API_URL"] = API_URL
        streamlit_cmd = [
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port", str(STREAMLIT_PORT),
            "--server.address", STREAMLIT_HOST,
        ]
        streamlit_proc = subprocess.Popen(streamlit_cmd, cwd=str(ROOT), env=env)

        # Главный цикл — ждём, пока streamlit или uvicorn не упадёт
        try:
            while True:
                if uvicorn_proc.poll() is not None:
                    print("[run_app] uvicorn завершился, останавливаю streamlit")
                    streamlit_proc.terminate()
                    break
                if streamlit_proc.poll() is not None:
                    print("[run_app] streamlit завершился, останавливаю uvicorn")
                    break
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[run_app] Ctrl+C получен, завершаю процессы…")
            streamlit_proc.terminate()
    finally:
        try:
            uvicorn_proc.terminate()
            uvicorn_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            uvicorn_proc.kill()
        except Exception:
            pass
        print("[run_app] оба процесса остановлены")


if __name__ == "__main__":
    main()

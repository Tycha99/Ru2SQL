"""Загрузка модели + LoRA-адаптера и инференс.

На десктопе/ноутбуке без GPU работает на CPU. Медленно, но достаточно для разработки и демо.
На Kaggle/Colab — на GPU, быстрее.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.config import settings
from src.data.prompt import build_chat_messages
from src.models.postprocess import postprocess


@dataclass
class GenerationResult:
    sql: str
    raw_output: str


class InferenceEngine:
    """Singleton-обёртка над моделью. Загружается один раз при старте API."""

    def __init__(
        self,
        base_model_name: str | None = None,
        lora_adapter_path: str | None = None,
        device: str | None = None,
    ):
        self.base_model_name = base_model_name or settings.base_model_name
        self.lora_adapter_path = lora_adapter_path or settings.lora_adapter_path
        self.device = device or settings.device
        self.tokenizer = None
        self.model = None
        self._loaded = False

    def load(self) -> None:
        """Лениво грузим модель. На CPU без квантизации."""
        if self._loaded:
            return

        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
        # bfloat16 вдвое меньше float32 (~6 ГБ vs ~12 ГБ) и поддерживается на CPU
        self.model = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            dtype=torch.bfloat16,
            device_map=self.device if self.device != "cpu" else None,
        )

        # Подцепляем LoRA-адаптер: сначала ищем локально, потом на HF Hub
        adapter_path = Path(self.lora_adapter_path)
        adapter_id = str(adapter_path) if adapter_path.exists() else self.lora_adapter_path
        try:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, adapter_id)
        except ImportError:
            pass  # peft не установлен — работаем на базовой модели

        self.model.eval()
        self._loaded = True

    def generate(
        self,
        schema: str,
        question: str,
        max_new_tokens: int | None = None,
    ) -> GenerationResult:
        """Принимает schema (текст DDL) и вопрос, возвращает SQL."""
        if not self._loaded:
            self.load()

        messages = build_chat_messages(schema, question)
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or settings.max_new_tokens,
                do_sample=settings.do_sample,
                temperature=settings.temperature if settings.do_sample else 1.0,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
        raw = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return GenerationResult(sql=postprocess(raw), raw_output=raw)

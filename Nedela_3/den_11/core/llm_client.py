# -*- coding: utf-8 -*-
"""LLM-клиент за интерфейсом: LLMClient (ABC) + RouterAIClient + MockClient.

Агент зависит ТОЛЬКО от абстракции LLMClient; конкретный провайдер инжектится
на старте. MockClient — детерминированная заглушка, закрывает тесты без живого
ключа (API_KEY=test-key).
"""
import os
import time
from abc import ABC, abstractmethod

import requests

# OpenAI-совместимый эндпоинт RouterAI.
URL = "https://routerai.ru/api/v1/chat/completions"
MODEL = "stepfun/step-3.5-flash"
REQUEST_TIMEOUT = 30
# Паузы между повторами при HTTP 429.
RETRY_DELAYS = [2, 4, 8]


class LLMClient(ABC):
    """Абстрактный LLM-клиент. Сигнатура неизменяема (контракт §6.1)."""

    @abstractmethod
    def complete(self, messages, **params) -> str:
        """Отправляет список сообщений и возвращает текст ответа (или None при сбое)."""


class RouterAIClient(LLMClient):
    """Реальный клиент RouterAI (OpenAI-совместимый)."""

    def __init__(self, api_key: str = None, model: str = MODEL, max_tokens: int = None):
        self.api_key = api_key or os.getenv("API_KEY")
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, messages, **params) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {"model": self.model, "messages": messages}
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        data.update(params)

        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.post(URL, headers=headers, json=data,
                                         timeout=REQUEST_TIMEOUT)
                if response.status_code == 429:
                    if attempt == len(RETRY_DELAYS):
                        print("[API] Лимит запросов: все повторы исчерпаны.")
                        return None
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                response.raise_for_status()
                result = response.json()
                if "choices" not in result or not result["choices"]:
                    return None
                return result["choices"][0]["message"]["content"] or ""
            except requests.exceptions.RequestException as error:
                print(f"[API] Ошибка сети/HTTP: {error}")
                return None
            except (KeyError, IndexError, ValueError) as error:
                print(f"[API] Неожиданный формат ответа: {error}")
                return None
        return None


class MockClient(LLMClient):
    """Детерминированная заглушка для тестов и прогонов без живого ключа.

    Возвращает ответ, отражающий поданный контекст: перечисляет, какие блоки
    памяти/сообщения видит, — это позволяет сценариям проверять «доставку»
    слоёв без реальных вызовов API.
    """

    def __init__(self, name: str = "Mock"):
        self.name = name
        self.calls = []

    def complete(self, messages, **params) -> str:
        self.calls.append(messages)
        # Собираем видимый контекст: роли и первые символы содержимого.
        seen = []
        for msg in messages:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            seen.append(f"{role}:{content[:80]}")
        return f"[{self.name}] вижу {len(messages)} сообщений: " + " || ".join(seen)
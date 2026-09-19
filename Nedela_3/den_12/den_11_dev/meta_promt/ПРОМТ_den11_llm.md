# ПРОМТ_den11_llm — создание LLM-клиента за интерфейсом (core/llm_client.py)

## 1. Цель и граница
Создать `LLMClient` (ABC) + реализации: `RouterAIClient` (живой OpenAI-совместимый
вызов RouterAI) и `MockClient` (детерминированная заглушка для тестов без живого ключа).

Что НЕ делаем: не добавляем провайдеров сверх этих двух, не трогаем сборку промта.

## 2. Вход (зависимостей от storage/memory НЕТ — изолированный слой)
- Донор `Nedela_2/den_10/den_10_Kod.py` (паттерн retry 429, `requests`, обработка
  choices/usage, `raise_for_status`).
- `$AI9_ROOT/Step-3.5-Flash_params.md` (модель, эндпоинт, temperature 0..2).

## 3. Контракт (неизменяемый — источник истины; в цикле отладки НЕ правится)
```python
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...
    # Возвращает текст ответа или None при сбое. Сигнатура НЕ меняется.

class RouterAIClient(LLMClient):
    def __init__(self, api_key=None, model=MODEL, max_tokens=None)
    def complete(self, messages, **params) -> str

class MockClient(LLMClient):
    def __init__(self, name="Mock")
    def complete(self, messages, **params) -> str
```

### 3.1 Обязательные константы (уроки дня 10, п.16 §7)
```python
URL = "https://routerai.ru/api/v1/chat/completions"
MODEL = "stepfun/step-3.5-flash"      # не менять, не «уточнять»
MODEL_CONTEXT_LIMIT = 262144
PRICE_IN_PER_M = 11.0                 # ₽ / 1M входящих
PRICE_OUT_PER_M = 33.0                # ₽ / 1M исходящих
REQUEST_TIMEOUT = 30
RETRY_DELAYS = [2, 4, 8]              # повтор при HTTP 429
```

### 3.2 Требования к реализациям
- `RouterAIClient.complete`: формирует `{model, messages, [max_tokens], **params}`,
  шлёт через `requests.post(URL, headers={Authorization: Bearer key, Content-Type:
  application/json}, timeout=REQUEST_TIMEOUT)`; на 429 повторяет по RETRY_DELAYS,
  исчерпание → None; `raise_for_status()`; разбирает `choices[0].message.content`;
  любые ошибки → печать и None (не падать). Ключ берётся из аргумента или `os.getenv("API_KEY")`.
- `MockClient.complete`: детерминированный ответ — перечисляет сообщения, которые
  «видит» (`"role:content[:80]"`), чтобы тесты и сценарии проверяли доставку слоёв
  БЕЗ обращения к API. Накопление `self.calls` — для проверок в тестах.

## 4. Выход (scope — только этот файл)
- `core/llm_client.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — `test_llm.py` зелёный (exit 0). Проверяется: `LLMClient`
абстрактный (не инстанцируется); `MockClient` детерминирован и отражает слои/сообщения;
`RouterAIClient` без ключа/сети возвращает None, не падает. Живой вызов — только по
согласию (§3), в автономном прогоне не выполняется.

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_04_llm.md` (✅). Цикл отладки — §6.1.
Приёмка — §7 п.10 (LLM за интерфейсом, агент зависит только от ABC), п.16
(retry 429), п.17 (тесты без живого ключа).
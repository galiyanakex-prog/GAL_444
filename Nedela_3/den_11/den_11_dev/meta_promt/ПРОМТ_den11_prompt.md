# ПРОМТ_den11_prompt — создание PromptBuilder (core/prompt_builder.py)

## 1. Цель и граница
Создать сборщик промта явными блоками в каноническом порядке + дозированная доставка
(`deliver: set`) + токен-бюджет. Порядок (арх §2.4):
```
[system: роль] → [system: профиль] → [system: долговременная] → [system: рабочая] →
[system: summary общего префикса, опц.] → [messages: краткосрочная] →
[user: текущий запрос] → [резерв под ответ — это лимит бюджета, НЕ сообщение]
```

Что НЕ делаем: не реализуем фильтр инвариантов; не владеем слоями памяти (получает
УЖЕ собранные блоки — см. контракт владельца PromptContext ниже).

## 2. Вход (зависимость: контракт `memory/base.py` готов, блоки слоёв уже собраны Agent'ом)
- `ND/arch/arch_den_11_plan_2.md` §3.5 (порядок блоков, бюджет).
- `ND/arch/arch_den_11.md` §2.4.

## 3. Контракты (сигнатуры)
```python
BLOCK_ORDER = ("role", "profile", "long_term", "working", "summary",
               "short_term", "current")

class PromptContext:   # ВЛАДЕЛЕЦ: один и тот же класс, объявлен В core/agent.py; builder его импортирует
    def __init__(self, query: str, memory_blocks: dict, summary: str = "",
                 short_term_messages: list = None)
    # memory_blocks — {имя_слоя: str} (уже отформатированные тексты);
    # summary — общий summary префикса; short_term_messages — [{role, content}].

class PromptBuilder:
    def __init__(self, role_prompt: str, token_estimator=None)
    # token_estimator default: lambda text: max(1, len(text)//4)
    def build(self, ctx, deliver: set, budget: int | None = None) -> list[dict]
```

### 3.1 Семантика сборки (обязательна)
- Начинается с `{"role":"system","content": role_prompt}`.
- Слои `profile`, `long_term`, `working` добавляются как `system` с заголовком
  `"[<имя>]\n<текст>"` ТОЛЬКО если имя ∈ `deliver` и блок присутствует.
- `summary` — `system`-блок `"Саммари:\n<текст>"`, только если непустой и ∈ deliver.
- `short_term` — сообщения `{role, content}` из `ctx.short_term_messages`, только если ∈ deliver.
- Последним — `{"role":"user","content": ctx.query}` (обязательный блок).
- **Дозированная доставка**: набор слоёв — параметр; минимум один режим с урезанным
  набором (часть слоёв опущена ОСОЗНАННО) — это проверяется тестом.
- **Бюджет** (§3.5, R9): `sum(tokens обязательных) + sum(tokens необязательных) ≤ budget`.
  При превышении урезаются НЕОБЯЗАТЕЛЬНЫЕ блоки в порядке их следования; роль и
  текущий запрос — обязательные и не урезаются. Резерв — это «место под ответ»,
  которое бюджет должен оставить (проявляется как недоотправка необязательных блоков),
  а не дополнительное сообщение.

## 4. Выход (scope — только этот файл)
- `core/prompt_builder.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — `test_prompt.py` зелёный (exit 0). Проверяется: порядок
блоков; обязательные роль+query всегда есть и идут первой/последней; дозированная
доставка (невыбранный слой отсутствует); бюджет урезает необязательные блоки и не
трогает обязательные; summary-блок появляется только при наличии текста.

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_05_prompt.md` (✅). Цикл отладки — §6.1.
Приёмка — §7 п.5 (дозированная доставка), п.9 (явные блоки, видно в логе/артефакте).

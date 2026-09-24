# Сценарий ручной демонстрации «День 16 — Подключение MCP»

> Назначение: показать куратору выполнение требований `Задание_d16.txt` в живом REPL.
> Время: 5–7 минут. Файл — артефакт процесса, живёт только в `dev/`.

## Реквизиты

- Терминал в корне проекта, venv активирует обёртка сама.
- **Живой режим** (нагляднее): локальный stdio MCP-сервер поднимается сам
  (`servers.json` по умолчанию → `demo`); ключ LLM для MCP-шагов **не нужен**
  (`/mcp`-команды и `--mcp-probe` токенов LLM не тратят).
- **Запасной режим** (без сети/подпроцессов): тестовый контур
  (`FakeMCPTransport`) — `API_KEY=test-key python dev/tests_debug/scenario.py`
  (сценарий `scenario_mcp_discovery`).
- Демо-пользователь — свежий (`demo`), чтобы показать интервью и создание дерева с нуля.
- Для шага 4 понадобится второй терминал (REPL не закрываем).

---

## Шаг 1. One-shot результат задания: `--mcp-probe`

```bash
./run.sh --mcp-probe
```

**Увидите:**

```
[MCP] Подключение к серверам: demo
[MCP] Соединение установлено (READY). Список доступных инструментов:

  mcp.demo.get_time
    description: ...
    input_schema: {...}
  mcp.demo.echo
    ...
  mcp.demo.weather_stub
    ...

[MCP] Всего инструментов: 3
[MCP] Соединение закрыто (DISCONNECTED).
```

> Требования: соединение устанавливается; список инструментов корректно
> возвращается; список выводится кодом. Exit-код — 0.

## Шаг 2. REPL: семейство `/mcp`

```bash
./run.sh --user demo --mcp
```

(если пользователь `demo` новый — пройти интервью: имя, стиль, ограничения, контекст)

```
/mcp status
/mcp servers
/mcp connect
/mcp tools
/mcp refresh
/mcp status
/mcp disconnect
```

**Увидите:**

- `status` до подключения: `demo: disconnected`, каталог v0 (тулов: 0);
- `servers`: `demo: transport=stdio, enabled=True, trust=low, allowed=все, denied=—`;
- `connect`: «Подключение установлено: READY»;
- `tools` до refresh: «Каталог пуст (выполните: /mcp refresh)» — каталог честен;
- `refresh`: «Каталог обновлён: 3 тулов (версия 1); серверы READY: ['demo'];
  снимок сохранён (catalog.json)»;
- `tools` после refresh: `mcp.demo.get_time`, `mcp.demo.echo`,
  `mcp.demo.weather_stub` — имя, description, input-схема;
- `status`: `demo: ready`, «Каталог инструментов: версия 1, тулов: 3»;
- `disconnect`: «Соединения закрыты (DISCONNECTED)».

Во втором терминале:

```bash
cat users/demo/integrations/mcp/catalog.json
```

**Увидите:** снимок каталога (schema_version 1, version 1, 3 тула) — каталог
переживает перезапуск (персистентность через `Store`).

## Шаг 3. Изоляция прав (allowed/denied_tools)

В `users/demo/integrations/mcp/servers.json` добавить серверу `demo`
`"denied_tools": ["weather_stub"]`, затем в REPL:

```
/mcp connect
/mcp refresh
/mcp tools
```

**Увидите:** 2 тула — `weather_stub` не попал в discovery (изоляция прав через
тулинг: серверу даём только часть тулов). Вернуть конфиг обратно — `/mcp refresh`
снова даёт 3 тула (атомарный swap, version растёт).

## Шаг 4. Недоступный сервер — деградация, не падение

В `servers.json` заменить `command` на несуществующий модуль (или остановить
сервер), затем:

```
/mcp connect
/mcp status
/memory
```

**Увидите:** `demo: failed` (overall FAILED), тулов нет — но REPL жив: `/memory`,
`/profile`, `/state` работают (память, профили и машина состояний не зависят от
MCP). Вернуть конфиг обратно.

## Шаг 5 (опционально, 60 секунд). Наследие + граница «инструмент ≠ переход»

```
/plan Сделать REST API на Django
/goto implementation
/state
```

**Увидите:** отказ «Нельзя делать реализацию до утверждённого плана…» — машина
состояний дней 11–15 работает как раньше; MCP её не трогает (вызов инструмента
никогда не означает переход `TaskStage`).

---

## Соответствие требованиям `Задание_d16.txt`

| Требование задания | Где показано |
|---|---|
| MCP SDK установлен / сервер поднимается | Шаг 1 (stdio-подпроцесс demo_server поднимается сам) |
| Соединение устанавливается | Шаг 1 («Соединение установлено (READY)»), Шаг 2 (`/mcp connect`) |
| Список инструментов корректно возвращается | Шаги 1–2 (3 тула: get_time, echo, weather_stub — нормализация → ToolRegistry) |
| Список выводится кодом | Шаг 1 (`--mcp-probe` печатает имя/description/схему, exit 0), Шаг 2 (`/mcp tools`) |
| Изоляция прав через тулинг | Шаг 3 (denied_tools) |
| Недоступный сервер не роняет агента | Шаг 4 (FAILED, REPL жив) |
| Наследие без регрессии | Шаг 5 (переходы/память работают; MCP off по умолчанию) |

**Финальная фраза куратору:** «Агент подключается к MCP-серверу по стандарту:
handshake initialize → tools/list → нормализация во внутреннюю модель → каталог
в ToolRegistry с атомарным snapshot; список инструментов выводится кодом
(--mcp-probe и /mcp tools); MCP — источник инструментов, а не слой контроля:
TaskStage, память и профили MCP не трогает».

---

## Замечания для честности демо

- `--mcp-probe` и `/mcp connect` поднимают **локальный** stdio MCP-сервер
  (`integrations/mcp/demo_server.py`, подпроцесс) — внешняя сеть не нужна;
  ключ LLM не нужен (`/mcp`-команды токенов не тратят).
- Авто-эквивалент демо: `API_KEY=test-key python dev/tests_debug/scenario.py`
  (сценарий `scenario_mcp_discovery`: probe-флоу, REPL-флоу, деградация — всё на
  `FakeMCPTransport`, без подпроцессов) + гейт `check_acceptance.sh` (18/18).
- Без флага `--mcp` агент работает ровно как den_15 (MCP off по умолчанию —
  критерий 40).
- После демо дерево `users/demo/` можно удалить вручную или оставить как артефакт
  показа; на данные `cli_user`/`tester` демо не влияет.
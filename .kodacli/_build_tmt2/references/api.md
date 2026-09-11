# API

## Endpoint
`POST https://routerai.ru/api/v1/chat/completions` — OpenAI-совместимый чат-эндпоинт RouterAI.

## Model
`stepfun/step-3.5-flash` — основная модель проекта AI_9 (см. `Step-3.5-Flash_params.md`).
- Контекст: 256K токенов.
- Стоимость: 11 RUB / 1M входных токенов, 33 RUB / 1M выходных.
- Разрешено менять: `temperature`, `top_p`, `max_tokens`, `stop`, `presence_penalty`, `frequency_penalty`.
- Запрещено передавать: `reasoning_effort`, `thinking`, `response_format`, `tools`, `seed`.
  Скрипт их не отправляет.

## Request
```json
{
  "model": "stepfun/step-3.5-flash",
  "messages": [
    {"role": "system", "content": "<промпт режима>"},
    {"role": "user", "content": "<текст пользователя>"}
  ],
  "temperature": 0.2
}
```
Заголовки: `Authorization: Bearer $API_KEY`, `Content-Type: application/json`.
Таймаут одного запроса: 30 сек.

## Response
Из ответа берётся `choices[0].message.content` и обрезается по краям.
Любое другое устройство ответа считается ошибкой формата (exit 1).

## Retry policy
Только HTTP 429: до трёх повторов с паузами 2, 4, 8 сек (как в `Den_6_Kod*.py`).
Другие ошибки (4xx/5xx, сеть, таймаут) не повторяются — скрипт завершается с exit 1.

## Key lookup
Порядок поиска `API_KEY`:
1. `--env <путь>` (явный `.env`);
2. переменная окружения `TMT_ENV_FILE`;
3. переменная окружения `API_KEY`;
4. ближайший `.env` от текущего каталога вверх по дереву.

Ключ подставляется только в заголовок запроса и никогда не печатается.

## Cost per mode
- `compress` / `restore` — 1 запрос;
- `roundtrip` — 2 запроса;
- `ask` — 3 запроса.

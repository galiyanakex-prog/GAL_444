# API

## Endpoint
`POST https://api.kodacode.ru/v1/chat/completions` — OpenAI-совместимый
чат-эндпоинт внутренней экосистемы Koda. Внешние провайдеры не используются.

## Models
- `koda-pro` — по умолчанию (совпадает с `"model"` в `~/.kodacli/settings.json`).
- `koda-base` — альтернатива (быстрее, для простых прогонов слоёв).
Другие модели передавать запрещено. Флаг `--model` принимает только эти два
значения.

## Request
```json
{
  "model": "koda-pro",
  "messages": [
    {"role": "system", "content": "<промпт слоя>"},
    {"role": "user", "content": "<текст>"}
  ],
  "temperature": 0.2,
  "max_tokens": 900
}
```
Заголовки: `Authorization: Bearer $TOKEN`, `Content-Type: application/json`.
Таймаут одного запроса: 30 сек. `--max-tokens 0` — не передавать лимит.
Из ответа берётся `choices[0].message.content` (`reasoning_content`
игнорируется).

## Response
`choices[0].message.content`, обрезка по краям. Другое устройство ответа —
ошибка формата (exit 1).

## Retry policy
Только HTTP 429: до трёх повторов с паузами 2, 4, 8 сек.
Другие ошибки (4xx/5xx, сеть, таймаут) не повторяются — exit 1.

## Token lookup (koda-auth)
1. `--token-file <путь>` (первая строка — токен);
2. переменная окружения `KODA_AUTH_TOKEN`;
3. штатное хранилище koda-cli: `~/.config/koda/credentials.json`,
   поле `kodaAuth.accessToken`.

Токен читается лениво: только когда реально нужен запрос к API. Ход, закрытый
кэшем или таблицей коротких ответов, проходит без токена.
Токен идёт только в заголовок и никогда не печатается.
Не найден при нужде в запросе — exit 2. Срок действия — `kodaAuth.expiresAt`;
при истечении требуется повторный вход в koda-cli (скрипт токен не обновляет).

## Cache
Файл `<скилл>/.cache/tmt_cache.json`, ключ — sha256(режим|модель|текст).
Попадание в кэш = 0 запросов. Флаги: `--cache <путь>`, `--no-cache`.
Неудачные ответы в кэш не пишутся.

## Calls per mode
- `in` (алиас `compress`) — 1 запрос; 0 при кэше или таблице коротких ответов;
- `out` (алиас `restore`) — 1 запрос; 0 при кэше;
- `gate` — 0, если в блоке нет строк `USER:` (exit 3); иначе 1 запрос на `out`;
- `batch` — 1 запрос на все не-кэшированные строки;
- `roundtrip` — 2 запроса;
- `ask` — 3 запроса.
# Examples

## Полный ход (смысл всего скилла)
User (RU):
"Привет! Подскажи, пожалуйста, как у нас в проекте проверяется, что виртуальное
окружение реально активно? А то я каждый раз не уверен."

L1 IN (скрипт, 1 запрос):
```bash
$PY $TMT --mode in --text "<текст выше>"
```
"[IN] Verify virtual environment is actually active in this project."

L2 CORE (агент, machine English, без скрипта и без русского):
```internal
Check VIRTUAL_ENV, which python -> .venv/bin. Prompt prefix unreliable.
Repo has .venv in AI_9 and Nedela_1/2.
```

Gate: пользователю нужен ответ на вопрос -> одна пользовательская строка.

L3 OUT (скрипт, 1 запрос):
```bash
$PY $TMT --mode out --raw --text "Check VIRTUAL_ENV is set. Check \`which python\` points to .venv/bin. Prompt prefix is unreliable."
```
"Проверьте, что переменная VIRTUAL_ENV задана и `which python` указывает на
.venv/bin. Префикс в приглашении терминала — ненадёжный признак."

Пользователь видит только этот текст. Рассуждения выше — нет.

## Молчаливый ход (exit 3, 0 запросов)
Агент поправил `den_8_Kod.py`, прогнал ruff и тесты:
```internal
Ruff clean. 12 tests pass.
```
Строк `USER:` нет -> `--mode gate` выходит с кодом 3, API не дёргается,
русского вывода нет.

## Шум не доходит до пользователя
Плохо (это ушло бы в перевод):
"Sure! I have successfully updated the file. Let me know if anything else needed."
Хорошо (не помечено USER: -> молчаливый ход):
"Updated den_8_Kod.py: retry on 429 added. Tests pass."

## Gate по internal-блоку
```bash
$PY $TMT --mode gate --text '```internal
Build ok, 3 files touched.
USER: Готово. Запустить тесты?
```'
```
"[OUT] Готово. Запустить тесты?" — служебная строка отброшена до перевода.

## in (standalone)
Input:
"Нужен скрипт, который читает токен из credentials.json и делает запрос к
эндпоинту Koda."
Output:
"[IN] Create script. Read token from credentials.json. Send request to Koda endpoint."

## out (standalone)
Input:
"Add retry logic for 429. Max 3 attempts. Delay 2s, 4s, 8s."
Output:
"[OUT] Добавь логику повторов при ошибке 429. Максимум три попытки, задержки 2, 4 и 8 секунд."

## ask (standalone, все слои делает эндпоинт)
Input: RU вопрос.
Конвейер: in -> answer (EN machine) -> out.
Пользователь видит `[OUT]`; `[IN]` и `[ANSWER-EN]` — только по запросу.

## Routing
- русское сообщение, `mode=...` нет -> автоматический ход (in, core, gate, out)
- явный `mode=...` -> standalone-режим скрипта
- «сожми в машинный английский» -> `in`
- «разверни в русский» -> `out`
- «покажи обе формы» -> `roundtrip`
- «реши через эндпоинт Koda» -> `ask`
- «покажи внутренний слой» -> напечатать EN-заметки как есть, без перевода
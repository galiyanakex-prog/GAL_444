# Examples

## compress
Input:
"Привет! Подскажи, пожалуйста, можно ли как-то настроить проект так, чтобы он автоматически подхватывал настройки из файла .env, иначе мне приходится каждый раз вводить ключ вручную, а это очень неудобно."
Output:
"Configure project to auto-load settings from .env. Manual key entry each run is inconvenient."

## restore
Input:
"Add retry logic for 429. Max 3 attempts. Delay 2s, 4s, 8s."
Output:
"Добавь логику повторов при ошибке 429. Максимум три попытки, задержки 2, 4 и 8 секунд."

## roundtrip
Input:
"Нужен скрипт, который читает API_KEY из .env и делает запрос к RouterAI."
Compress:
"Create script. Read API_KEY from .env. Send request to RouterAI."
Restore:
"Нужен скрипт, который читает API_KEY из .env и отправляет запрос к RouterAI."

## ask
Input:
"Как проверить, что виртуальное окружение действительно активно?"
Compress:
"Verify virtual environment is active."
Answer-EN:
"Check VIRTUAL_ENV set. Check `which python` points to .venv/bin. Prompt prefix is unreliable."
Restore:
"Проверьте, что переменная VIRTUAL_ENV задана и `which python` указывает на .venv/bin. Префикс в приглашении терминала — ненадёжный признак."

## Routing
- "Сожми этот текст в машинный английский" -> `--mode compress`
- "Разверни обратно в нормальный русский" -> `--mode restore`
- "Покажи обе формы" -> `--mode roundtrip`
- "Реши задачу через Step-3.5-Flash в машинном английском" -> `--mode ask`

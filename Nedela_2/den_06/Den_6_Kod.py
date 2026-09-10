# ============================================================================
# День 6 — Den_6_Kod.py (все три техники через CLI-флаги)
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Три варианта A/B/C — это три стратегии поверх одного и того же каркаса
# «чат-бот с историей». Вместо трёх копий кода делаем один каркас +
# подключаемые стратегии. Выбор стратегии — два флага: --context (как
# формировать окно запроса) и --memory (что и как сохранять/загружать).
# Это первый шаг к пониманию, почему в больших проектах стратегии оформляют
# отдельными модулями (Strategy pattern). Здесь диспетчеризация — через
# if/elif по строке режима, как принято в учебных однофайловых скриптах.
#
# Запуск:
#   python den_06/Den_6_Kod.py --context sliding-window --memory session
#   python den_06/Den_6_Kod.py --context compression --memory compressed
#   python den_06/Den_6_Kod.py --context leveling --memory layered
# ============================================================================

# 1. Импорты: os, sys, argparse, datetime, requests, dotenv ------------------

# Импортируем модуль os для чтения переменных окружения и проверки файлов.
import os

# Импортируем модуль sys для настройки кодировки стандартного ввода.
import sys

# Импортируем модуль traceback для записи полного стека ошибки в журнал.
import traceback

# Импортируем модуль time для паузы между повторами при HTTP 429.
import time

# Импортируем модуль argparse для разбора аргументов командной строки.
import argparse

# Импортируем модуль datetime для отметок времени в логе и файле саммари.
from datetime import datetime

# Импортируем библиотеку для отправки HTTP-запросов к API.
import requests

# Импортируем функцию, которая загружает переменные из файла .env.
from dotenv import load_dotenv


# 2. load_dotenv() + проверка API_KEY -----------------------------------------

# Загружаем переменные из файла .env в окружение программы.
load_dotenv()

# Получаем API-ключ из переменной окружения API_KEY.
api_key = os.getenv("API_KEY")

# Настраиваем кодировку stdin на UTF-8, чтобы русский текст вводился корректно.
sys.stdin.reconfigure(encoding='utf-8')

# Проверяем, удалось ли найти API-ключ.
if not api_key:
    # Останавливаем программу и показываем понятную ошибку, если ключ отсутствует.
    raise RuntimeError(
        "Переменная API_KEY не найдена. "
        "Добавьте API-ключ в файл .env"
    )

# 3. Парсинг и валидация флагов -----------------------------------------------

# Разбираем аргументы командной строки.
parser = argparse.ArgumentParser(
    description="Чат-бот Дня 6: три техники контекста и три типа памяти через флаги."
)

# Флаг --context: техника управления контекстом (по умолчанию sliding-window).
parser.add_argument(
    "--context",
    type=str,
    default="sliding-window",
    choices=["sliding-window", "compression", "leveling"],
    help="Техника контекста: sliding-window, compression, leveling.",
)

# Флаг --memory: тип памяти (по умолчанию session).
parser.add_argument(
    "--memory",
    type=str,
    default="session",
    choices=["session", "compressed", "layered"],
    help="Тип памяти: session, compressed, layered.",
)

# Флаг --window: размер окна для sliding-window (по умолчанию 10).
parser.add_argument(
    "--window",
    type=int,
    default=10,
    help="Размер окна для sliding-window (по умолчанию 10).",
)

# Флаг --keep: размер окна для compression/leveling (по умолчанию 6).
parser.add_argument(
    "--keep",
    type=int,
    default=6,
    help="Размер окна для compression/leveling (по умолчанию 6).",
)

# Флаг --load: какие слои загружать из лога (только для layered-памяти).
parser.add_argument(
    "--load",
    type=str,
    default="all",
    help="Какие слои загружать (layered): all, high, high,mid, none.",
)

# Флаг --log: имя лог-файла (по умолчанию Den_6_log.md).
parser.add_argument(
    "--log",
    type=str,
    default="Den_6_log.md",
    help="Имя лог-файла.",
)

# Выполняем разбор аргументов и сохраняем результат.
args = parser.parse_args()

# Валидация: layered-память имеет смысл только с leveling-контекстом.
if args.memory == "layered" and args.context != "leveling":
    # Предупреждаем и автоисправляем контекст на leveling (не падаем).
    print("[Конфиг] layered-память имеет смысл только с leveling-контекстом, включаю leveling")
    # Исправляем контекст на leveling.
    args.context = "leveling"

# Валидация: compressed-память имеет смысл только с compression-контекстом.
if args.memory == "compressed" and args.context != "compression":
    # Предупреждаем и автоисправляем контекст на compression (не падаем).
    print("[Конфиг] compressed-память имеет смысл только с compression-контекстом, включаю compression")
    # Исправляем контекст на compression.
    args.context = "compression"

# Валидация: session-память имеет смысл только со sliding-window-контекстом.
if args.memory == "session" and args.context != "sliding-window":
    # Предупреждаем и автоисправляем контекст на sliding-window (не падаем).
    print("[Конфиг] session-память имеет смысл только со sliding-window-контекстом, включаю sliding-window")
    # Исправляем контекст на sliding-window.
    args.context = "sliding-window"

# Определяем эффективный размер окна в зависимости от контекста.
if args.context == "sliding-window":
    # Для sliding-window используем --window (по умолчанию 10).
    WINDOW = args.window
# Для compression и leveling используем --keep (по умолчанию 6).
else:
    # Размер окна из флага --keep.
    WINDOW = args.keep

# Имя лог-файла из флага --log.
LOG_FILE = args.log

# Имя файла саммари (для compressed и layered памяти).
SUMMARY_FILE = "Den_6_summary.md"

# 4. Константы -----------------------------------------------------------------

# API endpoint RouterAI (OpenAI-совместимый).
URL = "https://routerai.ru/api/v1/chat/completions"

# Модель, через которую идут запросы.
MODEL = "stepfun/step-3.5-flash"

# Порог сжатия: когда вне окна накапливается >= 8 сообщений — запускаем сжатие.
COMPRESS_THRESHOLD = 8

# Заголовки HTTP-запроса: авторизация по ключу и тип данных JSON.
HEADERS = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# System prompt — роль агента (стратегический слой, сообщение 1).
SYSTEM_PROMPT = "Ты полезный ассистент. Отвечай кратко на русском языке."

# Стратегический слой, сообщение 2: общие инструкции (только для leveling).
RULES_PROMPT = (
    "Правила работы: сохраняй ключевые факты о пользователе. "
    "Если пользователь просит что-то запомнить — подтверди это."
)

# System prompt для отдельного запроса сжатия истории в саммари.
COMPRESS_PROMPT = (
    "Ты сжимаешь диалоги. Сделай краткое саммари ключевых фактов, "
    "решений и договорённостей. Только саммари, без приветствий и комментариев."
)

# Таймаут запроса к API в секундах.
REQUEST_TIMEOUT = 30

# Список задержек между повторами при HTTP 429 (экспоненциальная: 2 → 4 → 8 сек).
RETRY_DELAYS = [2, 4, 8]

# Имя файла журнала ошибок: сюда пишется полный стек любой непредвиденной ошибки.
ERROR_LOG = "Den_6_error.log"


# Функция записи непредвиденной ошибки в журнал (с полным стеком вызовов).
def log_error(context, error):
    # Открываем журнал ошибок в режиме дозаписи с кодировкой UTF-8.
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        # Пишем разделитель с датой, временем и контекстом ошибки.
        f.write(f"\n{'=' * 60}\n")
        # Пишем время и место возникновения ошибки.
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {context}\n")
        # Пишем тип ошибки и её сообщение.
        f.write(f"{type(error).__name__}: {error}\n")
        # Пишем полный стек вызовов — чтобы найти точное место падения.
        f.write(traceback.format_exc())
    # Дублируем краткое сообщение в консоль (окно может закрыться).
    print(f"[Ошибка] {context}: {error} (подробности в {ERROR_LOG})")

# Словарь маркеров слоёв: имя слоя -> список ключевых слов (в нижнем регистре).
LAYER_MARKERS = {
    # Высокий слой: ключевые факты, решения, просьбы запомнить.
    "high": ["запомни", "важно", "меня зовут", "мой", "моя", "моё", "всегда", "никогда"],
    # Средний слой: задачи и планы.
    "mid": ["нужно", "сделать", "план", "давай", "задача"],
}

# Словарь подписей слоёв для вывода в консоль и лог.
LAYER_LABELS = {
    # Подпись высокого слоя.
    "high": "high",
    # Подпись среднего слоя.
    "mid": "mid",
    # Подпись низкого слоя (всё остальное).
    "low": "low",
}

# 5. ask_llm(messages) — общий запрос с retry при 429 --------------------------


# Функция отправки сообщения в LLM с повтором при HTTP 429 (лимит запросов).
def ask_llm(messages):
    # Формируем тело запроса: модель и список сообщений.
    data = {
        "model": MODEL,
        "messages": messages,
    }

    # Перебираем попытки: первая обычная, дальше — с задержками из RETRY_DELAYS.
    for attempt in range(len(RETRY_DELAYS) + 1):
        # Начинаем блок обработки возможных ошибок при обращении к API.
        try:
            # Отправляем POST-запрос к API с таймаутом.
            response = requests.post(
                URL, headers=HEADERS, json=data, timeout=REQUEST_TIMEOUT
            )

            # Если сервер вернул 429 (слишком много запросов) — пробуем ещё раз.
            if response.status_code == 429:
                # Если это была последняя попытка — выходим из цикла с ошибкой.
                if attempt == len(RETRY_DELAYS):
                    # Сообщаем пользователю, что лимит не снялся за все попытки.
                    print("[API] Лимит запросов: все повторы исчерпаны.\n")
                    # Возвращаем None — вызывающий код поймёт, что ответа нет.
                    return None

                # Берём задержку для текущей попытки из списка.
                delay = RETRY_DELAYS[attempt]

                # Сообщаем пользователю, что ждём перед повтором.
                print(f"[API] Лимит запросов, повтор через {delay} сек...")

                # Приостанавливаем программу на указанное количество секунд.
                time.sleep(delay)

                # Переходим к следующей попытке.
                continue

            # Проверяем остальные HTTP-ошибки (неверный ключ, недоступность и т.п.).
            response.raise_for_status()

            # Получаем JSON-ответ сервера.
            result = response.json()

            # Проверяем, что в ответе есть варианты ответа (choices).
            if "choices" not in result or not result["choices"]:
                # Сообщаем о неожиданном формате ответа.
                print("[API] Неожиданный формат ответа: нет choices.\n")
                # Возвращаем None — ответа нет.
                return None

            # Достаём текст первого варианта ответа модели.
            bot_response = result["choices"][0]["message"]["content"] or ""

            # Возвращаем текст ответа вызывающему коду.
            return bot_response

        # Перехватываем ошибку HTTP (кроме уже обработанной 429).
        except requests.exceptions.HTTPError as error:
            # Выводим понятное сообщение с текстом ошибки.
            print(f"[API] Ошибка HTTP: {error}\n")
            # Возвращаем None — ответа нет.
            return None

        # Перехватываем сетевые ошибки (нет соединения, таймаут).
        except requests.exceptions.RequestException as error:
            # Выводим понятное сообщение с текстом ошибки.
            print(f"[API] Ошибка сети: {error}\n")
            # Возвращаем None — ответа нет.
            return None

        # Перехватываем ошибки разбора ответа (неожиданный формат JSON).
        except (KeyError, IndexError, ValueError) as error:
            # Выводим понятное сообщение об ошибке формата.
            print(f"[API] Неожиданный формат ответа API: {error}\n")
            # Возвращаем None — ответа нет.
            return None


# 6. compress_history — общее сжатие (для B и C) -------------------------------


# Функция сжатия старых сообщений в саммари через отдельный вызов LLM.
def compress_history(old_messages, old_summary):
    # Собираем текст переписки из старых сообщений: «Роль: текст» построчно.
    transcript = "\n".join(
        f"{'Пользователь' if msg['role'] == 'user' else 'Агент'}: {msg['content']}"
        for msg in old_messages
    )

    # Формируем сообщения для запроса сжатия: system-промпт + задание.
    compress_messages = [
        # System-сообщение с ролью «сжимателя диалогов».
        {"role": "system", "content": COMPRESS_PROMPT},
        # User-сообщение: старое саммари (для консолидации) + переписка.
        {
            "role": "user",
            "content": (
                f"Предыдущее саммари:\n{old_summary or '(нет)'}\n\n"
                f"Сообщения диалога:\n{transcript}\n\n"
                "Объедини всё в единое обновлённое саммари."
            ),
        },
    ]

    # Отправляем запрос сжатия в LLM (retry при 429 внутри ask_llm).
    new_summary = ask_llm(compress_messages)

    # Возвращаем текст саммари или None, если запрос не удался.
    return new_summary


# 7. detect_layer — автоопределение слоя (для C) --------------------------------


# Функция автоопределения слоя сообщения по ключевым маркерам.
def detect_layer(text):
    # Приводим текст к нижнему регистру для поиска маркеров без учёта регистра.
    text_lower = text.lower()

    # Сначала проверяем маркеры высокого слоя (факты и решения важнее задач).
    for marker in LAYER_MARKERS["high"]:
        # Если маркер найден в тексте — сообщение относится к высокому слою.
        if marker in text_lower:
            # Возвращаем имя слоя «high».
            return "high"

    # Затем проверяем маркеры среднего слоя (задачи и планы).
    for marker in LAYER_MARKERS["mid"]:
        # Если маркер найден в тексте — сообщение относится к среднему слою.
        if marker in text_lower:
            # Возвращаем имя слоя «mid».
            return "mid"

    # Если ни один маркер не найден — это обычная переписка, низкий слой.
    return "low"


# 8. build_messages_sliding — стратегия контекста A ------------------------------


# Функция формирования запроса для sliding-window: [system] + последние N.
def build_messages_sliding(history, window):
    # Начинаем с system-сообщения — роли агента.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Добавляем последние N сообщений диалога (окно).
    messages.extend(
        # Каждое сообщение превращаем в формат API: только role и content.
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-window:]
    )

    # Возвращаем готовый список сообщений для запроса.
    return messages


# 9. build_messages_compression — стратегия контекста B --------------------------


# Функция формирования запроса для compression: [system] + [саммари] + окно.
def build_messages_compression(history, summary, keep):
    # Начинаем с system-сообщения — роли агента.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Если саммари не пустое — добавляем его вторым system-сообщением.
    if summary:
        # Саммари едет сразу после system, чтобы агент «помнил» старый контекст.
        messages.append(
            {"role": "system", "content": f"Саммари более раннего диалога:\n{summary}"}
        )

    # Добавляем последние K сообщений диалога (оперативное окно).
    messages.extend(
        # Каждое сообщение превращаем в формат API: только role и content.
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-keep:]
    )

    # Возвращаем готовый список сообщений для запроса.
    return messages


# 10. build_messages_leveling — стратегия контекста C -----------------------------


# Функция формирования запроса для leveling: стратегия → инструкции → саммари → окно.
def build_messages_leveling(history, summary, keep):
    # Начинаем со стратегического слоя: сообщение 1 — роль агента.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Стратегический слой, сообщение 2 — общие инструкции (не меняются).
    messages.append({"role": "system", "content": RULES_PROMPT})

    # Если саммари оперативного слоя не пустое — добавляем его третьим system-сообщением.
    if summary:
        # Саммари едет после инструкций, чтобы агент «помнил» сжатый контекст.
        messages.append(
            {"role": "system", "content": f"Саммари более раннего диалога:\n{summary}"}
        )

    # Оперативный слой: добавляем последние K сообщений диалога.
    messages.extend(
        # Каждое сообщение превращаем в формат API: только role и content.
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-keep:]
    )

    # Возвращаем готовый список сообщений для запроса.
    return messages


# 11. build_messages — диспетчер стратегий контекста ------------------------------


# Функция-диспетчер: выбирает стратегию контекста по имени режима.
# (В реальном проекте здесь был бы Strategy pattern с классами-стратегиями.)
def build_messages(mode, history, summary, window):
    # Для sliding-window вызываем соответствующую стратегию.
    if mode == "sliding-window":
        # Возвращаем запрос, собранный стратегией A.
        return build_messages_sliding(history, window)

    # Для compression вызываем соответствующую стратегию.
    if mode == "compression":
        # Возвращаем запрос, собранный стратегией B.
        return build_messages_compression(history, summary, window)

    # Для leveling вызываем соответствующую стратегию.
    if mode == "leveling":
        # Возвращаем запрос, собранный стратегией C.
        return build_messages_leveling(history, summary, window)

    # Если режим неизвестен — это ошибка конфигурации, сообщаем и падаем.
    raise ValueError(f"Неизвестный режим контекста: {mode}")


# 12. save/load: функции стратегий памяти -----------------------------------------


# Функция дозаписи одного сообщения в Markdown-лог (общая для всех режимов).
def append_log(msg, layered=False):
    # Определяем роль для отображения («Вы» или «Агент»).
    role = "Вы" if msg["role"] == "user" else "Агент"

    # Открываем лог-файл в режиме дозаписи с кодировкой UTF-8.
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        # Для layered-памяти добавляем пометку слоя в строку лога.
        if layered:
            # Записываем строку формата «**Роль** [слой]: текст».
            f.write(f"**{role}** [{msg['layer']}]: {msg['content']}\n")
        # Для остальных режимов — обычная строка без слоя.
        else:
            # Записываем строку формата «**Роль:** текст».
            f.write(f"**{role}:** {msg['content']}\n")


# Функция записи события сжатия в Markdown-лог (для compressed и layered).
def log_compression(n, length):
    # Открываем лог-файл в режиме дозаписи с кодировкой UTF-8.
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        # Пишем событие сжатия: время, количество сообщений и длину саммари.
        f.write(
            f"> 🔧 [{datetime.now().strftime('%H:%M:%S')}] "
            f"Сжатие: {n} сообщений → саммари ({length} символов)\n"
        )


# Функция загрузки саммари из файла (для compressed и layered памяти).
def load_compressed_summary():
    # Если файла саммари нет — возвращаем пустую строку.
    if not os.path.exists(SUMMARY_FILE):
        # Пустая строка означает «саммари пока нет».
        return ""

    # Открываем файл саммари на чтение с кодировкой UTF-8.
    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        # Читаем все строки файла в список.
        lines = f.readlines()

    # Пропускаем заголовок (# ...) и строку «Обновлено: ...», собираем остальное.
    text_lines = [
        # Берём строку без перевода строки, если это не заголовок и не дата.
        line.rstrip("\n")
        for line in lines
        # Пропускаем первую строку-заголовок и строку с датой обновления.
        if not line.startswith("#") and not line.startswith("Обновлено:")
    ]

    # Убираем пустые строки в начале и конце, склеиваем остальной текст.
    return "\n".join(text_lines).strip()


# Функция сохранения саммари в файл (перезапись целиком при каждом обновлении).
def save_compressed_summary(summary):
    # Открываем файл саммари на запись (перезапись) с кодировкой UTF-8.
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        # Пишем заголовок первого уровня с названием техники.
        f.write("# Саммари диалога — День 6\n")
        # Пишем строку с датой и временем последнего обновления.
        f.write(f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        # Пишем текст саммари и перевод строки в конце.
        f.write(f"{summary}\n")


# Функция загрузки выбранных слоёв из лога прошлой сессии (для layered памяти).
def load_layered_history(path, layers):
    # Если лог-файла нет или набор слоёв пуст — возвращаем пустой список.
    if not os.path.exists(path) or not layers:
        # Пустой список — загружать нечего.
        return []

    # Список загруженных сообщений из выбранных слоёв.
    loaded = []

    # Текущая роль сообщения (определяется по строке лога).
    current_role = None

    # Открываем лог-файл на чтение с кодировкой UTF-8.
    with open(path, "r", encoding="utf-8") as f:
        # Читаем лог построчно.
        for line in f:
            # Убираем пробелы и перевод строки по краям.
            stripped = line.strip()

            # Строки вида «**Вы** [high]: текст» — сообщения пользователя.
            if stripped.startswith("**Вы** ["):
                # Запоминаем роль пользователя для этой строки.
                current_role = "user"
            # Строки вида «**Агент** [high]: текст» — сообщения агента.
            elif stripped.startswith("**Агент** ["):
                # Запоминаем роль агента для этой строки.
                current_role = "assistant"
            # Прочие строки (заголовки, даты, события сжатия) пропускаем.
            else:
                # Сбрасываем роль и переходим к следующей строке.
                current_role = None
                # Переходим к следующей строке лога.
                continue

            # Извлекаем слой из квадратных скобок после роли.
            layer_part = stripped.split("[", 1)[1].split("]", 1)[0]

            # Извлекаем текст сообщения после «]: ».
            content = stripped.split("]: ", 1)[1] if "]: " in stripped else ""

            # Если слой сообщения входит в выбранный набор — загружаем его.
            if layer_part in layers:
                # Добавляем сообщение в формате полной истории.
                loaded.append(
                    {
                        # Роль сообщения (user или assistant).
                        "role": current_role,
                        # Текст сообщения.
                        "content": content,
                        # Слой сообщения.
                        "layer": layer_part,
                        # Время загрузки (оригинальное время в логе не хранится).
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

    # Возвращаем список загруженных сообщений выбранных слоёв.
    return loaded


# 13. Обработчики команд (с проверкой доступности в режиме) -----------------------


# Обработчик /history: полная история с пометками, зависящими от режима.
def cmd_history(full_history, archived, summary):
    # Вычисляем индекс, с которого сообщения находятся в окне.
    in_window_from = max(0, len(full_history) - WINDOW)

    # Сначала показываем сообщения, уже свёрнутые в саммари (B и C).
    for msg in archived:
        # Определяем роль сообщения для отображения («Вы» или «Агент»).
        role = "Вы" if msg["role"] == "user" else "Агент"

        # Для layered-памяти добавляем пометку слоя.
        if args.memory == "layered":
            # Печатаем сообщение с пометкой слоя и «в саммари».
            print(f"[{msg['layer']}] [в саммари] {role}: {msg['content']}")
        # Для остальных режимов — без слоя.
        else:
            # Печатаем сообщение с пометкой «в саммари».
            print(f"[в саммари] {role}: {msg['content']}")

    # Затем показываем активную историю: в окне или вне окна.
    for i, msg in enumerate(full_history):
        # Определяем роль сообщения для отображения («Вы» или «Агент»).
        role = "Вы" if msg["role"] == "user" else "Агент"

        # Формируем пометку слоя для layered-памяти.
        layer_tag = f"[{msg['layer']}] " if args.memory == "layered" else ""

        # Если индекс сообщения попадает в окно — помечаем «в окне».
        if i >= in_window_from:
            # Печатаем сообщение с пометкой «в окне».
            print(f"{layer_tag}[в окне] {role}: {msg['content']}")
        # Для sliding-window вытесненные помечаем «вытеснено».
        elif args.context == "sliding-window":
            # Печатаем сообщение с пометкой «вытеснено».
            print(f"{layer_tag}[вытеснено] {role}: {msg['content']}")
        # Для compression/leveling вне окна — «вне окна» (ещё не сжаты).
        else:
            # Печатаем сообщение с пометкой «вне окна».
            print(f"{layer_tag}[вне окна] {role}: {msg['content']}")

    # После списка печатаем пустую строку для читаемости.
    print()


# Обработчик /window: размер окна (только для sliding-window).
def cmd_window(full_history):
    # Считаем, сколько сообщений сейчас находится в окне.
    in_window = min(len(full_history), WINDOW)
    # Печатаем размер окна и количество сообщений в нём.
    print(f"[Окно] {in_window} из {WINDOW} сообщений\n")


# Обработчик /summary: текущее саммари (для compressed и layered).
def cmd_summary(summary):
    # Если саммари пустое — сообщаем об этом.
    if not summary:
        # Печатаем сообщение о том, что саммари ещё не создано.
        print("[Саммари] Саммари пока пусто\n")
    # Иначе показываем текст саммари.
    else:
        # Печатаем текст саммари и пустую строку для читаемости.
        print(f"[Саммари] {summary}\n")


# Обработчик /layers: статистика по слоям (только для layered).
def cmd_layers(full_history):
    # Вычисляем индекс, с которого сообщения находятся в окне.
    in_window_from = max(0, len(full_history) - WINDOW)

    # Перебираем слои в порядке важности: high, mid, low.
    for layer in ("high", "mid", "low"):
        # Считаем сообщения этого слоя во всей активной истории.
        total = sum(1 for msg in full_history if msg["layer"] == layer)

        # Считаем сообщения этого слоя, попадающие в окно запроса.
        in_window = sum(
            1
            for i, msg in enumerate(full_history)
            # Сообщение в окне, если его индекс >= начала окна и слой совпадает.
            if i >= in_window_from and msg["layer"] == layer
        )

        # Печатаем статистику слоя: всего и сколько из них в окне.
        print(f"[Слои] {layer}={total} (в окне: {in_window})")

    # После статистики печатаем пустую строку для читаемости.
    print()


# Обработчик /layer: смена приоритета сообщения пользователя (только layered).
def cmd_layer(full_history, parts):
    # Проверяем, что команда имеет ровно два аргумента.
    if len(parts) != 3 or parts[2] not in LAYER_LABELS:
        # Сообщаем о неправильном формате команды.
        print("[Слой] Формат: /layer <номер> <high|mid|low>\n")
        # Выходим из обработчика.
        return

    # Извлекаем номер сообщения (позиция с конца, 1 — последнее).
    try:
        # Пробуем преобразовать номер в целое число.
        number = int(parts[1])
    # Если номер не число — сообщаем об ошибке формата.
    except ValueError:
        # Сообщаем о неправильном номере.
        print("[Слой] Номер должен быть целым числом\n")
        # Выходим из обработчика.
        return

    # Находим сообщения пользователя в активной истории (с конца).
    user_messages = [msg for msg in full_history if msg["role"] == "user"]

    # Проверяем, что запрошенный номер существует среди сообщений пользователя.
    if number < 1 or number > len(user_messages):
        # Сообщаем, что сообщения с таким номером нет.
        print(f"[Слой] Нет сообщения пользователя с номером {number}\n")
        # Выходим из обработчика.
        return

    # Берём сообщение пользователя по номеру (1 — последнее, 2 — предпоследнее...).
    target = user_messages[-number]

    # Меняем слой выбранного сообщения на указанный в команде.
    target["layer"] = parts[2]

    # Сообщаем пользователю об успешной смене слоя.
    print(f"[Слой] Сообщение изменено: {target['content'][:50]} → {parts[2]}\n")


# Обработчик /compress: принудительное сжатие (для compression и leveling).
def cmd_compress(full_history, summary, archived):
    # Если сжимать нечего — сообщаем и возвращаем исходные значения.
    if not full_history:
        # Печатаем сообщение об отсутствии сообщений для сжатия.
        print("[Сжатие] Нет сообщений для сжатия\n")
        # Возвращаем исходные значения без изменений.
        return full_history, summary, archived

    # Вызываем сжатие через LLM: старое саммари консолидируется с перепиской.
    new_summary = compress_history(full_history, summary)

    # Если сжатие не удалось — не теряем сообщения, оставляем всё как было.
    if new_summary is None:
        # Сообщаем пользователю, что сжатие отложено, сообщения сохранены.
        print("[Сжатие] Не удалось, сообщения сохранены, попробуем в следующий раз\n")
        # Возвращаем исходные значения без изменений.
        return full_history, summary, archived

    # Запоминаем длину нового саммари для уведомления.
    summary_length = len(new_summary)

    # Сохраняем новое саммари в файл (перезапись целиком).
    save_compressed_summary(new_summary)

    # Записываем событие сжатия в лог-файл.
    log_compression(len(full_history), summary_length)

    # Выводим уведомление о сжатии с количеством сообщений и длиной саммари.
    print(
        f"[Сжатие] {len(full_history)} сообщений свёрнуты в саммари "
        f"(длина саммари: {summary_length} символов)\n"
    )

    # Переносим все сжатые сообщения в архив для /history.
    archived.extend(full_history)

    # Очищаем активную историю (сообщения теперь внутри саммари).
    full_history = []

    # Возвращаем обновлённые значения.
    return full_history, new_summary, archived


# 14. Главный цикл -----------------------------------------------------------------

# Заголовок лог-файла: создаём файл с шапкой, если его ещё нет.
if not os.path.exists(LOG_FILE):
    # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        # Пишем заголовок с режимами и размером окна.
        f.write(
            f"# Лог диалога — День 6 (контекст={args.context}, память={args.memory}, окно={WINDOW})\n\n"
        )

# Печатаем выбранный режим работы.
print(f"[Режим] контекст={args.context}, память={args.memory}, окно={WINDOW}")

# --- Инициализация памяти в зависимости от режима ---------------------------------

# Переменная саммари (используется в режимах compressed и layered).
summary = ""

# Архив сообщений, свёрнутых в саммари (для показа в /history).
archived = []

# Для session-памяти: лог не загружается, но сообщаем о найденном файле.
if args.memory == "session":
    # Если лог-файл уже существует — уведомляем о прошлой сессии.
    if os.path.exists(LOG_FILE):
        # Уведомление о найденном прошлом логе (контекст не загружается).
        print(
            f"[Память] Найден прошлый лог: {LOG_FILE} "
            "(в контекст не загружается — сессия новая)"
        )

# Для compressed-памяти: загружаем саммари из файла.
elif args.memory == "compressed":
    # Загружаем саммари прошлой сессии из файла.
    summary = load_compressed_summary()

    # Если саммари найдено и не пустое — сообщаем пользователю о загрузке.
    if summary:
        # Печатаем уведомление с длиной загруженного саммари в символах.
        print(f"[Память] Загружено саммари прошлой сессии ({len(summary)} символов)")

# Для layered-памяти: загружаем саммари + выбранные слои из лога.
elif args.memory == "layered":
    # Загружаем саммари прошлой сессии из файла.
    summary = load_compressed_summary()

    # Если саммари найдено и не пустое — сообщаем пользователю о загрузке.
    if summary:
        # Печатаем уведомление с длиной загруженного саммари в символах.
        print(f"[Память] Загружено саммари прошлой сессии ({len(summary)} символов)")

    # Разбираем значение --load в множество выбранных слоёв.
    if args.load == "all":
        # «Всё» — загружаем все три слоя.
        load_layers_set = {"high", "mid", "low"}
    # «Ничего» — чистая сессия без загрузки памяти.
    elif args.load == "none":
        # Пустое множество — ни один слой не загружается.
        load_layers_set = set()
    # Иначе ожидаем список слоёв через запятую, например «high,mid».
    else:
        # Разбиваем строку по запятым, убираем пробелы, оставляем только известные слои.
        load_layers_set = {
            part.strip() for part in args.load.split(",") if part.strip() in LAYER_LABELS
        }

    # Загружаем из лога сообщения выбранных слоёв.
    loaded_messages = load_layered_history(LOG_FILE, load_layers_set)

    # Если что-то загрузилось — показываем статистику загрузки.
    if loaded_messages:
        # Заполняем активную историю загруженными сообщениями.
        full_history = loaded_messages
        # Считаем количество загруженных сообщений по каждому слою.
        stats = {
            layer: sum(1 for m in loaded_messages if m["layer"] == layer)
            for layer in ("high", "mid", "low")
        }
        # Определяем, какие слои были пропущены (не выбраны флагом --load).
        skipped = [layer for layer in ("high", "mid", "low") if layer not in load_layers_set]
        # Формируем строку пропущенных слоёв для уведомления.
        skipped_text = f" (слой {', '.join(skipped)} пропущен)" if skipped else ""
        # Печатаем статистику загрузки по слоям.
        print(
            f"[Память] Загружено: high={stats['high']}, mid={stats['mid']}, "
            f"low={stats['low']}{skipped_text}"
        )
    # Если загружать было нечего — начинаем с пустой истории.
    else:
        # Пустая активная история — сессия начинается с чистого листа.
        full_history = []

# Для session и compressed память начинается с пустой истории.
if args.memory != "layered":
    # Пустая активная история — сессия начинается с чистого листа.
    full_history = []

# Счётчик сообщений, вытесненных из окна (для уведомления один раз за сдвиг).
evicted_count = 0

# Приветственное сообщение агента при старте.
GREETING = "Привет! Я ваш помощник. Чем могу помочь?"

# Выводим приветствие в консоль.
print(f"Агент: {GREETING}\n")

# Дозаписываем приветствие в лог с отметкой времени.
with open(LOG_FILE, "a", encoding="utf-8") as f:
    # Пишем разделитель с текущими датой и временем.
    f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    # Для layered-памяти пишем приветствие с пометкой слоя low.
    if args.memory == "layered":
        # Пишем приветствие как реплику агента с нейтральным слоем low.
        f.write(f"**Агент** [low]: {GREETING}\n")
    # Для остальных режимов — обычная строка.
    else:
        # Пишем приветствие как реплику агента.
        f.write(f"**Агент:** {GREETING}\n")

# Выводим шапку программы: название, режимы, окно и имя лог-файла.
print(f"🤖 Чат-бот — День 6 (контекст={args.context}, память={args.memory}, окно={WINDOW})")
print(f"Лог: {LOG_FILE}")
print("Введите /exit для завершения.\n")

# Запускаем бесконечный цикл, чтобы пользователь мог отправлять много сообщений.
while True:
    try:
    # Показываем приглашение «Вы:», читаем ввод и удаляем пробелы по краям.
        user_input = input("Вы: ").strip()

        # Обрабатываем команду /history — доступна во всех режимах.
        if user_input == "/history":
            # Вызываем обработчик истории.
            cmd_history(full_history, archived, summary)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /window — только для sliding-window.
        if user_input == "/window":
            # Проверяем доступность команды в текущем режиме.
            if args.context == "sliding-window":
                # Вызываем обработчик окна.
                cmd_window(full_history)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /window недоступна в режиме context={args.context}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /summary — для compressed и layered.
        if user_input == "/summary":
            # Проверяем доступность команды в текущем режиме.
            if args.memory in ("compressed", "layered"):
                # Вызываем обработчик саммари.
                cmd_summary(summary)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /summary недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /compress — для compressed и layered.
        if user_input == "/compress":
            # Проверяем доступность команды в текущем режиме.
            if args.memory in ("compressed", "layered"):
                # Вызываем обработчик сжатия и обновляем состояние.
                full_history, summary, archived = cmd_compress(full_history, summary, archived)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /compress недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /layers — только для layered.
        if user_input == "/layers":
            # Проверяем доступность команды в текущем режиме.
            if args.memory == "layered":
                # Вызываем обработчик статистики слоёв.
                cmd_layers(full_history)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /layers недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /layer — только для layered.
        if user_input.startswith("/layer "):
            # Проверяем доступность команды в текущем режиме.
            if args.memory == "layered":
                # Разбиваем команду на части и вызываем обработчик.
                cmd_layer(full_history, user_input.split())
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /layer недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /clear — доступна во всех режимах.
        if user_input == "/clear":
            # Очищаем активную историю (лог-файл при этом сохраняется).
            full_history = []
            # Очищаем архив свёрнутых сообщений.
            archived = []
            # Для compressed и layered сбрасываем и саммари.
            if args.memory in ("compressed", "layered"):
                # Сбрасываем саммари в памяти.
                summary = ""
            # Сообщаем пользователю об очистке.
            print("[Контекст] Контекст очищен (лог-файл сохранён)\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /exit — доступна во всех режимах.
        if user_input == "/exit":
            # Для compressed и layered сохраняем саммари в файл.
            if args.memory in ("compressed", "layered") and summary:
                # Сохраняем актуальное саммари в файл.
                save_compressed_summary(summary)
                # Сообщаем пользователю, что саммари сохранено.
                print(f"[Память] Саммари сохранено: {SUMMARY_FILE}")
            # Сообщаем пользователю, что лог сохранён.
            print(f"[Память] Лог сохранён: {LOG_FILE}")
            # Прерываем бесконечный цикл и завершаем программу.
            break

        # Проверяем, осталась ли строка пустой после удаления пробелов.
        if not user_input:
            # Пропускаем текущую итерацию и снова ожидаем пользовательский ввод.
            continue

        # Для layered-памяти определяем слой сообщения пользователя по маркерам.
        if args.memory == "layered":
            # Автоматически определяем слой сообщения.
            layer = detect_layer(user_input)
        # Для остальных режимов слой не используется.
        else:
            # Слой не определён (не используется в этом режиме).
            layer = None

        # Добавляем новое сообщение пользователя в активную историю.
        if args.memory == "layered":
            # Для layered добавляем сообщение со слоем и временем.
            full_history.append(
                {
                    # Роль сообщения — пользователь.
                    "role": "user",
                    # Текст сообщения.
                    "content": user_input,
                    # Определённый слой приоритета.
                    "layer": layer,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        # Для session и compressed — без слоя.
        else:
            # Добавляем сообщение с ролью, текстом и временем.
            full_history.append(
                {
                    # Роль сообщения — пользователь.
                    "role": "user",
                    # Текст сообщения.
                    "content": user_input,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        # Формируем messages для запроса через диспетчер стратегий контекста.
        messages = build_messages(args.context, full_history, summary, WINDOW)

        # Отправляем запрос к LLM и получаем ответ (или None при ошибке).
        bot_response = ask_llm(messages)

        # Если ответа нет (ошибка API) — удаляем сообщение пользователя и продолжаем.
        if bot_response is None:
            # Удаляем последнее сообщение пользователя, на которое модель не ответила.
            full_history.pop()
            # Переходим к следующей итерации цикла.
            continue

        # Добавляем ответ модели в активную историю.
        if args.memory == "layered":
            # Для layered ответ наследует слой сообщения пользователя.
            full_history.append(
                {
                    # Роль сообщения — ассистент.
                    "role": "assistant",
                    # Текст ответа.
                    "content": bot_response,
                    # Слой наследуется от сообщения пользователя.
                    "layer": layer,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        # Для session и compressed — без слоя.
        else:
            # Добавляем ответ с ролью, текстом и временем.
            full_history.append(
                {
                    # Роль сообщения — ассистент.
                    "role": "assistant",
                    # Текст ответа.
                    "content": bot_response,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        # Выводим ответ модели и пустую строку для читаемости.
        print(f"Агент: {bot_response}\n")

        # Дозаписываем обмен (пользователь и агент) в лог-файл.
        append_log(full_history[-2], layered=(args.memory == "layered"))
        # Дозаписываем ответ агента в лог-файл.
        append_log(full_history[-1], layered=(args.memory == "layered"))

        # --- Пост-обработка: вытеснение (A) или автосжатие (B и C) ---------------------

        # Для sliding-window проверяем появление новых вытесненных сообщений.
        if args.context == "sliding-window":
            # Считаем, сколько сообщений сейчас вне окна.
            new_evicted = max(0, len(full_history) - WINDOW)

            # Если количество вытесненных увеличилось — окно сдвинулось.
            if new_evicted > evicted_count:
                # Выводим ненавязчивое уведомление о вытеснении.
                print(
                    f"[Контекст] Сообщение вышло из окна "
                    f"(осталось {WINDOW} последних)\n"
                )

            # Запоминаем новое количество вытесненных сообщений.
            evicted_count = new_evicted

        # Для compression и leveling проверяем порог автосжатия.
        else:
            # Считаем сообщения вне окна оперативного слоя.
            outside_window = len(full_history) - WINDOW

            # Если вне окна накопилось >= порога — запускаем автоматическое сжатие.
            if outside_window >= COMPRESS_THRESHOLD:
                # Сжимаем все сообщения вне окна (старые), оставляя окно нетронутым.
                old_messages = full_history[:-WINDOW]

                # Вызываем сжатие через LLM: старое саммари консолидируется.
                new_summary = compress_history(old_messages, summary)

                # Если сжатие удалось — обновляем состояние.
                if new_summary is not None:
                    # Запоминаем длину нового саммари для уведомления.
                    summary_length = len(new_summary)

                    # Сохраняем новое саммари в файл (перезапись целиком).
                    save_compressed_summary(new_summary)

                    # Записываем событие сжатия в лог-файл.
                    log_compression(len(old_messages), summary_length)

                    # Выводим уведомление о сжатии.
                    print(
                        f"[Сжатие] {len(old_messages)} сообщений свёрнуты в саммари "
                        f"(длина саммари: {summary_length} символов)\n"
                    )

                    # Обновляем саммари в памяти.
                    summary = new_summary

                    # Переносим сжатые сообщения в архив для /history.
                    archived.extend(old_messages)

                    # Удаляем сжатые сообщения из активной истории (они в саммари).
                    del full_history[:len(old_messages)]
                # Если сжатие не удалось — не теряем сообщения.
                else:
                    # Сообщаем, что сжатие отложено, сообщения сохранены.
                    print("[Сжатие] Не удалось, сообщения сохранены, попробуем в следующий раз\n")

    # Перехватываем Ctrl+D (EOF) — корректный выход без ошибки.
    except EOFError:
        # Сообщаем о завершении и прерываем цикл.
        print("\n[Выход] Ввод завершён (EOF)")
        break

    # Перехватываем Ctrl+C — корректный выход без traceback.
    except KeyboardInterrupt:
        # Сообщаем о прерывании и прерываем цикл.
        print("\n[Выход] Прервано пользователем")
        break

    # Перехватываем любую другую непредвиденную ошибку в теле цикла.
    except Exception as error:
        # Записываем полный стек ошибки в журнал ошибок.
        log_error("Ошибка в главном цикле", error)
        # Просим нажать Enter, чтобы окно не закрылось мгновенно.
        input("Нажмите Enter для продолжения...")

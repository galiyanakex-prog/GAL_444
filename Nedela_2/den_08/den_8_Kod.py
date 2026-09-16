# ============================================================================
# День 8 — den_8_Kod.py (подсчёт токенов и стоимости диалога, класс Agent)
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Модель не хранит состояние: каждый обмен мы заново отправляем ей ВЕСЬ диалог
# (system + история), поэтому «токены текущего запроса» растут с каждым
# сообщением, а суммарный расход растёт как 1+2+3+…+N. Токены — это реальные
# деньги (Step-3.5-Flash: входящие 11 ₽/1M, исходящие 33 ₽/1M), а контекстное
# окно (262K токенов) — конечный ресурс: когда диалог в него не влезает, запрос
# падает ошибкой API. День 8 делает эти три вещи видимыми и измеримыми:
#   1) токены текущего запроса  — из usage.prompt_tokens ответа API;
#   2) токены всей истории      — накопительная сумма usage за сессию;
#   3) токены ответа модели     — из usage.completion_tokens;
# плюс стоимость в рублях, CSV-журнал роста расхода, контроль лимита контекста
# (/tokens, /cost, /scenario). Локальная оценка токенов (≈chars/3–4) служит для
# прогноза ДО отправки и для проверки лимита; авторитет — usage из ответа API.
# Донор (агент с JSON-персистентностью) читал из ответа API только choices, блок
# usage выбрасывался — именно его День 8 и начинает считать (Суть_N2.txt, §2.3:
# «один диалог с кодом 8 000–10 000 токенов, ~100 сообщений → достижение лимита»).
#
# Запуск:
#   python den_08/den_8_Kod.py --context sliding-window --memory session
#   python den_08/den_8_Kod.py --context compression --memory compressed
#   python den_08/den_8_Kod.py --context leveling --memory layered
#   python den_08/den_8_Kod.py --max-context-tokens 60   # демонстрация переполнения
# ============================================================================

# 1. Импорты: os, sys, json, argparse, datetime, requests, dotenv --------------

# Импортируем модуль os для чтения переменных окружения и проверки файлов.
import os
import csv

# Импортируем модуль sys для настройки кодировки стандартного ввода.
import sys

# Импортируем модуль json для сохранения и загрузки контекста агента (День 8).
import json

# Импортируем readline для редактирования ввода: стрелки (история/перемещение
# курсора), Home/End/Delete. Без него input() вставляет escape-последовательности
# стрелок («[A», «[D»...) прямо в текст сообщения.
try:
    # Работает на Linux (GNU readline); обёрнуто в try — чтобы скрипт не падал
    # на платформах без readline (например, Windows).
    import readline
# Если readline недоступен — ввод просто без редактирования, как раньше.
except ImportError:
    pass

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
# errors="replace" — вместо падения (UnicodeDecodeError) при вводе в другой
# кодировке (например, CP1251 из ярлыка/терминала) «битые» байты заменяются
# на символ-заглушку, и цикл продолжается.
sys.stdin.reconfigure(encoding='utf-8', errors='replace')

# Настраиваем кодировку stdout: при выводе в перенаправленный не-UTF-8 поток
# «непечатаемые» символы заменяются заглушкой вместо UnicodeEncodeError.
sys.stdout.reconfigure(errors='replace')

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
    description="Чат-бот Дня 8: подсчёт токенов и стоимости диалога (токены запроса, "
    "истории и ответа), три техники контекста и три типа памяти через флаги."
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

# Флаг --log: имя лог-файла (по умолчанию Den_8_log.md).
parser.add_argument(
    "--log",
    type=str,
    default="Den_8_log.md",
    help="Имя лог-файла.",
)

# Флаг --context-file: путь к JSON-файлу контекста (День 8).
parser.add_argument(
    "--context-file",
    type=str,
    default="den_8_context.json",
    help="JSON-файл контекста для сохранения/загрузки (по умолчанию den_8_context.json).",
)

# Флаг --fresh: начать новую сессию, игнорируя прошлый JSON-снимок (День 8).
# Легальный способ получить чистую сессию, не удаляя файл руками: снимок на диске
# остаётся нетронутым до ближайшего сохранения (/exit, Ctrl+C, Ctrl+D, /save).
parser.add_argument(
    "--fresh",
    action="store_true",
    help="Начать новую сессию: не загружать прошлый JSON-снимок (перезаписать его при сохранении).",
)

# Флаг --max-context-tokens: искусственный лимит контекстного окна (День 8).
# Реальное окно модели — 262K токенов, «сжигать» его живыми запросами незачем:
# лимит ставят маленьким (например, 60), чтобы показать переполнение дёшево.
parser.add_argument(
    "--max-context-tokens",
    type=int,
    default=None,
    help="Лимит токенов контекста для проверки перед отправкой (по умолчанию окно модели).",
)

# Флаг --max-tokens: верхний предел длины ответа модели (День 8).
# Уходит прямо в тело запроса API; позволяет дёшево резать исходящие токены.
parser.add_argument(
    "--max-tokens",
    type=int,
    default=None,
    help="Максимум токенов в ответе модели (по умолчанию без лимита).",
)

# Флаг --token-log: имя CSV-журнала роста токенов и стоимости (День 8).
parser.add_argument(
    "--token-log",
    type=str,
    default="den_8_tokens.csv",
    help="CSV-журнал токенов и стоимости по каждому обмену (по умолчанию den_8_tokens.csv).",
)

# Флаг --price-in: цена миллиона входящих токенов в рублях (День 8).
parser.add_argument(
    "--price-in",
    type=float,
    default=None,
    help="Цена 1M входящих токенов в рублях (по умолчанию из Step-3.5-Flash_params.md).",
)

# Флаг --price-out: цена миллиона исходящих токенов в рублях (День 8).
parser.add_argument(
    "--price-out",
    type=float,
    default=None,
    help="Цена 1M исходящих токенов в рублях (по умолчанию из Step-3.5-Flash_params.md).",
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

# Проверка размера окна: ноль или отрицательное число сделали бы окно пустым.
if WINDOW < 1:
    # Останавливаем программу с понятным объяснением.
    raise RuntimeError("Размер окна (--window / --keep) должен быть больше нуля.")

# Каталог этого скрипта: все артефакты (лог, саммари, JSON контекста, журнал
# ошибок) пишутся рядом с кодом, а не туда, откуда запущен скрипт — иначе .sh
# с cd разложили бы их по корню AI_9.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Имя лог-файла из флага --log (если путь относительный — фиксируем его за den_08).
if os.path.isabs(args.log):
    LOG_FILE = args.log
else:
    LOG_FILE = os.path.join(BASE_DIR, args.log)

# Имя файла саммари (для compressed и layered памяти) — производное от ПОЛНОГО
# пути лога, чтобы саммари жило рядом со своим логом: при --log /tmp/x.md и
# саммари будет в /tmp, а не в каталоге скрипта. Разные логи — разные саммари.
SUMMARY_FILE = os.path.splitext(LOG_FILE)[0] + ".summary.md"

# Путь к JSON-файлу контекста (День 8): относительный путь фиксируется за
# каталогом скрипта, абсолютный — используется как есть.
if os.path.isabs(args.context_file):
    CONTEXT_FILE = args.context_file
else:
    CONTEXT_FILE = os.path.join(BASE_DIR, args.context_file)

# Путь к CSV-журналу токенов (День 8): та же схема — относительный путь
# фиксируется за каталогом скрипта, абсолютный используется как есть.
if os.path.isabs(args.token_log):
    TOKEN_LOG = args.token_log
else:
    TOKEN_LOG = os.path.join(BASE_DIR, args.token_log)

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
ERROR_LOG = os.path.join(BASE_DIR, "den_8_error.log")

# Версия формата JSON-снимка контекста (День 8): при изменении структуры
# в будущем старые снимки можно отличить по номеру версии. В версии 2 появился
# блок usage (накопленные токены и стоимость), снимки версии 1 грузаются без падения.
CONTEXT_VERSION = 2

# Минимальная версия снимка, которую умеем мигрировать на текущую.
# Снимки старее не поднимаем (структура неизвестна), новее — отказываемся честно.
MIN_MIGRATABLE_VERSION = 1

# Цена 1M входящих токенов в рублях (Step-3.5-Flash_params.md).
PRICE_IN_PER_M = 11.0

# Цена 1M исходящих токенов в рублях — втрое дороже входящих (там же).
PRICE_OUT_PER_M = 33.0

# Реальное контекстное окно модели в токенах (Step-3.5-Flash_params.md: 262K).
# Нужно как значение по умолчанию: «сжигать» его живыми запросами незачем.
MODEL_CONTEXT_LIMIT = 262144

# Признаки того, что API сам отказал из-за переполнения контекста (День 8).
# Ищем подстроки в тексте ошибки без регистра: у разных шлюзов формулировки свои,
# поэтому список намеренно шире одного канонического кода.
CONTEXT_OVERFLOW_MARKERS = (
    "context_length_exceeded",
    "context length",
    "maximum context",
    "too many tokens",
    "input is too long",
    "prompt is too long",
    "превышен",
    "слишком длин",
)

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

# Порядок слоёв: от самого важного к самому второстепенному.
LAYER_ORDER = ("high", "mid", "low")

# Промпты сжатия по слоям (layered-память): чем выше слой, тем бережнее сжатие.
# Идея leveled-memory: факты высокого слоя не имеют права теряться при сжатии,
# тогда как болтовня низкого слоя сворачивается максимально агрессивно.
COMPRESS_PROMPTS = {
    # Высокий слой: ключевые факты — сохраняем дословно, ничего не опускаем.
    "high": (
        "Ты сохраняешь ключевые факты о пользователе. Перечисли ВСЕ факты, имена, "
        "даты, цифры и договорённости из сообщений списком. Ничего не опускай и не "
        "перефразируй смысл. Только список, без приветствий и комментариев."
    ),
    # Средний слой: задачи и планы — сохраняем все, формулировки короче.
    "mid": (
        "Ты сохраняешь задачи и планы. Перечисли ВСЕ задачи, сроки и договорённости "
        "списком, кратко, но без потерь. Только список, без приветствий и комментариев."
    ),
    # Низкий слой: обычная переписка — сжимаем максимально сильно.
    "low": (
        "Ты сжимаешь переписку. Сделай предельно краткое саммари сути в 1-3 "
        "предложениях. Только саммари, без приветствий и комментариев."
    ),
}

# Сколько сообщений высокого/среднего слоя вне окна дополнительно попадает в
# запрос leveling (защита от бесконечного роста приоритетного блока).
PRIORITY_CAP = 6

# Известные внутренние имена стратегий контекста: нужны для проверки значений,
# прочитанных из JSON-снимка (мусор в снимке иначе уронит сборку запроса).
KNOWN_STRATEGIES = ("sliding_window", "history_compression", "context_leveling")

# Известные типы памяти: тоже проверяются при загрузке JSON-снимка.
KNOWN_MEMORY_TYPES = ("session", "compressed", "layered")

# Список известных slash-команд: нужен, чтобы нераспознанная строка, начинающаяся
# с «/», не уходила в LLM как обычный текст (лишние вызовы API, мусор в истории).
KNOWN_COMMANDS = (
    "/history",
    "/window",
    "/summary",
    "/compress",
    "/layers",
    "/layer",
    "/save",
    "/load",
    "/tokens",
    "/cost",
    "/scenario",
    "/clear",
    "/help",
    "/exit",
)


# Эффективные цены за 1M токенов: флаг переопределяет справочное значение,
# если пользователь его задал (иначе берём тариф из Step-3.5-Flash_params.md).
if args.price_in is not None:
    PRICE_IN_PER_M = args.price_in
if args.price_out is not None:
    PRICE_OUT_PER_M = args.price_out

# Эффективный лимит контекста: флаг переопределяет реальное окно модели.
if args.max_context_tokens is not None:
    MAX_CONTEXT_TOKENS = args.max_context_tokens
else:
    MAX_CONTEXT_TOKENS = MODEL_CONTEXT_LIMIT

# Валидация лимита контекста: ноль или отрицательное число запретили бы любой запрос.
if MAX_CONTEXT_TOKENS < 1:
    raise RuntimeError("Значение --max-context-tokens должно быть больше нуля.")

# Валидация лимита ответа: 0 или меньше означали бы «не генерировать ничего».
if args.max_tokens is not None and args.max_tokens < 1:
    raise RuntimeError("Значение --max-tokens должно быть больше нуля.")


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


# Функция дозаписи строки обмена в CSV-журнал токенов (День 8).
# Заголовок пишется один раз — только если файла ещё нет. Любая ошибка записи
# (битый путь, права, диск) НЕ роняет чат: печатаем предупреждение один раз.
def append_token_log(agent):
    # Начинаем блок защиты: сбой журнала не должен прерывать диалог.
    try:
        # Проверяем существование файла, чтобы решить, нужен ли заголовок.
        is_new = not os.path.exists(TOKEN_LOG)

        # Открываем журнал в режиме дозаписи; newline="" — требование модуля csv.
        with open(TOKEN_LOG, "a", newline="", encoding="utf-8") as f:
            # Создаём писателя CSV.
            writer = csv.writer(f)

            # Для нового файла сначала пишем строку заголовка.
            if is_new:
                # Колонки: номер обмена, время, режим, окно, три счётчика токенов,
                # стоимость обмена и накопительная стоимость сессии.
                writer.writerow([
                    "exchange", "timestamp", "context_strategy", "window",
                    "prompt_tokens", "completion_tokens", "total_tokens",
                    "history_tokens", "cost_rubles", "cost_total_rubles",
                ])

            # Стоимость обмена может быть None (usage не пришёл) — тогда пустая ячейка.
            cost = agent.cost_rubles()

            # Форматируем стоимость с 6 знаками: суммы порядка 0.001–0.01 ₽ обычное дело.
            cost_str = "" if cost is None else f"{cost:.6f}"

            # То же для накопительной стоимости сессии.
            total_str = f"{agent.cost_total():.6f}"

            # Пишем строку текущего обмена.
            writer.writerow([
                agent.exchanges,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                agent.context_strategy,
                agent.window,
                agent.last_usage.get("prompt_tokens", ""),
                agent.last_usage.get("completion_tokens", ""),
                agent.last_usage.get("total_tokens", ""),
                agent.usage_total["total_tokens"],
                cost_str,
                total_str,
            ])

    # Перехватываем любую ошибку записи (OSError и прочие неожиданные).
    except Exception as error:
        # Предупреждаем только один раз за сессию — иначе замусорим каждый обмен.
        if not agent.token_log_warned:
            # Помечаем, что предупреждение уже показано.
            agent.token_log_warned = True
            # Печатаем понятное сообщение с путём, который не записался.
            print(f"[Журнал] Не удалось записать CSV ({TOKEN_LOG}): {error}")


# 5. Токен-функции: локальная оценка токенов (День 8) ---------------------------


# Переменная-кэш кодировки tiktoken: None — ещё не пробовали импортировать,
# False — tiktoken недоступен (больше не пробуем), объект — кодировка готова.
# tiktoken в venv недели отсутствует, поэтому он ОПЦИОНАЛЕН: без него работает
# эвристика, а зависимость от внешнего пакета не появляется (AI_9_main.md:
# программы не должны зависеть от ресурсов за пределами Nedela_*).
_TIKTOKEN_ENCODING = None


# Функция ленивой загрузки кодировки tiktoken (вызывается один раз на оценку).
def get_token_encoding():
    # Если мы уже пробовали импортировать tiktoken — возвращаем результат сразу.
    if _TIKTOKEN_ENCODING is not None:
        # Возвращаем кэш: False (нет пакета) или объект кодировки.
        return _TIKTOKEN_ENCODING

    # Начинаем блок попытки импорта и создания кодировки.
    try:
        # Импортируем модуль tiktoken локально: при отсутствии ImportError
        # перехватывается здесь и не мешает работе всей программы.
        import tiktoken

        # Берём кодировку o200k_base (актуальная для новых моделей),
        # при её отсутствии откатываемся на cl100k_base.
        try:
            # Пробуем современную кодировку.
            encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            # Старая кодировка — тоже даёт разумную оценку.
            encoding = tiktoken.get_encoding("cl100k_base")

        # Кэшируем успешный результат (записываем, а не читаем).
        globals()["_TIKTOKEN_ENCODING"] = encoding
    # Если модуля нет или он не смог инициализировать кодировку — работаем на эвристике.
    except Exception:
        # Кэшируем отказ, чтобы не повторять дорогую попытку на каждом сообщении.
        globals()["_TIKTOKEN_ENCODING"] = False

    # Возвращаем актуальное состояние кодировки.
    return _TIKTOKEN_ENCODING


# Функция локальной оценки числа токенов в тексте (ДО отправки запроса).
# Авторитетная цифра — usage из ответа API; эта оценка нужна, чтобы предсказать
# расход и проверить лимит контекста заранее.
def estimate_tokens(text):
    # Пустой текст не стоит ни одного токена.
    if not text:
        # Возвращаем ноль.
        return 0

    # Пробуем получить точную кодировку tiktoken.
    encoding = get_token_encoding()

    # Если кодировка доступна — считаем точно.
    if encoding:
        # len от списка токенов = число токенов по кодировке модели.
        return len(encoding.encode(text))

    # Эвристика без внешних зависимостей: считаем символы по алфавитам.
    # Кириллица в современных BPE-токенизаторах «дороже»: примерно 1 токен
    # на 3 символа; латиница и прочие — примерно 1 токен на 4 символа.
    cyrillic = 0

    # Счётчик прочих символов (латиница, цифры, знаки, пробелы).
    other = 0

    # Перебираем символы текста и относим их к нужной группе.
    for char in text:
        # Проверяем принадлежность символа к кириллице (оба регистра).
        if "а" <= char <= "я" or "А" <= char <= "Я" or char == "ё" or char == "Ё":
            # Увеличиваем счётчик кириллических символов.
            cyrillic += 1
        # Все остальные символы идут в общую корзину.
        else:
            # Увеличиваем счётчик прочих символов.
            other += 1

    # Суммируем оценки по группам и округляем вверх (берём с запасом).
    estimated = -(-cyrillic // 3) + -(-other // 4)

    # Нулевая оценка невозможна для непустого текста: минимум один токен.
    return max(1, estimated)


# Функция локальной оценки токенов всего запроса (списка сообщений).
# Служебная разметка сообщения (role, рамки) добавляет несколько токенов сверху —
# их тоже учитываем, иначе оценка систематически занижалась бы.
PER_MESSAGE_OVERHEAD_TOKENS = 4


def estimate_messages_tokens(messages):
    # Сумма токенов содержимого всех сообщений запроса.
    total = 0

    # Перебираем сообщения в формате API (role + content).
    for message in messages:
        # Берём текст сообщения (пустого содержимого в наших сборщиках нет,
        # но .get страхует от неожиданной структуры).
        content = message.get("content", "")

        # Прибавляем оценку текста и служебные токены сообщения.
        total += estimate_tokens(content) + PER_MESSAGE_OVERHEAD_TOKENS

    # Возвращаем итоговую оценку запроса в токенах.
    return total


# 6. detect_layer(text) — автоопределение слоя (функция уровня модуля, для C) ---


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


# 7. class Agent — один класс, стратегии внутри ---------------------------------


# Класс Agent — отдельная сущность, которая «знает» всё о диалоге:
# режимы контекста и памяти, историю, саммари, слои и то, как обращаться к LLM.
# Наружу (в CLI-цикл) отдаёт только ответы и сведения о контексте — CLI работает
# исключительно через публичные методы.
class Agent:
    # Создаём агента: роль, стратегии контекста и памяти, размеры окон.
    def __init__(self, system_prompt: str, context_strategy: str = "sliding_window",
                 memory_type: str = "session", window: int = 10, keep: int = 6,
                 load_layers: str = "all", max_context_tokens: int = None,
                 max_tokens: int = None, price_in_per_m: float = None,
                 price_out_per_m: float = None):
        """system_prompt — роль агента;
        context_strategy — техника управления контекстом:
            "sliding_window", "history_compression", "context_leveling";
        memory_type — тип памяти:
            "session", "compressed", "layered";
        max_context_tokens — лимит контекста для проверки перед отправкой (День 8);
        max_tokens — лимит длины ответа модели (День 8);
        price_in_per_m / price_out_per_m — цены 1M токенов в рублях (День 8)."""
        # Приводим имена флагов CLI к внутренним именам стратегий.
        strategy_map = {
            "sliding-window": "sliding_window",
            "compression": "history_compression",
            "leveling": "context_leveling",
        }

        # Стратегический слой: роль агента (не меняется в ходе сессии).
        self.system_prompt = system_prompt

        # Стратегия контекста (внутреннее имя).
        self.context_strategy = strategy_map.get(context_strategy, context_strategy)

        # Тип памяти (совпадает с именем флага).
        self.memory_type = memory_type

        # Размер окна: для sliding_window — window, для остальных — keep.
        self.window = window if self.context_strategy == "sliding_window" else keep

        # Режим загрузки слоёв из лога (используется только layered-памятью).
        self.load_layers = load_layers

        # Полная история диалога. Формат записи зависит от памяти:
        # session/compressed: {"role", "content", "timestamp"};
        # layered: {"role", "content", "layer", "timestamp"}.
        self.full_history = []

        # Архив сообщений, уже свёрнутых в саммари (для показа в /history).
        self.archived = []

        # Саммари старых сообщений: единая строка для compressed-памяти (слоёв
        # там нет). Для layered-памяти используется summary_by_layer ниже.
        self.summary = ""

        # Послойные саммари (только layered): у каждого слоя своё саммари,
        # сжатое своим промптом — high почти без потерь, low максимально сильно.
        self.summary_by_layer = {layer: "" for layer in LAYER_ORDER}

        # Счётчик вытесненных из окна сообщений (для уведомления в sliding_window).
        self.evicted_total = 0

        # Счётчик уже записанных в лог сообщений: /save и /exit дозаписывают
        # только то, чего ещё нет в файле, не плодя дублей.
        self.saved_count = 0

        # --- День 8: токен-учёт -------------------------------------------------
        # usage последнего успешного обмена: {"prompt_tokens", "completion_tokens",
        # "total_tokens"}; пустой словарь — значит ответа с usage ещё не было.
        self.last_usage = {}

        # Накопительные итоги сессии — это и есть «токены всей истории диалога»:
        # сумма prompt_tokens и completion_tokens по всем обменам (модель stateless,
        # каждый обмен оплачивается заново).
        self.usage_total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
        }

        # Номер текущего обмена (1, 2, 3…) — для CSV-журнала и вывода в консоль.
        self.exchanges = 0

        # Лимит контекста, проверяемый перед отправкой (из --max-context-tokens);
        # если не задан — реальное окно модели из справочника.
        self.max_context_tokens = max_context_tokens if max_context_tokens is not None else MAX_CONTEXT_TOKENS

        # Лимит длины ответа (из --max-tokens); None — лимита нет, API сам решает.
        self.max_tokens = max_tokens

        # Цены за 1M токенов для расчёта стоимости: флаг либо справочник.
        self.price_in_per_m = price_in_per_m if price_in_per_m is not None else PRICE_IN_PER_M
        self.price_out_per_m = price_out_per_m if price_out_per_m is not None else PRICE_OUT_PER_M

        # Флаг «ошибка записи CSV уже показана»: предупреждаем один раз, а не каждый обмен.
        self.token_log_warned = False

    # Внутренний метод: учёт блока usage из ответа API (День 8).
    # Вызывается сразу после разбора JSON — до проверки choices, потому что токены
    # запроса уже списаны независимо от того, понравился нам формат ответа или нет.
    # is_main=False — это служебный запрос (автосжатие саммари): его токены честно
    # попадают в накопительную сумму, но НЕ перетягивают на себя «токены текущего
    # запроса», иначе /tokens показал бы бы стоимость сжатия вместо ответа пользователю.
    def _record_usage(self, usage, is_main=True):
        # Оставляем только числовые поля, которые умеем считать; прочее (например,
        # reasoning-токены у некоторых API) игнорируем, чтобы не считать вслепую.
        normalized = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

        # Если API вовсе не прислал usage — помечаем обмен как «без usage»:
        # last_usage остаётся пустым, и счётчики честно скажут «нет данных».
        if not usage:
            # Пустой словарь — сигнал «авторитетных токенов нет» (только для основного).
            if is_main:
                self.last_usage = {}
            # Пустой usage не считаем обменом с данными.
            return

        # Если total_tokens не пришёл, считаем его суммой частей.
        if not normalized["total_tokens"]:
            normalized["total_tokens"] = (
                normalized["prompt_tokens"] + normalized["completion_tokens"]
            )

        # Сохраняем usage последнего ОСНОВНОГО обмена (для /tokens и /cost).
        if is_main:
            self.last_usage = normalized

        # Накопительная сумма по сессии — «токены всей истории диалога».
        # Сюда идут и служебные запросы сжатия: они тоже стоят денег.
        self.usage_total["prompt_tokens"] += normalized["prompt_tokens"]
        self.usage_total["completion_tokens"] += normalized["completion_tokens"]
        self.usage_total["total_tokens"] += normalized["total_tokens"]

        # Число обменов, по которым пришли реальные данные usage (только основные).
        if is_main:
            self.usage_total["requests"] += 1

    # Публичный метод (День 8): токены ПОСЛЕДНЕГО запроса — то есть «токены текущего
    # запроса» из задания. Модель stateless, поэтому это весь отправленный контекст,
    # а не только набранная только что строка. None — если usage не приходил.
    def tokens_request(self):
        # Возвращаем входящие токены последнего обмена (или None).
        return self.last_usage.get("prompt_tokens")

    # Публичный метод (День 8): токены ВСЕЙ ИСТОРИИ диалога — накопительная сумма
    # входящих и исходящих по всем обменам сессии (с учётом загруженного снимка).
    def tokens_history(self):
        # Суммарный total_tokens с начала сессии.
        return self.usage_total["total_tokens"]

    # Публичный метод (День 8): токены ПОСЛЕДНЕГО ответа модели. None — если usage
    # не приходил (например, API его не отдаёт).
    def tokens_response(self):
        # Возвращаем исходящие токены последнего обмена (или None).
        return self.last_usage.get("completion_tokens")

    # Публичный метод (День 8): стоимость последнего обмена в рублях по тарифу
    # (входящие и исходящие тарифицируются по-разному). None — если usage не приходил.
    def cost_rubles(self):
        # Если авторитетных токенов нет — стоимость неизвестна, не выдумываем её.
        if not self.last_usage:
            # Возвращаем None.
            return None

        # Считаем: (токены / 1M) * цена за 1M по каждой стороне отдельно.
        return (
            self.last_usage["prompt_tokens"] * self.price_in_per_m
            + self.last_usage["completion_tokens"] * self.price_out_per_m
        ) / 1_000_000

    # Публичный метод (День 8): стоимость всей сессии в рублях — «прайс» накопленного
    # контекста: каждый обмен оплачивался заново, поэтому сумма честная.
    def cost_total(self):
        # Та же формула, но по накопительным итогам сессии.
        return (
            self.usage_total["prompt_tokens"] * self.price_in_per_m
            + self.usage_total["completion_tokens"] * self.price_out_per_m
        ) / 1_000_000

    # Внутренний метод: один запрос к LLM с повтором при HTTP 429.
    # Снаружи не вызывается — CLI работает только с публичными методами.
    # is_main=False помечает служебный запрос (сжатие саммари) для токен-учёта.
    def _ask_llm(self, messages, is_main=True):
        # Формируем тело запроса: модель и список сообщений.
        data = {
            "model": MODEL,
            "messages": messages,
        }

        # День 8: если задан --max-tokens, передаём его API — это верхний предел
        # генерации, самый дешёвый способ урезать дорогие исходящие токены.
        if self.max_tokens is not None:
            # Кладём лимит длины ответа в тело запроса.
            data["max_tokens"] = self.max_tokens

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

                # День 8: считываем блок usage ДО проверки choices — токены за этот
                # запрос уже списаны, значит учесть их обязаны, даже если формат
                # ответа нас не устроил. Отсутствие usage не считается ошибкой:
                # часть API его не отдаёт (тогда остаёмся на локальной оценке).
                self._record_usage(result.get("usage") or {}, is_main=is_main)

                # Проверяем, что в ответе есть варианты ответа (choices).
                if "choices" not in result or not result["choices"]:
                    # Сообщаем о неожиданном формате ответа.
                    print("[API] Неожиданный формат ответа: нет choices.\n")
                    # Возвращаем None — ответа нет.
                    return None

                # Достаём текст первого варианта ответа модели.
                return result["choices"][0]["message"]["content"] or ""

            # Перехватываем ошибку HTTP (кроме уже обработанной 429).
            except requests.exceptions.HTTPError as error:
                # День 8: локальная оценка приблизительная, поэтому лимит не гарантирует
                # отказа от API. Если отказ всё же про длину контекста — говорим об этом
                # прямо: это учебный смысл дня, а не абстрактная «ошибка HTTP».
                error_text = str(error).lower()
                if any(marker in error_text for marker in CONTEXT_OVERFLOW_MARKERS):
                    # Сообщаем причину и способ исправить.
                    print(
                        "[Контекст] API отказал: контекст длиннее окна модели.\n"
                        "Уменьшите контекст: /compress, короче --window/--keep, "
                        "--load high или меньше загружать через /load.\n"
                    )
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

    # Стратегия контекста A: [system] + последние N сообщений.
    def _build_messages_sliding(self) -> list:
        # Начинаем с system-сообщения — роли агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Добавляем последние N сообщений диалога (окно).
        messages.extend(
            # Каждое сообщение превращаем в формат API: только role и content.
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.full_history[-self.window:]
        )

        # Возвращаем готовый список сообщений для запроса.
        return messages

    # Стратегия контекста B: [system] + [саммари, если есть] + последние K.
    def _build_messages_compression(self) -> list:
        # Начинаем с system-сообщения — роли агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Если саммари не пустое — добавляем его вторым system-сообщением.
        if self.summary:
            # Саммари едет сразу после system, чтобы агент «помнил» старый контекст.
            messages.append(
                {"role": "system", "content": f"Саммари более раннего диалога:\n{self.summary}"}
            )

        # Добавляем последние K сообщений диалога (оперативное окно).
        messages.extend(
            # Каждое сообщение превращаем в формат API: только role и content.
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.full_history[-self.window:]
        )

        # Возвращаем готовый список сообщений для запроса.
        return messages

    # Стратегия контекста C: стратегия → инструкции → послойные саммари →
    # приоритетный блок вне окна → окно (строгий порядок).
    def _build_messages_leveling(self) -> list:
        # Стратегический слой, сообщение 1 — роль агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Стратегический слой, сообщение 2 — общие инструкции (не меняются).
        messages.append({"role": "system", "content": RULES_PROMPT})

        # Оперативный слой, часть 1: саммари каждого слоя (если оно непустое).
        # Порядок — по важности: high, mid, low.
        for layer in LAYER_ORDER:
            # Саммари слоя берём из послойного словаря.
            layer_summary = self.summary_by_layer.get(layer, "")
            # Пустое саммари слоя в запрос не отправляем.
            if layer_summary:
                # Подписываем, из какого слоя саммари, чтобы модель понимала приоритет.
                messages.append(
                    {
                        "role": "system",
                        "content": f"Саммари более раннего диалога (слой {layer}):\n{layer_summary}",
                    }
                )

        # Оперативный слой, часть 2: приоритетный блок — сообщения high/mid,
        # которые уже вышли из окна, но ещё не свёрнуты в саммари (порог сжатия
        # не достигнут). Без этого блока важный факт «пропадает» сразу после
        # вытеснения из окна, хотя leveled-память обещает обратное.
        priority_messages = [
            msg
            for msg in self.full_history[:-self.window]
            if msg.get("layer") in ("high", "mid")
        ]
        # Ограничиваем блок сверху (newest-first), чтобы он не разрастался бесконечно.
        for msg in priority_messages[-PRIORITY_CAP:]:
            # Помечаем приоритет прямо в содержании — модель видит вес сообщения.
            messages.append(
                {
                    "role": msg["role"],
                    "content": f"[приоритет {msg['layer']}] {msg['content']}",
                }
            )

        # Оперативный слой, часть 3: последние K сообщений диалога.
        messages.extend(
            # Каждое сообщение превращаем в формат API: только role и content.
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.full_history[-self.window:]
        )

        # Возвращаем готовый список сообщений для запроса.
        return messages

    # Диспетчер стратегий контекста: выбирает сборщик запроса по строке режима.
    # (В реальном проекте здесь был бы Strategy pattern с классами-стратегиями.)
    def _build_messages(self) -> list:
        # Для sliding_window вызываем соответствующую стратегию.
        if self.context_strategy == "sliding_window":
            # Возвращаем запрос, собранный стратегией A.
            return self._build_messages_sliding()

        # Для history_compression вызываем стратегию B.
        if self.context_strategy == "history_compression":
            # Возвращаем запрос, собранный стратегией B.
            return self._build_messages_compression()

        # Для context_leveling вызываем стратегию C.
        if self.context_strategy == "context_leveling":
            # Возвращаем запрос, собранный стратегией C.
            return self._build_messages_leveling()

        # Если режим неизвестен — это ошибка конфигурации, сообщаем и падаем.
        raise ValueError(f"Неизвестный режим контекста: {self.context_strategy}")

    # Общее сжатие ОДНОЙ группы сообщений в саммари (для B и C).
    # summary — прежнее саммари этой же группы (консолидируется, а не заменяется),
    # prompt — промпт сжатия (общий для compressed, послойный для layered).
    # Возвращает текст нового саммари или None, если запрос не удался.
    def _compress_history(self, old_messages, summary, prompt=COMPRESS_PROMPT):
        # Собираем текст переписки из старых сообщений: «Роль: текст» построчно.
        transcript = "\n".join(
            f"{'Пользователь' if msg['role'] == 'user' else 'Агент'}: {msg['content']}"
            for msg in old_messages
        )

        # Формируем сообщения для запроса сжатия: system-промпт + задание.
        compress_messages = [
            # System-сообщение с ролью «сжимателя диалогов».
            {"role": "system", "content": prompt},
            # User-сообщение: старое саммари (для консолидации) + переписка.
            {
                "role": "user",
                "content": (
                    f"Предыдущее саммари:\n{summary or '(нет)'}\n\n"
                    f"Сообщения диалога:\n{transcript}\n\n"
                    "Объедини всё в единое обновлённое саммари."
                ),
            },
        ]

        # Отправляем запрос сжатия в LLM (retry при 429 внутри _ask_llm).
        # is_main=False: это служебный запрос — его токены попадут в накопительную
        # стоимость сессии, но не подменят собой «токены текущего запроса».
        new_summary = self._ask_llm(compress_messages, is_main=False)

        # Возвращаем текст саммари или None, если запрос не удался.
        return new_summary

    # Запуск сжатия вытесненных сообщений с учётом типа памяти.
    # Возвращает словарь {слой: новое саммари}; для compressed ключ — пустая
    # строка (слоёв нет). Если не сжался ни один слой — возвращает None, и
    # вызывающий код оставляет сообщения нетронутыми (повтор на следующем пороге).
    def _run_compression(self, old_messages):
        # compressed-память: одно общее саммари на все сообщения.
        if self.memory_type != "layered":
            # Старое саммари консолидируется с новыми сообщениями.
            new_summary = self._compress_history(old_messages, self.summary)
            # Пустой ключ — «саммари без слоя».
            return {"": new_summary} if new_summary is not None else None

        # layered-память: группируем вытесненные сообщения по слоям и сжимаем
        # каждый слой своим промптом — high почти без потерь, low агрессивно.
        groups = {layer: [] for layer in LAYER_ORDER}
        # Раскладываем сообщения по их слоям.
        for msg in old_messages:
            # Неизвестный слой относим в low: лучше сжать, чем потерять.
            groups[msg.get("layer", "low") if msg.get("layer") in LAYER_ORDER else "low"].append(msg)

        # Результаты сжатия только по непустым слоям.
        results = {}
        # Слои обходим по важности, чтобы high-запрос ушёл первым.
        for layer in LAYER_ORDER:
            # Пустую группу слоя не сжимаем и не трогаем.
            if not groups[layer]:
                # Переходим к следующему слою.
                continue
            # Сжимаем слой, консолидируя его прежнее саммари.
            new_summary = self._compress_history(
                groups[layer], self.summary_by_layer[layer], COMPRESS_PROMPTS[layer]
            )
            # Слой, сжатый успешно, попадает в результат.
            if new_summary is not None:
                # Запоминаем новое саммари слоя.
                results[layer] = new_summary

        # Если не сжался ни один слой — сжатие считается неудачным.
        return results or None

    # Внутреннее применение сжатия: обновляет саммари, переносит сообщения в архив.
    # summaries — результат _run_compression: {слой: текст} либо {"": текст}.
    def _apply_compression(self, old_messages, summaries):
        # layered-память: обновляем только те слои, что сжались успешно.
        if self.memory_type == "layered":
            # Переносим новые саммари по слоям.
            for layer, layer_summary in summaries.items():
                # Заменяем саммари соответствующего слоя.
                self.summary_by_layer[layer] = layer_summary
            # Сжатые сообщения — те, что относятся к успешно сжатым слоям;
            # сообщения неудачных слоёв остаются в истории и сожмутся позже.
            compressed_messages = [
                msg for msg in old_messages
                if (msg.get("layer") if msg.get("layer") in LAYER_ORDER else "low") in summaries
            ]
            # Общая длина саммари всех слоёв — для уведомления и лога.
            summary_length = sum(len(text) for text in self.summary_by_layer.values())
        # compressed-память: одно саммари на всё.
        else:
            # Обновляем саммари агента: старое консолидировано в новом.
            self.summary = summaries[""]
            # Сжаты все переданные сообщения.
            compressed_messages = list(old_messages)
            # Запоминаем длину нового саммари для уведомления и лога.
            summary_length = len(self.summary)

        # Сохраняем новое саммари в файл (перезапись целиком).
        self.save_summary(SUMMARY_FILE)

        # Записываем событие сжатия в лог-файл.
        log_compression(len(compressed_messages), summary_length)

        # Выводим уведомление о сжатии с количеством сообщений и длиной саммари.
        print(
            f"[Сжатие] {len(compressed_messages)} сообщений свёрнуты в саммари "
            f"(длина саммари: {summary_length} символов)\n"
        )

        # Переносим сжатые сообщения в архив (они остаются видны в /history).
        self.archived.extend(compressed_messages)

        # Убираем сжатые сообщения из активной истории (они теперь в саммари).
        # Фильтр по объекту, а не срез: при частичном сжатии по слоям сжатые
        # сообщения могут стоять в истории не сплошным блоком.
        compressed_ids = {id(msg) for msg in compressed_messages}
        # Оставляем только несжатые сообщения.
        self.full_history = [
            msg for msg in self.full_history if id(msg) not in compressed_ids
        ]


    # Главный метод агента: принять сообщение пользователя и вернуть ответ LLM.
    # Диспетчеризация в нужную стратегию контекста происходит внутри.
    # Внутренний метод (День 8): проверка запроса на переполнение контекста ДО отправки.
    # Возвращает None, если запрос проходит, либо текст объяснения для пользователя,
    # если не проходит. Смысл приёма: отказ стоит дешевле, чем попытка — запрос к API
    # с переполненным контекстом и оплачивается, и отклоняется, поэтому считать выгоднее.
    def _context_limit_check(self, messages):
        # Локально оцениваем запрос в токенах (tiktoken либо эвристика по символам).
        estimated = estimate_messages_tokens(messages)

        # Запрос влезает в лимит — отправляем спокойно.
        if estimated <= self.max_context_tokens:
            # Разрешения достаточно, объяснение не нужно.
            return None

        # Считаем, насколько превысили лимит, чтобы назвать конкретную цифру.
        over = estimated - self.max_context_tokens

        # Возвращаем объяснение: цифры + что делать (только текстовые подсказки,
        # без «магических» действий — решение всегда за пользователем).
        return (
            f"Запрос не отправлен: оценка {estimated} токенов превышает лимит "
            f"{self.max_context_tokens} на {over}.\n"
            "Что уменьшить контекст: /compress — свернуть старые сообщения в саммари; "
            "--window/--keep — короче окно; --load high — загружать только важные слои; "
            "--max-context-tokens — поднять лимит, если он задан слишком низко."
        )

    def send_message(self, user_message: str):
        # Для layered-памяти определяем слой сообщения по маркерам.
        if self.memory_type == "layered":
            # Автоматически определяем приоритет сообщения.
            layer = detect_layer(user_message)
        # Для остальных режимов слой не используется.
        else:
            # Слой не определён (не используется в этом режиме).
            layer = None

        # Добавляем реплику пользователя в историю (формат зависит от памяти).
        if self.memory_type == "layered":
            # Для layered добавляем сообщение со слоем и временем.
            self.full_history.append(
                {
                    # Роль сообщения — пользователь.
                    "role": "user",
                    # Текст сообщения.
                    "content": user_message,
                    # Определённый слой приоритета.
                    "layer": layer,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        # Для session и compressed — без слоя.
        else:
            # Добавляем сообщение с ролью, текстом и временем.
            self.full_history.append(
                {
                    # Роль сообщения — пользователь.
                    "role": "user",
                    # Текст сообщения.
                    "content": user_message,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        # Формируем запрос через диспетчер стратегий контекста.
        messages = self._build_messages()

        # День 8: проверяем переполнение ДО обращения к API. Реплику пользователя
        # убираем из истории — обмен не состоялся, история остаётся целой.
        limit_problem = self._context_limit_check(messages)
        if limit_problem is not None:
            # Печатаем объяснение с конкретными цифрами и подсказками.
            print(f"[Контекст] {limit_problem}\n")
            # Удаляем реплику пользователя, добавленную выше.
            self.full_history.pop()
            # Возвращаем None — цикл продолжится без запроса и без списания токенов.
            return None

        # Отправляем запрос к LLM и получаем ответ (или None при ошибке).
        bot_response = self._ask_llm(messages)

        # Если ответа нет (ошибка API) — убираем реплику пользователя из истории,
        # чтобы она не «висела» без ответа и не попала в саммари.
        if bot_response is None:
            # Удаляем последнее сообщение пользователя.
            self.full_history.pop()
            # Возвращаем None — CLI продолжит цикл без ответа.
            return None

        # День 8: обмен состоялся — увеличиваем счётчик обменов. Он нужен как номер
        # строки в CSV-журнале и как множитель в прогнозе стоимости.
        self.exchanges += 1

        # День 8: дозаписываем строку обмена в CSV-журнал токенов. Ошибка записи
        # обрабатывается внутри и чат не роняет.
        append_token_log(self)

        # Добавляем ответ модели в историю (формат зависит от памяти).
        if self.memory_type == "layered":
            # Для layered ответ наследует слой сообщения пользователя.
            self.full_history.append(
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
            self.full_history.append(
                {
                    # Роль сообщения — ассистент.
                    "role": "assistant",
                    # Текст ответа.
                    "content": bot_response,
                    # Текущая дата и время.
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        # --- Пост-обработка: вытеснение (A) или автосжатие (B и C) ---

        # Для sliding_window проверяем появление новых вытесненных сообщений.
        if self.context_strategy == "sliding_window":
            # Считаем, сколько сообщений сейчас вне окна.
            new_evicted = max(0, len(self.full_history) - self.window)

            # Если количество вытесненных увеличилось — окно сдвинулось.
            if new_evicted > self.evicted_total:
                # Выводим ненавязчивое уведомление о вытеснении (один раз за сдвиг).
                print(
                    f"[Контекст] Сообщение вышло из окна "
                    f"(осталось {self.window} последних)\n"
                )

            # Запоминаем новое количество вытесненных сообщений.
            self.evicted_total = new_evicted

        # Для history_compression и context_leveling проверяем порог автосжатия.
        else:
            # Считаем сообщения вне окна оперативного слоя.
            outside_window = len(self.full_history) - self.window

            # Если вне окна накопилось >= порога — запускаем автоматическое сжатие.
            if outside_window >= COMPRESS_THRESHOLD:
                # Сжимаем все сообщения вне окна (старые), оставляя окно нетронутым.
                old_messages = self.full_history[:-self.window]

                # Сжатие через LLM: для layered — по слоям, для compressed — общее.
                summaries = self._run_compression(old_messages)

                # Если сжатие удалось — применяем его к состоянию агента.
                if summaries is not None:
                    # Сохранение, архивирование и уведомление — в общем методе.
                    self._apply_compression(old_messages, summaries)
                # Если сжатие не удалось — не теряем сообщения.
                else:
                    # Сообщаем, что сжатие отложено, сообщения сохранены.
                    print("[Сжатие] Не удалось, сообщения сохранены, попробуем в следующий раз\n")

        # Возвращаем текст ответа для вывода в консоль.
        return bot_response

    # Принудительное сжатие (команда /compress): сворачивает все активные
    # сообщения в саммари. Возвращает (кол-во сообщений, длина саммари)
    # или None, если сжимать нечего/сжатие не удалось.
    def compress(self):
        # Если активных сообщений нет — сжимать нечего.
        if not self.full_history:
            # Сообщаем пользователю об отсутствии сообщений для сжатия.
            print("[Сжатие] Нет сообщений для сжатия\n")
            # Возвращаем None — операции не было.
            return None

        # Копируем активные сообщения: сжатие изменит сам список.
        old_messages = list(self.full_history)

        # Запоминаем количество сжимаемых сообщений до изменения истории.
        n = len(old_messages)

        # Сжатие через LLM: для layered — по слоям, для compressed — общее.
        summaries = self._run_compression(old_messages)

        # Если сжатие не удалось — не теряем сообщения, оставляем всё как было.
        if summaries is None:
            # Сообщаем пользователю, что сжатие отложено, сообщения сохранены.
            print("[Сжатие] Не удалось, сообщения сохранены, попробуем в следующий раз\n")
            # Возвращаем None — сжатие не состоялось.
            return None

        # Применяем сжатие: саммари, архив, уведомление.
        self._apply_compression(old_messages, summaries)

        # Возвращаем кортеж: количество сообщений и суммарную длину саммари.
        return (n, self.get_summary_length())

    # Смена приоритета сообщения по индексу (команда /layer, только layered).
    # Индекс — позиция сообщения пользователя с конца, начиная с 1.
    def set_layer(self, index: int, layer: str) -> bool:
        # Проверяем, что указанный слой существует.
        if layer not in LAYER_LABELS:
            # Неверное имя слоя — операция не выполнена.
            return False

        # Находим сообщения пользователя в активной истории (с конца).
        user_messages = [msg for msg in self.full_history if msg["role"] == "user"]

        # Проверяем, что запрошенный номер существует среди сообщений пользователя.
        if index < 1 or index > len(user_messages):
            # Индекс вне диапазона — операция не выполнена.
            return False

        # Берём сообщение пользователя по номеру (1 — последнее, 2 — предпоследнее...).
        target = user_messages[-index]

        # Меняем приоритет выбранного сообщения.
        target["layer"] = layer

        # Возвращаем признак успеха.
        return True

    # Текст сообщения пользователя по номеру с конца активной истории.
    # Нужен CLI, чтобы показать именно то сообщение, у которого сменили слой
    # (нумерация та же, что в set_layer: 1 — последнее сообщение пользователя).
    def get_user_message(self, index: int) -> str:
        # Находим сообщения пользователя в активной истории (с конца).
        user_messages = [msg for msg in self.full_history if msg["role"] == "user"]

        # Проверяем, что запрошенный номер существует.
        if index < 1 or index > len(user_messages):
            # Нет такого сообщения — возвращаем None.
            return None

        # Возвращаем текст сообщения по номеру (1 — последнее).
        return user_messages[-index]["content"]

    # Полная длина саммари в символах: единого — для compressed, суммы по
    # слоям — для layered. Нужна для уведомлений, /window и статистики загрузки.
    def get_summary_length(self) -> int:
        # layered: суммарная длина саммари всех слоёв.
        if self.memory_type == "layered":
            # Складываем длины непустых послойных саммари.
            return sum(len(text) for text in self.summary_by_layer.values())
        # session/compressed: длина единого саммари.
        return len(self.summary)

    # Сохранение саммари в файл (перезапись целиком при каждом обновлении).
    # Для layered файл пишется секциями по слоям, иначе — одним блоком.
    def save_summary(self, filepath: str):
        # layered-память: пишем по секции на каждый непустой слой.
        if self.memory_type == "layered":
            # Секции только для слоёв с непустым саммари.
            sections = [
                (layer, text) for layer, text in self.summary_by_layer.items() if text
            ]
            # Ни один слой не сжат — файл не трогаем (пустых заголовков не плодим).
            if not sections:
                # Просто выходим: сохранять нечего.
                return

            # Открываем файл саммари на запись (перезапись) с кодировкой UTF-8.
            with open(filepath, "w", encoding="utf-8") as f:
                # Пишем заголовок первого уровня с названием техники.
                f.write("# Саммари диалога — День 8 (послойно)\n")
                # Пишем строку с датой и временем последнего обновления.
                f.write(f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                # Каждую секцию — отдельным подзаголовком слоя и текстом.
                for layer, text in sections:
                    # Подзаголовок слоя.
                    f.write(f"\n## слой {layer}\n\n")
                    # Текст саммари слоя.
                    f.write(f"{text}\n")
            # Файл записан.
            return

        # Если саммари пустое — файл не трогаем (пустых заголовков не плодим).
        if not self.summary:
            # Просто выходим: сохранять нечего.
            return

        # Открываем файл саммари на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем заголовок первого уровня с названием техники.
            f.write("# Саммари диалога — День 8\n")
            # Пишем строку с датой и временем последнего обновления.
            f.write(f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            # Пишем текст саммари и перевод строки в конце.
            f.write(f"{self.summary}\n")

    # Разбор значения --load в множество выбираемых слоёв.
    def _parse_load_layers(self, value):
        # Если указано «all» — выбираем все слои.
        if value == "all":
            # Возвращаем все известные слои.
            return set(LAYER_ORDER)

        # Если указано «none» — возвращаем пустое множество (чистая сессия).
        if value == "none":
            # Ни один слой не будет загружен.
            return set()

        # Иначе ожидаем список через запятую, например «high,mid».
        return {
            part.strip() for part in value.split(",") if part.strip() in LAYER_LABELS
        }

    # Сохранение истории: дозаписывает в Markdown-лог только НОВЫЕ сообщения.
    # Счётчик saved_count нужен, чтобы /save не затирал live-лог и чтобы
    # повторные /save не создавали дубли.
    def save_history(self, filepath: str):
        # Отбираем сообщения, которых ещё нет в файле.
        new_messages = self.full_history[self.saved_count:]

        # Если новых сообщений нет — файл не трогаем (пустых заголовков не плодим).
        if not new_messages:
            # Просто выходим: сохранять нечего.
            return

        # Открываем лог в режиме дозаписи с кодировкой UTF-8.
        with open(filepath, "a", encoding="utf-8") as f:
            # Пишем разделитель с датой и временем — одна запись на сохранение.
            f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Перебираем новые сообщения и пишем каждое отдельной строкой.
            for msg in new_messages:
                # Роль «user» показываем как «Вы», «assistant» — как «Агент».
                role = "Вы" if msg["role"] == "user" else "Агент"

                # Для layered-памяти добавляем пометку слоя.
                if self.memory_type == "layered":
                    # Пишем строку формата «**Роль** [слой]: текст».
                    f.write(f"**{role}** [{msg['layer']}]: {msg['content']}\n")
                # Для остальных режимов — обычная строка.
                else:
                    # Пишем строку формата «**Роль:** текст».
                    f.write(f"**{role}:** {msg['content']}\n")

        # Запоминаем, что теперь в файле лежит вся текущая история.
        self.saved_count = len(self.full_history)

    # Отметка «вся история уже в логе». Её делает CLI после дозаписи обмена
    # функцией append_log(): без неё /save повторно записал бы те же строки.
    def mark_saved(self):
        # Считаем все текущие сообщения сохранёнными.
        self.saved_count = len(self.full_history)


    # Очистка контекста (сброс истории; для compressed/layered — и саммари).
    def clear_context(self):
        # Полностью очищаем активную историю диалога в памяти.
        self.full_history = []

        # Сбрасываем счётчик сохранённых: следующая запись — новая сессия.
        self.saved_count = 0

        # Очищаем архив свёрнутых сообщений.
        self.archived = []

        # Для compressed и layered сбрасываем и саммари.
        if self.memory_type in ("compressed", "layered"):
            # Сбрасываем саммари в памяти.
            self.summary = ""

            # Для layered чистим и послойные саммари: иначе /clear окажется
            # неполным, а ближайший /exit перезапишет снимок старыми секциями.
            self.summary_by_layer = {layer: "" for layer in LAYER_ORDER}

            # Удаляем файл саммари на диске: иначе после перезапуска вернётся
            # старое саммари из файла и /clear окажется неполным.
            if os.path.exists(SUMMARY_FILE):
                # Удаляем файл саммари.
                os.remove(SUMMARY_FILE)

        # Сбрасываем счётчик вытесненных сообщений.
        self.evicted_total = 0

    # Краткое описание текущего контекста: режим, окно, саммари, слои.
    def get_context_summary(self) -> str:
        # Считаем, сколько сообщений сейчас реально помещается в окне.
        in_window = min(len(self.full_history), self.window)

        # Базовая часть: режим, окно и заполненность.
        text = (
            f"[Контекст] режим={self.context_strategy}, память={self.memory_type}; "
            f"в окне: {in_window} из {self.window}"
        )

        # Для compressed и layered добавляем сведения о саммари.
        if self.memory_type in ("compressed", "layered"):
            # Дописываем длину саммари в символах (для layered — сумму по слоям).
            text += f"; саммари: {self.get_summary_length()} символов"

        # Для layered добавляем статистику слоёв.
        if self.memory_type == "layered":
            # Собираем счётчики сообщений по слоям в одну строку.
            layers_text = ", ".join(
                f"{layer}={sum(1 for msg in self.full_history if msg['layer'] == layer)}"
                for layer in LAYER_ORDER
            )
            # Дописываем статистику слоёв.
            text += f"; слои: {layers_text}"

        # Возвращаем готовую строку для вывода.
        return text

    # Полная история с пометками для команды /history.
    # Возвращает список словарей {"role", "content", "layer"|"", "status"}.
    def get_history(self) -> list:
        # Индекс первого сообщения, которое ещё попало в окно.
        in_window_from = max(0, len(self.full_history) - self.window)

        # Собираем архивные сообщения с пометкой «в саммари».
        result = [
            {
                "role": msg["role"],
                "content": msg["content"],
                # Слой есть только у layered-памяти.
                "layer": msg.get("layer", ""),
                "status": "в саммари",
            }
            for msg in self.archived
        ]

        # Добавляем активные сообщения с пометками положения в контексте.
        for index, msg in enumerate(self.full_history):
            # Для sliding_window вытесненные помечаем «вытеснено».
            if self.context_strategy == "sliding_window":
                # Сообщение либо в окне, либо уже вытеснено.
                status = "в окне" if index >= in_window_from else "вытеснено"
            # Для compression/leveling вне окна — «вне окна» (ещё не сжаты).
            else:
                # Сообщение либо в окне, либо вне окна (ждёт сжатия).
                status = "в окне" if index >= in_window_from else "вне окна"

            # Добавляем сообщение с пометками.
            result.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    # Слой есть только у layered-памяти.
                    "layer": msg.get("layer", ""),
                    "status": status,
                }
            )

        # Возвращаем готовый список для вывода.
        return result

    # Текущее саммари — для команды /summary.
    # Для layered собираем непустые послойные саммари в текст с подписями слоёв.
    def get_summary(self) -> str:
        # layered-память: секции вида «[high] текст» через перевод строки.
        if self.memory_type == "layered":
            # Собираем только непустые слои, в порядке важности.
            parts = [
                f"[{layer}] {text}"
                for layer, text in self.summary_by_layer.items()
                if text
            ]
            # Пустой список даёт пустую строку — /summary корректно скажет «пусто».
            return "\n".join(parts)

        # session/compressed: единое саммари (пустая строка, если саммари нет).
        return self.summary

    # Статистика по слоям для команды /layers (только layered):
    # возвращает словарь {слой: {"total": всего, "in_window": в окне,
    # "summary_length": длина саммари слоя}}.
    def get_layers_stats(self) -> dict:
        # Индекс первого сообщения, которое ещё попало в окно.
        in_window_from = max(0, len(self.full_history) - self.window)

        # Собираем по каждому слою количество сообщений и длину саммари.
        return {
            layer: {
                # Сколько сообщений этого слоя во всей активной истории.
                "total": sum(1 for msg in self.full_history if msg["layer"] == layer),
                # Сколько из них попадает в окно запроса.
                "in_window": sum(
                    1
                    for index, msg in enumerate(self.full_history)
                    if index >= in_window_from and msg["layer"] == layer
                ),
                # Длина саммари этого слоя в символах (0, если слой не сжат).
                "summary_length": len(self.summary_by_layer.get(layer, "")),
            }
            for layer in LAYER_ORDER
        }


    # --- День 8: JSON-персистентность контекста ------------------------------

    # Сохранение полного состояния агента в JSON-файл (ядро Дня 8).
    # Снимок содержит всё, что нужно продолжить диалог «как будто агент
    # не выключался»: историю, архив, саммари, режимы и размер окна.
    def save_context_json(self, filepath: str):
        # Собираем словарь-снимок текущего состояния агента.
        snapshot = {
            # Версия формата — на случай будущих изменений структуры.
            "version": CONTEXT_VERSION,
            # Дата и время сохранения — для человека, читающего файл.
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # Режимы и окно — чтобы восстановить конфигурацию агента.
            "context_strategy": self.context_strategy,
            "memory_type": self.memory_type,
            "window": self.window,
            # Полная активная история диалога (с timestamp и layer для layered).
            "full_history": self.full_history,
            # Архив сообщений, свёрнутых в саммари (для compressed/layered).
            "archived": self.archived,
            # Текст саммари (пустая строка, если сжатия не было); для layered
            # остаётся пустым — сжатие идёт в summary_by_layer ниже.
            "summary": self.summary,
            # Послойные саммари (v2): {слой: текст}. Для layered — источник
            # сжатого контекста, для остальных режимов — пустой словарь.
            "summary_by_layer": self.summary_by_layer,
            # Счётчик вытесненных из окна сообщений (для sliding_window).
            "evicted_total": self.evicted_total,
            # День 8: накопительный токен-учёт сессии — чтобы после перезапуска
            # /cost показывал стоимость ВСЕГО диалога, а не только новой части.
            "usage_total": dict(self.usage_total),
        }

        # Открываем JSON-файл на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем снимок: ensure_ascii=False — кириллица остаётся читаемой,
            # indent=2 — файл можно открыть и посмотреть глазами.
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # Загрузка состояния агента из JSON-файла (ядро Дня 8).
    # Принимает флаги запуска (context_strategy, memory_type, window) — они
    # нужны, чтобы предупредить о расхождении снимка с CLI. Возвращает словарь
    # со статистикой загрузки или None (нет файла / повреждён / несовместим) —
    # в любом случае программа продолжает работу.
    def load_context_json(self, filepath: str, cli_strategy: str = None,
                          cli_memory: str = None, cli_window: int = None):
        # Флаг --context приходит в виде «sliding-window», а снимок хранит
        # внутреннее имя «sliding_window» — приводим для честного сравнения.
        # Для отображения в предупреждении сохраняем исходную строку флага.
        cli_strategy_label = cli_strategy
        # Карта имён флагов CLI → внутренние имена стратегий.
        strategy_map = {
            "sliding-window": "sliding_window",
            "compression": "history_compression",
            "leveling": "context_leveling",
        }
        # Если флаг передан — приводим его к внутреннему имени.
        if cli_strategy is not None:
            # Неизвестное значение оставляем как есть (совпадение не найдётся —
            # но это не критично: проверка известных значений идёт по снимку).
            cli_strategy = strategy_map.get(cli_strategy, cli_strategy)

        # Если файла контекста нет — это нормальная ситуация первого запуска.
        if not os.path.exists(filepath):
            # Сообщаем пользователю и начинаем чистую сессию.
            print("[Память] Прошлый контекст не найден, начинаю новую сессию")
            # Загрузки не было.
            return None

        # Начинаем блок обработки повреждённого или неожиданного файла.
        try:
            # Открываем JSON-файл на чтение с кодировкой UTF-8.
            with open(filepath, "r", encoding="utf-8") as f:
                # Разбираем JSON в словарь-снимок.
                snapshot = json.load(f)
        # Файл есть, но это не валидный JSON (обрыв записи, ручная правка).
        except json.JSONDecodeError as error:
            # Сообщаем о повреждении и продолжаем с чистой сессией.
            print(f"[Память] Файл контекста повреждён ({error}), начинаю новую сессию")
            # Загрузки не было.
            return None

        # Проверяем версию формата. Снимки старее MIN_MIGRATABLE_VERSION не
        # поднимаем (структура неизвестна); v1 мигрируем в v2 ниже, v3+ — отказ.
        snapshot_version = snapshot.get("version") if isinstance(snapshot, dict) else None
        # Снимок без версии или старше минимально поддерживаемой — несовместим.
        if not isinstance(snapshot_version, int) or snapshot_version < MIN_MIGRATABLE_VERSION:
            # Сообщаем о несовместимой версии и причине отказа.
            print(
                f"[Память] Файл контекста имеет версию {snapshot_version!r}, "
                f"поддерживается от {MIN_MIGRATABLE_VERSION} до {CONTEXT_VERSION} — "
                "начинаю новую сессию"
            )
            # Файл на диске не трогаем, в лог его тоже не поднимаем.
            return None

        # Снимок новее текущего формата — не знаем его структуру, отказ.
        if snapshot_version > CONTEXT_VERSION:
            # Сообщаем, что снимок сделан более новой версией программы.
            print(
                f"[Память] Файл контекста имеет версию {snapshot_version}, "
                f"ожидается до {CONTEXT_VERSION} — начинаю новую сессию"
            )
            # Файл на диске не трогаем, в лог его тоже не поднимаем.
            return None

        # Начинаем блок проверки структуры снимка.
        try:
            # Восстанавливаем режимы и окно из снимка.
            snapshot_strategy = snapshot["context_strategy"]
            # Тип памяти из снимка.
            snapshot_memory = snapshot["memory_type"]
            # Размер окна из снимка.
            snapshot_window = snapshot["window"]

            # Валидируем значения из снимка: мусорная стратегия/тип уронили бы
            # сборку запроса в _build_messages — поэтому отсекаем их здесь.
            if snapshot_strategy not in KNOWN_STRATEGIES:
                # Сообщаем о несовместимом значении стратегии.
                print(
                    f"[Память] Неизвестный режим контекста в снимке "
                    f"({snapshot_strategy!r}), начинаю новую сессию"
                )
                # Файл не удаляем, в лог его не поднимаем.
                return None

            # Проверяем тип памяти из снимка по списку известных значений.
            if snapshot_memory not in KNOWN_MEMORY_TYPES:
                # Сообщаем о несовместимом значении типа памяти.
                print(
                    f"[Память] Неизвестный тип памяти в снимке "
                    f"({snapshot_memory!r}), начинаю новую сессию"
                )
                # Файл не удаляем, в лог его не поднимаем.
                return None

            # Проверяем размер окна из снимка: ноль/отрицательное сделало бы
            # окно пустым, а окно-строка сломала бы арифметику.
            if not isinstance(snapshot_window, int) or snapshot_window < 1:
                # Сообщаем о некорректном размере окна.
                print(
                    f"[Память] Некорректный размер окна в снимке "
                    f"({snapshot_window!r}), начинаю новую сессию"
                )
                # Файл не удаляем, в лог его не поднимаем.
                return None

            # Предупреждаем о расхождении снимка с флагами CLI: конфигурация
            # берётся из снимка, а явные флаги запуска игнорируются.
            if cli_strategy is not None and cli_strategy != snapshot_strategy:
                # Метка [Конфиг] в том же стиле, что и автоисправление флагов.
                print(
                    f"[Конфиг] Режим контекста из снимка ({snapshot_strategy}) "
                    f"отличается от флага --context ({cli_strategy_label}) — беру из снимка"
                )
            if cli_memory is not None and cli_memory != snapshot_memory:
                # Предупреждение о расхождении типа памяти.
                print(
                    f"[Конфиг] Тип памяти из снимка ({snapshot_memory}) "
                    f"отличается от флага --memory ({cli_memory}) — беру из снимка"
                )
            if cli_window is not None and cli_window != snapshot_window:
                # Предупреждение о расхождении размера окна.
                print(
                    f"[Конфиг] Размер окна из снимка ({snapshot_window}) "
                    f"отличается от флага запуска ({cli_window}) — беру из снимка"
                )

            # Применяем проверенную конфигурацию из снимка.
            self.context_strategy = snapshot_strategy
            # Тип памяти из снимка.
            self.memory_type = snapshot_memory
            # Размер окна из снимка.
            self.window = snapshot_window

            # Восстанавливаем историю: каждая запись должна быть словарём
            # с role и content; timestamp может отсутствовать в старых снимках.
            restored_history = []
            # Для layered фильтруем слои по --load уже здесь: источник истины —
            # снимок, а не Markdown-лог (иначе load_history затирал архив).
            chosen = self._parse_load_layers(self.load_layers)
            # Перебираем записи активной истории из снимка.
            for msg in snapshot.get("full_history", []):
                # Запись обязана быть словарём; иначе структура несовместима.
                if not isinstance(msg, dict):
                    # Прерываем восстановление — снимок битый.
                    raise TypeError("запись full_history не является словарём")
                # Копируем запись как есть — формат совпадает с внутренним.
                entry = dict(msg)
                # Если timestamp потерялся — ставим время загрузки.
                entry.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                # Для layered-памяти слой обязателен: если его нет в снимке
                # (например, снимок сделан в session-режиме) — определяем
                # автоматически по маркерам текста.
                if self.memory_type == "layered" and "layer" not in entry:
                    # Автоопределение слоя по тексту сообщения.
                    entry["layer"] = detect_layer(entry["content"])
                # Для layered пропускаем сообщения, чей слой не выбран --load.
                if self.memory_type == "layered" and entry.get("layer") not in chosen:
                    # Слой исключён флагом --load — в контекст не попадает.
                    continue
                # Добавляем восстановленную запись в историю.
                restored_history.append(entry)

            # Восстановленная история становится активной историей агента.
            self.full_history = restored_history

            # Восстанавливаем архив свёрнутых сообщений (для compressed/layered).
            self.archived = list(snapshot.get("archived", []))

            # Для layered-памяти у архивных записей тоже может не быть слоя.
            if self.memory_type == "layered":
                # Перебираем архивные записи и дополняем слой при отсутствии.
                for msg in self.archived:
                    # Автоопределение слоя по тексту сообщения.
                    msg.setdefault("layer", detect_layer(msg["content"]))

            # Восстанавливаем саммари (пустая строка, если его не было).
            self.summary = snapshot.get("summary", "")

            # Восстанавливаем послойные саммари (v2). Для снимков v1 ключа нет —
            # мигрируем: прежнее единое саммари было смешанным, поэтому относим
            # его в low (самый «терпимый» к потерям слой), а high/mid остаются
            # пустыми — сожмутся заново из архива при ближайшем сжатии.
            snapshot_sbl = snapshot.get("summary_by_layer")
            if snapshot_version == 1 or not isinstance(snapshot_sbl, dict):
                # Свежий словарь пустых послойных саммари.
                self.summary_by_layer = {layer: "" for layer in LAYER_ORDER}
                # Единое саммари v1 переезжает в low-слой.
                self.summary_by_layer["low"] = self.summary
                # Для layered-памяти уведомляем о миграции снимка.
                if snapshot_version == 1 and self.memory_type == "layered":
                    # Сообщение о том, что старый снимок поднят в новый формат.
                    print("[Память] Снимок v1 мигрирован в v2 (саммари перенесено в слой low)")
            else:
                # v2: поднимаем послойные саммари, дополняя недостающие слои пустым.
                self.summary_by_layer = {
                    layer: (snapshot_sbl.get(layer, "") if isinstance(snapshot_sbl.get(layer, ""), str) else "")
                    for layer in LAYER_ORDER
                }

            # Восстанавливаем счётчик вытесненных сообщений.
            self.evicted_total = snapshot.get("evicted_total", 0)

            # День 8: восстанавливаем накопительный токен-учёт. Снимки версии 1
            # (день 7) блока usage не содержат — тогда остаёмся на нулях, это честно:
            # токены той сессии нам неизвестны, выдумывать их нельзя.
            saved_usage = snapshot.get("usage_total") or {}

            # Начинаем блок: частично битый блок usage не должен уронить загрузку.
            try:
                # Каждое поле берём отдельно с дефолтом и приведением к числу.
                self.usage_total = {
                    "prompt_tokens": int(saved_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(saved_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(saved_usage.get("total_tokens", 0) or 0),
                    "requests": int(saved_usage.get("requests", 0) or 0),
                }
            # Не число, неожиданный тип — считаем блок usage несостоявшимся.
            except (ValueError, TypeError):
                # Оставляем нули: токены неизвестны, но диалог продолжается.
                self.usage_total = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "requests": 0,
                }

            # usage последнего обмена не держим между сессиями — в новой сессии
            # «токены текущего запроса» узнаем только после первого обмена.
            self.last_usage = {}

            # Если снимок старого формата (v1) — предупреждаем, что стоимость
            # прошлой части диалога не восстановлена.
            if snapshot_version == 1:
                # Сообщение не критичное: диалог продолжается, просто без старых токенов.
                print(
                    "[Память] Снимок старого формата (v1): накопленные токены "
                    "прошлой сессии неизвестны, счётчики начнут с нуля"
                )

        # Структура файла не соответствует ожидаемой (нет ключей, не те типы).
        except (KeyError, TypeError, AttributeError) as error:
            # Сообщаем о неожиданной структуре и продолжаем с чистой сессией.
            print(f"[Память] Файл контекста повреждён ({error}), начинаю новую сессию")
            # Сбрасываем состояние в чистую сессию, чтобы не осталась «половина».
            self.full_history = []
            # Архив тоже пуст.
            self.archived = []
            # Саммари пустое.
            self.summary = ""
            # Послойные саммари тоже пустые.
            self.summary_by_layer = {layer: "" for layer in LAYER_ORDER}
            # Счётчик вытеснений обнулён.
            self.evicted_total = 0
            # День 8: токен-учёт тоже сбрасываем, чтобы «залипшие» старые токены
            # не выдавали себя за стоимость текущей (битой) сессии.
            self.usage_total = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "requests": 0,
            }
            self.last_usage = {}
            # Файл на диске и Markdown-лог не трогаем: там может оставаться
            # читаемая история, которую пользователь спасёт вручную.
            return None

        # Снимок и Markdown-лог ведутся параллельно (оба сохраняются при /exit),
        # поэтому считаем восстановленную историю уже записанной в лог: иначе
        # ближайший /exit дозаписал бы её повторно и получились бы дубли.
        self.saved_count = len(self.full_history)

        # Собираем статистику загрузки для сообщения пользователю.
        stats = {
            # Сколько сообщений восстановлено в активную историю.
            "loaded": len(self.full_history),
            # Длина восстановленного саммари в символах (для layered — сумма по слоям).
            "summary_length": self.get_summary_length(),
        }

        # Возвращаем статистику вызывающему коду (главный цикл её печатает).
        return stats


# 8. Функции лога (append_log, log_compression) — CLI-уровень --------------------


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


# Информационная функция: предупреждение о Markdown-логе прошлой сессии.
# Вызывается ТОЛЬКО когда JSON-снимок не восстановлен — иначе сообщение
# противоречило бы факту («контекст восстановлен» + «сессия новая»).
def notify_old_log(filepath):
    # Лога нет — предупреждать не о чем.
    if not os.path.exists(filepath):
        # Просто выходим.
        return

    # Сообщаем, что лог найден, но состояние из него не поднимается:
    # источник истины — JSON-снимок, лог нужен человеку.
    print(
        f"[Память] Найден прошлый лог: {filepath} "
        "(в контекст не загружается — состояние восстанавливается только из JSON-снимка)"
    )



# 9. Обработчики команд CLI (с проверкой доступности) ----------------------------


# Обработчик /history: полная история с пометками, зависящими от режима.
def cmd_history(agent):
    # Данные берём у агента, а не из «своего» списка — CLI не лезет в историю.
    history = agent.get_history()

    # Если история пуста — сразу сообщаем об этом.
    if not history:
        # Печатаем пояснение и пустую строку для читаемости.
        print("[История] Пока пусто\n")
        # Завершаем обработчик.
        return

    # Перебираем сообщения, полученные от агента.
    for msg in history:
        # Определяем роль сообщения для отображения («Вы» или «Агент»).
        role = "Вы" if msg["role"] == "user" else "Агент"

        # Формируем пометку слоя для layered-памяти.
        layer_tag = f"[{msg['layer']}] " if msg["layer"] else ""

        # Печатаем сообщение: слой (если есть), статус, роль, текст.
        print(f"{layer_tag}[{msg['status']}] {role}: {msg['content']}")

    # После списка печатаем пустую строку для читаемости.
    print()


# Обработчик /window: размер окна (только для sliding-window).
def cmd_window(agent):
    # Описание контекста формирует сам агент.
    print(agent.get_context_summary())
    # Печатаем пустую строку для читаемости.
    print()


# Обработчик /summary: текущее саммари (для compressed и layered).
def cmd_summary(agent):
    # Текст саммари берём у агента.
    summary_text = agent.get_summary()

    # Если саммари пустое — сообщаем об этом.
    if not summary_text:
        # Печатаем сообщение о том, что саммари ещё не создано.
        print("[Саммари] Саммари пока пусто\n")
    # Иначе показываем текст саммари.
    else:
        # Печатаем текст саммари и пустую строку для читаемости.
        print(f"[Саммари] {summary_text}\n")


# Обработчик /layers: статистика по слоям (только для layered).
def cmd_layers(agent):
    # Сначала общая картина контекста (окно, порог, слои, саммари).
    print(agent.get_context_summary())

    # Статистику считает сам агент, CLI только печатает.
    stats = agent.get_layers_stats()

    # Перебираем слои в порядке важности: high, mid, low.
    for layer in LAYER_ORDER:
        # Печатаем статистику слоя: всего, в окне и длину саммари слоя.
        print(
            f"[Слои] {layer}={stats[layer]['total']} "
            f"(в окне: {stats[layer]['in_window']}, "
            f"саммари: {stats[layer]['summary_length']} символов)"
        )

    # После статистики печатаем пустую строку для читаемости.
    print()


# Обработчик /layer: смена приоритета сообщения (только layered).
def cmd_layer(agent, parts):
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

    # Смену приоритета выполняет агент; он же проверяет диапазон и имя слоя.
    if not agent.set_layer(number, parts[2]):
        # Сообщаем, что команду применить не удалось.
        print(f"[Слой] Нет сообщения пользователя с номером {number}\n")
        # Выходим из обработчика.
        return

    # Текст изменённого сообщения берём у агента по той же нумерации, что и
    # в set_layer (активная история, 1 — последнее сообщение пользователя).
    # Раньше здесь использовался get_history() (архив + активные) — после
    # сжатия номер указывал на чужое/архивное сообщение.
    changed_text = agent.get_user_message(number)

    # Если сообщение вдруг не найдено (краевой случай) — сообщаем об этом.
    if changed_text is None:
        # Сообщаем о недоступном номере.
        print(f"[Слой] Нет сообщения пользователя с номером {number}\n")
        # Выходим из обработчика.
        return

    # Сообщаем пользователю об успешной смене слоя.
    print(f"[Слой] Сообщение изменено: {changed_text[:50]} → {parts[2]}\n")


# Обработчик /help: список команд с пометкой доступности в текущем режиме.
def cmd_help(agent, args):
    # Печатаем заголовок справки.
    print("[Справка] Доступные команды:")

    # /history — доступна во всех режимах.
    print("  /history — показать историю диалога (все режимы)")

    # /window — только для sliding-window.
    if args.context == "sliding-window":
        # Команда доступна в текущем режиме контекста.
        print("  /window — параметры окна контекста (sliding-window)")
    else:
        # Команда недоступна в текущем режиме контекста.
        print("  /window — недоступна в текущем режиме контекста")

    # /summary — для compressed и layered.
    if args.memory in ("compressed", "layered"):
        # Команда доступна в текущем режиме памяти.
        print("  /summary — показать текущее саммари (compressed/layered)")
    else:
        # Команда недоступна в текущем режиме памяти.
        print("  /summary — недоступна в режиме memory=session")

    # /compress — для compressed и layered.
    if args.memory in ("compressed", "layered"):
        # Команда доступна в текущем режиме памяти.
        print("  /compress — принудительно сжать историю в саммари (compressed/layered)")
    else:
        # Команда недоступна в текущем режиме памяти.
        print("  /compress — недоступна в режиме memory=session")

    # /layers и /layer — только для layered.
    if args.memory == "layered":
        # Команды доступны в текущем режиме памяти.
        print("  /layers — статистика слоёв (layered)")
        print("  /layer <номер> <high|mid|low> — сменить приоритет сообщения (layered)")
    else:
        # Команды недоступны в текущем режиме памяти.
        print(f"  /layers — недоступна в режиме memory={args.memory}")
        print(f"  /layer — недоступна в режиме memory={args.memory}")

    # /save и /load — JSON-операции, доступны во всех режимах.
    print("  /save — сохранить контекст в JSON-снимок (все режимы)")
    print("  /load — восстановить контекст из JSON-снимка (все режимы)")

    # Токен-команды Дня 8 — во всех режимах.
    print("  /tokens — три счётчика токенов и локальная оценка (все режимы)")
    print("  /cost — стоимость обмена, сессии и прогноз (все режимы)")
    print("  /scenario — сравнение трёх сценариев расхода (все режимы)")

    # /clear, /help, /exit — доступны во всех режимах.
    print("  /clear — очистить контекст (все режимы)")
    print("  /help — эта справка (все режимы)")
    print("  /exit — завершить работу (все режимы)")
    print()


# Обработчик /compress: принудительное сжатие (для compression и leveling).
def cmd_compress(agent):
    # Сжатие выполняет агент: сворачивает все активные сообщения в саммари.
    agent.compress()


# Обработчик /save: ручное сохранение контекста в JSON (День 8).
def cmd_save_context(agent):
    # Снимок состояния делает сам агент; CLI только указывает файл.
    agent.save_context_json(CONTEXT_FILE)

    # Сообщаем пользователю, куда сохранён контекст.
    print(f"[Память] Контекст сохранён: {CONTEXT_FILE}\n")


# Обработчик /tokens: три счётчика токенов + локальная оценка (День 8).
def cmd_tokens(agent):
    # Берём счётчики у агента: они могут быть None, если usage не приходил.
    req = agent.tokens_request()
    resp = agent.tokens_response()
    hist = agent.tokens_history()

    # Форматируем «нет данных» для отсутствующих значений (API не прислал usage).
    req_str = req if req is not None else "нет данных"
    resp_str = resp if resp is not None else "нет данных"

    # Печатаем три счётчика из задания.
    print(f"[Токены] Текущий запрос: {req_str} | Ответ: {resp_str} | Вся история: {hist}")

    # Локальная оценка ПОСЛЕДНЕГО сообщения пользователя: показывает, сколько токенов
    # добавит следующая отправка (до того, как деньги спишутся). Это прогноз, а не
    # авторитетная цифра: авторитет — usage из ответа API.
    # Берём именно сообщение пользователя (агент считает его по full_history), а не
    # последнюю запись истории — иначе после обмена оценка дала бы ответ модели.
    last_user = agent.get_user_message(1) if agent.full_history else None

    # Есть ли сообщение пользователя для оценки.
    if last_user is not None:
        # Оцениваем его текст локально.
        local = estimate_tokens(last_user)

        # Печатаем оценку с пометкой «локальная».
        print(f"[Токены] Локальная оценка последнего сообщения: ~{local}")
    # Пустая история — оценивать нечего.
    else:
        # Сообщаем, что истории (или реплик пользователя) нет.
        print("[Токены] История пуста — локальная оценка нечего считать")

    # Пустая строка для читаемости.
    print()


# Обработчик /scenario: сравнение трёх сценариев расхода токенов (День 8).
# Короткий диалог, длинный диалог (тексты генерируются локально) и диалог сверх лимита.
# Живые запросы к API — ТОЛЬКО после явного «y»; иначе всё считается локально.
def cmd_scenario(agent):
    # Спрашиваем пользователя про живой прогон: деньги тратятся только с его согласия.
    answer = input("Сделать живые запросы к API? Тратятся реальные деньги (y/N): ")

    # Живой режим только при явном «y» (регистр не важен); всё остальное — отказ.
    live = answer.strip().lower() == "y"

    # Готовим три сценария: имя и список сообщений пользователя.
    scenarios = [
        # Короткий диалог: одна короткая реплика.
        ("короткий", ["Привет"]),
        # Длинный диалог: одна большая реплика (~2000 символов, генерируется локально).
        ("длинный", ["Расскажи про токенизацию. " * 100]),
        # Сверх лимита: реплика, которая заведомо не влезет в --max-context-tokens
        # (если лимит не задан, сравниваем с окном модели — тогда сценарий просто пройдёт).
        ("сверх-лимита", ["Подробно про устройство трансформеров и attention. " * 500]),
    ]

    # Заголовок таблицы результатов.
    print(f"\n[Сценарии] Режим: {'ЖИВОЙ API' if live else 'оценка без API'}")

    # Перебираем сценарии по очереди.
    for name, messages in scenarios:
        # Локальная оценка суммарного запроса для этого сценария (без API).
        estimated = estimate_messages_tokens(
            [{"role": "system", "content": agent.system_prompt}]
            + [{"role": "user", "content": m} for m in messages]
        )

        # Проверяем, влезает ли сценарий в лимит контекста агента.
        fits = estimated <= agent.max_context_tokens

        # Начинаем строку результата: имя, оценка, вердикт по лимиту.
        line = f"  {name}: ~{estimated} токенов, "

        # Если сценарий не влезает — API не нужен, ответ известен заранее.
        if not fits:
            # Дополняем строку вердиктом о блокировке.
            line += "ЗАБЛОКИРОВАН лимитом (запрос не отправляется, 0 ₽)"
            # Печатаем результат и переходим к следующему сценарию.
            print(line)
            # Следующий сценарий.
            continue

        # Сценарий влезает в лимит: решаем, делать ли живой запрос.
        if not live:
            # Без согласия пользователя — только локальная оценка стоимости.
            line += f"оценка без API: ~{(estimated * agent.price_in_per_m) / 1_000_000:.6f} ₽ вход"
            # Печатаем и идём дальше.
            print(line)
            # Следующий сценарий.
            continue

        # Живой прогон: отправляем сообщения по очереди через агента.
        for message in messages:
            # Отправка реплики: внутри проверка лимита, запрос, CSV, счётчики.
            agent.send_message(message)

        # После прогона берём фактические цифры последнего обмена.
        cost = agent.cost_rubles()

        # Форматируем стоимость (usage мог не прийти).
        cost_str = f"{cost:.6f} ₽" if cost is not None else "нет данных"

        # Дополняем строку фактом живого прогона.
        line += f"ЖИВОЙ прогон выполнен, стоимость обмена: {cost_str}"

        # Печатаем результат сценария.
        print(line)

    # Итоговая строка: накопительная стоимость сессии после всех прогонов.
    print(f"  Итог сессии: {agent.cost_total():.6f} ₽\n")


# Обработчик /cost: стоимость обмена, сессии и прогноз на 100 обменов (День 8).
def cmd_cost(agent):
    # Стоимость последнего обмена (None, если usage не приходил).
    cost = agent.cost_rubles()

    # Накопительная стоимость сессии — считается всегда (даже с нулями).
    total = agent.cost_total()

    # Форматируем стоимость обмена: либо сумма, либо честное «нет данных».
    cost_str = f"{cost:.6f} ₽" if cost is not None else "нет данных"

    # Печатаем стоимость последнего обмена и всей сессии.
    print(f"[Стоимость] Последний обмен: {cost_str} | Вся сессия: {total:.6f} ₽")

    # Прогноз: если каждый следующий обмен будет стоить как последний, сколько
    # выйдет за 100 обменов. Наглядно показывает рост расходов при длинном диалоге.
    if cost is not None:
        # Умножаем стоимость обмена на 100.
        forecast = cost * 100

        # Печатаем прогноз с пояснением допущения.
        print(f"[Стоимость] Прогноз на 100 таких обменов: {forecast:.2f} ₽")
    # Без usage прогноз строить не на чем.
    else:
        # Сообщаем, что прогноза нет.
        print("[Стоимость] Прогноз недоступен: API не прислал usage")

    # Пустая строка для читаемости.
    print()


# Обработчик /load: ручная загрузка контекста из JSON (День 8).
def cmd_load_context(agent):
    # Передаём флаги запуска, чтобы агент предупредил о расхождении снимка.
    stats = agent.load_context_json(
        CONTEXT_FILE,
        cli_strategy=agent.context_strategy,
        cli_memory=agent.memory_type,
        cli_window=agent.window,
    )

    # Если загрузка не состоялась — сообщение уже напечатал агент.
    if stats is None:
        # Завершаем обработчик.
        return

    # Сообщаем пользователю результат восстановления.
    print(
        f"[Память] Контекст восстановлен: {stats['loaded']} сообщений "
        f"(саммари: {stats['summary_length']} символов)\n"
    )




# 10. Главный цикл -----------------------------------------------------------------

# Заголовок лог-файла: создаём файл с шапкой, если его ещё нет.
# Оборачиваем в try: сбой создания (нет прав/каталога) не должен валить
# программу до первого ввода — сообщаем об ошибке и продолжаем работу.
if not os.path.exists(LOG_FILE):
    # Пробуем создать файл с шапкой.
    try:
        # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            # Пишем заголовок с режимами и размером окна.
            f.write(
                f"# Лог диалога — День 8 (контекст={args.context}, память={args.memory}, окно={WINDOW})\n\n"
            )
    # Сбой создания лога не критичен: пишем в журнал и продолжаем.
    except OSError as error:
        # Фиксируем ошибку в журнале ошибок.
        log_error("Не удалось создать лог-файл", error)

# Создаём агента: он один отвечает за стратегии контекста, память и запросы к API.
agent = Agent(
    SYSTEM_PROMPT,
    context_strategy=args.context,
    memory_type=args.memory,
    window=args.window,
    keep=args.keep,
    load_layers=args.load,
    max_context_tokens=MAX_CONTEXT_TOKENS,
    max_tokens=args.max_tokens,
    price_in_per_m=PRICE_IN_PER_M,
    price_out_per_m=PRICE_OUT_PER_M,
)

# Печатаем выбранный режим работы.
print(f"[Режим] контекст={args.context}, память={args.memory}, окно={WINDOW}")

# --- День 8: автозагрузка контекста из JSON (до приветствия) ---------------
# Выполняется для ВСЕХ режимов памяти — в этом смысл дня: агент продолжает
# диалог так, как будто не выключался. Передаём флаги запуска, чтобы агент
# предупредил, если снимок перезаписывает конфигурацию CLI.
# Флаг --fresh отключает загрузку: пользователь явно попросил новую сессию.
if args.fresh:
    # Загрузку не делаем, файл на диске не трогаем — он будет перезаписан
    # при ближайшем сохранении (/save, /exit, Ctrl+C, Ctrl+D).
    print("[Память] Флаг --fresh: начинаю новую сессию, прошлый снимок игнорируется")
    # Статистика загрузки отсутствует — сессия чистая.
    context_stats = None
else:
    # Обычный старт: поднимаем состояние из JSON-снимка.
    context_stats = agent.load_context_json(
        CONTEXT_FILE,
        cli_strategy=args.context,
        cli_memory=args.memory,
        cli_window=WINDOW,
    )

# Если контекст восстановлен — печатаем статистику загрузки.
if context_stats is not None:
    # Сообщение с числом восстановленных сообщений и длиной саммари.
    print(
        f"[Память] Контекст восстановлен: {context_stats['loaded']} сообщений "
        f"(саммари: {context_stats['summary_length']} символов)"
    )
# Если снимок НЕ восстановлен (первый запуск / --fresh / битый файл) и при этом
# в каталоге лежит Markdown-лог прошлой сессии — честно предупреждаем: лог есть,
# но в контекст он не поднимается. Единственный источник истины — JSON-снимок,
# Markdown-лог читается только человеком.
else:
    notify_old_log(LOG_FILE)

# Для layered-памяти показываем статистику загрузки слоёв.
if agent.memory_type == "layered":
    # Повторно получаем статистику: она отражает состояние после JSON-снимка.
    stats = agent.get_layers_stats()

    # Определяем, какие слои были пропущены (не выбраны флагом --load).
    chosen = agent._parse_load_layers(args.load)

    # Список пропущенных слоёв.
    skipped = [layer for layer in LAYER_ORDER if layer not in chosen]

    # Формируем подпись пропущенных слоёв (её нет, если выбрано «all»).
    if len(skipped) == 1:
        # Один пропущенный слой — в единственном числе.
        skipped_text = f" (слой {skipped[0]} пропущен)"
    # Несколько пропущенных слоёв — во множественном числе.
    elif skipped:
        # Перечисляем пропущенные слои.
        skipped_text = f" (слои {', '.join(skipped)} пропущены)"
    # Пропущенных слоёв нет — подписи не будет.
    else:
        # Пустая строка.
        skipped_text = ""

    # Печатаем статистику загрузки: сколько сообщений каждого слоя попало в контекст.
    print(
        f"[Память] Загружено: high={stats['high']['total']}, mid={stats['mid']['total']}, "
        f"low={stats['low']['total']}{skipped_text}"
    )

# Приветственное сообщение агента при старте.
GREETING = "Привет! Я ваш помощник. Чем могу помочь?"

# Выводим приветствие в консоль.
print(f"Агент: {GREETING}\n")

# Дозаписываем приветствие в лог с отметкой времени.
# Оборачиваем в try: сбой записи (нет прав/диск) не должен валить программу
# до первого ввода — сообщаем об ошибке и продолжаем работу.
try:
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
# Сбой записи приветствия не критичен: пишем в журнал и продолжаем.
except OSError as error:
    # Фиксируем ошибку в журнале ошибок.
    log_error("Не удалось записать приветствие в лог", error)

# Выводим шапку программы: название, режимы, окно и имена файлов.
print(f"🤖 Чат-бот — День 8 (контекст={args.context}, память={args.memory}, окно={WINDOW})")
print(f"Лог: {LOG_FILE}")
print(f"Контекст (JSON): {CONTEXT_FILE}")
print("Введите /help для списка команд, /exit для завершения.\n")

# Запускаем бесконечный цикл, чтобы пользователь мог отправлять много сообщений.
# Весь цикл обёрнут в try/except: любая непредвиденная ошибка пишется в журнал,
# а программа не «молча» закрывает окно — она показывает ошибку и ждёт Enter.
while True:
    try:
        # Показываем приглашение «Вы:», читаем ввод и удаляем пробелы по краям.
        user_input = input("Вы: ").strip()

        # Любая строка, начинающаяся с «/», обязана быть известной командой.
        # Без этой проверки опечатка или ещё не реализованная команда
        # уходила в LLM как обычный текст: модель отвечала прозой, а сама
        # команда попадала в лог как реплика пользователя.
        if user_input.startswith("/"):
            # Команда — первое слово строки (у /layer есть аргументы).
            command = user_input.split()[0]

            # Неизвестную команду обрабатываем на месте, не дёргая API.
            if command not in KNOWN_COMMANDS:
                # Говорим, что команда неизвестна, и перечисляем доступные.
                print(
                    f"[Команда] Неизвестная команда: {command}. "
                    f"Доступны: {', '.join(KNOWN_COMMANDS)}\n"
                )
                # Переходим к следующему вводу, ничего не отправляя агенту.
                continue

        # Обрабатываем команду /help — доступна во всех режимах.
        if user_input == "/help":
            # Печатаем справку по командам с учётом текущего режима.
            cmd_help(agent, args)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /history — доступна во всех режимах.
        if user_input == "/history":
            # Вызываем обработчик истории.
            cmd_history(agent)
            # Переходим к следующей итерации цикла.
            continue


        # Обрабатываем команду /window — только для sliding-window.
        if user_input == "/window":
            # Проверяем доступность команды в текущем режиме.
            if args.context == "sliding-window":
                # Вызываем обработчик окна.
                cmd_window(agent)
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
                cmd_summary(agent)
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
                # Вызываем обработчик сжатия.
                cmd_compress(agent)
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
                cmd_layers(agent)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /layers недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /layer — только для layered.
        # Ловим и «/layer» без аргументов: иначе строка ушла бы в LLM.
        if user_input == "/layer" or user_input.startswith("/layer "):
            # Проверяем доступность команды в текущем режиме.
            if args.memory == "layered":
                # Разбиваем команду на части и вызываем обработчик.
                cmd_layer(agent, user_input.split())
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /layer недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /save — ручное сохранение контекста в JSON (День 8).
        if user_input == "/save":
            # Сохранение выполняет обработчик: снимок состояния агента в JSON.
            cmd_save_context(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /tokens — три счётчика токенов (День 8).
        if user_input == "/tokens":
            # Вывод делает обработчик: счётчики агента + локальная оценка.
            cmd_tokens(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /cost — стоимость обмена и сессии (День 8).
        if user_input == "/cost":
            # Вывод делает обработчик: обмен, сессия, прогноз на 100 обменов.
            cmd_cost(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /scenario — три сценария расхода токенов (День 8).
        if user_input == "/scenario":
            # Прогон выполняет обработчик: живой API только после y/N.
            cmd_scenario(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /load — ручная загрузка контекста из JSON (День 8).
        if user_input == "/load":
            # Загрузка выполняет обработчик: восстановление состояния агента.
            cmd_load_context(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /clear — доступна во всех режимах.
        if user_input == "/clear":
            # Очистку делает агент: история стирается, для compressed/layered — и саммари.
            agent.clear_context()
            # Сообщаем пользователю об очистке (JSON-файл на диске не трогаем —
            # долговременная память управляется явно через /load и /exit).
            print("[Контекст] Контекст очищен (лог-файл сохранён)\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /exit — доступна во всех режимах.
        if user_input == "/exit":
            # Для compressed и layered сохраняем саммари в файл.
            if args.memory in ("compressed", "layered"):
                # Сохраняем актуальное саммари в файл (пустое не перезаписывает).
                agent.save_summary(SUMMARY_FILE)
                # Сообщаем пользователю, что саммари сохранено.
                print(f"[Память] Саммари сохранено: {SUMMARY_FILE}")
            # День 8: сохраняем полный контекст в JSON перед выходом.
            agent.save_context_json(CONTEXT_FILE)
            # Сообщаем пользователю, что контекст сохранён.
            print(f"[Память] Контекст сохранён: {CONTEXT_FILE}")
            # Дозаписываем в Markdown-лог всё, что append_log ещё не записал.
            agent.save_history(LOG_FILE)
            # Сообщаем пользователю, что лог сохранён.
            print(f"[Память] Лог сохранён: {LOG_FILE}")
            # Прерываем бесконечный цикл и завершаем программу.
            break

        # Проверяем, осталась ли строка пустой после удаления пробелов.
        if not user_input:
            # Пропускаем текущую итерацию и снова ожидаем пользовательский ввод.
            continue

        # Отправляем сообщение агенту: стратегия контекста, запрос, ответ и
        # пост-обработка (вытеснение/сжатие) — внутри агента.
        bot_response = agent.send_message(user_input)

        # Если ответа нет (ошибка API) — цикл продолжается, история не испорчена.
        if bot_response is None:
            # Переходим к следующей итерации цикла.
            continue

        # Выводим ответ модели и пустую строку для читаемости.
        print(f"Агент: {bot_response}\n")

        # Дозаписываем обмен (пользователь и агент) в лог-файл.
        # Сообщения берём у агента — у него актуальная история с приоритетами.
        history = agent.get_history()

        # Для layered-памяти лог пишется с пометками слоёв.
        layered = args.memory == "layered"

        # Дозаписываем реплику пользователя.
        append_log(history[-2], layered=layered)
        # Дозаписываем ответ агента.
        append_log(history[-1], layered=layered)

        # Сообщаем агенту, что обмен уже лежит в логе: иначе следующий /save
        # или /exit дозапишет эти же сообщения вторично.
        agent.mark_saved()

    # Перехватываем Ctrl+D (EOF) — корректный выход без ошибки.
    except EOFError:
        # День 8: сохраняем контекст и при выходе по EOF — агент «не выключался».
        agent.save_context_json(CONTEXT_FILE)
        # Сообщаем о сохранении контекста.
        print(f"[Память] Контекст сохранён: {CONTEXT_FILE}")
        # Сообщаем о завершении и прерываем цикл.
        print("\n[Выход] Ввод завершён (EOF)")
        break

    # Перехватываем Ctrl+C — корректный выход без traceback.
    except KeyboardInterrupt:
        # День 8: сохраняем контекст и при прерывании — агент «не выключался».
        agent.save_context_json(CONTEXT_FILE)
        # Сообщаем о сохранении контекста.
        print(f"\n[Память] Контекст сохранён: {CONTEXT_FILE}")
        # Сообщаем о прерывании и прерываем цикл.
        print("[Выход] Прервано пользователем")
        break

    # Перехватываем любую другую непредвиденную ошибку в теле цикла.
    except Exception as error:
        # Записываем полный стек ошибки в журнал ошибок.
        log_error("Ошибка в главном цикле", error)
        # Просим нажать Enter, чтобы окно не закрылось мгновенно.
        # Ctrl+D на этом вводе тоже должен завершать программу корректно.
        try:
            input("Нажмите Enter для продолжения...")
        except EOFError:
            # Ввод завершён (Ctrl+D) — выходим из цикла без ошибки.
            print("\n[Выход] Ввод завершён (EOF)")
            break

# ============================================================================
# День 10 — den_10_Kod.py (управление контекстом: разные стратегии, класс Agent)
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Не одна техника контекста, а НАБОР стратегий + переключатель между ними +
# честное сравнение на одном сценарии. Модель stateless, и запрос растёт как
# 1+2+3+…+N — день отвечает на это тремя обязательными стратегиями («без summary»):
#   1) Sliding Window — только последние N сообщений, старые ОТБРАСЫВАЮТСЯ
#      (удаление, не сжатие — уточнение Алексея Гладкова в чате курса);
#      → self.window (--window), _build_messages_sliding;
#   2) Sticky Facts / Key-Value Memory — блок фактов «ключ: значение» (цель,
#      ограничения, предпочтения, решения, договорённости), который обновляется
#      после КАЖДОГО сообщения пользователя отдельным служебным LLM-запросом
#      («сухая выжимка по шаблону», только новые факты — Dmitry Sevostianov);
#      в запрос идёт facts (system-сообщением) + «сырое» окно (Ivan Bazhenov);
#      → self.facts, _update_facts, _build_messages_facts, FACTS_FILE;
#   3) Branching — checkpoint в диалоге, ветки от одного места, независимое
#      продолжение, переключение; ветки хранятся в директории Branches/
#      (каждая — отдельный файл), активная ветка видна в приглашении ввода;
#      → self.branches, self.active_branch, branch_create/list/switch,
#      _build_messages_branching.
# Режимы compression/leveling предыдущего дня СОХРАНЕНЫ (задание говорит
# «минимум 3» — готовое не выбрасываем).
# Сравнение — команда /compare-strategies: сценарий «собираем ТЗ» (10–15 сообщений)
# прогоняется на каждой стратегии, печатается таблица по 4 критериям задания:
# качество, стабильность, расход токенов, удобство. ВАЖНО (урок предыдущего дня):
# обновление facts после каждого сообщения — дополнительный платный LLM-запрос,
# его токены учитываются отдельно (self.facts_usage) и честно показываются.
#
# Запуск:
#   python den_10/den_10_Kod.py --context sliding-window --memory session
#   python den_10/den_10_Kod.py --context facts --memory session
#   python den_10/den_10_Kod.py --context branching --memory session
#   python den_10/den_10_Kod.py --context compression --memory compressed  # из донора
# Внутри чата: /facts (блок фактов), /branch list|switch|new (ветки),
# /compare-strategies (сравнение трёх стратегий на сценарии «ТЗ»).
# ============================================================================

# 1. Импорты: os, sys, json, argparse, datetime, requests, dotenv --------------

# Импортируем модуль os для чтения переменных окружения и проверки файлов.
import os
import csv

# Импортируем модуль sys для настройки кодировки стандартного ввода.
import sys

# Импортируем модуль json для сохранения и загрузки контекста агента (День 10).
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
    description="Чат-бот Дня 10: набор стратегий управления контекстом (sliding-window / "
    "facts / branching + compression / leveling) и сравнение их на одном сценарии."
)

# Флаг --context: техника управления контекстом (по умолчанию sliding-window).
# День 10: добавлены facts (Sticky Facts / Key-Value Memory) и branching (ветки);
# старые choices сохранены — задание требует «минимум 3» стратегии, готовое не выбрасываем.
parser.add_argument(
    "--context",
    type=str,
    default="sliding-window",
    choices=["sliding-window", "compression", "leveling", "facts", "branching"],
    help="Техника контекста: sliding-window, compression, leveling, facts, branching.",
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

# Флаг --log: имя лог-файла (по умолчанию Den_10_log.md).
parser.add_argument(
    "--log",
    type=str,
    default="Den_10_log.md",
    help="Имя лог-файла.",
)

# Флаг --context-file: путь к JSON-файлу контекста (День 10).
parser.add_argument(
    "--context-file",
    type=str,
    default="den_10_context.json",
    help="JSON-файл контекста для сохранения/загрузки (по умолчанию den_10_context.json).",
)

# Флаг --fresh: начать новую сессию, игнорируя прошлый JSON-снимок (День 10).
# Легальный способ получить чистую сессию, не удаляя файл руками: снимок на диске
# остаётся нетронутым до ближайшего сохранения (/exit, Ctrl+C, Ctrl+D, /save).
parser.add_argument(
    "--fresh",
    action="store_true",
    help="Начать новую сессию: не загружать прошлый JSON-снимок (перезаписать его при сохранении).",
)

# Флаг --max-context-tokens: искусственный лимит контекстного окна (День 10).
# Реальное окно модели — 262K токенов, «сжигать» его живыми запросами незачем:
# лимит ставят маленьким (например, 60), чтобы показать переполнение дёшево.
parser.add_argument(
    "--max-context-tokens",
    type=int,
    default=None,
    help="Лимит токенов контекста для проверки перед отправкой (по умолчанию окно модели).",
)

# Флаг --max-tokens: верхний предел длины ответа модели (День 10).
# Уходит прямо в тело запроса API; позволяет дёшево резать исходящие токены.
parser.add_argument(
    "--max-tokens",
    type=int,
    default=None,
    help="Максимум токенов в ответе модели (по умолчанию без лимита).",
)

# Флаг --token-log: имя CSV-журнала роста токенов и стоимости (День 10).
parser.add_argument(
    "--token-log",
    type=str,
    default="den_10_tokens.csv",
    help="CSV-журнал токенов и стоимости по каждому обмену (по умолчанию den_10_tokens.csv).",
)

# Флаг --price-in: цена миллиона входящих токенов в рублях (День 10).
parser.add_argument(
    "--price-in",
    type=float,
    default=None,
    help="Цена 1M входящих токенов в рублях (по умолчанию из Step-3.5-Flash_params.md).",
)

# Флаг --price-out: цена миллиона исходящих токенов в рублях (День 10).
parser.add_argument(
    "--price-out",
    type=float,
    default=None,
    help="Цена 1M исходящих токенов в рублях (по умолчанию из Step-3.5-Flash_params.md).",
)

# --- Флаги Дня 10: настройки сжатия истории -----------------------------------

# Флаг --compress-every: порог автосжатия. Формулировка задания — «остальное
# заменяйте summary (например каждые 10 сообщений)», поэтому по умолчанию 10.
# В доноре порог был жёсткой константой (8); День 10 делает его настраиваемым,
# чтобы на одном коде показать и «каждые 10», и «каждые 3» (дёшево для тестов).
parser.add_argument(
    "--compress-every",
    type=int,
    default=None,
    help="Сжимать старые сообщения в саммари, когда вне окна накопилось N сообщений "
    "(по умолчанию 10 — как в задании).",
)

# Флаг --summary-word-limit: лимит длины саммари в СЛОВАХ (Ч7, Petr ограничивал 50).
# Считается не токенами: лимит формулируется в промпте сжатия, а не в параметрах
# API — так он влияет на текст, а не только обрезает ответ.
parser.add_argument(
    "--summary-word-limit",
    type=int,
    default=None,
    help="Максимум слов в саммари (по умолчанию 120; в чате курса тестировали 50).",
)

# Флаг --compress-temperature: температура отдельного запроса сжатия (Ч6).
# Ниже основной (0.2 против 1): саммари обязано быть фактичным, а не творческим;
# Roman Sokk отмечал, что температура сжатия заметно меняет результат.
parser.add_argument(
    "--compress-temperature",
    type=float,
    default=None,
    help="Температура запроса сжатия (по умолчанию 0.2 — стабильнее фактика).",
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
# День 10: стратегии facts и branching — тоже «лёгкие» режимы без сжатия, они
# совместимы с session-памятью (факты и ветки сами управляют контекстом), поэтому
# автоисправление для них НЕ срабатывает — иначе новые стратегии было бы не запустить.
if args.memory == "session" and args.context not in ("sliding-window", "facts", "branching"):
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

# Путь к JSON-файлу контекста (День 10): относительный путь фиксируется за
# каталогом скрипта, абсолютный — используется как есть.
if os.path.isabs(args.context_file):
    CONTEXT_FILE = args.context_file
else:
    CONTEXT_FILE = os.path.join(BASE_DIR, args.context_file)

# Путь к CSV-журналу токенов (День 10): та же схема — относительный путь
# фиксируется за каталогом скрипта, абсолютный используется как есть.
if os.path.isabs(args.token_log):
    TOKEN_LOG = args.token_log
else:
    TOKEN_LOG = os.path.join(BASE_DIR, args.token_log)

# --- Пути Дня 10: факты и ветки ------------------------------------------------

# Файл блока фактов (Sticky Facts): ключ → значение. Персистентен между сессиями,
# обновляется после каждого сообщения пользователя в режиме facts.
FACTS_FILE = os.path.join(BASE_DIR, "den_10_facts.json")

# Директория веток (Branching): каждая ветка — отдельный JSON-файл внутри.
# Требование пользователя: ветки хранятся отдельно, файл на ветку.
BRANCHES_DIR = os.path.join(BASE_DIR, "Branches")

# Имя ветки по умолчанию: создаётся автоматически при старте режима branching.
DEFAULT_BRANCH = "main"

# 4. Константы -----------------------------------------------------------------

# API endpoint RouterAI (OpenAI-совместимый).
URL = "https://routerai.ru/api/v1/chat/completions"

# Модель, через которую идут запросы.
MODEL = "stepfun/step-3.5-flash"

# Порог сжатия по умолчанию: когда вне окна накапливается >= N сообщений —
# запускаем сжатие. В доноре это была жёсткая константа (8); День 10 делает порог
# настраиваемым флагом --compress-every, а здесь хранит только значение по
# умолчанию — ровно 10, как в формулировке задания («например каждые 10 сообщений»).
COMPRESS_THRESHOLD = 10

# Лимит длины саммари в словах по умолчанию (используется, если флаг не задан).
SUMMARY_WORD_LIMIT = 120

# Температура запроса сжатия по умолчанию (используется, если флаг не задан).
COMPRESS_TEMPERATURE = 0.2

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
# День 10 (Ч6, Ч7): промпт стал ШАБЛОНОМ — в него подставляются язык переписки
# и лимит слов. Вывод из чата курса: Petr ограничивал саммари 50 словами, и
# саммари должно быть на языке переписки (иначе оно «съедает» смысл для
# последующих ответов). Плейсхолдеры заполняются в _compress_history через .format().
COMPRESS_PROMPT = (
    "Ты сжимаешь диалоги. Сделай краткое саммари ключевых фактов, решений и "
    "договорённостей. Пиши саммари на {language} языке, не более {word_limit} "
    "слов. Только саммари, без приветствий и комментариев."
)

# System prompt для служебного запроса обновления блока фактов (День 10, Sticky Facts).
# По чату курса (Dmitry Sevostianov): это «сухая выжимка по шаблону», а не суммаризация —
# модель возвращает ТОЛЬКО новые/изменённые факты в формате «ключ: значение», а если новых
# нет — пустой ответ (тогда блок не меняется и лишних токенов не тратится). Язык фактов =
# язык переписки (урок предыдущего дня).
FACTS_PROMPT = (
    "Ты извлекаешь факты из диалога для долговременной памяти агента. Выдели из последнего "
    "сообщения пользователя важные факты: цель, ограничения, предпочтения, решения, "
    "договорённости. Формат ответа — строки «ключ: значение», по одному факту на строку. "
    "Правила: пиши на {language} языке; верни ТОЛЬКО новые или изменившиеся факты (уже "
    "известные не повторяй); если новых фактов нет — верни пустой ответ. Без комментариев "
    "и приветствий."
)

# Таймаут запроса к API в секундах.
REQUEST_TIMEOUT = 30

# Список задержек между повторами при HTTP 429 (экспоненциальная: 2 → 4 → 8 сек).
RETRY_DELAYS = [2, 4, 8]

# Имя файла журнала ошибок: сюда пишется полный стек любой непредвиденной ошибки.
ERROR_LOG = os.path.join(BASE_DIR, "den_10_error.log")

# Версия формата JSON-снимка контекста (День 10): при изменении структуры
# в будущем старые снимки можно отличить по номеру версии. В версии 2 появился
# блок usage (накопленные токены и стоимость), снимки версии 1 грузаются без падения.
# В версии 3 добавлены настройки сжатия: порог --compress-every, лимит слов
# саммари и температура сжатия. Снимки версии 2 грузаются с дефолтами этих полей.
# В версии 4 добавлены данные Дня 10: блок фактов (facts), активная ветка
# (active_branch) и список веток (branching). Сами сообщения веток живут в файлах
# директории Branches/ — в снимок попадают только имя активной ветки и список.
# Снимки версии 3 грузаются с дефолтами новых полей.
CONTEXT_VERSION = 4

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

# Признаки того, что API сам отказал из-за переполнения контекста (День 10).
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
# Тот же шаблон с язык/лимит, что и общий COMPRESS_PROMPT, но с разной
# строгостью к сохранению фактов/задач/болтовни (идея leveled-memory).
COMPRESS_PROMPTS = {
    # Высокий слой: ключевые факты — сохраняем дословно, ничего не опускаем.
    "high": (
        "Ты сохраняешь ключевые факты о пользователе. Перечисли ВСЕ факты, имена, "
        "даты, цифры и договорённости из сообщений списком. Пиши на {language} языке, "
        "не более {word_limit} слов. Ничего не опускай и не перефразируй смысл. "
        "Только список, без приветствий и комментариев."
    ),
    # Средний слой: задачи и планы — сохраняем все, формулировки короче.
    "mid": (
        "Ты сохраняешь задачи и планы. Перечисли ВСЕ задачи, сроки и договорённости "
        "списком, кратко, но без потерь. Пиши на {language} языке, не более "
        "{word_limit} слов. Только список, без приветствий и комментариев."
    ),
    # Низкий слой: обычная переписка — сжимаем максимально сильно.
    "low": (
        "Ты сжимаешь переписку. Сделай предельно краткое саммари сути в 1-3 "
        "предложениях. Пиши на {language} языке, не более {word_limit} слов. "
        "Только саммари, без приветствий и комментариев."
    ),
}

# Сколько сообщений высокого/среднего слоя вне окна дополнительно попадает в
# запрос leveling (защита от бесконечного роста приоритетного блока).
PRIORITY_CAP = 6

# Известные внутренние имена стратегий контекста: нужны для проверки значений,
# прочитанных из JSON-снимка (мусор в снимке иначе уронит сборку запроса).
# День 10: добавлены facts и branching.
KNOWN_STRATEGIES = (
    "sliding_window",
    "history_compression",
    "context_leveling",
    "facts",
    "branching",
)

# Известные типы памяти: тоже проверяются при загрузке JSON-снимка.
KNOWN_MEMORY_TYPES = ("session", "compressed", "layered")

# Список известных slash-команд: нужен, чтобы нераспознанная строка, начинающаяся
# с «/», не уходила в LLM как обычный текст (лишние вызовы API, мусор в истории).
KNOWN_COMMANDS = (
    "/history",
    "/window",
    "/summary",
    "/compress",
    "/compare",
    "/compare-strategies",
    "/facts",
    "/branch",
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

# --- Валидация и эффективные значений флагов сжатия Дня 10 ---------------------
# Все три флага имеют default=None: «флаг не задан» отличается от «задан».
# Приоритет значения: явный флаг > значение из загруженного снимка > константа
# по умолчанию. Загрузка снимка (load_context_json) переопределит эти значения,
# только если флаг НЕ был задан в командной строке — иначе явный запуск молча
# затирался бы старым снимком.

# Валидация порога сжатия (если задан): 0 или меньше означали бы «сжимать после
# каждого сообщения», что обнулило бы окно и сожгло лишние токены.
if args.compress_every is not None and args.compress_every < 1:
    raise RuntimeError("Значение --compress-every должно быть больше нуля.")

# Валидация лимита слов саммари (если задан): 0 слов = пустое саммари = потеря контекста.
if args.summary_word_limit is not None and args.summary_word_limit < 1:
    raise RuntimeError("Значение --summary-word-limit должно быть больше нуля.")

# Валидация температуры сжатия (если задана): API принимает 0..2
# (Step-3.5-Flash_params.md).
if args.compress_temperature is not None and not 0 <= args.compress_temperature <= 2:
    raise RuntimeError("Значение --compress-temperature должно быть в диапазоне 0..2.")

# Эффективный порог автосжатия: флаг, иначе константа по умолчанию (10).
if args.compress_every is not None:
    COMPRESS_THRESHOLD = args.compress_every

# Эффективный лимит слов саммари: флаг, иначе константа (120).
if args.summary_word_limit is not None:
    SUMMARY_WORD_LIMIT = args.summary_word_limit

# Эффективная температура сжатия: флаг, иначе константа (0.2).
if args.compress_temperature is not None:
    COMPRESS_TEMPERATURE = args.compress_temperature


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


# Функция дозаписи строки обмена в CSV-журнал токенов (День 10).
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


# 5. Токен-функции: локальная оценка токенов (День 10) ---------------------------


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
                 price_out_per_m: float = None, compress_every: int = None,
                 summary_word_limit: int = None, compress_temperature: float = None):
        """system_prompt — роль агента;
        context_strategy — техника управления контекстом:
            "sliding_window", "history_compression", "context_leveling";
        memory_type — тип памяти:
            "session", "compressed", "layered";
        max_context_tokens — лимит контекста для проверки перед отправкой (День 10);
        max_tokens — лимит длины ответа модели (День 10);
        price_in_per_m / price_out_per_m — цены 1M токенов в рублях (День 10);
        compress_every — порог автосжатия в сообщениях (День 10, по умолчанию 10);
        summary_word_limit — лимит длины саммари в словах (День 10);
        compress_temperature — температура запроса сжатия (День 10)."""
        # Приводим имена флагов CLI к внутренним именам стратегий.
        # День 10: добавлены facts (Sticky Facts) и branching (ветки диалога).
        strategy_map = {
            "sliding-window": "sliding_window",
            "compression": "history_compression",
            "leveling": "context_leveling",
            "facts": "facts",
            "branching": "branching",
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

        # --- День 10: токен-учёт -------------------------------------------------
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

        # --- День 10: настройки сжатия истории --------------------------------
        # Порог автосжатия: сколько сообщений вне окна допустимо, прежде чем
        # сворачивать их в саммари. Приоритет: явный флаг > снимок > константа (10).
        self.compress_every = compress_every if compress_every is not None else COMPRESS_THRESHOLD

        # Лимит длины саммари в словах (уходит в текст промпта сжатия).
        self.summary_word_limit = summary_word_limit if summary_word_limit is not None else SUMMARY_WORD_LIMIT

        # Температура отдельного запроса сжатия (ниже основной — фактичнее).
        self.compress_temperature = compress_temperature if compress_temperature is not None else COMPRESS_TEMPERATURE

        # Флаги «значение задано ЯВНО при создании агента» (флаг CLI). Нужны
        # загрузчику снимка: он не должен затирать явную волю запуска старым
        # снимком. Храним их как поля, чтобы класс не зависел от глобального args.
        self.compress_every_explicit = compress_every is not None
        self.summary_word_limit_explicit = summary_word_limit is not None
        self.compress_temperature_explicit = compress_temperature is not None

        # День 10 (Ч8): отдельный накопитель токенов СЛУЖЕБНЫХ запросов сжатия.
        # Их токены уже входят в usage_total (они тоже стоят денег), но здесь они
        # учтены САМИ ПО СЕБЕ — чтобы /compare мог показать экономию ДВУМЯ строками:
        # «без учёта суммаризации» и «с её учётом». Без этого поля нельзя честно
        # сказать, окупается ли сжатие: сама суммаризация — платный запрос.
        self.summary_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
        }

        # --- День 10: Sticky Facts (стратегия facts) --------------------------
        # Блок фактов «ключ → значение»: цель, ограничения, предпочтения,
        # решения, договорённости. Обновляется после КАЖДОГО сообщения
        # пользователя служебным LLM-запросом (_update_facts).
        self.facts = {}

        # Если файл фактов уже существует (прошлые сессии) — загружаем его:
        # факты персистентны, это и есть «долговременная память» стратегии.
        if os.path.exists(FACTS_FILE):
            try:
                with open(FACTS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Берём только словари: битый/чужой файл не должен ронять чат.
                if isinstance(loaded, dict):
                    self.facts = loaded
            except (json.JSONDecodeError, OSError):
                # Битый файл фактов — начинаем с пустого блока, чат продолжается.
                print(f"[Факты] Файл фактов повреждён, начинаю с пустого блока: {FACTS_FILE}")

        # Отдельный накопитель токенов служебных запросов обновления фактов
        # (по образцу summary_usage): они входят в общую стоимость сессии, но
        # не подменяют «токены текущего запроса» — урок предыдущего дня (Ч8).
        self.facts_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
        }

        # Флаг «предупреждение о сбое обновления фактов уже показано»: чтобы не
        # спамить пользователя при каждом сообщении, если API недоступен.
        self.facts_warned = False

        # --- День 10: Branching (стратегия branching) -------------------------
        # Словарь веток: имя → путь к JSON-файлу ветки. Сами сообщения живут в
        # файлах директории Branches/ (требование пользователя), в памяти агента —
        # только карта веток и имя активной.
        self.branches = {}

        # Имя активной ветки (в ней ведётся диалог).
        self.active_branch = DEFAULT_BRANCH

        # Если выбран режим branching — готовим директорию и ветку main.
        if self.context_strategy == "branching":
            # Директория Branches/ создаётся, если её ещё нет (exist_ok — не падаем
            # при повторном запуске).
            os.makedirs(BRANCHES_DIR, exist_ok=True)

            # Ветка main — точка входа: создаём, если файла ещё нет.
            if not os.path.exists(self._branch_path(DEFAULT_BRANCH)):
                # Пустая ветка main: сообщений нет, родителя нет.
                self._save_branch(DEFAULT_BRANCH, [])

            # Регистрируем main в карте веток.
            self.branches[DEFAULT_BRANCH] = self._branch_path(DEFAULT_BRANCH)

    # Внутренний метод: учёт блока usage из ответа API (День 10).
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
        # Служебный запрос копим ОТДЕЛЬНО — для честной экономики сравнения
        # стратегий (урок предыдущего дня: суммаризация/факты сами стоят денег).
        # Это подмножество usage_total.
        else:
            self.summary_usage["prompt_tokens"] += normalized["prompt_tokens"]
            self.summary_usage["completion_tokens"] += normalized["completion_tokens"]
            self.summary_usage["total_tokens"] += normalized["total_tokens"]
            self.summary_usage["requests"] += 1

    # Публичный метод (День 10): токены ПОСЛЕДНЕГО запроса — то есть «токены текущего
    # запроса» из задания. Модель stateless, поэтому это весь отправленный контекст,
    # а не только набранная только что строка. None — если usage не приходил.
    def tokens_request(self):
        # Возвращаем входящие токены последнего обмена (или None).
        return self.last_usage.get("prompt_tokens")

    # Публичный метод (День 10): токены ВСЕЙ ИСТОРИИ диалога — накопительная сумма
    # входящих и исходящих по всем обменам сессии (с учётом загруженного снимка).
    def tokens_history(self):
        # Суммарный total_tokens с начала сессии.
        return self.usage_total["total_tokens"]

    # Публичный метод (День 10): токены ПОСЛЕДНЕГО ответа модели. None — если usage
    # не приходил (например, API его не отдаёт).
    def tokens_response(self):
        # Возвращаем исходящие токены последнего обмена (или None).
        return self.last_usage.get("completion_tokens")

    # Публичный метод (День 10): стоимость последнего обмена в рублях по тарифу
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

    # Публичный метод (День 10): стоимость всей сессии в рублях — «прайс» накопленного
    # контекста: каждый обмен оплачивался заново, поэтому сумма честная.
    def cost_total(self):
        # Та же формула, но по накопительным итогам сессии.
        return (
            self.usage_total["prompt_tokens"] * self.price_in_per_m
            + self.usage_total["completion_tokens"] * self.price_out_per_m
        ) / 1_000_000

    # Публичный метод (День 10, Ч8): стоимость ВСЕХ служебных запросов сжатия за сессию.
    # Нужна команде /compare, чтобы показать вторую строку экономики — «с учётом
    # суммаризации». Это та часть cost_total, которую «съело» само сжатие.
    def cost_summarization(self):
        # Та же формула тарифа, но по накопителю summary_usage.
        return (
            self.summary_usage["prompt_tokens"] * self.price_in_per_m
            + self.summary_usage["completion_tokens"] * self.price_out_per_m
        ) / 1_000_000

    # Публичный метод (День 10): стоимость ВСЕХ служебных запросов обновления
    # фактов за сессию. Нужна /compare-strategies, чтобы честно показать: в режиме
    # facts каждый обмен дороже — само извлечение фактов стоит денег.
    def cost_facts(self):
        # Та же формула тарифа, но по накопителю facts_usage.
        return (
            self.facts_usage["prompt_tokens"] * self.price_in_per_m
            + self.facts_usage["completion_tokens"] * self.price_out_per_m
        ) / 1_000_000

    # Внутренний метод: один запрос к LLM с повтором при HTTP 429.
    # Снаружи не вызывается — CLI работает только с публичными методами.
    # is_main=False помечает служебный запрос (сжатие саммари) для токен-учёта.
    def _ask_llm(self, messages, is_main=True, temperature=None):
        # Формируем тело запроса: модель и список сообщений.
        data = {
            "model": MODEL,
            "messages": messages,
        }

        # День 10: если задан --max-tokens, передаём его API — это верхний предел
        # генерации, самый дешёвый способ урезать дорогие исходящие токены.
        if self.max_tokens is not None:
            # Кладём лимит длины ответа в тело запроса.
            data["max_tokens"] = self.max_tokens

        # День 10 (Ч6): температура передаётся ТОЛЬКО для служебного запроса сжатия
        # (там нужна фактичность, self.compress_temperature = 0.2 по умолчанию).
        # Основной запрос остаётся без temperature — на дефолте API, как в доноре,
        # чтобы сравнение качества в /compare не съезжало из-за нового параметра.
        if temperature is not None:
            # Кладем температуру в тело запроса (API принимает 0..2).
            data["temperature"] = temperature

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

                # День 10: считываем блок usage ДО проверки choices — токены за этот
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
                # День 10: локальная оценка приблизительная, поэтому лимит не гарантирует
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

    # Стратегия контекста C: стратегия → инструкции → саммари → окно (строгий порядок).
    def _build_messages_leveling(self) -> list:
        # Стратегический слой, сообщение 1 — роль агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Стратегический слой, сообщение 2 — общие инструкции (не меняются).
        messages.append({"role": "system", "content": RULES_PROMPT})

        # Оперативный слой, часть 1: саммари старых сообщений (если оно есть).
        if self.summary:
            # Саммари едет после инструкций, чтобы агент «помнил» сжатый контекст.
            messages.append(
                {"role": "system", "content": f"Саммари более раннего диалога:\n{self.summary}"}
            )

        # Оперативный слой, часть 2: последние K сообщений диалога.
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

        # День 10: для facts вызываем стратегию «факты + окно».
        if self.context_strategy == "facts":
            # Возвращаем запрос, собранный стратегией Sticky Facts.
            return self._build_messages_facts()

        # День 10: для branching вызываем стратегию активной ветки.
        if self.context_strategy == "branching":
            # Возвращаем запрос, собранный из истории активной ветки.
            return self._build_messages_branching()

        # Если режим неизвестен — это ошибка конфигурации, сообщаем и падаем.
        raise ValueError(f"Неизвестный режим контекста: {self.context_strategy}")

    # Стратегия контекста Дня 10: Branching — запрос строится из истории АКТИВНОЙ
    # ветки. Ветка хранит ПОЛНУЮ свою историю (без сжатия — «без summary»): каждая
    # ветка независима, переключение подменяет историю целиком.
    def _build_messages_branching(self) -> list:
        # Начинаем с system-сообщения — роли агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Добавляем ВСЕ сообщения активной ветки: ветка и есть «контекст» этой
        # стратегии — пользователь сам управляет её размером через ветвление.
        messages.extend(
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.full_history
        )

        # Возвращаем готовый список сообщений для запроса.
        return messages

    # Стратегия контекста Дня 10: Sticky Facts / Key-Value Memory.
    # Запрос = system + «Важные факты» (если есть) + последние N сообщений «сырыми».
    # По чату курса (Ivan Bazhenov): окно едет НЕискажённым, факты — обогащение
    # промпта отдельным system-сообщением (Ч2).
    def _build_messages_facts(self) -> list:
        # Начинаем с system-сообщения — роли агента.
        messages = [{"role": "system", "content": self.system_prompt}]

        # Если блок фактов не пуст — добавляем его вторым system-сообщением.
        # Это и есть «долговременная память» стратегии: старые сообщения
        # отброшены, но ключевые данные живут в фактах.
        if self.facts:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Важные факты из диалога (ключ: значение):\n"
                        f"{self._format_facts()}"
                    ),
                }
            )

        # Добавляем последние N сообщений диалога (окно) «как есть» — без
        # каких-либо изменений: Ч2 требует «сырое» окно.
        messages.extend(
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.full_history[-self.window:]
        )

        # Возвращаем готовый список сообщений для запроса.
        return messages

    # Публичный метод (День 10): собирает ДВА варианта запроса для /compare.
    # Возвращает кортеж (messages_full, messages_compressed) для одного и того же
    # контрольного вопроса — чтобы сравнить качество ответа и расход токенов.
    #   messages_full     — «как было бы без сжатия»: system + ВЕСЬ диалог
    #                       (архив + активная история) + вопрос. Это верхняя граница
    #                       расхода: модель видит каждую старую реплику.
    #   messages_compressed — «как есть при сжатии»: system + саммари + окно + вопрос.
    #                       Старая часть свёрнута, поэтому запрос короче.
    # Метод НИЧЕГО не отправляет и не меняет состояние — только собирает списки.
    def build_compare_variants(self, question: str):
        # --- Вариант «до»: весь диалог целиком + контрольный вопрос ---
        full_messages = [{"role": "system", "content": self.system_prompt}]

        # Сначала архив (старые, уже свёрнутые в саммари сообщения) — в исходном
        # виде: так выглядит история, если бы сжатия никогда не было.
        for msg in self.archived:
            full_messages.append({"role": msg["role"], "content": msg["content"]})

        # Затем активная история (окно и всё, что ещё не сжато).
        for msg in self.full_history:
            full_messages.append({"role": msg["role"], "content": msg["content"]})

        # Контрольный вопрос про ранний контекст — одинаковый в обоих вариантах.
        full_messages.append({"role": "user", "content": question})

        # --- Вариант «после»: саммари вместо старой части + окно + тот же вопрос ---
        compressed_messages = [{"role": "system", "content": self.system_prompt}]

        # Саммари вторым system-сообщением (если оно уже есть).
        if self.summary:
            compressed_messages.append(
                {"role": "system", "content": f"Саммари более раннего диалога:\n{self.summary}"}
            )

        # Окно оперативных сообщений — ровно то, что пошло бы в compression-запрос.
        for msg in self.full_history[-self.window:]:
            compressed_messages.append({"role": msg["role"], "content": msg["content"]})

        # Тот же контрольный вопрос.
        compressed_messages.append({"role": "user", "content": question})

        # Возвращаем оба варианта.
        return full_messages, compressed_messages

    # Публичный метод (День 10): локальная оценка экономии для /compare (без API).
    # Считает токены обоих вариантов и переводит разницу в рубли по тарифу входящих
    # (разница — это входящие токены; исходящие в обоих вариантах примерно равны).
    # Возвращает словарь с цифрами для печати; авторитет — usage живого прогона.
    def estimate_compare(self, question: str):
        # Собираем два варианта запроса.
        full_messages, compressed_messages = self.build_compare_variants(question)

        # Локально оцениваем размер каждого запроса в токенах.
        full_tokens = estimate_messages_tokens(full_messages)
        compressed_tokens = estimate_messages_tokens(compressed_messages)

        # Экономия входящих токенов на одном обмене (может быть и отрицательной,
        # если саммари вышло длинным — это честный результат, не прячем его).
        saved_tokens = full_tokens - compressed_tokens

        # Переводим разницу входящих токенов в рубли по цене входящих.
        saved_rubles = (saved_tokens * self.price_in_per_m) / 1_000_000

        # Возвращаем набор цифр для обработчика команды.
        return {
            "full_tokens": full_tokens,
            "compressed_tokens": compressed_tokens,
            "saved_tokens": saved_tokens,
            "saved_rubles": saved_rubles,
            # Ч8: накопленная за сессию стоимость служебных запросов сжатия —
            # её /compare вычитает из экономии во второй строке экономики.
            "summarization_cost": self.cost_summarization(),
        }

    # Публичный метод (День 10): ОДИН запрос к LLM по готовому списку сообщений
    # БЕЗ изменения истории. Нужен живому /compare: отправляем два готовых варианта
    # запроса и сравниваем ответы, но диалог агента остаётся нетронутым
    # (иначе контрольный вопрос «пачкал» бы историю). Токены запроса при этом
    # честно попадают в usage_total — деньги списываются по-настоящему.
    def ask_once(self, messages):
        # Возвращаем текст ответа или None при ошибке (повторы при 429 внутри).
        return self._ask_llm(messages, is_main=True)

    # Общее сжатие старых сообщений в саммари (для B и C).
    # Возвращает текст нового саммари или None, если запрос не удался.
    # Внутреннее (День 10, Ч6): определяет язык переписки по старым сообщениям.
    # Простейшая эвристика без внешних библиотек: считаем кириллицу и латиницу.
    # Если кириллических букв больше — язык русский, иначе английский. Возвращает
    # слово для подстановки в промпт сжатия («русском» / «английском»).
    # --- День 10: Sticky Facts (стратегия facts) ------------------------------

    # Обновление блока фактов после сообщения пользователя. Служебный LLM-запрос
    # «по шаблону» (Ч3): модель возвращает только НОВЫЕ/изменённые факты в формате
    # «ключ: значение»; если новых нет — пустой ответ, блок не меняется.
    # Вызывается ТОЛЬКО в режиме facts (иначе лишние платные запросы).
    def _update_facts(self, user_message):
        # Определяем язык переписки — факты пишутся на языке диалога.
        language = self._detect_language(
            [{"role": "user", "content": user_message}]
        )

        # Заполняем шаблон промпта языком.
        system_prompt = FACTS_PROMPT.format(language=language)

        # Формируем служебный запрос: инструкция + уже известные факты (чтобы
        # модель не повторяла их) + новое сообщение пользователя.
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Уже известные факты (не повторяй их):\n"
                    f"{self._format_facts() or '(пока нет)'}\n\n"
                    f"Новое сообщение пользователя:\n{user_message}"
                ),
            },
        ]

        # Служебный запрос: is_main=False — токены пойдут в facts_usage, а не в
        # «токены текущего запроса»; температура низкая — фактичность важнее
        # творчества (урок предыдущего дня).
        answer = self._ask_llm(
            messages, is_main=False, temperature=self.compress_temperature
        )

        # Сбой API — факты просто не обновляются, чат продолжается. Предупреждение
        # печатаем один раз за серию сбоев, чтобы не спамить при каждом сообщении.
        if answer is None:
            if not self.facts_warned:
                print("[Факты] Не удалось обновить (API недоступен), продолжаю без обновления")
                self.facts_warned = True
            return

        # Серия сбоев закончилась — сбрасываем флаг предупреждения.
        self.facts_warned = False

        # Разбираем ответ построчно: «ключ: значение». Пустой ответ = новых фактов
        # нет (модель так и instructed в FACTS_PROMPT) — выходим без изменений.
        updated_keys = []
        for line in answer.splitlines():
            # Убираем пробелы и пропускаем пустые строки.
            line = line.strip()
            if not line:
                continue

            # Строка обязана содержать разделитель «:» — иначе это не факт.
            if ":" not in line:
                continue

            # Режем по ПЕРВОМУ двоеточию: в значении двоеточия допустимы.
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Пустой ключ или значение — мусорная строка, пропускаем.
            if not key or not value:
                continue

            # Мердж в блок фактов (новые и изменённые).
            self.facts[key] = value
            updated_keys.append(key)

        # Если ни одного факта не добавлено — сохранять файл не нужно.
        if not updated_keys:
            return

        # Сохраняем блок фактов в файл (перезапись целиком, UTF-8, читаемый вид).
        try:
            with open(FACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.facts, f, ensure_ascii=False, indent=2)
        except OSError as error:
            # Ошибка записи не роняет чат: факты остаются в памяти сессии.
            log_error("Сохранение файла фактов", error)
            print("[Факты] Не удалось сохранить файл фактов")
            return

        # Короткое уведомление: какие ключи добавлены/обновлены и сколько всего.
        print(
            f"[Факты] Обновлено: {', '.join(updated_keys)} "
            f"({len(self.facts)} фактов всего)"
        )

    # Форматирование блока фактов для подстановки в запрос (и для /facts).
    def _format_facts(self) -> str:
        # Пустой блок — пустая строка (вызывающий код подставит «(пока нет)»).
        if not self.facts:
            return ""

        # Каждая строка — «ключ: значение».
        return "\n".join(f"{key}: {value}" for key, value in self.facts.items())

    # --- День 10: Branching (стратегия branching) -----------------------------

    # Путь к файлу ветки по имени. Имя очищается от пробелов; вложенность и
    # обход директорий исключаются: разрешаем буквы/цифры/дефис/подчёркивание.
    def _branch_path(self, name: str) -> str:
        # Оставляем только безопасные символы имени файла.
        safe = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_")

        # Если после очистки имя пустое — используем запасное.
        if not safe:
            safe = "branch"

        # Файл ветки внутри директории Branches/.
        return os.path.join(BRANCHES_DIR, safe + ".json")

    # Сохранение ветки в её JSON-файл. messages — список сообщений ветки
    # (в формате истории агента: role/content/timestamp).
    def _save_branch(self, name: str, messages: list):
        # Собираем содержимое файла ветки: метаданные + сообщения.
        data = {
            # Имя ветки (как в карте веток).
            "name": name,
            # Дата создания (фиксируется при создании, при перезаписи не меняется —
            # поэтому читаем существующий файл, если он есть).
            "created": self._branch_created(name),
            # Родитель/checkpoint: от какой ветки ответвились (None у main).
            "parent": self.branches.get(name, {}).get("parent") if isinstance(self.branches.get(name), dict) else None,
            # Сообщения ветки — полная независимая история.
            "messages": messages,
        }

        # Пишем JSON с отступами: файл можно открыть и посмотреть глазами.
        with open(self._branch_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Дата создания ветки: из существующего файла (если есть) или текущая.
    def _branch_created(self, name: str) -> str:
        # Пробуем прочитать существующий файл ветки.
        try:
            with open(self._branch_path(name), "r", encoding="utf-8") as f:
                data = json.load(f)
            # Если дата есть — сохраняем её (перезапись не должна менять историю).
            if isinstance(data, dict) and data.get("created"):
                return data["created"]
        # Файла нет или он битый — это создание новой ветки.
        except (json.JSONDecodeError, OSError):
            pass

        # Возвращаем текущее время как дату создания.
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Загрузка ветки из файла. Возвращает список сообщений или None (файла нет /
    # битый JSON / неожиданная структура) — вызывающий код решает, что делать.
    def _load_branch(self, name: str):
        # Путь к файлу ветки.
        path = self._branch_path(name)

        # Нет файла — ветки не существует.
        if not os.path.exists(path):
            return None

        # Читаем и разбираем JSON; любая проблема — None (чат не падает).
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as error:
            # Сообщаем о битом файле: ветка не загружается, остальные работают.
            print(f"[Ветки] Файл ветки повреждён ({error}): {path}")
            return None

        # Структура обязана быть словарём со списком messages.
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            # Возвращаем сообщения ветки.
            return data["messages"]

        # Неожиданная структура — считаем файл битым.
        print(f"[Ветки] Неожиданная структура файла ветки: {path}")
        return None

    # Создание новой ветки от ТЕКУЩЕГО места диалога (checkpoint из задания:
    # «создайте 2 ветки от одного места»). Текущая ветка сохраняется в файл,
    # активной становится новая — диалог продолжается в ней. Возвращает True.
    def branch_create(self, name: str) -> bool:
        # Путь к файлу новой ветки.
        path = self._branch_path(name)

        # Ветка с таким именем уже существует — не перезаписываем чужую историю.
        if os.path.exists(path):
            # Сообщаем и отказываемся затирать.
            print(f"[Ветки] Ветка «{name}» уже существует, переключитесь: /branch switch {name}")
            return False

        # Сначала сохраняем текущую ветку в её файл (checkpoint не должен быть
        # только в памяти — иначе при выходе точка ветвления потеряется).
        self._save_branch(self.active_branch, list(self.full_history))

        # Регистрируем путь текущей ветки в карте (если ещё не зарегистрирована).
        self.branches[self.active_branch] = {"path": self._branch_path(self.active_branch)}

        # Копируем текущий диалог в новую ветку — это и есть checkpoint.
        self._save_branch(name, list(self.full_history))

        # Регистрируем новую ветку в карте с родителем (откуда ответвились).
        self.branches[name] = {"path": path, "parent": self.active_branch}

        # Активной становится НОВАЯ ветка: диалог продолжается в ней (задание:
        # «продолжите диалог в каждой ветке независимо»).
        self.active_branch = name

        # Сообщаем пользователю о создании с точкой ответвления.
        print(
            f"[Ветки] Создана ветка «{name}» от текущего места "
            f"(checkpoint: {len(self.full_history)} сообщений), продолжаю в ней"
        )

        # Успех.
        return True

    # Список веток для /branch list: имя, число сообщений, дата создания, активная.
    def branch_list(self) -> list:
        # Собираем информацию по всем JSON-файлам в директории веток.
        result = []

        # Если директории нет — веток нет (режим мог не инициализироваться).
        if not os.path.isdir(BRANCHES_DIR):
            # Возвращаем пустой список.
            return result

        # Перебираем файлы директории (только .json — это ветки).
        for filename in sorted(os.listdir(BRANCHES_DIR)):
            # Пропускаем не-JSON файлы.
            if not filename.endswith(".json"):
                continue

            # Имя ветки — имя файла без расширения.
            name = filename[:-5]

            # Читаем метаданные и сообщения (битый файл — помечаем и идём дальше).
            try:
                with open(os.path.join(BRANCHES_DIR, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                # Битая ветка видна в списке, но с пометкой.
                result.append({"name": name, "messages": -1, "created": "", "active": False})
                continue

            # Добавляем сводку по ветке.
            result.append(
                {
                    # Имя ветки.
                    "name": name,
                    # Число сообщений в ветке.
                    "messages": len(data.get("messages", [])),
                    # Дата создания.
                    "created": data.get("created", ""),
                    # Активна ли эта ветка сейчас.
                    "active": name == self.active_branch,
                }
            )

        # Возвращаем список сводок.
        return result

    # Переключение на другую ветку: текущая сохраняется, выбранная загружается.
    # Возвращает True при успехе (история агента подменена сообщениями ветки).
    def branch_switch(self, name: str) -> bool:
        # Переключение на текущую ветку — бессмысленная операция.
        if name == self.active_branch:
            # Сообщаем и не делаем ничего.
            print(f"[Ветки] Ветка «{name}» уже активна")
            return False

        # Загружаем целевую ветку из файла.
        messages = self._load_branch(name)

        # Ветки нет или файл битый — остаёмся на текущей ветке.
        if messages is None:
            # Подсказываем пользователю доступные ветки.
            print(f"[Ветки] Не удалось загрузить ветку «{name}». Доступны: /branch list")
            return False

        # Сначала сохраняем текущую ветку (ничего не теряем при переключении).
        self._save_branch(self.active_branch, list(self.full_history))

        # Подменяем активную историю сообщениями выбранной ветки.
        self.full_history = list(messages)

        # Меняем имя активной ветки.
        self.active_branch = name

        # Регистрируем путь в карте веток (для последующих сохранений).
        self.branches[name] = {"path": self._branch_path(name)}

        # Сообщаем пользователю об успешном переключении.
        print(
            f"[Ветки] Переключился на «{name}» "
            f"({len(self.full_history)} сообщений в ветке)"
        )

        # Успех.
        return True

    def _detect_language(self, messages) -> str:
        # Счётчики букв двух алфавитов.
        cyrillic = 0
        latin = 0

        # Проходим по всем текстам старых сообщений.
        for msg in messages:
            # Считаем символы каждого текста.
            for ch in msg.get("content", ""):
                # Кириллица (диапазон Unicode для русских букв, регистр не важен).
                if "а" <= ch.lower() <= "я" or ch.lower() == "ё":
                    cyrillic += 1
                # Латиница.
                elif "a" <= ch.lower() <= "z":
                    latin += 1

        # Кириллицы больше или она есть, а латиницы нет — считаем русский язык.
        if cyrillic >= latin and cyrillic > 0:
            return "русском"

        # Иначе — английский (в т.ч. пустой переписке: безопасный дефолт).
        return "английском"

    def _compress_history(self, old_messages, summary, prompt=None):
        # Собираем текст переписки из старых сообщений: «Роль: текст» построчно.
        transcript = "\n".join(
            f"{'Пользователь' if msg['role'] == 'user' else 'Агент'}: {msg['content']}"
            for msg in old_messages
        )

        # День 10 (Ч6): определяем язык переписки, чтобы саммари было на нём,
        # а не на языке промпта (иначе саммари «съедает» смысл для ответов).
        language = self._detect_language(old_messages)

        # День 10 (Ч6, Ч7): заполняем шаблон промпта языком и лимитом слов.
        # Для compressed-памяти берём общий COMPRESS_PROMPT, для layered —
        # послойный шаблон из COMPRESS_PROMPTS.
        template = prompt if prompt is not None else COMPRESS_PROMPT
        system_prompt = template.format(
            language=language, word_limit=self.summary_word_limit
        )


        # Формируем сообщения для запроса сжатия: system-промпт + задание.
        compress_messages = [
            # System-сообщение с ролью «сжимателя диалогов» (язык + лимит слов).
            {"role": "system", "content": system_prompt},
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
        # temperature=self.compress_temperature (Ч6): сжатие при 0.2 фактичнее,
        # чем при дефолтной температуре основного запроса.
        new_summary = self._ask_llm(
            compress_messages, is_main=False, temperature=self.compress_temperature
        )

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
    # Внутренний метод (День 10): проверка запроса на переполнение контекста ДО отправки.
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

        # День 10 (Sticky Facts): обновляем блок фактов после КАЖДОГО сообщения
        # пользователя — но ТОЛЬКО в режиме facts (в других режимах факты не
        # нужны, а служебный запрос стоит денег). Сбой обновления не влияет на
        # основной запрос: чат продолжается, факты обновятся в следующий раз.
        if self.context_strategy == "facts":
            self._update_facts(user_message)

        # Формируем запрос через диспетчер стратегий контекста.
        messages = self._build_messages()

        # День 10: проверяем переполнение ДО обращения к API. Реплику пользователя
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

        # День 10: обмен состоялся — увеличиваем счётчик обменов. Он нужен как номер
        # строки в CSV-журнале и как множитель в прогнозе стоимости.
        self.exchanges += 1

        # День 10: дозаписываем строку обмена в CSV-журнал токенов. Ошибка записи
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
            # Порог берём из self.compress_every (флаг --compress-every, по умолчанию 10).
            if outside_window >= self.compress_every:
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
                f.write("# Саммари диалога — День 10 (послойно)\n")
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
            f.write("# Саммари диалога — День 10\n")
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
    # повторные /save не создавали дублей.
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
            # Дописываем длину саммари в символах.
            text += f"; саммари: {len(self.summary)} символов"

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
    def get_summary(self) -> str:
        # Возвращаем текст саммари (пустая строка, если саммари нет).
        return self.summary

    # Статистика по слоям для команды /layers (только layered):
    # возвращает словарь {слой: {"total": всего, "in_window": в окне}}.
    def get_layers_stats(self) -> dict:
        # Индекс первого сообщения, которое ещё попало в окно.
        in_window_from = max(0, len(self.full_history) - self.window)

        # Собираем по каждому слою общее количество и количество в окне.
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
            }
            for layer in LAYER_ORDER
        }

    # --- День 10: JSON-персистентность контекста ------------------------------

    # Сохранение полного состояния агента в JSON-файл (ядро Дня 10).
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
            # Текст саммари (пустая строка, если сжатия не было).
            "summary": self.summary,
            # Счётчик вытесненных из окна сообщений (для sliding_window).
            "evicted_total": self.evicted_total,
            # День 10: накопительный токен-учёт сессии — чтобы после перезапуска
            # /cost показывал стоимость ВСЕГО диалога, а не только новой части.
            "usage_total": dict(self.usage_total),
            # День 10 (v3, Ч8): накопитель токенов служебных запросов сжатия —
            # подмножество usage_total, нужно для строки экономики /compare.
            "summary_usage": dict(self.summary_usage),
            # День 10 (v3): настройки сжатия — порог, лимит слов саммари, температура.
            # Пишем ПОЛЯ агента (в них уже учтён приоритет «явный флаг > снимок >
            # константа»), а не глобальные константы: снимок обязан отражать то,
            # что реально действовало в этой сессии.
            "compress_every": self.compress_every,
            "summary_word_limit": self.summary_word_limit,
            "compress_temperature": self.compress_temperature,
            # День 10 (v4): блок фактов — персистентен и в файле FACTS_FILE, но
            # дублируем в снимок: снимок — полный слепок сессии «как была».
            "facts": dict(self.facts),
            # День 10 (v4): накопитель токенов служебных запросов обновления фактов.
            "facts_usage": dict(self.facts_usage),
            # День 10 (v4): ветки — только ИМЯ активной и список имён; сами сообщения
            # живут в файлах директории Branches/ (требование пользователя), дублировать
            # их в снимок не нужно.
            "active_branch": self.active_branch,
            "branches": sorted(self.branches.keys()),
        }

        # Открываем JSON-файл на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем снимок: ensure_ascii=False — кириллица остаётся читаемой,
            # indent=2 — файл можно открыть и посмотреть глазами.
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # Загрузка состояния агента из JSON-файла (ядро Дня 10).
    # Возвращает словарь со статистикой загрузки или None, если файла нет
    # или он повреждён — в обоих случаях программа продолжает работу.
    def load_context_json(self, filepath: str):
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

        # Начинаем блок проверки структуры снимка.
        try:
            # Восстанавливаем режимы и окно из снимка.
            self.context_strategy = snapshot["context_strategy"]
            # Тип памяти из снимка.
            self.memory_type = snapshot["memory_type"]
            # Размер окна из снимка.
            self.window = snapshot["window"]

            # Восстанавливаем историю: каждая запись должна быть словарём
            # с role и content; timestamp может отсутствовать в старых снимках.
            restored_history = []
            # Перебираем записи активной истории из снимка.
            for msg in snapshot.get("full_history", []):
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

            # Восстанавливаем счётчик вытесненных сообщений.
            self.evicted_total = snapshot.get("evicted_total", 0)

            # День 10: восстанавливаем накопительный токен-учёт. Снимки версии 1
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

            # День 10 (v3, Ч8): восстанавливаем накопитель токенов суммаризации.
            # Снимки v1/v2 этого блока не содержат — остаёмся на нулях (честно).
            saved_summary_usage = snapshot.get("summary_usage") or {}
            try:
                self.summary_usage = {
                    "prompt_tokens": int(saved_summary_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(saved_summary_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(saved_summary_usage.get("total_tokens", 0) or 0),
                    "requests": int(saved_summary_usage.get("requests", 0) or 0),
                }
            except (ValueError, TypeError):
                self.summary_usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "requests": 0,
                }

            # День 10 (v3): восстанавливаем настройки сжатия из снимка, но НЕ затираем
            # то, что пользователь явно задал флагом запуска: приоритет такой —
            # явный флаг > снимок > константа по умолчанию. Снимки версии 2 этих
            # полей не содержат: тогда поля агента остаются как после разбора флагов.
            if (not self.compress_every_explicit
                    and snapshot.get("compress_every") is not None):
                # Порог обязан быть >= 1, иначе окно схлопнется; приводим к int.
                try:
                    self.compress_every = max(1, int(snapshot["compress_every"]))
                # Мусор в поле — оставляем значение из флагов/дефолт.
                except (ValueError, TypeError):
                    pass

            # Лимит слов саммари — тем же способом.
            if (not self.summary_word_limit_explicit
                    and snapshot.get("summary_word_limit") is not None):
                try:
                    self.summary_word_limit = max(1, int(snapshot["summary_word_limit"]))
                except (ValueError, TypeError):
                    pass

            # Температура сжатия: дополнительно проверяем диапазон API 0..2.
            if (not self.compress_temperature_explicit
                    and snapshot.get("compress_temperature") is not None):
                try:
                    saved_temp = float(snapshot["compress_temperature"])
                    # В диапазон приводим отсечением: вне 0..2 API вернул бы ошибку.
                    self.compress_temperature = min(2.0, max(0.0, saved_temp))
                except (ValueError, TypeError):
                    pass

            # День 10 (v4): восстанавливаем блок фактов из снимка (если есть и это
            # словарь). Файл FACTS_FILE уже загружен в __init__; снимок может быть
            # новее файла — берём из снимка, он отражает последний выход из чата.
            saved_facts = snapshot.get("facts")
            if isinstance(saved_facts, dict):
                # Мердж: снимок дополняет/обновляет то, что было в файле.
                self.facts.update(saved_facts)

            # День 10 (v4): восстанавливаем накопитель токенов обновления фактов
            # (по образцу summary_usage; снимки v1–v3 этого поля не содержат).
            saved_facts_usage = snapshot.get("facts_usage") or {}
            try:
                self.facts_usage = {
                    "prompt_tokens": int(saved_facts_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(saved_facts_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(saved_facts_usage.get("total_tokens", 0) or 0),
                    "requests": int(saved_facts_usage.get("requests", 0) or 0),
                }
            except (ValueError, TypeError):
                # Мусор в поле — остаёмся на нулях, диалог продолжается.
                self.facts_usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "requests": 0,
                }

            # День 10 (v4): восстанавливаем активную ветку (только в режиме branching).
            # Сами сообщения веток грузятся из файлов Branches/ при branch_switch.
            if self.context_strategy == "branching":
                # Имя активной ветки из снимка (если валидно).
                saved_active = snapshot.get("active_branch")
                if isinstance(saved_active, str) and saved_active:
                    # Активной становится сохранённая ветка.
                    self.active_branch = saved_active

                # Регистрируем сохранённые имена веток в карте (пути вычислим по
                # требованию); файлы могли быть удалены — branch_switch это учтёт.
                saved_branches = snapshot.get("branches")
                if isinstance(saved_branches, list):
                    # Каждое имя — строка → путь через _branch_path.
                    for branch_name in saved_branches:
                        # Только строки регистрируем.
                        if isinstance(branch_name, str) and branch_name:
                            # Регистрация пути ветки в карте.
                            self.branches[branch_name] = {
                                "path": self._branch_path(branch_name)
                            }

            # Если снимок старше текущего формата — предупреждаем, но НЕ падаем:
            # недостающие поля (v1 — usage, v2 — настройки сжатия Дня 10) подставляются
            # дефолтами, диалог продолжается.
            snapshot_version = snapshot.get("version", 1)
            if snapshot_version < CONTEXT_VERSION:
                # Сообщение не критичное: диалог продолжается, просто часть
                # накопленных данных прошлой сессии неизвестна.
                print(
                    f"[Память] Снимок старого формата (v{snapshot_version}, "
                    f"текущий v{CONTEXT_VERSION}): недостающие поля возьму по умолчанию, "
                    "накопленные токены прошлой сессии могут быть не восстановлены"
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
            # Счётчик вытеснений обнулён.
            self.evicted_total = 0
            # Загрузки не было.
            return None

        # Собираем статистику загрузки для сообщения пользователю.
        stats = {
            # Сколько сообщений восстановлено в активную историю.
            "loaded": len(self.full_history),
            # Длина восстановленного саммари в символах.
            "summary_length": len(self.summary),
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


# Обработчик /facts: печать блока фактов (День 10, стратегия facts).
def cmd_facts(agent):
    # Форматируем блок фактов через агентский метод.
    facts_text = agent._format_facts()

    # Если фактов нет — сообщаем об этом.
    if not facts_text:
        # Печатаем сообщение о пустом блоке.
        print("[Факты] Фактов пока нет (обновляются после каждого сообщения)\n")
    # Иначе показываем весь блок «ключ: значение».
    else:
        # Печатаем блок и пустую строку для читаемости.
        print(f"[Факты]\n{facts_text}\n")


# Обработчик /branch (День 10, стратегия branching).
# Форматы (требования пользователя): /branch list — просмотр веток;
# /branch switch <имя> — переключение; /branch new <имя> — создание от текущего места.
def cmd_branch(agent, parts):
    # Без аргумента — печатаем подсказку по формату команды.
    if not parts:
        # Подсказка со всеми тремя подкомандами.
        print(
            "[Ветки] Использование:\n"
            "  /branch list            — список веток (активная помечена *)\n"
            "  /branch switch <имя>    — переключиться на ветку\n"
            "  /branch new <имя>       — создать ветку от текущего места\n"
        )
        return

    # Первая часть — подкоманда.
    subcommand = parts[0].strip().lower()

    # /branch list: таблица веток с пометкой активной.
    if subcommand == "list":
        # Получаем сводки по всем веткам у агента.
        branches = agent.branch_list()

        # Если веток нет (директория пуста) — сообщаем.
        if not branches:
            # Сообщение о пустом списке.
            print("[Ветки] Веток нет (директория Branches пуста)\n")
            return

        # Печатаем каждую ветку: * для активной, имя, сообщения, дата.
        for branch in branches:
            # Звёздочка у активной ветки.
            marker = "*" if branch["active"] else " "

            # Битая ветка (messages = -1) — особая строка.
            if branch["messages"] < 0:
                # Предупреждение о повреждённом файле.
                print(f"  {marker} {branch['name']} (ФАЙЛ ПОВРЕЖДЁН)")
                continue

            # Обычная строка: маркер, имя, число сообщений, дата создания.
            created = f", создана {branch['created']}" if branch["created"] else ""
            print(f"  {marker} {branch['name']} ({branch['messages']} сообщений{created})")

        # Пустая строка для читаемости.
        print()

    # /branch switch <имя>: переключение на выбранную ветку.
    elif subcommand == "switch":
        # Имя ветки — второй аргумент; без него — подсказка.
        if len(parts) < 2:
            # Подсказка по формату.
            print("[Ветки] Укажите имя ветки: /branch switch <имя>\n")
            return

        # Переключение выполняет агент (сохранит текущую, загрузит выбранную).
        agent.branch_switch(parts[1].strip())

        # Пустая строка после результата (сообщение печатает агент).
        print()

    # /branch new <имя>: создание ветки от текущего места (checkpoint).
    elif subcommand == "new":
        # Имя ветки — второй аргумент; без него — подсказка.
        if len(parts) < 2:
            # Подсказка по формату.
            print("[Ветки] Укажите имя ветки: /branch new <имя>\n")
            return

        # Создание выполняет агент (сохранит текущую, скопирует checkpoint,
        # активирует новую).
        agent.branch_create(parts[1].strip())

        # Пустая строка после результата.
        print()

    # Неизвестная подкоманда — подсказка.
    else:
        # Сообщаем о неверной подкоманде и показываем формат.
        print(f"[Ветки] Неизвестная подкоманда «{subcommand}». См. /branch\n")


# Обработчик /layers: статистика по слоям (только для layered).
def cmd_layers(agent):
    # Сначала общая картина контекста (окно, порог, слои, саммари).
    print(agent.get_context_summary())

    # Статистику считает сам агент, CLI только печатает.
    stats = agent.get_layers_stats()

    # Перебираем слои в порядке важности: high, mid, low.
    for layer in LAYER_ORDER:
        # Печатаем статистику слоя: всего и сколько из них в окне.
        print(f"[Слои] {layer}={stats[layer]['total']} (в окне: {stats[layer]['in_window']})")

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

    # Находим изменённое сообщение, чтобы показать результат пользователю.
    user_messages = [msg for msg in agent.get_history() if msg["role"] == "user"]

    # Берём сообщение пользователя по номеру (1 — последнее).
    target = user_messages[-number]

    # Сообщаем пользователю об успешной смене слоя.
    print(f"[Слой] Сообщение изменено: {target['content'][:50]} → {parts[2]}\n")


# Обработчик /compress: принудительное сжатие (для compression и leveling).
def cmd_compress(agent):
    # Сжатие выполняет агент: сворачивает все активные сообщения в саммари.
    agent.compress()


# Обработчик /compress on|off (День 10, Ч5): включает/выключает сжатие НА ЛЕТУ.
# Petr в чате курса просил именно переключатель режима, а не только ручное /compress.
# Реализация: переключаем стратегию контекста агента между sliding_window (сжатие
# ВЫКЛ — старое просто вытесняется) и history_compression (сжатие ВКЛ — старое
# сворачивается в саммари). История при этом НЕ теряется: сообщения остаются в
# full_history, меняется только то, КАК они попадают в следующий запрос.
def cmd_compress_toggle(agent, state):
    # Нормализуем аргумент команды к нижнему регистру.
    state = state.strip().lower()

    # Запоминаем, какой стратегия была ДО переключения (для печати «было → стало»).
    was = agent.context_strategy

    # Команда «on»: включаем сжатие — стратегия history_compression.
    if state == "on":
        # Переключаем стратегию агента на сжатие истории.
        agent.context_strategy = "history_compression"
        # Подбираем человекочитаемое слово о текущем состоянии.
        verdict = "ВКЛЮЧЕНО (history_compression)"
    # Команда «off»: выключаем сжатие — стратегия sliding_window (окно «как есть»).
    elif state == "off":
        # Переключаем стратегию агента на скользящее окно.
        agent.context_strategy = "sliding_window"
        # Слово о состоянии.
        verdict = "ВЫКЛЮЧЕНО (sliding_window)"
    # Любой другой аргумент — подсказка, состояние не меняем.
    else:
        # Говорим, как правильно пользоваться командой.
        print("[Сжатие] Использование: /compress on  или  /compress off\n")
        return

    # Считаем размер запроса «как есть» (окно) и «со сжатием» (саммари + окно),
    # чтобы показать эффект переключения в токенах прямо сейчас, без API.
    full_tokens = estimate_messages_tokens(agent._build_messages())

    # Печатаем результат переключения и текущий размер формируемого запроса.
    print(
        f"[Сжатие] {verdict} (было: {was}). "
        f"Размер следующего запроса сейчас: ~{full_tokens} токенов. "
        "История сохранена целиком.\n"
    )


# Обработчик /compare (День 10, ядро дня): качество и расход «до/после» сжатия.
# Один контрольный вопрос про РАННИЙ контекст задаётся в двух вариантах запроса:
#   «до»  — вся история целиком (как было бы без сжатия);
#   «после» — саммари + окно (как есть при сжатии).
# Печатаем оба ответа (сравнение качества) и экономию токенов/рублей (сравнение
# расхода). Ч8: экономию показываем ДВУМЯ строками — без учёта суммаризации и с её
# учётом, плюс оговорка про сброс prompt-cache. Живые запросы — только после «y».
def cmd_compare(agent):
    # Контрольный вопрос: просим вспомнить самое раннее сообщение (то, что могло
    # уже уйти в саммари). Если саммари потеряло деталь — это видно по ответу.
    question = "Во что мы договорились играть в самом начале нашего разговора? Ответь кратко."

    # Собираем два варианта запроса и локальную оценку (без обращения к API).
    full_messages, compressed_messages = agent.build_compare_variants(question)
    est = agent.estimate_compare(question)

    # Печатаем локальную оценку расхода — она доступна всегда, даже без API.
    print("\n[Сравнение] Локальная оценка запроса (без API):")
    print(f"  ДО  (вся история): ~{est['full_tokens']} токенов")
    print(f"  ПОСЛЕ (саммари+окно): ~{est['compressed_tokens']} токенов")

    # Экономия входящих токенов на одном обмене (может быть отрицательной — честно).
    print(f"  Экономия на одном запросе: ~{est['saved_tokens']} токенов")

    # --- Ч8: экономика ДВУМЯ строками ----------------------------------------
    # Строка 1: экономия только от укорочения запроса (без учёта суммаризации).
    print(
        f"  Экономика БЕЗ учёта суммаризации: ~{est['saved_rubles']:.6f} ₽ на запросе"
    )

    # Строка 2: та же экономия минус стоимость ВСЕХ служебных запросов сжатия за сессию.
    net = est["saved_rubles"] - est["summarization_cost"]
    print(
        f"  Экономика С учётом суммаризации (само сжатие стоило "
        f"~{est['summarization_cost']:.6f} ₽ за сессию): ~{net:.6f} ₽ на запросе"
    )

    # Оговорка про prompt-cache (вывод из чата курса): сжатие меняет префикс запроса,
    # поэтому кэш промпта сбрасывается — фактическая экономия может быть меньше расчётной.
    print(
        "  Примечание: сжатие меняет начало запроса, поэтому prompt-кэш провайдера\n"
        "  сбрасывается — реальная экономия может быть ниже расчётной."
    )

    # Спрашиваем про живой прогон: тратятся реальные деньги, нужно явное «y».
    answer = input("\nСделать ЖИВОЕ сравнение ответов (2 запроса к API)? (y/N): ")

    # Живой режим только при явном «y».
    if answer.strip().lower() != "y":
        # Без согласия ограничиваемся локальной оценкой.
        print("[Сравнение] Живые запросы пропущены. Локальной оценки достаточно для вывода.\n")
        return

    # Живой прогон: отправляем оба варианта одним и тем же контрольным вопросом.
    print("[Сравнение] Отправляю запрос «ДО» (вся история)...")
    answer_full = agent.ask_once(full_messages)
    # Фиксируем usage первого живого запроса (до второго, иначе перезатрётся).
    full_usage = dict(agent.last_usage)

    print("[Сравнение] Отправляю запрос «ПОСЛЕ» (саммари + окно)...")
    answer_compressed = agent.ask_once(compressed_messages)
    # Фиксируем usage второго живого запроса.
    compressed_usage = dict(agent.last_usage)

    # --- Печать качества: оба ответа рядом -----------------------------------
    print("\n[Сравнение] КАЧЕСТВО ответов:")
    print(f"  ДО:     {answer_full if answer_full is not None else '(ошибка API)'}")
    print(f"  ПОСЛЕ:  {answer_compressed if answer_compressed is not None else '(ошибка API)'}")

    # --- Печать расхода по ФАКТИЧЕСКИМ usage (авторитетнее локальной оценки) ---
    print("\n[Сравнение] РАСХОД по факту (usage API):")

    # Форматируем входящие токены каждого варианта («нет данных», если usage не пришёл).
    full_in = full_usage.get("prompt_tokens")
    comp_in = compressed_usage.get("prompt_tokens")
    full_in_str = full_in if full_in is not None else "нет данных"
    comp_in_str = comp_in if comp_in is not None else "нет данных"

    print(f"  ДО:     входящих токенов: {full_in_str}")
    print(f"  ПОСЛЕ:  входящих токенов: {comp_in_str}")

    # Фактическая экономия входящих токенов (если оба usage пришли).
    if full_in is not None and comp_in is not None:
        saved_live = full_in - comp_in
        saved_live_rubles = (saved_live * agent.price_in_per_m) / 1_000_000
        print(f"  Фактическая экономия на запросе: {saved_live} токенов (~{saved_live_rubles:.6f} ₽)")
    # Один из usage не пришёл — фактическую экономию не выдумываем.
    else:
        print("  Фактическую экономию не посчитать: API не прислал usage по одному из запросов.")

    # Пустая строка для читаемости.
    print()


# Обработчик /save: ручное сохранение контекста в JSON (День 10).
def cmd_save_context(agent):
    # Снимок состояния делает сам агент; CLI только указывает файл.
    agent.save_context_json(CONTEXT_FILE)

    # Сообщаем пользователю, куда сохранён контекст.
    print(f"[Память] Контекст сохранён: {CONTEXT_FILE}\n")


# Обработчик /tokens: три счётчика токенов + локальная оценка (День 10).
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
    if agent.full_history:
        # Берём последнее сообщение истории.
        last = agent.full_history[-1]

        # Оцениваем его текст локально.
        local = estimate_tokens(last.get("content", ""))

        # Печатаем оценку с пометкой «локальная».
        print(f"[Токены] Локальная оценка последнего сообщения: ~{local}")
    # Пустая история — оценивать нечего.
    else:
        # Сообщаем, что история пуста.
        print("[Токены] История пуста — локальная оценка нечего считать")

    # Пустая строка для читаемости.
    print()


# Обработчик /scenario: сравнение трёх сценариев расхода токенов (День 10).
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


# Обработчик /compare-strategies (День 10, ядро дня): сравнение трёх стратегий
# управления контекстом на ОДНОМ сценарии («собираем ТЗ, 10–15 сообщений»). 
# Сценарий генерируется ЛОКАЛЬНО (детерминизм: все стратегии получают одинаковые
# сообщения). Прогон — на временных экземплярах Agent с артефактами в /tmp,
# чтобы не портить сессию пользователя. Сравнение по 4 критериям задания:
# качество, стабильность, расход токенов, удобство. Живой API — только после «y».
def cmd_compare_strategies(agent):
    # --- Сценарий «собираем ТЗ»: 12 сообщений с фактами -----------------------
    # Каждое сообщение несёт конкретную деталь ТЗ; ранние детали (1–4) — то, что
    # sliding-window отбросит: по ним и проверяем стабильность стратегий.
    scenario = [
        "Собираем ТЗ. Цель: интернет-магазин косметики.",
        "Целевая аудитория: женщины 25–45 лет.",
        "Платформа: мобильное приложение на iOS и Android.",
        "Ключевая функция: подбор косметики по типу кожи.",
        "Нужна корзина и оплата картой.",
        "Дизайн: минимализм, светлая тема.",
        "Интеграция с 1С обязательна.",
        "Срок запуска: 1 октября.",
        "Бюджет: до 1,5 млн рублей.",
        "Хостинг: облачный, российский.",
        "Поддержка 24/7 на первом месяце.",
        "Финализируем: согласуем все пункты ТЗ?",
    ]

    # Контрольный вопрос про РАННИЕ детали (то, что sliding-window уже отбросил).
    control_question = "Какая целевая аудитория и какой срок запуска в нашем ТЗ?"

    # Ключевые детали, которые обязаны сохраниться (для проверки стабильности).
    key_facts = ["25–45", "1 октября"]

    # Спрашиваем про живой прогон: тратятся реальные деньги, нужно явное «y».
    answer = input("Сделать ЖИВОЙ прогон сценария на 3 стратегиях (много запросов)? (y/N): ")

    # Живой режим только при явном «y».
    live = answer.strip().lower() == "y"

    # Без согласия — печатаем локальную оценку и описание механики.
    if not live:
        # Заголовок локального режима.
        print("\n[Сравнение] Локальная оценка (без API):")

        # Для каждой стратегии считаем локальную оценку запроса на ПОСЛЕДНЕМ
        # сообщении сценария (когда история самая длинная).
        for strategy in ("sliding-window", "facts", "branching"):
            # Временный агент стратегии с артефактами в /tmp (не трогаем день).
            probe = Agent(
                "Ты помогаешь собирать ТЗ.",
                context_strategy=strategy,
                memory_type="session",
                window=4,
            )

            # Прогоняем сценарий локально: только история, без запросов к API.
            for message in scenario:
                # Добавляем сообщение в историю (как send_message, но без API).
                probe.full_history.append(
                    {"role": "user", "content": message, "timestamp": "test"}
                )

            # Собираем запрос последнего обмена и оцениваем его локально.
            estimated = estimate_messages_tokens(probe._build_messages())

            # Печатаем оценку и описание поведения стратегии.
            print(
                f"  {strategy}: ~{estimated} токенов на последнем запросе; "
                + _strategy_behavior(strategy)
            )

        # Оговорка про служебные запросы фактов (урок предыдущего дня).
        print(
            "  Примечание: в режиме facts каждое сообщение пользователя = дополнительный\n"
            "  служебный запрос обновления фактов (платный) — в живом прогоне это видно\n"
            "  в колонке расхода."
        )

        # Подсказка про живой режим.
        print("  Для фактического сравнения ответов повторите команду и ответьте y.\n")
        return

    # --- Живой прогон: три временных агента, одинаковый сценарий ---------------
    print("\n[Сравнение] ЖИВОЙ прогон сценария (12 сообщений) на каждой стратегии...")

    # Результаты по каждой стратегии: ответ на контрольный вопрос + usage.
    results = {}

    # Перебираем три обязательные стратегии задания.
    for strategy in ("sliding-window", "facts", "branching"):
        # Временный агент стратегии; артефакты — в /tmp (изолированно от дня).
        probe = Agent(
            "Ты помогаешь собирать ТЗ. Отвечай кратко.",
            context_strategy=strategy,
            memory_type="session",
            window=4,
        )

        # Прогоняем сценарий: каждое сообщение через send_message (с факами/ветками,
        # как в реальной работе стратегии).
        for message in scenario:
            # Отправка реплики: внутри обновление фактов (для facts) и т.д.
            probe.send_message(message)

        # Контрольный вопрос — тоже через send_message (полный обмен).
        answer_text = probe.send_message(control_question)

        # Фиксируем результат: ответ и накопленный расход сессии.
        results[strategy] = {
            # Ответ на контрольный вопрос (или заглушка при ошибке API).
            "answer": answer_text if answer_text is not None else "(ошибка API)",
            # Входящие токены последнего (контрольного) запроса.
            "last_prompt": probe.tokens_request(),
            # Накопительный расход всей сессии (все обмены + служебные).
            "total_tokens": probe.tokens_history(),
            # Стоимость служебных запросов обновления фактов.
            "facts_cost": probe.cost_facts(),
        }

        # Прогресс для пользователя.
        print(f"  {strategy}: готово")

    # --- Печать сравнения по 4 критериям задания -------------------------------
    print("\n[Сравнение] КАЧЕСТВО (ответы на контрольный вопрос):")
    # Ответы каждой стратегии на один и тот же вопрос.
    for strategy, result in results.items():
        # Печатаем ответ (обрезаем длинные до 200 символов).
        print(f"  {strategy}: {result['answer'][:200]}")

    print("\n[Сравнение] СТАБИЛЬНОСТЬ (сохранение ключевых деталей):")
    # Для каждой стратегии проверяем вхождения ключевых фактов в ответ.
    for strategy, result in results.items():
        # Считаем, сколько ключевых деталей найдено в ответе.
        found = sum(1 for fact in key_facts if fact in result["answer"])
        # Печатаем вердикт: найдено из скольких.
        print(f"  {strategy}: {found}/{len(key_facts)} ключевых деталей в ответе")

    print("\n[Сравнение] РАСХОД ТОКЕНОВ (вся сессия, по usage API):")
    # Накопительный расход каждой стратегии.
    for strategy, result in results.items():
        # Печатаем общий расход и, для facts, стоимость служебных запросов.
        facts_note = (
            f" (из них обновление фактов: {result['facts_cost']:.6f} ₽)"
            if strategy == "facts" and result["facts_cost"] is not None
            else ""
        )
        # Строка расхода.
        print(f"  {strategy}: {result['total_tokens']} токенов{facts_note}")

    print("\n[Сравнение] УДОБСТВО (поведение для пользователя):")
    # Описание поведения каждой стратегии.
    for strategy in results:
        # Печатаем описание.
        print(f"  {strategy}: {_strategy_behavior(strategy)}")

    # Пустая строка для читаемости.
    print()


# Описание поведения стратегии для критерия «удобство» (День 10).
def _strategy_behavior(strategy: str) -> str:
    # Возвращаем короткое человекочитаемое описание по имени стратегии.
    if strategy == "sliding-window":
        # Окно: просто и без настроек, но старое теряется.
        return "ничего настраивать не нужно, но ранние детали теряются из окна"
    # Факты: автоматически, но с доп. запросами.
    if strategy == "facts":
        # Описание фактов.
        return "факты обновляются автоматически, ранние детали сохраняются, но каждый обмен дороже"
    # Ветки: ручное управление.
    if strategy == "branching":
        # Описание веток.
        return "полный контроль через /branch (list/switch/new), но переключение вручную"
    # Незнакомая стратегия — нейтральное описание.
    return "особого поведения нет"


# Обработчик /cost: стоимость обмена, сессии и прогноз на 100 обменов (День 10).
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


# Обработчик /load: ручная загрузка контекста из JSON (День 10).
def cmd_load_context(agent):
    # Загрузку выполняет агент; он же обрабатывает отсутствие/повреждение файла.
    stats = agent.load_context_json(CONTEXT_FILE)

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
if not os.path.exists(LOG_FILE):
    # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        # Пишем заголовок с режимами и размером окна.
        f.write(
            f"# Лог диалога — День 10 (контекст={args.context}, память={args.memory}, окно={WINDOW})\n\n"
        )

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
    # День 10: настройки сжатия (None = «флаг не задан», возьмётся константа по умолчанию).
    compress_every=args.compress_every,
    summary_word_limit=args.summary_word_limit,
    compress_temperature=args.compress_temperature,
)

# Печатаем выбранный режим работы.
print(f"[Режим] контекст={args.context}, память={args.memory}, окно={WINDOW}")

# --- День 10: автозагрузка контекста из JSON (до приветствия) ---------------
# Выполняется для ВСЕХ режимов памяти — в этом смысл дня: агент продолжает
# диалог так, как будто не выключался. Markdown-лог (load_history) при этом
# ведёт себя как в Дне 6 (зависит от memory_type) — он человекочитаемая копия.
context_stats = agent.load_context_json(CONTEXT_FILE)

# Если контекст восстановлен — печатаем статистику загрузки.
if context_stats is not None:
    # Сообщение с числом восстановленных сообщений и длиной саммари.
    print(
        f"[Память] Контекст восстановлен: {context_stats['loaded']} сообщений "
        f"(саммари: {context_stats['summary_length']} символов)"
    )

# Загружаем память прошлой сессии из Markdown-лога (поведение зависит от memory_type).
agent.load_history(LOG_FILE)

# Для layered-памяти показываем статистику загрузки слоёв.
if args.memory == "layered":
    # Повторно получаем статистику: load_history вернул её при вызове выше,
    # но для читаемости пересчитываем по текущему состоянию агента.
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

# Выводим шапку программы: название, режимы, окно и имена файлов.
print(f"🤖 Чат-бот — День 10 (контекст={args.context}, память={args.memory}, окно={WINDOW})")

# День 10: в режиме branching печатаем активную ветку в шапке — пользователь
# сразу видит, в какой ветке ведётся диалог.
if args.context == "branching":
    # Строка с именем активной ветки и подсказкой переключения.
    print(f"Активная ветка: {agent.active_branch} (список: /branch list)")
print(f"Лог: {LOG_FILE}")
print(f"Контекст (JSON): {CONTEXT_FILE}")
print("Команды: /history /window /summary /compress [on|off] /compare /layers /layer "
      "/facts /branch /compare-strategies /save /load /tokens /cost /scenario /clear /exit")
print("Сжатие на лету: /compress on (саммари+окно) | /compress off (окно как есть).")
print("Сравнение до/после сжатия: /compare (качество ответов + экономия токенов/₽).")
print("Факты (режим facts): /facts — текущий блок фактов.")
print("Ветки (режим branching): /branch list | /branch switch <имя> | /branch new <имя>.")
print("Введите /exit для завершения.\n")

# Запускаем бесконечный цикл, чтобы пользователь мог отправлять много сообщений.
# Весь цикл обёрнут в try/except: любая непредвиденная ошибка пишется в журнал,
# а программа не «молча» закрывает окно — она показывает ошибку и ждёт Enter.
while True:
    try:
        # Приглашение ввода: в режиме branching показываем активную ветку
        # (требование пользователя — «в терминале должно быть видно, какая ветка
        # активна»); в остальных режимах — обычное «Вы: ».
        if args.context == "branching":
            # Приглашение с именем активной ветки в квадратных скобках.
            prompt = f"Вы [{agent.active_branch}]: "
        # Обычное приглашение для остальных стратегий.
        else:
            # Стандартное приглашение донора.
            prompt = "Вы: "

        # Показываем приглашение, читаем ввод и удаляем пробелы по краям.
        user_input = input(prompt).strip()

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

        # Обрабатываем команду /facts — печать блока фактов (День 10).
        # Осмысленна в режиме facts: там факты обновляются автоматически.
        if user_input == "/facts":
            # Проверяем, что выбрана стратегия facts.
            if args.context == "facts":
                # Печать блока делает обработчик.
                cmd_facts(agent)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /facts недоступна в режиме context={args.context}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /branch — ветки диалога (День 10).
        # Содержательно работает в режиме branching; в остальных — подсказка.
        if user_input == "/branch" or user_input.startswith("/branch "):
            # Проверяем, что выбрана стратегия branching.
            if args.context == "branching":
                # Разбираем команду на части (подкоманда + аргумент) и вызываем.
                cmd_branch(agent, user_input.split()[1:])
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /branch недоступна в режиме context={args.context}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем /compress on|off (День 10, Ч5) — переключатель сжатия на лету.
        # Доступен во ВСЕХ режимах: смысл именно в том, чтобы включить или выключить
        # сжатие, не перезапускаясь. Проверяем раньше точного «/compress».
        if user_input.startswith("/compress "):
            # Отделяем аргумент (on/off) от самой команды.
            cmd_compress_toggle(agent, user_input[len("/compress "):])
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /compress — ручное сжатие, для compressed и layered.
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

        # Обрабатываем команду /compare (День 10, ядро дня) — качество и расход до/после.
        # Осмысленна там, где есть саммари (compressed/layered): в sliding-window
        # саммари пустое, и «после» совпало бы с «до».
        if user_input == "/compare":
            # Проверяем, что есть чем сравнивать (саммари имеет смысл в этих режимах).
            if args.memory in ("compressed", "layered"):
                # Сравнение делает обработчик: локальная оценка + живой прогон после y/N.
                cmd_compare(agent)
            # В остальных режимах команда недоступна.
            else:
                # Сообщаем о недоступности команды.
                print(f"[Команда] /compare недоступна в режиме memory={args.memory}\n")
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем /compare-strategies (День 10, ядро дня) — сравнение трёх
        # стратегий на сценарии «ТЗ». Доступна во всех режимах: сравнение не
        # зависит от текущей стратегии пользователя (прогон на временных агентах).
        if user_input == "/compare-strategies":
            # Сравнение делает обработчик: локальная оценка или живой прогон после y/N.
            cmd_compare_strategies(agent)
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
        if user_input.startswith("/layer "):
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

        # Обрабатываем команду /save — ручное сохранение контекста в JSON (День 10).
        if user_input == "/save":
            # Сохранение выполняет обработчик: снимок состояния агента в JSON.
            cmd_save_context(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /tokens — три счётчика токенов (День 10).
        if user_input == "/tokens":
            # Вывод делает обработчик: счётчики агента + локальная оценка.
            cmd_tokens(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /cost — стоимость обмена и сессии (День 10).
        if user_input == "/cost":
            # Вывод делает обработчик: обмен, сессия, прогноз на 100 обменов.
            cmd_cost(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /scenario — три сценария расхода токенов (День 10).
        if user_input == "/scenario":
            # Прогон выполняет обработчик: живой API только после y/N.
            cmd_scenario(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /load — ручная загрузка контекста из JSON (День 10).
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
            # День 10: сохраняем полный контекст в JSON перед выходом.
            agent.save_context_json(CONTEXT_FILE)
            # Сообщаем пользователю, что контекст сохранён.
            print(f"[Память] Контекст сохранён: {CONTEXT_FILE}")
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

    # Перехватываем Ctrl+D (EOF) — корректный выход без ошибки.
    except EOFError:
        # День 10: сохраняем контекст и при выходе по EOF — агент «не выключался».
        agent.save_context_json(CONTEXT_FILE)
        # Сообщаем о сохранении контекста.
        print(f"[Память] Контекст сохранён: {CONTEXT_FILE}")
        # Сообщаем о завершении и прерываем цикл.
        print("\n[Выход] Ввод завершён (EOF)")
        break

    # Перехватываем Ctrl+C — корректный выход без traceback.
    except KeyboardInterrupt:
        # День 10: сохраняем контекст и при прерывании — агент «не выключался».
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
        input("Нажмите Enter для продолжения...")

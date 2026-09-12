# ============================================================================
# День 7 — den_7_Kod.py (сохранение контекста в JSON, класс Agent)
#
# КЛЮЧЕВАЯ ИДЕЯ:
# В Дне 6 память между запусками имели только compressed/layered-режимы
# (и то — только саммари/слои из Markdown-лога), а session-память умирала
# вместе с процессом. День 7 добавляет универсальную персистентность:
# полное состояние агента (история, архив, саммари, слои, режимы) снимается
# в JSON-файл и восстанавливается при следующем запуске. JSON выбран потому,
# что это машиночитаемый формат без потерь: Markdown-лог удобен человеку,
# но при парсинге теряет timestamps и структуру. Теперь «агент не выключался»
# — это не метафора: после перезапуска он продолжает диалог с того же места,
# со всей историей и саммари (Суть_N2.txt, §2.1: «иллюзия памяти создаётся
# подгрузкой сохранённых данных из файлов»).
#
# Запуск:
#   python den_07/den_7_Kod.py --context sliding-window --memory session
#   python den_07/den_7_Kod.py --context compression --memory compressed
#   python den_07/den_7_Kod.py --context leveling --memory layered
# ============================================================================

# 1. Импорты: os, sys, json, argparse, datetime, requests, dotenv --------------

# Импортируем модуль os для чтения переменных окружения и проверки файлов.
import os

# Импортируем модуль sys для настройки кодировки стандартного ввода.
import sys

# Импортируем модуль json для сохранения и загрузки контекста агента (День 7).
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
    description="Чат-бот Дня 7: сохранение контекста в JSON, три техники контекста и три типа памяти через флаги."
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

# Флаг --log: имя лог-файла (по умолчанию Den_7_log.md).
parser.add_argument(
    "--log",
    type=str,
    default="Den_7_log.md",
    help="Имя лог-файла.",
)

# Флаг --context-file: путь к JSON-файлу контекста (День 7).
parser.add_argument(
    "--context-file",
    type=str,
    default="den_7_context.json",
    help="JSON-файл контекста для сохранения/загрузки (по умолчанию den_7_context.json).",
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

# Имя лог-файла из флага --log (если путь относительный — фиксируем его за den_07).
if os.path.isabs(args.log):
    LOG_FILE = args.log
else:
    LOG_FILE = os.path.join(BASE_DIR, args.log)

# Имя файла саммари (для compressed и layered памяти) — производное от имени лога,
# чтобы у разных логов не было одного саммари на всех.
SUMMARY_FILE = os.path.join(BASE_DIR, os.path.splitext(os.path.basename(LOG_FILE))[0] + ".summary.md")

# Путь к JSON-файлу контекста (День 7): относительный путь фиксируется за
# каталогом скрипта, абсолютный — используется как есть.
if os.path.isabs(args.context_file):
    CONTEXT_FILE = args.context_file
else:
    CONTEXT_FILE = os.path.join(BASE_DIR, args.context_file)

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
ERROR_LOG = os.path.join(BASE_DIR, "den_7_error.log")

# Версия формата JSON-снимка контекста (День 7): при изменении структуры
# в будущем старые снимки можно отличить по номеру версии.
CONTEXT_VERSION = 1

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


# 5. detect_layer(text) — автоопределение слоя (функция уровня модуля, для C) ---


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


# 6. class Agent — один класс, стратегии внутри ---------------------------------


# Класс Agent — отдельная сущность, которая «знает» всё о диалоге:
# режимы контекста и памяти, историю, саммари, слои и то, как обращаться к LLM.
# Наружу (в CLI-цикл) отдаёт только ответы и сведения о контексте — CLI работает
# исключительно через публичные методы.
class Agent:
    # Создаём агента: роль, стратегии контекста и памяти, размеры окон.
    def __init__(self, system_prompt: str, context_strategy: str = "sliding_window",
                 memory_type: str = "session", window: int = 10, keep: int = 6,
                 load_layers: str = "all"):
        """system_prompt — роль агента;
        context_strategy — техника управления контекстом:
            "sliding_window", "history_compression", "context_leveling";
        memory_type — тип памяти:
            "session", "compressed", "layered"."""
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

        # Саммари старых сообщений (для compressed и layered).
        self.summary = ""

        # Счётчик вытесненных из окна сообщений (для уведомления в sliding_window).
        self.evicted_total = 0

    # Внутренний метод: один запрос к LLM с повтором при HTTP 429.
    # Снаружи не вызывается — CLI работает только с публичными методами.
    def _ask_llm(self, messages):
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
                return result["choices"][0]["message"]["content"] or ""

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

        # Если режим неизвестен — это ошибка конфигурации, сообщаем и падаем.
        raise ValueError(f"Неизвестный режим контекста: {self.context_strategy}")

    # Общее сжатие старых сообщений в саммари (для B и C).
    # Возвращает текст нового саммари или None, если запрос не удался.
    def _compress_history(self, old_messages, summary):
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
                    f"Предыдущее саммари:\n{summary or '(нет)'}\n\n"
                    f"Сообщения диалога:\n{transcript}\n\n"
                    "Объедини всё в единое обновлённое саммари."
                ),
            },
        ]

        # Отправляем запрос сжатия в LLM (retry при 429 внутри _ask_llm).
        new_summary = self._ask_llm(compress_messages)

        # Возвращаем текст саммари или None, если запрос не удался.
        return new_summary

    # Внутреннее применение сжатия: сохраняет саммари, переносит сообщения в архив.
    def _apply_compression(self, old_messages, new_summary):
        # Запоминаем длину нового саммари для уведомления и лога.
        summary_length = len(new_summary)

        # Обновляем саммари агента: старое консолидировано в новом.
        self.summary = new_summary

        # Сохраняем новое саммари в файл (перезапись целиком).
        self.save_summary(SUMMARY_FILE)

        # Записываем событие сжатия в лог-файл.
        log_compression(len(old_messages), summary_length)

        # Выводим уведомление о сжатии с количеством сообщений и длиной саммари.
        print(
            f"[Сжатие] {len(old_messages)} сообщений свёрнуты в саммари "
            f"(длина саммари: {summary_length} символов)\n"
        )

        # Переносим сжатые сообщения в архив (они остаются видны в /history).
        self.archived.extend(old_messages)

        # Удаляем сжатые сообщения из активной истории (они теперь внутри саммари).
        del self.full_history[:len(old_messages)]

    # Главный метод агента: принять сообщение пользователя и вернуть ответ LLM.
    # Диспетчеризация в нужную стратегию контекста происходит внутри.
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

        # Отправляем запрос к LLM и получаем ответ (или None при ошибке).
        bot_response = self._ask_llm(messages)

        # Если ответа нет (ошибка API) — убираем реплику пользователя из истории,
        # чтобы она не «висела» без ответа и не попала в саммари.
        if bot_response is None:
            # Удаляем последнее сообщение пользователя.
            self.full_history.pop()
            # Возвращаем None — CLI продолжит цикл без ответа.
            return None

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

                # Вызываем сжатие через LLM: старое саммари консолидируется.
                new_summary = self._compress_history(old_messages, self.summary)

                # Если сжатие удалось — применяем его к состоянию агента.
                if new_summary is not None:
                    # Сохранение, архивирование и уведомление — в общем методе.
                    self._apply_compression(old_messages, new_summary)
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

        # Вызываем сжатие через LLM: старое саммари консолидируется.
        new_summary = self._compress_history(old_messages, self.summary)

        # Если сжатие не удалось — не теряем сообщения, оставляем всё как было.
        if new_summary is None:
            # Сообщаем пользователю, что сжатие отложено, сообщения сохранены.
            print("[Сжатие] Не удалось, сообщения сохранены, попробуем в следующий раз\n")
            # Возвращаем None — сжатие не состоялось.
            return None

        # Применяем сжатие: саммари, архив, уведомление.
        self._apply_compression(old_messages, new_summary)

        # Возвращаем кортеж: количество сообщений и длину нового саммари.
        return (n, len(self.summary))

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

    # Сохранение саммари в файл (перезапись целиком при каждом обновлении).
    def save_summary(self, filepath: str):
        # Если саммари пустое — файл не трогаем (пустых заголовков не плодим).
        if not self.summary:
            # Просто выходим: сохранять нечего.
            return

        # Открываем файл саммари на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем заголовок первого уровня с названием техники.
            f.write("# Саммари диалога — День 7\n")
            # Пишем строку с датой и временем последнего обновления.
            f.write(f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            # Пишем текст саммари и перевод строки в конце.
            f.write(f"{self.summary}\n")

    # Загрузка саммари из файла (для compressed и layered памяти).
    def load_summary(self, filepath: str):
        # Если файла саммари нет — саммари остаётся пустым.
        if not os.path.exists(filepath):
            # Пустая строка означает «саммари пока нет».
            return

        # Открываем файл саммари на чтение с кодировкой UTF-8.
        with open(filepath, "r", encoding="utf-8") as f:
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
        self.summary = "\n".join(text_lines).strip()

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

    # Сохранение истории в файл (формат зависит от memory_type).
    # Основной лог ведётся дозаписью через append_log(); этот метод делает
    # полный снимок истории (архив + активные сообщения) в указанный файл.
    def save_history(self, filepath: str):
        # Открываем файл на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем заголовок с режимами и размером окна.
            f.write(
                f"# Лог диалога — День 7 (контекст={self.context_strategy}, "
                f"память={self.memory_type}, окно={self.window})\n\n"
            )

            # Пишем отметку времени снимка.
            f.write(f"## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # Перебираем архивные сообщения (свёрнутые в саммари).
            for msg in self.archived:
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

            # Перебираем активные сообщения.
            for msg in self.full_history:
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

    # Загрузка истории из файла (для layered — с учётом load_layers).
    # Возвращает статистику загрузки словарём (для layered) или None.
    def load_history(self, filepath: str):
        # Для session-памяти лог не загружается: сессия всегда новая.
        if self.memory_type == "session":
            # Если файл существует — сообщаем о найденном логе.
            if os.path.exists(filepath):
                # Уведомление о найденном прошлом логе (контекст не загружается).
                print(
                    f"[Память] Найден прошлый лог: {filepath} "
                    "(в контекст не загружается — сессия новая)"
                )
            # Загрузки не было.
            return None

        # Для compressed-памяти загружаем только саммари.
        if self.memory_type == "compressed":
            # Загружаем саммари прошлой сессии из файла.
            self.load_summary(SUMMARY_FILE)

            # Если саммари найдено и не пустое — сообщаем пользователю о загрузке.
            if self.summary:
                # Печатаем уведомление с длиной загруженного саммари в символах.
                print(f"[Память] Загружено саммари прошлой сессии ({len(self.summary)} символов)")
            # Загрузка истории сообщений не выполняется.
            return None

        # Для layered-памяти: саммари + выбранные слои из лога.
        # Разбираем значение --load в множество выбираемых слоёв.
        chosen = self._parse_load_layers(self.load_layers)

        # Статистика: сколько сообщений каждого слоя прочитано и загружено.
        stats = {layer: 0 for layer in LAYER_ORDER}

        # Если файла нет или выбрано «none» — возвращаем пустую статистику.
        if not os.path.exists(filepath) or not chosen:
            # Добавляем в статистику список пропущенных слоёв.
            stats["skipped"] = [layer for layer in LAYER_ORDER if layer not in chosen]
            # Ничего не загружено.
            stats["loaded"] = 0
            # Возвращаем статистику.
            return stats

        # Список сообщений, которые реально загружаем в оперативный слой.
        loaded = []

        # Открываем лог-файл на чтение с кодировкой UTF-8.
        with open(filepath, "r", encoding="utf-8") as f:
            # Читаем лог построчно.
            for line in f:
                # Убираем пробелы и перевод строки по краям.
                stripped = line.strip()

                # Строки вида «**Вы** [high]: текст» — сообщения пользователя.
                if stripped.startswith("**Вы** ["):
                    # Роль этой строки — пользователь.
                    role = "user"
                # Строки вида «**Агент** [high]: текст» — сообщения агента.
                elif stripped.startswith("**Агент** ["):
                    # Роль этой строки — ассистент.
                    role = "assistant"
                # Прочие строки (заголовки, даты, события сжатия) пропускаем.
                else:
                    # Переходим к следующей строке лога.
                    continue

                # Извлекаем слой из квадратных скобок после роли.
                layer_part = stripped.split("[", 1)[1].split("]", 1)[0]

                # Извлекаем текст сообщения после «]: ».
                content = stripped.split("]: ", 1)[1] if "]: " in stripped else ""

                # Слой должен быть известным, а текст — непустым.
                if layer_part not in LAYER_LABELS or not content:
                    # Переходим к следующей строке лога.
                    continue

                # Считаем сообщение этого слоя прочитанным из файла.
                stats[layer_part] += 1

                # Если слой выбран флагом --load — добавляем его в оперативный слой.
                if layer_part in chosen:
                    # Добавляем сообщение в формате полной истории агента.
                    loaded.append(
                        {
                            # Роль сообщения (user или assistant).
                            "role": role,
                            # Текст сообщения.
                            "content": content,
                            # Слой приоритета из лога.
                            "layer": layer_part,
                            # Время загрузки (оригинальное время в логе не хранится).
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )

        # Загруженные сообщения становятся оперативным слоем агента.
        self.full_history = loaded

        # Сколько сообщений реально попало в контекст.
        stats["loaded"] = len(loaded)

        # Какие слои были пропущены (не выбраны флагом --load).
        stats["skipped"] = [layer for layer in LAYER_ORDER if layer not in chosen]

        # Возвращаем статистику для вывода в консоль.
        return stats

    # Очистка контекста (сброс истории; для compressed/layered — и саммари).
    def clear_context(self):
        # Полностью очищаем активную историю диалога в памяти.
        self.full_history = []

        # Очищаем архив свёрнутых сообщений.
        self.archived = []

        # Для compressed и layered сбрасываем и саммари.
        if self.memory_type in ("compressed", "layered"):
            # Сбрасываем саммари в памяти.
            self.summary = ""

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

    # --- День 7: JSON-персистентность контекста ------------------------------

    # Сохранение полного состояния агента в JSON-файл (ядро Дня 7).
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
        }

        # Открываем JSON-файл на запись (перезапись) с кодировкой UTF-8.
        with open(filepath, "w", encoding="utf-8") as f:
            # Пишем снимок: ensure_ascii=False — кириллица остаётся читаемой,
            # indent=2 — файл можно открыть и посмотреть глазами.
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # Загрузка состояния агента из JSON-файла (ядро Дня 7).
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


# 7. Функции лога (append_log, log_compression) — CLI-уровень --------------------


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


# 8. Обработчики команд CLI (с проверкой доступности) ----------------------------


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


# Обработчик /save: ручное сохранение контекста в JSON (День 7).
def cmd_save_context(agent):
    # Снимок состояния делает сам агент; CLI только указывает файл.
    agent.save_context_json(CONTEXT_FILE)

    # Сообщаем пользователю, куда сохранён контекст.
    print(f"[Память] Контекст сохранён: {CONTEXT_FILE}\n")


# Обработчик /load: ручная загрузка контекста из JSON (День 7).
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



# 9. Главный цикл -----------------------------------------------------------------

# Заголовок лог-файла: создаём файл с шапкой, если его ещё нет.
if not os.path.exists(LOG_FILE):
    # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        # Пишем заголовок с режимами и размером окна.
        f.write(
            f"# Лог диалога — День 7 (контекст={args.context}, память={args.memory}, окно={WINDOW})\n\n"
        )

# Создаём агента: он один отвечает за стратегии контекста, память и запросы к API.
agent = Agent(
    SYSTEM_PROMPT,
    context_strategy=args.context,
    memory_type=args.memory,
    window=args.window,
    keep=args.keep,
    load_layers=args.load,
)

# Печатаем выбранный режим работы.
print(f"[Режим] контекст={args.context}, память={args.memory}, окно={WINDOW}")

# --- День 7: автозагрузка контекста из JSON (до приветствия) ---------------
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
print(f"🤖 Чат-бот — День 7 (контекст={args.context}, память={args.memory}, окно={WINDOW})")
print(f"Лог: {LOG_FILE}")
print(f"Контекст (JSON): {CONTEXT_FILE}")
print("Введите /exit для завершения.\n")

# Запускаем бесконечный цикл, чтобы пользователь мог отправлять много сообщений.
# Весь цикл обёрнут в try/except: любая непредвиденная ошибка пишется в журнал,
# а программа не «молча» закрывает окно — она показывает ошибку и ждёт Enter.
while True:
    try:
        # Показываем приглашение «Вы:», читаем ввод и удаляем пробелы по краям.
        user_input = input("Вы: ").strip()

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

        # Обрабатываем команду /save — ручное сохранение контекста в JSON (День 7).
        if user_input == "/save":
            # Сохранение выполняет обработчик: снимок состояния агента в JSON.
            cmd_save_context(agent)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /load — ручная загрузка контекста из JSON (День 7).
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
            # День 7: сохраняем полный контекст в JSON перед выходом.
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
        # День 7: сохраняем контекст и при выходе по EOF — агент «не выключался».
        agent.save_context_json(CONTEXT_FILE)
        # Сообщаем о сохранении контекста.
        print(f"[Память] Контекст сохранён: {CONTEXT_FILE}")
        # Сообщаем о завершении и прерываем цикл.
        print("\n[Выход] Ввод завершён (EOF)")
        break

    # Перехватываем Ctrl+C — корректный выход без traceback.
    except KeyboardInterrupt:
        # День 7: сохраняем контекст и при прерывании — агент «не выключался».
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

# -*- coding: utf-8 -*-
# ============================================================================
# День 11 — den_11_Kod.py (модель памяти агента)
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Переход от «одного снимка состояния» к ЯВНОЙ модели памяти. Информация
# разделяется на типы (краткосрочная / рабочая / долговременная + профиль),
# хранится физически раздельно, ЯВНО маршрутизируется при сохранении
# (memory.remember(layer, ...)) и ДОЗИРОВАННО подмешивается в промт
# (deliver: set[str]). Агент — stateful: идентификация на старте,
# интервью-инициализация для нового ID, resume «с того же места».
#
# Уроки дня 10 (п.16 §7): try: import readline; sys.stdin/stdout.reconfigure
# (errors="replace"); BASE_DIR; retry 429 (в LLM-клиенте); токен-учёт + CSV.
#
# Запуск:
#   python den_11_Kod.py                # интерактивный REPL (спросит user_id)
#   python den_11_Kod.py --user alice   # сразу идентификация alice
#   python den_11_Kod.py --mock         # тестовый режим на MockClient (без ключа)
#
# Внутри чата: /memory /profile /tasks /task <имя> /deliver <слои>
# /compare /summary /state /tokens /cost /help /exit
# ============================================================================

# 1. Импорты ----------------------------------------------------------------
import os
import sys
import csv

# readline — редактирование ввода (стрелки); без него input() вставляет
# escape-последовательности в текст. Обёрнуто в try: на Windows не падаем.
try:
    import readline
except ImportError:
    pass

import argparse
from datetime import datetime
from uuid import uuid4

# Путь к модулям дня: добавляем каталог скрипта в sys.path, чтобы импорты
# core.* и memory.* работали независимо от того, откуда запущен скрипт.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv

# Импортируем слои дня из модулей (абстракции, фасады, менеджер).
from storage.store import Store, safe_name
from storage.db import ProfileRepository
from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager, default_layers, LAYER_ORDER
from core.llm_client import RouterAIClient, MockClient, LLMClient, MODEL
from core.prompt_builder import PromptBuilder
from core.agent import Agent
from core.state_machine import TaskState, ALLOWED_TRANSITIONS

# 2. Окружение и ключ --------------------------------------------------------
load_dotenv()
api_key = os.getenv("API_KEY")

# Кодировки stdin/stdout: errors="replace" — битые байты заменяются заглушкой,
# а не роняют программу (урок дня 10).
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(errors="replace")

# 3. Флаги --------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Чат-бот Дня 11: агент с явной моделью памяти (memory layers)."
)
parser.add_argument("--user", type=str, default=None,
                    help="Идентификатор пользователя (без него — спросит на старте).")
parser.add_argument("--deliver", type=str, default="profile,long_term,working,short_term",
                    help="Набор слоёв для доставки в промт (через запятую).")
parser.add_argument("--mock", action="store_true",
                    help="Режим MockClient: ответы от заглушки, ключ не нужен.")
parser.add_argument("--fresh", action="store_true",
                    help="Не восстанавливать прошлое состояние (новая сессия).")
parser.add_argument("--log", type=str, default="Den_11_log.md",
                    help="Имя лог-файла.")
parser.add_argument("--token-log", type=str, default="den_11_tokens.csv",
                    help="CSV-журнал токенов и стоимости (по умолчанию den_11_tokens.csv).")
parser.add_argument("--max-tokens", type=int, default=None,
                    help="Лимит длины ответа модели.")
parser.add_argument("--price-in", type=float, default=11.0,
                    help="Цена 1M входящих токенов в рублях (по умолчанию 11).")
parser.add_argument("--price-out", type=float, default=33.0,
                    help="Цена 1M исходящих токенов в рублях (по умолчанию 33).")
parser.add_argument("--memory-dir", type=str, default=None,
                    help="Каталог хранилища памяти (по умолчанию users/ рядом с кодом).")
args = parser.parse_args()

# Корень хранилища памяти: users/ рядом со скриптом (BASE_DIR), если не задано.
MEMORY_ROOT = args.memory_dir if args.memory_dir else os.path.join(BASE_DIR, "users")
LOG_FILE = os.path.join(BASE_DIR, args.log) if not os.path.isabs(args.log) else args.log
TOKEN_LOG = os.path.join(BASE_DIR, args.token_log) if not os.path.isabs(args.token_log) else args.token_log

# 4. Роль агента ---------------------------------------------------------------
SYSTEM_PROMPT = (
    "Ты полезный ассистент с явной моделью памяти. Отвечай кратко на русском языке, "
    "учитывая переданные блоки памяти. Если блок памяти отсутствует — отвечай без него."
)

# 5. Локальная оценка токенов (для /tokens, /cost, CSV; авторитет — usage живого API) ---
def estimate_tokens(text: str) -> int:
    """Грубая локальная оценка: ~1 токен на 4 символа (без внешних зависимостей)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages) -> int:
    """Оценка списка сообщений API (роль + служебные ~4 токена на сообщение)."""
    return sum(estimate_tokens(m.get("content", "")) + 4 for m in messages)


# 6. Лог маршрутизации памяти ---------------------------------------------------
def log_line(line: str):
    """Пишет строку в лог-файл (журнал «что куда легло»)."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
    except OSError:
        pass


# 7. CSV-журнал токенов (п.16) ---------------------------------------------------
def append_token_log(exchange, prompt_tokens, cost_rubles):
    """Дозаписывает строку обмена в CSV. Ошибка записи не роняет чат."""
    try:
        is_new = not os.path.exists(TOKEN_LOG)
        with open(TOKEN_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["exchange", "timestamp", "prompt_tokens",
                                 "cost_rubles", "cost_total_rubles"])
            writer.writerow([exchange, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             prompt_tokens, f"{cost_rubles:.6f}",
                             f"{cost_rubles * exchange:.6f}"])
    except OSError:
        pass


# 8. Композиция объектов (DI) ---------------------------------------------------
def build_agent(user_id=None, mock=False):
    """Собирает Store + профиль-репозиторий + слои + LLM-клиент в Agent."""
    store = Store(MEMORY_ROOT, log=log_line)
    repo = ProfileRepository(os.path.join(MEMORY_ROOT, "profiles.db"), log=log_line)
    store.profile_repo = repo

    memory = MemoryManager(default_layers(store, log=log_line), log=log_line)
    builder = PromptBuilder(SYSTEM_PROMPT)

    if mock or api_key is None or api_key == "test-key":
        client = MockClient(name="Mock")
    else:
        client = RouterAIClient(api_key=api_key, max_tokens=args.max_tokens)

    return Agent(client, memory, builder, store, user_id=user_id,
                 default_task="Основная_задача", log=log_line)


# 9. Интервью-инициализация ------------------------------------------------------
def run_interview(agent: Agent, user_id: str):
    """Проводит интервью (стиль/констрейнты/контекст) и создаёт дерево памяти."""
    print(f"[Инициализация] Новый пользователь «{user_id}» — проведу интервью.\n")
    name = input("Ваше имя: ").strip()
    answers = {}
    for key, question in agent.interview_questions():
        val = input(f"{question}\n> ").strip()
        answers[key] = val
    agent.initialize_user(user_id, name, answers)
    print(f"[Инициализация] Профиль и дерево users/{user_id}/ созданы.\n")


# 10. Печать справки ---------------------------------------------------------------
def print_help():
    print("[Справка] Доступные команды:")
    print("  /memory              — снимок «какие данные в каком типе памяти»")
    print("  /profile             — показать профиль (style/constraints/context)")
    print("  /tasks               — список задач + активная задача")
    print("  /task <имя>          — переключить/создать задачу (с отметкой перехода)")
    print("  /deliver <слои>      — набор включаемых слоёв (напр. profile,working)")
    print("  /compare             — сравнение ответа с/без слоя долговременной памяти")
    print("  /summary             — резюме сессий текущей задачи")
    print("  /state               — task state machine (стадии + переходы)")
    print("  /tokens              — локальная оценка токенов последнего запроса")
    print("  /cost                — стоимость обменов (локальная оценка)")
    print("  /help                — эта справка")
    print("  /exit                — завершить и сохранить состояние")
    print()


# 11. Демонстрация влияния памяти на ответы ----------------------------------------
def compare_demonstration(agent: Agent, exchange_tracker):
    """Сравнение ответа с/без долговременной памяти (демонстрация задания п.14)."""
    question = "Какой стек я предпочитаю и почему?"

    # Вариант 1: все слои.
    agent.deliver = {"profile", "long_term", "working", "short_term"}
    prompt_ctx_full = agent.build_context(question)
    messages_full = agent.prompts.build(prompt_ctx_full, agent.deliver)
    answer_full = agent.llm.complete(messages_full)

    # Вариант 2: без слоя долговременной памяти (урезанный режим).
    agent.deliver = {"profile", "working", "short_term"}
    prompt_ctx_cut = agent.build_context(question)
    messages_cut = agent.prompts.build(prompt_ctx_cut, agent.deliver)
    answer_cut = agent.llm.complete(messages_cut)

    # Учёт токенов демонстрации (локальная оценка).
    tokens_full = estimate_messages_tokens(messages_full)
    tokens_cut = estimate_messages_tokens(messages_cut)
    cost_full = (tokens_full * args.price_in) / 1_000_000
    cost_cut = (tokens_cut * args.price_in) / 1_000_000
    exchange_tracker["n"] += 2
    exchange_tracker["tokens"] += tokens_full + tokens_cut
    exchange_tracker["cost"] += cost_full + cost_cut

    print("\n[Сравнение] Влияние долговременной памяти на ответы:")
    print(f"  С long_term  (~{tokens_full} вх. токенов): {answer_full if answer_full else '(нет ответа)'}")
    print(f"  БЕЗ long_term (~{tokens_cut} вх. токенов): {answer_cut if answer_cut else '(нет ответа)'}")
    print("  (разница показывает, как слой долговременной памяти меняет ответ)\n")


# 12. Показать state machine -------------------------------------------------------
def show_state():
    print("[State machine] Стадии и разрешённые переходы:")
    for state in TaskState:
        targets = ALLOWED_TRANSITIONS.get(state, set())
        names = ", ".join(t.value for t in targets) or "—"
        print(f"  {state.value} → {names}")
    print()


# 13. Главная программа ------------------------------------------------------------
def main():
    # Идентификация: --user либо интерактивный ввод ДО загрузки памяти.
    user_id = args.user
    agent = build_agent(user_id=user_id, mock=args.mock)

    # Накопительный трекер токенов сессии (локальная оценка).
    exchange_tracker = {"n": 0, "tokens": 0, "cost": 0.0}

    if user_id is None:
        user_id = input("Идентификатор пользователя (user_id): ").strip()
        if not user_id:
            user_id = "anonymous"
        agent.user_id = user_id

    # Загрузка памяти существующего пользователя либо интервью нового.
    profile_repo = agent.store.profile_repo
    if not args.fresh and profile_repo.exists(user_id):
        agent.load_state(user_id)
        print(f"[Память] Пользователь «{user_id}» найден, контекст загружен. Задача: {agent.task}")
    else:
        run_interview(agent, user_id)

    # Применяем --deliver (набор слоёв по умолчанию).
    deliver = {part.strip() for part in args.deliver.split(",") if part.strip()}
    agent.deliver = deliver & set(LAYER_ORDER)
    print(f"[Режим] Доставка слоёв: {sorted(agent.deliver)}")
    if args.mock:
        print("[Режим] MockClient (заглушка) — живых запросов к API не будет.")
    print("Команды: /memory /profile /tasks /task /deliver /compare /summary /state /tokens /cost /help /exit\n")

    # Главный цикл.
    while True:
        try:
            user_input = input(f"Вы [{agent.task}]: ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input.split()[0]
                if command == "/help":
                    print_help()
                    continue
                if command == "/memory":
                    ctx = MemoryContext(agent.user_id, agent.task, agent.session_id)
                    print(f"[Память]\n{agent.memory.report(ctx)}\n")
                    continue
                if command == "/profile":
                    profile = agent.memory.layers["profile"].read(
                        MemoryContext(agent.user_id))
                    print(f"[Профиль]\n{profile}\n")
                    continue
                if command == "/tasks":
                    tasks = agent.store.list_tasks(agent.user_id)
                    active = agent.task
                    print(f"[Задачи] Всего: {len(tasks)}; активная: {active}")
                    for t in tasks:
                        marker = "*" if t == safe_name(active) else " "
                        print(f"  {marker} {t}")
                    print()
                    continue
                if command == "/task":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        print("[Задача] Укажите имя: /task <имя>\n")
                        continue
                    agent.switch_task(parts[1].strip())
                    print(f"[Задача] Переключился на «{parts[1].strip()}»\n")
                    continue
                if command == "/deliver":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        print("[Доставка] Укажите слои: /deliver profile,working\n")
                        continue
                    chosen = {p.strip() for p in parts[1].split(",") if p.strip()}
                    agent.deliver = chosen & set(LAYER_ORDER)
                    print(f"[Доставка] Теперь: {sorted(agent.deliver)}\n")
                    continue
                if command == "/compare":
                    compare_demonstration(agent, exchange_tracker)
                    continue
                if command == "/summary":
                    text = agent.store.read_sessions_resume(agent.user_id, agent.task)
                    print(f"[Саммари]\n{text or '(пусто)'}\n")
                    continue
                if command == "/state":
                    show_state()
                    continue
                if command == "/tokens":
                    print(f"[Токены] Обменов: {exchange_tracker['n']} | "
                          f"Всего вх. оценка: {exchange_tracker['tokens']} | "
                          f"Последний запрос: см. CSV {os.path.basename(TOKEN_LOG)}\n")
                    continue
                if command == "/cost":
                    print(f"[Стоимость] Оценка сессии (вход): {exchange_tracker['cost']:.6f} ₽ "
                          f"(вход {args.price_in} ₽/1M, выход {args.price_out} ₽/1M)\n")
                    continue
                if command == "/exit":
                    agent.save_state()
                    print("[Выход] Состояние сохранено. До встречи!")
                    break
                print(f"[Команда] Неизвестная команда: {command}. См. /help\n")
                continue

            # Обычное сообщение → полный цикл агента.
            answer = agent.respond(user_input)
            if answer is None:
                print("[API] Ответ не получен.\n")
                continue

            # Токен-учёт: локальная оценка собранного запроса последнего обмена.
            last_ctx = agent.build_context(user_input)
            last_messages = agent.prompts.build(last_ctx, agent.deliver)
            prompt_tokens = estimate_messages_tokens(last_messages)
            exchange_tracker["n"] += 1
            exchange_tracker["tokens"] += prompt_tokens
            exchange_cost = (prompt_tokens * args.price_in) / 1_000_000
            exchange_tracker["cost"] += exchange_cost
            append_token_log(exchange_tracker["n"], prompt_tokens, exchange_cost)

            print(f"Агент: {answer}\n")

        except EOFError:
            agent.save_state()
            print("\n[Выход] Ввод завершён (EOF)")
            break
        except KeyboardInterrupt:
            agent.save_state()
            print("\n[Выход] Прервано пользователем")
            break
        except Exception as error:
            log_line(f"[Ошибка] {type(error).__name__}: {error}")
            print(f"[Ошибка] {error}\n")


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
# ============================================================================
# Kod.py — точка входа агента с явной моделью памяти
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
#   python Kod.py                # интерактивный REPL (спросит user_id)
#   python Kod.py --user alice   # сразу идентификация alice
#   python Kod.py --mock         # тестовый режим на MockClient (без ключа)
#
# Внутри чата: /memory /profile [list|show|use|new|route|auto] /tasks
# /task <имя> /deliver <слои> /compare /summary /state /tokens /cost /help /exit
# ============================================================================

# 1. Импорты ----------------------------------------------------------------
import os
import sys
import csv
import json

# readline — редактирование ввода (стрелки); без него input() вставляет
# escape-последовательности в текст. Обёрнуто в try: на Windows не падаем.
try:
    import readline
except ImportError:
    pass

import argparse
from datetime import datetime

# Путь к модулям дня: добавляем каталог скрипта в sys.path, чтобы импорты
# core.* и memory.* работали независимо от того, откуда запущен скрипт.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv

# Импортируем слои дня из модулей (абстракции, фасады, менеджер).
from storage.store import Store, safe_name
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import (RouterAIClient, MockClient, MODEL_CONTEXT_LIMIT,
                             PRICE_IN_PER_M, PRICE_OUT_PER_M)
from core.prompt_builder import PromptBuilder, DELIVERABLE
from core.agent import Agent, StubExecutor
from core.state_machine import TaskStage, ALLOWED_TRANSITIONS
from core.invariants import Invariant, ConstraintSet

# 2. Окружение и ключ --------------------------------------------------------
load_dotenv()
api_key = os.getenv("API_KEY")

# Кодировки stdin/stdout: errors="replace" — битые байты заменяются заглушкой,
# а не роняют программу (урок дня 10).
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(errors="replace")

# 3. Флаги --------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Чат-бот: агент с явной моделью памяти (memory layers)."
)
parser.add_argument("--user", type=str, default=None,
                    help="Идентификатор пользователя (без него — спросит на старте).")
parser.add_argument("--profile", type=str, default=None,
                    help="Активный профиль на старте (несуществующий → предупреждение и default).")
parser.add_argument("--deliver", type=str, default="profile,invariants,long_term,working,short_term",
                    help="Набор слоёв для доставки в промт (через запятую).")
parser.add_argument("--mock", action="store_true",
                    help="Режим MockClient: ответы от заглушки, ключ не нужен.")
parser.add_argument("--fresh", action="store_true",
                    help="Не восстанавливать прошлое состояние (новая сессия).")
parser.add_argument("--log", type=str, default="Den_log.md",
                    help="Имя лог-файла.")
parser.add_argument("--token-log", type=str, default="tokens.csv",
                    help="CSV-журнал токенов и стоимости (по умолчанию tokens.csv).")
parser.add_argument("--max-tokens", type=int, default=None,
                    help="Лимит длины ответа модели.")
parser.add_argument("--budget", type=int, default=None,
                    help="Лимит входящих токенов промта: необязательные блоки "
                         "опускаются (роль и текущий запрос — всегда). Ориентир для "
                         "ручного значения — MODEL_CONTEXT_LIMIT (%d) минус резерв "
                         "под ответ. По умолчанию выключен." % MODEL_CONTEXT_LIMIT)
parser.add_argument("--price-in", type=float, default=PRICE_IN_PER_M,
                    help="Цена 1M входящих токенов в рублях (по умолчанию 11).")
parser.add_argument("--price-out", type=float, default=PRICE_OUT_PER_M,
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
    "учитывая переданные блоки памяти. Если блок памяти отсутствует — отвечай без него. "
    "Работай в рамках текущего этапа задачи, не перепрыгивай этапы; переходы "
    "контролирует код."
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
        # В тестовом режиме план/шаги детерминированы (без сети): StubExecutor.
        executor = StubExecutor()
    else:
        client = RouterAIClient(api_key=api_key, max_tokens=args.max_tokens)
        executor = None  # Agent построит LLMExecutor по умолчанию

    return Agent(client, memory, builder, store, user_id=user_id,
                 default_task="Основная_задача", log=log_line, executor=executor)


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
    print("  /profile             — активный профиль (style/constraints/context)")
    print("  /profile list        — профили пользователя (* default, > активный)")
    print("  /profile show <id>   — полный JSON профиля")
    print("  /profile use <id>    — переключить активный профиль сессии")
    print("  /profile new <id>    — создать профиль (мини-интервью)")
    print("  /profile route <текст> — показать решение роутера, НЕ переключая")
    print("  /profile auto on|off — авто-роутинг профиля по каждому запросу")
    print("  /tasks               — список задач + активная задача")
    print("  /task <имя>          — переключить/создать задачу (с отметкой перехода)")
    print("  /task retry          — повтор задачи из состояния failed (→ planning)")
    print("  /plan <цель>         — новая задача: план строится и ожидает утверждения")
    print("  /approve             — утвердить план (planning → plan_approved)")
    print("  /goto <этап>         — попытка явного перехода (демо контроля переходов)")
    print("  /transitions         — карта переходов + журнал попыток и отказов")
    print("  /step                — один шаг автомата (снимок: этап/шаг/действие)")
    print("  /run                 — крутить автомат до done/failed (не обходит /approve)")
    print("  /pause               — пауза на любом рабочем этапе (состояние сохраняется)")
    print("  /resume              — продолжение с того же шага, без повторных объяснений")
    print("  /deliver <слои>      — набор включаемых слоёв (напр. profile,working)")
    print("  /compare             — сравнение ответа с/без слоя долговременной памяти")
    print("  /summary             — резюме сессий текущей задачи")
    print("  /state               — снимок задачи + task state machine (этапы, переходы)")
    print("  /invariants          — список инвариантов (id, category, severity, active)")
    print("  /invariant add <id> <category> <текст>  — добавить инвариант")
    print("  /invariant set <id> <текст> [--yes]     — изменить (нужно подтверждение)")
    print("  /invariant on|off <id>                  — включить/выключить инвариант")
    print("  /check <действие>    — прогнать действие через проверку инвариантов (демо)")
    print("  /tokens              — локальная оценка токенов последнего запроса")
    print("  /cost                — стоимость обменов (локальная оценка)")
    print("  /help                — эта справка")
    print("  /exit                — завершить и сохранить состояние")
    print()


# 10.1 Обработка семейства команд /profile (персонализация) -------------------------
def handle_profile_command(agent: Agent, user_input: str):
    """Разбирает /profile [list|show|use|new|route|auto]; голое /profile — как раньше."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else ""

    # Голое /profile — активный профиль (обратная совместимость с днём 11).
    if not sub:
        ctx = MemoryContext(agent.user_id, profile_id=agent.active_profile or "")
        profile = agent.memory.layers["profile"].read(ctx)
        active = agent.active_profile or "(default)"
        print(f"[Профиль] активный: {active}\n{profile}\n")
        return

    if sub == "list":
        profiles = agent.store.list_profiles(agent.user_id)
        # Активный профиль: явный выбор сессии, иначе — default из хранилища.
        active = agent.active_profile
        if active is None and agent.store.profile_repo is not None:
            active = agent.store.profile_repo.get_default(agent.user_id)
        print("[Профили]")
        for pid, is_default in profiles:
            marks = ("*" if is_default else " ") + (">" if pid == active else " ")
            print(f"  {marks} {pid}")
        print("  (* — default, > — активный)\n")
        return

    if sub == "show":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile show <id>\n")
            return
        profile = agent.store.load_profile(agent.user_id, parts[2])
        if profile is None:
            print(f"[Профиль] «{parts[2]}» не найден.\n")
            return
        print(f"[Профиль {parts[2]}]\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n")
        return

    if sub == "use":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile use <id>\n")
            return
        if agent.switch_profile(parts[2]):
            print(f"[Профиль] Активный профиль: {parts[2]}\n")
        else:
            print(f"[Профиль] «{parts[2]}» не существует (см. /profile list)\n")
        return

    if sub == "new":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile new <id>\n")
            return
        run_profile_interview(agent, parts[2])
        return

    if sub == "route":
        text = user_input.split(maxsplit=2)
        if len(text) < 3:
            print("[Роутер] Укажите текст: /profile route <текст>\n")
            return
        if agent.router is None:
            print("[Роутер] Недоступен (нет репозитория профилей).\n")
            return
        print(agent.router.explain(agent.user_id, text[2]) + "\n")
        return

    if sub == "auto":
        mode = parts[2] if len(parts) > 2 else ""
        if mode == "on":
            agent.auto_route = True
            print("[Роутер] Авто-роутинг включён (профиль выбирается по каждому запросу).\n")
        elif mode == "off":
            agent.auto_route = False
            print("[Роутер] Авто-роутинг выключен.\n")
        else:
            print(f"[Роутер] Авто-роутинг: {'on' if agent.auto_route else 'off'} "
                  f"(управление: /profile auto on|off)\n")
        return

    print(f"[Профиль] Неизвестная подкоманда: {sub}. См. /help\n")


def run_profile_interview(agent: Agent, profile_id: str):
    """Мини-интервью создания профиля: name, domain, triggers, style, constraints, context."""
    print(f"[Профиль] Создание профиля «{profile_id}» (мини-интервью).")
    name = input("  Имя профиля: ").strip() or profile_id
    domain = input("  Домен (область запросов): ").strip()
    triggers = [t.strip() for t in input("  Триггеры (через запятую): ").split(",") if t.strip()]
    style = input("  Стиль ответов: ").strip()
    constraints = input("  Ограничения: ").strip()
    context = input("  Контекст: ").strip()
    profile = {
        "id": agent.user_id,
        "profile_id": profile_id,
        "name": name,
        "domain": domain,
        "triggers": triggers,
        "style": {"answers": style},
        "constraints": {"answers": constraints},
        "context": {"answers": context},
        "skills": [],
    }
    agent.store.save_profile(agent.user_id, profile, profile_id)
    agent.switch_profile(profile_id)
    print(f"[Профиль] Профиль «{profile_id}» создан и активирован.\n")


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
def show_state(agent: Agent):
    """Полный снимок TaskState + карта переходов + разрешённые из текущей + отказы."""
    st = agent.task_state
    if st is not None:
        steps = st.steps or []
        print("[Состояние задачи]")
        print(f"  Задача: {st.objective} (id: {st.task_id})")
        print(f"  Этап: {st.stage.value}")
        if steps:
            idx = min(st.current_step, len(steps) - 1)
            print(f"  Шаг: {st.current_step}/{len(steps)} — {steps[idx]}")
        else:
            print(f"  Шаг: {st.current_step}/0 (план ещё не построен)")
        if st.expected_action:
            print(f"  Ожидаемое действие: {st.expected_action}")
        if st.previous_stage:
            print(f"  Вернуться после паузы к: {st.previous_stage.value}")
        if st.error:
            print(f"  Ошибка: {st.error}")
        print(f"  Результатов собрано: {len(st.results)}")
        allowed = ALLOWED_TRANSITIONS.get(st.stage, set())
        names = ", ".join(t.value for t in sorted(allowed, key=lambda s: s.value)) or "—"
        print(f"  Разрешённые переходы из {st.stage.value}: {names}")
        refused = sum(1 for e in st.transition_log if not e.get("allowed"))
        print(f"  Отказов в журнале переходов: {refused}")
        print()
    else:
        print("[Состояние задачи] Нет активной задачи (создайте: /plan <цель>)\n")
    print("[State machine] Этапы и разрешённые переходы:")
    for stage in TaskStage:
        targets = ALLOWED_TRANSITIONS.get(stage, set())
        names = ", ".join(t.value for t in sorted(targets, key=lambda s: s.value)) or "—"
        print(f"  {stage.value} → {names}")
    print()



# 12.1 Печать снимка автомата после команд жизненного цикла ------------------------
def print_task_snapshot(agent: Agent, header: str):
    """Компактный снимок: этап, шаг N/M + текст шага, ожидаемое действие, последний результат."""
    st = agent.task_state
    print(f"[{header}]")
    if st is None:
        print("  Нет активной задачи (сначала /plan <цель>)\n")
        return
    steps = st.steps or []
    step_view = f"{st.current_step}/{len(steps)}"
    if steps:
        idx = min(st.current_step, len(steps) - 1)
        step_view += f" — {steps[idx]}"
    print(f"  Этап: {st.stage.value} | Шаг: {step_view}")
    if st.expected_action:
        print(f"  Ожидаемое действие: {st.expected_action}")
    if st.stage.value == "paused" and st.previous_stage:
        print(f"  Вернуться после паузы к: {st.previous_stage.value}")
    if st.error:
        print(f"  Ошибка: {st.error}")
    if st.results:
        last = str(st.results[-1])
        print(f"  Последний результат: {last[:120]}")
    print()


# 12.2 Инварианты: список/добавление/изменение/вкл-выкл + демонстрация проверки ---------
def handle_invariants_command(agent: Agent, user_input: str):
    """Разбирает /invariants и /invariant add|set|on|off (День 14).

    /invariants                       — список правил задачи;
    /invariant add <id> <cat> <текст> — добавить правило;
    /invariant set <id> <текст> [--yes] — изменить (без --yes требует подтверждения);
    /invariant on|off <id>            — включить/выключить.
    """
    parts = user_input.split()
    command = parts[0]

    # /invariants — список.
    if command == "/invariants":
        if not agent.constraints.invariants:
            print("[Инварианты] Набор пуст (все действия разрешены). "
                  "Добавить: /invariant add <id> <category> <текст>\n")
            return
        print(f"[Инварианты] Задача «{agent.task}»:")
        for inv in agent.constraints.invariants:
            flag = "on " if inv.active else "off"
            print(f"  [{flag}] {inv.id} | {inv.category} | {inv.severity} | {inv.description}")
        print()
        return

    # /invariant <sub> ...
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "add":
        if len(parts) < 5:
            print("[Инварианты] Формат: /invariant add <id> <category> <текст>\n")
            return
        inv_id, category = parts[2], parts[3]
        text = user_input.split(maxsplit=4)[4].strip()
        agent.add_invariant(Invariant(id=inv_id, category=category, description=text))
        print(f"[Инварианты] Добавлен {inv_id} ({category}).\n")
        return

    if sub == "set":
        if len(parts) < 4:
            print("[Инварианты] Формат: /invariant set <id> <текст> [--yes]\n")
            return
        inv_id = parts[2]
        authorized = "--yes" in parts
        text = user_input.split(maxsplit=3)[3]
        if authorized:
            text = text.replace("--yes", "").strip()
        try:
            agent.update_invariant(inv_id, text, authorized=authorized)
            print(f"[Инварианты] Изменён {inv_id}.\n")
        except PermissionError as error:
            print(f"[Инварианты] {error} Повторите с --yes для подтверждения.\n")
        except KeyError as error:
            print(f"[Инварианты] {error}\n")
        return

    if sub in ("on", "off"):
        if len(parts) < 3:
            print(f"[Инварианты] Формат: /invariant {sub} <id>\n")
            return
        inv_id = parts[2]
        if agent.toggle_invariant(inv_id, sub == "on"):
            print(f"[Инварианты] {inv_id} → {sub}.\n")
        else:
            print(f"[Инварианты] Инвариант «{inv_id}» не найден.\n")
        return

    print("[Инварианты] Подкоманды: add | set | on | off (см. /help)\n")


def check_demonstration(agent: Agent, user_input: str):
    """ /check <действие> — прогнать ProposedAction через InvariantChecker (без исполнения)."""
    parts = user_input.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        print("[Проверка] Укажите действие: /check <описание действия>\n")
        return
    text = parts[1].strip()
    action = agent.propose_action(text)
    violations = agent.check_invariants(action)
    warnings = agent.invariant_warnings(action)
    print(f"[Проверка] Действие: {action.description}")
    print(f"  technology={action.technology} | language={action.language} | "
          f"adds_dependency={action.adds_dependency} | "
          f"changes_database_schema={action.changes_database_schema}")
    if violations:
        print("  Результат: ЗАПРЕЩЕНО. Нарушения:")
        for violation in violations:
            print(f"    - {violation}")
    else:
        print("  Результат: разрешено (блокирующих нарушений нет).")
    for warning in warnings:
        print(f"  ⚠ {warning}")
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
        # --fresh: сохранённое состояние задачи игнорируется — старт с PLANNING.
        if args.fresh:
            agent.task_state = None
            # ...и сохранённый набор инвариантов не восстанавливается (arch_den_14 §2.12).
            agent.constraints = ConstraintSet()

    # Флаг --profile: активный профиль на старте (после идентификации).
    # Несуществующий профиль → предупреждение и default (active_profile=None).
    if args.profile:
        if agent.switch_profile(args.profile):
            print(f"[Профиль] Активный профиль на старте: {args.profile}")
        else:
            print(f"[Профиль] ⚠ Профиль «{args.profile}» не найден — использую default.")

    # Применяем --deliver (набор слоёв по умолчанию).
    deliver = {part.strip() for part in args.deliver.split(",") if part.strip()}
    agent.deliver = deliver & set(DELIVERABLE)
    # Бюджет промта: None — обрезание выключено (поведение не меняется).
    agent.prompt_budget = args.budget
    print(f"[Режим] Доставка слоёв: {sorted(agent.deliver)}")
    if args.budget is not None:
        print(f"[Режим] Бюджет промта: {args.budget} токенов "
              f"(необязательные блоки опускаются)")
    if args.mock:
        print("[Режим] MockClient (заглушка) — живых запросов к API не будет.")
    print("Команды: /memory /profile [list|show|use|new|route|auto] /tasks /task [retry] "
          "/plan /approve /goto /transitions /step /run /pause /resume /deliver /compare "
          "/summary /state /tokens /cost /help /exit\n")

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
                    handle_profile_command(agent, user_input)
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
                        print("[Задача] Укажите имя: /task <имя> | /task retry\n")
                        continue
                    arg = parts[1].strip()
                    if arg == "retry":
                        # Восстановление из failed → planning (единственный выход).
                        if agent.retry_task():
                            print("[Задача] Повтор: failed → planning, шаги и результаты очищены.\n")
                        else:
                            print("[Задача] /task retry: задача не в состоянии failed.\n")
                        continue
                    agent.switch_task(arg)
                    print(f"[Задача] Переключился на «{arg}»\n")
                    continue
                if command == "/plan":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or not parts[1].strip():
                        print("[План] Укажите цель: /plan <цель задачи>\n")
                        continue
                    objective = parts[1].strip()
                    agent.start_task(objective)
                    # Первый проход: new → planning (план построен, ожидает /approve).
                    agent.step_task()
                    print_task_snapshot(agent, "План")
                    continue
                if command == "/approve":
                    print(agent.approve_plan() + "\n")
                    continue
                if command == "/goto":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or not parts[1].strip():
                        stages = ", ".join(s.value for s in TaskStage)
                        print(f"[Переход] Укажите стадию: /goto <этап>. Стадии: {stages}\n")
                        continue
                    print(agent.attempt_transition(parts[1].strip()) + "\n")
                    continue
                if command == "/transitions":
                    print(agent.transitions_report() + "\n")
                    continue
                if command == "/step":
                    if agent.task_state is None:
                        print("[Шаг] Нет активной задачи (сначала /plan <цель>)\n")
                        continue
                    agent.step_task()
                    print_task_snapshot(agent, "Шаг")
                    continue
                if command == "/run":
                    if agent.task_state is None:
                        print("[Прогон] Нет активной задачи (сначала /plan <цель>)\n")
                        continue
                    agent.run_to_end()
                    print_task_snapshot(agent, "Прогон")
                    continue
                if command == "/pause":
                    if agent.pause():
                        print_task_snapshot(agent, "Пауза")
                    continue
                if command == "/resume":
                    if agent.resume():
                        print_task_snapshot(agent, "Продолжение")
                    continue
                if command == "/deliver":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        print("[Доставка] Укажите слои: /deliver profile,working\n")
                        continue
                    chosen = {p.strip() for p in parts[1].split(",") if p.strip()}
                    agent.deliver = chosen & set(DELIVERABLE)
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
                    show_state(agent)
                    continue
                if command == "/invariants":
                    handle_invariants_command(agent, user_input)
                    continue
                if command == "/invariant":
                    handle_invariants_command(agent, user_input)
                    continue
                if command == "/check":
                    check_demonstration(agent, user_input)
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
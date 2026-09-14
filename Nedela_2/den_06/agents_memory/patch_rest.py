import io

PATH = "/home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9/Nedela_2/den_06/den_6_Kod.py"

with io.open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

def rep(old, new, tag):
    global src
    n = src.count(old)
    assert n == 1, f"[{tag}] ожидалось 1 совпадение, найдено {n}"
    src = src.replace(old, new)
    print(f"OK: {tag}")

# ---------- ШАГ 9б: reconfigure stdout ----------
rep(
"""sys.stdin.reconfigure(encoding='utf-8', errors='replace')

# Проверяем, удалось ли найти API-ключ.""",
"""sys.stdin.reconfigure(encoding='utf-8', errors='replace')

# Настраиваем кодировку stdout: при выводе в перенаправленный не-UTF-8 поток
# «непечатаемые» символы заменяются заглушкой вместо UnicodeEncodeError.
sys.stdout.reconfigure(errors='replace')

# Проверяем, удалось ли найти API-ключ.""",
"шаг 9б: stdout.reconfigure")

# ---------- ШАГ 7: /help в KNOWN_COMMANDS ----------
rep(
"""    "/save",
    "/load_history",
    "/clear",
    "/exit",
)""",
"""    "/save",
    "/load_history",
    "/clear",
    "/help",
    "/exit",
)""",
"шаг 7: /help в KNOWN_COMMANDS")

# ---------- ШАГ 4: публичный get_user_message ----------
rep(
"""        # Возвращаем признак успеха.
        return True

    # Сохранение саммари в файл (перезапись целиком при каждом обновлении).
    def save_summary(self, filepath: str):""",
"""        # Возвращаем признак успеха.
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

    # Сохранение саммари в файл (перезапись целиком при каждом обновлении).
    def save_summary(self, filepath: str):""",
"шаг 4: get_user_message")

# ---------- ШАГ 4: cmd_layer показывает сообщение из активной истории ----------
rep(
"""    # Находим изменённое сообщение, чтобы показать результат пользователю.
    user_messages = [msg for msg in agent.get_history() if msg["role"] == "user"]

    # Берём сообщение пользователя по номеру (1 — последнее).
    target = user_messages[-number]

    # Сообщаем пользователю об успешной смене слоя.
    print(f"[Слой] Сообщение изменено: {target['content'][:50]} → {parts[2]}\\n")""",
"""    # Текст изменённого сообщения берём у агента по той же нумерации, что и
    # в set_layer (активная история, 1 — последнее сообщение пользователя).
    # Раньше здесь использовался get_history() (архив + активные) — после
    # сжатия номер указывал на чужое/архивное сообщение.
    changed_text = agent.get_user_message(number)

    # Сообщаем пользователю об успешной смене слоя.
    print(f"[Слой] Сообщение изменено: {changed_text[:50]} → {parts[2]}\\n")""",
"шаг 4: cmd_layer")

# ---------- ШАГ 6: layered загружает саммари ----------
rep(
"""        # Для layered-памяти: саммари + выбранные слои из лога.
        # Разбираем значение --load в множество выбираемых слоёв.
        chosen = self._parse_load_layers(self.load_layers)""",
"""        # Для layered-памяти: саммари + выбранные слои из лога.
        # Загружаем саммари прошлой сессии (симметрично compressed-ветке):
        # /exit для layered саммари сохраняет, значит его нужно и поднимать.
        self.load_summary(SUMMARY_FILE)

        # Если саммари найдено и не пустое — сообщаем пользователю о загрузке.
        if self.summary:
            # Печатаем уведомление с длиной загруженного саммари в символах.
            print(f"[Память] Загружено саммари прошлой сессии ({len(self.summary)} символов)")

        # Разбираем значение --load в множество выбираемых слоёв.
        chosen = self._parse_load_layers(self.load_layers)""",
"шаг 6: layered load_summary")

# ---------- ШАГ 8: /clear удаляет файл саммари ----------
rep(
"""        # Для compressed и layered сбрасываем и саммари.
        if self.memory_type in ("compressed", "layered"):
            # Сбрасываем саммари в памяти.
            self.summary = \"\"""",
"""        # Для compressed и layered сбрасываем и саммари.
        if self.memory_type in ("compressed", "layered"):
            # Сбрасываем саммари в памяти.
            self.summary = ""

            # Удаляем файл саммари на диске: иначе после перезапуска вернётся
            # старое саммари из файла и /clear окажется неполным.
            if os.path.exists(SUMMARY_FILE):
                # Удаляем файл саммари.
                os.remove(SUMMARY_FILE)""",
"шаг 8: /clear удаляет SUMMARY_FILE")

# ---------- ШАГ 7: cmd_help ----------
rep(
"""# Обработчик /compress: принудительное сжатие (для compression и leveling).
def cmd_compress(agent):""",
"""# Обработчик /help: список команд с пометкой доступности в текущем режиме.
def cmd_help(agent, args):
    # Печатаем заголовок справки.
    print("[Справка] Доступные команды:")

    # /history — доступна во всех режимах.
    print("  /history — показать историю диалога (все режимы)")

    # /window — только для sliding-window.
    if args.context == "sliding_window":
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

    # /save — доступна во всех режимах.
    print("  /save — сохранить историю в лог-файл (все режимы)")

    # /load_history — ручная загрузка лога только для session.
    if args.memory == "session":
        # Команда доступна в текущем режиме памяти.
        print("  /load_history — загрузить лог в контекст (session)")
    else:
        # В compressed/layered память поднимается автоматически при старте.
        print(f"  /load_history — не нужна: память загружается автоматически (memory={args.memory})")

    # /clear, /help, /exit — доступны во всех режимах.
    print("  /clear — очистить контекст (все режимы)")
    print("  /help — эта справка (все режимы)")
    print("  /exit — завершить работу (все режимы)")
    print()


# Обработчик /compress: принудительное сжатие (для compression и leveling).
def cmd_compress(agent):""",
"шаг 7: cmd_help")

# ---------- ШАГ 7: обработчик /help в главном цикле ----------
rep(
"""        # Обрабатываем команду /history — доступна во всех режимах.
        if user_input == "/history":""",
"""        # Обрабатываем команду /help — доступна во всех режимах.
        if user_input == "/help":
            # Печатаем справку по командам с учётом текущего режима.
            cmd_help(agent, args)
            # Переходим к следующей итерации цикла.
            continue

        # Обрабатываем команду /history — доступна во всех режимах.
        if user_input == "/history":""",
"шаг 7: обработчик /help")

# ---------- ШАГ 4: /layer без аргументов не уходит в LLM ----------
rep(
"""        # Обрабатываем команду /layer — только для layered.
        if user_input.startswith("/layer "):""",
"""        # Обрабатываем команду /layer — только для layered.
        # Ловим и «/layer» без аргументов: иначе строка ушла бы в LLM.
        if user_input == "/layer" or user_input.startswith("/layer "):""",
"шаг 4: /layer без аргументов")

# ---------- ШАГ 7: упомянуть /help в стартовой шапке ----------
rep(
"""print("Введите /exit для завершения.\\n")""",
"""print("Введите /help для списка команд, /exit для завершения.\\n")""",
"шаг 7: шапка /help")

# ---------- ШАГ 9а: try вокруг стартовой дозаписи приветствия ----------
rep(
"""# Дозаписываем приветствие в лог с отметкой времени.
with open(LOG_FILE, "a", encoding="utf-8") as f:
    # Пишем разделитель с текущими датой и временем.
    f.write(f"\\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
    # Для layered-памяти пишем приветствие с пометкой слоя low.
    if args.memory == "layered":
        # Пишем приветствие как реплику агента с нейтральным слоем low.
        f.write(f"**Агент** [low]: {GREETING}\\n")
    # Для остальных режимов — обычная строка.
    else:
        # Пишем приветствие как реплику агента.
        f.write(f"**Агент:** {GREETING}\\n")""",
"""# Дозаписываем приветствие в лог с отметкой времени.
# Оборачиваем в try: сбой записи (нет прав/диск) не должен валить программу
# до первого ввода — сообщаем об ошибке и продолжаем работу.
try:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        # Пишем разделитель с текущими датой и временем.
        f.write(f"\\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n")
        # Для layered-памяти пишем приветствие с пометкой слоя low.
        if args.memory == "layered":
            # Пишем приветствие как реплику агента с нейтральным слоем low.
            f.write(f"**Агент** [low]: {GREETING}\\n")
        # Для остальных режимов — обычная строка.
        else:
            # Пишем приветствие как реплику агента.
            f.write(f"**Агент:** {GREETING}\\n")
# Сбой записи приветствия не критичен: пишем в журнал и продолжаем.
except OSError as error:
    # Фиксируем ошибку в журнале ошибок.
    log_error("Не удалось записать приветствие в лог", error)""",
"шаг 9а: try вокруг приветствия")

# ---------- ШАГ 10: EOFError на input в except Exception ----------
rep(
"""    # Перехватываем любую другую непредвиденную ошибку в теле цикла.
    except Exception as error:
        # Записываем полный стек ошибки в журнал ошибок.
        log_error("Ошибка в главном цикле", error)
        # Просим нажать Enter, чтобы окно не закрылось мгновенно.
        input("Нажмите Enter для продолжения...")""",
"""    # Перехватываем любую другую непредвиденную ошибку в теле цикла.
    except Exception as error:
        # Записываем полный стек ошибки в журнал ошибок.
        log_error("Ошибка в главном цикле", error)
        # Просим нажать Enter, чтобы окно не закрылось мгновенно.
        # Ctrl+D на этом вводе тоже должен завершать программу корректно.
        try:
            input("Нажмите Enter для продолжения...")
        except EOFError:
            # Ввод завершён (Ctrl+D) — выходим из цикла без ошибки.
            print("\\n[Выход] Ввод завершён (EOF)")
            break""",
"шаг 10: EOFError на input")

with io.open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("Все патчи применены.")

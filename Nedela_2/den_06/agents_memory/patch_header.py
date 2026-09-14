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

# Шаг 5: перечень команд в шапке файла.
rep(
"""# Запуск:
#   python den_06/den_6_Kod.py --context sliding-window --memory session
#   python den_06/den_6_Kod.py --context compression --memory compressed
#   python den_06/den_6_Kod.py --context leveling --memory layered
# ============================================================================""",
"""# Запуск:
#   python den_06/den_6_Kod.py --context sliding-window --memory session
#   python den_06/den_6_Kod.py --context compression --memory compressed
#   python den_06/den_6_Kod.py --context leveling --memory layered
#
# Команды в чате (полный список — по /help):
#   /history      — показать историю диалога (все режимы)
#   /window       — параметры окна контекста (sliding-window)
#   /summary      — показать текущее саммари (compressed/layered)
#   /compress     — принудительно сжать историю в саммари (compressed/layered)
#   /layers       — статистика слоёв (layered)
#   /layer <N> <high|mid|low> — сменить приоритет сообщения (layered)
#   /save         — сохранить историю в лог-файл (все режимы)
#   /load_history — загрузить лог в контекст (session)
#   /clear        — очистить контекст (все режимы)
#   /help         — справка по командам (все режимы)
#   /exit         — завершить работу (все режимы)
# ============================================================================""",
"шаг 5: перечень команд в шапке")

with io.open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("Патч применён.")
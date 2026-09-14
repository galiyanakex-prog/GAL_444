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

# Шаг 9а (дополнение): создание лог-файла тоже не должно валить программу.
rep(
"""# Заголовок лог-файла: создаём файл с шапкой, если его ещё нет.
if not os.path.exists(LOG_FILE):
    # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        # Пишем заголовок с режимами и размером окна.
        f.write(
            f"# Лог диалога — День 6 (контекст={args.context}, память={args.memory}, окно={WINDOW})\\n\\n"
        )""",
"""# Заголовок лог-файла: создаём файл с шапкой, если его ещё нет.
# Оборачиваем в try: сбой создания (нет прав/каталога) не должен валить
# программу до первого ввода — сообщаем об ошибке и продолжаем работу.
if not os.path.exists(LOG_FILE):
    # Пробуем создать файл с шапкой.
    try:
        # Открываем файл на запись (создаём новый) с кодировкой UTF-8.
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            # Пишем заголовок с режимами и размером окна.
            f.write(
                f"# Лог диалога — День 6 (контекст={args.context}, память={args.memory}, окно={WINDOW})\\n\\n"
            )
    # Сбой создания лога не критичен: пишем в журнал и продолжаем.
    except OSError as error:
        # Фиксируем ошибку в журнале ошибок.
        log_error("Не удалось создать лог-файл", error)""",
"шаг 9а: try вокруг создания лога")

with io.open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("Патч применён.")

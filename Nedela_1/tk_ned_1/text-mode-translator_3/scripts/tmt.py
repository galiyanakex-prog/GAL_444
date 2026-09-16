#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tmt.py — конвейер слоёв скилла text-mode-translator_3 (v3, layer architecture).

Архитектура:
  L1 IN    RU -> machine English   (слой «перевести русский текст на machine English»)
  L2 CORE  machine English only    (рассуждения агента; скрипт не участвует, русский запрещён)
  L3 OUT   machine English -> RU   (только то, что требует реакции пользователя)

Русский остаётся только на двух границах. Всё промежуточное живёт на machine
English, чтобы свести к минимуму русскоязычный обмен токенами с LLM.

Режимы:
  in        RU -> EN machine                  (алиас: compress)
  out       EN machine -> RU                  (алиас: restore)
  gate      internal block -> USER:-строки -> RU   (главный режим L3)
  batch     несколько EN строк -> RU одним запросом
  roundtrip RU -> EN machine -> RU
  ask       RU -> EN machine -> ответ модели на EN machine -> RU

Экономия квоты:
  - gate на молчаливом ходе (нет USER:-строк) = 0 запросов, exit 3;
  - односложные ответы («да», «продолжай», ...) разрешаются таблицей = 0 запросов;
  - повтор того же текста берётся из кэша = 0 запросов;
  - серия пользовательских строк идёт одним batch-запросом, а не серией out.

Токен никогда не печатается.
"""

import argparse  # разбор аргументов командной строки
import hashlib   # ключ кэша
import json      # кэш и вывод --json
import os        # переменные окружения
import re        # разбор USER:-строк и нумерованного вывода batch
import sys       # stdin/stdout, коды выхода
import time      # паузы при ретраях 429
from pathlib import Path  # пути токена и кэша

import requests  # HTTP-запросы к эндпоинту Koda

API_URL = "https://api.kodacode.ru/v1/chat/completions"  # внутренний эндпоинт Koda
ALLOWED_MODELS = ("koda-pro", "koda-base")  # другие модели запрещены
DEFAULT_MODEL = "koda-pro"  # совпадает с "model" в ~/.kodacli/settings.json
CREDENTIALS_FILE = Path.home() / ".config" / "koda" / "credentials.json"
CACHE_FILE = Path(__file__).resolve().parent.parent / ".cache" / "tmt_cache.json"
REQUEST_TIMEOUT = 30  # секунд на один запрос
RETRY_DELAYS = [2, 4, 8]  # паузы при 429
TEMPERATURE = 0.2  # перевод должен быть детерминированным
MAX_TOKENS_DEFAULT = 900  # потолок вывода: слои короткие, лишнее — перерасход
CACHE_LIMIT = 500  # сколько записей держать в кэше

MODES = ("in", "out", "gate", "batch", "roundtrip", "ask", "compress", "restore")
ALIASES = {"compress": "in", "restore": "out"}

# Промпты слоёв. Держатся короткими: чем меньше мусора, тем стабильнее формат.
# Отдельного промпта для gate нет: фильтрация USER:-строк детерминирована
# в коде, переводится уже отфильтрованный текст промптом "out".
PROMPTS = {
    "in": (
        "Translate the given Russian text into machine English. "
        "Rules: short telegraphic English, noun phrases and imperative fragments, "
        "no politeness, no fluff, no explanations, no Russian words. "
        "Preserve meaning and every constraint exactly. Add nothing. Remove nothing. "
        "Keep identifiers, file names, numbers and units verbatim. "
        "Output ONLY the machine English text."
    ),
    "out": (
        "Translate the given machine English into clear natural Russian. "
        "Rules: natural Russian wording, expand only what clarity requires, "
        "keep structure and intent, do not over-explain, add no facts, "
        "no greetings and no sign-offs. Keep code, paths, identifiers and numbers verbatim. "
        "Output ONLY the Russian text."
    ),
    "batch": (
        "Translate each numbered machine English item into clear natural Russian. "
        "Keep the same numbering, one line per item, no extra text, no explanations. "
        "Keep code, paths, identifiers and numbers verbatim."
    ),
    "answer": (
        "You answer the user's request. "
        "Reply ONLY in compact machine English: telegraphic, short fragments, "
        "no politeness, no fluff, no Russian words. Keep the answer factual and complete."
    ),
}

# Односложные ответы разрешаются таблицей: конвейер не тратит запросы на ерунду.
SHORT_ANSWERS = {
    "да": "yes", "нет": "no", "ок": "ok", "хорошо": "ok", "ладно": "ok",
    "продолжай": "continue", "продолжать": "continue", "далее": "next",
    "отмена": "cancel", "отмени": "cancel", "стоп": "stop",
    "спасибо": "thanks", "сам реши": "you decide", "на твоё усмотрение": "you decide",
    "ясно": "understood", "понятно": "understood",
}

USER_LINE = re.compile(r"^\s*(?:[-*]\s*)?USER\s*:\s*(.*)$", re.IGNORECASE)
FENCE_LINE = re.compile(r"^\s*```")


def get_token(args):
    """Токен koda-auth или None. Приоритет: --token-file, KODA_AUTH_TOKEN, credentials.json."""
    if args.token_file:
        path = Path(args.token_file).expanduser()
        if path.is_file():
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            if lines and lines[0].strip():
                return lines[0].strip()
        return None
    from_env = os.getenv("KODA_AUTH_TOKEN")
    if from_env:
        return from_env.strip()
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        token = data.get("kodaAuth", {}).get("accessToken")
        return str(token).strip() if token else None
    except (OSError, ValueError):
        return None


def call_llm(system_prompt, user_text, args):
    """Один запрос к эндпоинту Koda. Возвращает текст ответа или None при ошибке.

    Токен берётся лениво и только когда запрос реально нужен: ход, закрытый
    кэшем или таблицей коротких ответов, обходится без токена.
    """
    token = get_token(args)
    if token is None:
        sys.stderr.write("[Конфиг] Токен koda-auth не найден: выполните вход в koda-cli "
                         "или передайте --token-file\n")
        sys.exit(2)
    body = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": args.temperature,
    }
    if args.max_tokens:
        body["max_tokens"] = args.max_tokens
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.post(API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429:
                if attempt < len(RETRY_DELAYS):
                    sys.stderr.write("[API] 429, повтор через %d сек\n" % RETRY_DELAYS[attempt])
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                sys.stderr.write("[API] 429: лимит запросов, повторы исчерпаны\n")
                return None
            response.raise_for_status()
            payload = response.json()
            return payload["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as error:
            sys.stderr.write("[API] Ошибка запроса: %s\n" % error)
            return None
        except (KeyError, IndexError, ValueError) as error:
            sys.stderr.write("[API] Неожиданный формат ответа: %s\n" % error)
            return None
    return None


def cache_key(args, kind, source):
    return hashlib.sha256(("%s|%s|%s" % (kind, args.model, source)).encode("utf-8")).hexdigest()


def load_cache(args):
    """Кэш переводов: повторяющиеся формулировки не должны стоить запросов."""
    if args.no_cache:
        return {}
    try:
        data = json.loads(Path(args.cache).expanduser().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(args, cache):
    if args.no_cache or not cache:
        return
    path = Path(args.cache).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Кэш ограничивается сверху, иначе файл разрастается бесконечно.
        keys = list(cache.keys())[-CACHE_LIMIT:]
        trimmed = {k: cache[k] for k in keys}
        path.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # кэш — оптимизация, а не обязательная часть конвейера


def cached(args, cache, kind, source):
    """(hit, value): значение из кэша по тройке (слой, модель, текст)."""
    if args.no_cache:
        return False, None
    entry = cache.get(cache_key(args, kind, source))
    if isinstance(entry, str) and entry:
        return True, entry
    return False, None


def remember(args, cache, kind, source, value):
    if args.no_cache or not value:
        return
    cache[cache_key(args, kind, source)] = value


def read_input(args):
    """Текст для обработки: из --text, --file или stdin."""
    if args.text is not None:
        return args.text.strip()
    if args.file:
        return Path(args.file).expanduser().read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def strip_internal_block(source):
    """Снимает обёртку ```internal ... ```, если агент передал блок целиком."""
    lines = source.splitlines()
    if lines and FENCE_LINE.match(lines[0]):
        lines = lines[1:]
        if lines and FENCE_LINE.match(lines[-1]):
            lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_user_lines(source):
    """Gate: только строки USER:, в исходном порядке, без префикса."""
    kept = [m.group(1).strip() for m in (USER_LINE.match(line) for line in source.splitlines()) if m]
    return [line for line in kept if line]


def step(name, payload, args, cache, kind=None):
    """Шаг конвейера с кэшем. Сухой прогон не трогает API. Провал шага = exit 1."""
    kind = kind or name
    hit, value = cached(args, cache, kind, payload)
    if hit:
        sys.stderr.write("[Cache] Шаг '%s' взят из кэша\n" % name)
        return value
    if args.dry_run:
        return "[dry-run] %s: %s" % (name, payload[:80])
    out = call_llm(PROMPTS[kind], payload, args)
    if out is None:
        sys.stderr.write("[Конвейер] Шаг '%s' не выполнен\n" % name)
        sys.exit(1)
    remember(args, cache, kind, payload, out)
    return out


def run_in(source, args, cache, result):
    """L1 IN: RU -> machine English. Односложные ответы — таблицей, без запроса."""
    normalized = source.strip().rstrip("!?.。").lower()
    if normalized in SHORT_ANSWERS:
        result["in"] = SHORT_ANSWERS[normalized]
        result["table_hit"] = True
        sys.stderr.write("[Table] Односложный ответ разрешён без запроса\n")
        return result["in"]
    result["in"] = step("in", source, args, cache, kind="in")
    return result["in"]


def run_out(source, args, cache, result):
    """L3 OUT: machine English -> русский."""
    result["out"] = step("out", source, args, cache, kind="out")
    return result["out"]


def run_batch(source, args, cache, result):
    """Несколько пользовательских строк — одним запросом вместо серии out."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    if not lines:
        sys.stderr.write("[Вход] Batch: пустой список строк\n")
        sys.exit(2)
    if len(lines) == 1:
        return run_out(lines[0], args, cache, result)
    payload = "\n".join("%d. %s" % (i, line) for i, line in enumerate(lines, 1))
    raw = step("batch", payload, args, cache, kind="batch")
    parsed = {}
    for match in re.finditer(r"(?m)^(\d+)[.)]\s*(.+)$", raw):
        parsed[int(match.group(1))] = match.group(2).strip()
    restored = []
    for i, line in enumerate(lines, 1):
        # Нераспознанная моделью строка остаётся на EN: лучше честный EN,
        # чем молчаливая подстановка или ручной перевод.
        restored.append(parsed.get(i, line))
    result["out"] = "\n".join(restored)
    return result["out"]


def run_pipeline(args, cache):
    source = read_input(args)
    if not source:
        sys.stderr.write("[Вход] Пустой текст: передайте --text, --file или stdin\n")
        sys.exit(2)

    mode = ALIASES.get(args.mode, args.mode)
    result = {"mode": args.mode, "source": source}

    if mode == "in":
        run_in(source, args, cache, result)
    elif mode == "out":
        run_out(source, args, cache, result)
    elif mode == "batch":
        run_batch(source, args, cache, result)
    elif mode == "gate":
        kept = extract_user_lines(strip_internal_block(source))
        if not kept:
            sys.stderr.write("[Gate] Пользовательских строк нет — молчаливый ход, 0 запросов\n")
            sys.exit(3)
        result["user_lines"] = kept
        run_batch("\n".join(kept), args, cache, result)
    elif mode == "roundtrip":
        compressed = run_in(source, args, cache, result)
        run_out(compressed, args, cache, result)
    else:  # ask
        compressed = run_in(source, args, cache, result)
        answer = step("answer", compressed, args, cache, kind="answer")
        result["answer_en"] = answer
        run_out(answer, args, cache, result)

    return result


def output(result, args):
    """Печатает результат: JSON, --raw (только русский) или блоками с метками."""
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.raw and "out" in result:
        print(result["out"])
        return
    for key, label in (("in", "IN"), ("answer_en", "ANSWER-EN"), ("out", "OUT")):
        if key in result:
            print("[%s]\n%s\n" % (label, result[key]))


def main():
    parser = argparse.ArgumentParser(
        description="Конвейер слоёв RU <-> EN machine (L1 IN / L2 CORE / L3 OUT) "
                    "через внутренний эндпоинт Koda")
    parser.add_argument("--mode", choices=list(MODES), default="roundtrip",
                        help="in=RU->EN (алиас compress), out=EN->RU (алиас restore), "
                             "gate=фильтр USER:-строк + RU, batch=несколько строк одним "
                             "запросом, roundtrip, ask")
    parser.add_argument("--text", help="текст для обработки")
    parser.add_argument("--file", help="файл с текстом (UTF-8)")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=list(ALLOWED_MODELS),
                        help="модель Koda: koda-pro (по умолчанию) или koda-base")
    parser.add_argument("--temperature", type=float, default=TEMPERATURE,
                        help="температура модели (0..2)")
    parser.add_argument("--max-tokens", type=int, default=MAX_TOKENS_DEFAULT,
                        help="потолок выводных токенов (0 = не передавать)")
    parser.add_argument("--token-file", help="файл с токеном koda-auth (первая строка)")
    parser.add_argument("--cache", default=str(CACHE_FILE), help="файл кэша переводов")
    parser.add_argument("--no-cache", action="store_true", help="отключить кэш")
    parser.add_argument("--raw", action="store_true",
                        help="печатать только текст без меток (для L3-вывода)")
    parser.add_argument("--json", action="store_true", help="вывести результат JSON-ом")
    parser.add_argument("--dry-run", action="store_true", help="собрать конвейер без запросов к API")
    args = parser.parse_args()

    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    cache = load_cache(args)
    try:
        result = run_pipeline(args, cache)
    finally:
        save_cache(args, cache)  # кэш сохраняется и при exit 3, и при exit 1
    output(result, args)


if __name__ == "__main__":
    main()
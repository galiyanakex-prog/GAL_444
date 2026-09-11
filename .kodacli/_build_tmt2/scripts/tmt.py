#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tmt.py — конвейер скилла text-mode-translator_2.

Отличие от v1 (text-mode-translator): преобразование выполняет не сам агент,
а внешняя модель stepfun/step-3.5-flash через RouterAI. Агент лишь запускает
этот скрипт и возвращает пользователю финальный русский текст.

Режимы:
  compress   RU -> EN machine
  restore    EN machine -> RU
  roundtrip  RU -> EN machine -> RU (по умолчанию)
  ask        RU -> EN machine -> ответ модели на EN machine -> RU

Ключ API берётся из API_KEY: переменная окружения либо ближайший .env
(поиск от текущего каталога вверх). Ключ никогда не печатается.
"""

import argparse  # разбор аргументов командной строки
import json      # вывод результата в машиночитаемом виде (--json)
import os        # переменные окружения
import sys       # stdin/stdout, коды выхода
import time      # паузы при ретраях 429
from pathlib import Path  # поиск .env по дереву каталогов

import requests  # HTTP-запросы к RouterAI
from dotenv import load_dotenv  # чтение .env

API_URL = "https://routerai.ru/api/v1/chat/completions"  # OpenAI-совместимый чат-эндпоинт RouterAI
MODEL = "stepfun/step-3.5-flash"  # основная модель проекта AI_9
REQUEST_TIMEOUT = 30  # секунд на один запрос
RETRY_DELAYS = [2, 4, 8]  # паузы при 429, как в Den_6_Kod*.py
TEMPERATURE = 0.2  # низкая температура: перевод должен быть детерминированным

# Системные промпты режимов. Держатся короткими: чем меньше мусора,
# тем стабильнее формат ответа модели.
PROMPTS = {
    "compress": (
        "You compress Russian text into compact machine English. "
        "Rules: short English, telegraphic, noun phrases and imperative fragments, "
        "no politeness, no fluff, no explanations. "
        "Preserve meaning and every constraint exactly. Add nothing. Remove nothing. "
        "Output ONLY the compressed English text."
    ),
    "restore": (
        "You restore compact machine English into clear natural Russian. "
        "Rules: natural Russian wording, expand only what clarity requires, "
        "keep structure and intent, do not over-explain, do not add facts. "
        "Output ONLY the Russian text."
    ),
    "answer": (
        "You answer the user's request. "
        "Reply ONLY in compact machine English: telegraphic, short fragments, "
        "no politeness, no fluff, no Russian words. Keep the answer factual and complete."
    ),
}


def find_env_file(explicit):
    """Возвращает путь к .env или None. Приоритет: явный флаг, TMT_ENV_FILE, поиск вверх от CWD."""
    if explicit:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() else None
    from_env = os.getenv("TMT_ENV_FILE")
    if from_env:
        candidate = Path(from_env).expanduser()
        return candidate if candidate.is_file() else None
    cwd = Path.cwd()
    for base in [cwd, *cwd.parents]:  # поднимаемся до корня файловой системы
        candidate = base / ".env"
        if candidate.is_file():
            return candidate
    return None


def get_api_key(explicit_env):
    """Загружает .env и возвращает API_KEY (или None)."""
    env_file = find_env_file(explicit_env)
    if env_file:
        load_dotenv(env_file)
    return os.getenv("API_KEY") or None


def call_llm(system_prompt, user_text, model, temperature):
    """Один запрос к модели. Возвращает текст ответа или None при ошибке."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
    }
    headers = {"Authorization": "Bearer " + str(os.getenv("API_KEY")), "Content-Type": "application/json"}
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.post(API_URL, headers=headers, json=body, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429:  # повтор запроса после паузы
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


def read_input(args):
    """Текст для обработки: из --text, --file или stdin."""
    if args.text is not None:
        return args.text.strip()
    if args.file:
        return Path(args.file).expanduser().read_text(encoding="utf-8").strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def run_pipeline(args):
    """Выполняет выбранный режим. Возвращает dict с результатами шагов."""
    source = read_input(args)
    if not source:
        sys.stderr.write("[Вход] Пустой текст: передайте --text, --file или stdin\n")
        sys.exit(2)

    result = {"mode": args.mode, "source": source}

    if args.mode == "restore":
        steps = [("restore", PROMPTS["restore"], source)]
    elif args.mode == "compress":
        steps = [("compress", PROMPTS["compress"], source)]
    else:  # roundtrip и ask начинаются одинаково: RU -> EN machine
        steps = [("compress", PROMPTS["compress"], source)]

    current = source
    for name, prompt, payload in steps:
        if args.dry_run:
            current = "[dry-run] %s: %s" % (name, payload[:80])
        else:
            current = call_llm(prompt, payload, args.model, args.temperature)
        if current is None:
            sys.stderr.write("[Конвейер] Шаг '%s' не выполнен\n" % name)
            sys.exit(1)
        result[name] = current

    if args.mode == "roundtrip":
        payload = current
        current = (
            "[dry-run] restore: %s" % payload[:80]
            if args.dry_run
            else call_llm(PROMPTS["restore"], payload, args.model, args.temperature)
        )
        if current is None:
            sys.stderr.write("[Конвейер] Шаг 'restore' не выполнен\n")
            sys.exit(1)
        result["restore"] = current

    if args.mode == "ask":
        payload = current
        answer = (
            "[dry-run] answer: %s" % payload[:80]
            if args.dry_run
            else call_llm(PROMPTS["answer"], payload, args.model, args.temperature)
        )
        if answer is None:
            sys.stderr.write("[Конвейер] Шаг 'answer' не выполнен\n")
            sys.exit(1)
        result["answer_en"] = answer
        restored = (
            "[dry-run] restore: %s" % answer[:80]
            if args.dry_run
            else call_llm(PROMPTS["restore"], answer, args.model, args.temperature)
        )
        if restored is None:
            sys.stderr.write("[Конвейер] Шаг 'restore' не выполнен\n")
            sys.exit(1)
        result["restore"] = restored

    return result


def output(result, as_json):
    """Печатает результат: JSON или блоками с метками."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    order = ["compress", "answer_en", "restore"]
    labels = {"compress": "COMPRESS", "answer_en": "ANSWER-EN", "restore": "RESTORE"}
    for key in order:
        if key in result:
            print("[%s]\n%s\n" % (labels[key], result[key]))


def main():
    parser = argparse.ArgumentParser(description="Конвейер RU <-> EN machine через RouterAI (Step-3.5-Flash)")
    parser.add_argument("--mode", choices=["compress", "restore", "roundtrip", "ask"], default="roundtrip")
    parser.add_argument("--text", help="текст для обработки")
    parser.add_argument("--file", help="файл с текстом (UTF-8)")
    parser.add_argument("--model", default=MODEL, help="идентификатор модели RouterAI")
    parser.add_argument("--temperature", type=float, default=TEMPERATURE, help="температура модели (0..2)")
    parser.add_argument("--env", help="явный путь к .env с API_KEY")
    parser.add_argument("--json", action="store_true", help="вывести результат JSON-ом")
    parser.add_argument("--dry-run", action="store_true", help="собрать конвейер без запросов к API")
    args = parser.parse_args()

    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if not args.dry_run and not get_api_key(args.env):
        sys.stderr.write("[Конфиг] API_KEY не найден: нужен .env рядом/выше или переменная окружения\n")
        sys.exit(2)

    output(run_pipeline(args), args.json)


if __name__ == "__main__":
    main()

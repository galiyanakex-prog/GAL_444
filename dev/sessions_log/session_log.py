#!/usr/bin/env python3
"""Минимальный логгер действий агента.

Пишет только дату, время, действие и краткий объект.
Предназначен для вызова из ядра, а не из LLM.
"""

import argparse
import datetime as dt
import os
import re
import sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
ACTIONS = {
    "session_start", "session_end", "read", "write", "edit", "bash",
    "task", "wait", "ask", "web_search", "agent_message", "other",
}


def now() -> dt.datetime:
    return dt.datetime.now()


def fmt_time(value: dt.datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def day_dir(value: dt.datetime) -> str:
    return value.strftime("%d.%m.%Y")


def file_name(value: dt.datetime) -> str:
    return f"sessions_log_{value.strftime('%d.%m.%Y-%H-%M')}.md"


def clean_target(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\n", " ").replace("\r", " ").strip()
    value = re.sub(r"\s+", " ", value)
    if os.path.isabs(value):
        value = os.path.basename(value)
    value = value.replace("/home/", "").replace("\\", "/")
    return value[:120]


def append_line(path: str, action: str, target: str = "") -> None:
    if action not in ACTIONS:
        raise SystemExit(f"неизвестное действие: {action}")
    label = f"{action}: {target}" if target else action
    line = f"- {fmt_time(now())} — {label}\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def cmd_start(_: argparse.Namespace) -> None:
    value = now()
    directory = os.path.join(BASE, day_dir(value))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, file_name(value))
    suffix = 1
    while os.path.exists(path):
        suffix += 1
        path = os.path.join(directory, file_name(value) + f"-{suffix}")
    with open(path, "x", encoding="utf-8") as fh:
        fh.write(f"# Сессия {fmt_time(value)}\n\n")
        fh.write(f"- {fmt_time(value)} — session_start\n")
    print(path)


def cmd_event(args: argparse.Namespace) -> None:
    append_line(args.file, args.action, clean_target(args.target))


def cmd_end(args: argparse.Namespace) -> None:
    append_line(args.file, "session_end")


def cmd_stats(_: argparse.Namespace) -> None:
    sessions = 0
    actions: Counter[str] = Counter()
    days: list[str] = []
    for root, _, files in os.walk(BASE):
        for name in files:
            if not name.startswith("sessions_log_") or not name.endswith(".md"):
                continue
            sessions += 1
            days.append(os.path.basename(root))
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                for line in fh:
                    match = re.match(r"^- .+? — ([a-z_]+)(?::.*)?$", line.strip())
                    if match:
                        actions[match.group(1)] += 1
    print(f"сессий: {sessions}")
    print(f"действий: {sum(actions.values())}")
    for name, count in actions.most_common():
        print(f"  {name}: {count}")
    if days:
        print(f"дни: {min(days)} .. {max(days)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Лог действий агента")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="создать файл сессии").set_defaults(func=cmd_start)

    event = sub.add_parser("event", help="добавить действие")
    event.add_argument("--file", required=True)
    event.add_argument("--action", required=True, choices=sorted(ACTIONS))
    event.add_argument("--target", default="")
    event.set_defaults(func=cmd_event)

    end = sub.add_parser("end", help="завершить сессию")
    end.add_argument("--file", required=True)
    end.set_defaults(func=cmd_end)

    sub.add_parser("stats", help="сводка").set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())

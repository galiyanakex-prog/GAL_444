# -*- coding: utf-8 -*-
"""Фасад хранилища: каноническая иерархия users/<id>/tasks/<task>/sessions/<id>.

Канон куратора (Суть_N3 §4.8 п.3):
  users/<user_id>/
  ├── profile.json                 # зеркало профиля (JSON, источник — SQLite)
  ├── long_term_memory.json        # ссылка на профиль + задачи + решения
  └── tasks/<task_name>/
      ├── working_memory.json      # описание задачи, ссылки на сессии, резюме жизненного цикла
      ├── sessions_resume.md       # резюме сессий (только данные о задаче)
      └── sessions/<session_id>/
          └── session.json         # краткосрочная память: сообщения сессии

Store — единственный, кто знает пути. Остальные слои (MemoryLayer) получают
контекст {user_id, task, session_id} и работают через этот фасад, не трогая
файловую систему напрямую (инкапсуляция через фасады, из arch_prim R3).
"""
import json
import os
import re
from datetime import datetime


def safe_name(name: str) -> str:
    """Безопасное имя каталога/файла: буквы, цифры, дефис, подчёркивание.

    Пробелы и прочие символы заменяются на подчёркивание, чтобы имя задачи
    «Подбор косметики» превратилось в допустимый каталог «Подбор_косметики».
    """
    name = (name or "").strip()
    name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё\-_ ]+", " ", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name[:80] or "task"


class Store:
    """Фасад файлового хранилища поверх канонической иерархии пользователя."""

    def __init__(self, root: str, profile_repo=None, log=None):
        # Корень всех пользователей: <BASE_DIR>/users.
        self.root = root
        # Репозиторий профилей в SQLite (может быть None — тогда профиль только в JSON).
        self.profile_repo = profile_repo
        self.log = log or (lambda line: None)
        os.makedirs(self.root, exist_ok=True)

    def user_dir(self, user_id: str) -> str:
        return os.path.join(self.root, safe_name(user_id))

    def task_dir(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.user_dir(user_id), "tasks", safe_name(task_name))

    def session_dir(self, user_id: str, task_name: str, session_id: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "sessions", safe_name(session_id))

    def ensure_user(self, user_id: str) -> str:
        """Создаёт каталоги пользователя под все канонические файлы. Идемпотентно."""
        path = self.user_dir(user_id)
        os.makedirs(path, exist_ok=True)
        return path

    def ensure_task(self, user_id: str, task_name: str) -> str:
        path = self.task_dir(user_id, task_name)
        os.makedirs(os.path.join(path, "sessions"), exist_ok=True)
        return path

    def ensure_session(self, user_id: str, task_name: str, session_id: str) -> str:
        path = self.session_dir(user_id, task_name, session_id)
        os.makedirs(path, exist_ok=True)
        return path

    def read_json(self, filepath: str, default):
        """Читает JSON; при отсутствии/повреждении возвращает default (не падает)."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    def write_json(self, filepath: str, data) -> str:
        """Пишет JSON; каталог создаётся автоматически. Возвращает путь файла."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    # --- Профиль -----------------------------------------------------------------
    def profile_path(self, user_id: str) -> str:
        return os.path.join(self.user_dir(user_id), "profile.json")

    def save_profile(self, user_id: str, profile: dict) -> str:
        """Сохраняет профиль: в SQLite (авторитет) + зеркало profile.json."""
        self.ensure_user(user_id)
        path = self.write_json(self.profile_path(user_id), profile)
        if self.profile_repo is not None:
            self.profile_repo.save_profile(user_id, profile)
        return path

    def load_profile(self, user_id: str):
        # Авторитет — SQLite; зеркало JSON — fallback (например, если базу удалили).
        if self.profile_repo is not None:
            profile = self.profile_repo.load_profile(user_id)
            if profile is not None:
                return profile
        return self.read_json(self.profile_path(user_id), None)

    # --- Долговременная память ---------------------------------------------------
    def long_term_path(self, user_id: str) -> str:
        return os.path.join(self.user_dir(user_id), "long_term_memory.json")

    def read_long_term(self, user_id: str) -> dict:
        data = self.read_json(self.long_term_path(user_id), None)
        if data is None:
            data = {"profile_ref": user_id, "tasks": [], "decisions": [], "knowledge": []}
        data.setdefault("profile_ref", user_id)
        data.setdefault("tasks", [])
        data.setdefault("decisions", [])
        data.setdefault("knowledge", [])
        return data

    def write_long_term(self, user_id: str, data: dict) -> str:
        self.ensure_user(user_id)
        return self.write_json(self.long_term_path(user_id), data)

    # --- Рабочая память -----------------------------------------------------------
    def working_path(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "working_memory.json")

    def read_working(self, user_id: str, task_name: str) -> dict:
        data = self.read_json(self.working_path(user_id, task_name), None)
        if data is None:
            data = {
                "description": "",
                "refs": [],
                "lifecycle_summary": "",
                "decisions": [],
                "constraints": [],
                "facts": [],
                "open_questions": [],
                "current_state": "planning",
            }
        for key in ("description", "refs", "lifecycle_summary", "decisions",
                    "constraints", "facts", "open_questions"):
            data.setdefault(key, [] if key not in ("description", "lifecycle_summary") else "")
        data.setdefault("current_state", "planning")
        return data

    def write_working(self, user_id: str, task_name: str, data: dict) -> str:
        self.ensure_task(user_id, task_name)
        return self.write_json(self.working_path(user_id, task_name), data)

    # --- Резюме сессий задачи -----------------------------------------------------
    def sessions_resume_path(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "sessions_resume.md")

    def read_sessions_resume(self, user_id: str, task_name: str) -> str:
        path = self.sessions_resume_path(user_id, task_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def write_sessions_resume(self, user_id: str, task_name: str, text: str) -> str:
        self.ensure_task(user_id, task_name)
        path = self.sessions_resume_path(user_id, task_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    # --- Краткосрочная память (сессия) ---------------------------------------------
    def session_path(self, user_id: str, task_name: str, session_id: str) -> str:
        return os.path.join(self.session_dir(user_id, task_name, session_id), "session.json")

    def read_session(self, user_id: str, task_name: str, session_id: str) -> dict:
        data = self.read_json(self.session_path(user_id, task_name, session_id), None)
        if data is None:
            data = {"messages": []}
        data.setdefault("messages", [])
        return data

    def write_session(self, user_id: str, task_name: str, session_id: str, data: dict) -> str:
        self.ensure_session(user_id, task_name, session_id)
        return self.write_json(self.session_path(user_id, task_name, session_id), data)

    # --- Утилиты -------------------------------------------------------------------
    def list_tasks(self, user_id: str) -> list:
        """Список имён задач пользователя (по каталогам, сортировка по имени)."""
        tasks_dir = os.path.join(self.user_dir(user_id), "tasks")
        if not os.path.isdir(tasks_dir):
            return []
        return sorted(
            entry for entry in os.listdir(tasks_dir)
            if os.path.isdir(os.path.join(tasks_dir, entry))
        )
# -*- coding: utf-8 -*-
"""Профили пользователей: JSON в БД SQLite (канон куратора, Суть_N3 §4.8 п.6).

Профиль — отдельная сущность. Авторитетный источник — таблица profiles в SQLite;
файл users/<id>/profile.json — читаемое зеркало, которое пишет Store для
соответствия канонической иерархии хранения (см. store.py).
"""
import json
import os
import sqlite3
from datetime import datetime


class ProfileRepository:
    """Хранилище профилей (JSON) в SQLite: один профиль на user_id."""

    def __init__(self, db_path: str, log=None):
        # Путь к файлу базы (обычно users/profiles.db).
        self.db_path = db_path
        self.log = log or (lambda line: None)
        # Каталог базы создаём заранее, чтобы sqlite.connect не упал на первом старте.
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self):
        """Открывает соединение; row_factory — для доступа по имени колонки."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Создаёт таблицу profiles, если её ещё нет (идемпотентно)."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save_profile(self, user_id: str, profile: dict) -> str:
        """Сохраняет (вставляет или обновляет) профиль пользователя.

        Возвращает строку «куда легло» для журнала маршрутизации памяти.
        """
        updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = json.dumps(profile, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profiles(user_id, profile_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, payload, updated),
            )
        self.log(f"[Хранилище] profile = JSON в SQLite (таблица profiles, user_id={user_id})")
        return f"SQLite:profiles:{user_id}"

    def load_profile(self, user_id: str):
        """Возвращает профиль как dict или None, если пользователя нет."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["profile_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def exists(self, user_id: str) -> bool:
        """Есть ли профиль в базе (по этому признаку отличаем старых и новых)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row is not None
#!/usr/bin/env python3
"""main-tk.py — Графический интерфейс для запуска Den_*.py программ."""

import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHAT_LOG = Path(__file__).resolve().parent / "chat-log.md"

DEN_PROGRAMS = {
    "Den_1_Kod.py": {
        "path": PROJECT_ROOT / "001_День 1" / "Den_1_Kod.py",
        "options": [],
    },
    "Den_2_Kod.py": {
        "path": PROJECT_ROOT / "002_День 2" / "Den_2_Kod.py",
        "options": [
            {"flag": "--free", "type": "checkbox", "label": "Свободный режим"},
            {"flag": "--json", "type": "checkbox", "label": "JSON-режим"},
            {"flag": "--stop-sequence", "type": "text", "label": "Стоп-последовательность"},
            {"flag": "--temperature", "type": "number", "label": "Температура", "default": 0.7, "min": 0.0, "max": 2.0},
            {"flag": "--max-tokens", "type": "number", "label": "Max tokens", "default": 500},
        ],
    },
    "Den_3_Kod.py": {
        "path": PROJECT_ROOT / "003_День 3" / "Den_3_Kod.py",
        "options": [
            {"flag": "--direct", "type": "checkbox", "label": "Прямой ответ"},
            {"flag": "--step-by-step", "type": "checkbox", "label": "Пошаговое решение"},
            {"flag": "--generate-prompt", "type": "checkbox", "label": "Генерация промпта"},
            {"flag": "--experts", "type": "checkbox", "label": "Группа экспертов"},
            {"flag": "--compare", "type": "checkbox", "label": "Финальное сравнение"},
            {"flag": "--expected-answer", "type": "text", "label": "Эталонный ответ"},
            {"flag": "--temperature", "type": "number", "label": "Температура", "default": 0.7, "min": 0.0, "max": 2.0},
            {"flag": "--max-tokens", "type": "number", "label": "Max tokens", "default": 500},
        ],
    },
    "Den_4_Kod.py": {
        "path": PROJECT_ROOT / "004_День 4" / "Den_4_Kod.py",
        "options": [
            {"flag": "--temp-0.3", "type": "checkbox", "label": "Температура 0.3"},
            {"flag": "--temp-0.7", "type": "checkbox", "label": "Температура 0.7"},
            {"flag": "--temp-1.3", "type": "checkbox", "label": "Температура 1.3"},
            {"flag": "--compare", "type": "checkbox", "label": "Финальное сравнение"},
            {"flag": "--temperature", "type": "number", "label": "Произвольная температура", "default": None, "min": 0.0, "max": 2.0},
            {"flag": "--max-tokens", "type": "number", "label": "Max tokens", "default": 500},
        ],
    },
    "Den_5_Kod.py": {
        "path": PROJECT_ROOT / "005_День 5" / "Den_5_Kod.py",
        "options": [
            {"flag": "--weak", "type": "checkbox", "label": "Слабая модель (Llama 3)"},
            {"flag": "--medium", "type": "checkbox", "label": "Средняя модель (GPT-5 Nano)"},
            {"flag": "--strong", "type": "checkbox", "label": "Сильная модель (DeepSeek)"},
            {"flag": "--compare", "type": "checkbox", "label": "Финальное сравнение"},
            {"flag": "--model", "type": "text", "label": "Произвольная модель"},
            {"flag": "--temperature", "type": "number", "label": "Температура", "default": 0.7, "min": 0.0, "max": 2.0},
            {"flag": "--max-tokens", "type": "number", "label": "Max tokens", "default": 500},
        ],
    },
}

# ---------------------------------------------------------------------------
# Парсинг вывода
# ---------------------------------------------------------------------------
MSG_RE = re.compile(r"^(Вы|Бот):\s*(.*)", re.DOTALL)
SEPARATOR_RE = re.compile(r"^={3,}$")


class ChatApp:
    """Основное приложение чата."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AI Chat — Den Runner")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        self.current_program = None
        self.subprocess = None
        self.process_thread = None
        self.is_running = False
        self._stop_event = threading.Event()
        self._last_log_date = None
        self._bot_buffer = ""  # накопитель ответа бота

        self._build_ui()
        self._clear_chat_log()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        # --- Верхняя панель ---
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(top, text="Программа:").pack(side="left")
        self.var_program = tk.StringVar(value="")
        self.combo_program = tk.OptionMenu(
            top, self.var_program, "", *DEN_PROGRAMS.keys(), command=self._on_program_select
        )
        self.combo_program.config(width=22)
        self.combo_program.pack(side="left", padx=(5, 10))

        self.btn_start = tk.Button(top, text="▶ Запустить", command=self._start_program, state="disabled")
        self.btn_start.pack(side="left", padx=3)
        self.btn_stop = tk.Button(top, text="⏹ Остановить", command=self._stop_program, state="disabled")
        self.btn_stop.pack(side="left", padx=3)

        # --- Панель опций ---
        self.options_frame = tk.LabelFrame(self.root, text="Опции", padx=10, pady=5)
        self.options_frame.pack(fill="x", padx=10, pady=5)
        self._option_widgets = []

        # --- Чат ---
        chat_frame = tk.Frame(self.root)
        chat_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.chat_text = tk.Text(
            chat_frame, wrap="word", state="disabled",
            font=("Consolas", 11), bg="#f8f8f8"
        )
        scrollbar = tk.Scrollbar(chat_frame, command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.chat_text.pack(side="left", fill="both", expand=True)

        # Теги для форматирования
        self.chat_text.tag_configure("user", foreground="#1a73e8", font=("Consolas", 11, "bold"))
        self.chat_text.tag_configure("bot", foreground="#0d7a37", font=("Consolas", 11, "bold"))
        self.chat_text.tag_configure("system", foreground="#888", font=("Consolas", 10, "italic"))
        self.chat_text.tag_configure("separator", foreground="#ccc")
        self.chat_text.tag_configure("timestamp", foreground="#999", font=("Consolas", 9))

        # --- Ввод ---
        input_frame = tk.Frame(self.root)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))

        self.input_var = tk.StringVar()
        self.input_var.trace_add("write", self._on_input_key)

        self.entry = tk.Entry(input_frame, textvariable=self.input_var, font=("Consolas", 12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry.bind("<Return>", lambda e: self._send_message())
        self.entry.bind("<Shift-Return>", lambda e: self._insert_newline())

        self.btn_send = tk.Button(input_frame, text="Отправить", command=self._send_message)
        self.btn_send.pack(side="right")

    # ------------------------------------------------------------------
    # Опции
    # ------------------------------------------------------------------
    def _on_program_select(self, program_name: str):
        """Очистить старые опции и создать новые для выбранной программы."""
        self._clear_options()
        self.current_program = program_name if program_name else None
        self.btn_start.config(state="disabled" if not program_name else "normal")

        if not program_name:
            return

        program = DEN_PROGRAMS[program_name]
        for opt in program["options"]:
            widget = self._create_option_widget(opt)
            if widget:
                self._option_widgets.append(widget)

    def _create_option_widget(self, opt: dict):
        flag = opt["flag"]
        otype = opt["type"]
        label = opt["label"]

        row = len(self._option_widgets)
        tk.Label(self.options_frame, text=label, width=22, anchor="w").grid(
            row=row, column=0, padx=(0, 5), pady=2, sticky="w"
        )

        if otype == "checkbox":
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(self.options_frame, variable=var).grid(row=row, column=1, pady=2)
            return (flag, var, otype)

        elif otype == "text":
            var = tk.StringVar(value="")
            tk.Entry(self.options_frame, textvariable=var, width=30).grid(row=row, column=1, pady=2, sticky="ew")
            return (flag, var, otype)

        elif otype == "number":
            default = opt.get("default")
            var = tk.StringVar(value=str(default) if default is not None else "")
            tk.Entry(self.options_frame, textvariable=var, width=12).grid(row=row, column=1, pady=2, sticky="w")
            return (flag, var, otype)

        return None

    def _clear_options(self):
        for widget in self._option_widgets:
            try:
                widget[1].trace_remove("write", None)
            except Exception:
                pass
        for child in self.options_frame.winfo_children():
            child.destroy()
        self._option_widgets.clear()

    def _build_args(self) -> list[str]:
        """Собрать аргументы командной строки из опций."""
        args = []
        for flag, var, otype in self._option_widgets:
            if otype == "checkbox":
                if var.get():
                    args.append(flag)
            elif otype == "text":
                val = var.get().strip()
                if val:
                    args.extend([flag, val])
            elif otype == "number":
                val = var.get().strip()
                if val:
                    try:
                        float(val)
                        args.extend([flag, val])
                    except ValueError:
                        pass
        return args

    # ------------------------------------------------------------------
    # Запуск / остановка
    # ------------------------------------------------------------------
    def _start_program(self):
        if not self.current_program:
            return

        program = DEN_PROGRAMS[self.current_program]
        path = program["path"]

        if not path.exists():
            self._append_system(f"Файл не найден: {path}")
            return

        args = self._build_args()
        cmd = [sys.executable, "-u", str(path)] + args

        self._append_system(f"Запуск: {' '.join(cmd)}\n")
        self.is_running = True
        self._stop_event.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.combo_program.config(state="disabled")
        self.entry.config(state="normal")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        self.subprocess = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        self.process_thread = threading.Thread(target=self._read_output, daemon=True)
        self.process_thread.start()

    def _stop_program(self):
        self.is_running = False
        self._stop_event.set()

        if self.subprocess:
            try:
                self.subprocess.terminate()
                self.subprocess.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.subprocess.kill()

        self.subprocess = None
        self._append_system("Программа остановлена.\n")
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.combo_program.config(state="normal")
        self.entry.config(state="disabled")

    # ------------------------------------------------------------------
    # Чтение вывода
    # ------------------------------------------------------------------
    def _read_output(self):
        """Фоновый поток чтения stdout subprocess."""
        try:
            while self.is_running and not self._stop_event.is_set():
                line = self.subprocess.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\n\r")
                if line:
                    self.root.after(0, self._display_output, line)
        except Exception as e:
            self.root.after(0, self._append_system, f"[Ошибка чтения: {e}]\n")
        finally:
            # Финализируем последний буфер бота
            if self._bot_buffer.strip():
                self.root.after(0, self._log_message, "Бот", self._bot_buffer)
                self.root.after(0, self._flush_bot_buffer)
            self.root.after(0, self._on_process_exit)

    def _on_process_exit(self):
        self.is_running = False
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.combo_program.config(state="normal")
        self.entry.config(state="disabled")
        self._append_system("Программа завершила работу.\n")

    # ------------------------------------------------------------------
    # Отображение
    # ------------------------------------------------------------------
    def _display_output(self, line: str):
        """Отобразить строку вывода в чате."""
        # Пропускаем разделители
        if SEPARATOR_RE.match(line):
            return

        # Проверяем формат "Вы: ..." или "Бот: ..."
        m = MSG_RE.match(line)
        if m:
            who, text = m.group(1), m.group(2)
            tag = "user" if who == "Вы" else "bot"
            self.chat_text.configure(state="normal")
            self.chat_text.insert("end", f"{who}: ", tag)
            # Разбиваем многострочный текст по переносам
            for tline in text.split("\n"):
                self.chat_text.insert("end", tline + "\n")
            self.chat_text.configure(state="disabled")
            self.chat_text.see("end")

            # При появлении нового сообщения — сбрасываем буфер бота
            if self._bot_buffer.strip():
                self._log_message("Бот", self._bot_buffer)
                self._bot_buffer = ""

            # Логгируем "Вы" сразу
            if who == "Вы":
                self._log_message("Вы", text)
            # "Бот" — накапливаем в буфер
            elif who == "Бот":
                self._bot_buffer = text
            return

        # Если это продолжение ответа бота (не начинается с "Вы:" или "Бот:")
        if self._bot_buffer:
            self._bot_buffer += "\n" + line
            self.chat_text.configure(state="normal")
            self.chat_text.insert("end", line + "\n")
            self.chat_text.configure(state="disabled")
            self.chat_text.see("end")
            return

        # Всё остальное — как есть
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", line + "\n")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _append_system(self, text: str):
        """Добавить системное сообщение."""
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", text, "system")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _flush_bot_buffer(self):
        """Записать накопленный ответ бота в лог и очистить буфер."""
        if self._bot_buffer.strip():
            self._log_message("Бот", self._bot_buffer)
            self._bot_buffer = ""

    # ------------------------------------------------------------------
    # Отправка сообщений
    # ------------------------------------------------------------------
    def _on_input_key(self, *args):
        """Скрыть кнопку отправки, когда поле пустое."""
        self.btn_send.config(state="normal" if self.input_var.get().strip() else "disabled")

    def _insert_newline(self, event=None):
        self.entry.insert("insert", "\n")
        return "break"

    def _send_message(self):
        text = self.input_var.get().strip()
        if not text or not self.is_running or not self.subprocess:
            return

        self.input_var.set("")
        self.btn_send.config(state="disabled")

        # Отображаем в чате
        self.chat_text.configure(state="normal")
        self.chat_text.insert("end", f"Вы: {text}\n", "user")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

        # Записываем в лог
        self._log_message("Вы", text)

        # Отправляем в subprocess
        try:
            self.subprocess.stdin.write(text + "\n")
            self.subprocess.stdin.flush()
        except Exception as e:
            self._append_system(f"[Ошибка отправки: {e}]\n")

    # ------------------------------------------------------------------
    # Логирование
    # ------------------------------------------------------------------
    def _clear_chat_log(self):
        """Очистить лог при запуске."""
        CHAT_LOG.write_text("")

    def _log_message(self, who: str, text: str):
        """Записать сообщение в chat-log.md."""
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        # Добавляем дату, если новая
        if date_str != self._last_log_date:
            with open(CHAT_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[{date_str}]\n\n")
            self._last_log_date = date_str

        with open(CHAT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{self.current_program} | {time_str}\n")
            f.write(f"{who}: {text}\n\n")

    def save_log(self):
        """Сохранить текущую сессию (лог уже пишется построчно, но на всякий случай)."""
        pass  # Лог пишется сразу при каждом сообщении

    # ------------------------------------------------------------------
    # Закрытие
    # ------------------------------------------------------------------
    def _on_closing(self):
        if self.is_running:
            self._stop_program()
        self.save_log()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = ChatApp(root)
    root.protocol("WM_DELETE_WINDOW", app._on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

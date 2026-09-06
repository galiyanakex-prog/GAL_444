#!/bin/bash
# Запуск main-tk.py (GUI-интерфейс) с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python tk_ned_1/main-tk.py

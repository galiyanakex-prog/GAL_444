#!/bin/bash
# Запуск den_6_Kod.py с активацией виртуального окружения (работает из любого каталога)
cd "$(dirname "$0")"
source ../.venv/bin/activate
python den_6_Kod.py "$@"

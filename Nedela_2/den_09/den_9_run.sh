#!/bin/bash
# Запуск den_9_Kod.py с активацией виртуального окружения (работает из любого каталога)
cd "$(dirname "$0")"
source ../../.venv/bin/activate
python den_9_Kod.py "$@"

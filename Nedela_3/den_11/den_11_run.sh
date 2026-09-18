#!/bin/bash
# Запуск den_11_Kod.py с активацией виртуального окружения (канон донора).
# Работает из любого каталога: cd к каталогу скрипта, затем venv недели AI_9.
cd "$(dirname "$0")"
source ../../.venv/bin/activate
python den_11_Kod.py "$@"
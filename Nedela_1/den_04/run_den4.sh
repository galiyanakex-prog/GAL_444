#!/bin/bash
# Запуск Den_4_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_04/Den_4_Kod.py "$@"

#!/bin/bash
# Запуск Den_5_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_05/Den_5_Kod.py "$@"

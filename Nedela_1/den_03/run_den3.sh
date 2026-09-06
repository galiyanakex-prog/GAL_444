#!/bin/bash
# Запуск Den_3_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_03/Den_3_Kod.py "$@"

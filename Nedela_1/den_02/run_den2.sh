#!/bin/bash
# Запуск Den_2_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_02/Den_2_Kod.py "$@"

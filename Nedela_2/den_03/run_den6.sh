#!/bin/bash
# Запуск Den_6_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_06/Den_6_Kod.py "$@"

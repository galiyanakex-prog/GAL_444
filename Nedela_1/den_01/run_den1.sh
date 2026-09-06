#!/bin/bash
# Запуск Den_1_Kod.py с активацией виртуального окружения
cd "$(dirname "$0")/.."
source .venv/bin/activate
python den_01/Den_1_Kod.py

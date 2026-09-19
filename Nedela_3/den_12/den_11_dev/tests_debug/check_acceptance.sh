#!/bin/bash
# check_acceptance.sh — гейт приёмки дня 11 (§7.1 START-PROMT_d11.md).
# Идемпотентен: использует временный каталог /tmp/den11_acc_$$ и НЕ трогает users/ дня.
# Запуск: cd "$KOD" && API_KEY=test-key bash "$TST/check_acceptance.sh"

set -u
# Скрипт лежит в den_11/den_11_dev/tests_debug/ → KOD = два уровня вверх (den_11).
KOD="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$(cd "$KOD/../.." && pwd)/.venv/bin/python"   # AI9_ROOT/.venv/bin/python
TST="$KOD/den_11_dev/tests_debug"
TMP="/tmp/den11_acc_$"
mkdir -p "$TMP"
PASS=0; FAIL=0; TOTAL=0

check() {  # check <описание> <команда...>
  TOTAL=$((TOTAL+1))
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  [$TOTAL] ✅ $desc"
    PASS=$((PASS+1))
  else
    echo "  [$TOTAL] ❌ $desc"
    FAIL=$((FAIL+1))
  fi
}

echo "=== Приёмка дня 11 ==="

# 1. Комплектность и сборка (L1)
check "py_compile всей сборки" "$PY" -m py_compile "$KOD/den_11_Kod.py" "$KOD"/core/*.py "$KOD"/memory/*.py "$KOD"/storage/*.py
check "README непустой" test -s "$KOD/README_d11.md"
check "run.sh исполняемый" test -x "$KOD/den_11_run.sh"
check "run.desktop непустой" test -s "$KOD/den_11_run.desktop"

# 2..13, 17: юнит-тесты (L2)
check "юнит-тесты памяти/хранилища/промта/LLM/стейта/агента" env -u API_KEY "$PY" "$TST/unit_runner.py"

# 14: демонстрации (manual) — закрываются прогоном scenario (L4)
check "сценарии задания (L4)" env API_KEY=test-key "$PY" "$TST/scenario.py"

# 15: текстовое описание модели памяти
check "README содержит раздел модели памяти" grep -q "Модель памяти" "$KOD/README_d11.md"

# 16: токен-учёт и CSV (наличие флага и журнала)
check "CSV-журнал токенов создаётся (local smoke)" bash -c "cd '$KOD' && printf 'a\nX\nu\nu\nu\nHi\n/exit\n' | API_KEY=test-key '$PY' den_11_Kod.py --mock --memory-dir '$TMP/users' >/dev/null 2>&1 && test -f '$KOD/den_11_tokens.csv'"

# 19: Проверка_Д11.md только в den_11_dev
check "в корне дня нет Проверка_Д11.md" bash -c "test ! -e '$KOD/Проверка_Д11.md'"

# ИтОГ
echo ""
echo "ИТОГ: $PASS из $TOTAL зелёные (FAIL=$FAIL)"
rm -rf "$TMP"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1

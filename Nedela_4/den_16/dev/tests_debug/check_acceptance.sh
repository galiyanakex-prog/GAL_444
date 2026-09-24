#!/bin/bash
# check_acceptance.sh — гейт приёмки (§7.1 START-PROMT.md).
# Идемпотентен: использует временный каталог dev/tests_debug/.tmp/acc_$$ и НЕ трогает users/ дня.
# Запуск: cd "$KOD" && API_KEY=test-key bash "$TST/check_acceptance.sh"

set -u
# Скрипт лежит в <день>/dev/tests_debug/ → KOD = два уровня вверх (корень дня).
KOD="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$(cd "$KOD/../.." && pwd)/.venv/bin/python"   # AI9_ROOT/.venv/bin/python
TST="$KOD/dev/tests_debug"
TMP="$TST/.tmp/acc_$$"
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

echo "=== Приёмка ==="

# 1. Комплектность и сборка (L1)
check "py_compile всей сборки" "$PY" -m py_compile "$KOD/Kod.py" "$KOD"/core/*.py "$KOD"/memory/*.py "$KOD"/storage/*.py
check "README непустой" test -s "$KOD/README.md"
check "run.sh исполняемый" test -x "$KOD/run.sh"
check "run.desktop непустой" test -s "$KOD/run.desktop"

# 2..13, 17: юнит-тесты (L2)
check "юнит-тесты памяти/хранилища/промта/LLM/стейта/агента" env -u API_KEY "$PY" "$TST/unit_runner.py"

# 14: демонстрации (manual) — закрываются прогоном scenario (L4)
check "сценарии задания (L4)" env API_KEY=test-key "$PY" "$TST/scenario.py"

# 15: текстовое описание модели памяти
check "README содержит раздел модели памяти" grep -q "Модель памяти" "$KOD/README.md"

# 16: токен-учёт и CSV (наличие флага и журнала)
check "CSV-журнал токенов создаётся (local smoke)" bash -c "cd '$KOD' && printf 'a\nX\nu\nu\nu\nHi\n/exit\n' | API_KEY=test-key '$PY' Kod.py --mock --memory-dir '$TMP/users' --log '$TMP/log.md' --token-log '$TMP/tokens.csv' >/dev/null 2>&1 && test -f '$TMP/tokens.csv'"

# 19: Проверка.md только в dev/
check "в корне дня нет Проверка.md" bash -c "test ! -e '$KOD/Проверка.md'"

# 20 (День 15): task_state.json создаётся и переживает перезапуск (пауза → resume).
# Прогон 1: /plan → /approve → /step → /pause → /exit (снимок на диске, stage=paused).
# Прогон 2 (новый процесс, тот же memory-dir): /resume → /run → done.
check "task_state.json переживает перезапуск (пауза→resume→done)" bash -c "
  set -e
  D='$TMP/fsm'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/step\n/pause\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"paused\"' \"\$SNAP\"
  printf '/resume
/run
/exit
' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
"

# 21 (День 14): инварианты хранятся отдельно от диалога и переживают перезапуск.
# Прогон 1: добавить инвариант → invariants.json на диске (отдельный от session.json).
# Прогон 2 (новый процесс, тот же memory-dir): /invariants видит правило.
check "инварианты хранятся отдельно и переживают перезапуск" bash -c "
  set -e
  D='$TMP/inv'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/invariant add framework.django architecture Django\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  INV=\$(find \"\$MD\" -name invariants.json | head -n1)
  test -n \"\$INV\"
  grep -q 'framework.django' \"\$INV\"
  printf '/invariants\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'framework.django'
"

# 22 (День 14): конфликт запроса и инварианта → отказ (действие не исполняется).
check "конфликт запроса и инварианта → отказ" bash -c "
  '$PY' - <<'PYEOF'
import os, sys, tempfile
sys.path.insert(0, '$KOD')
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor
from core.invariants import Invariant
tmp = tempfile.mkdtemp(prefix='acc_inv_', dir='$TMP')
root = os.path.join(tmp, 'users')
store = Store(root, profile_repo=ProfileRepository(os.path.join(root, 'p.db')))
a = Agent(MockClient(), MemoryManager(default_layers(store)), PromptBuilder('r'), store,
          user_id='u', executor=StubExecutor())
a.initialize_user('u', 'И', {'style':'a','constraints':'b','context':'c'})
a.add_invariant(Invariant(id='framework.django', category='architecture', description='Django'))
before = a.tool_calls
res = a.propose_and_check('перепиши API на FastAPI')
assert res['allowed'] is False and a.tool_calls == before
assert 'framework.django' in res['message']
print('ok')
PYEOF
"

# 23 (День 15): недопустимый переход блокируется кодом и логируется.
# /plan → /goto implementation → ОТКАЗАНО; stage не изменилась (planning);
# в task_state.json есть transition_log с allowed=false.
check "недопустимый переход блокируется кодом и логируется" bash -c "
  set -e
  D='$TMP/goto'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/goto implementation\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'ОТКАЗАНО'
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"planning\"' \"\$SNAP\"
  grep -q '\"allowed\": false' \"\$SNAP\"
  grep -qi 'нельзя делать реализацию до утверждённого плана' \"\$SNAP\"
"

# 24 (День 15): флоу утверждения плана (/plan → /approve → /run → done).
check "флоу утверждения плана (/approve)" bash -c "
  set -e
  D='$TMP/approve'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/run\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" 2>/dev/null | grep -q 'утверждён'
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
  grep -q '\"to\": \"plan_approved\"' \"\$SNAP\"
"

# 25 (День 15): пауза → перезапуск процесса → resume → done (шаг не повторён).
# Прогон 1: /plan → /approve → /step → /pause → /exit (1 результат, paused).
# Прогон 2 (новый процесс, тот же memory-dir): /resume → /run → done (3 результата).
check "пауза → перезапуск → resume (шаг не повторён)" bash -c "
  set -e
  D='$TMP/pause15'; MD=\"\$D/users\"
  printf 'u\nИ\nкраткий\nPython\nцель\n/plan Тестовая цель\n/approve\n/step\n/pause\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  SNAP=\$(find \"\$MD\" -name task_state.json | head -n1)
  test -n \"\$SNAP\"
  grep -q '\"stage\": \"paused\"' \"\$SNAP\"
  test \"\$(grep -c 'Результат шага' \"\$SNAP\")\" = \"1\"
  printf '/resume\n/run\n/exit\n' \
    | API_KEY=test-key '$PY' '$KOD/Kod.py' --user u --mock --memory-dir \"\$MD\" \
      --log \"\$D/log.md\" --token-log \"\$D/tokens.csv\" >/dev/null 2>&1
  grep -q '\"stage\": \"done\"' \"\$SNAP\"
  test \"\$(grep -c 'Результат шага' \"\$SNAP\")\" = \"3\"
"

# 26–28 (День 16): --mcp-probe на fake-транспорте (без сети и stdio-подпроцессов).
# Обёртка получает корень дня через ACC_BASE (надёжнее подсчёта dirname) и
# подменяет load_servers_config/MCPGatewaySync ДО вызова run_mcp_probe().
# 26: exit 0 + READY + 3 тула; 27: имена mcp.demo.*;
# 28: description + input_schema каждого тула в выводе.
check "--mcp-probe (fake) → READY, 3 тула, exit 0" bash -c "
  set -e
  D='$TMP/probe'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'Соединение установлено (READY)' \"\$D/out.txt\"
  grep -q 'Всего инструментов: 3' \"\$D/out.txt\"
  grep -q 'Соединение закрыто (DISCONNECTED)' \"\$D/out.txt\"
"

check "имена mcp.demo.* в выводе probe" bash -c "
  set -e
  D='$TMP/probe2'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'mcp.demo.get_time' \"\$D/out.txt\"
  grep -q 'mcp.demo.echo' \"\$D/out.txt\"
  grep -q 'mcp.demo.weather_stub' \"\$D/out.txt\"
"

check "имя + description + input_schema тула в probe" bash -c "
  set -e
  D='$TMP/probe3'; mkdir -p \"\$D\"
  cat > \"\$D/wrapper.py\" <<'WEOF'
# -*- coding: utf-8 -*-
import os, sys
BASE = os.environ['ACC_BASE']
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, 'Kod.py')]
import Kod
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import FakeMCPTransport
import integrations.mcp.config as mcp_config
import integrations.mcp.gateway as mcp_gateway_mod
FAKE_TOOLS = [
    {'name': 'get_time', 'description': 'Текущее время',
     'inputSchema': {'type': 'object', 'properties': {}, 'required': []}},
    {'name': 'echo', 'description': 'Повтор текста',
     'inputSchema': {'type': 'object',
                     'properties': {'text': {'type': 'string'}},
                     'required': ['text']}},
    {'name': 'weather_stub', 'description': 'Погода (заглушка)',
     'inputSchema': {'type': 'object',
                     'properties': {'location': {'type': 'string'},
                                    'units': {'type': 'string'}},
                     'required': ['location']}},
]
def fake_servers():
    return [MCPServerConfig(server_id='demo', transport='stdio',
                            command='python', enabled=True, trust_level='low')]
class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {'demo': FakeMCPTransport(FAKE_TOOLS, server_id='demo')})
    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync
sys.exit(Kod.run_mcp_probe())
WEOF
  ACC_BASE='$KOD' '$PY' \"\$D/wrapper.py\" >\"\$D/out.txt\" 2>&1
  grep -q 'description: Текущее время' \"\$D/out.txt\"
  grep -q 'description: Повтор текста' \"\$D/out.txt\"
  grep -q 'description: Погода (заглушка)' \"\$D/out.txt\"
  grep -q '\"required\": \[\"text\"\]' \"\$D/out.txt\"
  grep -q '\"required\": \[\"location\"\]' \"\$D/out.txt\"
"

# ИтОГ
echo ""
echo "ИТОГ: $PASS из $TOTAL зелёные (FAIL=$FAIL)"


rm -rf "$TMP"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1

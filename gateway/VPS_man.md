# VPS_man.md — диагностика и поднятие сайта AI_9

Служебная справка: **почему `http://91.188.212.77:8080/chat` показывает «Сервис
временно недоступен.»** и как поднять весь контур с нуля.

Раздел 1–4 — проверка «что упало», раздел 5 — инструкция по запуску (хост + VPS).

---

## 1. Схема контура (кто за что отвечает)

```
браузер
  │  http://91.188.212.77:8080
  ▼
[VPS] ai9-gateway.service  — Flask, `python -m gateway.app`, слушает 0.0.0.0:8080
  │  http://127.0.0.1:8090          ← loopback САМОГО VPS
  ▼
[VPS] sshd держит reverse-порт 127.0.0.1:8090   ← создан туннелем с хоста
  │  (по SSH-каналу)
  ▼
[ХОСТ] ai9-tunnel.service — ssh -R 127.0.0.1:8090:127.0.0.1:8090 mcp-vps
  │  127.0.0.1:8090
  ▼
[ХОСТ] serve.py — фасад агента, слушает 127.0.0.1:8090 (loopback)
  │  http://127.0.0.1:1234/v1            http://127.0.0.1:11434
  ▼                                        ▼
[ХОСТ] LM Studio (lms server)        [ХОСТ] Ollama (эмбеддинги/RAG)
       модель должна быть LOADED
```

Правило: **публичен только `:8080`**. Фасад `:8090` нигде не смотрит наружу —
он виден на VPS только как loopback, и только потому, что туннель его пробросил.

### Цепочка зависимостей (падает любое звено — сайт «недоступен»)

| # | Компонент | Где | Порт | Как проверить |
|---|---|---|---|---|
| 1 | LM Studio server | хост | `1234` | `lms server status` |
| 2 | модель загружена | хост | — | `lms ls` → `✓ LOADED` |
| 3 | фасад `serve.py` | хост | `8090` | `curl http://127.0.0.1:8090/models` |
| 4 | туннель `ai9-tunnel` | хост | — | `systemctl --user is-active ai9-tunnel` |
| 5 | reverse-порт | VPS | `8090` | `ss -ltnp \| grep 8090` |
| 6 | шлюз `ai9-gateway` | VPS | `8080` | `systemctl --user is-active ai9-gateway` |

> Симптом «Сервис временно недоступен.» = **шлюз жив, но фасад ему не отвечает**.
> То есть проблема в звеньях 1–5, а не в 6. Если не отвечает сам `:8080`
> (`connection refused`) — проблема в звене 6.

---

## 2. Быстрая диагностика за 60 секунд

### 2.1 На хосте (домашняя машина) — по порядку

```bash
# (1) LM Studio
lms server status                     # → "The server is running on port 1234."
curl -s -o /dev/null -w "lms 1234 -> %{http_code}\n" http://127.0.0.1:1234/api/show

# (2) модель загружена
lms ls | grep -i loaded               # → должен быть хотя бы один "✓ LOADED"

# (3) фасад — ГЛАВНЫЙ ПОДОЗРЕВАЕМЫЙ
ss -ltnp | grep ':8090' || echo "8090 НЕ слушается → serve.py не запущен"
curl -s -o /dev/null -w "facade 8090 -> %{http_code}\n" http://127.0.0.1:8090/models
pgrep -af serve.py || echo "serve.py НЕ запущен"

# (4) туннель
systemctl --user is-active ai9-tunnel
journalctl --user -u ai9-tunnel -n 30 --no-pager
```

**Ключевой признак в логе туннеля:**

```
ssh[...]: connect_to 127.0.0.1 port 8090: failed.
```

Это значит: туннель **поднят**, VPS **принял** проброс, но при первом же запросе
ssh пытается соединиться с **домашним** `127.0.0.1:8090`, а там никого.
→ **Не запущен `serve.py`.** Ничего чинить в SSH/sshd не нужно.

Второй признак того же: `restart counter is at NNNN` в строке
`Scheduled restart job` — туннель гоняется по кругу.

### 2.2 На VPS

```bash
# (5) reverse-порт: слушает sshd
ss -ltnp | grep ':8090'
#   127.0.0.1:8090  → туннель есть, всё ок
#   пусто           → туннель с хоста не поднят (см. 2.1 п.4)

# (6) шлюз
systemctl --user is-active ai9-gateway
ss -ltnp | grep ':8080'
curl -s -o /dev/null -w "gateway 8080 -> %{http_code}\n" http://127.0.0.1:8080/
# ожидаемо 302 (редирект на /login)

# фасад через туннель (главная проверка сквозняка внутри VPS)
curl -s -o /dev/null -w "facade via tunnel -> %{http_code}\n" http://127.0.0.1:8090/models
#   200 → весь путь до хоста работает
#   000 → туннель есть, но на хосте serve.py мёртв
#   404 → serve.py жив, но /models нет (старый код фасада)

# логи шлюза
journalctl --user -u ai9-gateway -n 40 --no-pager
```

### 2.3 С любой машины (снаружи)

```bash
curl -s -o /dev/null -w "8080 -> %{http_code}\n" http://91.188.212.77:8080/
curl -s -o /dev/null -w "8090 -> %{http_code}\n" http://91.188.212.77:8090/
#   8090 обязан НЕ отвечать (timeout / refused) — так и задумано.
#   Если 8090 отвечает из интернета — это дыра: проверьте -R 127.0.0.1:8090:...
#   и GatewayPorts (должен быть no/по умолчанию).
```

---

## 3. Матрица симптомов

| Что вижу | Где причина | Чекнуть | Починить |
|---|---|---|---|
| Страница чата: «Сервис временно недоступен.» | фасад не отвечает | `2.1 (3)` | запустить `serve.py` (раздел 5.2) |
| То же, но `serve.py` запущен | туннель мёртв | `2.1 (4)` | `systemctl --user restart ai9-tunnel` |
| То же, туннель active, лог `connect_to ... failed` | `serve.py` не на `127.0.0.1:8090` | `ss -ltnp \| grep 8090` | перезапустить фасад без `--host` |
| `connection refused` на `:8080` | шлюз упал | `journalctl -u ai9-gateway` | `systemctl --user restart ai9-gateway` |
| `:8080` отвечает, `:8090` на VPS пуст | туннель не поднят / хост выключен | `2.1 (4)` | поднять туннель + `enable-linger` |
| Ответ `502` от фасада / «Ответ не получен (LLM недоступен)» | LM Studio или модель | `lms server status`, `lms ls` | `lms server start`, `lms load …` |
| Висит >180 с, потом 503 | очередь фасада (1 запрос) или медленная большая модель | `curl http://127.0.0.1:8090/state?user=…` → `busy` | дождаться/разгрузить модель |
| `429` | лимит 6/мин | `gateway.json` | подождать минуту |
| `413` | запрос > 8000 символов | `gateway.json` | сократить |
| «Вопросы интервью устарели» | снапшот VPS ≠ хост | — | `sync_questions.py` + копирование (5.4) |
| Пустой список моделей в UI | фасад не отдаёт `/models` | `curl 127.0.0.1:8090/models` | перезапустить фасад |
| Хост перезагрузился — сайт лежит | юниты user-скоупа не поднялись | `loginctl show-user $USER --property=Linger` | `loginctl enable-linger $USER` |

---

## 4. Частые грабли (уже кусались)

1. **`lms load` без `lms server start`** — модель в списке есть, порт `1234`
   не слушается → фасад жив, но агент не может сгенерировать ответ.
2. **`ControlMaster` в `~/.ssh/config`.** Для `mcp-vps` включён
   `ControlMaster auto`. Если туннель сядет на чужой master, процесс `ssh`
   сразу завершится (status=0), systemd зациклит рестарт, порт не поднимется.
   В `ai9-tunnel.service` **обязательны** `-o ControlMaster=no -o ControlPath=none`.
3. **Фасад подняли с `--host 0.0.0.0`** — он это запрещает и упадёт с
   `ValueError`. Только loopback.
4. **Туннель ставили на VPS.** Он ставится **на хост** и НЕ входит в
   `dev/vps/services.list`.
5. **`systemctl --user` по неинтерактивному SSH** не поднимается без
   `XDG_RUNTIME_DIR` / `DBUS_SESSION_BUS_ADDRESS` — используйте
   `dev/vps/deploy_services.sh` (он их выставляет).
6. **Секрет сессии.** Если `GATEWAY_SECRET` не задан, шлюз создаёт
   `gateway/.secret`. Удаление файла → всех пользователей разлогинит.
7. **Rate-limit in-memory** — рестарт шлюза обнуляет счётчики (это норма).

---

## 5. Как поднять всё (инструкция)

> Порядок: сначала **хост** (LM Studio → фасад → туннель), потом **VPS**
> (шлюз). VPS можно не трогать, если `ai9-gateway` уже `active`.

### 5.1 Хост — LM Studio

```bash
lms server status || lms server start
lms ls                                   # выбрать боевую модель
lms load "qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated" -y
lms ls | grep -i loaded                  # → ✓ LOADED
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:1234/api/show   # → 200
```

Не хватает RAM — `lms unload --all` и загрузить только боевую.

### 5.2 Хост — фасад агента (`serve.py`, порт 8090)

Разовый запуск (для проверки):

```bash
cd ~/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python serve.py            # RAG выключен
# .venv/bin/python serve.py --rag    # с RAG-слоем (нужен Ollama :11434)
```

Ожидаемо: `[Фасад] слушает http://127.0.0.1:8090 (RAG=выкл, mock=False)`.

Проверка:

```bash
curl -s http://127.0.0.1:8090/models | head -c 200; echo
curl -s "http://127.0.0.1:8090/state?user=test"   # → "alive": true
```

**Постоянный запуск через systemd (рекомендуется).** Создать
`~/.config/systemd/user/ai9-facade.service`:

```ini
[Unit]
Description=AI_9 facade (serve.py, loopback :8090)
After=network-online.target

[Service]
WorkingDirectory=/home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
ExecStart=/home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9/.venv/bin/python serve.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9/.env

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now ai9-facade
systemctl --user status ai9-facade --no-pager
```

> ⚠ Фасад требует, чтобы LM Studio/Ollama были запущены **до** него — они
> GUI-приложения, их systemd не поднимает. После перезагрузки хоста:
> включить LM Studio (+ загрузить модель), остальное поднимется само.

### 5.3 Хост — туннель

```bash
# предпосылки (один раз)
cat ~/.ssh/config | grep -A8 'Host mcp-vps'      # есть алиас (dev/vps/ssh_config.snippet)
ssh mcp-vps 'echo ok'                            # → ok (ключ работает)

# установка юнита
cp dev/vps/units/ai9-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ai9-tunnel

# чтобы жил без логин-сессии и после перезагрузки
loginctl enable-linger "$USER"

# проверка
systemctl --user is-active ai9-tunnel            # → active
journalctl --user -u ai9-tunnel -n 20 --no-pager # → БЕЗ "connect_to ... failed"
```

Если в логе снова `connect_to 127.0.0.1 port 8090: failed` — **вернитесь к 5.2**
(фасад не запущен), туннель тут ни при чём.

### 5.4 VPS — шлюз (один раз / после правок кода)

```bash
# (один раз) отдельный venv шлюза: flask + requests
ssh mcp-vps 'python3 -m venv /home/t/doc/.venv && \
  /home/t/doc/.venv/bin/pip install flask requests'

# скопировать код шлюза с хоста (на VPS нет rsync — идёт tar)
cd ~/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
tar czf - --exclude='users.db' --exclude='__pycache__' --exclude='.secret' gateway \
  | ssh mcp-vps 'mkdir -p /home/t/doc/AI_9 && tar xzf - -C /home/t/doc/AI_9'
ssh mcp-vps 'mkdir -p /home/t/doc/AI_9/dev/vps/units'
tar czf - dev/vps/units/ai9-gateway.service dev/vps/services.list \
    dev/vps/deploy_services.sh .gitignore \
  | ssh mcp-vps 'tar xzf - -C /home/t/doc/AI_9'

# секрет сессии (если ещё не задан)
ssh mcp-vps 'grep -q GATEWAY_SECRET /home/t/doc/AI_9/.env || \
  echo "GATEWAY_SECRET=$(openssl rand -hex 32)" >> /home/t/doc/AI_9/.env'

# деплой + запуск юнитов
ssh mcp-vps 'cd /home/t/doc/AI_9 && bash dev/vps/deploy_services.sh'
# ожидаемо: ai9-gateway  active  :8080  (mcp-* тоже active)
```

Обновление вопросов интервью (если менялся канон в `core/agent.py`):

```bash
.venv/bin/python gateway/sync_questions.py
tar czf - gateway/questions.json | ssh mcp-vps 'tar xzf - -C /home/t/doc/AI_9'
ssh mcp-vps 'systemctl --user restart ai9-gateway'
```

### 5.5 Сквозная проверка (с хоста, всё одной пачкой)

```bash
echo "== хост =="
lms server status
pgrep -af serve.py || echo "serve.py НЕ запущен"
ss -ltnp | grep -E ':(8090|1234)'
systemctl --user is-active ai9-tunnel

echo "== vps =="
ssh mcp-vps 'ss -ltnp | grep -E ":(8080|8090)";
  systemctl --user is-active ai9-gateway;
  curl -s -o /dev/null -w "facade via tunnel -> %{http_code}\n" http://127.0.0.1:8090/models;
  curl -s -o /dev/null -w "gateway -> %{http_code}\n" http://127.0.0.1:8080/'

echo "== снаружи =="
curl -s -o /dev/null -w "8080 -> %{http_code}\n" http://91.188.212.77:8080/
```

Ожидаемый «здоровый» вывод: `1234` и `8090` слушаются на хосте, туннель
`active`, на VPS `127.0.0.1:8090` + `0.0.0.0:8080`, `facade via tunnel -> 200`,
`gateway -> 302`, снаружи `8080 -> 302`.

### 5.6 Остановка (по необходимости)

```bash
# хост
systemctl --user stop ai9-tunnel ai9-facade
# vps
ssh mcp-vps 'systemctl --user stop ai9-gateway'
```

---

## 6. Куда смотреть дальше

- `dev/vps/README_gateway.md` — полная выкатка шлюза (этап 10, S2)
- `dev/vps/sshd_gateway.snippet` — справка по `GatewayPorts` (в текущей схеме
  правки **не нужны**, `no` по умолчанию — это правильно)
- `gateway/gateway.json` — адрес фасада, таймауты, лимиты
- `README.md` §LM Studio — алгоритм `lms server start → lms load → lms ps`

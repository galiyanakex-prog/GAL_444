# debug_plan_0.md — рабочий план этапа D0 «Базовая линия и воспроизведение бага»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** дебага проекта `den_14`
> по плану-эталону `dev/meta_promt/debug_plan.md`. Разворачивает этап **D0** из
> `debug_plan.md` §5 в конкретные команды, правки и ожидаемые результаты.
> **Конец этого этапа — автоматический гейт в этап D1** (`debug_plan_1.md`).
> Источники: `debug_plan.md` (эталон, реестр §3), `README.md` §«Известные
> шероховатости», `arch_den_14.md` (целевое состояние).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **D0** — Базовая линия и воспроизведение бага |
| Рабочий план | `dev/meta_promt/debug_plan_0.md` (этот файл) |
| Зависит от | — (стартовый этап) |
| Открывает | `dev/meta_promt/debug_plan_1.md` (D1 — Доставка блоков: `DELIVERABLE`) |
| Закрывает | — (инвентаризация; подтверждение реестра A1–A7/B1–B4) |
| Тип изменений | **Только чтение/прогон** — код проекта не меняется |
| Живой ключ | **Не нужен** (`API_KEY=test-key` / `MockClient`) |
| Точка отката | Исходное состояние (этап ничего не ломает) |

**Цель этапа.** Зафиксировать зелёный baseline **до** правок, **доказать** баг A1
(блок `[system: invariants]` не попадает в промт в запущенном CLI) и подтвердить
реестр проблем `debug_plan.md` §3 по фактическому коду (точные файлы/строки).

---

## 1. Вход и предусловия

- Текущее дерево `Nedela_3/den_14/` (итог миграции M0–M8, все гейты зелёные).
- `dev/meta_promt/debug_plan.md` (эталон: реестр §3, границы §0.2).
- `dev/tests_debug/` (`unit_runner.py`, `smoke.py`, `scenario.py`,
  `check_acceptance.sh`).
- `dev/meta_promt/debug_log.md` (журнал — сюда пишется результат этапа).
- `.venv` недели (активация через `run.sh` или `source ../../.venv/bin/activate`).

**Предусловия:** миграция M0–M8 завершена (см. `dev/migr_log.md`, итог); открытых
ошибок нет. Ничего не коммитить.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 0.1 — Активировать окружение и зафиксировать точку старта
1. Перейти в каталог проекта и активировать `.venv`:
   ```bash
   cd Nedela_3/den_14
   source ../../.venv/bin/activate
   ```
2. Зафиксировать версию Python и состояние каталога (что изменено до старта;
   git-репозитория в каталоге дня нет — R3 из `migr_log.md`, фиксация по `find`).
3. **Ожидаемый результат:** окружение активно; точка старта зафиксирована в журнале.

### Шаг 0.2 — Регрессионный baseline (без живого ключа)
Прогнать существующий контур целиком:
```bash
export API_KEY=test-key
python -m py_compile Kod.py core/*.py memory/*.py storage/*.py   # L1
env -u API_KEY python dev/tests_debug/unit_runner.py             # L2 — 69 OK
env API_KEY=test-key python dev/tests_debug/smoke.py             # L3 — SMOKE OK
env API_KEY=test-key python dev/tests_debug/scenario.py          # L4 — 8 сценариев
env API_KEY=test-key bash dev/tests_debug/check_acceptance.sh    # гейт — 12/12
```
1. Зафиксировать результаты: число тестов, сценариев, гейт `N из 12`, exit-коды.
2. **Ожидаемый результат:** baseline зелёный — L2 69 OK / 0 FAIL, L3 OK, L4 8/8,
   гейт 12/12, все EXIT 0.

### Шаг 0.3 — Воспроизвести баг A1 (доказательство)
Прогон CLI в изолированном `--memory-dir` (в `.tmp/`), `--mock`:
```bash
D=dev/tests_debug/.tmp/dbg_a1; rm -rf "$D"; mkdir -p "$D"
printf 'u\nИ\nкраткий\nPython\nцель\n' \
  | API_KEY=test-key python Kod.py --mock --user u --memory-dir "$D/users" \
    --log "$D/log.md" --token-log "$D/tokens.csv" \
    --deliver profile,invariants,long_term,working,short_term <<'EOF'
/invariant add framework.django architecture Использовать Django
Привет, проверка доставки блоков
/exit
EOF
```
1. В выводе ответа `MockClient` (перечисляет видимые блоки) найти блок
   `[system: invariants]` / текст «Обязательные инварианты:».
2. Повторить **без** `--deliver` (дефолт argparse — без `invariants`): блок
   отсутствует и там.
3. Зафиксировать в `debug_log.md`: **факт бага** — при любом `--deliver` блок
   инвариантов в промт CLI не попадает (пересечение `deliver & set(LAYER_ORDER)`
   вырезает `invariants`; `LAYER_ORDER` его не содержит).
4. **Ожидаемый результат:** баг воспроизведён и зафиксирован (это и есть
   обоснование этапа D1).

### Шаг 0.4 — Подтвердить реестр проблем по коду
Сверить каждый ID из `debug_plan.md` §3 с фактическим кодом (grep + чтение):
```bash
grep -n "LAYER_ORDER" Kod.py core/agent.py memory/manager.py
grep -n "MODEL_CONTEXT_LIMIT\|PRICE_IN\|PRICE_OUT\|11.0\|33.0" core/llm_client.py Kod.py
grep -n "budget" core/agent.py Kod.py core/prompt_builder.py
grep -n "def identify\|ROLES" core/agent.py
grep -n "SHORT_TERM_WINDOW\|\[-10:\]" memory/short_term.py core/agent.py
grep -n "^import\|^from" core/agent.py Kod.py storage/store.py
```
1. Заполнить таблицу «ID → файл:строка → подтверждено» (в `debug_log.md`).
2. Отметить точки, которые **не трогаем** (контракты `debug_plan.md` §0.2):
   `llm_client.py` (сигнатуры), `memory/*` (контракт `MemoryLayer`), `storage/db.py`,
   `state_machine.py`, `profile_router.py`, `core/invariants.py`, фасад `Store`,
   `LAYER_ORDER` в `memory/manager.py`.
3. **Ожидаемый результат:** реестр подтверждён; расхождений реестра с кодом нет
   (если есть — запись в `debug_log.md`, корректировка эталона по процедуре §1.1).

### Шаг 0.5 — Зафиксировать «вне скоупа»
Перенести в `debug_log.md` (раздел уже создан) подтверждение: пустые каталоги
`fixtures/`/`smoke/`, `.tmp/`, заделы (`PolicyEngine`, `next_state()`, `parent_id`,
скиллы), живой смоук — не чиним.

---

## 3. Выход этапа

- Зафиксированный baseline (L1/L2/L3/L4/гейт, exit-коды).
- Факт бага A1 (воспроизведение, вывод, место в коде).
- Таблица подтверждения реестра A1–A7/B1–B4 (файл:строка).
- Список неизменяемых контрактов (точки «не трогать»).
- Запись этапа **D0** в `dev/meta_promt/debug_log.md`.

---

## 4. Автоматический гейт D0→D1

Гейт считается **зелёным**, если одновременно:
- [ ] baseline зелёный (L1 ok / L2 69 OK / L3 OK / L4 8/8 / гейт 12/12, EXIT 0);
- [ ] баг A1 воспроизведён и зафиксирован в `debug_log.md`;
- [ ] реестр §3 подтверждён по коду (таблица «ID → файл:строка» заполнена);
- [ ] неизменяемые контракты перечислены;
- [ ] «вне скоупа» зафиксировано.

**Зелёный** → запись D0 в `debug_log.md` (✅) → **перечитать `debug_plan.md`** →
создать/открыть `debug_plan_1.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап D0
остаётся открыт.

---

## 5. Запись в `debug_log.md` (форма §7.4 `debug_plan.md`)

```text
## Этап D0 — Базовая линия и воспроизведение бага
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Закрыто: — (инвентаризация)
- Было: <baseline неизвестен, баг A1 не доказан>
- Стало: <baseline зелёный; баг A1 воспроизведён (факт); реестр подтверждён>
- Проверка: <L1/L2/L3/L4/гейт + прогон CLI с инвариантом, exit-коды>
- Артефакты: <изменённых файлов продукта нет; записи в debug_log.md>
- Спорное/риски: <если есть>
- Перечитывание debug_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт D0→D1: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/meta_promt/debug_plan.md`, затем приступить к **D1** по
`dev/meta_promt/debug_plan_1.md` (`DELIVERABLE` в `core/prompt_builder.py` + дефолт
`--deliver` в `Kod.py` — закрытие бага A1).

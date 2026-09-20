[Этап E / Фаза A] Хранилище: несколько профилей — ✅
- storage/db.py: схема profiles(user_id, profile_id, profile_json, is_default, updated_at), PRIMARY KEY (user_id, profile_id); миграция старой схемы (PRAGMA table_info → RENAME → перенос строк как profile_id='default', is_default=1, одна транзакция); save_profile/load_profile с profile_id; list_profiles/get_default/set_default; exists() — семантика прежняя.
- storage/store.py: зеркала users/<id>/profiles/<pid>.json; users/<id>/profile.json — зеркало default (обратная совместимость); profiles_dir/profile_path/list_profiles/set_default_profile.
- Проверка: L1 py_compile OK; L2 test_storage 7/7 OK БЕЗ ПРАВОК; ручная проверка (.tmp/check_phaseA.py): roundtrip двух профилей независим, первый → is_default=1, get/set_default работают, зеркала на месте, миграция тестовой БД старой схемы данные не потеряла (legacy → default).

[Этап E / Фаза B] Память и роутер — ✅
- memory/base.py: MemoryContext(user_id, task="", session_id="", profile_id="") — аддитивный параметр; as_dict() включает profile_id; вызовы с 3 аргументами работают.
- memory/profile.py: read/write активного профиля (ctx.profile_id or None → default); merge-инвариант сохранён; as_prompt_block: «Профиль: <name> (<profile_id>)» первой строкой, прежние строки (Имя/Стиль/Ограничения/Контекст), «Пайплайн скиллов:» (нумерованные инструкции), «Домен: <domain>».
- core/profile_router.py (новый): ProfileRouter.route() (+2 за триггер, +1 за домен, победитель >0, ничья/ноль → None) и explain(); лог «[Роутер] …»; детерминированный (без LLM).
- Проверка: L1 OK; L2 test_memory 6/6, test_prompt 4/4 БЕЗ ПРАВОК; ручная проверка (.tmp/check_phaseB.py): два профиля → разные блоки, скиллы и домен в блоке, merge не затирает поля, роутер: триггер → профиль, ноль → None, ничья → None, explain содержит разбор, лог «[Роутер]» присутствует.

[Этап E / Фаза C] Агент и CLI — ✅
- core/agent.py: active_profile/auto_route/router в __init__ (роутер — только если у store есть profile_repo); switch_profile() (лог «[Агент] активный профиль: <id>», False если профиля нет); build_context передаёт profile_id=active_profile or ""; respond() при auto_route вызывает роутер ДО сборки промта.
- Kod.py: /profile list|show|use|new|route|auto (голое /profile — как раньше); флаг --profile <id> (несуществующий → предупреждение и default); /help дополнен; run_profile_interview для /profile new.
- Проверка: L1 OK; L2 test_agent 4/4 БЕЗ ПРАВОК; L3 smoke OK; ручной прогон (.tmp/check_phaseC.py) в --mock: list/show/use/route/auto работают, auto_route переключил профиль «economist» до сборки промта (лог «[Агент] активный профиль: economist», «[Роутер]»), --profile chemist активируется на старте, --profile nope → предупреждение и default, два профиля на один запрос → разные ответы MockClient.

[Этап E / Фаза D] Тесты, документация, приёмка — ✅
- dev/tests_debug/unit/test_person.py (новый, 9 тестов): мультипрофильный roundtrip, миграция старой схемы, обратная совместимость (load без id, MemoryContext 3 аргумента), роутер (триггеры/регистр/ноль/ничья/explain), блок профиля (имя + пайплайн скиллов + домен, два профиля → разные блоки), switch_profile, auto_route до сборки промта, два профиля → разные ответы.
- dev/tests_debug/scenario.py: + scenario_personalization (6-й сценарий) — профили «Химик»/«Экономист», один запрос → разный состав промта (MockClient отражает блоки), auto_route, лог «[Роутер]» и «[Агент] активный профиль».
- README.md: + раздел «Персонализация» (модель профиля, роутер, блок промта), команды /profile-семейства, флаг --profile (11 флагов), дерево core/profile_router.py, иерархия profiles/, демонстрация п.14, показатели тестов 40/6, задел «исполнение пайплайна скиллов».
- dev/Проверка.md: + строки 20–22 (несколько профилей; миграция и обратная совместимость; роутер и авто-выбор), итог 22 из 22.
- ГЕЙТ (без живого ключа): L1 py_compile всей сборки OK; L2 unit_runner 40 OK / 0 FAIL; L3 smoke SMOKE OK; L4 scenario 6/6 SCENARIO OK; check_acceptance.sh 9 из 9 (FAIL=0), exit 0. Вывод и временные файлы — только dev/tests_debug/.tmp/; users/ пуст, корень не загрязнён (Den_log.md — записи этапа E, tokens.csv — только заголовок). Прежние 19 пунктов dev/Проверка.md без регрессии.

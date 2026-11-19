# OpenPower — попередній аудит готовності до First Playable

**Дата аудиту:** 14 листопада 2026  
**Контрольна версія:** `main`, commit `9b7a85fa732bc0523c1d576ac59d6977c73b4fdd`  
**Коміт:** merge PR #7 “Reduce client snapshot publication latency”, 14.11.2026 06:41 UTC  
**Режим:** read-only; репозиторій, гілки, PR та issues не змінювалися.

## Межі та надійність висновків

Аудит спирається на опублікований GitHub `main` на вказаному SHA. У робочому середовищі не було checkout репозиторію, тому для пошуку й AST-аналізу використано окрему read-only копію: її `HEAD` відповідав цьому SHA, а робоче дерево було чистим. Незапушені зміни паралельного агента тут не видимі. Тому відкриті задачі нижче є приймальними воротами аудиту, а не дорученням дублювати його роботу.

GitHub не показував відкритих PR або issues на момент перевірки. [PR #6 — Enforce strict architecture contracts](https://github.com/Tymofii-Lytvynenko/OpenPower/pull/6) та [PR #7 — Reduce client snapshot publication latency](https://github.com/Tymofii-Lytvynenko/OpenPower/pull/7) уже злиті; повторювати цю роботу не потрібно. PR #5 про заміну mock економічних панелей закритий без злиття, тому фактичний код контрольного main є джерелом істини.

Виконуваного Repowise в середовищі немає. Керований Repowise-розділ у [AGENTS.md](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/AGENTS.md) посилається на індекс від 1 листопада 2026, commit `ab4735e`, отже він застарів для цього аудиту. Замість нього використано Git tree/API, локальний пошук, огляд фактичного коду й AST-граф імпортів. AST успішно розібрав 528 production Python-файлів і знайшов 1 983 внутрішні ребра імпорту. Граф імпортів не є повним графом виконання: динамічні loaders і composition points перевірялися окремо.

**Коди статусу:**

- **VERIFIED** — конкретну поведінку підтверджено тестом або запуском на контрольному SHA.
- **PARTIAL** — реалізація чи тести є, але не закривають повний ланцюг або актуальний запуск.
- **BROKEN** — дефект відтворено на контрольному SHA.
- **NOT_IMPLEMENTED** — потрібного шляху/компонента немає в опублікованому контрольному SHA.
- **IN_PROGRESS** — специфікація/план залишає роботу відкритою; це не доказ стану незапушеної гілки агента.
- **UNKNOWN** — доказів недостатньо.

## 1. Загальна оцінка готовності

**Вердикт: опублікований `main` ще не проходить визначення First Playable зі специфікації Freeplay.** Існує історично перевірений сценарій Open Sandbox, у якому запускали світ, змінювали податок, керували часом, переміщували підрозділи та зберігали/завантажували гру. Але гравець усе ще проходить сценарійний запуск, а прямого запуску без кампанії та автоматизованого freeplay acceptance flow немає.

Це не означає, що гру неможливо запустити. Вужчий висновок: **сценарний slice має попередній практичний доказ; вимогу відкритого freeplay без campaign-запису не доведено і на цьому SHA не реалізовано.**

| Ворота | Статус | Доказ |
|---|---|---|
| Сценарний старт і базовий ігровий екран | PARTIAL | [Плейтест](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/PLAYTEST_PLAN.md#L34-L55) описує реальний Windows-запуск Open Sandbox за UKR 14.10.2026; це не запуск без кампанії й не доказ контрольного SHA. |
| Прямий старт за вибраною державою без сценарію | NOT_IMPLEMENTED на опублікованому main | NewGameView відкриває сценарійний етап і вимагає country + scenario; NewGameTask посилає ActionStartCampaign і чекає campaigns row. |
| Час, економічне рішення, переміщення та save/load у сценарному sandbox | PARTIAL | Плейтест 14.10 зафіксував зміну податку, дату/паузу, рух дев’яти підрозділів і продовження після завантаження. |
| Політичне та дипломатичне рішення з видимим авторитетним наслідком | PARTIAL | Системи, команди, панелі та вузькі тести є; у плейтесті цих дій не виконували. |
| Save/resume freeplay без campaign metadata | UNKNOWN / IN_PROGRESS | У специфікації це T010–T011; на контрольному main немає відповідних freeplay acceptance-тестів. |
| Автоматизований наскрізний freeplay journey | NOT_IMPLEMENTED у контрольному main | T006 і T013 не виконані; UI journey/fixture для freeplay core loop немає. |
| CI на контрольному SHA | VERIFIED для вибраних перевірок | Architecture (`validate`) і Property на 9b7a85f завершилися успішно. Це не повний GUI або pytest набір. |
| Повний запуск гри у цьому середовищі | UNKNOWN | Немає pytest і ключових графічних залежностей; поточний реальний запуск тут не відбувся. |

Задокументований ручний плейтест — історичний доказ із [PLAYTEST_PLAN.md](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/PLAYTEST_PLAN.md#L34-L55) та [PLAYTEST_REPORT.md](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/PLAYTEST_REPORT.md#L1-L76). Він не прив’язаний до commit 9b7a85f, тому для поточного SHA не виставлено VERIFIED.

## 2. Карта архітектури й підсистем

Основний шлях у коді:

`main.py` → клієнтські Window/View → UI-панелі й контролери → semantic GameAction → ClientSessionProxy та IPC → GameSession / CommandPipeline → Engine → динамічно завантажені модулі й зареєстровані системи → авторитетний GameState → snapshot → read-only ClientGameStateView → відображення та command feedback.

Save йде через `ActionSaveGame` та SaveWriter; load — через DataLoader/LoadGameTask та запуск сесії за save_name. Composition для клієнта й окремого server-процесу зосереджена у [main.py](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/main.py#L26-L57). Ініціалізація сесії завантажує модулі, дані й карту та реєструє системи у [src/server/session.py](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/session.py#L95-L145).

Поточна архітектура має:

- **34 системи base-модуля**, зареєстровані у [modules/base/registration.py](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/modules/base/registration.py#L39-L76).
- **37 HUD PanelSpec** у [game_panel_registry.py](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/ui/layouts/game_panel_registry.py); GameLayout реєструє їх і підключає діалоги/feedback у [game_layout.py](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/ui/layouts/game_layout.py#L119-L126).
- **86 підтипів GameAction**, спільний стан із Polars-таблицями, time/globals/system_state/determinism/journal і transient events/current_actions; є **49 підтипів DomainGameEvent**.
- Межі архітектури з passive client, shared contracts, engine, server і module policy; PR #6 додав/оновив суворі архітектурні перевірки.

Команда проходить через окремі boundary: клієнтський proxy нумерує й кладе її в IPC, server приймає, GameSession перевіряє маршрут і передає action Engine. Це видно у [ClientSessionProxy](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/client_session.py#L67-L80), [server process](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/server_process.py#L87-L102), [GameSession tick](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/session.py#L182-L238) та [Engine registration/step](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/engine/simulator.py#L49-L70).

**Межа контрактів:** `SystemAccess.handles` перевіряється як route до consumer дії; Engine будує порядок за dependencies/phase. Але `SystemAccess.reads` і `writes` зараз лише декларації: runtime Engine не звіряє їх із фактичним доступом до таблиць. Це архітектурний guardrail, не runtime sandbox.

## 3. Інвентаризація та показники охоплення

Recursive Git tree на контрольному SHA повернув **2 563 entries без truncation: 2 377 файлів і 186 директорій**. Повний список файлів із категорією, механікою, кандидатними тестами та застереженням про status є у супровідному CSV-інвентарі.

| Категорія | Кількість файлів | Що охоплює |
|---|---:|---|
| `src/` | 334 | 328 Python-файлів, client, shared, server, engine, core, simulation tooling, шейдери й ресурси. |
| `modules/` | 649 | 175 Python-файлів, 207 TOML, 8 TSV, 252 PNG та модульні дані/ресурси. |
| `tests/` | 1 014 | 583 Python-файли, 430 JSON UI fixture/journey артефактів, 1 README; є unit/component, architecture і property-тести. |
| `specs/` | 275 | 34 feature-пакети (001–012, 101–122) і кореневі документи scope. |
| `docs/` | 30 | Архітектура, playtest, UX/test reference та generated UI reference. |
| Інші корені | 75 | `.agents`, конфігурація, утиліти, tools, `user_data`, archive й entrypoints. |

У `modules/base` є 164 Python-файли в `systems`, але лише 34 зареєстровані systems; решта — політики, builders, resolvers, допоміжні компоненти й AI. У `tests/ui` є 430 JSON-файлів, але freeplay core-loop journey серед них немає.

CSV використовує евристику назв/шляхів для кандидатних тестів; це не доказ, що тест проходить весь UI→simulation ланцюг. Для неоглянутих файлів status лишається UNKNOWN. Документація та специфікації не зараховуються як доказ реалізації.

## 4. Матриця стану механік та інтеграцій

Status оцінює готовність до First Playable, а не саме існування класу.

| Механіка / зареєстровані системи | UI → Action → система → дані / persistence | Тестові й практичні докази | Статус |
|---|---|---|---|
| **Запуск, bootstrap, кампанія:** BootstrapSystem, CampaignSetupSystem, CampaignSystem | Main menu → NewGameView → NewGameTask → ActionStartCampaign → base systems → world state. Server/session/engine підключені. | `test_window_boot.py`, `test_session_startup.py`, `test_new_game_view_coverage.py`, `test_new_game_task.py`; плейтест запускав Open Sandbox. Нові game tests частково mock-based. | **PARTIAL.** Сценарійний шлях є; freeplay без campaign row відсутній. |
| **Прямий freeplay старт** | На main NewGameView починає з `setup_stage = "scenario"`; старт вимагає country і selected scenario. NewGameTask надсилає ActionStartCampaign і чекає campaigns table. | [NewGameView](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/views/new_game_view.py#L40-L54), [render/start](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/views/new_game_view.py#L175-L217), [start guard](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/views/new_game_view.py#L307-L329), [NewGameTask](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/tasks/new_game_task.py#L95-L138); 122 T002–T004 відкриті. | **NOT_IMPLEMENTED** у публічному main. P0 gate для заявленого First Playable. |
| **Час і керування симуляцією: TimeSystem** | Central bar надсилає ActionSetPaused/ActionSetGameSpeed; command path і snapshot підключені; TimeSystem оновлює дату/state. | `test_time_system.py`, `test_client_game_clock.py); PT-04 зафіксував speed 5 і pause у плейтесті. | **PARTIAL.** Історичний доказ для сценарійного старту; на поточному SHA не повторено. |
| **Економіка, бюджет, ресурси, виробництво:** InternalEconomySystem, BudgetSystem, EconomicHealthSystem, TradeSystem, BilateralTradeSystem, DiplomaticAidSystem | Economy/resource panels надсилають команди; таблиці країн, ledger, ресурсів зберігаються у GameState; systems зареєстровані. | `test_economy_smoke.py`, budget/economic-health integration tests; PT-03 підтвердив 35% income tax у наступному авторитетному snapshot. | **PARTIAL.** Один гравецький lever має історичний live-доказ; усі інші економічні цикли — ні. |
| **Політика, устрій, закони, identity:** PoliticsSystem, PoliticalLifecycleSystem, IdentityPolicySystem | Politics/law/constitutional panels → actions → відповідні таблиці та events. | political initialization/lifecycle/law/election tests; політичного рішення в documented playtest немає. T007 відкритий. | **PARTIAL.** Механіка й панелі є; end-to-end політичний наслідок не доведений. |
| **Демографія та міграція:** PopulationSystem, MigrationSystem | Оновлення population, migration policies/flows за часовими межами; panels присутні. | population, migration system та integration tests; live UI acceptance відсутня. | **PARTIAL.** Simulation-side покриття; розвиток світу у клієнтській сесії не підтверджений. |
| **Дипломатія, treaties, recognition, war/peace:** DiplomacySystem, AdvancedDiplomacySystem, DiplomaticBalanceSystem, RecognitionSystem | Treaty/relations/war/peace panels dispatch actions; handlers змінюють treaty/war/relations/news/messages і відповідні таблиці. | `test_diplomacy_system.py`, advanced diplomacy, treaty/recognition/peace-deal tests; playtest не мав дипломатичної дії. T008 відкритий. | **PARTIAL.** Simulation-side інтеграція є; повний UI-to-result шлях не пройдено. |
| **Війська, накази, readiness, movement:** MilitarySystem | Unit list/controller → move/readiness/production/deployment actions → units, routes, readiness/order tables. | `test_unit_move_orders.py`, order-workflow та military tests; PT-05 перевірив маршрут і координати групи з дев’яти підрозділів. | **PARTIAL.** Групове переміщення історично доведено; інші накази й rejection cases — ні. |
| **Бої та battle strategy:** CombatSystem, BattleStrategySystem | Attack/move actions змінюють battle/unit/casualty/occupation data; battle panels/renderers є. | combat/tactical/replay/strategy/performance tests; [manual blockers](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/specs/manual-acceptance-blockers.md) лишають live battle matrix відкритою. | **PARTIAL.** Кодове й автоматизоване покриття є; бойовий UI та продуктивність не перевірено в актуальному запуску. |
| **Можливості, дослідження, foreign orders:** MilitaryCapabilitySystem, ResearchProgramSystem, ForeignOrderSystem | Capability/design/research/production/order actions мають panels і simulation state. | `test_military_capability_system.py`, `test_research_program_system.py`, `test_foreign_order_system.py`; live UAT відсутній. | **PARTIAL.** Треба перевірити хоча б один завершений гравецький шлях у кожному домені. |
| **Covert та strategic warfare:** CovertOperationsSystem, StrategicWarfareSystem | Cell/mission і strategic strike/defense actions мають panels, services і таблиці. | `test_covert_operations_system.py`, `test_strategic_warfare_system.py`; manual acceptance T014/T019 у blocker-list відкрита. | **PARTIAL.** Немає live-перевірки feedback, доступності та відображення наслідків. |
| **Територія й інфраструктура:** TerritorySystem, InfrastructureSystem | ActionAnnexRegion/ActionOccupyRegion/ActionSetRegionOwner змінюють owner/controller; infrastructure projects мають actions і таблиці. | `test_territory_system_coverage.py`, `test_territory_entry.py`, infrastructure integration tests. | **PARTIAL.** Код конкретніший за стару roadmap-замітку; повний клієнтський цикл не перевірено. |
| **AI, advisor, автономний світ:** AISystem, AdvisorRecommendationSystem, AdvisorSettingsSystem | AISystem працює на EventNewDay і породжує actions, які доходять до owning systems; advisor panels читають рекомендації/state. | `test_ai_integration.py` перевіряє Engine.step і зміни state від AI actions; advisor tests присутні. Довгий live run не задокументовано. | **PARTIAL.** Сильний simulation-side доказ; немає багатоденного клієнтського run на контрольному SHA. |
| **Події, історія, пошта/новини/об’єктиви:** RandomEventsSystem, HistorySystem | Event responses та історичні факти потрапляють у journal/state; feeds і panels є. | random-event, history, event-feed та journal tests; manual blockers для event/history flows лишаються. | **PARTIAL.** Системи є; весь шлях від події до видимого повідомлення потребує перевірки. |
| **Save/load** | Save UI викликає callback, server атомарно пише persistent fields; DataLoader відновлює state і migrations. | save-writer atomicity, load task, migration і campaign persistence tests; PT-06 пройшов у сценарійному sandbox. У 122 T010–T011 відкриті. | **PARTIAL.** Сценарійний roundtrip має історичний доказ; freeplay без campaigns row — UNKNOWN. |
| **Модулі та розширення** | ModManager читає manifests/dependencies, динамічно завантажує registration, агрегує systems/schemas/migrations; client presentation loader має окрему composition boundary. | mod manager/data layering/CLI tests; sample `energy_crisis` є. | **PARTIAL.** Loader і composition points підключені; комбінації модулів у реальному GUI не перевірені. |
| **Налаштування та локалізація** | Display/settings/audio/theme UI і код є. У tracked tree не знайдено localization catalog або gettext runtime; локалізація UI-рядків не підтверджена. | Display/settings/audio tests є; мовного acceptance flow немає. | **NOT_IMPLEMENTED** для формальної localization; цільова мова — UNKNOWN. |
| **Мережевий multiplayer** | README та scope визначають як майбутню або виключену роботу. Окремий локальний server process не є мережею. | Spec 102 описує майбутній режим; він поза freeplay MVP. | **NOT_IMPLEMENTED**, але не blocker одиночного First Playable. |
| **Продуктивність і стабільність** | Engine робить checkpoint/rollback state і system state після exception; snapshots і telemetry підключені; PR #7 переносить підготовку snapshot із render thread. | CI вибраних checks зелений; perf/unit tests є; жовтневі frame samples не вимірюють контрольний SHA. | **PARTIAL.** Немає актуального GUI профілю, довгої сесії та цільових hardware вимірів. |

Наскрізні переходи мають такі докази:

| Перехід | Підтверджено | Бракує |
|---|---|---|
| UI → команда | Панелі надсилають semantic actions; central bar — pause/speed. | Не кожна дія перевірена вручну у грі. |
| Команда → авторитетна simulation | Proxy/IPC/session/Engine з’єднані; дія без handler відхиляється. | E2E-підтвердження кожної репрезентативної дії. |
| Simulation → state | 34 systems реєструються; системні тести перевіряють багато доменів. | Немає повного freeplay acceptance на точному SHA. |
| State → видимий результат | Snapshot і feedback consumers є; UI component tests покривають частини. | Не доведені реальний render, наслідки й rejection reasons для чотирьох доменів. |
| State → save/load | Persistent fields, atomic writer, loader, migrations; старий sandbox roundtrip. | Немає тесту freeplay state без campaign metadata. |
| AI → розвиток світу | Інтеграційний test підтверджує AI-generated actions під час Engine.step. | Немає багатоденного клієнтського acceptance на актуальному SHA. |

## 5. Неповні реалізації та розірвані інтеграції

### Прямий freeplay маршрут розірваний на UI/startup

Зараз Country setup підпорядкований вибору сценарію. NewGameView починає з `setup_stage = "scenario"`; `_start_game` повертається без scenario id. NewGameTask надсилає ActionStartCampaign і вважає гру готовою після запису в campaigns. Це пряма залежність старту гри від campaign lifecycle.

Очікувана поведінка — вибрати країну, створити авторитетний world/session і відкрити карту без scenario/objective row. Кампанії мають лишитися додатковим режимом. Open Sandbox є сценарійним workaround, а не таким шляхом.

### Автоматизована freeplay journey відсутня

У контрольному дереві немає `FreeplayStartTask`, `freeplay_setup_window.py`, `test_freeplay_core_loop.py`, `test_freeplay_save_load.py`, `tests/ui/fixtures/freeplay_core_loop.json` або відповідного journey. У UI є багато інших journey, але немає маршруту запуску без сценарію. У tasks T006/T013 відкриті.

### Domain-action acceptance не зведене в один ланцюг

Окремі тести перевіряють systems і UI-компоненти. Немає автоматизованого проходу, який виконує економічну, політичну, військову й дипломатичну команди, перевіряє авторитетний наслідок і те, що бачить гравець. Це прогалина доказу повного циклу, не доказ, що самі панелі не працюють.

### Command result потребує acceptance-перевірки

У [GameSession._tick](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/session.py#L212-L238) один Engine.step виконує всі commands; якщо tick успішний, кожна отримує EXECUTED. Водночас [BudgetSystem._handle_update_budget](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/modules/base/systems/economy/budget_system.py#L629-L645) може повернутися без зміни, наприклад, якщо немає countries table або допустимих allocation fields. Це доводить, що “tick завершився” і “конкретна команда мала очікуваний наслідок” — різні твердження. Це ризик точності feedback, не доказ, що всі команди дають false success. Потрібен focused test на handled no-op/rejection.

### Save/load має сильну базу, але вужчий доказ, ніж очікує Freeplay

State schema позначає tables, time, globals, system_state, determinism і journal як persistent; events/current_actions — transient. SaveWriter пише persistent fields через staged atomic rename; DataLoader відновлює state і migrations. Ручний сценарійний save/reload проходив. Доказу для сесії без campaigns row і відновлення country, дати, tax та pending movement order немає.

### Документація відстає від коду

`.agents/rules/roadmap.md` усе ще каже, що diplomacy actions не обробляються, а territory механіка номінальна. Поточний код реєструє DiplomacySystem і TerritorySystem; territory handler обробляє annex/occupy/owner actions. Старі формулювання не описують контрольний main. README називає симуляцію “background thread”, тоді як main/server launcher запускають окремий процес. Це документаційний борг, не встановлений runtime-дефект.

### Кандидати на потенційно мертвий код

AST-граф і пошук по production source виявили низькоіндексні candidates. Це не автоматичне приписування дефекту:

- `modules/base/systems/military/occupation_system.py`: має клас і прямі тести, але не імпортується у production path і не входить до registration. Інші системи, зокрема combat і battle strategy, теж оновлюють occupations. Перевірити, чи це старий дубль, або чи треба інша інтеграція.
- `src/client/ui/layouts/base_layout.py`: source-level caller не знайдений; поточна композиція використовує GameLayout.
- `src/client/services/audio_service.py`: тести є, production import не знайдений; перевірити, чи це extension point або непідключений сервіс.
- `src/engine/system_state.py` і `src/server/state.py`: compatibility/re-export або shim-файли; production code імпортує shared contracts напряму.

Нічого з цього не треба видаляти без окремого підтвердження. `ReadinessSystem` може виглядати незареєстрованим, але його створює й викликає MilitarySystem як helper; це не розрив registration.

## 6. Критичні архітектурні й технічні ризики

1. **Freeplay launcher залежить від campaign row.** Це підтверджений blocker основної вимоги на контрольному main.
2. **Немає повного automated journey**, що доводить UI → авторитетний світ → feedback → persistence.
3. **EXECUTED — статус всього tick, не доказ станозміни кожної команди.** Визначити семантику та перевірити no-op/rejection.
4. **Freeplay save/load не має власного acceptance доказу.** Перевірений старий сценарійний шлях.
5. **Рендеринг, запуск графічних залежностей і GUI-поведінка невідомі на актуальному SHA.** Architecture/property CI не замінює Arcade/ImGui запуск.
6. **SystemAccess.reads/writes не enforced у runtime.** Це обмежує гарантію контракту; CI після PR #6 перевіряє архітектурні правила.
7. **Модульні й світові дані потребують content audit.** 207 TOML та 8 TSV показують обсяг, але не правильність усіх записів.
8. **Localization catalog не знайдено.** Якщо перший білд має бути українською, це окремий acceptance gate.
9. **Жовтневі frame samples недостатні як performance gate.** Немає актуальних довгих вимірів frame time, memory, snapshot latency чи великих battle loads.

## 7. P0/P1 проблеми

| Пріоритет і проблема | Прямий доказ | Очікувана поведінка | Конкретне завдання | Критерій перевірки |
|---|---|---|---|---|
| **P0 — немає старту freeplay без сценарію** (для визначення First Playable; сценарійний старт окремо існує) | [NewGameView](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/views/new_game_view.py#L40-L54), [start guard](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/views/new_game_view.py#L307-L329), [NewGameTask](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/client/tasks/new_game_task.py#L95-L138); 122 T002–T004 unchecked. | Країна → одна авторитетна сесія → карта; scenario/objective/campaign rows не обов’язкові. | Додати no-scenario path; визначати readiness за world/player context, не ActionStartCampaign/campaigns row; зберегти cancellation cleanup. **Не дублювати, якщо це вже робить паралельний агент.** | Автоматизований тест із selected country і scenario=None відкриває GameView із правильним player context; відсутні campaigns/objectives не блокують; cancel/failure не лишає процесу. |
| **P1 — не доведено UI → команда → авторитетний наслідок для core domains** | Action/IPC/session/Engine з’єднані; 122 T005–T009 відкриті; freeplay journey немає. | Економічний, політичний, військовий і дипломатичний наказ змінює відповідний authoritative state і показує наслідок або причину відмови. | Використати UI test harness; створити deterministic journey; перевірити state/result і видимий feedback, не вводячи нову simulation/schema. | Реальний server session проходить тести; UI journey створює report/artifacts; accepted actions мають state delta, rejected — зрозумілу причину, AI result не показано як player error. |
| **P1 — no-campaign save/resume не підтверджено** | [GameState persistence fields](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/shared/state.py#L87-L138), [atomic writer](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/io/save_writer.py#L35-L130), [loader](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/io/data_load_manager.py#L43-L103); 122 T010–T011 відкриті. | Save без campaign/objective metadata відновлює country, date, tax, pending move order і продовжує симуляцію. | Додати contract test; persistence змінювати лише за виявленою помилкою. | Roundtrip звіряє ці поля; campaigns table не потрібна; після load проходить наступний simulation step. |
| **P1 — CommandResult може не відповідати ефекту конкретної команди** | [GameSession._tick](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/src/server/session.py#L212-L238) присвоює спільний tick status усім commands; [BudgetSystem handler](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/modules/base/systems/economy/budget_system.py#L629-L645) має silent no-op гілки. | Результат має відповідати конкретному наказу; UI не стверджує про відсутню зміну. | Визначити поведінку handled-no-op і додати focused test/feedback case; змінювати API лише якщо тест доведе, що контракт недостатній. | Тест надсилає handled action без ефекту/з невалідною ціллю й перевіряє, що результат не заявляє про неіснуючу зміну. |

P0/P1 перелік стосується публічного snapshot main. Перша проблема ймовірно перетинається з паралельною реалізацією. Перед постановкою задач потрібно звірити її branch/diff, коли він стане доступний. Відсутність відкритого PR не доводить відсутність local/unpushed роботи.

## 8. Функції, які вже можна предметно тестувати

Наявні сценарії та acceptance-напрями; фактичний результат обмежений поточним CI та задокументованим старим плейтестом.

- Main Menu, сценарійний Singleplayer/Open Sandbox і відкриття GameView.
- Вибір країни/партії та сценарійні setup callbacks.
- Час: pause/speed/date на рівні UI-компонента і TimeSystem.
- Зміна personal income tax із перевіркою наступного server state.
- Групове переміщення військ із маршрутом, readiness переходом і переміщенням між регіонами.
- Save → menu → load → continue у тимчасовому профілі.
- Headless simulation/CLI, deterministic seed, command pipeline, journal/snapshot, state migrations.
- Вузькі системні перевірки AI → handlers, treaty, production, population, migration, politics, combat, history, random events і save atomicity.
- Архітектурні правила та property tests у CI на точному SHA.

[PLAYTEST_PLAN.md](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/PLAYTEST_PLAN.md#L15-L55) фіксує PT-01–08: menu, UKR Open Sandbox, 0.35 tax, speed/pause, рух дев’яти підрозділів, save/load і продовження на кілька днів. Objective state перевірено частково; для одного виходу код процесу не зафіксовано. Політичних/дипломатичних дій та прямого запуску без campaign не було.

У репозиторії актуальні CI runs на контрольному SHA: [Architecture](https://github.com/Tymofii-Lytvynenko/OpenPower/actions/runs/43567555248) і [Property tests](https://github.com/Tymofii-Lytvynenko/OpenPower/actions/runs/43567555200) — success. Це вибрані jobs, не доказ проходження всіх 583 Python-тестів або реального GUI запуску. Ізольована спроба запустити `python -m pytest -q` зупинилась через `No module named pytest`; `python main.py ui-test list` — через відсутній `imgui_bundle`. Це обмеження середовища, не результат тестового падіння продукту.

## 9. План поглибленого аудиту й підготовки

### Крок 0 — зняти snapshot змін паралельного агента

1. Після завершення поточного етапу отримати фактичний branch/diff або commit SHA.
2. Звірити файли зі списком T002–T013 у [specs/122 tasks.md](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/specs/122-freeplay-core-loop-and-system-polish/tasks.md).
3. Позначити, які ворота закриті новим кодом і тестами; не повторювати реалізаційні задачі, що вже є у diff.

### P0 — direct no-scenario launch

1. Перевірити country selection без scenario.
2. Запустити session і дочекатися авторитетного world/player snapshot.
3. Відкрити GameView і перевірити player country без campaigns/objectives.
4. Перевірити startup failure, повторний запуск і cancellation cleanup.

**Готово, якщо:** no-scenario path проходить із вибраною країною, а сценарний шлях лишається доступним.

### P1 — дії й видимий результат

1. Виконати по одній валідній дії: tax, government form/law, military move, treaty.
2. Для кожної перевірити handler, journal result, state change і UI feedback.
3. Додати no-op, invalid target, stale action, unhandled action та AI-owned result.
4. Перевірити pause/speed і хоча б один day transition із AI/events/population.

**Готово, якщо:** успіх має підтверджений наслідок; відмова має причину; player-команди й AI-події не плутаються.

### P1 — freeplay save/resume

1. Зберегти сесію без campaign metadata.
2. Зіставити country, дату, tax, pause/speed і pending movement.
3. Відновити сесію після перезапуску та просунути ще один tick.

**Готово, якщо:** зазначені поля збігаються після load і симуляція продовжується.

### P2 — UI/runtime та доменне охоплення

1. Запустити freeplay UI journey на стандартному viewport.
2. Перевірити map draw/picking/zoom, panels, input focus, resize/HiDPI, save/load dialogs, меню та вихід.
3. Виконати коротку сесію з економічною, політичною, дипломатичною та військовою активністю; зафіксувати system errors.
4. Окремо пройти battle/covert/strategic warfare/foreign orders.

**Готово, якщо:** UI journey створює report/artifacts, а графічні й interaction flows не зупиняють основну сесію.

### P2/P3 — контент, performance, документація

1. Перевірити цілісність world tables, країн/регіонів/flags і ключових схем.
2. Виміряти frame time, snapshot/update latency і пам’ять під довшим запуском та навантаженням.
3. Визначити, чи потрібна українська локалізація до першого публічного білда.
4. Оновити roadmap/README після звірки з кодом.
5. Перевірити orphan candidates із секції 5; змінювати лише за результатом аудиту.

## 10. Що неможливо підтвердити без виконання гри

- Чи стартує UI на цільовому Windows/Linux і чи створюється OpenGL/Arcade context.
- Чи правильно рендериться карта, picking/focus/drag, шейдери, шрифти й panels у реальному viewport.
- Чи працює повний current-SHA цикл client → IPC → server process → Engine → snapshot → feedback.
- Чи помітні політичні й дипломатичні наслідки, і чи коректні rejection messages.
- Чи стабільно розвивається AI/world у довшій сесії; чи є stalls, deadlocks або повільні витоки.
- Чи зберігається та завантажується freeplay без campaign metadata після процесного restart.
- Реальні frame time/p95 latency/пам’ять на цільовій машині; старі зразки не дають performance guarantee.
- Чи працюють різні module combinations у графічній сесії без конфліктів.
- Які саме незапушені зміни має паралельний агент: публічні PR/branches не показують локальний diff.

## Джерела з контрольного snapshot

- [README](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/README.md)
- [CONSTITUTION](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/CONSTITUTION.md)
- [AGENTS.md та Repowise metadata](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/AGENTS.md)
- [Runtime architecture](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/ARCHITECTURE.md)
- [Freeplay specification 122](https://github.com/Tymofii-Lytvynenko/OpenPower/tree/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/specs/122-freeplay-core-loop-and-system-polish)
- [Playtest plan](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/docs/PLAYTEST_PLAN.md)
- [Manual acceptance blockers](https://github.com/Tymofii-Lytvynenko/OpenPower/blob/9b7a85fa732bc0523c1d576ac59d6977c73b4fdd/specs/manual-acceptance-blockers.md)
- [GitHub Actions](https://github.com/Tymofii-Lytvynenko/OpenPower/actions)

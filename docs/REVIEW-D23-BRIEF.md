# Streif — Brief незалежного review D23 (межа Spike-2 → MVP-0)

> **Статус:** підготовлено 2026-06-27, до запуску в наступній сесії.
> **Рішення:** `DECISIONS.md` **D23** — незалежне адверсивне review на межі Spike-2 → MVP-0
> («spike→продукт = остання дешева мить виправити фундамент перед UI-розробкою»).
> **Як запускати:** багатоагентний адверсивний воркфлоу (шаблон як для матчингу D25) — див. §5.

---

## 1. Мета й тип review

**Gate перед MVP-0.** Spike-2 майже завершено (Stage A/B ✅, C 🛠️ battery); поверх — on-demand (D24) і edge/centroid-матчинг (D25→D25.1). Перед тим як будувати MVP-0 (Room, eligibility-фільтр, onboarding, дизайн), треба **незалежно перевірити фундамент**: код, архітектуру, оптимальність тех-стеку.

**Дві гілки review (обидві):**
1. **Код + архітектура** — баги, гонки, lifecycle, edge-cases, борг у вже інтегрованому Spike-2.
2. **Tech-stack-optimality re-check** — чи поточні вибори (Kotlin/Views+MapLibre, on-demand Overpass→CDN, файли→Room, двошаровий overlay) оптимальні на порозі продукту, чи є дешевший/надійніший шлях ДО того, як ми на них наростимо MVP.

**Дух:** свіжі агенти, **без вкладення в попередні рішення**; адверсивно ламати, не підтверджувати. Знахідки — верифікувати (не приймати на віру).

---

## 2. Що ВЖЕ ревʼюїлось (не передивлятись наосліп — шукати НОВЕ й системне)

| Раніше | Що покрито |
|---|---|
| Stage A (2026-06-22) | Claude-адверсивний (30 агентів, 12 багів) + codex gpt-5.4 (3, з них 2 нові) — init стирав live-стан, executor-leak. Усе виправлено. |
| On-demand D24 (2026-06-26) | codex (C1–C4): гонка `BuildingStore`, async-зона не реплеїла шлях, bare-id vs `w<id>`, leak `AreaLoader`. Виправлено. |
| Матчинг D25 (2026-06-26) | 4 проєкти-агенти + 3 адверсивні скептики → відхилили abreast (курс шумний), обрали closest-approach. |

**D23 — це КОМПЛЕКСНИЙ пас по ВСЬОМУ інтегрованому Spike-2** (не по окремих змінах), **плюс ще не рев'юйований рефайн D25.1** (centroid-closest-approach), **плюс tech-stack re-check**. Шукати: системні/міжкомпонентні проблеми, регресії від інтеграції, те, що окремі вузькі рев'ю проґавили.

---

## 3. Мапа коду (`C:\Users\mail\AndroidStudioProjects\Streif`, пакет `no.streif.spike`, ~1.8k рядків Kotlin)

| Файл | Рядків | Відповідальність | Ключові рішення / ризик-зони |
|---|---|---|---|
| `TrackingRepository.kt` | 201 | **Ядро** (singleton): gate→матчинг→reveal→persist→статка; міст service↔Activity | **D25.1** (`matchAt`: edge-eligibility + centroid-closest-approach + `moved`-guard, `runMin`), accuracy fail-closed, скид якоря/`runMin` на межах сесії, replay на zone-load. **Гонки main↔фон; lifecycle стану** |
| `BuildingStore.kt` | 225 | in-memory **bbox-grid**, інкрементальний+thread-safe; `candidatesPoint`→edge+centroid; `nearest` | **D25/D25.1**, **D24**, локальна проєкція за широтою запиту; `@Synchronized`-коректність; vertex-avg центроїд (зсув) |
| `AreaSource.kt` | 132 | `OverpassAreaSource` (3 дзеркала, OSM-парсер XmlPullParser → Polygon) | **D24**; ⚠️ ODbL-тест→CC-BY; мережеві помилки/таймаути/парс-крайнощі |
| `AreaLoader.kt` | 59 | on-demand: кеш→fetch→`addFeatures`→`onAreaLoaded`; retry-backoff | **D24**; executor-потоки, failedUntil-кулдаун, `@Volatile status` |
| `AreaCache.kt` | 32 | дисковий кеш зон (geojson per-tile) | I/O, ключ тайла, часткові записи |
| `WalkTrackingService.kt` | 147 | FGS `type=location`, реєстрація Fused + Activity Recognition | foreground-only, START_NOT_STICKY, перм-перед-startForeground (API34+), lifecycle |
| `ActivityGate.kt` | 53 | vehicle/bike-фільтр (AR + швидкісний гістерезис) | **D5**; гістерезис-стан, деградація без `ACTIVITY_RECOGNITION` |
| `ActivityTransitionReceiver.kt` | 24 | прийом AR-переходів | broadcast-безпека, lifecycle |
| `LocationProvider.kt` | 52 | Fused за інтерфейсом | інтервал, точність, no-GMS-шлях |
| `VisitStore.kt` / `SessionStore.kt` / `Stats.kt` | 45/21/18 | збереження розкриттів (id,тип,час) + сесій + метрики | **D13**; файл-персист (на MVP-0 → Room D11); формат/міграція |
| `DiagnosticRecorder.kt` | 34 | сирий трек+батарея у CSV | **D14, gated `BuildConfig.DEBUG`** — перевірити, що off у release структурно |
| `MarkLog.kt` | 20 | ✓/✗ ground-truth (debug) | gated DEBUG |
| `MainActivity.kt` | 444 | UI (карта+кнопка+статус), walk/perf-режими, дозволи, камера, маркування | D7 (native MapView), wiring, дозвіл-флоу, re-attach без втрати стану |
| `PerfHarness.kt` / `PerfProbe.kt` | 175/78 | перф-інструментація (frame-listener) + bench/combo/replay | D22; поза продакшн-шляхом |

**Тести:** `BuildingStoreTest.kt` (edge/centroid/grid/Oslo — 7 кейсів), `ExampleUnitTest.kt`. **Аналіз польових логів:** `spike/fieldtest/analyze.py`.

---

## 4. Фокус-області (lenses) + відомі спец-прогалини для тиску

**Технічні lenses (адверсивно):**
1. **Конкурентність / стан:** `BuildingStore` мутується у фоні (`AreaLoader`), читається з main (`matchAt`) — чи всі шляхи під локом? `runMin`/`revealed`/`recent`-буфери — гонки? Скид стану на межах сесії — нічого не тече?
2. **Матчинг D25.1 (НОВЕ, не рев'юйоване):** centroid-closest-approach + `moved`-guard — крайнощі: стояння+джитер, розворот, видовжені/L-будинки (vertex-avg центроїд зсунутий), zone-load replay коректність, перф edge+centroid щофікса.
3. **FGS/lifecycle:** старт/стоп, перм-перед-startForeground, OEM-killers (відомий ризик, D29 acceptance), процес-смерть/відновлення.
4. **On-demand/мережа (D24):** Overpass-таймаути/429/504, парс-крайнощі (relation-будинки, дірки), кеш-узгодженість, bbox-обчислення.
5. **Приватність (D14/D24):** сирий GPS не виходить; bbox→Overpass задокументовано (`07`); diagnostic off у release — перевірити **структурно**.
6. **Перф на mid-range:** двошаровий overlay + edge-матчинг — чи тримається поза Pixel 9 (дозамір заблоковано — оцінити теоретично).

**Спец-прогалини (review має зважити — вони стануть MVP-0-роботою):**
- **D24 CC-BY пайплайн/CDN** — хто/де/коли будує продакшн-джерело (🔴 блокує реліз; зараз Overpass-тест).
- **Eligibility-фільтр D6** — джерело пішої мережі (OSM `highway`? turrutebasen?) + алгоритм буфера (не вирішено).
- **Room-схема (D11)** — таблиці/колонки/`stable_id`/індекси/міграції (каркас, не фінал).
- **Стабільність `building_id`** при переході Overpass→CC-BY (різні id-простори) — D30 анти-ретроактив.

**Tech-stack re-check (окрема панель):** Views+MapLibre 13.3.0 vs альтернативи; Overpass→CC-BY-CDN-стратегія; файли→Room тайминг; чи двошаровий overlay досі оптимальний (P7 feature-state watch).

---

## 5. Run-plan (наступна сесія)

Багатоагентний адверсивний воркфлоу (шаблон D25):
1. **Find (паралельно по lenses §4):** N агентів-рецензентів, кожен по своїй області, читають код → структуровані знахідки (файл:рядок, severity, опис, репро).
2. **Verify (адверсивно):** на кожну знахідку — скептики, що намагаються її **спростувати** (false-positive guard); лишати лише підтверджені.
3. **Tech-stack панель:** окремі агенти на re-check (стек/дані/сховище) → за/проти + рекомендація.
4. **Synthesize:** звести в пріоритезований список (🔴blocker / 🟠 / 🟡) + рішення по спец-прогалинах §4.
5. **(Опц.) codex** як друга модель (крос-модельне, D23) — звірити/доповнити.

**Вихід review:** список підтверджених проблем + рішення по 2 блокуючих спец-прогалинах (D24-пайплайн, eligibility-D6) → тоді MVP-0.

**Поза scope D23:** UI-полір, гейміфікація-деталі (фаза MVP-1), P10/P13-прототипи (окремий продуктовий трек), фінальні дизайн-токени.

---

## 6. Контекст для агентів (вхідні файли)
- Рішення: `docs/DECISIONS.md` (D1–D30 + D25.1). Хронологія+as-built: `docs/CHANGELOG.md`. Архітектура: `docs/05-tech-architecture.md`. Дані: `06`. Приватність: `07`. Скоуп MVP-0: `09`.
- Стан spike: `spike/android-render/SPIKE-STATUS.md`. Польовий аналіз: `spike/fieldtest/analyze.py` (+ `diag.csv`/`marks.csv`).
- Код: `C:\Users\mail\AndroidStudioProjects\Streif\app\src\main\java\no\streif\spike\*.kt` (мапа §3).

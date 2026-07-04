# Streif — Changelog

> Хронологічний журнал змін: **що змінилось, коли, і ЧОМУ**. Призначення — легке стороннє
> review (codex) і згадування, як і чому побудована кожна частина.
> Канон **рішень** (повне обґрунтування) — `DECISIONS.md`. Операційний стан spike —
> `spike/android-render/SPIKE-STATUS.md`. Дизайн-архітектура — `05-tech-architecture.md`.

---

## 2026-07-05 — UI-стек залочено (Compose+M3, D32) + швидкий FAB-фікс кнопок

**Рішення про UI-стек верифіковано адверсивним воркфлоу** (3 research: native-landscape / cross-platform / MapLibre-fit + devil's-advocate + вердикт; веб-джерела 2026). Розглянуто ВСІ 6 сучасних опцій (Compose+M3, Material 3 Expressive, Flutter, React Native, KMP+Compose Multiplatform, legacy Views). Адверсивний агент чесно не зміг побудувати реальний кейс проти.
- **D32 — UI = Jetpack Compose + base Material 3.** Причини: нативний Kotlin (нуль-bridge до FGS/Fused/sensors/Room — вони нижче UI, framework-invariant); MapLibre Native Android v13.1.0 first-party (обгортки Flutter/RN відстають; Flutter має проблему фонового GPS ~$500/рік плагін); solo-dev один skillset; View/XML заморожено.
- **Уточнення:** (1) писати Compose **CMP-clean** → двері iOS через KMP+CMP безкоштовно; (2) Material 3 Expressive **à-la-carte** (base 1.4.0 floor); (3) map через `AndroidView` над наявним MapView, НЕ pre-1.0 `maplibre-compose`.
- Повний Compose-план UI-міграції → `10-roadmap.md` §12b (робити ПІСЛЯ польової валідації даних).

**Швидкий FAB-фікс (проміжно на Views, до Compose-міграції).** Замінено застарілі emoji-на-сірому-квадраті кнопки на Material 3:
- Компас + «до мене» → `FloatingActionButton` (SIZE_MINI, елевація, векторні Material-іконки `ic_compass`/`ic_my_location`). Компас course-up тепер підсвічується через M3-тінт (`colorPrimary`/`colorPrimaryContainer`, `applyCompassTint`), не hardcoded-синій.
- «Почати прогулянку» → `MaterialButton` (filled pill, cornerRadius=100, іконка `ic_walk`).
- Тема застосунку — вже `Theme.Material3.DayNight.NoActionBar`, тож FAB працює без змін теми. Збірка ✅; візуальна перевірка на Pixel 9 чекає під'єднання пристрою.
- **Файли:** `MainActivity.kt` (типи полів → FAB/MaterialButton, конструкція кнопок, `themeColor`/`applyCompassTint`), `res/drawable/ic_compass.xml` + `ic_my_location.xml` + `ic_walk.xml` (нові векторні).

---

## 2026-07-04 — D6-eligibility на офіційний Kartverket Elveg (NVDB Vegnett Pluss), Варіант B (D31)

**Замінено OSM-highways на офіційну дорожню мережу Kartverket для шару D6-accessible** — останній продакшн-пункт даних D31. Адверсивно-верифікований воркфлоу (3 research + pedestrian-скептик + synth, першоджерела Kartverket/Geonorge).

**Що з'ясував воркфлоу:**
- «Elveg 2.0» тепер розповсюджується як **NVDB Vegnett Pluss** (UUID `97e6a869-…`, **CC BY 4.0**, формат **GML**, EPSG:5973 — горизонтально == 25833). Завантаження — Geonorge order-API (POST `/api/order` → файл одразу `ReadyForDownload`).
- Elveg **містить пішохідні шляхи** як першокласні (`fortau/gangveg/gsv/gangfelt/trapp`) — страх «тільки для авто» хибний. **АЛЕ** `sti`/`traktorveg` (неформальні стежки) ще накочуються (2026–2027) → recall-ризик по будинках, доступних лише лісовою стежкою.
- typeVeg-літерали у ЖИВОМУ файлі ≠ специфікація (`bilveg`/`gsv`, не `enkelBilveg`/`gangOgSykkelveg`) — фільтр писано проти реальних значень.

**A/B-гейт (обов'язковий перед перезаливкою, `spike/pipeline/elveg_ab.py`):** на Volda Elveg-only дав 82.0% accessible vs OSM 80.5%, але **регресував 309 буд.** (hytte 106 / outbuilding 113 — саме trail-reachable, підтверджує sti-провал). → **обрано Варіант B: Elveg + OSM-footpath-bridge** — нуль регресії, accessible регіону **83→87%**. Обґрунтування: тайл **і так ODbL** (геометрія OSM у Варіанті 1), тож bridge не додає ліцензійної ціни зараз; прибрати коли геометрія→FKB І Elveg домігрує стежки (або +Turrutebasen для природного шару).

**Реалізація:** `parse_elveg` (Veglenke→walkable-лінії, 5973→4326, той самий тип що OSM highways — `compute_accessible` НЕ змінено) + прапорці `--elveg=`/`--osm-bridge` у `build_tiles.py`; manifest-атрибуція += NVDB Vegnett Pluss. Перегенеровано Volda+Ørsta = 416 тайлів (1.3 MB gzip). Клієнтська атрибуція «© Kartverket · © OpenStreetMap» уже покриває (Kartverket = Matrikkelen+Elveg).

**⚠️ Відома розбіжність pipeline-vs-runtime:** offline-CDN-тайли несуть Elveg-eligibility; runtime on-demand (Overpass, `USE_CDN=false`) на девайсі й далі рахує accessible з OSM-highways (Elveg там немає). Вирівняється, коли Elveg-мережа теж поїде pre-hosted.

**TODO:** перезалити тайли на R2 (потрібен новий токен — старий відкликано); custom-domain перед зовнішнім тестером.

**Файли:** `spike/pipeline/build_tiles.py` (parse_elveg + CLI + attribution), `spike/pipeline/elveg_ab.py` (A/B-гейт, new), `spike/pipeline/README.md` (Elveg-крок).

---

## 2026-07-04 — Desk-полір після CC-BY: атрибуція в UI + Room off-main/BundledSQLiteDriver

**Атрибуція даних (юр-вимога ODbL OSM + CC-BY Kartverket).** Постійний видимий рядок
«© Kartverket · © OpenStreetMap» унизу-центр мапи (`R.string.attribution`; `MainActivity`
TextView, поряд із логотипом MapLibre). Verified на пристрої. Без цього — порушення обох ліцензій.

**Room-полір (D11) — закрито останній тех-борг MVP-0-ядра з D23-review.**
- *Проблема:* `matchAt`/reveal іде на **main-looper** (Fused-колбек), а `visitDao.insertAll` на кожному
  розкритті + старт-читання `visitDao.all()`/міграція — блокуючий Room на головному потоці
  (`allowMainThreadQueries` — spike-шорткат). При рості історії розкриттів = jank/ANR.
- *Фікс:* усі Room/файл-виклики винесено на `TrackingRepository.dbIo` (single-thread executor, FIFO —
  серіалізує операції). `startSession`/`checkpointSession`/`endSession`/reveal-`insertAll`/`reset` —
  fire-and-forget off-main (значення snapshot-ляться на main перед чергою; `sessionRowId` @Volatile,
  читається/пишеться лише в dbIo). `init` тепер робить міграцію+читання в dbIo → reconcile+UI назад
  на main (`dbMain.post`). `allowMainThreadQueries` прибрано.
- *BundledSQLiteDriver (D11):* `.setDriver(BundledSQLiteDriver())` + `.setQueryCoroutineContext(Dispatchers.IO)`
  + `androidx.sqlite:sqlite-bundled:2.6.2` (= версія, що її тягне Room 2.8.4). Однаковий SQLite на всіх
  пристроях (не залежить від версії ОС), `libsqliteJni.so` у APK.
- *Верифіковано на Pixel 9:* збірка ✅; запуск без креша (нуль «Cannot access database on the main thread»);
  init-reconcile + area-fetch (970) працюють; START→STOP (session insert+delete через драйвер) без помилок;
  `databases/streif.db.lck` підтверджує, що BundledSQLiteDriver реально активний (WAL: db-wal/db-shm).
- *Файли:* `MvpDatabase.kt` (driver+coroutine-context, прибрано shortcut), `TrackingRepository.kt`
  (dbIo executor + off-main усіх DAO-викликів + async init), `MainActivity.kt` (init-сигнатура),
  `build.gradle.kts`/`libs.versions.toml` (sqlite-bundled).

---

## 2026-07-04 — CC-BY продакшн-дані ЖИВІ: Варіант-1 пайплайн (OSM+Matrikkelen) → Cloudflare R2 (D31 realized)

**Найбільша віха: тестові Overpass-дані замінено офіційним CC-BY-пайплайном, тайли живі на CDN.** Реалізує D31 (обрано Варіант 1: OSM-геометрія ODbL + Matrikkelen-збагачення).

**Крок 0.1 — верифікація join (головний ризик Варіанту 1) ✅.** Спайк point-in-polygon (Matrikkelen `representasjonspunkt` → OSM-полігон): Volda **98.5%** будинків збагачено `bygningsnummer`+тип; лише 14 полігонів з >1 точкою. Ørsta нижче (**84%**) — бо OSM має БІЛЬШЕ об'єктів (11833) ніж Matrikkelen (10435) → стеля join 88%; решта лишає OSM-тип-фолбек. Не баг.
- *Розкладка типів (офіційна Matrikkelen `bygningstype` → 6 категорій Streif):* **outbuilding 50%** (гаражі/naust/fjøs — половина всіх «будинків»!), housing 34%, hytte 11%, public 3%, other 2%, sacral 0.2%. Мапінг кодів: 161-172→hytte, 181-183/231-249/431-449→outbuilding, 671-679→sacral (66x — то культура/diskotek, НЕ церкви), решта 1xx→housing, 3xx-8xx→public, 2xx→other. **⚠️ Продуктове питання (відкрите):** чи розкривати гаражі нарівні з житлом — рішення відкладено до польових цифр (P10/retention).

**Пайплайн `spike/pipeline/` (offline CLI):**
- `fetch_osm.py` — OSM будинки+дороги per-kommune (Overpass area-query по `ref`; ~12k буд./kommune, ~17 MB JSON).
- `build_tiles.py` — Matrikkelen GML (пряме Geonorge-завантаження, EPSG:25833→4326 pyproj) + OSM → point-in-polygon join → D6-`accessible` (той самий highway-buffer-алгоритм що в Kotlin) → тайли `area_{la}_{lo}.geojson` (сітка 0.02°, id=`m<bygningsnummer>` | фолбек `w<osmid>`; props building_id/type/accessible). Мульти-kommune → union на межі.
- `upload_r2.py` — boto3 S3-API заливка на R2 з правильними заголовками.
- *Джерело Matrikkelen:* прямий per-kommune URL `nedlasting.geonorge.no/.../Basisdata_{nr}_{Name}_25833_MatrikkelenBygning_GML.zip` (Ø→O транслітерація в назві). Order-flow API таймаутив — прямий URL працює.

**Результат: Volda+Ørsta = 416 тайлів, 8.2 MB → 2.2 MB gzip.** 91% з офіційним `bygningsnummer`, D6-accessible 83%.

**Хостинг = Cloudflare R2 (D31 (2) resolved), верифіковано адверсивним воркфлоу** (6 research-агентів + synth + 3 скептики cost/prod/correctness, веб-джерела Cloudflare docs):
- **R2, не Pages:** Pages має стелю 20k файлів (впремося на нац.масштабі); R2 — без ліміту об'єктів + object-store-семантика (перезалити частину тайлів).
- **$0:** лімітує читання 10M/міс (юзаємо ~0.09%), egress безкоштовний, сховище 10 GB. Storage class = **Standard** (Infrequent Access НЕ в free-tier + retrieval fee).
- **Знахідка correctness-скептика:** R2 **сам не стискає** (авто-стиснення Cloudflare — лише на custom-domain) → тайли **передстиснено gzip** (57 KB найбільший замість 330). Android розпаковує прозоро.
- **Live:** `https://pub-b1c9ae365792405880b62e24ccda0df1.r2.dev/area_{la}_{lo}.geojson`. Заголовки перевірено end-to-end (200, Content-Encoding: gzip, 970 фіч розпакувалось, неіснуючий тайл→404).

**Android-споживач (`CdnGeoJsonAreaSource.kt` + `BuildConfig`):**
- Реалізує `AreaSource`: ключ тайла = `AreaCache.keyFor` (0.02°) → GET `$CDN_BASE_URL/area_{la}_{lo}.geojson` → parse. Фічі вже несуть building_id/type/accessible (нуль runtime-збагачення).
- Витримує 3 gzip-пастки (перевірено проти скептика): `responseCode` ДО `inputStream` (404→emptyList, не FileNotFoundException); `readText()` до EOF (не `getContentLength()`, яке gzip обнуляє); `Accept-Encoding` не чіпаю (прозора розпаковка).
- Перемикач: `BuildConfig.USE_CDN`=true + `CDN_BASE_URL`=r2.dev-URL. `false` → runtime-Overpass (dogfood-фолбек). `MainActivity` вибирає джерело. Зібрано+увімкнено (APK ✅), встановлення чекає під'єднання Pixel 9.
- *Файли:* `CdnGeoJsonAreaSource.kt` (нове), `build.gradle.kts` (buildConfigField USE_CDN/CDN_BASE_URL), `MainActivity.kt` (вибір джерела), `AreaCache.kt`/`AreaLoader.kt` (тайл 0.02°/fetch-halfKm 1.4 — раніше).

**TODO продакшн (не блокує польовий тест):** eligibility на Elveg (зараз accessible з OSM-highway у тайлах); custom-domain `tiles.streif.no` перед зовнішнім тестером → вимкнути r2.dev; міграція на pre-hosted FKB через публічного партнера (D31); токен R2 з чату — відкликати.

---

## 2026-07-04 — Лок рішень перед MVP-0 (D6, D30) + матчинг-фікси #4/#5

**Ухвалено 2 рішення (Денис погодив рекомендації), лок у DECISIONS:**
- **D30 — продакшн `building_id` = Matrikkelen `bygningsnummer`** (не OSM `w<wayId>`). Причина: OSM-id не переживе Overpass→CC-BY (осиротіли б усі розкриття). Overpass-era dogfood-розкриття = одноразові (або опц. spatial-remap історії Дениса); Room несе колонку `source`. Геометричний хеш відхилено (OSM≠Matrikkelen-контур → зсув+колізії).
- **D6 — eligibility: джерело = OSM `highway`** (footway/residential/path…; НЕ turrutebasen — то природний шар), **буфер ~25–30 м**, прапорець `eligible` рахувати на сервері (build-time). «Мій бік vs через дорогу» → fast-follow. Ліцензія OSM(ODbL) для build-time булевого — підтвердити при міграції (P4).

**Матчинг-фікси з D23-review (`TrackingRepository.kt`, assembleDebug ✅):**
- **#4 тангенційний промах** — розчеплено вікно eligibility (стіна ≤`R_FAR`=18) від вікна тайминга: кандидатів для centroid-CA беремо ширше (`R_TRACK`=30), а `passedMiddle` розкриває лише будинки, чия стіна колись була ≤`R_FAR` (`eligible`-сет). Тепер дотичний прохід на 15–18 м не випадає з кандидатів до підтвердження.
- **#5 cold-start буфер** — replay-буфер тепер за ЧАСОМ (`RECENT_WINDOW_MS`=90с, cap 240), не фіксовані 12 фіксів → повільний Overpass-fetch (>24с) більше не губить ранні будинки.
- **+ replay-коректність:** реальний `moved` з послідовних фіксів (не `i>0` — прибирає джитер-розкриття стоячи, codex #2); replay не біжить після Stop (`isTracking`-guard) + чистка буфера в `endSession` (codex #3).
- *Верифікація (replay на польових даних, `analyze.py` секція 14):* recall **101→110/112**, хибних 4→5 (+1 — «через дорогу», лікує D6), тайминг «по середині» збережено (past-середини 3.2→3.3 м). Ristevegen 1 тепер розкривається на **1-му** дотичному проході (edge 19.3 м) замість 2-го (edge 1.1 м, +16 хв).
- *Далі:* чиста повторна прогулянка (без кабелю → заразом Stage C) підтвердить live-поведінку (cold-start recovery) + дасть чисті ✓/✗-мітки для фіналізації `R_TRACK`/`R_FAR` (P2).

**MVP-0 старт — Room-персистенція (D11) замінює flat-файли** (`MvpDatabase`, KSP; verified на пристрої):
- *Схема:* `visits(buildingId PK, type, firstSeenTs, source)` + `sessions(id, startTs, endTs, distanceM, newCount)`. Колонка `source` (D30): dogfood="osm", продакшн="matrikkelen" — простір імен для міграції Overpass→CC-BY.
- *Збірка:* KSP `2.2.10-2.0.2` (під Kotlin 2.2.10, що його тягне AGP) + Room `2.8.4`. **Гальмо AGP 9.2.1:** вбудований Kotlin відхиляє KSP-source-set → потрібен `android.disallowKotlinSourceSets=false` у `gradle.properties` (інакше build fail «Kotlin source set contains build/generated/ksp»).
- *Importer:* одноразова міграція `visited.txt` → Room (`MvpImporter`). **Верифіковано на Pixel 9: 132 dogfood-розкриття мігрували (усі source="osm"), БД створюється, запуск без креша, reconcile відновлює розкриття з Room.**
- *D23 #11 (втрата сесії) виправлено:* сесія `insert` на старті → checkpoint (на reveal + кожні ~15 фіксів) → update/delete на Stop. Краш/OOM посеред прогулянки більше не губить усю сесію (раніше `sessions.csv` писався лише на штатний Stop).
- *DEBUG-дубль:* у debug розкриття далі пишуться й у `visited.txt` — щоб `analyze.py` (польовий аналіз під час тюнінгу) не зламався. Release — тільки Room.
- *Spike-шорткати (→ MVP-0-полір):* `allowMainThreadQueries` (обсяг записів мізерний, jank нехтовний); класичний Room-драйвер — BundledSQLiteDriver (D11) + винесення на IO-dispatcher відкладено.
- *Файли:* `MvpDatabase.kt` (нове: entities+DAO+DB+importer), `TrackingRepository.kt` (visitDao/sessionDao замість VisitStore/SessionStore + session-checkpoint), `MainActivity.kt` (wiring), `build.gradle.kts`/`libs.versions.toml`/`gradle.properties` (KSP+Room). `VisitStore` лишився (importer-load + DEBUG-дубль); `SessionStore` більше не використовується.

**MVP-0 — D6 eligibility («доступний з пішої мережі») реалізовано + verified.**
- *Механіка:* `AreaSource` тепер тягне ще й OSM `highway` (пішу мережу) поряд із будинками → рахує прапорець `accessible` на кожен будинок (контур ≤ буфера **28 м** від пішохідної дороги; grid-індекс сегментів, локальна проєкція). `matchAt` розкриває **лише accessible**. Fail-open: якщо мережі нема — усі accessible (не блокуємо reveal). Seed/perf-режими без прапорця → accessible=true.
- *WALKABLE:* footway/pedestrian/path/steps/residential/living_street/service/unclassified/track/cycleway/tertiary (motorway/trunk/primary самі по собі — не піша мережа).
- *Верифікація (польова `d6verify.py` + пристрій):* Volda-тайл live → **accessible 3453/3705 (93%)**; на польових даних **112/112 should-розкриттів лишились accessible** (нуль хибних негативів — жодного правильного будинку не відсічено), відсіяно ~8% недосяжних.
- *⚠️ Чесне обмеження:* D6 (проста версія) **НЕ рятує «через дорогу»** — 5/5 should-not (across-street) лишились accessible (вони в межах 28 м від дороги, якою ти йшов). Це не про досяжність, а про «мій бік vs протилежний бік» → **fast-follow** (як каже лок D6). Той +1 хибний reveal з фіксу #4 D6 НЕ прибирає.
- *Клієнтський розрахунок* (dogfood на OSM/ODbL); продакшн — на сервері в CC-BY-пайплайні (лок D6).
- *Файли:* `AreaSource.kt` (highway-fetch + `tagAccessible` + grid), `BuildingStore.kt` (`accessible`-масив + `isAccessible`), `TrackingRepository.kt` (гейт у `matchAt`).

**MVP-0 (а) — onboarding + прогрес.**
- *Onboarding:* перший запуск → картка «Це твоя мапа. Кожен будинок, повз який пройдеш пішки, засвітиться своїм кольором… Без поспіху, без штрафів.» + «Зрозуміло» (SharedPreferences-gated, показ РАЗ; спокій D20/D28, без логіну D26). Verified на пристрої: з'являється раз, прапорець тримається на повторному запуску.
- *Прогрес:* Coverage-% тепер від **досяжних** будинків (D6 `accessibleCount`), не від усіх завантажених → «Розкрито N (X% околиці)». Чесніший знаменник (розкрито ⊆ accessible). *(Дрібний борг: на relaunch показує 0, поки зона не довантажилась+reconcile — можна показувати лічильник із Room одразу.)*
- *Файли:* `MainActivity.kt` (`maybeShowOnboarding` + текст «% околиці»), `BuildingStore.kt` (`accessibleCount`), `Stats.kt`/`TrackingRepository.kt` (знаменник).

**MVP-0 (б) — side-aware D6 (across-road): СПРОБА → ВІДКОЧЕНО (негативний результат, verified).**
- *Ідея:* не розкривати будинок, якщо лінія GPS→центр перетинає проїзну дорогу-бар'єр. Реалізовано (AreaSource віддає дороги як LineString, `BuildingStore.crossesRoad` segment-crossing, гейт у `matchAt`), зібралось.
- *Верифікація (`d6b_verify.py` на польових даних) показала, що фіча НЕ працює:*
  - усі проїзні (incl residential): **should помилково блоковано 49/108 (45%)** — у щільному місті лінія 15–30 м майже завжди перетинає якусь residential-дорогу.
  - лише великі (secondary+): безпечно (2% хибних), але **0/5 should-not** — бо хибні reveals у Volda НЕ across-highway.
  - Корінь: 5 «should-not» — **мікс** (across-residential + «зарано» w634020402 на 3м + «помірно» 11–14м), не чиста across-road геометрія → crossing-check будь-якої ширини їх не ловить.
- *Рішення:* **відкочено до post-(а)** — не шипимо фічу, що ламає 45% правильних розкриттів заради 0 користі. Across-road лишається відкритим: потребує розумнішого підходу («той самий тротуар/бік», не сирий crossing) + більшої вибірки ✓/✗-міток. Перевірка врятувала від регресії. Скрипт `d6b_verify.py` лишено для майбутньої спроби.

**Польова марк-прогулянка (Walk 5, ~25хв) на новому білді — фікси спрацювали живцем.**
- *Мітки:* 57 ✓ · 5 ✗ хибних · ~1 пропуск. **Пропуски ↓ ~3× проти старих walk** (5.5%→1.7%) — recall #4/#5 живцем.
- *Replay задеплоєної логіки:* recall **162/164 (99%)**, тайминг «по центру» збережено, Ristevegen-тип ловиться.
- *Точність не змінилась* (5 хибних) — 7 «should-not» це мікс (across-road + «зарано» w634020402 на 3м + помірні), пороги не лікують (R=16…22 → 7/7). (б)-територія.
- *Присуд P2:* пороги фактично на оптимумі; лишається точність (across-road/«зарано»), не поріг.

**P17 — обертання мапи (компас) + фідбек-правки, verified на пристрої.**
- *Механіка:* перемикач як у Google Maps — **іконка 🧭 справа ПО ЦЕНТРУ** екрана (не налазить на статус угорі; за фідбеком). Тап: north-up ↔ course-up (підсвітка синім). Course-up: `SensorEventListener`(ROTATION_VECTOR) → компас-курс зі згладжуванням (кутовий low-pass через 360°, throttle ~12Hz), камера bearing = курс; MapLibre показує власний компас-індикатор. Дефолт north-up.
- *Тайминг-фідбек* («розкривається після проходу → невпевненість, чи не вертатись»): замір (`timing.py`) — recall/precision від `SLACK_CEN` НЕ залежать → безпечно. **`SLACK_CEN 2→1`** — розкриття ~1м раніше (past-центру 3.3→2.3м). p90-хвіст «пізно» (~10м) = холодний старт зони (розкриття пачкою при довантаженні тайла) → окремо, лік = префетч наперед.
- *Обмеження компаса (spike):* азимут без tilt-remap — найкраще коли телефон ~пласко; чиста версія (LocationComponent / fusion GPS+компас) → MVP-1.
- *Файли:* `MainActivity.kt` (компас+кнопка), `TrackingRepository.kt` (`SLACK_CEN`).

**Префетч зони НАПЕРЕД руху + дрібніші тайли (фікс «розкриття після проходу» на cold-start).**
- *Проблема:* тайли були великі (0.05° ≈ 5.5×2.6км, fetch 6км-бокс = ~3700 буд.) → за прогулянку майже не виходиш за тайл; головна затримка = повільний cold-load стартового тайла (розкриття пачкою при довантаженні = «після проходу»).
- *Зміни:* (1) **TILE 0.05→0.02** (~2.2×1км) + fetch `halfKm` 3.0→1.4 → тайл **~2600 буд. замість 3705** (verified на пристрої), швидший cold-load; (2) **`prefetchAhead`** — на кожному фіксі проєктуємо точку за 1000м у напрямку руху (GPS-курс або сегмент попередній→поточний) і префетчимо її тайл → наступний тайл завантажений ДО того, як дійдеш. Тайл менший → тепер префетч реально спрацьовує в межах прогулянки.
- *Verified:* `area_3107_304 fetch: +2612` (D6 accessible 2512/2612), запуск без креша.
- *Обмеження:* перший (стартовий) тайл усе одно ~2600 буд. — пом'якшується `preloadArea` (тягнеться на відкритті застосунку, до Старту); повний лік (дрібні миттєві тайли) — із CC-BY CDN.
- *Файли:* `AreaCache.kt` (TILE), `AreaLoader.kt` (halfKm), `TrackingRepository.kt` (`prefetchAhead`).

**Локалізація (D18) — каркас bokmål / nynorsk / англійська.**
- UI-рядки MainActivity + сповіщення сервісу витягнуто у string-ресурси: `values/` (англ., дефолт) + `values-nb/` (bokmål) + `values-nn/` (nynorsk). Мова — за локаллю пристрою (fallback → англ.). Verified: телефон uk-UA → англ. дефолт («Revealed N (X% of area) · tap Start», «START WALK», типи housing/outbuilding/…).
- ⚠️ Норвезькі переклади **чернеткові** — звірити носієм (особливо nynorsk).
- Не покрито (follow-up): транзієнтні діагностичні нотатки (gate/loading) в `ActivityGate`/`AreaLoader` лишились укр. — не мають Context (треба рефактор note→key).
- Файли: `res/values{,-nb,-nn}/strings.xml`, `MainActivity.kt`, `WalkTrackingService.kt`.

**Вільний пан мапи + кнопка «до мене» (фідбек: мапа постійно центрувалась, годі роздивитись).**
- Камера слідує за позицією ЛИШЕ доки `followMe=true`; щойно юзер перетягнув/зумнув пальцем (`OnCameraMoveStarted` = `REASON_API_GESTURE`) → `followMe=false`, мапа лишається де поставив (і компас-обертання теж не смикає).
- Кнопка **◎** (bottom-right) — повертає до поточної позиції (zoom 16.5 + bearing) і відновлює слідування. Як my-location у Google Maps.
- Verified на пристрої: свайп рухає мапу (не смикає назад), тап ◎ центрує назад.
- Файл: `MainActivity.kt` (`followMe`, `OnCameraMoveStartedListener`, `recenter()`; `updateCamera` під `followMe`).

**CC-BY продакшн-дані (D31) — рішення 1–4 залочено + КРОК 0 (data-спайк) виконано → гіпотеза D8 не спрацьовує для нашого регіону.**
- *Лок (D31):* (1) eligibility-джерело продакшн = Kartverket Elveg; (2) хостинг = безкоштовний статик-CDN; (3) обсяг = регіон-first; (4) міграція Overpass-розкриттів = стерти.
- *Крок 0 (research-воркфлоу 6 агентів + прямі Geonorge-API/WFS-зонди):* **головна знахідка — INSPIRE Buildings НЕ покриває Volda/Sunnmøre.** WFS `wfs.inspire-bu-core2d_limited` реально віддає полігони + `bygningsnummer` (localId), CC-BY, bbox-фільтр працює (Осло-регіон → 499 буд.), АЛЕ широкий bbox по Møre og Romsdal → **0 будинків** (покриття «deficient» на заході). Тобто **точних відкритих CC-BY footprints для нашого регіону НЕМА** (FKB `AccessIsRestricted:true`, INSPIRE відсутній). *(Прим.: попередній спайк D8 схибив на «голому» endpoint — 500; правильний = `_limited`; але для Volda все одно 0.)*
- *Що ПОКРИВАЄ Volda (CC-BY):* Matrikkelen-Bygningspunkt (ТОЧКИ + `bygningstype` + `bygningsnummer`, national, per-kommune-файл) + N50 (генералізовані полігони). Точних індивідуальних footprints — нема.
- *Рішення (Денис, 2026-07-04):* **Варіант 1 — OSM-геометрія (self-host, ODbL) + Matrikkelen-збагачення** (bygningsnummer+тип через point-in-polygon join, CC-BY). Причина: INSPIRE не покриває регіон, FKB закритий для приватних. **FKB = апгрейд ПОТІМ через публічного партнера** (kommune/fylkeskommune/høgskule — усі Norge-digitalt-партнери; дають дані+легітимність+спонсорство; природна послідовність: OSM-демо → партнер → FKB). Атрибуція © OSM + © Kartverket; тайл = ODbL. → D31/D8 уточнено.
- *Артефакти:* `scratchpad/step0_research.js` (воркфлоу) + прямі WFS-тести.

---

## 2026-07-01 — Польова прогулянка (Ristevegen 1) + незалежне review D23 + 3 фікси

**Польовий аналіз (прогулянка ~26 хв, 780 фіксів, телефон підключено → батарея не міряна).** D25.1 у цілому тримається (replay-recall 101/112, розкриття медіана 3.2 м від центру, 77% ≤5 м).
- *Ristevegen 1 (`w396301435`) — подвійний прохід:* прохід 1 (302с) edge **15.4 м** / центроїд 35.3 м, note=ok → НЕ розкрито (Денис поставив ✗); прохід 2 (~1256с, +16 хв) edge **1.1 м** → розкрито. По-фіксовий трейс дав **корінь:** відстеження `runMin`/`passedMiddle` (centroid-closest-approach) обмежене тим самим вікном eligibility (`edge≤R_FAR=18`), що й кандидатність. На дотичному проході вікно закрилось (308с edge→19.3) захопивши лише **+1.0 м** росту центроїда (< `SLACK_CEN=2`); `near_wall` (edge≤3) не спрацював (найближче 15.4 м). → тангенційні проходи на 15–18 м систематично пропускаються. **Незалежно підтверджено D23-воркфлоу (знахідка #4).**
- *Окремо — холодний старт зони:* 36 фіксів із note «завантаження зони…»; будинки, повз які пройшов лише під час довантаження тайла (напр. `w909035749/750`, `w986943649`), **назавжди пропущені** (буфер replay 12≈24с < часу Overpass-fetch). Лік: префетч попереду руху + розширити буфер за часом.
- *Висновок для тюнінгу:* ⚠️ **не тюнити `R_FAR` на цих даних** — тангенційний промах + cold-start спотворюють recall (P2 оновлено).

**Незалежне review D23 (межа Spike-2 → MVP-0)** — дві незалежні гілки, знахідки верифіковано по коду.
- *Гілка 1 (D23-воркфлоу):* 47 агентів, 7 адверсивних lens + 3 tech-stack панелі → 18 знахідок → адверсивна верифікація скептиками (16 підтв., **2 спрост.**: «стале `runMin` придушує reveal» — навпаки, занижений `runMin` робить `passedMiddle` легшим; «`stopWalk` краш» — foreground-тап звільнений від background-start обмежень).
- *Гілка 2 (codex gpt-5.4, read-only):* 5 знахідок; **знайшов backup-egress, який мій власний прохід пропустив** (перевіряв лише мережевий egress).
- *Вердикт:* **готово до MVP-0 з умовами; переробки архітектури не треба.** 3 реліз-блокери: (1) 🔴 `allowBackup=true` → `filesDir` (у debug — сирий diag.csv) у Google-хмару = порушення D14; (2) 🔴 Overpass ODbL→CC-BY CDN (реліз, не dogfood); (3) 🔴 `building_id` не переживе зміну джерела → скидання розкриттів (розширено D30). Плюс кластер 🟠: FGS тихо самопереривається (кнопка бреше), `setGeoJson` перебудова O(revealed)/reveal, втрата сесії без checkpoint, `way["building"]`-only (relation-будинки), Overpass HoL-стал (3×130с на single-thread). Хибна тривога воркфлоу «MapLibre 13.3.0 не існує» — відкинуто (стале знання; реально в build.gradle, працює на Pixel 9); але `optimization{enable=false}` на release **справді вимикає R8/minify** — увімкнути перед релізом.
- *Спец-прогалини:* **D24 CC-BY** — Geonorge INSPIRE Core2d + Matrikkelen → CLI → per-tile GeoJSON на тій самій сітці 0.05° (тип на сервері) → статичний CDN; `CdnGeoJsonAreaSource` за `BuildConfig`. **D6 eligibility** — OSM footway-граф (НЕ turrutebasen), гейтиться на Room → послідовність Room→D6; це справжня відповідь на суперечність Ristevegen 1.

**3 дешеві фікси застосовано (assembleDebug ✅ зелений):**
- **#1 `allowBackup=false`** (AndroidManifest.xml) — `filesDir` більше не йде в Google-бекап (D14).
- **#6 `ensureArea` з-під walk-gate** (TrackingRepository.onLocation) — префетч зони більше не чекає 3-х dwell-фіксів ActivityGate; лише пропускаємо авто-швидкість (`>MAX_PED_SPEED`).
- **#14 `reattachWalk` відновлює `store`** (MainActivity + getter `TrackingRepository.currentStore`) — після пересоздання Activity DEBUG all-шар і ✓/✗-мітки (інструмент тюнінгу Дениса) більше не мертві.
- *Не чіпав* (потребують дизайну/більших змін): тангенційне розчеплення вікон, розширення replay-буфера, FGS-watchdog, checkpoint сесії, relation-парсер, backup-виключення тонкі — у беклог MVP-0.
- *Артефакти:* `spike/fieldtest/{diag,marks,visited}.csv` + `area_1243_12{1,2}.geojson` (стягнуто з пристрою). Аналіз-порядок незмінний (`analyze.py`).

**Планування (без коду):** оцінено фіча-запит Дениса «мапа розвертається за напрямком руху» (як автонавігатор) → занесено в план як **P17** (`DECISIONS.md`) + Фаза 5 (`10` §8). Фіксовано: опційний перемикач, **дефолт north-up** (для пішохода course-up дезорієнтує); відкрите — компасний heading (куди дивишся) vs GPS-course (куди йдеш). Реалізація: швидкий спайк у наявній камері АБО MapLibre `LocationComponent` (MVP-1, прибирає ручний me-шар).

---

## 2026-06-27 — Польовий ретест D25 → рефайн тайминга D25.1 (centroid-closest-approach)

**Тайминг матчингу: edge-closest-approach → CENTROID-closest-approach** — рефайн D25 за польовим ретестом.
- *Привід (дані):* нова прогулянка (чистий on-demand після `pm clear`) → 1563 фікси + 66 ✓/✗-міток, GPS медіана 4.8 м. D25 покращав тайминг (edge@reveal 12.7→7.9 м), але Денис: «деякі ще фарбуються до того, як дійшов; ідеал — **приблизно по середині, коли йдеш уздовж**». `analyze.py` (секція 12/13) знайшов корінь: **`MIN_EDGE=8` спрацьовує на ПЕРЕДНЬОМУ куті** будинку (як тільки за 8 м від найближчої стіни = на початку).
- *Метод (D25.1):* **eligibility** лишається edge ≤ R_FAR=18 (через дорогу/видовжені ловляться), а **тайминг** тепер по closest-approach до **ЦЕНТРОЇДА** (`runMin` зберігає центроїд-дист; розкрити коли виросла на **SLACK_CEN=2 м** над мінімумом = проминув середину) + малий байпас **MIN_EDGE_NEAR=3 м**/всередині замість MIN_EDGE=8 + **`moved`-guard** (тайминг-розкриття лише на русі ≥MIN_MOVE — проти GPS-джитера на місці). Центроїд лежить у центрі будинку, тож «проминув центроїд» = «навпроти середини».
- *Replay-верифікація на тому ж треку:* розкриття лягає медіана **3.3 м від центру** (79% у межах 5 м від центру) проти переднього кута D25; recall 61→**56/61** (ціна: будинки, повз середину яких не пройшов — завернув/зупинився), хибних 4→3. Юніт-тести зелені (+ centroid-вихід `candidatesPoint`).
- *Дані-артефакт (не баг):* розкрився будинок, якого фізично немає — **застарілий OSM-footprint** (знесений). Лікується продакшн-CC-BY + періодичним refresh + ✗-маркуванням; не матчинг.
- *Тунабельне (P2):* `SLACK_CEN`/`MIN_EDGE_NEAR`. *Батарея* знову зіпсована (гуляв з повербанком) — Stage C чекає чистого виходу.
- *Файли:* `BuildingStore.kt` (`candidatesPoint` тепер віддає й центроїд-дист), `TrackingRepository.kt` (`matchAt` → centroid-CA + `moved`-guard; константи MIN_EDGE_NEAR=3/SLACK_CEN=2), `BuildingStoreTest.kt`.

---

## 2026-06-27 — Конкурентний аналіз, рішення D26–D30, git + зведення майстер-файлів

**Конкурентний аналіз (планування, без коду).** Багатоагентне дослідження 20 застосунків-аналогів (reveal-the-map / completion / територія / дослідження + норвезькі: DNT/UT, StikkUT, Stolpejakten, Trimpoeng, Fjelltoppjakten, Peakbook, Norgeskart, World Uncovered, Walksy) — механіки + свіжі відгуки.
- *Висновки:* ніша «розкривання повністю видимої мапи за типом» у Норвегії **вільна**; найближчий конкурент за гейміфікацією — DNT/UT (SjekkUT); фандинг-прецедент **Sparebanken Møre→StikkUT (2 млн kr)** підтверджує модель монетизації; топ-болі жанру (фонова зупинка трекінгу, батарея, paywall, втрата прогресу, MapLibre-рендер на mid-range) → анти-патерни `09` §11.
- *Дизайн-фідбек Дениса* (огляд сторів): еталон **Walkable** + іконки **Walksy**; уникати перевантаження/яскравості/мультяшності → `08` §14 + принципи §1/§8.

**Нові рішення (ухвалені) D26–D30** (із proposed P9/P11/P12/P14/P15):
- **D26** deferred auth — логін пропонувати після розкриття частини карти (Фаза 5; v2 cloud-backup).
- **D27** POI «цікаві місця» — у **природному шарі**: read-only з відкритих даних → особисті локальні нотатки (device-local) → публічні відгуки v2.
- **D28** візуальна мова — мінімалізм, контурні іконки колір-за-типом, низька щільність маркерів, collect/unlock **БЕЗ абстрактного score** (лічильники повноти — ок).
- **D29** UX точності GPS — не розкривати/не пропускати тихо (урок Turf).
- **D30** захист від ретроактивної зміни «розкрито» (анти CityStrides/OSM).
- *Відкриті:* **P10** (двигун новизни/утримання малих міст — прототип+вимір), **P13** (м'яка гейміфікація: повнота числом + щоденна нагорода без примусу/штрафів), **P16** (авто-маршрут v2+). Імпорт історії — розглянуто й **знято**.

**Інфраструктура.**
- **Git** — проєкт узято під версійний контроль (гілка `main`); `.gitignore` виключає APK (~341 МБ) і регенеровані geo-дані; tracked ~24 МБ (код/доки/польові CSV/скриншоти). *Привід:* під час правок `DECISIONS.md` злиплися рядки без можливості відкату.
- **Зведення майстер-файлів** — `AGENTS.md` став **єдиним джерелом** контексту; `CLAUDE.md` = тонкий `@import` (без дублювання 16 КБ). *Навіщо AGENTS.md:* його читає codex (крос-модельний рецензент, D23).
- *Файли:* `DECISIONS.md` (D26–D30, P10/P13/P16), `08` §14/§1/§8, `09` §11/§3/§4, `10` (фази 4/5/6/11), `AGENTS.md`/`CLAUDE.md`, `.gitignore`/`.gitattributes`.

---

## 2026-06-26 (вечір) — Spike-2: edge-матчинг (фікс «зарано» + «через дорогу»), D25

**Матчинг центроїд → контур (edge-distance) + closest-approach** — заміна D5-радіуса, на основі польового присуду.
- *Привід (дані):* 4 прогулянки → 2147 фіксів + 91 ручна ✓/✗-мітка. Денис: «деякі будинки фарбуються ще до того, як я дійшов» + «деякі через дорогу не фарбувались». `analyze.py` довів **один корінь — матчинг до ЦЕНТРОЇДА:** у момент розкриття GPS у медіані 12.7 м від стіни (19 м від центроїда = диск спрацьовує на межі R), 81% розкриттів >10 м від стіни, випередження медіана 11.2 м; а пропущені через дорогу мали стіну 14 м, але центроїд 25 м (>R). Видовжені будинки, повз які пройшов за 2-6 м, лишались сірими (центроїд в іншому кінці).
- *Метод (D25):* (1) відстань GPS→**контур полігона** (point-to-ring, point-in-polygon→0), у локальній проєкції за широтою запиту (коректно по всій Норвегії); (2) **bbox-grid** — будинок індексується у ВСІ комірки, що накриває bbox (інакше великий будинок із далеким центроїдом випадає до edge-тесту — фікс із adversarial-рев'ю); (3) **R_FAR=18 м**; (4) **closest-approach gate** — розкрити коли edge виросла на SLACK=1.5 м над мінімумом (= проминув найближчу точку, йшов уздовж) АБО стіна ≤ MIN_EDGE=8 м (впритул).
- *Чому closest-approach, а не abreast (курс):* 4 незалежні проєкти-агенти зійшлись на abreast, але **3 адверсивні скептики (всі holds:false)** його завернули — курс на 2-м базі шумний (P(похибка>75°)=36% за Монте-Карло), плюс баг кута від кінця сегмента (заявлені 80/83 неперевірені) + діра re-match на zone-load. closest-approach course-free, помиляється «пізніше» (як просив Денис), zone-load діру не має. Вибір зроблено проти консенсусу проєктувальників — саме на користь адверсивного шару.
- *Replay-верифікація на тому ж треку (before field retest):* recall **69→76/83**, edge@reveal медіана **19.2→9.9 м**, 9/15 раніше-пропущених тепер ловляться, 3 видовжені «2-6 м» — усі ✓. Хибних 6→4. Юніт-тести: edge=0 всередині, через-дорогу-по-стіні-не-центроїду, grid-gather великого будинку, Oslo-широта.
- *Залишок:* 6/15 пропусків — ширші вулиці (edge >18); важіль `R_FAR`→20 за нових даних (P2). НЕ чіпали: vehicle-gate, ACC_MAX, building_id.
- *Файли:* `BuildingStore.kt` (геометрія кілець + bbox-grid + `candidatesPoint`/edge), `TrackingRepository.kt` (`matchAt` + `runMin` closest-approach + zone-load replay через gated-матчер), `MainActivity.kt` (radiusM 20→18). Інструмент аналізу: `spike/fieldtest/analyze.py`.

---

## 2026-06-26 — Spike-2: on-demand, мульти-сіті, статистика, vehicle-gate, іконка

**On-demand area download** (D24, замінює S8) — головна зміна дня.
- *Чому:* польовий тест (12 781 фікс) довів, що **фіксований бандл bbox не масштабується** під рух — розкривалось лише там, де я вгадав зону (Volda), бо Денис рухається регіоном ~300 км. Геокод сіл (2-км bbox) щоразу схибив.
- *Як:* `BuildingStore` став **інкрементальним + thread-safe**; `AreaLoader` на кожному (gate-ok) фіксі гарантує, що тайл (~0.05°) навколо тебе завантажений: локальний кеш → інакше `OverpassAreaSource` (Overpass-запит + OSM-парсер на Kotlin) → `addFeatures`. `reconcilePersisted()` відновлює збережені розкриття, коли їхня зона довантажується.
- *Джерело за інтерфейсом* (`AreaSource`): тест = Overpass (ODbL, нуль інфри, флакі — кешуємо зону раз). **⚠️ Перед релізом мігрувати на Pre-hosted CC-BY CDN** (надійність+масштаб+ліцензія) — D24/S8, P4. Запис у канон на прохання Дениса, щоб не забути.
- *Валідовано на Pixel 9:* порожній старт → fetch Volda-тайла (3705 буд.) → тап Старт → розкрив будинок.

**Інші зміни:**
- **Камера на свіжий фікс** (`getCurrentLocation`, не `lastLocation`). *Чому:* `lastLocation` був застарілий — показувало Volda, коли Денис був у Oslo.
- **Мульти-сіті бандл (стопгап, S8)** — проміжний крок до on-demand: bbox по реальних зонах із `diag.csv` (Hallingdal/Land/Oslo/Gardermoen). Замінений on-demand того ж дня.
- **Vehicle/bike-gate (Stage B, D5)** — `ActivityGate` (Activity Recognition Transition API + швидкісний гістерезис) блокує розкриття в авто/велосипеді. *Польовий тест підтвердив:* на дорогах gate коректно блокував.
- **Статистика (D13)** — `Stats`/`SessionStore`/`VisitStore` (тип+час): Coverage/Variety/Discovery, без score.
- **Diagnostic-збір (D14)** — `DiagnosticRecorder` пише сирий трек у `diag.csv`. *Чому gated на `BuildConfig.DEBUG`:* release автоматично не збирає (структурно, не TODO) — на вимогу Дениса «не забути прибрати в публічній версії».
- **Іконка** — placeholder «мапа новизни» (кольорові будинки в колі розкриття + маркер на фьорд-ночі). Фінал — із брендом (P1).
- **Код-рев'ю Spike-2 Stage A:** Claude-адверсивний (30 агентів, 12 реальних багів) + **codex gpt-5.4** (3, з них 2 нові, яких Claude не побачив: init стирав live-стан, executor-leak). Усе виправлено. *Висновок:* крос-модельне review додає реальну цінність → стандарт на gate Spike-2→MVP-0 (D23).
- **Код-рев'ю on-demand (codex gpt-5.4):** 4 реальні знахідки (усі підтверджено адверсивно) → виправлено: **C1** гонка даних — `BuildingStore` мутується у фоні, читався з main без локу → синхронізовані аксесори (`featureAt`/`idAt`/`indexOf`); **C2** async-зона не реплеїла пройдений шлях → буфер нещодавніх фіксів + replay у `onAreaLoaded`; **C3** старі bare-id ≠ on-demand `w<id>` → reconcile пробує `w$id` (відновило 14 «втрачених» розкриттів на пристрої!); **C4** новий `AreaLoader` на кожне пересоздання → переюз store+loader (без витоку executor).
- **On-demand робастність (до польового тесту):** retry-backoff для невдалих зон (Overpass флакі — кулдаун 20с замість спаму щофікса; кеш після успіху назавжди); показ статусу зони на екрані («завантаження зони…» / «немає даних зони»), щоб видно було, що відбувається, а не «застосунок завис».
- **Ground-truth маркування будинків (debug, на прохання Дениса):** на тесті тап по будинку → цикл мітки **✓ correct → ✗ wrong → знято**, одразу лог у `marks.csv` (`t,building_id,mark,lat,lon,wasRevealed`). *Навіщо:* точний ручний фідбек «розкрито правильно/хибно» для тюнінгу порогів матчингу (P2) — звіряти проти `diag.csv`. *Як:* `MarkLog` (append, DEBUG-gated) + кольорові `CircleLayer` мітки + напівпрозорий шар «усі завантажені будинки» (видно, що тапати). **Ідентифікація будинку — через наш `BuildingStore.nearest()` (spatial-index), НЕ `queryRenderedFeatures`** — render-query на пристрої повертав 0 (texture/timing-норов MapLibre); `nearest()` надійний у SurfaceView і texture. Валідовано на Pixel 9 (повний цикл + обидва режими).

---

## 2026-06-22 — Spike-1 v2 (рендер-перф присуд) — D22

- *Питання:* чи двошаровий overlay тримає зростаючий visited-набір плавно. *Присуд (Pixel 9):* **~60 fps пану до 4000 visited**; async `setGeoJson`-латентність ≤~100 мс до 2000.
- *Ключове, спростоване даними:* **sync (`withSynchronousUpdate(true)`) — погано** (≈2× латентність + колапс fps 60→5 при пан+апдеті) → дефолт **async** (D7 виправлено, S7).
- *Інструмент:* власний MapLibre frame-listener (HWUI-tools SurfaceView не бачать — звірено з доками).
- *Метод:* перф-режими bench/combo/replay (`PerfHarness`) + research-воркфлоу з адверсивною верифікацією проти доків MapLibre.

## 2026-06-21 — Spike-1 v1 + Фаза-0

- **Spike-1 v1 (D21):** MapLibre Native рендерить ~10.8k кольорових будинків Volda. PMTiles вантажити `pmtiles://file://` (`asset://` крешить); `.pmtiles` потребує `noCompress`; tiles — tippecanoe.
- **Фаза-0 gate:** стороннє review + адверсивний тех-стек-пас → backend прибрано з MVP (CLI-пайплайн, D12); матчинг уточнено (D5); метрики 3-вимірні (D13). Канон рішень створено (`DECISIONS.md`).

---

## Архітектура as-built (Spike-2, Android `no.streif.spike`)

| Компонент | Відповідальність | Ключові рішення |
|---|---|---|
| `MainActivity` | UI (карта+кнопка+статус), режими walk/perf, дозволи, камера, wiring | D7 (native MapView), C1 (no re-init live-сесії) |
| `WalkTrackingService` | FGS `type=location`, реєстрація Fused + Activity Recognition | foreground-only (без BACKGROUND_LOCATION), START_NOT_STICKY |
| `LocationProvider`/`FusedLocationProvider` | джерело GPS за інтерфейсом (no-GMS-шлях лишено) | Fused, ~2с інтервал |
| `TrackingRepository` (singleton) | ядро: gate→матчинг→reveal→збереження→статка; міст service↔Activity | **D25.1** (`matchAt`: edge-eligibility + **centroid**-closest-approach `runMin` + `moved`-guard), accuracy fail-closed, скид якоря/runMin на межах сесії |
| `ActivityGate` | vehicle/bike-фільтр (AR + швидкісний гістерезис) | D5, консервативно (dwell) |
| `BuildingStore` | in-memory bbox-grid, інкрементальний+thread-safe, **edge+centroid** (`candidatesPoint`) | **D25/D25.1** (edge-eligibility до контуру + центроїд-дист для тайминга), D24, локальна проєкція за широтою запиту |
| `AreaLoader`+`AreaCache`+`AreaSource`/`OverpassAreaSource` | on-demand завантаження зон + кеш + парс OSM | **D24** (джерело за інтерфейсом → CC-BY CDN пізніше) |
| `VisitStore`/`SessionStore`/`Stats` | збереження розкриттів (id,тип,час) + сесій + метрики | D13 (Coverage/Variety/Discovery), D11 (Room — на MVP-0) |
| `DiagnosticRecorder` | сирий трек для тюнінгу (CSV) | **D14, gated `BuildConfig.DEBUG`** |
| `MarkLog` + тап-обробник | ground-truth мітки ✓/✗ розкриття (CSV) для тюнінгу матчингу | **gated `BuildConfig.DEBUG`**; ідентифікація через `BuildingStore.nearest()`, не render-query |
| `PerfProbe`/`PerfHarness` | перф-інструментація (frame-listener) + bench/combo/replay | D22 (HWUI не бачить SurfaceView) |

> Дані будинків: тест = Overpass on-demand (ODbL). Продакшн = CC-BY (INSPIRE+Matrikkelen) на CDN — **міграція обов'язкова (D24/S8/P4)**.

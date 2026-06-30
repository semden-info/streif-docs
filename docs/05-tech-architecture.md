# Streif — Tech Architecture (Технічна архітектура)

> **Статус:** Чернетка v0.2 — 2026-06-21 (узгоджено з `DECISIONS.md` після Фази-0; враховано Spike-1)
> **Спирається на:** `01-product-vision.md`, `02-user-personas.md`, `03-feature-spec.md`, `04-gamification.md`
> **Призначення:** технічна архітектура MVP (**місто-first, device-local**) + ADR. Технічні рішення **звірені з актуальною документацією** (MapLibre, Kartverket, Android, OSM, червень 2026) — ключові джерела в кінці. Детальні джерела/ліцензії даних → `06`; числові пороги матчингу як acceptance criteria → `09`.

> ⚠️ **Звір виявив дві неточності в попередніх матеріалах — виправлено 2026-06-20** (`03` §A і CLAUDE.md «Дані»):
> 1. **`feature-state` недоступний у MapLibre Native на Android** → `03` §A оновлено на двошаровий overlay-підхід.
> 2. **FKB-Bygning не відкритий** (Norge digitalt) → CLAUDE.md «Дані» уточнено: відкриті — INSPIRE Buildings Core2d + Matrikkelen (CC-BY 4.0).

---

## 1. Принципи архітектури

- **Offline-first** — Room (SQLite) = джерело істини; мапа, трекінг, реєстрація відвідувань працюють без мережі (`01` §7).
- **Багатошарова модель з дня 1, наповнюємо лише місто** — схема даних під 3 шари (місто/стежки/вершини), але MVP реалізує тільки місто (`01` §4).
- **Privacy-by-design** — на сервер лише агрегований стан «відвідано», ніколи не сирі GPS-треки (`01` §7 → `07`).
- **Battery** — Fused Location + Activity Recognition; не тримати high-accuracy GPS постійно.
- **MVP-прагматизм (device-local first)** — найпростіше, що відвантажує тестовий білд: перша версія **без живого backend і без логіну** (рішення Дениса — швидше тестувати).

## 2. Огляд системи

```
        ┌─────────────────────── BUILD-TIME (раз) ───────────────────────┐
        │  Kartverket open data (INSPIRE Buildings Core2d + Matrikkelen)  │
        │     → building2osm / GDAL → Tippecanoe → PMTiles (CLI)      │
        └───────────────────────────────┬────────────────────────────────┘
                                         │ buildings.pmtiles
                                         ▼
   ┌──────────────────────────── ANDROID (runtime) ────────────────────────────┐
   │  buildings.pmtiles  (bundled asset у MVP; CDN пізніше)                      │
   │  Kartverket WMTS raster (topograatone) ── базова карта (online)            │
   │                                                                            │
   │  MapLibre GL Native ─ двошаровий рендер:                                   │
   │     [1] сіра база будинків (PMTiles)   [2] visited-overlay (GeoJsonSource) │
   │  Room (SQLite) = джерело істини: будинки, стан «відвідано», статистика     │
   │  Foreground Service ─ Fused Location + Activity Recognition (трекінг)      │
   └────────────────────────────────────────────────────────────────────────────┘
                                         ┆ (post-MVP)
                            опортуністичний sync агрегату → Laravel/PostGIS
```

**Ключове:** для першого білда **немає backend узагалі** — генерація tiles це **CLI-пайплайн без БД** (`building2osm`/GDAL → Tippecanoe → PMTiles). Laravel/PostGIS — лише потенційний v2 (sync/social, `DECISIONS.md` D12). Це і є device-local лінія.

## 3. Android-клієнт

**Стек:** Kotlin + Jetpack Compose · MapLibre GL Native · Room (+ BundledSQLiteDriver) · WorkManager + Foreground Service · Hilt (DI) · Retrofit + Kotlinx Serialization (для майбутнього sync).

### 3.1 ★ Рендеринг і зафарбовування (головна архітектурна корекція)

`feature-state` — те, чим у MapLibre GL JS роблять per-feature розфарбування — **на MapLibre Native (Android) недоступне** (немає Java/Kotlin-біндингу; issue #1698 відкритий, `promoteId` теж не експонований). Тому будуємо **двошаровий дизайн** (рекомендація звіру):

1. **База будинків** — `FillLayer` поверх PMTiles vector-source, **статичний сірий**. Малює всі тисячі будинків дешево (GPU-friendly).
2. **Visited-overlay** — окремий `GeoJsonSource`, що містить **лише відвідані** будинки; `FillLayer` фарбує їх **за типом** через `match`/`get` по property `type` (мала фіксована к-сть категорій — саме те, для чого `match` придатний). Оновлення — `setGeoJson()` при кожному новому візиті.

**Правила продуктивності** (звір — `setGeoJson` re-парсить усю колекцію, partial-update API немає):
- Room = джерело істини відвіданих; overlay тримати **малим** (тільки visited, в ідеалі — лише ті, що в поточному viewport).
- Оновлення `setGeoJson` — **поза main-thread**, debounce/батчинг; **ніколи** не передавати в overlay усе місто.
- **Уникати** гігантського `match` по тисячах ID на базовому шарі (документований перф-регрес, повний reflow стилю на кожен апдейт).
- **Стабільний building ID** «запікати» в tile-property (Tippecanoe) + тримати в Room для дедупу.
- **Інтеграція:** native `MapView` усередині Compose (не wrapper-бібліотека, pre-1.0). Параметри overlay: `GeoJsonOptions.withSynchronousUpdate(false)` — **async** (sync ≈2× латентність + колапс fps при пан+апдеті — spike v2, `DECISIONS.md` D22/S7); overlay `maxzoom ~14–16`.
- **Feature-state на Android — немає в 13.x** (#1698 open, PR #4219 unmerged, перевірено на spike v2 2026-06-22) → двошаровий overlay єдиний; watch-item `DECISIONS.md` P7.
- **★ Spike-1 v1 (підтверджено на Pixel 9):** bundled PMTiles вантажити **`pmtiles://file://`** (копія asset→`filesDir` на 1-му запуску) — **`pmtiles://asset://` крешить** (`incorrect header check`, баг AssetFileSource, усі MapLibre 12.3.1–13.3.0); `.pmtiles`-asset потребує **`noCompress`**. Рендер ~10.8k кольорових будинків Volda — ✅ (`DECISIONS.md` D21).
- **★ Spike-1 v2 (підтверджено на Pixel 9, `DECISIONS.md` D22):** двошаровий overlay тримає **~60 fps пану до 4000 visited**; async `setGeoJson`-латентність ≤~100 мс до 2000; пам'ять стабільна; матчинг radius-grid точний. Перф міряти **власним MapLibre frame-listener** (HWUI/SurfaceView не бачать).

### 3.2 Базова карта

Kartverket **WMTS raster**, шар **`topograatone` (сіра)** — `https://cache.kartverket.no/v1/wmts/1.0.0/topograatone/default/webmercator/{z}/{y}/{x}.png` як `raster`-source. Сіра база ідеально лягає на механіку «сіре за замовчуванням → колір при розкритті». **Атрибуція «© Kartverket» (CC-BY 4.0) обов'язкова в UI.** (Vector-база Kartverket `landtopo` поки `/test/`, без SLA — не для MVP.) **Офлайн (review):** raster — онлайн-WMTS, тож для офлайну **попередньо кешувати bbox регіону** (`OfflineManager`) або bundle; **не** покладатись на live-WMTS у полі. Письмово підтвердити з Kartverket умови офлайн-копіювання (`DECISIONS.md` D15/P4).

## 4. Трекінг і батарея

- **Foreground Service `type="location"`** (Android 14+): дозволи `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_LOCATION` + `ACCESS_FINE_LOCATION` (runtime, while-in-use). **Свідомо уникаємо `ACCESS_BACKGROUND_LOCATION`** — запускаємо FGS лише з видимого екрана. Це (а) тримає Streif **поза Google Play background-location review** і (б) підкріплює privacy-by-design (`01` §7). FGS зберігає доступ до локації навіть при згаслому екрані.
- **Fused Location** — `PRIORITY_HIGH_ACCURACY`, інтервал ~3–5 с + `setMinUpdateDistanceMeters(~5–10 м)` (стоячи — без апдейтів). Достатньо, щоб зафіксувати, повз які будинки пройшов пішки.
- **Guard проти авто** — **Activity Transition API** (`ACTIVITY_RECOGNITION`) як **підказка** (не єдиний gate): знижує довіру на `IN_VEHICLE`, відновлює на `WALKING`/`RUNNING`. Бекстоп — швидкісний фільтр **із гістерезисом** (різні пороги входу/виходу зі стану «авто»), щоб не відсікати швидких бігунів (`DECISIONS.md` D5). Fallback, якщо немає Google Play services або дозвіл відхилено.
- `removeLocationUpdates` + `stopForeground` на «стоп» або still-timeout.

## 5. ★ Реєстрація відвідувань (алгоритм матчингу)

**Edge-distance матчинг + closest-approach gate** (`DECISIONS.md` **D25**, польовий присуд 2026-06-26 — замінив центроїд-радіус D5). Будинок позначається «**розкрито**», коли GPS наближається до його **КОНТУРУ** (полігона), а не до центроїда.

> **Чому не центроїд (заміна D5):** польовий тест (2147 фіксів + 91 ручна мітка) показав, що відстань до центроїда спричиняла **обидві** скарги: будинки попереду засвічувались зарано (центроїд входив у радіус за ~11 м до того, як ти порівнявся), а будинки через дорогу / видовжені — пропускались (стіна за 14 м, але центроїд за 25 м, поза R). Edge-distance прив'язує матч до **ближньої стіни**.

**Алгоритм (як реалізовано, `BuildingStore`/`TrackingRepository`; тайминг уточнено в `DECISIONS.md` D25.1):**
- **Eligibility = GPS → контур полігона ≤ `R_FAR`** (point-to-ring edge-distance; всередині footprint → 0). Локальна планарна проєкція **за широтою запиту** (коректно по всій Норвегії). Це ловить будинки через дорогу/видовжені (стіна близько, навіть якщо центроїд далеко).
- **bbox-grid:** будинок індексується у **всі** комірки, що накриває його bbox → великий/видовжений будинок із далеким центроїдом, але близькою стіною не випадає до edge-тесту.
- **Тайминг = closest-approach до ЦЕНТРОЇДА (D25.1):** розкрити, коли відстань до **центроїда виросла на `SLACK_CEN` над мінімумом** (= проминув **середину** будинку, «по середині, коли йдеш уздовж» — польова вимога Дениса), **АБО** стіна ≤ `MIN_EDGE_NEAR` / всередині (впритул-байпас). Лише на реальному русі (`moved`-guard ≥ `MIN_MOVE` — проти GPS-джитера на місці). *Чому центроїд для тайминга:* edge-closest-approach (D25) спрацьовував на передньому **куті** будинку (зарано); центроїд лежить у центрі → розкриття лягає навпроти середини. *Чому не abreast-курс:* adversarial-рев'ю — курс на короткій базі шумний (крихкий); closest-approach course-free, помиляється «пізніше».
- **Параметри (тунабельні, поточні):** `R_FAR=18 м` (eligibility) · `MIN_EDGE_NEAR=3 м` (впритул) · `SLACK_CEN=2 м` (центроїд-CA) · `ACC_MAX=30 м` (fail-closed). Replay-верифікація: розкриття медіана **3.3 м від центру** будинку (79% у межах 5 м).
- **Vehicle-gate (D5/Stage B):** Activity Transition API (`ACTIVITY_RECOGNITION`) як **підказка** + швидкісний гістерезис; рахується ПЕРЕД матчингом. Польово-валідовано (98% швидких фіксів блоковано).
- **Eligibility-фільтр (D6):** рахувати лише будинки, доступні з публічної пішої мережі — **ще НЕ реалізовано, на MVP-0**.

**Тунабельні параметри** (фіналізуються як acceptance criteria в `09`, `DECISIONS.md` P2): `R_FAR` (18↔20 на ширші вулиці) · `SLACK_CEN` · `MIN_EDGE_NEAR` · `ACC_MAX`. Тюнінг — через ✓/✗-маркування (debug) + `spike/fieldtest/analyze.py` на польових логах.

**Edge-cases:** дуже широка вулиця (інший бік за >18 м — свідомо не ловимо при R_FAR=18; важіль →20); GPS-дрейф (accuracy-gate); стояння впритул (MIN_EDGE-байпас); зона довантажується пізніше (replay нещодавнього шляху через той самий gated-матчер, D24/C2).

## 6. Модель даних

- **Room (клієнт, джерело істини):** `buildings` (stable_id, type, layer, геометрія для overlay), `visits` (building_id, timestamp), агрегована статистика (% покриття, лічильники). Метрики накопичувальні (`04` §3).
- **Build-time (CLI, без БД):** просторовий join INSPIRE-полігонів + Matrikkelen-типів через `ogr2ogr`/GDAL; схема даних спроєктована під 3 шари, наповнюємо лише місто. PostGIS — лише v2 (`DECISIONS.md` D12).
- **Що синхається пізніше (v2):** агрегований стан «розкрито», **не** треки (`07`).

## 7. Дані й tiles (pipeline)

**Джерело будинків (звірено):**
- **Геометрія — INSPIRE Buildings Core2d** (CC-BY 4.0, ~4.3 млн footprint-полігонів). *Тип НЕ з INSPIRE-полігонів — а з Matrikkelen (наступний пункт); виправлено після review.*
- **Matrikkelen-Bygningspunkt** (CC-BY 4.0) — тип (`bygningstype`), але **точкова** геометрія; для enrich/валідації типу.
- **`building2osm`** (CC0-інструмент) — робить join «INSPIRE полігони + Matrikkelen тип» → полігони+типи **CC-BY 4.0**. ⚠️ *Його WFS зараз не віддає полігони (тех-стек-пас) — тягнути per-kommune файли **прямо з Geonorge**, а з інструмента брати лише `building_types.csv`.*
- **OSM** — Volda (1577) і Ørsta (1520) уже на **100% імпорту полігонів** (із тих самих Kartverket-даних), з типами; **але ліцензія ODbL** (share-alike). Швидкий bootstrap, не «чистий» для продукту.
- ⚠️ **FKB-Bygning НЕ планувати** — Norge digitalt-обмежений (платний доступ).
- `bygningstype`-коди: стандарт NS3457 / SSB Klass 31 (111 enebolig, hytte/fritidsbolig, 671 kirke …).

**Доставка будинків — on-demand завантаження зон (`DECISIONS.md` D24, замінює фіксований бандл S8).** Польовий тест довів, що фіксований bbox-бандл не масштабується під рух користувача (розкривалось лише там, де вгадано зону). Натомість:
- `BuildingStore` **інкрементальний** (починається порожнім, thread-safe); `AreaLoader` на кожному (gate-ok) фіксі гарантує, що тайл (~0.05°) навколо GPS завантажений: локальний кеш → інакше мережевий fetch → `addFeatures`. `reconcilePersisted()` відновлює збережені розкриття, коли їхня зона довантажиться.
- **Джерело за інтерфейсом** (`AreaSource`): **тест = Runtime Overpass** (OSM/ODbL, нуль інфри, флакі — кешуємо зону раз). ⚠️ **ОБОВ'ЯЗКОВО мігрувати на pre-hosted CC-BY CDN ПЕРЕД публічним релізом** (надійність + масштаб для багатьох юзерів + ліцензія CC-BY 4.0) — тригер `DECISIONS.md` D24 / P4. **NB (приватність):** on-demand шле **bbox-координати** до стороннього сервера — новий вихідний потік, задокументовано в `07` (сирий GPS-трек усе одно не залишає пристрій, D14).
- **PMTiles (Tippecanoe→`pmtiles://file://`, D21)** лишається для **seed перф-режимів** (bench/replay), не для продакшн-доставки.

**Рендер PMTiles:** MapLibre Android підтримує PMTiles **нативно з v11.8.0**; беремо **13.3.0**. PMTiles **не підтримує** offline-pack API → glyphs/sprites/style теж бандлити локально.

## 8. Backend

**MVP — backend НЕ потрібен** (уточнено після review + тех-стек-пас, `DECISIONS.md` D12). Build-time генерація tiles — це **CLI-пайплайн без БД**: `building2osm`/GDAL → Tippecanoe → PMTiles (версіоновані скрипти). Жодних Laravel/Filament/PostGIS/Sanctum/Redis/FCM у MVP.

**v2 (sync/social):** стек обрати, коли з'являться реальні вимоги (Laravel+Filament+Postgres vs Supabase vs Django — `DECISIONS.md` P5). Тоді ж — акаунти, лідерборди, FCM (мінімально, «без push-тиску» `04` §9). На сервер — лише агрегований стан (`07`).

## 9. ★ Технічний spike (найбільший ризик — валідувати ДО UI)

**Розділено на два (після review, `DECISIONS.md` D17):**
1. **Spike 1 — рендер:** реальні дані → PMTiles → **симульований GPS** → двошарове кольорування плавно на mid-range Android (кількасот–низькі тисячі visited). Міряти frame-time на toggle + латентність `setGeoJson`. **Ізолює #1 ризик** від GPS; можна в кімнаті, детерміновано.
2. **Spike 2 — трекінг:** реальний FGS `type=location` (Android 14+, без `SecurityException`) + Activity Transition gating + diagnostic mode.

## 10. ADR-список (короткі записи)

| # | Рішення | Контекст / наслідок |
|---|---|---|
| ADR-01 | Kotlin + Jetpack Compose | сучасний Android-стек |
| ADR-02 | MapLibre GL Native (не Google/Mapbox) | open, vector, наші tiles, без per-map fee |
| **ADR-03** | **Зафарбовування БЕЗ `feature-state`: двошарово** (сіра vector-база + visited GeoJSON-overlay, колір за типом через `match`) | `feature-state` недоступний на Native Android (#1698); visited у Room, overlay малий, off-main-thread |
| ADR-04 | Room = джерело істини | offline-first |
| ADR-05 | **Радіус-матчинг** для MVP (не street-corridor) | простіше, швидше; точність — пізніше |
| **ADR-06** | Дані будинків: **INSPIRE Buildings Core2d (CC-BY 4.0)** канонічно (через `building2osm`); OSM — bootstrap; **не FKB** | чиста CC-BY-атрибуція vs ODbL share-alike |
| ADR-07 | PMTiles **bundled-asset** у першому білді; CDN пізніше; MapLibre **13.x** | нуль інфри, офлайн; стабільність |
| ADR-08 | Base map Kartverket **WMTS `topograatone`** (raster) | сіра база під механіку; vector `landtopo` — `/test/`, пізніше |
| ADR-09 | **Device-local MVP** без акаунтів; **foreground-only** location (без BACKGROUND_LOCATION) | швидший тест; поза Play-review; privacy |

## 11. Технічний скоуп MVP — що НЕ робимо

Health Connect · Strava/Garmin sync · соц-backend/акаунти/sync · push-кампанії · природний шар + safety-GATE · `ACCESS_BACKGROUND_LOCATION` · CDN (поки bundled) · street-corridor матчинг. Каркас (схема даних під 3 шари) — так; реалізація — ні.

## 12. Відкриті точки / залежності + виявлені неточності

**Виявлені неточності — виправлено (2026-06-20):**
- **CLAUDE.md «Дані»:** уточнено — FKB-Bygning обмежений (Norge digitalt); відкриті — **INSPIRE Buildings Core2d + Matrikkelen (CC-BY 4.0)**.
- **`03` §A:** оновлено на двошаровий overlay-підхід (feature-state на Native недоступний).

**Відкриті точки:**
- **Джерело будинків:** ✅ вирішено — **A: `building2osm` → CC-BY 4.0** (канонічний пайплайн); OSM — лише опційний bootstrap для першого spike.
- **Пороги матчингу** (R, dwell) — підібрати на місцевості → `09`.
- **Кольори за типами будівель** → `08`.
- **Точні Geonorge endpoint/UUID/формати** INSPIRE Core2d — підтвердити в Geonorge UI → `06`.
- **Коли вмикати CDN і backend-sync** → `10`.

---

### Ключові джерела звіру

- **feature-state gap (Native Android):** [maplibre-native #1698](https://github.com/maplibre/maplibre-native/issues/1698), [#185](https://github.com/maplibre/maplibre-native/issues/185); data-driven styling — [Android example](https://maplibre.org/maplibre-native/android/examples/styling/data-driven-style/).
- **PMTiles (Android native ≥11.8.0):** [MapLibre Android PMTiles](https://maplibre.org/maplibre-native/android/examples/data/PMTiles/); [Tippecanoe](https://github.com/felt/tippecanoe).
- **Дані будинків:** [OSM Norway Building Import](https://wiki.openstreetmap.org/wiki/Import/Catalogue/Norway_Building_Import); [building2osm](https://github.com/nkamapper/building2osm); [FKB-Bygning (Norge digitalt)](https://data.norge.no/en/datasets/a43ebac8-7b1c-4feb-9832-f77d2fa38b6e/fkb-bygning); [Matrikkelen-Bygningspunkt](https://data.norge.no/en/datasets/06b0758f-e590-4004-8eaf-e2801f4dc34e/matrikkelen-bygningspunkt); [bygningstype (SSB Klass 31)](https://www.ssb.no/klass/klassifikasjoner/31).
- **Android трекінг:** [optimize for battery](https://developer.android.com/develop/sensors-and-location/location/battery/optimize); [activity transitions](https://developer.android.com/develop/sensors-and-location/location/transitions); [FGS types](https://developer.android.com/develop/background-work/services/fgs/service-types).
- **Kartverket база + умови:** [WMTS cache](https://www.kartverket.no/en/on-land/kart/bygge-inn-kart-pa-nett); [terms of use (CC-BY 4.0)](https://www.kartverket.no/en/api-and-data/terms-of-use).

# Streif — Spike Plan (План технічних spike)

> **Статус:** v0.1 — 2026-06-21
> **Спирається на:** `05` §9, `09` §8, `10` §4, `DECISIONS.md` D17
> **Призначення:** конкретний план технічних spike перед розробкою UI. Перехід із фази документації у фазу виконання.

> **Що таке spike:** короткий, time-boxed, **одноразовий** експеримент, щоб зняти технічний ризик **до** будівництва справжнього. Вихід — **знання + рішення-gate**, не продакшн-код. Код можна викинути.

---

## Spike 1 — Рендер (головний ризик #1)

**Питання:** чи MapLibre Native на **реальному mid-range Android** плавно рендерить сіру PMTiles-базу будинків **і** перефарбовує зростаючий visited-набір (GeoJSON-overlay) до **низьких тисяч**, повністю офлайн, native MapView у Compose?

**Перший зріз: Volda (kommune 1577)** — там живе власник, легко звіряти результат «на око». Дані — **реальний Geonorge-пайплайн** (заодно валідує сам пайплайн).

### 1. Дані — ✅ ГОТОВО (для spike — OSM; Geonorge — на продакшн)
> **Статус (2026-06-21, перевірено наживо):** INSPIRE WFS зараз віддає лише **точки, не полігони** (підтверджує README `building2osm`) → для spike дані взято з **OSM** (Volda, **10 814 будинків**, типізовані → `spike/buildings.pmtiles`, tippecanoe). Дані OSM — GDAL/Docker; **tiles — tippecanoe** (образ `spike/tippecanoe/`). Скрипти: `spike/fetch_osm.py`, `spike/build_osm_tiles.py`. Чистий **CC-BY Geonorge-пайплайн** — продакшн-задача (`DECISIONS.md` D8/P4).

*Продакшн-ціль (Geonorge, коли WFS віддаватиме полігони):*
1. **Геометрія** — INSPIRE Buildings Core2d для Volda через **відкритий WFS** (`wfs.inspire-bu-core2d`, GetFeature по bbox Volda).
2. **Тип** — Matrikkelen-Bygningspunkt для Volda 1577, **per-kommune GML** (`nedlasting.geonorge.no`).
3. **Spatial join** тип→полігон (point-in-polygon на bygningsnr) + маппінг `bygningstype` → колірна група (`building_types.csv` як референс).
4. → **GeoJSON** зі стабільним `building_id` + property `type`.
5. **Tippecanoe** → `buildings.pmtiles` (bundled-asset).
   *(WFS у `building2osm` зламаний — тягнути напряму; `06` §3.)*
   **Скрипт:** `spike/build_volda_tiles.py`.

### ✅ Проміжний результат — статичний рендер (v1, 2026-06-21)

Зібрано одноразовий каркас (View-based MapLibre `MapView`; AS-проєкт `no.streif.spike`, файли в `spike/android-render/`) і **протестовано на Pixel 9**:
- **Рендер тисяч кольорових будинків Volda працює** (PMTiles + палітра `08`). **Ризик #1 (рендер) — знятий.**
- **PMTiles вантажити `pmtiles://file://`** (копія asset→`filesDir` на 1-му запуску). `pmtiles://asset://` **крешить** `incorrect header check` (баг AssetFileSource, усі MapLibre 12.3.1–13.3.0). `.pmtiles`-asset — обов'язково `noCompress`. GeoJSON-джерело теж рендерить (запас).
- Деталі → `DECISIONS.md` D21, `05` §3.1.

**Лишилось у Spike 1 (= v2):** двошаровий overlay (§2) + симульований GPS (§3) + **перф-присуд** (§4–5) — це і є головний ризик.

### ✅ Spike-1 v2 — механіка + перф-присуд (2026-06-22, Pixel 9, provisional)

Зібрано v2 (режими replay/bench/combo; `BuildingStore` + `PerfProbe` + `MainActivity`) і **протестовано на Pixel 9**:
- **Двошаровий overlay тримає ~60 fps пану до 4000 visited** у viewport (bench і combo). Критерії §4 (60 fps; ≥1000–2000) — пройдено з запасом.
- **`setGeoJson` async-латентність** ≤~100 мс до 2000 (148 мс@4000), поза main-тредом.
- **sync — погано:** при пан+апдеті колапс fps 60→48→19→5 (N=1000/2000/4000) → дефолт **async** (`withSynchronousUpdate(false)`); D7 виправлено, `DECISIONS.md` S7/D22.
- **Пам'ять стабільна** (без витоку, ~41 МБ@1387). Матчинг radius-grid точний (1387/1387).
- **Інструмент** — власний MapLibre frame-listener (HWUI/SurfaceView не бачать; research 2026-06-22). Деталі → `DECISIONS.md` **D22**, `spike/android-render/SPIKE-STATUS.md`.
- **Лишилось для gate:** дозамір на **mid-range** (§7) — Pixel 9 флагман.

### 2. Каркас-застосунок (одноразовий)
- Compose + native MapLibre `MapView`.
- Стиль: база `topograatone` (raster; для офлайну — pre-cache bbox Volda через `OfflineManager`) + **сірий FillLayer будинків** (PMTiles) + **visited** `GeoJsonSource`/FillLayer (колір за `type` через `match`).

### 3. Симульований GPS
- Записаний/синтетичний маршрут по Volda (lat/lon + час) — **replay** у застосунку.
- Радіус-матчинг у застосунку → додавати будинки в overlay через `setGeoJson` (off-main-thread, `withSynchronousUpdate(true)`, viewport-scoped).
- **Без** реального GPS / FGS / батареї.

### 4. Критерії успіху
- ~60 fps пан/зум із базою + будинками; **без джанку** на toggle.
- `setGeoJson` оновлення→рендер **< ~100 мс**, поза main-thread.
- тримає **≥1000–2000** visited у viewport без деградації.
- пам'ять стабільна на довгому маршруті (без витоку).
- працює **офлайн** (bundled PMTiles + кешована база).

### 5. Інструментація
- frame-time / fps (Macrobenchmark / JankStats), латентність `setGeoJson`, пам'ять.
- Заміри на **100 / 500 / 1000 / 2000+** visited.

### 6. Перевірка feature-state — ✅ закрито (недоступно)
- Android `setFeatureState` у MapLibre Native **13.x НЕ існує** (issue #1698 open, PR #4219 unmerged станом на 2026-06-22) → head-to-head неможливий; двошаровий overlay — єдиний шлях. Watch-item → `DECISIONS.md` P7.

### 7. Пристрій
- **Основний тест-пристрій — Google Pixel 9** (власника).
- ⚠️ *Caveat:* Pixel 9 — **флагман**; для **gate-присуду по продуктивності** додатково зміряти на **mid-range/старшому** пристрої — джанк-ризик живе саме на слабшому залізі, а не на Pixel 9.

### 8. Gate
- Проходить критерії → **Spike 2**. Не проходить → feature-state (якщо вийшов) або **редизайн рендеру ДО коду UI**.

**Поза scope Spike 1:** реальний GPS, FGS, батарея, eligibility-фільтр, UI-полір, гейміфікація, акаунти, повний регіон.

---

## Spike 2 — Трекінг (після Spike 1)

**Питання:** чи реальний FGS-трекінг + матчинг працюють надійно й прийнятно по батареї на реальному пристрої?

- **FGS `type=location`** (foreground-only) + Fused Location + **Activity Recognition** (vehicle-gate з **гістерезисом**).
- Уточнений матчинг: **буфер сегмента**, accuracy, мінімальне переміщення (`05` §5).
- **Diagnostic mode** — сирий трек локально ~30 днів (`07` §4).
- Перевірити: працює при **згаслому екрані**; **OEM-killers** (Samsung/Xiaomi); **батарея** на типовій прогулянці; false positives/negatives через diagnostic-трек.
- **Gate:** надійно + батарея ок → будуємо MVP-0.

---

## Після spike

**MVP-0** (`09` §3) → dogfood у Volda → міряти головне: **чи Streif справді змушує обрати новий маршрут** (`01` §9, `DECISIONS.md` D2).

## Відкриті точки

- Конкретний симульований маршрут Volda — записати реальний трек чи синтезувати.
- Знайти один **mid-range/старший** пристрій для gate-замірів (Pixel 9 — основний dev/тест).
- Стартові `R` / accuracy — гіпотези (`09` §6).

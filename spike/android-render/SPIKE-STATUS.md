# Spike — стан і як продовжити

> Оновлено: 2026-06-22. Для безшовного продовження (зокрема в новій сесії).

## Стан
- **Spike-1 v1 (статичний рендер) — ✅ ГОТОВО** (2026-06-21). Кольорові будинки Volda через PMTiles на Pixel 9. Ризик #1 знятий. → `DECISIONS.md` D21.
- **Spike-1 v2 (механіка + перф) — ✅ ГОТОВО provisional** (2026-06-22, Pixel 9). Двошаровий overlay + симульований GPS + перф-присуд. → `DECISIONS.md` **D22**.
- **Spike-2 Stage A (реальний GPS) — ✅ ЗБУДОВАНО + device-validated** (2026-06-22, Pixel 9, окрім руху). FGS `type=location` + Fused + сегмент-матчинг (D5) + accuracy/min-move gate + файл-збереження + walk-UI. На пристрої: тап «Старт» → FGS (`types=0x8`) → реальний фікс (22м) → point-match розкрив будинок → **persistence через рестарт** ✅, без креша. Перф-режими (bench 60fps@4000) цілі після винесення в `PerfHarness`. Код пройшов **2 незалежні рев'ю** (Claude-адверсивний + codex gpt-5.4): 12 багів виправлено. **Лишилось:** рух (сегмент-матчинг) — потребує реальної ходьби; **Stage B** (vehicle/bike-gate); **Stage C** (battery-gate). Runbook: `SPIKE2-WALKTEST.md`. Код: `MainActivity/WalkTrackingService/TrackingRepository/LocationProvider/VisitStore/BuildingStore/PerfHarness`.
- **Spike-2 додатки (2026-06-22):** **статистика** (Coverage/Variety/Discovery, D13 — `Stats`/`SessionStore`/`VisitStore` з типом+часом); **diagnostic-збір** сирого треку (`DiagnosticRecorder`→`diag.csv`, **gated `BuildConfig.DEBUG`** → off у release, D14); **мульти-сіті дані** — `buildings.geojson` тепер 30 117 будинків (Volda + Vinstra 3145 + Torpo 823 + Enger 221 + Oslo-центр 5км 15114; `spike/build_multicity.py`), `largeHeap`, kLon за локальною широтою; парс 3.2с без OOM на Pixel 9. Інші міста — база Kartverket (без сірої PMTiles; Volda лишає свою). Shareable APK: `spike/streif-multicity-debug.apk`.
- **Spike-2 Stage B (vehicle/bike-gate) — ✅ ЗБУДОВАНО + device-validated (пішохід)** (2026-06-22). `ActivityGate` (Activity Recognition Transition API + швидкісний гістерезис, D5) → `ActivityTransitionReceiver` + AR-реєстрація у `WalkTrackingService` + консультація в `TrackingRepository.onLocation` (блок → скид якоря). Деградує до speed-only без `ACTIVITY_RECOGNITION`. На пристрої: AR без креша; gate проходить dwell→ok при ходьбі (видно в `diag.csv`). **Поле:** блок авто/велосипеда (>7 м/с / `IN_VEHICLE`/`ON_BICYCLE`) + тюнінг порогів (P2) — потребує реальної їзди.
- **On-demand area download — ✅ ЗБУДОВАНО + device-validated (2026-06-26, D24).** Польовий тест довів, що фіксований бандл не масштабується під рух → перейшли на on-demand. `BuildingStore` інкрементальний+thread-safe; `AreaLoader` на (gate-ok) фіксі тягне тайл (~0.05°) навколо тебе: кеш → інакше `OverpassAreaSource` (Overpass-запит + OSM-парсер на Kotlin) → `addFeatures` → перематч/відновлення збережених. На пристрої: порожній store → fetch Volda-тайла з Overpass (3705 буд.) → тап Старт → **розкрив будинок** ✅. Працює **будь-де в Норвегії**. **Джерело за інтерфейсом** — `OverpassAreaSource` (ODbL, тест) → **⚠️ мігрувати на Pre-hosted CC-BY CDN перед релізом (D24/S8, P4)**. Стопгап-бандл `buildings.geojson` (43k) лишився лише для перф-режимів (seed).
- **Далі:** Stage C (battery-gate — реальна прогулянка, фізичний анплаг) + польове тюнінг матчингу/gate + (на майбутнє) міграція джерела на CC-BY CDN; перед продакшн-стелею — **дозамір на mid-range** (`11` §7).

## Присуд Spike-1 v2 (Pixel 9) — стисло
- **~60 fps пану до 4000 visited** у viewport (bench і combo). Ціль «≥1000–2000 без деградації» — з запасом.
- **`setGeoJson` async-латентність:** 100→24, 500→17, 1000→68, 2000→99, **4000→148 мс**. (sync ≈2× гірше.)
- **sync = погано:** при пан+апдеті **колапс fps** 60→48→19→**5** на N=1000/2000/4000 (render-тред блокується). → дефолт **async** (`withSynchronousUpdate(false)`); D7 виправлено, S7.
- **Пам'ять стабільна** (GC-sawtooth, без витоку, ~41 МБ@1387 visited). Матчинг radius-grid точний (1387/1387).
- **feature-state на Android 13.x НЕ існує** (#1698 open, PR #4219 unmerged) → двошаровий overlay єдиний; §6 спайку закрито.

## Ключові факти (щоб не наступати на ті ж граблі)
- **Перф міряти ВЛАСНИМ frame-listener MapLibre** (`addOnDidFinishRenderingFrameListener` → `fully, frameEncodingTime, frameRenderingTime`). HWUI-інструменти (gfxinfo / JankStats / Macrobenchmark / Perfetto FrameTimeline) **SurfaceView MapLibre не бачать**. fps рахуємо по wall-clock міжкадровому інтервалу (unit-independent). → research-звіт 2026-06-22.
- **Екран мусить бути увімкнений увесь замір.** Блокування → `onStop` → SurfaceView знищується → рендер стоп («no frames»), а процес дроселюється (parse 2с→14с). Фікс: app має `FLAG_KEEP_SCREEN_ON`; для CLI — `adb shell svc power stayon true`.
- **PMTiles вантажити `pmtiles://file://`** — `MainActivity` копіює `assets/buildings.pmtiles` → `filesDir` і переписує URL у стилі. `pmtiles://asset://` **крешить** (`incorrect header check`, усі 12.3.1–13.3.0).
- `app/build.gradle.kts`: `androidResources { noCompress += "pmtiles" }` — **обов'язково**.
- Tiles — **tippecanoe** (не GDAL), образ `spike/tippecanoe/`.
- `CameraUpdateFactory.scrollBy` у 13.x **немає** — пан через `newLatLng` (зсув target).

## Проєкт і дані
- Android Studio проєкт: `C:\Users\mail\AndroidStudioProjects\Streif` (package `no.streif.spike`), MapLibre `13.3.0`, AGP 9.2.1 (Kotlin вбудований — окремий плагін не потрібен).
- Код v2: `BuildingStore.kt` (парс geojson + uniform-grid індекс + radius-матч), `PerfProbe.kt` (frame-listener + латентність + лог `SPIKEPERF`), `MainActivity.kt` (режими replay/bench/combo, intent-extras).
- Assets: `buildings.pmtiles` (сіра база), `buildings.geojson` (10 814 — геометрія overlay + центроїди матчингу), `route.json` (синтетична змійка, 3216 точок, розкриває 1387), `style.json` (база + сірі будинки; visited-шар додається в коді).
- Регенерація даних/маршруту: `spike/build_osm_tiles.py` (tippecanoe), `spike/gen_route.py` (маршрут).

## Збірка/тест із CLI (я драйвлю сам; AS Run перезаписує — не використовувати)
- JBR: `C:\Program Files\Android\Android Studio\jbr` → `$env:JAVA_HOME`.
- Build: `& "<proj>\gradlew.bat" -p "<proj>" :app:assembleDebug --console=plain`
- APK: `<proj>\app\build\outputs\apk\debug\app-debug.apk`
- adb: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`, пристрій `48290DLAQ003FR` (Pixel 9).
- Цикл: `install -r` → `svc power stayon true` → `logcat -c` → `am start … <extras>` → чекати → `logcat -d -s SPIKEPERF`.

### Режими запуску (intent-extras)
- **bench** (статичні N, латентність + frame-time під паном після осідання):
  `am start -n no.streif.spike/.MainActivity --es mode bench` (додати `--ez sync true` для контрасту)
- **combo** (пан ОДНОЧАСНО з апдейтами — combined-стрес):
  `… --es mode combo` (та `--ez sync true`)
- **replay** (симульований GPS, накопичення + пам'ять):
  `… --es mode replay --ei tickMs 25` (додати `--ez texture true` для `screencap`)
- Інші extras: `--ei radius 30`, `--ei flushMs 150`, `--ez stats true` (`enableRenderingStatsView`), `--es zoom 14`.
- Скрін (лише при `texture=true`): `screencap -p /sdcard/s.png` → `pull`.

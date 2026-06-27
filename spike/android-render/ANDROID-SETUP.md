# Android spike — setup / build

> **Статус:** проєкт давно збутстрапнуто й розгорнуто далеко за межі v1. Цей файл тримає
> (а) **поточний спосіб білду/запуску** (CLI), (б) первинний bootstrap як історичний запис.
> Поточний стан spike → `SPIKE-STATUS.md`. Проєкт Android Studio: `C:\Users\mail\AndroidStudioProjects\Streif` (пакет `no.streif.spike`).

## Поточний білд/запуск (CLI — НЕ Android Studio «Run ▶»)
Збірка й тест драйвляться через `gradlew` + `adb` (JBR як `JAVA_HOME`), не через кнопку Run:
```
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
gradlew.bat :app:assembleDebug        # збірка APK
gradlew.bat :app:testDebugUnitTest    # юніт-тести матчингу (BuildingStore)
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n no.streif.spike/.MainActivity   # walk-режим (on-demand)
```
- **Режими `MainActivity`:** `walk` (on-demand, реальний/тестовий трекінг) і `perf` (seed PMTiles + `PerfHarness` для рендер-бенчу).
- **Польовий тест + маркування** → `SPIKE2-WALKTEST.md`. **Батарея** → `SPIKE2-BATTERY.md`.
- **Дані будинків — on-demand (D24):** тягнуться зонами на льоту (Runtime Overpass, тест); `buildings.pmtiles` лишився лише як seed для `perf`-режимів.

## Ключові факти збірки (як налаштовано)
- Пакет `no.streif.spike` · Kotlin · Min SDK 24 · Views (не Compose у spike).
- MapLibre: `org.maplibre.gl:android-sdk:13.3.0`.
- PMTiles вантажити `pmtiles://file://` (копія asset→`filesDir`); `pmtiles://asset://` крешить (D21); `.pmtiles`-asset потребує `noCompress`.
- Дозволи: `INTERNET`, `ACCESS_FINE/COARSE_LOCATION`, `FOREGROUND_SERVICE(_LOCATION)`, `POST_NOTIFICATIONS`, `ACTIVITY_RECOGNITION`.

## Якщо щось не так
- **Gradle/AGP** свариться → текст помилки сюди.
- **Порожній/сірий екран у walk** → перевір мобільні дані (on-demand тягне зону з мережі) + дозвіл локації.
- **Базова карта не вантажиться** → дозвіл INTERNET + мережа.

---
<details><summary>Історія: первинний bootstrap v1 (зроблено)</summary>

v1 фарбував усі будинки за типом статично — щоб зняти ризик #1 (рендер на MapLibre Native). Проєкт створено як Empty Views Activity (`no.streif.spike`, Kotlin, Min SDK 24), додано MapLibre 13.3.0 + `INTERNET`, MainActivity з `spike/android-render/MainActivity.kt`, asset-и `style.json` + `buildings.pmtiles`. Результат (Pixel 9): сіра карта Volda з кольоровими будинками — ризик #1 знято (D21). Далі — v2 (двошаровий overlay + симульований GPS + перф-присуд, D22), потім Spike-2 (реальний FGS, edge-матчинг, on-demand).
</details>

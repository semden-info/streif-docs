# Streif — Data Sources (Джерела даних)

> **Статус:** Чернетка v0.2 — 2026-06-21 (узгоджено з `DECISIONS.md` після Фази-0)
> **Спирається на:** `01-product-vision.md`, `03-feature-spec.md`, `05-tech-architecture.md`
> **Призначення:** реєстр джерел даних — ліцензії, атрибуції, доступ/endpoint-и, формати. Технічний пайплайн → `05`; приватність → `07`. Endpoint-и звірені (червень 2026); частина позначена «підтвердити в Geonorge UI / у Kartverket».

> **Скоуп цього документа:** міські джерела (будинки + база) — **детально під MVP**; природа/безпека/хижки — **каркасом** на майбутнє (узгоджено з поетапним виконанням, `01` §4).

---

## 1. Принципи роботи з даними

- **Пріоритет відкритих держданих.** **CC-BY > ODbL** (проста атрибуція замість share-alike — `05` ADR-06).
- **Атрибуція обов'язкова й дослівна.** Кожне джерело має власне формулювання → екран «Джерела/Атрибуція» в застосунку (§9).
- **Відтворюваність.** Пайплайн = версіоновані скрипти + датовані снапшоти, не ручні викачування.
- **Freshness.** Різна періодичність (matrikkel — щодня; turrutebasen/N50 — щотижня; попередження — щодня).
- **Offline-first.** Дані кешуються/бандляться; погода й varsom — кеш із повагою до `Expires` (`05` §1).

## 2. Зведена таблиця

| Джерело | Шар | Ліцензія | Доступ/формат | Статус |
|---|---|---|---|---|
| INSPIRE Buildings Core2d (полігони) | Місто | CC-BY 4.0 ⚠ (метадані неоднозначні) | відкритий WFS (GML) | **MVP** |
| Matrikkelen-Bygningspunkt (тип) | Місто | CC-BY 4.0 | GML/FGDB/PostGIS, WFS | **MVP** |
| `building2osm` (інструмент) | Місто | CC0 (код); дані CC-BY 4.0 | Python | **MVP** |
| Kartverket WMTS `topograatone` (база) | Усі | CC-BY 4.0 | WMTS raster | **MVP** |
| **Runtime Overpass (on-demand)** | Місто | ODbL ⚠ | Overpass API (bbox) | **тест D24** ⚠→CC-BY |
| Turrutebasen | Стежки | CC-BY 4.0 | FGDB/GML/GPX/PostGIS, WMS | каркас |
| høydedata DTM/DOM | Природа | CC-BY 4.0 | GeoTIFF/LAZ, OGC | каркас |
| N50 (Høgdekurver) | Природа | CC-BY 4.0 | GDB/SQL/GML | каркас |
| SSR Stedsnavn | Вершини | CC-BY 4.0 (+db-захист) | REST/WFS/GML | каркас |
| NVE Snøskred/Jord/Flom | **GATE** | NLOD (~CC-BY 3.0 NO) | REST JSON | каркас |
| MET Locationforecast 2.0 | **GATE**/погода | NLOD 2.0 + CC-BY 4.0 | REST JSON | каркас |
| DNT Nasjonal Turbase | Хижки | per-object (verify) | REST JSON (key) | каркас |
| Kartverket Friluftsliv | Хижки/стежки | CC-BY 4.0 | GeoJSON/GML/GPX | каркас |

---

## 3. ★ Будинки (місто — MVP)

Геометрія й тип походять з **двох** джерел, які з'єднує `building2osm`:

**Геометрія — INSPIRE Buildings Core2d** (~4.3 млн footprint-полігонів, з matrikkel).
- UUID `bff47a2e-693d-49f3-987a-e8becce72f4c`; **відкритий WFS** (без авторизації): `wfs.geonorge.no/skwms1/wfs.inspire-bu-core2d` (FeatureType `Building`), GML 3.2.1, запит по bbox.
- ⚠ **Ліцензійна неоднозначність:** формальні INSPIRE-метадані ще тегують «Norge digitalt-лісензію», хоча WFS відкритий, а реліз 2020 й OSM-імпорт трактують дані як CC-BY 4.0. **Підтвердити з Kartverket до публічного релізу** (→ §11). *Не плутати* з обмеженим `wfs.inspire-bu-core2d_limited`.

**Тип — Matrikkelen-Bygningspunkt** (точки з `bygningstype`; **однозначно CC-BY 4.0**).
- UUID `24d7e9d1-87f6-45a0-b38e-3447f8d7f9a1`; per-kommune GML-завантаження (`nedlasting.geonorge.no/.../MatrikkelenBygning/GML/...`); WFS `wfs.matrikkelen-bygningspunkt`; формати FGDB/GML/PostGIS/SOSI; оновлення щодня.
- Коди `bygningstype` — стандарт **NS3457 / SSB Klass 31** (111 enebolig, hytte/fritidsbolig, 671 kirke …).

**З'єднання — `building2osm`** (NKAmapper, код **CC0**; дані на виході — **CC-BY 4.0**).
- Тягне INSPIRE-полігони + Matrikkelen-точки + рівні адрес, робить spatial join (тип→полігон) і мапить `bygningstype → building=*`. ⚠️ **WFS у `building2osm` зараз не віддає полігони** (тех-стек-пас) — тягнути per-kommune файли **прямо з Geonorge**, а з інструмента брати лише `building_types.csv`.
- Виклик для пілота: `python3 building2osm.py 1577` (Volda), `python3 building2osm.py 1520` (Ørsta). *(Kommunenummer валідувати — реформи 2020/2024, → §11.)*

**OSM як bootstrap** — Volda/Ørsta вже 100% полігонів+типів (із тих самих Kartverket-даних), але **ODbL** (share-alike). Лише для швидкого spike, не канонічно.

**★ Доставка — on-demand (`DECISIONS.md` D24).** MVP більше **не** фіксований бандл: застосунок тягне будинки в bbox навколо GPS **на льоту** (`AreaLoader` → локальний кеш). Джерело за інтерфейсом:
- **Тест (зараз) = Runtime Overpass** (`overpass-api.de` та дзеркала; OSM/**ODbL**) — нуль інфри, але флакі (504/429) і share-alike-ліцензія. Прийнятно лише для dogfood.
- **⚠️ Продакшн (обов'язково перед публічним релізом) = pre-hosted CC-BY** (INSPIRE Core2d + Matrikkelen) **на власному CDN** — надійність + масштаб для багатьох юзерів + чиста CC-BY-ліцензія. Тригер: `DECISIONS.md` **D24 / P4**, §11 нижче.
- **NB (приватність):** on-demand надсилає **bbox-координати** (~3 км навколо користувача) до стороннього сервера — новий вихідний потік даних, задокументовано в `07`. Сирий GPS-трек усе одно не залишає пристрій (D14).

**Атрибуція:** `© Kartverket` (CC-BY-джерело); поки тест на Overpass — також `© OpenStreetMap contributors` (ODbL).

## 4. Базова карта

**Kartverket WMTS (raster), шар `topograatone` (сіра)** — `https://cache.kartverket.no/v1/wmts/1.0.0/topograatone/default/webmercator/{z}/{y}/{x}.png` як `raster`-source. Кольоровий `topo` — за потреби.
- Ліцензія **CC-BY 4.0**; атрибуція **«© Kartverket»** + лінк на kartverket.no обов'язкова в UI.
- Технічні ліміти — «вказані для кожного сервісу»; cache — best-effort безкоштовна інфра.
- Vector-база Kartverket `landtopo` — поки `/test/`, без SLA → на потім (`05` ADR-08).

## 5. Висоти / рельєф (каркас)

**høydedata.no** — DTM/DOM (терен/поверхня) + LiDAR. UUID `91bd03b1-...`; DTM1 ATOM-feed; GeoTIFF/LAZ; OGC WCS/WMS/WFS. **CC-BY 4.0**, `© Kartverket`.
- *Caveat:* меншість LiDAR-проєктів обмежені для Norge digitalt — **підтвердити, що Sunnmøre/Møre og Romsdal у відкритому наборі** (→ §11).
- Використання: вибірка DTM у точках вершин SSR → висота; профілі набору для стежок.

**N50 Kartdata (Høgdekurver / горизонталі)** — легша векторна альтернатива для рельєфних ліній; GDB/SQL/GML; **CC-BY 4.0**.

## 6. Стежки — turstier (каркас)

**Turrutebasen** (Nasjonal database for tur- og friluftsruter): fotrute/skiloype/sykkelrute, gradering, довжина. UUID `d1422d17-...`; **WMS підтверджено** (`wms.geonorge.no/skwms1/wms.friluftsruter2`); формати FGDB/GML/GPX/PostGIS/SOSI; оновлення щотижня. **CC-BY 4.0**, `© Kartverket`.
- км/висота — комбінація геометрії стежки + høydedata (§5).
- WFS-endpoint точно не підтверджено → для імпорту брати PostGIS/FGDB bulk (→ §11).

## 7. Вершини / назви / хижки (каркас)

**SSR — Sentralt stedsnavnregister** (назви вершин). UUID `e1c50348-...`; **REST без авторизації**: `ws.geonorge.no/stedsnavn/v1/` (фільтр `navneobjekttype=fjell`); JSON/XML. **CC-BY 4.0 + database protection** — для систематичного використання формулювання «Stadnamn frå SSR © Kartverket».
- REST обмежений 5000 на запит → для повного збору вершин брати WFS/GML bulk.
- Коди вершин поза `fjell` (topp/ås/berg) — перелічити через `/navneobjekttyper` (→ §11).

**DNT-хижки — два шляхи:**
- **Nasjonal Turbase (NTB)** — `api.nasjonalturbase.no` (потрібен **API-key**); найбагатші метадані хижок (обслуговувана/самообслуга, ліжка, координати). **Ліцензія per-object** (не єдина CC-BY) — підтвердити з DNT.
- **Kartverket Friluftsliv** — **відкритий CC-BY 4.0** baseline точок хижок/стежок (бідніші метадані). Рекомендований для каркасу; NTB додає операційні дані, якщо умови підійдуть.

## 8. Безпека — GATE, лише природний шар (каркас)

> Прив'язка: природний шар **не виходить у продакшн без** varsom + yr + disclaimer + SOS (`01` §7, `03` §D). Усе нижче — каркас; на місто-MVP не впливає.

**NVE Snøskredvarsel (лавини)** v6.3.2 — `api01.nve.no/hydrology/forecast/avalanche/...`; JSON/XML; **без ключа**; ключ за **Varsom-регіонами** (varslingsregioner). **NLOD (~CC-BY 3.0 NO).** Атрибуція: **«Varsler fra Snøskredvarslingen i Norge og www.varsom.no»**. **Показувати ПОВНЕ попередження** (рівень + текст), не вирізаний індикатор — вимога умов і безпеки.

**NVE Jordskred + Flom (зсуви/паводки)** — той самий хост; ключ за **kommune/fylke**; є **CAP-feed** (зручно для алертів). NLOD.

**MET Locationforecast 2.0 (погода, yr)** — `api.met.no/weatherapi/locationforecast/2.0/compact?lat=&lon=`; JSON; **NLOD 2.0 + CC-BY 4.0**; **без ключа, але ОБОВ'ЯЗКОВИЙ ідентифікуючий `User-Agent`** (напр. `Streif/0.1 contact@semden.info`) — інакше **403**. Ліміт 20 req/s на застосунок; поважати `Expires`/`If-Modified-Since`; **не скрейпити yr.no — лише api.met.no**. Атрибуція: **«Data from MET Norway»**.

## 9. Ліцензії й атрибуція (зведено)

| Ліцензія | Джерела | Наслідок |
|---|---|---|
| **CC-BY 4.0** | Kartverket (Matrikkelen, база, turrutebasen, høydedata, N50, SSR, Friluftsliv), MET | проста атрибуція |
| **NLOD (~CC-BY 3.0 NO)** | NVE-попередження | атрибуція + повний показ |
| **NLOD 2.0** | MET (поряд із CC-BY) | + ідентифікуючий User-Agent |
| **ODbL** | OSM (лише bootstrap) | share-alike — уникати канонічно |
| **CC0** | код `building2osm` | без вимог (дані все одно CC-BY) |
| **per-object** | DNT NTB | перевіряти кожен об'єкт |

**Екран атрибуції** має містити дослівно: `© Kartverket` · `Data from MET Norway` · `Varsler fra Snøskredvarslingen/Flomvarslingen i Norge og www.varsom.no` · для систематичного SSR — `Stadnamn frå SSR © Kartverket`. **SSR має database-захист** поверх CC-BY.

## 10. Відтворюваність / оновлення

- **Доставка — on-demand (D24):** будинки тягнуться зонами на льоту + локальний кеш (інкрементальна свіжість), не версіонований бандл. Продакшн-джерело (CC-BY на CDN) регенерувати періодично з Geonorge; PMTiles-бандл (CLI: per-kommune Geonorge → `ogr2ogr` → Tippecanoe) лишається лише для seed перф-режимів (`05` §7).
- **Freshness:** matrikkel kommunevis — щодня; turrutebasen/N50 — щотижня; NVE/MET — щодня, кеш із повагою до `Expires`.
- **Регенерація tiles** — періодична; фіксувати версію джерела в білді.

## 11. Відкриті точки

- 🔴 **МІГРАЦІЯ on-demand джерела Overpass → pre-hosted CC-BY CDN** (`DECISIONS.md` D24/P4) — **обов'язкова перед публічним релізом**. Зараз on-demand тягне з Runtime Overpass (ODbL, флакі); продакшн потребує власного CDN з CC-BY (INSPIRE+Matrikkelen) — надійність, масштаб, ліцензія. *Не блокує dogfood; блокує реліз.* Денис: не забути цей перехід.
- ⚠ **Ліцензія footprint-полігонів INSPIRE** — метадані неоднозначні (Norge digitalt vs CC-BY). **Підтвердити з Kartverket до публічного релізу**, або брати геометрію лише з однозначно-CC-BY поставок. *Не блокує dogfood; блокує публічний реліз.*
- ⚠ **Офлайн-копіювання базової карти** — письмово підтвердити з Kartverket (умови згадують спецправа для частини Geovekst-даних) → `DECISIONS.md` P4.
- **Точні Geonorge download/WFS endpoint-и** (turrutebasen, Friluftsliv) — підтвердити через `kartkatalog.geonorge.no` metadata API (HTML JS-рендериться).
- **SSR peak-коди** поза `fjell` (topp/ås/berg) — перелічити через `/navneobjekttyper`.
- **DNT NTB reuse rights** — підтвердити з DNT, або лишитись на open Kartverket Friluftsliv.
- **høydedata** — підтвердити, що LiDAR-проєкти Sunnmøre/M&R у відкритому наборі.
- **Kommunenummer** (1577 Volda / 1520 Ørsta) — валідувати перед хардкодом (`ws.geonorge.no/kommuneinfo`).

---

### Ключові джерела звірки

- **Будинки:** [INSPIRE Buildings Core2d](https://kartkatalog.geonorge.no/metadata/inspire-buildings-core-2d/bff47a2e-693d-49f3-987a-e8becce72f4c) · [Matrikkelen-Bygningspunkt](https://kartkatalog.geonorge.no/metadata/matrikkelen-bygningspunkt/24d7e9d1-87f6-45a0-b38e-3447f8d7f9a1) · [building2osm](https://github.com/NKAmapper/building2osm) · [bygningstype (SSB Klass 31)](https://www.ssb.no/klass/klassifikasjoner/31)
- **База/природа:** [Kartverket terms (CC-BY 4.0)](https://www.kartverket.no/en/api-and-data/terms-of-use) · [Turrutebasen](https://kartkatalog.geonorge.no/metadata/turrutebasen/d1422d17-6d95-4ef1-96ab-8af31744dd63) · [høydedata.no](https://kartkatalog.geonorge.no/metadata/hoeydedatano/91bd03b1-54b5-4393-9fd0-3c927b4bb608) · [SSR Stedsnavn API](https://ws.geonorge.no/stedsnavn/v1/)
- **Безпека/погода/хижки:** [NVE snøskredvarsel](https://api.nve.no/doc/snoeskredvarsel/) · [NVE flomvarsling](https://api.nve.no/doc/flomvarsling/) · [MET Terms of Service](https://api.met.no/doc/TermsOfService) · [Nasjonal Turbase](https://developer.nasjonalturbase.no/) · [Kartverket Friluftsliv](https://www.kartverket.no/en/api-and-data/friluftsliv)

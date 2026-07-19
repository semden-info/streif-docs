# Streif — CC-BY tile pipeline (Варіант 1, D31)

Офлайн-пайплайн: **OSM-геометрія (ODbL) + Matrikkelen-тип (CC-BY)** → статичні тайли `area_{la}_{lo}.geojson`
(сітка 0.02°) на CDN. Замінює тестове runtime-Overpass-джерело (D24) перед релізом.

Комбінований тайл = **ODbL** (share-alike). Атрибуція: **© OpenStreetMap contributors · © Kartverket (Matrikkelen, CC BY 4.0)**.

## Передумови
```
pip install pyproj boto3          # pyproj — репроєкція 25833→4326; boto3 — заливка R2
```

## Флоу (per регіон)

### 1. Matrikkelen-Bygningspunkt (тип + bygningsnummer + точка), per kommune
Прямий Geonorge-URL (Ø→O у назві; order-flow API таймаутить — прямий працює):
```
https://nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/Basisdata_{NR}_{Name}_25833_MatrikkelenBygning_GML.zip
# 1577 Volda, 1520 Orsta. Розпакувати -> *.gml (EPSG:25833, ~11k буд./kommune)
```

### 2. OSM будинки + дороги, per kommune
```
python fetch_osm.py 1577 osm_volda.json      # Overpass area-query по ref=kommune
python fetch_osm.py 1520 osm_orsta.json
```

### 2b. Elveg (NVDB Vegnett Pluss) — офіційна walkable-мережа для D6 (D31)
«Elveg 2.0» тепер розповсюджується як **NVDB Vegnett Pluss** (UUID `97e6a869-8dd4-4379-bf39-f7d7dbf94863`, CC BY 4.0, GML, EPSG:5973≈25833). Завантаження — order-API (POST повертає файл одразу, `ReadyForDownload`):
```
POST https://nedlasting.geonorge.no/api/order
{"email":"...","orderLines":[{"metadataUuid":"97e6a869-8dd4-4379-bf39-f7d7dbf94863",
  "areas":[{"code":"1577","type":"kommune","name":"Volda"}],
  "formats":[{"name":"GML"}],
  "projections":[{"code":"5973","codespace":"http://www.opengis.net/def/crs/EPSG/0/5973"}]}]}
# відповідь.files[0].downloadUrl -> GET -> unzip -> {komm}NVDBVegnettPluss.gml
```
Walkable-фільтр (typeVeg-літерали з ЖИВОГО файлу): pedestrian `fortau/gangveg/gsv/gangfelt/trapp` завжди + `bilveg/kanalveg/rkj` крім vegkategori E/R; виключити `bilferje`. ⚠️ `sti`/`traktorveg` (стежки) в Elveg ще накочуються (2026–2027) → провал recall по неформальних стежках, тому `--osm-bridge` (нижче) або пізніше Turrutebasen.

### 2c. SSB Tettsteder — межі поселень для per-tettsted Coverage-% (P20)
Coverage-% рахується від **поточного tettsted** (міського поселення), а не від комуни (P18 давав завелику area = 22 645 буд. обох комун → «0,7%» абстрактне). Джерело — **SSB Tettsteder** (власник Statistisk sentralbyrå, ліцензія **NLOD** — відкрита, атрибуція; **не** буквально CC-BY, але сумісна). Датасет **НЕ віддається через Geonorge nedlasting** (capabilities 404) — SSB хостить власний WFS:
```
python fetch_tettsteder.py tettsteder.gml           # default рік=2025, bbox=Volda/Ørsta регіон
# WFS https://kart.ssb.no/api/mapserver/v1/wfs/tettsteder, тип ms:tettsted_2025 (щорічний), GML EPSG:4326
```
Кожен tettsted несе стабільний `tett_nr` (SSB tettstednummer) + `tettstedsnavn` + `befolkning_tettsted`. Geometry MultiSurface (без дірок). Атрибуція межі — **© Statistisk sentralbyrå**.

### 3. Join → тайли (Matrikkelen + OSM-геометрія + Elveg-eligibility + Tettsteder → 0.02°)
```
python build_tiles.py OUTDIR REF_LAT [--elveg=e1.gml,e2.gml] [--osm-bridge] [--tettsteder=t.gml] [--region=…] [--kommuner=…] GML1 OSM1 [GML2 OSM2 ...]
# продакшн (Volda+Ørsta, Elveg + OSM-bridge — Варіант B, D31; + Tettsteder P20; + kommune-тег P30):
python build_tiles.py ./tiles 62.15 \
  --elveg=1577NVDBVegnettPluss.gml,1520NVDBVegnettPluss.gml --osm-bridge \
  --tettsteder=tettsteder.gml --region="Volda+Ørsta" \
  --kommuner=1577:Volda,1520:Ørsta \
  volda.gml osm_volda.json  orsta.gml osm_orsta.json
# без --elveg → D6 рахується з OSM-highways (dogfood-фолбек); без --tettsteder → P20-файл не емітиться
# без --kommuner → тег комуни не пишеться, вихід ІДЕНТИЧНИЙ дореформеному (зворотна сумісність)
```
**`--kommuner=КОД:Назва,…` (P30).** Один запис на КОЖНУ пару вхідних файлів, **у тому самому порядку**, що й пари
(вхід і так per-kommune, тож комуна відома з **індексу пари** — ні PIP, ні нових джерел не треба). Кількість записів
має точно збігатися з кількістю пар, інакше `AssertionError`. Мапа `building_id → kommune` будується під час читання
пар; id глобально унікальні (OSM way-id), колізій між комунами немає.

Вихід: `area_{la}_{lo}.geojson` (props: `building_id`=`m<bygningsnummer>`|`w<osmid>`, `type` [6 категорій], `accessible` [D6], **`tettsted_id`** [P20, tett_nr або відсутній=сільське], **`kommune`** [P30, рядок-kommunenummer напр. `"1577"`; відсутній лише якщо невідомо]) + `manifest.json` (P18, per-регіон; **+ блок `byKommune`** [P30] — `{КОД: {name, total, accessible, byType:{кат:{total,accessible}}}}` ПОРЯД із наявними `total`/`accessible`/`byType`, наявні не змінюються) + **`tettsteder.geojson`** (P20: межі + per-tettsted `total`/`accessible`/`byType`; **+ `kommune`/`kommune_name`** [P30] — **мажоритарна** комуна будівель цього поселення, ties → менший код; лише data-backed поселення).
Ключ тайла ЗБІГАЄТЬСЯ з `AreaCache.keyFor` (0.02°) — тайли лягають у наявний on-demand механізм.
⚠️ **Після регенерації Denis має очистити кеш зон на девайсі** (`filesDir/areas`) — старі кешовані тайли без `tettsted_id`/`kommune` інакше лишаться (D24: «раз стягнули — назавжди»).
**A/B-гейт перед перезаливкою:** `elveg_ab.py` — порівнює accessible% Elveg-vs-OSM на Volda, ловить регресію (будинок, доступний лише пішо-стежкою, що OSM ловить, а Elveg — ні).

### 4. Gzip (R2 сам НЕ стискає — передстискаємо; bash-цикл повільний на Windows → Python)
```
python -c "import gzip,glob,os,shutil; os.makedirs('tiles-gz',exist_ok=True); [shutil.copyfileobj(open(f,'rb'),gzip.open('tiles-gz/'+os.path.basename(f),'wb',9)) for f in glob.glob('tiles/area_*.geojson')]"
```

### 5. Заливка на Cloudflare R2
Cloudflare: R2 → Create bucket `streif-tiles` (Location hint WEUR, Standard) → Settings → Public Development URL → Enable.
API-token: Account API Token, Object Read & Write, scope=streif-tiles → Access Key + Secret + Account ID.
```
cp tiles/manifest.json tiles/tettsteder.geojson tiles-gz/   # обидва P18+P20-файли поруч із передстисненими тайлами
R2_ACCOUNT_ID=... R2_ACCESS_KEY=... R2_SECRET_KEY=... \
  python upload_r2.py ./tiles-gz
# area_*.geojson: Content-Encoding: gzip (передстиснені); manifest.json: uncompressed;
# tettsteder.geojson: gzip у коді upload_r2 (виключений з area-glob, щоб не віддати битим)
```

### 5b. `retag_kommune.py` — РАЗОВИЙ міст: перетегувати вже опубліковані тайли (P30)

> ⚠️ **Це не канон.** Канонічний шлях додавання комуни — прапорець `build_tiles.py --kommuner=…`
> (крок 3), де комуна відома з **індексу пари** вхідних файлів. `retag_kommune.py` — **разовий**
> інструмент, лишений у репо як задокументований прецедент; при наступному **повному регені**
> користуватися `--kommuner`, а не ним.

**Навіщо знадобився.** Вхідні GML (Matrikkelen/OSM/Elveg) зникли з тимчасових тек, а перезавантаження
дороге (Elveg — через order-API з поштою) **і дало б інший зріз даних** (OSM живий, Matrikkelen
оновлюється) → розійшлося б із теперішнім продакшном по кількості будівель і `accessible`.
Перетегування натомість бере **самі продакшн-тайли з CDN** і дописує лише `kommune`, зберігаючи
**точну парність** із продакшном: ті самі 22 645 будівель, 19 723 accessible (Elveg-based),
ті самі `building_id` і `tettsted_id`.

**Чим відрізняється від `--kommuner`.** Походження будівлі з готового тайла вже не відновити, тож
комуна визначається **post-hoc — PIP по центроїду кільця** в **офіційних межах Kartverket**
(`ws.geonorge.no/kommuneinfo/v1/kommuner/{nr}/omrade?utkoordsys=4258` — відкритий GET, без ключа,
GeoJSON MultiPolygon у lon/lat; дірки й мультиполігони враховано). Будівлі, що не влучили в жодну
межу (прибережна генералізація), пробуються на **найближчу межу в межах `--tol-m`** (150 м);
не влучили і там → лишаються **без тега** (краще без, ніж хибно).

```
PYTHONIOENCODING=utf-8 \
python retag_kommune.py OUTDIR --cache=./cdn-cache --kommuner=1577:Volda,1520:Ørsta [--tol-m=150]
```
Все мережеве (416 тайлів + `tettsteder.geojson` + межі комун) **кешується на диск** у `--cache` —
повторний запуск сервіси не смикає. Вихід збігається з тим, що чекає `upload_r2.py`:
`area_*.geojson` **передстиснені gzip** (як крок 4), `manifest.json` і `tettsteder.geojson` — **плоскі**.

Дописується рівно те саме, що й у `--kommuner`: `kommune` у кожну будівлю (решта props недоторкана),
блок `byKommune` **поряд** із наявними ключами manifest, `kommune`/`kommune_name` на кожен tettsted
(мажоритарна комуна його будівель, ties → менший код).

**Звірка (виводить сам скрипт; факт прогону 2026-07-19):**
```
byKommune сума total      : 22645 == manifest.total       OK
byKommune сума accessible : 19723 == manifest.accessible  OK
  1577 Volda: 10812/9180 · 1520 Ørsta: 11833/10543
  byType по комунах у сумі == загальний byType (6/6 категорій)  OK
без kommune: 0 · fallback-за-відстанню: 0 · tettsteder з kommune: 5/5
тайли після gzip: 416 файлів, 22645 фіч, битих 0                OK
```
Тобто **жодна** будівля не потребувала допуску 150 м — усі 22 645 впали строго всередину офіційних меж.

### 6. Увімкнути в застосунку
`app/build.gradle.kts` defaultConfig:
```
buildConfigField("boolean", "USE_CDN", "true")
buildConfigField("String", "CDN_BASE_URL", "\"https://pub-<hash>.r2.dev\"")
```
`CdnGeoJsonAreaSource` будує `$CDN_BASE_URL/area_{la}_{lo}.geojson`. `USE_CDN=false` → runtime-Overpass (dogfood).

## bygningstype → 6 категорій Streif (у `build_tiles.py::category`)
| Код | Категорія |
|---|---|
| 161–172 | hytte (fritidsbolig/seter/koie) |
| 181–183, 231–249, 431–449 | outbuilding (garasje/uthus/naust/fjøs/hangar) |
| 671–679 | sacral (kirke/kapell/bedehus) — NB: 66x = культура, не церкви |
| решта 100–199 | housing |
| 300–599, 600–669, 700–899 | public |
| 2xx, 999 | other |

## POI «цікаві місця» — Nature-v1 (D34, points-only)

Куратні точки з **відкритих даних** для «збирай»-механіки (D34; reveal лишається головним). Points-only (стежки-лінії відкладено); курація лін (require-name + алгоритм-гейт + ручна ухвала людини, codex-review).

**Атрибуція POI-шару** (пише сам `build_poi.py` у поле `attribution`): **© OpenStreetMap contributors (ODbL) · © Miljødirektoratet (Naturbase, NLOD 2.0)** — поряд із © Kartverket (Matrikkelen) і © Statistisk sentralbyrå (Tettsteder) з тайлових секцій вище.

### 1. Джерела (fetch-скрипти = сирі дані, без курації)
```
python fetch_poi.py       poi_raw.json     1577 1520   # Overpass: viewpoint/cultural/church/badeplass/hut/shelter/peak
python fetch_trails.py    trails_raw.json  1577 1520   # піша мережа OSM: highway=path|footway|track|steps|pedestrian|
                                                       #   cycleway|residential|living_street|service|unclassified|tertiary
                                                       #   + relation route=hiking (маркований маршрут) — для safety-гейту
python fetch_naturbase.py naturbase.json   1577 1520   # Naturbase «kartlagte friluftslivsområder» (Miljødirektoratet)
python fetch_osm.py 1577 osm_volda.json                # (уже є для тайлів) — потрібні для правила «POI ≠ будинок»
```
**Naturbase** (`fetch_naturbase.py`) — ArcGIS REST `kart.miljodirektoratet.no/.../friluftsliv_kartlagt/MapServer/1/query`, `f=geojson`, **ключ не потрібен**, пагінація по 1000. Ліцензія **NLOD 2.0**, атрибуція **© Miljødirektoratet**. Тягне **всі** закартовані зони комун (**385 områder** для 1577+1520); що з них badeplass — вирішує `build_poi.py`. Це наше джерело **badeplass**: в OSM пляжів із назвами тут практично немає, а Naturbase дає `omraadenavn` + `omraadebeskrivelse` + `omraadeverdi` + стабільний `kartlagtFOID`.

### 2. Курація → `poi.geojson`
```
PYTHONIOENCODING=utf-8 \
python build_poi.py poi.geojson poi_raw.json \
  --tettsteder=tettsteder.gml \
  --safe --trails=trails_raw.json \
  --dedup-buildings=osm_volda.json,osm_orsta.json \
  --naturbase=naturbase.json --allow-unnamed --images \
  --nature-allow=poi_nature_allowlist.txt --block=poi_blocklist.txt \
  --report=poi_candidates.tsv
# ⚠️ PYTHONIOENCODING обов'язковий на Windows (cp1252 ламає вивід) — див. «Пастки»
```
Прапорці (дефолти в дужках):

| Прапорець | Що робить |
|---|---|
| `--safe` + `--trails=` | safety-гейт **природних** POI (D34 ⑧): ≤ `--trail-max` (60 м) до пішої мережі · `sac_scale` ≤ `--sac-max` (2 = T2 mountain_hiking; T3+ = скрембл) · `ele` ≤ `--ele-max` (1000 м) |
| `--dedup-buildings=` | правило **«POI ≠ будинок»**: будинок і так фарбується reveal-механікою (D25) → POI-дубль дав би подвійне розкриття. Викидає POI, якщо його `source_id` = way-id будинку або точка лежить у полігоні будинку (PIP). **Виняток — `hut`/`shelter`** (хижка/gapahuk = ціль походу, не фон) |
| `--allow-unnamed` | viewpoint/shelter/badeplass без `name` → генерична назва (Utsiktspunkt/Gapahuk/Badeplass) + `name_generic:true`. Для peak/church/cultural назва лишається обов'язковою. Генерики дедупляться **лише за відстанню** |
| `--naturbase=` | додає badeplass-кандидатів (полігон → центроїд; площа > 100 000 м² відсікається, щоб центроїд не впав посеред озера) |
| `--dup-m` (50) / `--dup-cross-m` (100) | near-dup у межах одного джерела / між джерелами (центроїд Naturbase і точка OSM того самого пляжу природно розходяться) |
| `--report=file.tsv` | таблиця природних кандидатів (`trail_m`, `sac`, `on_route`, `ele`, `auto_ok`, `why`) — **для людської ухвали** (D34 ⑦: гібрид алгоритм+людина) |
| `--nature-allow=` | фінальний список природних POI, ухвалений людиною (лише ці `source_id`); перекриває авто-гейт |
| `--allow=` / `--block=` | глобальний tight-allowlist / блоклист за `source_id` |
| `--city-only` | тест-режим: лише міські POI (у tettsted), без гір |
| `--images` | фото → Wikimedia Commons (`image` + `image_credit` + `image_wikidata`). **Два шляхи:** (1) OSM-тег `wikidata` → claim P18 (або тег `image`); (2) **геопошук** Wikidata за координатами (`wikibase:around`) для POI, яким (1) фото не дав |
| `--no-images-geo` | лишити тільки шлях (1) — стара поведінка `--images` (без мережевих запитів до WDQS) |
| `--geo-radius` (0.5) | радіус геопошуку, км |

Провенанс per-feature: `poi_id`, `type`, `name`, `source`, `source_id`, `license`, `city`, `fetched` (+ `trail_m`/`sac`/`ele` у safe-режимі, `verdi` для Naturbase, `name_generic`, `image`, `image_wikidata`).

#### Геопошук фото (шлях 2) — чому такі вузькі критерії
Після правила «POI ≠ будинок» церкви (носії тега `wikidata`) пішли з POI-шару → на 70 POI лишився **1** тег `wikidata`, тобто шлях (1) на природних POI майже не працює. Геопошук це частково компенсує, але **легко чіпляє фото сусіднього об'єкта**. Живою розвідкою по 70 POI зафіксовано:

| Кандидат | Чому НЕ беремо |
|---|---|
| `Klovetinden` → `Masdalskloven` (fjell, **39 м**) | інший об'єкт → «мала відстань + сумісний тип» БЕЗ звіряння назви дає хибне фото |
| `Straumshamn, badeplass` → `Straumshamn` (**назва збігається**) | її P18 = фото **кірхи** → самого збігу назви теж не досить |
| радіус 2,5 км замість 0,5 | **жодного** нового правильного збігу, лише шум |

Тому: **іменований POI** — нормалізована назва == label сутності **І** тип `P31` (з підкласами `P279*`) сумісний з категорією; **генерична назва** (Utsiktspunkt/Gapahuk/Badeplass — звіряти нічого) — лише ≤150 м **І** сумісний тип. Сумнівно → **без фото**. Запити батчаться (`VALUES`, 10 центрів на запит), retry на 429/503; WDQS недоступний → тихо без фото. ⚠️ **описовий User-Agent обов'язковий** (WDQS і Commons інакше 403).
**Реальний вихід на Volda+Ørsta: 3/70 з фото** (тег 1 + геопошук 2: Helgehornet, Rotsethornet). Мало — бо тутешні вершини просто не мають Wikidata-сутностей із P18; це стеля даних, а не критеріїв.

### 3. Актуальний результат (Volda+Ørsta)
**70 POI** — peak 26 · badeplass 15 · viewpoint 14 · shelter 7 · cultural 6 · hut 2; **7 міських / 63 природних**.
- Правило «POI ≠ будинок» викинуло **14** (13 церков лишаються на карті **фіолетовими будинками** — розкриваються reveal-механікою, не «збиранням»).
- Safety-гейт відсіяв **206** природних кандидатів (переважно вершини > 1000 м або `sac` ≥ T3).

### ⚠️ Пастки
- **Windows-консоль cp1252** ламає друк українського/норвезького виводу → запускати з `PYTHONIOENCODING=utf-8`.
- **Nasjonal Turbase (DNT API) — МЕРТВИЙ:** `api.nasjonalturbase.no` → 404, дев-портал не існує, сам DNT пише, що відкритий доступ закрито. Джерело **хижок** = OSM (3 об'єкти в Volda/Ørsta), пізніше — Kartverket SSR.
- **Turrutebasen** (CC BY 4.0, uuid `d1422d17-6d95-4ef1-96ab-8af31744dd63`) — це джерело для **СТЕЖОК** (лінія-reveal, ще не збудовано); як джерело хижок марне (1 хижка на весь Sunnmøre).
- Повний safety-gate для природних POI у проді (varsom/yr/SOS) — **реліз-гейт** (D34), не тест-гейт; на тесті пускаємо лише авто-безпечне + ухвалене людиною.

## Продакшн-TODO (D31)
- **Eligibility → Elveg ✅ ЗРОБЛЕНО (Варіант B: Elveg + OSM-bridge).** Тайли-`accessible` рахуються з Kartverket NVDB Vegnett Pluss + OSM-footpath-bridge (нуль recall-регресії). ⚠️ **Pipeline-vs-runtime розбіжність:** offline-тайли на CDN несуть Elveg-eligibility, але **runtime on-demand (D24, USE_CDN=false / Overpass) на девайсі й далі рахує accessible з OSM-highways** — Elveg там немає. Повне вирівнювання — коли Elveg-мережа теж поїде pre-hosted. Прибрати OSM-bridge, коли (а) геометрія → CC-BY (FKB) І (б) Elveg домігрує `sti`/`traktorveg` (~2027), або додати Turrutebasen (природний шар).
- **Custom domain** `tiles.streif.no` перед першим зовнішнім тестером (r2.dev — dev-only, rate-limited) → потім вимкнути r2.dev + Smart Tiered Cache.
- **FKB-геометрія** через публічного партнера (kommune/fylkeskommune/Høgskulen) — апгрейд без зміни архітектури (Matrikkelen-номер як стабільний id). Див. `docs/partner-outreach.md`.
- **Overpass-era розкриття** — одноразово стерти (dogfood; `source` у Room розрізняє osm/matrikkelen).

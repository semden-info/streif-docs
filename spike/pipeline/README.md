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
python build_tiles.py OUTDIR REF_LAT [--elveg=e1.gml,e2.gml] [--osm-bridge] [--tettsteder=t.gml] [--region=…]
                                     [--kommuner=… | --pairs=list.txt] [--simplify-m=15] GML1 OSM1 [GML2 OSM2 ...]
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

**`--pairs=list.txt` — масштаб фюльке/країни.** 27 комун MR = 54 позиційні аргументи + довжелезний `--kommuner`;
замість цього — файл, по рядку на комуну. Позиційний виклик і `--kommuner` **лишаються робочими** (звірено: вихід
байт-у-байт однаковий); `--pairs` із ними взаємовиключний (падає з поясненням).
```
# gen/pairs_mr.txt — KOD:Назва:matrikkelen.gml:osm.json[:elveg.gml]
# `#` — коментар (і хвостовий теж), порожні рядки пропускаються
1577:Volda:volda.gml:osm_volda.json:1577NVDBVegnettPluss.gml
1520:Ørsta:orsta.gml:osm_orsta.json:1520NVDBVegnettPluss.gml
1508|Ålesund|C:\data\1508.gml|C:\data\osm_1508.json     # `|` — коли шляхи абсолютні
```
* Роздільник — `:`, але **не той, за яким іде `/` або `\`**, тож `C:\data\volda.gml` не ріжеться на диску.
  Якщо в рядку є `|`, роздільником стає **тільки** `|` (мішати в одному рядку не можна).
* П'яте поле (Elveg) необов'язкове; воно **доповнює** `--elveg=`, не замінює.
* Відносні шляхи шукаються спершу від cwd, потім від каталогу самого списку.

**`--simplify-m=15` (деф.) — спрощення кілець `tettsteder.geojson`.** Застосунок качає цей файл **цілком**, а SSB
дає кільця з кроком вершин **2,6 м** (растрова «сходинка»); на MR це 677 тис. вершин = **13,4 МБ**. Douglas-Peucker
15 м → **0,4 МБ** (2,6% вершин), і кордон, який P20 малює **лінією**, візуально той самий: у поселень >1 км² площа
змінюється на **0,4-1,0%**. Спрощується **тільки вихідна геометрія** — тег `tettsted_id` рахується по **точних**
кільцях, тож приписування будівель не зачіпається (звірено: 0 різниць на 229 500 будівлях). Для дрібних полігонів
eps автоматично обмежується 1/20 їх розміру, щоб клаптик 100×100 м не «розчинився». `--simplify-m=0` — вимкнути.

Вихід: `area_{la}_{lo}.geojson` (props: `building_id`=`m<bygningsnummer>`|`w<osmid>`, `type` [6 категорій], `accessible` [D6], **`tettsted_id`** [P20, tett_nr або відсутній=сільське], **`kommune`** [P30, рядок-kommunenummer напр. `"1577"`; відсутній лише якщо невідомо], **`bt`** [сирий bygningstype, ціле напр. `183`; **відсутній, якщо нема матчу на Matrikkelen** — див. нижче]) + `manifest.json` (P18, per-регіон; **+ блок `byKommune`** [P30] — `{КОД: {name, total, accessible, byType:{кат:{total,accessible}}, byBygningstype, bygningstypeUnknown}}` ПОРЯД із наявними `total`/`accessible`/`byType`, наявні не змінюються) + **`tettsteder.geojson`** (P20: межі + per-tettsted `total`/`accessible`/`byType`/`byBygningstype`/`bygningstypeUnknown`; **+ `kommune`/`kommune_name`** [P30] — **мажоритарна** комуна будівель цього поселення, ties → менший код; лише data-backed поселення).
Ключ тайла ЗБІГАЄТЬСЯ з `AreaCache.keyFor` (0.02°) — тайли лягають у наявний on-demand механізм.
⚠️ **Після регенерації Denis має очистити кеш зон на девайсі** (`filesDir/areas`) — старі кешовані тайли без `tettsted_id`/`kommune` інакше лишаться (D24: «раз стягнули — назавжди»).
**A/B-гейт перед перезаливкою:** `elveg_ab.py` — порівнює accessible% Elveg-vs-OSM на Volda, ловить регресію (будинок, доступний лише пішо-стежкою, що OSM ловить, а Elveg — ні).

### 4. Gzip (R2 сам НЕ стискає — передстискаємо; bash-цикл повільний на Windows → Python)
```
python -c "import gzip,glob,os,shutil; os.makedirs('tiles-gz',exist_ok=True); [shutil.copyfileobj(open(f,'rb'),gzip.GzipFile('tiles-gz/'+os.path.basename(f),'wb',9,mtime=0)) for f in glob.glob('tiles/area_*.geojson')]"
```
⚠️ **`mtime=0` обов'язковий.** Без нього gzip пише поточний час у заголовок, байти щоразу інакші —
і пропуск незмінених у `upload_r2.py` (звірка ETag) не спрацьовує: усе заливається наново.

⚠️ **Проба детермінізму в `gzip_tiles.py` хибно-негативна** (знайдено 2026-07-20, дефект самої проби,
не виходу). Вона перестискає файл у `BytesIO` і звіряє байти з файлом на диску — але `GzipFile` пише в
заголовок **FNAME** лише коли має імʼя файлу: у файловому варіанті прапорець `8`, у `BytesIO` — `0`,
тож байти НІКОЛИ не збігаються і проба завжди друкує «⚠ РОЗБІЖНІСТЬ». Справжній детермінізм перевірено
інакше — перестисненням у файл із **тим самим імʼям**: 200/200 тайлів байт-у-байт і в `tiles`, і в
`tiles_v2`. Пропуск за ETag справний; проба потребує однорядкової правки (писати пробу теж у файл).

### 5. Заливка на Cloudflare R2
Cloudflare: R2 → Create bucket `streif-tiles` (Location hint WEUR, Standard) → Settings → Public Development URL → Enable.
API-token: Account API Token, Object Read & Write, scope=streif-tiles → Access Key + Secret + Account ID.
```
cp tiles/manifest.json tiles/tettsteder.geojson tiles-gz/   # обидва P18+P20-файли поруч із передстисненими тайлами
R2_ACCOUNT_ID=... R2_ACCESS_KEY=... R2_SECRET_KEY=... \
  python upload_r2.py ./tiles-gz [--workers=12] [--force] [--dry-run] [--verify=KEY]
# area_*.geojson: Content-Encoding: gzip (передстиснені); manifest.json: uncompressed;
# tettsteder.geojson + poi.geojson: gzip у коді upload_r2 (виключені з area-glob, щоб не віддати битими)
```
**Паралельно + пропуск незмінених.** Один прохід `list_objects_v2` збирає ETag усіх наявних об'єктів;
далі кожен файл заливається лише якщо його MD5 ≠ ETag. Заливка — `ThreadPoolExecutor` (свій boto3-клієнт
на потік). На 418 об'єктах із латентністю 150 мс: **послідовно 63 с → 5,4 с при `--workers=12` (x11,8)**;
екстраполяція на 3400 тайлів фюльке — **~20 хв → ~1 хв**, а повторний прогін після дрібної правки
заливає лише змінене (звірено на фейковому S3: змінили 1 тайл → `put=1`, решта 417 пропущені).

| Прапорець | Що робить |
|---|---|
| `--workers=N` (12) | паралельні заливки. 24 ще прискорює, 32+ ловить `SlowDown` від R2 |
| `--force` | залити все, не читаючи інвентар бакета |
| `--dry-run` | показати, що змінилось, нічого не заливаючи (креденшли все одно потрібні — читаємо перелік) |
| `--verify=KEY` | HEAD цього ключа наприкінці (деф. — перший area-тайл прогону, а не захардкожений) |

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

## Масштаб ФЮЛЬКЕ (Møre og Romsdal, 27 комун) — репетиція перед національним

**27 комун fylke 15:** 1505 Kristiansund · 1506 Molde · 1508 Ålesund · 1511 Vanylven · 1514 Sande ·
1515 Herøy · 1516 Ulstein · 1517 Hareid · 1520 Ørsta · 1525 Stranda · 1528 Sykkylven · 1531 Sula ·
1532 Giske · 1535 Vestnes · 1539 Rauma · 1547 Aukra · 1554 Averøy · 1557 Gjemnes · 1560 Tingvoll ·
1563 Sunndal · 1566 Surnadal · 1573 Smøla · 1576 Aure · 1577 Volda · 1578 Fjord · 1579 Hustadvika ·
1580 Haram.

**Звідки брати дані на 27 комун** (перевірено живими запитами 2026-07-19):

| Джерело | Як | Пастка |
|---|---|---|
| Matrikkelen | прямий per-kommune URL працює для всіх 27 (Ø→O, Å→A, пробіл→`_`); разом 33,7 МБ | **Fylke-файл НЕ брати** — усередині один злитий GML без поділу по комунах. Надійніше спарсити відкритий лістинг `nedlasting.geonorge.no/geonorge/Basisdata/MatrikkelenBygning/GML/` і зіставити за `_{kommunenr}_`, ніж вгадувати транслітерацію |
| Elveg (NVDB Vegnett Pluss) | **пошта НЕ потрібна** (§2b застарів): відкритий каталог `nedlasting.geonorge.no/geonorge/Samferdsel/NVDB-VegnettPluss/GML/`, файл `Samferdsel_15_More_og_Romsdal_5973_NVDB-VegnettPluss_GML.zip` (68 МБ) містить **рівно 27** записів `{kommunenr}NVDBVegnettPluss.gml` — уже per-kommune | — |
| OSM | Geofabrik `europe/norway/vestlandet-latest.osm.pbf` (256 МБ) покриває всі 27 комун MR | Geofabrik віддає **soft-404** (HTTP 200 + ~9,6 КБ HTML) на неіснуючі імена — перевіряти **за розміром**. Окремого MR-екстракту немає. Overpass на 27 комун ненадійний (Ålesund: 504 на overpass-api.de) |
| SSB Tettsteder | той самий WFS, bbox на все фюльке → 105 поселень / 424 полігони / 677 тис. вершин | — |

**Заміряно на синтетиці масштабу фюльке** (229 500 будівель у справжніх межах поселень MR, 27 «комун»,
Python 3.14, Windows): **123,7 с → 36,6 с**, пік RSS **0,80 ГБ**, 2362 тайли (61 МБ до gzip).
Пофічний diff старого й нового виходу на однаковому вході: `geometry` **0** різниць, `type` **0**,
`tettsted_id` **0**, `kommune` **0**, `accessible` — **5 із 229 500** (0,002%, свідома корекція, нижче).

**Що саме прискорилось.** Приписування tettsted (`locate_tettsted`) було лінійним скан­уванням усіх
поселень із неіндексованим PIP по кільцю на 8-32 тис. вершин: **0,69-0,92 мс на будівлю** (заміряно на
22 645 продакшн-центроїдах) = 2,6-3,5 хв на фюльке і під годину на країні. Тепер грід-індекс полігонів
(`tett_grid`, клітинка 0,02°) + **смуговий індекс ребер** (`band_index`, смуга `TBAND`=0,0002°≈22 м,
у смугах лежать **індекси** ребер у `array('i')`, а не копії координат — інакше на нац.масштабі індекс
з'їв би гігабайти): **8,0-8,8 мкс на будівлю, x78-x88**, RAM індексу +5,4 МБ на всі 105 поселень MR.
Ребро в смугах орієнтоване так само, як у старому `pip()`, і тестується тим самим виразом → результат
**побітово той самий** (0 розбіжностей на 22 645 продакшн-будівлях і на 229 500 синтетичних).

**⚠️ `accessible` після повного регену трохи зміниться — це виправлення, а не регресія.**
`compute_accessible` більше не бере одну опорну широту на весь регіон: `kLon` рахується **за широтою
будівлі**. Стара схема на фюльке помилялася на **±3,6%** буфера (±1 м із 28), а на національному
діапазоні 58-71°N — **до +43%** (тобто «доступним» ставало те, що за 39 м від дороги). Звірено з
геодезичним еталоном (`pyproj.Geod`): нова реалізація збігається у **всіх** тест-кейсах, стара
помиляється на 6 із 18. Ціна — **5 будівель із 229 500** змінили прапорець (напрямок узгоджений із
широтою: південніше опорної `True→False`, північніше `False→True`).

**Регресійний перегін із `bt` (2026-07-20) — борг із коміту `7422ecb` закрито.** Ті самі 27 пар,
ті самі параметри → `tiles_v2`. Пофічна звірка проти еталонного `tiles` (`verify_bt.py`, усі **236 456**
фіч усіх **4288** тайлів): `geometry` **0** різниць, `building_id`/`type`/`accessible`/`tettsted_id`/`kommune`
— **0 різниць у ЗНАЧЕННЯХ і 0 зниклих ключів**, єдиний новий ключ у фічах — `bt` (226 777 разів).
`manifest`: `region`/`tileDeg`/`attribution`/`total`/`accessible`/`byType`/`tiles[]` (усі 4288 записів) —
**ІДЕНТИЧНІ**; `byKommune` — усі 27 комун ідентичні поле-в-полі (`name`/`total`/`accessible`/`byType`);
нові ключі лише `byBygningstype`+`bygningstypeUnknown`. `tettsteder.geojson`: 87 поселень, геометрія
кордонів **0** різниць, спільні props **0** різниць. Пік RSS **1,75 ГБ** — той самий. Знаменники
сходяться на всіх трьох рівнях (0/27 комун і 0/87 поселень розбіжних).
⚠️ Wall-clock 261 с проти 97 с еталона — це **не** регресія коду: усі проміжні лічильники парсингу
збігаються дообʼєкта, а сповільнення рівномірне по фазах читання GML (холодний файловий кеш ОС —
еталонний прогін ішов одразу після завантаження файлів). Нова робота на фічу — один `dict.get` + інкремент.

## bygningstype → 6 категорій Streif (у `build_tiles.py::category`)
| Код | Категорія |
|---|---|
| 161–172 | hytte (fritidsbolig/seter/koie) |
| 181–183, 231–249, 431–449 | outbuilding (garasje/uthus/naust/fjøs/hangar) |
| 671–679 | sacral (kirke/kapell/bedehus) — NB: 66x = культура, не церкви |
| решта 100–199 | housing |
| 300–599, 600–669, 700–899 | public |
| 2xx, 999 | other |

### Сирий `bygningstype` у тайлі (`bt`) + знаменники + довідник назв

**Принцип:** збирати найдетальніші дані, показувати агреговано. Код `bygningstype` і так читався в
`parse_matrikkelen`, але **викидався** одразу після обчислення 6-категорійного `category()` — стиснення
116 реальних кодів у 6 кошиків незворотне. Тепер код їде в тайл поряд із категорією (`"bt":183`), тож
інше групування, деталізація в картці чи колекційна ціль («усі naust у Volda») не потребуватимуть
перегену. Це **не нові дані** — це припинення втрати наявних.

**Чесна відсутність.** `bt` пишеться **лише** там, де є матч на Matrikkelen (на MR — 95,9%). Для решти
ключа просто **немає**: заглушку («0», «невідомо») не вигадуємо, інакше знаменники колекцій брехали б.
На MR звірено: усі 226 777 зматчених будівель мають код (жодна не лишилась зматченою-без-коду), 9 679
(4,1%) — без ключа взагалі.

**Знаменники.** Без них деталізація в тайлі марна: застосунок знав би «розкрито 3 naust», але не «з 47».
Тому `byBygningstype` = `{"183": {"total": 15203, "accessible": 8866}}` емітиться на **трьох** рівнях —
`manifest` (регіон), `manifest.byKommune[КОД]` (комуна, P31), `tettsteder.geojson` props (поселення, P20) —
плюс окремий чесний лічильник `bygningstypeUnknown` (будівлі без коду). Емітяться **лише коди, що реально
трапились** (не всі 129 кодлиста, жодних нулів). Інваріант перевіряється `assert`-ом у пайплайні:
`сума byBygningstype + bygningstypeUnknown == total`.

**Довідник назв — `bygningstype.json`** (генератор `fetch_bygningstype.py`, 129 кодів, 21 КБ). Показувати
користувачеві «111» не можна, а зашивати назви в Android означало б другу копію кодлиста.
Джерела — обидва офіційні й машиночитні, поле **`src` у кожному рядку** каже, звідки саме назва:

| Джерело | Внесок | Чому саме так |
|---|---|---|
| **SSB KLASS #31** «Standard for bygningstype / Matrikkelen» ([API](https://data.ssb.no/api/klass/v1/classifications/31), `copyrighted=false`) | 126 кодів 3-го рівня + ієрархія (`main` → `group` → код) | база: повніші назви + групування для UI |
| **Geonorge SOSI** `kartdata/bygningstypekode` ([API](https://register.geonorge.no/api/sosi-kodelister/kartdata/bygningstypekode.json)) | доповнення: **956** Turisthytter · **970** Sykehus med akuttmottak · **999** Ukjent bygningstype | KLASS — надмножина SOSI **окрім** цих трьох; **999 нам критичний** (реальний код у Matrikkelen, 454 буд. на MR) |

У 45 кодах назви джерел різняться редакційно (SOSI коротші: «Enebolig m/hybel/sokkelleilighet» проти
KLASS «Enebolig med hybelleilighet, sokkelleilighet o.l.») — беремо KLASS.

**Що показали дані MR** (27 комун, 236 456 будівель): **116 різних кодів** зі 129 кодлиста; кодів **поза**
кодлистом — жодного. Топ: `111` Enebolig 53 568 · `181` Garasje/uthus 50 684 · `241` Hus for dyr 16 972 ·
`161` Fritidsbygning 16 881 · `183` **Naust, båthus, sjøbu 15 203** · `113` Våningshus 10 373.
На комуну — 61-108 кодів (сер. 81). Naust: Volda 730, Ørsta 515.

⚠️ **«other» сирий код НЕ розчиняє.** Очікування було, що смітник на ~2078 обʼєктів у Volda/Ørsta
розкладеться на конкретні коди. Факт: із 2080 «other» там **лише 279 мають код** (219 Annen
industribygning 93 · 999 Ukjent 51 · 212 Verkstedbygning 50 · 211 Fabrikkbygning 46 · 216 vannforsyning 24 ·
214 renseanlegg 15), а **1801 (87%) коду не мають узагалі** — це будівлі **без матчу на Matrikkelen**, які
впали в `other` через OSM-фолбек `osm_classify`. По всьому MR так само: «other» 10 159, з кодом 3 382,
без коду 6 777. **Висновок для дизайну колекцій:** «other» — це переважно проблема **покриття матчингу**,
а не грубого групування; сирий код її не лікує.

**Ціна (заміряно на MR, звірка `verify_bt.py`):** тайли gzip **13,75 → 14,00 МБ (+1,8%)**, разом на
пристрій 13,88 → 14,15 МБ (+2,0%); `bt` коштує 9,00 байта на будівлю до gzip і **1,14 байта після**.
`manifest.json` плоский 227 → 372 КБ (+63,6%), gzip 20,0 → 31,0 КБ; `tettsteder.geojson` плоский
352 → 467 КБ, gzip 108 → 123 КБ (+13,9%). Зростання manifest — це 27 комун × ~81 код × 2 лічильники,
тобто реальний корисний вантаж, а не оверхед формату: компактне кодування `[total, accessible]` замість
`{"total":…,"accessible":…}` економить лише **0,8 КБ gzip** (30,9 → 30,1), бо gzip і так зʼїдає повторювані
ключі. Найбільший важіль на **плоский** розмір — прибрати `indent=1` при записі manifest: 372 → 217 КБ,
що **менше за дореформені 227 КБ** (gzip 29,0 КБ). Свідомо **не** змінено — це змінило б формат для всього
manifest, а рішення за Денисом. ⚠️ На нац.масштабі (357 комун) блок `byBygningstype` дасть ~1,3 МБ
плоского manifest — ще один аргумент за per-region manifests (знахідка №3 фюльке-прогону), не нова проблема.

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

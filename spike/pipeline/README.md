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

### 3. Join → тайли (Matrikkelen + OSM-геометрія + Elveg-eligibility → 0.02°)
```
python build_tiles.py OUTDIR REF_LAT [--elveg=e1.gml,e2.gml] [--osm-bridge] GML1 OSM1 [GML2 OSM2 ...]
# продакшн (Volda+Ørsta, Elveg + OSM-bridge — Варіант B, D31):
python build_tiles.py ./tiles 62.15 \
  --elveg=1577NVDBVegnettPluss.gml,1520NVDBVegnettPluss.gml --osm-bridge \
  volda.gml osm_volda.json  orsta.gml osm_orsta.json
# без --elveg → D6 рахується з OSM-highways (dogfood-фолбек)
```
Вихід: `area_{la}_{lo}.geojson` (props: `building_id`=`m<bygningsnummer>`|`w<osmid>`, `type` [6 категорій], `accessible` [D6]) + `manifest.json`.
Ключ тайла ЗБІГАЄТЬСЯ з `AreaCache.keyFor` (0.02°) — тайли лягають у наявний on-demand механізм.
**A/B-гейт перед перезаливкою:** `elveg_ab.py` — порівнює accessible% Elveg-vs-OSM на Volda, ловить регресію (будинок, доступний лише пішо-стежкою, що OSM ловить, а Elveg — ні).

### 4. Gzip (R2 сам НЕ стискає — передстискаємо; bash-цикл повільний на Windows → Python)
```
python -c "import gzip,glob,os,shutil; os.makedirs('tiles-gz',exist_ok=True); [shutil.copyfileobj(open(f,'rb'),gzip.open('tiles-gz/'+os.path.basename(f),'wb',9)) for f in glob.glob('tiles/area_*.geojson')]"
```

### 5. Заливка на Cloudflare R2
Cloudflare: R2 → Create bucket `streif-tiles` (Location hint WEUR, Standard) → Settings → Public Development URL → Enable.
API-token: Account API Token, Object Read & Write, scope=streif-tiles → Access Key + Secret + Account ID.
```
R2_ACCOUNT_ID=... R2_ACCESS_KEY=... R2_SECRET_KEY=... \
  python upload_r2.py ./tiles-gz
# ставить Content-Type: application/json, Content-Encoding: gzip, Cache-Control
```

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

## Продакшн-TODO (D31)
- **Eligibility → Elveg ✅ ЗРОБЛЕНО (Варіант B: Elveg + OSM-bridge).** Тайли-`accessible` рахуються з Kartverket NVDB Vegnett Pluss + OSM-footpath-bridge (нуль recall-регресії). ⚠️ **Pipeline-vs-runtime розбіжність:** offline-тайли на CDN несуть Elveg-eligibility, але **runtime on-demand (D24, USE_CDN=false / Overpass) на девайсі й далі рахує accessible з OSM-highways** — Elveg там немає. Повне вирівнювання — коли Elveg-мережа теж поїде pre-hosted. Прибрати OSM-bridge, коли (а) геометрія → CC-BY (FKB) І (б) Elveg домігрує `sti`/`traktorveg` (~2027), або додати Turrutebasen (природний шар).
- **Custom domain** `tiles.streif.no` перед першим зовнішнім тестером (r2.dev — dev-only, rate-limited) → потім вимкнути r2.dev + Smart Tiered Cache.
- **FKB-геометрія** через публічного партнера (kommune/fylkeskommune/Høgskulen) — апгрейд без зміни архітектури (Matrikkelen-номер як стабільний id). Див. `docs/partner-outreach.md`.
- **Overpass-era розкриття** — одноразово стерти (dogfood; `source` у Room розрізняє osm/matrikkelen).

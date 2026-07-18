# -*- coding: utf-8 -*-
"""
Build curated POI points for Streif Nature-v1 (D34, points-only, post-codex-review).

IN : OSM POI JSON (fetch_poi.py) [+ optional SSB Tettsteder GML for city/nature tag]
     [+ optional OSM trail network (fetch_trails.py) для safety-gate природних POI]
     [+ optional OSM buildings (fetch_osm.py) для правила «POI ≠ будинок»]
     [+ optional Naturbase GeoJSON (fetch_naturbase.py) — badeplass з офіційних даних]
OUT: poi.geojson — Point FeatureCollection. Кожна фіча:
     poi_id, type (Streif POI-категорія), name, source, source_id, license, city (bool), fetched
     [safe-режим: + trail_m, sac, ele — сигнали досяжності/складності, за якими курували]
     [--allow-unnamed: + name_generic=true, якщо назва згенерована (Utsiktspunkt/Gapahuk/Badeplass)]
     [naturbase: + verdi — мітка цінності Miljødirektoratet (без score)]

Курація (codex: лін, require-name + ручний контроль): категорія-фільтр + name-обов'язковий +
дедуп (source_id + near-dup same name/category ≤50м) + опційні poi_allowlist.txt / poi_blocklist.txt
(source_id-и). Провенанс per-feature (codex MINOR #13). city/нейчур = tettsteder-PIP (реюз build_tiles).

**Правило «POI ≠ будинок» (`--dedup-buildings=osm_volda.json,osm_orsta.json`):** будинок і так
фарбується reveal-механікою (D25) → POI, що Є будинком, дав би подвійне розкриття того самого місця.
Викидаємо POI, якщо (a) його source_id = way-id будинку (церкви як way), або (b) точка лежить
усередині полігона будинку (PIP). **Виняток — `hut`/`shelter`** (хижка/gapahuk = ціль походу, не фон).

**Безіменні POI (`--allow-unnamed`):** viewpoint/shelter/badeplass без `name` — не шум, а реальні
місця (краєвид, gapahuk, пляж) → пускаємо під генеричною норвезькою назвою + `name_generic:true`
(UI/курація це бачать). Для peak/church/cultural назва лишається обов'язковою (без неї — шум).
Генерики дедупляться **лише за відстанню** (той самий тип ≤ `--dup-m`, деф. 50 м), тому два різні
безіменні краєвиди за 500 м один від одного лишаються обидва (verified: найближча пара — 127 м, обидва).

**Safety-allowlist для природних POI (D34 ⑧/(h) — тест = лише безпечні/доступні місця):**
`--safe --trails=trails_raw.json` пропускає природний POI, лише якщо він
  (1) ≤ `--trail-max` м від пішої мережі OSM (досяжний, а не «стіна»),
  (2) шлях біля нього не складніший за `--sac-max` (sac_scale; T3+ = скрембл → ні),
  (3) ele ≤ `--ele-max` (високогір'я — на реліз, з varsom/yr-гейтом).
Це **алгоритм-фільтр**; фінальний список ухвалює людина (D34 ⑦: гібрид) через
`--nature-allow=poi_nature_allowlist.txt` (лише ці природні source_id) / `--block=`.
`--report=file.tsv` друкує таблицю кандидатів із метриками — для ухвали Дениса.

**Фото POI (`--images`) — ДВА шляхи (другий доданий після правила «POI ≠ будинок»):**
  (1) **OSM-тег** `wikidata` → claim P18, або тег `image` напряму (наявна поведінка, не змінена);
  (2) **геопошук Wikidata** (`wikibase:around`) для POI, яким (1) фото не дав — шукаємо сутність
      поруч і беремо її P18. Вмикається тим самим `--images`; вимкнути — `--no-images-geo`.
Причина (2): після правила «POI ≠ будинок» церкви (носії `wikidata`-тега) пішли з шару → на 70 POI
лишився 1 тег `wikidata`, тобто шлях (1) на природних POI майже не працює.

⚠️ **Precision-first** (геопошук легко чіпляє фото СУСІДНЬОГО об'єкта). Живою розвідкою по 70 POI
(Volda/Ørsta) зафіксовано хибні збіги, які «наївні» критерії пропустили б:
  · `Klovetinden` → `Masdalskloven` (fjell, **39 м**) — інший об'єкт, тобто «мала відстань + сумісний
    тип» БЕЗ звіряння назви дає хибне фото. → для іменованих POI відстань-фолбек **не використовуємо**.
  · `Straumshamn, badeplass` → сутність `Straumshamn` (**назва збігається**), але її P18 = фото кірхи. →
    самого збігу назви теж НЕ досить. → **назва І сумісний тип P31** (обидві умови).
  · радіус 2,5 км замість 0,5 не дав ЖОДНОГО нового правильного збігу (лише шум) → радіус тримаємо малим.
Підсумок правил: **іменований POI** — нормалізована назва == назві сутності **І** тип P31 сумісний з
категорією; **генерична назва** (Utsiktspunkt/Gapahuk/Badeplass — звіряти нічого) — лише відстань
≤`GEO_GENERIC_M` **І** сумісний тип. Сумнівно → БЕЗ фото.
Провенанс: `image` (Commons FilePath), `image_credit`, **`image_wikidata`** = Qid-джерело фото
(щоб дотягнути автора/ліцензію per-image — pre-release TODO). WDQS недоступний → тихо без фото.

usage: python build_poi.py OUT.geojson POI_RAW.json [--tettsteder=t.gml] [--safe --trails=trails_raw.json]
       [--dedup-buildings=osm1.json,osm2.json] [--allow-unnamed] [--naturbase=naturbase.json]
       [--nature-allow=f.txt] [--allow=f.txt] [--block=f.txt] [--report=cand.tsv] [--images] [--city-only]
       [--no-images-geo] [--geo-radius=0.5] [--trail-max=60] [--sac-max=2] [--ele-max=1000] [--dup-m=50]
"""
import sys, os, re, json, math, time, datetime, urllib.request, urllib.parse, urllib.error

# --- Streif POI-категорії з OSM-тегів (куратний набір; None = не показуємо) ---
# ⚠️ historic=* шумний: 204 seter/støl (shieling) — сільські ферми, не «цікаві місця».
# Whitelist справді цікавих культурних підтипів (codex #11: звузити курацію).
CULTURAL_HIST = {"monument", "memorial", "ruins", "heritage", "castle", "fort", "manor",
                 "archaeological_site", "church", "chapel", "wayside_shrine", "wayside_cross",
                 "boundary_stone", "cannon", "ship", "aircraft", "locomotive", "tomb", "citywalls"}
def poi_category(t):
    tour = (t.get("tourism") or "").lower(); hist = (t.get("historic") or "").lower()
    nat = (t.get("natural") or "").lower(); am = (t.get("amenity") or "").lower()
    leis = (t.get("leisure") or "").lower(); bld = (t.get("building") or "").lower()
    if tour == "viewpoint": return "viewpoint"
    if tour in ("alpine_hut", "wilderness_hut"): return "hut"
    if am == "shelter": return "shelter"
    if am == "place_of_worship" or bld == "church": return "church"
    if nat == "beach" or leis == "beach_resort": return "badeplass"
    if nat == "peak": return "peak"
    if hist in CULTURAL_HIST or tour == "artwork": return "cultural"   # seter/farm/… → None (шум)
    return None

# Безіменні POI цих типів (--allow-unnamed) → генерична норвезька назва + name_generic:true.
# peak/church/cultural без назви = шум (їх і далі відсіює require-name).
GENERIC_NAME = {"viewpoint": "Utsiktspunkt", "shelter": "Gapahuk", "badeplass": "Badeplass"}

def coords(e):
    if e.get("type") == "node": return e.get("lon"), e.get("lat")
    c = e.get("center") or {}; return c.get("lon"), c.get("lat")

def load_ids(path):
    if not path or not os.path.exists(path): return set()
    return {ln.strip() for ln in open(path, encoding="utf-8") if ln.strip() and not ln.startswith("#")}

CELL = 0.01           # ~1.1 км — грід (стежки + будинки), щоб не сканувати тисячі об'єктів на кожен POI

# --- правило «POI ≠ будинок» (--dedup-buildings): будинок уже фарбується reveal-механікою (D25) ---
BUILDING_KEEP = {"hut", "shelter"}      # хижка/gapahuk — ціль походу, а не фон → лишаємо як POI

def is_shelter_like(t):
    """Чи об'єкт Є хижкою/укриттям ЗА ТЕГАМИ (незалежно від того, яку категорію віддав poi_category).
    Потрібно, бо теги перетинаються: gapahuk з краєвидом = `amenity=shelter` + `tourism=viewpoint`
    → категорія «viewpoint», але правило «POI ≠ будинок» його чіпати не повинне."""
    return ((t.get("amenity") or "").lower() == "shelter"
            or (t.get("tourism") or "").lower() in ("alpine_hut", "wilderness_hut")
            or bool(t.get("shelter_type")))

def parse_buildings(paths):
    """OSM-будинки (fetch_osm.py, `out body`) → (set way-id, грід полігонів) для правила «POI ≠ будинок»."""
    from build_tiles import parse_osm                      # реюз: node-lookup + замикання кільця
    ids, grid, n = set(), {}, 0
    for p in paths:
        for bid, ring, _t in parse_osm(p)[0]:
            xs = [c[0] for c in ring]; ys = [c[1] for c in ring]
            bb = (min(xs), min(ys), max(xs), max(ys))
            ids.add(bid); n += 1
            for cy in range(int(math.floor(bb[1] / CELL)), int(math.floor(bb[3] / CELL)) + 1):
                for cx in range(int(math.floor(bb[0] / CELL)), int(math.floor(bb[2] / CELL)) + 1):
                    grid.setdefault((cx, cy), []).append((bid, ring, bb))
    print(f"  buildings: {n} полігонів у {len(grid)} комірках (правило «POI ≠ будинок»)")
    return ids, grid

def building_at(lon, lat, grid):
    """way-id будинку, всередині якого лежить точка (PIP), або None."""
    from build_tiles import pip
    for bid, ring, bb in grid.get((int(math.floor(lon / CELL)), int(math.floor(lat / CELL))), ()):
        if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and pip(lon, lat, ring):
            return bid
    return None

# --- safety-gate природних POI (--safe): піша мережа OSM → досяжність + складність (D34 ⑧) ---
# sac_scale (OSM): T1 hiking … T6. T3+ = скрембл/експозиція → поза тестом (safety = release-gate, не test-gate,
# але на тесті пускаємо ЛИШЕ безпечно-доступне: рішення Дениса + codex (h)).
SAC_RANK = {"hiking": 1, "mountain_hiking": 2, "demanding_mountain_hiking": 3,
            "alpine_hiking": 4, "demanding_alpine_hiking": 5, "difficult_alpine_hiking": 6}

def parse_trails(path):
    """OSM ways/relations (fetch_trails.py, `out geom`) → грід сегментів: (lon1,lat1,lon2,lat2,sac,route)."""
    j = json.load(open(path, encoding="utf-8"))
    grid = {}
    nseg = 0
    def add_geom(geom, sac, route):
        nonlocal nseg
        pts = [(g["lon"], g["lat"]) for g in geom if "lon" in g and "lat" in g]
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            seg = (x1, y1, x2, y2, sac, route)
            for cy in range(int(math.floor(min(y1, y2) / CELL)), int(math.floor(max(y1, y2) / CELL)) + 1):
                for cx in range(int(math.floor(min(x1, x2) / CELL)), int(math.floor(max(x1, x2) / CELL)) + 1):
                    grid.setdefault((cx, cy), []).append(seg)
            nseg += 1
    for e in j.get("elements", []):
        t = e.get("tags", {})
        if e.get("type") == "way" and e.get("geometry"):
            add_geom(e["geometry"], SAC_RANK.get((t.get("sac_scale") or "").lower(), 0), False)
        elif e.get("type") == "relation" and t.get("route") == "hiking":
            for m in e.get("members", []):
                if m.get("geometry"): add_geom(m["geometry"], 0, True)   # маркований маршрут (T-merka тощо)
    print(f"  trails: {nseg} сегментів у {len(grid)} комірках ({os.path.basename(path)})")
    return grid

def _seg_dist2(px, py, x1, y1, x2, y2, kLon):
    """Квадрат відстані (м²) точки до сегмента в локальній планарній проєкції."""
    ax, ay = (x1 - px) * kLon, (y1 - py) * 111320.0
    bx, by = (x2 - px) * kLon, (y2 - py) * 111320.0
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 <= 1e-9: return ax * ax + ay * ay
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return cx * cx + cy * cy

def trail_signals(lon, lat, grid, radius=250.0):
    """(dist_m до пішої мережі, макс. sac_scale у радіусі, чи є маркований маршрут у радіусі)."""
    kLon = 111320.0 * math.cos(math.radians(lat))
    cx0, cy0 = int(math.floor(lon / CELL)), int(math.floor(lat / CELL))
    best = float("inf"); sac = 0; route = False; r2 = radius * radius
    for cy in (cy0 - 1, cy0, cy0 + 1):
        for cx in (cx0 - 1, cx0, cx0 + 1):
            for (x1, y1, x2, y2, s, rt) in grid.get((cx, cy), ()):
                d2 = _seg_dist2(lon, lat, x1, y1, x2, y2, kLon)
                if d2 < best: best = d2
                if d2 <= r2:
                    if s > sac: sac = s
                    if rt: route = True
    return (math.sqrt(best) if best < float("inf") else float("inf")), sac, route

def parse_ele(t):
    try: return float(str(t.get("ele", "")).replace(",", "."))
    except Exception: return None

# --- Naturbase badeplass (--naturbase): Miljødirektoratet, NLOD 2.0 (© Miljødirektoratet) ---
# Фільтр звірено з ЖИВИМИ даними (385 områder Volda+Ørsta): сирий `omraadetype=Strandsone…` дав би
# 66 зон, з них 11 лососевих річок, 5 småbåthamn, turveg-и — це НЕ пляжі. Precision-first (Денис:
# «краще менше, але точно пляжі») → ключове слово badeplass/sandstrand у назві АБО в описі.
# Площа-кап відсіює великі озера (Rotevatnet 1,4 км², Vatnevatnet 2,1 км²), де «bading» лише згадано
# в описі, а центроїд полігона впав би посеред води.
NB_NAME = re.compile(r"badeplass|badetur|badestrand|sandstrand", re.I)
NB_DESC = re.compile(r"badeplass|badestrand|sandstrand", re.I)
NB_AREA_MAX = 100000.0        # м²
NB_VERDI = {"SvaertViktigFriluftslivsomraade": "Svært viktig",
            "ViktigFriluftslivsomraade": "Viktig",
            "RegistrertFriluftslivsomraade": "Registrert",
            "IkkeVerdisattFriluftslivsomraade": "Ikke verdisatt"}

def _rings(geom):
    """Polygon/MultiPolygon → список зовнішніх кілець [(lon,lat)…] (дірки для центроїда не критичні)."""
    g = geom or {}
    if g.get("type") == "Polygon": return [r for r in g.get("coordinates", [])[:1]]
    if g.get("type") == "MultiPolygon": return [p[0] for p in g.get("coordinates", []) if p]
    return []

def _area_centroid(ring, lat0):
    """(площа м², центроїд) кільця в локальній планарній проєкції."""
    kx = 111320.0 * math.cos(math.radians(lat0)); ky = 110540.0
    A = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0] * kx, ring[i][1] * ky
        x2, y2 = ring[i + 1][0] * kx, ring[i + 1][1] * ky
        cr = x1 * y2 - x2 * y1
        A += cr; cx += (x1 + x2) * cr; cy += (y1 + y2) * cr
    if abs(A) < 1e-9: return 0.0, (ring[0][0], ring[0][1])
    A *= 0.5
    return abs(A), (cx / (6 * A) / kx, cy / (6 * A) / ky)

def parse_naturbase(path, area_max=NB_AREA_MAX):
    """Naturbase-полігони → badeplass-кандидати (полігон → центроїд; провенанс NLOD 2.0)."""
    from build_tiles import pip
    j = json.load(open(path, encoding="utf-8"))
    out = []; nskip_big = 0
    for f in j.get("features", []):
        p = f.get("properties", {})
        name = (p.get("omraadenavn") or "").strip()
        desc = (p.get("omraadebeskrivelse") or "").strip()
        if not (NB_NAME.search(name) or NB_DESC.search(desc)): continue
        rs = _rings(f.get("geometry"))
        if not rs: continue
        lat0 = rs[0][0][1]
        ring = max(rs, key=lambda r: _area_centroid(r, lat0)[0])       # найбільше кільце
        area, (lon, lat) = _area_centroid(ring, lat0)
        if area > area_max:                    # велике озеро/фіорд-зона: центроїд — посеред води
            nskip_big += 1; continue
        if not pip(lon, lat, ring):            # увігнутий полігон → центроїд поза ним: беремо найближчу вершину
            lon, lat = min(ring, key=lambda c: (c[0] - lon) ** 2 + (c[1] - lat) ** 2)
        sid = (p.get("kartlagtFOID") or "").strip()
        if not sid: continue                   # без стабільного id провенанс неповний → пропускаємо
        out.append({"cat": "badeplass", "name": name or GENERIC_NAME["badeplass"],
                    "generic": not name, "lon": lon, "lat": lat,
                    "sid": sid, "source": "naturbase", "license": "NLOD 2.0",
                    "wd": None, "img": None, "ele": None,
                    "extra": {"verdi": NB_VERDI.get(p.get("omraadeverdi"), p.get("omraadeverdi"))}})
    print(f"  naturbase: {len(out)} badeplass ({nskip_big} відсіяно за площею >{area_max:.0f} м²) "
          f"({os.path.basename(path)}, © Miljødirektoratet, NLOD 2.0)")
    return out

# --- фото POI (--images): Wikidata P18 / OSM image-тег → URL картинки з Wikimedia Commons (© Commons) ---
# ⚠️ ОПИСОВИЙ User-Agent обов'язковий: і Commons, і WDQS віддають 403 на дефолтний UA urllib.
UA = "Streif-pipeline/0.1 (contact@semden.info)"

def commons_filepath(fn):
    fn = fn.strip()
    if fn.lower().startswith("file:"): fn = fn[5:]
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(fn.replace(" ", "_")) + "?width=640"

def resolve_wikidata_images(ids):
    """batch Wikidata wbgetentities → {Qid: commons_url} за claim P18 (image)."""
    out = {}; ids = list(ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&ids="
               + "|".join(chunk) + "&props=claims&format=json")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            j = json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as ex:
            print(f"  wikidata fail: {ex}"); continue
        for qid, ent in j.get("entities", {}).items():
            p18 = ent.get("claims", {}).get("P18")
            if p18:
                try: out[qid] = commons_filepath(p18[0]["mainsnak"]["datavalue"]["value"])
                except Exception: pass
    return out

# --- шлях (2): геопошук Wikidata за координатами (для POI без wikidata-тега) ---
GEO_RADIUS_KM = 0.5      # радіус wikibase:around; 2,5 км живою розвідкою дав лише шум (див. docstring)
GEO_GENERIC_M = 150.0    # генерична назва (звіряти нічого) → лише дуже близька + типово сумісна сутність
GEO_BATCH = 10           # центрів на один SPARQL-запит (VALUES) — НЕ запит на POI
GEO_PAUSE = 1.5          # с між запитами — поважаємо rate limit WDQS

# Сумісність P31 сутності з нашою POI-категорією (перевіряємо з підкласами: P31/P279*).
# Саме цей гейт відкидає «Straumshamn» (busetnad, фото кірхи) для badeplass — при збігу назви.
GEO_TYPE_OK = {
    "peak":      {"Q8502", "Q54050", "Q207326"},                       # fjell / haug / topp
    "viewpoint": {"Q8502", "Q54050", "Q207326", "Q6017969", "Q1440300", "Q34763", "Q34038"},
    "badeplass": {"Q40080", "Q23397", "Q39594", "Q45776"},             # strand/innsjø/vik/fjord (NB: elv — ні)
    "hut":       {"Q182676", "Q17087359"},                             # fjellhytte / villmarkshytte
    "shelter":   {"Q182676", "Q17087359", "Q1797440"},                 # + gapahuk (lean-to)
    "cultural":  {"Q4989906", "Q179700", "Q860861", "Q5003624", "Q575759", "Q839954",
                  "Q17715832", "Q1785071", "Q16970", "Q33506", "Q12518", "Q35112127"},
}

def wdqs(query, tries=3):
    """SPARQL до WDQS → json або None. Retry+пауза на 429/503; будь-який збій = тихо без фото."""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            return json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 503) and a < tries - 1:
                wait = 5 * (a + 1)
                print(f"  wdqs {ex.code} → пауза {wait}с"); time.sleep(wait); continue
            print(f"  wdqs fail: {ex}"); return None
        except Exception as ex:
            if a < tries - 1: time.sleep(5 * (a + 1)); continue
            print(f"  wdqs fail: {ex}"); return None
    return None

_ART = ("ene", "ane", "et", "en", "a")        # норвезькі суфікси означеності: Helgehornet ≡ Helgehorn

def _name_keys(s):
    """Нормалізовані ключі назви (для звіряння POI ↔ label сутності)."""
    s = (s or "").lower().replace("ø", "o").replace("æ", "a").replace("å", "a")
    if not s.strip(): return set()
    # ⚠️ відрізаємо ХВОСТИ до зняття пунктуації — інакше кома вже стерта й split нічого не робить
    cuts = {s,
            re.split(r"\s*,", s)[0],                        # «Straumshamn, badeplass» → «straumshamn»
            re.sub(r"\s+i\s+\S+$", "", s)}                  # «Helgehornet i Volda» → «helgehornet»
    keys = set()
    for c in cuts:
        c = re.sub(r"[^0-9a-zà-ÿ]+", " ", c).strip()
        if not c or re.fullmatch(r"q\d+", c): continue      # WDQS віддає Qid, коли label немає
        keys.add(c)
        for suf in _ART:                                    # знімаємо означеність лише з довгих основ
            if c.endswith(suf) and len(c) - len(suf) >= 4:
                keys.add(c[: -len(suf)]); break
    return keys

def names_match(poi_name, label):
    a, b = _name_keys(poi_name), _name_keys(label)
    return bool(a and b and (a & b))

def resolve_type_roots(qids):
    """{P31-Qid: set(коренів із GEO_TYPE_OK, до яких він зводиться через P279*)}."""
    roots = sorted({r for s in GEO_TYPE_OK.values() for r in s})
    out = {}; qids = sorted(qids)
    for i in range(0, len(qids), 60):
        chunk = qids[i:i + 60]
        q = ("SELECT ?t ?root WHERE { VALUES ?t { %s } VALUES ?root { %s } ?t wdt:P279* ?root. }"
             % (" ".join("wd:" + x for x in chunk), " ".join("wd:" + x for x in roots)))
        j = wdqs(q)
        if not j: continue
        for b in j.get("results", {}).get("bindings", []):
            out.setdefault(b["t"]["value"].rsplit("/", 1)[-1], set()).add(b["root"]["value"].rsplit("/", 1)[-1])
        time.sleep(GEO_PAUSE)
    return out

def geosearch_images(targets, radius_km=GEO_RADIUS_KM):
    """[(idx, lon, lat, cat, name, generic)] → {idx: (commons_url, Qid)} за геопошуком + звірянням."""
    hits = {}          # idx → [(dist_m, qid, label, {p31…})]
    for i in range(0, len(targets), GEO_BATCH):
        chunk = targets[i:i + GEO_BATCH]
        vals = " ".join('"Point(%s %s)"^^geo:wktLiteral' % (t[1], t[2]) for t in chunk)
        q = """SELECT ?c ?place ?placeLabel ?img ?dist ?type WHERE {
  VALUES ?c { %s }
  SERVICE wikibase:around { ?place wdt:P625 ?loc. bd:serviceParam wikibase:center ?c.
    bd:serviceParam wikibase:radius "%s". bd:serviceParam wikibase:distance ?dist. }
  ?place wdt:P18 ?img.
  OPTIONAL { ?place wdt:P31 ?type. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "nn,nb,no,en". }
} LIMIT 400""" % (vals, radius_km)
        j = wdqs(q)
        if not j: continue                                   # WDQS лежить → просто без фото
        by_c = {}
        for b in j.get("results", {}).get("bindings", []):
            by_c.setdefault(b["c"]["value"], []).append(b)
        for t in chunk:
            for b in by_c.get("Point(%s %s)" % (t[1], t[2]), []):
                qid = b["place"]["value"].rsplit("/", 1)[-1]
                rec = None
                for h in hits.setdefault(t[0], []):
                    if h[1] == qid: rec = h; break
                if rec is None:
                    rec = [float(b["dist"]["value"]) * 1000.0, qid, b.get("placeLabel", {}).get("value", ""),
                           set(), b["img"]["value"]]
                    hits[t[0]].append(rec)
                if "type" in b: rec[3].add(b["type"]["value"].rsplit("/", 1)[-1])
        time.sleep(GEO_PAUSE)

    type_roots = resolve_type_roots({q for hs in hits.values() for h in hs for q in h[3]})
    out = {}
    for idx, lon, lat, cat, name, generic in targets:
        ok_roots = GEO_TYPE_OK.get(cat)
        if not ok_roots: continue
        for dist, qid, label, p31, img in sorted(hits.get(idx, []), key=lambda h: h[0]):
            if not any(type_roots.get(t, set()) & ok_roots for t in p31): continue   # тип не той → далі
            if generic:
                if dist > GEO_GENERIC_M: continue        # звіряти нічого → лише впритул
            elif not names_match(name, label):
                continue                                  # іменований POI: без збігу назви — НЕ беремо
            out[idx] = (commons_filepath(urllib.parse.unquote(img.rsplit("/", 1)[-1])), qid)
            break
    return out

def main():
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    city_only = "--city-only" in sys.argv    # безпечний тест-режим: лише міські POI (у tettsted), без гір
    do_images = "--images" in sys.argv        # фото з Wikidata/Commons (мережа) → prop "image"
    # --images = тег + геопошук; --no-images-geo лишає стару поведінку (лише OSM-тег wikidata/image)
    do_geo = do_images and "--no-images-geo" not in sys.argv
    safe = "--safe" in sys.argv               # safety-gate природних POI (досяжність+складність+висота)
    allow_unnamed = "--allow-unnamed" in sys.argv   # viewpoint/shelter/badeplass без name → генерична назва
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    out, raw_path = rest[0], rest[1]
    allow = load_ids(args.get("--allow")); block = load_ids(args.get("--block"))
    nature_allow = load_ids(args.get("--nature-allow"))     # людська ухвала (D34 ⑦): лише ці природні POI
    trail_max = float(args.get("--trail-max", 60))          # м до пішої мережі (досяжність)
    sac_max = int(args.get("--sac-max", 2))                 # 2 = mountain_hiking (T2); T3+ = скрембл → ні
    ele_max = float(args.get("--ele-max", 1000))            # м н.р.м. (високогір'я — на реліз із varsom/yr)
    dup_m = float(args.get("--dup-m", 50))                  # радіус near-dup у МЕЖАХ одного джерела
    dup2 = dup_m * dup_m
    # Крос-джерельний радіус ширший: центроїд полігона Naturbase і точка OSM того САМОГО пляжу
    # природно розходяться (verified: Botnasanden ↔ безіменний OSM-пляж = 58 м). Вужчий поріг лишив би
    # обидва = подвійна ціль на одному місці. 100 м безпечно: найближчі РІЗНІ об'єкти одного типу —
    # 89 м (Ivar Aasen/Anders Hovden) і 127 м (два краєвиди), але обидві пари внутрішньо-OSM.
    geo_radius = float(args.get("--geo-radius", GEO_RADIUS_KM))   # км, радіус wikibase:around (--images)
    dupx_m = float(args.get("--dup-cross-m", 100))
    dupx2 = dupx_m * dupx_m

    trails = None
    if args.get("--trails"): trails = parse_trails(args["--trails"])
    if safe and trails is None:
        print("⚠️  --safe без --trails: гейт досяжності не працює → природні POI не пройдуть")

    bld_ids, bld_grid = set(), {}
    if args.get("--dedup-buildings"):
        bld_ids, bld_grid = parse_buildings([p for p in args["--dedup-buildings"].split(",") if p])

    tett = []
    if args.get("--tettsteder"):
        from build_tiles import parse_tettsteder                        # реюз PIP
        tett = parse_tettsteder(args["--tettsteder"])
        print(f"  tettsteder: {len(tett)} поселень (для city/nature-тегу)")

    fetched = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    skipped = {"no_name": 0, "no_cat": 0, "no_coord": 0, "dup": 0, "blocked": 0, "building": 0}
    dropped_buildings = []                     # (cat, name, sid, чому) — логуємо, що саме викинуло правило (1)

    # ---------- 1) кандидати: OSM (fetch_poi.py) ----------
    j = json.load(open(raw_path, encoding="utf-8"))
    cands = []
    for e in j.get("elements", []):
        t = e.get("tags", {})
        cat = poi_category(t)
        if not cat: skipped["no_cat"] += 1; continue
        name = (t.get("name") or "").strip()
        generic = False
        if not name:
            if allow_unnamed and cat in GENERIC_NAME:
                name, generic = GENERIC_NAME[cat], True         # краєвид/gapahuk/пляж без назви — не шум
            else:
                skipped["no_name"] += 1; continue
        lon, lat = coords(e)
        if lon is None or lat is None: skipped["no_coord"] += 1; continue
        sid = f"{e['type'][0]}{e['id']}"              # n123 / w456 / r789
        cands.append({"cat": cat, "name": name, "generic": generic, "lon": lon, "lat": lat,
                      "sid": sid, "source": "osm", "license": "ODbL",
                      "wd": (t.get("wikidata") or "").strip() or None, "img": t.get("image"),
                      "ele": parse_ele(t), "extra": {},
                      # ⚠️ захист від правила «POI ≠ будинок» рахуємо з ТЕГІВ, а не з присвоєної категорії:
                      # об'єкт може бути водночас `amenity=shelter` і `tourism=viewpoint` (gapahuk з краєвидом),
                      # і poi_category віддасть «viewpoint» — тоді перевірка `cat in BUILDING_KEEP` не спрацює
                      # й gapahuk тихо викинуло б як будинок (саме той тип, який правило мало захистити).
                      "keep_bld": is_shelter_like(t)})

    # ---------- 2) кандидати: Naturbase badeplass (--naturbase) ----------
    if args.get("--naturbase"):
        cands += parse_naturbase(args["--naturbase"])

    # ---------- 2b) ручна курація (--allow/--block) — НА ВСІ ДЖЕРЕЛА ----------
    # Фільтри мусять діяти й на Naturbase (D34 ⑦: фінальний список ухвалює людина). Інакше ціле джерело
    # непідконтрольне: поганий badeplass не заблокувати, а --allow дає хибне відчуття «лише ці POI».
    if block or allow:
        kept = []
        for c in cands:
            if c["sid"] in block: skipped["blocked"] += 1; continue
            if allow and c["sid"] not in allow: continue      # tight-режим: лише allowlist
            kept.append(c)
        cands = kept

    # ---------- 3) правило «POI ≠ будинок» (--dedup-buildings) ----------
    # Будинок і так фарбується reveal-механікою (D25) → POI-дубль дав би подвійне розкриття місця.
    if bld_ids:
        keep = []
        for c in cands:
            if c["cat"] in BUILDING_KEEP or c.get("keep_bld"):         # hut/shelter — ціль, не фон
                keep.append(c); continue
            if c["source"] == "osm" and c["sid"] in bld_ids:           # (a) сам POI = way будинку
                dropped_buildings.append((c["cat"], c["name"], c["sid"], "=building")); continue
            b = building_at(c["lon"], c["lat"], bld_grid)              # (b) точка всередині будинку
            if b:
                dropped_buildings.append((c["cat"], c["name"], c["sid"], "in " + b)); continue
            keep.append(c)
        skipped["building"] = len(dropped_buildings)
        cands = keep
        if dropped_buildings:
            print(f"  «POI ≠ будинок»: викинуто {len(dropped_buildings)} (лишаються будинками на карті):")
            for cat, nm, sid, why in dropped_buildings:
                print(f"      - {cat:9s} {nm} [{sid}] {why}")

    # ---------- 4) дедуп: source_id + near-dup ----------
    # Іменовані — перші, генерики — після: за колізії (той самий тип ≤50 м) виграє named, а не «Utsiktspunkt».
    # Генерики звіряються ТІЛЬКИ за відстанню (назва в них однакова → інакше склеїли б усі краєвиди підряд).
    cands.sort(key=lambda c: c["generic"])           # stable: named (False) → generic (True)
    feats = []; meta = []; seen = set(); near = []   # near: (cat, name, generic, source, lon, lat)
    cand_rows = []                                   # звіт по природних кандидатах (--report)
    kept_by_cat = {}
    for c in cands:
        cat, name, lon, lat, sid = c["cat"], c["name"], c["lon"], c["lat"], c["sid"]
        key = f"{c['source']}:{sid}"
        if key in seen: skipped["dup"] += 1; continue
        kLon = 111320.0 * math.cos(math.radians(lat)); dupd = False
        for c2, n2, g2, s2, x2, y2 in near:
            if c2 != cat: continue
            if not (c["generic"] or g2 or n2 == name): continue   # named-named: лише той самий name
            dx = (lon - x2) * kLon; dy = (lat - y2) * 111320.0
            # той самий об'єкт із РІЗНИХ джерел (OSM-точка vs центроїд полігона Naturbase) — ширший радіус
            lim = dup2 if s2 == c["source"] else dupx2
            if dx * dx + dy * dy < lim: dupd = True; break
        if dupd: skipped["dup"] += 1; continue
        seen.add(key); near.append((cat, name, c["generic"], c["source"], lon, lat))

        city = None
        if tett:
            from build_tiles import locate_tettsted
            city = locate_tettsted(lon, lat, tett) is not None
        if city_only and city is not True:               # safe-тест: пропустити все поза містом (гори тощо)
            skipped["nature"] = skipped.get("nature", 0) + 1
            continue

        # --- safety-gate природних POI (--safe / --nature-allow): D34 ⑧ + (h) ---
        props_safe = {}
        if city is not True and (safe or nature_allow or trails):
            dist, sac, on_route = (float("inf"), 0, False)
            if trails: dist, sac, on_route = trail_signals(lon, lat, trails)
            ele = c["ele"]
            auto_ok = (dist <= trail_max and sac <= sac_max and (ele is None or ele <= ele_max))
            why = []
            if dist > trail_max: why.append(f"trail>{trail_max:.0f}м")
            if sac > sac_max: why.append("sac>T%d" % sac_max)
            if ele is not None and ele > ele_max: why.append(f"ele>{ele_max:.0f}")
            cand_rows.append((cat, name, sid, dist, sac, on_route, ele, auto_ok, ";".join(why) or "ok"))
            approved = (sid in nature_allow) if nature_allow else (auto_ok if safe else True)
            if not approved:
                skipped["nature_unsafe"] = skipped.get("nature_unsafe", 0) + 1
                continue
            props_safe = {"trail_m": round(dist) if dist < 9999 else None,
                          "sac": sac or None, "ele": ele}

        props = {"poi_id": ("osm_" if c["source"] == "osm" else "nb_") + sid,
                 "type": cat, "name": name,
                 "source": c["source"], "source_id": sid, "license": c["license"],
                 "city": city, "fetched": fetched, **c["extra"], **props_safe}
        if c["generic"]: props["name_generic"] = True      # назва згенерована → UI/курація це бачать
        feats.append({"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": props})
        meta.append((c["wd"], c["img"]))                   # для --images
        kept_by_cat[cat] = kept_by_cat.get(cat, 0) + 1

    if args.get("--report") and cand_rows:            # таблиця кандидатів → людська ухвала (D34 ⑦)
        cand_rows.sort(key=lambda c: (not c[7], c[3]))
        with open(args["--report"], "w", encoding="utf-8") as fh:
            fh.write("cat\tname\tsource_id\ttrail_m\tsac\ton_route\tele\tauto_ok\twhy\n")
            for c in cand_rows:
                fh.write("%s\t%s\t%s\t%.0f\t%d\t%s\t%s\t%s\t%s\n" % (
                    c[0], c[1], c[2], min(c[3], 99999), c[4], "route" if c[5] else "",
                    "" if c[6] is None else "%.0f" % c[6], "OK" if c[7] else "no", c[8]))
        print(f"  report: {sum(1 for c in cand_rows if c[7])}/{len(cand_rows)} природних пройшли авто-гейт -> {args['--report']}")

    if do_images:                                            # фото → prop "image" (Wikidata P18 / Commons image-тег)
        # --- шлях (1): OSM-тег wikidata → P18, або тег image напряму (наявна поведінка) ---
        wd_url = resolve_wikidata_images({wd for wd, _ in meta if wd})
        ntag = 0
        for f, (wd, imgtag) in zip(feats, meta):
            url = wd_url.get(wd) if wd else None
            qid = wd if url else None
            if not url and imgtag:
                it = imgtag.strip()
                if not it.lower().startswith("http"): url = commons_filepath(it)      # bare / "File:X"
                elif "wikimedia.org" in it: url = it                                   # commons/upload URL
            if url:
                f["properties"]["image"] = url
                f["properties"]["image_credit"] = "© Wikimedia Commons"
                if qid: f["properties"]["image_wikidata"] = qid                        # провенанс (автор/ліцензія — TODO)
                ntag += 1

        # --- шлях (2): геопошук Wikidata для тих, кому (1) фото не дав ---
        ngeo = 0
        if do_geo:
            targets = [(i, f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1],
                        f["properties"]["type"], f["properties"]["name"],
                        bool(f["properties"].get("name_generic")))
                       for i, f in enumerate(feats) if not f["properties"].get("image")]
            print(f"  images-geo: геопошук Wikidata для {len(targets)} POI без фото "
                  f"(r={geo_radius} км, батч {GEO_BATCH})")
            for idx, (url, qid) in geosearch_images(targets, geo_radius).items():
                p = feats[idx]["properties"]
                p["image"] = url
                p["image_credit"] = "© Wikimedia Commons"
                p["image_wikidata"] = qid
                ngeo += 1
                print(f"      + {p['type']:9s} {p['name']} ← {qid} {url.rsplit('/', 1)[-1][:48]}")
        print(f"  images: {ntag + ngeo}/{len(feats)} POI з фото "
              f"(тег={ntag} геопошук={ngeo}) (© Wikimedia Commons)")

    attribution = "© OpenStreetMap contributors (ODbL)"
    if any(f["properties"]["source"] == "naturbase" for f in feats):
        attribution += " · © Miljødirektoratet (Naturbase, NLOD 2.0)"
    fc = {"type": "FeatureCollection",
          "attribution": attribution,
          "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "features": feats}
    json.dump(fc, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    ncity = sum(1 for f in feats if f["properties"]["city"] is True)
    ngen = sum(1 for f in feats if f["properties"].get("name_generic"))
    nnb = sum(1 for f in feats if f["properties"]["source"] == "naturbase")
    print(f"POI: {len(feats)} kept  {kept_by_cat}")
    print(f"  city={ncity} nature={len(feats)-ncity}  generic-name={ngen}  naturbase={nnb}  skipped={skipped}")
    print(f"  -> {out}")

if __name__ == "__main__":
    main()

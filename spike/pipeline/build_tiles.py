# -*- coding: utf-8 -*-
"""
Streif CC-BY tile pipeline (Variant 1: OSM geometry [ODbL] + Matrikkelen type [CC-BY]).

IN : Matrikkelen-Bygningspunkt GML (per kommune) + OSM buildings+highways JSON (per kommune)
OUT: area_{la}_{lo}.geojson tiles (0.02deg grid, matches AreaCache.keyFor) with props
     building_id (m<bygningsnummer> | w<osmid>), type (Streif 6-cat), accessible (bool D6)
     + manifest.json (з dataVersion — версією СХЕМИ тайлів для кеш-інвалідації на клієнті)
"""
import sys, os, re, json, math, datetime
from array import array
import xml.etree.ElementTree as ET
from pyproj import Transformer

# ---------- ВЕРСІЯ СХЕМИ ТАЙЛІВ (кеш-інвалідація на клієнті) ----------
# Клієнт кешує зони НАЗАВЖДИ (D24 «раз стягнули — назавжди»), тож зміна СКЛАДУ властивостей у тайлі
# лишалась би непоміченою: старий кеш мовчки віддавав би фічі без нового поля, і фіча просто не
# працювала б (так `bt` був порожній, а Coverage по комуні — нуль). `dataVersion` у manifest.json —
# єдиний сигнал «формат змінився, перезавантаж зони».
#
# ⚠️ Це НЕ `generated` (час збірки). Реген тих самих даних не має скидати кеш у всіх користувачів —
# це зайвий трафік на рівному місці. Версія описує ФОРМАТ І СКЛАД ВЛАСТИВОСТЕЙ, а не свіжість.
#
# ПІДІЙМАТИ, коли: додано/перейменовано/прибрано властивість фічі · змінено семантику наявної
# (інша шкала, інший id-простір `building_id`) · змінено сітку тайлів (`TILE`).
# НЕ підіймати, коли: перезібрали ті самі дані · додали/прибрали комуни · змінились лише лічильники
# в manifest · оновився Matrikkelen/OSM без зміни полів.
#
# Історія:
#   1 — building_id, type, accessible (+ tettsted_id P20, kommune P30/P31)
#   2 — + bt (сирий bygningstype, P28)
DATA_VERSION = 2

TILE = 0.02          # must match AreaCache.TILE
BUFFER = 28.0        # D6 accessible buffer (m), must match AreaSource.BUFFER
CELL = 40.0          # grid cell (m) for highway proximity
# lat-смуга індексу ребер tettsted-кільця. 0.005° успадковано з retag_kommune.Poly, але там межі
# КОМУН (~2300 ребер), а тут кільце міста SSB — 8700+ ребер із кроком 2,6 м, тож смуга 555 м усе ще
# містила ~1500 ребер. Заміряно на реальних даних (22 645 продакшн-центроїдів, mr_tettsteder.gml):
#   0.005°=557 м → 127 мкс/виклик · 0.001°=111 м → 33 · 0.0002°=22 м → 7,6 · 0.0001°=11 м → 4,1
# RAM індексу при цьому 85,1 → 86,9 MB (+1,8), результат побітово той самий. Беремо 22 м.
TBAND = 0.0002
TGRID = 0.02         # клітинка грід-індексу полігонів tettsteder (град.) — відсів кандидатів для PIP
SIMPLIFY_M = 15.0    # Douglas-Peucker для ВИХІДНИХ кілець tettsteder.geojson (м); 0 = вимкнено

APP = "{http://skjema.geonorge.no/SOSI/produktspesifikasjon/Matrikkelen-Bygningspunkt/20211101}"
GML = "{http://www.opengis.net/gml/3.2}"
MS = "{http://mapserver.gis.umn.edu/mapserver}"   # SSB Tettsteder WFS feature ns (P20)

# ---------- Matrikkelen bygningstype: СИРИЙ код ----------
# Принцип: збирати найдетальніше, показувати агреговано. `category()` нижче стискає ~116 реальних кодів
# у 6 категорій — незворотно. Тому поряд із категорією ми ТЯГНЕМО В ТАЙЛ сам код (`bt`): якщо колись
# захочемо інше групування, нові колекційні цілі («усі naust у Volda») чи деталізацію в картці —
# дані вже будуть зібрані, а не втрачені. Людські назви кодів — `bygningstype.json` (див. README).
def bt_code(raw):
    """Сирий <bygningstype> → канонічний числовий код (int) або None.
    None = у джерелі коду нема / він не числовий ⇒ властивість `bt` просто НЕ пишеться.
    Заглушки («0», «невідомо») свідомо НЕ вигадуємо: будівля без матчу на Matrikkelen (у MR це 4,1%)
    має лишатись чесно невідомою, інакше знаменники колекцій будуть брехати."""
    s = (raw or "").strip()
    return int(s) if s.isdigit() else None

def bt_bump(d, code, acc):
    """Лічильник {код: {total, accessible}} — спільний для manifest/byKommune/tettsteder.
    Ключ рядковий: JSON-об'єкт усе одно має рядкові ключі, тож так однаково і в Python, і на виході."""
    e = d.setdefault(str(code), {"total": 0, "accessible": 0})
    e["total"] += 1
    if acc: e["accessible"] += 1

# ---------- Matrikkelen bygningstype -> Streif 6 categories ----------
def category(code):
    try: c = int(code)
    except (TypeError, ValueError): return "other"
    if 671 <= c <= 679: return "sacral"       # kirke/kapell/bedehus/religious
    if 161 <= c <= 172: return "hytte"        # fritidsbolig/seter/koie/rorbu
    if 181 <= c <= 183: return "outbuilding"  # garasje/uthus/anneks/naust
    if 231 <= c <= 249: return "outbuilding"  # lager + landbruk (fjos/driftsbygning)
    if 431 <= c <= 449: return "outbuilding"  # garasje/hangar
    if 100 <= c <= 199: return "housing"
    if 300 <= c <= 599: return "public"
    if 600 <= c <= 669: return "public"
    if 700 <= c <= 899: return "public"
    return "other"                            # 2xx industri/energi, 999

# ---------- OSM building=* -> Streif (fallback when no Matrikkelen match), mirrors AreaSource.classify ----------
SACRAL = {"church","chapel","cathedral","mosque","temple","synagogue","shrine","monastery"}
HYTTE = {"cabin","hut","chalet"}
HOUSING = {"house","detached","residential","apartments","terrace","semidetached_house","bungalow","dormitory","houseboat","static_caravan","farm"}
OUTBUILDING = {"garage","garages","shed","barn","farm_auxiliary","carport","greenhouse","industrial","warehouse","service","hangar","stable","sty","cowshed","silo","storage_tank","roof"}
PUBLIC = {"commercial","retail","office","school","kindergarten","university","college","hospital","public","civic","hotel","sports_centre","sports_hall","train_station","transportation","government","fire_station"}
PUBLIC_AM = {"school","kindergarten","university","college","hospital","townhall","library","community_centre","fire_station","police"}
PUBLIC_TOUR = {"hotel","hostel","guest_house"}
HYTTE_TOUR = {"chalet","alpine_hut","wilderness_hut"}
WALKABLE = {"footway","pedestrian","path","steps","residential","living_street","service","unclassified","track","cycleway","tertiary"}

# ---------- Kartverket Elveg 2.0 / NVDB Vegnett Pluss (D31): walkable-мережа для D6 ----------
# typeVeg-літерали — з ЖИВОГО файлу Volda (не зі специфікації, де enkelBilveg/gangOgSykkelveg).
NVDB = "{https://skjema.geonorge.no/SOSI/produktspesifikasjon/NVDBVegnettPluss/1.1}"
ELVEG_PED = {"fortau","gangveg","gsv","gangfelt","trapp"}      # пішохідна інфра — завжди walkable
ELVEG_DRIVE = {"bilveg","kanalveg","rkj"}                      # локальні проїзні — walkable, крім E/R-трас
ELVEG_NONWALK_CAT = {"E","R"}                                  # europaveg / riksveg
ELVEG_FERRY = {"bilferje","passasjerferje"}

def parse_elveg(path):
    """NVDB Vegnett Pluss GML → walkable-лінії (list[polyline] у WGS84) — той самий тип, що OSM highways,
    тож compute_accessible не міняється. CRS файлу EPSG:5973 (гориз.==25833); x,y з 3D-posList → 4326."""
    tr = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    lines = []
    for ev, el in ET.iterparse(path, events=("end",)):
        if el.tag == NVDB + "Veglenke":
            tv = (el.findtext(NVDB + "typeVeg") or "").strip().lower()
            cat = (el.findtext(NVDB + "vegkategori") or "").strip().upper()
            if tv not in ELVEG_FERRY and ((tv in ELVEG_PED) or (tv in ELVEG_DRIVE and cat not in ELVEG_NONWALK_CAT)):
                ls = el.find(".//" + GML + "LineString")
                pos = el.find(".//" + GML + "posList")
                if pos is not None and pos.text:
                    dim = int(ls.get("srsDimension", "2")) if ls is not None else 2
                    nums = pos.text.split()
                    pts = [tr.transform(float(nums[i]), float(nums[i + 1]))
                           for i in range(0, len(nums) - (dim - 1), dim)]
                    if len(pts) >= 2:
                        lines.append(pts)
            el.clear()
    return lines

def osm_classify(t):
    b = (t.get("building") or "").lower()
    am = (t.get("amenity") or "").lower()
    tour = (t.get("tourism") or "").lower()
    if b in SACRAL or am == "place_of_worship": return "sacral"
    if b in HYTTE or tour in HYTTE_TOUR: return "hytte"
    if b in HOUSING: return "housing"
    if b in OUTBUILDING: return "outbuilding"
    if b in PUBLIC: return "public"
    if b in ("yes", ""):
        if am in PUBLIC_AM or t.get("shop") or t.get("office") or tour in PUBLIC_TOUR: return "public"
    return "other"

# ---------- parse Matrikkelen ----------
def parse_matrikkelen(path):
    tr = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    pts = []
    for ev, el in ET.iterparse(path, events=("end",)):
        if el.tag == APP + "Bygning":
            bnr = el.findtext(APP + "bygningsnummer")
            btype = el.findtext(APP + "bygningstype")
            pos = el.find(".//" + GML + "pos")
            if bnr and pos is not None and pos.text:
                e, n = pos.text.split()
                lon, lat = tr.transform(float(e), float(n))
                pts.append((bnr, category(btype), bt_code(btype), lon, lat))
            el.clear()
    return pts

# ---------- parse OSM (Overpass JSON) ----------
def parse_osm(path):
    j = json.load(open(path, encoding="utf-8"))
    nodes = {}
    ways = []
    for e in j["elements"]:
        if e["type"] == "node":
            nodes[e["id"]] = (e["lon"], e["lat"])
        elif e["type"] == "way":
            ways.append(e)
    buildings = []   # (id, ring[list(lon,lat)], type)
    highways = []    # list of polylines [(lon,lat)...]
    for w in ways:
        t = w.get("tags", {})
        coords = [nodes[n] for n in w["nodes"] if n in nodes]
        b = t.get("building"); hw = t.get("highway")
        if b and b != "no" and len(coords) >= 4:
            if coords[0] != coords[-1]:
                coords = coords + [coords[0]]
            buildings.append(("w%d" % w["id"], coords, osm_classify(t)))
        elif hw in WALKABLE and len(coords) >= 2:
            highways.append(coords)
    return buildings, highways

# ---------- D6 accessible (highway buffer), mirrors AreaSource.tagAccessible ----------
def compute_accessible(buildings, highways, ref_lat):
    if not highways:
        return {bid: True for bid, _, _ in buildings}
    # kLon за широтою КОЖНОЇ будівлі, а не однією опорною на регіон. На фюльке похибка ще мала, але
    # на нац.масштабі (58°N…71°N: cos 0,53 проти 0,33) фіксована опорна широта тихо спотворила б
    # буфер D6 у півтора раза. Схема: грід ребер лишається в ОПОРНИХ метрах (потрібна одна спільна
    # система), а відстань міряємо, домноживши x-складову на r = cos(lat_буд)/cos(ref).
    # ref беремо як МАКСИМАЛЬНУ широту даних ⇒ r >= 1 ⇒ справжня відстань >= опорної ⇒ пошук
    # у радіусі BUFFER опорних метрів лишається НАДМНОЖИНОЮ справжнього (нічого не губимо).
    ref = max(ref_lat,
              max((p[1] for poly in highways for p in poly), default=ref_lat),
              max((ring[0][1] for _b, ring, _t in buildings), default=ref_lat))
    cos_ref = math.cos(math.radians(ref))
    kLon = 111320.0 * cos_ref; kLat = 111320.0
    segs = []  # (x1,y1,x2,y2)
    for poly in highways:
        for i in range(len(poly) - 1):
            segs.append((poly[i][0]*kLon, poly[i][1]*kLat, poly[i+1][0]*kLon, poly[i+1][1]*kLat))
    grid = {}
    for i, (x1, y1, x2, y2) in enumerate(segs):
        cx = int(min(x1, x2)//CELL); cxM = int(max(x1, x2)//CELL); cyM = int(max(y1, y2)//CELL)
        while cx <= cxM:
            cy = int(min(y1, y2)//CELL)
            while cy <= cyM:
                grid.setdefault((cx, cy), []).append(i); cy += 1
            cx += 1
    def dist2(px, py, ax, ay, bx, by):
        dx = bx-ax; dy = by-ay; l2 = dx*dx+dy*dy
        t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/l2))
        ex = px-(ax+t*dx); ey = py-(ay+t*dy); return ex*ex+ey*ey
    b2 = BUFFER*BUFFER; span = int(BUFFER//CELL)+1
    out = {}
    for bid, ring, _ in buildings:
        acc = False
        r = math.cos(math.radians(ring[0][1])) / cos_ref     # >= 1; будинок < 100 м, тож одне r на кільце
        for lon, lat in ring:
            px = lon*kLon; py = lat*kLat
            cx0 = int(px//CELL); cy0 = int(py//CELL)
            for dx in range(-span, span+1):
                for dy in range(-span, span+1):
                    for si in grid.get((cx0+dx, cy0+dy), ()):
                        ax, ay, bx, by = segs[si]
                        if dist2(px*r, py, ax*r, ay, bx*r, by) <= b2:
                            acc = True; break
                    if acc: break
                if acc: break
            if acc: break
        out[bid] = acc
    return out

# ---------- point-in-polygon + grid index ----------
def pip(x, y, ring):
    inside = False; n = len(ring); j = n-1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj-xi)*(y-yi)/(yj-yi)+xi):
            inside = not inside
        j = i
    return inside

# ---------- смуговий (band) індекс ребер кільця — ідея з retag_kommune.py::Poly ----------
# Навіщо: кільця tettsteder мають до 32 тис. вершин, і лінійний locate_tettsted коштував 0,69-0,92 мс
# на будівлю (виміряно на 22 645 продакшн-центроїдах) — на фюльке це 230 тис. викликів ≈ 2,6-3,5 хв
# ЛИШЕ на приписування tettsted, на країні — під годину. Смуги роблять ray-cast O(кілька ребер):
# заміряно 8,0-8,8 мкс/виклик, тобто x78-x88, при 0 розбіжностей у результаті.
# Відмінність від retag_kommune.Poly: там смуги зберігають КОПІЇ координат ребра — тут індекси
# (array('i')), бо на нац.масштабі копії роздули б індекс на гігабайти (див. band_index).
def band_index(ring):
    """lat-смуга -> ІНДЕКСИ ребер (array('i'), а не копії координат: на нац.масштабі копії роздували б
    індекс до гігабайтів — виміряно +171% RAM проти +3% на індексах).
    Ребро i — це (ring[i], ring[i-1]), тобто РІВНО пара (поточна, попередня) з pip(); ring[-1] для i=0
    сам загортається на останню вершину. Той самий вираз + ті самі float-об'єкти ⇒ та сама арифметика
    з плаваючою комою ⇒ результат BIT-IDENTICAL до лінійного pip() (звірено на 22 645 продакшн-будівлях)."""
    bands = {}
    n = len(ring)
    for i in range(n):
        yi = ring[i][1]; yj = ring[i-1][1]
        b0 = int(min(yi, yj) // TBAND); b1 = int(max(yi, yj) // TBAND)
        for b in range(b0, b1 + 1):
            bands.setdefault(b, array("i")).append(i)
    return bands

def pip_banded(x, y, ring, bands):
    """Те саме, що pip(), але перебирає лише ребра, що перетинають lat-смугу точки.
    Ребро, яке МОЖЕ перетнути горизонталь y, обов'язково лежить у смузі int(y//TBAND) — bands
    містить ребро в КОЖНІЙ смузі його lat-діапазону, тож жодного перетину не губимо."""
    inside = False
    for i in bands.get(int(y // TBAND), ()):
        xi, yi = ring[i]; xj, yj = ring[i-1]
        if ((yi > y) != (yj > y)) and (x < (xj-xi)*(y-yi)/(yj-yi)+xi):
            inside = not inside
    return inside

# ---------- Douglas-Peucker (спрощення ВИХІДНИХ кілець tettsteder; тег tettsted_id рахується по ТОЧНИХ) ----------
def dp_simplify(ring, eps_m, kLon, kLat):
    """DP на ЗАМКНЕНОМУ кільці: перша й остання (== першій) вершини закріплені, тож базовий відрізок
    вироджений у точку і кільце не може схлопнутись. Ітеративно (стек, не рекурсія) — кільця SSB
    бувають 7000+ вершин. eps у метрах через локальну рівнокутну проєкцію."""
    n = len(ring)
    if eps_m <= 0 or n <= 5:
        return ring
    pts = [(x * kLon, y * kLat) for x, y in ring]
    # Захист від «розчинення» дрібних полігонів: 15 м на клаптику 100×100 м — це вже груба зміна форми
    # (виміряно на SSB MR: полігони <1 га втрачали до 61% площі, тоді як Ålesund 15 км² — 0,56%).
    # Обмежуємо eps масштабом САМОГО полігона: не більше 1/20 його характерного розміру.
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    eps = min(eps_m, math.sqrt((max(xs) - min(xs)) * (max(ys) - min(ys))) / 20.0)
    keep = [False] * n; keep[0] = keep[n-1] = True
    stack = [(0, n - 1)]; e2 = eps * eps
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1: continue
        ax, ay = pts[i0]; bx, by = pts[i1]
        dx = bx - ax; dy = by - ay; l2 = dx*dx + dy*dy
        best = -1.0; bi = -1
        for k in range(i0 + 1, i1):
            px, py = pts[k]
            t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / l2))
            ex = px - (ax + t*dx); ey = py - (ay + t*dy); d2 = ex*ex + ey*ey
            if d2 > best: best = d2; bi = k
        if best > e2:
            keep[bi] = True; stack.append((i0, bi)); stack.append((bi, i1))
    out = [ring[i] for i in range(n) if keep[i]]
    if len(out) < 4 or out[0] != out[-1]:   # виродження — краще лишити оригінал, ніж зламати полігон
        return ring
    return out

# ---------- SSB Tettsteder (P20): межі поселень для per-tettsted Coverage-% ----------
def _lname(tag):
    return tag.rsplit("}", 1)[-1]

def parse_tettsteder(path):
    """SSB Tettsteder WFS-GML → [{'id','name','pop','polys':[(ring,bbox,bands)...]}].
    `ring` = зовнішнє кільце [(lon,lat)...] (дірок нема — verified data-спайк 2026-07-11).
    Осі: файл з fetch_tettsteder.py — EPSG:4326 (posList «lat lon») → міняємо на (lon,lat).
    Фолбек: значення схожі на UTM (|coord|>400) → репроєкція 25833→4326 (на випадок іншого srsName)."""
    # визначити систему координат по першому posList
    utm = False
    for _ev, el in ET.iterparse(path, events=("end",)):
        if _lname(el.tag) == "posList" and el.text:
            v = el.text.split()
            if v and (abs(float(v[0])) > 400 or abs(float(v[1])) > 400):
                utm = True
            el.clear(); break
        el.clear()
    tr = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True) if utm else None

    def to_lonlat(a, b):
        # geo4326: posList = (lat, lon) → (lon, lat); utm33: (easting, northing) → transform
        return tr.transform(a, b) if tr else (b, a)

    tett = []
    for _ev, el in ET.iterparse(path, events=("end",)):
        ln = _lname(el.tag)
        if ln.startswith("tettsted_") and el.tag.startswith(MS):
            tid = name = pop = ""
            polys = []
            for ch in el.iter():
                cn = _lname(ch.tag)
                if cn == "tett_nr": tid = (ch.text or "").strip()
                elif cn == "tettstedsnavn": name = (ch.text or "").strip()
                elif cn == "befolkning_tettsted": pop = (ch.text or "").strip()
                elif cn == "posList" and ch.text:
                    nums = ch.text.split()
                    ring = [to_lonlat(float(nums[i]), float(nums[i + 1])) for i in range(0, len(nums) - 1, 2)]
                    if len(ring) >= 4:
                        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
                        polys.append((ring, (min(xs), min(ys), max(xs), max(ys)), band_index(ring)))
            if tid and polys:
                tett.append({"id": tid, "name": name,
                             "pop": int(pop) if pop.isdigit() else 0, "polys": polys})
            el.clear()
    return tett

def tett_grid(tett):
    """Грід-індекс полігонів (клітинка TGRID°): (cx,cy) -> [(індекс tettsted, індекс polys)].
    Кандидати ВІДСОРТОВАНІ за (ti,pi), тож перший, що містить точку, — той самий, що й при
    лінійному скані у файловому порядку → семантика locate_tettsted не змінюється."""
    g = {}
    for ti, t in enumerate(tett):
        for pi, (_ring, bb, _bands) in enumerate(t["polys"]):
            for cx in range(int(bb[0] // TGRID), int(bb[2] // TGRID) + 1):
                for cy in range(int(bb[1] // TGRID), int(bb[3] // TGRID) + 1):
                    g.setdefault((cx, cy), []).append((ti, pi))
    for v in g.values(): v.sort()
    return g

def locate_tettsted(lon, lat, tett, grid=None):
    """Який tettsted містить точку (lon,lat)? грід-відсів → bbox → banded-PIP.
    None = поза всіма (сільське/між містами). grid=None → лінійний скан (стара поведінка, для тестів)."""
    if grid is None:
        for t in tett:
            for ring, bb, bands in t["polys"]:
                if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and pip_banded(lon, lat, ring, bands):
                    return t["id"]
        return None
    for ti, pi in grid.get((int(lon // TGRID), int(lat // TGRID)), ()):
        ring, bb, bands = tett[ti]["polys"][pi]
        if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and pip_banded(lon, lat, ring, bands):
            return tett[ti]["id"]
    return None

# ---------- --pairs=list.txt: одна комуна на рядок замість 54 позиційних аргументів ----------
def _split_spec(line):
    """Роздільник `|`, якщо він є в рядку (радимо для абсолютних Windows-шляхів), інакше `:` —
    але НЕ той, за яким іде / чи \\, щоб не порізати `C:\\data\\volda.gml` на «C» і «\\data\\...»."""
    if "|" in line:
        return [s.strip() for s in line.split("|")]
    return [s.strip() for s in re.split(r":(?![\\/])", line)]

def read_pairs_file(path):
    """Формат рядка: KOD:Назва:matrikkelen.gml:osm.json[:elveg.gml]  (`#` — коментар, порожні — пропуск).
    Повертає (kommuner, pairs, elveg) у ПОРЯДКУ файлу — рівно те, що дали б --kommuner + позиційні пари.
    Відносні шляхи: спершу як є (від cwd), інакше — від каталогу самого списку."""
    base = os.path.dirname(os.path.abspath(path))
    def resolve(p):
        if os.path.isabs(p) or os.path.exists(p): return p
        alt = os.path.join(base, p)
        return alt if os.path.exists(alt) else p        # не існує ніде → лишаємо як є (впаде з чітким шляхом)
    kommuner, pairs, elveg = [], [], []
    for ln, raw in enumerate(open(path, encoding="utf-8-sig"), 1):
        s = raw.split("#", 1)[0].strip()
        if not s: continue
        f = _split_spec(s)
        assert len(f) >= 4, (f"{path}:{ln}: очікую KOD:Назва:matrikkelen.gml:osm.json[:elveg.gml], "
                             f"а полів {len(f)}: {f!r}")
        code, name, gml, osm = f[0], f[1], f[2], f[3]
        assert code, f"{path}:{ln}: порожній kommunenummer"
        kommuner.append((code, name))
        pairs += [resolve(gml), resolve(osm)]
        if len(f) >= 5 and f[4]: elveg.append(resolve(f[4]))
    assert kommuner, f"{path}: жодного рядка з даними"
    return kommuner, pairs, elveg

def main():
    # usage: build_tiles.py OUTDIR REF_LAT [--elveg=e1.gml,e2.gml] [--osm-bridge] GML1 OSM1 [GML2 OSM2 ...]
    #   --elveg=…    : D6-eligibility з Kartverket Elveg (замість OSM highways). Кома-розділені GML.
    #   --osm-bridge : додати OSM footway/path/track до Elveg (закрити sti-провал; повертає ODbL по вег-шару).
    #   --tettsteder=… : SSB Tettsteder GML (P20) — межі поселень для per-tettsted Coverage-% + boundary-шар.
    #   --kommuner=…   : P30 — код:назва на КОЖНУ пару вхідних файлів, у тому самому порядку
    #                    (напр. 1577:Volda,1520:Ørsta). Комуна відома з індексу пари — вхід і так per-kommune,
    #                    тож ні PIP, ні нових джерел не треба. Не переданий → тег не пишеться (зворотна сумісність).
    #   --pairs=list.txt : масштаб фюльке/країни — один рядок «KOD:Назва:gml:osm[:elveg]» на комуну
    #                    замість 54 позиційних аргументів + --kommuner. Взаємовиключний із ними.
    #   --simplify-m=15  : Douglas-Peucker кілець у tettsteder.geojson (застосунок качає файл ЦІЛКОМ).
    #                    0 = вимкнути. На tettsted_id НЕ впливає — PIP рахується по точних кільцях.
    elveg_paths, osm_bridge, region, tett_path, kommuner, rest = [], False, "", "", [], []
    pairs_file, simplify_m = "", SIMPLIFY_M
    for a in sys.argv[1:]:
        if a.startswith("--elveg="): elveg_paths = [p for p in a[len("--elveg="):].split(",") if p]
        elif a == "--osm-bridge": osm_bridge = True
        elif a.startswith("--region="): region = a[len("--region="):]   # P18: назва регіону в manifest
        elif a.startswith("--tettsteder="): tett_path = a[len("--tettsteder="):]   # P20
        elif a.startswith("--pairs="): pairs_file = a[len("--pairs="):]
        elif a.startswith("--simplify-m="): simplify_m = float(a[len("--simplify-m="):])
        elif a.startswith("--kommuner="):                                          # P30
            for spec in a[len("--kommuner="):].split(","):
                spec = spec.strip()
                if not spec: continue
                code, _, kname = spec.partition(":")
                kommuner.append((code.strip(), kname.strip()))
        else: rest.append(a)
    assert len(rest) >= 2, "need OUTDIR REF_LAT [--elveg=…] then GML OSM pairs (або --pairs=list.txt)"
    outdir, ref_lat = rest[0], float(rest[1])
    pairs = rest[2:]
    if pairs_file:
        assert not pairs, "--pairs=… разом із позиційними парами — обери щось одне"
        assert not kommuner, "--pairs=… вже містить коди комун — прибери --kommuner=…"
        kommuner, pairs, fe = read_pairs_file(pairs_file)
        elveg_paths = elveg_paths + fe          # per-line elveg ДОПОВНЮЄ --elveg=, не замінює
        print(f"--pairs={os.path.basename(pairs_file)}: {len(kommuner)} комун, "
              f"{len(pairs)//2} пар файлів, elveg-із-списку {len(fe)}")
    assert len(pairs) % 2 == 0 and pairs, "need OUTDIR REF_LAT [--elveg=…] then GML OSM pairs"
    npairs = len(pairs) // 2
    if kommuner:
        assert len(kommuner) == npairs, (
            f"--kommuner: {len(kommuner)} записів, а пар вхідних файлів {npairs} — "
            f"треба рівно один код:назва на пару, у тому самому порядку")
    os.makedirs(outdir, exist_ok=True)
    mats, buildings, osm_hw = [], [], []
    kom_of = {}        # P30: osm building_id -> kommunenummer (з ІНДЕКСУ пари, без PIP)
    kom_name = dict(kommuner)
    for i in range(0, len(pairs), 2):
        m = parse_matrikkelen(pairs[i])
        b, h = parse_osm(pairs[i + 1])
        if kommuner:
            kcode = kommuner[i // 2][0]
            dup = 0
            for bid, _ring, _ot in b:
                if bid in kom_of: dup += 1          # id-колізія між комунами (не має бути: OSM way-id глобальні)
                kom_of[bid] = kcode
            print(f"  {os.path.basename(pairs[i])}: Matrikkelen={len(m)} OSM buildings={len(b)} "
                  f"highways={len(h)} kommune={kcode} ({kom_name[kcode]})"
                  + (f" ⚠ {dup} id-колізій перезаписано" if dup else ""))
        else:
            print(f"  {os.path.basename(pairs[i])}: Matrikkelen={len(m)} OSM buildings={len(b)} highways={len(h)}")
        mats += m; buildings += b; osm_hw += h
    # D31: eligibility-мережа = офіційний Elveg (CC-BY), якщо задано; інакше OSM-highways (dogfood-фолбек)
    if elveg_paths:
        highways = []
        for ep in elveg_paths:
            e = parse_elveg(ep); highways += e
            print(f"  {os.path.basename(ep)}: Elveg walkable={len(e)}")
        src = "Elveg (NVDB Vegnett Pluss)"
        if osm_bridge:
            highways += osm_hw; src += f" + OSM-bridge ({len(osm_hw)})"
    else:
        highways = osm_hw; src = "OSM-highways (dogfood)"
    print(f"COMBINED: Matrikkelen={len(mats)} buildings={len(buildings)} | eligibility={src}: {len(highways)} ліній")

    accessible = compute_accessible(buildings, highways, ref_lat)

    # P20: межі SSB Tettsteder — приписуємо будівлю до поселення (centroid PIP → tettsted_id)
    tett = parse_tettsteder(tett_path) if tett_path else []
    tgrid = tett_grid(tett) if tett else None
    if tett_path:
        print(f"  tettsteder: {len(tett)} поселень у файлі ({os.path.basename(tett_path)}), "
              f"{sum(len(t['polys']) for t in tett)} полігонів, грід-клітинок {len(tgrid or ())}")

    # spatial index of building bboxes (0.002deg ~200m cells)
    GC = 0.002
    bbi = {}
    binfo = []  # (bid, ring, osm_type, (minx,miny,maxx,maxy))
    for bid, ring, ot in buildings:
        xs = [c[0] for c in ring]; ys = [c[1] for c in ring]
        bb = (min(xs), min(ys), max(xs), max(ys))
        idx = len(binfo); binfo.append((bid, ring, ot, bb))
        cx0 = int(bb[0]//GC); cx1 = int(bb[2]//GC); cy0 = int(bb[1]//GC); cy1 = int(bb[3]//GC)
        for cx in range(cx0, cx1+1):
            for cy in range(cy0, cy1+1):
                bbi.setdefault((cx, cy), []).append(idx)

    # join Matrikkelen -> building
    mat_of = {}   # building idx -> (bnr, category, bygningstype|None)
    matched = 0
    for bnr, cat, bt, lon, lat in mats:
        cx = int(lon//GC); cy = int(lat//GC)
        for idx in bbi.get((cx, cy), ()):
            bid, ring, ot, bb = binfo[idx]
            if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and pip(lon, lat, ring):
                if idx not in mat_of:      # first point wins (14 multi-point in Volda)
                    mat_of[idx] = (bnr, cat, bt); matched += 1
                break

    # emit features per tile (assign by centroid)
    tiles = {}
    enriched = 0
    for idx, (bid, ring, ot, bb) in enumerate(binfo):
        cxlon = sum(c[0] for c in ring[:-1]) / (len(ring)-1)
        cylat = sum(c[1] for c in ring[:-1]) / (len(ring)-1)
        m = mat_of.get(idx)
        bt = None
        if m:
            fid = "m" + m[0]; ftype = m[1]; bt = m[2]; enriched += 1
        else:
            fid = bid; ftype = ot
        props = {"building_id": fid, "type": ftype, "accessible": accessible.get(bid, True)}
        if bt is not None: props["bt"] = bt          # сирий bygningstype; НЕМА матчу на Matrikkelen → нема ключа
        kc = kom_of.get(bid)                                         # P30: тег комуни (з індексу пари)
        if kc: props["kommune"] = kc                                 # невідома комуна → без тега
        if tett:                                                     # P20: тег поселення (Android читає прямо з фічі)
            tid = locate_tettsted(cxlon, cylat, tett, tgrid)
            if tid: props["tettsted_id"] = tid                       # поза всіма tettsteder → без тега (сільське)
        feat = {"type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[round(x, 7), round(y, 7)] for x, y in ring]]},
                "properties": props}
        la = round(cylat / TILE); lo = round(cxlon / TILE)
        tiles.setdefault((la, lo), []).append(feat)

    kv = "Matrikkelen" + (" + NVDB Vegnett Pluss/Elveg 2.0" if elveg_paths else "")
    manifest = {"tiles": [], "tileDeg": TILE,
                # Версія СХЕМИ тайлів (не свіжості) — клієнт по ній інвалідує кеш зон. Див. DATA_VERSION.
                "dataVersion": DATA_VERSION,
                "attribution": f"© OpenStreetMap contributors (ODbL) · © Kartverket ({kv}, CC BY 4.0)"}
    for (la, lo), feats in sorted(tiles.items()):
        key = f"area_{la}_{lo}"
        json.dump({"type": "FeatureCollection", "features": feats},
                  open(os.path.join(outdir, key + ".geojson"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        manifest["tiles"].append({"key": key, "n": len(feats)})
    # P18 region-manifest: лічильники по типах (застосунок показує «X розкрито з Y у місті» + city-Coverage-%)
    CATS = ["housing", "hytte", "public", "sacral", "outbuilding", "other"]
    byType = {c: {"total": 0, "accessible": 0} for c in CATS}
    # Знаменники по СИРИХ bygningstype (майбутні колекції «усі naust у Volda»): без них деталізація
    # в тайлі марна — застосунок знав би «розкрито 3 naust», але не «з 47». Емітимо ЛИШЕ коди, що
    # реально трапились (жодних нулів на всі 126 кодів кодлиста), + окремо чесний лічильник «коду нема».
    byBt = {}
    btUnknown = {"total": 0, "accessible": 0}
    tot_all = acc_all = 0
    for feats in tiles.values():
        for f in feats:
            p = f["properties"]; d = byType.setdefault(p["type"], {"total": 0, "accessible": 0})
            d["total"] += 1; tot_all += 1
            acc = p["accessible"]
            if acc: d["accessible"] += 1; acc_all += 1
            bt = p.get("bt")
            if bt is None:
                btUnknown["total"] += 1
                if acc: btUnknown["accessible"] += 1
            else:
                bt_bump(byBt, bt, acc)
    manifest["region"] = region
    manifest["generated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["byType"] = byType
    manifest["byBygningstype"] = dict(sorted(byBt.items()))       # сорт — детермінізм діфів між ребілдами
    manifest["bygningstypeUnknown"] = btUnknown                   # будівлі без матчу на Matrikkelen
    manifest["total"] = tot_all
    manifest["accessible"] = acc_all
    # P30: byKommune — ті самі лічильники, але в розрізі комуни (ПОРЯД із наявними, наявні не чіпаємо).
    # Комуни з --kommuner присутні завжди, навіть із нулями (щоб Android не бачив «зникла комуна»).
    if kommuner:
        def _kom_entry(nm):
            return {"name": nm, "total": 0, "accessible": 0,
                    "byType": {c: {"total": 0, "accessible": 0} for c in CATS},
                    "byBygningstype": {}, "bygningstypeUnknown": {"total": 0, "accessible": 0}}
        byKom = {code: _kom_entry(nm) for code, nm in kommuner}
        for feats in tiles.values():
            for f in feats:
                p = f["properties"]; kc = p.get("kommune")
                if not kc: continue
                e = byKom.setdefault(kc, _kom_entry(kom_name.get(kc, "")))
                d = e["byType"].setdefault(p["type"], {"total": 0, "accessible": 0})
                acc = p["accessible"]
                e["total"] += 1; d["total"] += 1
                if acc: e["accessible"] += 1; d["accessible"] += 1
                bt = p.get("bt")                      # знаменники колекцій у розрізі комуни
                if bt is None:
                    e["bygningstypeUnknown"]["total"] += 1
                    if acc: e["bygningstypeUnknown"]["accessible"] += 1
                else:
                    bt_bump(e["byBygningstype"], bt, acc)
        for e in byKom.values():
            e["byBygningstype"] = dict(sorted(e["byBygningstype"].items()))
        manifest["byKommune"] = byKom
        kom_sum = sum(e["total"] for e in byKom.values())
        print("byKommune (P30): " + " · ".join(
            f"{c} {e['name']} {e['total']}/{e['accessible']}" for c, e in byKom.items())
            + f" | сума {kom_sum}/{tot_all}"
            + ("" if kom_sum == tot_all else f" ⚠ {tot_all - kom_sum} буд. без тега комуни"))
    # ⚠️ БЕЗ indent: manifest читає лише машина, а відступи коштували 40% його розміру. З появою
    # `byBygningstype` (27 комун × ~81 код) файл виріс 227→372 КБ; без відступів — 217 КБ, тобто
    # МЕНШЕ, ніж до появи кодів. На нац.масштабі ця економія масштабується разом із файлом.
    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"manifest: region='{region}' dataVersion={DATA_VERSION} total={tot_all} accessible={acc_all} "
          f"byType={ {k: v['total'] for k, v in byType.items()} }")
    top_bt = sorted(byBt.items(), key=lambda kv: -kv[1]["total"])[:8]
    print(f"byBygningstype: {len(byBt)} кодів у даних, топ "
          + " · ".join(f"{c}={v['total']}" for c, v in top_bt)
          + f" | без коду (нема матчу на Matrikkelen) {btUnknown['total']} "
            f"({100*btUnknown['total']/max(tot_all,1):.1f}%)")
    bt_sum = sum(v["total"] for v in byBt.values())
    assert bt_sum + btUnknown["total"] == tot_all, (
        f"знаменники bygningstype не сходяться: {bt_sum}+{btUnknown['total']} != {tot_all}")

    # P20: per-tettsted лічильники + boundary-GeoJSON (Android: %-Coverage поточного tettsted + видимий кордон).
    # Емітимо лише tettsteder, у яких Є будівлі (data-backed) — щоб кожен намальований кордон був покривним
    # (не «0% Ulsteinvik», для якого ми не тягнули будинків). Сусіди без даних просто не малюються.
    if tett:
        tname = {t["id"]: t["name"] for t in tett}; tpop = {t["id"]: t["pop"] for t in tett}
        tc = {}   # tid -> {name,pop,total,accessible,byType:{cat:{total,accessible}}}
        for feats in tiles.values():
            for f in feats:
                p = f["properties"]; tid = p.get("tettsted_id")
                if not tid: continue
                e = tc.setdefault(tid, {"name": tname.get(tid, ""), "pop": tpop.get(tid, 0),
                                        "total": 0, "accessible": 0,
                                        "byType": {c: {"total": 0, "accessible": 0} for c in CATS},
                                        "byBygningstype": {},
                                        "bygningstypeUnknown": {"total": 0, "accessible": 0},
                                        "kom": {}})
                d = e["byType"].setdefault(p["type"], {"total": 0, "accessible": 0})
                acc = p["accessible"]
                e["total"] += 1; d["total"] += 1
                if acc: e["accessible"] += 1; d["accessible"] += 1
                bt = p.get("bt")                            # знаменники колекцій у розрізі поселення
                if bt is None:
                    e["bygningstypeUnknown"]["total"] += 1
                    if acc: e["bygningstypeUnknown"]["accessible"] += 1
                else:
                    bt_bump(e["byBygningstype"], bt, acc)
                kc = p.get("kommune")                       # P30: голоси на мажоритарну комуну поселення
                if kc: e["kom"][kc] = e["kom"].get(kc, 0) + 1
        feats_out = []
        vin = vout = 0
        for t in tett:
            c = tc.get(t["id"])
            if not c: continue
            # Спрощення — ЛИШЕ для вихідної геометрії (кордон малюється лінією, P20; деталізація SSB
            # там надлишкова, а файл застосунок качає ЦІЛКОМ). tettsted_id вище вже пораховано
            # по ТОЧНИХ кільцях, тож приписування будівель спрощення не зачіпає.
            coords = []
            for ring, bb, _bands in t["polys"]:
                kLat = 111320.0; kLon = 111320.0 * math.cos(math.radians((bb[1] + bb[3]) / 2))
                s = dp_simplify(ring, simplify_m, kLon, kLat)
                vin += len(ring); vout += len(s)
                coords.append([[[round(x, 6), round(y, 6)] for x, y in s]])
            props = {"tett_nr": t["id"], "name": c["name"], "pop": c["pop"],
                     "total": c["total"], "accessible": c["accessible"], "byType": c["byType"],
                     "byBygningstype": dict(sorted(c["byBygningstype"].items())),
                     "bygningstypeUnknown": c["bygningstypeUnknown"]}
            if c["kom"]:                                    # P30: мажоритарна комуна (ties → менший код, детермінізм)
                kc = max(sorted(c["kom"]), key=lambda k: c["kom"][k])
                props["kommune"] = kc
                props["kommune_name"] = kom_name.get(kc, "")
            feats_out.append({"type": "Feature",
                "geometry": {"type": "MultiPolygon", "coordinates": coords},
                "properties": props})
        tfc = {"type": "FeatureCollection", "region": region, "generated": manifest["generated"],
               "attribution": "© Statistisk sentralbyrå (Tettsteder, NLOD)", "features": feats_out}
        json.dump(tfc, open(os.path.join(outdir, "tettsteder.geojson"), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        assigned = sum(c["total"] for c in tc.values())
        top = {c["name"]: c["total"] for c in sorted(tc.values(), key=lambda x: -x["total"])[:8]}
        tsz = os.path.getsize(os.path.join(outdir, "tettsteder.geojson"))
        print(f"tettsteder (P20): {len(feats_out)} з даними -> tettsteder.geojson {top}; "
              f"{assigned}/{len(binfo)} буд. у tettsted, {len(binfo)-assigned} поза (сільське)")
        print(f"  спрощення кілець: --simplify-m={simplify_m:g} → вершин {vin}→{vout} "
              f"({100*vout/max(vin,1):.1f}%), файл {tsz/1024:.0f} KB")

    acc_n = sum(1 for v in accessible.values() if v)
    print(f"joined: {matched}/{len(buildings)} buildings enriched w/ Matrikkelen ({100*enriched/max(len(buildings),1):.1f}%)")
    print(f"accessible (D6): {acc_n}/{len(buildings)} ({100*acc_n/max(len(buildings),1):.1f}%)")
    print(f"tiles written: {len(tiles)} -> {outdir}")

if __name__ == "__main__":
    main()

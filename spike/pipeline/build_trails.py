# -*- coding: utf-8 -*-
"""GML Turrutebasen → `trails.geojson`: марковані маршрути, нарізані на **наші** сегменти.

Реалізує інкремент 1 плану `docs/TRAILS-BRIEF.md` (лінійна механіка D34).

**Чому нарізаємо самі** (рішення Q1). Turrutebasen нарізаний під власні потреби: у тих самих
даних трапляються ділянки по 40 м і по 3 км, тож «пройдено 3 з 5» означало б різне в різних
маршрутах. Цілий маршрут як одиниця теж не годиться — 12-кілометровий давав би «3%» місяцями,
рівно та «фонова робота на роки», яку ми вже відкинули для колекцій (`CollectionRules.MAX_SIZE`).
Наша нарізка ~[TARGET_M] м передбачувана й росте на кожній прогулянці.

⚠️ **`segment_id` мусить бути стабільним між збірками.** Інакше наступний ребілд даних осиротить
увесь записаний прогрес — та сама пастка, що з ключем колекцій (P28). Тому якір — `lokalId` фічі
(UUID від Kartverket, а не наш порядковий номер) плюс індекс сегмента всередині неї.
**Межа цієї стабільності названа чесно:** якщо Kartverket перезніме сам маршрут (зміниться
геометрія), межі сегментів зсунуться і частина прогресу осиротіє. Захисту від цього тут немає —
є лише вибір НЕ додавати до цього ще й власну нестабільність.

Ліцензія: Kartverket, CC BY 4.0.

usage:
    python build_trails.py RAW.xml OUT.geojson [--min-len=75] [--target=200] [--keep-unnamed]
"""
import io
import json
import math
import re
import sys

TARGET_M = 200.0        # цільова довжина сегмента
MIN_TAIL_M = 75.0       # коротший хвіст вливаємо в попередній, щоб не плодити недоліжків

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True) for a in sys.argv[1:] if a.startswith("--")}
raw_path = args[0] if args else "turrutebasen_raw.xml"
out_path = args[1] if len(args) > 1 else "trails.geojson"
TARGET_M = float(opts.get("--target", TARGET_M))
MIN_TAIL_M = float(opts.get("--min-len", MIN_TAIL_M))
keep_unnamed = bool(opts.get("--keep-unnamed", False))

R = 6371008.8


def haversine(a, b):
    """Метри між (lon, lat)."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def cut(coords, target=TARGET_M, min_tail=MIN_TAIL_M):
    """Ламану → список сегментів ~`target` м.

    ⚠️ Ріжемо ВСЕРЕДИНІ ребра, а не по вузлах: вузли Turrutebasen стоять нерівномірно (де рельєф
    складніший — густіше), тож нарізка «по найближчому вузлу» дала б ті самі стрибки довжини, від
    яких ми й тікаємо. Точка розрізу інтерполюється лінійно — на масштабі 200 м кривина землі
    неістотна.
    """
    segs, cur, acc = [], [coords[0]], 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        d = haversine(a, b)
        while acc + d >= target:
            t = (target - acc) / d if d > 0 else 1.0
            p = lerp(a, b, t)
            cur.append(p)
            segs.append(cur)
            cur, acc = [p], 0.0
            a, d = p, haversine(p, b)
        acc += d
        cur.append(b)
    if len(cur) > 1:
        tail = sum(haversine(cur[i], cur[i + 1]) for i in range(len(cur) - 1))
        # Хвіст коротший за поріг не існує окремо: «пройдено 40 м із 200» читалось би як повна
        # ділянка, а на карті це майже точка.
        if tail < min_tail and segs:
            segs[-1] = segs[-1] + cur[1:]
        else:
            segs.append(cur)
    return segs


def seg_len(c):
    return sum(haversine(c[i], c[i + 1]) for i in range(len(c) - 1))


text = io.open(raw_path, encoding="utf-8", errors="replace").read()
features = text.split("<app:Fotrute ")[1:]
print("фіч у вході: %d" % len(features))


def one(f, tag):
    m = re.search(r"<app:%s>([^<]*)</app:%s>" % (tag, tag), f)
    return m.group(1).strip() if m else ""


out, skipped_unmarked, skipped_unnamed, skipped_short = [], 0, 0, 0
routes = {}
for f in features:
    if one(f, "merking").upper() != "JA":       # Q3: лише МАРКОВАНІ
        skipped_unmarked += 1
        continue
    local_id = one(f, "lokalId")
    name = one(f, "rutenavn")
    number = one(f, "rutenummer")
    if not local_id:
        continue
    # ⚠️ 35 фіч у Volda+Ørsta названі «Ukjent» — це не назва, а її відсутність. Картка з таким
    # заголовком гірша за відсутність картки, тож за замовчуванням їх не беремо.
    named = name and name.lower() not in ("ukjent", "ukjend")
    if not named and not keep_unnamed:
        skipped_unnamed += 1
        continue

    m = re.search(r"<gml:posList[^>]*>([^<]+)</gml:posList>", f)
    if not m:
        continue
    nums = [float(x) for x in m.group(1).split()]
    # ⚠️ lat lon (див. `fetch_turrutebasen.py`) → GeoJSON хоче lon lat.
    coords = [(nums[i + 1], nums[i]) for i in range(0, len(nums) - 1, 2)]
    if len(coords) < 2:
        continue

    trail_id = number or ("n:" + name)
    routes.setdefault(trail_id, {"name": name if named else "", "segments": 0, "len": 0.0})
    for i, seg in enumerate(cut(coords)):
        L = seg_len(seg)
        if L < 1.0:
            skipped_short += 1
            continue
        out.append({
            "type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": [[round(x, 6), round(y, 6)] for x, y in seg]},
            "properties": {
                # Стабільний ключ прогресу: UUID фічі Kartverket + індекс усередині неї.
                "seg": "%s:%d" % (local_id, i),
                "trail": trail_id,
                "name": routes[trail_id]["name"],
                "len_m": round(L),
            },
        })
        routes[trail_id]["segments"] += 1
        routes[trail_id]["len"] += L

for f in out:
    # ⚠️ Позначка джерела на КОЖНІЙ фічі (заувага 9). Без неї відкат OSM неможливий у принципі:
    # ані відрізнити, ані порахувати, ані сказати людині, звідки стежка. Дешевше поле в проєкті
    # важко придумати, а без нього все інше — здогадки.
    f["properties"]["src"] = "kartverket"

# ── OSM: доповнення набору (заувага 9). ВИМКНЕНО, поки не передано `--osm` ────────────────────────
#
# ⚠️ **«Вимкнено» тут — стан за замовчуванням, а не окрема дія.** Це і є найдешевший рівень відкату:
# якщо польова перевірка покаже, що стежки з OSM погані, достатньо зібрати без прапорця й залити —
# `trails.geojson` іде з CDN, тож раунд у Play не потрібен. Прогрес на зниклих стежках осиротіє
# (рядки в Room лишаться, але жодна ділянка їх не питатиме) — не зникне й нічого не зламає; якщо
# ті самі лінії повернуться з тими самими id, він повернеться сам.
osm_path = opts.get("--osm")
osm_stats = None
if osm_path:
    import osm_trails
    osm_feats, osm_stats = osm_trails.build(
        osm_path,
        target_m=TARGET_M,
        min_tail_m=MIN_TAIL_M,
        min_chain_m=float(opts.get("--osm-min", 500)),
        max_chain_m=float(opts.get("--osm-max", 5000)),
        landmarks=opts.get("--landmarks"),
    )
    out.extend(osm_feats)

# ── D34 нарешті виконано: СТЕЖКИ ЛИШЕ ПОЗА МІСТОМ (рішення Дениса 2026-08-07) ─────────────────────
#
# D34 ④ казав це з самого початку, але пайплайн не мав полігонів поселень, і правило залишалось на
# папері. Тепер `tettsteder.geojson` є, і воно виконується.
#
# **Чому взагалі:** у місті будинки вже покривають той самий крок, тож стежка там зараховує ту саму
# прогулянку вдруге — і незрозуміло, що саме ти просуваєш. Плюс саме в місті живе «сміття» OSM
# (доріжки між під'їздами). Виміряно перед рішенням: у Kartverket у поселеннях лише **2%** ділянок,
# у OSM — **35%**.
#
# ⚠️ **Фільтруємо МАРШРУТАМИ, а не ділянками.** Порізати маршрут по межі поселення означало б, що в
# маршруту «з міста в гори» зникає початок: змінюється знаменник «N з M», а прогрес на викинутих
# ділянках осиротіє посеред пройденого. Тому маршрут відкидається цілком, якщо БІЛЬША ЧАСТИНА його
# довжини лежить у поселенні. Наслідок названо чесно: `Volda sentrum – Prestholmen` (та сама
# стежка, на якій механіка вперше спрацювала в полі) зникає — це прийнято свідомо.
tett_path = opts.get("--tettsteder")
if tett_path:
    tt = json.load(io.open(tett_path, encoding="utf-8"))

    def _rings(f):
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        return [poly[0] for poly in polys]

    _polys = [r for f in tt.get("features", []) for r in _rings(f)]

    def _inside(pt, ring):
        x, y = pt
        c, n, j = False, len(ring), len(ring) - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
                c = not c
            j = i
        return c

    def _in_town(pt):
        return any(_inside(pt, r) for r in _polys)

    by_trail = {}
    for f in out:
        pr = f["properties"]
        c = f["geometry"]["coordinates"]
        mid = c[len(c) // 2]
        t = by_trail.setdefault(pr["trail"], {"in": 0.0, "all": 0.0, "name": pr["name"]})
        t["all"] += pr["len_m"]
        if _in_town(mid):
            t["in"] += pr["len_m"]

    urban = {t for t, v in by_trail.items() if v["all"] > 0 and v["in"] * 2 > v["all"]}
    dropped_km = sum(v["all"] for t, v in by_trail.items() if t in urban) / 1000.0
    before = len(out)
    out = [f for f in out if f["properties"]["trail"] not in urban]
    print()
    print("поза містом (D34): відкинуто маршрутів %d · ділянок %d · %.1f км"
          % (len(urban), before - len(out), dropped_km))
    for t in sorted(urban, key=lambda t: -by_trail[t]["all"])[:6]:
        v = by_trail[t]
        print("  %-28s %.1f км (у місті %.0f%%)"
              % ((v["name"] or t)[:28], v["all"] / 1000.0, 100.0 * v["in"] / v["all"]))

attribution = "© Kartverket (Turrutebasen, CC BY 4.0)"
if osm_path:
    # ⚠️ ODbL вимагає атрибуції — це не формальність і не косметика.
    attribution += " · © OpenStreetMap contributors (ODbL)"

fc = {"type": "FeatureCollection",
      "attribution": attribution,
      "features": out}
io.open(out_path, "w", encoding="utf-8", newline="\n").write(
    json.dumps(fc, ensure_ascii=False, separators=(",", ":")))

# ⚠️ Статистика нижче — ЛИШЕ про Turrutebasen. Спершу я порахував її по всьому `out` уже після
# доливання OSM, і вийшло «34 маршрути · 1222 сегменти»: числа з різних джерел в одному рядку.
kv = [f for f in out if f["properties"]["src"] == "kartverket"]
lens = [f["properties"]["len_m"] for f in kv]
short = [x for x in lens if x < MIN_TAIL_M]
print("Turrutebasen: маршрутів %d · сегментів %d" % (len(routes), len(kv)))
# ⚠️ Називаємо вголос, а не ховаємо: коротка ділянка рахується як ПОВНА, тож вона легша за решту.
# Причина структурна — Turrutebasen ріже маршрут на багато коротких фіч, а ми ріжемо ВСЕРЕДИНІ
# фічі (щоб `segment_id` тримався за `lokalId`). Зшивати фічі маршруту перед нарізкою було б
# рівномірніше, але прив'язало б id до складу маршруту, а не до окремої фічі — тобто обміняло б
# видиму ваду на невидиму (осиротілий прогрес, P28). Рішення — після польового тесту.
print("пропущено: немарковані %d · без назви %d · вироджені %d"
      % (skipped_unmarked, skipped_unnamed, skipped_short))
if lens:
    lens_sorted = sorted(lens)
    print("довжина сегмента: мін %d · медіана %d · макс %d · сума %.1f км"
          % (lens_sorted[0], lens_sorted[len(lens) // 2], lens_sorted[-1], sum(lens) / 1000.0))
    print("коротших за %d м: %d із %d (%.1f%%), а це лише %.2f км із %.1f — артефакт нарізки джерела"
          % (MIN_TAIL_M, len(short), len(kv), 100.0 * len(short) / len(kv),
             sum(short) / 1000.0, sum(lens) / 1000.0))
if osm_stats:
    print()
    print("OSM (заувага 9): ланцюгів %d · %.1f км · сегментів %d"
          % (osm_stats["chains"], osm_stats["km"], osm_stats["segments"]))
    print("  відкинуто: коротших за поріг %d · мереж (задовгих) %d"
          % (osm_stats["dropped_short"], osm_stats["dropped_mesh"]))
print("→ %s (%d КБ)" % (out_path, len(json.dumps(fc)) // 1024))
print()
print("найдовші маршрути:")
for t, r in sorted(routes.items(), key=lambda kv: -kv[1]["len"])[:8]:
    print("  %-24s %-34s %3d ділянок · %.1f км"
          % (t[:24], (r["name"] or "(без назви)")[:34], r["segments"], r["len"] / 1000.0))

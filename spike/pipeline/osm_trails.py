# -*- coding: utf-8 -*-
"""OSM-стежки → сегменти для `trails.geojson` (польова заувага 9, 2026-08-07).

Кличеться з `build_trails.py --osm=osm_paths.json`. Окремий файл, бо гілка Turrutebasen тут ні до
чого: у неї своє джерело, свої правила й свій якір `segment_id`.

**Головне рішення: відбір ГЕОМЕТРИЧНИЙ, а не тегами.** Розвідка 2026-08-07 показала, що тегів у
OSM практично немає (`width` 0,3% · `sac_scale` 0,7% · `name` 0,3%), тож задум «фільтрувати за
шириною» нездійсненний. Зате геометрія є завжди, і саме вона відрізняє стежку від садової доріжки.

**Три кроки відбору, і кожен закриває свою ваду:**

1. **Ланцюги.** Суміжні лінії зшиваються за спільними вузлами (union-find). Одна лінія в OSM — це
   не маршрут, а шматок між двома розвилками; сама по собі вона нічого не означає.
2. **Вікно 0,5-5 км** (рішення Дениса). Знизу відсікається шум: 291 ланцюг коротший за 500 м, і
   їхня медіана — **111 м**, тобто це під'їзди, огризки й садові доріжки.
   ⚠️ Зверху відсікаються **мережі**: 12 ланцюгів довших за 5 км тримають 169 км із 242, у
   середньому по 14 км. Це не стежки — це все, що десь торкається одне одного, злипле в один
   компонент. Картка «0 з 214 ділянок» для такої плями маршрутом не є (D34) і не закриється
   ніколи, тобто читалася б як вічний борг (D20).
3. **Назва за найближчим орієнтиром** — бо власної немає в 99,7%.

⚠️ **Якір `seg` — id ЛІНІЇ OSM, а не ланцюга.** Ланцюги перезшиваються від будь-якої правки в OSM
(хтось домалював стежку — два компоненти злилися), і прив'язка до них осиротила б прогрес при
кожному ребілді. Id лінії стабільний, поки лінію не розрізали. Та сама логіка, що з `lokalId`
Kartverket, і та сама чесно названа межа.

⚠️ **Назва йде в ДАНІ, тож вона одномовна** — норвезька, як і назви з Turrutebasen. Локалізувати
її нічим: у файлі лежить рядок, а не ключ. Тому форма описова («Sti ved X»), а не імітація
офіційної назви — щоб її не сплутати з маркованим маршрутом.
"""
import io
import json
import math

R = 6371008.8


def _hav(a, b):
    """Метри між (lon, lat)."""
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _line_len(coords):
    return sum(_hav(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def _cut(coords, target, min_tail):
    """Нарізка ламаної на шматки ~`target` м. Копія правила з `build_trails` — навмисно:
    ділянки обох джерел мусять бути одного розміру, інакше «12 з 74» означало б різне."""
    out, cur, acc = [], [coords[0]], 0.0
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        d = _hav(a, b)
        if d <= 0:
            continue
        while acc + d >= target:
            t = (target - acc) / d
            mid = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            cur.append(mid)
            out.append(cur)
            cur, acc = [mid], 0.0
            a, d = mid, _hav(mid, b)
        acc += d
        cur.append(b)
    if len(cur) >= 2:
        if out and _line_len(cur) < min_tail:
            out[-1].extend(cur[1:])      # короткий хвіст вливаємо в попередній
        else:
            out.append(cur)
    return out


# ⚠️ **Орієнтиром може бути лише ТОПОНІМ.** Перший прогін давав «Sti ved Gapahuk 2», «Sti ved
# Lavvo», «Sti ved Utsiktspunkt» і — найгірше — «Sti ved Abraham Bernhard Mahler» (це статуя).
# Причина: у POI-наборі поруч із власними назвами вершин лежать об'єкти, чия «назва» насправді є
# НАЗВОЮ ТИПУ. Стежка «біля гапахука» не орієнтує нікого: гапахуків багато, і жоден із них не є
# місцем на карті. Тому з POI беремо лише вершини (`peak` — справжні топоніми Stadnamn), а решту
# орієнтирів дають поселення. Перевірено на живих даних: `Sandhornet`, `Helgehornet`, `Volda`.
_TOPONYM_POI = {"peak"}


def _landmarks(path):
    """Орієнтири для назв: точки з ТОПОНІМОМ. Приймає `poi.geojson` (лише вершини) і
    `tettsteder.geojson` (для полігонів беремо центроїд-середнє — точності «біля чого це» досить)."""
    pts = []
    if not path:
        return pts
    for src in str(path).split(","):
        try:
            d = json.load(io.open(src.strip(), encoding="utf-8"))
        except Exception:
            continue
        for f in d.get("features", []):
            props = f.get("properties") or {}
            name = props.get("name") or ""
            if not name:
                continue
            # Файл POI має `type`; у tettsteder його немає — і всі вони топоніми за побудовою.
            if "type" in props and props.get("type") not in _TOPONYM_POI:
                continue
            g = f.get("geometry") or {}
            c = g.get("coordinates")
            t = g.get("type")
            if t == "Point":
                pts.append((c[0], c[1], name))
            elif t in ("Polygon", "MultiPolygon"):
                ring = c[0] if t == "Polygon" else c[0][0]
                xs = [p[0] for p in ring]
                ys = [p[1] for p in ring]
                pts.append((sum(xs) / len(xs), sum(ys) / len(ys), name))
    return pts


def build(osm_path, target_m, min_tail_m, min_chain_m, max_chain_m, landmarks=None):
    data = json.load(io.open(osm_path, encoding="utf-8"))
    ways = [w for w in data.get("elements", []) if w.get("geometry") and w.get("nodes")]

    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w in ways:
        ns = w["nodes"]
        for i in range(len(ns) - 1):
            union(ns[i], ns[i + 1])

    chains = {}
    for w in ways:
        coords = [(p["lon"], p["lat"]) for p in w["geometry"]]
        if len(coords) < 2:
            continue
        c = find(w["nodes"][0])
        ch = chains.setdefault(c, {"len": 0.0, "ways": []})
        ch["len"] += _line_len(coords)
        ch["ways"].append((w["id"], coords))

    kept = {c: v for c, v in chains.items() if min_chain_m <= v["len"] < max_chain_m}

    lm = _landmarks(landmarks)

    def name_for(ch):
        if not lm:
            return ""
        # Центр ланцюга — середнє по точках; «біля чого це» точнішого не потребує.
        xs = [p[0] for _, coords in ch["ways"] for p in coords]
        ys = [p[1] for _, coords in ch["ways"] for p in coords]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        best = min(lm, key=lambda p: _hav((cx, cy), (p[0], p[1])))
        return "Sti ved %s" % best[2]

    # Довші ланцюги першими: розрізнювач-номер тоді дістається коротшим, а найпомітніша стежка
    # біля орієнтира лишається без нього.
    order = sorted(kept.items(), key=lambda kv: -kv[1]["len"])
    used = {}
    feats = []
    stats = {"chains": len(kept), "km": sum(v["len"] for v in kept.values()) / 1000.0,
             "dropped_short": sum(1 for v in chains.values() if v["len"] < min_chain_m),
             "dropped_mesh": sum(1 for v in chains.values() if v["len"] >= max_chain_m),
             "segments": 0}
    for c, ch in order:
        base = name_for(ch)
        used[base] = used.get(base, 0) + 1
        name = base if used[base] == 1 else "%s %d" % (base, used[base])
        trail_id = "osm:%d" % min(wid for wid, _ in ch["ways"])
        for wid, coords in ch["ways"]:
            for i, seg in enumerate(_cut(coords, target_m, min_tail_m)):
                L = _line_len(seg)
                if L < 1.0:
                    continue
                feats.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString",
                                 "coordinates": [[round(x, 6), round(y, 6)] for x, y in seg]},
                    "properties": {
                        "seg": "osm%d:%d" % (wid, i),   # якір — лінія, не ланцюг (див. заголовок)
                        "trail": trail_id,
                        "name": name,
                        "len_m": round(L),
                        "src": "osm",
                    },
                })
                stats["segments"] += 1
    return feats, stats

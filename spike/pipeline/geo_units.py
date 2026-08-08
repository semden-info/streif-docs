# -*- coding: utf-8 -*-
"""Належність об'єкта до **географічної одиниці** — спільне ядро для стежок.

Навіщо окремий модуль. PIP по полігонах у цьому пайплайні вже написано **двічі**: у
`retag_kommune.py` (класи `Poly`/`Kommune`, межі комун) і всередині `build_trails.py` (`_inside`,
фільтр «поза містом»). Третя копія — під тегування стежок комуною — зробила б із цього те саме
**дзеркало**, яке проєкт уже ловив у схемі категорій: три місця рахують «те саме» і колись
розходяться. Тому логіка живе тут, а `build_trails.py` (канонічний шлях) і `retag_trails.py`
(разовий міст над живим файлом) її **імпортують**.

⚠️ `retag_kommune.py` свідомо НЕ чіпаємо — це заморожений разовий скрипт, який уже відпрацював по
продакшн-тайлах; переписувати його заднім числом означало б ризикувати відтворюваністю того, що вже
залито.

**Правило належності — БІЛЬША ЧАСТИНА ДОВЖИНИ маршруту**, те саме, що у фільтрі «стежки лише поза
містом» (D34, 2026-08-07). Різати маршрут по межі не можна: у маршруту «з міста в гори» змінився б
знаменник «N з M», а прогрес на відрізаних ділянках осиротів би **посеред** пройденого.

Ліцензія меж: Kartverket kommuneinfo (відкритий GET).
"""
import io
import json
import gzip
import os
import time
import urllib.request

KOMMUNEINFO = "https://ws.geonorge.no/kommuneinfo/v1/kommuner/{code}/omrade?utkoordsys=4258"
PUNKT = "https://ws.geonorge.no/kommuneinfo/v1/punkt?nord={lat}&ost={lon}&koordsys=4258"
UA = "Streif-pipeline/0.1 (contact@semden.info)"


# ── мережа з кешем на диску: сервіс Kartverket не смикаємо повторно ───────────────────────────────
def fetch(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return open(path, "rb").read()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            open(path, "wb").write(raw)
            return raw
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


class Area:
    """Полігон(и) з дірками + bbox-відсів. `contains(lon, lat)` — ray casting.

    Дірки обов'язкові: без них фіорд усередині комуни рахувався б її частиною. Смугового індексу
    тут немає навмисно — на 978 ділянках проти двох-трьох меж він не окупається (у `retag_kommune`
    точок було 236 тисяч, і там він потрібен).
    """

    def __init__(self, geom):
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        self.polys = []
        for poly in polys:
            rings = [[(float(p[0]), float(p[1])) for p in ring] for ring in poly]
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            self.polys.append((rings, (min(xs), min(ys), max(xs), max(ys))))

    @staticmethod
    def _inside(x, y, ring):
        c, n, j = False, len(ring), len(ring) - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
                c = not c
            j = i
        return c

    def contains(self, x, y):
        for rings, bb in self.polys:
            if not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
                continue
            if not self._inside(x, y, rings[0]):
                continue
            if any(self._inside(x, y, h) for h in rings[1:]):
                continue
            return True
        return False


def load_kommune(code, cache):
    """Офіційна межа комуни → (name, Area). Кешується на диску."""
    j = json.loads(fetch(KOMMUNEINFO.format(code=code),
                         os.path.join(cache, "kommune_%s.json" % code)).decode("utf-8"))
    return j.get("kommunenavn", ""), Area(j["omrade"])


def punkt_kommune(lon, lat, cache):
    """Яка комуна в цій точці (kommuneinfo `punkt`) → (код, назва) або (None, None).

    Потрібне для **автовиявлення**: bbox джерела — прямокутник, тож у набір заходять сусідні
    комуни, яких у списку не було. Без цього маршрут в Ulstein лишився б без одиниці, а прогрес на
    ньому — недосяжним із UI.
    """
    try:
        j = json.loads(fetch(PUNKT.format(lat="%.6f" % lat, lon="%.6f" % lon),
                             os.path.join(cache, "punkt_%.5f_%.5f.json" % (lat, lon))).decode("utf-8"))
        code = str(j.get("kommunenummer") or "").strip()
        return (code or None), (j.get("kommunenavn") or "")
    except Exception:
        return None, None


def _mid(feature):
    c = feature["geometry"]["coordinates"]
    return c[len(c) // 2]


def tag_routes_by_kommune(features, seed_codes, cache, discover=True, log=print):
    """Проставити `kommune`/`kommune_name` КОЖНІЙ фічі за комуною її МАРШРУТУ.

    @param features   список фіч `trails.geojson` (правиться на місці).
    @param seed_codes коди, з яких починаємо (напр. `["1577", "1520"]`).
    @param discover   доганяти сусідів через `punkt` для маршрутів, що не лягли в жодну відому межу.

    Повертає звіт `{код: {"name", "routes", "segments", "km"}}` + ключ `""` для нерозпізнаних.

    ⚠️ Одиниця рахується по маршруту ЦІЛКОМ, а тег кладеться на кожну ділянку: на клієнті ділянка —
    те, що приходить із файла, а маршрут збирається з ділянок, тож тег мусить бути там, де його
    прочитають.
    """
    os.makedirs(cache, exist_ok=True)
    koms = {}
    for code in seed_codes:
        name, area = load_kommune(code, cache)
        koms[code] = (name, area)
        log("  межа %s %s" % (code, name))

    # 1) розкладка довжин: маршрут → {код: метри} + невідоме
    routes = {}
    for f in features:
        p = f["properties"]
        L = float(p.get("len_m") or 0)
        r = routes.setdefault(p.get("trail", ""), {"by": {}, "unknown": 0.0, "feats": [],
                                                   "name": p.get("name", "")})
        r["feats"].append(f)
        lon, lat = _mid(f)
        hit = None
        for code, (_, area) in koms.items():
            if area.contains(lon, lat):
                hit = code
                break
        if hit:
            r["by"][hit] = r["by"].get(hit, 0.0) + L
        else:
            r["unknown"] += L

    # 2) автовиявлення: маршрут, більшість якого поза відомими межами, питає kommuneinfo про свою
    #    середню ділянку — і знайдена комуна стає повноцінним кандидатом для ВСІХ маршрутів.
    if discover:
        added = []
        for tid, r in routes.items():
            best = max(r["by"].values()) if r["by"] else 0.0
            if r["unknown"] <= best:
                continue
            mid_feat = r["feats"][len(r["feats"]) // 2]
            lon, lat = _mid(mid_feat)
            code, name = punkt_kommune(lon, lat, cache)
            if code and code not in koms:
                nm, area = load_kommune(code, cache)
                koms[code] = (nm or name, area)
                added.append("%s %s" % (code, nm or name))
        if added:
            log("  автовиявлено сусідів: %s" % ", ".join(sorted(set(added))))
            # перерахунок ПОВНІСТЮ, а не лише «сиротам»: нова межа може забрати ділянки й у тих
            # маршрутів, які вже мали більшість, — інакше сума по одиницях перестала б сходитись.
            for r in routes.values():
                r["by"], r["unknown"] = {}, 0.0
                for f in r["feats"]:
                    L = float(f["properties"].get("len_m") or 0)
                    lon, lat = _mid(f)
                    hit = None
                    for code, (_, area) in koms.items():
                        if area.contains(lon, lat):
                            hit = code
                            break
                    if hit:
                        r["by"][hit] = r["by"].get(hit, 0.0) + L
                    else:
                        r["unknown"] += L

    # 3) тег на кожну фічу маршруту-переможця
    report = {}
    for tid, r in routes.items():
        code, L = "", r["unknown"]
        for c, v in sorted(r["by"].items()):
            if v > L:
                code, L = c, v
        name = koms[code][0] if code in koms else ""
        km = sum(float(f["properties"].get("len_m") or 0) for f in r["feats"]) / 1000.0
        for f in r["feats"]:
            # Порожній рядок, а не відсутній ключ: клієнт читає `optString`, і «нема одиниці» має
            # бути станом, який видно, а не мовчазною діркою.
            f["properties"]["kommune"] = code
            f["properties"]["kommune_name"] = name
        e = report.setdefault(code, {"name": name, "routes": 0, "segments": 0, "km": 0.0})
        e["routes"] += 1
        e["segments"] += len(r["feats"])
        e["km"] += km
    return report


def print_report(report, log=print):
    log("")
    log("одиниця маршруту (більша частина довжини):")
    for code in sorted(report, key=lambda c: -report[c]["km"]):
        e = report[code]
        title = ("%s %s" % (code, e["name"])).strip() if code else "— без одиниці —"
        log("  %-22s маршрутів %3d · ділянок %4d · %6.1f км"
            % (title[:22], e["routes"], e["segments"], e["km"]))
    lost = report.get("")
    if lost:
        # ⚠️ Кажемо вголос: маршрут без одиниці не покажеться в шторці НІДЕ — прогрес на ньому
        # лишиться в Room, але дістатись до нього буде нічим.
        log("  ⚠️ %d маршрутів без одиниці — у шторці вони не з'являться в жодній вкладці"
            % lost["routes"])

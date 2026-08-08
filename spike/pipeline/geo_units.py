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
import math
import os
import time
import urllib.request

KOMMUNEINFO = "https://ws.geonorge.no/kommuneinfo/v1/kommuner/{code}/omrade?utkoordsys=4258"
PUNKT = "https://ws.geonorge.no/kommuneinfo/v1/punkt?nord={lat}&ost={lon}&koordsys=4258"
UA = "Streif-pipeline/0.1 (contact@semden.info)"

# Скільки разів доганяти сусідів. Стеля, а не очікування: раунди сходяться за один-два (кожен
# додає щонайменше одну комуну), а без стелі помилка в даних дала б нескінченний цикл із запитами
# до чужого сервісу.
MAX_DISCOVER_ROUNDS = 6


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


R_EARTH = 6371008.8


def _hav(a, b):
    """Метри між (lon, lat)."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def _mid(feature):
    """Точка на ПОЛОВИНІ ДОВЖИНИ ділянки — не середній вузол за індексом.

    ⚠️ Різниця не теоретична (знахідка review 5). Вузли в джерелі стоять нерівномірно — там, де
    рельєф складніший, густіше (це прямо записано в `build_trails.cut`). Тому «середній вузол»
    зміщений у бік густої частини, і на прикордонній ділянці це віддає ЦІЛУ її довжину не тій
    комуні. Для маршруту, близького до 50/50, кількох таких ділянок досить, щоб перевернути тег
    цілого маршруту.

    Половина довжини такого зсуву не має: вона за побудовою ділить ділянку навпіл по метрах.
    """
    c = feature["geometry"]["coordinates"]
    if len(c) < 2:
        return c[0]
    half = sum(_hav(c[i], c[i + 1]) for i in range(len(c) - 1)) / 2.0
    acc = 0.0
    for i in range(len(c) - 1):
        d = _hav(c[i], c[i + 1])
        if acc + d >= half:
            t = (half - acc) / d if d > 0 else 0.0
            return (c[i][0] + (c[i + 1][0] - c[i][0]) * t,
                    c[i][1] + (c[i + 1][1] - c[i][1]) * t)
        acc += d
    return c[-1]


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
        r = routes.setdefault(p.get("trail", ""), {"by": {}, "unknown": 0.0, "feats": [],
                                                   "orphans": [], "name": p.get("name", "")})
        r["feats"].append(f)

    def assign():
        """Перекласти ділянки по комунах наново. Тримає й список НЕРОЗПІЗНАНИХ фіч."""
        for r in routes.values():
            r["by"], r["unknown"], r["orphans"] = {}, 0.0, []
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
                    r["orphans"].append(f)

    assign()

    # 2) автовиявлення сусідів. bbox джерела — прямокутник, тож у набір заходять комуни, яких у
    #    списку не було; без них маршрут лишиться без одиниці, а прогрес на ньому — недосяжним.
    #
    # ⚠️ **Раундами, поки знаходяться нові** (знахідка review 4). Один раунд ламався на маршруті,
    # що виходить із комуни й повертається: питали СЕРЕДНЮ ділянку, знаходили комуну B, а більшість
    # лишалась у нерозпізнаній A — і маршрут діставав порожній тег. Тепер питаємо саме НЕРОЗПІЗНАНУ
    # ділянку, і після кожного додавання перекладаємо все наново.
    if discover:
        for _round in range(MAX_DISCOVER_ROUNDS):
            added = []
            for r in routes.values():
                best = max(r["by"].values()) if r["by"] else 0.0
                if r["unknown"] <= best or not r["orphans"]:
                    continue
                lon, lat = _mid(r["orphans"][len(r["orphans"]) // 2])
                code, name = punkt_kommune(lon, lat, cache)
                if code and code not in koms:
                    nm, area = load_kommune(code, cache)
                    koms[code] = (nm or name, area)
                    added.append("%s %s" % (code, nm or name))
            if not added:
                break
            log("  автовиявлено сусідів: %s" % ", ".join(sorted(set(added))))
            # Перекладаємо ПОВНІСТЮ, а не лише «сиротам»: нова межа може забрати ділянки й у тих
            # маршрутів, які вже мали більшість, — інакше сума по одиницях перестала б сходитись.
            assign()

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


def _selftest():
    """`python geo_units.py --selftest` — перевірки БЕЗ мережі.

    ⚠️ Тестів у цього пайплайна не було взагалі, і review слушно на це вказало. Повного harness тут
    не заводимо (він потягнув би залежності в проєкт, де їх нема), але два правила, на яких усе
    тримається, мусять мати сторожа: середина рахується по ДОВЖИНІ, і належність — по більшій
    частині маршруту, а не по окремій ділянці.
    """
    ok = 0

    # 1) середина — по довжині, не по індексу вузла. Вузли згущені на початку: індексна середина
    #    лишилась би там, хоча майже вся довжина далі.
    f = {"geometry": {"coordinates": [[0.0, 62.0], [0.001, 62.0], [0.002, 62.0], [1.0, 62.0]]}}
    x, _ = _mid(f)
    assert x > 0.4, "середина за довжиною має бути посеред ДОВГОГО ребра, а не серед густих вузлів"
    assert f["geometry"]["coordinates"][2][0] == 0.002, "вхід не мутуємо"
    ok += 1

    # 2) вироджені входи не валять збірку
    assert _mid({"geometry": {"coordinates": [[5.0, 62.0]]}}) == [5.0, 62.0]
    ok += 1

    # 3) належність — по БІЛЬШІЙ ЧАСТИНІ довжини маршруту, а не по більшості ділянок.
    #    Дві короткі ділянки в A проти однієї довгої в B → маршрут B.
    class _FakeArea:
        def __init__(self, lo, hi):
            self.lo, self.hi = lo, hi

        def contains(self, x, y):
            return self.lo <= x < self.hi

    def feat(seg, x0, x1, length):
        return {"properties": {"seg": seg, "trail": "t", "name": "N", "len_m": length},
                "geometry": {"coordinates": [[x0, 62.0], [x1, 62.0]]}}

    feats = [feat("a", 0.0, 0.1, 100), feat("b", 0.1, 0.2, 100), feat("c", 1.0, 1.1, 900)]
    koms_backup = {"A": ("Альфа", _FakeArea(-1.0, 0.5)), "B": ("Бета", _FakeArea(0.5, 2.0))}

    global load_kommune
    real_load = load_kommune
    load_kommune = lambda code, cache: koms_backup[code]          # noqa: E731 — на час тесту
    try:
        rep = tag_routes_by_kommune(feats, ["A", "B"], cache=".", discover=False, log=lambda *_: None)
    finally:
        load_kommune = real_load
    assert [f["properties"]["kommune"] for f in feats] == ["B", "B", "B"], \
        "усі ділянки маршруту дістають ОДНУ комуну — ту, де більша частина довжини"
    assert set(rep) == {"B"} and rep["B"]["routes"] == 1 and rep["B"]["segments"] == 3
    ok += 1

    print("самоперевірка geo_units: %d із 3 OK" % ok)


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


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
        print("Це модуль. Перевірка: python geo_units.py --selftest")

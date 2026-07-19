# -*- coding: utf-8 -*-
"""
Streif P30 — РАЗОВИЙ міст: перетегування ВЖЕ ОПУБЛІКОВАНИХ тайлів комуною, без повного регену.

НАВІЩО (і чому це не канон):
    Канонічний шлях — `build_tiles.py --kommuner=1577:Volda,1520:Ørsta`, де комуна відома з
    ІНДЕКСУ пари вхідних файлів (вхід і так per-kommune). Але вхідні GML (Matrikkelen/OSM/Elveg)
    зникли з тимчасових тек, а перезавантаження дороге (Elveg — через order-API з поштою) І
    дало б ІНШИЙ зріз даних (OSM живий, Matrikkelen оновлюється) — тобто розійшлося б із
    продакшном по кількості будівель та accessible.
    Цей скрипт натомість бере САМІ продакшн-тайли з CDN і дописує лише `kommune`, зберігаючи
    ТОЧНУ парність із теперішнім продакшном (ті самі building_id / tettsted_id / accessible).
    Комуна тут визначається post-hoc — PIP по центроїду кільця в ОФІЦІЙНИХ межах Kartverket
    (kommuneinfo), бо походження будівлі з тайла вже не відновити.

ВХІД : CDN (manifest.json + area_*.geojson + tettsteder.geojson) + ws.geonorge.no/kommuneinfo
ВИХІД: OUTDIR/area_*.geojson (ПЕРЕДСТИСНЕНІ gzip, як крок 4 README) + manifest.json (плоский,
       + блок `byKommune`) + tettsteder.geojson (плоский, + `kommune`/`kommune_name`)

Usage (Windows: ЗАВЖДИ PYTHONIOENCODING=utf-8):
    python retag_kommune.py OUTDIR --cache=DIR --kommuner=1577:Volda,1520:Ørsta [--tol-m=150]
"""
import sys, os, json, gzip, math, time, urllib.request, urllib.error

CDN = "https://pub-b1c9ae365792405880b62e24ccda0df1.r2.dev"
KOMMUNEINFO = "https://ws.geonorge.no/kommuneinfo/v1/kommuner/{code}/omrade?utkoordsys=4258"
UA = "Streif-pipeline/0.1 (contact@semden.info)"
CATS = ["housing", "hytte", "public", "sacral", "outbuilding", "other"]
BAND = 0.005     # lat-смуга індексу ребер для PIP (град.)
CELL = 200.0     # клітинка грід-індексу для fallback-відстані (м)


# ---------- мережа (з кешем на диску — сервіси не смикаємо повторно) ----------
def fetch(url, path, binary=False):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return open(path, "rb").read()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)     # тайли на R2 передстиснені
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(raw)
            return raw
        except (urllib.error.URLError, OSError) as e:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


# ---------- геометрія: PIP з дірками + смуговий індекс ребер ----------
class Poly:
    """Один полігон (зовнішнє кільце + дірки) з lat-смуговим індексом ребер.
    Смуги роблять ray-cast ~O(кілька ребер) замість O(2314) на точку."""
    def __init__(self, rings):
        self.rings = rings
        self.bbox = self._bbox(rings[0])
        self.bands = [self._index(r) for r in rings]

    @staticmethod
    def _bbox(ring):
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return (min(xs), min(ys), max(xs), max(ys))

    @staticmethod
    def _index(ring):
        bands = {}
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % n]
            b0 = int(min(y1, y2) // BAND); b1 = int(max(y1, y2) // BAND)
            for b in range(b0, b1 + 1):
                bands.setdefault(b, []).append((x1, y1, x2, y2))
        return bands

    @staticmethod
    def _cross(x, y, edges):
        inside = False
        for x1, y1, x2, y2 in edges:
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        return inside

    def contains(self, x, y):
        bb = self.bbox
        if not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
            return False
        if not self._cross(x, y, self.bands[0].get(int(y // BAND), ())):
            return False
        for holes in self.bands[1:]:                      # дірка → точка НЕ в комуні
            if self._cross(x, y, holes.get(int(y // BAND), ())):
                return False
        return True


class Kommune:
    def __init__(self, code, name, geom, ref_lat):
        self.code = code; self.name = name
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        self.polys = [Poly([[(float(p[0]), float(p[1])) for p in ring] for ring in poly])
                      for poly in polys]
        # грід-індекс ВСІХ ребер (у метрах) — для fallback «найближча межа»
        self.kLon = 111320.0 * math.cos(math.radians(ref_lat)); self.kLat = 111320.0
        self.segs = []; self.grid = {}
        for poly in self.polys:
            for ring in poly.rings:
                for i in range(len(ring)):
                    a = ring[i]; b = ring[(i + 1) % len(ring)]
                    s = (a[0] * self.kLon, a[1] * self.kLat, b[0] * self.kLon, b[1] * self.kLat)
                    si = len(self.segs); self.segs.append(s)
                    cx0 = int(min(s[0], s[2]) // CELL); cx1 = int(max(s[0], s[2]) // CELL)
                    cy0 = int(min(s[1], s[3]) // CELL); cy1 = int(max(s[1], s[3]) // CELL)
                    if (cx1 - cx0) > 50 or (cy1 - cy0) > 50:     # довге ребро — не роздувати індекс
                        self.grid.setdefault("long", []).append(si); continue
                    for cx in range(cx0, cx1 + 1):
                        for cy in range(cy0, cy1 + 1):
                            self.grid.setdefault((cx, cy), []).append(si)

    def contains(self, x, y):
        return any(p.contains(x, y) for p in self.polys)

    def dist_m(self, lon, lat, tol):
        """Відстань до межі в метрах, але не далі tol (інакше None) — шукаємо лише в сусідніх клітинках."""
        px = lon * self.kLon; py = lat * self.kLat
        span = int(tol // CELL) + 1
        cx0 = int(px // CELL); cy0 = int(py // CELL)
        best = None
        cand = list(self.grid.get("long", ()))
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                cand += self.grid.get((cx0 + dx, cy0 + dy), ())
        for si in cand:
            ax, ay, bx, by = self.segs[si]
            ddx = bx - ax; ddy = by - ay; l2 = ddx * ddx + ddy * ddy
            t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((px - ax) * ddx + (py - ay) * ddy) / l2))
            ex = px - (ax + t * ddx); ey = py - (ay + t * ddy)
            d = math.hypot(ex, ey)
            if best is None or d < best:
                best = d
        return best if (best is not None and best <= tol) else None


def main():
    args = sys.argv[1:]
    outdir = None; cache = None; kommuner = []; tol = 150.0
    for a in args:
        if a.startswith("--cache="): cache = a[len("--cache="):]
        elif a.startswith("--tol-m="): tol = float(a[len("--tol-m="):])
        elif a.startswith("--kommuner="):
            for spec in a[len("--kommuner="):].split(","):
                spec = spec.strip()
                if spec:
                    code, _, nm = spec.partition(":")
                    kommuner.append((code.strip(), nm.strip()))
        else: outdir = a
    assert outdir and kommuner, __doc__
    cache = cache or os.path.join(outdir, "cdn-cache")
    os.makedirs(outdir, exist_ok=True)

    # 1) продакшн-манифест + тайли + tettsteder з CDN
    manifest = json.loads(fetch(f"{CDN}/manifest.json", os.path.join(cache, "manifest.json")))
    keys = [t["key"] for t in manifest["tiles"]]
    print(f"manifest: {len(keys)} тайлів, total={manifest['total']} accessible={manifest['accessible']}")
    raw_tiles = {}
    for i, k in enumerate(keys, 1):
        raw_tiles[k] = json.loads(fetch(f"{CDN}/{k}.geojson", os.path.join(cache, k + ".geojson")))
        if i % 100 == 0 or i == len(keys):
            print(f"  завантажено {i}/{len(keys)}")
    tett = json.loads(fetch(f"{CDN}/tettsteder.geojson", os.path.join(cache, "tettsteder.geojson")))
    print(f"tettsteder: {len(tett['features'])} поселень")

    # 2) офіційні межі комун (Kartverket kommuneinfo, відкритий GET; кеш на диску)
    koms = []
    for code, nm in kommuner:
        j = json.loads(fetch(KOMMUNEINFO.format(code=code), os.path.join(cache, f"kommune_{code}.json")))
        k = Kommune(code, nm or j.get("kommunenavn", ""), j["omrade"], 62.15)
        print(f"  межа {code} {k.name}: {len(k.polys)} полігон(ів), {len(k.segs)} ребер, "
              f"дірок {sum(len(p.rings) - 1 for p in k.polys)}")
        koms.append(k)

    # 3) PIP по центроїду кільця → kommune (fallback: найближча межа в межах tol)
    hits = {k.code: 0 for k in koms}; near = {k.code: 0 for k in koms}; untagged = 0
    for key, fc in raw_tiles.items():
        for f in fc["features"]:
            ring = f["geometry"]["coordinates"][0]
            n = len(ring) - 1 if ring[0] == ring[-1] and len(ring) > 1 else len(ring)
            cx = sum(p[0] for p in ring[:n]) / n
            cy = sum(p[1] for p in ring[:n]) / n
            code = None
            for k in koms:
                if k.contains(cx, cy):
                    code = k.code; hits[code] += 1; break
            if code is None:                                  # прибережна генералізація межі
                best = None
                for k in koms:
                    d = k.dist_m(cx, cy, tol)
                    if d is not None and (best is None or d < best[1]):
                        best = (k.code, d)
                if best:
                    code = best[0]; near[code] += 1
            if code:
                f["properties"]["kommune"] = code             # решта props недоторкана
            else:
                untagged += 1
    print("PIP: " + " · ".join(f"{k.code} {k.name} {hits[k.code]}+{near[k.code]}(fallback)" for k in koms)
          + f" | без тега {untagged}")

    # 4) manifest: byKommune ПОРЯД із наявними ключами (наявні не чіпаємо)
    byKom = {c: {"name": nm, "total": 0, "accessible": 0,
                 "byType": {c2: {"total": 0, "accessible": 0} for c2 in CATS}}
             for c, nm in kommuner}
    tett_votes = {}
    for fc in raw_tiles.values():
        for f in fc["features"]:
            p = f["properties"]; kc = p.get("kommune")
            tid = p.get("tettsted_id")
            if tid and kc:
                tett_votes.setdefault(tid, {})[kc] = tett_votes.setdefault(tid, {}).get(kc, 0) + 1
            if not kc: continue
            e = byKom.setdefault(kc, {"name": "", "total": 0, "accessible": 0,
                                      "byType": {c2: {"total": 0, "accessible": 0} for c2 in CATS}})
            d = e["byType"].setdefault(p["type"], {"total": 0, "accessible": 0})
            e["total"] += 1; d["total"] += 1
            if p["accessible"]: e["accessible"] += 1; d["accessible"] += 1
    manifest["byKommune"] = byKom

    # 5) tettsteder: мажоритарна комуна поселення (ties → менший код, як у build_tiles)
    tagged_t = 0
    for f in tett["features"]:
        v = tett_votes.get(f["properties"].get("tett_nr"))
        if v:
            kc = max(sorted(v), key=lambda x: v[x])
            f["properties"]["kommune"] = kc
            f["properties"]["kommune_name"] = dict(kommuner).get(kc, "")
            tagged_t += 1

    # 6) запис: тайли ПЕРЕДСТИСНЕНІ gzip, manifest/tettsteder — плоскі
    for key, fc in raw_tiles.items():
        body = json.dumps(fc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with gzip.GzipFile(os.path.join(outdir, key + ".geojson"), "wb", 9, mtime=0) as g:
            g.write(body)
    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(tett, open(os.path.join(outdir, "tettsteder.geojson"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # 7) ЗВІРКА (виводимо числа — це і є приймальний критерій)
    print("\n=== ЗВІРКА ===")
    ks = sum(e["total"] for e in byKom.values()); ka = sum(e["accessible"] for e in byKom.values())
    print(f"byKommune сума total      : {ks} vs manifest.total      {manifest['total']}  "
          f"{'OK' if ks == manifest['total'] else 'РОЗБІЖНІСТЬ'}")
    print(f"byKommune сума accessible : {ka} vs manifest.accessible {manifest['accessible']}  "
          f"{'OK' if ka == manifest['accessible'] else 'РОЗБІЖНІСТЬ'}")
    for c, e in byKom.items():
        print(f"  {c} {e['name']}: {e['total']}/{e['accessible']} "
              + " ".join(f"{t}={e['byType'][t]['total']}" for t in CATS))
    for t in CATS:
        s = sum(e["byType"][t]["total"] for e in byKom.values())
        sa = sum(e["byType"][t]["accessible"] for e in byKom.values())
        g = manifest["byType"][t]
        print(f"  byType {t:12s}: {s}/{sa} vs {g['total']}/{g['accessible']}  "
              f"{'OK' if (s, sa) == (g['total'], g['accessible']) else 'РОЗБІЖНІСТЬ'}")
    print(f"без kommune               : {untagged}")
    print(f"tettsteder з kommune      : {tagged_t}/{len(tett['features'])}")

    # gzip round-trip: кожен тайл читається назад і має ту саму кількість фіч
    bad = 0; feats = 0
    for t in manifest["tiles"]:
        p = os.path.join(outdir, t["key"] + ".geojson")
        try:
            fc = json.loads(gzip.open(p, "rb").read().decode("utf-8"))
            feats += len(fc["features"])
            if len(fc["features"]) != t["n"]: bad += 1
        except Exception:
            bad += 1
    print(f"тайли після gzip          : {len(manifest['tiles'])} файлів, {feats} фіч, "
          f"битих/розбіжних {bad}  {'OK' if bad == 0 and feats == manifest['total'] else 'РОЗБІЖНІСТЬ'}")
    print(f"вихід -> {outdir}")


if __name__ == "__main__":
    main()

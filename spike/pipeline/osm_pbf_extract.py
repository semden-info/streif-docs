# -*- coding: utf-8 -*-
"""
Streif — OSM .pbf → per-kommune JSON у ФОРМАТІ Overpass (той самий, що дає fetch_osm.py).

НАВІЩО: Overpass не тягне нац.масштаб (Ålesund: 504 на overpass-api.de, ~75 с на kumi лише
для count). Geofabrik-екстракт (напр. vestlandet-latest.osm.pbf) — офлайн, детермінований,
один файл на весь регіон. Ліцензія та сама (OSM ODbL).

ВИХІД — байт-у-байт сумісний із fetch_osm.py, щоб build_tiles.py НЕ міняти:
    {"elements": [
        {"type": "node", "id": <int>, "lon": <float>, "lat": <float>},
        {"type": "way",  "id": <int>, "nodes": [<int>...], "tags": {...}}
    ]}
build_tiles.parse_osm() будує nodes[id]→(lon,lat), потім way.nodes → кільце/полілінію;
теги, що реально читаються далі: building, amenity, tourism, shop, office (osm_classify)
та highway (WALKABLE-фільтр для D6-accessible). Ми віддаємо ВСІ теги way — надлишок дешевий
і лишає запас на майбутні класифікатори.

ВІДБІР way: є тег `building` АБО `highway` (як в Overpass-запиті fetch_osm.py:
  way["building"](area.k); way["highway"](area.k);). Фільтрацію highway за WALKABLE
робить build_tiles, ми її НЕ дублюємо (щоб не розійтися з Overpass-гілкою).

ПРИНАЛЕЖНІСТЬ ДО КОМУНИ: PIP центроїда way в ОФІЦІЙНИХ межах Kartverket
(ws.geonorge.no/kommuneinfo/.../omrade?utkoordsys=4258 — той самий сервіс і той самий
смуговий ray-cast, що в retag_kommune.py). Overpass-варіант різав по area admin_level=7;
різниця — на прибережній генералізації межі, тому є --tol-m (fallback «майже на межі»).
Way, що не влучив у жодну комуну, просто не потрапляє в жоден вихід.

Usage (Windows: ЗАВЖДИ PYTHONIOENCODING=utf-8):
    python osm_pbf_extract.py PBF OUTDIR --kommuner=1577,1520[,...] [--cache=DIR] [--tol-m=150]
      OUTDIR/osm_<nr>.json     — per-kommune Overpass-подібний JSON
"""
import sys, os, json, math, urllib.request

import osmium

KOMMUNEINFO = "https://ws.geonorge.no/kommuneinfo/v1/kommuner/{code}/omrade?utkoordsys=4258"
UA = "Streif-pipeline/0.1 (contact@semden.info)"
BAND = 0.005     # lat-смуга індексу ребер для PIP (град.) — як у retag_kommune.py
CELL = 200.0     # клітинка грід-індексу для fallback-відстані (м)


def fetch(url, path):
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        return open(path, "rb").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(raw)
    return raw


# ---------- PIP-межі (той самий підхід, що retag_kommune.py) ----------
class Poly:
    """Полігон (зовнішнє кільце + дірки) з lat-смуговим індексом ребер: ray-cast ~O(кілька ребер)."""

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
        xs0 = min(p.bbox[0] for p in self.polys); ys0 = min(p.bbox[1] for p in self.polys)
        xs1 = max(p.bbox[2] for p in self.polys); ys1 = max(p.bbox[3] for p in self.polys)
        self.bbox = (xs0, ys0, xs1, ys1)
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
        """Відстань до межі в метрах, але не далі tol (інакше None)."""
        px = lon * self.kLon; py = lat * self.kLat
        span = int(tol // CELL) + 1
        cx0 = int(px // CELL); cy0 = int(py // CELL)
        best = None
        cand = list(self.grid.get("long", ()))
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                cand += self.grid.get((cx0 + dx, cy0 + dy), ())
        for si in cand:
            x1, y1, x2, y2 = self.segs[si]
            ddx = x2 - x1; ddy = y2 - y1; l2 = ddx * ddx + ddy * ddy
            t = 0.0 if l2 <= 0 else max(0.0, min(1.0, ((px - x1) * ddx + (py - y1) * ddy) / l2))
            ex = px - (x1 + t * ddx); ey = py - (y1 + t * ddy)
            d = math.hypot(ex, ey)
            if best is None or d < best:
                best = d
        return best if (best is not None and best <= tol) else None


# ---------- читання pbf ----------
def extract(pbf, koms, tol_m):
    """Один прохід по pbf з кеш-індексом координат вузлів (flex_mem).
    Повертає {code: {"nodes": {id: (lon,lat)}, "ways": [dict]}}."""
    out = {k.code: {"nodes": {}, "ways": []} for k in koms}
    # спільний bbox усіх комун — дешевий ранній відсів (Vestlandet >> MR)
    bx0 = min(k.bbox[0] for k in koms); by0 = min(k.bbox[1] for k in koms)
    bx1 = max(k.bbox[2] for k in koms); by1 = max(k.bbox[3] for k in koms)

    fp = (osmium.FileProcessor(pbf)
          .with_locations("flex_mem")
          .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
          .with_filter(osmium.filter.KeyFilter("building", "highway")))

    seen = kept = 0
    for w in fp:
        seen += 1
        if seen % 200000 == 0:
            print("  ways scanned=%d kept=%d" % (seen, kept), flush=True)
        pts = []
        try:
            for n in w.nodes:
                if n.location.valid():
                    pts.append((n.ref, n.location.lon, n.location.lat))
        except Exception:
            continue
        if len(pts) < 2:
            continue
        cx = sum(p[1] for p in pts) / len(pts)
        cy = sum(p[2] for p in pts) / len(pts)
        if not (bx0 - 0.02 <= cx <= bx1 + 0.02 and by0 - 0.02 <= cy <= by1 + 0.02):
            continue
        code = None
        for k in koms:
            if k.contains(cx, cy):
                code = k.code; break
        if code is None and tol_m > 0:                    # прибережна генералізація межі
            best = None
            for k in koms:
                d = k.dist_m(cx, cy, tol_m)
                if d is not None and (best is None or d < best[0]):
                    best = (d, k.code)
            if best:
                code = best[1]
        if code is None:
            continue
        kept += 1
        bucket = out[code]
        for nid, lon, lat in pts:
            bucket["nodes"][nid] = (lon, lat)
        bucket["ways"].append({"type": "way", "id": w.id,
                               "nodes": [p[0] for p in pts],
                               "tags": dict(w.tags)})
    print("  ways scanned=%d kept=%d" % (seen, kept), flush=True)
    return out


def main(argv):
    pbf = outdir = None; codes = []; cache = None; tol = 150.0
    for a in argv:
        if a.startswith("--kommuner="):
            codes = [c.strip() for c in a.split("=", 1)[1].split(",") if c.strip()]
        elif a.startswith("--cache="):
            cache = a.split("=", 1)[1]
        elif a.startswith("--tol-m="):
            tol = float(a.split("=", 1)[1])
        elif pbf is None:
            pbf = a
        else:
            outdir = a
    assert pbf and outdir and codes, __doc__
    os.makedirs(outdir, exist_ok=True)
    cache = cache or os.path.join(outdir, "kommune-cache")

    koms = []
    for code in codes:
        j = json.loads(fetch(KOMMUNEINFO.format(code=code),
                             os.path.join(cache, "kommune_%s.json" % code)))
        k = Kommune(code, j.get("kommunenavn", ""), j["omrade"], 62.7)
        print("  межа %s %-14s %2d полігон(ів), %6d ребер" % (k.code, k.name, len(k.polys), len(k.segs)),
              flush=True)
        koms.append(k)

    print("читаю %s (%.1f МБ) …" % (os.path.basename(pbf), os.path.getsize(pbf) / 1024 / 1024), flush=True)
    res = extract(pbf, koms, tol)

    print("%-6s %-14s %8s %8s %8s %9s" % ("nr", "kommune", "ways", "build", "highw", "KB"))
    for k in koms:
        r = res[k.code]
        els = [{"type": "node", "id": nid, "lon": lo, "lat": la}
               for nid, (lo, la) in r["nodes"].items()] + r["ways"]
        path = os.path.join(outdir, "osm_%s.json" % k.code)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"elements": els}, f, ensure_ascii=False)
        nb = sum(1 for w in r["ways"] if "building" in w["tags"])
        nh = sum(1 for w in r["ways"] if "highway" in w["tags"])
        print("%-6s %-14s %8d %8d %8d %9.1f" % (k.code, k.name, len(r["ways"]), nb, nh,
                                                os.path.getsize(path) / 1024), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

# -*- coding: utf-8 -*-
"""
Fetch curated "interesting places" (POI) from OSM/Overpass for Norwegian kommuner -> raw JSON.
Nature-v1 points-only (D34, post-codex-review). ODbL — attribution © OpenStreetMap.

Куратний набір типів (не «кожна точка» — codex: почати лін, 1 джерело + require-name):
  viewpoint · cultural/historic · church · badeplass · hut/shelter · peak.
build_poi.py категоризує, вимагає name, дедупить, тегує city/nature (tettsteder PIP),
додає провенанс per-feature.

usage: python fetch_poi.py OUT.json [KOMM1 KOMM2 ...]   (default 1577 1520 = Volda+Ørsta)
"""
import sys, json, time, urllib.request, urllib.parse

out = sys.argv[1] if len(sys.argv) > 1 else "poi_raw.json"
komm = sys.argv[2:] if len(sys.argv) > 2 else ["1577", "1520"]
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
areas = "".join(f'area["admin_level"="7"]["ref"="{k}"];' for k in komm)
q = f'''[out:json][timeout:180];
({areas})->.a;
(
 nwr["tourism"~"^(viewpoint|artwork|alpine_hut|wilderness_hut)$"](area.a);
 nwr["historic"]["name"](area.a);
 nwr["amenity"~"^(place_of_worship|shelter)$"](area.a);
 nwr["natural"~"^(peak|beach)$"](area.a);
 nwr["leisure"="beach_resort"](area.a);
 way["building"="church"]["name"](area.a);
);
out tags center;'''
data = urllib.parse.urlencode({"data": q}).encode()
for m in MIRRORS:
    try:
        print(f"try {m} …", flush=True)
        req = urllib.request.Request(m, data=data,
            headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
        with urllib.request.urlopen(req, timeout=200) as r:
            raw = r.read()
        j = json.loads(raw)
        n = len(j.get("elements", []))
        print(f"OK: {n} elements ({len(raw)//1024} KB) -> {out}", flush=True)
        open(out, "wb").write(raw)
        sys.exit(0 if n else 2)
    except Exception as e:
        print(f"  fail: {e}", flush=True); time.sleep(3)
print("ALL MIRRORS FAILED", flush=True); sys.exit(1)

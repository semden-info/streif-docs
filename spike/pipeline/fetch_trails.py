# -*- coding: utf-8 -*-
"""
Fetch walkable trail network (OSM) for the POI **safety gate** (D34 ⑧ / safe-allowlist).
Nature-POI зараховуємо до тесту лише якщо місце **досяжне пішки по стежці/дорозі** —
цей файл дає геометрію мережі, `build_poi.py --safe` міряє до неї відстань.

Тягне: пішохідні/стежкові `highway`-ways + relation `route=hiking` (маркований маршрут =
сильніший сигнал «людське місце, а не стіна»). ODbL — атрибуція © OpenStreetMap.

usage: python fetch_trails.py OUT.json [KOMM1 KOMM2 ...]   (default 1577 1520 = Volda+Ørsta)
"""
import sys, json, time, urllib.request, urllib.parse

out = sys.argv[1] if len(sys.argv) > 1 else "trails_raw.json"
komm = sys.argv[2:] if len(sys.argv) > 2 else ["1577", "1520"]
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
areas = "".join(f'area["admin_level"="7"]["ref"="{k}"];' for k in komm)
q = f'''[out:json][timeout:300];
({areas})->.a;
(
 way["highway"~"^(path|footway|track|steps|pedestrian|cycleway|residential|living_street|service|unclassified|tertiary)$"](area.a);
 relation["route"="hiking"](area.a);
);
out geom;'''
data = urllib.parse.urlencode({"data": q}).encode()
for m in MIRRORS:
    try:
        print(f"try {m} …", flush=True)
        req = urllib.request.Request(m, data=data,
            headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
        with urllib.request.urlopen(req, timeout=320) as r:
            raw = r.read()
        j = json.loads(raw)
        els = j.get("elements", [])
        ways = sum(1 for e in els if e.get("type") == "way")
        rels = sum(1 for e in els if e.get("type") == "relation")
        print(f"OK: {ways} ways + {rels} hiking-routes ({len(raw)//1024} KB) -> {out}", flush=True)
        open(out, "wb").write(raw)
        sys.exit(0 if els else 2)
    except Exception as e:
        print(f"  fail: {e}", flush=True); time.sleep(3)
print("ALL MIRRORS FAILED", flush=True); sys.exit(1)

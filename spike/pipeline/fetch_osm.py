# -*- coding: utf-8 -*-
"""Fetch OSM buildings+highways for a Norwegian kommune via Overpass area query -> raw JSON."""
import sys, json, time, urllib.request, urllib.parse

komm = sys.argv[1] if len(sys.argv) > 1 else "1577"
out = sys.argv[2]
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
# Norwegian kommune boundary: admin_level=7, ref=<nr>. Fetch buildings + highways clipped to it.
q = f'''[out:json][timeout:240];
area["admin_level"="7"]["ref"="{komm}"]->.k;
(way["building"](area.k);
 way["highway"](area.k););
out body; >; out skel qt;'''
data = urllib.parse.urlencode({"data": q}).encode()
for m in MIRRORS:
    try:
        print(f"try {m} ...", flush=True)
        req = urllib.request.Request(m, data=data,
            headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
        with urllib.request.urlopen(req, timeout=260) as r:
            raw = r.read()
        j = json.loads(raw)
        els = j.get("elements", [])
        nb = sum(1 for e in els if e.get("type") == "way" and "building" in e.get("tags", {}))
        nh = sum(1 for e in els if e.get("type") == "way" and "highway" in e.get("tags", {}))
        print(f"OK: {len(els)} elements ({len(raw)//1024} KB) | buildings={nb} highways={nh}", flush=True)
        open(out, "wb").write(raw)
        sys.exit(0)
    except Exception as e:
        print(f"  fail: {e}", flush=True)
        time.sleep(3)
print("ALL MIRRORS FAILED", flush=True)
sys.exit(1)

# -*- coding: utf-8 -*-
"""
Fetch SSB Tettsteder polygons (P20) for a bbox via SSB's own MapServer WFS -> GML.

Data-спайк 2026-07-11: SSB Tettsteder (Geonorge UUID 173f4a15-dead-4f82-b92e-f37396b72cea,
власник Statistisk sentralbyrå, ліцензія NLOD — відкрита, атрибуція) НЕ віддається через
Geonorge nedlasting API (capabilities 404 для цього датасету) — SSB хостить власний WFS:
  https://kart.ssb.no/api/mapserver/v1/wfs/tettsteder
Типи per-year: ms:tettsted_2016 … ms:tettsted_2025 (щорічне оновлення). Вихід — GML 3.2,
EPSG:4326 напряму (axis lat,lon — build_tiles.parse_tettsteder міняє на lon,lat).

Кожен tettsted несе: tett_nr (стабільний SSB tettstednummer), tettstedsnavn, befolkning_tettsted.

usage: python fetch_tettsteder.py OUT.gml [YEAR] [MINLON MINLAT MAXLON MAXLAT]
  default YEAR=2025, bbox = Volda/Ørsta регіон (5.6..6.6E, 61.9..62.5N).
"""
import sys, urllib.request, urllib.parse

WFS = "https://kart.ssb.no/api/mapserver/v1/wfs/tettsteder"

out = sys.argv[1] if len(sys.argv) > 1 else "tettsteder.gml"
year = sys.argv[2] if len(sys.argv) > 2 else "2025"
# bbox за замовч. накриває Volda+Ørsta (+сусідні tettsteder регіону); WFS 2.0 з urn-CRS = axis lat,lon
if len(sys.argv) >= 7:
    minlon, minlat, maxlon, maxlat = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
else:
    minlon, minlat, maxlon, maxlat = "5.6", "61.9", "6.6", "62.5"

params = {
    "service": "WFS", "version": "2.0.0", "request": "GetFeature",
    "typenames": f"ms:tettsted_{year}",
    "srsName": "urn:ogc:def:crs:EPSG::4326",
    # urn-CRS => axis order lat,lon => bbox = minLat,minLon,maxLat,maxLon,CRS
    "bbox": f"{minlat},{minlon},{maxlat},{maxlon},urn:ogc:def:crs:EPSG::4326",
}
url = WFS + "?" + urllib.parse.urlencode(params)
req = urllib.request.Request(url, headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
print(f"GET tettsted_{year} bbox=({minlon},{minlat})..({maxlon},{maxlat}) …", flush=True)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
except Exception as e:
    print(f"FAILED: {e}", flush=True); sys.exit(1)
n = raw.count(f"<ms:tettsted_{year}".encode())
open(out, "wb").write(raw)
print(f"OK: {len(raw)//1024} KB -> {out} | {n} tettsteder", flush=True)
if n == 0:
    print("WARN: 0 tettsteder — перевір рік/bbox (можливо, ms:tettsted_<year> не існує)", flush=True)
    sys.exit(2)

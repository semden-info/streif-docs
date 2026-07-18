# -*- coding: utf-8 -*-
"""
Fetch Naturbase «kartlagte friluftslivsområder» (Miljødirektoratet) -> raw GeoJSON.
Джерело badeplass-POI для Nature-v1 (D34): офіційно закартовані зони відпочинку —
на відміну від OSM, badeplass тут мають **назву + опис + verdi** (сигнал курації).

Ліцензія: **NLOD 2.0** (Norsk lisens for offentlige data) — атрибуція **© Miljødirektoratet**.
Ключ не потрібен; ArcGIS REST (MapServer/1 = friluftsliv_kartlagt_omrtype, polygon).
Поля: omraadenavn · omraadetype · omraadeverdi · omraadebeskrivelse · kommune(Navn) ·
      kartlagtFOID (стабільний Naturbase-id, напр. FK00016784) · faktaark · tilrettelegging.

Цей скрипт тягне **усі** закартовані зони комун (385 для 1577+1520) — фільтр «що є badeplass»
робить `build_poi.py --naturbase=…` (як fetch_poi.py=сирі дані / build_poi.py=курація).

usage: python fetch_naturbase.py OUT.json [KOMM1 KOMM2 ...]   (default 1577 1520 = Volda+Ørsta)
"""
import sys, json, urllib.request, urllib.parse

URL = ("https://kart.miljodirektoratet.no/arcgis/rest/services/"
       "friluftsliv_kartlagt/MapServer/1/query")
FIELDS = ("omraadenavn,omraadetype,omraadeverdi,omraadebeskrivelse,"
          "kommune,kommuneNavn,kartlagtFOID,faktaark,tilrettelegging,tilgjengelighet")
PAGE = 1000                                  # maxRecordCount сервера = 2000

out = sys.argv[1] if len(sys.argv) > 1 else "naturbase.json"
komm = sys.argv[2:] if len(sys.argv) > 2 else ["1577", "1520"]
where = "kommune IN (%s)" % ",".join("'%s'" % k for k in komm)

feats, offset = [], 0
while True:
    p = {"where": where, "outFields": FIELDS, "returnGeometry": "true",
         "outSR": "4326", "f": "geojson",
         "resultOffset": str(offset), "resultRecordCount": str(PAGE)}
    try:
        print(f"GET Naturbase {where} offset={offset} …", flush=True)
        req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(p),
            headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
        with urllib.request.urlopen(req, timeout=180) as r:
            j = json.loads(r.read())
    except Exception as e:
        print(f"FAILED: {e}", flush=True); sys.exit(1)
    if j.get("error"):
        print(f"FAILED: {j['error']}", flush=True); sys.exit(1)
    page = j.get("features", [])
    feats += page
    if len(page) < PAGE: break              # остання сторінка
    offset += PAGE

fc = {"type": "FeatureCollection",
      "attribution": "© Miljødirektoratet (Naturbase, NLOD 2.0)",
      "features": feats}
raw = json.dumps(fc, ensure_ascii=False).encode("utf-8")
open(out, "wb").write(raw)
poly = sum(1 for f in feats if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon"))
print(f"OK: {len(feats)} områder ({poly} полігонів, {len(raw)//1024} KB) -> {out}", flush=True)
sys.exit(0 if feats else 2)

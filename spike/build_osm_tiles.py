#!/usr/bin/env python3
"""
Spike 1 (варіант B, OSM): volda.osm -> buildings.geojson -> buildings.pmtiles.
Усе на GDAL (без tippecanoe, без geopandas). Запуск у GDAL-контейнері.
"""
import subprocess, os, json
from collections import Counter

WORK = "/work"
OSM = f"{WORK}/volda.osm"
RAW = f"{WORK}/_raw.geojson"
GEOJSON = f"{WORK}/buildings.geojson"
PMTILES = f"{WORK}/buildings.pmtiles"

COLS = "building,amenity,shop,office,tourism,leisure,historic,man_made,name,osm_way_id,osm_id"


def classify(p):
    b = (p.get("building") or "").lower()
    am = (p.get("amenity") or "").lower()
    tour = (p.get("tourism") or "").lower()
    if b in ("church", "chapel", "cathedral", "mosque", "temple", "synagogue",
             "shrine", "monastery") or am == "place_of_worship":
        return "sacral"
    if b in ("cabin", "hut", "chalet") or tour in ("chalet", "alpine_hut", "wilderness_hut"):
        return "hytte"
    if b in ("house", "detached", "residential", "apartments", "terrace",
             "semidetached_house", "bungalow", "dormitory", "houseboat",
             "static_caravan", "farm"):
        return "housing"
    if b in ("garage", "garages", "shed", "barn", "farm_auxiliary", "carport",
             "greenhouse", "industrial", "warehouse", "service", "hangar",
             "stable", "sty", "cowshed", "silo", "storage_tank", "roof"):
        return "outbuilding"
    if b in ("commercial", "retail", "office", "school", "kindergarten",
             "university", "college", "hospital", "public", "civic", "hotel",
             "sports_centre", "sports_hall", "train_station", "transportation",
             "government", "fire_station"):
        return "public"
    if b in ("yes", ""):  # generic — уточнюємо за функцією
        if (am in ("school", "kindergarten", "university", "college", "hospital",
                   "townhall", "library", "community_centre", "fire_station", "police")
                or p.get("shop") or p.get("office")
                or tour in ("hotel", "hostel", "guest_house")):
            return "public"
    return "other"


# 1. OSM multipolygons (building) -> сирий GeoJSON
if os.path.exists(RAW):
    os.remove(RAW)
subprocess.run([
    "ogr2ogr", "-f", "GeoJSON", RAW, OSM, "multipolygons",
    "-where", "building IS NOT NULL AND building <> 'no'",
    "-select", COLS,
], check=True)

# 2. класифікація -> чистий GeoJSON (type + building_id)
gj = json.load(open(RAW))
feats = gj.get("features", [])
out = []
for i, f in enumerate(feats):
    p = f.get("properties", {}) or {}
    bid = p.get("osm_way_id") or p.get("osm_id") or f"v{i}"
    f["properties"] = {"building_id": str(bid), "type": classify(p)}
    if f.get("geometry"):
        out.append(f)

json.dump({"type": "FeatureCollection", "features": out},
          open(GEOJSON, "w"), ensure_ascii=False)

print("buildings:", len(out))
print("by type:", dict(Counter(f["properties"]["type"] for f in out)))

# 3. GeoJSON -> PMTiles (GDAL)
if os.path.exists(PMTILES):
    os.remove(PMTILES)
subprocess.run([
    "ogr2ogr", "-f", "PMTiles", PMTILES, GEOJSON,
    "-nln", "buildings",
    "-dsco", "MINZOOM=11", "-dsco", "MAXZOOM=16",
], check=True)
print("wrote", PMTILES, "(", os.path.getsize(PMTILES), "bytes )")

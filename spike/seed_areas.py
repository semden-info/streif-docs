#!/usr/bin/env python3
"""
Пре-сід on-demand-кешу: розбити buildings_multicity.geojson на per-tile файли у форматі
AreaCache (тайл 0.05°, ключ як у Kotlin: Math.round = floor(x/0.05 + 0.5)).
Вихід: seed_areas/area_<la>_<lo>.geojson — пушиться в files/areas/ на пристрої.
"""
import json, math, os, glob
from collections import defaultdict

TILE = 0.05
base = os.path.dirname(os.path.abspath(__file__))
out_dir = os.path.join(base, "seed_areas")
os.makedirs(out_dir, exist_ok=True)
for f in glob.glob(os.path.join(out_dir, "*.geojson")):
    os.remove(f)


def centroid(geom):
    if geom["type"] == "MultiPolygon":
        ring = geom["coordinates"][0][0]
    elif geom["type"] == "Polygon":
        ring = geom["coordinates"][0]
    else:
        return None
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def tile_key(lat, lon):
    la = math.floor(lat / TILE + 0.5)   # = Kotlin Math.round(lat/TILE)
    lo = math.floor(lon / TILE + 0.5)
    return la, lo


gj = json.load(open(os.path.join(base, "buildings_multicity.geojson"), encoding="utf-8"))
buckets = defaultdict(list)
for feat in gj["features"]:
    c = centroid(feat["geometry"])
    if not c:
        continue
    buckets[tile_key(c[1], c[0])].append(feat)

for (la, lo), feats in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
    name = f"area_{la}_{lo}.geojson"
    json.dump({"type": "FeatureCollection", "features": feats},
              open(os.path.join(out_dir, name), "w"), ensure_ascii=False)
    print(f"{name}: {len(feats)}")

print(f"\nтайлів: {len(buckets)}, будинків: {sum(len(v) for v in buckets.values())}")

#!/usr/bin/env python3
"""
Spike-2 — мульти-сіті buildings.geojson (для тесту в кількох містах).
Геокод (Nominatim) → Overpass bbox (ways+nodes) → парс полігонів (pure Python) →
класифікація типів → об'єднання з наявним Volda-geojson. Без GDAL/tippecanoe/docker.

Вихід: buildings_multicity.geojson (копіюється в app як buildings.geojson).
building_id нових міст = "w<osm_way_id>" (унікальні; не колізують із bare-id Volda).
"""
import urllib.request, urllib.parse, json, time, math, os
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Streif-spike/0.3 (contact@semden.info)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter"]

# (мітка, lat, lon, half-розмір bbox у км) — ПРЯМІ координати з реального треку (diag.csv),
# щедрі зони, бо геокод сіл схибив і Денис рухається широким регіоном.
AREAS = [
    ("Gardermoen", 60.194, 11.100, 5.0),  # аеропорт OSL — Денис ТУТ зараз (перший!)
    ("Hallingdal", 60.69, 8.85, 10.0),    # головна база (6898 фіксів ходьби) — Ål/Torpo долина
    ("Land",       60.74, 10.26, 8.0),    # (60.75,10.25)
    ("LandS",      60.55, 10.36, 6.0),    # (60.55,10.35)
    ("Oslo",       59.9109, 10.7528, 2.0),  # центр щільний — 2 км, щоб не роздути пам'ять
]


def geocode(q):
    url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
    if not r:
        raise RuntimeError(f"geocode failed: {q}")
    return float(r[0]["lat"]), float(r[0]["lon"])


def overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for rnd in range(3):
        for base in OVERPASS:
            try:
                req = urllib.request.Request(base, data=data, headers={**UA, "Content-Type": "application/x-www-form-urlencoded"})
                return urllib.request.urlopen(req, timeout=240).read()
            except Exception as e:
                last = e; print(f"  overpass retry ({base.split('/')[2]}): {e}"); time.sleep(8)
    raise RuntimeError(f"overpass failed: {last}")


def classify(p):
    b = (p.get("building") or "").lower()
    am = (p.get("amenity") or "").lower()
    tour = (p.get("tourism") or "").lower()
    if b in ("church", "chapel", "cathedral", "mosque", "temple", "synagogue", "shrine", "monastery") or am == "place_of_worship":
        return "sacral"
    if b in ("cabin", "hut", "chalet") or tour in ("chalet", "alpine_hut", "wilderness_hut"):
        return "hytte"
    if b in ("house", "detached", "residential", "apartments", "terrace", "semidetached_house", "bungalow", "dormitory", "houseboat", "static_caravan", "farm"):
        return "housing"
    if b in ("garage", "garages", "shed", "barn", "farm_auxiliary", "carport", "greenhouse", "industrial", "warehouse", "service", "hangar", "stable", "sty", "cowshed", "silo", "storage_tank", "roof"):
        return "outbuilding"
    if b in ("commercial", "retail", "office", "school", "kindergarten", "university", "college", "hospital", "public", "civic", "hotel", "sports_centre", "sports_hall", "train_station", "transportation", "government", "fire_station"):
        return "public"
    if b in ("yes", ""):
        if (am in ("school", "kindergarten", "university", "college", "hospital", "townhall", "library", "community_centre", "fire_station", "police")
                or p.get("shop") or p.get("office") or tour in ("hotel", "hostel", "guest_house")):
            return "public"
    return "other"


def parse_buildings(osm_xml):
    root = ET.fromstring(osm_xml)
    nodes = {}
    for n in root.iter("node"):
        nodes[n.get("id")] = (round(float(n.get("lon")), 6), round(float(n.get("lat")), 6))
    feats = []
    for w in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
        b = tags.get("building")
        if not b or b == "no":
            continue
        refs = [nd.get("ref") for nd in w.findall("nd")]
        ring = [nodes[r] for r in refs if r in nodes]
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        feats.append({
            "type": "Feature",
            "properties": {"building_id": "w" + w.get("id"), "type": classify(tags)},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    return feats


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    all_feats = []

    # 1) наявний Volda (зберігаємо як є)
    volda = json.load(open(os.path.join(base, "buildings.geojson"), encoding="utf-8"))
    vf = volda["features"]
    all_feats.extend(vf)
    print(f"Volda (наявні): {len(vf)}")

    # 2) зони з реального треку (резюмовано + ІНКРЕМЕНТАЛЬНИЙ запис — деплой після кожної зони)
    from collections import Counter
    out = os.path.join(base, "buildings_multicity.geojson")

    def write_out():
        json.dump({"type": "FeatureCollection", "features": all_feats}, open(out, "w"), ensure_ascii=False)
        return os.path.getsize(out) / 1e6

    for label, lat, lon, half in AREAS:
        cache = os.path.join(base, f"_cache_{label}.geojson")
        if os.path.exists(cache):
            feats = json.load(open(cache, encoding="utf-8"))
            print(f"{label}: {len(feats)} (cache)")
        else:
            dlat = half / 111.32
            dlon = half / (111.32 * math.cos(math.radians(lat)))
            s, w, n, e = lat - dlat, lon - dlon, lat + dlat, lon + dlon
            query = f'[out:xml][timeout:240];(way["building"]({s},{w},{n},{e}););(._;>;);out body;'
            osm = overpass(query)
            feats = parse_buildings(osm)
            json.dump(feats, open(cache, "w"), ensure_ascii=False)
            print(f"{label} @({lat:.4f},{lon:.4f}) bbox~{half*2:.0f}km: {len(feats)}  {dict(Counter(f['properties']['type'] for f in feats))}")
            time.sleep(2)
        all_feats.extend(feats)
        print(f"  -> буфер: {len(all_feats)} буд., {write_out():.1f} МБ (ЗАПИСАНО {os.path.basename(out)})")

    print(f"\nTOTAL: {len(all_feats)} buildings ({write_out():.1f} MB)")


if __name__ == "__main__":
    main()

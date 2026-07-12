# -*- coding: utf-8 -*-
"""
Build curated POI points for Streif Nature-v1 (D34, points-only, post-codex-review).

IN : OSM POI JSON (fetch_poi.py) [+ optional SSB Tettsteder GML for city/nature tag]
OUT: poi.geojson — Point FeatureCollection. Кожна фіча:
     poi_id, type (Streif POI-категорія), name, source, source_id, license, city (bool), fetched

Курація (codex: лін, require-name + ручний контроль): категорія-фільтр + name-обов'язковий +
дедуп (source_id + near-dup same name/category ≤50м) + опційні poi_allowlist.txt / poi_blocklist.txt
(source_id-и). Провенанс per-feature (codex MINOR #13). city/нейчур = tettsteder-PIP (реюз build_tiles).

usage: python build_poi.py OUT.geojson POI_RAW.json [--tettsteder=t.gml] [--allow=poi_allowlist.txt] [--block=poi_blocklist.txt]
"""
import sys, os, json, math, datetime, urllib.request, urllib.parse

# --- Streif POI-категорії з OSM-тегів (куратний набір; None = не показуємо) ---
# ⚠️ historic=* шумний: 204 seter/støl (shieling) — сільські ферми, не «цікаві місця».
# Whitelist справді цікавих культурних підтипів (codex #11: звузити курацію).
CULTURAL_HIST = {"monument", "memorial", "ruins", "heritage", "castle", "fort", "manor",
                 "archaeological_site", "church", "chapel", "wayside_shrine", "wayside_cross",
                 "boundary_stone", "cannon", "ship", "aircraft", "locomotive", "tomb", "citywalls"}
def poi_category(t):
    tour = (t.get("tourism") or "").lower(); hist = (t.get("historic") or "").lower()
    nat = (t.get("natural") or "").lower(); am = (t.get("amenity") or "").lower()
    leis = (t.get("leisure") or "").lower(); bld = (t.get("building") or "").lower()
    if tour == "viewpoint": return "viewpoint"
    if tour in ("alpine_hut", "wilderness_hut"): return "hut"
    if am == "shelter": return "shelter"
    if am == "place_of_worship" or bld == "church": return "church"
    if nat == "beach" or leis == "beach_resort": return "badeplass"
    if nat == "peak": return "peak"
    if hist in CULTURAL_HIST or tour == "artwork": return "cultural"   # seter/farm/… → None (шум)
    return None

def coords(e):
    if e.get("type") == "node": return e.get("lon"), e.get("lat")
    c = e.get("center") or {}; return c.get("lon"), c.get("lat")

def load_ids(path):
    if not path or not os.path.exists(path): return set()
    return {ln.strip() for ln in open(path, encoding="utf-8") if ln.strip() and not ln.startswith("#")}

# --- фото POI (--images): Wikidata P18 / OSM image-тег → URL картинки з Wikimedia Commons (© Commons) ---
def commons_filepath(fn):
    fn = fn.strip()
    if fn.lower().startswith("file:"): fn = fn[5:]
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(fn.replace(" ", "_")) + "?width=640"

def resolve_wikidata_images(ids):
    """batch Wikidata wbgetentities → {Qid: commons_url} за claim P18 (image)."""
    out = {}; ids = list(ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&ids="
               + "|".join(chunk) + "&props=claims&format=json")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
            j = json.load(urllib.request.urlopen(req, timeout=60))
        except Exception as ex:
            print(f"  wikidata fail: {ex}"); continue
        for qid, ent in j.get("entities", {}).items():
            p18 = ent.get("claims", {}).get("P18")
            if p18:
                try: out[qid] = commons_filepath(p18[0]["mainsnak"]["datavalue"]["value"])
                except Exception: pass
    return out

def main():
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    city_only = "--city-only" in sys.argv    # безпечний тест-режим: лише міські POI (у tettsted), без гір
    do_images = "--images" in sys.argv        # фото з Wikidata/Commons (мережа) → prop "image"
    rest = [a for a in sys.argv[1:] if not a.startswith("--")]
    out, raw_path = rest[0], rest[1]
    allow = load_ids(args.get("--allow")); block = load_ids(args.get("--block"))

    tett = []
    if args.get("--tettsteder"):
        from build_tiles import parse_tettsteder, locate_tettsted   # реюз PIP
        tett = parse_tettsteder(args["--tettsteder"])
        print(f"  tettsteder: {len(tett)} поселень (для city/nature-тегу)")

    j = json.load(open(raw_path, encoding="utf-8"))
    fetched = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    feats = []; meta = []; seen = set(); near = []     # meta: (wikidata, image-тег) паралельно feats; near: дедуп
    kept_by_cat = {}; skipped = {"no_name": 0, "no_cat": 0, "no_coord": 0, "dup": 0, "blocked": 0}
    for e in j.get("elements", []):
        t = e.get("tags", {})
        cat = poi_category(t)
        if not cat: skipped["no_cat"] += 1; continue
        name = (t.get("name") or "").strip()
        if not name: skipped["no_name"] += 1; continue
        lon, lat = coords(e)
        if lon is None or lat is None: skipped["no_coord"] += 1; continue
        sid = f"{e['type'][0]}{e['id']}"              # n123 / w456 / r789
        if sid in block: skipped["blocked"] += 1; continue
        if allow and sid not in allow: continue        # tight-режим: лише allowlist
        if sid in seen: skipped["dup"] += 1; continue
        # near-dup: та сама категорія+назва в межах ~50м (церква як node+way тощо)
        kLon = 111320.0 * math.cos(math.radians(lat)); dupd = False
        for c2, n2, x2, y2 in near:
            if c2 == cat and n2 == name:
                dx = (lon - x2) * kLon; dy = (lat - y2) * 111320.0
                if dx * dx + dy * dy < 2500: dupd = True; break
        if dupd: skipped["dup"] += 1; continue
        seen.add(sid); near.append((cat, name, lon, lat))
        city = None
        if tett:
            from build_tiles import locate_tettsted
            city = locate_tettsted(lon, lat, tett) is not None
        if city_only and city is not True:               # safe-тест: пропустити все поза містом (гори тощо)
            skipped["nature"] = skipped.get("nature", 0) + 1
            continue
        feats.append({"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {"poi_id": f"osm_{sid}", "type": cat, "name": name,
                           "source": "osm", "source_id": sid, "license": "ODbL",
                           "city": city, "fetched": fetched}})
        meta.append(((t.get("wikidata") or "").strip() or None, t.get("image")))   # для --images
        kept_by_cat[cat] = kept_by_cat.get(cat, 0) + 1

    if do_images:                                            # фото → prop "image" (Wikidata P18 / Commons image-тег)
        wd_url = resolve_wikidata_images({wd for wd, _ in meta if wd})
        nimg = 0
        for f, (wd, imgtag) in zip(feats, meta):
            url = wd_url.get(wd) if wd else None
            if not url and imgtag:
                it = imgtag.strip()
                if not it.lower().startswith("http"): url = commons_filepath(it)      # bare / "File:X"
                elif "wikimedia.org" in it: url = it                                   # commons/upload URL
            if url:
                f["properties"]["image"] = url
                f["properties"]["image_credit"] = "© Wikimedia Commons"
                nimg += 1
        print(f"  images: {nimg}/{len(feats)} POI з фото (© Wikimedia Commons)")

    fc = {"type": "FeatureCollection",
          "attribution": "© OpenStreetMap contributors (ODbL)",
          "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "features": feats}
    json.dump(fc, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    ncity = sum(1 for f in feats if f["properties"]["city"] is True)
    print(f"POI: {len(feats)} kept  {kept_by_cat}")
    print(f"  city={ncity} nature={len(feats)-ncity}  skipped={skipped}")
    print(f"  -> {out}")

if __name__ == "__main__":
    main()

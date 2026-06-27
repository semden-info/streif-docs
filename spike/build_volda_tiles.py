#!/usr/bin/env python3
"""
Streif — Spike 1 data pipeline: Volda (kommune 1577).

Геометрія: INSPIRE Buildings Core2d (відкритий Geonorge WFS).
Тип:       Matrikkelen-Bygningspunkt (поле bygningstype).
Вихід:     buildings.geojson + buildings.pmtiles
           (кожен будинок: стабільний building_id + колірна група `type`).

Це SPIKE-скрипт: мета — валідувати пайплайн і дати дані для рендер-spike.
Код чорновий, можна викидати/переписувати.

── Залежності ───────────────────────────────────────────────
  Python:  pip install geopandas requests
  Система: GDAL/ogr2ogr · tippecanoe (felt/tippecanoe ≥ 2.17)

── Запуск ───────────────────────────────────────────────────
  python3 build_volda_tiles.py

── NB (перевірити на ПЕРШОМУ запуску — Geonorge треба звіряти наживо) ──
  • назви шарів/полів WFS (bygningstype, bygningsnummer, localId) можуть
    відрізнятись — скрипт друкує доступні колонки; підправ TYPE_FIELD/ID_FIELD;
  • WFS має ліміт к-сті фіч і ~10–15 хв затримку — для Volda (~12k) зазвичай ок,
    але звір повноту; якщо неповно — переходь на per-kommune файли nedlasting.geonorge.no;
  • колірна мапа bygningstype → група — наближена; уточнити за SSB Klass 31 / building_types.csv.
"""

import os
import sys
import subprocess
import requests
import geopandas as gpd

# ── Конфіг ───────────────────────────────────────────────────
KOMMUNE = "1577"  # Volda
WORKDIR = os.path.dirname(os.path.abspath(__file__))
INSPIRE_GPKG = os.path.join(WORKDIR, "_inspire.gpkg")
MATRIKKEL_GPKG = os.path.join(WORKDIR, "_matrikkel.gpkg")
OUT_GEOJSON = os.path.join(WORKDIR, "buildings.geojson")
OUT_PMTILES = os.path.join(WORKDIR, "buildings.pmtiles")

# Відкриті WFS (без авторизації)
INSPIRE_WFS = "WFS:https://wfs.geonorge.no/skwms1/wfs.inspire-bu-core2d"
INSPIRE_LAYER = "Building"
MATRIKKEL_WFS = "WFS:https://wfs.geonorge.no/skwms1/wfs.matrikkelen-bygningspunkt"
MATRIKKEL_LAYER = "Bygning"          # ← звір через: ogrinfo "WFS:.../wfs.matrikkelen-bygningspunkt"

TYPE_FIELD = "bygningstype"          # ← звір реальну назву поля
ID_FIELD = "bygningsnummer"          # ← стабільний id (fallback нижче, якщо нема)
METRIC_SRS = "EPSG:25832"            # ETRS89 / UTM 32N — для Møre og Romsdal

# Приблизний fallback-bbox Volda (lon/lat) — перевір, якщо API недоступне
FALLBACK_BBOX = (5.85, 61.95, 6.65, 62.30)


# ── Колірна група за bygningstype (NS3457 / SSB Klass 31) ─────
def classify(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "other"
    if 111 <= c <= 159 or c == 193:   # bolig
        return "housing"
    if 161 <= c <= 172:               # fritidsbolig / seterhus (hytte)
        return "hytte"
    if 181 <= c <= 183:               # garasje / uthus / naust до bolig
        return "outbuilding"
    if 200 <= c <= 299:               # industri / lager / landbruk
        return "outbuilding"
    if 671 <= c <= 673:               # kirke / religion
        return "sacral"
    if 300 <= c <= 899:               # kontor/forretning/skole/kultur/helse...
        return "public"
    return "other"
    # NB: "rare" (fyr, stavkyrkje, kulturminne) поки не виділяємо за кодом — TBD.


# ── 1. bbox Volda ────────────────────────────────────────────
def get_bbox():
    url = f"https://ws.geonorge.no/kommuneinfo/v1/kommuner/{KOMMUNE}"
    try:
        r = requests.get(url, params={"utkoordsys": "4326"}, timeout=30)
        r.raise_for_status()
        box = r.json().get("avgrensningsboks", {})
        coords = box.get("coordinates", [])[0]  # [[lon,lat], ...]
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        print(f"  bbox (API): {bbox}")
        return bbox
    except Exception as e:
        print(f"  ! kommuneinfo не вдалось ({e}) → fallback bbox", file=sys.stderr)
        return FALLBACK_BBOX


# ── 2. Завантаження WFS через ogr2ogr (пагінація + репроєкція) ─
def ogr_fetch(wfs, layer, out_gpkg, bbox):
    minx, miny, maxx, maxy = bbox
    if os.path.exists(out_gpkg):
        os.remove(out_gpkg)
    cmd = [
        "ogr2ogr", "-f", "GPKG", out_gpkg, wfs, layer,
        "-spat", str(minx), str(miny), str(maxx), str(maxy),
        "-spat_srs", "EPSG:4326",
        "-t_srs", METRIC_SRS,
        "-skipfailures",
    ]
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ── 3. Join тип→полігон + класифікація + стабільний id ───────
def join_and_classify():
    poly = gpd.read_file(INSPIRE_GPKG)
    pts = gpd.read_file(MATRIKKEL_GPKG)
    print(f"\n  INSPIRE полігонів: {len(poly)} | колонки: {list(poly.columns)}")
    print(f"  Matrikkelen точок: {len(pts)} | колонки: {list(pts.columns)}\n")

    # Підстраховка назв полів
    type_col = TYPE_FIELD if TYPE_FIELD in pts.columns else None
    id_col = ID_FIELD if ID_FIELD in pts.columns else None
    if type_col is None:
        sys.exit(f"  ! Поле типу '{TYPE_FIELD}' не знайдено. Онови TYPE_FIELD за колонками вище.")

    keep = ["geometry", type_col] + ([id_col] if id_col else [])
    pts = pts[keep]

    # точка-в-полігоні; беремо першу точку на полігон
    joined = gpd.sjoin(poly, pts, predicate="contains", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]

    poly = poly.copy()
    poly["type"] = joined[type_col].map(classify).values
    if id_col:
        poly["building_id"] = joined[id_col].fillna("").astype(str).values
    # fallback id, якщо bygningsnummer відсутній/порожній
    poly["building_id"] = [
        bid if bid else f"v{KOMMUNE}-{i}"
        for i, bid in enumerate(poly.get("building_id", [""] * len(poly)))
    ]

    out = poly[["building_id", "type", "geometry"]].to_crs("EPSG:4326")
    if os.path.exists(OUT_GEOJSON):
        os.remove(OUT_GEOJSON)
    out.to_file(OUT_GEOJSON, driver="GeoJSON")

    counts = out["type"].value_counts().to_dict()
    print(f"  → {OUT_GEOJSON}: {len(out)} будинків")
    print(f"    розподіл за типом: {counts}")


# ── 4. Tippecanoe → PMTiles ──────────────────────────────────
def make_pmtiles():
    if os.path.exists(OUT_PMTILES):
        os.remove(OUT_PMTILES)
    cmd = [
        "tippecanoe", "-zg", "-o", OUT_PMTILES, "-l", "buildings",
        "--use-attribute-for-id", "building_id",   # стабільний feature id (D7)
        "--drop-densest-as-needed", "--force",
        OUT_GEOJSON,
    ]
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"  → {OUT_PMTILES}")


def main():
    print("Streif Spike 1 — pipeline Volda (1577)")
    print("[1/4] bbox…")
    bbox = get_bbox()
    print("[2/4] INSPIRE полігони (WFS)…")
    ogr_fetch(INSPIRE_WFS, INSPIRE_LAYER, INSPIRE_GPKG, bbox)
    print("[2/4] Matrikkelen точки (WFS)…")
    ogr_fetch(MATRIKKEL_WFS, MATRIKKEL_LAYER, MATRIKKEL_GPKG, bbox)
    print("[3/4] join + класифікація…")
    join_and_classify()
    print("[4/4] tippecanoe → pmtiles…")
    make_pmtiles()
    print("\n✓ Готово. buildings.pmtiles → бандл у каркас-застосунок (pmtiles://asset://).")


if __name__ == "__main__":
    main()

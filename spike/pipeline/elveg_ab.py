# -*- coding: utf-8 -*-
"""D31 GATE: A/B recall — D6 accessible з OSM-highways vs Elveg(NVDB Vegnett Pluss) на Volda.
Ловимо регресію (будинок доступний по OSM-стежці, але НЕ по Elveg) ПЕРЕД перезаливкою тайлів."""
import sys, xml.etree.ElementTree as ET
from pyproj import Transformer
sys.path.insert(0, ".")
from build_tiles import parse_osm, compute_accessible   # compute_accessible джерело-агностична

SC = "C:/Users/mail/AppData/Local/Temp/claude/C--Users-mail-OneDrive-Projects-Streif--claude-worktrees-wonderful-noyce-43a362/2c21efd0-437f-4f21-95af-7584ef27c924/scratchpad"
GML = SC + "/elveg_volda/1577NVDBVegnettPluss.gml"
OSM = SC + "/osm_volda_raw.json"

NVDB = "{https://skjema.geonorge.no/SOSI/produktspesifikasjon/NVDBVegnettPluss/1.1}"
GMLNS = "{http://www.opengis.net/gml/3.2}"

# фактичні typeVeg-літерали з живого файлу Volda (НЕ зі специфікації):
PED = {"fortau", "gangveg", "gsv", "gangfelt", "trapp"}   # завжди walkable (пішохідна інфра)
DRIVE = {"bilveg", "kanalveg", "rkj"}                     # локальні проїзні — walkable, крім E/R трас
NONWALK_CAT = {"E", "R"}                                  # europaveg / riksveg (пішоходи заборонені/небезпечно)
FERRY = {"bilferje", "passasjerferje"}

def parse_elveg(path):
    tr = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)  # 5973 гориз. == 25833
    lines = []
    kept = {}
    for ev, el in ET.iterparse(path, events=("end",)):
        if el.tag == NVDB + "Veglenke":
            tv = (el.findtext(NVDB + "typeVeg") or "").strip().lower()
            cat = (el.findtext(NVDB + "vegkategori") or "").strip().upper()
            walk = (tv in PED) or (tv in DRIVE and cat not in NONWALK_CAT)
            if walk and tv not in FERRY:
                ls = el.find(".//" + GMLNS + "LineString")
                pos = el.find(".//" + GMLNS + "posList")
                if pos is not None and pos.text:
                    dim = int(ls.get("srsDimension", "2")) if ls is not None else 2
                    nums = pos.text.split()
                    pts = []
                    for i in range(0, len(nums) - (dim - 1), dim):
                        lon, lat = tr.transform(float(nums[i]), float(nums[i + 1]))
                        pts.append((lon, lat))
                    if len(pts) >= 2:
                        lines.append(pts); kept[tv] = kept.get(tv, 0) + 1
            el.clear()
    print("Elveg walkable lines by typeVeg:", dict(sorted(kept.items(), key=lambda kv: -kv[1])))
    return lines

buildings, osm_hw = parse_osm(OSM)
elveg_hw = parse_elveg(GML)
print(f"buildings={len(buildings)}  OSM-highways={len(osm_hw)}  Elveg-walkable={len(elveg_hw)}")

REF = 62.08
accOSM = compute_accessible(buildings, osm_hw, REF)
accELV = compute_accessible(buildings, elveg_hw, REF)

nO = sum(1 for v in accOSM.values() if v)
nE = sum(1 for v in accELV.values() if v)
N = len(buildings)
regressed = [b for b in accOSM if accOSM[b] and not accELV.get(b)]   # OSM=так, Elveg=ні (НЕБЕЗПЕКА)
gained    = [b for b in accELV if accELV[b] and not accOSM.get(b)]   # Elveg=так, OSM=ні
print(f"\n=== A/B accessible% (Volda, {N} буд.) ===")
print(f"OSM-highways : {nO} ({100*nO/N:.1f}%)")
print(f"Elveg        : {nE} ({100*nE/N:.1f}%)")
print(f"REGRESSED (OSM✓→Elveg✗): {len(regressed)}  ({100*len(regressed)/N:.1f}%)  <- recall-ризик")
print(f"GAINED    (OSM✗→Elveg✓): {len(gained)}")
# де регресія за типом OSM-будинку
if regressed:
    from collections import Counter
    bmap = {b[0]: b for b in buildings}
    ct = Counter(bmap[b][2] for b in regressed if b in bmap)
    print("regressed за OSM-типом:", dict(ct))

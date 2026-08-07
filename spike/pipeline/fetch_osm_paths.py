# -*- coding: utf-8 -*-
"""OSM-стежки для доповнення Turrutebasen (польова заувага 9, 2026-08-07).

**Навіщо взагалі.** Turrutebasen дає лише **марковані** маршрути, і біля Volda їх у радіусі 6 км
рівно **п'ять**. Тобто міська частина лінійної механіки практично порожня — не через наші фільтри,
а через саме джерело (перевірено на даних 2026-08-06).

⚠️ **Що спростувала розвідка (2026-08-07), перш ніж це писалось.** Задум був «фільтрувати за
характеристиками — шириною, складністю». У 1729 ліній навколо Volda/Ørsta:
`width` — **0,3%** · `sac_scale` — 0,7% · `trail_visibility` — 0,3% · **`name` — 0,3%** ·
`surface` — 16%. Фільтрувати за характеристиками **неможливо: їх немає**. Лишається те, що є в
100% ліній — тип `highway` і сама **геометрія**.

Тому відбір тут геометричний, а не тегами; сам відбір робить `build_trails.py --osm`.

⚠️ **Ліцензія — ODbL**, не CC BY, як у решти наших даних. `trails.geojson` уже несе `attribution`;
при вмиканні OSM туди дописується друге джерело. Це не формальність: ODbL вимагає атрибуції.

usage:
    python fetch_osm_paths.py OUT.json [--bbox=62.05,5.90,62.25,6.30]
"""
import io
import json
import sys
import urllib.request

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True)
        for a in sys.argv[1:] if a.startswith("--")}
out_path = args[0] if args else "osm_paths.json"
bbox = opts.get("--bbox", "62.05,5.90,62.25,6.30")      # Volda + Ørsta, радіус прогулянки

# ⚠️ `footway` НЕ беремо: у місті це тротуари вздовж вулиць і доріжки між під'їздами. Вони
# формально пішохідні, але стежками не є — а саме «сміття» й було тим, чого Денис просив уникнути.
# `steps` теж ні: сходи не «проходять уздовж», вони з'єднують.
Q = """[out:json][timeout:240];
way["highway"~"^(path|track|bridleway)$"](%s);
out body geom;""" % bbox


def fetch():
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(
                url, data=Q.encode("utf-8"),
                headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
            with urllib.request.urlopen(req, timeout=260) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:      # noqa: BLE001 — по черзі пробуємо дзеркала
            last = e
            print("  %s → %s" % (url, e))
    raise last


data = fetch()
ways = [e for e in data.get("elements", []) if e.get("type") == "way" and e.get("geometry")]
io.open(out_path, "w", encoding="utf-8", newline="\n").write(
    json.dumps({"elements": ways}, ensure_ascii=False, separators=(",", ":")))
print("ліній із геометрією: %d → %s" % (len(ways), out_path))

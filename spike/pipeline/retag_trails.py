# -*- coding: utf-8 -*-
"""Streif — РАЗОВИЙ міст: дописати комуну **вже опублікованому** `trails.geojson`, без перезбирання.

НАВІЩО САМЕ ТАК (той самий аргумент, що в `retag_kommune.py`, і він тут навіть сильніший):
    Канонічний шлях — `build_trails.py --kommuner=…`, і він теж уміє тегувати. Але перезібрати
    набір означає взяти джерела ЗАНОВО, а одне з них — **живий OSM**: ланцюги перезшиються від
    будь-якої правки, яку хтось зробив за ці дні, і `seg`-якорі частини стежок зміняться. Тобто
    невинне «додати поле» коштувало б осиротілого прогресу — рівно того, від чого застерігає D30.
    Тут же ми беремо БАЙТ-У-БАЙТ той файл, що лежить на CDN, і додаємо одне поле: `seg`, `trail`,
    геометрія й порядок фіч лишаються ті самі.

ВХІД : CDN `trails.geojson` (або локальний файл) + межі комун з ws.geonorge.no/kommuneinfo
ВИХІД: OUT.geojson із `kommune`/`kommune_name` на кожній фічі + звірка (числа = приймальний критерій)

⚠️ Нічого нікуди не заливає. Публікація на R2 — окремий крок і окреме рішення власника.

Usage (Windows: ЗАВЖДИ PYTHONIOENCODING=utf-8):
    python retag_trails.py OUT.geojson [--in=trails.geojson] [--cache=DIR]
                                       [--kommuner=1577,1520] [--no-discover]
"""
import io
import json
import os
import sys

import geo_units

CDN = "https://pub-b1c9ae365792405880b62e24ccda0df1.r2.dev"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True)
            for a in sys.argv[1:] if a.startswith("--")}
    out_path = args[0] if args else "trails.geojson"
    cache = opts.get("--cache") or os.path.join(os.path.dirname(os.path.abspath(out_path)), "cache")
    seeds = [c.strip() for c in str(opts.get("--kommuner", "1577,1520")).split(",") if c.strip()]
    discover = not opts.get("--no-discover")

    src = opts.get("--in")
    if src:
        raw = io.open(src, encoding="utf-8").read()
        print("вхід: %s" % src)
    else:
        raw = geo_units.fetch(f"{CDN}/trails.geojson",
                              os.path.join(cache, "trails.geojson")).decode("utf-8")
        print("вхід: %s/trails.geojson (жива публікація)" % CDN)

    fc = json.loads(raw)
    feats = fc["features"]
    before_ids = [f["properties"].get("seg") for f in feats]
    before_km = sum(float(f["properties"].get("len_m") or 0) for f in feats) / 1000.0
    routes_before = {f["properties"].get("trail") for f in feats}
    print("фіч %d · маршрутів %d · %.1f км" % (len(feats), len(routes_before), before_km))

    report = geo_units.tag_routes_by_kommune(feats, seeds, cache, discover=discover)
    geo_units.print_report(report)

    # ── ЗВІРКА: тег дописано, решта недоторкана ───────────────────────────────────────────────────
    print()
    print("=== ЗВІРКА ===")
    same_ids = [f["properties"].get("seg") for f in feats] == before_ids
    after_km = sum(float(f["properties"].get("len_m") or 0) for f in feats) / 1000.0
    tagged = sum(1 for f in feats if f["properties"].get("kommune"))
    routes_after = {f["properties"].get("trail") for f in feats}
    print("  порядок і `seg` фіч          : %s" % ("OK" if same_ids else "РОЗБІЖНІСТЬ"))
    print("  маршрутів                    : %d vs %d  %s"
          % (len(routes_after), len(routes_before),
             "OK" if routes_after == routes_before else "РОЗБІЖНІСТЬ"))
    print("  довжина                      : %.1f vs %.1f км  %s"
          % (after_km, before_km, "OK" if abs(after_km - before_km) < 0.05 else "РОЗБІЖНІСТЬ"))
    print("  ділянок із комуною           : %d із %d (%.1f%%)"
          % (tagged, len(feats), 100.0 * tagged / max(1, len(feats))))
    # Одна комуна на маршрут — інваріант, а не побажання: клієнт бере тег ПЕРШОЇ ділянки маршруту.
    per_route = {}
    for f in feats:
        per_route.setdefault(f["properties"]["trail"], set()).add(f["properties"].get("kommune", ""))
    split = [t for t, s in per_route.items() if len(s) > 1]
    print("  маршрутів із двома комунами  : %d  %s" % (len(split), "OK" if not split else "РОЗБІЖНІСТЬ"))

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
    print("→ %s (%d КБ)" % (out_path, os.path.getsize(out_path) // 1024))
    print("⚠️ На R2 НЕ залито — це окремий крок і окреме рішення власника.")


if __name__ == "__main__":
    main()

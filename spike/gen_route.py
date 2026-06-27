#!/usr/bin/env python3
"""
Spike-1 v2 — генератор СИНТЕТИЧНОГО маршруту для replay-GPS.

Будує відтворювану coverage-«змійку» (boustrophedon) крізь щільний центр Volda.
Мета — не реалізм GPS (це Spike-2), а контрольований, повторюваний вхід, що
природно накопичує visited уздовж довгого прогону (перевірка механіки + пам'яті).

Вихід: route.json = [{ "lat", "lon", "t" }] (t — секунди від старту, 1.4 м/с).
Також друкує, скільки будинків змійка розкриє при R=30 м (sanity-check).

Запуск:  python gen_route.py   (з теки spike/)
"""
import json, math

CENTER_LAT, CENTER_LON = 62.146, 6.071
HALF_NS_M = 600.0   # половина висоти коробки (N-S), метри
HALF_EW_M = 800.0   # половина ширини коробки (E-W), метри
ROW_STEP_M = 50.0   # відстань між рядами змійки
PT_STEP_M = 12.0    # відстань між точками вздовж ряду
WALK_MPS = 1.4      # пішохідна швидкість (для t; replay усе одно tick-based)
MATCH_R_M = 30.0    # для sanity-оцінки розкриттів

KLAT = 111320.0
KLON = 111320.0 * math.cos(math.radians(CENTER_LAT))


def main():
    dlat_row = ROW_STEP_M / KLAT
    dlon_pt = PT_STEP_M / KLON
    lat0 = CENTER_LAT - HALF_NS_M / KLAT
    lat1 = CENTER_LAT + HALF_NS_M / KLAT
    lon0 = CENTER_LON - HALF_EW_M / KLON
    lon1 = CENTER_LON + HALF_EW_M / KLON

    pts = []
    lat = lat0
    flip = False
    while lat <= lat1:
        lon_seq = []
        lon = lon1 if flip else lon0
        while (lon >= lon0) if flip else (lon <= lon1):
            lon_seq.append(round(lon, 6))
            lon += (-dlon_pt if flip else dlon_pt)
        for lon in lon_seq:
            pts.append((round(lat, 6), lon))
        lat += dlat_row
        flip = not flip

    # часові мітки (1.4 м/с по фактичних відстанях)
    out = []
    t = 0.0
    for i, (la, lo) in enumerate(pts):
        if i > 0:
            pla, plo = pts[i - 1]
            dx = (lo - plo) * KLON
            dy = (la - pla) * KLAT
            t += math.hypot(dx, dy) / WALK_MPS
        out.append({"lat": la, "lon": lo, "t": round(t, 1)})

    json.dump(out, open("route.json", "w"), ensure_ascii=False)
    print(f"route points: {len(out)}")
    print(f"bbox lat {lat0:.5f}..{lat1:.5f}  lon {lon0:.5f}..{lon1:.5f}")
    print(f"duration @1.4 m/s: {out[-1]['t']/60:.1f} min (replay is tick-based, not realtime)")

    # --- sanity: скільки будинків розкриє маршрут при R=30 м ---
    gj = json.load(open("buildings.geojson", encoding="utf-8"))
    cents = []
    for f in gj["features"]:
        g = f["geometry"]
        ring = g["coordinates"][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0]
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        cents.append((sum(xs) / len(xs), sum(ys) / len(ys)))

    revealed = set()
    r2 = MATCH_R_M * MATCH_R_M
    for p in out:
        plat, plon = p["lat"], p["lon"]
        for idx, (clon, clat) in enumerate(cents):
            if idx in revealed:
                continue
            dx = (clon - plon) * KLON
            dy = (clat - plat) * KLAT
            if dx * dx + dy * dy <= r2:
                revealed.add(idx)
    print(f"buildings revealed by route @R={MATCH_R_M:.0f}m: {len(revealed)} / {len(cents)}")


if __name__ == "__main__":
    main()

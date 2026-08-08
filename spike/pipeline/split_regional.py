# -*- coding: utf-8 -*-
"""P38/P36 — нарізати чотири регіональні файли **по комунах** + індекс комун.

ПРОБЛЕМА (P38). Плитковий шар будівель масштабується сам: `area_{la}_{lo}.geojson` не знає про
регіон. А чотири файли тягнуться ЦІЛКОМ одним GET на першому запуску й лягають у пам'ять цілком:
`manifest.json` · `tettsteder.geojson` · `poi.geojson` · `trails.geojson`.

⚠️ **Зміряно перед роботою, і це переставило пріоритети:** `manifest` (217 КБ) і `tettsteder`
(467 КБ) вже покривають УСЮ Møre og Romsdal і на цьому масштабі не болять. Болить `trails` — 575 КБ
на 2,5 комуни, тобто ≈6 МБ на всю MR. Саме він робить розширення неможливим.

⚠️ **Друга знахідка: 59% маніфесту — мертвий вантаж.** Масив `tiles` (4288 записів, 129 КБ) клієнт
**не читає взагалі** — у коді немає жодного звернення. Тут він переїжджає в **покомунні** маніфести,
де вперше стає потрібним: саме з нього P36 знає, які плитки тягнути для «завантажити комуну».

**Чому по комунах, а не 0,02°-плитками** (рішення Дениса): маршрут перетинає плитки, отже його
довелось би або дублювати, або **різати по межі** — а різати маршрути **D34 заборонив двічі**
(«маршрут втрачає початок, прогрес осиротіє посеред пройденого»). Тег комуни ж уже стоїть на всіх
чотирьох наборах.

**ЧОМУ МІСТ, А НЕ ПЕРЕЗБІРКА** — той самий аргумент, що в `retag_trails.py`: беремо байт-у-байт те,
що лежить на CDN, і лише перекладаємо по теках. Жодна фіча не змінюється, тож прогрес не сироти́ть.

ВИХІД:
    kommuner.json            індекс: код · назва · bbox · скільки чого · оцінка обсягу передзавантаження
    manifest/{код}.json      тотали комуни + СПИСОК ЇЇ ПЛИТОК (для P36)
    tettsteder/{код}.geojson поселення цієї комуни (з полігонами)
    poi/{код}.geojson        POI цієї комуни
    trails/{код}.geojson     маршрути цієї комуни
    manifest.json            той самий кореневий, але БЕЗ `tiles` (−59%)

⚠️ Старі цілі файли в корені CDN **лишаються недоторканими** — клієнти 25-27 читають саме їх, і
прибрати їх означало б миттєво позбавити їх стежок, POI й меж поселень.

Usage (Windows: ЗАВЖДИ PYTHONIOENCODING=utf-8):
    python split_regional.py OUTDIR [--cache=DIR] [--src=DIR]
"""
import io
import json
import os
import sys

import geo_units

CDN = "https://pub-b1c9ae365792405880b62e24ccda0df1.r2.dev"

# Оцінка обсягу передзавантаження — байтів на будівлю по мережі (gzip). Виміряно 2026-08-08 на
# чотирьох живих плитках різного наповнення: 52 Б. ⚠️ Це ОЦІНКА для підпису кнопки, а не облік;
# кнопка мусить казати «≈», інакше перше ж розходження читатиметься як обман.
BYTES_PER_BUILDING = 52


def load(name, cache, src):
    if src:
        return io.open(os.path.join(src, name), encoding="utf-8").read()
    return geo_units.fetch(f"{CDN}/{name}", os.path.join(cache, name)).decode("utf-8")


def write_json(path, obj, pretty=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        else:
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    return os.path.getsize(path)


def tile_bbox(key, deg):
    """`area_3097_323` → (minLon, minLat, maxLon, maxLat).

    ⚠️ **Ключ — ЦЕНТР плитки, а не її кут.** Клієнт рахує його округленням
    (`AreaCache.keyFor`: `Math.round(lat / TILE)`, і `centerLat` це прямо підтверджує), тож коробка
    йде на пів-плитки в обидва боки. Спершу я написав тут `la*deg .. (la+1)*deg` — тобто ту саму
    формулу з кутовою семантикою, і вона давала зсув ~1,1 км, від чого прикордонні плитки могли
    приписатись не тій комуні.

    Це рівно те дзеркало, яке проєкт уже ловив у схемі категорій: формула живе у двох місцях і
    рано чи пізно розходиться. Тут вона лишається продубльованою (пайплайн і клієнт — різні мови),
    але принаймні названа: **джерело правди — `AreaCache`**, і будь-яка зміна там мусить прийти сюди.
    """
    parts = key.split("_")
    la, lo = int(parts[1]), int(parts[2])
    half = deg / 2.0
    return (lo * deg - half, la * deg - half, lo * deg + half, la * deg + half)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True)
            for a in sys.argv[1:] if a.startswith("--")}
    outdir = args[0] if args else "split"
    cache = opts.get("--cache") or os.path.join(outdir, "cdn-cache")
    src = opts.get("--src")
    os.makedirs(outdir, exist_ok=True)

    manifest = json.loads(load("manifest.json", cache, src))
    # ⚠️ Пастка, у яку легко впасти двічі: цей скрипт ЧИТАЄ `tiles`, а його ж вихід прибирає їх із
    # кореневого маніфесту — тобто повторний прогін по свіжій публікації не знайшов би нічого.
    # Тому масив живе окремим `tiles.json` (лише для інструментів пайплайну; застосунок його не
    # питає ніколи), і читаємо ми звідти, якщо в маніфесті його вже немає.
    if not manifest.get("tiles"):
        try:
            manifest["tiles"] = json.loads(load("tiles.json", cache, src))["tiles"]
            print("`tiles` узято з tiles.json (кореневий маніфест уже нарізаний)")
        except Exception:
            print("⛔ ані manifest.tiles, ані tiles.json — передзавантаження (P36) порахувати нічим")
            sys.exit(2)
    tett = json.loads(load("tettsteder.geojson", cache, src))
    poi = json.loads(load("poi.geojson", cache, src))
    trails = json.loads(load("trails.geojson", cache, src))
    deg = float(manifest.get("tileDeg") or 0.02)
    codes = sorted(manifest.get("byKommune", {}).keys())
    print("вхід: %d плиток · %d поселень · %d POI · %d ділянок · %d комун"
          % (len(manifest.get("tiles", [])), len(tett["features"]), len(poi["features"]),
             len(trails["features"]), len(codes)))

    # ── межі комун: потрібні для bbox індексу й для прив'язки POI (єдиний набір без тега) ─────────
    print()
    print("межі комун (kommuneinfo, кеш на диску):")
    koms = {}
    for c in codes:
        name, area = geo_units.load_kommune(c, cache)
        koms[c] = (name or manifest["byKommune"][c].get("name", ""), area)
    print("  завантажено %d" % len(koms))

    def bbox_of(area):
        xs0 = min(bb[0] for _, bb in area.polys); ys0 = min(bb[1] for _, bb in area.polys)
        xs1 = max(bb[2] for _, bb in area.polys); ys1 = max(bb[3] for _, bb in area.polys)
        return [round(xs0, 5), round(ys0, 5), round(xs1, 5), round(ys1, 5)]

    # ── розкладка ────────────────────────────────────────────────────────────────────────────────
    by_tett, by_poi, by_trail, by_tiles = {}, {}, {}, {}

    for f in tett["features"]:
        c = f["properties"].get("kommune", "")
        if c:
            by_tett.setdefault(c, []).append(f)

    # ⚠️ POI — ЄДИНИЙ набір без тега комуни, тож тут PIP. Точка, а не маршрут: ніякої «більшої
    # частини» не треба, і саме тому POI не мав тега досі.
    poi_lost = 0
    for f in poi["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        hit = next((c for c, (_, a) in koms.items() if a.contains(lon, lat)), None)
        if hit:
            by_poi.setdefault(hit, []).append(f)
        else:
            poi_lost += 1

    for f in trails["features"]:
        c = f["properties"].get("kommune", "")
        if c:
            by_trail.setdefault(c, []).append(f)

    # Плитки → комуни за ГЕОМЕТРІЄЮ ключа, без жодного завантаження: ключ це округлені координати.
    # ⚠️ Плитка на межі потрапляє в ОБИДВІ комуни, і це навмисно: для передзавантаження зайва
    # маленька плитка нешкідлива, а пропущена лишає дірку рівно там, де людина переходить межу.
    for t in manifest.get("tiles", []):
        x0, y0, x1, y1 = tile_bbox(t["key"], deg)
        probes = ((x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2))
        for c, (_, a) in koms.items():
            if any(a.contains(px, py) for px, py in probes):
                by_tiles.setdefault(c, []).append(t)

    # ── запис ────────────────────────────────────────────────────────────────────────────────────
    index = []
    total_bytes = 0
    for c in codes:
        km = manifest["byKommune"][c]
        tiles = by_tiles.get(c, [])
        buildings = sum(t["n"] for t in tiles)
        per = dict(km)
        per["kommune"] = c
        per["tileDeg"] = deg
        per["dataVersion"] = manifest.get("dataVersion")
        per["attribution"] = manifest.get("attribution")
        per["tiles"] = tiles                       # ⬅ саме тут `tiles` уперше стають потрібні (P36)
        n = write_json(os.path.join(outdir, "manifest", c + ".json"), per)
        total_bytes += n

        for sub, feats, attribution in (
            ("tettsteder", by_tett.get(c, []), tett.get("attribution")),
            ("poi", by_poi.get(c, []), poi.get("attribution")),
            ("trails", by_trail.get(c, []), trails.get("attribution")),
        ):
            fc = {"type": "FeatureCollection", "features": feats}
            if attribution:
                fc["attribution"] = attribution    # ⚠️ атрибуція їде в КОЖЕН шматок, не лише в цілий
            total_bytes += write_json(os.path.join(outdir, sub, c + ".geojson"), fc)

        index.append({
            "code": c,
            "name": koms[c][0] or km.get("name", ""),
            "bbox": bbox_of(koms[c][1]),
            "buildings": km.get("total", 0),
            "accessible": km.get("accessible", 0),
            "tiles": len(tiles),
            # Оцінка для підпису кнопки P36 — плитки цієї комуни, ≈52 Б на будівлю в gzip.
            "prefetchBytesApprox": buildings * BYTES_PER_BUILDING,
            "tettsteder": len(by_tett.get(c, [])),
            "poi": len(by_poi.get(c, [])),
            "trailSegments": len(by_trail.get(c, [])),
        })

    write_json(os.path.join(outdir, "kommuner.json"),
               {"generated": manifest.get("generated"), "tileDeg": deg,
                "dataVersion": manifest.get("dataVersion"), "kommuner": index}, pretty=True)

    # ── Два кореневі файли, і різниця між ними — про перехід, а не про формат ────────────────────
    #
    # `manifest.json` лишається тим, чим був, мінус мертвий масив `tiles`. ⚠️ `byKommune` звідти
    # прибрати НЕ МОЖНА: на ньому тримається статистика клієнтів 25-27, і вони оновляться не всі й
    # не одразу. Єдине, що ми забираємо, — те, чого не читає ЖОДЕН клієнт.
    slim = {k: v for k, v in manifest.items() if k != "tiles"}
    slim_bytes = write_json(os.path.join(outdir, "manifest.json"), slim, pretty=True)

    # `region.json` — заголовок регіону для НОВИХ клієнтів: усе те саме, але вже без `byKommune`,
    # бо покомунне вони беруть покомунно. Саме цей файл лишається малим на національному масштабі:
    # `byKommune` на 357 комун коштував би ~2 МБ, а заголовок — десятки кілобайтів.
    region = {k: v for k, v in slim.items() if k != "byKommune"}
    region_bytes = write_json(os.path.join(outdir, "region.json"), region, pretty=True)
    # Масив плиток — для інструментів пайплайну (і для повторного прогону цього ж скрипта).
    # ⚠️ Застосунок його не читає ні зараз, ні раніше: у клієнтському коді немає жодного звернення
    # до `tiles`, і саме тому 129 КБ їхали в кожен телефон дарма.
    write_json(os.path.join(outdir, "tiles.json"),
               {"tileDeg": deg, "dataVersion": manifest.get("dataVersion"), "tiles": manifest["tiles"]})

    # ── ЗВІРКА (числа = приймальний критерій) ────────────────────────────────────────────────────
    print()
    print("=== ЗВІРКА ===")
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("  %-34s %8s vs %-8s %s" % (label, got, want, "OK" if good else "РОЗБІЖНІСТЬ"))

    check("поселень розкладено", sum(len(v) for v in by_tett.values()), len(tett["features"]))
    check("POI розкладено", sum(len(v) for v in by_poi.values()), len(poi["features"]))
    check("ділянок розкладено", sum(len(v) for v in by_trail.values()), len(trails["features"]))
    check("комун в індексі", len(index), len(codes))

    # ⚠️ Плитки СВІДОМО можуть дублюватись між сусідами — звіряємо покриття, не суму.
    #
    # ⚠️ І так само свідомо частина плиток НЕ покривається жодною комуною: bbox джерела —
    # прямокутник, тож у набір заходять шматки сусідніх фюльке (виміряно 2026-08-08: 7 плиток на
    # 36 будівель — Stad, Oppdal, Rindal, Heim). Це не дефект нарізки, а той самий артефакт, що вже
    # ловився на стежках. Такі плитки лишаються доступними НА ЛЬОТУ (плитковий шар про регіони не
    # знає — у цьому й суть P38), просто їх не можна передзавантажити.
    #
    # Поріг, а не нуль: жменя плиток на межі регіону нормальна, сотні означали б поламану
    # прив'язку — і саме цю різницю перевірка мусить бачити.
    covered = {t["key"] for v in by_tiles.values() for t in v}
    all_tiles = manifest.get("tiles", [])
    lost = [t for t in all_tiles if t["key"] not in covered]
    lost_b = sum(t["n"] for t in lost)
    print("  %-34s %8d vs %-8d %s" % ("плиток покрито", len(covered), len(all_tiles),
                                      "OK" if not lost else "поза регіоном — див. нижче"))
    if lost:
        share_t = 100.0 * len(lost) / max(1, len(all_tiles))
        share_b = 100.0 * lost_b / max(1, manifest.get("total", 1))
        print("     %d плиток (%.2f%%) · %d будівель (%.3f%%) поза межами всіх %d комун — "
              "артефакт прямокутного bbox; на льоту доступні, передзавантажити не можна"
              % (len(lost), share_t, lost_b, share_b, len(codes)))
        if share_t > 1.0 or share_b > 0.5:
            print("     ⛔ це вже забагато для артефакту — прив'язка плиток зламана")
            ok = False
    print("  %-34s %8d" % ("комун без жодної плитки", sum(1 for e in index if e["tiles"] == 0)))
    if poi_lost:
        print("  ⚠️ POI поза всіма межами: %d — вони не потраплять у жоден покомунний файл" % poi_lost)
        ok = False

    print()
    print("розмір: покомунні разом %.1f КБ · manifest.json (для 25-27) %.1f КБ, був %.1f КБ (−%.0f%%)"
          % (total_bytes / 1024, slim_bytes / 1024, len(json.dumps(manifest)) / 1024,
             100 * (1 - slim_bytes / max(1, len(json.dumps(manifest))))))
    print("        region.json (для нових) %.1f КБ — саме він лишається малим на 357 комунах"
          % (region_bytes / 1024))
    # ⚠️ Головне число не сума, а те, що тягне ОДИН клієнт. Сума покомунних приблизно дорівнює
    # цілим файлам (структура повторюється), і сама по собі нічого не каже.
    whole = sum(len(json.dumps(x)) for x in (manifest, tett, poi, trails))
    print("що тягне клієнт на першому запуску:")
    for c in sorted(codes, key=lambda c: -(len(by_trail.get(c, [])) + len(by_tett.get(c, [])))) [:3]:
        one = region_bytes + sum(
            os.path.getsize(os.path.join(outdir, sub, c + ext))
            for sub, ext in (("tettsteder", ".geojson"), ("poi", ".geojson"), ("trails", ".geojson")))
        print("  %-16s %6.1f КБ замість %.1f КБ (−%.0f%%)"
              % (koms[c][0][:16], one / 1024, whole / 1024, 100 * (1 - one / whole)))
    print("найбільші комуни за передзавантаженням:")
    for e in sorted(index, key=lambda e: -e["prefetchBytesApprox"])[:5]:
        print("  %-16s %4d плиток · ≈%.1f МБ · маршрутів-ділянок %d"
              % (e["name"][:16], e["tiles"], e["prefetchBytesApprox"] / 1048576, e["trailSegments"]))
    print("→ %s" % outdir)
    print("⚠️ На R2 НЕ залито. Старі цілі файли в корені лишаються — їх читають клієнти 25-27.")
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()

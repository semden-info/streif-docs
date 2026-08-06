# -*- coding: utf-8 -*-
"""Тягне **марковані пішохідні маршрути** з Kartverket Turrutebasen (WFS, шар `app:Fotrute`).

⚠️ Це НЕ те саме, що сусідній `fetch_trails.py`. Той тягне пішу мережу з **OSM** і живить
safety-allowlist для POI (D34 ⑧) — «чи є куди дійти». Цей дає **самі маршрути як контент**
для лінійної механіки D34: те, що людина проходить і що їй зараховується.

Джерело обрано рішенням Q3 брифа (`docs/TRAILS-BRIEF.md`): **лише Turrutebasen**, без OSM `path`.
Підстава не в обсязі, а в безпеці: на Volda+Ørsta у Turrutebasen 22 маркованих маршрути проти 2346
ліній `path` в OSM, і незнакована стежка ≠ безпечна, а ми ведемо людей у гори.

⚠️ **Порядок осей — lat lon.** Сервіс віддає `urn:ogc:def:crs:EPSG::4326`, тобто широта ПЕРША
(перевірено на живій відповіді: `62.192064 6.066404` — це Volda, а не Індійський океан). Той самий
запит із коротким `EPSG:4326` дав би зворотний порядок і мовчазно правдоподібне сміття.

Ліцензія: Kartverket, **CC BY 4.0** — атрибуція вже є в застосунку (`R.string.attribution`).

usage:
    python fetch_turrutebasen.py OUT.xml [minLat minLon maxLat maxLon]
    (деф. bbox — Volda+Ørsta)
"""
import sys
import time
import urllib.request

WFS = "https://wfs.geonorge.no/skwms1/wfs.turogfriluftsruter"
CRS = "urn:ogc:def:crs:EPSG::4326"
PAGE = 500

out = sys.argv[1] if len(sys.argv) > 1 else "turrutebasen_raw.xml"
if len(sys.argv) > 5:
    bbox = tuple(float(x) for x in sys.argv[2:6])
else:
    bbox = (62.05, 5.90, 62.40, 6.60)          # Volda + Ørsta із запасом


def page(start):
    q = (
        f"{WFS}?service=WFS&version=2.0.0&request=GetFeature"
        f"&typenames=app:Fotrute&srsName={CRS}"
        f"&count={PAGE}&startIndex={start}"
        f"&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},{CRS}"
    )
    req = urllib.request.Request(q, headers={"User-Agent": "Streif-pipeline/0.1 (contact@semden.info)"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read()


chunks = []
start = 0
while True:
    for attempt in range(3):
        try:
            raw = page(start)
            break
        except Exception as e:                       # мережа Geonorge буває млява — не падаємо з першої
            print("  спроба %d не вдалась: %s" % (attempt + 1, e), flush=True)
            time.sleep(4)
    else:
        raise SystemExit("Geonorge не відповів після трьох спроб; нічого не записано")

    n = raw.count(b"<app:Fotrute ")
    print("startIndex=%-5d → %d фіч (%d КБ)" % (start, n, len(raw) // 1024), flush=True)
    chunks.append(raw)
    if n < PAGE:
        break
    start += PAGE

# Склеюємо сторінки як є: `build_trails.py` читає їх регулярками пофічно, тож валідний
# спільний GML-конверт не потрібен — а склеювати XML «правильно» коштувало б залежності.
with open(out, "wb") as f:
    for c in chunks:
        f.write(c)

total = sum(c.count(b"<app:Fotrute ") for c in chunks)
print("усього фіч: %d → %s" % (total, out))
sys.exit(0 if total else 2)

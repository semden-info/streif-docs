# -*- coding: utf-8 -*-
"""Генератор довідника `bygningstype.json`: код bygningstype -> людська норвезька назва.

НАВІЩО. У тайлі лежить СИРИЙ код (`bt`, див. build_tiles.py) — 111, 181, 719… Показувати
користувачеві «111» не можна, а зашивати назви в Android-код означало б тримати другу копію
кодлиста. Тож довідник — окремий маленький файл поряд із тайлами.

ДЖЕРЕЛА (обидва офіційні й машиночитні; тому НІЧОГО не вигадуємо руками):
  1. SSB KLASS #31 «Standard for bygningstype / Matrikkelen» — 126 кодів 3-го рівня
     + ієрархія (рівень 1 «hovedfunksjon» -> рівень 2 «bygningsgruppe» -> рівень 3 код).
     https://data.ssb.no/api/klass/v1/classifications/31   (copyrighted=false)
  2. Geonorge SOSI-kodeliste `kartdata/bygningstypekode` — 129 кодів, назви коротші.
     https://register.geonorge.no/api/sosi-kodelister/kartdata/bygningstypekode.json

ЧОМУ ДВА. Звірено запитами 2026-07-20: KLASS — НАДмножина SOSI за винятком рівно трьох кодів,
яких у KLASS немає: 956 «Turisthytter», 970 «Sykehus med akuttmottak», 999 «Ukjent bygningstype».
999 нам критичний — це реальний код у Matrikkelen. Тож база = KLASS (повніші назви + ієрархія),
доповнення = SOSI для цих трьох. Поле `src` у КОЖНОМУ рядку каже, звідки саме назва, — щоб
згодом було видно, що не вигадано (у 45 кодах назви джерел відрізняються редакційно, беремо KLASS).

ЗАПУСК:  python fetch_bygningstype.py bygningstype.json
"""
import sys, json, urllib.request, datetime

UA = {"Accept": "application/json",
      "User-Agent": "Streif-pipeline/1.0 (+https://github.com/streif; contact@semden.info)"}
KLASS = "https://data.ssb.no/api/klass/v1/classifications/31/codesAt?date="
SOSI = "https://register.geonorge.no/api/sosi-kodelister/kartdata/bygningstypekode.json"


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "bygningstype.json"
    today = datetime.date.today().isoformat()

    codes = get(KLASS + today)["codes"]
    by_code = {c["code"]: c for c in codes}
    # рівні 1/2 потрібні лише як назви-батьки для рівня 3 (UI може групувати: «Bolig / Enebolig»)
    lvl3 = [c for c in codes if c["level"] == "3"]

    entries = {}
    for c in lvl3:
        grp = by_code.get(c["parentCode"], {})
        main_ = by_code.get(grp.get("parentCode", ""), {})
        entries[c["code"]] = {"name": c["name"],
                              "group": grp.get("name", ""),
                              "main": main_.get("name", ""),
                              "src": "ssb-klass-31"}

    sosi = {i["codevalue"]: i["label"] for i in get(SOSI)["containeditems"] if i.get("codevalue")}
    added = []
    for code, label in sorted(sosi.items()):
        if code not in entries:                       # 956 / 970 / 999 — у KLASS їх немає
            entries[code] = {"name": label, "group": "", "main": "", "src": "geonorge-sosi-kartdata"}
            added.append(code)

    doc = {"_about": "bygningstype (Matrikkelen) -> норвезька назва. Ключ = той самий код, "
                     "що лежить у властивості `bt` тайла area_*.geojson.",
           "_sources": {"ssb-klass-31": KLASS + "<date>",
                        "geonorge-sosi-kartdata": SOSI},
           "_generated": today,
           "_note": f"База — SSB KLASS #31 ({len(lvl3)} кодів 3-го рівня). Доповнено з SOSI-кодлиста "
                    f"кодами, яких у KLASS немає: {', '.join(added) if added else '—'}. "
                    f"Поле src у кожному рядку — звідки назва.",
           "codes": {k: entries[k] for k in sorted(entries)}}
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{out}: {len(entries)} кодів (KLASS {len(lvl3)} + SOSI-доповнення {len(added)}: {added})")


if __name__ == "__main__":
    main()

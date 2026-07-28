# -*- coding: utf-8 -*-
"""D39 — аналіз телеметрії закритого тесту.

Читає ndjson/json-об'єкти, зняті з R2 (`telemetry/<день>/<install>-<ts>.json`), і відповідає на ті
самі чотири питання, заради яких телеметрію й вмикали:

  1. ЯКІСТЬ МАТЧИНГУ поза Volda   — мітки ✓/✗ + розкриттів на кілометр за одиницями;
  2. ВИЖИВАННЯ ПРОГУЛЯНКИ на чужих OEM — розподіл тривалості/дистанції за моделлю пристрою;
  3. ЗДОРОВ'Я ДАНИХ               — частки невдач зон/тайлів, промахи manifest, стан синку;
  4. RETENTION (P10)              — активні дні, прогулянки на тиждень, крива дожиття.

Запуск:
    python analyze_telemetry.py <тека з json-ами>

Свідомо без залежностей (stdlib) — як і `fieldtest/analyze.py`: цей скрипт має запускатись на
будь-якій машині без підготовки.
"""
import json, os, sys, glob
from collections import defaultdict

# ⚠️ Windows: консоль за замовчуванням cp1252, і будь-який кириличний рядок валить скрипт
# `UnicodeEncodeError` ще до першої цифри. Проєкт розробляється саме на Windows, тож це не
# «про всяк випадок», а обов'язковий рядок — без нього скрипт не запускається взагалі.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DAY = 24 * 60 * 60 * 1000


def load(folder):
    """Усі пакети з теки. Пошкоджений файл пропускаємо гучно — але не валимо прогін."""
    out = []
    for fp in sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True)):
        try:
            with open(fp, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception as e:
            print(f"  ! пропущено {os.path.basename(fp)}: {e}")
    return out


def pct(part, whole):
    return f"{100.0 * part / whole:.1f}%" if whole else "—"


def main(folder):
    batches = load(folder)
    if not batches:
        print("Пакетів не знайдено. Спершу зняти з R2 — див. README.md")
        return
    installs = {b.get("install") for b in batches}
    print(f"пакетів: {len(batches)} · телефонів: {len(installs)}\n")

    # ── 1. Якість матчингу ────────────────────────────────────────────────────────────────────────
    # `marks` — те, що тестер сам позначив. `ok=false` означає «цього будинку я не проходив», тобто
    # хибне розкриття. Це пряма оцінка PRECISION у чужій забудові — того, чого 151 мітка з Volda
    # дати не може. Recall так не міряється: про непозначені пропуски ми нічого не знаємо.
    marks_ok = marks_bad = 0
    bad_ids = []
    for b in batches:
        for m in b.get("marks", []):
            if m.get("ok"):
                marks_ok += 1
            else:
                marks_bad += 1
                bad_ids.append(m.get("id"))
    total_marks = marks_ok + marks_bad
    print("── 1. Якість матчингу (мітки тестерів) ──")
    if total_marks:
        print(f"  позначено: {total_marks} · правильних {marks_ok} · ХИБНИХ {marks_bad} "
              f"({pct(marks_bad, total_marks)})")
        print(f"  precision (за міткам): {pct(marks_ok, total_marks)}")
        if bad_ids:
            print(f"  хибні building_id (перші 20): {', '.join(str(i) for i in bad_ids[:20])}")
            print("  → підняти геометрію цих будинків і подивитись, чим вони схожі "
                  "(вузька вулиця? видовжені? двір?)")
    else:
        print("  міток немає — режим оцінювання ніхто не вмикав")

    # Розкриттів на кілометр — груба, але дуже чутлива ознака. Різкий відхил від volda-норми в
    # чужій одиниці означає, що R_FAR/MIN_EDGE там працюють інакше.
    per_unit = defaultdict(list)
    for b in batches:
        for w in b.get("walks", []):
            dist = w.get("distM", 0.0)
            if dist < 200:          # надто коротка прогулянка — шум, а не сигнал
                continue
            unit = w.get("tett") or (w.get("komm", "") and f"kommune {w['komm']}") or "поза поселенням"
            per_unit[unit].append(w.get("reveals", 0) * 1000.0 / dist)
    if per_unit:
        print("\n  розкриттів на км за одиницями (медіана · прогулянок):")
        for unit, vals in sorted(per_unit.items(), key=lambda kv: -len(kv[1])):
            vals.sort()
            med = vals[len(vals) // 2]
            print(f"    {unit:<28} {med:6.1f}   n={len(vals)}")
        print("  → одиниці з різко нижчою щільністю варті окремого погляду: там або інша забудова,")
        print("    або матчинг не дотягується (те саме, що ловили в Volda до D25).")

    # ── 2. Виживання прогулянки на чужих OEM ──────────────────────────────────────────────────────
    # ⚠️ Прямого дренажу батареї в пакеті НЕМА (модель бере підсумки з Room, а Room про батарею не
    # знає). Тому дивимось ПРОКСІ: якщо на певному OEM прогулянки систематично коротші — це і є
    # підпис «фонову службу вбили». Точний дренаж — окремий інкремент, якщо проксі щось покаже.
    by_device = defaultdict(list)
    for b in batches:
        for w in b.get("walks", []):
            by_device[b.get("device", "?")].append((w.get("durS", 0), w.get("distM", 0.0)))
    print("\n── 2. Прогулянки за пристроєм (проксі на вбивство FGS) ──")
    for dev, ws in sorted(by_device.items(), key=lambda kv: -len(kv[1])):
        durs = sorted(d for d, _ in ws)
        dists = sorted(m for _, m in ws)
        med_d = durs[len(durs) // 2] / 60.0
        med_m = dists[len(dists) // 2]
        short = sum(1 for d in durs if d < 300)      # <5 хв — підозра на обрив, не на прогулянку
        print(f"  {dev:<28} n={len(ws):3d}  медіана {med_d:5.1f} хв / {med_m:6.0f} м  "
              f"· коротших за 5 хв: {short} ({pct(short, len(ws))})")
    print("  → висока частка коротких на одному OEM при нормальній на інших = служба гинула.")

    # ── 3. Здоров'я даних ─────────────────────────────────────────────────────────────────────────
    tot = defaultdict(int)
    http = defaultdict(int)
    for b in batches:
        h = b.get("health") or {}
        for k in ("areaOk", "areaFail", "manifestMiss", "photoFail",
                  "syncOk", "syncFail", "syncRestored", "syncDup"):
            tot[k] += h.get(k, 0)
        for code, n in (h.get("httpFail") or {}).items():
            http[code] += n
    area_total = tot["areaOk"] + tot["areaFail"]
    print("\n── 3. Здоров'я даних ──")
    print(f"  зони: {tot['areaOk']} ок · {tot['areaFail']} невдач ({pct(tot['areaFail'], area_total)})")
    if http:
        print("  коди невдач: " + " · ".join(f"{c}×{n}" for c, n in sorted(http.items(), key=lambda kv: -kv[1])))
    print(f"  промахи manifest: {tot['manifestMiss']} · невдачі фото POI: {tot['photoFail']}")
    sync_total = tot["syncOk"] + tot["syncFail"]
    print(f"  синк: {tot['syncOk']} ок · {tot['syncFail']} невдач ({pct(tot['syncFail'], sync_total)}) "
          f"· відновлень {tot['syncRestored']}")
    # ⚠️ Найважливіший рядок блоку: польова перевірка §B.6 #13.
    if tot["syncDup"]:
        print(f"  ⚠️  ДУБЛІКАТИ КОПІЇ в Drive: {tot['syncDup']} разів — тобто сценарій §B.6 #13 "
              f"реальний, і фікс (злиття замість знищення) працює саме там, де треба")
    else:
        print("  дублікатів копії в Drive не траплялось (фікс §B.6 #13 поки не мав нагоди спрацювати)")

    # ── 4. Retention (P10) ────────────────────────────────────────────────────────────────────────
    # Беремо ОСТАННІЙ пакет кожного телефона: retention у ньому кумулятивний.
    latest = {}
    for b in batches:
        i = b.get("install")
        if i and (i not in latest or b.get("ts", 0) > latest[i].get("ts", 0)):
            latest[i] = b
    print("\n── 4. Retention (P10 — міряємо, не припускаємо) ──")
    rows = []
    for i, b in latest.items():
        r = b.get("retention") or {}
        days = r.get("days", 0)
        active = r.get("activeDays", 0)
        rows.append((days, active, r.get("walks", 0), r.get("reveals", 0), i))
    rows.sort(reverse=True)
    print(f"  {'днів':>5} {'активних':>9} {'прогулянок':>11} {'розкрито':>9}  телефон")
    for days, active, walks, reveals, i in rows:
        print(f"  {days:>5} {active:>9} {walks:>11} {reveals:>9}  {str(i)[:8]}")
    if rows:
        alive = sum(1 for d, a, *_ in rows if d >= 7 and a >= 2)
        print(f"\n  телефонів із ≥7 днів і ≥2 активними днями: {alive} з {len(rows)}")
        print("  → це і є питання P10. Мала вибірка — дивитись на форму, не на відсоток.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])

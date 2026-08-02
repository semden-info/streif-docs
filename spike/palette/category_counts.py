# -*- coding: utf-8 -*-
import json, collections

BT = r"C:/Users/mail/OneDrive/Projects/Streif/spike/pipeline/bygningstype.json"
MAN = r"C:/Users/mail/AppData/Local/Temp/claude/C--Users-mail-OneDrive-Projects-Streif--claude-worktrees-musing-moore-821b72/9096a584-cdbe-4f64-ae3b-f4adee00e862/scratchpad/dbcheck/files/manifest.json"

bt = json.load(open(BT, encoding="utf-8"))["codes"]
man = json.load(open(MAN, encoding="utf-8"))

# --- 0. sanity ---
print("region:", man["region"], "dataVersion:", man["dataVersion"], "generated:", man["generated"])
print("total:", man["total"], "accessible:", man["accessible"])
print("btUnknown:", man["bygningstypeUnknown"])
byBt = man["byBygningstype"]
print("codes in manifest:", len(byBt), " codes in asset:", len(bt))
print("in manifest not in asset:", sorted(set(byBt) - set(bt)))
print("in asset not in manifest:", sorted(set(bt) - set(byBt)))
sum_t = sum(v["total"] for v in byBt.values())
sum_a = sum(v["accessible"] for v in byBt.values())
print("sum byBygningstype total/acc:", sum_t, sum_a,
      "+unknown ->", sum_t + man["bygningstypeUnknown"]["total"],
      sum_a + man["bygningstypeUnknown"]["accessible"])

# --- 1. group -> category (Semden 12 + дві ухвалені заміни) ---
G2C = {
    "Enebolig": "Bolig",
    "Tomannsbolig": "Bolig",
    "Rekkehus, kjedehus, andre småhus": "Bolig",          # ЗАМІНА 1
    "Store boligbygg": "Bolig",
    "Annen boligbygning": "Bolig",
    "Bygning for bofellesskap": "Bolig",
    "Garasje og uthus til bolig": "Garasje/uthus",
    "Garasje- og hangarbygning": "Garasje/uthus",
    "Fritidsbolig": "Hytte",
    "Koie, seterhus og lignende": "Hytte",
    "Fiskeri- og landbruksbygning": "Landbruk/fiske",
    "Industribygning": "Industri/energi",                  # ЗАМІНА 2
    "Energiforsyningsbygning": "Industri/energi",          # ЗАМІНА 2
    "Lagerbygning": "Lager",
    "Forretningsbygning": "Handel/kontor",
    "Kontorbygning": "Handel/kontor",
    "Bygning for overnatting": "Handel/service",
    "Restaurantbygning": "Handel/service",
    "Hotellbygning": "Handel/service",
    "Skolebygning": "Samfunn/kultur",
    "Idrettsbygning": "Samfunn/kultur",
    "Kulturhus": "Samfunn/kultur",
    "Museums- og biblioteksbygning": "Samfunn/kultur",
    "Universitet- og høgskolebygning": "Samfunn/kultur",
    "Beredskapsbygning": "Samfunn/kultur",
    "Sykehjem": "Helsebygning",
    "Primærhelsebygning": "Helsebygning",
    "Sykehus": "Helsebygning",
    "Bygning for religiøse aktiviteter": "Sakral",
    "Offentlig toalett": "Andre",
    "Monument": "Andre",
    "Fengselsbygning": "Andre",
    "Ekspedisjonsbygning, terminal": "Andre",
    "Veg- og trafikktilsynsbygning": "Andre",
    "Telekommunikasjonsbygning": "Andre",
}

groups_seen = collections.Counter()
code2cat, code2grp = {}, {}
for code, meta in bt.items():
    g = meta.get("group")
    groups_seen[g] += 1
    if g is None or g == "":
        cat = "Andre"
        g = "(без групи)"
    else:
        cat = G2C.get(g)
    code2grp[code] = g
    if cat is None:
        raise SystemExit("НЕЗМАПОВАНА ГРУПА: %r (код %s)" % (g, code))
    code2cat[code] = cat

print("\nгруп у асеті:", len(groups_seen), sorted(groups_seen.items(), key=lambda x: str(x[0]))[:3])
print("груп без назви:", groups_seen.get(None, 0) + groups_seen.get("", 0))

# коди, що є в manifest, але не в асеті — кинути в Andre явно
extra = sorted(set(byBt) - set(bt))
for c in extra:
    code2cat[c] = "Andre"
    code2grp[c] = "(немає в асеті)"

ORDER = ["Bolig", "Garasje/uthus", "Landbruk/fiske", "Hytte", "Industri/energi",
         "Samfunn/kultur", "Lager", "Handel/kontor", "Handel/service",
         "Helsebygning", "Sakral", "Andre"]

# --- 2. регіональні тотали ---
cat_total = collections.Counter()
cat_acc = collections.Counter()
cat_codes = collections.defaultdict(list)
cat_groups = collections.defaultdict(set)
for code, cat in code2cat.items():
    cat_codes[cat].append(int(code))
    cat_groups[cat].add(code2grp[code])
    v = byBt.get(code)
    if v:
        cat_total[cat] += v["total"]
        cat_acc[cat] += v["accessible"]

# --- 3. per kommune: >=5 ДОСЯЖНИХ ---
byKom = man["byKommune"]
print("\nкомун:", len(byKom))
kom5 = collections.Counter()
kom_present = collections.Counter()   # >=1 досяжна
per_kom_detail = collections.defaultdict(dict)
for kcode, ke in byKom.items():
    kname = ke.get("name", kcode)
    acc_by_cat = collections.Counter()
    for code, v in ke.get("byBygningstype", {}).items():
        cat = code2cat.get(code, "Andre")
        acc_by_cat[cat] += v["accessible"]
    for cat in ORDER:
        n = acc_by_cat[cat]
        per_kom_detail[cat][kname] = n
        if n >= 5:
            kom5[cat] += 1
        if n >= 1:
            kom_present[cat] += 1

# --- 4. звіт ---
print("\n%-18s %9s %9s %7s %7s %5s  %s" % ("категорія", "усього", "досяжних", ">=5/27", ">=1/27", "кодів", "групи"))
tt = ta = 0
for cat in ORDER:
    tt += cat_total[cat]; ta += cat_acc[cat]
    print("%-18s %9d %9d %7d %7d %5d  %s" % (
        cat, cat_total[cat], cat_acc[cat], kom5[cat], kom_present[cat],
        len(cat_codes[cat]), " · ".join(sorted(cat_groups[cat]))))
print("%-18s %9d %9d" % ("СУМА", tt, ta))
print("manifest total/acc:", man["total"], man["accessible"])
print("різниця (btUnknown):", man["total"] - tt, man["accessible"] - ta)

# --- 5. перевірка неперетину / повноти ---
allcodes = [c for cat in ORDER for c in cat_codes[cat]]
assert len(allcodes) == len(set(allcodes)), "ПЕРЕТИН КОДІВ!"
print("\nкодів усього:", len(allcodes), "унікальних:", len(set(allcodes)))
missing_in_map = sorted(set(byBt) - set(str(c) for c in allcodes))
print("коди з manifest поза мапінгом:", missing_in_map)

# --- 6. деталі Andre ---
print("\n--- ANDRE: розклад ---")
for c in sorted(cat_codes["Andre"]):
    v = byBt.get(str(c), {"total": 0, "accessible": 0})
    print("  %s %-55s grp=%-32s total=%6d acc=%6d" % (
        c, bt.get(str(c), {}).get("name", "?")[:55], code2grp[str(c)][:32], v["total"], v["accessible"]))
print("  bygningstypeUnknown (нема bt узагалі):", man["bygningstypeUnknown"])

# --- 7. коми де категорія <5 ---
print("\n--- де категорія НЕ дотягує до 5 досяжних ---")
for cat in ORDER:
    bad = sorted([(n, k) for k, n in per_kom_detail[cat].items() if n < 5])
    if bad:
        print("%-18s (%d комун): %s" % (cat, len(bad), ", ".join("%s=%d" % (k, n) for n, k in bad)))

# --- 8. повні списки кодів ---
print("\n--- ПОВНІ СПИСКИ КОДІВ ---")
for cat in ORDER:
    print("%-18s (%d): %s" % (cat, len(cat_codes[cat]), ", ".join(str(c) for c in sorted(cat_codes[cat]))))

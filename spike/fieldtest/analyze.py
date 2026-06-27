# -*- coding: utf-8 -*-
"""Field-test analysis: matching timing (too-early), cross-street misses, gate, battery.
Pure-python planar geometry (cheap-ruler), no shapely."""
import json, math, glob, os, bisect
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
KLAT = 111320.0
def klon(lat): return 111320.0 * math.cos(math.radians(lat))
REF_LAT = 62.146
KLON_REF = klon(REF_LAT)
R_APP = 20.0          # current matching radius (centroid<->point/segment)
ACC_MAX = 30.0

# ---------- load buildings ----------
buildings = {}   # id -> {ring:[(lon,lat)], cen:(lon,lat)}
for fp in glob.glob(os.path.join(BASE, "area_*.geojson")):
    fc = json.load(open(fp, encoding="utf-8"))
    for f in fc["features"]:
        pid = f.get("properties", {}).get("building_id")
        if not pid or pid in buildings:
            continue
        g = f.get("geometry") or {}
        t = g.get("type")
        if t == "Polygon": ring = g["coordinates"][0]
        elif t == "MultiPolygon": ring = g["coordinates"][0][0]
        else: continue
        n = len(ring)
        cx = sum(p[0] for p in ring) / n
        cy = sum(p[1] for p in ring) / n   # vertex-avg = matches app centroid()
        buildings[pid] = {"ring": ring, "cen": (cx, cy)}
print(f"buildings loaded: {len(buildings)}")

# ---------- grid over centroids ----------
CELL = 50.0
def cellof(lon, lat): return (int(math.floor(lon*KLON_REF/CELL)), int(math.floor(lat*KLAT/CELL)))
grid = defaultdict(list)
for pid, b in buildings.items():
    grid[cellof(*b["cen"])].append(pid)
def near_ids(lon, lat, rad):
    span = int(rad/CELL)+1; cx, cy = cellof(lon, lat); out = []
    for dx in range(-span, span+1):
        for dy in range(-span, span+1):
            out += grid.get((cx+dx, cy+dy), [])
    return out

def d_centroid(lon, lat, b):
    kl = klon(lat); dx = (b["cen"][0]-lon)*kl; dy = (b["cen"][1]-lat)*KLAT
    return math.hypot(dx, dy)

def pt_seg(px, py, ax, ay, bx, by):
    dx = bx-ax; dy = by-ay; L2 = dx*dx+dy*dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/L2))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))

def inside_edge(lon, lat, b):
    """(inside_bool, edge_dist_m) — edge_dist 0 if inside."""
    kl = klon(lat); px = lon*kl; py = lat*KLAT
    ring = b["ring"]; inside = False; mind = 1e18
    for i in range(len(ring)-1):
        x1, y1 = ring[i]; x2, y2 = ring[i+1]
        d = pt_seg(px, py, x1*kl, y1*KLAT, x2*kl, y2*KLAT)
        if d < mind: mind = d
        if (y1 > lat) != (y2 > lat):
            xint = (x2-x1)*(lat-y1)/(y2-y1)+x1
            if lon < xint: inside = not inside
    return inside, (0.0 if inside else mind)

def pct(vals, p):
    if not vals: return float('nan')
    s = sorted(vals); k = (len(s)-1)*p/100.0
    f = int(math.floor(k)); c = min(f+1, len(s)-1)
    return s[f] + (s[c]-s[f])*(k-f)

# ---------- load diag track ----------
track = []  # dict t,lat,lon,acc,speed,matched,total,note,batt,uah
for ln in open(os.path.join(BASE, "diag.csv"), encoding="utf-8"):
    ln = ln.strip()
    if not ln: continue
    p = ln.split(",")
    if len(p) < 9: continue
    try:
        track.append(dict(t=int(p[0]), lat=float(p[1]), lon=float(p[2]),
                          acc=float(p[3]), speed=float(p[4]), matched=int(p[5]),
                          total=int(p[6]), note=",".join(p[7:-2]),
                          batt=int(p[-2]), uah=int(p[-1])))
    except ValueError:
        continue
track.sort(key=lambda r: r["t"])
T = [r["t"] for r in track]
print(f"diag fixes: {len(track)}")

# ---------- segment into walks (gap > 120s) ----------
walks = []; cur = [track[0]]
for r in track[1:]:
    if r["t"] - cur[-1]["t"] > 120000:
        walks.append(cur); cur = [r]
    else:
        cur.append(r)
walks.append(cur)

def gps_at(t):
    i = bisect.bisect_left(T, t)
    cands = [j for j in (i-1, i) if 0 <= j < len(track)]
    if not cands: return None
    j = min(cands, key=lambda k: abs(track[k]["t"]-t))
    return track[j]

# ---------- load visited (reveals with timestamp) ----------
visited = []  # (id,type,t)
for ln in open(os.path.join(BASE, "visited.txt"), encoding="utf-8"):
    ln = ln.strip()
    if not ln: continue
    p = ln.split(",")
    if len(p) >= 3:
        visited.append((p[0], p[1], int(p[2])))
vis_ids = set(v[0] for v in visited)

# ---------- load marks (ground truth) ----------
marks = []  # dict id,mark,lat,lon,was,t
for ln in open(os.path.join(BASE, "marks.csv"), encoding="utf-8"):
    ln = ln.strip()
    if not ln: continue
    p = ln.split(",")
    if len(p) >= 6:
        marks.append(dict(t=int(p[0]), id=p[1], mark=p[2], lat=float(p[3]),
                          lon=float(p[4]), was=(p[5].lower() == "true")))
# final mark per building (last action wins the cycle)
final_mark = {}
for m in marks:
    final_mark[m["id"]] = m
print(f"visited: {len(visited)}  | marks rows: {len(marks)}  unique marked: {len(final_mark)}")

# ---------- closest approach of track to every near building ----------
min_edge = {}   # id -> (edge_dist, t)
for r in track:
    for pid in near_ids(r["lon"], r["lat"], 80.0):
        _, ed = inside_edge(r["lon"], r["lat"], buildings[pid])
        if pid not in min_edge or ed < min_edge[pid][0]:
            min_edge[pid] = (ed, r["t"])

print("\n================ 1. WALKS ================")
for i, w in enumerate(walks, 1):
    dur = (w[-1]["t"]-w[0]["t"])/60000.0
    sp = [r["speed"] for r in w if r["speed"] >= 0]
    accs = [r["acc"] for r in w if r["acc"] >= 0]
    db = w[0]["batt"]-w[-1]["batt"]
    duah = (w[0]["uah"]-w[-1]["uah"])/1000.0   # mAh discharged (+ = discharge)
    charging = w[-1]["uah"] > w[0]["uah"]
    spd_med = pct(sp, 50); kind = "АВТО" if spd_med > 3.0 else "пішки"
    blocked = sum(1 for r in w if r["note"] not in ("ok", "") and "точність" not in r["note"])
    print(f"  Walk {i}: {kind:5s} {len(w):4d} фікс  {dur:5.1f}хв  v_med={spd_med:4.1f} v_p90={pct(sp,90):4.1f} m/s"
          f"  acc_med={pct(accs,50):4.1f} p90={pct(accs,90):4.1f}m  батарея {db:+d}% ({duah:+.0f}mAh{' CHARGING' if charging else ''})"
          f"  gate-block-фіксів={blocked}")

print("\n================ 2. GPS / ACCURACY ================")
allacc = [r["acc"] for r in track if r["acc"] >= 0]
print(f"  acc: med={pct(allacc,50):.1f}  p75={pct(allacc,75):.1f}  p90={pct(allacc,90):.1f}  p95={pct(allacc,95):.1f}  max={max(allacc):.1f}")
print(f"  фіксів з acc>20м: {sum(1 for a in allacc if a>20)} ({100*sum(1 for a in allacc if a>20)/len(allacc):.0f}%)  | acc>{ACC_MAX:.0f} (відкинуто): рахуються в gate")

print("\n================ 3. БАТАРЕЯ ================")
net_uah = (track[0]["uah"]-track[-1]["uah"])/1000.0
print(f"  net за сесію: {track[0]['batt']}%→{track[-1]['batt']}% ({net_uah:+.0f} mAh)  "
      f"{'<- ЗАРЯДЖАВСЯ (авто/USB) -> чистий замір неможливий' if net_uah<0 else ''}")
# discharge тільки на піших фіксах (speed<=2.5), коли uah спадає
foot_disch = 0.0; foot_t = 0
for a, b in zip(track, track[1:]):
    if a["speed"] >= 0 and a["speed"] <= 2.5 and (a["t"]-track[0]['t']):
        d = (a["uah"]-b["uah"])/1000.0; dt = b["t"]-a["t"]
        if d > 0 and dt < 10000:   # розряд, нормальний інтервал
            foot_disch += d; foot_t += dt
if foot_t:
    print(f"  розряд на піших фіксах: {foot_disch:.0f} mAh за {foot_t/60000:.0f}хв = {foot_disch/(foot_t/3600000):.0f} mAh/год (груба, екран часто ON через маркування)")
print("  -> для чистого присуду Stage C треба окрема піша прогулянка БЕЗ кабелю і без маркування")

print("\n================ 4. VEHICLE-GATE (fix-level) ================")
fast = [r for r in track if r["speed"] > 3.0]
fast_blocked = sum(1 for r in fast if r["note"] not in ("ok", ""))
fast_matched = sum(r["matched"] for r in fast if r["speed"] > 3.0)
fast_ok = [r for r in fast if r["note"] == "ok"]
print(f"  швидких фіксів (>3 m/s): {len(fast)}  | заблоковано gate: {fast_blocked} ({100*fast_blocked/max(1,len(fast)):.0f}%)")
print(f"  РОЗКРИТО під час швидких фіксів (leak): {fast_matched}  | швидких але note=ok: {len(fast_ok)}")
gnotes = defaultdict(int)
for r in track:
    if r["note"] not in ("ok", ""): gnotes[r["note"]] += 1
for nt, c in sorted(gnotes.items(), key=lambda x:-x[1])[:6]:
    print(f"     блок-note '{nt}': {c}")

print("\n================ 5. ТАЙМИНГ РОЗКРИТТЯ ('зарано'?) ================")
ed_at_reveal = []; cen_at_reveal = []; lead_m = []; far_reveals = 0
for (pid, typ, tr) in visited:
    b = buildings.get(pid)
    if not b: continue
    g = gps_at(tr)
    if not g: continue
    inside, ed = inside_edge(g["lon"], g["lat"], b)
    cd = d_centroid(g["lon"], g["lat"], b)
    ed_at_reveal.append(ed); cen_at_reveal.append(cd)
    if ed > 10: far_reveals += 1
    # lead vs closest approach
    if pid in min_edge:
        ed_min, t_min = min_edge[pid]
        # approx ground distance travelled reveal->closest (sum along track)
        lo, hi = sorted((tr, t_min))
        seg = [r for r in track if lo <= r["t"] <= hi]
        dd = 0.0
        for a, bb in zip(seg, seg[1:]):
            kl = klon(a["lat"]); dd += math.hypot((bb["lon"]-a["lon"])*kl, (bb["lat"]-a["lat"])*KLAT)
        if tr < t_min - 1000:   # revealed BEFORE closest approach
            lead_m.append(dd)
print(f"  розкрито будинків (з геометрією): {len(ed_at_reveal)}")
print(f"  EDGE-дист у момент розкриття:  med={pct(ed_at_reveal,50):.1f}  p75={pct(ed_at_reveal,75):.1f}  p90={pct(ed_at_reveal,90):.1f}  max={max(ed_at_reveal):.1f} м")
print(f"  CENTROID-дист у момент розкр.: med={pct(cen_at_reveal,50):.1f}  p90={pct(cen_at_reveal,90):.1f} м")
print(f"  розкрито коли GPS >10м від СТІНИ будинку: {far_reveals}/{len(ed_at_reveal)} ({100*far_reveals/len(ed_at_reveal):.0f}%)  <- 'зарано'")
print(f"  розкрито ПЕРЕД точкою найближчого підходу: {len(lead_m)} буд., випередження med={pct(lead_m,50):.1f}м p90={pct(lead_m,90):.1f}м")

print("\n================ 6. ПРОПУСКИ (marks wasRevealed=false) ================")
missed = [m for m in final_mark.values() if not m["was"] and m["mark"] in ("correct", "wrong")]
print(f"  позначено як пропущені (не розкрилися): {len(missed)}")
reason = defaultdict(int); miss_edge = []; miss_cen = []
for m in missed:
    b = buildings.get(m["id"])
    if not b:
        reason["немає в store (зона не довантажена?)"] += 1; continue
    ce = min_edge.get(m["id"], (1e9, 0))[0]
    miss_edge.append(ce)
    # min centroid over track
    mc = 1e9
    for r in track:
        d = d_centroid(r["lon"], r["lat"], b)
        if d < mc: mc = d
    miss_cen.append(mc)
    if mc <= R_APP: reason["центроїд БУВ ≤20м (інша причина: gate/accuracy/seg)"] += 1
    elif ce <= 12: reason["edge≤12 але centroid>20 (центроїдний матчинг винен — видовжений/через дорогу)"] += 1
    elif ce <= 20: reason["edge 12-20 (потрібен edge-матчинг ~20м)"] += 1
    elif ce <= 30: reason["edge 20-30 (широка вулиця/далеко)"] += 1
    else: reason["edge>30 (далеко від треку — мабуть не повз нього йшов)"] += 1
if miss_edge:
    print(f"  min EDGE-дист треку до пропущених: med={pct(miss_edge,50):.1f} p90={pct(miss_edge,90):.1f}м")
    print(f"  min CENTROID-дист: med={pct(miss_cen,50):.1f} p90={pct(miss_cen,90):.1f}м")
for rs, c in sorted(reason.items(), key=lambda x:-x[1]):
    print(f"    {c:3d}  {rs}")

print("\n================ 7. MARKS зведення ================")
cc = defaultdict(int)
for m in final_mark.values():
    cc[(m["mark"], m["was"])] += 1
for (mk, was), c in sorted(cc.items()):
    print(f"  mark={mk:8s} wasRevealed={str(was):5s}: {c}")
false_reveals = [m for m in final_mark.values() if m["mark"] == "wrong" and m["was"]]
print(f"  ✗ ХИБНІ розкриття (wrong + wasRevealed): {len(false_reveals)}")

print("\n================ 8. СИМУЛЯЦІЯ КАНДИДАТІВ (виправлена ground-truth) ================")
# СЕМАНТИКА міток:
#   ✓correct+was=true  -> правильно розкрито           => SHOULD reveal
#   ✗wrong  +was=false -> «неправильно що НЕ розкрито»  => SHOULD reveal (пропуск через дорогу)
#   ✗wrong  +was=true  -> розкрито, але «неправильно»   => SHOULD-NOT / погана подія (зарано/чужий)
should = set(m["id"] for m in final_mark.values()
             if (m["mark"] == "correct" and m["was"]) or (m["mark"] == "wrong" and not m["was"]))
should_not = set(m["id"] for m in final_mark.values() if m["mark"] == "wrong" and m["was"])
print(f"  SHOULD reveal={len(should)}  SHOULD-NOT={len(should_not)}")
print(f"  edge-дист 'should-not' будинків до треку: " +
      ", ".join(f"{min_edge.get(p,(99,0))[0]:.0f}" for p in should_not))

# heading per track index (з попереднього зміщення)
def bearing(lon1, lat1, lon2, lat2):
    kl = klon(lat1); return math.degrees(math.atan2((lon2-lon1)*kl, (lat2-lat1)*KLAT))
heading = [None]*len(track)
for i in range(1, len(track)):
    a, b = track[i-1], track[i]
    if math.hypot((b["lon"]-a["lon"])*klon(a["lat"]), (b["lat"]-a["lat"])*KLAT) >= 1.0:
        heading[i] = bearing(a["lon"], a["lat"], b["lon"], b["lat"])
    else:
        heading[i] = heading[i-1]

def angdiff(a, b):
    d = abs((a-b+180) % 360 - 180); return d

def simulate(mode, R, abreast=None):
    """mode='centroid'|'edge'; abreast=deg threshold (None=off)."""
    revealed = {}; reveal_ed = {}
    for i, r in enumerate(track):
        if r["acc"] > ACC_MAX or r["note"] != "ok":
            continue
        for pid in near_ids(r["lon"], r["lat"], 45.0):
            if pid in revealed: continue
            b = buildings[pid]
            if mode == "centroid":
                d = d_centroid(r["lon"], r["lat"], b); ins = False; ed = d; hit = d <= R
            else:
                ins, ed = inside_edge(r["lon"], r["lat"], b); hit = ins or ed <= R
            if not hit: continue
            if abreast is not None and not ins and heading[i] is not None:
                bb = bearing(r["lon"], r["lat"], b["cen"][0], b["cen"][1])
                if angdiff(heading[i], bb) < abreast:   # будинок ще ПОПЕРЕДУ -> чекаємо
                    continue
            revealed[pid] = r["t"]; reveal_ed[pid] = ed
    return set(revealed), reveal_ed

print(f"  {'rule':28s} {'recall':>9s} {'хибних':>7s} {'edge@reveal med/p90':>22s}")
cands = [("centroid R=20 (ЗАРАЗ)", "centroid", 20, None),
         ("edge R=14", "edge", 14, None),
         ("edge R=16", "edge", 16, None),
         ("edge R=18", "edge", 18, None),
         ("edge R=20", "edge", 20, None),
         ("edge R=18 +abreast75", "edge", 18, 75),
         ("edge R=20 +abreast75", "edge", 20, 75),
         ("edge R=22 +abreast75", "edge", 22, 75),
         ("edge R=20 +abreast90", "edge", 20, 90)]
for name, mode, R, ab in cands:
    rv, red = simulate(mode, R, ab)
    rec = len(rv & should); fp = len(rv & should_not)
    eds = [red[p] for p in rv if p in red]
    print(f"  {name:28s} {rec:3d}/{len(should):<4d} {fp:4d}/{len(should_not):<2d} "
          f"   {pct(eds,50):5.1f}/{pct(eds,90):5.1f}m")

# --- closest-approach gate: розкрити коли edge почала РОСТИ (проминув найближчу точку) ---
def simulate_closest(R, slack=1.5, near_small=6.0):
    runmin = {}; revealed = {}; reveal_ed = {}
    for r in track:
        if r["acc"] > ACC_MAX or r["note"] != "ok":
            continue
        for pid in near_ids(r["lon"], r["lat"], 45.0):
            if pid in revealed: continue
            ins, ed = inside_edge(r["lon"], r["lat"], buildings[pid])
            if not (ins or ed <= R):
                if pid in runmin: runmin[pid] = min(runmin[pid], ed)
                continue
            rm = runmin.get(pid, ed); runmin[pid] = min(rm, ed)
            # розкрити: всередині, АБО дуже близько, АБО вже проминув (edge > мінімум+slack)
            if ins or ed <= near_small or ed > runmin[pid] + slack:
                revealed[pid] = r["t"]; reveal_ed[pid] = ed
    return set(revealed), reveal_ed
for R in (18, 20, 22):
    rv, red = simulate_closest(R)
    rec = len(rv & should); fp = len(rv & should_not)
    eds = [red[p] for p in rv if p in red]
    print(f"  {'edge R='+str(R)+' +closest-approach':28s} {rec:3d}/{len(should):<4d} {fp:4d}/{len(should_not):<2d} "
          f"   {pct(eds,50):5.1f}/{pct(eds,90):5.1f}m")

print("\n================ 9. ХАРАКТЕРИСТИКА СПІРНИХ МІТОК ================")
print("  -- 6 будинків: БУЛО розкрито, але позначено ✗ wrong --")
print(f"  {'id':14s} {'тип':12s} {'edge@розкр':>10s} {'найбл.підхід':>12s} {'висновок':>26s}")
rev_t = {v[0]: v[2] for v in visited}
rev_ty = {v[0]: v[1] for v in visited}
for m in final_mark.values():
    if not (m["mark"] == "wrong" and m["was"]): continue
    pid = m["id"]; b = buildings.get(pid)
    if not b: 
        print(f"  {pid:14s} (немає геометрії)"); continue
    ed_rev = None
    if pid in rev_t:
        g = gps_at(rev_t[pid])
        if g: _, ed_rev = inside_edge(g["lon"], g["lat"], b)
    cmin = min_edge.get(pid, (None,0))[0]
    if cmin is not None and cmin <= 6:
        verdict = "ПІДІЙШОВ впритул -> ЗАРАНО"
    elif cmin is not None and cmin <= 12:
        verdict = "підійшов помірно"
    else:
        verdict = "НЕ підходив -> через дорогу/далеко"
    er = f"{ed_rev:.0f}м" if ed_rev is not None else "?"
    cm = f"{cmin:.0f}м" if cmin is not None else "?"
    print(f"  {pid:14s} {rev_ty.get(pid,'?'):12s} {er:>10s} {cm:>12s} {verdict:>26s}")

print("\n  -- 15 будинків: НЕ розкрито, позначено ✗ (пропуски) --")
print(f"  {'id':14s} {'найбл.підхід(edge)':>18s} {'centroid':>9s} {'тип на карті?':>14s}")
for m in final_mark.values():
    if not (m["mark"] == "wrong" and not m["was"]): continue
    pid = m["id"]; b = buildings.get(pid)
    if not b:
        print(f"  {pid:14s}  НЕМАЄ в store (зона не довантажилась?)"); continue
    cmin = min_edge.get(pid,(None,0))[0]
    mc = min(d_centroid(r["lon"], r["lat"], b) for r in track)
    cm = f"{cmin:.0f}м" if cmin is not None else "?"
    print(f"  {pid:14s} {cm:>18s} {mc:>8.0f}м")

print("\n================ 10. ДВОРАДІУСНИЙ ГІБРИД ================")
def simulate_two_radius(r_near, r_far, slack=1.5):
    runmin = {}; revealed = {}; reveal_ed = {}
    for r in track:
        if r["acc"] > ACC_MAX or r["note"] != "ok": continue
        for pid in near_ids(r["lon"], r["lat"], 45.0):
            if pid in revealed: continue
            ins, ed = inside_edge(r["lon"], r["lat"], buildings[pid])
            if ed <= r_far + 10:
                runmin[pid] = min(runmin.get(pid, ed), ed)
            if ins or ed <= r_near:
                revealed[pid] = r["t"]; reveal_ed[pid] = ed
            elif ed <= r_far and pid in runmin and ed > runmin[pid] + slack:
                revealed[pid] = r["t"]; reveal_ed[pid] = ed
    return set(revealed), reveal_ed

print(f"  {'rule':30s} {'recall':>8s} {'хибних':>7s} {'edge@reveal med/p90':>22s}  (житло3 / сараї3)")
# окремо housing-early(3) vs outbuilding-far(3)
house_early = set(m["id"] for m in final_mark.values() if m["mark"]=="wrong" and m["was"]
                  and rev_ty_g.get(m["id"])=="housing") if False else None
for rn, rf in [(6,16),(8,16),(8,18),(8,20),(10,18),(10,20),(12,20)]:
    rv, red = simulate_two_radius(rn, rf)
    rec = len(rv & should); fp = len(rv & should_not)
    eds = [red[p] for p in rv if p in red]
    # розкіл should_not по типу
    sn_house = sum(1 for p in (rv & should_not) if rev_ty.get(p)=="housing")
    sn_out = sum(1 for p in (rv & should_not) if rev_ty.get(p) and rev_ty.get(p)!="housing")
    print(f"  near={rn:>2} far={rf:<2} +closest      {rec:3d}/{len(should):<3d} {fp:4d}/{len(should_not):<2d} "
          f"   {pct(eds,50):5.1f}/{pct(eds,90):5.1f}m        ({sn_house}/{sn_out})")

print("\n================ 11. ВЕРИФІКАЦІЯ ВПРОВАДЖЕНОГО ФІКСУ (replay) ================")
# ТОЧНА логіка TrackingRepository.matchAt: edge≤MIN_EDGE АБО edge>priorMin+SLACK
R_FAR, MIN_EDGE, SLACK = 18.0, 8.0, 1.5
def replay_impl():
    runmin = {}; revealed = {}; reveal_ed = {}
    for r in track:
        if r["acc"] > ACC_MAX or r["note"] != "ok":   # той самий matchable-гейт, що в застосунку
            continue
        for pid in near_ids(r["lon"], r["lat"], R_FAR + 5):
            ins, ed = inside_edge(r["lon"], r["lat"], buildings[pid])
            if ed > R_FAR and not ins:
                continue
            prior = runmin.get(pid)
            runmin[pid] = ed if prior is None else min(prior, ed)
            if pid in revealed:
                continue
            passed = prior is not None and ed > prior + SLACK
            if ed <= MIN_EDGE or passed:
                revealed[pid] = r["t"]; reveal_ed[pid] = ed
    return set(revealed), reveal_ed

rv, red = replay_impl()
rec = len(rv & should); fp = len(rv & should_not)
eds = [red[p] for p in rv if p in red]
print(f"  НОВА логіка: розкрито {len(rv)} буд. | recall {rec}/{len(should)} | хибних {fp}/{len(should_not)}")
print(f"  edge@reveal: med={pct(eds,50):.1f}  p90={pct(eds,90):.1f} м")
print(f"  СТАРА (centroid R=20): recall 69/83, edge@reveal med 19.2 м")
print(f"  -> recall {69}→{rec} (+{rec-69}) | edge@reveal 19.2→{pct(eds,50):.1f} м (тайминг ↓ {19.2-pct(eds,50):.1f} м)")

# чи ловляться тепер 15 раніше-пропущених (✗ wasRevealed=false)?
missed_ids = [m["id"] for m in final_mark.values() if m["mark"]=="wrong" and not m["was"]]
now_caught = sum(1 for p in missed_ids if p in rv)
print(f"  раніше-пропущені (✗ не розкриті): {now_caught}/{len(missed_ids)} тепер ловляться")
# спец-кейс: 2 видовжені будинки, повз які пройшов за 2-6 м
for pid in ("w632007457", "w909011994", "w986947820"):
    if pid in buildings:
        ce = min_edge.get(pid,(None,0))[0]
        print(f"    {pid} (стіна {ce:.0f}м, центроїд далеко): {'РОЗКРИТО ✓' if pid in rv else 'НЕ розкрито ✗'}")

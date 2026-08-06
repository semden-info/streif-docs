# -*- coding: utf-8 -*-
"""Кандидати кольору ПРОЙДЕНОЇ стежки в режимі «природа» (заувага Дениса: яскравіше, можливо жовте).

Міряємо проти того, що РЕАЛЬНО на екрані в природному режимі:
  • 12 заливок будівель, композитно при fillOpacity 0,55 поверх підложки (вони там блідніють);
  • 7 кольорів POI на повну (у природі вони, навпаки, БІЛЬШІ й головніші);
  • базовий пунктир стежки.
Плюс контраст до підложки (видимість) і симуляція дальтонізму.
"""
import importlib.util, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "palette_check.py")
spec = importlib.util.spec_from_file_location('pc', SRC)
m = importlib.util.module_from_spec(spec); sys.modules['pc'] = m
try:
    spec.loader.exec_module(m)
except SystemExit:
    pass

# ЖИВА палітра застосунку (BuildingCategory.kt), не PAL_A12 зі скрипта — там ще довиправковий Bolig.
BUILDINGS = [
    ("bolig", "#3B6A07"), ("garasje", "#B53850"), ("landbruk", "#602B0F"), ("hytte", "#F38C0F"),
    ("industri", "#164150"), ("samfunn", "#36AFBC"), ("handel_kontor", "#2883C6"),
    ("lager", "#A9A087"), ("handel_service", "#D7634D"), ("sakral", "#2551D7"),
    ("helse", "#963681"), ("andre", "#8F8A93"),
]
POI = list(m.POI)
TRAIL_BASE = ("trail:base", "#63605C")

PAPER = "#F4F2EF"
LAND = "#E6E3DE"
DARKEST = m.DARKEST_BG        # #C2BFBA — найтемніша ділянка підложки
NATURE_ALPHA = 0.55

CANDIDATES = [
    ("нинішнє чорнило", "#1A0F2E"),
    ("жовтий чистий",   "#FFD400"),
    ("жовтий теплий",   "#F2B705"),
    ("бурштин",         "#E8A317"),
    ("лимонний темн.",  "#D9B300"),
    ("жовто-зелений",   "#C8D400"),
    ("маркер червон.",  "#E8362A"),
    ("маджента",        "#E5007E"),
    ("бірюза яскр.",    "#00C2A8"),
]


def nature_set():
    """Що видно на екрані в режимі «природа»."""
    out = []
    for name, hexv in BUILDINGS:
        out.append((name + "@0.55", m.composite(hexv, LAND, NATURE_ALPHA)))
    out += [(n, h) for n, h in POI]
    out.append(TRAIL_BASE)
    return out


def report(cand_name, cand_hex, others):
    rows = []
    for kind in ("normal", "deutan", "protan", "tritan"):
        lab_c = m.sim_lab(cand_hex, kind, "machado")
        worst = min(
            (m.ciede2000(lab_c, m.sim_lab(h, kind, "machado")), n) for n, h in others
        )
        rows.append((kind, worst))
    c_paper = m.contrast(cand_hex, PAPER)
    c_dark = m.contrast(cand_hex, DARKEST)
    return rows, c_paper, c_dark


others = nature_set()
print("Режим «природа»: 12 заливок при 0,55 + 7 POI + базовий пунктир = %d кольорів\n" % len(others))
hdr = f'{"кандидат":18} {"hex":9} {"norm":>6} {"deut":>6} {"prot":>6} {"trit":>6} {"c/пап":>6} {"c/тем":>6}  найближчий (normal)'
print(hdr)
print("-" * len(hdr))
for name, hexv in CANDIDATES:
    rows, cp, cd = report(name, hexv, others)
    vals = {k: v for k, v in rows}
    nearest = vals["normal"][1]
    print(f'{name:18} {hexv:9} {vals["normal"][0]:6.2f} {vals["deutan"][0]:6.2f} '
          f'{vals["protan"][0]:6.2f} {vals["tritan"][0]:6.2f} {cp:6.2f} {cd:6.2f}  {nearest}')

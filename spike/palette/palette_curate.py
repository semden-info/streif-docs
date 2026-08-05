# -*- coding: utf-8 -*-
"""Курація двох кольорів A12 в межах виміряних коридорів (`08` §15.11.2).

Питання, на яке відповідає цей скрипт: **чи справді неможливо** зробити `Sakral` фіолетовим, а
`Bolig` трав'яним, не зламавши чотиричастинного правила §15.11.3. §15.11.2 стверджує, що ні
(«чистий зелений і чистий фіолет під deuteranopia сходяться»), але це було сказано без перебору.

Метод: решта 10 кольорів A12 стоять нерухомо, два шукані перебираються по сітці LCh, кожен
кандидат перевіряється правилом цілком — на всіх 66 парах, у нормальному зорі й у чотирьох
симуляціях (дві моделі × deutan/protan + tritan).

```bash
PYTHONIOENCODING=utf-8 python spike/palette/palette_curate.py
```
"""
import math
from itertools import combinations

from palette_check import (
    PAL_A12, ciede2000, hex2lab, sim_lab, contrast, lin_to_srgb,
    WP_D65, inv3, M_RGB2XYZ, mat_apply,
)

M_XYZ2RGB = inv3(M_RGB2XYZ)

# Пороги §15.11.3. Контраст тут НЕ гейт: A12 несе межу обведенням, тобто правило №3
# задовольняється гілкою «АБО обов'язкове обведення».
T_NORMAL, T_DICHROM, T_TRITAN = 17.0, 10.0, 8.0


def lch2hex(L, C, h_deg):
    """LCh(ab) → "#RRGGBB"; None, якщо кандидат поза sRGB-гамутом."""
    a = C * math.cos(math.radians(h_deg))
    b = C * math.sin(math.radians(h_deg))
    fy = (L + 16) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def finv(t):
        d = 6.0 / 29.0
        return t ** 3 if t > d else 3 * d * d * (t - 4.0 / 29.0)

    xyz = (finv(fx) * WP_D65[0], finv(fy) * WP_D65[1], finv(fz) * WP_D65[2])
    lin = mat_apply(M_XYZ2RGB, xyz)
    if any(v < -0.001 or v > 1.001 for v in lin):
        return None                      # поза гамутом — клампити не можна, це зсув відтінку
    return '#%02X%02X%02X' % tuple(
        max(0, min(255, round(lin_to_srgb(v) * 255))) for v in lin)


def score(pal):
    """(normal_min, dichrom_min, tritan_min) по всіх парах набору."""
    out = []
    for kinds in (('normal',), ('deutan', 'protan'), ('tritan',)):
        worst = float('inf')
        for kind in kinds:
            for model in (('vienot',) if kind == 'normal' else ('vienot', 'machado')):
                labs = {n: sim_lab(h, kind, model) for n, h in pal}
                for (n1, _), (n2, _) in combinations(pal, 2):
                    d = ciede2000(labs[n1], labs[n2])
                    if d < worst:
                        worst = d
        out.append(worst)
    return tuple(out)


def passes(s):
    return s[0] >= T_NORMAL and s[1] >= T_DICHROM and s[2] >= T_TRITAN


def search(target, hue_range, label):
    """Перебір одного кольору при решті нерухомій."""
    others = [(n, h) for n, h in PAL_A12 if n != target]
    best = []
    for hue in range(hue_range[0], hue_range[1] + 1, 4):
        for L in range(25, 66, 4):
            for C in range(20, 81, 6):
                hx = lch2hex(L, C, hue)
                if hx is None:
                    continue
                s = score(others + [(target, hx)])
                if passes(s):
                    best.append((min(s[0] - T_NORMAL, s[1] - T_DICHROM, s[2] - T_TRITAN),
                                 hx, hue, L, C, s))
    best.sort(reverse=True)
    print("\n== %s : кандидатів, що проходять правило цілком — %d ==" % (label, len(best)))
    cur = dict(PAL_A12)[target]
    cs = score(PAL_A12)
    print("   нинішній %s: normal %.2f · dichrom %.2f · tritan %.2f  -> %s"
          % (cur, cs[0], cs[1], cs[2], "проходить" if passes(cs) else "НЕ проходить"))
    for margin, hx, hue, L, C, s in best[:12]:
        print("   %s  hue %3d  L* %2d  C* %2d   normal %5.2f · dichrom %5.2f · tritan %5.2f"
              % (hx, hue, L, C, s[0], s[1], s[2]))
    return best


if __name__ == "__main__":
    print("Нерухомі 10 кольорів A12; пороги: normal %.0f · dichrom %.0f · tritan %.0f"
          % (T_NORMAL, T_DICHROM, T_TRITAN))
    # Sakral: фіолет — від синьо-фіолетового до пурпурового.
    search("Sakral", (280, 340), "Sakral -> фіолет (претензія «став синім»)")
    # Bolig: трав'яний зелений замість оливкового.
    search("Bolig", (110, 165), "Bolig -> трав'яний (претензія «став оливковим»)")

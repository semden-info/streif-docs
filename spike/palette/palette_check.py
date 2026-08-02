# -*- coding: utf-8 -*-
"""Independent palette audit: CIEDE2000, CVD simulation, contrast. Stdlib only."""
import math
from itertools import combinations

# ---------------- color space ----------------

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def rgb2hex(rgb):
    return '#%02X%02X%02X' % tuple(max(0, min(255, round(c * 255))) for c in rgb)

def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def lin_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

# sRGB D65 -> XYZ
M_RGB2XYZ = [[0.4124564, 0.3575761, 0.1804375],
             [0.2126729, 0.7151522, 0.0721750],
             [0.0193339, 0.1191920, 0.9503041]]

WP_D65 = (0.95047, 1.00000, 1.08883)

def mat_apply(M, v):
    return tuple(sum(M[i][j] * v[j] for j in range(3)) for i in range(3))

def lin_rgb(hexstr):
    return tuple(srgb_to_lin(c) for c in hex2rgb(hexstr))

def lin2lab(rgb_lin):
    X, Y, Z = mat_apply(M_RGB2XYZ, rgb_lin)
    def f(t):
        d = 6.0 / 29.0
        return t ** (1.0 / 3.0) if t > d ** 3 else t / (3 * d * d) + 4.0 / 29.0
    fx, fy, fz = f(X / WP_D65[0]), f(Y / WP_D65[1]), f(Z / WP_D65[2])
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))

def hex2lab(h):
    return lin2lab(lin_rgb(h))

# ---------------- CIEDE2000 (Sharma/Wu/Dalal 2005 formulation) ----------------

def ciede2000(lab1, lab2, kL=1.0, kC=1.0, kH=1.0):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    def hp(ap, bp):
        if ap == 0 and bp == 0:
            return 0.0
        h = math.degrees(math.atan2(bp, ap))
        return h + 360 if h < 0 else h

    h1p = hp(a1p, b1)
    h2p = hp(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    else:
        d = h2p - h1p
        if d > 180:
            d -= 360
        elif d < -180:
            d += 360
        dhp = d
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2.0)

    Lbp = (L1 + L2) / 2.0
    Cbp = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hbp = h1p + h2p
    else:
        if abs(h1p - h2p) <= 180:
            hbp = (h1p + h2p) / 2.0
        elif (h1p + h2p) < 360:
            hbp = (h1p + h2p + 360) / 2.0
        else:
            hbp = (h1p + h2p - 360) / 2.0

    T = (1 - 0.17 * math.cos(math.radians(hbp - 30))
         + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6))
         - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25.0) ** 2))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc

    return math.sqrt((dLp / (kL * Sl)) ** 2 + (dCp / (kC * Sc)) ** 2 +
                     (dHp / (kH * Sh)) ** 2 +
                     Rt * (dCp / (kC * Sc)) * (dHp / (kH * Sh)))

# --- self-validation against Sharma et al. published test set (subset) ---
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]

def validate():
    worst = 0.0
    for a, b, exp in SHARMA:
        got = ciede2000(a, b)
        worst = max(worst, abs(got - exp))
    return worst

# ---------------- CVD simulation ----------------

# Model A: Vienot/Brettel/Mollon 1999 (protan/deutan), Brettel two-plane (tritan)
# LMS from LINEAR sRGB (Hunt-Pointer-Estevez style matrix used in Vienot 1999)
M_RGB2LMS = [[17.8824, 43.5161, 4.11935],
             [3.45565, 27.1554, 3.86714],
             [0.0299566, 0.184309, 1.46709]]

def inv3(M):
    a, b, c = M[0]
    d, e, f = M[1]
    g, h, i = M[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]

M_LMS2RGB = inv3(M_RGB2LMS)

def vienot(rgb_lin, kind):
    L, M, S = mat_apply(M_RGB2LMS, rgb_lin)
    if kind == 'protan':
        L = 2.02344 * M - 2.52581 * S
    elif kind == 'deutan':
        M = 0.494207 * L + 1.24827 * S
    elif kind == 'tritan':
        # Brettel two half-planes, anchored on 485nm / 660nm
        # decide half-plane by comparison with the neutral axis
        if (M / L if L else 0) < (0.34478 / 0.65518):
            S = -0.395913 * L + 0.801109 * M
        else:
            S = -0.062921 * L + 0.292070 * M
    out = mat_apply(M_LMS2RGB, (L, M, S))
    return tuple(max(0.0, min(1.0, v)) for v in out)

# Model B: Machado, Oliveira & Fernandes 2009, severity 1.0, on LINEAR rgb
MACHADO = {
    'protan': [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    'deutan': [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    'tritan': [[1.255528, -0.076749, -0.178779],
               [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}

def machado(rgb_lin, kind):
    out = mat_apply(MACHADO[kind], rgb_lin)
    return tuple(max(0.0, min(1.0, v)) for v in out)

def sim_lab(hexstr, kind, model):
    rl = lin_rgb(hexstr)
    if kind == 'normal':
        return lin2lab(rl)
    sim = vienot(rl, kind) if model == 'vienot' else machado(rl, kind)
    return lin2lab(sim)

def sim_hex(hexstr, kind, model):
    rl = lin_rgb(hexstr)
    if kind == 'normal':
        return hexstr
    sim = vienot(rl, kind) if model == 'vienot' else machado(rl, kind)
    return rgb2hex(tuple(lin_to_srgb(c) for c in sim))

# ---------------- WCAG contrast ----------------

def rel_lum(hexstr):
    r, g, b = lin_rgb(hexstr)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(h1, h2):
    a, b = rel_lum(h1), rel_lum(h2)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)

# ---------------- palette ----------------

PAL = [
    ("Bolig",                 "#2E8B3D"),
    ("Garasje/uthus",         "#E0392B"),
    ("Landbruk/fiske",        "#6E4B23"),
    ("Hytte",                 "#F2A007"),
    ("Industri/energi",       "#37474F"),
    ("Samfunn/kultur",        "#16A6A0"),
    ("Lager",                 "#B99476"),
    ("Handel/kontor",         "#2479C2"),
    ("Servering/overnatting", "#E86F15"),
    ("Helse",                 "#D81B60"),
    ("Sakral",                "#8E44D0"),
    ("Andre",                 "#9AA0A6"),
]

BACKGROUNDS = [
    ("topograatone paper (lys)", "#F4F2EF"),
    ("topograatone landmasse",   "#E6E3DE"),
    ("graatone skygge/vann",     "#D3D0CB"),
    ("hvit",                     "#FFFFFF"),
    ("mork bakgrunn (typisk)",   "#2B2B2B"),
    ("mork bakgrunn (djup)",     "#121212"),
]


def pair_table(kind, model):
    labs = {n: sim_lab(h, kind, model) for n, h in PAL}
    rows = []
    for (n1, _), (n2, _) in combinations(PAL, 2):
        rows.append((ciede2000(labs[n1], labs[n2]), n1, n2))
    rows.sort()
    return rows


def main():
    err = validate()
    print("== CIEDE2000 self-test vs Sharma et al. published set ==")
    print("   pairs tested: %d, max abs error: %.6f  -> %s"
          % (len(SHARMA), err, "OK" if err < 0.0002 else "FAIL"))

    print("\n== 1. Normal vision, all 66 pairs ==")
    rows = pair_table('normal', 'vienot')
    print("   pairs: %d   min dE: %.2f   median: %.2f   max: %.2f"
          % (len(rows), rows[0][0], rows[len(rows) // 2][0], rows[-1][0]))
    print("   ten worst:")
    for d, a, b in rows[:10]:
        print("     %5.2f  %-22s <-> %-22s" % (d, a, b))
    print("   below 15: %d ; below 17.1: %d"
          % (sum(1 for r in rows if r[0] < 15), sum(1 for r in rows if r[0] < 17.1)))

    print("\n== 2. Colour-vision deficiency ==")
    for kind in ('deutan', 'protan', 'tritan'):
        for model in ('vienot', 'machado'):
            rows = pair_table(kind, model)
            bad = [r for r in rows if r[0] < 10]
            print("\n   -- %s / %s : min dE %.2f ; pairs <10 = %d ; <5 = %d"
                  % (kind, model, rows[0][0], len(bad),
                     sum(1 for r in rows if r[0] < 5)))
            for d, a, b in rows[:8]:
                mark = " <<<" if d < 10 else ""
                print("       %5.2f  %-22s <-> %-22s%s" % (d, a, b, mark))

    print("\n   simulated hex (vienot | machado):")
    for n, h in PAL:
        print("     %-22s %s  d:%s|%s  p:%s|%s  t:%s|%s" % (
            n, h,
            sim_hex(h, 'deutan', 'vienot'), sim_hex(h, 'deutan', 'machado'),
            sim_hex(h, 'protan', 'vienot'), sim_hex(h, 'protan', 'machado'),
            sim_hex(h, 'tritan', 'vienot'), sim_hex(h, 'tritan', 'machado')))

    print("\n== 3. Contrast on basemaps ==")
    print("   %-22s %6s %6s %6s | %s" % ("category", "L*", "C*", "hue", " ".join(
        "%-11s" % b[0][:11] for b in BACKGROUNDS)))
    for n, h in PAL:
        L, a, b = hex2lab(h)
        C = math.hypot(a, b)
        hue = (math.degrees(math.atan2(b, a)) + 360) % 360
        cs = " ".join("%-11.2f" % contrast(h, bg[1]) for bg in BACKGROUNDS)
        print("   %-22s %6.1f %6.1f %6.0f | %s" % (n, L, C, hue, cs))

    print("\n   L* spread: min %.1f max %.1f" % (
        min(hex2lab(h)[0] for _, h in PAL), max(hex2lab(h)[0] for _, h in PAL)))

    print("\n   pairs whose |dL*| < 8 (weak lightness separation):")
    for (n1, h1), (n2, h2) in combinations(PAL, 2):
        dl = abs(hex2lab(h1)[0] - hex2lab(h2)[0])
        if dl < 8:
            print("     dL* %5.2f  %-22s <-> %-22s  (dE %.1f)"
                  % (dl, n1, n2, ciede2000(hex2lab(h1), hex2lab(h2))))

    print("\n   contrast < 3.0 against any background:")
    for n, h in PAL:
        for bn, bh in BACKGROUNDS:
            c = contrast(h, bh)
            if c < 3.0:
                print("     %-22s vs %-26s %.2f" % (n, bn, c))


main()

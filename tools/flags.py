"""Flags for the new nations (period-inspired, c. 1789) and every size the game needs.

Each flag is a list of shapes drawn in normalised coordinates (x 0..1 left->right, y 0..1 top->bottom)
and rendered with 4x4 supersampling. derive() makes the in-game variants in the style of the originals:
the 3D textures (map flag, battle standard, figure flag) are painted with the cloth of the game's own flags
and keep their pole or frame, the UI icons copy the frames and round-badge styles of the original icons.
"""
import math, os

def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


# ---------------------------------------------------------------- shapes
def rect(x0, y0, x1, y1, c):
    return ('rect', x0, y0, x1, y1, rgb(c))

def circle(cx, cy, r, c):
    return ('circle', cx, cy, r, rgb(c))

def crescent(cx, cy, r, off, c):
    return ('crescent', cx, cy, r, off, rgb(c))

def star(cx, cy, r, c, n=5, inner=0.42, rot=-90):
    return ('star', cx, cy, r, rgb(c), n, inner, rot)

def poly(pts, c):
    return ('poly', pts, rgb(c))

def rays(cx, cy, r0, r1, n, w, c):
    return ('rays', cx, cy, r0, r1, n, w, rgb(c))


def _inside_poly(pts, x, y):
    c = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _hit(s, x, y, aspect):
    k = s[0]
    if k == 'rect':
        return s[1] <= x < s[3] and s[2] <= y < s[4]
    if k == 'circle':
        return ((x - s[1]) * aspect) ** 2 + (y - s[2]) ** 2 <= s[3] ** 2
    if k == 'crescent':
        _, cx, cy, r, off = s[:5]
        return (((x - cx) * aspect) ** 2 + (y - cy) ** 2 <= r * r and
                ((x - cx - off / aspect) * aspect) ** 2 + (y - cy) ** 2 > (r * 0.82) ** 2)
    if k == 'star':
        _, cx, cy, r, col, n, inner, rot = s
        pts = []
        for i in range(2 * n):
            a = math.radians(rot + 180.0 * i / n)
            rr = r if i % 2 == 0 else r * inner
            pts.append((cx + rr * math.cos(a) / aspect, cy + rr * math.sin(a)))
        return _inside_poly(pts, x, y)
    if k == 'poly':
        return _inside_poly(s[1], x, y)
    if k == 'rays':
        _, cx, cy, r0, r1, n, w = s[:7]
        dx, dy = (x - cx) * aspect, y - cy
        d = math.hypot(dx, dy)
        if not r0 <= d <= r1:
            return False
        a = (math.atan2(dy, dx) / (2 * math.pi) * n) % 1.0
        return a < w or a > 1 - w
    return False


def _col(s):
    return s[4] if s[0] == 'star' else s[7] if s[0] == 'rays' else s[5] if s[0] == 'crescent' else s[-1]


def _bbox(s, aspect):
    k = s[0]
    if k == 'rect':
        return s[1:5]
    if k == 'poly':
        xs, ys = [p[0] for p in s[1]], [p[1] for p in s[1]]
        return min(xs), min(ys), max(xs), max(ys)
    r = s[4] if k == 'rays' else s[3]
    return s[1] - r / aspect, s[2] - r, s[1] + r / aspect, s[2] + r


def _is_field(s, aspect):
    """Bands, borders, crosses, hoists: shapes running from edge to edge."""
    x0, y0, x1, y1 = _bbox(s, aspect)
    return (x0 <= 0.005 and x1 >= 0.995) or (y0 <= 0.005 and y1 >= 0.995)


def render(shapes, w, h, ss=4, design_aspect=None):
    """-> rows top-down RGBA.

    design_aspect: the aspect the design was drawn for (2.0 here). On a canvas of another aspect the field (bands,
    borders, crosses) stretches to fill it while the emblem keeps its proportions, as on the game's own square flags.
    Without it every shape simply scales to the canvas (the old behaviour)."""
    aspect = w / h
    plan = [(s, _col(s), None) for s in shapes]
    if design_aspect and abs(design_aspect - aspect) > 1e-6:
        emb = [s for s in shapes if not _is_field(s, design_aspect)]
        if emb:
            bb = [_bbox(s, design_aspect) for s in emb]
            ex0, ey0 = min(b[0] for b in bb), min(b[1] for b in bb)
            ex1, ey1 = max(b[2] for b in bb), max(b[3] for b in bb)
            cx, cy = (ex0 + ex1) / 2, (ey0 + ey1) / 2
            stretch = design_aspect / aspect          # emblem width per design unit on this canvas
            g = 1.0                                   # shrink the emblem only if it would not fit across
            if ex1 - ex0 > 0:
                g = min(g, 0.88 / ((ex1 - ex0) * stretch), cx / ((cx - ex0) * stretch), (1 - cx) / ((ex1 - cx) * stretch))
            g = max(g, 0.05)
            plan = [(s, _col(s), None if _is_field(s, design_aspect) else (cx, cy, g * stretch, g)) for s in shapes]
    rows = []
    for py in range(h):
        row = bytearray(w * 4)
        for px in range(w):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss) / w
                    y = (py + (sy + 0.5) / ss) / h
                    col = (0, 0, 0)
                    for s, c, t in plan:
                        if t is None:
                            if _hit(s, x, y, aspect):
                                col = c
                        elif _hit(s, t[0] + (x - t[0]) / t[2], t[1] + (y - t[1]) / t[3], design_aspect):
                            col = c
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]
            n = ss * ss
            row[px * 4:px * 4 + 4] = bytes((acc[0] // n, acc[1] // n, acc[2] // n, 255))
        rows.append(row)
    return rows


# ---------------------------------------------------------------- designs (period-inspired)
DESIGNS = {
    # Qajar Persia (from 1789): lion and sun on white, green and red borders
    'PERSIA': [rect(0, 0, 1, 1, '#f4f1e6'), rect(0, 0, 1, 0.12, '#2f7d32'), rect(0, 0.88, 1, 1, '#b5222b'),
               rays(0.62, 0.42, 0.13, 0.24, 16, 0.18, '#e0a020'), circle(0.62, 0.42, 0.13, '#f0b429'),
               poly([(0.22, 0.72), (0.27, 0.56), (0.40, 0.52), (0.55, 0.55), (0.66, 0.60), (0.72, 0.56), (0.76, 0.62),
                     (0.70, 0.72), (0.64, 0.66), (0.42, 0.66), (0.34, 0.76), (0.30, 0.76), (0.31, 0.66)], '#c8861a'),
               poly([(0.30, 0.50), (0.37, 0.42), (0.36, 0.56)], '#c8861a')],
    # First Saudi State (Emirate of Diriyah): green field, white inscription and sword
    'ARABIA': [rect(0, 0, 1, 1, '#1d6b3a'),
               rect(0.18, 0.30, 0.30, 0.36, '#ffffff'), rect(0.33, 0.27, 0.40, 0.40, '#ffffff'), rect(0.43, 0.30, 0.58, 0.36, '#ffffff'),
               rect(0.61, 0.26, 0.66, 0.40, '#ffffff'), rect(0.69, 0.30, 0.82, 0.36, '#ffffff'), rect(0.18, 0.40, 0.82, 0.43, '#ffffff'),
               rect(0.16, 0.64, 0.80, 0.69, '#ffffff'), poly([(0.80, 0.62), (0.88, 0.665), (0.80, 0.71)], '#ffffff'),
               rect(0.12, 0.60, 0.16, 0.73, '#ffffff')],
    # Emirate of Bukhara (Turkestan): crimson field, golden crescent and star
    'TURKESTAN': [rect(0, 0, 1, 1, '#8e1b2a'), rect(0, 0, 1, 0.08, '#d9a52b'), rect(0, 0.92, 1, 1, '#d9a52b'),
                  crescent(0.44, 0.50, 0.26, 0.10, '#e8bd3a'), star(0.62, 0.50, 0.12, '#e8bd3a')],
    # Siberia: white over green (Siberian regional colours: snow and taiga), sable-coloured hoist
    'SIBERIA': [rect(0, 0, 1, 0.5, '#f7f7f2'), rect(0, 0.5, 1, 1, '#2e7d43'), rect(0, 0, 0.18, 1, '#3b2b20'),
                star(0.09, 0.50, 0.07, '#f2c12e', 6, 0.5)],
    # Sahara (Tuat oases, Saharan Berbers): indigo with a golden sun over the dunes
    'SAHARA': [rect(0, 0, 1, 1, '#283a8c'), poly([(0, 0.78), (0.25, 0.66), (0.5, 0.74), (0.75, 0.64), (1, 0.72), (1, 1), (0, 1)], '#d8a64a'),
               circle(0.50, 0.38, 0.16, '#f2c12e'), rays(0.50, 0.38, 0.17, 0.25, 12, 0.16, '#f2c12e')],
}


def _tore_tamga(col, cx=0.5, cy=0.5, height=0.56, stroke=8.0):
    """Tamga of the Tore (the Genghisid clan of the Kazakh khans): an arch over a central stroke, after
    Wikimedia Commons File:Kazakh_Tamga_70.svg (drawn in a 100x100 box, sourced there to e-history.kz on the
    tamga seals of the Kazakh khans). Strokes thickened from 5 to `stroke` units to read at 64 px."""
    k = height / 51.0                                   # the sign spans ~51 units high (24.4..75.6 with the stroke)
    X = lambda u: cx + (u - 50) * k / 2.0               # flag is 2:1, so x units are half as long
    Y = lambda v: cy + (v - 50) * k
    t = stroke / 2
    out = [rect(X(14 - t), Y(43.08), X(14 + t), Y(71.08), col), rect(X(86 - t), Y(43.08), X(86 + t), Y(71.08), col),
           rect(X(50 - t), Y(30.13), X(50 + t), Y(71.08), col)]
    # the arch: cubic Bezier (14,43.08) (25.03,23.97) (75.22,24.42) (86,43.08), offset by half the stroke both ways
    P = [(14, 43.08), (25.03, 23.97), (75.22, 24.42), (86, 43.08)]
    outer, inner = [], []
    for i in range(25):
        s = i / 24
        b = [(1 - s) ** 3, 3 * s * (1 - s) ** 2, 3 * s * s * (1 - s), s ** 3]
        db = [-3 * (1 - s) ** 2, 3 * (1 - s) ** 2 - 6 * s * (1 - s), 6 * s * (1 - s) - 3 * s * s, 3 * s * s]
        px, py = sum(w * p[0] for w, p in zip(b, P)), sum(w * p[1] for w, p in zip(b, P))
        tx, ty = sum(w * p[0] for w, p in zip(db, P)), sum(w * p[1] for w, p in zip(db, P))
        n = math.hypot(tx, ty) or 1.0
        nx, ny = ty / n, -tx / n                        # points away from the arch's centre (up)
        outer.append((X(px + nx * t), Y(py + ny * t)))
        inner.append((X(px - nx * t), Y(py - ny * t)))
    out.append(poly(outer + inner[::-1], col))
    # round caps and joins (circles are round in pixels, radius in flag-height units)
    out += [circle(X(u), Y(v), t * k, col) for u, v in ((14, 71.08), (86, 71.08), (50, 71.08), (50, 30.13), (14, 43.08), (86, 43.08))]
    return out


# Kazakh Khanate c. 1789 (replaces the anachronistic modern sky-blue flag). The banners of the Kazakh khans and
# sultans were white, Ablai Khan's (18th century) being the one remembered (kaspex.kz/?p=118 "State symbols of the
# Republic of Kazakhstan"; the cultural.kz encyclopedia, "Banner complexes (bunchuk, tu)", lists "Abylaidyn aq tuy",
# Ablai's white banner). Emblem: the Tore tamga of the khans' clan (see _tore_tamga). Its blue (the steppe's sky, kok)
# is our choice; no colour of the sign on a banner is recorded.
DESIGNS['KAZAKHSTAN'] = [rect(0, 0, 1, 1, '#f4f1e6')] + _tore_tamga('#1d4f91')

# Chechenya: green field with the white-red-white stripes along the bottom
DESIGNS['CHECHNYA'] = ([rect(0, 0, 1, 1, '#2e7639'), rect(0, 0.58, 1, 0.68, '#f6f6f2'), rect(0, 0.68, 1, 0.78, '#d42a1e'),
                        rect(0, 0.78, 1, 0.88, '#f6f6f2'),
                        circle(0.49, 0.30, 0.205, '#111111'), circle(0.49, 0.30, 0.185, '#2e7639'),          # emblem ring
                        circle(0.555, 0.175, 0.045, '#111111'),                                        # moon
                        poly([(0.40, 0.31), (0.405, 0.27), (0.425, 0.25), (0.43, 0.20), (0.445, 0.225), (0.46, 0.20), (0.465, 0.24), (0.49, 0.265), (0.58, 0.262), (0.605, 0.28), (0.63, 0.30), (0.61, 0.31)], '#111111'),        # lying wolf
                        rect(0.40, 0.33, 0.60, 0.35, '#111111'), poly([(0.42, 0.35), (0.49, 0.42), (0.56, 0.35)], '#111111')]   # pedestal
                       + [star(0.49 + 0.105 * __import__('math').cos(a), 0.30 + 0.155 * __import__('math').sin(a), 0.014, '#111111')
                          for a in [__import__('math').radians(d) for d in (30, 50, 70, 90, 110, 130, 150)]])

# map colours (RGB); stored BGR in the database
COLOURS = {'PERSIA': '#d9822b', 'ARABIA': '#d6447f', 'TURKESTAN': '#7a3fb0', 'KAZAKHSTAN': '#c03aa8',
           'SIBERIA': '#f0f0f4', 'SAHARA': '#3346c8', 'CHECHNYA': '#7a1f3d'}
# chosen to stay distinct after the game tints them with the yellow parchment (blue-greens turn green there)


# ---------------------------------------------------------------- in-game variants
def blank(w, h, c=(0, 0, 0, 0)):
    return [bytearray(bytes(c) * w) for _ in range(h)]


def paste(dst, src, x, y):
    for j, row in enumerate(src):
        dst[y + j][x * 4:x * 4 + len(row)] = row


def frame(rows, t, c):
    h, w = len(rows), len(rows[0]) // 4
    for y in range(h):
        for x in range(w):
            if x < t or y < t or x >= w - t or y >= h - t:
                rows[y][x * 4:x * 4 + 4] = bytes(c)
    return rows


# ---------------------------------------------------------------- painted cloth and badges of the original art
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
# Models/BANDERAS/*.tga and the minor nations' Models/NN/Bandera.dds (both 128x64): the flag mesh of BanderaA.V3D maps
# u 0.017..0.866 (x <= 110) onto the cloth and the pole-and-spear mesh u 0.88..0.99; x >= 111 is the same pole strip
# in every original
POLE_X = 111
# Figuras/NN/Bandera.tga (256x256, the whole texture is on the figure's flag): cloth inside the red frame and gold line
FIG_BOX = (9, 9, 246, 247)
LUM = (0.30, 0.59, 0.11)
TONE = (0.69, 0.67, 0.57)        # flat colour -> painted 3D texture: whites ~(170,165,138), reds ~(140,10,25) as the originals
TONE_UI = (0.96, 0.95, 0.90)     # the UI icons are painted brighter (French white 246,247,223 in the round icons)
_CACHE = {}


def _img(*parts):
    """Original picture under data/ -> float32 RGBA, top-down."""
    from PIL import Image
    import numpy as np
    return np.asarray(Image.open(os.path.join(DATA, *parts)).convert('RGBA')).astype(np.float32)


def _arr(rows):
    import numpy as np
    return np.frombuffer(b''.join(bytes(r) for r in rows), np.uint8).reshape(len(rows), -1, 4)[..., :3].astype(np.float32)


def _rows(a, alpha=None):
    """float/uint8 HxWx3 (or x4) -> rows of RGBA bytearrays."""
    import numpy as np
    a = np.clip(np.asarray(a, np.float32) + 0.5, 0, 255).astype(np.uint8)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255 if alpha is None else alpha, np.uint8)], 2)
    return [bytearray(a[y].tobytes()) for y in range(a.shape[0])]


def _resize(a, w, h, method='lanczos'):
    from PIL import Image
    import numpy as np
    m = {'lanczos': Image.LANCZOS, 'bilinear': Image.BILINEAR}[method]
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), m), np.float32)
    return np.asarray(Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8)).resize((w, h), m), np.float32)


def _blur(a, r):
    """Separable box blur with edge padding."""
    import numpy as np
    for ax in (0, 1):
        pad = [(r, r) if i == ax else (0, 0) for i in range(2)]
        c = np.cumsum(np.pad(a, pad, mode='edge'), axis=ax, dtype=np.float64)
        c = np.insert(c, 0, 0, axis=ax)
        n = a.shape[ax]
        a = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax) - np.take(c, np.arange(n), axis=ax)) / (2 * r + 1)
    return a.astype(np.float32)


def _cloth_map(srcs, box, gap):
    """Cloth luminance of original two-band flags, every band divided by its own median: folds, weave, worn edges.
    srcs: [(path parts, bands to use, row where the bands meet)]."""
    import numpy as np
    x0, y0, x1, y1 = box
    acc = np.zeros((y1 - y0, x1 - x0), np.float32)
    n = np.zeros_like(acc)
    rows = np.arange(y0, y1)[:, None] + np.zeros((1, x1 - x0))
    for parts, bands, split in srcs:
        L = _img(*parts)[y0:y1, x0:x1, :3] @ np.array(LUM, np.float32)
        for band in bands:
            m = rows < split - gap if band == 'top' else rows >= split + gap
            acc[m] += L[m] / np.median(L[m])
            n[m] += 1
    R = np.where(n > 0, acc / np.maximum(n, 1), np.nan)
    # rows that no band covers (where the bands meet): the folds interpolated from the rows above and below,
    # the weave copied from nearby rows
    bad = np.isnan(R).all(1)
    ys = np.flatnonzero(bad)
    if len(ys):
        r = max(1, R.shape[1] // 40)
        low = lambda row: np.convolve(np.pad(row, r, mode='edge'), np.ones(2 * r + 1) / (2 * r + 1), 'valid')
        a, b = ys.min() - 1, ys.max() + 1
        k = b - a
        for y in ys:
            w = (y - a) / k
            src = R[y - k] if y - k >= 0 and not bad[y - k] else R[y + k]
            R[y] = low(R[a]) * (1 - w) + low(R[b]) * w + (src - low(src))
    return np.clip(R / np.median(R), 0.3, 1.4).astype(np.float32)


def _cloth():
    """Cloth maps, pole strip and frames taken from the original art (once)."""
    if not _CACHE:
        B = lambda n: ('Models', 'BANDERAS', n + '.tga')
        F = lambda n: ('Game', 'GameModes', 'Gestion', 'Figuras', n, 'Bandera.tga')
        # Hanover's flag: two light bands (yellow over white) show the whole cloth; dark bands hide it
        _CACHE['banner'] = _cloth_map([(B('Hannover'), ('top', 'bottom'), 32)], (0, 0, POLE_X, 64), 3)
        _CACHE['figure'] = _cloth_map([(F('17Hanover'), ('top', 'bottom'), 128)], FIG_BOX, 4)
        _CACHE['pole'] = _img(*B('Prusia'))[:, POLE_X:, :3]
        _CACHE['frame'] = _img(*F('03Prusia'))[..., :3]
        # BANDERA_ICONO_DEFAULT (46x30): soft shadow, stone frame, black and white lines around a 31x16 flag at (7, 7)
        _CACHE['s46'] = _img('Game', 'UI', 'ModeloGestion', 'InterfaceGestionNeutrales.tga')[1:31, 796:842]
    return _CACHE


def _paint(flat, R, tone, lift):
    """Flat design colours -> painted cloth: tone into the originals' value range and multiply by the cloth luminance;
    dark colours also get a little of the folds as light, as the originals' dark fields do."""
    import numpy as np
    base = flat * np.array(tone, np.float32)
    lum = base @ np.array(LUM, np.float32)
    out = base * R[..., None] + ((R - 1) * lift * (1 - lum / 255))[..., None]
    return np.clip(out, 0, 255)


def _relief(R, w, h):
    """The cloth for UI icons: folds and weave, but not the dark worn edges."""
    hp = R / _blur(R, max(2, R.shape[0] // 6))
    return _resize(1 + (hp - 1) * 0.8, w, h, 'bilinear')


def banner(flat):
    """128x64 map flag / battle standard: painted cloth (flat: 64 x POLE_X x 3 design picture) + the original pole."""
    import numpy as np
    c = _cloth()
    out = np.empty((64, 128, 3), np.float32)
    out[:, :POLE_X] = _paint(flat, c['banner'], TONE, 30.0)
    out[:, POLE_X:] = c['pole']
    return out


def figure(flat):
    """256x256 figure flag: the original red frame with its gold line around the painted cloth (flat: FIG_BOX size)."""
    c = _cloth()
    x0, y0, x1, y1 = FIG_BOX
    out = c['frame'].copy()
    out[y0:y1, x0:x1] = _paint(flat, c['figure'], TONE, 30.0)
    return out


def ui_art(flat, square=False):
    """Flat design picture -> the brighter painted cloth of the UI icons."""
    R = _cloth()['figure' if square else 'banner']
    return _paint(flat, _relief(R, flat.shape[1], flat.shape[0]), TONE_UI, 20.0)


# round icons as measured on the originals (FR/PR/OT): flag disc (offset, diameter), rim colour top-left ->
# bottom-right and its alpha, inner shading (strength, px), drop shadow (dx, dy, softness, alpha), soft glass edge
BADGES = {
    'i38': dict(size=38, o=0, d=36, rim=((178, 163, 44), (128, 118, 22)), rim_a=(1.0, 0.9), shade=(0.38, 2.0),
                shadow=(0.8, 2.0, 1.5, 0.6), glass=0.0),
    'd54': dict(size=54, o=0, d=50, rim=((212, 212, 212), (227, 227, 227)), rim_a=(0.84, 0.94), shade=(0.33, 1.8),
                shadow=(1.5, 3.0, 2.5, 0.7), glass=0.0),
    'e57': dict(size=57, o=3, d=51, rim=((116, 115, 115), (158, 158, 155)), rim_a=(0.4, 0.86), shade=(0.0, 1.0),
                shadow=(1.0, 2.0, 1.5, 0.62), glass=0.42),
}
RIM_SELECT = ((206, 188, 46), (220, 201, 49))
RIM_DISABLE = ((33, 28, 28), (33, 29, 29))


def badge(art, style, rim=None, rim_a=None, dim=1.0):
    """Round icon in the style of the originals: art (HxWx3) squeezed into the disc. Returns HxWx4 float."""
    import numpy as np
    st = BADGES[style]
    S, o, D = st['size'], st['o'], st['d']
    rim = rim or st['rim']
    rim_a = rim_a or st['rim_a']
    c, R = o + (D - 1) / 2.0, D / 2.0
    flag = np.zeros((S, S, 3), np.float32)
    flag[o:o + D, o:o + D] = _resize(art, D, D) * dim
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    dx, dy = xx - c, yy - c
    d = np.hypot(dx, dy)
    e = R - d                                                      # distance inside the edge
    cov = np.clip(e + 0.5, 0, 1)
    t = np.clip(0.5 + (dx + dy) / (2.83 * np.maximum(d, 1)), 0, 1)[..., None]   # 0 top-left .. 1 bottom-right
    rim_col = np.array(rim[0], np.float32) * (1 - t) + np.array(rim[1], np.float32) * t
    ra = rim_a[0] * (1 - t[..., 0]) + rim_a[1] * t[..., 0]
    w_rim = np.clip(1.5 - e, 0, 1)                                 # the outermost pixel ring
    k, s = st['shade']
    shade = 1 - k * np.exp(-np.maximum(e - 1, 0) / s)
    glass = st['glass'] * np.exp(-((e - 1) / 2.6) ** 2) * (e > 0.5)
    col = flag * (shade * (1 - 1.2 * glass))[..., None]
    col = col * (1 - w_rim[..., None]) + rim_col * w_rim[..., None]
    a_disc = cov * (1 - w_rim * (1 - ra)) * (1 - glass)
    sdx, sdy, soft, sa = st['shadow']
    a_sh = sa * np.clip((R + soft - np.hypot(xx - c - sdx, yy - c - sdy)) / (2 * soft), 0, 1)
    a = a_disc + a_sh * (1 - a_disc)
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = col * (a_disc / np.maximum(a, 1e-6))[..., None]
    out[..., 3] = a * 255
    return out


def _disabled(b, k=0.5, alpha=0.318):
    """The originals' greyed round flag icons: half as bright and mostly transparent."""
    b = b.copy()
    b[..., :3] *= k
    b[..., 3] *= alpha
    return b


def _ui_set(big, sq):
    """UI icons from the UI picture of the flag (big: 2:1, sq: square). Returns dict name -> rows."""
    import numpy as np
    c = _cloth()
    v = {}
    f31 = _resize(big, 31, 16)
    s33 = np.full((18, 33, 3), 254, np.float32)                    # white line round the flag (JUG_<x>, 33x18)
    s33[1:17, 1:32] = f31
    v['s33'] = _rows(s33)
    s46 = c['s46'].copy()                                          # BANDERA_ICONO_<x>: the original stone frame
    s46[7:23, 7:38, :3] = f31
    s46[7:23, 7:38, 3] = 255
    v['s46'] = _rows(s46)
    w = big.shape[1]
    mid = big[:, int(w * 0.19):int(w * 0.81)]                      # diplomacy buttons: middle of the flag
    # brightness as the originals: selected ~1.35x normal, disabled ~0.45x normal and a little greyer
    v['d54_normal'] = _rows(badge(mid, 'd54', dim=0.82))
    v['d54_select'] = _rows(badge(mid, 'd54', RIM_SELECT, (0.99, 1.0), dim=1.12))
    grey = mid * 0.9 + (mid @ np.array(LUM, np.float32))[..., None] * 0.1
    v['d54_disable'] = _rows(badge(grey, 'd54', RIM_DISABLE, (0.99, 1.0), dim=0.37))
    i38 = badge(sq, 'i38')                                         # flag icons and historical battles: whole flag
    v['i38_normal'] = _rows(i38)
    v['i38_disable'] = _rows(_disabled(i38))
    v['h38'] = _rows(i38)
    v['e57'] = _rows(badge(sq, 'e57', dim=0.82))
    return v


def derive(key):
    """All variants for one nation. Returns dict name -> rows (RGBA, top-down)."""
    sh = DESIGNS[key]
    x0, y0, x1, y1 = FIG_BOX
    big = render(sh, 256, 128, 3)                                        # flat flag, 2:1
    sq = _arr(render(sh, x1 - x0, y1 - y0, 3, design_aspect=2.0))       # flat flag, square (as the game's own)
    v = {}
    v['map'] = _rows(banner(_arr(render(sh, POLE_X, 64, 4, design_aspect=2.0))))   # Models/BANDERAS (3D map flag)
    v['standard'] = [bytearray(r) for r in v['map']]                    # battle standard (DXT1), same picture as the minors'
    v['figure'] = _rows(figure(sq))                                     # Figuras Bandera.tga
    v.update(_ui_set(ui_art(_arr(big)), ui_art(sq, square=True)))
    # Select Empire row strips (297x57) made from the original strips (painted from the flat flag there)
    v.update(select_strips(big))
    return v


def notification(key):
    """Welcome-message picture (147x160 in a 256x256 texture, like NotificacionInicio*.tga): faded flag, vignette."""
    flag = render(DESIGNS[key], 147, 160, 3)
    out = blank(256, 256)
    for y in range(160):
        for x in range(147):
            r, g, b = flag[y][x * 4:x * 4 + 3]
            lum = (r * 3 + g * 6 + b) / 10
            fade = 0.55
            r, g, b = [int(c * (1 - fade) + lum * fade * 0.95 + 18 * fade) for c in (r, g, b)]
            dx, dy = (x - 73) / 73, (y - 80) / 80
            v = max(0.0, 1.0 - 0.55 * (dx * dx + dy * dy) ** 1.2)
            grain = 0.92 + 0.08 * math.sin(x * 1.7 + y * 0.9) * math.cos(y * 1.3)
            out[1 + y][(1 + x) * 4:(1 + x) * 4 + 4] = bytes((int(r * v * grain), int(g * v * grain), int(b * v * grain), 255))
    return out


# ---------------------------------------------------------------- variants from an existing flag picture
def scale(rows, w, h):
    """Bilinear resize of RGBA rows (top-down) to w x h."""
    sw, sh = len(rows[0]) // 4, len(rows)
    out = []
    for y in range(h):
        fy = (y + 0.5) * sh / h - 0.5
        y0 = max(0, min(sh - 1, int(math.floor(fy)))); y1 = min(sh - 1, y0 + 1); ty = min(1.0, max(0.0, fy - y0))
        row = bytearray(w * 4)
        for x in range(w):
            fx = (x + 0.5) * sw / w - 0.5
            x0 = max(0, min(sw - 1, int(math.floor(fx)))); x1 = min(sw - 1, x0 + 1); tx = min(1.0, max(0.0, fx - x0))
            for c in range(4):
                a = rows[y0][x0 * 4 + c] * (1 - tx) + rows[y0][x1 * 4 + c] * tx
                b = rows[y1][x0 * 4 + c] * (1 - tx) + rows[y1][x1 * 4 + c] * tx
                row[x * 4 + c] = int(a * (1 - ty) + b * ty + 0.5)
        out.append(row)
    return out


def opaque(rows):
    """Copy with alpha forced to 255 (the BANDERAS pictures are 24-bit or carry no useful alpha)."""
    out = []
    for r in rows:
        r = bytearray(r)
        r[3::4] = bytes([255]) * (len(r) // 4)
        out.append(r)
    return out


def derive_image(img):
    """Select Empire and welcome variants from a flag picture (e.g. Models/BANDERAS/Espanya.tga)."""
    img = opaque(img)
    keep = int(len(img[0]) // 4 * 0.86)                # drop the grey flag pole at the right edge
    img = [r[:keep * 4] for r in img]
    big = scale(img, 256, 128)
    b = _arr(big)
    v = {'e57': _rows(badge(b[:, int(256 * 0.19):int(256 * 0.81)], 'e57', dim=1.15))}   # 3D texture -> UI brightness
    v.update(select_strips(big))
    v['notification'] = _notification_from(scale(img, 147, 160))
    return v


def _notification_from(flag):
    out = blank(256, 256)
    for y in range(160):
        for x in range(147):
            r, g, b = flag[y][x * 4:x * 4 + 3]
            lum = (r * 3 + g * 6 + b) / 10
            fade = 0.55
            r, g, b = [int(c * (1 - fade) + lum * fade * 0.95 + 18 * fade) for c in (r, g, b)]
            dx, dy = (x - 73) / 73, (y - 80) / 80
            vv = max(0.0, 1.0 - 0.55 * (dx * dx + dy * dy) ** 1.2)
            grain = 0.92 + 0.08 * math.sin(x * 1.7 + y * 0.9) * math.cos(y * 1.3)
            out[1 + y][(1 + x) * 4:(1 + x) * 4 + 4] = bytes((min(255, int(r * vv * grain)), min(255, int(g * vv * grain)),
                                                             min(255, int(b * vv * grain)), 255))
    return out


# ---------------------------------------------------------------- Select Empire row strips from the game's own art
SE_DIR = __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), '..', 'data',
                                    'Game', 'UI', 'MainMenu', 'SelectEmpire')
# 297x57 strips (GB): normal is painted in the dialog background, dark = disabled look, gold frame = selected
SE_NORMAL = ('SeleccionImperioA_.tga', 49, 153)
SE_DARK = ('SeleccionImperioA_.tga', 23, 929)
SE_SEL = ('SeleccionImperioB_.tga', 102, 431)
SE_PANEL = (9, 4, 143, 53)            # flag panel interior (x0, y0, x1, y1), dark frame just outside


def _se_strip(spec):
    from PIL import Image
    import numpy as np
    f, u, v = spec
    im = Image.open(__import__('os').path.join(SE_DIR, f)).convert('RGBA')
    return np.asarray(im.crop((u, v, u + 297, v + 57))).astype(np.float32)


def select_strips(flag):
    """b297_fondo / b297_disable / b297_sel rows: the original strips with the nation's flag in the panel,
    faded and darkened towards the edges like the painted originals."""
    from PIL import Image
    import numpy as np
    x0, y0, x1, y1 = SE_PANEL
    w, h = x1 - x0, y1 - y0
    src = np.asarray(flag, dtype=np.uint8).reshape(len(flag), -1, 4)[:, :, :3]
    f = np.asarray(Image.fromarray(src).resize((w, h), Image.LANCZOS)).astype(np.float32)
    # painted on parchment like the originals: multiply onto parchment, brushy coverage, smoky dark edges
    parch = _se_strip(('SeleccionImperioA_.tga', 120, 535))[:h, :w, :3]
    lum = f @ np.array([0.30, 0.59, 0.11], np.float32)
    f = f * 0.80 + lum[..., None] * 0.20
    rng = np.random.default_rng(7)
    def noise(sx, sy):
        n = Image.fromarray((rng.random((max(2, h // sy), max(2, w // sx))) * 255).astype(np.uint8))
        return np.asarray(n.resize((w, h), Image.BICUBIC), np.float32) / 255.0
    brush = np.clip(0.55 * noise(18, 3) + 0.30 * noise(6, 2) + 0.25 * noise(2, 1), 0, 1)
    paint = np.clip(parch * f / 175.0, 0, 255)
    cover = np.clip(0.55 + 0.55 * brush, 0, 1)[..., None]
    f = parch * (1 - cover) + paint * cover
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = (xx - (w - 1) / 2) / ((w - 1) / 2), (yy - (h - 1) / 2) / ((h - 1) / 2)
    smoke = np.clip(np.abs(dx) ** 2.5 * 0.75 + np.abs(dy) ** 3 * 0.45 + (noise(10, 4) - 0.5) * 0.35 * (np.abs(dx) ** 1.5 + 0.2), 0, 0.85)
    f = f * (1 - smoke[..., None]) + np.array([38, 30, 22], np.float32) * smoke[..., None]
    normal = _se_strip(SE_NORMAL)
    dark = _se_strip(SE_DARK)
    ratio = dark[y0:y1, 150:290, :3].mean((0, 1)) / normal[y0:y1, 150:290, :3].mean((0, 1))
    out = {}
    for name, base, k in (('b297_fondo', normal, 1.0), ('b297_disable', dark, ratio), ('b297_sel', _se_strip(SE_SEL), 1.08)):
        s = base.copy()
        s[y0:y1, x0:x1, :3] = np.clip(f * k, 0, 255)
        s[..., 3] = 255
        a = s.astype(np.uint8)
        out[name] = [bytearray(a[r].tobytes()) for r in range(57)]
    return out

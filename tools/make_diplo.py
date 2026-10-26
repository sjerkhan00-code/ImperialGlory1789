"""2D province maps of the menus and the diplomacy window (UIC_MAPAPAISES), rebuilt for the whole map.

How the game does it (re_tools/report_diplomacy.md): one background bitmap (.FONDO, MapaDiplomacia.tga or
Comun/MapaPaises.tga, map interior x 51..501, y 99..576) and per province three sprites (released / pressed /
selected) cut from atlases. A sprite's .X/.Y is its pixel position in the background texture; its RGB is the
background under it, brightened (per-channel curves measured from the original pairs), its alpha a soft mask.
The window shows and tints sprites per owner at runtime; provinces without an entry are skipped.

Here: a projection of the whole map into the interior that keeps Europe large (monotone, separable focus warp,
the original art is hand-drawn and not an exact projection either), masks from the province meshes, the original
brightening curves, and new atlases. The background takes its look from the original interior, measured at run
time (orig_style: water and land tone curves, its clouds at the same place, the maroon coast line, the borders
in the sprite seams, its ship drawings) and only the fine detail from the campaign map's own tiles. All five
UIDefs_MapaPaises*.sb get the same PROVINCIAS list.
"""
import os, re, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import meshgen as MG
import retile as RT
import tga
from igmod import Mng, v3d_objects, find_block

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, MOD, BUILD = (os.path.join(ROOT, d) for d in ('data', 'mod', 'build'))
DIPLO_BG = 'Game/UI/ModeloGestion/Diplomacia/MapaDiplomacia.tga'
COMUN_BG = 'Game/UI/Comun/MapaPaises.tga'
ATLAS = 'Game/UI/ModeloGestion/Diplomacia/ProvDiplo%s%d.tga'          # state, sheet
STATES = (('SOLTADO', 'NoSel'), ('PULSADO', 'Puls'), ('SELECT', 'Sel'))
ORIG_ATLAS = {'NoSel': 'Game/UI/Comun/ProvinciasNoSeleccion.tga', 'Puls': 'Game/UI/Comun/ProvinciasPulsado.tga',
              'Sel': 'Game/UI/Comun/ProvinciasSeleccion.tga'}
SEL_SB = 'Game/UI/ModeloGestion/Diplomacia/UIDefs_MapaPaisesSeleccion.sb'
IX0, IY0, IX1, IY1 = 51, 99, 501, 577            # map interior in the background textures
W, H = IX1 - IX0, IY1 - IY0
SS = 4                                           # mask supersampling

# focus warp knots: (world coordinate, fraction of the interior). The original window showed x 1350..14945 and
# z 12168..-379 (fit to its art); that part keeps about half the width and height.
KX = [(-400.0, 0.0), (1350.0, 0.035), (14945.0, 0.50), (44300.0, 1.0)]
KZ = [(13500.0, 0.0), (12168.0, 0.02), (-379.0, 0.53), (-11300.0, 1.0)]


def _pchip(knots):
    """Monotone cubic (Fritsch-Carlson) through knots; returns f(array) and its inverse."""
    xs = np.array([k[0] for k in knots]); ys = np.array([k[1] for k in knots])
    if xs[0] > xs[-1]:
        xs, ys = xs[::-1], ys[::-1]
    h = np.diff(xs); dlt = np.diff(ys) / h
    m = np.zeros_like(xs)
    m[0], m[-1] = dlt[0], dlt[-1]
    for i in range(1, len(xs) - 1):
        if dlt[i - 1] * dlt[i] <= 0:
            m[i] = 0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / dlt[i - 1] + w2 / dlt[i])
    grid = np.linspace(xs[0], xs[-1], 20001)
    k = np.clip(np.searchsorted(xs, grid) - 1, 0, len(xs) - 2)
    t = (grid - xs[k]) / h[k]
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    vals = h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1]
    order = np.argsort(vals)
    return (lambda a: np.interp(a, grid, vals)), (lambda f: np.interp(f, vals[order], grid[order]))


FX, FX_INV = _pchip(KX)
FZ, FZ_INV = _pchip(KZ)


def project(x, z):
    """world -> pixel in the interior image (0..W, 0..H)."""
    return FX(np.asarray(x)) * W, FZ(np.asarray(z)) * H


def _img(path):
    return np.asarray(Image.open(path).convert('RGBA'))


def _src(rel):
    for base in (MOD, os.path.join(ROOT, 'data1'), DATA):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)


def _orig(rel):
    for base in (os.path.join(ROOT, 'data1'), DATA):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)


# ---------------------------------------------------------------- background
# The original interior (MapaDiplomacia.tga) is a dark parchment: teal-grey water and light parchment land under the
# same large light and dark clouds, a ~3 px maroon coast line with a dark halo on the water side, thin dark borders
# in the seams between the province sprites and faint ship drawings. All of that is measured from the original here
# (orig_style) and laid over the campaign map art, which only gives the fine detail (paper, lines, marks).
LUMW = np.array([0.30, 0.59, 0.11], np.float32)
S_V = 10.0                                       # px: scale of the original's clouds (its vignette)
SHIPS = ((250, 124), (334, 285), (57, 160))      # the clearest ship drawings of the original (interior px)
SHIP_R = 13                                      # px: radius of a ship drawing (masts included)


def _world_mosaic(scale=256):
    """The campaign map art (9 x 7 tiles of the enlarged map) at `scale` px per tile, top row first."""
    canvas = Image.new('RGB', (9 * scale, 7 * scale))
    for row in range(7):
        for col in range(9):
            p = next((q for q in (os.path.join(BUILD, 'oldarea', 'tiles', 'tile_%d_%d.png' % (col, row)),
                                  os.path.join(BUILD, 'art', 'deframe', 'tile_%d_%d.png' % (col, row)),
                                  os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))) if os.path.exists(q)),
                     os.path.join(BUILD, 'tiles_png', 'T00%d00%d.png' % (3 - row, col)))
            canvas.paste(Image.open(p).convert('RGB').resize((scale, scale), Image.LANCZOS), (col * scale, row * scale))
    return np.asarray(canvas).astype(np.float32), scale


def _art_sample():
    """The campaign map art projected into the interior (H x W x 3) and the world x, z of every pixel."""
    mos, sc = _world_mosaic()
    ys, xs = np.mgrid[0:H * 2, 0:W * 2].astype(np.float32)
    wx = FX_INV((xs + 0.5) / (W * 2)); wz = FZ_INV((ys + 0.5) / (H * 2))
    z_top = MG.ROWS[4]
    mx = (wx - RT.X0) / MG.TILE_W * sc - 0.5
    my = (z_top - wz) / MG.TILE_H * sc - 0.5
    mx = np.clip(mx, 0, mos.shape[1] - 1.001); my = np.clip(my, 0, mos.shape[0] - 1.001)
    x0, y0 = mx.astype(int), my.astype(int); fx, fy = (mx - x0)[..., None], (my - y0)[..., None]
    img = (mos[y0, x0] * (1 - fx) * (1 - fy) + mos[y0, x0 + 1] * fx * (1 - fy)
           + mos[y0 + 1, x0] * (1 - fx) * fy + mos[y0 + 1, x0 + 1] * fx * fy)
    return (img.reshape(H, 2, W, 2, 3).mean((1, 3)), wx.reshape(H, 2, W, 2).mean((1, 3)),
            wz.reshape(H, 2, W, 2).mean((1, 3)))


# small image helpers (numpy; scipy only for exact distances when it is installed)
def _gauss(a, s):
    """Separable gaussian blur with reflected borders (H x W or H x W x C)."""
    a = np.asarray(a, np.float32)
    r = max(1, int(3 * s + 0.5))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / s) ** 2); k /= k.sum()
    for ax in (0, 1):
        pad = [(0, 0)] * a.ndim; pad[ax] = (r, r)
        p = np.pad(a, pad, mode='reflect')
        out = np.zeros_like(a)
        for i, w in enumerate(k):
            sl = [slice(None)] * a.ndim; sl[ax] = slice(i, i + a.shape[ax])
            out += w * p[tuple(sl)]
        a = out
    return a


def _nc(v, m, s, fill=None):
    """Local mean of v over the pixels of mask m (normalised convolution); far from m it tends to `fill`."""
    m = np.asarray(m, np.float32)
    if fill is None:
        fill = v[m > 0].mean(0) if m.any() else v.reshape(-1, *v.shape[2:]).mean(0)
    eps = 1e-3
    den = _gauss(m, s) + eps
    if v.ndim == 3:
        return (_gauss(v * m[..., None], s) + eps * np.asarray(fill, np.float32)) / den[..., None]
    return (_gauss(v * m, s) + eps * fill) / den


def _maxf3(a):
    return np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)),
                      np.float32) / 255.0


def _close3(a):
    """3 x 3 closing: fills the seams between sprites without growing the outer edge."""
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3)), np.float32) / 255.0


def _supersample():
    try:
        import scipy.ndimage  # noqa: F401
        return 4
    except ImportError:
        return 1


def _dist(mask, R=16):
    """Distance (px) from every pixel to the nearest True pixel of mask (capped at R without scipy)."""
    if not mask.any():
        return np.full(mask.shape, float(R), np.float32)
    try:
        from scipy import ndimage
        return ndimage.distance_transform_edt(~mask).astype(np.float32)
    except ImportError:
        h, w = mask.shape
        d = np.where(mask, 0.0, float(R)).astype(np.float32)
        p = np.pad(mask, R, mode='edge')
        for r, dx, dy in sorted(((dx * dx + dy * dy) ** 0.5, dx, dy) for dx in range(-R, R + 1)
                                for dy in range(-R, R + 1) if 0 < dx * dx + dy * dy <= R * R):
            np.minimum(d, np.where(p[R + dy:R + dy + h, R + dx:R + dx + w], r, R), out=d)
        return d


def _up(a, ss):
    if ss == 1:
        return np.asarray(a, np.float32)
    return np.asarray(Image.fromarray(np.asarray(a, np.float32), 'F').resize((W * ss, H * ss), Image.BILINEAR))


def _down(a, ss):
    return a if ss == 1 else a.reshape(H, ss, W, ss).mean((1, 3))


def _sdist(soft, ss):
    """Signed distance (px) to the 0.5 contour of a soft mask: > 0 outside, < 0 inside."""
    up = _up(soft, ss) >= 0.5
    return _down(np.where(up, 0.5 - _dist(~up, 16 * ss), _dist(up, 16 * ss) - 0.5) / ss, ss)


def _seam_dist(plain, where, ss):
    """Distance (px) to the seams between neighbouring sprites (plain: the union of their alpha), only where
    `where`."""
    seam = (_up(_close3(plain), ss) >= 0.5) & (_up(plain, ss) < 0.6) & (_up(where.astype(np.float32), ss) >= 0.5)
    return _down(_dist(seam, 16 * ss) / ss, ss)


def _erode(mask, n):
    m = Image.fromarray(mask.astype(np.uint8) * 255)
    for _ in range(n):
        m = m.filter(ImageFilter.MinFilter(3))
    return np.asarray(m) > 127


def _despeckle(a, thr):
    """Single pixels brighter or darker by thr than all 8 neighbours (dots in the campaign art) take their median;
    lines keep their pixels (a line pixel has neighbours like itself)."""
    p = np.pad(a, 1, mode='edge')
    nb = np.stack([p[y:y + H, x:x + W] for y in range(3) for x in range(3) if (y, x) != (1, 1)])
    lo, hi = nb.min(0), nb.max(0)
    return np.where((a > hi + thr) | (a < lo - thr), np.median(nb, 0), a)


def _robust_std(x):
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size else 0.0


def _fine(N, m):
    """Grain: N minus its 1 px local mean within m."""
    return N - _nc(np.where(m, N, 1.0), m, 1.0, 1.0)


def _sprite_union(keep):
    """Union of the original sprites' alpha (0..1) for the provinces with keep(idx)."""
    at = _img(_orig(ORIG_ATLAS['NoSel']))
    txt = open(_orig(SEL_SB), 'rb').read().decode('latin1')
    m = np.zeros((H, W), np.float32)
    for idx, X, Y, U, V, SX, SY in _entries(txt):
        if not keep(idx):
            continue
        a = at[V:V + SY, U:U + SX, 3].astype(np.float32) / 255.0
        x0, y0 = X - IX0, Y - IY0
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + SX), min(H, y0 + SY)
        if xb > xa and yb > ya:
            m[ya:yb, xa:xb] = np.maximum(m[ya:yb, xa:xb], a[ya - y0:yb - y0, xa - x0:xb - x0])
    return m


def _orig_land_mask():
    """Land provinces (idx 1..51) of the original map, from the original sprites' alpha."""
    return _sprite_union(lambda i: i <= 51)


def _profile(x, ratio, sel, edges):
    """Mean colour ratio (H x W x 3) over the pixels of sel by distance x, in bins centred on edges (1 if too few)."""
    out = np.ones((len(edges), 3), np.float32)
    half = (edges[1] - edges[0]) / 2
    for i, e in enumerate(edges):
        m = sel & (np.abs(x - e) <= half)
        if m.sum() >= 40:
            out[i] = ratio[m].mean(0)
    return out


_STYLE = {}


def orig_style():
    """What the original interior looks like, measured from it (cached)."""
    if _STYLE:
        return _STYLE
    ss = _supersample()
    ref = _img(_orig(DIPLO_BG))[IY0:IY1, IX0:IX1, :3].astype(np.float32)
    lum = ref @ LUMW
    rl0 = _orig_land_mask(); rl = _maxf3(rl0)                     # playable land, as the land mask in build()
    rs0 = _sprite_union(lambda i: i > 51)                         # sea zones
    teal = _gauss(ref[..., 1] - ref[..., 0], 2.0) >= -2.5          # water (the unplayable land is brown)
    d = _sdist(rl, ss)
    to_teal, in_teal = _dist(teal), _dist(~teal)
    opensea = teal & (in_teal > 4) & (d > 6)
    land = (rl > 0.5) & (d < -3)
    other = ~teal & (rl < 0.05) & (to_teal > 4)                    # unplayable land, without its coast line
    # the clouds: brightness of each kind of ground relative to its mean, joined and smoothed
    rel = np.zeros_like(lum); valid = np.zeros_like(lum)
    for m in (opensea, land, other):
        rel[m] = lum[m] / lum[m].mean(); valid[m] = 1
    st = {'V': _nc(rel, valid, S_V, 1.0)}
    for k, m in (('sea', opensea), ('land', land)):
        base = _nc(lum, m, S_V)
        st[k + '_mean'] = float(lum[m].mean())
        st[k + '_grain'] = _robust_std(_fine(np.where(m, lum / base, 1.0), m)[m])
        st[k + '_base'] = _nc(ref, m, S_V)
        # luminance -> colour (the per-channel tone curves): mean chroma per luminance step, held at the ends
        b = np.clip(lum[m].astype(int), 0, 255)
        n = np.bincount(b, minlength=256); have = np.nonzero(n >= 30)[0]
        cur = np.zeros((256, 3), np.float32)
        for c in range(3):
            ratio = np.bincount(b, weights=ref[..., c][m], minlength=256)[have] / n[have] / np.maximum(have, 1)
            cur[:, c] = np.interp(np.arange(256), have, ratio) * np.arange(256)
        st[k + '_curve'] = cur
    # coast: colour relative to the local land / water colour by signed distance from the land sprites' edge, only
    # where the water is close (inland seams are no coast) and away from the unplayable land
    far = _dist(_erode(other, 2)) > 10
    near = to_teal <= 6
    e = np.arange(-6, 0.01, 0.25)
    st['coast_land_d'] = e
    st['coast_land'] = _profile(d, ref / np.maximum(st['land_base'], 1), far & near & (rl > 0.5) & (d < 0), e)
    e = np.arange(0, 14.01, 0.25)
    st['coast_sea_d'] = e
    st['coast_sea'] = _profile(d, ref / np.maximum(st['sea_base'], 1), far & near & (rl < 0.5) & (d >= 0), e)
    # borders: colour relative to the local colour by distance from the seams between the sprites
    e = np.arange(0, 4.01, 0.25)
    st['border_d'] = e
    for k, dist, sel in (('land', _seam_dist(rl0, d < -2.0, ss), land & (d < -2.5)),
                         ('sea', _seam_dist(rs0, teal & (d > 2.0), ss), teal & (d > 4))):
        p = _profile(dist, ref / np.maximum(st[k + '_base'], 1), sel, e)
        st['border_' + k] = p / p[e >= 2.5].mean(0)          # 1 away from the line (the base includes the lines)
    # ship drawings: brightness relative to the water in a ring around them, inside a soft disc (water only)
    r = SHIP_R + 2
    py, px = np.mgrid[-r:r + 1, -r:r + 1]
    rr = np.hypot(px / 0.85, py)                                   # a ship is taller than wide
    st['ships'] = []
    for cx, cy in SHIPS:
        sl = (slice(cy - r, cy + r + 1), slice(cx - r, cx + r + 1))
        water = np.clip((in_teal[sl] - 3.0) / 2.0, 0, 1)             # not the coast line nor its halo
        ring = (rr > SHIP_R - 1) & (rr < SHIP_R + 2) & (water > 0.99)
        soft = np.clip((SHIP_R - rr) / 3.0, 0, 1) * water
        st['ships'].append((1 + (lum[sl] / lum[sl][ring].mean() - 1) * soft)[..., None])
    _STYLE.update(st)
    return _STYLE


def _find_ships(N, sea_ok):
    """Ship icons of the campaign art: small dark compact blobs in the open water (N: art relative to its
    surroundings). Blobs with a neighbour closer than 14 px (the compass rose) are left alone."""
    blob = (_gauss(N, 1.0) < 0.85) & sea_ok
    seen = np.zeros_like(blob); found = []
    ys, xs = np.nonzero(blob)
    for y0, x0 in zip(ys, xs):
        if seen[y0, x0]:
            continue
        stack, pts = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop(); pts.append((y, x))
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < H and 0 <= xx < W and blob[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; stack.append((yy, xx))
        p = np.array(pts)
        h, w = np.ptp(p[:, 0]) + 1, np.ptp(p[:, 1]) + 1
        if 4 <= len(p) <= 80 and max(h, w) <= 12 and max(h, w) <= 3.5 * min(h, w):
            found.append((p[:, 1].mean(), p[:, 0].mean()))
    return [(x, y) for i, (x, y) in enumerate(found)
            if all((x - u) ** 2 + (y - v) ** 2 >= 14 ** 2 for j, (u, v) in enumerate(found) if j != i)]


def render_interior(land, land_sprites=None, sea_sprites=None, seed=1789):
    """land: H x W soft mask (0..1) of the land provinces (seams closed); land_sprites / sea_sprites: the plain
    unions of the land / sea province masks, whose seams are the borders. Returns the interior RGB (float)."""
    st = orig_style()
    ss = _supersample()
    art, wx, wz = _art_sample()
    La = art @ LUMW
    rng = np.random.default_rng(seed)
    noise = _gauss(rng.standard_normal((H, W)).astype(np.float32), 0.5)
    noise /= noise.std()
    d = _sdist(land, ss)
    far = np.full((H, W), 99.0, np.float32)
    dl = _seam_dist(land_sprites, d < -2.0, ss) if land_sprites is not None else far
    dz = _seam_dist(sea_sprites, d > 2.0, ss) if sea_sprites is not None else far
    # the old map art (x 473..20192, z -970..12506) and the new tiles differ in grain: each part on its own
    oldart = (wx < 20192) & (wz > -970)
    yy, xx = np.mgrid[0:H, 0:W]
    L = np.zeros((H, W), np.float32)
    ships = []
    for k, m, band, lines in (('land', d <= 0, 5.0, dl), ('sea', d > 0, 4.0, dz)):
        # the art's own coast and border drawing is replaced by the original's (see below): grain only there
        keep = np.clip((np.abs(d) - band + 2.5) / 2.5, 0, 1) * np.clip((lines - 1.0) / 2.0, 0, 1)
        core = m & (keep > 0.99)
        N = np.where(m, La / np.maximum(_nc(La, core, S_V), 1), 1.0)
        N = _despeckle(N, 0.2)
        g = st[k + '_grain']
        if k == 'sea':
            # the art's small ship icons in open water make room for the original's ship drawings
            r = SHIP_R + 2
            for cx, cy in _find_ships(N, core & (d > 6)):
                x0, y0 = int(round(cx)), int(round(cy))
                disc = (xx - x0) ** 2 + (yy - y0) ** 2 <= SHIP_R ** 2
                if r <= x0 < W - r and r <= y0 < H - r and d[disc].min() > 2.5:
                    ships.append((x0, y0))
                    keep = np.where((xx - cx) ** 2 + (yy - cy) ** 2 <= 36, 0.0, keep)
        for part in (oldart, ~oldart):
            sel = core & part
            if sel.sum() < 100:
                continue
            # the art's contrast as it is (never above the original's grain), the missing grain as noise
            ga = _robust_std(_fine(N, sel)[sel])
            s = min(1.0, g / max(ga, 1e-6))
            add = np.sqrt(max(g * g - (ga * s) ** 2, 0.0))
            sel = m & part
            N[sel] = 1 + (N[sel] - 1) * s + noise[sel] * add
        N = keep * N + (1 - keep) * (1 + noise * g)
        Lk = st['V'] * N
        # the clouds lie where they lie in the original; the mean is the original's mean of this ground
        L[m] = (Lk * (st[k + '_mean'] / (Lk[core].mean() if core.any() else 1.0)))[m]
    out = np.zeros((H, W, 3), np.float32)
    Li = np.clip(L, 0, 255)
    for k, m in (('land', d <= 0), ('sea', d > 0)):
        for c in range(3):
            out[..., c] = np.where(m, np.interp(Li, np.arange(256), st[k + '_curve'][:, c]), out[..., c])
    for c in range(3):
        out[..., c] *= np.where(d <= 0,
                                np.interp(d, st['coast_land_d'], st['coast_land'][:, c], left=1.0)
                                * np.interp(dl, st['border_d'], st['border_land'][:, c], right=1.0),
                                np.interp(d, st['coast_sea_d'], st['coast_sea'][:, c], right=1.0)
                                * np.interp(dz, st['border_d'], st['border_sea'][:, c], right=1.0))
    r = SHIP_R + 2
    for i, (x0, y0) in enumerate(ships):
        patch = st['ships'][i % len(st['ships'])]
        if (i // len(st['ships'])) % 2:
            patch = patch[:, ::-1]
        out[y0 - r:y0 + r + 1, x0 - r:x0 + r + 1] *= patch
    return np.clip(out, 0, 255)


# ---------------------------------------------------------------- brightening curves from the original pairs
def _entries(txt):
    """(idx, X, Y, U, V, SX, SY) of every BMP_SOLTADO in a UIDefs_MapaPaises file."""
    res = []
    for m in re.finditer(r'\.IDX\s+(\d+).*?\.BMP_SOLTADO\s*\[[^\]]*?\.X\s+(\d+)\s+\.Y\s+(\d+)\s+\.U\s+(\d+)\s+\.V\s+(\d+)'
                         r'\s+\.SX\s+(\d+)\s+\.SY\s+(\d+)', txt, re.S):
        res.append(tuple(int(g) for g in m.groups()))
    return res


def curves():
    """LUTs (256 x 3): background -> NoSel, NoSel -> Puls, NoSel -> Sel."""
    bg = _img(_orig(DIPLO_BG)).astype(np.float32)
    at = {k: _img(_orig(v)).astype(np.float32) for k, v in ORIG_ATLAS.items()}
    txt = open(_orig(SEL_SB), 'rb').read().decode('latin1')
    pairs = {'NoSel': ([], []), 'Puls': ([], []), 'Sel': ([], [])}
    for idx, X, Y, U, V, SX, SY in _entries(txt):
        n = at['NoSel'][V:V + SY, U:U + SX]
        ok = n[..., 3] == 255
        pairs['NoSel'][0].append(bg[Y:Y + SY, X:X + SX, :3][ok]); pairs['NoSel'][1].append(n[..., :3][ok])
        for k in ('Puls', 'Sel'):
            pairs[k][0].append(n[..., :3][ok]); pairs[k][1].append(at[k][V:V + SY, U:U + SX, :3][ok])
    luts = {}
    for k, (a, b) in pairs.items():
        a = np.concatenate(a); b = np.concatenate(b)
        lut = np.zeros((256, 3), np.float32)
        for c in range(3):
            s = np.bincount(a[:, c].astype(int), weights=b[:, c], minlength=256)
            n = np.bincount(a[:, c].astype(int), minlength=256)
            have = n > 20
            vals = np.interp(np.arange(256), np.nonzero(have)[0], s[have] / n[have])
            lut[:, c] = np.maximum.accumulate(vals)          # monotone
        luts[k] = lut
    return luts


def apply_lut(img, lut):
    i = np.clip(img, 0, 255).astype(int)
    return np.stack([lut[i[..., c], c] for c in range(3)], -1)


# ---------------------------------------------------------------- province masks
def province_triangles(v3d_path):
    """mesh name (lower case) -> list of triangles [(x, z) * 3] in world coordinates."""
    d = open(v3d_path, 'rb').read()
    res = {}
    for o, cid, size, name, parent in v3d_objects(d):
        if cid != 0x2000:
            continue
        b = d[o:o + size]
        body, vh, group, fmt, stride, nv = RT._mesh_layout(b, 0)
        if stride != 28:
            continue
        tx, _, tz = struct.unpack_from('<3f', b, body + 64 + 48)
        pts = [struct.unpack_from('<3f', b, vh + 20 + 28 * i) for i in range(nv)]
        ih = vh + 20 + 28 * nv
        ni = struct.unpack_from('<I', b, ih + 12)[0]
        idx = struct.unpack_from('<%dH' % ni, b, ih + 16)
        res[name.lower()] = [tuple((pts[i][0] + tx, pts[i][2] + tz) for i in idx[t:t + 3]) for t in range(0, ni, 3)]
    return res


def mask(tris):
    """Soft alpha (H x W, 0..1) of the projected triangles, slightly shrunk so neighbours keep a dark seam."""
    im = Image.new('L', (W * SS, H * SS), 0)
    dr = ImageDraw.Draw(im)
    for tri in tris:
        px, py = project([p[0] for p in tri], [p[1] for p in tri])
        dr.polygon([(float(a) * SS, float(b) * SS) for a, b in zip(px, py)], fill=255)
    im = im.filter(ImageFilter.MinFilter(5))
    return np.asarray(im.resize((W, H), Image.BOX), np.float32) / 255.0


def comun_tone():
    """Per-channel gain and offset that turn the original diplomacy interior into the original menu one."""
    a = _img(_orig(DIPLO_BG))[IY0:IY1, IX0:IX1, :3].reshape(-1, 3).astype(np.float64)
    b = _img(_orig(COMUN_BG))[IY0:IY1, IX0:IX1, :3].reshape(-1, 3).astype(np.float64)
    fit = [np.polyfit(a[:, c], b[:, c], 1) for c in range(3)]
    return np.array([f[0] for f in fit], np.float32), np.array([f[1] for f in fit], np.float32)


# ---------------------------------------------------------------- build
def build(write, sb_texts):
    """write(rel, bytes) stores a mod file; sb_texts: dict rel -> text of the five UIDefs_MapaPaises files.
    Returns the updated dict."""
    mng = Mng(open(os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read())
    recs = Mng.parse_provinces(mng.section(4))
    tris = province_triangles(os.path.join(MOD, 'Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D'))
    luts = curves()
    masks = {}
    for r in recs:
        tt = tris.get(r['name'].lower())
        if tt:
            masks[r['idx']] = mask(tt)
    land = np.zeros((H, W), np.float32)
    for r in recs:
        if not r['sea'] and r['idx'] in masks:
            land = np.maximum(land, masks[r['idx']])
    sea = np.zeros((H, W), np.float32)
    for r in recs:
        if r['sea'] and r['idx'] in masks:
            sea = np.maximum(sea, masks[r['idx']])
    land_sprites = land
    land = np.asarray(Image.fromarray((land * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)), np.float32) / 255.0
    interior = render_interior(land, land_sprites, sea)
    # backgrounds: original frames, new interior; the menus' copy (Comun) is darker in the original
    gain, off = comun_tone()
    for rel in (DIPLO_BG, COMUN_BG):
        o = _img(_orig(rel))
        a = o.copy()
        a[IY0:IY1, IX0:IX1, :3] = np.clip(np.rint(interior * gain + off if rel == COMUN_BG else interior),
                                          0, 255).astype(np.uint8)
        # the last row of the interior box is the frame's in the original: keep it
        lum = o[..., :3].astype(np.float32) @ LUMW
        if lum[IY1 - 1, IX0:IX1].mean() > 1.4 * lum[IY1 - 3, IX0:IX1].mean():
            a[IY1 - 1, IX0:IX1] = o[IY1 - 1, IX0:IX1]
        hh, ww = a.shape[:2]
        write(rel, None, (ww, hh, [bytearray(a[r].tobytes()) for r in range(hh)]))
    lit = {'NoSel': apply_lut(interior, luts['NoSel'])}
    lit['Puls'] = apply_lut(lit['NoSel'], luts['Puls'])
    lit['Sel'] = apply_lut(lit['NoSel'], luts['Sel'])
    # sprites, land first so that coastal clicks pick the land
    sprites = []
    for r in sorted(recs, key=lambda r: (r['sea'], r['idx'])):
        if r['idx'] not in masks:
            print('  diplomacy map: no mesh for', r['name'])
            continue
        m = masks[r['idx']]
        ys, xs = np.nonzero(m > 0.02)
        if len(xs) == 0:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        sprites.append((r, x0, y0, x1 - x0, y1 - y0, m[y0:y1, x0:x1]))
    # shelf packing into 1024 x 1024 sheets
    sheets, place = [], {}
    order = sorted(range(len(sprites)), key=lambda i: -sprites[i][4])
    x = y = rowh = 0; sheet = -1
    for i in order:
        w, h = sprites[i][3], sprites[i][4]
        if sheet < 0 or x + w > 1024:
            x, y, rowh = 0, y + rowh + 2, 0
        if sheet < 0 or y + h > 1024:
            sheet += 1; x = y = rowh = 0
            sheets.append({k: np.zeros((1024, 1024, 4), np.uint8) for k in lit})
        place[i] = (sheet, x, y)
        r, sx, sy, w, h, m = sprites[i]
        for k in lit:
            px = np.concatenate([lit[k][sy:sy + h, sx:sx + w], (m * 255)[..., None]], -1)
            sheets[sheet][k][y:y + h, x:x + w] = np.clip(px, 0, 255).astype(np.uint8)
        x += w + 2; rowh = max(rowh, h)
    for s, sh in enumerate(sheets):
        for k, a in sh.items():
            write(ATLAS % (k, s + 1), None, (1024, 1024, [bytearray(a[r].tobytes()) for r in range(1024)]))
    # PROVINCIAS block
    CR = chr(13) + chr(10)
    lines = ['.PROVINCIAS', '[']
    for i, (r, sx, sy, w, h, m) in enumerate(sprites):
        s, u, v = place[i]
        lines += ['', '\t#---------------------------------------------- %s ' % r['name'].upper(), '\t[', '\t\t.PROVINCIA', '\t\t[',
                  '\t\t\t.IDX %d' % r['idx'], '\t\t\t.ENABLED TRUE']
        for tag, k in STATES:
            lines.append('\t\t\t.BMP_%-8s [ .FILE "%s" .X %d .Y %d .U %d .V %d .SX %d .SY %d .ALPHA TRUE .PRIORITY 30 ]'
                         % (tag, ATLAS % (k, s + 1), IX0 + sx, IY0 + sy, u, v, w, h))
        lines += ['\t\t]', '\t]']
    lines += [']']
    block = CR.join(lines)
    for rel, txt in sb_texts.items():
        m0 = re.search(r'^\.PROVINCIAS\b', txt, re.M)
        a, b = find_block(txt, m0.end())
        sb_texts[rel] = txt[:m0.start()] + block + txt[b:]
    print('  diplomacy/menu maps: %d province sprites on %d atlas sheet(s)' % (len(sprites), len(sheets)))
    return sb_texts, interior, sprites


if __name__ == '__main__':
    # preview only: composites in build/diplo, nothing written to mod
    os.makedirs(os.path.join(BUILD, 'diplo'), exist_ok=True)
    files = {}
    def write(rel, data, img=None):
        files[rel] = img
    sb = {SEL_SB: open(_src(SEL_SB), 'rb').read().decode('latin1')}
    sb, interior, sprites = build(write, sb)
    w, h, rows = files[DIPLO_BG]
    bg = np.frombuffer(b''.join(rows), np.uint8).reshape(h, w, 4).astype(np.float32)
    tint = [(194, 235, 152), (158, 185, 132), (229, 215, 120), (204, 178, 128), (196, 132, 132)]
    comp = bg.copy()
    sheets = {}
    for rel, img in files.items():
        if 'ProvDiploNoSel' in rel:
            ww, hh, rr = img
            sheets[rel] = np.frombuffer(b''.join(rr), np.uint8).reshape(hh, ww, 4).astype(np.float32)
    for m in re.finditer(r'\.IDX\s+(\d+).*?\.BMP_SOLTADO\s*\[\s*\.FILE\s+"([^"]+)"\s+\.X\s+(\d+)\s+\.Y\s+(\d+)\s+\.U\s+(\d+)\s+\.V\s+(\d+)\s+\.SX\s+(\d+)\s+\.SY\s+(\d+)',
                         sb[SEL_SB], re.S):
        idx, f, X, Y, U, V, SX, SY = m.groups(); X, Y, U, V, SX, SY = map(int, (X, Y, U, V, SX, SY))
        spr = sheets[f][V:V + SY, U:U + SX]
        col = np.array(tint[int(idx) % 5], np.float32) / 255.0
        a = spr[..., 3:4] / 255.0
        comp[Y:Y + SY, X:X + SX, :3] = comp[Y:Y + SY, X:X + SX, :3] * (1 - a) + spr[..., :3] * col * a
    Image.fromarray(comp[40:620, 30:520].astype(np.uint8)).save(os.path.join(BUILD, 'diplo', 'new_tinted.png'))
    Image.fromarray(bg[40:620, 30:520].astype(np.uint8)).save(os.path.join(BUILD, 'diplo', 'new_background.png'))
    print('previews in build/diplo/new_*.png')

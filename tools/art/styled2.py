"""styled2: full-resolution map tiles that match the original Imperial Glory map art (1024 px per tile).

Extends tools/styled.py (geography, warp, patch libraries, old-art keep mask) with measured reproductions of the
original tiles' look.  Everything is measured from build/tiles_png/T00RR0CC.png (the 16 original tiles):

  * base colour  = low-frequency colour field (stains, streaks) synthesised by quilting large patches of the
                   original land / sea low-pass colour (sigma 16 px) - inside the old map area it IS the old art's
                   own low-pass, so the join at the old frame is continuous,
  * fine texture = high-pass patches of the original land (texlib) and sea (sea_texture), contrast matched,
  * province borders = solid brown ink (113,70,57), ~5 px, with the original's dark 'pillow' rim shading inside
                   every province (measured profile: -50 lum at 5 px, decaying over ~40 px), no dashed borders,
  * coasts       = the original's shore profile (2026-10-22, see _coast): water darkening towards the coast under dotted
                   concentric ripple lines (quantile-mapped onto the original's water colours by distance from the
                   shore; measured signed-distance profiles), crisp brown band + dark outline on the land,
  * graticule    = the original's conic grid (apex and spacing fitted to the original lines) continued over the map,
  * mountains    = the original's glyph stamps placed densely where the prototype draws ranges,
  * rivers       = procedural blue-grey branching rivers flowing to the sea (new area only),
  * ships        = four ship drawings cut from the original tiles, in open sea.

Usage (same as styled.py):  from art import styled2; styled2.render_tile(col, row) -> 1024x1024x3 uint8
or  python tools/art/render_all2.py [--force] [--preview]
"""
import os, sys, math, json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import styled, texlib, gen_world as GW
from styled import TS, PX, PAD, CELL, PATCH, _hash, _quilt

ROOT = styled.ROOT
CACHE = os.path.join(ROOT, 'build', 'art', 'cache')
os.makedirs(CACHE, exist_ok=True)
NCOLS, NROWS = 9, 7
FC = 4.0                                  # g px per low-pass field cell
FW, FH = int(NCOLS * 512 / FC), int(NROWS * 512 / FC)
OLD_X1 = 1860.0                           # g px: old art kept to the left of this (styled.py)
OLD_Y1 = GW.OLD_Y1 - 30                   # g px: old art kept above this

# measured ink colours (original tiles, 1024 px per tile)
BORDER = np.array([118.0, 68.0, 54.0])
COAST_INK = np.array([72.0, 52.0, 38.0])             # dark outline on the land side of the shore
COAST_BAND_OLD = np.array([112.0, 72.0, 42.0])       # brown coast band on the land
HATCH = np.array([58.0, 74.0, 84.0])                 # (only the pre-2026-10-22 water step, _coast_old)
RIVER = np.array([92.0, 112.0, 116.0])
SEA_LINE = np.array([63.0, 72.0, 80.0])          # sea-zone border ink (measured core (65,73,81))
GRAT_MUL = 0.64                           # graticule ink is a multiply layer
_c = {}


def _hash2(i, j, k=0):
    """Well-mixed deterministic hash in [0, 1) (styled._hash correlates on small grids)."""
    h = (int(i) * 374761393 + int(j) * 668265263 + int(k) * 2246822519 + 0x9E3779B9) & 0xffffffff
    h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
    h = (h ^ (h >> 16)) & 0x7fffffff
    return h / 0x7fffffff
DEBUG = os.environ.get('STYLED2_DEBUG')


def _stage(name, out):
    if DEBUG:
        print('  stage %-10s mean %s' % (name, np.round(out.mean((0, 1)), 1)), flush=True)


# ----------------------------------------------------------------------------------------------- original tiles
def _comp():
    """The 16 original tiles as one 4096x4096 float image (tile px = global px of cols 0..3, rows 0..3)."""
    if 'comp' not in _c:
        comp = np.zeros((4096, 4096, 3), np.float32)
        for r in range(4):
            for c in range(4):
                comp[(3 - r) * 1024:(4 - r) * 1024, c * 1024:(c + 1) * 1024] = \
                    np.asarray(Image.open(os.path.join(texlib.TILES, 'T00%d00%d.png' % (r, c))).convert('RGB'))
        _c['comp'] = comp
    return _c['comp']


def _masks():
    """Land / sea / ink masks of the original composite."""
    if 'masks' not in _c:
        comp = _comp()
        R, G, B = comp[..., 0], comp[..., 1], comp[..., 2]
        lum = comp.mean(-1)
        sea = B > R + 8
        sea = ndimage.binary_closing(ndimage.binary_opening(sea, iterations=3), iterations=3)
        land = R > B + 10
        red = (R - G > 25) & (R - B > 30)
        dark = lum < ndimage.median_filter(lum, 15) - 22
        lab, nl = ndimage.label(dark); sl = ndimage.find_objects(lab)
        keep = np.zeros(nl + 1, bool)
        for k, s in enumerate(sl, 1):
            if max(s[0].stop - s[0].start, s[1].stop - s[1].start) > 120:
                keep[k] = True                                     # long strokes: graticule, routes, rivers
        inner = np.zeros((4096, 4096), bool); inner[300:3780, 230:3900] = True
        ink = ndimage.binary_dilation(red | keep[lab] | (lum < 70), iterations=4)
        _c['masks'] = (sea, land, ink, inner)
    return _c['masks']


# ------------------------------------------------------------------------------------------ low-frequency fields
def _lowpass_source(mask, sigma=16.0):
    """Normalised-convolution low-pass colour of the original over `mask`, at FC g px per cell, plus its weight."""
    comp = _comp()
    w = ndimage.gaussian_filter(mask.astype(np.float32), sigma)
    lp = np.stack([ndimage.gaussian_filter(comp[..., k] * mask, sigma) for k in range(3)], -1) / np.maximum(w, 1e-3)[..., None]
    # cells with no data nearby: fill from a much wider average (and finally the global mean) so no cell is black
    w4 = ndimage.gaussian_filter(mask.astype(np.float32), sigma * 4)
    lp4 = np.stack([ndimage.gaussian_filter(comp[..., k] * mask, sigma * 4) for k in range(3)], -1) / np.maximum(w4, 1e-3)[..., None]
    mu = comp[mask].mean(0)
    lp4 = np.where((w4 > 0.02)[..., None], lp4, mu)
    t = np.clip(w / 0.25, 0, 1)[..., None]
    lp = lp * t + lp4 * (1 - t)
    s = int(FC * PX)                                             # composite px per cell
    return lp[s // 2::s, s // 2::s], w[s // 2::s, s // 2::s]


def _synth_field(name, mask, P, seed, min_valid=0.97, contrast=1.0, shift=0.0, target=None, smooth=0.0, streak=0.0):
    """Global (FH x FW) low-pass colour field: the old art's own low-pass inside the old area, quilted patches
    of it (P cells square) everywhere else."""
    fn = os.path.join(CACHE, 'lp_%s.npy' % name)
    if os.path.exists(fn):
        return np.load(fn)
    lp, w = _lowpass_source(mask)
    valid = w > 0.35
    h, wd = valid.shape
    frac = ndimage.uniform_filter(valid.astype(np.float32), P, mode='constant')
    cand = np.argwhere(frac > min_valid)                           # patch centres
    cand = cand[(cand[:, 0] >= P // 2) & (cand[:, 0] < h - P // 2) & (cand[:, 1] >= P // 2) & (cand[:, 1] < wd - P // 2)]
    if len(cand) == 0:
        raise RuntimeError('no valid %s patches' % name)
    rng = np.random.default_rng(seed)
    acc = np.zeros((FH, FW, 3), np.float32); wsum = np.zeros((FH, FW), np.float32)
    # the real old art: cells of the old area (g x < OLD_X1, g y < OLD_Y1), feathered over 24 cells, trusted only where valid
    ys, xs = np.mgrid[0:FH, 0:FW]
    gx = (xs + 0.5) * FC; gy = (ys + 0.5) * FC
    feather = np.clip((OLD_X1 + 60 - gx) / 100.0, 0, 1) * np.clip((OLD_Y1 + 60 - gy) / 100.0, 0, 1)
    real = np.zeros((FH, FW, 3), np.float32); rw = np.zeros((FH, FW), np.float32)
    real[:h, :wd] = lp; rw[:h, :wd] = np.clip((w - 0.35) / 0.3, 0, 1)
    rw = rw * feather * 40.0
    acc += real * rw[..., None]; wsum += rw
    win = np.outer(np.hanning(P), np.hanning(P)).astype(np.float32) + 1e-3
    step = P // 2
    for j in range(-step, FH + step, step):
        for i in range(-step, FW + step, step):
            cy, cx = cand[rng.integers(len(cand))]
            src = lp[cy - P // 2:cy + P // 2, cx - P // 2:cx + P // 2]
            if rng.random() < 0.5:
                src = src[:, ::-1]
            if rng.random() < 0.5:
                src = src[::-1]
            y0, x0 = j, i
            sy0, sx0 = max(0, -y0), max(0, -x0); sy1, sx1 = min(P, FH - y0), min(P, FW - x0)
            if sy1 <= sy0 or sx1 <= sx0:
                continue
            acc[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] += src[sy0:sy1, sx0:sx1] * win[sy0:sy1, sx0:sx1, None]
            wsum[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] += win[sy0:sy1, sx0:sx1]
    field = acc / wsum[..., None]
    # blending averages patches and loses contrast: restore the source's low-pass spread outside the old area
    new = feather < 0.01
    mu_s = lp[valid].mean(0); sd_s = lp[valid].std(0)
    mu_f = field[new].mean(0); sd_f = field[new].std(0)
    if smooth > 0:
        field = ndimage.gaussian_filter(field, (smooth, smooth, 0))      # larger, softer stain scale
    mu_f = field[new].mean(0); sd_f = field[new].std(0)
    mu_t = mu_s + shift if target is None else np.asarray(target, np.float64)
    field_adj = (field - mu_f) * (sd_s / np.maximum(sd_f, 1e-3)) * contrast + mu_t
    field_adj = np.clip(field_adj, mu_t - 2.0 * sd_s * contrast, mu_t + 2.0 * sd_s * contrast)
    if streak > 0:                                                       # worn parchment: horizontal scratches / fibres
        rs = np.random.default_rng(seed + 100)
        st = ndimage.gaussian_filter(rs.random((FH, FW)), (1.2, 18.0))
        st = (st - st.mean()) / (st.std() + 1e-6)
        st2 = ndimage.gaussian_filter(rs.random((FH, FW)), (3.0, 60.0))
        st2 = (st2 - st2.mean()) / (st2.std() + 1e-6)
        field_adj = field_adj + (0.6 * st + 0.4 * st2)[..., None] * streak * np.array([1.0, 1.0, 1.1])
    field = field_adj * (1 - feather[..., None]) + field * feather[..., None]
    field = field.astype(np.float32)
    np.save(fn, field)
    return field


def _fields():
    if 'fields' not in _c:
        sea, land, ink, inner = _masks()
        R = _comp()[..., 0]; G = _comp()[..., 1]; B = _comp()[..., 2]
        red = ndimage.binary_dilation((R - G > 25) & (R - B > 30), iterations=18)   # borders and their rim shading
        lm = ndimage.binary_erosion(land, iterations=26) & ~ink & ~red & inner
        sm = ndimage.binary_erosion(sea, iterations=8) & ~ink & inner
        _c['fields'] = (_synth_field('land', lm, 64, 11, 0.85, 0.50, target=(176.0, 166.0, 146.0), smooth=2.5, streak=5.0),
                        _synth_field('sea', sm, 40, 12, 0.75, 0.32, target=(112.0, 137.0, 148.0), smooth=3.5, streak=1.5))
    return _c['fields']


# ------------------------------------------------------------------------------------------------------ graticule
GRAT_APEX = (1023.2, -1916.7)             # g px, fitted to the original's meridians
GRAT_TH0, GRAT_DTH = 0.2, 2.77            # meridian angles (deg from straight down, + to the right)
GRAT_R0, GRAT_DR = 2320.5, 351.5          # parallel radii in g px


def _graticule(gx, gy):
    """Alpha (0..1) of the original's conic grid lines at g coordinates gx, gy (arrays)."""
    dx = gx - GRAT_APEX[0]; dy = gy - GRAT_APEX[1]
    r = np.hypot(dx, dy)
    th = np.degrees(np.arctan2(dx, dy))
    dth = (th - GRAT_TH0 + GRAT_DTH / 2) % GRAT_DTH - GRAT_DTH / 2
    dmer = np.abs(np.radians(dth)) * r                             # g px to the nearest meridian
    dpar = np.abs((r - GRAT_R0 + GRAT_DR / 2) % GRAT_DR - GRAT_DR / 2)
    d = np.minimum(dmer, dpar) * PX                                  # tile px
    a = np.clip(1.6 - d / 1.6, 0, 1)                                 # ~3 px line, soft edge
    # uneven hand-drawn ink: modulate along the line
    n = _c.setdefault('gnoise', ndimage.gaussian_filter(np.random.default_rng(3).random((256, 256)), 3))
    n = (n - n.min()) / (n.max() - n.min())
    mod = 0.55 + 0.45 * styled._wrap_sample(n, gx / 3.0, gy / 3.0)
    return a * mod


# ------------------------------------------------------------------------------------------------- mountain ranges
# (lon, lat) polylines of real ranges, half-width in degrees, strength
RANGES = [
    ([(73, 36), (78, 34), (84, 28.5), (90, 28), (96, 29)], 1.5, 1.0),         # Himalaya
    ([(64, 35), (70, 36), (73, 36.5)], 1.2, 1.0),                              # Hindu Kush
    ([(72, 38.5), (76, 36)], 1.2, 1.0),                                        # Pamir / Karakoram
    ([(80, 32), (90, 33), (98, 32)], 2.0, 0.55),                               # Tibet
    ([(78, 36), (90, 36), (98, 36)], 1.0, 0.8),                                # Kunlun
    ([(70, 42), (80, 42.5), (88, 43)], 1.2, 0.9),                              # Tian Shan
    ([(85, 50), (90, 48), (96, 47), (100, 50)], 1.2, 0.9),                     # Altai
    ([(90, 52), (100, 53)], 1.0, 0.7),                                         # Sayan
    ([(44, 37), (48, 34), (52, 30), (56, 28)], 1.2, 0.9),                      # Zagros
    ([(49, 37), (54, 36.5)], 0.8, 0.8),                                        # Elburz
    ([(58, 66), (59, 60), (58, 55), (57, 51)], 0.9, 0.8),                      # Urals
    ([(37, 13), (38, 10), (39, 7)], 1.5, 0.9),                                 # Ethiopian highlands
    ([(-8, 31), (-4, 33), (2, 35), (8, 36)], 1.0, 0.8),                        # Atlas
    ([(27, -31), (29, -29), (30, -27)], 1.0, 0.8),                             # Drakensberg
    ([(146, -38), (149, -33), (152, -28), (147, -20), (145, -17)], 1.2, 0.85), # Great Dividing Range
    ([(137, 36), (139, 37), (140, 39), (141, 41)], 0.8, 0.8),                  # Japanese Alps
    ([(104, 20), (106, 17), (108, 14), (108, 12)], 0.8, 0.7),                  # Annamite
    ([(73, 20), (74, 15), (76, 11)], 0.6, 0.55),                               # Western Ghats
    ([(85, 20), (82, 17), (79, 14)], 0.6, 0.45),                               # Eastern Ghats
    ([(128, 66), (132, 62), (135, 58)], 1.2, 0.6),                             # Verkhoyansk
    ([(110, 55), (120, 56), (130, 56)], 1.0, 0.6),                             # Stanovoy / Yablonoi
    ([(135, 44), (138, 48)], 0.8, 0.6),                                        # Sikhote-Alin
    ([(158, 53), (160, 57)], 0.8, 0.6),                                        # Kamchatka
    ([(40, 20), (42, 16), (44, 13)], 0.8, 0.6),                                # Hejaz / Yemen
    ([(6, 23)], 1.2, 0.5), ([(18, 21)], 1.0, 0.5),                             # Hoggar, Tibesti
    ([(36, 0), (36, -5), (34, -8)], 0.8, 0.5),                                 # East African rift
    ([(10, 6)], 1.0, 0.4),                                                     # Cameroon highlands
    ([(115, 1)], 1.2, 0.5),                                                    # Borneo
    ([(97, 4), (101, -1), (104, -4)], 0.6, 0.6),                               # Barisan (Sumatra)
    ([(137, -4), (141, -5), (145, -6)], 0.8, 0.7),                             # New Guinea
    ([(121, 17)], 0.6, 0.5),                                                   # Luzon Cordillera
    ([(106, 34), (110, 34)], 0.8, 0.6),                                        # Qinling
    ([(99, 27), (101, 30), (102, 33)], 1.0, 0.8),                              # Hengduan
    ([(110, 25), (114, 25)], 0.8, 0.4),                                        # Nan Ling
    ([(47, -19), (47, -22)], 0.8, 0.5),                                        # Madagascar
    ([(168, -45), (171, -43)], 0.6, 0.7),                                      # Southern Alps
]


def _range_density(lon, lat, step=8):
    """Mountain-range strength (0..1) per pixel from RANGES, computed on a coarse grid and upsampled."""
    lo = lon[::step, ::step]; la = lat[::step, ::step]
    out = np.zeros_like(lo)
    cl = np.cos(np.radians(np.clip(la, -80, 80)))
    for pts, w, amp in RANGES:
        d2 = np.full_like(lo, 1e9)
        for k in range(len(pts)):
            a = np.array(pts[k], float); b = np.array(pts[min(k + 1, len(pts) - 1)], float)
            ab = b - a; L2 = ab @ ab
            t = 0.0 if L2 < 1e-9 else np.clip(((lo - a[0]) * ab[0] + (la - a[1]) * ab[1]) / L2, 0, 1)
            dx = (lo - (a[0] + t * ab[0])) * cl; dy = la - (a[1] + t * ab[1])
            d2 = np.minimum(d2, dx * dx + dy * dy)
        out = np.maximum(out, amp * np.exp(-d2 / (w * w)))
    full = ndimage.zoom(out, step, order=1)
    full = full[:lon.shape[0], :lon.shape[1]]
    if full.shape != lon.shape:
        full = np.pad(full, ((0, lon.shape[0] - full.shape[0]), (0, lon.shape[1] - full.shape[1])), mode='edge')
    return np.clip(full, 0, 1)


# ------------------------------------------------------------------------------------------------------- rivers
def _coarse_land(step=8.0):
    """Land mask of the whole map on a step-g-px grid (no coast wobble), with g coordinates."""
    game, land, mount, noise, stain = styled._maps()
    f = _c.setdefault('warp', styled._cache['warp'])
    W, H = int(NCOLS * 512 / step), int(NROWS * 512 / step)
    ys, xs = np.mgrid[0:H, 0:W]
    gx = (xs + 0.5) * step; gy = (ys + 0.5) * step
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    q = np.empty_like(pts); ll = np.empty_like(pts)
    for i in range(0, len(pts), 150000):
        q[i:i + 150000], ll[i:i + 150000] = f(pts[i:i + 150000])
    lon = ll[:, 0].reshape(H, W); lat = ll[:, 1].reshape(H, W)
    L = GW.sample(land, (lon - GW.LON0) / GW.RES, (GW.LAT1 - lat) / GW.RES)
    L[(lon > 189.5) | (lon < GW.LON0 + 0.5) | (lat < -55)] = 0
    return L > 0.5, gx, gy


def _rivers():
    """Procedural rivers for the new area: list of polylines in g px.  Cached."""
    fn = os.path.join(CACHE, 'rivers.json')
    if os.path.exists(fn):
        return json.load(open(fn))
    step = 8.0
    land, gx, gy = _coarse_land(step)
    H, W = land.shape
    old = (gx < OLD_X1 + 40) & (gy < OLD_Y1 + 40)
    dist = ndimage.distance_transform_edt(land)                    # cells to sea
    rng = np.random.default_rng(21)
    noise = ndimage.gaussian_filter(rng.random((H, W)), 2.5); noise = (noise - noise.min()) / (noise.max() - noise.min())
    pot = ndimage.gaussian_filter(dist, 1.5) + noise * 6.0          # descend this to the sea
    occupied = np.zeros((H, W), bool)
    rivers = []

    def trace(y, x, maxlen=400):
        path = [(y, x)]
        for _ in range(maxlen):
            best = None; bv = pot[y, x] - 1e-6
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and pot[yy, xx] < bv:
                        bv = pot[yy, xx]; best = (yy, xx)
            if best is None:
                return path, False
            y, x = best
            path.append((y, x))
            if not land[y, x] or old[y, x]:
                return path, True
            if occupied[y, x]:
                return path, True
        return path, False

    # sources: inland, outside the old area, spread out
    cand = np.argwhere(land & ~old & (dist > 14))
    rng.shuffle(cand)
    taken = np.zeros((H, W), bool)
    for (y, x) in cand:
        if taken[max(0, y - 22):y + 22, max(0, x - 22):x + 22].any():
            continue
        path, ok = trace(y, x)
        if not ok or len(path) < 18:
            continue
        taken[y, x] = True
        for (py, px_) in path:
            occupied[py, px_] = True
        rivers.append([(float((px_ + 0.5) * step), float((py + 0.5) * step)) for (py, px_) in path])
    # tributaries: shorter, must join a river or the sea
    cand = np.argwhere(land & ~old & (dist > 6))
    rng.shuffle(cand)
    ntrib = 0
    occ_d = ndimage.distance_transform_edt(~occupied)
    for (y, x) in cand[:6000]:
        if occupied[y, x] or occ_d[y, x] < 6 or occ_d[y, x] > 40:
            continue
        if taken[max(0, y - 12):y + 12, max(0, x - 12):x + 12].any():
            continue
        path, ok = trace(y, x, 120)
        if not ok or len(path) < 8 or not occupied[path[-1]]:
            continue
        taken[y, x] = True
        for (py, px_) in path:
            occupied[py, px_] = True
        rivers.append([(float((px_ + 0.5) * step), float((py + 0.5) * step)) for (py, px_) in path])
        ntrib += 1
        if ntrib > 3 * len(rivers):
            break
    # smooth the polylines
    out = []
    for r in rivers:
        a = np.array(r)
        if len(a) > 4:
            a = np.stack([ndimage.gaussian_filter1d(a[:, 0], 1.2, mode='nearest'), ndimage.gaussian_filter1d(a[:, 1], 1.2, mode='nearest')], 1)
        out.append(a.tolist())
    json.dump(out, open(fn, 'w'))
    return out


def _draw_rivers(X0, Y0, n, hard):
    """River ink alpha for the padded window (tile px)."""
    im = Image.new('L', (n, n), 0); dr = ImageDraw.Draw(im)
    rng = np.random.default_rng(X0 * 7 + Y0 * 13 + 1)
    for r in _rivers():
        a = np.array(r) * PX - np.array([X0, Y0])
        if a[:, 0].max() < -10 or a[:, 0].min() > n + 10 or a[:, 1].max() < -10 or a[:, 1].min() > n + 10:
            continue
        # taper: thin near the source, 2-3 px near the mouth; small wobble
        k = len(a)
        for i in range(1, k):
            w = 2 if i < k * 0.4 else 3
            dr.line([tuple(a[i - 1]), tuple(a[i])], fill=255, width=w)
    al = ndimage.gaussian_filter(np.asarray(im, np.float32) / 255, 0.7)
    return np.clip(al * 1.2, 0, 1) * hard


# --------------------------------------------------------------------------------------------------------- ships
SHIPS = [((1211, 1184), 100), ((1771, 1237), 90), ((2240, 2320), 92), ((2140, 3200), 96)]   # composite centre, half-size


def _ships():
    if 'ships' not in _c:
        comp = _comp(); out = []
        for (x, y), hs in SHIPS:
            p = comp[y - hs:y + hs, x - hs:x + hs]
            lum = p.mean(-1)
            bg = np.median(np.concatenate([lum[:8].ravel(), lum[-8:].ravel(), lum[:, :8].ravel(), lum[:, -8:].ravel()]))
            a = np.clip((bg - lum - 8) / 30.0, 0, 1)
            lab, nl = ndimage.label(ndimage.binary_dilation(a > 0.15, iterations=3))
            if nl:
                sizes = ndimage.sum(np.ones_like(a), lab, range(1, nl + 1))
                cen = lab[hs - 20:hs + 20, hs - 20:hs + 20]
                keep = [k for k in np.unique(cen) if k > 0] or [int(np.argmax(sizes)) + 1]
                a = a * np.isin(lab, keep)
            a = ndimage.gaussian_filter(a, 0.6)
            yy, xx = np.mgrid[0:2 * hs, 0:2 * hs]
            a *= np.clip((hs - 6 - np.hypot(yy - hs, xx - hs)) / 10.0, 0, 1)
            out.append((p.astype(np.float32), a.astype(np.float32)))
        _c['ships'] = out
    return _c['ships']


def _stamp_ships(out, ds, hard, X0, Y0, n):
    ships = _ships()
    G = 720
    for j in range((Y0 - 220) // G, (Y0 + n) // G + 1):
        for i in range((X0 - 220) // G, (X0 + n) // G + 1):
            if _hash2(i, j, 21) > 0.5:
                continue
            cx = i * G + int(_hash2(i, j, 22) * (G - 200)) + 100 - X0; cy = j * G + int(_hash2(i, j, 23) * (G - 200)) + 100 - Y0
            if cx < -200 or cy < -200 or cx > n + 200 or cy > n + 200:
                continue
            gcx, gcy = (cx + X0) / PX, (cy + Y0) / PX
            if gcx < OLD_X1 + 120 and gcy < OLD_Y1 + 120:
                continue                                           # the old art has its own ships
            img, a = ships[int(_hash2(i, j, 24) * len(ships))]
            hs = a.shape[0] // 2
            x0, y0 = cx - hs, cy - hs
            sx0, sy0 = max(0, -x0), max(0, -y0); sx1, sy1 = min(2 * hs, n - x0), min(2 * hs, n - y0)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            ccx, ccy = int(np.clip(cx, 0, n - 1)), int(np.clip(cy, 0, n - 1))
            if hard[ccy, ccx] or ds[ccy, ccx] < hs + 30:
                continue
            reg = out[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1]
            aa = a[sy0:sy1, sx0:sx1, None]
            # the drawing is ink on sea: multiply the sea by the sprite's darkness so sea texture shows through
            spr = img[sy0:sy1, sx0:sx1]
            bgc = np.median(spr.reshape(-1, 3), 0)
            ink = reg * np.clip(spr / np.maximum(bgc, 1), 0, 1.2)
            out[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = reg * (1 - aa) + ink * aa
    return out


# ------------------------------------------------------------------------------------------------------ borders
def _border_mask(hard, X0, Y0, n):
    """Solid province border ink mask (0..1) for the window; coast edges are left to the coast treatment."""
    core = Image.new('L', (n, n), 0); dc = ImageDraw.Draw(core)

    def land(x, y):
        xi, yi = int(x), int(y)
        return 0 <= xi < n and 0 <= yi < n and hard[yi, xi]
    for (ax, ay), (bx, by), same, nsides in styled._edges():
        ax -= X0; ay -= Y0; bx -= X0; by -= Y0
        if max(ax, bx) < -8 or min(ax, bx) > n + 8 or max(ay, by) < -8 or min(ay, by) > n + 8:
            continue
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        nx, ny = -(by - ay) / L * 9, (bx - ax) / L * 9
        ok = True
        for f in (0.2, 0.5, 0.8):
            mx, my = ax + (bx - ax) * f, ay + (by - ay) * f
            if not (land(mx + nx, my + ny) and land(mx - nx, my - ny)):
                ok = False; break
        if not ok:
            continue
        dc.line([(ax, ay), (bx, by)], fill=255, width=6)
    c = ndimage.gaussian_filter(np.asarray(core, np.float32) / 255, 0.9)
    return np.clip(c * 1.15, 0, 1)


def _rim(d):
    """Province 'pillow' darkening (fraction of the base colour) at d px from the nearest border / coast on land."""
    return 0.31 * np.exp(-np.maximum(d - 4, 0) / 12.0) + 0.08 * np.exp(-np.maximum(d - 4, 0) / 40.0)


# --------------------------------------------------------------------------------------------------- sea zones
def _sea_edges():
    """Edges shared by exactly two sea zones (build/sea/sea_zones.json), in global tile px."""
    if 'sea_edges' in _c:
        return _c['sea_edges']
    import meshgen as MG
    fn = os.path.join(ROOT, 'build', 'sea', 'sea_zones.json')
    out = []
    if os.path.exists(fn):
        data = json.load(open(fn, encoding='utf8'))
        edges = {}
        for k, w in data.items():
            poly = w['poly']
            for i in range(len(poly)):
                a = tuple(round(v, 1) for v in poly[i - 1]); b = tuple(round(v, 1) for v in poly[i])
                key = (a, b) if a < b else (b, a)
                edges[key] = edges.get(key, 0) + 1

        def gp(x, z):
            return ((x - MG.COLS[0]) / MG.TILE_W * 512.0 * PX, (MG.ROWS[4] - z) / MG.TILE_H * 512.0 * PX)
        for (a, b), cnt in edges.items():
            if cnt == 2:                                           # outer map edges and single-sided edges are skipped
                out.append((gp(*a), gp(*b)))
    _c['sea_edges'] = out
    return out


def _sea_border_mask(hard, ds, X0, Y0, n, gx, gy, noise):
    """Soft dark sea-zone border ink (0..1) for the window: open-sea parts of shared zone edges only."""
    im = Image.new('L', (n, n), 0); dr = ImageDraw.Draw(im)

    def near_land(x, y):
        xi, yi = int(x), int(y)
        if not (0 <= xi < n and 0 <= yi < n):
            return False
        return hard[yi, xi] or ds[yi, xi] < 14
    for (ax, ay), (bx, by) in _sea_edges():
        ax -= X0; ay -= Y0; bx -= X0; by -= Y0
        if max(ax, bx) < -8 or min(ax, bx) > n + 8 or max(ay, by) < -8 or min(ay, by) > n + 8:
            continue
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        k = max(2, int(L / 24))
        fs = np.linspace(0, 1, k + 1)
        xs = ax + (bx - ax) * fs; ys = ay + (by - ay) * fs
        inside = [(0 <= x < n and 0 <= y < n) for x, y in zip(xs, ys)]
        if sum(inside) and sum(near_land(x, y) for x, y, i in zip(xs, ys, inside) if i) > 0.5 * sum(inside):
            continue                                               # the edge runs along a coast
        # gentle hand-drawn wobble, perpendicular to the edge, continuous across tiles (global noise)
        nx, ny = -(by - ay) / L, (bx - ax) / L
        wob = (styled._wrap_sample(noise, (xs + X0) / PX * 0.35 + 900, (ys + Y0) / PX * 0.35 + 700) - 0.5) * 7.0
        pts = [(float(x + nx * w), float(y + ny * w)) for x, y, w in zip(xs, ys, wob)]
        dr.line(pts, fill=255, width=5, joint='curve')
    a = ndimage.gaussian_filter(np.asarray(im, np.float32) / 255, 1.6)
    return np.clip(a * 1.1, 0, 1) * (~hard) * np.clip((ds - 5.0) / 4.0, 0, 1)


# ------------------------------------------------------------------------------------------------------- coast
def _coast_old(out, hard, ds, dl, gx, gy, noise, n):
    """The coast step before 2026-10-22 (kept as the 'before' reference of the shore-halo fix; not used by render_tile)."""
    band = np.clip((dl - 1.5) / 2.0, 0, 1) * np.clip((16.0 - dl) / 5.0, 0, 1) * hard
    out = out * (1 - 0.62 * band[..., None]) + COAST_BAND_OLD * (0.62 * band)[..., None]
    near = np.exp(-ds / 20.0) * (~hard)
    out = out + np.array([20.0, 15.0, 6.0]) * near[..., None]
    wobble = (styled._wrap_sample(noise, gx * 5.0 + 300, gy * 5.0) - 0.5) * 2.2
    dsw = ds + wobble
    hatch = np.zeros((n, n), np.float32)
    for k in range(11):
        hatch += np.exp(-((dsw - (5.0 + 3.6 * k)) / 0.8) ** 2) * (0.6 * math.exp(-k / 8.0))
    hatch = np.clip(hatch, 0, 1) * (~hard)
    out = out * (1 - hatch[..., None]) + HATCH * hatch[..., None]
    ink = np.clip(1.8 - np.where(hard, dl, ds), 0, 1) * 0.8
    return out * (1 - ink[..., None]) + COAST_INK * ink[..., None]


# Shore treatment measured from the original tiles (2026-10-22, "pale shore halo" fix).  The old step (_coast_old)
# BRIGHTENED the water next to the coast (+20/+15/+6 within ~20 px) and started its hatching only 5 px out, which left a
# light shore line (lum ~136 at 1..3 px against ~132 open sea, where the 2005 art is ~110: +25..+35 too light).  The
# original does the opposite: the water DARKENS towards the coast (median -30 lum at 1 px, open-sea level again at
# ~14 px, colour turning grey: R -19 G -29 B -39) under dotted concentric ripple lines (a line every ~2.3 px that start
# at the shore and fade out by ~15 px).
#   water: per-pixel quantile mapping.  Each water pixel gets a rank r (from its own brightness, a fine speckle and the
#          dotted-ring pattern; the rings are the darkest ranks) and takes the colour the ORIGINAL's water has at that
#          rank and distance (table _coast_tables: 41 quantiles per colour channel for every pixel distance, measured
#          on the Britain / Scandinavia / Mediterranean windows of the 16 original tiles), so the brightness and colour
#          distribution at every distance from the coast is the original's (light tail scaled by COAST['kpos'] because
#          the new sea's grain is calmer than the original's).  Fades out between COAST['B0'] and ['B1'] px.
#   land:  unchanged: the crisp brown band + dark outline.  (A profile-matched soft band was tried and dropped: it
#          matched the original's MEAN land profile but lost the crisp band edge the original draws; the new land is
#          lighter than the original only beyond the band, where it is plain parchment.)
COAST = dict(P=2.4, w=0.7, start=1.2, pha=0.6, phs=10.0, pha2=0.25, dsig=0.9, dth=0.9, spsig=0.6, A=4.0,
             LL=16.0, LS=7.0, lam=0.95, kpos=0.7, B0=9.0, B1=19.0)
COAST_BOXES = [(760, 1560, 720, 1320), (240, 1320, 1320, 2080), (2160, 3440, 520, 2560)]   # y0, y1, x0, x1 of the 4096 composite
COAST_DMAX, NQ = 26, 41
NEW_SEA_MED = np.array([112.6, 136.4, 147.4])        # the new sea's open-water median colour (measured on styled2 tiles)
NEW_SEA_LUM_Q = [102.4, 108.8, 112.1, 114.4, 116.2, 117.8, 119.2, 120.4, 121.6, 122.6, 123.7, 124.6, 125.5, 126.4,
                 127.2, 128.1, 128.9, 129.7, 130.5, 131.3, 132.1, 132.9, 133.7, 134.5, 135.4, 136.2, 137.1, 138.0,
                 138.9, 139.8, 140.8, 141.8, 142.9, 144.1, 145.4, 146.9, 148.6, 150.6, 153.0, 156.5, 163.3]   # its 41 brightness quantiles
_QS = (np.arange(NQ) + 0.5) / NQ


def _coast_tables():
    """(tab[d, q, channel], far[q, channel]): the original water's colour quantiles at distance d (1..COAST_DMAX px
    from land, bins d +- 0.5) and in open water (36..48 px).  Cached in build/art/cache/coast_q1.npz."""
    if 'coastq' in _c:
        return _c['coastq']
    fn = os.path.join(CACHE, 'coast_q1.npz')
    if os.path.exists(fn):
        z = np.load(fn)
        _c['coastq'] = (z['tab'], z['far'])
        return _c['coastq']
    comp = _comp()
    b = ndimage.gaussian_filter(comp, (1.0, 1.0, 0))
    sea = (b[..., 2] - b[..., 0]) > 6
    sea = ndimage.binary_opening(sea, structure=ndimage.generate_binary_structure(2, 1), iterations=4)   # no rivers / lines
    lab, nl = ndimage.label(sea)
    sizes = ndimage.sum(sea, lab, range(1, nl + 1))
    keep = np.zeros(nl + 1, bool); keep[1:] = sizes >= 3000
    sea = keep[lab]
    ds = ndimage.distance_transform_edt(sea)
    reg = np.zeros(sea.shape, bool)
    for (y0, y1, x0, x1) in COAST_BOXES:
        reg[y0:y1, x0:x1] = True
    reg &= sea
    tab = np.zeros((COAST_DMAX + 1, NQ, 3), np.float32)
    for d in range(1, COAST_DMAX + 1):
        m = reg & (ds > d - 0.5) & (ds <= d + 0.5)
        for k in range(3):
            tab[d, :, k] = np.quantile(comp[..., k][m], _QS)
    tab[0] = tab[1]
    tab = ndimage.gaussian_filter1d(tab, 0.6, axis=0, mode='nearest').astype(np.float32)
    m = reg & (ds > 36) & (ds <= 48)
    far = np.stack([np.quantile(comp[..., k][m], _QS) for k in range(3)], -1).astype(np.float32)
    np.savez(fn, tab=tab, far=far)
    _c['coastq'] = (tab, far)
    return _c['coastq']


def _coast_rank_lut():
    """lut[d, 0..100]: quantiles of the coast step's rank score t at distance d (so r = F_d(t) is uniform at every
    distance, whatever tile is rendered)."""
    if 'coastr' in _c:
        return _c['coastr']
    k = COAST
    rng = np.random.default_rng(5)
    N = 200000
    z0 = rng.standard_normal(N); sp = rng.standard_normal(N)
    line = np.exp(-(((rng.random(N) - 0.5) * k['P']) / k['w']) ** 2)
    dm = np.clip((rng.standard_normal(N) + k['dth']) / 0.55, 0, 1)
    qf = np.linspace(0, 1, 101)
    lut = np.zeros((COAST_DMAX + 1, 101), np.float32)
    for d in range(COAST_DMAX + 1):
        wl = np.clip((k['LL'] - d) / k['LS'], 0, 1) * np.clip((d - 0.3) / 0.7, 0, 1)
        t = math.sqrt(1 - k['lam'] ** 2) * z0 + k['lam'] * (sp - k['A'] * line * dm * wl)
        lut[d] = np.quantile(t, qf)
    _c['coastr'] = (lut, qf)
    return _c['coastr']


def _coast_noise(name):
    """Wrap noise textures (1024 x 1024, unit variance, padded by one wrapped row/column) for the coast step."""
    if 'cn_' + name not in _c:
        k = COAST
        sigma, seed = {'ph': (k['phs'], 11), 'ph2': (k['phs'] * 0.4, 12), 'sp': (k['spsig'], 13), 'dm': (k['dsig'], 14)}[name]
        t = ndimage.gaussian_filter(np.random.default_rng(seed).standard_normal((1024, 1024)).astype(np.float32), sigma, mode='wrap')
        t /= t.std()
        _c['cn_' + name] = np.pad(t, ((0, 1), (0, 1)), mode='wrap')
    return _c['cn_' + name]


def _coast_samp(name, x, y):
    return ndimage.map_coordinates(_coast_noise(name), [y % 1024, x % 1024], order=1)


def _smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _coast(out, hard, ds, dl, X, Y, rim_done=True):
    """Shore treatment (see the comment above).  out (n, n, 3) float, hard = land mask, ds = px from land in the water,
    dl = px from the water on land, X, Y = global full-resolution px coordinates of the window (arrays).  rim_done:
    the land already carries the 'pillow' darkening (render_tile); deframe's filled areas have not."""
    out = _coast_water(out, hard, ds, X, Y)
    return _coast_land(out, hard, dl, rim_done)


def _coast_water(out, hard, ds, X, Y):
    """The water half of _coast (also used by tools/art/oldarea/northfix.py)."""
    from scipy.special import ndtri
    k = COAST
    tab, far = _coast_tables()
    lut, qf = _coast_rank_lut()
    # --- water: quantile mapping onto the original's colours at this distance from the shore
    yi, xi = np.nonzero((~hard) & (ds < k['B1']))
    if len(yi):
        d = ds[yi, xi].astype(np.float32)
        x = X[yi, xi]; y = Y[yi, xi]
        px = out[yi, xi]
        z0 = ndtri(np.clip(np.interp(px.mean(-1), NEW_SEA_LUM_Q, _QS, left=_QS[0] * 0.5, right=1 - (1 - _QS[-1]) * 0.5), 1e-4, 1 - 1e-4))
        ph = _coast_samp('ph', x + 5, y + 9) * k['pha'] + _coast_samp('ph2', x + 55, y + 19) * k['pha2']
        u = (d + ph - k['start']) / k['P']
        line = np.exp(-(((u - np.round(u)) * k['P']) / k['w']) ** 2)
        dm = np.clip((_coast_samp('dm', x + 7, y + 81) + k['dth']) / 0.55, 0, 1)
        wl = np.clip((k['LL'] - d) / k['LS'], 0, 1) * np.clip((d - 0.3) / 0.7, 0, 1)
        s = _coast_samp('sp', x + 77, y + 21) - k['A'] * line * dm * wl
        t = math.sqrt(1 - k['lam'] ** 2) * z0 + k['lam'] * s
        di = np.clip(np.round(d).astype(int), 0, COAST_DMAX)
        r = np.empty_like(t)
        for dv in np.unique(di):
            m = di == dv
            r[m] = np.interp(t[m], lut[dv], qf)
        dd = np.clip(d, 0, COAST_DMAX - 0.001)
        qi = np.clip(r * NQ - 0.5, 0, NQ - 1.001)
        mapped = np.stack([ndimage.map_coordinates(tab[..., c], [dd, qi], order=1) for c in range(3)], -1)
        delta = mapped - far[NQ // 2]
        mapped = NEW_SEA_MED + np.where(delta > 0, delta * k['kpos'], delta)
        beta = _smoothstep((k['B1'] - d) / (k['B1'] - k['B0']))[:, None]
        out = out.copy()
        out[yi, xi] = px * (1 - beta) + mapped * beta
    return out


def _coast_land(out, hard, dl, rim_done=True):
    """The land half of _coast: the new art's established crisp brown coast band (unchanged since 2026-10-16) and a
    dark outline on the land side of the shore only (the water side is the original's own soft edge now)."""
    if not rim_done:
        rim = _rim(dl) * hard
        out = out * (1 - rim[..., None] * np.array([1.0, 1.1, 1.25]))
    band = np.clip((dl - 1.5) / 2.0, 0, 1) * np.clip((16.0 - dl) / 5.0, 0, 1) * hard
    out = out * (1 - 0.62 * band[..., None]) + COAST_BAND_OLD * (0.62 * band)[..., None]
    ink = np.clip(1.8 - dl, 0, 1) * 0.8 * hard
    return out * (1 - ink[..., None]) + COAST_INK * ink[..., None]


# ------------------------------------------------------------------------------------------------------- render
def render_tile(col, row):
    """col 0..8, row 0..6 from the top. Returns a 1024x1024x3 uint8 array."""
    game, land, mount, noise, stain = styled._maps()
    sea_lib, plain_lib, mount_lib = styled._lib()
    f = styled._cache['warp']
    lp_land, lp_sea = _fields()
    n = TS + 2 * PAD
    X0 = col * TS - PAD; Y0 = row * TS - PAD
    ys, xs = np.mgrid[0:n, 0:n]
    gx = (X0 + xs + 0.5) / PX; gy = (Y0 + ys + 0.5) / PX
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    q = np.empty_like(pts); ll = np.empty_like(pts)
    for i in range(0, len(pts), 150000):
        q[i:i + 150000], ll[i:i + 150000] = f(pts[i:i + 150000])
    px = q[:, 0].reshape(n, n); py = q[:, 1].reshape(n, n)
    lon = ll[:, 0].reshape(n, n); lat = ll[:, 1].reshape(n, n)
    L = GW.sample(land, (lon - GW.LON0) / GW.RES, (GW.LAT1 - lat) / GW.RES)
    L[(lon > 189.5) | (lon < GW.LON0 + 0.5) | (lat < -55)] = 0
    wob = styled._wrap_sample(noise, gx * 3.0, gy * 3.0) - 0.5
    hard = (L + wob * 0.22) > 0.5
    ds = ndimage.distance_transform_edt(~hard)                     # px from land, in the sea
    dl = ndimage.distance_transform_edt(hard)                      # px from sea, on land
    # --- base: the original's low-frequency colour fields
    fx = gx / FC - 0.5; fy = gy / FC - 0.5
    base = np.where(hard[..., None], GW.sample(lp_land, fx, fy), GW.sample(lp_sea, fx, fy))
    # --- fine texture: the original's high-pass, contrast matched (orig plain land 12, sea 13)
    det_land = _quilt(X0, Y0, n, n, plain_lib, lambda i, j: int(_hash(i, j, 3) * len(plain_lib))) * 1.3
    if 'sea' not in styled._cache:
        styled._cache['sea'] = np.load(os.path.join(ROOT, 'build', 'sea_detail.npy'))
    sd_tex = styled._cache['sea']; S = sd_tex.shape[0]
    yy = (Y0 + np.arange(n)) % S; xx = (X0 + np.arange(n)) % S
    det_sea = sd_tex[np.ix_(yy, xx)] * 1.3
    out = base + np.where(hard[..., None], det_land, det_sea)
    _stage('base+hp', out)
    # --- mountain glyphs (the original's drawings), dense chains where the prototype draws ranges
    inproto = (px >= 40) & (py >= 40) & (px <= 1960) & (py <= 1285)
    m = np.where(inproto, GW.sample(mount, px, py), 0.0)
    stamps = styled._cache['stamps']
    clump = styled._wrap_sample(noise, gx * 0.15 + 500, gy * 0.15 + 300)      # ranges come in chains / clusters
    rd = _range_density(lon, lat)                                               # real ranges (RANGES) dominate
    m = (m * 0.6 * (1 - rd) + rd * 1.1) * np.clip((clump - 0.3) * 2.6, 0, 1.3)
    G = 44
    for j in range((Y0 - PATCH) // G, (Y0 + n) // G + 1):
        for i in range((X0 - PATCH) // G, (X0 + n) // G + 1):
            cx = i * G + int(_hash(i, j, 5) * G) - X0; cy = j * G + int(_hash(i, j, 6) * G) - Y0
            ccx, ccy = int(np.clip(cx + PATCH // 2, 0, n - 1)), int(np.clip(cy + PATCH // 2, 0, n - 1))
            if not hard[ccy, ccx] or dl[ccy, ccx] < 26 or _hash(i, j, 7) > (m[ccy, ccx] - 0.27) * 0.85:
                continue
            col_, a_ = stamps[int(_hash(i, j, 8) * len(stamps))]
            sx0, sy0 = max(0, -cx), max(0, -cy); sx1, sy1 = min(PATCH, n - cx), min(PATCH, n - cy)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            reg = out[cy + sy0:cy + sy1, cx + sx0:cx + sx1]
            aa = a_[sy0:sy1, sx0:sx1, None] * hard[cy + sy0:cy + sy1, cx + sx0:cx + sx1, None]
            ink = np.minimum(col_[sy0:sy1, sx0:sx1], reg)
            out[cy + sy0:cy + sy1, cx + sx0:cx + sx1] = reg * (1 - aa) + ink * aa
    _stage('mountains', out)
    # --- rivers
    rv = _draw_rivers(X0, Y0, n, hard) * (dl > 3)
    out = out * (1 - 0.8 * rv[..., None]) + RIVER * (0.8 * rv)[..., None]
    _stage('rivers', out)
    # --- province borders: solid ink + the pillow rim inside every province (also along coasts)
    bm = _border_mask(hard, X0, Y0, n) * (dl > 1.0)
    dline = ndimage.distance_transform_edt(~((bm > 0.5) | ~hard))  # px to nearest border line or sea, on land
    rim = _rim(dline) * hard
    out = out * (1 - rim[..., None] * np.array([1.0, 1.1, 1.25]))
    out = out * (1 - 0.92 * bm[..., None]) + BORDER * (0.92 * bm)[..., None]
    _stage('borders', out)
    # --- coast: dark ink line, brown land band, darkened hatched sea band
    out = _coast(out, hard, ds, dl, gx * PX, gy * PX)
    # --- sea-zone borders (soft dark ink between maritime provinces)
    sb = _sea_border_mask(hard, ds, X0, Y0, n, gx, gy, noise) * 0.92
    out = out * (1 - sb[..., None]) + SEA_LINE * sb[..., None]
    _stage('coast', out)
    # --- graticule (the original's conic grid, multiply ink)
    ga = _graticule(gx, gy) * 0.95
    out = out * (1 - ga[..., None] * (1 - GRAT_MUL))
    _stage('graticule', out)
    # --- ships in open sea
    out = _stamp_ships(out, ds, hard, X0, Y0, n)
    _stage('ships', out)
    # --- the old map art inside its frame (as styled.py)
    keepx = np.clip((OLD_X1 - gx) / 60.0, 0, 1); keepy = np.clip((OLD_Y1 - gy) / 40.0, 0, 1)
    hole = np.clip((np.hypot((gx - 1832) / 70.0, (gy - 88) / 95.0) - 1.0) / 0.35, 0, 1)
    keep = keepx * keepy * hole * (gx >= 0) * (gy >= 0)
    if keep.max() > 0:
        orig = GW.sample(game, np.clip(gx, 0, 2047), np.clip(gy, 0, 2047))
        if col <= 3 and row <= 3:
            t = np.asarray(Image.open(os.path.join(texlib.TILES, 'T00%d00%d.png' % (3 - row, col)))).astype(float)
            full = np.zeros((n, n, 3)); full[PAD:PAD + TS, PAD:PAD + TS] = t
            inside = np.zeros((n, n), bool); inside[PAD:PAD + TS, PAD:PAD + TS] = True
            orig = np.where(inside[..., None], full, orig)
        out = orig * keep[..., None] + out * (1 - keep[..., None])
    return np.clip(out[PAD:PAD + TS, PAD:PAD + TS], 0, 255).astype(np.uint8)


if __name__ == '__main__':
    col, row = int(sys.argv[1]), int(sys.argv[2])
    img = render_tile(col, row)
    p = os.path.join(ROOT, 'build', 'art', 'styled2_%d_%d.png' % (col, row))
    Image.fromarray(img).save(p)
    print(p)

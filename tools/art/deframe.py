"""Remove the old parchment sheet's frame from the campaign-map tiles so the original art runs on into the new map.

The original 16 tiles were painted as a sheet with its own frame: torn black outer edges, a burnt dark corner at the
top left, a neatline (double dotted rectangle) with degree numbers and tick marks in the margins, ink blots and a
"coffee ring" cartouche in the south margin, and a general darkening of the parchment towards the sheet edges.
With the map extended past those edges they all read as seams, so this module

  * builds a "hole" mask of everything that belongs to the frame (margins, torn edges, the burnt corner, blots, ring),
  * fills the holes with map content continued from the surrounding art: each hole pixel takes the sea/land class of the
    nearest kept pixel, its colour from a class-wise normalised blur of the kept art (so sea stays sea-coloured and
    land stays parchment-coloured) and its grain from patches of the game's own clean sea / parchment textures
    (texlib.py), quilted on a global grid so neighbouring tiles agree.  Inside the burnt corner the art that is still
    faintly visible under the stain (graticule, a ship) is recovered by illumination correction and mixed in,
  * flattens the sheet's edge vignette with a smooth gain so the old art meets the new tiles at the same brightness.

Everything inside the neatline that is not a blot stays untouched.

deframe_tile(col, row, img) is a pure post-process for one 1024 px tile (rows counted from the top); it reads its
neighbours from build/tiles_new (or build/tiles_png) for context.  Run as a script it writes the 16 affected tiles to
build/art/deframe/tile_<col>_<row>.png plus preview.png and before/after crops.

    python tools/art/deframe.py            # all 16 tiles + preview + crops
    python tools/art/deframe.py 3 1        # one tile
"""
import os, sys
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import texlib

BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'art', 'deframe')
TS = 1024
PAD = 384                                 # context taken from the neighbours around a tile
# extent of the original art in global full-res px (2 px per g px; see styled.py keepx / keepy)
OLD_X_FULL, OLD_X_END = 3600.0, 3720.0    # old art fully kept west of OLD_X_FULL, gone east of OLD_X_END
OLD_Y_FULL, OLD_Y_END = 3710.0, 3790.0
# the sheet's neatline (double dotted line) in global px: the margins outside it are frame
NEAT_TOP, NEAT_LEFT = 266, 192
# hand-placed frame ornaments (global px): ink blot bottom left, cartouche ring in the Sahara
BLOT_SW = (232, 3392, 92, 142)            # cx, cy, rx, ry
RING = (725, 3537, 135, 180)              # cx, cy, rx, ry of an ellipse enclosing the ring's brown strokes
VIGNETTE_BAND = 900.0                     # px inward from the old frame over which the edge darkening is flattened
REF_LEVEL = {'land': 168.0, 'sea': 133.0}  # the sheet's interior brightness per class (measured, see report)
# coast treatment for coasts that fall inside filled areas (styled.py's colours)
SEA_DARK = np.array([82.0, 104.0, 114.0]); RIM = np.array([205.0, 118.0, 62.0])
RIM_DARK = np.array([92.0, 52.0, 30.0]); LAND_SHADE = np.array([118.0, 80.0, 46.0])

_cache = {}


# ----------------------------------------------------------------------------------------------- tile I/O
def tile_path(col, row):
    p = os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))
    if os.path.exists(p):
        return p
    if 0 <= col <= 3 and 0 <= row <= 3:
        return os.path.join(BUILD, 'tiles_png', 'T00%d00%d.png' % (3 - row, col))
    return None


def load_tile(col, row):
    p = tile_path(col, row)
    if p is None:
        return None
    return np.asarray(Image.open(p).convert('RGB')).astype(np.float32)


def context(col, row, img, pad=PAD):
    """(TS+2pad)^2 canvas: img in the middle, the neighbouring tiles (from disk) around it, edge-replicated outside."""
    n = TS + 2 * pad
    C = np.zeros((n, n, 3), np.float32)
    known = np.zeros((n, n), bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            t = img if (dr == 0 and dc == 0) else load_tile(col + dc, row + dr)
            if t is None:
                continue
            x0, y0 = pad + dc * TS, pad + dr * TS
            sx0, sy0 = max(0, -x0), max(0, -y0)
            sx1, sy1 = min(TS, n - x0), min(TS, n - y0)
            C[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = t[sy0:sy1, sx0:sx1]
            known[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] = True
    if not known.all():                                   # map edge: replicate the nearest known pixel
        idx = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
        C = C[idx[0], idx[1]]
    return C


# ----------------------------------------------------------------------------------------------- masks
def sea_class(C):
    """True where the art is sea (blue-ish), from a lightly blurred colour."""
    b = ndimage.gaussian_filter(C, (3, 3, 0))
    return (b[..., 2] - b[..., 0]) > 6


def frame_mask(C, X0, Y0):
    """Hard mask (bool) of frame features inside the context window whose top-left is global (X0, Y0)."""
    n = C.shape[0]
    ys, xs = np.mgrid[0:n, 0:n]
    gx, gy = xs + X0, ys + Y0
    lum = C.mean(-1)
    inold = (gx < OLD_X_END + 40) & (gy < OLD_Y_END + 40)
    m = np.zeros((n, n), bool)
    # margins outside the neatline (numbers, ticks, torn edges)
    m |= inold & ((gy < NEAT_TOP) | (gx < NEAT_LEFT))
    # the burnt dark corner at the top left: the dark region connected to the corner
    reg = (gx < 1100) & (gy < 1700) & (gx >= 0) & (gy >= 0)
    if reg.any():
        dark = (ndimage.gaussian_filter(lum, 4) < 92) & reg
        dark = ndimage.binary_opening(dark, iterations=3)
        lab, nl = ndimage.label(dark)
        if nl:
            # components touching the sheet's left/top margins belong to the corner stain
            touch = set(np.unique(lab[m & dark])) - {0}
            sizes = ndimage.sum(dark, lab, range(1, nl + 1))
            big = {k for k in range(1, nl + 1) if sizes[k - 1] > 20000}
            keep = touch | big
            if keep:
                corner = np.isin(lab, list(keep))
                m |= ndimage.binary_dilation(corner, iterations=52)   # the stain has a wide soft edge
    # the torn black outer edge wherever it shows (very dark pixels near the sheet border)
    border = inold & ((gy < 420) | (gx < 420) | (gx > OLD_X_FULL - 300) | (gy > OLD_Y_FULL - 300))
    black = (ndimage.gaussian_filter(lum, 1.5) < 45) & border
    black = ndimage.binary_opening(black, iterations=2)
    m |= ndimage.binary_dilation(black, iterations=10)
    # ink blots and stains: large dark anomalies against the local parchment level, in the east/north strips
    strip = inold & (gx > OLD_X_FULL - 420)
    if strip.any():
        bl = ndimage.gaussian_filter(lum, 5)
        med = ndimage.median_filter(bl[::4, ::4], 41)
        med = ndimage.zoom(med, 4, order=1)[:n, :n]
        anom = (bl < med - 34) & strip
        anom = ndimage.binary_opening(anom, iterations=4)          # drops mountain hatching and thin lines
        sea = sea_class(C) & ~ndimage.binary_dilation(anom, iterations=8)
        nearsea = ndimage.binary_dilation(sea, iterations=20)
        lab, nl = ndimage.label(anom)
        if nl:
            good = []
            for k, sl in enumerate(ndimage.find_objects(lab), 1):
                comp = lab[sl] == k
                area = comp.sum(); h, w = comp.shape
                if area < 700 or area < 0.45 * h * w or not (0.35 < h / float(w) < 2.8):
                    continue                                       # not compact: coast, border, hatching
                if (comp & nearsea[sl]).any():
                    continue                                       # coast rims are drawn dark too
                good.append(k)
            if good:
                m |= ndimage.binary_dilation(np.isin(lab, good), iterations=30)   # blots fade out softly
                big = [k for k in good if (lab == k).sum() > 5000]
                if big:
                    m |= ndimage.binary_dilation(np.isin(lab, big), iterations=60)
    # hand-placed ornaments
    cx, cy, rx, ry = BLOT_SW
    m |= (((gx - cx) / (rx + 14.0)) ** 2 + ((gy - cy) / (ry + 14.0)) ** 2) < 1
    m |= ring_mask(C, X0, Y0)
    return m & inold


def ring_mask(C, X0, Y0):
    """The cartouche ring in the Sahara: its two brown strokes (R-B well above the parchment's) inside an ellipse,
    so the hatching between the strokes is kept."""
    n = C.shape[0]
    ys, xs = np.mgrid[0:n, 0:n]
    gx, gy = xs + X0, ys + Y0
    cx, cy, rx, ry = RING
    rr = np.hypot((gx - cx) / float(rx), (gy - cy) / float(ry))
    zone = (rr > 0.45) & (rr < 1.0)
    if not zone.any():
        return zone
    b = ndimage.gaussian_filter(C, (2, 2, 0))
    brown = ((b[..., 0] - b[..., 2]) > 36) & (b.mean(-1) < 150) & zone
    brown = ndimage.binary_opening(brown, iterations=1)
    return ndimage.binary_dilation(brown, iterations=5)


# ----------------------------------------------------------------------------------------------- fill
def _lib():
    if 'lib' not in _cache:
        sea, plain, mount = texlib.build()
        def prep(lst):
            out = []
            for p in lst:
                for q in (p, p[::-1, ::-1]):
                    out.append((q - ndimage.gaussian_filter(q, (10, 10, 0))).astype(np.float32))
            return out
        _cache['lib'] = (prep(sea), prep(plain))
    return _cache['lib']


def _hash(i, j, k=0):
    v = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791)
    return (v & 0x7fffffff) / 0x7fffffff


def local_patches(C, ok, hp_sigma=26, P=192, step=64):
    """High-pass patches cut from the kept art of one class inside the context window (ok: bool mask of usable px).
    Patches with long strokes (graticule, borders, ships) are skipped, as in texlib."""
    hp = C - ndimage.gaussian_filter(C, (hp_sigma, hp_sigma, 0))
    lum = C.mean(-1)
    out = []
    n = C.shape[0]
    for y in range(0, n - P + 1, step):
        for x in range(0, n - P + 1, step):
            if ok[y:y + P, x:x + P].mean() < 0.995:
                continue
            l = lum[y:y + P, x:x + P]
            faint = l < np.median(l) - 22
            if faint.mean() > 0.06:
                continue
            lab, k = ndimage.label(ndimage.binary_dilation(faint, iterations=1))
            if k:
                sl = ndimage.find_objects(lab)
                if max(max(o[0].stop - o[0].start, o[1].stop - o[1].start) for o in sl) > 60:
                    continue
            q = hp[y:y + P, x:x + P].astype(np.float32)
            if ndimage.gaussian_filter(q.mean(-1), 12).std() > 4.0:
                continue                                           # a tonal step (blend zone, stain edge) inside
            out.append(q); out.append(q[::-1, ::-1])
    return out


def mottle(X0, Y0, n):
    """Unit-variance band-pass noise field (periodic, 1024 px) sampled in global coordinates: the parchment's
    mid-scale blotchiness that lies between the colour low-pass and the fine grain of the patches."""
    if 'mottle' not in _cache:
        rng = np.random.default_rng(23)
        f = rng.random((1024, 1024)).astype(np.float32)
        f = ndimage.gaussian_filter(f, 11, mode='wrap') - ndimage.gaussian_filter(f, 45, mode='wrap')
        _cache['mottle'] = f / f.std()
    f = _cache['mottle']
    yy = (Y0 + np.arange(n)) % 1024; xx = (X0 + np.arange(n)) % 1024
    return f[np.ix_(yy, xx)]


def quilt(X0, Y0, n, lib, salt):
    """High-pass texture quilted from `lib` patches on a global grid (feathered patches overlapping by half)."""
    P = lib[0].shape[0]; CELL = P // 2
    acc = np.zeros((n, n, 3), np.float32); wsum = np.zeros((n, n), np.float32)
    win = np.outer(np.hanning(P), np.hanning(P)).astype(np.float32) + 1e-3
    for j in range((Y0 - P) // CELL, (Y0 + n) // CELL + 2):
        for i in range((X0 - P) // CELL, (X0 + n) // CELL + 2):
            px, py = i * CELL - X0, j * CELL - Y0
            sx0, sy0 = max(0, -px), max(0, -py); sx1, sy1 = min(P, n - px), min(P, n - py)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            p = lib[int(_hash(i, j, salt) * len(lib)) % len(lib)]
            acc[py + sy0:py + sy1, px + sx0:px + sx1] += p[sy0:sy1, sx0:sx1] * win[sy0:sy1, sx0:sx1, None]
            wsum[py + sy0:py + sy1, px + sx0:px + sx1] += win[sy0:sy1, sx0:sx1]
    return acc / np.maximum(wsum, 1e-6)[..., None]


def class_lowpass(C, w, sigmas=(24, 70, 200)):
    """Normalised blur of C using only pixels weighted by w; small sigma where enough support, larger further away."""
    out = None; conf = None
    for s in sigmas:
        num = ndimage.gaussian_filter(C * w[..., None], (s, s, 0))
        den = ndimage.gaussian_filter(w, s)
        lp = num / np.maximum(den, 1e-6)[..., None]
        if out is None:
            out, conf = lp, den
        else:
            a = np.clip(conf / 0.08, 0, 1)[..., None]
            out = out * a + lp * (1 - a)
            conf = np.maximum(conf, den)
    return out


def warp_land():
    """Land probability of the extended map's geography over the old sheet, 1 sample per 8 full px (cached on disk)."""
    if 'warp' in _cache:
        return _cache['warp']
    p = os.path.join(OUT, 'warp_land_8.npy')
    if os.path.exists(p):
        L = np.load(p)
    else:
        import warp, gen_world as GW
        f = warp.game_to_lonlat()
        land = np.asarray(Image.open(os.path.join(BUILD, 'land_lonlat.png'))).astype(float) / 255
        n = 4096 // 8
        ys, xs = np.mgrid[0:n, 0:n]
        pts = np.stack([((xs * 8 + 4) / 2.0).ravel(), ((ys * 8 + 4) / 2.0).ravel()], 1)
        q, ll = f(pts)
        lon = ll[:, 0].reshape(n, n); lat = ll[:, 1].reshape(n, n)
        L = GW.sample(land, (lon - GW.LON0) / GW.RES, (GW.LAT1 - lat) / GW.RES)
        L[(lon > 189.5) | (lon < GW.LON0 + 0.5) | (lat < -55)] = 0
        L = L.astype(np.float32)
        os.makedirs(OUT, exist_ok=True); np.save(p, L)
    _cache['warp'] = L
    return L


def _drop_specks(cls, hole, min_area):
    """Remove small islands / lakes that lie entirely inside the filled area."""
    for val in (True, False):
        lab, nl = ndimage.label(cls == val)
        if not nl:
            continue
        sizes = ndimage.sum(np.ones_like(cls, np.float32), lab, range(1, nl + 1))
        outside = set(np.unique(lab[~hole])) - {0}
        bad = [k for k in range(1, nl + 1) if sizes[k - 1] < min_area and k not in outside]
        if bad:
            cls = np.where(np.isin(lab, bad), not val, cls)
    return cls


def fill_holes(C, hole, X0, Y0, recover=None, cls_force=None):
    """Replace hole (bool) pixels of C by continued map content.  recover: optional bool mask of hole pixels whose
    underlying art is still visible (burnt corner) and gets mixed back after illumination correction.
    cls_force: optional bool (n, n) sea class to use for the hole pixels instead of the vote (e.g. a strait that the
    vote would close)."""
    n = C.shape[0]
    keep = ~hole
    sea = sea_class(C)
    # pixels right next to a hole are often stained too: they do not vote and do not give colour
    ring = ndimage.binary_dilation(hole, iterations=24)
    keepv = keep & ~ring
    keepf = keepv.astype(np.float32)
    # class of each hole pixel: smoothed vote of the kept pixels around it (no stripes from alternating coasts)
    psea = class_lowpass(sea.astype(np.float32)[..., None], keepf, sigmas=(16, 48, 140))[..., 0]
    conf = np.clip(ndimage.gaussian_filter(keepf, 48) / 0.25, 0, 1)
    # far from any kept art the vote means little: fall back to the map's real geography there
    ys, xs = np.mgrid[0:n, 0:n]
    L = warp_land(); nl = L.shape[0]
    wl = ndimage.map_coordinates(L, [np.clip((ys + Y0) / 8.0 - 0.5, 0, nl - 1), np.clip((xs + X0) / 8.0 - 0.5, 0, nl - 1)], order=1)
    wl[((xs + X0) < 800) & ((ys + Y0) < 1400)] = 0                  # the burnt corner is open Atlantic
    psea = conf * psea + (1 - conf) * (1 - wl)
    psea = ndimage.gaussian_filter(psea, 3)
    cls = np.where(hole, psea > 0.5, sea)
    cls = _drop_specks(cls, hole, 7000)
    if cls_force is not None:                                       # caller-given sea/land class for the hole pixels
        cls = np.where(hole, cls_force, sea)
    wsea = (keepv & sea).astype(np.float32); wland = (keepv & ~sea).astype(np.float32)
    lp = np.where(cls[..., None], class_lowpass(C, wsea), class_lowpass(C, wland))
    sea_lib, land_lib = _lib()
    far = ndimage.binary_dilation(hole, iterations=6)
    loc_sea = local_patches(C, keep & ~far & sea); loc_land = local_patches(C, keep & ~far & ~sea)
    tex_s = quilt(X0, Y0, n, loc_sea if len(loc_sea) >= 8 else sea_lib, 11)
    tex_l = quilt(X0, Y0, n, loc_land if len(loc_land) >= 8 else land_lib, 12)
    fill = lp + np.where(cls[..., None], tex_s, tex_l)
    # mid-scale blotchiness, with the amplitude the kept art of each class shows in this window
    bp = ndimage.gaussian_filter(C, (11, 11, 0)) - ndimage.gaussian_filter(C, (45, 45, 0))
    def amp(w):
        sel = w > 0
        return np.array([np.std(bp[..., k][sel]) if sel.sum() > 5000 else 4.0 for k in range(3)], np.float32)
    amp_s, amp_l = amp(keepv & sea), amp(keepv & ~sea)
    fill = fill + mottle(X0, Y0, n)[..., None] * np.where(cls[..., None], amp_s, amp_l) * 0.9
    # coasts that run through the filled area get the original's coast treatment (styled2._coast: water darkening
    # towards the shore under dotted ripple rings, dark coast band fading out slowly; measured on the original tiles,
    # 2026-10-22: the earlier orange rim + pale water band left a light shore line), only well inside the hole
    dist_in = ndimage.distance_transform_edt(hole)
    w = np.clip((dist_in - 6) / 14.0, 0, 1)
    if w.any():
        import styled2
        ds = ndimage.distance_transform_edt(cls)                    # sea px -> distance to land
        dl = ndimage.distance_transform_edt(~cls)
        coasted = styled2._coast(fill, ~cls, ds, dl, xs + X0 + 0.5, ys + Y0 + 0.5, rim_done=False)
        fill = fill * (1 - w[..., None]) + coasted * w[..., None]
    if recover is not None and recover.any():
        # the stain is (nearly) multiplicative: divide by its own low-pass to get the ink drawn under it
        own = ndimage.gaussian_filter(C.mean(-1), 14)
        rec = C.mean(-1) / np.maximum(own, 6.0)
        ink = np.clip(rec - ndimage.gaussian_filter(rec, 8), -0.6, 0.0)      # darker-than-surroundings only
        ink = np.where(ink < -0.10, ink + 0.10, 0.0)                           # strokes, not stain speckle
        ink = ndimage.gaussian_filter(ink, 0.7)
        a = ndimage.gaussian_filter(recover.astype(np.float32), 6) * 0.8
        fill = fill * (1 + (ink * a)[..., None])
    a = ndimage.gaussian_filter(hole.astype(np.float32), 2.0)[..., None]
    return C * (1 - a) + fill * a


# ----------------------------------------------------------------------------------------------- vignette
# Medians measured by measure_new_art_levels() on the 2026-10-16 tiles and FROZEN on 2026-10-22: the shore-halo fix
# (styled2._coast) moved the measured medians by 1 colour unit (land B 133 -> 132, sea B 145 -> 146), which shifted the
# frame blending of every deframed tile by up to 2 levels and flipped northfix's energy thresholds (dotted patches in
# tile row 0).  The level only anchors the frame blending, so it must not follow coast-treatment changes.
NEW_ART_LEVELS = {'land': np.array([163.0, 153.0, 133.0], np.float32), 'sea': np.array([112.0, 135.0, 145.0], np.float32)}


def new_art_levels():
    return NEW_ART_LEVELS


def measure_new_art_levels():
    """Mean colour of land and sea in the new tiles that border the old sheet (col 4, row 4), measured once."""
    if 'newlev' in _cache:
        return _cache['newlev']
    acc = {'land': [], 'sea': []}
    for col, row in [(4, r) for r in range(4)] + [(c, 4) for c in range(4)]:
        t = load_tile(col, row)
        if t is None:
            continue
        t = t[::4, ::4]
        sea = sea_class(t)
        acc['sea'].append(t[sea]); acc['land'].append(t[~sea])
    lev = {}
    for k, v in acc.items():
        v = np.concatenate(v) if v else None
        lev[k] = np.median(v, 0).astype(np.float32) if v is not None and len(v) > 5000 else np.full(3, REF_LEVEL[k], np.float32)
    _cache['newlev'] = lev
    return lev


def vignette_gain(C, hole, X0, Y0):
    """Smooth per-pixel gain (n, n, 1) that lifts the sheet's darkened edge zone to the brightness of its interior."""
    n = C.shape[0]
    ys, xs = np.mgrid[0:n, 0:n]
    gx, gy = xs + X0, ys + Y0
    sea = sea_class(C)
    keep = (~hole).astype(np.float32)
    S = 90
    # local colour of land and sea separately (normalised blur over kept pixels of that class)
    def level(w):
        num = ndimage.gaussian_filter(C * w[..., None], (S, S, 0)); den = ndimage.gaussian_filter(w, S)
        return num / np.maximum(den, 1e-6)[..., None], den
    lland, dland = level(keep * ~sea); lsea, dsea = level(keep * sea)
    isl = (dland > dsea)[..., None]
    loc = np.where(isl, lland, lsea)
    lev = new_art_levels()
    # brightness: lift the darkened edge zone to the sheet's interior level (never darken);
    # colour: at the frame itself match the new art's land / sea colour so the two meet without a step
    lum_t = np.where(isl[..., 0], REF_LEVEL['land'], REF_LEVEL['sea'])
    g_lum = np.clip(lum_t / np.maximum(loc.mean(-1), 30.0), 1.0, 1.45)[..., None]
    col_t = np.where(isl, lev['land'], lev['sea'])
    g_col = np.clip(col_t / np.maximum(loc, 30.0), 0.8, 1.5)
    # only near the sheet's frame, fading to 1 inward
    d_edge = np.minimum.reduce([gx - NEAT_LEFT, gy - NEAT_TOP, OLD_X_FULL - gx, OLD_Y_FULL - gy])
    wgt = np.clip(1 - d_edge / VIGNETTE_BAND, 0, 1) ** 1.2
    inold = (gx < OLD_X_END) & (gy < OLD_Y_END)
    # the new art east/south of the old frame is already flat: taper the gain across the blend zone
    tap = np.clip((OLD_X_END - gx) / (OLD_X_END - OLD_X_FULL), 0, 1) * np.clip((OLD_Y_END - gy) / (OLD_Y_END - OLD_Y_FULL), 0, 1)
    wgt = (wgt * tap * inold)[..., None]
    # the colour match is strongest right at the frame and fades faster than the brightness lift
    wcol = np.clip(1 - d_edge / (VIGNETTE_BAND * 0.6), 0, 1)[..., None] ** 1.5 * (tap * inold)[..., None]
    g = (1 + (g_lum - 1) * wgt) * (1 - wcol) + g_col * wcol
    g = ndimage.gaussian_filter(g, (20, 20, 0))
    return g


# ----------------------------------------------------------------------------------------------- main entry
def affected(col, row):
    return 0 <= col <= 3 and 0 <= row <= 3


def deframe_tile(col, row, img):
    """img: HxWx3 uint8/float array (1024 px tile, rows from the top). Returns the cleaned uint8 tile."""
    img = np.asarray(img).astype(np.float32)
    if not affected(col, row):
        return np.clip(img, 0, 255).astype(np.uint8)
    C = context(col, row, img)
    X0, Y0 = col * TS - PAD, row * TS - PAD
    hole = frame_mask(C, X0, Y0)
    n = C.shape[0]
    ys, xs = np.mgrid[0:n, 0:n]
    gx, gy = xs + X0, ys + Y0
    # the burnt corner: inside the neatline (not plain margin) and genuinely dark -> recover the art underneath
    recover = hole & (gx >= NEAT_LEFT) & (gy >= NEAT_TOP) & (gx < 1100) & (gy < 1700) & (C.mean(-1) > 25)
    gain = vignette_gain(C, hole, X0, Y0)
    C = C * gain
    out = fill_holes(C, hole, X0, Y0, recover)
    out = out[PAD:PAD + TS, PAD:PAD + TS]
    return np.clip(out, 0, 255).astype(np.uint8)


def mosaic(scale, tile_fn, cols=9, rows=7):
    s = int(TS * scale)
    W = Image.new('RGB', (cols * s, rows * s))
    for r in range(rows):
        for c in range(cols):
            t = tile_fn(c, r)
            if t is None:
                continue
            W.paste(Image.fromarray(np.asarray(t).astype(np.uint8)).resize((s, s), Image.LANCZOS), (c * s, r * s))
    return W


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if len(argv) >= 2:
        col, row = int(argv[0]), int(argv[1])
        img = load_tile(col, row)
        p = os.path.join(OUT, 'tile_%d_%d.png' % (col, row))
        Image.fromarray(deframe_tile(col, row, img)).save(p)
        print(p)
        return
    done = {}
    for row in range(4):
        for col in range(4):
            img = load_tile(col, row)
            out = deframe_tile(col, row, img)
            done[(col, row)] = out
            p = os.path.join(OUT, 'tile_%d_%d.png' % (col, row))
            Image.fromarray(out).save(p)
            print(p, flush=True)
    def final(c, r):
        return done.get((c, r)) if (c, r) in done else load_tile(c, r)
    mosaic(0.25, final).save(os.path.join(OUT, 'preview.png'))
    # before / after crops of the worst seams (full resolution, 1024 px wide)
    crops = {'kazakhstan_east': (3200, 300, 4224, 1324), 'sahara_south': (1000, 3300, 2024, 4324),
             'corner_topleft': (0, 0, 1024, 1024), 'blot_ring_southwest': (0, 2900, 1024, 3924)}
    def canvas(fn, x0, y0, x1, y1):
        im = Image.new('RGB', (x1 - x0, y1 - y0))
        for r in range(y0 // TS, (y1 - 1) // TS + 1):
            for c in range(x0 // TS, (x1 - 1) // TS + 1):
                t = fn(c, r)
                if t is None:
                    continue
                im.paste(Image.fromarray(np.asarray(t).astype(np.uint8)), (c * TS - x0, r * TS - y0))
        return im
    for name, box in crops.items():
        b = canvas(load_tile, *box); a = canvas(final, *box)
        both = Image.new('RGB', (b.width * 2 + 16, b.height), (255, 255, 255))
        both.paste(b, (0, 0)); both.paste(a, (b.width + 16, 0))
        both.save(os.path.join(OUT, 'crop_%s.png' % name))
    print(os.path.join(OUT, 'preview.png'))


if __name__ == '__main__':
    main(sys.argv[1:])

"""Full-resolution map tiles in the game's own style (1024 px per tile, 2 px per g px).

Layers, all computed in global g coordinates so neighbouring tiles join without seams:
  * land/sea from Natural Earth through warp.game_to_lonlat (the prototype's layout),
  * base colours = the game's median sea and land colours with large soft stains,
  * fine texture = high-pass detail of patches cut from the game's own tiles (texlib.py), quilted on a global grid,
    with mountain patches where the prototype draws mountains,
  * the game's coast treatment: darker water with engraved ripple lines, orange rim with a dark outline,
    brown shading on the land side,
  * inside the old map frame the original art is kept and blended into the new art at the old frame.
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warp, texlib, gen_world as GW

ROOT = GW.ROOT
TS = 1024                     # tile size in px
PX = 2.0                      # px per g px
SEA_MED = np.array([122.0, 142.0, 151.0])
LAND_MED = np.array([172.0, 162.0, 143.0])
RIM = np.array([205.0, 118.0, 62.0])
RIM_DARK = np.array([92.0, 52.0, 30.0])
LAND_SHADE = np.array([118.0, 80.0, 46.0])
SEA_DARK = np.array([82.0, 104.0, 114.0])
CELL, PATCH = 64, 128          # quilting grid step and patch size (px); patches overlap by half
PAD = 64

_cache = {}


BORDER = np.array([115.0, 68.0, 57.0])
BORDER_HALO = np.array([120.0, 88.0, 64.0])
DASH = np.array([98.0, 58.0, 44.0])


EDGES_JSON = None             # province polygons the borders are drawn from (default build/world_provinces.json)


def _edges():
    """Unique province border edges of the bigger map in global tile px, with the 1789 owners on each side."""
    if 'edges' in _cache:
        return _cache['edges']
    import json, world_nations as WN
    data = json.load(open(EDGES_JSON or os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))
    owner_of_code = {'GB': 'GRAN_BRETANYA', 'FR': 'FRANCIA', 'NL': 'BATAVIA', 'PT': 'PORTUGAL', 'ES': 'ESPANYA',
                     'RU': 'RUSIA', 'OT': 'OTOMANO', 'KZ': 'HANNOVER'}
    owner = {}
    for k, w in data.items():
        owner[k] = WN.EXTRA_OWNER.get(k, owner_of_code.get(w['owner']))
    for n in WN.NATIONS:
        for k in n[3]:
            owner[k] = n[0]
    for k, n in WN.EXTRA_TO_NATION.items():
        owner[k] = n
    edges = {}
    def gp(x, z):
        return ((x - MG.COLS[0]) / MG.TILE_W * 512.0 * PX, (MG.ROWS[4] - z) / MG.TILE_H * 512.0 * PX)
    import meshgen as MG
    for k, w in data.items():
        poly = w['poly']
        for i in range(len(poly)):
            a = tuple(round(v, 1) for v in poly[i - 1]); b = tuple(round(v, 1) for v in poly[i])
            key = (a, b) if a < b else (b, a)
            edges.setdefault(key, []).append(owner[k])
    out = []
    for (a, b), owners in edges.items():
        pa, pb = gp(*a), gp(*b)
        same = len(owners) == 2 and owners[0] == owners[1]
        out.append((pa, pb, same, len(owners)))
    _cache['edges'] = out
    return out


def _draw_borders(out, hard, X0, Y0, n):
    from PIL import ImageDraw
    core = Image.new('L', (n, n), 0); halo = Image.new('L', (n, n), 0); dash = Image.new('L', (n, n), 0)
    dc, dh, dd = ImageDraw.Draw(core), ImageDraw.Draw(halo), ImageDraw.Draw(dash)
    def land(x, y):
        xi, yi = int(x), int(y)
        return 0 <= xi < n and 0 <= yi < n and hard[yi, xi]
    for (ax, ay), (bx, by), same, nsides in _edges():
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
            continue                                   # coast: drawn by the coast treatment instead
        if same:
            step, on = 19.0, 12.0
            s = 0.0
            while s < L:
                e = min(L, s + on)
                p0 = (ax + (bx - ax) * s / L, ay + (by - ay) * s / L); p1 = (ax + (bx - ax) * e / L, ay + (by - ay) * e / L)
                dd.line([p0, p1], fill=255, width=3)
                s += step
        else:
            dh.line([(ax, ay), (bx, by)], fill=255, width=9)
            dc.line([(ax, ay), (bx, by)], fill=255, width=3)
    h = ndimage.gaussian_filter(np.asarray(halo, np.float32) / 255, 2.0)[..., None] * 0.35
    c = ndimage.gaussian_filter(np.asarray(core, np.float32) / 255, 0.6)[..., None] * 0.92
    d = ndimage.gaussian_filter(np.asarray(dash, np.float32) / 255, 0.6)[..., None] * 0.85
    out = out * (1 - h) + BORDER_HALO * h
    out = out * (1 - c) + BORDER * c
    out = out * (1 - d) + DASH * d
    return out


def _lib():
    if 'lib' not in _cache:
        sea, plain, mount = texlib.build()
        def prep(lst, flips):
            out = []
            for p in lst:
                for q in [p] + [f(p) for f in flips]:
                    low = ndimage.gaussian_filter(q, (14, 14, 0))
                    out.append((q - low).astype(np.float32))
            return out
        rot = lambda a: a[::-1, ::-1]; mir = lambda a: a[:, ::-1]
        _cache['lib'] = (prep(sea, [rot]), prep(plain, [rot]), prep(mount, []))
        stamps = []
        for p in mount:
            lum = p.mean(-1)
            med = ndimage.median_filter(lum, 25)
            core = (med - lum) > 18
            lab, nl = ndimage.label(core)
            if nl:
                sizes = ndimage.sum(core, lab, range(1, nl + 1))
                edge = set(np.unique(np.concatenate([lab[:4].ravel(), lab[-4:].ravel(), lab[:, :4].ravel(), lab[:, -4:].ravel()])))
                good = [k for k in range(1, nl + 1) if sizes[k - 1] >= 14 and k not in edge]
                core = np.isin(lab, good)
            a = np.clip((med - lum - 6) / 30.0, 0, 1) * ndimage.binary_dilation(core, iterations=2)
            a = ndimage.gaussian_filter(a, 0.5)
            if 0.015 < a.mean() < 0.12:
                stamps.append((p.astype(np.float32), a.astype(np.float32)))
        _cache['stamps'] = stamps
    return _cache['lib']


def _maps():
    if 'maps' not in _cache:
        game, land, detail, grain = GW.load()
        rng = np.random.default_rng(7)
        noise = ndimage.gaussian_filter(rng.random((1024, 1024)), 6, mode='wrap')
        noise = (noise - noise.min()) / (noise.max() - noise.min())
        stain = ndimage.gaussian_filter(rng.random((1000, 1250)), 22)      # one field over the whole map, 4 g px per cell
        stain = stain + 0.6 * ndimage.gaussian_filter(rng.random((1000, 1250)), 7)
        stain = (stain - stain.min()) / (stain.max() - stain.min())
        mount = ndimage.gaussian_filter(detail, 6)
        mount = np.clip(mount / (np.percentile(mount, 97) + 1e-6), 0, 1)
        _cache['maps'] = (game, land, mount, noise, stain)
        _cache['warp'] = warp.game_to_lonlat()
    return _cache['maps']


def _wrap_sample(tex, x, y):
    h, w = tex.shape
    return GW.sample(np.pad(tex, ((0, 1), (0, 1)), mode='wrap'), x % w, y % h)


def _hash(i, j, k=0):
    v = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791)
    return (v & 0x7fffffff) / 0x7fffffff


def _quilt(x0, y0, w, h, lib, choose):
    """Feather-blended patches on a global grid (px coordinates). choose(i, j) -> list index."""
    acc = np.zeros((h, w, 3), np.float32); wsum = np.zeros((h, w), np.float32)
    win = np.outer(np.hanning(PATCH), np.hanning(PATCH)).astype(np.float32) + 1e-3
    i0, i1 = (x0 - PATCH) // CELL, (x0 + w) // CELL + 1
    j0, j1 = (y0 - PATCH) // CELL, (y0 + h) // CELL + 1
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            px, py = i * CELL - x0, j * CELL - y0
            sx0, sy0 = max(0, -px), max(0, -py)
            sx1, sy1 = min(PATCH, w - px), min(PATCH, h - py)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            p = lib[choose(i, j) % len(lib)]
            acc[py + sy0:py + sy1, px + sx0:px + sx1] += p[sy0:sy1, sx0:sx1] * win[sy0:sy1, sx0:sx1, None]
            wsum[py + sy0:py + sy1, px + sx0:px + sx1] += win[sy0:sy1, sx0:sx1]
    return acc / np.maximum(wsum, 1e-6)[..., None]


def render_tile(col, row):
    """col 0..8, row 0..6 from the top. Returns a 1024x1024x3 uint8 array."""
    game, land, mount, noise, stain = _maps()
    sea_lib, plain_lib, mount_lib = _lib()
    f = _cache['warp']
    n = TS + 2 * PAD
    X0 = col * TS - PAD; Y0 = row * TS - PAD                     # global px of the padded window
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
    wob = _wrap_sample(noise, gx * 3.0, gy * 3.0) - 0.5
    hard = (L + wob * 0.22) > 0.5
    ds = ndimage.distance_transform_edt(~hard)                     # px from land, in the sea
    dl = ndimage.distance_transform_edt(hard)                      # px from sea, on land
    st = GW.sample(stain, gx / 4.0 + 20, gy / 4.0 + 20)
    base = np.where(hard[..., None], LAND_MED * (0.86 + 0.24 * st)[..., None],
                    SEA_MED * (0.93 + 0.12 * st)[..., None])
    inproto = (px >= 40) & (py >= 40) & (px <= 1960) & (py <= 1285)
    m = np.where(inproto, GW.sample(mount, px, py), 0.12)
    mcell = lambda i, j: m[int(np.clip(j * CELL - Y0 + PATCH // 2, 0, n - 1)), int(np.clip(i * CELL - X0 + PATCH // 2, 0, n - 1))]
    det_land = _quilt(X0, Y0, n, n, plain_lib, lambda i, j: int(_hash(i, j, 3) * len(plain_lib)))
    if 'sea' not in _cache:
        _cache['sea'] = np.load(os.path.join(ROOT, 'build', 'sea_detail.npy'))
    sd_tex = _cache['sea']; S = sd_tex.shape[0]
    yy = (Y0 + np.arange(n)) % S; xx = (X0 + np.arange(n)) % S
    det_sea = sd_tex[np.ix_(yy, xx)]
    out = base + np.where(hard[..., None], det_land, det_sea)
    # mountain glyphs: ink stamped from the game's own mountain drawings, density from the prototype
    stamps = _cache['stamps']
    G = 110
    for j in range((Y0 - PATCH) // G, (Y0 + n) // G + 1):
        for i in range((X0 - PATCH) // G, (X0 + n) // G + 1):
            cx = i * G + int(_hash(i, j, 5) * G) - X0; cy = j * G + int(_hash(i, j, 6) * G) - Y0
            ccx, ccy = int(np.clip(cx + PATCH // 2, 0, n - 1)), int(np.clip(cy + PATCH // 2, 0, n - 1))
            if not hard[ccy, ccx] or dl[ccy, ccx] < 24 or _hash(i, j, 7) > (m[ccy, ccx] - 0.25) * 1.4:
                continue
            col_, a_ = stamps[int(_hash(i, j, 8) * len(stamps))]
            sx0, sy0 = max(0, -cx), max(0, -cy); sx1, sy1 = min(PATCH, n - cx), min(PATCH, n - cy)
            if sx1 <= sx0 or sy1 <= sy0:
                continue
            reg = out[cy + sy0:cy + sy1, cx + sx0:cx + sx1]
            aa = a_[sy0:sy1, sx0:sx1, None] * hard[cy + sy0:cy + sy1, cx + sx0:cx + sx1, None]
            ink = np.minimum(col_[sy0:sy1, sx0:sx1], reg)
            out[cy + sy0:cy + sy1, cx + sx0:cx + sx1] = reg * (1 - aa) + ink * aa
    out = _draw_borders(out, hard, X0, Y0, n)
    # coast: sea side darkening and engraved ripple lines
    sd = np.exp(-ds / 22.0) * (~hard)
    out = out * (1 - 0.45 * sd[..., None]) + SEA_DARK * (0.45 * sd)[..., None]
    for k, a in ((9.0, 0.30), (15.0, 0.22), (22.0, 0.15)):
        rip = np.exp(-((ds - k) / 1.1) ** 2) * (~hard)
        out = out * (1 - a * rip[..., None]) + SEA_DARK * 0.8 * (a * rip)[..., None]
    rim = np.exp(-(ds / 2.2) ** 2) * (~hard) + np.exp(-(dl / 2.0) ** 2) * hard
    out = out * (1 - 0.85 * rim[..., None]) + RIM * (0.85 * rim)[..., None]
    rimd = np.exp(-((ds - 3.6) / 0.9) ** 2) * (~hard)
    out = out * (1 - 0.7 * rimd[..., None]) + RIM_DARK * (0.7 * rimd)[..., None]
    sh = np.exp(-dl / 10.0) * hard * (1 - np.exp(-(dl / 2.0) ** 2))
    out = out * (1 - 0.55 * sh[..., None]) + LAND_SHADE * (0.55 * sh)[..., None]
    # the old map art inside its frame
    keepx = np.clip((1860 - gx) / 60.0, 0, 1); keepy = np.clip((GW.OLD_Y1 - 30 - gy) / 40.0, 0, 1)
    hole = np.clip((np.hypot((gx - 1832) / 70.0, (gy - 88) / 95.0) - 1.0) / 0.35, 0, 1)   # the black blot top right
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
    p = os.path.join(ROOT, 'build', 'styled_%d_%d.png' % (col, row))
    Image.fromarray(img).save(p)
    print(p)

"""Prototype battle map 'Caucasus' for Chechenya (province record idx 93, battle scenario name "93").

Derived from the original 51 Republica Helvetica map (template: chunk set, mountain rim, the two stone houses with
their interior sectors and garrison data, decor, sky, fog, sounds, victory conditions 'control the village').
New: a procedural mountain valley heightmap (W-E river gorge with two fords, ridges, the aul on a slope), shading,
sector map (navmesh), troop areas, zones, locations, river sounds, tree placement, a 4096^2 terrain texture made from
original terrain textures (Escocia / Helvetica / Suecia), minimap, previews.

    python tools/lvl_caucasus.py            # writes build/battlemaps/93/ and build/preview/lvl_caucasus_*.png

Output folder build/battlemaps/93/ mirrors Game/GameModes/Batalla/Escenarios/93/ (make_map copies it when
NEW_BATTLE_MAPS is True). Nothing here touches the game, the paks or save data.
"""
import json
import math
import os
import shutil
import sys

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lvl          # noqa: E402
import lvl_nav      # noqa: E402
import lvl_tex      # noqa: E402
import lvl_v3d      # noqa: E402

ROOT = os.path.dirname(HERE)
ESC = os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Batalla', 'Escenarios')
TEMPLATE = os.path.join(ESC, '51', '51RepublicaHelvetica.lvl')
SCEN = '93'                                   # battle scenario name of Chechenya (province record idx 93)
POOL_KEY = 'CHECHNYA'                         # province enum key (quick-game preview ESCENARIO_<key>)
LVL_NAME = '93Caucaso.lvl'
OUT = os.path.join(ROOT, 'build', 'battlemaps', SCEN)
PREVIEW = os.path.join(ROOT, 'build', 'preview')
SIZE = 75000.0
N = 181
CELL = SIZE / (N - 1)
SEED = 1789

# layout (cm, x east, z north): attacker deploys south, defender north, the aul (template houses) north-east
GORGE = [(-3000, 38500), (9000, 37800), (19000, 35200), (29000, 33800), (39000, 35600), (48000, 38600),
         (57000, 40400), (66000, 39000), (78000, 36500)]
FORDS = [(27500, 'west'), (60000, 'east')]     # x of the two fords
ATT_CENTER = (31500.0, 15500.0)
DEF_CENTER = (42500.0, 63000.0)
VILLAGE = (54850.0, 50100.0)


# ------------------------------------------------------------------ noise
def value_noise(X, Z, rng, period):
    """Smooth value noise (cubic lattice interpolation) at world coords, lattice spacing `period` cm."""
    n = int(SIZE / period) + 4
    g = rng.random((n, n))
    return ndimage.map_coordinates(g, [Z / period + 1.5, X / period + 1.5], order=3, mode='wrap')


def fbm(X, Z, rng, period=20000.0, octaves=6, persistence=0.5, ridged=False):
    out = np.zeros(X.shape)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        layer = value_noise(X, Z, rng, period / 2 ** o)
        if ridged:
            layer = (1.0 - np.abs(2.0 * layer - 1.0)) ** 2
        out += amp * layer
        tot += amp
        amp *= persistence
    return out / tot


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def polyline_dist(X, Z, pts):
    """Distance of grid points to a polyline and the arc-length parameter of the closest point."""
    best = np.full(X.shape, 1e18)
    s_at = np.zeros(X.shape)
    acc = 0.0
    for (x0, z0), (x1, z1) in zip(pts[:-1], pts[1:]):
        dx, dz = x1 - x0, z1 - z0
        L2 = dx * dx + dz * dz
        t = np.clip(((X - x0) * dx + (Z - z0) * dz) / L2, 0, 1)
        d = np.hypot(X - (x0 + t * dx), Z - (z0 + t * dz))
        m = d < best
        best = np.where(m, d, best)
        s_at = np.where(m, acc + t * math.sqrt(L2), s_at)
        acc += math.sqrt(L2)
    return best, s_at


def gorge_z(x):
    xs, zs = zip(*GORGE)
    return float(np.interp(x, xs, zs))


# ------------------------------------------------------------------ heightmap
def heightmap(orig, house_pads):
    """181 x 181 heights (cm), row = z. Derived from the template: its natural mountain rim is made taller and
    sharper (Caucasus ridges), the basin becomes a valley rising to the north, cut W-E by a gorge with two fords;
    deployment plateaus are smoothed, the aul gets flat pads. At the map edge the heights equal the template,
    so the scenery outside the map (TerrenoContiguo.V3D) still fits."""
    rng = np.random.default_rng(SEED)
    ax = np.arange(N) * CELL
    X, Z = np.meshgrid(ax, ax)
    orig = orig.astype(float)
    os_ = ndimage.gaussian_filter(orig, 1.5)
    def band(e0, e1):                                        # smooth in both axes (no diagonal creases)
        return smoothstep(e0, e1, X) * smoothstep(e0, e1, SIZE - X) * smoothstep(e0, e1, Z) * smoothstep(e0, e1, SIZE - Z)
    A = band(1200.0, 8000.0)                                 # 0 at the very edge
    inner = band(4000.0, 15000.0)
    basin = 5200.0
    mount = smoothstep(basin + 1200.0, basin + 5500.0, os_)
    ridges = fbm(X, Z, rng, 22000.0, 6, 0.55, ridged=True)
    h = orig.copy()
    h += A * 0.8 * np.maximum(0.0, os_ - basin)              # taller rim
    h += A * mount * 3200.0 * (ridges - 0.3)                 # sharp ridges and ravines on the mountains
    # valley floor: rises north of the gorge towards the defender's plateau
    gz = np.array([gorge_z(x) for x in ax])[None, :]
    north = Z - gz
    wz = (fbm(X, Z, rng, 30000.0, 3) - 0.5) * 8000.0
    flat = inner * (1.0 - mount)
    h += flat * (3400.0 * smoothstep(2500.0, 24000.0, north + wz) + 500.0 * smoothstep(-22000.0, -2000.0, north))
    calm = np.ones_like(h)
    for cx, cz in (ATT_CENTER, DEF_CENTER):
        calm = np.minimum(calm, 0.25 + 0.75 * smoothstep(8000, 15000, np.hypot(X - cx, Z - cz)))
    und = fbm(X + wz, Z - wz, rng, 11000.0, 5) - 0.5
    h += flat * calm * 1000.0 * und
    # the gorge: steep walls, a 14 m wide bed ~30 m below the rims; gentle ramps at the fords
    d, s_ = polyline_dist(X, Z, GORGE)
    ford = np.zeros_like(h)
    for fx, _ in FORDS:
        ford = np.maximum(ford, np.exp(-((X - fx) / 3600.0) ** 2))
    half_bed = 700.0
    wall = 1600.0 + 4800.0 * ford
    depth = (3100.0 - 1700.0 * ford) * A
    prof = 1.0 - smoothstep(half_bed, half_bed + wall, d)
    prof = prof ** (1.0 + 1.5 * (1 - ford)) * A              # sharp cliff edge where there is no ford
    rim = ndimage.uniform_filter(h, 7)
    bedline = np.array([gorge_z(x) for x in ax])
    bed = 3700.0 + 350.0 * (X / SIZE)                         # the stream falls to the west
    floor = np.maximum(np.minimum(bed + 0 * rim, rim), rim - depth)
    h = h * (1 - prof) + floor * prof
    rocky = fbm(X, Z, rng, 2500.0, 3, ridged=True)
    h += 350.0 * rocky * prof * (1 - ford) * (prof < 0.9) * A
    # deployment plateaus: pull towards their own smoothed surface
    for cx, cz in (ATT_CENTER, DEF_CENTER):
        w = (1 - smoothstep(6000, 13000, np.hypot(X - cx, Z - cz))) * A
        h = h * (1 - 0.85 * w) + ndimage.gaussian_filter(h, 7) * 0.85 * w
    # the aul: flat pads under the houses
    for (px, pz, r) in house_pads:
        dpad = np.hypot(X - px, Z - pz)
        hp = float(ndimage.map_coordinates(ndimage.gaussian_filter(h, 2), [[pz / CELL], [px / CELL]], order=1)[0])
        w = 1 - smoothstep(r, r + 1400.0, dpad)
        h = h * (1 - w) + hp * w
    return h.astype(np.float32)


def slope_deg(h):
    gz, gx = np.gradient(h.astype(float), CELL)
    return np.degrees(np.arctan(np.hypot(gx, gz)))


def height_image(h, px=724, contour=500.0):
    """North-up shaded relief with contour lines every `contour` cm (preview)."""
    big = ndimage.zoom(h.astype(float), px / N, order=3)
    hs = lvl_tex.hillshade(big, SIZE / px, light=(-0.45, 0.6, 0.65))
    hn = ((big - big.min()) / (big.max() - big.min()))[::-1]
    col = np.stack([90 + 150 * hn, 120 + 90 * hn, 80 + 60 * hn], -1) * (0.45 + 0.65 * hs[..., None])
    c = (big[::-1] // contour)
    edge = (np.abs(np.diff(c, axis=0, prepend=c[:1])) + np.abs(np.diff(c, axis=1, prepend=c[:, :1]))) > 0
    col[edge] *= 0.55
    return np.clip(col, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ shading (terrain vertex colours)
def normals(h):
    gz, gx = np.gradient(h.astype(float), CELL)
    n = np.stack([-gx, np.ones_like(gx), -gz], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def fit_shade(m):
    """Least-squares fit of the template's baked vertex shade: grey = k0 + N.L (corr 0.98-0.99 on the originals),
    clamped to 63..255."""
    v, h = m.vertices(), m.heights()
    iz, ix = m.grid_index(v)
    N_ = normals(h)[iz, ix]
    c = (v['c'] & 255) / 255.0
    ok = (c > 0.26) & (c < 0.99)
    sol = np.linalg.lstsq(np.c_[np.ones(ok.sum()), N_[ok]], c[ok], rcond=None)[0]
    return float(sol[0]), sol[1:]


def make_shade(k0, L):
    def shade(vtx, h):
        iz = np.round(vtx['z'] / CELL).astype(int)
        ix = np.round(vtx['x'] / CELL).astype(int)
        g = np.clip(k0 + normals(h)[iz, ix] @ L, 63 / 255.0, 1.0)
        gi = np.round(g * 255).astype(np.uint32)
        return (gi << 16) | (gi << 8) | gi
    return shade


# ------------------------------------------------------------------ masks
def gorge_profile(X, Z):
    d, _ = polyline_dist(X, Z, GORGE)
    ford = np.zeros(X.shape)
    for fx, _ in FORDS:
        ford = np.maximum(ford, np.exp(-((X - fx) / 3600.0) ** 2))
    return d, ford


def mask_polygons(mask, simplify=120.0, min_cells=3):
    """Raster mask (row = z, 181 x 181 nodes; a node stands for the cell around it) -> shapely geometry with
    smoothed outlines (morphological buffer close/open, then topology-preserving simplification)."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    lab, n = ndimage.label(mask)
    out = []
    for k in range(1, n + 1):
        zz, xx = np.nonzero(lab == k)
        if len(zz) < min_cells:
            continue
        g = unary_union([box(x * CELL - CELL / 2, z * CELL - CELL / 2, x * CELL + CELL / 2, z * CELL + CELL / 2)
                         for z, x in zip(zz, xx)])
        g = g.buffer(CELL * 0.7, 2).buffer(-CELL * 0.7, 2).simplify(simplify, preserve_topology=True)
        out += [p for p in lvl_nav.polys_of(g) if p.area > min_cells * CELL * CELL * 0.5]
    return unary_union(out) if out else None


# ------------------------------------------------------------------ trees
def place_trees(h, n, rng, avoid):
    """Tree positions: forest patches on the valley slopes and gorge rims (Caucasus beech and pine woods), never
    on cliffs, in the gorge, on the deployment plateaus or in the aul."""
    ax = np.arange(N) * CELL
    X, Z = np.meshgrid(ax, ax)
    sl = slope_deg(h)
    patch = fbm(X, Z, rng, 9000.0, 4)
    d, ford = gorge_profile(X, Z)
    edge = np.minimum(np.minimum(X, SIZE - X), np.minimum(Z, SIZE - Z))
    ok = (sl > 6) & (sl < 30) & (patch > 0.53) & (d > 2600) & (edge > 4500) & (h < 14500)
    for (cx, cz, r) in avoid:
        ok &= np.hypot(X - cx, Z - cz) > r
    cand = np.argwhere(ok)
    rng.shuffle(cand)
    pts = []
    for iz, ix in cand:
        x = ix * CELL + rng.uniform(-CELL / 2, CELL / 2)
        z = iz * CELL + rng.uniform(-CELL / 2, CELL / 2)
        if all((x - a) ** 2 + (z - b) ** 2 > 650.0 ** 2 for a, b in pts[-400:]):
            pts.append((x, z))
            if len(pts) >= n:
                break
    return pts


# ------------------------------------------------------------------ texture
TEX = 4096                                     # 4 x 4 tiles of 1024 px, like every original map
# material source boxes in the full-resolution (4096 px, north-up) composites of the original maps
SRC_GRASS_ESC = [(1320, 240, 2240, 760), (2400, 80, 3200, 720), (2360, 1200, 2800, 1520)]
SRC_GRASS_HEL = [(3200, 1520, 3600, 2400), (720, 2240, 1480, 2800), (2400, 2700, 3000, 3200)]
SRC_ROCK_HEL = [(0, 1560, 260, 2240), (1300, 140, 1860, 420), (0, 3620, 420, 4060)]
SRC_ROCK_ESC = [(100, 760, 400, 1040), (420, 1100, 700, 1420), (1620, 940, 1920, 1180), (3560, 600, 3860, 920)]
SRC_SNOW_SUE = [(2560, 3320, 3040, 3600), (1320, 1800, 1760, 2240), (3200, 3420, 3700, 3680)]


def composite(scen, lvl_name):
    p = os.path.join(ESC, scen, lvl_name)
    t = lvl.load(p).get(lvl.TERRAIN)
    return lvl_tex.map_texture(os.path.join(ESC, scen, 'Models'), mip=0, names=[mt[2] for mt in t['materials']])


def escocia_stream(img):
    """Centre line of the original Escocia stream bed (pixel coords), from its shallow-river sectors, pulled onto
    the darkest line of the painted channel; the bridges at both ends are left out."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    m = lvl.load(os.path.join(ESC, '02', '02Escocia.lvl'))
    sm = m.get(lvl.SECTORMAP)
    polys = lvl_nav.sector_polygons(sm)
    u = unary_union([polys[s['id']] for s in sm['sectors'] if s['type'] == lvl_nav.TT['RIO_POCO_PROFUNDO']])
    piece = max([g for g in lvl_nav.polys_of(u) if g.bounds[0] > 20000], key=lambda g: g.area)
    lum = ndimage.gaussian_filter(img.astype(float).mean(-1), 6)
    pts = []
    for x in np.arange(27000, 57500, 700):
        inter = piece.intersection(LineString([(x, 0), (x, SIZE)]))
        if inter.is_empty:
            continue
        b = inter.bounds
        c, r = lvl_tex.world_to_px(x, (b[1] + b[3]) / 2, SIZE, TEX)
        rows = np.arange(int(r) - 90, int(r) + 90)
        best = rows[np.argmin(lum[rows, int(c)])]
        pts.append((float(c), float(best)))
    sm_ = ndimage.uniform_filter1d(np.array(pts), 5, axis=0)
    return [tuple(p) for p in sm_]


def paths():
    """Two mule tracks: west route over the west ford, east route over the east ford up to the aul."""
    def g(x):
        return gorge_z(x)
    east = [ATT_CENTER, (40000, 21000), (50000, 28500), (57000, 34500), (FORDS[1][0], g(FORDS[1][0])),
            (60500, 44000), (57500, 48000), VILLAGE, (51000, 54500), (46500, 59000), DEF_CENTER]
    west = [ATT_CENTER, (29000, 22000), (27000, 28500), (FORDS[0][0], g(FORDS[0][0])), (28500, 41000),
            (31500, 48500), (36500, 56000), DEF_CENTER]
    out = []
    rng = np.random.default_rng(SEED + 7)
    for line in (east, west):
        pts = np.array(line, float)
        dense = [pts[0]]                                    # wander: jitter the points inserted between the
        for a, b in zip(pts[:-1], pts[1:]):                 # control points (fords, aul stay on the track)
            n = max(1, int(np.hypot(*(b - a)) / 2500.0))
            dense += [a + (b - a) * k / n + (rng.normal(0, 700.0, 2) if k < n else 0) for k in range(1, n + 1)]
        pts = np.array(dense)
        for _ in range(4):                                  # Chaikin smoothing
            q = [pts[0]]
            for a, b in zip(pts[:-1], pts[1:]):
                q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
            q.append(pts[-1])
            pts = np.array(q)
        out.append([tuple(p) for p in pts])
    return out


def texture(h, trees, k0, L):
    """4096 x 4096 north-up terrain texture from original art (Escocia meadows and stream bed, Helvetic grass,
    limestone and the aul's yards, Swedish snow), tree shadows painted like the originals'."""
    rng = np.random.default_rng(SEED + 2)
    hel = composite('51', '51RepublicaHelvetica.lvl')
    esc = composite('02', '02Escocia.lvl')
    sue = composite('38', '38Suecia.lvl')
    shape = (TEX, TEX)
    # terrain fields at texture resolution (row 0 = north), smooth (cubic) so that no cell blocks show
    hz = ndimage.zoom(h.astype(np.float32)[::-1], TEX / N, order=3)[:TEX, :TEX]
    sl = ndimage.gaussian_filter(slope_deg(h)[::-1], 0.8)
    slope = ndimage.zoom(sl, TEX / N, order=3)[:TEX, :TEX]
    rows, cols = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    Xw = cols / TEX * SIZE
    Zw = SIZE - rows / TEX * SIZE
    nz = fbm(Xw[::8, ::8], Zw[::8, ::8], rng, 6000.0, 4)
    noise = ndimage.zoom(nz, 8, order=1)[:TEX, :TEX]
    nf = fbm(Xw[::4, ::4], Zw[::4, ::4], rng, 1200.0, 3)
    fine = ndimage.zoom(nf, 4, order=1)[:TEX, :TEX]
    # materials: Escocia meadow, drier Helvetic grass on slopes and in patches
    grass_e = lvl_tex.patch_synth(shape, [(esc, b) for b in SRC_GRASS_ESC], rng, orient=False)
    grass_h = lvl_tex.patch_synth(shape, [(hel, b) for b in SRC_GRASS_HEL], rng, orient=False)
    w_dry = np.clip((noise - 0.45) * 2.5 + (slope - 14) / 28.0 + (fine - 0.5) * 0.6, 0, 1)
    img = grass_e * (1 - w_dry[..., None]) + grass_h * w_dry[..., None]
    del grass_e, grass_h
    # grey rock (Escocia outcrops, some Helvetic limestone) on steep ground and the gorge walls
    rock = lvl_tex.patch_synth(shape, [(esc, b) for b in SRC_ROCK_ESC] * 2 + [(hel, b) for b in SRC_ROCK_HEL], rng,
                               patch=256, step=160) * 0.86
    d_g, ford = gorge_profile(Xw[::4, ::4], Zw[::4, ::4])
    d_g = ndimage.zoom(d_g, 4, order=1)[:TEX, :TEX]
    ford = ndimage.zoom(ford, 4, order=1)[:TEX, :TEX]
    w_rock = np.clip((slope - 31) / 10.0 + (noise - 0.5) * 0.9 + (fine - 0.5) * 1.2, 0, 0.92)
    w_rock = np.maximum(w_rock, np.clip((1 - smoothstep(800, 2600, d_g + 500 * (fine - 0.5))) * (1 - ford), 0, 1))
    img = img * (1 - w_rock[..., None]) + rock * w_rock[..., None]
    # snow on the high ground, broken by rock
    snow = lvl_tex.patch_synth(shape, [(sue, b) for b in SRC_SNOW_SUE], rng, patch=320, step=224) * 0.8
    w_snow = np.clip((hz - 13800) / 1300.0 + (noise - 0.5) * 1.2 + (fine - 0.5) * 1.0, 0, 1)         * (1 - smoothstep(38, 52, slope))
    img = img * (1 - w_snow[..., None]) + snow * w_snow[..., None]
    del snow
    nh = fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 320.0, 3)
    hf = ndimage.zoom(nh, 2, order=1)[:TEX, :TEX]            # high-frequency noise for ragged edges
    # gorge bed: wet gravel (darkened rock) with a dark torrent and a little foam (no water mesh in this map)
    bedw = 1 - smoothstep(450, 800, d_g + 250 * (fine - 0.5) + 180 * (hf - 0.5))
    gravel = rock * np.array([0.7, 0.72, 0.76], np.float32)
    img = img * (1 - bedw[..., None]) + gravel * bedw[..., None]
    water = (1 - smoothstep(60, 230, d_g + 220 * (hf - 0.5) + 120 * (fine - 0.5))) * 0.85
    foam = np.clip((hf - 0.66) * 6, 0, 1) * (d_g < 180)
    wcol = gravel * 0.45 + np.array([14, 22, 26], np.float32)
    wcol = wcol * (1 - foam[..., None]) + np.array([132, 140, 142], np.float32) * foam[..., None]
    img = img * (1 - water[..., None]) + wcol * water[..., None]
    del rock, gravel, wcol
    # mule tracks: Helvetic path colour, textured by the ground under them, ragged edges
    pc = np.array([140, 120, 62], np.float32)
    lum = img.mean(-1, keepdims=True)
    detail = lum / (ndimage.uniform_filter(lum[..., 0], 31)[..., None] + 1.0)
    for line in paths():
        pl = [tuple(lvl_tex.world_to_px(x, z, SIZE, TEX)) for x, z in line]
        sub = 2
        dd2, ss2, _ = lvl_tex.polyline_frame(cols[::sub, ::sub], rows[::sub, ::sub], pl)
        dd2 = ndimage.zoom(dd2, sub, order=1)[:TEX, :TEX]
        wob = (noise - 0.5) * 6 + (hf - 0.5) * 7
        w_p = (1 - smoothstep(2.5, 7.0, dd2 + wob)) * 0.72 * (1 - (d_g < 900) * (1 - ford))
        rut = 1 - 0.18 * np.exp(-((np.abs(dd2) - 2.2) / 0.9) ** 2)
        col = pc * (0.55 + 0.45 * detail) * (rut * (0.9 + 0.2 * hf))[..., None]
        img = img * (1 - w_p[..., None]) + col * w_p[..., None]
    # painted macro shading like the originals (soft darker patches)
    img *= (0.88 + 0.24 * noise)[..., None]
    # tree shadows (cast north-west, as painted in the originals)
    tpx = [tuple(lvl_tex.world_to_px(x, z, SIZE, TEX)) for x, y, z in trees]
    img *= lvl_tex.tree_shadows(shape, tpx, rng)[..., None]
    # the aul: the original painted yards and house shadows around the houses (they did not move)
    dv = np.hypot(Xw - VILLAGE[0], Zw - VILLAGE[1])
    w_v = 1 - smoothstep(1300, 2600, dv)
    img = img * (1 - w_v[..., None]) + hel.astype(np.float32) * w_v[..., None]
    # border band: back to the original texture where the heights are the template's
    def band(e0, e1):
        return smoothstep(e0, e1, Xw) * smoothstep(e0, e1, SIZE - Xw) * smoothstep(e0, e1, Zw) * smoothstep(e0, e1, SIZE - Zw)
    A = band(1200.0, 6000.0)
    img = img * A[..., None] + hel.astype(np.float32) * (1 - A[..., None])
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ build
def build(write=True):
    m = lvl.load(TEMPLATE)
    rng = np.random.default_rng(SEED + 1)
    h0 = m.heights()
    ob = m.get(lvl.OBJECTLIST)
    houses = [i for i, o in enumerate(ob['instances']) if o['type'] == lvl.TO_CONSTRUCCION]
    pads = [(ob['instances'][i]['matrix'][12], ob['instances'][i]['matrix'][14], 750.0) for i in houses]
    h = heightmap(h0, pads)
    k0, L = fit_shade(m)
    m.set_heights(h, make_shade(k0, L), carry=False)

    def H(x, z):
        return float(m.height_at(x, z, h))

    # --- buildings follow their pads (instance, garrison posts, interior sectors)
    sm0 = m.get(lvl.SECTORMAP)
    P0 = sm0['points']
    sec_dy = {}
    for i in houses:
        o = ob['instances'][i]
        x, z = o['matrix'][12], o['matrix'][14]
        dy = H(x, z) - o['matrix'][13]
        lvl.shift_instance(o, 0.0, dy, 0.0)
        for sid in m.construction_sectors(o):
            sec_dy[sid] = dy
        for d in ob['instances']:                      # the grass decor laid around the house
            if d['type'] == lvl.TO_DECORADO and math.hypot(d['matrix'][12] - x, d['matrix'][14] - z) < 400:
                lvl.shift_instance(d, 0.0, dy, 0.0)

    # --- trees: the template's 253 trees moved to the new forest patches
    tv = bytearray(open(os.path.join(ESC, '51', 'Models', 'Arboles.V3D'), 'rb').read())
    T = lvl_v3d.trees(tv)
    avoid = [(ATT_CENTER[0], ATT_CENTER[1], 11000.0), (DEF_CENTER[0], DEF_CENTER[1], 11000.0),
             (VILLAGE[0], VILLAGE[1], 3800.0)]
    def edge_of(x, z):
        return min(x, SIZE - x, z, SIZE - z)
    stay = [(t, c) for t, c in T if edge_of(*lvl_v3d.translation(tv, t['m2'])[::2]) < 4500.0]   # painted in the rim
    T = [(t, c) for t, c in T if edge_of(*lvl_v3d.translation(tv, t['m2'])[::2]) >= 4500.0]
    tpos = place_trees(h, len(T), rng, avoid)
    trees = []
    for (trunk, canopies), (x, z) in zip(T, tpos):
        x0, y0, z0 = lvl_v3d.translation(tv, trunk['m2'])
        y = H(x, z) - 15.0
        lvl_v3d.move_tree(tv, trunk, canopies, x - x0, y - y0, z - z0)
        trees.append((x, y, z))
    for trunk, canopies in T[len(tpos):]:             # not enough room: sink the rest out of sight
        lvl_v3d.move_tree(tv, trunk, canopies, 0.0, -20000.0, 0.0)
    kept_trees = [tuple(lvl_v3d.translation(tv, t['m2'])) for t, c in stay]
    tr = np.array(trees + kept_trees)
    lvl_v3d.set_global_bbox(tv, [float(tr[:, 0].min() - 800), float(tr[:, 1].min() - 50), float(tr[:, 2].min() - 800)],
                            [float(tr[:, 0].max() + 800), float(tr[:, 1].max() + 2500), float(tr[:, 2].max() + 800)])

    # --- sector map
    ax = np.arange(N) * CELL
    X, Z = np.meshgrid(ax, ax)
    sl = slope_deg(h)
    d, ford = gorge_profile(X, Z)
    near_aul = np.hypot(X - VILLAGE[0], Z - VILLAGE[1]) < 2500
    from shapely.geometry import LineString, Point, box
    from shapely.ops import unary_union
    bed = LineString(GORGE).buffer(900.0, 4)
    ford_boxes = unary_union([box(fx - 2200, 0, fx + 2200, SIZE) for fx, _ in FORDS])
    regions = []
    # (no BOSQUE sectors: forest has no hard-coded troop modifier, only footstep sounds; it would triple the
    # sector count)
    snow = mask_polygons(ndimage.binary_opening((h > 14200) & (sl < 33), iterations=1), simplify=350.0, min_cells=8)
    if snow is not None:
        regions.append((snow, dict(type=lvl_nav.TT['NIEVE_NO_PROFUNDA'], a=1)))
    # impassable: the gorge walls (outside the fords) and big steep mountain faces (> 42 deg, heavily simplified);
    # the rest of the mountains stays passable as on the original Helvetic map
    walls = LineString(GORGE).buffer(2500.0, 4).difference(ford_boxes)
    steep = mask_polygons(ndimage.binary_opening(sl > 42, iterations=2), simplify=600.0, min_cells=40)
    cliff = unary_union([walls] + ([steep] if steep is not None else []))
    regions.append((cliff, dict(type=lvl_nav.TT['OBSTACULO'], a=0)))
    regions.append((bed.difference(ford_boxes), dict(type=lvl_nav.TT['RIO_PROFUNDO'], a=0)))
    regions.append((bed.intersection(ford_boxes), dict(type=lvl_nav.TT['RIO_POCO_PROFUNDO'], a=1)))
    keep = []
    for sdict in sm0['sectors']:
        if sdict['id'] in sec_dy:
            dy = sec_dy[sdict['id']]
            sd = dict(sdict)
            sd['p1'] = [sd['p1'][0], sd['p1'][1] + dy, sd['p1'][2]]
            keep.append(([(P0[i][0], P0[i][2], P0[i][1] + dy) for i in sdict['poly']], sd))
    sm, kmap = lvl_nav.build(SIZE, regions, keep, height=H)
    for s_ in sm['sectors']:
        if s_['type'] != lvl_nav.TT['INTERIOR']:
            s_['c'] = 1 if math.degrees(math.acos(max(-1.0, min(1.0, abs(s_['p2'][1]))))) > 10 else 0
    probs = lvl_nav.validate(sm, SIZE)
    assert not probs, probs[:5]
    m.chunk(lvl.SECTORMAP).data = sm
    m.remap_sector_ids({keep[k][1]['id']: new for k, new in kmap.items()})
    m.chunk(lvl.GRAFOIA).data = lvl_nav.build_graph(sm, 20)

    # --- logic: height planes (detection bonus between them), troop areas, zones, locations, sounds
    tl = m.get(lvl.TERRAINLOGIC)
    inner = h[20:-20, 20:-20]
    tl['planes'] = [float(np.percentile(inner, 50)), float(np.percentile(inner, 95))]
    posts = m.get(lvl.POSTROOPER)
    shift = {}
    for side, center in ((4, ATT_CENTER), (8, DEF_CENTER)):
        grp = [p for p in posts if p['flags'] & side]
        cx = np.mean([p['pos'][0] for p in grp])
        cz = np.mean([p['pos'][2] for p in grp])
        shift[side] = (center[0] - cx, center[1] - cz)
        for p in grp:
            p['pos'][0] += shift[side][0]
            p['pos'][2] += shift[side][1]
            p['pos'][1] = H(p['pos'][0], p['pos'][2])
    for a in m.get(lvl.ARBZONES):
        # deployment zones: bando 1 = attacker (troop flag 4), bando 0 = defender (flag 8) - checked on the template,
        # whose bando-1 zone holds the attacker's troop areas; kept inside the map
        side = {1: 4, 0: 8}.get(a['bando'])
        if side and a['type'] == 2:
            a['poly'] = [[min(max(x + shift[side][0], 300.0), SIZE - 300.0),
                          min(max(z + shift[side][1], 300.0), SIZE - 300.0)] for x, z in a['poly']]
    locs = m.get(lvl.LOCATIONS)
    meadows = [(47000.0, 56000.0), (24000.0, 47000.0), (61000.0, 26000.0)]
    k = 0
    for l in locs:
        if l['name'] == 'LOC_Atacante':
            l['pos'][0], l['pos'][2] = ATT_CENTER
        elif l['name'] == 'LOC_Defensor':
            l['pos'][0], l['pos'][2] = DEF_CENTER
        elif l['type'] == 1 and math.hypot(l['pos'][0] - VILLAGE[0], l['pos'][2] - VILLAGE[1]) > 5000:
            l['pos'][0], l['pos'][2] = meadows[k % len(meadows)]
            k += 1
        l['pos'][1] = H(l['pos'][0], l['pos'][2]) - l.get('ybias', 0.0)
    gx = 40000.0
    locs.append(dict(type=0, name='LOC_Garganta', uid=0, pos=[gx, H(gx, gorge_z(gx)) + 1500.0, gorge_z(gx)],
                     angles=[0.0, 0.0], particles=locs[-1]['particles'], ciclico=0, frames=0, escala=1.0, ybias=0.0))
    snd = m.get(lvl.SOUND)
    pos_ = [e for e in snd['positional'] if e[0] != 'S_RIO']
    for e in pos_:
        e[4][1] = H(e[4][0], e[4][2]) + 300.0
    for x in np.linspace(4000, 71000, 7):
        z = gorge_z(x)
        pos_.append(['S_RIO', 100, 14000.0, 2000.0, [float(x), H(x, z) + 200.0, float(z)]])
    snd['positional'] = pos_
    if write:
        os.makedirs(os.path.join(OUT, 'Models'), exist_ok=True)
        m.save(os.path.join(OUT, LVL_NAME))
        open(os.path.join(OUT, 'Models', 'Arboles.V3D'), 'wb').write(bytes(tv))
    return m, h, trees, tv


# ------------------------------------------------------------------ scenario folder, minimap, previews
TEXTS = {
    'LTEXT_TEXTUISECUENCIAS_CAUCASO_ATACANTE_1':
        'The mountaineers of the Caucasus have made this valley their fortress. Cross the gorge at the fords '
        'and give them no rest!',
    'LTEXT_TEXTUISECUENCIAS_CAUCASO_ATACANTE_2':
        'Our objective is the aul on the far slope. Take the village and hold it, and the valley is ours.',
    'LTEXT_TEXTUISECUENCIAS_CAUCASO_DEFENSOR_1':
        'The invaders have come up our valley. The gorge and the mountains fight with us: let them bleed at the '
        'fords!',
    'LTEXT_TEXTUISECUENCIAS_CAUCASO_DEFENSOR_2':
        'Hold the aul at all costs. As long as the village is ours, every attack will break on our slopes.',
}
INTRO = '''-- --------------------------------------------
-- Caucasus (scenario %(scen)s, generated by tools/lvl_caucasus.py from the 51 intro)
-- --------------------------------------------
function inicia_secuencia()
  estado_defecto_secuencia()
  secuencia1();
end

-- panorama of the gorge (a camera relative to a location adapts to the new relief)
function secuencia1 ()
  estado_defecto_secuencia()
  muestra_tropas_amigas()
  local time1 = nil
  local time2 = nil
  local maxTime = nil
  time1 = reproduce_camara_relativa ("game/gameModes/Batalla/Camaraspresentacion/CamaraEdifBg01.V3D", "LOC_Garganta", false, 1.6 )
  time2 = reproduce_texto ("LTEXT_TEXTUISECUENCIAS_CAUCASO_%(side)s_1")
  maxTime = max (time1, time2)
  temporizador ( maxTime, "secuencia2" )
  fade_color (0,0,0,150, 0,0,0,0,  -0,0.5)
  fade_color (204,215,228,0, 204,215,228,255,    maxTime-0.5,0.5)
end

-- the aul
function secuencia2 ()
  estado_defecto_secuencia()
  muestra_tropas_amigas()
  local time1 = nil
  local time2 = nil
  local maxTime = nil
  time1 = reproduce_camara_relativa ("game/gameModes/Batalla/Camaraspresentacion/CamaraEdifBg03.V3D", "LOC_Aldea", false, 0.9 )
  time2 = reproduce_texto ("LTEXT_TEXTUISECUENCIAS_CAUCASO_%(side)s_2")
  maxTime = max (time1, time2)
  temporizador ( maxTime, "comenzar_batalla" )
  fade_color (204,215,228,255, 204,215,228,0,0,0.5)
  fade_color (204,215,228,0, 224,235,248,255,maxTime-2,2)
end
'''
CAMARA = '''#---------------------------------------------
#    Script de definicion de camara de mapa (Caucasus, scenario %s)
#---------------------------------------------
.ATACANTE
[
  .ANGLE     [ 17.1    1.8    ]
  .TARGET    [ %.1f  %.1f   ]

]
.DEFENSOR
[
  .ANGLE     [ 31.8    180.9    ]
  .TARGET    [ %.1f  %.1f   ]

]
'''


def shade_grid(h, k0, L):
    return np.clip(k0 + normals(h) @ L, 63 / 255.0, 1.0)


def topdown(tex, h, k0, L, px=1024):
    """What the camera sees from straight above: texture x baked vertex shade (x2, the terrain's modulate)."""
    t = np.asarray(ndimage.zoom(tex.astype(np.float32), (px / tex.shape[0], px / tex.shape[1], 1), order=1))
    sh = ndimage.zoom(shade_grid(h, k0, L)[::-1], px / N, order=1)[:px, :px]
    return np.clip(t * sh[..., None] * 1.9, 0, 255).astype(np.uint8)


def minimap(tex, h, k0, L, m):
    """256 x 256 32-bit TGA like the originals: map in the top-left 231 x 231, alpha 212 inside, a 243 frame,
    roofs drawn in the original orange."""
    img = topdown(tex, h, k0, L, 231).astype(np.float32) * 0.62
    ob = m.get(lvl.OBJECTLIST)
    for o in ob['instances']:
        if o['type'] == lvl.TO_CONSTRUCCION:
            c, r = lvl_tex.world_to_px(o['matrix'][12], o['matrix'][14], SIZE, 231)
            img[int(r) - 2:int(r) + 2, int(c) - 2:int(c) + 3] = (196, 98, 52)
    out = np.zeros((256, 256, 4), np.uint8)
    out[..., :3] = np.round(img.reshape(-1, 3).mean(0)).astype(np.uint8)
    out[:231, :231, :3] = np.clip(img, 0, 255).astype(np.uint8)
    out[:231, :231, 3] = 212
    out[0, :231, 3] = out[230, :231, 3] = out[:231, 0, 3] = out[:231, 230, 3] = 243
    return out


def overlay(base, m, px=1024):
    """Deployment areas, zones, sector types, AI graph and buildings over a top-down image."""
    from PIL import Image, ImageDraw
    im = Image.fromarray(base).convert('RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)

    def P(x, z):
        c, r = lvl_tex.world_to_px(x, z, SIZE, px)
        return (float(c), float(r))
    sm = m.get(lvl.SECTORMAP)
    pts = sm['points']
    col = {lvl_nav.TT['OBSTACULO']: (200, 30, 30, 90), lvl_nav.TT['RIO_PROFUNDO']: (20, 40, 160, 150),
           lvl_nav.TT['RIO_POCO_PROFUNDO']: (60, 170, 255, 170), lvl_nav.TT['NIEVE_NO_PROFUNDA']: (255, 255, 255, 60),
           lvl_nav.TT['INTERIOR']: (255, 120, 0, 200)}
    for s in sm['sectors']:
        poly = [P(pts[i][0], pts[i][2]) for i in s['poly']]
        c = col.get(s['type'])
        d.polygon(poly, outline=(255, 255, 255, 40), fill=c)
    for n in m.get(lvl.GRAFOIA)['nodes']:
        d.polygon([P(*q) for q in n['poly']], outline=(255, 255, 255, 170))
    for a in m.get(lvl.ARBZONES):
        c = (255, 230, 0, 255) if a['type'] == 2 else (255, 140, 0, 255)
        d.line([P(*q) for q in a['poly'] + a['poly'][:1]], fill=c, width=3)
    for p in m.get(lvl.POSTROOPER):
        x, z = p['pos'][0], p['pos'][2]
        w_, h_ = p['size']
        ca, sa = math.cos(p['angle']), math.sin(p['angle'])
        q = [(x + ca * dx + sa * dz, z - sa * dx + ca * dz) for dx, dz in       # clockwise angle (see lvl.check)
             ((-w_ / 2, -h_ / 2), (w_ / 2, -h_ / 2), (w_ / 2, h_ / 2), (-w_ / 2, h_ / 2))]
        d.polygon([P(*v) for v in q], outline=(0, 255, 255, 255) if p['flags'] & 4 else (255, 0, 255, 255), width=2)
    for l in m.get(lvl.LOCATIONS):
        c = P(l['pos'][0], l['pos'][2])
        d.ellipse([c[0] - 4, c[1] - 4, c[0] + 4, c[1] + 4], outline=(255, 255, 0, 255))
        if l.get('name'):
            d.text((c[0] + 6, c[1] - 6), l['name'], fill=(255, 255, 0, 255))
    return np.array(Image.alpha_composite(im, lay).convert('RGB'))


def write_scenario(m, tex, h, k0, L):
    """Everything make_map needs: the scenario folder and the minimap."""
    mdir = os.path.join(OUT, 'Models')
    src = os.path.join(ESC, '51', 'Models')
    for fn in os.listdir(src):                    # houses, decor, sky, outside scenery, tree textures, detail
        if fn.lower().endswith('.scc') or fn == 'Arboles.V3D' or (fn.startswith('T00') and fn.endswith('.tga')):
            continue
        shutil.copyfile(os.path.join(src, fn), os.path.join(mdir, fn))
    lvl_tex.write_tiles(mdir, tex)
    shutil.copyfile(os.path.join(ESC, '51', 'Clima.sb'), os.path.join(OUT, 'Clima.sb'))
    open(os.path.join(OUT, 'Camara.sb'), 'w', encoding='latin1', newline='\r\n').write(
        CAMARA % (SCEN, ATT_CENTER[0], ATT_CENTER[1] - 1300, DEF_CENTER[0], DEF_CENTER[1] + 4000))
    for side, fn in (('ATACANTE', 'introAtacante.lua'), ('DEFENSOR', 'introDefensor.lua')):
        open(os.path.join(OUT, fn), 'w', encoding='latin1', newline='\r\n').write(INTRO % dict(scen=SCEN, side=side))
    mm = minimap(tex, h, k0, L, m)
    red = np.zeros((256, 256, 3), np.uint8)                # network-game minimap: 144 x 144 in a magenta frame
    red[0:146, 0:146] = (252, 0, 255)
    red[1:145, 1:145] = np.asarray(ndimage.zoom(mm[:231, :231, :3].astype(np.float32), (144 / 231, 144 / 231, 1),
                                                order=1)).clip(0, 255).astype(np.uint8)[:144, :144]
    lvl_tex.write_tga24(os.path.join(ROOT, 'build', 'battlemaps', 'minimap_red', SCEN + 'Caucaso.tga'), red)
    json.dump(dict(scenario=SCEN, lvl=LVL_NAME, minimap=SCEN + 'Caucaso.tga', template='51', texts=TEXTS,
                   pool_key=POOL_KEY, minimap_red=SCEN + 'Caucaso.tga'),
              open(os.path.join(OUT, 'battlemap.json'), 'w', encoding='utf8'), indent=1)
    lvl_tex.write_tga32(os.path.join(ROOT, 'build', 'battlemaps', 'minimap', SCEN + 'Caucaso.tga'), mm)
    return mm


if __name__ == '__main__':
    m, h, trees, tv = build()
    sm = m.get(lvl.SECTORMAP)
    import collections
    print('sectors', len(sm['sectors']), dict(collections.Counter(hex(s['type']) for s in sm['sectors'])),
          'links', len(sm['links']), 'graph', len(m.get(lvl.GRAFOIA)['nodes']), 'trees', len(trees))
    m0 = lvl.load(TEMPLATE)
    k0, L = fit_shade(m0)
    tex = texture(h, trees, k0, L)
    mm = write_scenario(m, tex, h, k0, L)
    os.makedirs(PREVIEW, exist_ok=True)
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_heightmap.png'), height_image(h))
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_heightmap_original51.png'), height_image(m0.heights()))
    td = topdown(tex, h, k0, L)
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_topdown.png'), td)
    hel = composite('51', '51RepublicaHelvetica.lvl')
    td0 = topdown(hel, m0.heights(), k0, L)
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_topdown_original51.png'), td0)
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_overlay.png'), overlay(td, m))
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_compare.png'),
                     np.concatenate([td0[::2, ::2], np.full((512, 8, 3), 255, np.uint8), td[::2, ::2]], 1))
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_minimap.png'), mm[..., :3])
    lvl_tex.save_png(os.path.join(PREVIEW, 'lvl_caucasus_detail.png'),
                     np.clip(tex[1700:2700, 2500:3500].astype(np.float32) * 1.9, 0, 255).astype(np.uint8))
    # round trip of the written map
    raw = open(os.path.join(OUT, LVL_NAME), 'rb').read()
    assert lvl.Lvl(raw).pack() == raw
    for c in lvl.Lvl(raw).walk():
        if c.id in lvl.CODECS:
            lvl.Lvl(raw).get(c.id)
    print('wrote', OUT)

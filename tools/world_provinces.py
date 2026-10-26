"""Province shapes for the extended map (1789 proposal), in world coordinates.

Land = the same land/sea test the map art uses (Natural Earth through warp.game_to_lonlat), on a STEP grid.
Cells covered by an existing province, and the old map art area, are not available. Each free land cell goes to
the nearest proposal seed (Voronoi in map space); a province keeps the connected piece around its seed.
Borders are traced on the grid, split into chains at points where the neighbour changes, and every chain is
simplified once, so two neighbours share exactly the same border.
Writes build/world_provinces.json: {key: {name, owner, region, note, poly: [[x, z], ...], seed: [x, z]}}.
"""
import os, sys, json, math, re
import numpy as np
from scipy import ndimage
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warp, meshgen as MG, gen_world as GW, render_map as RM
from igmod import V3D
import struct

ROOT = GW.ROOT
STEP = 40.0
X0, X1 = MG.COLS[0], MG.COLS[0] + 9 * MG.TILE_W
Z0, Z1 = MG.ROWS[0] - 3 * MG.TILE_H, MG.ROWS[4]
# historical fixes (re_tools/report_history.md): Natural Earth admin-1 code -> proposal id
ADMIN_OVERRIDE = {
    'SAU-845': 'hejaz', 'SAU-848': 'hejaz', 'SAU-885': 'hejaz',
    'SAU-846': 'najd', 'SAU-847': 'najd', 'SAU-1098': 'najd',
    'SAU-886': 'yemen', 'SAU-887': 'yemen', 'SAU-1096': 'yemen', 'OMN-2411': 'yemen',
    'OMN-2425': 'muscat', 'OMN-2424': 'muscat', 'OMN-2414': 'muscat', 'OMN-2405': 'muscat', 'OMN-2406': 'muscat',
    'OMN-5496': 'muscat', 'OMN-2426': 'muscat', 'OMN-5497': 'muscat', 'OMN-2404': 'muscat',
    'ARE-341': 'muscat', 'ARE-348': 'muscat', 'ARE-338': 'muscat', 'ARE-344': 'muscat', 'ARE-349': 'muscat', 'ARE-339': 'muscat',
    'EGY-1556': 'upperegypt', 'EGY-1550': 'upperegypt', 'EGY-1551': 'upperegypt', 'LBY-2969': 'fezzan',
    'NER-92': 'bornu', 'NER-796': 'bornu', 'CMR-1462': 'bornu',
    'NER-91': 'hausa', 'NER-93': 'hausa', 'NGA-2879': 'hausa',
    'NER-4859': 'timbuktu', 'NER-94': 'timbuktu',
    'SDN-883': 'darfur', 'SDN-882': 'darfur',
    'AGO-1882': 'kongo', 'AGO-1881': 'kongo', 'AGO-1885': 'loango', 'ZMB-5511': 'kazembe',
    'ZAF-1206': 'kalahari', 'ZAF-1201': 'kalahari', 'ZAF-1208': 'kalahari', 'ZAF-1210': 'kalahari',
    'LSO-1213': 'kalahari', 'LSO-1211': 'kalahari', 'LSO-1212': 'kalahari', 'LSO-1214': 'kalahari', 'LSO-1215': 'kalahari',
    'LSO-1202': 'kalahari', 'LSO-1203': 'kalahari', 'LSO-3453': 'kalahari', 'LSO-1204': 'kalahari', 'LSO-1205': 'kalahari',
    'BGD-2488': 'bengal', 'IND-3254': 'nepal',
    'PAK-1112': 'peshawar', 'PAK-1109': 'kashmir', 'PAK-1111': 'kashmir',
    'TJK-367': 'kokand', 'UZB-361': 'kokand', 'UZB-362': 'kokand',
    'RUS-2605': 'mongolia', 'RUS-2609': 'amur', 'RUS-2613': 'amur', 'RUS-2611': 'amur', 'RUS-2610': 'irkutsk',
    'PRK-3307': 'korea', 'PRK-3314': 'korea', 'PRK-5495': 'korea',
}
SEED_FIX = {'swahili': (38.6, -6.8), 'bombay': (73.3, 18.2),     # seed on the mainland, not on Zanzibar
            'kandahar': (65.71, 31.62), 'punjab': (74.34, 31.55),  # Kandahar city, Lahore
            'okhotsk': (143.24, 59.36)}                            # Okhotsk town (Amur below is Qing)
OLD_G = (1860.0, 1895.0)          # old map art (g px): x < 1860 and y < 1895 stays as it is


def world_to_g(x, z):
    return (x - MG.COLS[0]) / MG.TILE_W * 512.0, (MG.ROWS[4] - z) / MG.TILE_H * 512.0


def proposal():
    html = open(os.path.join(ROOT, 'build', 'forslagskart_1789.html'), encoding='utf8').read()
    block = html[html.index('const P = ['):html.index('];', html.index('const P = ['))]
    rows = re.findall(r"\['([^']+)','([^']+)',(-?[\d.]+),(-?[\d.]+),'([A-Z]+)','([^']+)','([^']*)'\]", block)
    return [dict(id=a, name=b, lon=float(c), lat=float(d), owner=e, region=f, note=g) for a, b, c, d, e, f, g in rows]


def existing_labels(nx, nz):
    """Grid of existing province ids (by mesh name index), -1 = none. Uses the built mod model."""
    p = os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'Gestion', 'Mapa', 'MapaGestionVolumenes.V3D')
    d = open(p, 'rb').read()
    v = V3D(d)
    lab = -np.ones((nz, nx), np.int32)
    names = []
    from PIL import ImageDraw
    img = Image.new('I', (nx, nz), -1); dr = ImageDraw.Draw(img)
    for k, (st, en, name) in enumerate(v.blocks):
        if name.startswith('W') and name[1:2].isupper():
            continue                                   # our own world provinces from an earlier build
        b = d[st:en]; f = V3D.mesh_fields(b)
        tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]
        pts = [((x + tx - X0) / STEP, (Z1 - (z + tz)) / STEP) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        for t in range(0, len(idx), 3):
            dr.polygon([pts[i] for i in idx[t:t + 3]], fill=k, outline=k)
        names.append(name)
    return np.asarray(img, np.int32), names


def land_grid():
    nx = int(round((X1 - X0) / STEP)); nz = int(round((Z1 - Z0) / STEP))
    xs = X0 + (np.arange(nx) + 0.5) * STEP; zs = Z1 - (np.arange(nz) + 0.5) * STEP
    X, Zz = np.meshgrid(xs, zs)
    gx, gy = world_to_g(X, Zz)
    f = warp.game_to_lonlat()
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    ll = np.empty_like(pts)
    for i in range(0, len(pts), 200000):
        ll[i:i + 200000] = f(pts[i:i + 200000])[1]
    lon = ll[:, 0].reshape(nz, nx); lat = ll[:, 1].reshape(nz, nx)
    landim = np.asarray(Image.open(os.path.join(ROOT, 'build', 'land_lonlat.png'))).astype(float) / 255
    L = GW.sample(landim, (lon - GW.LON0) / GW.RES, (GW.LAT1 - lat) / GW.RES)
    L[(lon > 189.5) | (lon < GW.LON0 + 0.5) | (lat < -55)] = 0
    return L > 0.5, gx, gy, lon, lat, xs, zs


def trace_loops(mask):
    """Boundary loops (corner coordinates) of a boolean mask; returns the outer loop of the largest region."""
    lab, n = ndimage.label(mask)
    if not n:
        return None
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = lab == (int(np.argmax(sizes)) + 1)
    keep = ndimage.binary_fill_holes(keep)
    edges = {}
    ys, xs = np.nonzero(keep)
    H, W = keep.shape
    def cell(i, j):
        return 0 <= j < H and 0 <= i < W and keep[j, i]
    for j, i in zip(ys, xs):
        # corners: (i, j) top-left; walking with the region on the left (y down)
        if not cell(i, j - 1): edges[(i + 1, j)] = (i, j)
        if not cell(i + 1, j): edges[(i + 1, j + 1)] = (i + 1, j)
        if not cell(i, j + 1): edges[(i, j + 1)] = (i + 1, j + 1)
        if not cell(i - 1, j): edges[(i, j)] = (i, j + 1)
    start = min(edges)
    loop, p = [start], edges[start]
    while p != start:
        loop.append(p); p = edges[p]
    return loop, keep


def dp(pts, tol):
    if len(pts) < 3:
        return list(pts)
    a, b = np.array(pts[0], float), np.array(pts[-1], float)
    P = np.array(pts[1:-1], float)
    ab = b - a; L = np.hypot(*ab)
    if L < 1e-9:
        d = np.hypot(*(P - a).T)
    else:
        d = np.abs(ab[0] * (P[:, 1] - a[1]) - ab[1] * (P[:, 0] - a[0])) / L
    k = int(np.argmax(d))
    if d[k] > tol:
        return dp(pts[:k + 2], tol)[:-1] + dp(pts[k + 1:], tol)
    return [pts[0], pts[-1]]


def smooth(pts, it):
    """Chaikin corner cutting with fixed end points (shared chains stay identical for both neighbours)."""
    pts = [tuple(map(float, p)) for p in pts]
    for _ in range(it):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out[1] = pts[0]; out[-1] = pts[-1]
        pts = [p for k, p in enumerate(out) if k == 0 or p != out[k - 1]]
    return pts


def main(tol_cells=1.4):
    P = proposal()
    land, gx, gy, lon, lat, xs, zs = land_grid()
    nz, nx = land.shape
    ex, ex_names = existing_labels(nx, nz)
    old = (gx < OLD_G[0]) & (gy < OLD_G[1])
    free = land & (ex < 0) & ~old
    # seeds: nearest free land cell (in lon/lat) to each proposal point
    fy, fx = np.nonzero(free)
    seeds = []
    for p in P:
        if p['id'] in SEED_FIX:
            p['lon'], p['lat'] = SEED_FIX[p['id']]
        d = (lon[fy, fx] - p['lon']) ** 2 * math.cos(math.radians(p['lat'])) ** 2 + (lat[fy, fx] - p['lat']) ** 2
        k = int(np.argmin(d))
        seeds.append((fy[k], fx[k], math.sqrt(d[k])))
    # land pieces: islands and continents (narrow straits cut by one erosion step) and modern countries
    lab, ncomp = ndimage.label(ndimage.binary_erosion(land, iterations=1))
    if ncomp:
        _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
        comp = np.where(land, lab[iy, ix], 0)
    else:
        comp = np.zeros_like(land, int)
    ctry_r = np.load(os.path.join(ROOT, 'build', 'countries_lonlat.npy'))
    ci = np.clip(((lon - GW.LON0) / GW.RES).astype(int), 0, ctry_r.shape[1] - 1)
    cj = np.clip(((GW.LAT1 - lat) / GW.RES).astype(int), 0, ctry_r.shape[0] - 1)
    ctry = ctry_r[cj, ci].astype(int)
    if (ctry[land] < 0).any():                      # coastal cells just outside a country polygon: nearest country
        m = ctry < 0
        _, (iy, ix) = ndimage.distance_transform_edt(m, return_indices=True)
        ctry = np.where(m, ctry[iy, ix], ctry)
    sy = np.array([s[0] for s in seeds]); sx = np.array([s[1] for s in seeds])
    s_comp = comp[sy, sx]; s_ctry = ctry[sy, sx]
    from scipy.spatial import cKDTree
    own = np.empty(len(fx), int)
    keys = comp[fy, fx] * 1000 + ctry[fy, fx]
    for key in np.unique(keys):
        c, k = divmod(int(key), 1000)
        idx = np.nonzero(keys == key)[0]
        for cand in (np.nonzero((s_comp == c) & (s_ctry == k))[0], np.nonzero(s_comp == c)[0],
                     np.nonzero(s_ctry == k)[0], np.arange(len(seeds))):
            if len(cand):
                break
        tree = cKDTree(np.stack([sx[cand], sy[cand]], 1))
        _, j = tree.query(np.stack([fx[idx], fy[idx]], 1))
        own[idx] = cand[j]
    # whole admin-1 units (Natural Earth): each unit goes to the province holding most of its cells, so borders
    # follow real provincial lines instead of straight distance cuts
    adm_r = np.load(os.path.join(ROOT, 'build', 'admin1_lonlat.npy'))
    adm = adm_r[cj, ci]
    cell_adm = adm[fy, fx]
    seed_unit = adm[sy, sx]
    for u in np.unique(cell_adm):
        if u < 0:
            continue
        idx = np.nonzero(cell_adm == u)[0]
        inside = np.nonzero(seed_unit == u)[0]
        if len(inside) == 1:
            own[idx] = inside[0]                                   # the unit around a province's capital
        elif len(inside) > 1:
            tree = cKDTree(np.stack([sx[inside], sy[inside]], 1))  # several capitals: split by distance
            _, j = tree.query(np.stack([fx[idx], fy[idx]], 1))
            own[idx] = inside[j]
        else:
            votes = np.bincount(own[idx])
            own[idx] = int(np.argmax(votes))
    units = json.load(open(os.path.join(ROOT, 'build', 'admin1_units.json'), encoding='utf8'))
    code_ix = {u['code']: i for i, u in enumerate(units)}
    pid_ix = {p['id']: k for k, p in enumerate(P)}
    for code, prov in ADMIN_OVERRIDE.items():
        own[cell_adm == code_ix[code]] = pid_ix[prov]
    label = -np.ones((nz, nx), np.int32)
    label[fy, fx] = own
    # keep the connected piece around each seed; orphan pieces go to the neighbouring province that touches them most
    final = -np.ones_like(label)
    for k, (yy, xx, dist) in enumerate(seeds):
        m = label == k
        lab, n = ndimage.label(m)
        if not n or lab[yy, xx] == 0:
            continue
        final[lab == lab[yy, xx]] = k
    orphan = (label >= 0) & (final < 0)
    for _ in range(40):
        if not orphan.any():
            break
        grown = ndimage.grey_dilation(np.where(final >= 0, final + 1, 0), size=3) - 1
        take = orphan & (grown >= 0)
        final[take] = grown[take]
        orphan = (label >= 0) & (final < 0)
    # combined label grid for tracing borders: new provinces 0..n-1, existing provinces 1000+k, nothing -1
    comb = np.where(final >= 0, final, np.where(ex >= 0, 1000 + ex, -1))
    out = {}
    raw = {}
    for k, p in enumerate(P):
        m = final == k
        if m.sum() < 25:
            print('skip (too small)', p['name'], int(m.sum())); continue
        res = trace_loops(m)
        if res is None:
            continue
        loop, keep = res
        raw[k] = loop
    # split loops into chains at corners where the set of touching labels changes, simplify each chain once
    def corner_key(c):
        i, j = c
        s = set()
        for dj in (-1, 0):
            for di in (-1, 0):
                y, x = j + dj, i + di
                s.add(int(comb[y, x]) if 0 <= y < nz and 0 <= x < nx else -1)
        return frozenset(s)
    cache = {}
    for k, loop in raw.items():
        n = len(loop)
        junction = [len(corner_key(c)) >= 3 for c in loop]
        idx = [i for i in range(n) if junction[i]]
        if len(idx) < 2:
            # no junction: pick two far apart corners as artificial junctions
            idx = [0, n // 2]
        poly = []
        for a, b in zip(idx, idx[1:] + [idx[0] + n]):
            chain = [loop[i % n] for i in range(a, b + 1)]
            key = tuple(chain)
            rkey = tuple(reversed(chain))
            if rkey in cache:
                simp = list(reversed(cache[rkey]))
            elif key in cache:
                simp = cache[key]
            else:
                inland = all(-1 not in corner_key(cc) for cc in chain[1:-1]) and len(chain) > 2
                simp = smooth(dp(chain, 2.2), 3) if inland else dp(chain, tol_cells)
                cache[key] = simp
            poly.extend(simp[:-1])
        wpoly = [(float(X0 + i * STEP), float(Z1 - j * STEP)) for i, j in poly]
        wpoly = MG.ccw(wpoly)
        if not MG.is_simple(wpoly):
            import free_land
            wpoly = free_land.untangle(wpoly)
        p = P[k]
        yy, xx, dist = seeds[k]
        out[p['id']] = dict(name=p['name'], owner=p['owner'], region=p['region'], note=p['note'],
                            poly=[list(q) for q in wpoly], seed=[float(xs[xx]), float(zs[yy])], cells=int((final == k).sum()),
                            seed_err_deg=round(dist, 2))
    json.dump(out, open(os.path.join(ROOT, 'build', 'world_provinces.json'), 'w'))
    # preview
    rng = np.random.default_rng(1)
    pal = rng.integers(60, 230, (len(P) + 1, 3))
    img = np.zeros((nz, nx, 3), np.uint8); img[land] = (200, 190, 160); img[~land] = (110, 140, 160)
    img[ex >= 0] = (150, 150, 150)
    img[final >= 0] = pal[final[final >= 0]]
    Image.fromarray(img).resize((nx // 2, nz // 2)).save(os.path.join(ROOT, 'build', 'world_provinces_preview.png'))
    bad = [v['name'] for v in out.values() if not MG.is_simple(v['poly'])]
    print('provinces', len(out), 'not simple', bad, 'max verts', max(len(v['poly']) for v in out.values()))
    far = sorted(((v['seed_err_deg'], v['name']) for v in out.values()), reverse=True)[:6]
    print('largest seed moves (deg)', far)


if __name__ == '__main__':
    main()

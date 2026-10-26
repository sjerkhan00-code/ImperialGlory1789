"""Sea zones (maritime provinces) for the extended map: Atlantic coast of Africa, Indian Ocean, East Asia, Australia.

Method (mirrors tools/world_provinces.py):
  * sea = the land/sea test of the map art (build/land_lonlat.png through warp.game_to_lonlat) on the 40-unit grid,
    minus everything covered by an original province mesh (land or sea zone);
  * every zone has one or more seed points (lon/lat, 1789 names); each free sea cell goes to the nearest seed in
    world distance (Voronoi: straight open-sea borders, like the original zones), seeds of one zone merge;
  * a zone keeps the sea-connected piece around its seeds; fragments cut off by land go to the touching zone,
    lakes and unseeded water stay unassigned;
  * borders are traced on the grid and split into chains at junctions; every chain is simplified once, so two
    neighbours share exactly the same border polyline. Coast chains keep more detail than open-sea chains.
Outputs build/sea/sea_zones.json and build/sea/sea_zones.png (preview on build/kart_forhandsvisning.png).
Run from anywhere: python tools/art/sea/sea_zones.py
"""
import os, sys, json, math
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import meshgen as MG
import world_provinces as WP
from igmod import Mng

ROOT = WP.ROOT
OUT = os.path.join(ROOT, 'build', 'sea')
STEP = WP.STEP
X0, X1, Z0, Z1 = WP.X0, WP.X1, WP.Z0, WP.Z1

# ---------------------------------------------------------------------------------------------------------------
# Zones: key -> (name, [(lon, lat), ...] seeds).  Names in the style of late-18th-century English charts.
# Several seeds make one elongated zone along a coast; the Voronoi border between two zones is the bisector of
# their nearest seeds, which gives the straight open-sea borders of the original zones.
# ---------------------------------------------------------------------------------------------------------------
ZONES = {
    # --- Atlantic coast of Africa (the Cape route) ---
    'canary':      ('Canary Islands',          [('xz', -250, 3100), ('xz', -250, 2000), ('xz', -420, 900)]),
    'senegambia':  ('Coast of Senegambia',     [('xz', -300, -900), (-18.0, 12.0)]),
    'guinea':      ('Gulf of Guinea',          [(-9.0, 4.0), (-4.0, 2.5), (3.5, 3.5), (7.5, 1.5)]),
    'loango':      ('Coast of Loango',         [(9.5, -3.0), (11.0, -7.0)]),
    'angola':      ('Coast of Angola',         [(11.5, -12.0), (11.0, -16.0), (12.0, -21.0), (13.0, -26.0)]),
    'goodhope':    ('Cape of Good Hope',       [(16.5, -32.5), (19.5, -36.0), (24.0, -36.5), (28.5, -34.0)]),
    # --- open South Atlantic ("Ethiopic Sea" on 18th-century charts) and the Southern Ocean ---
    'ethiopic':    ('Ethiopic Sea',            [(-3.0, -6.0), (-4.0, -20.0), (-2.0, -35.0)]),
    'southern_w':  ('Southern Ocean (Cape)',   [(14.0, -46.0), (45.0, -44.0)]),
    # --- East Africa and the Arabian seas ---
    'mozambique':  ('Mozambique Channel',      [(32.0, -30.0), (34.5, -26.5), (40.0, -22.0), (40.5, -16.0), (42.0, -12.5)]),
    'zanzibar':    ('Coast of Zanzibar',       [(41.0, -7.5), (42.0, -2.5)]),
    'somali':      ('Coast of Ajan',           [(46.0, 2.0), (50.0, 7.0), (52.5, 11.0)]),
    'aden':        ('Gulf of Aden',            [(46.0, 12.5), (50.0, 13.0)]),
    'redsea':      ('Red Sea',                 [(42.0, 15.5), (39.0, 19.5), (36.5, 23.0), (34.5, 26.5)]),
    'gulf':        ('Persian Gulf',            [(50.0, 27.5), (52.5, 25.0), (58.5, 24.0), (61.5, 24.0)]),
    'arabian':     ('Arabian Sea',             [(60.0, 17.0), (64.0, 12.0), (56.0, 8.0)]),
    # --- open Indian Ocean ---
    'indian':      ('Indian Ocean',            [(54.0, -5.0), (72.0, -8.0), (88.0, -8.0), (63.0, -21.0), (80.0, -24.0), (72.0, 2.0),
                                                (75.0, -4.0), (97.0, -15.0), (52.0, -20.0), (49.0, -26.0), (52.0, -14.0)]),
    'southern_m':  ('Southern Ocean (Indian)', [(75.0, -41.0), (110.0, -46.0), (100.0, -30.0)]),
    # --- India and the Bay of Bengal ---
    'malabar':     ('Malabar Coast',           [(68.5, 22.5), (70.5, 19.5), (73.0, 14.0), (74.5, 9.5)]),
    'coromandel':  ('Coromandel Coast',        [(78.5, 7.5), (81.5, 11.5), (82.5, 15.5)]),
    'bengal':      ('Bay of Bengal',           [(87.5, 18.5), (89.5, 15.0), (85.0, 10.0), (82.5, 6.5)]),
    'andaman':     ('Andaman Sea',             [(92.5, 17.5), (93.5, 14.0), (96.5, 11.0), (97.5, 6.5)]),
    # --- East Indies ---
    'malacca':     ('Strait of Malacca',       [(100.5, 3.0), (103.0, 0.5)]),
    'sunda':       ('Sunda Strait',            [(96.0, 1.0), (98.5, -4.0), (102.5, -7.5), (106.5, -8.5), (111.0, -9.5)]),
    'java':        ('Java Sea',                [(109.0, -5.5), (113.5, -5.0)]),
    'siam':        ('Gulf of Siam',            [(101.5, 10.0), (103.0, 7.0)]),
    'scs_s':       ('South China Sea (South)', [(107.0, 3.5), (111.0, 7.0), (105.0, 7.5)]),
    'scs_n':       ('South China Sea (North)', [(112.0, 15.0), (116.0, 12.0), (116.5, 18.5), (113.5, 21.0), (117.0, 22.0)]),
    'tonkin':      ('Gulf of Tonkin',          [(107.5, 19.5), (108.5, 16.0)]),
    'formosa':     ('Formosa Strait',          [(120.0, 24.5), (121.0, 27.5)]),
    'sulu':        ('Sulu and Celebes Seas',   [(120.5, 8.5), (118.0, 10.5), (123.0, 10.5), (122.5, 3.5), (119.0, 1.0), (117.5, -2.5), (118.5, -5.5)]),
    'molucca':     ('Molucca Sea',             [(126.0, 1.0), (129.5, -1.0)]),
    'banda':       ('Banda Sea',               [(127.5, -6.0), (124.0, -5.0), (131.0, -5.5)]),
    'flores':      ('Flores Sea',              [(119.5, -7.0), (123.0, -8.0)]),
    'timor':       ('Timor Sea',               [(126.0, -11.0), (120.0, -12.5), (129.0, -13.0)]),
    'arafura':     ('Arafura Sea',             [(135.0, -8.5), (138.0, -10.0), (139.5, -14.5), (137.5, -12.0)]),
    'philippine':  ('Philippine Sea',          [(125.0, 16.0), (128.0, 10.0), (130.0, 20.0), (122.8, 23.5), (126.5, 5.0), (124.0, 8.0)]),
    # --- China, Korea, Japan, Kamchatka ---
    'ecs':         ('East China Sea',          [(124.0, 29.0), (126.5, 32.0), (128.5, 33.0), (126.0, 34.0), (122.5, 36.5), (120.5, 39.5)]),
    'japan_sea':   ('Sea of Japan',            [(134.0, 38.5), (131.0, 41.5), (138.0, 42.5), (140.5, 47.5), (138.5, 51.5)]),
    'okhotsk':     ('Sea of Okhotsk',          [(148.0, 54.5), (143.0, 56.5), (153.0, 58.0), (148.0, 44.0), (154.0, 47.5)]),
    'japan_pac':   ('Coast of Japan',          [(141.0, 34.5), (144.0, 38.5), (137.0, 32.0), (132.5, 30.5)]),
    'kamchatka':   ('Coast of Kamchatka',      [(161.0, 53.0), (164.0, 57.5), (158.0, 50.5)]),
    'bering':      ('Bering Sea',              [(172.0, 60.0), (176.0, 56.0), (180.0, 64.0), (186.0, 66.5)]),
    # --- open Pacific (three big zones) ---
    'pacific_n':   ('North Pacific Ocean',     [(142.0, 28.0), (158.0, 33.0), (175.0, 30.0), (178.0, 51.0), (198.0, 42.0), (195.0, 28.0)]),
    'pacific_w':   ('Caroline Islands',        [(134.0, 7.0), (150.0, 4.0), (163.0, 6.0), (166.0, 18.0), (147.0, 15.0), (176.0, 0.0),
                                                (192.0, 12.0), (188.0, -3.0)]),
    'pacific_s':   ('South Pacific Ocean',     [(168.0, -16.0), (178.0, -18.0), (190.0, -26.0), (188.0, -13.0), (165.0, -23.0),
                                                (168.0, -31.0), (180.0, -33.0), (184.0, -44.0), (185.0, -50.0), (196.0, -37.0)]),
    # --- New Guinea, Australia, New Zealand ---
    'newguinea':   ('Coast of New Guinea',     [(140.0, -2.5), (134.0, -1.5), (146.0, -4.5)]),
    'coral':       ('Coral Sea',               [(148.0, -16.0), (152.0, -22.0), (156.0, -17.0), (150.0, -8.5), (154.0, -5.0), (156.0, -11.0)]),
    'nsw':         ('Coast of New South Wales', [(153.5, -29.0), (152.0, -34.5)]),
    'tasman':      ('Tasman Sea',              [(160.0, -35.0), (162.0, -42.0), (158.0, -29.0), (171.5, -38.5), (146.0, -39.5), (149.5, -38.5)]),
    'bight':       ('Great Australian Bight',  [(133.0, -34.0), (126.0, -34.0), (140.0, -37.5)]),
    'newholland':  ('Coast of New Holland',    [(112.5, -22.0), (117.0, -18.0), (121.0, -16.0), (114.0, -34.0), (113.0, -28.0)]),
    'southern_e':  ('Southern Ocean (Van Diemen)', [(140.0, -50.0), (147.0, -46.0), (162.0, -52.0)]),
    'nz_e':        ('Cook Strait',             [(177.0, -36.5), (174.5, -44.5)]),
    'nz_w':        ('Dusky Bay',               [(168.0, -46.0)]),
}

# water left without a zone: the strip west of the old map north of Morocco and the strip above the old map
# (torn parchment edge in the art); the Caspian Sea is enclosed by original meshes and never gets a zone.
EXCLUDE = [dict(x_max=473.0, z_min=5000.0), dict(x_max=19090.0, z_min=12400.0)]
ARCTIC_LAT = 67.0            # water north of this (Kara, Laptev, East Siberian, Chukchi seas) gets no zone

# Cells forced to sea: a narrow corridor along the map's west edge where the painted Western Sahara coast runs
# off the map (z about 1900..-300); without it the Atlantic route around Africa is cut by the map edge.
EDGE_CORRIDOR = dict(cols=4, z_top=2200.0, z_bottom=-500.0)


def seed_cell(seed, free, lon, lat, xs, zs):
    """Nearest free sea cell to a (lon, lat) seed, or to ('xz', x, z) in world coordinates."""
    fy, fx = np.nonzero(free)
    if seed[0] == 'xz':
        d = (xs[fx] - seed[1]) ** 2 + (zs[fy] - seed[2]) ** 2
    else:
        lo, la = seed
        d = ((lon[fy, fx] - lo) * math.cos(math.radians(la))) ** 2 + (lat[fy, fx] - la) ** 2
    k = int(np.argmin(d))
    return fy[k], fx[k], math.sqrt(float(d[k]))


def province_labels(nx, nz, provs):
    img = Image.new('I', (nx, nz), -1)
    dr = ImageDraw.Draw(img)
    keys = list(provs)
    for k, key in enumerate(keys):
        pts = [((x - X0) / STEP, (Z1 - z) / STEP) for x, z in provs[key]['poly']]
        dr.polygon(pts, fill=k, outline=k)
    return np.asarray(img, np.int32), keys


def main(tol_coast=1.6, tol_open=4.0, max_verts=300):
    os.makedirs(OUT, exist_ok=True)
    g = np.load(os.path.join(OUT, 'grid.npz'))
    land, ex, lon, lat, xs, zs = g['land'], g['ex'], g['lon'], g['lat'], g['xs'], g['zs']
    ex_names = json.load(open(os.path.join(OUT, 'ex_names.json')))
    nz, nx = land.shape
    mng = Mng(open(os.path.join(ROOT, 'data', 'Game', 'GameModes', 'DefModeloGestion.mng'), 'rb').read())
    recs = Mng.parse_provinces(mng.section(4))
    ex_sea = {r['name'] for r in recs if r['sea']}
    ex_prov = {r['name'] for r in recs}
    provs = json.load(open(os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))
    plab, pkeys = province_labels(nx, nz, provs)
    plab = plab.copy()
    plab[land == 0] = -1                                    # provinces are land only
    plab[ex >= 0] = -1

    free = ~land & (ex < 0)
    r0 = int((Z1 - EDGE_CORRIDOR['z_top']) / STEP); r1 = int((Z1 - EDGE_CORRIDOR['z_bottom']) / STEP)
    free[r0:r1, :EDGE_CORRIDOR['cols']] = True
    XX, ZZ = np.meshgrid(xs, zs)
    for e in EXCLUDE:
        free &= ~((XX < e['x_max']) & (ZZ > e['z_min']))
    free &= ~((lat > ARCTIC_LAT) & (XX > 19090.0))

    keys = list(ZONES)
    sy, sx, sz = [], [], []
    for k, key in enumerate(keys):
        for s in ZONES[key][1]:
            y, x, d = seed_cell(s, free, lon, lat, xs, zs)
            sy.append(y); sx.append(x); sz.append(k)
            if d > 2.0:
                print('seed far from sea', key, s, round(d, 2))
    sy, sx, sz = np.array(sy), np.array(sx), np.array(sz)
    # Voronoi in world units (cells are square, 40 units)
    fy, fx = np.nonzero(free)
    tree = cKDTree(np.stack([sx, sy], 1))
    _, j = tree.query(np.stack([fx, fy], 1))
    label = -np.ones((nz, nx), np.int32)
    label[fy, fx] = sz[j]
    # keep the sea-connected piece(s) holding the zone's seeds
    final = -np.ones_like(label)
    for k in range(len(keys)):
        m = label == k
        lab, n = ndimage.label(m)
        ids = {int(lab[y, x]) for y, x, z in zip(sy, sx, sz) if z == k and lab[y, x]}
        if not ids:
            print('zone lost', keys[k]); continue
        final[np.isin(lab, list(ids))] = k
    orphan = (label >= 0) & (final < 0)
    for _ in range(60):
        if not orphan.any():
            break
        grown = ndimage.grey_dilation(np.where(final >= 0, final + 1, 0), size=3) - 1
        take = orphan & (grown >= 0)
        if not take.any():
            break
        final[take] = grown[take]
        orphan = (label >= 0) & (final < 0)
    # stray fragments (< 20 cells) go to the 4-neighbour zone with most shared edges, else stay unassigned
    for k in range(len(keys)):
        lab, n = ndimage.label(final == k)
        if n < 2:
            continue
        sizes = ndimage.sum(final == k, lab, range(1, n + 1))
        for c, sz_ in enumerate(sizes, 1):
            if sz_ >= 20:
                continue
            m = lab == c
            ring = ndimage.binary_dilation(m, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]]) & ~m
            vals = final[ring]; vals = vals[(vals >= 0) & (vals != k)]
            final[m] = int(np.bincount(vals).argmax()) if len(vals) else -1
    print('unassigned sea cells (lakes etc.)', int(((label >= 0) & (final < 0)).sum()))

    # enclosed land: islands inside a zone (holes of the filled region)
    comb = np.where(final >= 0, final, np.where(plab >= 0, 2000 + plab, np.where(ex >= 0, 1000 + ex, -1)))
    out = {}
    raw = {}
    for k, key in enumerate(keys):
        m = final == k
        if m.sum() < 20:
            print('skip (too small)', key, int(m.sum())); continue
        res = WP.trace_loops(m)
        if res is None:
            continue
        loop, keep = res
        hole = keep & ~m
        encl = [pkeys[v] for v in np.unique(plab[hole]) if v >= 0 and (plab[hole] == v).sum() >= 12]
        encl += [ex_names[v] for v in np.unique(ex[hole]) if v >= 0 and (ex[hole] == v).sum() >= 12]
        raw[k] = (loop, keep, encl, int(hole.sum()))

    def corner_key(c):
        i, j = c
        s = set()
        for dj in (-1, 0):
            for di in (-1, 0):
                y, x = j + dj, i + di
                s.add(int(comb[y, x]) if 0 <= y < nz and 0 <= x < nx else -2)
        return frozenset(s)

    def build(tol_c, tol_o):
        cache = {}
        polys = {}
        for k, (loop, keep, encl, nh) in raw.items():
            n = len(loop)
            junction = [len(corner_key(c)) >= 3 for c in loop]
            idx = [i for i in range(n) if junction[i]]
            if len(idx) < 2:
                idx = [0, n // 2]
            poly = []
            for a, b in zip(idx, idx[1:] + [idx[0] + n]):
                chain = [loop[i % n] for i in range(a, b + 1)]
                key = tuple(chain); rkey = tuple(reversed(chain))
                if rkey in cache:
                    simp = list(reversed(cache[rkey]))
                elif key in cache:
                    simp = cache[key]
                else:
                    ks = set()
                    for cc in chain[1:-1]:
                        ks |= corner_key(cc)
                    open_sea = all(0 <= v < 1000 for v in ks) and len(chain) > 2
                    simp = WP.dp(chain, tol_o if open_sea else tol_c)
                    cache[key] = simp
                poly.extend(simp[:-1])
            polys[k] = poly
        return polys

    polys = build(tol_coast, tol_open)
    worst = max(len(p) for p in polys.values())
    tc, to = tol_coast, tol_open
    while worst > max_verts:
        tc *= 1.25; to *= 1.25
        polys = build(tc, to)
        worst = max(len(p) for p in polys.values())
        print('simplify more', round(tc, 2), round(to, 2), 'max verts', worst)

    # adjacency on the grid (4-neighbours)
    def pairs(a, b):
        s = set()
        for sl in ((slice(None), slice(1, None), slice(None), slice(None, -1)),
                   (slice(1, None), slice(None), slice(None, -1), slice(None))):
            A = a[sl[0], sl[1]]; B = b[sl[2], sl[3]]
            m = (A != B)
            s |= set(zip(A[m].tolist(), B[m].tolist()))
        return s | {(q, p) for p, q in s}
    adj = pairs(comb, comb)
    for k, key in enumerate(keys):
        if k not in polys:
            continue
        wpoly = [(float(X0 + i * STEP), float(Z1 - j * STEP)) for i, j in polys[k]]
        wpoly = MG.ccw(wpoly)
        simple = MG.is_simple(wpoly)
        if not simple:
            import free_land
            wpoly = free_land.untangle(wpoly)
            simple = MG.is_simple(wpoly)
        nb = {q for p, q in adj if p == k}
        nsea = [keys[q] for q in sorted(nb) if 0 <= q < 1000]
        nsea += [ex_names[q - 1000] for q in sorted(nb) if 1000 <= q < 2000 and ex_names[q - 1000] in ex_sea]
        cland = [pkeys[q - 2000] for q in sorted(nb) if q >= 2000]
        cland += [ex_names[q - 1000] for q in sorted(nb) if 1000 <= q < 2000 and ex_names[q - 1000] in ex_prov - ex_sea]
        decor = [ex_names[q - 1000] for q in sorted(nb) if 1000 <= q < 2000 and ex_names[q - 1000] not in ex_prov]
        loop, keep, encl, nh = raw[k]
        m = final == k
        ys, xs_ = np.nonzero(m)
        cx = float(X0 + (xs_.mean() + 0.5) * STEP); cz = float(Z1 - (ys.mean() + 0.5) * STEP)
        # a centre inside the zone: the cell farthest from the zone border
        dist = ndimage.distance_transform_edt(m)
        jy, jx = np.unravel_index(int(np.argmax(dist)), dist.shape)
        rec = dict(name=ZONES[key][0], poly=[[round(x, 1), round(z, 1)] for x, z in wpoly],
                   neighbours_sea=nsea, coastal_land=cland, centre=[round(float(X0 + (jx + 0.5) * STEP), 1), round(float(Z1 - (jy + 0.5) * STEP), 1)],
                   cells=int(m.sum()), area_units2=int(m.sum() * STEP * STEP), simple=bool(simple))
        if decor:
            rec['coastal_decor'] = decor                       # original non-province land meshes (Arabia, Persia, ...)
        if encl:
            rec['enclosed_land'] = encl                        # islands inside the polygon (holes filled)
        out[key] = rec
    out['canary']['note'] = 'Includes a 160-unit corridor along the west map edge (z %d..%d) over painted land: the Western Sahara coast runs off the map there.' % (EDGE_CORRIDOR['z_top'], EDGE_CORRIDOR['z_bottom'])
    json.dump(out, open(os.path.join(OUT, 'sea_zones.json'), 'w'), indent=1)
    np.save(os.path.join(OUT, 'zone_labels.npy'), final)
    json.dump(keys, open(os.path.join(OUT, 'zone_keys.json'), 'w'))
    bad = [k for k, v in out.items() if not v['simple']]
    print('zones', len(out), 'not simple', bad, 'max verts', max(len(v['poly']) for v in out.values()))
    for k, v in out.items():
        if v.get('enclosed_land'):
            print('enclosed', k, v['enclosed_land'])
    preview(out, final, keys)
    return out


def preview(out, final, keys):
    bg = Image.open(os.path.join(ROOT, 'build', 'kart_forhandsvisning.png')).convert('RGBA')
    W, H = bg.size
    sx = W / (X1 - X0); sy = H / (Z1 - Z0)
    def px(x, z):
        return ((x - X0) * sx, (Z1 - z) * sy)
    rng = np.random.default_rng(7)
    lay = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for key, v in out.items():
        col = tuple(int(c) for c in rng.integers(40, 255, 3)) + (80,)
        dr.polygon([px(x, z) for x, z in v['poly']], fill=col, outline=(20, 20, 60, 220))
    bg = Image.alpha_composite(bg, lay)
    dr = ImageDraw.Draw(bg)
    try:
        font = ImageFont.truetype('arial.ttf', 11)
    except Exception:
        font = ImageFont.load_default()
    cent = {k: px(*v['centre']) for k, v in out.items()}
    for key, v in out.items():
        for n in v['neighbours_sea']:
            if n in cent and key < n:
                dr.line([cent[key], cent[n]], fill=(200, 30, 30, 255), width=1)
    for key, v in out.items():
        x, y = cent[key]
        dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(200, 30, 30, 255))
        t = v['name']
        tw = dr.textlength(t, font=font)
        dr.rectangle([x - tw / 2 - 2, y + 4, x + tw / 2 + 2, y + 17], fill=(255, 250, 230, 200))
        dr.text((x - tw / 2, y + 4), t, fill=(30, 20, 10, 255), font=font)
    bg.convert('RGB').save(os.path.join(OUT, 'sea_zones.png'))


if __name__ == '__main__':
    main()

"""Natural borders for the old edge provinces: extend each old province that ends at the straight old map edge
(x = 19930 east, z = -880/-970 south) with the piece of new-area land it should plausibly own in 1789, following
Natural Earth admin-1 units; the remaining new provinces shrink accordingly.

Rules (EXT): old mesh name -> admin-1 units (iso, name) taken from the new provinces. Whole units only, so every
new border follows a real provincial/country line. Cells of the unassigned desert strip inside the old art
rectangle (south of Cirenaica/Tripolitania, z > -710) are assigned by the same unit rules (STRIP).

Writes build/extend/extensions.json, world_provinces_ext.json, preview.png, report.json.
Run: python extend.py   (needs build/extend/grid.npz from grid.py; made automatically if missing)
"""
import os, sys, json, math, collections
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, TOOLS)
import world_provinces as WP, meshgen as MG, render_map as RM
import grid as G

ROOT = WP.ROOT
OUT = G.OUT
STEP, X0, Z1 = WP.STEP, WP.X0, WP.Z1
MOD_V3D = os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'Gestion', 'Mapa', 'MapaGestionVolumenes.V3D')

# old mesh -> admin-1 units (iso, name) it takes from the new provinces.  'iso:*' = every unit of that country.
EXT = {
    'SaharaOccidental': ['MR:*'],                                   # Moorish emirates to the Senegal river
    'Tuat': [('DZ', 'Adrar'), ('DZ', 'Tamanghasset')],              # Tanezrouft and the Hoggar (Kel Ahaggar)
    'Cirenaica': [('LY', 'Al Kufrah'), ('LY', 'Ajdabiya')],         # Jalu/Awjila and Kufra oases (Zuwayya)
    'Egipto': ['PROV:upperegypt', ('EG', 'Al Wadi at Jadid'), ('EG', 'Al Bahr al Ahmar'), ('EG', 'Aswan'),
               ('EG', 'Qina'), ('EG', 'Matruh')],                   # Mamluk Egypt to Aswan
    'Arabia': [('SA', "Ha'il"), ('SA', 'Al Quassim')],              # Jabal Shammar and Qasim
    'Oman': ['AE:*', ('OM', 'Musandam'), ('OM', 'Al Dhahira'), ('OM', 'Al Batnah North'), ('OM', 'Al Buraymi')],
    'Khorasan': [('IR', 'Kerman'), ('IR', 'Hormozgan'), ('IR', 'Sistan and Baluchestan'), ('AF', 'Nimroz'), ('AF', 'Ghor')],
    'Turkestan': [('UZ', 'Surkhandarya'), ('UZ', 'Jizzakh'), ('UZ', 'Kashkadarya'), ('UZ', 'Samarkand'),
                  ('TJ', 'Khatlon'), ('TJ', 'Tadzhikistan Territories'), ('TJ', 'Dushanbe'), ('AF', 'Jawzjan')],
    'Kazakhstan': [('KZ', 'Qaraghandy'), ('KZ', 'Aqmola'), ('KZ', 'Astana'), ('KZ', 'South Kazakhstan'), ('KZ', 'Qyzylorda')],
    'Siberia': [('RU', 'Khanty-Mansiy'), ('RU', 'Yamal-Nenets'), ('RU', "Tyumen'"), ('RU', 'Kurgan'), ('KZ', 'North Kazakhstan')],
}
# unassigned old-art strip south of Tripolitania/Cirenaica: unit -> new province id (Fezzan proper gets Murzuq)
STRIP_NEW = {('LY', 'Murzuq'): 'fezzan', ('LY', 'Sabha'): 'fezzan', ('LY', 'Wadi al Hayaa'): 'fezzan',
             ('LY', "Ash Shati'"): 'fezzan', ('LY', 'Ghat'): 'fezzan'}
STRIP_BOX = (5000, 13000, -1000, 0)       # x0, x1, z0, z1 of the strip region
SNAP = 48.0                                # max distance for snapping grid corners onto the real old mesh outline


def grow(comb):
    """Label of the nearest neighbour for every cell (grey dilation); old meshes (1000..1999) never spread."""
    src = np.where((comb >= 0) & ((comb < 1000) | (comb >= 2000)), comb + 1, 0)
    return ndimage.grey_dilation(src, size=3) - 1


def unit_index(units):
    ix = collections.defaultdict(list)
    for i, u in enumerate(units):
        ix[(u['iso'], u['name'])].append(i)
        ix[u['iso'] + ':*'].append(i)
    return ix


def build_labels():
    g, meta = G.load()
    land, ex, final, lon, lat, adm, ctry, xs, zs, old = [g[k] for k in ('land', 'ex', 'final', 'lon', 'lat', 'adm', 'ctry', 'xs', 'zs', 'old')]
    final = final.copy()
    names, P = meta['ex_names'], meta['P']
    pid = [p['id'] for p in P]
    units = json.load(open(os.path.join(ROOT, 'build', 'admin1_units.json'), encoding='utf8'))
    uix = unit_index(units)
    nz, nx = land.shape
    X, Z = np.meshgrid(xs, zs)
    before = {p['id']: int((final == k).sum()) for k, p in enumerate(P)}
    # 1. the unassigned strip inside the old art: by unit rule, otherwise to the touching old province / neighbour
    strip = land & (ex < 0) & (final < 0) & old & (X > STRIP_BOX[0]) & (X < STRIP_BOX[1]) & (Z > STRIP_BOX[2]) & (Z < STRIP_BOX[3])
    for key, prov in STRIP_NEW.items():
        for u in uix.get(key, []):
            final[strip & (adm == u)] = pid.index(prov)
    # 2. extension labels: ext index e -> old mesh k
    ext_names = list(EXT)
    extlab = -np.ones_like(final)
    for e, name in enumerate(ext_names):
        m = np.zeros_like(land)
        for rule in EXT[name]:
            if isinstance(rule, str) and rule.startswith('PROV:'):
                m |= final == pid.index(rule[5:])
            else:
                for u in uix.get(rule, []):
                    m |= adm == u
        m &= land & (ex < 0) & ((final >= 0) | strip)
        extlab[m] = e
    # keep only pieces touching their own old mesh (4-neighbours); the rest stays where it was
    for e, name in enumerate(ext_names):
        k = names.index(name)
        m = extlab == e
        lab, n = ndimage.label(m)
        touch = ndimage.binary_dilation(ex == k) & m
        ok = set(np.unique(lab[touch])) - {0}
        drop = m & ~np.isin(lab, list(ok))
        extlab[drop] = -1
    # remaining strip cells (no rule, not taken): nearest new/extension label
    comb = np.where(extlab >= 0, 2000 + extlab, np.where(final >= 0, final, np.where(ex >= 0, 1000 + ex, -1)))
    left = strip & (comb < 0)
    for _ in range(6):
        if not left.any():
            break
        grown = grow(comb)
        take = left & (grown >= 0)
        comb[take] = grown[take]
        left = strip & (comb < 0)
    # 3. new provinces: seed = own cell nearest the proposal point; keep the seed's piece; orphans to neighbours
    newlab = np.where((comb >= 0) & (comb < 1000), comb, -1)
    seeds = {}
    final2 = -np.ones_like(newlab)
    seed0 = g['seeds']; err0 = g['seed_err']
    for k, p in enumerate(P):
        m = newlab == k
        if not m.any():
            continue
        y0, x0 = int(seed0[k][0]), int(seed0[k][1])
        if newlab[y0, x0] == k:                       # original seed cell still ours: same choice as world_provinces
            seeds[k] = (y0, x0, float(err0[k]))
        else:                                         # (fezzan) own cell nearest the proposal point
            yy, xx = np.nonzero(m)
            d = (lon[yy, xx] - p['lon']) ** 2 * math.cos(math.radians(p['lat'])) ** 2 + (lat[yy, xx] - p['lat']) ** 2
            j = int(np.argmin(d))
            seeds[k] = (int(yy[j]), int(xx[j]), float(math.sqrt(d[j])))
        yy, xx, _ = seeds[k]
        lab, n = ndimage.label(m)
        final2[lab == lab[yy, xx]] = k
    comb2 = np.where(final2 >= 0, final2, np.where(extlab >= 0, 2000 + extlab, np.where(ex >= 0, 1000 + ex, -1)))
    orphan = (comb >= 0) & (comb2 < 0)
    for _ in range(40):
        if not orphan.any():
            break
        grown = grow(comb2)
        take = orphan & (grown >= 0)
        comb2[take] = grown[take]
        orphan = (comb >= 0) & (comb2 < 0)
    # extension pieces may have swallowed orphans: re-check that every piece still touches its mesh
    for e, name in enumerate(ext_names):
        k = names.index(name)
        m = comb2 == 2000 + e
        lab, n = ndimage.label(m)
        touch = ndimage.binary_dilation(ex == k) & m
        ok = set(np.unique(lab[touch])) - {0}
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        tiny = {c + 1 for c in range(n) if sizes[c] < 12}
        bad = m & ~np.isin(lab, list(ok - tiny))
        if bad.any():
            print('%s: %d cells detached or tiny -> neighbours' % (name, int(bad.sum())))
            comb2[bad] = -1
            for _ in range(10):
                grown = grow(comb2)
                take = bad & (comb2 < 0) & (grown >= 0) & (grown != 2000 + e)
                comb2[take] = grown[take]
                if not (bad & (comb2 < 0)).any():
                    break
    after = {p['id']: int((comb2 == k).sum()) for k, p in enumerate(P)}
    extcells = {name: int((comb2 == 2000 + e).sum()) for e, name in enumerate(ext_names)}
    return dict(comb=comb2, land=land, ex=ex, names=names, P=P, pid=pid, ext_names=ext_names, seeds=seeds, lon=lon, lat=lat,
                adm=adm, units=units, xs=xs, zs=zs, before=before, after=after, extcells=extcells, strip=strip)


def mesh_outlines():
    """name -> boundary edges of the old meshes (world x, z), like render_map.province_outlines but ignoring the
    zero-area sliver triangles at tile seams, which otherwise hide parts of the real boundary."""
    import struct, collections
    from igmod import V3D
    d = open(MOD_V3D, 'rb').read()
    v = V3D(d)
    out = {}
    for st, en, name in v.blocks:
        b = d[st:en]
        f = V3D.mesh_fields(b)
        tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]
        pts = [(round(x + tx, 1), round(z + tz, 1)) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        cnt = collections.Counter()
        for t in range(0, len(idx), 3):
            a, bb, c = (pts[i] for i in idx[t:t + 3])
            if abs(MG.area([a, bb, c])) < 1.0:
                continue
            for e in ((a, bb), (bb, c), (c, a)):
                cnt[tuple(sorted(e))] += 1
        out[name] = [k for k, n in cnt.items() if n == 1]
    return out


def seg_project(p, edges):
    """Nearest point on a list of segments and its distance."""
    px, pz = p
    best, bp = 1e18, p
    for (ax, az), (bx, bz) in edges:
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz or 1)))
        qx, qz = ax + t * dx, az + t * dz
        d = math.hypot(px - qx, pz - qz)
        if d < best:
            best, bp = d, (qx, qz)
    return bp, best


def outline_loops(edges):
    """Chain single-use boundary edges into closed loops (lists of points)."""
    adj = collections.defaultdict(list)
    for a, b in edges:
        adj[a].append(b); adj[b].append(a)
    used = set()
    loops = []
    for a, b in edges:
        if (a, b) in used or (b, a) in used:
            continue
        loop = [a, b]; used.add((a, b))
        while True:
            cur, prev = loop[-1], loop[-2]
            nxt = [q for q in adj[cur] if q != prev and (cur, q) not in used and (q, cur) not in used]
            if not nxt:
                break
            q = nxt[0]; used.add((cur, q))
            if q == loop[0]:
                break
            loop.append(q)
        if len(loop) >= 3:
            loops.append(loop)
    return loops


class MeshEdge:
    """Projection onto an old mesh outline and extraction of the outline path between two points on it."""
    def __init__(self, loops):
        self.loops = loops
        self.cum = []
        for L in loops:
            c = [0.0]
            for i in range(len(L)):
                a, b = L[i], L[(i + 1) % len(L)]
                c.append(c[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
            self.cum.append(c)
        self.verts = {v for L in loops for v in L}

    def project(self, p):
        best = (1e18, None)
        for li, L in enumerate(self.loops):
            n = len(L)
            for i in range(n):
                a, b = L[i], L[(i + 1) % n]
                dx, dz = b[0] - a[0], b[1] - a[1]
                t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / (dx * dx + dz * dz or 1)))
                q = (a[0] + t * dx, a[1] + t * dz)
                d = math.hypot(p[0] - q[0], p[1] - q[1])
                if d < best[0]:
                    best = (d, (li, i, t, q))
        return best

    def path(self, pa, pb):
        """Outline vertices strictly between two points on the same loop, the shorter way round; None if not possible."""
        da, A = self.project(pa); db, B = self.project(pb)
        if A is None or B is None or da > 1.5 or db > 1.5 or A[0] != B[0]:
            return None
        L, c = self.loops[A[0]], self.cum[A[0]]
        n = len(L); total = c[-1]
        sa = c[A[1]] + A[2] * (c[A[1] + 1] - c[A[1]])
        sb = c[B[1]] + B[2] * (c[B[1] + 1] - c[B[1]])
        fwd = (sb - sa) % total
        out = []
        if fwd <= total - fwd:           # forward: vertices after A up to B
            i = A[1] + 1
            while len(out) <= n:
                v = i % n
                if (c[v] - sa) % total >= fwd - 1e-6:
                    break
                out.append(L[v]); i += 1
        else:                            # backward: vertex A[1], A[1]-1 ... down to the one after B
            i = A[1]; back = total - fwd
            while len(out) <= n:
                v = i % n
                if (sa - c[v]) % total >= back - 1e-6:
                    break
                out.append(L[v]); i -= 1
        return out


def trace_all(D, tol_cells=1.4):
    comb, names, P, ext_names = D['comb'], D['names'], D['P'], D['ext_names']
    nz, nx = comb.shape
    outlines = mesh_outlines()
    meshes = {}
    for name, edges in outlines.items():
        if name in names and edges:
            meshes[names.index(name)] = MeshEdge(outline_loops(edges))

    def snap(pt, exset):
        """Nearest point on the outlines of the given old meshes; a corner shared by two meshes goes to their
        common vertex when there is one nearby."""
        exset = [k for k in exset if k in meshes]
        if not exset:
            return pt
        if len(exset) >= 2:
            best = (1e18, None)
            for k1 in exset:
                for v in meshes[k1].verts:
                    d = math.hypot(v[0] - pt[0], v[1] - pt[1])
                    if d < best[0] and d <= SNAP * 1.5 and any(k2 != k1 and meshes[k2].project(v)[0] < 1.0 for k2 in exset):
                        best = (d, v)
            if best[1] is not None:
                return best[1]
        best = (1e18, None)
        for k in exset:
            d, r = meshes[k].project(pt)
            if d < best[0]:
                best = (d, r[3])
        return best[1] if best[0] <= SNAP else pt

    def corner_key(c):
        i, j = c
        s = set()
        for dj in (-1, 0):
            for di in (-1, 0):
                y, x = j + dj, i + di
                s.add(int(comb[y, x]) if 0 <= y < nz and 0 <= x < nx else -1)
        return frozenset(s)

    def exset_of(key):
        return {v - 1000 for v in key if 1000 <= v < 2000}

    def world(pt):
        return (float(X0 + pt[0] * STEP), float(Z1 - pt[1] * STEP))

    # regions to trace: every new province and every connected piece of every extension
    regions = []                       # (kind, id, mask)
    for k, p in enumerate(P):
        m = comb == k
        if m.sum() >= 25:
            regions.append(('new', k, m))
        elif m.any():
            print('skip (too small)', p['id'], int(m.sum()))
    for e, name in enumerate(ext_names):
        m = comb == 2000 + e
        lab, n = ndimage.label(m)
        for c in range(1, n + 1):
            regions.append(('ext', e, lab == c))
    cache = {}
    result = []
    stats = collections.Counter()
    for kind, ident, m in regions:
        res = WP.trace_loops(m)
        if res is None:
            continue
        loop, keep = res
        n = len(loop)
        junction = [len(corner_key(c)) >= 3 for c in loop]
        idx = [i for i in range(n) if junction[i]]
        if len(idx) < 2:
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
                keys = [corner_key(cc) for cc in chain]
                inland = all(-1 not in kk for kk in keys[1:-1]) and len(chain) > 2
                pair = set()
                for kk in keys[1:-1]:
                    pair |= kk
                ex_in = [k for k in exset_of(pair) if k in meshes]
                p0 = snap(world(chain[0]), exset_of(keys[0]))
                p1 = snap(world(chain[-1]), exset_of(keys[-1]))
                mid = None
                if ex_in:                       # along an old mesh: the mesh's own outline between the end points
                    mid = meshes[ex_in[0]].path(p0, p1)
                    stats['mesh chain ok' if mid is not None else 'mesh chain fallback'] += 1
                if mid is None:
                    s = WP.smooth(WP.dp(chain, 2.2), 3) if inland else WP.dp(chain, tol_cells)
                    mid = [snap(world(pt), set(ex_in)) for pt in s[1:-1]]
                simp = [p0] + mid + [p1]
                cache[key] = simp
            poly.extend(simp[:-1])
        wpoly = [p for q, p in enumerate(poly) if q == 0 or p != poly[q - 1]]
        if len(wpoly) > 1 and wpoly[0] == wpoly[-1]:
            wpoly = wpoly[:-1]
        wpoly = MG.ccw(wpoly)
        if not MG.is_simple(wpoly):
            import free_land
            n0 = len(wpoly)
            wpoly = free_land.untangle(wpoly)
            stats['untangled'] += 1
            if len(wpoly) < 0.8 * n0:
                print('WARNING: untangle removed many vertices', kind, ident, n0, '->', len(wpoly))
        result.append((kind, ident, wpoly, int(m.sum())))
    print('chains:', dict(stats))
    return result


def preview(D, result, path):
    bg = Image.open(os.path.join(ROOT, 'build', 'kart_forhandsvisning.png')).convert('RGBA')
    W, H = bg.size
    def px(p):
        return ((p[0] - MG.COLS[0]) / MG.TILE_W * 256.0, (MG.ROWS[4] - p[1]) / MG.TILE_H * 256.0)
    over = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(over)
    rng = np.random.default_rng(3)
    P, ext_names = D['P'], D['ext_names']
    pal = {k: tuple(int(v) for v in rng.integers(70, 230, 3)) for k in range(len(P))}
    # hatch pattern for the extensions
    hatch = Image.new('RGBA', bg.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(hatch)
    for s in range(-H, W, 7):
        hd.line([(s, 0), (s + H, H)], fill=(180, 30, 30, 200), width=1)
    labels = []
    for kind, ident, poly, cells in result:
        pts = [px(p) for p in poly]
        if len(pts) < 3:
            continue
        if kind == 'new':
            col = pal[ident]
            dr.polygon(pts, fill=col + (95,), outline=(40, 40, 40, 230))
            labels.append((pts, P[ident]['name'], (20, 20, 20)))
        else:
            mask = Image.new('L', bg.size, 0)
            ImageDraw.Draw(mask).polygon(pts, fill=255)
            tint = Image.new('RGBA', bg.size, (255, 120, 60, 110))
            over.paste(Image.composite(tint, Image.new('RGBA', bg.size, (0, 0, 0, 0)), mask), (0, 0), mask)
            over.paste(hatch, (0, 0), mask)
            dr.polygon(pts, outline=(150, 20, 20, 255))
            labels.append((pts, '+' + ext_names[ident], (120, 0, 0)))
    # old province outlines
    outlines = mesh_outlines()
    for name, edges in outlines.items():
        if (name[0] in 'SW' and name[1:2].isupper()) or name.startswith('Mar') or name.startswith('Golfo') or name.startswith('Oceano'):
            continue
        for a, b in edges:
            dr.line([px(a), px(b)], fill=(255, 255, 255, 160), width=1)
    img = Image.alpha_composite(bg, over)
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', 11)
        font2 = ImageFont.truetype('arialbd.ttf', 11)
    except Exception:
        font = font2 = ImageFont.load_default()
    for pts, text, col in labels:
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        f = font2 if text.startswith('+') else font
        tw = dr.textlength(text, font=f)
        dr.text((cx - tw / 2 + 1, cy - 5 + 1), text, font=f, fill=(255, 255, 255))
        dr.text((cx - tw / 2, cy - 5), text, font=f, fill=col)
    img.convert('RGB').save(path)


def main():
    if not os.path.exists(os.path.join(OUT, 'grid.npz')):
        G.compute()
    D = build_labels()
    result = trace_all(D)
    P, pid, ext_names, seeds, xs, zs = D['P'], D['pid'], D['ext_names'], D['seeds'], D['xs'], D['zs']
    exts = collections.defaultdict(list)
    provs = {}
    bad = []
    for kind, ident, poly, cells in result:
        if not MG.is_simple(poly):
            bad.append((kind, ident))
        if kind == 'ext':
            exts[ext_names[ident]].append([list(p) for p in poly])
        else:
            p = P[ident]
            yy, xx, dist = seeds[ident]
            provs[p['id']] = dict(name=p['name'], owner=p['owner'], region=p['region'], note=p['note'],
                                  poly=[list(q) for q in poly], seed=[float(xs[xx]), float(zs[yy])], cells=cells,
                                  seed_err_deg=round(dist, 2))
    json.dump(dict(exts), open(os.path.join(OUT, 'extensions.json'), 'w'), indent=0)
    json.dump(provs, open(os.path.join(OUT, 'world_provinces_ext.json'), 'w'))
    preview(D, result, os.path.join(OUT, 'preview.png'))
    # report
    orig = json.load(open(os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))
    changed = {k: (D['before'][k], D['after'][k]) for k in pid if D['before'][k] != D['after'][k]}
    removed = [k for k in orig if k not in provs]
    rep = dict(ext_cells=D['extcells'], ext_pieces={k: len(v) for k, v in exts.items()}, changed=changed, removed=removed,
               not_simple=bad, cell_area=STEP * STEP)
    json.dump(rep, open(os.path.join(OUT, 'report.json'), 'w'), indent=1)
    print('extensions:', {k: (D['extcells'][k], len(exts.get(k, []))) for k in ext_names})
    print('changed new provinces:', changed)
    print('removed:', removed, 'not simple:', bad)
    print('provinces written', len(provs))


if __name__ == '__main__':
    main()

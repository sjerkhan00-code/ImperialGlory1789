"""Draw the new provinces' borders into the old-map tiles in the original ink style.

Base: build/art/deframe tiles, with tile row 0 replaced by the re-synthesised build/oldarea/tiles/tile_<c>_0.png
(northfix.py).  For every edge of every new polygon (build/oldarea/provinces.json):
  * coast / same-province edge (the other side is sea, nothing, or an extension piece of the same province): nothing,
  * edge on an original province outline (ink already painted): the pillow rim on the new province's side only,
  * otherwise a new border: solid ink line + the rim on both sides (the other side may be another new province,
    an original one such as Kursk north of Chechenya, or a 1789 province of the bigger map, e.g. Najd).
Writes the changed tiles to build/oldarea/tiles/, preview.png (the whole old area) and before/after crops.
"""
import os, sys, json, math
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, Point, LineString
from shapely.strtree import STRtree
import common as C, geo, ink, fillart, oldedge
from scipy import ndimage

TS = C.TS
TILES = os.path.join(C.OUT, 'tiles')


def load():
    # the ink polygons (outline chains snapped to the painted lines); provinces.json is the mesh version
    polys = {int(k): [tuple(p) for p in v] for k, v in json.load(open(os.path.join(C.OUT, 'provinces_ink.json'))).items()}
    # W: the 1789 provinces as they were before design.py moved their old-edge borders (erase_old_borders needs the
    # old lines; build/world_provinces.json has since been overwritten with the fixed version)
    pre = os.path.join(C.OUT, 'world_provinces_orig.json')
    W = json.load(open(pre if os.path.exists(pre) else os.path.join(C.BUILD, 'world_provinces.json'), encoding='utf8'))
    W2 = json.load(open(os.path.join(C.OUT, 'world_provinces_fixed.json'), encoding='utf8'))
    E2 = json.load(open(os.path.join(C.OUT, 'extensions_fixed.json'), encoding='utf8'))
    # extension pieces before design.py's old-edge junction fixes (to erase the moved borders painted in the art)
    pe = os.path.join(C.OUT, 'extensions_orig.json')
    load.E_orig = json.load(open(pe, encoding='utf8')) if os.path.exists(pe) else None
    return polys, W, W2, E2


NEAT = (192, 266, 3904, 3830)


def _newart_edges(W2, W, polys):
    """The province borders of the bigger map that stay as tools/art/styled2.py drew them, in styled's global tile px:
    every edge of a 1789 province polygon (build/oldarea/world_provinces_fixed.json) that is shared by two of them, or
    that the polygon already had before design.py (W) and that is not on an old-area province's outline (those, and
    the natural lines, are drawn by this script in the old art's ink).  The moved old-edge borders are not in it."""
    import styled, meshgen as MG
    from shapely.ops import unary_union
    def edges(poly):
        out = []
        for i in range(len(poly)):
            a = tuple(round(c, 1) for c in poly[i - 1]); b = tuple(round(c, 1) for c in poly[i])
            out.append((a, b) if a < b else (b, a))
        return out
    cnt = {}
    for v in W2.values():
        for k in edges(v['poly']):
            cnt[k] = cnt.get(k, 0) + 1
    before = {k for v in W.values() for k in edges(v['poly'])}
    ink = unary_union([Polygon(p).boundary for p in polys.values()])
    def on_ink(k):
        m = Point((k[0][0] + k[1][0]) / 2, (k[0][1] + k[1][1]) / 2)
        return ink.distance(m) < 1.0
    keep = [k for k, n in sorted(cnt.items()) if n == 2 or (k in before and not on_ink(k))]
    def gp(x, z):
        return ((x - MG.COLS[0]) / MG.TILE_W * 512.0 * styled.PX, (MG.ROWS[4] - z) / MG.TILE_H * 512.0 * styled.PX)
    return [(gp(*a), gp(*b), False, 2) for (a, b) in keep]


def newart_clean(col, row, edges):
    """The new-area art of old tile (col, row) as tools/art/styled2.py renders it (build/tiles_new is that render),
    but with only the borders that stay (_newart_edges): the art under the old-edge borders that moved.  Cached in
    build/oldarea/work/newart_<c>_<r>.png, keyed by those borders and the renderer's source."""
    import hashlib
    sys.path.insert(0, os.path.join(C.TOOLS, 'art'))
    h = hashlib.md5(repr(edges).encode())
    for f in ('styled2.py', 'styled.py'):
        for d in (os.path.join(C.TOOLS, 'art'), C.TOOLS):
            if os.path.exists(os.path.join(d, f)):
                h.update(open(os.path.join(d, f), 'rb').read())
    key = h.hexdigest()
    fn = os.path.join(geo.WORK, 'newart_%d_%d.png' % (col, row))
    if os.path.exists(fn) and os.path.exists(fn + '.key') and open(fn + '.key').read() == key:
        return np.asarray(Image.open(fn).convert('RGB')).astype(np.float32)
    import styled, styled2
    styled._cache['edges'] = edges
    print('  rendering the new-area art of tile %d,%d without the moved borders (styled2, ~40 s)' % (col, row), flush=True)
    t = styled2.render_tile(col, row)
    Image.fromarray(t).save(fn)
    open(fn + '.key', 'w').write(key)
    return t.astype(np.float32)


def newart_erase(img, mask, edges, feather=4.0):
    """Erase masked pixels where the deframe tiles show the new-area art unchanged (deframe tile == build/tiles_new):
    there the tile is re-rendered without the moved borders (newart_clean) and the difference is added, so the
    parchment grain, coasts and the other borders stay exactly those of the surrounding art (fillart's quilted old-art
    grain read as lighter patches at the Khorasan junctions).  Returns the bool mask of the pixels it handled (the rest
    is left to the caller)."""
    D = C.comp(True)
    done = np.zeros(mask.shape, bool)
    for r in range(4):
        for c in range(4):
            sl = (slice(r * TS, (r + 1) * TS), slice(c * TS, (c + 1) * TS))
            m = mask[sl]
            p_old = os.path.join(C.BUILD, 'tiles_new', 'tile_%d_%d.png' % (c, r))
            if not m.any() or not os.path.exists(p_old):
                continue
            S_old = np.asarray(Image.open(p_old).convert('RGB')).astype(np.float32)
            same = ndimage.gaussian_filter(np.abs(D[sl].astype(np.float32) - S_old).max(-1), 2.0) < 4.0
            same = ndimage.binary_erosion(same, iterations=6)
            sel = m & same
            if not sel.any():
                continue
            S_new = newart_clean(c, r, edges)
            a = ndimage.gaussian_filter(sel.astype(np.float32), feather)[..., None]
            img[sl] = img[sl] + (S_new - S_old) * a
            done[sl] = sel
    return done


def erase_old_borders(img, W, W2, band=42, E=None, E2=None, polys=None):
    """The deframe tiles already carry the straight old-edge borders of the 1789 provinces (ink + rim).  Where a
    border moved (W -> W2) restore the art under the old one: the original tile (with deframe's tonal gain) inside
    the neatline, re-synthesised parchment in the margins."""
    from PIL import ImageDraw
    old = []
    for key in W2:
        if W[key]['poly'] != W2[key]['poly']:
            d = Polygon(W[key]['poly']).boundary.difference(Polygon(W2[key]['poly']).boundary.buffer(0.5))
            old += [g for g in (d.geoms if hasattr(d, 'geoms') else [d]) if g.length > 1]
    # moved borders of the extension pieces (design.py's old-edge junction fixes): the old run between them
    if E and E2:
        from shapely.ops import unary_union
        for key in E2:
            if key in E and E[key] != E2[key]:
                b0 = unary_union([Polygon(p).boundary for p in E[key]])
                b1 = unary_union([Polygon(p).boundary for p in E2[key]] + [Polygon(v['poly']).boundary for v in W2.values()])
                d = b0.difference(b1.buffer(0.5))
                d = d.difference(Polygon([(19930.0 - 1, -2000), (19930.0 + 1, -2000), (19930.0 + 1, 14000), (19930.0 - 1, 14000)]).buffer(2.0))
                old += [g for g in (d.geoms if hasattr(d, 'geoms') else [d]) if g.length > 30]
    erase_old_borders.mask = None
    erase_old_borders.newart = None
    if not old:
        return img
    m = Image.new('L', (img.shape[1], img.shape[0]), 0); dr = ImageDraw.Draw(m)
    for ln in old:
        dr.line([tuple(C.w2p(x, z)) for x, z in ln.coords], fill=255, width=2 * band)
    mask = np.asarray(m) > 0
    print('  erasing %d old border runs (%.0f k px)' % (len(old), mask.sum() / 1000))
    ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    # where deframe kept the original art (it blends into the new art from x 3600 / y 3710 on: east / south of that
    # the original tile shows the old sheet's frame and stains, so the margins' rule applies there too)
    inside = (xs >= NEAT[0]) & (xs < 3600) & (ys >= NEAT[1]) & (ys < 3710)
    O = C.comp(False).astype(np.float32)
    # inside the neatline: the original pixels, scaled by deframe's smooth gain (vignette flattening)
    sel = mask & inside
    if sel.any():
        y0, y1 = ys[sel].min() - 60, ys[sel].max() + 61; x0, x1 = xs[sel].min() - 60, xs[sel].max() + 61
        y0, x0 = max(y0, 0), max(x0, 0)
        keep = ~mask[y0:y1, x0:x1]
        def lp(a, w, s=30):
            wf = ndimage.gaussian_filter(w.astype(np.float32), s)
            return np.stack([ndimage.gaussian_filter(a[..., k] * w, s) for k in range(3)], -1) / np.maximum(wf, 1e-3)[..., None]
        gain = lp(img[y0:y1, x0:x1], keep) / np.maximum(lp(O[y0:y1, x0:x1], keep), 1.0)
        rest = O[y0:y1, x0:x1] * np.clip(gain, 0.6, 1.6)
        a = ndimage.gaussian_filter(sel[y0:y1, x0:x1].astype(np.float32), 2.0)[..., None]
        img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a) + rest * a
    outside = mask & ~inside
    # where the deframe tiles show the new-area art: that art re-rendered without the moved borders (same grain,
    # coasts and other borders as around it); elsewhere in the margins re-synthesised parchment
    na = newart_erase(img, outside, _newart_edges(W2, W, polys)) if outside.any() and polys else np.zeros_like(outside)
    if (outside & ~na).any():
        fillart.fill(img, outside & ~na)
    print('  erased in the new-area art: %.0f k px, re-synthesised: %.0f k px' % (na.sum() / 1000, (outside & ~na).sum() / 1000))
    erase_old_borders.mask = mask
    erase_old_borders.newart = na
    return img


def _sea_world():
    """The painted sea of the old map as a world-coordinate shapely geometry (complement of geo.land_polys)."""
    if not hasattr(_sea_world, 'g'):
        from shapely.geometry import box
        x0, z1 = C.p2w(0, 0); x1, z0 = C.p2w(4 * TS, 4 * TS)
        _sea_world.g = box(x0, z0, x1, z1).difference(geo.land_polys())
    return _sea_world.g


def base_canvas():
    """deframe tiles with row 0 from northfix.py.  Reads build/oldarea/north (northfix's own copy), never this
    script's output in build/oldarea/tiles, so a re-run does not draw the borders a second time."""
    img = C.comp(True).copy()
    north = os.path.join(C.OUT, 'north')
    for c in range(4):
        p = os.path.join(north, 'tile_%d_0.png' % c)
        if not os.path.exists(north):
            p = os.path.join(TILES, 'tile_%d_0.png' % c)      # (old layout: run northfix.py first)
        if os.path.exists(p):
            img[0:TS, c * TS:(c + 1) * TS] = np.asarray(Image.open(p).convert('RGB'))
    return img


def main():
    polys, W, W2, E2 = load()
    O = geo.original_polys()
    # every land polygon with an owner name
    owners = []                                           # (name, shapely polygon)
    for pid, p in polys.items():
        owners.append((C.NAMES[pid], Polygon(p)))
    from shapely.ops import unary_union as _uu
    ours = _uu([Polygon(p) for p in polys.values()]).buffer(0)
    for name, G in O.items():
        if G.intersection(ours).area > 1000:          # carved at build time (Kursk by Chechenya, Moscu by Ural)
            G = G.difference(ours)
        owners.append((name, G))
    for key, v in W2.items():
        owners.append((key, Polygon(v['poly'])))
    for name, pieces in E2.items():
        for pl in pieces:
            owners.append((name, Polygon(pl)))
    geoms = [g for _, g in owners]
    tree = STRtree(geoms)
    orig_boundary = STRtree([G.boundary for G in O.values()])
    orig_bl = [G.boundary for G in O.values()]

    def owner(pt):
        for i in tree.query(Point(pt)):
            if geoms[i].contains(Point(pt)):
                return owners[i][0]
        return None

    def on_original(a, b):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        for i in orig_boundary.query(Point(m).buffer(3)):
            if orig_bl[i].distance(Point(m)) < 1.5 and orig_bl[i].distance(Point(a)) < 1.5 and orig_bl[i].distance(Point(b)) < 1.5:
                return True
        return False

    base = base_canvas().astype(np.float32)
    base, ch1 = oldedge.lift_out_of_play(base)            # the old playable edge's darkening (oldedge.py)
    base, ch2 = oldedge.refill_blots(base)                # deframe's smooth blot fills -> textured parchment
    base, ch3 = oldedge.top_seam(base)                    # the old top edge's seam (Arctic strip above it)
    base, ch4 = oldedge.restore_gulf(base)                # the painted Gulf at the old SE corner (provinces follow it)
    ch2 = ch2 | ch3 | ch4
    base = erase_old_borders(base, W, W2, E=load.E_orig, E2=E2, polys=polys)
    cv = ink.Canvas(base)
    pre = ch1 | ch2
    for r in range(4):
        for c in range(4):
            if pre[r * TS:(r + 1) * TS, c * TS:(c + 1) * TS].any():
                cv.touched[r, c] = True
    lum = cv.img.mean(-1)
    inkpx = (cv.img[..., 0] - cv.img[..., 1] > 16) & (cv.img[..., 0] - cv.img[..., 2] > 22) & (lum < 150)
    inkpx = ndimage.binary_dilation(inkpx, iterations=3)

    # strict version for the extension pieces: a real painted border, not the faint reddish ghost of an erased one
    inkstrict = (cv.img[..., 0] - cv.img[..., 1] > 30) & (cv.img[..., 0] - cv.img[..., 2] > 40) & (lum < 135)
    inkstrict = ndimage.binary_dilation(inkstrict, iterations=3)

    def has_ink(a, b, mask=None):
        """Does the art already show a reddish ink line along the segment a-b?"""
        inkpx_ = inkpx if mask is None else mask
        (ax, ay), (bx, by) = C.w2p(*a), C.w2p(*b)
        n = max(2, int(math.hypot(bx - ax, by - ay) / 3))
        hit = 0
        for t in np.linspace(0.05, 0.95, n):
            x, y = int(ax + (bx - ax) * t), int(ay + (by - ay) * t)
            if 0 <= y < inkpx_.shape[0] and 0 <= x < inkpx_.shape[1] and inkpx_[y, x]:
                hit += 1
        return hit / n > 0.4
    new_lines = []                                        # ink
    rim_jobs = {}                                         # owner name -> list of lines
    ext_rim = {}                                          # (name, piece index) -> lines (extension pieces)
    stats = {'coast': 0, 'orig': 0, 'new': 0, 'ext': 0}
    EDGE_E, EDGE_S = 19930.0, -880.0                      # the old map edge (design.py)

    def on_old_edge(a, b):
        return (abs(a[0] - EDGE_E) < 2 and abs(b[0] - EDGE_E) < 2) or (abs(a[1] - EDGE_S) < 2 and abs(b[1] - EDGE_S) < 2)

    def pieces(a, b, step=100.0):
        """Edges along the old map edge are tested in short pieces: the neighbour can change along them (the
        extension pieces do not always meet the old-area provinces at the same point)."""
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = int(L // step) + 1 if on_old_edge(a, b) else 1
        pts = [(a[0] + (b[0] - a[0]) * t / k, a[1] + (b[1] - a[1]) * t / k) for t in range(k + 1)]
        return list(zip(pts[:-1], pts[1:]))

    def ccw(pl):
        pl = [tuple(q) for q in pl]
        if pl[0] == pl[-1]:
            pl = pl[:-1]
        return pl if Polygon(pl).exterior.is_ccw else pl[::-1]

    def in_comp(a, b):
        (ax, ay), (bx, by) = C.w2p(*a), C.w2p(*b)
        lim = 4 * TS + 20
        return not ((ax > lim and bx > lim) or (ay > lim and by > lim) or (ax < -20 and bx < -20) or (ay < -20 and by < -20))

    loops = [(C.NAMES[pid], ccw(p), None) for pid, p in polys.items()]
    # extension pieces of our provinces: their borders with each other / the old-area provinces inside the old
    # tiles (x < 4096) are drawn nowhere else (styled2 drew the new-area tiles only)
    loops += [(name, ccw(pl), k) for name, pls in E2.items() if name in C.NAMES.values() for k, pl in enumerate(pls)]
    ext_runs = {}
    for me, p, piece in loops:
        n = len(p)
        for i in range(n):
            for a, b in pieces(p[i], p[(i + 1) % n]):
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 1e-6 or not in_comp(a, b):
                    continue
                nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L          # right-hand normal = outward for CCW
                m = ((a[0] + b[0]) / 2 + nx * 4, (a[1] + b[1]) / 2 + ny * 4)
                other = owner(m)
                if other is None or other == me:
                    stats['coast'] += 1
                    continue
                rim_add = (lambda ln: ext_rim.setdefault((me, piece), []).append(ln)) if piece is not None else                           (lambda ln: rim_jobs.setdefault(me, []).append(ln))
                if piece is not None:
                    # extension piece: decided per run of segments with the same neighbour (below)
                    ext_runs.setdefault((me, piece), []).append((a, b, other, has_ink(a, b, inkstrict), L))
                    continue
                if on_original(a, b):
                    stats['orig'] += 1
                    rim_add([a, b])
                    if not has_ink(a, b):                                  # outline without painted ink (Moscu / Kursk east edge)
                        new_lines.append([a, b]); stats['orig_inked'] = stats.get('orig_inked', 0) + 1
                        # the 2005 map ended there, so the original side has no pillow rim either: give it one, else
                        # the one-sided shading reads as a folded sheet edge
                        rim_jobs.setdefault(other, []).append([a, b])
                    continue
                stats['new'] += 1
                new_lines.append([a, b])
                rim_add([a, b])
                if other not in C.NAMES.values():                          # the other side is not one of ours
                    rim_jobs.setdefault(other, []).append([a, b])
    # borders between two 1789 provinces of the bigger map inside the erased bands (the erase brush also wipes the
    # painted borders right next to a moved one, e.g. Kandahar | Baluchistan at the Khorasan junction): redraw them
    em = erase_old_borders.mask
    if em is not None:
        em = ndimage.binary_erosion(em, iterations=3)
        if erase_old_borders.newart is not None:                  # the re-rendered new art kept those borders
            em &= ~ndimage.binary_dilation(erase_old_borders.newart, iterations=3)
        seen = set()
        wnames = set(W2)
        for key, v in W2.items():
            p = ccw(v['poly'])
            n = len(p)
            for i in range(n):
                a, b = p[i], p[(i + 1) % n]
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 1e-6 or not in_comp(a, b):
                    continue
                mx, my = C.w2p((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                if not (0 <= int(my) < em.shape[0] and 0 <= int(mx) < em.shape[1] and em[int(my), int(mx)]):
                    continue
                nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
                other = owner(((a[0] + b[0]) / 2 + nx * 4, (a[1] + b[1]) / 2 + ny * 4))
                if other is None or other == key or other not in wnames:
                    continue
                k_ = (min(tuple(a), tuple(b)), max(tuple(a), tuple(b)))
                if k_ in seen:
                    continue
                seen.add(k_)
                stats['world'] = stats.get('world', 0) + 1
                new_lines.append([a, b])
                rim_jobs.setdefault(key, []).append([a, b]); rim_jobs.setdefault(other, []).append([a, b])
    # extension pieces of ORIGINAL provinces north of the old top edge (design.py ARCTIC_STRIP: Finnmark -> Noruega,
    # Kola / Tersky -> Moscu): their borders with a different province (another piece, the 2005 mesh below the edge,
    # a 1789 province) are painted nowhere else.  Same owner (piece over its own mesh), the sea and our provinces
    # (their own loop draws those edges) are skipped.
    seas = {n_ for n_, G in O.items() if G.intersection(_sea_world()).area > 0.5 * G.area}
    seen_a = set()
    for name, pls in E2.items():
        if name in C.NAMES.values():
            continue
        for k, pl in enumerate(pls):
            if max(q[1] for q in pl) <= 12520.0:          # only the Arctic pieces
                continue
            p = ccw(pl)
            n = len(p)
            for i in range(n):
                a, b = p[i], p[(i + 1) % n]
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 1e-6 or not in_comp(a, b):
                    continue
                nx, ny = (b[1] - a[1]) / L, -(b[0] - a[0]) / L
                other = owner(((a[0] + b[0]) / 2 + nx * 4, (a[1] + b[1]) / 2 + ny * 4))
                if other is None or other == name or other in seas or other in C.NAMES.values():
                    continue
                key_ = (min(tuple(a), tuple(b)), max(tuple(a), tuple(b)))
                if key_ in seen_a or has_ink(a, b, inkstrict):
                    continue
                seen_a.add(key_)
                stats['arctic'] = stats.get('arctic', 0) + 1
                new_lines.append([a, b])
                # rims inside the whole province (mesh + its pieces), so the shading runs on across the old edge
                # instead of stopping at the piece's straight south side
                rim_jobs.setdefault(name, []).append([a, b])
                rim_jobs.setdefault(other, []).append([a, b])
    # extension-piece borders: a whole run (same neighbour, contiguous) is drawn when most of it shows no ink yet;
    # the new-area art has its own borders, but deframe / the old-new blend erased them in the old tiles' east strip
    for (me, piece), segs in ext_runs.items():
        runs = []
        for sg in segs:
            if runs and runs[-1][-1][2] == sg[2] and runs[-1][-1][1] == sg[0]:
                runs[-1].append(sg)
            else:
                runs.append([sg])
        if len(runs) > 1 and runs[0][0][0] == runs[-1][-1][1] and runs[0][0][2] == runs[-1][-1][2]:
            runs[0] = runs.pop() + runs[0]                             # the ring wraps around
        for run in runs:
            # within a run: the stretches without painted ink (short inked gaps < 120 units bridged), if long enough
            # (a run can be half painted, e.g. a new junction chord continuing an existing new-area border)
            stretches, cur, gap = [], [], []
            for sg in run:
                if sg[3]:
                    gap.append(sg)
                    continue
                if cur and gap and sum(g[4] for g in gap) >= 120.0:
                    stretches.append(cur); cur = []
                cur += gap + [sg] if cur else [sg]
                gap = []
            if cur:
                stretches.append(cur)
            other = run[0][2]
            for st_ in stretches:
                if sum(sg[4] for sg in st_) < 150.0:
                    continue
                for a, b, _, _, _ in st_:
                    stats['ext'] += 1
                    new_lines.append([a, b]); ext_rim.setdefault((me, piece), []).append([a, b])
                    if other not in C.NAMES.values():
                        rim_jobs.setdefault(other, []).append([a, b])
    print('edges: %(coast)d coast/same, %(orig)d on original outlines (%(orig_inked)d of them without ink), %(new)d new borders, %(ext)d extension-piece borders, %(world)d redrawn 1789 borders, %(arctic)d Arctic-strip borders' % dict(stats, orig_inked=stats.get('orig_inked', 0), world=stats.get('world', 0), arctic=stats.get('arctic', 0)))
    # merge consecutive segments into polylines for nicer joins
    def merge(segs):
        out = []
        for s in segs:
            if out and out[-1][-1] == s[0]:
                out[-1].append(s[1])
            else:
                out.append(list(s))
        return out
    cv.draw_ink(merge(new_lines))
    from shapely.ops import unary_union
    by_name = {}
    for n_, g in owners:                                  # every piece of a name (original mesh + extension pieces)
        if n_ not in C.NAMES.values():
            by_name.setdefault(n_, []).append(g)
    by_name = {n_: unary_union(gs).buffer(0) for n_, gs in by_name.items()}
    # an old-area province's pillow rim runs over its whole shape, main polygon and extension pieces together: shaded
    # per piece it stopped at the internal edge (the old map edge), a thin straight seam next to the junctions
    own_lines = {}
    for (name, k), lines in ext_rim.items():
        own_lines.setdefault(name, []).extend(lines)
    for name, lines in rim_jobs.items():
        if name in C.NAMES.values():
            own_lines.setdefault(name, []).extend(lines)
    for pid, p in polys.items():
        name = C.NAMES[pid]
        if name not in own_lines:
            continue
        G = unary_union([Polygon(p).buffer(0.3)] + [Polygon(q).buffer(0.3) for q in E2.get(name, [])]).buffer(-0.3)
        for q in (list(G.geoms) if G.geom_type == 'MultiPolygon' else [G]):
            if q.area > 1000.0:
                cv.draw_rim(list(q.exterior.coords), merge(own_lines[name]))
    for name, lines in rim_jobs.items():
        if name in C.NAMES.values():
            continue
        else:
            G = by_name.get(name)
            if G is None:
                continue
            parts = list(G.geoms) if G.geom_type == 'MultiPolygon' else [G]
            for q in parts:
                cv.draw_rim(list(q.exterior.coords), merge(lines))
    written = cv.save(TILES)
    # tiles changed only by northfix are already there; make sure every touched tile is written
    print('\n'.join(written))
    # preview of the whole old area at 1/2 scale, and before/after crops
    after = np.clip(cv.img, 0, 255).astype(np.uint8)
    before = C.comp(True)
    Image.fromarray(after).resize((2048, 2048), Image.LANCZOS).save(os.path.join(C.OUT, 'preview.png'))
    crops = {'caspian': (14000, 20192, 3500, 9500), 'urals_north': (13500, 20192, 8800, 13443),
             'gulf': (15500, 20192, -1000, 4300), 'sahara': (473, 6200, -1000, 1800)}
    for name, (x0, x1, z0, z1) in crops.items():
        px0, py0 = C.w2p(x0, z1); px1, py1 = C.w2p(x1, z0)
        px0, py0, px1, py1 = int(px0), int(py0), int(px1), int(py1)
        b = Image.fromarray(before[py0:py1, px0:px1]); a = Image.fromarray(after[py0:py1, px0:px1])
        s = min(1.0, 900.0 / a.width)
        if s < 1:
            b = b.resize((int(b.width * s), int(b.height * s)), Image.LANCZOS); a = a.resize(b.size, Image.LANCZOS)
        Wimg = Image.new('RGB', (a.width, a.height * 2 + 12), (255, 255, 255)); Wimg.paste(b, (0, 0)); Wimg.paste(a, (0, a.height + 12))
        Wimg.save(os.path.join(C.OUT, 'before_after_%s.png' % name))
    print('preview + crops written to', C.OUT)


if __name__ == '__main__':
    main()

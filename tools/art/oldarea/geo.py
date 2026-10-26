"""Geometry derived from the painted art: the land/sea mask of the old map, land polygons (shapely), the original
province polygons (polygonised outlines) and helpers to clip hand-designed claims against them.

Results are cached in build/oldarea/work/.
"""
import os, sys, json, collections
import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point, box
from shapely.ops import unary_union, polygonize
from shapely import affinity
import common as C

WORK = os.path.join(C.OUT, 'work')
os.makedirs(WORK, exist_ok=True)
TS = C.TS
# the sheet's neatline in composite px: original art inside, deframed fill outside
NEAT = (192, 266, 3904, 3830)      # x0, y0, x1, y1
_c = {}


def sea_mask():
    """bool 4096x4096: painted sea (original tiles inside the neatline, deframed tiles in the margins)."""
    fn = os.path.join(WORK, 'sea_mask.npy')
    if 'sea' in _c:
        return _c['sea']
    if os.path.exists(fn):
        _c['sea'] = np.load(fn)
        return _c['sea']
    orig = C.comp(False).astype(np.int16)
    defr = C.comp(True).astype(np.int16)
    x0, y0, x1, y1 = NEAT
    img = defr.copy()
    img[y0:y1, x0:x1] = orig[y0:y1, x0:x1]
    R, G, B = img[..., 0], img[..., 1], img[..., 2]
    sea = (B > R + 8)
    sea = ndimage.binary_opening(sea, iterations=3)
    sea = ndimage.binary_closing(sea, iterations=3)
    # drop sea specks (< 400 px) and land specks inside sea (< 400 px)
    lab, n = ndimage.label(sea)
    sizes = ndimage.sum(sea, lab, range(1, n + 1))
    sea = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 400])
    land = ~sea
    lab, n = ndimage.label(land)
    sizes = ndimage.sum(land, lab, range(1, n + 1))
    land = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 400])
    sea = ~land
    np.save(fn, sea)
    _c['sea'] = sea
    return sea


def _trace_boundaries(mask):
    """Closed iso-contours (level 0.5) of a bool mask by marching squares; returns rings of (px, py) in pixel-centre
    coordinates (pixel (x, y) spans x..x+1 so its centre is x+0.5)."""
    m = np.pad(mask, 1).astype(np.uint8)
    h, w = m.shape
    idx = m[:-1, :-1] * 8 + m[:-1, 1:] * 4 + m[1:, 1:] * 2 + m[1:, :-1]      # tl, tr, br, bl
    # edge midpoints of cell (y, x) (corners at pixel centres): T=(x+1, y+.5) wait: define corners tl=(x,y) tr=(x+1,y)
    T = lambda y, x: (x + 0.5, y); R = lambda y, x: (x + 1.0, y + 0.5); B = lambda y, x: (x + 0.5, y + 1.0); L = lambda y, x: (x, y + 0.5)
    table = {1: [(L, B)], 2: [(B, R)], 3: [(L, R)], 4: [(T, R)], 5: [(L, T), (B, R)], 6: [(T, B)], 7: [(L, T)],
             8: [(T, L)], 9: [(T, B)], 10: [(T, R), (B, L)], 11: [(T, R)], 12: [(L, R)], 13: [(B, R)], 14: [(L, B)]}
    segs = []
    for case, lst in table.items():
        ys, xs = np.nonzero(idx == case)
        for f, g in lst:
            a = np.stack([xs + 0.5 if f in (T, B) else (xs + 1.0 if f is R else xs.astype(float)),
                          ys.astype(float) if f is T else (ys + 1.0 if f is B else ys + 0.5)], 1)
            b = np.stack([xs + 0.5 if g in (T, B) else (xs + 1.0 if g is R else xs.astype(float)),
                          ys.astype(float) if g is T else (ys + 1.0 if g is B else ys + 0.5)], 1)
            segs.append(np.concatenate([a, b], 1))
    segs = np.concatenate(segs, 0)
    # link: every endpoint is shared by exactly two segments
    key = lambda p: (int(round(p[0] * 2)), int(round(p[1] * 2)))
    adj = collections.defaultdict(list)
    for i, s in enumerate(segs):
        adj[key(s[:2])].append(i); adj[key(s[2:])].append(i)
    used = np.zeros(len(segs), bool)
    rings = []
    for i0 in range(len(segs)):
        if used[i0]:
            continue
        ring = []
        i = i0; p = key(segs[i][:2])
        while not used[i]:
            used[i] = True
            s = segs[i]
            a, b = key(s[:2]), key(s[2:])
            q = b if a == p else a
            ring.append((q[0] / 2.0 - 1.0, q[1] / 2.0 - 1.0))      # unpad; pixel-centre coords
            nxt = [j for j in adj[q] if j != i]
            if not nxt:
                break
            i = nxt[0]; p = q
        if len(ring) > 3:
            rings.append(ring)
    return rings


def land_polys(tol_px=2.0):
    """Land of the old map as a shapely (Multi)Polygon in world coordinates, simplified by tol_px composite px."""
    key = 'land_%s' % tol_px
    if key in _c:
        return _c[key]
    fn = os.path.join(WORK, 'land_%s.wkb' % tol_px)
    if os.path.exists(fn):
        from shapely import wkb
        _c[key] = wkb.loads(open(fn, 'rb').read())
        return _c[key]
    land = ~sea_mask()
    rings = _trace_boundaries(land)
    polys = []
    for r in rings:
        if len(r) < 8:
            continue
        p = Polygon(r)
        if not p.is_valid:
            p = p.buffer(0)
        if p.area < 50:
            continue
        p = p.simplify(tol_px, preserve_topology=True)
        polys.append(p)
    # rings of holes are separate polygons here: rebuild with polygonize of all boundaries
    lines = unary_union([p.exterior for p in polys if not p.is_empty])
    faces = list(polygonize(lines))
    # a face is land if its representative point is land in the mask
    out = []
    for f in faces:
        rp = f.representative_point()
        px, py = int(round(rp.x)), int(round(rp.y))
        if 0 <= px < land.shape[1] and 0 <= py < land.shape[0] and land[py, px]:
            out.append(f)
    L = unary_union(out)
    # composite px -> world
    L = affinity.affine_transform(L, [C.TILE_W / TS, 0, 0, -C.TILE_H / TS, C.COLS[0], C.ROWS[4]])
    from shapely import wkb
    open(fn, 'wb').write(wkb.dumps(L))
    _c[key] = L
    return L


def original_polys():
    """name -> shapely polygon of each original province mesh (from its outline edges)."""
    if 'orig' in _c:
        return _c['orig']
    out = {}
    for name, edges in C.outlines().items():
        if not edges:
            continue
        edges = list(edges)
        # vertices duplicated at UV seams can differ by a few tenths: merge vertices closer than 3 units
        from scipy.spatial import cKDTree
        verts = sorted({v for e in edges for v in e})
        tree = cKDTree(verts)
        rep = {}
        for i, v in enumerate(verts):
            if v in rep:
                continue
            for j in tree.query_ball_point(v, 3.0):
                rep.setdefault(verts[j], v)
        edges = [(rep[a], rep[b]) for a, b in edges if rep[a] != rep[b]]
        # degenerate triangles leave a self-loop and an open gap in the ring: close the gap between the two
        # loose ends (Marruecos, Tripolitania)
        edges = [(a, b) for a, b in edges if a != b]
        deg = collections.Counter()
        for a, b in edges:
            deg[a] += 1; deg[b] += 1
        loose = [v for v, d in deg.items() if d == 1]
        while len(loose) >= 2:
            v = loose.pop()
            w = min(loose, key=lambda q: (q[0] - v[0]) ** 2 + (q[1] - v[1]) ** 2)
            loose.remove(w)
            edges.append((v, w))
        lines = unary_union([LineString([a, b]) for a, b in edges])
        faces = list(polygonize(lines))
        if faces:
            out[name] = unary_union(faces)
    _c['orig'] = out
    return out


def chain(name, a, b, pts=None):
    """Ordered vertex chain of province `name`'s outline from the vertex nearest a to the vertex nearest b
    (shortest way round the ring).  Returns list of (x, z) including both ends."""
    P = original_polys()[name]
    if isinstance(P, MultiPolygon):
        P = max(P.geoms, key=lambda g: g.area)
    ring = list(P.exterior.coords)[:-1]
    def nearest(q):
        return min(range(len(ring)), key=lambda i: (ring[i][0] - q[0]) ** 2 + (ring[i][1] - q[1]) ** 2)
    i, j = nearest(a), nearest(b)
    n = len(ring)
    fwd = [ring[(i + k) % n] for k in range((j - i) % n + 1)]
    bwd = [ring[(i - k) % n] for k in range((i - j) % n + 1)]
    def length(ch):
        return sum(np.hypot(ch[k][0] - ch[k - 1][0], ch[k][1] - ch[k - 1][1]) for k in range(1, len(ch)))
    return fwd if length(fwd) <= length(bwd) else bwd


def ccw(poly):
    return list(poly) if Polygon(poly).exterior.is_ccw else list(poly)[::-1]


def to_list(P, nd=1):
    """Largest polygon of P as a CCW vertex list (no closing duplicate)."""
    if isinstance(P, MultiPolygon):
        P = max(P.geoms, key=lambda g: g.area)
    pts = [(round(x, nd), round(y, nd)) for x, y in P.exterior.coords[:-1]]
    return ccw(pts)

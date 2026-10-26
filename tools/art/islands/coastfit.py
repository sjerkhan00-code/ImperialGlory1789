"""Coast fit: the coastal edges of the 1789 provinces follow the painted coast, the way the 2005 meshes do.

Why (2026-10-22, user screenshots of Japan / the Philippines / the Sundas): the world provinces come from a coarse
grid (tools/world_provinces.py); islands.py only cut open-water parts bigger than 800 units2 and added uncovered
islands, so most coasts kept straight grid cuts.  The land mesh carries the owner tint, the highlight and the fog
shading, so where it ran over the painted sea the sea and the art's light shore line showed as a pale band under the
bright tint, and painted land outside it was drawn dark with the sea zone.  The 2005 meshes lie a few px INSIDE the
painted coast (in the dark rim) and never over the sea (measured: 0.02 % of their area on sea, coast edge median
14 px inside the old art's not-blue mask; the new art's coast is a light line at 0..1 px, then the brown rim 3..15 px).

What: in the new art (outside the old sheet OLD_SHEET; pieces of old-area / 2005 meshes also outside the old 4 x 4
tiles + MARGIN, render_borders.py's canvas), each province's geometry (main polygon + extension pieces) is
  * cut to the painted land inset by INSET px (less on small islands: INSET_FRAC of their deepest point), on the
    ocean side only (water seeded by the sea zones; lakes, painted rivers and straits narrower than ~2*RIVER+1 px
    are not cut),
  * grown over uncovered painted land within REACH px, split between provinces by nearest distance (not into the
    parchment margin west of the old sheet, NO_ADD),
  * coasts traced at sub-pixel precision and simplified by SIMPLIFY px,
  * cleaned: hairline gaps between the parts of one province closed, thin sliver pieces and fragments on another
    province's land (old split remnants) dropped and their land shared out again.
Inland borders keep their exact vertices (no rounding), so the painted borders and design.py's lines stay as they
are.  The neighbour lists the build derives (make_map.neighbours + mutual + strait links, ordered as written into the
records) are checked after every pass; where one would change, the contact zone keeps its old geometry and the fit
runs again.  Province ids, names and owners are untouched (geometry only, save-safe).  write_outputs carries the
coast change over to the pre-design snapshots render_borders.py compares, so a re-run of it erases nothing new.

Run order: world_provinces.py -> extend.py -> oldarea/design.py (copy *_fixed) -> islands/islands.py -> THIS
(and again after any change of the map tiles: the land mask is read from them).
    python tools/art/islands/coastfit.py            dry run: build/coastfit/dry/*.json + report, nothing else
    python tools/art/islands/coastfit.py --apply    writes build/world_provinces.json, build/extend/extensions.json
                                                    and their copies in build/oldarea (backups in backups/coastfit_*)
Re-running is safe: build/coastfit/base_*.json keeps the geometry before the first fit; when the current files are
this script's own output (state.json hash) the fit restarts from that base, otherwise the current files are the
new base (an upstream step was re-run).  Verified 2026-10-22: a re-run reproduces the applied files byte for byte.
make_map.py companions: STRAIT_LINKS (frozen strait links) and meshgen.subtract_mesh_bytes_cdt (sea-zone cut).
"""
import os, sys, json, math, hashlib, time, shutil
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)
BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'coastfit')
sys.path.insert(0, os.path.join(TOOLS, 'art', 'oldarea'))
sys.path.insert(0, os.path.join(TOOLS, 'art'))
sys.path.insert(0, TOOLS)
import meshgen as MG
import deframe as DF

TS = 1024
NCOL, NROW = 9, 7
H, W = NROW * TS, NCOL * TS
X0, ZN = MG.COLS[0], MG.ROWS[4]
TW, TH = MG.TILE_W, MG.TILE_H
PXA = (TW / TS) * (TH / TS)                       # world units2 per full-resolution px

INSET = 4.0          # px inside the painted coast (into the brown rim; the light shore line stays outside)
INSET_MIN = 1.0      # px, smallest inset (tiny islands)
INSET_FRAC = 0.30    # small islands: inset = this share of their deepest point
SIMPLIFY = 0.6       # px, Douglas-Peucker tolerance of the traced coast
REACH = 40           # px: uncovered painted land this close to a province joins it
RIVER = 2            # px: water features narrower than ~2*RIVER+1 px (rivers, lines, narrow straits) are not cut
MIN_PART = 400.0     # world units2: smaller parts are dropped (about 20 px)
GAIN_BAND = 110.0    # world units: a neighbour link the fit would create keeps the old geometry where both
                     # provinces lie within this distance of each other (make_map.neighbours: 60 units, 40-unit samples)
NOT_BOX = (MG.COLS[0], MG.COLS[4], MG.ROWS[0], MG.ROWS[4])   # the old 4 x 4 tiles: x0, x1, z0, z1
MARGIN = 350.0       # world units around NOT_BOX left alone (render_borders' 42 px erase band)
NO_TRIM = {'najd', 'kandahar', 'kabul', 'timbuktu', 'baluch', 'hejaz',   # (islands.py; their old-edge runs are design.py's)
           'kokand', 'senegal', 'segu'}


def w2p(x, z):
    return (x - X0) / TW * TS, (ZN - z) / TH * TS


def p2w(px, py):
    return X0 + px / TS * TW, ZN - py / TS * TH


def tile_src(col, row):
    for p in (os.path.join(BUILD, 'oldarea', 'tiles', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'art', 'deframe', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))):
        if os.path.exists(p):
            return p
    return os.path.join(BUILD, 'tiles_png', 'T00%d00%d.png' % (3 - row, col))


def land_mask():
    """bool (H, W): painted land = not blue, from the tiles make_map uses.  deframe.sea_class's test (blue - red > 6)
    on a lighter blur (1 px instead of 3): the 3 px blur loses islets under ~6 px (e.g. off Nuyts Land)."""
    land = np.zeros((H, W), bool)
    for r in range(NROW):
        for c in range(NCOL):
            t = np.asarray(Image.open(tile_src(c, r)).convert('RGB')).astype(np.float32)
            b = ndimage.gaussian_filter(t, (1.0, 1.0, 0))
            land[r * TS:(r + 1) * TS, c * TS:(c + 1) * TS] = (b[..., 2] - b[..., 0]) <= 6
    return land


def raster(geoms, shape=(H, W), origin=(0, 0), value=1, im=None, mode='L'):
    """Fill shapely polygons (world) into an image of `shape` whose px (0, 0) is composite px `origin`."""
    if im is None:
        im = Image.new(mode, (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    ox, oy = origin
    for g in geoms:
        for gg in (g.geoms if hasattr(g, 'geoms') else [g]):
            if gg.geom_type != 'Polygon' or gg.is_empty:
                continue
            d.polygon([(w2p(x, z)[0] - ox, w2p(x, z)[1] - oy) for x, z in gg.exterior.coords], fill=value)
            for h in gg.interiors:
                d.polygon([(w2p(x, z)[0] - ox, w2p(x, z)[1] - oy) for x, z in h.coords], fill=0)
    return im


def signed_distance(inside, clip=48.0):
    """+ px from the nearest outside px for inside px, - for outside px (centre to centre - 0.5); blockwise."""
    out = np.zeros(inside.shape, np.float32)
    B, P = 1024, int(clip) + 2
    for y in range(0, inside.shape[0], B):
        for x in range(0, inside.shape[1], B):
            ya, yb = max(0, y - P), min(inside.shape[0], y + B + P)
            xa, xb = max(0, x - P), min(inside.shape[1], x + B + P)
            m = inside[ya:yb, xa:xb]
            s = np.where(m, ndimage.distance_transform_edt(m) - 0.5, -(ndimage.distance_transform_edt(~m) - 0.5))
            out[y:y + B, x:x + B] = np.clip(s, -clip, clip)[y - ya:y - ya + B, x - xa:x - xa + B]
    return out


# marching squares, inside (f > 0) on the right of the direction of travel (image coords, y down).
# corners tl tr br bl = bits 8 4 2 1; edges T R B L.  Saddles (5, 10): 'c' = centre inside.
_MS = {1: [('L', 'B')], 2: [('B', 'R')], 3: [('L', 'R')], 4: [('R', 'T')], 6: [('B', 'T')], 7: [('L', 'T')],
       8: [('T', 'L')], 9: [('T', 'B')], 11: [('T', 'R')], 12: [('R', 'L')], 13: [('R', 'B')], 14: [('B', 'L')],
       5: [('L', 'B'), ('R', 'T')], 10: [('T', 'L'), ('B', 'R')]}
_MSC = {5: [('L', 'T'), ('R', 'B')], 10: [('T', 'R'), ('B', 'L')]}


def contours(f, x_off=0.0, y_off=0.0):
    """Closed iso-lines f = 0 (linear interpolation) of a float field whose sample (y, x) sits at
    (x + 0.5 + x_off, y + 0.5 + y_off).  Returns rings (n x 2 arrays, px); shells have positive shoelace area in
    image coordinates, holes negative.  The field must be negative along its border."""
    tl, tr, br, bl = f[:-1, :-1], f[:-1, 1:], f[1:, 1:], f[1:, :-1]
    idx = ((tl > 0).astype(np.uint8) * 8 + (tr > 0) * 4 + (br > 0) * 2 + (bl > 0)).astype(np.uint8)
    cells = np.nonzero((idx > 0) & (idx < 15))
    ys, xs = cells
    ii = idx[ys, xs]
    cen = (tl[ys, xs] + tr[ys, xs] + br[ys, xs] + bl[ys, xs]) > 0
    # edge ids: T = h(y, x), B = h(y+1, x), L = v(y, x), R = v(y, x+1); h id = 2*(y*Wc + x), v id = 2*(y*Wc+x)+1
    Wc = f.shape[1] + 1
    def eid(e, y, x):
        if e == 'T': return 2 * (y * Wc + x)
        if e == 'B': return 2 * ((y + 1) * Wc + x)
        if e == 'L': return 2 * (y * Wc + x) + 1
        return 2 * (y * Wc + x + 1) + 1
    def ept(e, y, x):
        if e in ('T', 'B'):
            yy = y if e == 'T' else y + 1
            a, b = f[yy, x], f[yy, x + 1]
            t = a / (a - b)
            return x + t, float(yy)
        xx = x if e == 'L' else x + 1
        a, b = f[y, xx], f[y + 1, xx]
        t = a / (a - b)
        return float(xx), y + t
    start, nxt_pt = {}, {}
    for k in range(len(ys)):
        y, x, c = int(ys[k]), int(xs[k]), int(ii[k])
        segs = _MSC[c] if (c in _MSC and cen[k]) else _MS[c]
        for a, b in segs:
            ea, eb = eid(a, y, x), eid(b, y, x)
            start[ea] = eb
            if ea not in nxt_pt:
                nxt_pt[ea] = ept(a, y, x)
            if eb not in nxt_pt:
                nxt_pt[eb] = ept(b, y, x)
    rings, seen = [], set()
    for e0 in list(start):
        if e0 in seen:
            continue
        ring, e = [], e0
        while e not in seen:
            seen.add(e)
            ring.append(nxt_pt[e])
            e = start.get(e)
            if e is None:
                break
        if len(ring) >= 3:
            a = np.array(ring) + (0.5 + x_off, 0.5 + y_off)
            rings.append(a)
    return rings


def ring_area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def rings_to_polys(rings, simplify):
    """Shells + holes (px rings, orientation as contours()) -> world Polygons, simplified in px."""
    shells, holes = [], []
    for a in rings:
        A = ring_area(a)
        if abs(A) < 1.0:
            continue
        p = Polygon(a)
        if simplify:
            p = p.simplify(simplify, preserve_topology=True)
        if p.is_empty or p.area < 0.5:
            continue
        if not p.is_valid:
            p = p.buffer(0)
            if p.geom_type != 'Polygon':
                p = max(p.geoms, key=lambda q: q.area) if hasattr(p, 'geoms') and len(p.geoms) else p
            if p.is_empty:
                continue
        (shells if A > 0 else holes).append(Polygon(p.exterior))
    tree = STRtree(shells)
    hole_of = {i: [] for i in range(len(shells))}
    for h in holes:
        pt = h.representative_point()
        cand = [i for i in tree.query(pt) if shells[i].contains(pt)]
        if cand:
            hole_of[min(cand, key=lambda i: shells[i].area)].append(h)
    out = []
    for i, s in enumerate(shells):
        g = s
        if hole_of[i]:
            g = s.difference(unary_union(hole_of[i]))
        g = shapely.affinity.affine_transform(g, [TW / TS, 0, 0, -TH / TS, X0, ZN]) if not g.is_empty else g
        for gg in (g.geoms if hasattr(g, 'geoms') else [g]):
            if gg.geom_type == 'Polygon' and not gg.is_empty:
                out.append(gg.buffer(0) if not gg.is_valid else gg)
    return out


import shapely.affinity


def load_json(p):
    return json.load(open(p, encoding='utf8'))


def digest(*objs):
    return hashlib.sha1(json.dumps(objs, sort_keys=True).encode()).hexdigest()


def inputs():
    """(W, E, base_from) : the geometry to fit, from the base snapshot when the current files are our own output."""
    wf, ef = os.path.join(BUILD, 'world_provinces.json'), os.path.join(BUILD, 'extend', 'extensions.json')
    Wc, Ec = load_json(wf), load_json(ef)
    st = os.path.join(OUT, 'state.json')
    bw, be = os.path.join(OUT, 'base_world_provinces.json'), os.path.join(OUT, 'base_extensions.json')
    if os.path.exists(st) and os.path.exists(bw) and os.path.exists(be):
        s = load_json(st)
        if s.get('out_hash') == digest(Wc, Ec):
            return load_json(bw), load_json(be), 'base snapshot (current files are the last coast fit)'
    return Wc, Ec, 'current files'


def mesh_names(Wd):
    import islands as IS
    return IS.mesh_names()


OLD_SHEET = (473.0, 20192.0, -970.0, 14500.0)    # the old hand-painted sheet + its arctic strip (old-style coasts)
# the strip west of the old sheet (x < 473 above z -970) is parchment in the art (the old sheet's margin), not land:
# nothing grows into it (Senegal took 85,000 units2 of it in a first try)
NO_ADD = box(-1e6, -1100.0, 480.0, 1e6)


def edit_region(world):
    """World geometry where coasts may change: world=True everywhere in the new art, i.e. outside the old sheet;
    world=False also outside render_borders.py's canvas (the old 4 x 4 tiles + MARGIN; unused since write_outputs
    keeps the pre-design snapshots in step)."""
    big = box(-1e6, -1e6, 1e6, 1e6)
    if world:
        x0, x1, z0, z1 = OLD_SHEET
        return big.difference(box(x0, z0, x1, z1))
    x0, x1, z0, z1 = NOT_BOX
    return big.difference(box(x0 - MARGIN, z0 - MARGIN, x1 + MARGIN, z1 + MARGIN))


def original_land():
    """name -> polygon of the 2005 land meshes (sites only, never changed here)."""
    import geo
    from igmod import Mng
    m = Mng(open(os.path.join(ROOT, 'data', 'Game', 'GameModes', 'DefModeloGestion.mng'), 'rb').read())
    sea = {r['name']: r['sea'] for r in Mng.parse_provinces(m.section(4))}
    return {n: g for n, g in geo.original_polys().items() if not sea.get(n, 0)}, \
           {n: g for n, g in geo.original_polys().items() if sea.get(n, 0)}


def clean_ring(pts, protect, eps=0.05):
    """Drop duplicate and collinear vertices (they stall the ear clipper), keep protected ones.  No rounding: the
    inland vertices must stay bit-identical to the neighbours' (the base files keep full float precision)."""
    out = []
    for x, z in pts:
        q = (float(x), float(z))
        if not out or math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 1e-6:
            out.append(q)
    while len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-6:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        keep = []
        n = len(out)
        i = 0
        drop = set()
        for i in range(n):
            if (i - 1) % n in drop:
                continue
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            if b in protect:
                continue
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            cr = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if L < 1e-9 or cr / L < eps:
                drop.add(i)
        if drop and len(out) - len(drop) >= 3:
            out = [q for k, q in enumerate(out) if k not in drop]
            changed = True
    return out


def meshable(pts):
    t = [tuple(q) for q in pts]
    if len(t) < 3 or not MG.is_simple(t) or not Polygon(t).is_valid:
        return False
    try:
        tri = MG.triangulate(MG.ccw(t))
    except ValueError:
        return False
    return abs(sum(abs(MG.area(list(x))) for x in tri) - abs(MG.area(t))) < 1.0


def simplify_free(pts, protect, tol):
    """Douglas-Peucker on the runs between protected vertices only (inland borders keep every vertex)."""
    from shapely.geometry import LineString
    pr = [(float(x), float(z)) in protect for x, z in pts]
    if not any(pr):
        q = Polygon(pts).simplify(tol, preserve_topology=True)
        return list(q.exterior.coords)[:-1] if q.geom_type == 'Polygon' and not q.is_empty else pts
    k0 = pr.index(True)
    pts, pr = pts[k0:] + pts[:k0], pr[k0:] + pr[:k0]
    out, run = [], []
    for p, isp in zip(pts + [pts[0]], pr + [True]):
        if isp:
            if run:
                ln = LineString([out[-1]] + run + [p]).simplify(tol, preserve_topology=False)
                out += list(ln.coords)[1:-1]
                run = []
            out.append(p)
        else:
            run.append(p)
    return out[:-1]


def to_ring(g, protect, ccw_like=None):
    """Polygon -> (simple, ear-clippable vertex list (holes filled), tolerance used), or (None, None)."""
    ext = list(Polygon(g.exterior).exterior.coords)[:-1]
    tries = [(0.0, e) for e in (0.05, 0.2, 0.5)] + [(t, 0.05) for t in (0.3, 0.8, 1.5, 3.0)]
    for tol, eps in tries:
        src = simplify_free(ext, protect, tol) if tol else ext
        pts = clean_ring(src, protect, eps)
        if len(pts) < 3:
            return None, None
        if ccw_like is not None and Polygon(pts).exterior.is_ccw != ccw_like:
            pts = pts[::-1]
        if meshable(pts):
            return pts, (tol, eps)
    return None, None


def parts(g):
    return [q for q in (g.geoms if hasattr(g, 'geoms') else [g]) if q.geom_type == 'Polygon' and not q.is_empty]


def neighbour_lists(Wd, Ed):
    """mesh name -> ordered tuple of neighbour names, exactly as make_map.build_mod derives them from the geometry:
    make_map.neighbours (shapes + EXTENSIONS against the original outlines), new-new links made mutual, and the strait
    link of a world province that has no land neighbour."""
    import make_map as MM
    import islands as IS
    MM.EXTENSIONS = Ed
    shapes = {int(k): [tuple(p) for p in v] for k, v in load_json(os.path.join(BUILD, 'oldarea', 'provinces.json')).items()}
    mn = IS.mesh_names()
    name_of = {p: MM.PROVINCES[p][1] for p in shapes}
    pid = 101
    for key in sorted(Wd):
        shapes[pid] = [tuple(p) for p in Wd[key]['poly']]
        MM.PROVINCES[pid] = ('W_' + key, mn[key], key, '', '', None, '')
        name_of[pid] = mn[key]
        pid += 1
    nb = MM.neighbours(shapes)
    raw = {'~' + name_of[p]: {name_of[x[1]] if isinstance(x, tuple) else x for x in lst} for p, lst in nb.items()}
    for a_, lst in list(nb.items()):
        for n_ in lst:
            if isinstance(n_, tuple) and ('NEW', a_) not in nb.get(n_[1], []) and n_[1] in nb:
                nb[n_[1]].append(('NEW', a_))
    def gap(a, b):
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in shapes[a][::2] for q in shapes[b][::2])
    pid_of_mesh = {v: k for k, v in name_of.items()}
    frozen = getattr(MM, 'STRAIT_LINKS', {})
    for p in sorted(shapes):
        if p >= 101 and not nb[p]:
            fz = frozen.get(name_of[p])
            best = (gap(p, pid_of_mesh[fz]), pid_of_mesh[fz]) if fz in pid_of_mesh else min((gap(p, o), o) for o in shapes if o != p)
            if best[0] < 2500.0:
                nb[p].append(('NEW', best[1]))
                if not any(isinstance(x, tuple) and x[1] == p for x in nb[best[1]]):
                    nb[best[1]].append(('NEW', p))
    # ordered, as build_mod writes them into the province records (a link that turns from a land contact into a
    # strait / mutual link moves to the end of the list: Amur's Sakhalin did in a first try); '~name' = the raw
    # land contacts, to tell which link moved
    res = {name_of[p]: tuple(name_of[x[1]] if isinstance(x, tuple) else x for x in lst) for p, lst in nb.items()}
    res.update(raw)
    return res


def contact_zone(a, b, before, after, orig, tol=60.0, step=20.0, r=90.0):
    """Discs round the places where groups a and b come within `tol` (make_map.neighbours' tolerance) of each other,
    before or after the fit: there the old geometry is kept so the link stays exactly as it was."""
    from shapely.geometry import Point
    pts = []
    for G in (before, after):
        ga = G.get(a, orig.get(a)); gb = G.get(b, orig.get(b))
        if ga is None or gb is None or ga.is_empty or gb.is_empty:
            continue
        for g1, g2 in ((ga, gb), (gb, ga)):
            near = g2.boundary.buffer(tol)
            for ln in (g1.boundary.geoms if hasattr(g1.boundary, 'geoms') else [g1.boundary]):
                for i in range(int(ln.length / step) + 1):
                    p = ln.interpolate(i * step)
                    if near.contains(p):
                        pts.append(p)
    return unary_union([p.buffer(r) for p in pts]) if pts else None


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    APPLY = '--apply' in sys.argv
    Wd, Ed, frm = inputs()
    print('input:', frm)
    mesh = mesh_names(Wd)
    key_of = {v: k for k, v in mesh.items()}
    P_old = load_json(os.path.join(BUILD, 'oldarea', 'provinces.json'))
    orig_land, orig_sea = original_land()
    S = load_json(os.path.join(BUILD, 'sea', 'sea_zones.json'))
    ER_W, ER_O = edit_region(True), edit_region(False)
    ER = ER_W                                           # (the wider one: the sliver test)
    def world_group(n):
        # 1789 provinces change in the whole new art (write_outputs carries the coast change over to the pre-design
        # snapshot world_provinces_orig.json, which render_borders.py compares).  Pieces of the old-area / 2005
        # meshes only outside render_borders' canvas: their snapshot (extensions_orig.json) differs from the base by
        # more than design's lines (e.g. Egipto's islet), so a merge there would read as a moved border
        return groups[n]['world']

    # ---- groups: mesh name -> (main polygon or None, [pieces]); fixed sites
    groups = {}
    for k, v in Wd.items():
        groups[mesh[k]] = {'key': k, 'main': [tuple(q) for q in v['poly']], 'pieces': [], 'world': True}
    for n, pls in Ed.items():
        groups.setdefault(n, {'key': None, 'main': None, 'pieces': [], 'world': False})
        groups[n]['pieces'] = [[tuple(q) for q in pl] for pl in pls]
    # fixed sites: the old-area provinces and the 2005 land meshes inside the old sheet (beyond it the build cuts them:
    # Moscu / Kursk reach past the old edge under the world provinces)
    oldsheet = box(473.0, -970.0, 20192.0, 14500.0)
    fixed = [Polygon(v).buffer(0) for v in P_old.values()] + \
            [g.intersection(oldsheet) for g in orig_land.values() if not g.intersection(oldsheet).is_empty]
    geom = {}
    for n, G in groups.items():
        ps = ([Polygon(G['main']).buffer(0)] if G['main'] else []) + [Polygon(p).buffer(0) for p in G['pieces']]
        geom[n] = unary_union(ps).buffer(0)
    geom0 = dict(geom)                                  # the base, kept exactly outside the edit region and in K

    # ---- painted land, ocean, target field
    land = land_mask()
    print('land mask %.0f s' % (time.time() - t0))
    water = ~land
    water_o = ndimage.binary_opening(water, structure=np.ones((2 * RIVER + 1, 2 * RIVER + 1), bool))
    seed_im = raster([Polygon(z['poly']).buffer(0) for z in S.values()] + list(orig_sea.values()))
    seeds = np.asarray(seed_im) > 0
    lab, n = ndimage.label(water_o)
    hit = np.unique(lab[seeds & water_o])
    hit = hit[hit > 0]
    ocean_o = np.isin(lab, hit)
    del lab
    ocean = water & ndimage.binary_dilation(ocean_o, iterations=RIVER + 1)
    del ocean_o, water_o
    print('ocean: %d components seeded, %.1f %% of the map; %.0f s' % (len(hit), 100 * ocean.mean(), time.time() - t0))
    sd = signed_distance(~ocean)                    # + inside the not-ocean (land, lakes, rivers)
    labl, nl = ndimage.label(~ocean)
    rmax = ndimage.maximum(sd, labl, np.arange(1, nl + 1))
    ecomp = np.concatenate([[INSET], np.clip(INSET_FRAC * np.asarray(rmax), INSET_MIN, INSET)]).astype(np.float32)
    f = sd - ecomp[labl]
    # the field outside the edit region is land (no contour there); pad: replicate 2 px, then -1 so rings close
    erm = np.asarray(raster([box(NOT_BOX[0] - MARGIN, NOT_BOX[2] - MARGIN, NOT_BOX[1] + MARGIN, NOT_BOX[3] + MARGIN)])) > 0
    ers = np.asarray(raster([box(OLD_SHEET[0], OLD_SHEET[2], OLD_SHEET[1], OLD_SHEET[3])])) > 0
    f[ers] = 8.0
    fp = np.pad(np.pad(f, 2, mode='edge'), 1, constant_values=-1.0)
    rings = contours(fp, -3.0, -3.0)
    del fp
    T = rings_to_polys(rings, SIMPLIFY)
    del rings
    Ttree = STRtree(T)
    print('target coast: %d polygons, %d vertices; %.0f s' % (len(T), sum(len(p.exterior.coords) for p in T), time.time() - t0))
    target = f > 0
    del f

    def T_local(bb, pad=600.0):
        x0, z0, x1, z1 = bb
        r = box(x0 - pad, z0 - pad, x1 + pad, z1 + pad)
        loc = [shapely.clip_by_rect(T[i], *r.bounds) for i in Ttree.query(r)]
        return unary_union([g for g in loc if not g.is_empty]).buffer(0), r

    # ---- base clean-up: hairline gaps between the parts of one province close; thin sliver pieces (left by earlier
    # splits, e.g. a 1:30 wedge of Kyushu on Honshu's tip) go, their land is shared out again below
    slivers = []
    allnames = list(geom)
    alltree = STRtree([geom[k] for k in allnames] + fixed)
    allgeoms = [geom[k] for k in allnames] + fixed
    def touches_other(g, n):
        return any(allgeoms[i].intersection(g).area > 0.5 for i in alltree.query(g)
                   if i >= len(allnames) or allnames[i] != n)

    def fragment(p, n):
        """A small piece that is no island of its own: it lies on painted land that another province mostly
        covers (e.g. a wedge of Kyushu on Honshu's tip, left by an earlier split).  Its land is shared out again."""
        x0, z0, x1, z1 = p.bounds
        pa, pb = w2p(x0, z1); pc, pd = w2p(x1, z0)
        pa, pb = max(0, int(pa) - 30), max(0, int(pb) - 30)
        pc, pd = min(W, int(pc) + 31), min(H, int(pd) + 31)
        ww, hh = pc - pa, pd - pb
        own = np.asarray(raster([p], (hh, ww), (pa, pb))) > 0
        comp = labl[pb:pd, pa:pc]
        ids = comp[own & (comp > 0)]
        if not len(ids):
            return False                                # (over the sea: the cut deals with it)
        cid = np.bincount(ids).argmax()
        cm = comp == cid
        if cm[0, :].any() or cm[-1, :].any() or cm[:, 0].any() or cm[:, -1].any():
            win = box(p2w(pa, pd)[0], p2w(pa, pd)[1], p2w(pc, pb)[0], p2w(pc, pb)[1])
            oth = [allgeoms[i] for i in alltree.query(win) if i >= len(allnames) or allnames[i] != n]
            om = np.asarray(raster(oth, (hh, ww), (pa, pb))) > 0 if oth else np.zeros_like(own)
            return (om & cm).sum() > 0.5 * cm.sum() and (own & cm).sum() < 0.3 * cm.sum()
        return False                                    # a whole island inside the window: keep it
    for n in list(geom):
        A = geom[n]
        # (gaps up to ~25 units wide; a fill over the sea goes again with the cut below)
        closed = A.buffer(12.0, join_style=2).buffer(-12.0, join_style=2)
        gaps = [g for g in parts(closed.difference(A)) if g.area < 3000.0 and not touches_other(g, n)]
        if gaps:
            A = unary_union([A] + gaps).buffer(0)
        keep_ = []
        for p in parts(A):
            q = 4 * math.pi * p.area / max(p.length, 1e-9) ** 2
            inmain = groups[n]['main'] and p.intersection(Polygon(groups[n]['main']).buffer(0)).area > 0.5 * p.area
            ERn = ER_W if world_group(n) else ER_O
            if q < 0.15 and p.area < 8000.0 and not inmain and p.intersection(ERn).area > 0.5 * p.area:
                slivers.append((n, round(p.area), [round(v) for v in p.representative_point().coords[0]]))
            elif p.area < 8000.0 and not inmain and p.intersection(ERn).area > 0.5 * p.area and fragment(p, n):
                slivers.append((n, round(p.area), [round(v) for v in p.representative_point().coords[0]], 'fragment'))
            else:
                keep_.append(p)
        geom[n] = unary_union(keep_).buffer(0) if keep_ else A
    # fragments that only the cut separates (a sliver piece across a strait leaves a wedge on the far shore)
    for n in list(geom):
        A = geom[n]
        a_in = A.intersection(ER_W if world_group(n) else ER_O)
        if a_in.area < 1.0:
            continue
        Tl, _ = T_local(A.bounds, pad=200.0)
        M0 = Polygon(groups[n]['main']).buffer(0) if groups[n]['main'] else None
        for p in parts(a_in.intersection(Tl)):
            if p.area >= 8000.0 or (M0 is not None and p.intersection(M0).area > 0.5 * p.area):
                continue
            if fragment(p, n):
                geom[n] = geom[n].difference(p).buffer(0)
                slivers.append((n, round(p.area), [round(v) for v in p.representative_point().coords[0]], 'fragment after the cut'))
    print('base: %d thin sliver / fragment pieces dropped' % len(slivers))

    def fit_all(K):
        """Fit every group; K = world geometry kept exactly as it is (neighbour contacts)."""
        hasK = K is not None and not K.is_empty
        ERK_W = ER_W.difference(K) if hasK else ER_W
        ERK_O = ER_O.difference(K) if hasK else ER_O
        sites = {n: g for n, g in geom.items()}
        site_names = list(sites)
        stree = STRtree([sites[n] for n in site_names])
        ftree = STRtree(fixed)
        final, report, problems = {}, [], []
        for n in sorted(groups, key=lambda n: -geom[n].area):
            wg = world_group(n)
            r = fit_one(n, ERK_W if wg else ERK_O, ers if wg else erm, sites, site_names, stree, ftree, final, problems)
            if r:
                report.append(r)
        return final, report, problems

    def fit_one(n, er, notm, sites, site_names, stree, ftree, final, problems):
        """er: edit region (world geometry), notm: raster of where this group may not change."""
        A = geom[n]
        if A.is_empty:
            final[n] = A; return None
        a_in = A.intersection(er)
        if a_in.area < 1.0 and geom0[n].symmetric_difference(A).area < 1.0:
            final[n] = geom0[n]; return None
        Tl, rb = T_local(A.bounds, pad=REACH * 6.0 + 100)
        keep = geom0[n].difference(er)                # outside the edit region (and in K): exactly as it was
        cut = a_in.intersection(Tl)
        # additions: uncovered painted land within REACH px, nearest to this group (window raster)
        x0, z0, x1, z1 = A.bounds
        pa, pb = w2p(x0, z1); pc, pd = w2p(x1, z0)
        pa, pb = max(0, int(pa) - REACH - 8), max(0, int(pb) - REACH - 8)
        pc, pd = min(W, int(pc) + REACH + 9), min(H, int(pd) + REACH + 9)
        ww, hh = pc - pa, pd - pb
        win = box(p2w(pa, pd)[0], p2w(pa, pd)[1], p2w(pc, pb)[0], p2w(pc, pb)[1])
        others = [site_names[i] for i in stree.query(win.buffer(10)) if site_names[i] != n]
        oth_geoms = [final.get(o, sites[o]) for o in others] + [fixed[i] for i in ftree.query(win.buffer(10))]
        lab_im = Image.new('I', (ww, hh), 0)
        raster(oth_geoms, (hh, ww), (pa, pb), value=2, im=lab_im)
        raster([A], (hh, ww), (pa, pb), value=1, im=lab_im)
        labw = np.asarray(lab_im)
        own = labw == 1
        anys = labw > 0
        dist_own = ndimage.distance_transform_edt(~own)
        dist_oth = ndimage.distance_transform_edt(labw != 2) if (labw == 2).any() else np.full(own.shape, 1e9)
        erw = ~notm[pb:pd, pa:pc]
        cand = target[pb:pd, pa:pc] & land[pb:pd, pa:pc] & erw & ~anys & (dist_own <= REACH) & (dist_own < dist_oth)
        cl, cn = ndimage.label(cand)                  # drop specks, keep thin slivers along the province's own edge
        if cn:
            cs = ndimage.sum(cand, cl, np.arange(1, cn + 1))
            cand = np.isin(cl, np.nonzero(cs >= 4)[0] + 1)
        add = None
        if cand.sum() >= 4:
            cand2 = cand | (ndimage.binary_dilation(cand, iterations=2) & own)
            ag = rings_to_polys([a + (pa, pb) for a in contours(np.pad(cand2.astype(np.float32) - 0.5, 1, constant_values=-0.5), -1.0, -1.0)], 0.0)
            if ag:
                add = unary_union(ag).buffer(0).intersection(Tl).intersection(er).difference(NO_ADD)
                if oth_geoms:                       # (cut keeps any existing overlap as it was; additions never overlap)
                    add = add.difference(unary_union(oth_geoms))
        Fg = unary_union([g for g in (keep, cut, add) if g is not None and not g.is_empty]).buffer(0)
        # holes (an ocean lagoon closed off inside the province) stay covered as before: the mesh is one simple ring
        nh = sum(len(p.interiors) for p in parts(Fg))
        Fg = unary_union([Polygon(p.exterior) for p in parts(Fg)
                          if p.area >= MIN_PART or (p.intersection(A).area > 0.9 * p.area and p.area > 60)])
        if oth_geoms and nh:
            ov = Fg.intersection(unary_union(oth_geoms))
            if ov.area > 0.5:                       # a filled hole held another province: leave this group as it was
                problems.append((n, 'filled hole overlaps a neighbour by %.0f units2: kept as it was' % ov.area))
                Fg = geom0[n]
        final[n] = Fg
        A0 = geom0[n]
        return (n, A0.area, Fg.area, A0.difference(Fg).area, Fg.difference(A0).area, nh)

    def to_files(final, problems):
        """final geometry -> (world_provinces dict, extensions dict, notes)."""
        W2 = json.loads(json.dumps(Wd)); E2 = {}
        notes = []
        for n, G in groups.items():
            r = group_to_files(n, G, final, problems, notes, W2, E2)
        return W2, E2, notes

    def group_to_files(n, G, final, problems, notes, W2, E2):
        Fg = final[n]
        protect = set()
        if G['main']:
            protect |= {(float(x), float(z)) for x, z in G['main']}
        for p in G['pieces']:
            protect |= {(float(x), float(z)) for x, z in p}
        ps = sorted(parts(Fg), key=lambda p: -p.area)
        unchanged = not ps or Fg.symmetric_difference(geom0[n]).area <= 1.0
        if not ps:
            problems.append((n, 'empty after fit: kept as it was'))
        if unchanged:
            if G['main']:
                W2[G['key']]['poly'] = [list(q) for q in G['main']]
            if G['pieces']:
                E2[n] = [[list(q) for q in p] for p in G['pieces']]
            return
        pieces = []
        if G['main']:
            M0 = Polygon(G['main']).buffer(0)
            mp = max(ps, key=lambda p: p.intersection(M0).area)
            ring, how = to_ring(mp, protect, ccw_like=Polygon(G['main']).exterior.is_ccw)
            if how and how != (0.0, 0.05):
                notes.append((n, 'main', how))
            if ring is None:
                problems.append((n, 'main polygon not meshable: kept as it was'))
                W2[G['key']]['poly'] = [list(q) for q in G['main']]
                if G['pieces']:
                    E2[n] = [[list(q) for q in p] for p in G['pieces']]
                return
            W2[G['key']]['poly'] = [list(q) for q in ring]
            rest = [p for p in ps if p is not mp]
        else:
            rest = ps
        for p in rest:
            r, how = to_ring(p, protect, ccw_like=True)
            if how and how != (0.0, 0.05):
                notes.append((n, 'piece %.0f' % p.area, how))
            if r is None:
                problems.append((n, 'piece of %.0f units2 not meshable: dropped' % p.area))
                continue
            pieces.append([list(q) for q in r])
        if pieces:
            E2[n] = pieces

    # ---- fit; the neighbour lists the build computes (make_map.neighbours + strait links) must not change: where a
    # link would be lost or gained, the contact zone keeps its old geometry and the fit runs again
    nb0 = neighbour_lists(Wd, Ed)
    K = None
    kept_links = []
    band = {}                                           # pair -> band width, doubled while the pair still changes
    for it in range(6):
        final, report, problems = fit_all(K)
        W2, E2, notes = to_files(final, problems)
        nb1 = neighbour_lists(W2, E2)
        changed = set()
        for a in nb0:
            if a.startswith('~'):
                continue
            l0, l1 = nb0[a], nb1.get(a, ())
            if l0 != l1:                                # a final list differs (content or order): the links that
                moved = set(l0) ^ set(l1)               # appeared / went, and the land contacts that changed
                moved |= nb0.get('~' + a, set()) ^ nb1.get('~' + a, set())
                changed |= {tuple(sorted((a, b))) for b in moved}
        changed = sorted(changed)
        print('pass %d: %.0f s, neighbour links changed: %s' % (it + 1, time.time() - t0, changed or 'none'))
        if not changed:
            break
        kept_links += [c for c in changed if c not in kept_links]
        zones = []
        for a, b in changed:
            gained = any(y in nb1.get(x, ()) and y not in nb0.get(x, ()) for x, y in ((a, b), (b, a)))
            if gained:
                # a new contact: keep the old geometry wherever both lie within the band of each other (wider each
                # pass the contact persists: an added islet or a narrow channel can close the gap farther out)
                band[(a, b)] = band.get((a, b), GAIN_BAND / 2.0) * 2.0
                ga, gb = geom0.get(a, orig_land.get(a)), geom0.get(b, orig_land.get(b))
                if ga is not None and gb is not None:
                    zones.append(ga.buffer(band[(a, b)]).intersection(gb.buffer(band[(a, b)])))
            else:
                zones.append(contact_zone(a, b, geom0, final, orig_land))
        K = unary_union([z for z in zones if z is not None and not z.is_empty] + ([K] if K is not None else []))
    else:
        problems.append(('NEIGHBOURS', 'still differ after 6 passes: %s' % changed))
        if APPLY:
            raise SystemExit('neighbour lists still differ after 6 passes: %s (nothing written)' % changed)
    # ---- report
    rep = sorted(report, key=lambda r: -(r[3] + r[4]))
    lines = ['coast fit %s, inset %.1f px, simplify %.1f px, reach %d px' % (time.strftime('%Y-%m-%d %H:%M'), INSET, SIMPLIFY, REACH),
             'groups changed: %d; removed %.0f units2 (over the sea / outside the inset coast), added %.0f units2 (painted land)'
             % (sum(1 for r in rep if r[3] + r[4] > 1), sum(r[3] for r in rep), sum(r[4] for r in rep)),
             'problems: %s' % (problems or 'none'),
             'rings that needed more cleaning (tolerance, collinear eps): %s' % (notes or 'none'),
             'thin sliver pieces dropped (mesh, units2, at): %s' % (slivers or 'none'),
             'neighbour contact zones kept as they were: %s' % ('none' if K is None else
                 '%d discs, %.0f units2 (links %s)' % (len(parts(K)), K.area, kept_links)), '',
             '%-24s %10s %10s %9s %9s %5s' % ('mesh', 'area0', 'area1', 'removed', 'added', 'holes')]
    for r in rep:
        if r[3] + r[4] > 1:
            lines.append('%-24s %10.0f %10.0f %9.0f %9.0f %5d' % r)
    dst = OUT if APPLY else os.path.join(OUT, 'dry')
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, 'report.txt'), 'w', encoding='utf8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:7]))
    json.dump(W2, open(os.path.join(dst, 'world_provinces.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    json.dump(E2, open(os.path.join(dst, 'extensions.json'), 'w', encoding='utf8'), indent=0)
    if not APPLY:                                       # (the snapshots write_outputs would write, for review)
        W3, E3 = snapshots_in_step(Wd, Ed, W2, E2, frm)
        if W3 is not None:
            json.dump(W3, open(os.path.join(dst, 'world_provinces_orig.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
        if E3 is not None:
            json.dump(E3, open(os.path.join(dst, 'extensions_orig.json'), 'w', encoding='utf8'), indent=0)
    if APPLY:
        write_outputs(Wd, Ed, W2, E2, frm)
    print('done in %.0f s' % (time.time() - t0))
    return W2, E2


def apply_delta(orig_polys, base_g, new_g, main_ref=None):
    """Carry the coast change (new - base added, base - new removed) over to another version of the same geometry
    (design.py's pre-design snapshot, whose coasts equal the base's): rings, or None if that fails."""
    U = unary_union([Polygon(p).buffer(0) for p in orig_polys])
    U2 = U.union(new_g.difference(base_g)).difference(base_g.difference(new_g)).buffer(0)
    protect = {(float(x), float(z)) for p in orig_polys for x, z in p}
    for g in parts(new_g):
        protect |= {(float(x), float(z)) for x, z in g.exterior.coords}
    ps = [g for g in parts(U2) if g.area >= MIN_PART]
    if main_ref is not None and ps:
        ps = [max(ps, key=lambda g: g.intersection(main_ref).area)]
    out = []
    ccw = Polygon(orig_polys[0]).exterior.is_ccw if orig_polys else True
    for g in ps:
        r, how = to_ring(g, protect, ccw_like=ccw)
        if r is None:
            return None
        out.append([list(q) for q in r])
    return out


def snapshots_in_step(Wb, Eb, W2, E2, frm='current files'):
    """render_borders.py erases the painted border wherever a province's pre-design snapshot (oldarea/
    world_provinces_orig.json, extensions_orig.json) differs from the fixed geometry: give the snapshots the same
    coast change, so only design.py's moved lines differ, as before.  Returns (W3, E3) or None where a file is absent.
    A re-run from the base snapshot starts from the snapshots' base copies too (build/coastfit/base_*_orig.json)."""
    f3 = os.path.join(BUILD, 'oldarea', 'world_provinces_orig.json')
    fo = os.path.join(BUILD, 'oldarea', 'extensions_orig.json')
    if frm != 'current files':
        b3, bo = os.path.join(OUT, 'base_world_provinces_orig.json'), os.path.join(OUT, 'base_extensions_orig.json')
        f3 = b3 if os.path.exists(b3) else f3
        fo = bo if os.path.exists(bo) else fo
    W3 = load_json(f3) if os.path.exists(f3) else None
    if W3 is not None:
        for k in W3:
            if k not in W2 or W2[k]['poly'] == Wb[k]['poly'] or W3[k]['poly'] == W2[k]['poly']:
                continue                                # unchanged, or already in step (a re-run)
            if W3[k]['poly'] == Wb[k]['poly']:
                W3[k]['poly'] = W2[k]['poly']
                continue
            B = Polygon(Wb[k]['poly']).buffer(0); N = Polygon(W2[k]['poly']).buffer(0)
            r = apply_delta([W3[k]['poly']], B, N, main_ref=Polygon(W3[k]['poly']).buffer(0))
            if not r:
                raise SystemExit('cannot carry the coast fit over to world_provinces_orig.json: %s' % k)
            W3[k]['poly'] = r[0]
    E3 = load_json(fo) if os.path.exists(fo) else None
    if E3 is not None:
        for k in E3:
            if Eb.get(k) == E2.get(k) or k not in Eb:
                continue
            B = unary_union([Polygon(p).buffer(0) for p in Eb[k]])
            N = unary_union([Polygon(p).buffer(0) for p in E2.get(k, [])])
            r = apply_delta(E3[k], B, N)
            if r is None:
                raise SystemExit('cannot carry the coast fit over to extensions_orig.json: %s' % k)
            E3[k] = r
    return W3, E3


def write_outputs(Wb, Eb, W2, E2, frm):
    """Back up and write the fitted geometry into the build inputs (and keep the design/render copies in step)."""
    wf, ef = os.path.join(BUILD, 'world_provinces.json'), os.path.join(BUILD, 'extend', 'extensions.json')
    f2 = os.path.join(BUILD, 'oldarea', 'world_provinces_fixed.json')
    f3 = os.path.join(BUILD, 'oldarea', 'world_provinces_orig.json')
    fe = os.path.join(BUILD, 'oldarea', 'extensions_fixed.json')
    bk = os.path.join(ROOT, 'backups', 'coastfit_' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bk, exist_ok=True)
    for p in (wf, ef, f2, f3, fe, os.path.join(BUILD, 'oldarea', 'extensions_orig.json')):
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(bk, os.path.relpath(p, BUILD).replace(os.sep, '__')))
    if frm == 'current files':
        json.dump(Wb, open(os.path.join(OUT, 'base_world_provinces.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
        json.dump(Eb, open(os.path.join(OUT, 'base_extensions.json'), 'w', encoding='utf8'), indent=0)
        for src_, dst_ in ((f3, 'base_world_provinces_orig.json'), (os.path.join(BUILD, 'oldarea', 'extensions_orig.json'), 'base_extensions_orig.json')):
            if os.path.exists(src_):
                shutil.copy2(src_, os.path.join(OUT, dst_))
    W3, E3 = snapshots_in_step(Wb, Eb, W2, E2, frm)
    json.dump(W2, open(wf, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    json.dump(E2, open(ef, 'w', encoding='utf8'), indent=0)
    if os.path.exists(f2):
        Wx = load_json(f2)
        for k in Wx:
            if k in W2:
                Wx[k]['poly'] = W2[k]['poly']
        json.dump(Wx, open(f2, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    if W3 is not None:
        json.dump(W3, open(f3, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    if E3 is not None:
        json.dump(E3, open(os.path.join(BUILD, 'oldarea', 'extensions_orig.json'), 'w', encoding='utf8'), indent=0)
    if os.path.exists(fe):
        json.dump(E2, open(fe, 'w', encoding='utf8'), indent=0)
    json.dump({'out_hash': digest(load_json(wf), load_json(ef)), 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
               'backup': os.path.relpath(bk, ROOT)}, open(os.path.join(OUT, 'state.json'), 'w'), indent=1)
    print('written (backups in %s)' % os.path.relpath(bk, ROOT))


if __name__ == '__main__':
    main()

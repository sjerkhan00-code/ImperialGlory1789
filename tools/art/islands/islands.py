"""Islands and coasts of the bigger map that are land in the art but lie outside every province -> extension pieces.

The world provinces (build/world_provinces.json) are one simple polygon each, built from a coarse grid, so many
islands (Philippines, Moluccas, Lesser Sundas, Shikoku, ...) and some coast strips were left without a province:
no owner tint, not clickable.  This script finds every land component of the map art (the tiles make_map uses,
land = not blue) that no province / sea-zone-free polygon covers, outside the hand-painted old area, and adds it
as an extension piece of the right province (build/extend/extensions.json, key = the province's mesh name
'W' + letters of its display name, exactly as make_map.add_world_provinces names it).

Run AFTER tools/art/oldarea/design.py (and after copying its *_fixed.json files):
    python tools/art/islands/islands.py           -> updates build/extend/extensions.json and
                                                     build/oldarea/extensions_fixed.json, build/islands/*
Re-running is safe: the pieces it added last time (build/islands/added.json) are removed first.
"""
import os, sys, json, math, re, unicodedata
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import Polygon, MultiPolygon, Point, box
from shapely.ops import unary_union, nearest_points
from shapely.strtree import STRtree
from shapely import affinity

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)
BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'islands')
sys.path.insert(0, os.path.join(TOOLS, 'art', 'oldarea'))
sys.path.insert(0, os.path.join(TOOLS, 'art'))
sys.path.insert(0, TOOLS)
import common as C, geo
import deframe as DF

TS = 1024
NCOL, NROW = 9, 7
F = 2                                      # detection at 1/2 resolution
MIN_AREA = 1500.0                          # world units2 (an island of ~8 x 8 px on the tiles)
MAX_DIST = 2500.0                          # islands farther than this from every province stay unowned (reported)
OLD = (473.0, 20192.0, -970.0, 12506.0)    # the hand-painted old area (its coasts are inset on purpose)

# historically sensible owners where "nearest province" would be wrong: (lon/lat-free) world boxes -> province key
RULES = [                                            # (x0, x1, z0, z1) of the piece's inner point -> key
    ((34300, 35650, 1900, 2760), 'kyushu'),          # Shikoku (touches the Honshu polygon) and isles round Kyushu
    ((33600, 34300, 600, 1900), 'kyushu'),           # Ryukyu (Satsuma's vassal)
    ((30300, 32000, -6000, -5250), 'sunda'),         # Bali .. Flores, Sumba: the Lesser Sundas
    ((32980, 34300, -5100, -3150), 'moluccas'),      # Halmahera, Ternate, Seram, Buru, Banda
    ((32000, 33700, -2200, -300), None),             # Philippines: the nearest Philippine province
]
EXCLUDE = [                                          # left unowned on purpose
    ((41300, 48000, -9000, -5900), 'New Caledonia / New Hebrides: no 1789 province near (nearest is New Zealand)'),
]
PHILIPPINES = ('luzon', 'visayas', 'mindanao')

WORLD_NAMES = None


def mesh_names():
    """province key -> mesh name, the rule of make_map.add_world_provinces (read-only copy of WORLD_NAMES)."""
    src = open(os.path.join(TOOLS, 'make_map.py'), encoding='utf8').read()
    ns = {}
    for m in re.finditer(r"^WORLD_NAMES(?: = |\.update\()(\{.*?\})\)?\s*$", src, re.S | re.M):
        ns.update(eval(m.group(1)))
    W = json.load(open(os.path.join(BUILD, 'world_provinces.json'), encoding='utf8'))
    out = {}
    for key, w in W.items():
        disp = ns.get(w['name'], w['name'])
        disp = unicodedata.normalize('NFKD', disp).encode('ascii', 'ignore').decode()
        out[key] = 'W' + re.sub(r'[^A-Za-z]', '', disp)
    return out


def tile_src(col, row):
    for p in (os.path.join(BUILD, 'oldarea', 'tiles', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'art', 'deframe', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))):
        if os.path.exists(p):
            return p
    return os.path.join(BUILD, 'tiles_png', 'T00%d00%d.png' % (3 - row, col))


def land_mask():
    """bool (NROW*TS/F, NCOL*TS/F): land in the map art (not blue), from the tiles make_map uses."""
    h, w = NROW * TS // F, NCOL * TS // F
    land = np.zeros((h, w), bool)
    img = np.zeros((h, w, 3), np.uint8)
    for r in range(NROW):
        for c in range(NCOL):
            t = np.asarray(Image.open(tile_src(c, r)).convert('RGB')).astype(np.float32)
            sea = DF.sea_class(t)
            lm = (~sea).reshape(TS // F, F, TS // F, F).mean((1, 3)) > 0.5
            land[r * TS // F:(r + 1) * TS // F, c * TS // F:(c + 1) * TS // F] = lm
            img[r * TS // F:(r + 1) * TS // F, c * TS // F:(c + 1) * TS // F] = t.reshape(TS // F, F, TS // F, F, 3).mean((1, 3)).astype(np.uint8)
    return land, img


def px2w(px, py):
    return C.p2w(px * F, py * F)


def w2px(x, z):
    a, b = C.w2p(x, z)
    return a / F, b / F


def raster(polys, shape):
    m = Image.new('L', (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(m)
    for P in polys:
        for g in (P.geoms if hasattr(P, 'geoms') else [P]):
            if g.is_empty:
                continue
            d.polygon([w2px(x, z) for x, z in g.exterior.coords], fill=255)
            for hole in g.interiors:
                d.polygon([w2px(x, z) for x, z in hole.coords], fill=0)
    return np.asarray(m) > 0


def trace(mask):
    """Polygons (world) of a bool mask's components (outer rings, pixel-centre marching squares)."""
    rings = geo._trace_boundaries(mask)
    polys = []
    for r in rings:
        if len(r) < 4:
            continue
        p = Polygon([px2w(x, y) for x, y in r])
        if not p.is_valid:
            p = p.buffer(0)
        polys.append(p)
    U = unary_union([p for p in polys if not p.is_empty])
    return U


def load_owned(strip_added):
    W = json.load(open(os.path.join(BUILD, 'world_provinces.json'), encoding='utf8'))
    E = json.load(open(os.path.join(BUILD, 'extend', 'extensions.json'), encoding='utf8'))
    if strip_added:
        E = remove_added(E)
    P = json.load(open(os.path.join(BUILD, 'oldarea', 'provinces.json')))
    S = json.load(open(os.path.join(BUILD, 'sea', 'sea_zones.json'), encoding='utf8'))
    prov = {k: Polygon(v['poly']).buffer(0) for k, v in W.items()}
    pieces = [(k, Polygon(p).buffer(0)) for k, v in E.items() for p in v]
    old = [Polygon(v).buffer(0) for v in P.values()] + list(geo.original_polys().values())
    return W, E, prov, pieces, old, S


def remove_added(E):
    fn = os.path.join(OUT, 'added.json')
    if not os.path.exists(fn):
        return E
    added = json.load(open(fn, encoding='utf8'))
    E2 = {}
    for k, v in E.items():
        rm = [json.dumps(p) for p in added.get(k, [])]
        keep = [p for p in v if json.dumps(p) not in rm]
        if keep:
            E2[k] = keep
    return E2


ARCTIC = (473.0, 20192.0, 12506.0, 14500.0)   # north of the old top edge: provinces there are inset from the coast on
                                              # purpose (old-area style), so only detached islands are taken


def candidates(W, E, prov, mesh):
    """Every land province as (mesh name, geometry): world provinces, the old-area pids, the original land meshes
    and all extension pieces (merged per mesh name)."""
    P = json.load(open(os.path.join(BUILD, 'oldarea', 'provinces.json')))
    L = geo.land_polys()
    out = {}
    for k, g in prov.items():
        out.setdefault(mesh[k], []).append(g)
    for pid, v in P.items():
        out.setdefault(C.NAMES[int(pid)], []).append(Polygon(v).buffer(0))
    for n, G in geo.original_polys().items():
        if G.intersection(L).area > 0.5 * G.area:                  # land meshes only
            out.setdefault(n, []).append(G)
    for k, v in E.items():
        for pl in v:
            out.setdefault(k, []).append(Polygon(pl).buffer(0))
    return {k: unary_union(v).buffer(0) for k, v in out.items()}


def split_by_nearest(q, cands, names):
    """Split polygon q between several touching provinces: each part goes to the nearest one (raster EDT)."""
    x0, z0, x1, z1 = q.bounds
    pad = 200.0
    gx0, gz1 = x0 - pad, z1 + pad
    res = 10.0                                                       # world units per cell
    w = int((x1 - x0 + 2 * pad) / res) + 1; h = int((z1 - z0 + 2 * pad) / res) + 1
    def ras(g):
        m = Image.new('L', (w, h), 0); d = ImageDraw.Draw(m)
        for gg in (g.geoms if hasattr(g, 'geoms') else [g]):
            if gg.geom_type == 'Polygon' and not gg.is_empty:
                d.polygon([((x - gx0) / res, (gz1 - z) / res) for x, z in gg.exterior.coords], fill=255)
        return np.asarray(m) > 0
    box_ = box(gx0, gz1 - h * res, gx0 + w * res, gz1)
    dist = np.stack([ndimage.distance_transform_edt(~ras(cands[n].intersection(box_))) for n in names])
    lab = np.argmin(dist, 0)
    out = []
    for i, n in enumerate(names):
        m = lab == i
        rings = geo._trace_boundaries(m)
        parts = [Polygon([(gx0 + x * res, gz1 - y * res) for x, y in r]).buffer(0) for r in rings if len(r) > 3]
        reg = unary_union([pp for pp in parts if not pp.is_empty])
        piece = q.intersection(reg)
        for g in (piece.geoms if hasattr(piece, 'geoms') else [piece]):
            if g.geom_type == 'Polygon' and g.area >= MIN_AREA * 0.5:
                out.append((n, g))
    return out


def meshable(pts):
    """Can make_map's ear clipper (meshgen.triangulate) mesh this polygon completely?"""
    import meshgen as MG
    t = [tuple(q) for q in pts]
    if len(t) < 3 or not MG.is_simple(t) or not Polygon(t).is_valid:
        return False
    try:
        tri = MG.triangulate(MG.ccw(t))
    except ValueError:
        return False
    return abs(sum(abs(MG.area(list(x))) for x in tri) - abs(MG.area(t))) < 1.0


def clean(pts, protect=frozenset(), eps=0.08):
    """Drop duplicate and (nearly) collinear vertices (they stall the ear clipper), except protected ones."""
    pts = [tuple(q) for q in pts]
    changed = True
    while changed and len(pts) > 3:
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            if b in protect:
                continue
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            cr = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if b == a or L < 1e-9 or cr / L < eps:
                del pts[i]
                changed = True
                break
    return pts


def mesh_piece(g, avoid=None):
    """A simple, ear-clippable vertex list (CCW, 0.1 rounded) for an island polygon, or None.  avoid: geometry
    the piece must not overlap (simplification can bulge into a neighbour)."""
    base = Polygon(g.exterior)
    variants = [(base, t) for t in (3.0, 4.0, 6.0, 9.0, 14.0)]
    variants += [(base.buffer(-e).buffer(e - 0.5), t) for e in (3.0, 6.0) for t in (3.0, 6.0)]   # pixel-thin necks
    for src, tol in variants:
        if src.is_empty:
            continue
        src = max(src.geoms, key=lambda r: r.area) if hasattr(src, 'geoms') else src
        q = Polygon(src.exterior).simplify(tol, preserve_topology=True).buffer(0)
        if avoid is not None and not q.is_empty:
            q = q.difference(avoid).buffer(0)
        if q.is_empty:
            return None
        q = max(q.geoms, key=lambda r: r.area) if hasattr(q, 'geoms') else q
        pts = clean([(round(x, 1), round(z, 1)) for x, z in q.exterior.coords[:-1]])
        if not Polygon(pts).exterior.is_ccw:
            pts = pts[::-1]
        if meshable(pts) and (avoid is None or Polygon(pts).intersection(avoid).area < 1.0):
            return pts
    # small awkward islands (pixel-thin necks): their convex hull, if that stays clear of everything else
    q = g.convex_hull
    if avoid is not None:
        q = q.difference(avoid).buffer(0)
    if q.geom_type == 'Polygon' and q.area < 3.0 * g.area:
        pts = clean([(round(x, 1), round(z, 1)) for x, z in q.exterior.coords[:-1]])
        if not Polygon(pts).exterior.is_ccw:
            pts = pts[::-1]
        if meshable(pts) and (avoid is None or Polygon(pts).intersection(avoid).area < 1.0):
            return pts
    return None


NO_TRIM = {'najd', 'kandahar', 'kabul', 'timbuktu', 'baluch', 'hejaz',   # design.py rewrites runs of these
           'kokand', 'senegal', 'segu'}                                     # (2026-10-23; not design.STYLED_JOBS)
TRIM_MIN = 800.0                                                  # world units2 of open water to bother


def land_full():
    """Full-resolution land mask (cached in build/islands/land_full.npy; --fresh rebuilds it)."""
    fn = os.path.join(OUT, 'land_full.npy')
    if os.path.exists(fn) and '--fresh' not in sys.argv:
        return np.unpackbits(np.load(fn), axis=1)[:, :NCOL * TS].astype(bool)
    land = np.zeros((NROW * TS, NCOL * TS), bool)
    for r in range(NROW):
        for c in range(NCOL):
            t = np.asarray(Image.open(tile_src(c, r)).convert('RGB')).astype(np.float32)
            land[r * TS:(r + 1) * TS, c * TS:(c + 1) * TS] = ~DF.sea_class(t)
    np.save(fn, np.packbits(land, axis=1))
    return land


def trim_provinces(land, mesh):
    """Cut the parts of each world province polygon that lie over open water (more than ~3 px off the painted
    coast at half resolution) and away from every other province (shared borders stay identical).  Parts of a
    province that the cut separates become extension pieces of its mesh.  Port provinces are checked so the quay
    keeps a coast facing its sea zone.  Writes build/world_provinces.json and build/oldarea/world_provinces_fixed.json
    (idempotent).  Returns ({mesh: [pieces]}, report rows, provinces)."""
    import meshgen as MG
    wf = os.path.join(BUILD, 'world_provinces.json')
    W = json.load(open(wf, encoding='utf8'))
    E = remove_added(json.load(open(os.path.join(BUILD, 'extend', 'extensions.json'), encoding='utf8')))
    P_old = json.load(open(os.path.join(BUILD, 'oldarea', 'provinces.json')))
    others_all = {('w', k): Polygon(v['poly']).buffer(0) for k, v in W.items()}
    for k, v in E.items():
        for i, pl in enumerate(v):
            others_all[('e', k, i)] = Polygon(pl).buffer(0)
    for k, v in P_old.items():
        others_all[('o', k)] = Polygon(v).buffer(0)
    L = geo.land_polys()
    for n, G in geo.original_polys().items():
        if G.intersection(L).area > 0.5 * G.area:
            others_all[('g', n)] = G
    keys_all = list(others_all)
    tree = STRtree([others_all[k] for k in keys_all])
    land = land_full()                                              # trimming works at full resolution
    landd = ndimage.binary_dilation(land, iterations=2)
    w2px, Fz = C.w2p, 1
    try:
        import ports as PT
        newports = PT.NEW_PORTS
    except Exception:
        newports = {}
    S = json.load(open(os.path.join(BUILD, 'sea', 'sea_zones.json'), encoding='utf8'))
    port_zone = {k: S[z]['poly'] for k, (z, _) in newports.items() if z in S}
    extra, rows = {}, []
    res_w, res_h = C.TILE_W / TS, C.TILE_H / TS
    for key in sorted(W):
        if key in NO_TRIM:
            continue
        poly = [tuple(q) for q in W[key]['poly']]
        P = Polygon(poly)
        x0, z0, x1, z1 = P.bounds
        a, b = w2px(x0, z1); c, d = w2px(x1, z0)
        a, b = max(0, int(a) - 24), max(0, int(b) - 24)
        c, d = min(land.shape[1], int(c) + 25), min(land.shape[0], int(d) + 25)
        ww, hh = c - a, d - b

        def ras(geoms):
            m = Image.new('L', (ww, hh), 0); dr = ImageDraw.Draw(m)
            for g in geoms:
                for gg in (g.geoms if hasattr(g, 'geoms') else [g]):
                    if gg.geom_type == 'Polygon' and not gg.is_empty:
                        dr.polygon([(w2px(x, z)[0] - a, w2px(x, z)[1] - b) for x, z in gg.exterior.coords], fill=255)
            return np.asarray(m) > 0
        m = ras([P])
        near = [others_all[keys_all[i]] for i in tree.query(P.buffer(200.0)) if keys_all[i] != ('w', key)]
        nearm = ndimage.binary_dilation(ras(near), iterations=12) if near else np.zeros_like(m)
        rem = m & ~landd[b:d, a:c] & ~nearm
        rem = ndimage.binary_opening(rem, iterations=1)
        lab, n = ndimage.label(rem)
        if not n:
            continue
        sizes = ndimage.sum(rem, lab, range(1, n + 1)) * res_w * res_h
        big = [i + 1 for i, sz in enumerate(sizes) if sz >= TRIM_MIN]
        if not big:
            continue
        rings = geo._trace_boundaries(np.isin(lab, big))
        R0 = unary_union([Polygon([C.p2w(x + a, y + b) for x, y in r]).buffer(0) for r in rings if len(r) > 3])
        nearU = unary_union(near).buffer(40.0) if near else None
        protect = frozenset(poly)
        for tol in (3.0, 6.0, 10.0, 16.0):
            R = R0.buffer(6.0).simplify(tol).intersection(P)
            if nearU is not None:
                R = R.difference(nearU)
            P2 = P.difference(R)
            parts = sorted([g for g in (P2.geoms if hasattr(P2, 'geoms') else [P2]) if g.geom_type == 'Polygon'], key=lambda g: -g.area)
            main_ = parts[0]
            newpoly = clean(list(main_.exterior.coords)[:-1], protect)
            if Polygon(newpoly).exterior.is_ccw != P.exterior.is_ccw:
                newpoly = newpoly[::-1]
            ok = meshable(newpoly)
            for g in near:
                l0 = P.boundary.intersection(g.buffer(1.0)).length
                l1 = Polygon(newpoly).boundary.intersection(g.buffer(1.0)).length
                if abs(l0 - l1) > 2.0:
                    ok = False
            if key in port_zone:
                zp = port_zone[key]
                dmin = lambda pp: min(min((q[0] - s_[0]) ** 2 + (q[1] - s_[1]) ** 2 for s_ in zp[::2]) for q in pp) ** 0.5
                if dmin(newpoly) > dmin(poly) + 250.0:
                    ok = False
            if ok:
                break
        removed = P.area - Polygon(newpoly).area - sum(g.area for g in parts[1:])
        if ok and removed < TRIM_MIN * 0.5:
            continue                                                 # (cleaning gave the notch back: nothing to do)
        if not ok:
            rows.append((key, 'SKIPPED (check failed)', round(removed), 0))
            continue
        W[key]['poly'] = [list(q) for q in newpoly]
        nsplit = 0
        for g in parts[1:]:
            if g.area >= MIN_AREA * 0.5:
                pts = mesh_piece(g)
                if pts is not None:
                    extra.setdefault(mesh[key], []).append([list(q) for q in pts])
                    nsplit += 1
        rows.append((key, 'trimmed', round(removed), nsplit))
    if not DRY:
        json.dump(W, open(wf, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
        f2 = os.path.join(BUILD, 'oldarea', 'world_provinces_fixed.json')
        if os.path.exists(f2):
            W2 = json.load(open(f2, encoding='utf8'))
            for k in W2:
                if k in W and k not in NO_TRIM:
                    W2[k]['poly'] = W[k]['poly']
            json.dump(W2, open(f2, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
        # render_borders.py erases the painted borders of provinces whose polygon differs from this pre-design
        # snapshot: keep the trimmed provinces in step so only design.py's moved borders count as moved
        f3 = os.path.join(BUILD, 'oldarea', 'world_provinces_orig.json')
        if os.path.exists(f3):
            W3 = json.load(open(f3, encoding='utf8'))
            for k in W3:
                if k in W and k not in NO_TRIM:
                    W3[k]['poly'] = W[k]['poly']
            json.dump(W3, open(f3, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    else:
        json.dump(W, open(os.path.join(OUT, 'world_provinces_dry.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    return extra, rows, W


def main():
    os.makedirs(OUT, exist_ok=True)
    mesh = mesh_names()
    fl0 = os.path.join(OUT, 'land_half.npy')
    if os.path.exists(fl0) and '--fresh' not in sys.argv:
        land0 = np.load(fl0)
    else:
        land0, img0 = land_mask()
        np.save(fl0, land0); Image.fromarray(img0).save(os.path.join(OUT, 'art_half.png'))
    trim_extra, trim_rows, Wt = trim_provinces(land0, mesh)
    tr = [r for r in trim_rows if r[1] == 'trimmed']
    print('trimmed %d provinces, %.0f units2 of open water removed, %d split-off parts, %d skipped'
          % (len(tr), sum(r[2] for r in tr), sum(r[3] for r in tr), len(trim_rows) - len(tr)))
    W, E, prov, pieces, old, S = load_owned(strip_added=True)
    if DRY:
        W = Wt
        prov = {k: Polygon(v['poly']).buffer(0) for k, v in W.items()}
    for k, v in trim_extra.items():
        pieces += [(k, Polygon(pl).buffer(0)) for pl in v]
    land, img = land0, np.asarray(Image.open(os.path.join(OUT, 'art_half.png')))   # (pass --fresh after new tiles)
    shape = land.shape
    owned_geoms = list(prov.values()) + [g for _, g in pieces] + old
    owned = raster(owned_geoms, shape)
    oldrect = raster([box(OLD[0], OLD[2], OLD[1], OLD[3])], shape)
    unc = land & ~owned & ~oldrect
    unc = ndimage.binary_opening(unc, iterations=2)          # coastal slivers of the coarse provinces go
    lab, n = ndimage.label(unc)
    px_area = (C.TILE_W / TS * F) * (C.TILE_H / TS * F)
    sizes = ndimage.sum(unc, lab, range(1, n + 1)) * px_area
    keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_AREA]
    print('uncovered land components: %d, of which %d >= %.0f units2' % (n, len(keep), MIN_AREA))
    # drawings in the sea (ships) are 'not blue' too: an island is warm (parchment, or all brown coast rim when
    # small); a ship is grey / black line work over blue water
    imf = img.astype(np.float32)
    lum = imf.mean(-1)
    warm = (imf[..., 0] > imf[..., 2] + 20) & (lum > 70)              # parchment or the brown coast rim
    pf = ndimage.mean(warm, lab, keep)
    drop = [k for k, f in zip(keep, pf) if f < 0.40]
    for k in drop:
        ys, xs = np.nonzero(lab == k)
        print('  not an island (drawing in the sea): at world %s, warm %.2f' % ([round(v) for v in px2w(xs.mean(), ys.mean())], pf[keep.index(k)]))
    keep = [k for k in keep if k not in drop]
    U = trace(np.isin(lab, keep))
    comps = [g for g in (U.geoms if hasattr(U, 'geoms') else [U]) if g.area >= MIN_AREA * 0.5]
    owned_u = unary_union(owned_geoms).buffer(0)
    cands = candidates(W, E, prov, mesh)
    names = list(cands)
    tree = STRtree([cands[k] for k in names])
    world_mesh = set(mesh[k] for k in prov)
    added = {}
    report = []
    unowned = []
    skipped = 0
    avoid_u = owned_u.buffer(0.5)
    for g in comps:
        g = g.buffer(0).simplify(3.0, preserve_topology=True)
        g = Polygon(g.exterior) if g.geom_type == 'Polygon' else max(g.geoms, key=lambda q: q.area)
        g = Polygon(g.exterior).difference(owned_u.buffer(0.3))
        parts = [q for q in (g.geoms if hasattr(g, 'geoms') else [g]) if q.geom_type == 'Polygon' and q.area >= MIN_AREA * 0.5]
        for q in parts:
            q = Polygon(q.exterior)
            c = q.representative_point()
            touch = []
            for i in tree.query(q.buffer(25.0)):
                k = names[i]
                L = q.boundary.intersection(cands[k].buffer(25.0)).length
                if L > 1.0:
                    touch.append((L, k))
            inarc = ARCTIC[0] <= c.x <= ARCTIC[1] and ARCTIC[2] <= c.y <= ARCTIC[3]
            if touch and inarc:
                skipped += 1                                        # the old-area coast inset, not an island
                continue
            jobs = []
            rule = next((k for (x0, x1, z0, z1), k in RULES if x0 <= c.x <= x1 and z0 <= c.y <= z1), False)
            excl = next((why for (x0, x1, z0, z1), why in EXCLUDE if x0 <= c.x <= x1 and z0 <= c.y <= z1), None)
            if excl:
                unowned.append((round(q.area), [round(v) for v in c.coords[0]], excl, 0))
                continue
            if rule is not False and not (rule is None and touch):
                key = mesh[rule] if rule else mesh[min(PHILIPPINES, key=lambda kk: prov[kk].distance(q))]
                jobs = [(key, q)]
                how = 'rule'
            elif touch:
                big = sorted([t for t in touch if t[0] >= 150.0], reverse=True)
                if len(big) >= 2:
                    jobs = split_by_nearest(q, cands, [k for _, k in big])
                else:
                    jobs = [(max(touch)[1], q)]
                how = 'touch'
            else:
                key = names[tree.nearest(q)]
                d = cands[key].distance(q)
                if d > MAX_DIST:
                    unowned.append((round(q.area), [round(v) for v in c.coords[0]], key, round(d)))
                    continue
                jobs = [(key, q)]
                how = 'near %d' % round(d)
            for key, qq in jobs:
                qq = Polygon(qq.exterior) if qq.geom_type == 'Polygon' else max(qq.geoms, key=lambda r: r.area)
                pts = mesh_piece(qq, avoid_u)
                if pts is None:
                    unowned.append((round(qq.area), [round(v) for v in c.coords[0]], 'not meshable', 0))
                    continue
                if Polygon(pts).area < MIN_AREA * 0.5:
                    continue
                added.setdefault(key, []).append([list(p) for p in pts])
                report.append((key, round(Polygon(pts).area), [round(v) for v in Polygon(pts).representative_point().coords[0]], how))
    print('skipped %d coastal bands of the old-area style Arctic pieces' % skipped)
    # final overlap check between the new pieces and everything else
    newg = [(k, Polygon(p)) for k, v in added.items() for p in v]
    bad = 0
    for i, (k, g) in enumerate(newg):
        if not g.is_valid:
            print('  INVALID piece', k); bad += 1
        if g.intersection(owned_u).area > 2.0:
            print('  piece %s overlaps provinces by %.0f' % (k, g.intersection(owned_u).area)); bad += 1
        for k2, g2 in newg[i + 1:]:
            if g.intersection(g2).area > 1.0:
                print('  pieces overlap', k, k2); bad += 1
    for k, v in trim_extra.items():
        added.setdefault(k, []).extend(v)
        for pl in v:
            report.append((k, round(Polygon(pl).area), [round(t) for t in Polygon(pl).representative_point().coords[0]], 'split off by trim'))
    E2 = dict(E)
    for k, v in added.items():
        E2[k] = E2.get(k, []) + v
    for fn in (os.path.join(BUILD, 'extend', 'extensions.json'), os.path.join(BUILD, 'oldarea', 'extensions_fixed.json')):
        if os.path.exists(fn) and not DRY:
            cur = json.load(open(fn, encoding='utf8'))
            cur = remove_added(cur)
            for k, v in added.items():
                cur[k] = cur.get(k, []) + v
            json.dump(cur, open(fn, 'w', encoding='utf8'), indent=0)
    json.dump(added, open(os.path.join(OUT, 'added_dry.json' if DRY else 'added.json'), 'w', encoding='utf8'), indent=0)
    by = {}
    for key, a, c, how in report:
        by.setdefault(key, [0, 0.0]); by[key][0] += 1; by[key][1] += a
    keyname = {v: k for k, v in mesh.items()}
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf8') as f:
        f.write('pieces added: %d, area %.0f units2, problems %d\n' % (len(report), sum(r[1] for r in report), bad))
        for key, (nn, a) in sorted(by.items(), key=lambda kv: -kv[1][1]):
            f.write('%-12s %-24s %3d pieces %9.0f units2\n' % (keyname.get(key, '(old area)'), key, nn, a))
        f.write('\nnot assigned (farther than %.0f from every province):\n' % MAX_DIST)
        for u in unowned:
            f.write('  area %s at %s, nearest %s at %s\n' % tuple(u))
        f.write('\ntrimmed provinces (key, status, open water removed units2, split-off parts):\n')
        for r in trim_rows:
            f.write('  %s\n' % (r,))
        f.write('\nall pieces:\n')
        for r in sorted(report):
            f.write('  %s\n' % (r,))
    print(open(os.path.join(OUT, 'report.txt'), encoding='utf8').read()[:3000])
    return added


DRY = '--dry' in sys.argv

if __name__ == '__main__':
    main()

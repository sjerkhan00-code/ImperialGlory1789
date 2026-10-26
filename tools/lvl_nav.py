"""Sector map (battle navmesh) builder for tools/lvl.py.

What the retail game needs (verified on all 56 original maps, 2026-10-21; loader FUN_0048e7e0):
  - sectors are CONVEX polygons that tile the map exactly ([1, size-1] squared), clockwise in (x, z)
    (negative shoelace area), ids 0..n-1 in file order;
  - every shared edge has exactly one link {secA, secB, i, j} with i -> j consecutive in secA's polygon;
    no T-junctions (a vertex of one sector never lies inside another sector's edge); collinear vertices are allowed;
  - sector 'a' = passable (the movement test is a != 0 AND type & troop mask; troops use mask 0xfffff, so 'a'
    decides), 'type' = one TT bit (speed / action modifiers FUN_0058fab0, footstep sounds), 'occl' = line-of-sight
    occlusion level (building walls 1), 'c' = steep-sector flag (median slope 14 deg vs 6), plane = (p1 one polygon
    vertex, p2 Newell normal of the 3D polygon), 'center' unused (0), 'b' + special = walk geometry (bridges).
  - construction modules list their interior sector ids (module['flanks'][k]['ids']): renumbering remaps them.
"""
import math

import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union, polygonize

# TT bits [V FUN_00490690]
TT = dict(ARIDO=0x1, ZONA_VERDE=0x2, CAMINO=0x4, NIEVE_NO_PROFUNDA=0x8, TERRENO_HELADO=0x10, BARRIZAL=0x20,
          NIEVE_PROFUNDA=0x40, TERRENO_CULTIVADO=0x80, TERRENO_ELEVADO=0x100, TRIGALES=0x200,
          RIO_POCO_PROFUNDO=0x400, RIO_PROFUNDO=0x800, BARRANCO=0x1000, PANTANO=0x2000, CIENAGA=0x4000,
          HIERBAS_ALTAS=0x8000, BOSQUE=0x10000, INTERIOR=0x20000, PASO_ESTRECHO=0x40000, OBSTACULO=0x80000)


# Generated sector coordinates are kept off round numbers. The engine's casilla grid (CMapaCasillas::init
# FUN_004d38d0, 75 x 75) looks up the sector of every casilla centre ((i + 0.5) * 1000 cm) with getSectorOwner
# (FUN_0048d4a0 -> ray-crossing test FUN_0058c000, which special-cases a point lying exactly on a horizontal edge);
# a centre on a shared edge belongs to no sector, the result is NULL and FUN_004d3010 crashes at 0x4d3017 (in-game,
# 2026-10-21: block-grid lines at 12500 / 37500 / 62500 cm). The 56 originals have no casilla centre on an edge.
OFFSET = np.array([37.371, 61.613])


def polys_of(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, 'geoms', []) if isinstance(g, Polygon) and g.area > 0]


def sector_polygons(sm):
    """{sector id: shapely Polygon (x, z)} of a decoded SECTORMAP."""
    P = sm['points']
    return {s['id']: Polygon([(P[i][0], P[i][2]) for i in s['poly']]) for s in sm['sectors']}


def _is_convex(pts, eps=1e-3):
    """Convex up to collinear vertices (|sin| of the turn < eps counts as straight)."""
    n = len(pts)
    sign = 0
    for k in range(n):
        a, b, c = pts[k - 1], pts[k], pts[(k + 1) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        l1 = math.hypot(b[0] - a[0], b[1] - a[1]); l2 = math.hypot(c[0] - b[0], c[1] - b[1])
        if l1 * l2 == 0 or abs(cr) < eps * l1 * l2:
            continue
        s = 1 if cr > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _merge_convex(tris):
    """Hertel-Mehlhorn: merge triangles (lists of vertex keys, ccw) across shared diagonals while convex."""
    polys = {i: list(t) for i, t in enumerate(tris)}
    coord = {}
    edge_owner = {}

    def edges(pid):
        p = polys[pid]
        return [(p[k], p[(k + 1) % len(p)]) for k in range(len(p))]
    for pid in polys:
        for e in edges(pid):
            edge_owner[e] = pid
    changed = True
    while changed:
        changed = False
        for e, pid in list(edge_owner.items()):
            if pid not in polys:
                continue
            a, b = e
            q = edge_owner.get((b, a))
            if q is None or q == pid or q not in polys:
                continue
            P, Q = polys[pid], polys[q]
            ia = P.index(a)
            ib = Q.index(b)
            # P: ... a b ...  ; Q: ... b a ... ; merged: P up to a, then Q from a+1 around to b (exclusive)...
            P_rot = P[ia + 1:] + P[:ia + 1]            # starts after a, ends with a  -> b ... a
            Q_rot = Q[ib + 1:] + Q[:ib + 1]            # starts after b, ends with b  -> a ... b
            merged = P_rot[:-1] + Q_rot[:-1]           # b..(before a) + a..(before b)
            if len(set(merged)) != len(merged):
                continue
            if not _is_convex([KEY2XY[k] for k in merged]):
                continue
            del polys[q]
            polys[pid] = merged
            for k in range(len(merged)):
                edge_owner[(merged[k], merged[(k + 1) % len(merged)])] = pid
            edge_owner.pop((a, b), None); edge_owner.pop((b, a), None)
            changed = True
    return list(polys.values())


KEY2XY = {}


def _key(x, y):
    k = (round(x, 2), round(y, 2))
    KEY2XY.setdefault(k, (float(k[0]), float(k[1])))
    return k


def convex_pieces(face):
    """Convex decomposition of a polygon (with holes) using only its own vertices (no Steiner points)."""
    face = shapely.normalize(face)
    if _is_convex(list(face.exterior.coords)[:-1]) and not face.interiors:
        ring = [_key(*c) for c in face.exterior.coords[:-1]]
        return [ring]
    tris = shapely.constrained_delaunay_triangles(face)
    out = []
    for t in tris.geoms:
        cs = list(t.exterior.coords)[:-1]
        if Polygon(cs).area < 1e-6:
            continue
        if shapely.is_ccw(t.exterior) is False:
            cs = cs[::-1]
        out.append([_key(*c) for c in cs])
    # triangles from CDT: make ccw consistently
    fixed = []
    for t in out:
        (x0, y0), (x1, y1), (x2, y2) = (KEY2XY[k] for k in t)
        if (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0) < 0:
            t = t[::-1]
        fixed.append(t)
    return _merge_convex(fixed)


def _ring_stats(ring):
    xy = [KEY2XY[k] for k in ring]
    n = len(xy)
    area = abs(0.5 * sum(xy[i][0] * xy[(i + 1) % n][1] - xy[(i + 1) % n][0] * xy[i][1] for i in range(n)))
    edge = min(math.hypot(xy[i][0] - xy[(i + 1) % n][0], xy[i][1] - xy[(i + 1) % n][1]) for i in range(n))
    return area, edge


def _merge_slivers(polys, attrs, min_area, min_edge, rounds=6):
    """Merge tiny or needle pieces into a neighbour across a shared edge when the union stays convex (same
    attributes preferred; otherwise the larger neighbour's attributes win). Pieces that cannot merge are kept."""
    polys, attrs = [list(p) for p in polys], list(attrs)
    for _ in range(rounds):
        owner = {}
        for pi, p in enumerate(polys):
            for k in range(len(p)):
                owner[(p[k], p[(k + 1) % len(p)])] = pi
        dead, changed = set(), False
        order = sorted(range(len(polys)), key=lambda i: _ring_stats(polys[i])[0])
        for pi in order:
            if pi in dead:
                continue
            area, edge = _ring_stats(polys[pi])
            if area >= min_area and edge >= min_edge:
                continue
            P = polys[pi]
            cands = []
            for k in range(len(P)):
                a, b = P[k], P[(k + 1) % len(P)]
                q = owner.get((b, a))
                if q is None or q in dead or q == pi:
                    continue
                Q = polys[q]
                ia, ib = P.index(a), Q.index(b)
                merged = (P[ia + 1:] + P[:ia + 1])[:-1] + (Q[ib + 1:] + Q[:ib + 1])[:-1]
                if len(set(merged)) != len(merged) or not _is_convex([KEY2XY[x] for x in merged]):
                    continue
                same = attrs[q] == attrs[pi]
                cands.append((not same, -_ring_stats(Q)[0], q, merged))
            if not cands:
                continue
            _, _, q, merged = min(cands, key=lambda c: (c[0], c[1]))
            polys[q] = merged                        # the neighbour keeps its attributes
            dead.add(pi)
            for k in range(len(merged)):
                owner[(merged[k], merged[(k + 1) % len(merged)])] = q
            changed = True
        polys = [p for i, p in enumerate(polys) if i not in dead]
        attrs = [a for i, a in enumerate(attrs) if i not in dead]
        if not changed:
            break
    return polys, attrs


def _fix_tjunctions(polys, tol=0.02):
    """Insert every vertex that lies inside another polygon's edge into that edge (collinear vertex), so that
    neighbouring sectors share whole edges (the link list needs identical endpoints)."""
    keys = sorted({k for p in polys for k in p})
    xy = np.array([KEY2XY[k] for k in keys])
    out = []
    for p in polys:
        ring = []
        for k in range(len(p)):
            a, b = p[k], p[(k + 1) % len(p)]
            ring.append(a)
            A, B = np.array(KEY2XY[a]), np.array(KEY2XY[b])
            d = B - A
            L2 = float(d @ d)
            if L2 == 0:
                continue
            lo, hi = np.minimum(A, B) - tol, np.maximum(A, B) + tol
            m = np.all((xy >= lo) & (xy <= hi), 1)
            if not m.any():
                continue
            cand = xy[m]
            t = ((cand - A) @ d) / L2
            dist = np.abs((cand[:, 0] - A[0]) * d[1] - (cand[:, 1] - A[1]) * d[0]) / math.sqrt(L2)
            sel = (t > 1e-9) & (t < 1 - 1e-9) & (dist < tol)
            if sel.any():
                ks = [keys[i] for i in np.nonzero(m)[0][sel]]
                ts = t[sel]
                for _, kk in sorted(zip(ts, ks)):
                    if kk != a and kk != b:
                        ring.append(kk)
        out.append(ring)
    return out


def build(size, regions, keep=None, block=None, height=None, attrs_default=None, min_area=1e-3, simplify=40.0,
          min_part=2e4, sliver_area=5000.0, sliver_edge=30.0):
    """Generate a SECTORMAP dict.

    size      map size in cm (square, origin 0)
    regions   [(shapely geometry, attrs)] painted in order (later wins); attrs = dict(type=TT bit, a=0/1,
              occl=0/1, c=0/1). Uncovered ground gets attrs_default (ZONA_VERDE, passable).
    keep      [(polygon coords [(x, z, y)...], sector dict)] sectors copied verbatim (building interiors):
              their polygons become holes; their ring may receive extra collinear vertices.
    block     optional max size of a generated piece (cm; the map is first cut into block squares). Default none:
              the originals have sectors up to 11 ha, and grid lines next to region vertices make slivers.
    simplify / min_part   region outline simplification (cm) and the smallest region part kept (cm2);
    sliver_area / sliver_edge   pieces smaller than this or with a shorter edge are merged into a neighbour
              (the 56 originals: smallest sector 0.32 m2, shortest edge 29 cm).
    height    f(x, z) -> terrain height (cm) for the point y.
    Returns (sectormap dict, {index in keep: new id}).
    """
    keep = keep or []
    attrs_default = attrs_default or dict(type=TT['ZONA_VERDE'], a=1, occl=0, c=0)
    dom = box(1, 1, size - 1, size - 1)                 # the originals tile [1, size - 1]
    keep_polys = [Polygon([(p[0], p[1]) for p in poly]) for poly, s in keep]
    holes = unary_union(keep_polys) if keep else Polygon()
    # flat partition: painted regions (input rounded to 1 cm; no precision model is attached, so the exact
    # building holes cut afterwards keep their coordinates), later wins
    def off(c):                                         # integer cm + a fixed fraction (see OFFSET); the map
        c = np.round(c)                                 # border (1 / size - 1) stays exact
        inner = (c > 1.5) & (c < size - 1.5)
        return np.where(inner, c + OFFSET[None, :], c)

    def rnd(g):
        return shapely.make_valid(shapely.transform(g, off))
    painted = []
    taken = Polygon()
    for geom, attrs in reversed(regions):
        g = rnd(geom.intersection(dom).simplify(simplify))
        g = g.difference(taken) if not taken.is_empty else g
        g = unary_union([p for p in polys_of(g) if p.area >= min_part])   # no slivers (originals: >= 0.32 m2)
        if not g.is_empty:
            painted.append((g, attrs))
            taken = unary_union([taken, g])
    rest = dom.difference(taken) if not taken.is_empty else dom
    painted.append((unary_union(polys_of(rest)), attrs_default))
    if not holes.is_empty:
        painted = [(g.difference(holes), a) for g, a in painted]
    # linework: region boundaries (incl. the hole rings) + block grid outside the holes
    lines = [dom.boundary]
    for g, _ in painted:
        for p in polys_of(g):
            lines.append(p.boundary)
    n = int(math.ceil(size / block)) if block else 1
    step = size / n
    grid = []
    for k in range(1, n):
        grid.append(LineString([(k * step + OFFSET[0], 1), (k * step + OFFSET[0], size - 1)]))
        grid.append(LineString([(1, k * step + OFFSET[1]), (size - 1, k * step + OFFSET[1])]))
    lines += [g.difference(holes) for g in grid] if not holes.is_empty else grid
    faces = list(polygonize(unary_union(lines)))
    out_polys, out_attrs, keep_new = [], [], {}
    for f in faces:
        if f.area < min_area:
            continue
        rp = f.representative_point()
        if not holes.is_empty and holes.contains(rp):
            continue
        attrs = next((a for g, a in painted if g.buffer(1e-3).contains(rp)), attrs_default)
        for piece in convex_pieces(f):
            out_polys.append(piece); out_attrs.append(('new', attrs))
    out_polys, out_attrs = _merge_slivers(out_polys, out_attrs, sliver_area, sliver_edge)
    for ki, (poly, s) in enumerate(keep):
        out_polys.append([_key(p[0], p[1]) for p in poly]); out_attrs.append(('keep', ki))
    out_polys = _fix_tjunctions(out_polys)
    # points, orientation (clockwise in x/z = negative shoelace), sectors
    pts, pidx = [], {}

    def pid(k):
        if k not in pidx:
            x, z = KEY2XY[k]
            y = float(height(x, z)) if height else 0.0
            pidx[k] = len(pts)
            pts.append([x, y, z])
        return pidx[k]
    kept_xyz = {}
    for poly, s in keep:
        for p in poly:
            kept_xyz[_key(p[0], p[1])] = p[2]
    sectors = []
    for ring, (kind, info) in zip(out_polys, out_attrs):
        xy = [KEY2XY[k] for k in ring]
        area = 0.5 * sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1]
                         for i in range(len(xy)))
        if area > 0:
            ring = ring[::-1]
        idx = [pid(k) for k in ring]
        for k in ring:                                # kept building points keep their own height
            if k in kept_xyz:
                pts[pidx[k]][1] = kept_xyz[k]
        if kind == 'keep':
            s = dict(keep[info][1])
            keep_new[info] = len(sectors)
        else:
            s = dict(a=info['a'], type=info['type'], b=0, special=None, c=info.get('c', 0),
                     center=[0.0, 0.0, 0.0], occl=info.get('occl', 0))
        s['id'] = len(sectors)
        s['poly'] = idx
        sectors.append(s)
    for s in sectors:                                  # plane: first vertex + Newell normal
        q = np.array([pts[i] for i in s['poly']], float)
        nrm = np.zeros(3)
        for i in range(len(q)):
            a, b = q[i], q[(i + 1) % len(q)]
            nrm[0] += (a[1] - b[1]) * (a[2] + b[2]); nrm[1] += (a[2] - b[2]) * (a[0] + b[0])
            nrm[2] += (a[0] - b[0]) * (a[1] + b[1])
        ln = np.linalg.norm(nrm)
        nrm = nrm / ln if ln > 0 else np.array([0.0, 1.0, 0.0])
        if s.get('special') is None and s['type'] != TT['INTERIOR']:
            s['p1'] = [float(v) for v in q[0]]
            s['p2'] = [float(v) for v in nrm]
            s['c'] = s.get('c', 0)
        if 'p1' not in s:
            s['p1'] = [float(v) for v in q[0]]
            s['p2'] = [float(v) for v in nrm]
    # links: each shared edge once, (i -> j) forward in secA
    owner = {}
    for s in sectors:
        q = s['poly']
        for k in range(len(q)):
            owner[(q[k], q[(k + 1) % len(q)])] = s['id']
    links = []
    for s in sectors:
        q = s['poly']
        for k in range(len(q)):
            i, j = q[k], q[(k + 1) % len(q)]
            b = owner.get((j, i))
            if b is not None and s['id'] < b:
                links.append([s['id'], b, i, j])
    return dict(points=pts, sectors=sectors, links=links), keep_new


def validate(sm, size, tol_area=1e-4):
    """Checks the invariants listed in the module doc. Returns a list of problems (empty = OK)."""
    probs = []
    P = sm['points']
    ids = [s['id'] for s in sm['sectors']]
    if ids != list(range(len(ids))):
        probs.append('ids not 0..n-1')
    tot = 0.0
    edges = {}
    for s in sm['sectors']:
        xy = [(P[i][0], P[i][2]) for i in s['poly']]
        if len(set(s['poly'])) != len(s['poly']) or len(xy) < 3:
            probs.append('sector %d degenerate' % s['id'])
            continue
        a = 0.5 * sum(xy[i][0] * xy[(i + 1) % len(xy)][1] - xy[(i + 1) % len(xy)][0] * xy[i][1] for i in range(len(xy)))
        if a >= 0:
            probs.append('sector %d not clockwise (area %.1f)' % (s['id'], a))
        if not _is_convex(xy):
            probs.append('sector %d not convex' % s['id'])
        tot += -a
        for k in range(len(s['poly'])):
            e = (s['poly'][k], s['poly'][(k + 1) % len(s['poly'])])
            edges[e] = s['id']
    if abs(tot - (size - 2) ** 2) > tol_area * size * size:
        probs.append('area %.0f != %.0f' % (tot, (size - 2) ** 2))
    # every edge either on the map border or matched by its reverse
    for (i, j), sid in edges.items():
        if (j, i) not in edges:
            x0, z0, x1, z1 = P[i][0], P[i][2], P[j][0], P[j][2]
            on_border = (abs(x0 - x1) < 1e-3 and (abs(x0) < 1.5 or abs(x0 - size) < 1.5)) or \
                        (abs(z0 - z1) < 1e-3 and (abs(z0) < 1.5 or abs(z0 - size) < 1.5))
            if not on_border:
                probs.append('open edge %d-%d in sector %d (T-junction?)' % (i, j, sid))
                if len(probs) > 20:
                    break
    nl = sum(1 for (i, j) in edges if (j, i) in edges) // 2
    if nl != len(sm['links']):
        probs.append('links %d != shared edges %d' % (len(sm['links']), nl))
    return probs


def build_graph(sm, n_regions=20, seed=1789, iters=25):
    """Battle-AI graph (GRAFOIA) from a sector map: k-means clusters of passable sectors (area weighted),
    polygon = convex hull of the cluster's sectors, neighbours = clusters joined by a passable link.
    Note [V, exe scan 2026-10-21]: the retail exe only loads, debug-draws (FUN_00497f00 behind DAT_009157fc) and
    frees this graph (vector DAT_00915808, no other reader), so it does not steer the AI; it is kept consistent
    for completeness."""
    from shapely.geometry import MultiPoint
    P = np.array(sm['points'])
    secs = [s for s in sm['sectors'] if s['a']]
    cen = np.array([P[s['poly']][:, [0, 2]].mean(0) for s in secs])
    area = np.array([Polygon(P[s['poly']][:, [0, 2]]).area for s in secs])
    rng = np.random.default_rng(seed)
    k = min(n_regions, len(secs))
    C = cen[rng.choice(len(secs), k, replace=False, p=area / area.sum())]
    for _ in range(iters):
        lab = np.argmin(((cen[:, None, :] - C[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                C[j] = (cen[lab == j] * area[lab == j, None]).sum(0) / area[lab == j].sum()
    lab = np.argmin(((cen[:, None, :] - C[None]) ** 2).sum(-1), 1)
    sid_lab = {s['id']: int(l) for s, l in zip(secs, lab)}
    nb = {j: set() for j in range(k)}
    for a, b, i, j in sm['links']:
        if a in sid_lab and b in sid_lab and sid_lab[a] != sid_lab[b]:
            nb[sid_lab[a]].add(sid_lab[b]); nb[sid_lab[b]].add(sid_lab[a])
    used = sorted(set(lab.tolist()))
    remap = {j: i for i, j in enumerate(used)}
    nodes = []
    for j in used:
        pts = np.concatenate([P[s['poly']][:, [0, 2]] for s, l in zip(secs, lab) if l == j])
        hull = MultiPoint([tuple(p) for p in pts]).convex_hull
        c = np.array(hull.centroid.coords[0])
        ring = [tuple(c + 0.94 * (np.array(q) - c)) for q in list(hull.exterior.coords)[:-1]]
        ring = ring[::-1] if Polygon(ring).exterior.is_ccw else ring
        nodes.append(dict(id=remap[j], kind=1, poly=[[float(x), float(z)] for x, z in ring],
                          nb=sorted(remap[n] for n in nb[j])))
    return dict(head=1, nodes=nodes)

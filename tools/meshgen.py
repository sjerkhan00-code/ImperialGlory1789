"""Build campaign-map province meshes and fog points from a world-space polygon.

Map V3D mesh block (both MapaGestion.V3D and MapaGestionVolumenes.V3D):
  40-byte header {0x2000, size, 16 zero bytes..., 0x2000, ?, mesh index}, STR name, STR parent,
  body: 3 x 4x4 matrix (translation in row 4 of matrices 2 and 3), 16 zero bytes, bbox 6f (local),
  sphere 4f (local centre + radius), u32 0,
  {0x2100, 20+28n, 514, 28, n} n x (x, y, z, u, v, u2, v2)   local coords
  {0x2300, 16+2m, 2, m} m x u16                              absolute vertex indices
  {0x2400, 12+20k, k} k x (vstart, vcount, istart, ntris, tile)   one sub-mesh per map tile
Tile = r*4 + c with r counted from the south; texture coordinates are linear in world position.
"""
import math, struct
from igmod import ws, V3D, v3d_objects, v3d_root

KU, CU = 0.00018540, 0.0929299          # u = KU*x + CU - col
KV, CV = 0.00026150, 0.51535            # v = CV + row - KV*z
K2U, C2U = 0.00037118, 0.17999          # detail texture
K2V, C2V = 0.00052348, 0.04110          # v2 = C2V - K2V*z
COLS = [(c - CU) / KU for c in range(5)]            # tile column edges in world x
ROWS = [(CV + r - 1) / KV for r in range(5)]        # tile row edges in world z (south first)


def area(poly):
    return sum(poly[k - 1][0] * poly[k][1] - poly[k][0] * poly[k - 1][1] for k in range(len(poly))) / 2


def ccw(poly):
    return poly if area(poly) > 0 else poly[::-1]


def _seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def is_simple(poly):
    n = len(poly)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def triangulate(poly):
    """Ear clipping; poly CCW, simple. Returns triangles as point triples."""
    pts = list(poly)
    tris = []
    def inside_tri(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
    guard = 0
    while len(pts) > 3 and guard < 10000:
        guard += 1
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 1e-9:
                continue
            if any(inside_tri(p, a, b, c) for p in pts if p not in (a, b, c)):
                continue
            tris.append((a, b, c))
            del pts[i]
            break
        else:
            raise ValueError('triangulation failed (polygon not simple?)')
    tris.append(tuple(pts))
    return tris


def clip(poly, axis, value, keep_greater):
    out = []
    for k in range(len(poly)):
        p, q = poly[k - 1], poly[k]
        pin = (p[axis] >= value) if keep_greater else (p[axis] <= value)
        qin = (q[axis] >= value) if keep_greater else (q[axis] <= value)
        if qin:
            if not pin:
                t = (value - p[axis]) / (q[axis] - p[axis])
                out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
            out.append(q)
        elif pin:
            t = (value - p[axis]) / (q[axis] - p[axis])
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


# material index for each map tile (r from the south, c from the west); the original 4 x 4 tiles are r*4+c.
# make_map extends this with the tiles of the bigger map (rows below 0, columns above 3).
TILE_MAT = {(r, c): r * 4 + c for r in range(4) for c in range(4)}
TILE_W, TILE_H = COLS[1] - COLS[0], ROWS[1] - ROWS[0]


def tiles_of(tris):
    """Split triangles at tile edges -> {(r, c): [triangles]}."""
    res = {}
    for tri in tris:
        xs = [p[0] for p in tri]; zs = [p[1] for p in tri]
        e = 1e-6
        c0 = int(math.floor((min(xs) - COLS[0]) / TILE_W + e)); c1 = int(math.floor((max(xs) - COLS[0]) / TILE_W - e))
        r0 = int(math.floor((min(zs) - ROWS[0]) / TILE_H + e)); r1 = int(math.floor((max(zs) - ROWS[0]) / TILE_H - e))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                assert (r, c) in TILE_MAT, ('no map tile', r, c)
                x0 = COLS[0] + c * TILE_W; z0 = ROWS[0] + r * TILE_H
                p = list(tri)
                for axis, val, g in ((0, x0, True), (0, x0 + TILE_W, False), (1, z0, True), (1, z0 + TILE_H, False)):
                    p = clip(p, axis, val, g)
                    if len(p) < 3:
                        break
                if len(p) >= 3 and abs(area(p)) > 1e-3:
                    for k in range(1, len(p) - 1):
                        res.setdefault((r, c), []).append((p[0], p[k], p[k + 1]))
    return res


def build_mesh(template_blob, name, poly, y, index):
    """Return a new mesh block for MapaGestion(.Volumenes).V3D, cloned from a template block."""
    poly = ccw(poly)
    tris = triangulate(poly)
    pieces = tiles_of(tris)
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    tx, tz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    verts, idx, subs = [], [], []
    for (r, c) in sorted(pieces):
        tile = TILE_MAT[(r, c)]
        vstart, istart, local = len(verts), len(idx), {}
        for tri in pieces[(r, c)]:
            # clockwise seen from above (x, z), like every original province: the engine culls back faces
            for (x, z) in tri[::-1]:
                key = (round(x, 3), round(z, 3))
                if key not in local:
                    local[key] = len(verts)
                    verts.append((x - tx, 0.0, z - tz, KU * x + CU - c, CV + r - KV * z, K2U * x + C2U, C2V - K2V * z))
                idx.append(local[key])
        subs.append((vstart, len(verts) - vstart, istart, (len(idx) - istart) // 3, tile))
    f = V3D.mesh_fields(template_blob)
    head = bytearray(template_blob[:40])
    body = bytearray(template_blob[f['body']:f['vh']])               # matrices .. u32 before vertices
    for mo in (64, 128):
        struct.pack_into('<3f', body, mo + 48, tx, y, tz)
    lx = [v[0] for v in verts]; lz = [v[2] for v in verts]
    struct.pack_into('<6f', body, 208, min(lx), 0.0, min(lz), max(lx), 0.0, max(lz))
    cx, cz = (min(lx) + max(lx)) / 2, (min(lz) + max(lz)) / 2
    rad = max(math.hypot(v[0] - cx, v[2] - cz) for v in verts)
    struct.pack_into('<4f', body, 232, cx, 0.0, cz, rad)
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(verts), 514, 28, len(verts)) + b''.join(struct.pack('<7f', *v) for v in verts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(idx), 2, len(idx)) + struct.pack('<%dH' % len(idx), *idx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20 * len(subs), len(subs)) + b''.join(struct.pack('<5I', *s) for s in subs)
    blob = bytearray(head + ws(name) + ws('MapaGestion') + body + vsec + isec + tsec)
    struct.pack_into('<I', blob, 4, len(blob))
    struct.pack_into('<I', blob, 36, index)
    return bytes(blob), len(verts), len(idx) // 3


def add_mesh(v, template_name, name, poly, y):
    st, en, _ = v.block(template_name)
    blob, nv, nt = build_mesh(bytes(v.d[st:en]), name, poly, y, len(v.blocks))
    v.d += blob
    v.blocks.append((len(v.d) - len(blob), len(v.d), name))
    for off, delta in ((V3D.H_A, nv), (V3D.H_VERTS, nv), (V3D.H_TRIS, nt), (V3D.H_MESHES, 1), (V3D.H_OBJS, 1), (v3d_root(v.d) + 12, 1)):
        struct.pack_into('<I', v.d, off, struct.unpack_from('<I', v.d, off)[0] + delta)
    return nv, nt


def point_in(poly, x, z):
    c = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[i - 1]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def interior_points(poly, spacing, margin=150.0):
    """Grid points inside the polygon, at least `margin` from its edges."""
    def edge_dist(x, z):
        best = 1e18
        for k in range(len(poly)):
            (ax, az), (bx, bz) = poly[k - 1], poly[k]
            dx, dz = bx - ax, bz - az
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz or 1)))
            best = min(best, math.hypot(x - ax - t * dx, z - az - t * dz))
        return best
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    out = []
    z = min(zs) + spacing / 2
    while z < max(zs):
        x = min(xs) + spacing / 2
        while x < max(xs):
            if point_in(poly, x, z) and edge_dist(x, z) >= margin:
                out.append((x, z))
            x += spacing
        z += spacing
    return out


def edge_distance(poly, x, z):
    best = 1e18
    for k in range(len(poly)):
        (ax, az), (bx, bz) = poly[k - 1], poly[k]
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz or 1)))
        best = min(best, math.hypot(x - ax - t * dx, z - az - t * dz))
    return best


def centre_point(poly):
    """The point deepest inside the polygon (furthest from every edge): armies, capitals and markers go here."""
    for spacing in (100, 60, 30):
        pts = interior_points(poly, spacing, 0)
        if pts:
            return max(pts, key=lambda p: edge_distance(poly, p[0], p[1]))
    return poly[0]


def second_point(poly, first, dist=450.0):
    """A second well-inside point about `dist` away from the first (for a second marker)."""
    pts = interior_points(poly, 80, 0) or [first]
    return max(pts, key=lambda p: min(edge_distance(poly, p[0], p[1]), 300.0) - abs(math.hypot(p[0] - first[0], p[1] - first[1]) - dist) * 0.5)


def clip_box(poly, box):
    """The part of a polygon inside the box (x0, x1, z0, z1); [] if none."""
    p = list(poly)
    for axis, val, g in ((0, box[0], True), (0, box[1], False), (1, box[2], True), (1, box[3], False)):
        p = clip(p, axis, val, g)
        if len(p) < 3:
            return []
    return p if abs(area(p)) > 1.0 else []


# Fog of war (Niebla.sb, FUN_00432510): every point of a known province adds 1 to a fog texel closer than D1 and a
# linear ramp to 0 at D2; the texel is clear at SAT = 2. The original points are about 500 units apart.
FOG_D1, FOG_D2 = 200.0, 600.0
FOG_CAP = 120          # points per mesh at most (the original Moscu has 123); every province clones the whole model,
                       # so the TOTAL count costs memory and load time, not the count of one mesh


def fog_sum(pts, x, z, d1=FOG_D1, d2=FOG_D2):
    """Niebla.sb contribution of the fog points pts at (x, z)."""
    s = 0.0
    for px, pz in pts:
        r = math.hypot(px - x, pz - z)
        s += 1.0 if r < d1 else (1.0 - (r - d1) / (d2 - d1) if r < d2 else 0.0)
    return s


def _lloyd(np, S, P, n):
    """n points relaxed over the samples S (k x 2) of shape P: farthest-point start from the sample nearest the
    centroid, Lloyd iterations (centroidal Voronoi), then each centre snapped to the nearest sample of its own cell,
    so every point lies inside the shape even for crescents. Deterministic."""
    c = np.array(P.centroid.coords[0])
    idx = [int(np.argmin(((S - c) ** 2).sum(1)))]
    d = ((S - S[idx[0]]) ** 2).sum(1)
    for _ in range(n - 1):
        k = int(np.argmax(d)); idx.append(k)
        d = np.minimum(d, ((S - S[k]) ** 2).sum(1))
    C = S[idx].astype(float)
    for _ in range(60):
        lab = np.argmin(((S[:, None, :] - C[None, :, :]) ** 2).sum(2), axis=1)
        cnt = np.bincount(lab, minlength=n)
        sx = np.bincount(lab, weights=S[:, 0], minlength=n); sz = np.bincount(lab, weights=S[:, 1], minlength=n)
        N = np.where(cnt[:, None] > 0, np.column_stack([sx, sz]) / np.maximum(cnt, 1)[:, None], C)
        moved = np.abs(N - C).max()
        C = N
        if moved < 0.5:
            break
    lab = np.argmin(((S[:, None, :] - C[None, :, :]) ** 2).sum(2), axis=1)
    out = []
    for j in range(n):
        m = S[lab == j]
        if len(m):
            k = int(np.argmin(((m - C[j]) ** 2).sum(1)))
            out.append((float(m[k][0]), float(m[k][1])))
    return out


def fog_positions(poly, spacing, box=None, exclude=None, cap=FOG_CAP):
    """Evenly spread fog points inside a polygon [(x, z)] (2026-10-23, replaces the grid of interior_points with a
    150-unit margin, which left 50 mid-sized provinces such as Zhili, Natal, Nepal with the 2-point fallback and
    the fog mostly uncleared): start with max(2, area / spacing^2) points, relax them (_lloyd), and add points
    while less than 90 % of the area gets at least half the clearing (sum >= 1; thin strips, gulfs, straits).
    Only the part on the fog plane box (x0, x1, z0, z1) and outside the polygons `exclude` counts. [] if none."""
    import numpy as np
    import shapely
    from shapely.geometry import Polygon as _P
    from shapely.ops import unary_union as _U
    P = (poly if hasattr(poly, 'geom_type') else _P(poly)).buffer(0)     # a ring [(x, z)] or a shapely shape
    if box is not None:
        P = P.intersection(shapely.box(box[0], box[2], box[1], box[3]))
    if exclude and not P.is_empty:
        b = P.bounds
        hit = [q for q in exclude if min(x for x, z in q) < b[2] and max(x for x, z in q) > b[0]
               and min(z for x, z in q) < b[3] and max(z for x, z in q) > b[1]]
        if hit:
            P = P.difference(_U([_P(q).buffer(0) for q in hit]))
    if P.is_empty or P.area < 1.0:
        return []
    n = min(cap, max(2, int(round(P.area / spacing ** 2))))
    step = math.sqrt(P.area / (40.0 * n))                 # about 40 samples per point
    x0, z0, x1, z1 = P.bounds
    shapely.prepare(P)
    for _ in range(5):                                   # thin slivers: refine until every point has samples
        X, Z = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(z0 + step / 2, z1, step))
        X, Z = X.ravel(), Z.ravel()
        ok = shapely.contains_xy(P, X, Z)
        S = np.column_stack([X[ok], Z[ok]])
        if len(S) >= 4 * n:
            break
        step /= 2
    if len(S) < n:
        q = P.representative_point()
        return [(q.x, q.y)] * 2
    pts = []
    for _ in range(8):
        pts = _lloyd(np, S, P, n)
        if n >= min(cap, len(S)):
            break
        Q = np.array(pts)
        r = np.sqrt(((S[:, None, :] - Q[None, :, :]) ** 2).sum(2))
        if (np.clip((FOG_D2 - r) / (FOG_D2 - FOG_D1), 0.0, 1.0).sum(1) >= 1.0).mean() >= 0.9:
            break
        n = min(cap, len(S), n + max(1, n // 4))
    return pts


def fog_hole_points(d, box, spacing, far=350.0, min_far=1.0e5, opening=60.0):
    """Fog points for enclosed map areas no province mesh covers (2026-10-23: the Caspian Sea, the Bass Strait gap
    between the sea zones), where the fog never cleared because only Dummies of province meshes clear it.
    d = MapaGestion.V3D bytes. Holes touching the fog plane's edge (the unexplored rim: Arctic, White Sea, as in the
    original game) are left alone; strips thinner than 2 x opening (coastal gaps) are opened away; a hole needs at
    least min_far units2 farther than `far` from every fog point. Each point goes to the nearest mesh, so it clears
    together with that province or sea zone. -> sorted [(mesh name, [(x, z), ...])]."""
    import numpy as np
    import shapely
    from shapely.geometry import Polygon as _P, Point as _Pt
    from shapely.ops import unary_union as _U
    objs = v3d_objects(d)
    trans, tri_geo, tri_name = {}, [], []
    for o, cid, size, name, par in objs:
        if cid == 0x2000:
            blob = d[o:o + size]
            trans[name] = struct.unpack_from('<3f', blob, V3D.mesh_fields(blob)['body'] + 128 + 48)
            for t in mesh_triangles(blob):
                if abs(area(t)) > 1e-6:
                    tri_geo.append(_P(t)); tri_name.append(name)
    have = []
    for o, cid, size, name, par in objs:
        if cid == 0x5000 and par in trans:
            lx, _, lz = struct.unpack_from('<3f', d, dummy_body(d, o) + 128 + 48)
            have.append((trans[par][0] + lx, trans[par][2] + lz))
    have = np.array(have)
    B = shapely.box(box[0], box[2], box[1], box[3])
    H = B.difference(_U(tri_geo).buffer(1.0))
    tree = shapely.STRtree(tri_geo)
    out = {}
    for g in sorted(getattr(H, 'geoms', [H]), key=lambda g: g.bounds):
        if g.area < min_far or g.buffer(5.0).intersects(B.exterior):
            continue
        g = g.buffer(-opening).buffer(opening).intersection(g)
        for h in sorted(getattr(g, 'geoms', [g]), key=lambda h: h.bounds):
            if h.geom_type != 'Polygon' or h.area < min_far:
                continue
            x0, z0, x1, z1 = h.bounds
            X, Z = np.meshgrid(np.arange(x0 + 30.0, x1, 60.0), np.arange(z0 + 30.0, z1, 60.0))
            X, Z = X.ravel(), Z.ravel()
            ok = shapely.contains_xy(h, X, Z)
            X, Z = X[ok], Z[ok]
            nb = have[(have[:, 0] > x0 - far) & (have[:, 0] < x1 + far) & (have[:, 1] > z0 - far) & (have[:, 1] < z1 + far)]
            dmin = np.hypot(X[:, None] - nb[None, :, 0], Z[:, None] - nb[None, :, 1]).min(1) if len(nb) else np.full(len(X), 1e9)
            if (dmin > far).sum() * 3600.0 < min_far:
                continue
            for x, z in fog_positions(h, spacing):
                i = int(tree.query_nearest(_Pt(x, z))[0])
                out.setdefault(tri_name[i], []).append((x, z))
    return sorted(out.items())


def add_fog_points(v, template_parent, parent, poly, mesh_y, first_index, spacing=520.0, box=None, piece=False,
                   exclude=None, skip_covered=False, points=None):
    """Fog-of-war control points for a new province or an extension piece, cloned from a template Dummy.
    box = (x0, x1, z0, z1) of the fog plane (Niebla.V3D): points outside it clear no fog texel and are not made
    (2026-10-21, review V7: 209 such points at the map's rim). piece = an extension piece of a mesh that has its
    own points: a piece wholly outside the fog plane gets none; with skip_covered a speck (< 1/4 spacing^2) whose
    outline the mesh's points already give sum >= 1.5 gets none either. exclude = land polygons a sea zone is cut
    by later (no points on that land). Placement: fog_positions.
    The engine places a Dummy at parent mesh transform x Dummy matrix 3 (helper loader FUN_00471f30 sets matrix 3 as
    the local matrix, vtable 0x8b6800 +0x6c = local x parent world; the matrix-2 'world' copy is not used), so the
    local offset is taken from the PARENT MESH's translation (2026-10-23: it was the polygon's own bbox centre,
    which put every extension-piece point off by mesh centre - piece centre: Luzon 19 of 22 points off the island)."""
    d = bytes(v.d) + v.tail
    objs = v3d_objects(d)
    next_id = len(objs)
    o, cid, size, name, par = next(t for t in objs if t[1] == 0x5000 and t[4] == template_parent)
    tmpl = d[o:o + size]
    p = 20 + 2 + len(name) + 1 + 2 + len(par) + 1
    tbody = tmpl[p:]
    ox, oy, oz = struct.unpack_from('<3f', tbody, 64 + 48)
    ly = struct.unpack_from('<f', tbody, 128 + 52)[0]
    mo = next(t for t in objs if t[1] == 0x2000 and t[3] == parent)
    mb = d[mo[0]:mo[0] + mo[2]]
    tx, _, tz = struct.unpack_from('<3f', mb, V3D.mesh_fields(mb)['body'] + 128 + 48)
    if points is not None:                     # given positions (fog_hole_points): poly is not used
        poly, piece = [], True
    if piece and skip_covered and abs(area(poly)) < 0.25 * spacing ** 2:
        have = []
        for t in objs:
            if t[1] == 0x5000 and t[4] == parent:
                lx, _, lz = struct.unpack_from('<3f', d, dummy_body(d, t[0]) + 128 + 48)
                have.append((tx + lx, tz + lz))
        if have and all(fog_sum(have, x, z) >= 1.5 for x, z in poly):
            return 0
    pts = list(points) if points is not None else fog_positions(poly, spacing, box, exclude)
    if not pts and not piece:                  # wholly off the plane (only SCanaryIslands, x < 463): keeps 2 points
        pts = fog_positions(poly, 1e9, None, exclude, cap=2) or fog_positions(poly, 1e9, cap=2)
    for k, (x, z) in enumerate(pts):
        body = bytearray(tbody)
        wy = mesh_y + ly
        struct.pack_into('<3f', body, 128 + 48, x - tx, ly, z - tz)
        struct.pack_into('<3f', body, 64 + 48, x, wy, z)
        q = 192 + 2 + struct.unpack_from('<H', body, 192)[0] + 24
        wb = list(struct.unpack_from('<6f', body, q))
        dx, dz, dyy = x - ox, z - oz, wy - oy
        struct.pack_into('<6f', body, q, wb[0] + dx, wb[1] + dz, wb[2] + dyy, wb[3] + dx, wb[4] + dz, wb[5] + dyy)
        head = bytearray(tmpl[:20])
        struct.pack_into('<I', head, 16, next_id + k)
        new = head + ws('%s%d' % ('NieblaLago' if points is not None else 'Niebla', first_index + k)) + ws(parent) + body
        struct.pack_into('<I', new, 4, len(new))
        v.d += new
    for off in (V3D.H_OBJS, 86):
        struct.pack_into('<I', v.d, off, struct.unpack_from('<I', v.d, off)[0] + len(pts))
    return len(pts)


def _surface_level(verts):
    ys = sorted(v[1] for v in verts)
    return ys[len(ys) // 2] if ys else 0.0


def extend_mesh_bytes(d, name, polys):
    """Add polygon pieces (world x, z) to an existing province mesh of a V3D file (bytes) -> (bytes, dv, dt).
    New triangles are clockwise like the originals; uv as for new meshes (retile.rebuild_model recomputes them)."""
    from igmod import v3d_objects
    o, cid, size, nm, par = next(t for t in v3d_objects(d) if t[3] == name and t[1] == 0x2000)
    blob = bytearray(d[o:o + size])
    f = V3D.mesh_fields(bytes(blob))
    body, vh, nv, ih, ni = f['body'], f['vh'], f['nv'], f['ih'], f['ni']
    tx, ty, tz = struct.unpack_from('<3f', blob, body + 128 + 48)
    verts = [list(struct.unpack_from('<7f', blob, vh + 20 + 28 * k)) for k in range(nv)]
    idx = list(struct.unpack_from('<%dH' % ni, blob, ih + 16))
    th = ih + 16 + 2 * ni
    f3, s3, ns = struct.unpack_from('<3I', blob, th)
    subs = [list(struct.unpack_from('<5I', blob, th + 12 + 20 * k)) for k in range(ns)]
    tail = bytes(blob[th + s3:])
    # level of the province surface: the median, not the mean (Moscu's 2005 mesh dips to y -8 beyond the old map
    # edge; the mean put the whole carved mesh under the art planes -> pale, striped province)
    ly = _surface_level(verts)
    for poly in polys:
        pieces = tiles_of(triangulate(ccw([tuple(q) for q in poly])))
        for (r, c) in sorted(pieces):
            vstart, istart, local = len(verts), len(idx), {}
            for tri in pieces[(r, c)]:
                for (x, z) in tri[::-1]:
                    key = (round(x, 3), round(z, 3))
                    if key not in local:
                        local[key] = len(verts)
                        verts.append([x - tx, ly, z - tz, KU * x + CU - c, CV + r - KV * z, K2U * x + C2U, C2V - K2V * z])
                    idx.append(local[key])
            subs.append([vstart, len(verts) - vstart, istart, (len(idx) - istart) // 3, TILE_MAT[(r, c)]])
    assert len(verts) < 65536
    head = bytearray(blob[:vh])
    lx = [v[0] for v in verts]; lyy = [v[1] for v in verts]; lz = [v[2] for v in verts]
    struct.pack_into('<6f', head, body + 208, min(lx), min(lyy), min(lz), max(lx), max(lyy), max(lz))
    cx, cz = (min(lx) + max(lx)) / 2, (min(lz) + max(lz)) / 2
    struct.pack_into('<4f', head, body + 232, cx, ly, cz, max(math.hypot(v[0] - cx, v[2] - cz) for v in verts))
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(verts), 514, 28, len(verts)) + b''.join(struct.pack('<7f', *v) for v in verts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(idx), 2, len(idx)) + struct.pack('<%dH' % len(idx), *idx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20 * len(subs), len(subs)) + b''.join(struct.pack('<5I', *s) for s in subs)
    nb = bytearray(bytes(head) + vsec + isec + tsec + tail)
    struct.pack_into('<I', nb, 4, len(nb))
    out = bytearray(d[:o] + bytes(nb) + d[o + size:])
    dv, dt = len(verts) - nv, (len(idx) - ni) // 3
    for off, delta in ((V3D.H_A, dv), (V3D.H_VERTS, dv), (V3D.H_TRIS, dt)):
        struct.pack_into('<I', out, off, struct.unpack_from('<I', out, off)[0] + delta)
    return bytes(out), dv, dt


def _clip_half(poly, a, b, keep_left):
    """Clip a polygon [(x, z)] by the line a->b; keep the left side (cross > 0) or the right side."""
    out = []
    def side(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    for k in range(len(poly)):
        p, q = poly[k - 1], poly[k]
        sp, sq = side(p), side(q)
        pin = sp > 0 if keep_left else sp < 0
        qin = sq > 0 if keep_left else sq < 0
        if pin != qin and sp != sq:
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        if qin:
            out.append(q)
    return out


def _minus_triangle(piece, tri):
    """Convex polygon minus triangle -> list of convex polygons (same orientation as piece)."""
    a, b, c = tri
    if ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 0:
        a, b, c = a, c, b                                  # make the triangle counter-clockwise
    res, rest = [], piece
    for e0, e1 in ((a, b), (b, c), (c, a)):
        outside = _clip_half(rest, e0, e1, keep_left=False)   # right of a ccw edge = outside the triangle
        if len(outside) >= 3 and abs(area(outside)) > 1.0:
            res.append(outside)
        rest = _clip_half(rest, e0, e1, keep_left=True)
        if len(rest) < 3:
            break
    return res


def subtract_mesh_bytes(d, name, polys):
    """Remove the area of polygons (world x, z) from an existing province mesh; the rest keeps its winding.
    UVs are left to retile.rebuild_model (it re-splits and re-maps every triangle)."""
    from igmod import v3d_objects
    o, cid, size, nm, par = next(t for t in v3d_objects(d) if t[3] == name and t[1] == 0x2000)
    blob = bytearray(d[o:o + size])
    f = V3D.mesh_fields(bytes(blob))
    body, vh, nv, ih, ni = f['body'], f['vh'], f['nv'], f['ih'], f['ni']
    tx, ty, tz = struct.unpack_from('<3f', blob, body + 128 + 48)
    verts = [struct.unpack_from('<7f', blob, vh + 20 + 28 * k) for k in range(nv)]
    idx = struct.unpack_from('<%dH' % ni, blob, ih + 16)
    th = ih + 16 + 2 * ni
    f3, s3, ns = struct.unpack_from('<3I', blob, th)
    tail = bytes(blob[th + s3:])
    # level of the province surface: the median, not the mean (Moscu's 2005 mesh dips to y -8 beyond the old map
    # edge; the mean put the whole carved mesh under the art planes -> pale, striped province)
    ly = _surface_level(verts)
    cut = []
    for poly in polys:
        for t in triangulate(ccw([tuple(q) for q in poly])):
            cut.append((t, min(p[0] for p in t), max(p[0] for p in t), min(p[1] for p in t), max(p[1] for p in t)))
    out_tris = []
    for k in range(0, ni, 3):
        tri = [(verts[i][0] + tx, verts[i][2] + tz) for i in idx[k:k + 3]]
        pieces = [tri]
        bx0, bx1 = min(p[0] for p in tri), max(p[0] for p in tri)
        bz0, bz1 = min(p[1] for p in tri), max(p[1] for p in tri)
        for t, x0, x1, z0, z1 in cut:
            if x1 < bx0 or x0 > bx1 or z1 < bz0 or z0 > bz1:
                continue
            nxt = []
            for pc in pieces:
                nxt += _minus_triangle(pc, t)
            pieces = nxt
            if not pieces:
                break
        for pc in pieces:
            for j in range(1, len(pc) - 1):
                out_tris.append((pc[0], pc[j], pc[j + 1]))
    nverts, nidx, local = [], [], {}
    for tri in out_tris:
        for (x, z) in tri:
            key = (round(x, 3), round(z, 3))
            if key not in local:
                local[key] = len(nverts)
                nverts.append((x - tx, ly, z - tz, 0.0, 0.0, K2U * x + C2U, C2V - K2V * z))
            nidx.append(local[key])
    assert nverts and len(nverts) < 65536, name
    head = bytearray(blob[:vh])
    lx = [v[0] for v in nverts]; lz = [v[2] for v in nverts]
    struct.pack_into('<6f', head, body + 208, min(lx), ly, min(lz), max(lx), ly, max(lz))
    cx, cz = (min(lx) + max(lx)) / 2, (min(lz) + max(lz)) / 2
    struct.pack_into('<4f', head, body + 232, cx, ly, cz, max(math.hypot(v[0] - cx, v[2] - cz) for v in nverts))
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(nverts), 514, 28, len(nverts)) + b''.join(struct.pack('<7f', *v) for v in nverts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(nidx), 2, len(nidx)) + struct.pack('<%dH' % len(nidx), *nidx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20, 1) + struct.pack('<5I', 0, len(nverts), 0, len(nidx) // 3, 0)
    nb = bytearray(bytes(head) + vsec + isec + tsec + tail)
    struct.pack_into('<I', nb, 4, len(nb))
    res = bytearray(d[:o] + bytes(nb) + d[o + size:])
    dv, dt = len(nverts) - nv, len(nidx) // 3 - ni // 3
    for off, delta in ((V3D.H_A, dv), (V3D.H_VERTS, dv), (V3D.H_TRIS, dt)):
        struct.pack_into('<I', res, off, struct.unpack_from('<I', res, off)[0] + delta)
    removed = sum(abs(area([(verts[i][0], verts[i][2]) for i in idx[k:k + 3]])) for k in range(0, ni, 3)) - sum(abs(area(tr)) for tr in out_tris)
    return bytes(res), dv, dt, removed


def subtract_mesh_bytes_cdt(d, name, polys):
    """subtract_mesh_bytes with the result re-triangulated as one shape (shapely constrained Delaunay), for the
    new sea zones (2026-10-22): clipping every sea triangle by every land triangle split the zones into ever more
    slivers once the coasts followed the painted coastline (sea meshes 183k -> 485k vertices, SSuluandCelebesSeas
    41k of the 65535 a mesh may have); the same area in a constrained triangulation needs about one vertex per
    outline vertex.  Same output layout, winding and return value as subtract_mesh_bytes."""
    from igmod import v3d_objects
    import shapely
    from shapely.geometry import Polygon as _P
    from shapely.ops import unary_union as _U
    o, cid, size, nm, par = next(t for t in v3d_objects(d) if t[3] == name and t[1] == 0x2000)
    blob = bytearray(d[o:o + size])
    f = V3D.mesh_fields(bytes(blob))
    body, vh, nv, ih, ni = f['body'], f['vh'], f['nv'], f['ih'], f['ni']
    tx, ty, tz = struct.unpack_from('<3f', blob, body + 128 + 48)
    verts = [struct.unpack_from('<7f', blob, vh + 20 + 28 * k) for k in range(nv)]
    idx = struct.unpack_from('<%dH' % ni, blob, ih + 16)
    th = ih + 16 + 2 * ni
    f3, s3, ns = struct.unpack_from('<3I', blob, th)
    tail = bytes(blob[th + s3:])
    ly = _surface_level(verts)
    tris0 = [[(verts[i][0] + tx, verts[i][2] + tz) for i in idx[k:k + 3]] for k in range(0, ni, 3)]
    sign = 1.0 if area(tris0[0]) > 0 else -1.0                     # keep the mesh's winding
    zone = _U([_P(t).buffer(0) for t in tris0 if abs(area(t)) > 1e-9]).buffer(0)
    land = _U([_P(p).buffer(0) for p in polys]).buffer(0)
    rest = zone.difference(land).buffer(0)
    out_tris = []
    for g in (shapely.constrained_delaunay_triangles(rest).geoms if not rest.is_empty else []):
        tr = list(g.exterior.coords)[:3]
        if abs(area(tr)) < 1e-6:
            continue
        if area(tr) * sign < 0:
            tr = tr[::-1]
        out_tris.append(tuple(tr))
    nverts, nidx, local = [], [], {}
    for tri in out_tris:
        for (x, z) in tri:
            key = (round(x, 3), round(z, 3))
            if key not in local:
                local[key] = len(nverts)
                nverts.append((x - tx, ly, z - tz, 0.0, 0.0, K2U * x + C2U, C2V - K2V * z))
            nidx.append(local[key])
    assert nverts and len(nverts) < 65536, name
    head = bytearray(blob[:vh])
    lx = [v[0] for v in nverts]; lz = [v[2] for v in nverts]
    struct.pack_into('<6f', head, body + 208, min(lx), ly, min(lz), max(lx), ly, max(lz))
    cx, cz = (min(lx) + max(lx)) / 2, (min(lz) + max(lz)) / 2
    struct.pack_into('<4f', head, body + 232, cx, ly, cz, max(math.hypot(v[0] - cx, v[2] - cz) for v in nverts))
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(nverts), 514, 28, len(nverts)) + b''.join(struct.pack('<7f', *v) for v in nverts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(nidx), 2, len(nidx)) + struct.pack('<%dH' % len(nidx), *nidx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20, 1) + struct.pack('<5I', 0, len(nverts), 0, len(nidx) // 3, 0)
    nb = bytearray(bytes(head) + vsec + isec + tsec + tail)
    struct.pack_into('<I', nb, 4, len(nb))
    res = bytearray(d[:o] + bytes(nb) + d[o + size:])
    dv, dt = len(nverts) - nv, len(nidx) // 3 - ni // 3
    for off, delta in ((V3D.H_A, dv), (V3D.H_VERTS, dv), (V3D.H_TRIS, dt)):
        struct.pack_into('<I', res, off, struct.unpack_from('<I', res, off)[0] + delta)
    removed = sum(abs(area(t)) for t in tris0) - sum(abs(area(tr)) for tr in out_tris)
    return bytes(res), dv, dt, removed


def mesh_world_box(blob):
    """(x0, x1, z0, z1) of a mesh block in world coordinates."""
    f = V3D.mesh_fields(bytes(blob))
    tx, ty, tz = struct.unpack_from('<3f', blob, f['body'] + 128 + 48)
    xs = [struct.unpack_from('<f', blob, f['vdata'] + 28 * k)[0] + tx for k in range(f['nv'])]
    zs = [struct.unpack_from('<f', blob, f['vdata'] + 28 * k + 8)[0] + tz for k in range(f['nv'])]
    return min(xs), max(xs), min(zs), max(zs)


def mesh_triangles(blob):
    """World (x, z) triangles of a mesh block."""
    f = V3D.mesh_fields(bytes(blob))
    tx, ty, tz = struct.unpack_from('<3f', blob, f['body'] + 128 + 48)
    vs = [struct.unpack_from('<3f', blob, f['vdata'] + 28 * k) for k in range(f['nv'])]
    idx = struct.unpack_from('<%dH' % f['ni'], blob, f['ih'] + 16)
    return [tuple((vs[i][0] + tx, vs[i][2] + tz) for i in idx[k:k + 3]) for k in range(0, f['ni'], 3)]


def on_triangles(tris, x, z):
    """True if (x, z) lies on one of the triangles (edges included)."""
    for (ax, az), (bx, bz), (cx, cz) in tris:
        if x < min(ax, bx, cx) or x > max(ax, bx, cx) or z < min(az, bz, cz) or z > max(az, bz, cz):
            continue
        d1 = (bx - ax) * (z - az) - (bz - az) * (x - ax)
        d2 = (cx - bx) * (z - bz) - (cz - bz) * (x - bx)
        d3 = (ax - cx) * (z - cz) - (az - cz) * (x - cx)
        if not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0)):
            return True
    return False


def dummy_body(d, o):
    """Offset of the body (3 matrices, 'Dummy', boxes) of the Dummy object at o: after the 20-byte head + 2 strings."""
    p = o + 20
    for _ in range(2):
        p += 2 + struct.unpack_from('<H', d, p)[0]
    return p


def prune_fog_points(before, after, names):
    """Review V4 (2026-10-21): the original fog Dummies of meshes cut for new provinces stayed in the carved-out
    land (Moscu 84, Kursk 37, Marruecos 3), so fog cleared over Siberia, Ural, Kazakhstan ... whenever Moscu or
    Kursk was visible. Drop each Dummy of the meshes `names` that lay on its mesh in `before` (the model before the
    cuts) but not in `after`; points already off their mesh in the original data stay as they were. A mesh left
    with no Dummy keeps one, moved to its centre (or the nearest point of its surface). The object list is then
    re-canonicalised (child counts, ids; igmod.v3d_canonical). -> (bytes, dropped, moved)"""
    from igmod import v3d_canonical
    ob = {t[3]: t for t in v3d_objects(before) if t[1] == 0x2000}
    objs = v3d_objects(after)
    oa = {t[3]: t for t in objs if t[1] == 0x2000}
    drop, move = set(), {}
    for name in names:
        kids = [t for t in objs if t[1] == 0x5000 and t[4] == name]
        if not kids:
            continue
        tb = mesh_triangles(before[ob[name][0]:ob[name][0] + ob[name][2]])
        ta = mesh_triangles(after[oa[name][0]:oa[name][0] + oa[name][2]])
        gone = []
        for t in kids:
            x, y, z = struct.unpack_from('<3f', after, dummy_body(after, t[0]) + 64 + 48)
            if on_triangles(tb, x, z) and not on_triangles(ta, x, z):
                gone.append(t)
        if gone and len(gone) == len(kids):
            keep = gone.pop(0)
            x0, x1, z0, z1 = mesh_world_box(after[oa[name][0]:oa[name][0] + oa[name][2]])
            c = ((x0 + x1) / 2, (z0 + z1) / 2)
            if not on_triangles(ta, *c):
                cents = [((a[0] + b[0] + e[0]) / 3, (a[1] + b[1] + e[1]) / 3) for a, b, e in ta]
                c = min(cents, key=lambda q: (q[0] - c[0]) ** 2 + (q[1] - c[1]) ** 2)
            move[keep[0]] = c
        drop |= {t[0] for t in gone}
    if not drop and not move:
        return after, 0, 0
    out = bytearray(after[:objs[0][0]])
    for (o, cid, size, name, par) in objs:
        if o in drop:
            continue
        blob = bytearray(after[o:o + size])
        if o in move:
            b = dummy_body(after, o) - o
            x, y, z = struct.unpack_from('<3f', blob, b + 64 + 48)
            dx, dz = move[o][0] - x, move[o][1] - z
            for mo in (64, 128):                    # world position and local offset shift alike
                px, py, pz = struct.unpack_from('<3f', blob, b + mo + 48)
                struct.pack_into('<3f', blob, b + mo + 48, px + dx, py, pz + dz)
            q = b + 192 + 2 + struct.unpack_from('<H', blob, b + 192)[0] + 24     # world box, stored (x, z, y) x 2
            wb = list(struct.unpack_from('<6f', blob, q))
            struct.pack_into('<6f', blob, q, wb[0] + dx, wb[1] + dz, wb[2], wb[3] + dx, wb[4] + dz, wb[5])
        out += blob
    out += after[objs[-1][0] + objs[-1][2]:]          # the {0xff, 8} end marker
    for off in (V3D.H_OBJS, 86):                      # object count, dummy count
        struct.pack_into('<I', out, off, struct.unpack_from('<I', out, off)[0] - len(drop))
    v = V3D(bytes(out))
    v3d_canonical(v)
    return v.pack(), len(drop), len(move)

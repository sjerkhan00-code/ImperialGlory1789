"""Compute province shapes for unused painted land.

Free land = inside the map frame, not covered by any existing province (PosicionesMapa.gp masks),
and not sea (blue in the painted map). Free cells are split between the rough proposal polygons in
new_provinces.py (cells outside every polygon go to the nearest one), then traced and simplified.
Writes build/forslag_*.png previews; shapes() returns {id: polygon} for building meshes later.
"""
import sys, os, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_map as R, crop_map as C
from new_provinces import PROPOSALS

STEP = 25.0
FRAME = (480.0, 19950.0, -880.0, 12640.0)          # inner edge of the painted map border: x0, x1, z0, z1
MAX_DIST = 900.0                                    # free cells further than this from every proposal stay empty


def inside(poly, x, z):
    c = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[i - 1]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def seg_dist(p, a, b):
    (px, pz), (ax, az), (bx, bz) = p, a, b
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz or 1)))
    return math.hypot(px - ax - t * dx, pz - az - t * dz)


def occupied_cells(nx, nz):
    """Cells covered by an existing province mesh (exact triangles), grown by one cell to close seams."""
    import struct
    from igmod import V3D
    x0, _, z0, _ = FRAME
    d = open(os.path.join(R.MAPA, 'MapaGestionVolumenes.V3D'), 'rb').read()
    v = V3D(d)
    occ = set()
    for st, en, name in v.blocks:
        b = d[st:en]; f = V3D.mesh_fields(b)
        tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]
        pts = [(x + tx, z + tz) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        for t in range(0, len(idx), 3):
            tri = [pts[k] for k in idx[t:t + 3]]
            i0 = max(0, int((min(p[0] for p in tri) - x0) / STEP)); i1 = min(nx - 1, int((max(p[0] for p in tri) - x0) / STEP))
            j0 = max(0, int((min(p[1] for p in tri) - z0) / STEP)); j1 = min(nz - 1, int((max(p[1] for p in tri) - z0) / STEP))
            for j in range(j0, j1 + 1):
                for i in range(i0, i1 + 1):
                    if inside(tri, x0 + (i + 0.5) * STEP, z0 + (j + 0.5) * STEP):
                        occ.add((i, j))
    grown = set(occ)
    for (i, j) in occ:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                grown.add((i + di, j + dj))
    return grown


def grid():
    rows = C.load_bg()
    x0, x1, z0, z1 = FRAME
    nx, nz = int((x1 - x0) / STEP), int((z1 - z0) / STEP)
    occ = occupied_cells(nx, nz)
    free = {}
    for j in range(nz):
        z = z0 + (j + 0.5) * STEP
        for i in range(nx):
            if (i, j) in occ:
                continue
            x = x0 + (i + 0.5) * STEP
            px = int((x - R.X0) / (R.TILE_W * 4) * 1024); py = int((R.Z0 - z) / (R.TILE_H * 4) * 1024)
            rr, gg, bb = rows[py][px * 3:px * 3 + 3]
            if bb > rr + 12 and bb > gg - 5:          # painted sea is distinctly blue
                continue
            free[(i, j)] = (x, z)
    return free, nx, nz


def assign(free):
    owner = {}
    for cell, (x, z) in free.items():
        best = None
        for pid, name, own, poly in PROPOSALS:
            if inside(poly, x, z):
                best = (0, pid); break
            d = min(seg_dist((x, z), poly[k], poly[k - 1]) for k in range(len(poly)))
            if d < MAX_DIST and (best is None or d < best[0]):
                best = (d, pid)
        if best:
            owner[cell] = best[1]
    # keep only the largest connected blob per province (drops slivers and islands)
    out = {}
    for pid in {p[0] for p in PROPOSALS}:
        cells = {c for c, o in owner.items() if o == pid}
        seen, blobs = set(), []
        for c in cells:
            if c in seen:
                continue
            stack, blob = [c], []
            seen.add(c)
            while stack:
                a = stack.pop(); blob.append(a)
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (a[0] + d[0], a[1] + d[1])
                    if n in cells and n not in seen:
                        seen.add(n); stack.append(n)
            blobs.append(blob)
        if blobs:
            for c in max(blobs, key=len):
                out[c] = pid
    return out


def trace(cells):
    """Outer boundary of a set of grid cells as a vertex loop in grid-corner coordinates."""
    edges = {}
    for (i, j) in cells:
        for a, b, n in (((i, j), (i + 1, j), (i, j - 1)), ((i + 1, j), (i + 1, j + 1), (i + 1, j)),
                        ((i + 1, j + 1), (i, j + 1), (i, j + 1)), ((i, j + 1), (i, j), (i - 1, j))):
            if n not in cells:
                edges[a] = b
    loops, used = [], set()
    for s in list(edges):
        if s in used:
            continue
        loop, p = [], s
        while p not in used and p in edges:
            used.add(p); loop.append(p); p = edges[p]
        loops.append(loop)
    return max(loops, key=len)


def simplify(pts, tol):
    if len(pts) < 4:
        return pts
    a, b = pts[0], pts[-1]
    d, k = max((seg_dist(p, a, b), n) for n, p in enumerate(pts[1:-1], 1))
    if d > tol:
        return simplify(pts[:k + 1], tol)[:-1] + simplify(pts[k:], tol)
    return [a, b]


def snap(polys, radius=110.0):
    """Move new-province vertices onto nearby vertices of existing province outlines, and onto each
    other, so shared borders coincide exactly."""
    anchors = set()
    for edges in R.province_outlines(os.path.join(R.MAPA, 'MapaGestionVolumenes.V3D')).values():
        for a, b in edges:
            anchors.add(a); anchors.add(b)
    anchors = list(anchors)
    out = {}
    for pid, poly in polys.items():
        new = []
        for x, z in poly:
            best = min(anchors, key=lambda a: (a[0] - x) ** 2 + (a[1] - z) ** 2)
            new.append(best if math.hypot(best[0] - x, best[1] - z) <= radius else (x, z))
        out[pid] = [p for k, p in enumerate(new) if p != new[k - 1]]
    # weld vertices of neighbouring new provinces
    pts = [p for poly in out.values() for p in poly]
    for pid, poly in out.items():
        for k, (x, z) in enumerate(poly):
            near = [q for q in pts if q != (x, z) and math.hypot(q[0] - x, q[1] - z) <= STEP * 2.5]
            if near:
                q = min(near); poly[k] = min(q, (x, z))
    return out


def untangle(poly):
    """Remove the small loops that snapping can create where a polygon crosses itself."""
    import meshgen
    poly = list(poly)
    for _ in range(50):
        n = len(poly); hit = None
        for i in range(n):
            for j in range(i + 2, n):
                if (i == 0 and j == n - 1):
                    continue
                if meshgen._seg_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                    hit = (i, j); break
            if hit:
                break
        if not hit:
            return poly
        i, j = hit
        inner = j - i                      # vertices i+1..j form one loop, the rest the other
        poly = poly[:i + 1] + poly[j + 1:] if inner <= n - inner else poly[i + 1:j + 1]
    return poly


def shapes(tol=40.0):
    free, nx, nz = grid()
    own = assign(free)
    x0, _, z0, _ = FRAME
    res = {}
    for pid, name, o, poly in PROPOSALS:
        cells = {c for c, v in own.items() if v == pid}
        if not cells:
            continue
        loop = [(x0 + i * STEP, z0 + j * STEP) for i, j in trace(cells)]
        n = len(loop) // 2
        res[pid] = simplify(loop[:n + 1], tol)[:-1] + simplify(loop[n:] + loop[:1], tol)[:-1]
    return {k: untangle(p) for k, p in snap(res).items()}, own, free


if __name__ == '__main__':
    res, own, free = shapes()
    for pid, poly in res.items():
        area = abs(sum(poly[k][0] * poly[k - 1][1] - poly[k - 1][0] * poly[k][1] for k in range(len(poly)))) / 2
        print(pid, next(p[1] for p in PROPOSALS if p[0] == pid), len(poly), 'vertices, area %.1f M' % (area / 1e6))
    polys = list(res.values())
    labels = [(str(pid), sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)) for pid, poly in res.items()]
    C.main(-600, 21000, -2000, 14000, 21, os.path.join(R.OUT, 'forslag_oversikt.png'), polys, labels)
    C.main(11000, 21000, -2000, 13000, 12, os.path.join(R.OUT, 'forslag_ost.png'), polys, labels)
    C.main(-600, 11500, -2000, 3500, 10, os.path.join(R.OUT, 'forslag_sor.png'), polys, labels)
    import json
    json.dump({str(k): v for k, v in res.items()}, open(os.path.join(R.OUT, 'forslag_former.json'), 'w'))

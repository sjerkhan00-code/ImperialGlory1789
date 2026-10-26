"""build/art/styled2_edges.json: the province polygons tools/art/styled2.py draws the borders of the new art from.

Why (2026-10-23, ig-map-engineer): build/tiles_new was rendered from build/coastfit/base_world_provinces_orig.json (the
pre-design, pre-coast-fit 1789 polygons).  That file is coastfit.py's base snapshot and is replaced by the coast-fitted
snapshot whenever coastfit runs on changed inputs, so it cannot stay the styled2 source.  This file takes its place:
  * start: build/art/styled2_edges.json if present (idempotent re-run), else build/coastfit/base_world_provinces_orig.json;
  * design.STYLED_JOBS: borders of 1789 provinces against the extension pieces of Egipto / Cirenaica made natural in
    design.py; render_borders.py cannot draw them (not old-area provinces, and below its canvas), styled2 does;
  * DENSIFY: long straight edges get collinear vertices every DENSIFY_STEP units.  styled2._border_mask draws an edge
    only when its test points at 20 / 50 / 80 % lie on land INSIDE the tile window, so one long segment crossing a
    tile edge was drawn in one tile only (South Australia | New South Wales stopped at the row 5 / 6 seam, and the
    missing pillow rim made Victoria 9 levels lighter below it).  Collinear points change no geometry.
Run:  python tools/art/styled_edges.py      then re-render the tiles that contain the changed borders, e.g.
      python tools/art/render_all2.py --force --edges build/art/styled2_edges.json --only 1,4 2,4
"""
import os, sys, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'art', 'styled2_edges.json')
BASE = os.path.join(BUILD, 'coastfit', 'base_world_provinces_orig.json')
sys.path.insert(0, os.path.join(HERE, 'oldarea'))

DENSIFY_STEP = 120.0
# (province key, edge end a, edge end b): a straight edge shared by two 1789 provinces; both polygons get the points
DENSIFY = [
    ('southaus', (34858.759978425025, -9996.979), (35338.759978425025, -8556.979)),     # | nsw (Victoria seam)
    ('nsw', (34858.759978425025, -9996.979), (35338.759978425025, -8556.979)),
]


def densify(poly, a, b, step, tol=1.0):
    """Insert collinear points every `step` units on the edge a-b of poly (either direction); unchanged if absent."""
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        for s, e in ((a, b), (b, a)):
            if math.hypot(p[0] - s[0], p[1] - s[1]) < tol and math.hypot(q[0] - e[0], q[1] - e[1]) < tol:
                L = math.hypot(q[0] - p[0], q[1] - p[1])
                k = int(L // step)
                if k < 1:
                    return poly, 0
                ins = [[round(p[0] + (q[0] - p[0]) * t / (k + 1), 4), round(p[1] + (q[1] - p[1]) * t / (k + 1), 4)]
                       for t in range(1, k + 1)]
                return poly[:i + 1] + ins + poly[i + 1:], len(ins)
    return poly, 0


def main():
    import design as D
    src = OUT if os.path.exists(OUT) else BASE
    W = json.load(open(src, encoding='utf8'))
    print('from', os.path.relpath(src, ROOT))
    for key, line in D.STYLED_JOBS:
        poly = [tuple(p) for p in W[key]['poly']]
        if D._has_run(poly, line):
            print('  %-8s natural line already in place' % key)
            continue
        a, b = line[0], line[-1]
        # the coast fit moved some coast vertices of the build polygons: end on this polygon's own vertex
        ia = min(range(len(poly)), key=lambda i: math.hypot(poly[i][0] - a[0], poly[i][1] - a[1]))
        ib = min(range(len(poly)), key=lambda i: math.hypot(poly[i][0] - b[0], poly[i][1] - b[1]))
        assert math.hypot(poly[ia][0] - a[0], poly[ia][1] - a[1]) < 8 and math.hypot(poly[ib][0] - b[0], poly[ib][1] - b[1]) < 8, key
        ln = [poly[ia]] + list(line[1:-1]) + [poly[ib]]
        new = D.replace_edge_run(poly, ln[0], ln[-1], ln, tol=0.01)
        W[key]['poly'] = [list(p) for p in D.geo.ccw(new)]
        print('  %-8s natural line: %d -> %d vertices' % (key, len(poly), len(new)))
    for key, a, b in DENSIFY:
        poly, k = densify([list(p) for p in W[key]['poly']], a, b, DENSIFY_STEP)
        W[key]['poly'] = poly
        print('  %-8s densified edge %s-%s: +%d points' % (key, a, b, k))
    json.dump(W, open(OUT, 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    print('wrote', os.path.relpath(OUT, ROOT))


if __name__ == '__main__':
    main()

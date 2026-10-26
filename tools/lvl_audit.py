"""Offline audit of a battle map against the invariants of the 56 original maps.

    python tools/lvl_audit.py <map.lvl> [--originals]

For every map it measures structural invariants (index ranges, cross references between chunks, sector-map
geometry, the engine's casilla look-ups, tree-set node counts) and, with --originals, the same numbers for the 56
original maps, then flags every value of the new map outside the originals' range or any hard error.

Hard errors are things the engine dereferences: a casilla centre (75 x 75 grid, CMapaCasillas::init FUN_004d38d0)
that no sector owns or that lies on a sector edge (getSectorOwner FUN_0048d4a0 returns NULL -> crash at 0x4d3017),
sector / point / link / construction-sector indices out of range, octree leaves that do not list every terrain
subset exactly once, index-buffer entries outside their subset, V3D child counts that do not match the nodes.
"""
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lvl          # noqa: E402
import lvl_nav      # noqa: E402
import lvl_v3d      # noqa: E402

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, 'build', 'lvl_original_stats.json')


def _pip(poly, px, pz):
    """Even-odd ray test in float32; also reports a point lying exactly on an edge."""
    inside, edge = False, False
    n = len(poly)
    for i in range(n):
        x0, z0 = poly[i]
        x1, z1 = poly[(i + 1) % n]
        if z0 == z1:
            if pz == z0 and min(x0, x1) <= px <= max(x0, x1):
                edge = True
            continue
        if (z0 <= pz < z1) or (z1 <= pz < z0):
            xc = np.float32(x0 + (pz - z0) * (x1 - x0) / (z1 - z0))
            if xc == px:
                edge = True
            if xc > px:
                inside = not inside
    return inside, edge


def _edge_dist(poly, px, pz):
    best = 1e18
    n = len(poly)
    for i in range(n):
        x0, z0 = poly[i]
        x1, z1 = poly[(i + 1) % n]
        dx, dz = x1 - x0, z1 - z0
        L2 = dx * dx + dz * dz or 1.0
        t = max(0.0, min(1.0, ((px - x0) * dx + (pz - z0) * dz) / L2))
        best = min(best, math.hypot(px - x0 - t * dx, pz - z0 - t * dz))
    return best


def stats(path):
    """Invariant measurements of one map. Returns (numbers, errors)."""
    m = lvl.load(path)
    S, E = {}, []
    t = m.get(lvl.TERRAIN)
    size = t['size'][0]
    # --- terrain mesh
    nv = len(t['vb']['data']) // t['vb']['stride']
    ib = np.frombuffer(bytes(t['ib']['data']), '<u2' if t['ib']['isize'] == 2 else '<u4')
    S['terrain_vertices'] = nv
    S['terrain_subsets'] = len(t['subsets'])
    for k, (fv, n, si, npr, mat) in enumerate(t['subsets']):
        idx = ib[si:si + 3 * npr]
        if fv + n > nv or si + 3 * npr > len(ib) or (len(idx) and (idx.min() < fv or idx.max() >= fv + n)):
            E.append('terrain subset %d indexes outside its range' % k)
        if mat >= len(t['materials']):
            E.append('terrain subset %d material %d out of range' % (k, mat))
    refs = []

    def walk(nd):
        refs.extend(nd['items'])
        for c in nd['children']:
            walk(c)
    walk(t['octree'])
    if sorted(refs) != list(range(len(t['subsets']))):
        E.append('octree leaves do not list every subset exactly once')
    h = m.heights()
    v = m.vertices()
    iz, ix = m.grid_index(v)
    S['vb_y_minus_heightmap_max'] = float(np.abs(h[iz, ix] - v['y']).max())
    if S['vb_y_minus_heightmap_max'] > 0.5:
        E.append('terrain VB y differs from the heightmap')
    # --- sector map
    sm = m.get(lvl.SECTORMAP)
    P = sm['points']
    ns = len(sm['sectors'])
    S['sectors'] = ns
    S['sector_points'] = len(P)
    S['sector_links'] = len(sm['links'])
    if [s['id'] for s in sm['sectors']] != list(range(ns)):
        E.append('sector ids not 0..n-1')
    for s in sm['sectors']:
        if any(i >= len(P) for i in s['poly']):
            E.append('sector %d point index out of range' % s['id'])
    for a, b, i, j in sm['links']:
        if a >= ns or b >= ns or i >= len(P) or j >= len(P):
            E.append('link out of range %s' % [a, b, i, j])
    polys = [[(np.float32(P[i][0]), np.float32(P[i][2])) for i in s['poly']] for s in sm['sectors']]
    S['sector_max_vertices'] = max(len(q) for q in polys)
    areas = [abs(0.5 * sum(float(q[k][0]) * float(q[(k + 1) % len(q)][1]) - float(q[(k + 1) % len(q)][0]) *
                           float(q[k][1]) for k in range(len(q)))) for q in polys]
    S['sector_min_area_m2'] = min(areas) / 1e4
    S['sector_max_area_m2'] = max(areas) / 1e4
    edges = [math.hypot(float(q[k][0]) - float(q[(k + 1) % len(q)][0]), float(q[k][1]) - float(q[(k + 1) % len(q)][1]))
             for q in polys for k in range(len(q))]
    S['sector_min_edge_cm'] = min(edges)
    deg = np.zeros(ns, int)
    for a, b, i, j in sm['links']:
        deg[a] += 1; deg[b] += 1
    S['sector_max_links'] = int(deg.max())
    S['impassable_area_pct'] = 100.0 * sum(a for a, s in zip(areas, sm['sectors']) if not s['a']) / sum(areas)
    # impassable groups (FUN_0048f0a0 merges connected impassable sectors)
    adj = {i: set() for i in range(ns)}
    for a, b, i, j in sm['links']:
        adj[a].add(b); adj[b].add(a)
    seen, groups = set(), []
    for s in sm['sectors']:
        if s['a'] or s['id'] in seen:
            continue
        stack, g = [s['id']], []
        seen.add(s['id'])
        while stack:
            k = stack.pop()
            g.append(k)
            for n_ in adj[k]:
                if n_ not in seen and not sm['sectors'][n_]['a']:
                    seen.add(n_); stack.append(n_)
        groups.append(g)
    S['impassable_groups'] = len(groups)
    S['impassable_largest_group'] = max([len(g) for g in groups] or [0])
    # casilla centres (engine look-up at load)
    bbs = [(min(p[0] for p in q), max(p[0] for p in q), min(p[1] for p in q), max(p[1] for p in q)) for q in polys]
    tl = m.get(lvl.TERRAINLOGIC)
    cs = tl['cells'][0] * tl['cell_size'][0] / 75.0
    none = on_edge = near = multi = 0
    for j in range(75):
        for i in range(75):
            px, pz = np.float32((i + 0.5) * cs), np.float32((j + 0.5) * cs)
            hits = 0
            for q, bb in zip(polys, bbs):
                if bb[0] <= px <= bb[1] and bb[2] <= pz <= bb[3]:
                    ins, ed = _pip(q, px, pz)
                    hits += ins
                    on_edge += ed
                    if _edge_dist(q, float(px), float(pz)) < 0.5:
                        near += 1
            none += hits == 0
            multi += hits > 1
    S['casilla_centres_on_sector_edge'] = on_edge
    S['casilla_centres_within_5mm_of_edge'] = near
    S['casilla_centres_without_sector'] = none
    S['casilla_centres_in_two_sectors'] = multi
    if none or on_edge:
        E.append('casilla centres without a sector (%d) or on a sector edge (%d): engine crash 0x4d3017' % (none, on_edge))
    # --- objects
    ob = m.get(lvl.OBJECTLIST)
    S['object_classes'] = len(ob['library'])
    S['object_instances'] = len(ob['instances'])
    for k, o in enumerate(ob['instances']):
        if o['cls'] >= len(ob['library']):
            E.append('instance %d class %d out of range' % (k, o['cls']))
        if ob['library'][o['cls']]['type'] != o['type']:
            E.append('instance %d type differs from its class' % k)
        x, z = o['matrix'][12], o['matrix'][14]
        if not (-1 <= x <= size + 1 and -1 <= z <= size + 1):
            S['instances_outside_map'] = S.get('instances_outside_map', 0) + 1     # originals: 0..1 (soft)
        for sid in m.construction_sectors(o):
            if sid >= ns:
                E.append('construction %d sector %d out of range' % (k, sid))
            elif sm['sectors'][sid]['type'] != lvl_nav.TT['INTERIOR']:
                S['construction_sectors_not_interior'] = S.get('construction_sectors_not_interior', 0) + 1
    # --- logic
    S['troop_areas'] = len(m.get(lvl.POSTROOPER))
    S['troop_areas_attacker'] = sum(1 for p in m.get(lvl.POSTROOPER) if p['flags'] & 4)
    S['troop_areas_defender'] = sum(1 for p in m.get(lvl.POSTROOPER) if p['flags'] & 8)
    for p in m.get(lvl.POSTROOPER) + m.get(lvl.LOCATIONS):
        if not (0 <= p['pos'][0] <= size and 0 <= p['pos'][2] <= size):
            E.append('troop area / location outside the map: %s' % p.get('name'))
    S['zones_outside_map'] = sum(1 for a in m.get(lvl.ARBZONES)          # originals: 0..1 (soft)
                                 if any(not (0 <= x <= size and 0 <= z <= size) for x, z in a['poly']))
    g = m.get(lvl.GRAFOIA)
    S['ai_graph_nodes'] = len(g['nodes'])
    # (originals list neighbour ids beyond the node count; the retail exe never reads the graph: soft)
    S['ai_graph_nb_beyond_count'] = sum(1 for n_ in g['nodes'] for k in n_['nb'] if k >= len(g['nodes']))
    S['sound_positional'] = len(m.get(lvl.SOUND)['positional'])
    # --- tree set
    md = os.path.join(os.path.dirname(os.path.abspath(path)), 'Models')
    tree = next((c['model'] for c in ob['library'] if c['type'] == lvl.TO_ARBOL), None)
    if tree and os.path.exists(os.path.join(md, tree)):
        d = open(os.path.join(md, tree), 'rb').read()
        objs = lvl_v3d.objects(d)
        names = {o['name'] for o in objs}
        S['tree_nodes'] = len(objs)
        if struct.unpack_from('<I', d, 90)[0] != len(objs):
            E.append('tree V3D header node count %d != %d' % (struct.unpack_from('<I', d, 90)[0], len(objs)))
        unique = len(names) == len(objs)                 # (03Irlanda has two nodes named 'Arboles')
        for o in objs:
            if not unique:
                break
            if o['parent'] and o['parent'] not in names:
                E.append('tree V3D node %s has a missing parent' % o['name'])
            nchild = sum(1 for c in objs if c['parent'] == o['name'])
            stored = struct.unpack_from('<I', d, o['off'] + (32 if o['cid'] == 0x2000 else 12))[0]
            if stored != nchild:
                E.append('tree V3D node %s child count %d != %d' % (o['name'], stored, nchild))
        mn, mx = lvl_v3d.global_bbox(d)
        for trunk, _ in lvl_v3d.trees(d):
            x, y, z = lvl_v3d.translation(d, trunk['m2'])
            if not (mn[0] <= x <= mx[0] and mn[2] <= z <= mx[2]):
                E.append('tree %s outside the model bounding box' % trunk['name'])
                break
            if not (-1 <= x <= size + 1 and -1 <= z <= size + 1):
                S['trees_outside_map'] = S.get('trees_outside_map', 0) + 1
    return S, E


def original_ranges(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return json.load(open(CACHE))
    allv = {}
    for p in lvl.original_maps():
        s, e = stats(p)
        for k, v in s.items():
            allv.setdefault(k, []).append(v)
        print('  %-28s %s' % (os.path.basename(p), ('errors: %s' % e) if e else 'ok'))
    rng = {k: [min(v), max(v)] for k, v in allv.items()}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(rng, open(CACHE, 'w'), indent=1)
    return rng


def audit(path, refresh=False):
    s, e = stats(path)
    rng = original_ranges(refresh)
    out = []
    for k, v in s.items():
        lo, hi = rng.get(k, [None, None])
        flag = '' if lo is None or lo <= v <= hi else '   <-- outside originals'
        out.append('%-38s %12.3f   originals %s..%s%s' % (k, v, lo, hi, flag))
    return out, e


if __name__ == '__main__':
    lines, errs = audit(sys.argv[1], '--originals' in sys.argv)
    print('\n'.join(lines))
    print('ERRORS:' if errs else 'no hard errors', *errs, sep='\n  ')
    sys.exit(1 if errs else 0)

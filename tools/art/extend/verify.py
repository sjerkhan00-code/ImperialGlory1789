"""Checks for build/extend: shared edges with the old meshes, overlaps, polygon validity, seeds, areas."""
import json, sys, math, struct, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import meshgen as MG
from igmod import V3D
from extend import MOD_V3D, seg_project, mesh_outlines, OUT
import grid as G

e = json.load(open(os.path.join(OUT, 'extensions.json')))
n = json.load(open(os.path.join(OUT, 'world_provinces_ext.json'), encoding='utf8'))
outl = mesh_outlines()
def shared(poly, edges):
    tot = shr = 0
    for k in range(len(poly)):
        a, b = poly[k - 1], poly[k]; L = math.hypot(b[0] - a[0], b[1] - a[1]); tot += L
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if all(seg_project(q, edges)[1] < 1.0 for q in (a, b, m)):
            shr += L
    return tot, shr
d = open(MOD_V3D, 'rb').read(); v = V3D(d)
tris = {}
for st, en, name in v.blocks:
    if name in e:
        b = d[st:en]; f = V3D.mesh_fields(b); tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]; pts = [(x + tx, z + tz) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        tris[name] = [(pts[idx[t]], pts[idx[t + 1]], pts[idx[t + 2]]) for t in range(0, len(idx), 3)]
def intri(p, a, b, c):
    def s(p1, p2, p3): return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a); return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
for name, polys in e.items():
    for p in polys:
        tot, shr = shared(p, outl[name])
        inside = sum(1 for q in MG.interior_points(p, 40, 0) if any(intri(q, *t) for t in tris[name]))
        xs = [q[0] for q in p]; zs = [q[1] for q in p]
        print('%-17s verts %3d simple %s perim %6.0f on-mesh-edge %5.0f (%2.0f%%) samples-in-mesh %2d  x[%6.0f %6.0f] z[%6.0f %6.0f]'
              % (name, len(p), MG.is_simple(p), tot, shr, 100 * shr / tot, inside, min(xs), max(xs), min(zs), max(zs)))
bad = [k for k, v in n.items() if not MG.is_simple(v['poly']) or len(v['poly']) < 3]
print('new provinces', len(n), 'not simple', bad)
# shared borders ext <-> new: every ext edge not on the mesh must be an edge of some new province (reversed)
newedges = set()
for v_ in n.values():
    pl = v_['poly']
    for k in range(len(pl)):
        newedges.add((tuple(pl[k - 1]), tuple(pl[k])))
for name, polys in e.items():
    miss = 0; tot = 0
    for p in polys:
        for k in range(len(p)):
            a, b = tuple(p[k - 1]), tuple(p[k])
            if seg_project(a, outl[name])[1] < 1.0 and seg_project(b, outl[name])[1] < 1.0:
                continue
            tot += 1
            if (b, a) not in newedges and (a, b) not in newedges:
                miss += 1
    print('%-17s ext edges off the mesh: %3d, not shared with a new province: %d' % (name, tot, miss))

# all land stays assigned: unassigned land cells after must be a subset of those before
from extend import build_labels
g, meta = G.load(); D = build_labels()
before = g['land'] & (g['ex'] < 0) & (g['final'] < 0)
after = g['land'] & (g['ex'] < 0) & ((D['comb'] < 0) | ((D['comb'] >= 1000) & (D['comb'] < 2000)))
print('unassigned land cells: before %d, after %d, newly unassigned %d, newly assigned %d' % (before.sum(), after.sum(), (after & ~before).sum(), (before & ~after).sum()))
# every extension edge: what is on the other side
import collections
comb = D['comb']; X0_, Z1_, STEP_ = -501.240021574973, 13443.02103250478, 40.0
alledges = [ed for nm, eds in outl.items() if not (nm[0] in 'SW' and nm[1:2].isupper()) for ed in eds]
extedges = {(tuple(p[k - 1]), tuple(p[k]), nm) for nm, polys in e.items() for p in polys for k in range(len(p))}
def cell(x, z):
    i = int((x - X0_) // STEP_); j = int((Z1_ - z) // STEP_)
    return int(comb[j, i]) if 0 <= j < comb.shape[0] and 0 <= i < comb.shape[1] else -1
for nm, polys in e.items():
    cat = collections.Counter()
    for p in polys:
        for k in range(len(p)):
            a, b = tuple(p[k - 1]), tuple(p[k])
            if seg_project(a, outl[nm])[1] < 1 and seg_project(b, outl[nm])[1] < 1: cat['own mesh'] += 1; continue
            if seg_project(a, alledges)[1] < 1 and seg_project(b, alledges)[1] < 1: cat['other old mesh'] += 1; continue
            if (b, a) in newedges or (a, b) in newedges: cat['new province'] += 1; continue
            if any((b, a, o) in extedges for o in e if o != nm): cat['other ext'] += 1; continue
            mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; dx, dz = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dz) or 1
            s1, s2 = cell(mx - dz / L * 25, mz + dx / L * 25), cell(mx + dz / L * 25, mz - dx / L * 25)
            cat['sea/unassigned' if -1 in (s1, s2) else 'OTHER %s/%s' % (s1, s2)] += 1
    print('%-17s %s' % (nm, dict(cat)))

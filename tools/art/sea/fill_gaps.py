"""Merge enclosed mesh-less sea gaps into a neighbouring sea zone (build/sea/sea_zones.json).

Why (2026-10-23, ig-map-engineer): tools/art/sea/sea_zones.py keeps only the sea-connected piece of a zone around its
seeds.  The Tasman Sea's Bass Strait seeds (146.0,-39.5) / (149.5,-38.5) fell in a piece cut off from the main Tasman
piece by the Coast of New South Wales and Southern Ocean (Van Diemen) cells, so that piece was dropped: ~3.4M units2
between Victoria, Van Diemen's Land and three zones (Bight, New South Wales, Van Diemen) had no zone at all.  No mesh
there means no fog clearing (meshgen.fog_hole_points had to add 12 'NieblaLago' points), no click target, no gp
figure cells and no ship route through the strait (the land mesh simply ended at the coast).

What: GAPS = [dict(seed, box, parts=[(zone, side polygon or None = the rest), ...])].  The gap holding the seed = the
box minus every sea zone, every 1789 land polygon (build/world_provinces.json) and every extension piece
(build/extend/extensions.json).  It is split by the side polygons; each part is grown GROW units over the coast (the
land cut in the build, meshgen.subtract_mesh_bytes_cdt, then defines the shore: no hairline gap), kept inside its
side and off the other zones, and merged into its zone; islets that end up enclosed are filled (the build cuts them
out of the mesh).  An island must never be enclosed by ONE zone (a polygon ring has no holes: the zone would cover
it and its gp mask would put ships on the land), hence the split: Van Diemen's Land keeps a stretch of its NE coast
on the Coast of New South Wales while the Southern Ocean (Van Diemen) takes Bass Strait and the sea SE of it.
Every zone a part touches must already be a sea neighbour of its zone (the sea graph, i.e. the neighbour lists
written into the province records, stays exactly as it was); coastal_land gains the land a part touches.
Idempotent: a seed already inside its first part's zone is skipped.

Run:  python tools/art/sea/fill_gaps.py            dry run: report + build/map6_audit/fill_gaps_<zones>.png
      python tools/art/sea/fill_gaps.py --apply    writes build/sea/sea_zones.json and its copy
                                                   build/oldarea/sea_zones_fixed.json (design.py reads the first and
                                                   writes the second; keep them equal).  Back them up first.
Then rebuild (make_map.py): the sea mesh, gp mask and fog points of the zone follow from the polygon.
"""
import os, sys, json
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)
BUILD = os.path.join(ROOT, 'build')
sys.path.insert(0, TOOLS)
import meshgen as MG

SEA = os.path.join(BUILD, 'sea', 'sea_zones.json')
SEA_COPY = os.path.join(BUILD, 'oldarea', 'sea_zones_fixed.json')
GROW = 6.0           # world units over the coast: only a margin against hairline gaps (the gp mask is not land-cut,
                     # so a wider band would give the zone figure cells on the land)
LAND_SIMPLIFY = 2.0  # world units: the grown outline over land (stays >= GROW - this outside the coast)
MIN_GAP = 1.0e6      # units2: a smaller hit is a coastal sliver, not the gap that was meant
FILL_MAX = 20000.0   # units2 of enclosed land a merged zone may cover (islets); more means an island got enclosed
# Bass Strait + the water east of Van Diemen's Land.  NSW_SIDE: from inside Van Diemen's Land (D) out over its NE
# corner, east of Flinders Island (B; the Furneaux islet 36403..36534 x -10470..-10354 stays on the strait side) to
# the Gippsland coast (C, 50 units inland), north through New South Wales; south edge D -> the Coast of New South
# Wales / Southern Ocean (Van Diemen) junction J (38541, -10987) and on east.
_D, _B, _C, _J = (36300.0, -10700.0), (36640.0, -10440.0), (36900.0, -9900.0), (38541.0, -10987.0)
NSW_SIDE = [(36900.0, -8000.0), (39500.0, -8000.0), (39500.0, -11010.0), _J, _D, _B, _C]
GAPS = [
    dict(seed=(36500.0, -10200.0), box=(32000.0, -12500.0, 39000.0, -8000.0),
         parts=[('southern_e', None), ('nsw', NSW_SIDE)]),
]


def load(path):
    return json.load(open(path, encoding='utf8'))


def dump(data, path):
    # same bytes as design.py's json.dump(..., indent=0, ensure_ascii=False) in Windows text mode (CRLF)
    s = json.dumps(data, indent=0, ensure_ascii=False).replace('\n', '\r\n')
    open(path, 'wb').write(s.encode('utf8'))


def main(apply):
    S = load(SEA)
    W = load(os.path.join(BUILD, 'world_provinces.json'))
    E = load(os.path.join(BUILD, 'extend', 'extensions.json'))
    land = {k: Polygon(v['poly']).buffer(0) for k, v in W.items()}
    pieces = [Polygon(r).buffer(0) for v in E.values() for r in v]
    changed = False
    for spec in GAPS:
        seed, bb = spec['seed'], spec['box']
        B = box(*bb)
        zones = {k: Polygon(v['poly']).buffer(0) for k, v in S.items()}
        first = spec['parts'][0][0]
        if zones[first].contains(Point(seed)):
            print('gap at %s: already inside %s, nothing to do' % (seed, first))
            continue
        near_land = unary_union([g for g in list(land.values()) + pieces if g.intersects(B)])
        gap = B.difference(unary_union([g for g in zones.values() if g.intersects(B)] + [near_land]))
        cands = [gap] if gap.geom_type == 'Polygon' else list(gap.geoms)
        G = next((p for p in cands if p.contains(Point(seed))), None)
        assert G is not None and G.area > MIN_GAP, ('no gap at the seed', seed)
        gx0, gz0, gx1, gz1 = G.bounds
        assert bb[0] < gx0 and bb[1] < gz0 and gx1 < bb[2] and gz1 < bb[3], ('gap reaches the search box edge', seed)
        print('gap at %s: %.0f units2, bounds %s' % (seed, G.area, [round(c) for c in G.bounds]))
        sides, rest = {}, B
        for zone, side in spec['parts']:
            if side is not None:
                sides[zone] = Polygon(side).intersection(B)
                rest = rest.difference(sides[zone])
        for zone, side in spec['parts']:
            if side is None:
                sides[zone] = rest
        new = {}
        for zone, _ in spec['parts']:
            Z, Sd = zones[zone], sides[zone]
            part = G.intersection(Sd)
            ring = part.buffer(2.0)
            t_zones = {k: ring.intersection(g.boundary).length for k, g in zones.items() if k != zone and ring.intersects(g)}
            t_zones = {k: L for k, L in t_zones.items() if L > 50.0}
            t_land = {k: ring.intersection(g.boundary).length for k, g in land.items() if ring.intersects(g)}
            t_land = {k: L for k, L in t_land.items() if L > 50.0}
            shared_own = ring.intersection(Z.boundary).length
            print('  %-10s part %.0f units2; shares %.0f units with the zone; touches zones %s; land %s'
                  % (zone, part.area, shared_own, {k: round(L) for k, L in t_zones.items()},
                     {k: round(L) for k, L in t_land.items()}))
            assert shared_own > 500.0, ('the part does not border its zone', zone)
            missing = [k for k in t_zones if k not in S[zone]['neighbours_sea']]
            assert not missing, ('merging would add sea neighbours (sea graph change)', zone, missing)
            # grow over the coast (offset curve simplified: it lies over land, which the build cuts away), then
            # re-clipped to the side and off the other zones and the parts finished before (exact shared borders)
            others = unary_union([g for k, g in zones.items() if k != zone and g.intersects(B)]
                                 + [v[1] for v in new.values()])
            grown = part.buffer(GROW, join_style=2, mitre_limit=2.0).simplify(LAND_SIMPLIFY)
            grown = grown.intersection(Sd).difference(others)
            U = unary_union([Z, part.difference(others), grown])
            if U.geom_type != 'Polygon':                      # loose specks (coastal slivers cut off by the side)
                main_ = max(U.geoms, key=lambda g: g.intersection(Z).area)
                lost = U.area - main_.area
                print('    dropped %d loose speck(s), %.0f units2' % (len(U.geoms) - 1, lost))
                assert lost < 5000.0, ('merge falls apart', zone, lost)
                U = main_
            filled = Polygon(U.exterior)
            fill = filled.difference(U).area
            assert fill <= FILL_MAX, ('an island would be enclosed by one zone', zone, round(fill))
            U = filled.simplify(0.0)                          # (collinear points only: no border moves)
            pts = []
            for x, z in U.exterior.coords[:-1]:
                q = [round(x, 3), round(z, 3)]
                if not pts or q != pts[-1]:
                    pts.append(q)
            if pts[0] == pts[-1]:
                pts.pop()
            if (MG.area(pts) > 0) != (MG.area(S[zone]['poly']) > 0):     # keep the winding of the original ring
                pts = pts[::-1]
            P = Polygon(pts)
            assert P.is_valid and MG.is_simple([tuple(q) for q in pts]), ('merged ring not simple', zone)
            assert len(pts) <= 300, ('too many vertices for check_zones.py', zone, len(pts))
            on_land = P.intersection(near_land).area
            print('    merged: %d -> %d vertices, area %.0f -> %.0f units2 (%.0f on land: cut out by the build; '
                  'islets filled %.0f)' % (len(S[zone]['poly']), len(pts), Z.area, P.area, on_land, fill))
            new[zone] = (pts, P, t_land, on_land)
        # cross checks on the result: overlaps, coverage of the gap, no island swallowed
        after = dict(zones)
        after.update({k: v[1] for k, v in new.items()})
        for zone in new:
            ov = {k: after[zone].intersection(g).area for k, g in after.items() if k != zone and after[zone].intersects(g)}
            ov = {k: round(a, 2) for k, a in ov.items() if a > 0.01}
            print('  %-10s overlap with other zones %s' % (zone, ov))
            assert all(a < 50.0 for a in ov.values()), ('merged zone overlaps another zone', zone, ov)
        left = G.difference(unary_union([v[1] for v in new.values()]))
        print('  gap left uncovered: %.0f units2 (coastal slivers)' % left.area)
        assert left.area < 0.01 * G.area, ('gap not covered', left.area)
        for k, g in land.items():
            if g.intersects(B) and g.area > 50000.0:
                cov = max(v[1].intersection(g).area for v in new.values()) / g.area
                assert cov < 0.25, ('a zone covers too much of', k, round(cov, 2))
        for zone, (pts, P, t_land, on_land) in new.items():
            rec = S[zone]
            rec['poly'] = pts
            for k in t_land:
                if k not in rec['coastal_land']:
                    rec['coastal_land'].append(k)
            sea_area = P.area - on_land
            rec['cells'] = int(round(sea_area / 1600.0))       # (informational: 40-unit grid cells, as sea_zones.py)
            rec['area_units2'] = int(round(sea_area))
            rec['simple'] = True
            note = ('Part of the Bass Strait gap merged in by tools/art/sea/fill_gaps.py (2026-10-23): sea_zones.py had '
                    'dropped that piece of the Tasman Sea, leaving it without any zone.')
            if note not in rec.get('note', ''):
                rec['note'] = (rec.get('note', '') + ' ' + note).strip()
        changed = True
        if not apply:
            preview(spec, new, G, zones, land, pieces, bb)
    if changed and apply:
        dump(S, SEA)
        dump(S, SEA_COPY)
        print('wrote', SEA, 'and', SEA_COPY)
    elif changed:
        print('dry run: nothing written (use --apply)')


def preview(spec, new, G, zones, land, pieces, bb):
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = bb
    s = 8.0
    im = Image.new('RGB', (int((x1 - x0) / s), int((z1 - z0) / s)), (40, 60, 90))
    d = ImageDraw.Draw(im)
    tp = lambda g: [((x - x0) / s, (z1 - z) / s) for x, z in g.exterior.coords]
    for g in land.values():
        if g.intersects(box(*bb)) and g.geom_type == 'Polygon':
            d.polygon(tp(g), fill=(170, 150, 120))
    for g in pieces:
        if g.intersects(box(*bb)) and g.geom_type == 'Polygon':
            d.polygon(tp(g), fill=(150, 170, 120))
    d.polygon(tp(G), outline=(255, 60, 60))
    for k, g in zones.items():
        if g.intersects(box(*bb)):
            d.line(tp(g), fill=(255, 255, 0), width=1)
    for col, (zone, v) in zip([(0, 255, 255), (255, 0, 255), (255, 255, 255)], new.items()):
        d.line(tp(v[1]), fill=col, width=2)
    out = os.path.join(BUILD, 'map6_audit')
    os.makedirs(out, exist_ok=True)
    im.save(os.path.join(out, 'fill_gaps_%s.png' % '_'.join(new)))


if __name__ == '__main__':
    main('--apply' in sys.argv)

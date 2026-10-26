"""Carry design.py's natural lines into coastfit.py's base snapshots (build/coastfit/base_*.json).

Why (2026-10-23, ig-map-engineer): coastfit.py fits from its pre-fit base snapshots only while the current files are
its own output (state.json hash).  After design.py changes lines in the (fitted) current files the hash differs and
coastfit re-fits the fitted files: not idempotent (+19k units2 of growth, then "cannot carry the coast fit over to
world_provinces_orig.json: hejaz").  This script applies design.WORLD_JOBS + STYLED_JOBS and EXT_RUNS to the base
snapshots too (end points snapped to the base polygon's own vertex: the coast fit moves coast ends a few units), puts
the STYLED_JOBS provinces / the touched 2005 pieces into the pre-design base snapshots (styled2 draws those lines), and
sets state.json's hash to the current files, so coastfit stays in base mode.

Recipe after editing a line in design.py (see .claude/knowledge/ig-map-engineer.md "Natural borders"):
    cd tools/art/oldarea && python design.py          (writes build/oldarea/*_fixed.json, keeps snapshots in step)
    copy build/oldarea/world_provinces_fixed.json -> build/world_provinces.json,
         build/oldarea/extensions_fixed.json      -> build/extend/extensions.json
    python tools/art/oldarea/rebase_coastfit.py
    python tools/art/islands/coastfit.py --apply      (twice: the second run must reproduce the files)
    python tools/art/styled_edges.py                  (STYLED_JOBS only) + re-render the touched styled2 tiles
    cd tools/art/oldarea && python render_borders.py
"""
import os, sys, json, math, copy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'islands'))
CF = os.path.join(ROOT, 'build', 'coastfit')


def load(p):
    return json.load(open(p, encoding='utf8'))


def snap_line(poly, line, reach=8.0):
    ia = min(range(len(poly)), key=lambda i: math.hypot(poly[i][0] - line[0][0], poly[i][1] - line[0][1]))
    ib = min(range(len(poly)), key=lambda i: math.hypot(poly[i][0] - line[-1][0], poly[i][1] - line[-1][1]))
    assert math.hypot(poly[ia][0] - line[0][0], poly[ia][1] - line[0][1]) < reach, ('start not on the polygon', line[0])
    assert math.hypot(poly[ib][0] - line[-1][0], poly[ib][1] - line[-1][1]) < reach, ('end not on the polygon', line[-1])
    return [tuple(poly[ia])] + [tuple(q) for q in line[1:-1]] + [tuple(poly[ib])]


def main():
    import design as D
    import coastfit as CFT
    Wb, Eb = load(os.path.join(CF, 'base_world_provinces.json')), load(os.path.join(CF, 'base_extensions.json'))
    Wo, Eo = load(os.path.join(CF, 'base_world_provinces_orig.json')), load(os.path.join(CF, 'base_extensions_orig.json'))
    for key, line in D.WORLD_JOBS + D.STYLED_JOBS:
        poly = [tuple(p) for p in Wb[key]['poly']]
        if D._has_run(poly, line):
            continue
        ln = snap_line(poly, line)
        new = D.geo.ccw(D.replace_edge_run(poly, ln[0], ln[-1], ln, tol=0.01))
        print('base %-8s %d -> %d vertices' % (key, len(poly), len(new)))
        Wb[key]['poly'] = [list(p) for p in new]
    Eb = D.fix_extension_runs(copy.deepcopy(Eb))
    for key, _ in D.STYLED_JOBS:
        Wo[key] = dict(Wo[key], poly=Wb[key]['poly'])
    for name in {n for n, *_ in D.EXT_RUNS if n not in D.C.NAMES.values()}:
        Eo[name] = Eb[name]
    json.dump(Wb, open(os.path.join(CF, 'base_world_provinces.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    json.dump(Eb, open(os.path.join(CF, 'base_extensions.json'), 'w', encoding='utf8'), indent=0)
    json.dump(Wo, open(os.path.join(CF, 'base_world_provinces_orig.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    json.dump(Eo, open(os.path.join(CF, 'base_extensions_orig.json'), 'w', encoding='utf8'), indent=0)
    Wc = load(os.path.join(ROOT, 'build', 'world_provinces.json'))
    Ec = load(os.path.join(ROOT, 'build', 'extend', 'extensions.json'))
    st = load(os.path.join(CF, 'state.json'))
    st['out_hash'] = CFT.digest(Wc, Ec)
    st['note'] = 'base snapshots carry design.py lines (tools/art/oldarea/rebase_coastfit.py); hash = current files'
    json.dump(st, open(os.path.join(CF, 'state.json'), 'w'), indent=1)
    print('base snapshots + state.json written; now run coastfit.py --apply (twice)')


if __name__ == '__main__':
    main()

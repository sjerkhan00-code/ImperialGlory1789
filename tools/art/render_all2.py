"""Render every extended-map tile with styled2 (cols 0..8, rows 0..6 from the top) into build/art/tiles/,
then build the downscaled 9x7 preview build/art/preview_9x7.png.

    python tools/art/render_all2.py [--force] [--edges <province polygons .json>] [--only c,r c,r ...]

--edges: the province polygons the borders are drawn from (styled.EDGES_JSON; default build/world_provinces.json, the
current polygons).  build/tiles_new was rendered from the pre-design, pre-coast-fit polygons, since 2026-10-23 kept in
build/art/styled2_edges.json (tools/art/styled_edges.py: the former build/coastfit/base_world_provinces_orig.json, which
coastfit.py may replace, plus design.STYLED_JOBS and densified long edges; verified 2026-10-23: re-renders of tiles
1_3 2_3 1_4 2_4 6_6 with it reproduce the stored tiles byte for byte), and the old-area pipeline (deframe -> northfix ->
render_borders) expects exactly that art, so use
    python tools/art/render_all2.py --force --edges build/art/styled2_edges.json
after a change of the coast / texture code.  Then copy build/art/tiles/*.png to build/tiles_new/ and rerun deframe.py,
oldarea/northfix.py and oldarea/render_borders.py (NOT design.py), then islands/coastfit.py --apply.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import styled2
from styled2 import styled
from PIL import Image
if '--edges' in sys.argv:
    styled.EDGES_JSON = os.path.abspath(sys.argv[sys.argv.index('--edges') + 1])
    print('borders from', styled.EDGES_JSON, flush=True)
OUT = os.path.join(styled2.ROOT, 'build', 'art', 'tiles')
os.makedirs(OUT, exist_ok=True)
only = [tuple(int(v) for v in a.split(',')) for a in sys.argv[sys.argv.index('--only') + 1:] if ',' in a] if '--only' in sys.argv else None
t0 = time.time()
for row in range(7):
    for col in range(9):
        if col <= 2 and row <= 2:
            continue                                  # untouched original tiles
        if only is not None and (col, row) not in only:
            continue
        p = os.path.join(OUT, 'tile_%d_%d.png' % (col, row))
        if os.path.exists(p) and '--force' not in sys.argv:
            continue
        Image.fromarray(styled2.render_tile(col, row)).save(p)
        print('tile', col, row, '%.0fs' % (time.time() - t0), flush=True)
# preview mosaic, 256 px per tile
S = 256
mos = Image.new('RGB', (9 * S, 7 * S))
for row in range(7):
    for col in range(9):
        if col <= 2 and row <= 2:
            p = os.path.join(styled2.texlib.TILES, 'T00%d00%d.png' % (3 - row, col))
        else:
            p = os.path.join(OUT, 'tile_%d_%d.png' % (col, row))
        if os.path.exists(p):
            mos.paste(Image.open(p).convert('RGB').resize((S, S), Image.LANCZOS), (col * S, row * S))
mos.save(os.path.join(styled2.ROOT, 'build', 'art', 'preview_9x7.png'))
print('done %.0fs' % (time.time() - t0))

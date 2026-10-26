"""Render every tile of the extended map that differs from the original (cols 0..8, rows 0..6 from the top)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import styled
from PIL import Image
OUT = os.path.join(styled.ROOT, 'build', 'tiles_new')
os.makedirs(OUT, exist_ok=True)
t0 = time.time()
for row in range(7):
    for col in range(9):
        if col <= 2 and row <= 2:
            continue                                  # untouched original tiles
        p = os.path.join(OUT, 'tile_%d_%d.png' % (col, row))
        if os.path.exists(p) and '--force' not in sys.argv:
            continue
        Image.fromarray(styled.render_tile(col, row)).save(p)
        print('tile', col, row, '%.0fs' % (time.time() - t0), flush=True)
print('done')

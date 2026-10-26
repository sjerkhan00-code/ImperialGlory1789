"""Texture library cut from the game's own 16 map tiles: clean sea, plain parchment land and mountain land patches.
Patches are 128 px squares at full tile resolution (1024 px per tile)."""
import os
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES = os.path.join(ROOT, 'build', 'tiles_png')
P = 128

# usable art inside the old frame, per tile (x0, y0, x1, y1) in tile px; rows counted from the south (T00RR0CC)
def _inner(r, c):
    x0 = 200 if c == 0 else 0
    x1 = 840 if c == 3 else 1024
    y0 = 140 if r == 3 else 0
    y1 = 760 if r == 0 else 1024
    return x0, y0, x1, y1


def build():
    sea, plain, mount = [], [], []
    for r in range(4):
        for c in range(4):
            im = np.asarray(Image.open(os.path.join(TILES, 'T00%d00%d.png' % (r, c)))).astype(np.float32)
            x0, y0, x1, y1 = _inner(r, c)
            for y in range(y0, y1 - P + 1, 48):
                for x in range(x0, x1 - P + 1, 48):
                    p = im[y:y + P, x:x + P]
                    R, G, B = p[..., 0], p[..., 1], p[..., 2]
                    lum = p.mean(-1)
                    seaf = ((B > R + 8)).mean()
                    landf = ((R > B + 10)).mean()
                    dm = lum < np.median(lum) - 38
                    dark = dm.mean()
                    redf = ((R - G > 32) & (R - B > 32)).mean()
                    if redf > 0.001 or (lum < 60).mean() > 0.0005:
                        continue                                   # red borders, orange coasts, ink blots
                    faint = lum < np.median(lum) - 20                # faint grid lines count as strokes too
                    lab, n = ndimage.label(ndimage.binary_dilation(faint, iterations=1))
                    if n:
                        sl = ndimage.find_objects(lab)
                        if max(max(s[0].stop - s[0].start, s[1].stop - s[1].start) for s in sl) > 70:
                            continue                               # long strokes: grid lines, borders, routes
                    if seaf > 0.99 and dark < 0.02:
                        sea.append(p)
                    elif landf > 0.99 and dark < 0.02:
                        plain.append(p)
                    elif landf > 0.98 and 0.05 < dark < 0.14:
                        mount.append(p)
    return sea, plain, mount


if __name__ == '__main__':
    s, p, m = build()
    print('sea', len(s), 'plain', len(p), 'mountain', len(m))
    for name, lib in (('sea', s), ('plain', p), ('mount', m)):
        if lib:
            n = min(36, len(lib))
            idx = np.linspace(0, len(lib) - 1, n).astype(int)
            sheet = Image.new('RGB', (6 * P, ((n + 5) // 6) * P))
            for k, i in enumerate(idx):
                sheet.paste(Image.fromarray(lib[i].astype(np.uint8)), ((k % 6) * P, (k // 6) * P))
            sheet.save(os.path.join(ROOT, 'build', 'texlib_%s.png' % name))

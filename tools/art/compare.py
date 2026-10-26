"""Full-resolution comparison crops of original art vs styled2 renders (build/art/compare_*.png).

Each sheet: left = a crop of original tiles, right = a crop of the new render at the same scale (1024 px per tile).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import styled2
from PIL import Image, ImageDraw
ROOT = styled2.ROOT
TILES = os.path.join(ROOT, 'build', 'art', 'tiles')


def tile(col, row):
    if col <= 2 and row <= 2:
        return Image.open(os.path.join(styled2.texlib.TILES, 'T00%d00%d.png' % (3 - row, col))).convert('RGB')
    return Image.open(os.path.join(TILES, 'tile_%d_%d.png' % (col, row))).convert('RGB')


def crop(x, y, w, h):
    """Crop of the global 9x7 tile mosaic in global tile px (1024 per tile)."""
    out = Image.new('RGB', (w, h))
    for row in range(y // 1024, (y + h - 1) // 1024 + 1):
        for col in range(x // 1024, (x + w - 1) // 1024 + 1):
            try:
                t = tile(col, row)
            except FileNotFoundError:
                continue
            out.paste(t, (col * 1024 - x, row * 1024 - y))
    return out


def sheet(name, a, b, la, lb):
    w = a.width + b.width + 16
    s = Image.new('RGB', (w, max(a.height, b.height) + 28), (40, 40, 40))
    s.paste(a, (0, 28)); s.paste(b, (a.width + 16, 28))
    d = ImageDraw.Draw(s); d.text((6, 8), la, fill=(255, 255, 255)); d.text((a.width + 22, 8), lb, fill=(255, 255, 255))
    s.save(os.path.join(ROOT, 'build', 'art', 'compare_%s.png' % name))


if __name__ == '__main__':
    # 1. original Balkans/Anatolia coast vs new India west coast
    sheet('coast_india', crop(1024 + 300, 2048 + 200, 700, 700), crop(4096 + 150, 3072 + 150, 700, 700),
          'original: Balkans / Aegean (tile 1,2)', 'new: west India (tile 4,3)')
    # 2. original central Europe provinces vs new Arabia / Persia provinces
    sheet('provinces_arabia', crop(1024 + 200, 1024 + 300, 700, 700), crop(3072 + 150, 2048 + 100, 700, 700),
          'original: central Europe (tile 1,1)', 'new: Persia / Arabia (tile 3,2)')
    # 3. the old/new join in Kazakhstan: one continuous crop across the boundary (old art ends at x 3720)
    j = crop(3072 + 300, 1024 + 150, 900, 700)
    j.save(os.path.join(ROOT, 'build', 'art', 'compare_join_kazakhstan.png'))
    # 4. the join south of the old frame (Africa / Sahara, old art ends at y ~3790)
    j = crop(1024 + 200, 3072 + 300, 900, 700)
    j.save(os.path.join(ROOT, 'build', 'art', 'compare_join_sahara.png'))
    # 5. open sea with ships: original North Sea vs new Indian Ocean
    sheet('sea_ships', crop(1024 + 100, 1024 + 60, 600, 500), crop(5120 + 100, 4096 + 200, 600, 500),
          'original: North Sea (tile 1,1)', 'new: Indian Ocean (tile 5,4)')
    print('ok')

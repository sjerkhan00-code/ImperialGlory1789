"""Shared helpers for the old-area province redesign (tools/art/oldarea).

World <-> composite pixel conversions, the 16 original tiles as one 4096x4096 image, the original province
outlines (from MapaGestionVolumenes.V3D) and the current polygons.  Nothing here writes into tools/, mod/ or data/.
"""
import os, sys, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import meshgen as MG
import render_map as RM

BUILD = os.path.join(ROOT, 'build')
OUT = os.path.join(BUILD, 'oldarea')
TILES = os.path.join(BUILD, 'tiles_png')
DEFRAME = os.path.join(BUILD, 'art', 'deframe')
MAPA = os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Gestion', 'Mapa')
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(OUT, 'tiles'), exist_ok=True)

COLS, ROWS, TILE_W, TILE_H = MG.COLS, MG.ROWS, MG.TILE_W, MG.TILE_H
TS = 1024
# extent of the hand-painted art (inside the sheet's neatline), world units
OLD_X0, OLD_X1, OLD_Z0, OLD_Z1 = 473.0, 20192.0, -970.0, 12506.0

NAMES = {1: 'SaharaOccidental', 2: 'Tuat', 3: 'Arabia', 4: 'Oman', 5: 'Persia', 6: 'Khorasan', 7: 'Turkestan',
         8: 'Kazakhstan', 9: 'Ural', 10: 'Siberia', 11: 'Chechenya'}
_c = {}


def w2p(x, z):
    """world (x, z) -> composite px (col, row), 1024 px per tile, row 0 at the north edge."""
    return (x - COLS[0]) / TILE_W * TS, (ROWS[4] - z) / TILE_H * TS


def p2w(px, py):
    return COLS[0] + px / TS * TILE_W, ROWS[4] - py / TS * TILE_H


def poly_px(poly):
    return [w2p(x, z) for x, z in poly]


def comp(deframed=False):
    """The 16 tiles as one 4096x4096 uint8 RGB array (deframed=True: build/art/deframe tiles)."""
    key = 'comp_d' if deframed else 'comp'
    if key not in _c:
        img = np.zeros((4 * TS, 4 * TS, 3), np.uint8)
        for r in range(4):          # r = row from the top
            for c in range(4):
                if deframed:
                    p = os.path.join(DEFRAME, 'tile_%d_%d.png' % (c, r))
                else:
                    p = os.path.join(TILES, 'T00%d00%d.png' % (3 - r, c))
                img[r * TS:(r + 1) * TS, c * TS:(c + 1) * TS] = np.asarray(Image.open(p).convert('RGB'))
        _c[key] = img
    return _c[key]


def outlines():
    """Original province outlines: name -> list of ((x, z), (x, z)) edges (world)."""
    if 'outl' not in _c:
        _c['outl'] = RM.province_outlines(os.path.join(MAPA, 'MapaGestionVolumenes.V3D'))
    return _c['outl']


def current_polys():
    d = {int(k): [tuple(p) for p in v] for k, v in json.load(open(os.path.join(BUILD, 'forslag_former.json'))).items()}
    d[11] = [tuple(p) for p in json.load(open(os.path.join(BUILD, 'chechnya_poly.json')))]
    return d


def extensions():
    return json.load(open(os.path.join(BUILD, 'extend', 'extensions.json'), encoding='utf8'))


def font(size=14):
    for p in (r'C:\Windows\Fonts\arial.ttf', r'C:\Windows\Fonts\DejaVuSans.ttf'):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def crop_view(x0, x1, z0, z1, scale=1.0, polys=None, show_outlines=True, grid=1000, deframed=False, labels=True,
              extra=None, poly_colour=(255, 0, 0)):
    """Render a world-rectangle crop of the composite with the original outlines (yellow), polys (red) and a grid.
    polys: {pid: polygon}.  extra: list of (polygon, colour).  Returns a PIL image."""
    px0, py0 = w2p(x0, z1); px1, py1 = w2p(x1, z0)
    px0, py0, px1, py1 = int(px0), int(py0), int(px1), int(py1)
    im = Image.fromarray(comp(deframed)[max(py0, 0):py1, max(px0, 0):px1]).convert('RGB')
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = font(13)

    def P(x, z):
        a, b = w2p(x, z)
        return ((a - px0) * scale, (b - py0) * scale)
    if grid:
        for gx in range(int(x0 // grid) * grid, int(x1) + grid, grid):
            a, _ = P(gx, 0)
            d.line([(a, 0), (a, im.height)], fill=(255, 255, 255), width=1)
            d.text((a + 2, 2), str(gx), fill=(255, 255, 0), font=f)
        for gz in range(int(z0 // grid) * grid, int(z1) + grid, grid):
            _, b = P(0, gz)
            d.line([(0, b), (im.width, b)], fill=(255, 255, 255), width=1)
            d.text((2, b + 2), str(gz), fill=(255, 255, 0), font=f)
    if show_outlines:
        for name, edges in outlines().items():
            pts = []
            for a, b in edges:
                if (x0 - 500 <= a[0] <= x1 + 500) and (z0 - 500 <= a[1] <= z1 + 500):
                    d.line([P(*a), P(*b)], fill=(255, 220, 0), width=2)
                    pts.append(a)
            if labels and pts:
                cx = sum(p[0] for p in pts) / len(pts); cz = sum(p[1] for p in pts) / len(pts)
                if x0 <= cx <= x1 and z0 <= cz <= z1:
                    d.text(P(cx, cz), name, fill=(255, 255, 255), font=f)
    if polys:
        for pid, poly in polys.items():
            pts = [P(*q) for q in poly]
            d.line(pts + pts[:1], fill=poly_colour, width=2)
            if labels:
                cx = sum(q[0] for q in poly) / len(poly); cz = sum(q[1] for q in poly) / len(poly)
                d.text(P(cx, cz), NAMES.get(pid, str(pid)), fill=poly_colour, font=f)
    for poly, col in (extra or []):
        pts = [P(*q) for q in poly]
        d.line(pts + pts[:1], fill=col, width=2)
    return im

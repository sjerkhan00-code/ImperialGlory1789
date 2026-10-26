"""Paint the extended campaign map (9 x 7 tiles) in the game's own style.

Inside the old map frame the game's original art is kept. Outside it, land and sea come from the user's prototype
picture, warped onto the game's geography (warp.py), and are painted with the game's measured colours, the game's
parchment grain (Detalle2.tga) and the game's coast treatment (dark water edge, dark ink line, orange-brown band).

Coordinates: "g" = pixels of the 2048 px composite of the original 16 tiles (512 px per tile, north up, origin at
the top-left corner of tile column 0 / top row). The extended map spans g x 0..4608 (9 columns) and g y 0..3584
(7 rows: the 4 original rows and 3 new rows to the south).
"""
import sys, os
import numpy as np
from PIL import Image, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warp, dds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LON0, LAT1, RES = -40.0, 82.0, 0.04       # build/land_lonlat.png (rasterize_land.py)
COL0, COLS, ROWS = -1, 9, 7          # tile columns -1..7, rows 0..6 counted from the top
SEA = np.array([133.0, 154.0, 164.0])      # median of the game's sea / mean grain (0.92)
LAND = np.array([184.0, 173.0, 152.0])     # median of the game's land / mean grain
COAST_LINE = np.array([82.0, 74.0, 62.0])
COAST_BAND = np.array([130.0, 97.0, 59.0])
SEA_EDGE = np.array([86.0, 105.0, 110.0])
OLD_X1, OLD_Y1 = 1955.0, 1925.0          # inner edge of the old frame (right, bottom), g px
# prototype pixels (x, y, radius) of things that are not land: ships, compass roses, the dark ovals
SHIPS_AND_ORNAMENTS = [(548, 62, 42), (298, 148, 22), (266, 276, 32), (145, 418, 40), (132, 632, 42), (240, 1085, 48),
                       (1040, 965, 42), (1885, 437, 34), (1855, 640, 38), (130, 170, 95), (1975, 60, 45), (45, 1225, 50),
                       (1950, 1255, 60)]


def blur(a, r):
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r))).astype(float) / 255


def load():
    game = np.asarray(Image.open(os.path.join(ROOT, 'build', 'game_map_2048.png')).convert('RGB')).astype(float)
    proto = Image.open(os.path.join(ROOT, 'build', 'prototype.png')).convert('RGB')
    from PIL import ImageDraw
    dr = ImageDraw.Draw(proto)
    sea = (88, 104, 120)
    for (cx, cy, r) in SHIPS_AND_ORNAMENTS:                               # ships, compass roses and dark ovals -> sea
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=sea)
    proto = proto.crop((14, 14, proto.width - 14, proto.height - 14))   # drop the picture's own frame
    proto = proto.resize((proto.width + 28, proto.height + 28))
    p = np.asarray(proto.filter(ImageFilter.GaussianBlur(1.2))).astype(float)
    landim = Image.open(os.path.join(ROOT, 'build', 'land_lonlat.png')).filter(ImageFilter.GaussianBlur(1.0))
    land = np.asarray(landim).astype(float) / 255
    lum = p.mean(-1)
    detail = np.clip((blur(lum / 255, 3) * 255 - lum) / 40.0, 0, 1)       # dark ink strokes (mountains, rivers)
    red = (p[..., 0] - p[..., 1] > 38) & (p[..., 0] > 120)               # the prototype's red province borders
    detail[red] = 0
    w, h, rows = dds.read_dds(os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Gestion', 'Mapa', 'Detalle2.tga'))
    g = np.array([[(r[i * 4] * 3 + r[i * 4 + 1] * 6 + r[i * 4 + 2]) / 10 for i in range(w)] for r in rows[::2]])[:, ::2]
    grain = 0.84 + 0.16 * (g - g.min()) / (g.max() - g.min())
    return game, land, detail, grain


def sample(img, x, y):
    """Bilinear sample of a 2D array at float pixel coordinates."""
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001); y = np.clip(y, 0, h - 1.001)
    x0 = x.astype(int); y0 = y.astype(int); fx = x - x0; fy = y - y0
    if img.ndim == 3:
        fx = fx[..., None]; fy = fy[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def render(scale, x0=COL0 * 512, y0=0, w=None, h=None, seed=1):
    """Render g-rect (x0, y0, w, h) at `scale` output px per g px. Returns an RGB uint8 array."""
    game, land, detail, grain = load()
    w = w or COLS * 512; h = h or ROWS * 512
    W, H = int(w * scale), int(h * scale)
    ys, xs = np.mgrid[0:H, 0:W]
    gx = x0 + (xs + 0.5) / scale; gy = y0 + (ys + 0.5) / scale
    t = warp.game_to_lonlat()
    q = np.empty((H * W, 2)); ll = np.empty((H * W, 2))
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    for i in range(0, len(pts), 200000):
        q[i:i + 200000], ll[i:i + 200000] = t(pts[i:i + 200000])
    px = q[:, 0].reshape(H, W); py = q[:, 1].reshape(H, W)
    lon = ll[:, 0].reshape(H, W); lat = ll[:, 1].reshape(H, W)
    L = sample(land, (lon - LON0) / RES, (LAT1 - lat) / RES)
    L[(lon > 189.5) | (lon < LON0 + 0.5) | (lat < -55)] = 0
    m = 40
    inproto = (px >= m) & (py >= m) & (px <= 2000 - m) & (py <= 1325 - m)
    rng = np.random.default_rng(seed)
    noise = blur(rng.random((H, W)), 2.5 * scale)
    hard = (L + (noise - 0.5) * 0.18 > 0.5).astype(float)                  # crisp coast with a hand-drawn wobble
    k = 4.0 * scale                                                        # coast widths follow the game (in g px)
    inner = blur(hard, k)                                                  # <1 near the coast on land
    outer = blur(hard, 2.2 * k)
    gr = sample(grain, (gx * 1.0) % grain.shape[1], (gy * 1.0) % grain.shape[0])
    stain = blur(rng.random((H, W)), 30 * scale)
    stain = (stain - stain.min()) / (stain.max() - stain.min() + 1e-6)
    stain = np.where(L > 0.5, 0.84 + 0.30 * stain, 0.94 + 0.12 * stain)   # the game's land has strong stains
    out = np.where(hard[..., None] > 0.5, LAND, SEA) * (gr * stain)[..., None]
    band = np.clip((1 - inner) * 2.2, 0, 1) * hard                        # land side of the coast
    out = out * (1 - band[..., None] * 0.85) + COAST_BAND * band[..., None] * 0.85
    edge = np.clip(outer * 1.6, 0, 1) * (1 - hard)                        # sea side of the coast
    out = out * (1 - edge[..., None] * 0.6) + SEA_EDGE * edge[..., None] * 0.6
    line = np.clip(1 - np.abs(blur(hard, 0.8 * scale) - 0.5) * 4, 0, 1)   # thin ink line on the coast
    out = out * (1 - line[..., None]) + COAST_LINE * line[..., None]
    ink = sample(detail, px, py) * hard * inproto
    out = out * (1 - ink[..., None] * 0.55) + np.array([70.0, 58.0, 44.0]) * ink[..., None] * 0.55
    # keep the game's own art inside the old frame, blending over the old frame line
    gxm = np.clip((OLD_X1 - gx) / 30.0, 0, 1); gym = np.clip((OLD_Y1 - gy) / 30.0, 0, 1)
    keep = (gxm * gym) * ((gx >= 0) & (gx < 2048) & (gy < 2048))
    orig = sample(game, np.clip(gx, 0, 2047), np.clip(gy, 0, 2047))
    out = orig * keep[..., None] + out * (1 - keep[..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


if __name__ == '__main__':
    img = render(0.25, x0=0, w=9 * 512, h=7 * 512)
    Image.fromarray(img).save(os.path.join(ROOT, 'build', 'world_preview.png'))
    print('preview', img.shape)

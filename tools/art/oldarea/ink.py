"""Draw province borders into the old-map tiles in the original hand-painted style.

Measured on the original tiles (tools/art/oldarea, see report): the border is a solid red-brown ink line
(core (108, 66, 50), ~5 px at 1024 px per tile) and every province carries a dark 'pillow' rim inside its border
(luminance -45..-50 at 4 px from the line, decaying over ~40 px; styled2._rim has the fitted profile).

API: Canvas(deframed=True) wraps the 4096x4096 composite of the old tiles (rows 0-3, cols 0-3); draw_ink(lines)
adds ink along world-coordinate polylines; draw_rim(poly, lines) shades the inside of world polygon `poly` near
the polylines `lines`; save(tiles_dir, changed_only=True) writes tile_<c>_<r>.png for the tiles that changed.
"""
import os, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import common as C

INK = np.array([124.0, 74.0, 62.0])
TS = C.TS


def rim_profile(d):
    """Darkening fraction at d px from the border line (styled2._rim scaled to the measured old-art profile)."""
    return 0.75 * (0.31 * np.exp(-np.maximum(d - 4, 0) / 12.0) + 0.08 * np.exp(-np.maximum(d - 4, 0) / 40.0))


class Canvas:
    def __init__(self, base=None, deframed=True):
        self.img = (base if base is not None else C.comp(deframed)).astype(np.float32).copy()
        self.touched = np.zeros((4, 4), bool)
        self.changed = np.zeros(self.img.shape[:2], bool)

    def _window(self, pts_px, margin):
        xs = [p[0] for p in pts_px]; ys = [p[1] for p in pts_px]
        x0 = max(0, int(min(xs) - margin)); x1 = min(4 * TS, int(max(xs) + margin) + 1)
        y0 = max(0, int(min(ys) - margin)); y1 = min(4 * TS, int(max(ys) + margin) + 1)
        return x0, y0, x1, y1

    def _mark(self, x0, y0, x1, y1, mask):
        self.changed[y0:y1, x0:x1] |= mask > 0.002
        for r in range(y0 // TS, (y1 - 1) // TS + 1):
            for c in range(x0 // TS, (x1 - 1) // TS + 1):
                sub = mask[max(r * TS - y0, 0):(r + 1) * TS - y0, max(c * TS - x0, 0):(c + 1) * TS - x0]
                if sub.size and sub.max() > 0.002:
                    self.touched[r, c] = True

    def line_mask(self, lines, x0, y0, x1, y1, width=5):
        """Antialiased ink mask (0..1) of world polylines in the window."""
        im = Image.new('L', ((x1 - x0) * 2, (y1 - y0) * 2), 0)
        d = ImageDraw.Draw(im)
        for ln in lines:
            pts = [((px - x0) * 2, (py - y0) * 2) for px, py in C.poly_px(ln)]
            if len(pts) >= 2:
                d.line(pts, fill=255, width=width * 2, joint='curve')
                for p in pts[1:-1]:
                    d.ellipse([p[0] - width, p[1] - width, p[0] + width, p[1] + width], fill=255)
        m = np.asarray(im, np.float32) / 255.0
        m = m.reshape(y1 - y0, 2, x1 - x0, 2).mean((1, 3))
        return np.clip(ndimage.gaussian_filter(m, 0.7) * 1.1, 0, 1)

    def draw_ink(self, lines, width=5, strength=0.88):
        if not lines:
            return
        pts = [p for ln in lines for p in C.poly_px(ln)]
        x0, y0, x1, y1 = self._window(pts, 16)
        m = self.line_mask(lines, x0, y0, x1, y1, width)
        reg = self.img[y0:y1, x0:x1]
        a = (strength * m)[..., None]
        # the ink is darker than anything under it: multiply-like, keeps the parchment grain faintly
        tone = INK * (0.8 + 0.2 * np.clip(reg / 160.0, 0, 1.3))     # keeps a little of the parchment grain
        self.img[y0:y1, x0:x1] = reg * (1 - a) + tone * a
        self._mark(x0, y0, x1, y1, m)

    def draw_rim(self, poly, lines, strength=1.0):
        """Pillow shading inside world polygon `poly` from the world polylines `lines` (its border)."""
        if not lines:
            return
        pts = C.poly_px(poly)
        x0, y0, x1, y1 = self._window(pts, 60)
        im = Image.new('L', (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(im).polygon([(px - x0, py - y0) for px, py in pts], fill=255)
        inside = np.asarray(im, np.float32) / 255.0
        ln = Image.new('L', (x1 - x0, y1 - y0), 0)
        d = ImageDraw.Draw(ln)
        for l in lines:
            p = [(px - x0, py - y0) for px, py in C.poly_px(l)]
            if len(p) >= 2:
                d.line(p, fill=255, width=1)
        lm = np.asarray(ln) > 0
        if not lm.any():
            return
        dist = ndimage.distance_transform_edt(~lm)
        rim = rim_profile(dist) * inside * strength
        reg = self.img[y0:y1, x0:x1]
        self.img[y0:y1, x0:x1] = reg * (1 - rim[..., None] * np.array([1.0, 1.08, 1.2]))
        self._mark(x0, y0, x1, y1, rim)

    def tile(self, col, row):
        return np.clip(self.img[row * TS:(row + 1) * TS, col * TS:(col + 1) * TS], 0, 255).astype(np.uint8)

    def save(self, out_dir, changed_only=True):
        os.makedirs(out_dir, exist_ok=True)
        written = []
        for r in range(4):
            for c in range(4):
                if changed_only and not self.touched[r, c]:
                    continue
                p = os.path.join(out_dir, 'tile_%d_%d.png' % (c, r))
                Image.fromarray(self.tile(c, r)).save(p)
                written.append(p)
        return written

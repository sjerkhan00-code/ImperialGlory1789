"""Fill a masked area of the old-map composite with plausible art: the surrounding art's broad colour per class
(land / sea) plus real parchment / sea grain quilted from clean patches of the original tiles, and the mid-scale
mottle.  Used to erase painted borders that moved (render_borders.py) in the synthetic margins, where the original
tile cannot be restored.
"""
import os, sys
import numpy as np
from scipy import ndimage
import common as C
sys.path.insert(0, os.path.join(C.TOOLS, 'art'))
import deframe as DF
from northfix import clean_patches

_c = {}


def _libs():
    """Clean high-pass patches of the original art (inside the neatline), per class."""
    if 'libs' not in _c:
        O = C.comp(False).astype(np.float32)
        sea = DF.sea_class(O)
        ys, xs = np.mgrid[0:O.shape[0], 0:O.shape[1]]
        inside = (xs >= 300) & (xs < 3800) & (ys >= 400) & (ys < 3700)
        land = clean_patches(O, inside & ~sea, step=96)
        seal = clean_patches(O, inside & sea, step=96)
        sea_lib, land_lib = DF._lib()
        _c['libs'] = (land if len(land) >= 8 else land_lib, seal if len(seal) >= 8 else sea_lib)
        # grain amplitude of the real art
        hp = O - ndimage.gaussian_filter(O, (10, 10, 0))
        lum = O.mean(-1)
        plain = lum > ndimage.median_filter(lum, 21) - 12
        _c['amp'] = {cls: 1.4826 * np.median(np.abs(hp[inside & m & plain]), 0) for cls, m in (('land', ~sea), ('sea', sea))}
        bp = ndimage.gaussian_filter(O, (11, 11, 0)) - ndimage.gaussian_filter(O, (45, 45, 0))
        _c['mamp'] = np.array([bp[..., k][inside].std() for k in range(3)], np.float32)
    return _c['libs']


def fill(img, mask, feather=3.0, libs=None):
    """img: HxWx3 float composite (modified in place); mask: bool HxW of pixels to re-synthesise.
    libs: optional (land, sea) high-pass patch lists to quilt from instead of the default ones."""
    if not mask.any():
        return img
    land_lib, sea_lib = _libs()
    if libs is not None:
        land_lib, sea_lib = libs
    ys, xs = np.nonzero(mask)
    y0, y1 = max(ys.min() - 160, 0), min(ys.max() + 161, img.shape[0]); x0, x1 = max(xs.min() - 160, 0), min(xs.max() + 161, img.shape[1])
    win = img[y0:y1, x0:x1]; m = mask[y0:y1, x0:x1]
    sea = DF.sea_class(win)
    # class of the masked pixels: nearest unmasked pixel's class
    idx = ndimage.distance_transform_edt(m, return_distances=False, return_indices=True)
    cls_sea = sea[idx[0], idx[1]]
    keep = ~m
    def lp(w, sigma=24):
        wf = ndimage.gaussian_filter(w.astype(np.float32), sigma)
        v = np.stack([ndimage.gaussian_filter(win[..., k] * w, sigma) for k in range(3)], -1) / np.maximum(wf, 1e-3)[..., None]
        wf2 = ndimage.gaussian_filter(w.astype(np.float32), sigma * 4)
        v2 = np.stack([ndimage.gaussian_filter(win[..., k] * w, sigma * 4) for k in range(3)], -1) / np.maximum(wf2, 1e-3)[..., None]
        t = np.clip(wf / 0.2, 0, 1)[..., None]
        return v * t + v2 * (1 - t)
    base = np.where(cls_sea[..., None], lp(keep & sea), lp(keep & ~sea))
    h, w = m.shape
    n = max(h, w)
    tl = DF.quilt(x0, y0, n, land_lib, 41)[:h, :w]; ts = DF.quilt(x0, y0, n, sea_lib, 42)[:h, :w]
    for t, cls in ((tl, 'land'), (ts, 'sea')):
        a = 1.4826 * np.median(np.abs(t), (0, 1)) + 1e-3
        t *= _c['amp'][cls] / a
    tex = np.where(cls_sea[..., None], ts, tl)
    mott = DF.mottle(x0, y0, n)[:h, :w][..., None] * _c['mamp'] * 0.5
    new = base + tex + mott
    a = ndimage.gaussian_filter(m.astype(np.float32), feather)[..., None]
    img[y0:y1, x0:x1] = win * (1 - a) + new * a
    return img

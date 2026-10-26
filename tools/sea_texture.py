"""Seamless 512 px sea detail (high-pass) made from the game's own sea pixels, long lines removed."""
import os
import numpy as np
from PIL import Image
from scipy import ndimage
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def long_lines(im):
    lum = im.mean(-1)
    dark = lum < ndimage.median_filter(lum, 21) - 14
    lab, n = ndimage.label(dark)
    if not n:
        return np.zeros_like(dark)
    sl = ndimage.find_objects(lab)
    keep = np.zeros(n + 1, bool)
    for k, s in enumerate(sl, 1):
        if max(s[0].stop - s[0].start, s[1].stop - s[1].start) > 40:
            keep[k] = True
    return ndimage.binary_dilation(keep[lab], iterations=4)


def main():
    blocks = []
    for r in range(4):
        for c in range(4):
            im = np.asarray(Image.open(os.path.join(ROOT, 'build', 'tiles_png', 'T00%d00%d.png' % (r, c)))).astype(np.float32)
            R, G, B = im[..., 0], im[..., 1], im[..., 2]
            sea = ndimage.binary_erosion(B > R + 8, iterations=20)
            ok = sea & ~long_lines(im) & ~ndimage.binary_dilation((R - G > 25), iterations=6)
            hp = im - ndimage.gaussian_filter(im, (16, 16, 0))
            frac = ndimage.uniform_filter(ok.astype(np.float32), 96)
            ys, xs = np.nonzero(frac > 0.92)
            for k in range(0, len(ys), 211):
                y, x = ys[k] - 48, xs[k] - 48
                if 0 <= y <= 1024 - 96 and 0 <= x <= 1024 - 96:
                    blocks.append(hp[y:y + 96, x:x + 96] * ok[y:y + 96, x:x + 96, None])
    print('clean sea blocks', len(blocks))
    rng = np.random.default_rng(5)
    S = 512
    out = np.zeros((S, S, 3), np.float32); cnt = np.zeros((S, S), np.float32)
    w = np.outer(np.hanning(96), np.hanning(96)).astype(np.float32) + 1e-3
    for j in range(0, S, 40):
        for i in range(0, S, 40):
            blk = blocks[rng.integers(len(blocks))]
            ys = (np.arange(96) + j) % S; xs = (np.arange(96) + i) % S
            out[np.ix_(ys, xs)] += blk * w[..., None]; cnt[np.ix_(ys, xs)] += w
    det = out / cnt[..., None]
    det *= blocks[0].std() / (det.std() + 1e-6)          # keep the original contrast after averaging
    np.save(os.path.join(ROOT, 'build', 'sea_detail.npy'), det)
    vis = np.clip(det + np.array([122, 142, 151]), 0, 255).astype(np.uint8)
    Image.fromarray(np.tile(vis, (2, 2, 1))).save(os.path.join(ROOT, 'build', 'sea_detail_vis.png'))


if __name__ == '__main__':
    main()

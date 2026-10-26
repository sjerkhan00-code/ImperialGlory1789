"""Remove two leftovers of the original sheet from the old-area composite before the new borders are drawn
(render_borders.py calls both on its base canvas):

  * lift_out_of_play: the original art is painted darker outside the 2005 game's playable provinces (east of Moscu
    and Kursk, around the Caspian, Persia, the Sahara south of the coastal provinces).  Those areas are now inside the
    new provinces, so the step at the old playable edge read as the sheet's straight east edge.  The darkening is
    lifted with a smooth per-channel gain: next to the old edge the out-of-play land is brought to the level of the
    playable land across it, fading out over EDGE_FADE px so it meets the rest of the map without a new step.
  * refill_blots: deframe.py painted the sheet's ink blots / stains out with smooth fills that northfix.py only
    partly re-textured (grey smudges east of the Urals).  Every such fill inside the neatline is re-synthesised with
    fillart.fill (the surrounding art's colour + parchment grain quilted from clean patches of the original tiles).
  * restore_gulf: the 2005 painting of the Persian Gulf / Gulf of Oman at the old SE corner, where deframe's blend into
    the new tiles had put the new tiles' (misplaced) coasts.
"""
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import common as C, geo, fillart
import sys
sys.path.insert(0, os.path.join(C.TOOLS, 'art'))
import deframe as DF

TS = C.TS
EDGE_FADE = 600.0                         # px over which the lift fades out away from the old playable edge
MAX_GAIN = 1.35
NEAT = (192, 266, 3904, 3830)
_c = {}


def play_mask():
    """bool 4096x4096: inside one of the 2005 game's provinces (land or sea)."""
    if 'play' not in _c:
        m = Image.new('L', (4 * TS, 4 * TS), 0)
        d = ImageDraw.Draw(m)
        for G in geo.original_polys().values():
            for g in (G.geoms if G.geom_type == 'MultiPolygon' else [G]):
                d.polygon([tuple(C.w2p(*p)) for p in g.exterior.coords], fill=255)
        _c['play'] = np.asarray(m) > 0
    return _c['play']


def _down(a, f=4):
    h, w = a.shape[:2]
    return a.reshape(h // f, f, w // f, f, *a.shape[2:]).mean((1, 3))


def lift_out_of_play(img):
    """img: 4096x4096x3 float composite, modified in place.  Returns (img, changed bool mask)."""
    F = 4
    play = play_mask()
    sea = geo.sea_mask() | DF.sea_class(img)               # (the painted mask misses the new White Sea strait)
    lum = img.mean(-1)
    plain = lum > ndimage.median_filter(lum[::2, ::2], 11).repeat(2, 0).repeat(2, 1) - 18      # no ink / glyphs
    pl = (play & ~sea & plain).astype(np.float32)
    rl = (~play & ~sea & plain).astype(np.float32)
    # work at 1/4 resolution: everything here is smooth
    imgd = _down(img, F); pld = _down(pl, F); rld = _down(rl, F)
    def lp(w, s):
        den = ndimage.gaussian_filter(w, s)
        return np.stack([ndimage.gaussian_filter(imgd[..., k] * w, s) for k in range(3)], -1) / np.maximum(den, 1e-4)[..., None], den
    # level of the playable land near the old edge, carried into the out-of-play side by nearest-neighbour
    lev_p, den_p = lp(pld, 8)                                      # sigma 32 px
    good = den_p > 0.35
    idx = ndimage.distance_transform_edt(~good, return_distances=False, return_indices=True)
    target = lev_p[idx[0], idx[1]]
    target = np.stack([ndimage.gaussian_filter(target[..., k], 15) for k in range(3)], -1)    # no streaks
    lev_r, den_r = lp(rld, 10)                                     # sigma 40 px
    ratio = np.clip(target / np.maximum(lev_r, 30.0), 1.0, MAX_GAIN)
    ratio = np.where((den_r > 0.05)[..., None], ratio, 1.0)
    # fade with the distance from the playable land, and to 1 at the composite's east / south edges (new tiles)
    dist = ndimage.distance_transform_edt(~(_down(play.astype(np.float32), F) > 0.5)) * F
    w = np.clip(1 - dist / EDGE_FADE, 0, 1) ** 1.3
    n = imgd.shape[0]
    yy, xx = np.mgrid[0:n, 0:n] * F
    w *= np.clip((3990 - xx) / 200.0, 0, 1) * np.clip((3990 - yy) / 200.0, 0, 1)
    g = 1 + (ratio - 1) * w[..., None]
    g = np.stack([ndimage.gaussian_filter(g[..., k], 3) for k in range(3)], -1)
    g = np.stack([ndimage.zoom(g[..., k], F, order=1) for k in range(3)], -1)
    # out-of-play land only (soft at coasts; the playable side keeps its art untouched)
    m = (~play & ~sea).astype(np.float32)
    m = ndimage.gaussian_filter(m, 2.0)
    m[play] = 0.0
    G = 1 + (g - 1) * m[..., None]
    img *= G
    changed = np.abs(G - 1).max(-1) > 0.004
    print('  out-of-play lift: %.0f k px changed, gain up to %.2f' % (changed.sum() / 1000, G.max()))
    return img, changed


def blot_mask():
    """bool 4096x4096: where deframe.py replaced the art inside the neatline (blots, stains), land only."""
    if 'blot' not in _c:
        O = C.comp(False).astype(np.float32); D = C.comp(True).astype(np.float32)
        def lp(a, s=40):
            return ndimage.gaussian_filter(a, (s, s, 0))
        r = lp(D) / np.maximum(lp(O), 1.0)                         # deframe's smooth vignette gain
        diff = np.abs(D - O * r).mean(-1)
        h = ndimage.gaussian_filter(diff, 3) > 14
        ys, xs = np.mgrid[0:4 * TS, 0:4 * TS]
        inside = (xs >= NEAT[0] + 20) & (xs < 3760) & (ys >= NEAT[1] + 8) & (ys < NEAT[3] - 20)
        inside |= (xs >= 3300) & (xs < 3760) & (ys >= 236) & (ys < 300)    # the big blot reached into the top margin
        h &= inside
        # only the east-strip blots / stains (the SW blot and the Sahara ring lie in the margins / are hatched over)
        h &= xs > 3100
        h = ndimage.binary_opening(h, iterations=2)
        lab, n = ndimage.label(h)
        sizes = ndimage.sum(h, lab, range(1, n + 1))
        h = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 300])
        h = ndimage.binary_dilation(h, iterations=8) & inside
        h &= ~geo.sea_mask()
        # deframe.py blends the old art into the new tiles east of x 3600 / south of y 3710 (OLD_X_FULL / OLD_Y_FULL),
        # so there it differs from the original by design (the new tiles' coasts and grain): not a blot.  A real blot
        # is a dark stain in the original; components without one that lie mostly in that band are left as deframe
        # made them (refilling them laid a smooth, coast-less fill over the Gulf's south coast at the old SE corner
        # and a strip of old-art grain down Khorasan's east side, next to the new art).  Only in the sheet's lower half
        # (tile rows 2-3): further north the refill also hides faint ink remnants of the old art in that band
        lo = ndimage.gaussian_filter(O.mean(-1), 4)
        band = (xs >= DF.OLD_X_FULL) | (ys >= DF.OLD_Y_FULL)
        lab, n = ndimage.label(h)
        drop = [k + 1 for k, sl in enumerate(ndimage.find_objects(lab)) if sl[0].start >= 2 * TS
                and (lo[sl][lab[sl] == k + 1] < 60).mean() < 0.02 and band[sl][lab[sl] == k + 1].mean() > 0.3]
        h &= ~np.isin(lab, drop)
        _c['blot'] = h
    return _c['blot']


def _marks(q):
    g = ndimage.gaussian_filter(q.mean(-1), 1.0)
    a = np.clip((-g - 15.0) / 10.0, 0, 1)                          # dark strokes only (the white crackle is grain)
    return ndimage.gaussian_filter(ndimage.grey_dilation(a, size=5), 1.2)


def _suppress_marks(q):
    """Replace the coherent marks of a high-pass patch (faint lettering, graticule / scratch lines, dots) by grain
    from shifted copies of the same patch (per pixel the copy with the fewest marks there)."""
    a = _marks(q)
    best, best_a = q, a
    for sh in ((41, 67), (-53, 29), (83, -37), (-71, -89), (17, 101), (97, 13)):
        r = np.roll(q, sh, (0, 1)); ra = np.roll(a, sh, (0, 1))
        better = ra < best_a
        best = np.where(better[..., None], r, best); best_a = np.minimum(best_a, ra)
    best = ndimage.gaussian_filter(best, (0.6, 0.6, 0)) * 0.3 + best * 0.7       # soften the patchwork seams
    k = np.clip(a / 0.6, 0, 1)[..., None]
    return (q * (1 - k) + best * k).astype(np.float32)


def strict_libs():
    """fillart's patch library (clean high-pass patches of the original tiles) with the marks suppressed: in a big
    blot fill, stray letters, dots and line stubs from the patches read as noise."""
    if 'libs' not in _c:
        land, sea = fillart._libs()
        _c['libs'] = ([_suppress_marks(q) for q in land], [_suppress_marks(q) for q in sea])
    return _c['libs']


def refill_blots(img):
    """Re-synthesise the deframe blot fills (modified in place).  Returns (img, changed bool mask)."""
    m = blot_mask().copy()
    # plus grain-less smears left in the north-east strip by northfix's own fill (not in the deframe difference)
    from northfix import energy
    y0, y1, x0, x1 = 200, 700, 3100, 3600          # (east of 3600 the old art blends into the smoother new art)
    win = img[y0:y1, x0:x1]
    en = energy(win)
    land = ~DF.sea_class(win)
    low = (en < 0.66 * np.median(en[land])) & land
    low = ndimage.binary_opening(low, iterations=2)
    lab, n = ndimage.label(low)
    if n:
        sizes = ndimage.sum(low, lab, range(1, n + 1))
        low = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= 120])
        m[y0:y1, x0:x1] |= ndimage.binary_dilation(low, iterations=6) & land
    if not m.any():
        return img, m
    before = img.copy()
    lab, n = ndimage.label(m)
    for k, sl in enumerate(ndimage.find_objects(lab), 1):           # one window per blot keeps fill() cheap
        fillart.fill(img, lab == k, libs=strict_libs())
    changed = np.abs(img - before).max(-1) > 0.5
    print('  blot fills re-synthesised: %d regions, %.0f k px' % (n, m.sum() / 1000))
    return img, changed


# the Persian Gulf and the Gulf of Oman at the old map's SE corner: world box (x0, x1, z0, z1), west of the old east
# edge, and the world x ranges over which the restored painting fades into the new art there
GULF_SE = (17000.0, 20030.0, -700.0, 1300.0)
GULF_EAST_FADE = (19905.0, 19975.0)        # coasts and land: a short fade, the two coasts meet at the old edge
GULF_WATER_FADE = (19840.0, 20030.0)       # open water (water in both arts): a longer one, up to the painted frame


def _extend(v, good, s):
    """Smooth field v (h, w, k) known where `good`: nearest-neighbour continuation, then a blur of s px."""
    idx = ndimage.distance_transform_edt(~good, return_distances=False, return_indices=True)
    v = v[idx[0], idx[1]]
    return np.stack([ndimage.gaussian_filter(v[..., k], s) for k in range(v.shape[-1])], -1)


def restore_gulf(img):
    """deframe.py blends the old art into the new tiles from x 3600 / y 3710 px on, and at the old map's SE corner that
    band runs through the Persian Gulf, the Musandam peninsula and the Gulf of Oman, where the new tiles' (warped
    Natural Earth) coasts lie up to ~150 units off the painted ones (Oman's province lay 18 % over that water).  The
    old-area provinces (Arabia, Oman, Khorasan) follow the painted coast (design.coast), so the 2005 painting is put
    back there: the painted water plus a 40 px coast band (and wherever the new tiles put water), as original pixels
    times deframe's own smooth gain per class (continued from where deframe kept the original), feathered into the
    deframe art.  Modified in place.  Returns (img, changed bool mask)."""
    F = 4
    x0, z1 = C.w2p(GULF_SE[0], GULF_SE[3]); x1, z0 = C.w2p(GULF_SE[1], GULF_SE[2])
    X0, Y0, X1, Y1 = int(x0), int(z1), int(x1) + 1, min(int(z0) + 1, 4 * TS)
    P = 160                                                   # context around the box (px)
    wx0, wy0, wx1, wy1 = max(X0 - P, 0), max(Y0 - P, 0), min(X1 + P, 4 * TS), min(Y1 + P, 4 * TS)
    wx1 -= (wx1 - wx0) % F; wy1 -= (wy1 - wy0) % F            # whole cells for the 1/F working resolution
    O = C.comp(False)[wy0:wy1, wx0:wx1].astype(np.float32)
    D = C.comp(True)[wy0:wy1, wx0:wx1].astype(np.float32)
    sea_o = geo.sea_mask()[wy0:wy1, wx0:wx1]
    ys, xs = np.mgrid[wy0:wy1, wx0:wx1]
    box = (xs >= X0) & (xs < X1) & (ys >= Y0) & (ys < Y1)
    R = (ndimage.binary_dilation(sea_o, iterations=40) | ndimage.binary_dilation(DF.sea_class(img[wy0:wy1, wx0:wx1]), iterations=30)) & box
    # deframe's gain where it kept the original (west of OLD_X_FULL, north of OLD_Y_FULL), per class, continued
    kept = (xs < DF.OLD_X_FULL - 40) & (ys < DF.OLD_Y_FULL - 30)
    Od, Dd = _down(O, F), _down(D, F)
    lum = O.mean(-1)
    G = {}
    for cls, m in (('sea', sea_o), ('land', ~sea_o)):
        w = (kept & m & (lum > 40)).astype(np.float32)        # no ink lines
        wd = _down(w, F)
        num = np.stack([ndimage.gaussian_filter(Dd[..., k] * wd, 10) for k in range(3)], -1)
        den = np.stack([ndimage.gaussian_filter(Od[..., k] * wd, 10) for k in range(3)], -1)
        cnt = ndimage.gaussian_filter(wd, 10)
        good = cnt > 0.15
        g = np.clip(num / np.maximum(den, 1e-3), 0.7, 1.5)
        g = _extend(g, good, 6)
        G[cls] = np.stack([ndimage.zoom(g[..., k], F, order=1)[:O.shape[0], :O.shape[1]] for k in range(3)], -1)
    cw = ndimage.gaussian_filter(sea_o.astype(np.float32), 1.5)[..., None]
    rest = O * (G['sea'] * cw + G['land'] * (1 - cw))
    wx = (xs + 0.5) / TS * C.TILE_W + C.COLS[0]               # world x of each pixel
    fade = np.clip((GULF_EAST_FADE[1] - wx) / (GULF_EAST_FADE[1] - GULF_EAST_FADE[0]), 0, 1)
    fade_w = np.clip((GULF_WATER_FADE[1] - wx) / (GULF_WATER_FADE[1] - GULF_WATER_FADE[0]), 0, 1)
    sea_d = ndimage.gaussian_filter(DF.sea_class(D).astype(np.float32), 4) > 0.5      # (the new art's hatching is light)
    water = ndimage.binary_erosion(sea_o, iterations=12) & sea_d
    ww = ndimage.gaussian_filter(water.astype(np.float32), 4)
    fade = fade * (1 - ww) + fade_w * ww
    a = (ndimage.gaussian_filter(R.astype(np.float32), 8) * fade)[..., None]
    win = img[wy0:wy1, wx0:wx1]
    img[wy0:wy1, wx0:wx1] = win * (1 - a) + rest * a
    changed = np.zeros(img.shape[:2], bool)
    changed[wy0:wy1, wx0:wx1] = a[..., 0] > 0.004
    print('  SE Gulf painting restored: %.0f k px' % (changed.sum() / 1000))
    return img, changed


def top_seam(img, edge=266, above=(150, 200), below=(300, 340)):
    """Blend the faint seam along the old sheet's top edge (y = 266): the land just inside it still carries a thin
    darker band, and the synthetic land above (now the Arctic strip) is a little darker than the art below.  Per
    column (40 px) the smoothed land profile (6 px vertically, ink excluded) is pulled from the level above the
    seam (rows `above`) to the level below it (rows `below`) across rows above[0] .. edge, flat to below[0], then
    eased back to the art.  Multiplicative: ink, coasts and grain stay.  Land only.  Returns (img, changed)."""
    y0, y1 = above[0] - 20, below[1] + 20
    S = img[y0:y1]
    lum = S.mean(-1)
    land = ~DF.sea_class(S)
    plain = lum > ndimage.median_filter(lum[::2, ::2], 9).repeat(2, 0).repeat(2, 1)[:S.shape[0], :S.shape[1]] - 14
    w = (land & plain).astype(np.float32)
    den = ndimage.gaussian_filter(w, (6, 40))
    P = np.stack([ndimage.gaussian_filter(S[..., k] * w, (6, 40)) for k in range(3)], -1) / np.maximum(den, 1e-3)[..., None]
    ys = np.arange(y0, y1)[:, None]

    def level(r0, r1):
        rows = ((ys >= r0) & (ys < r1)).astype(np.float32)
        wr = den * rows
        return (P * wr[..., None]).sum(0) / np.maximum(wr.sum(0), 1e-3)[..., None], wr.sum(0) / rows.sum()
    lt, ct = level(*above); lb, cb = level(*below)
    lt = np.where((ct > 0.2)[:, None], lt, lb); lb = np.where((cb > 0.2)[:, None], lb, lt)
    f = np.clip((ys - above[0]) / float(edge - above[0]), 0, 1)[..., None]
    D = lt[None] * (1 - f) + lb[None] * f
    g = np.clip(D / np.maximum(P, 20), 0.85, 1.3)
    t = np.clip((ys - above[0]) / 15.0, 0, 1) * np.clip((below[1] - ys) / 30.0, 0, 1)
    xs = np.arange(img.shape[1])[None, :]
    t = t * np.clip((xs - NEAT[0]) / 40.0, 0, 1) * np.clip((NEAT[2] - xs) / 40.0, 0, 1)
    g = np.where((den > 0.08)[..., None], g, 1.0)
    G = 1 + (g - 1) * (t * ndimage.gaussian_filter(land.astype(np.float32), 2))[..., None]
    img[y0:y1] = S * G
    changed = np.zeros(img.shape[:2], bool)
    changed[y0:y1] = np.abs(G - 1).max(-1) > 0.004
    # the neatline's thin dark double line (rows ~248..262) survives the 6 px smoothing: per row (no vertical
    # smoothing, 30 px along the row) pull it onto the line between the rows just above and just below
    b0, b1 = 240, 266
    S2 = img[b0 - 8:b1 + 8]
    lum2 = S2.mean(-1)
    land2 = ~DF.sea_class(S2)
    w2 = (land2 & (lum2 > ndimage.median_filter(lum2, (1, 15)) - 14)).astype(np.float32)
    den2 = ndimage.gaussian_filter1d(w2, 30, axis=1)
    R = np.stack([ndimage.gaussian_filter1d(S2[..., k] * w2, 30, axis=1) for k in range(3)], -1) / np.maximum(den2, 1e-3)[..., None]
    top_l = (R[:8] * den2[:8, :, None]).sum(0) / np.maximum(den2[:8].sum(0), 1e-3)[:, None]
    bot_l = (R[-8:] * den2[-8:, :, None]).sum(0) / np.maximum(den2[-8:].sum(0), 1e-3)[:, None]
    yy = np.arange(S2.shape[0])[:, None, None] / float(S2.shape[0] - 1)
    T = top_l[None] * (1 - yy) + bot_l[None] * yy
    g2 = np.clip(T / np.maximum(R, 20), 0.85, 1.25)
    g2 = np.where((den2 > 0.15)[..., None], g2, 1.0)
    t2 = np.clip(np.minimum(np.arange(S2.shape[0]), S2.shape[0] - 1 - np.arange(S2.shape[0])) / 6.0, 0, 1)[:, None]
    t2 = t2 * np.clip((xs - NEAT[0]) / 40.0, 0, 1) * np.clip((NEAT[2] - xs) / 40.0, 0, 1)
    G2 = 1 + (g2 - 1) * (t2 * ndimage.gaussian_filter(land2.astype(np.float32), 2))[..., None]
    img[b0 - 8:b1 + 8] = S2 * G2
    changed[b0 - 8:b1 + 8] |= np.abs(G2 - 1).max(-1) > 0.004
    # the texture still changes along a straight line (smooth margin fill above, crackled art below): re-synthesise
    # a thin wavy band across it with parchment grain (fillart, mark-free patches), ink strokes and coasts kept
    rng = np.random.default_rng(266)
    W_ = img.shape[1]
    nz = ndimage.gaussian_filter1d(rng.standard_normal(W_), 30); nz /= nz.std()
    nz2 = ndimage.gaussian_filter1d(rng.standard_normal(W_), 18); nz2 /= nz2.std()
    cy = 259.0 + 6.0 * nz; hw = np.clip(8.0 + 3.0 * nz2, 4.0, 13.0)
    by0, by1 = 230, 290
    yy2 = np.arange(by0, by1)[:, None]
    band = np.abs(yy2 - cy[None, :]) < hw[None, :]
    band[:, :NEAT[0] + 30] = False; band[:, 3700:] = False
    Sb = img[by0:by1]
    lumb = Sb.mean(-1)
    inkb = lumb < ndimage.median_filter(lumb, (1, 21)) - 22
    keep = ndimage.binary_dilation(inkb, iterations=2) | ndimage.binary_dilation(DF.sea_class(Sb), iterations=14)
    band &= ~keep
    m = np.zeros(img.shape[:2], bool)
    m[by0:by1] = band
    before = img.copy()
    for x0 in range(0, W_, 480):
        sub = np.zeros_like(m); sub[:, x0:x0 + 480] = m[:, x0:x0 + 480]
        if sub.any():
            fillart.fill(img, sub, feather=2.0, libs=strict_libs())
    changed |= np.abs(img - before).max(-1) > 0.5
    print('  top-edge seam blended: %.0f k px' % (changed.sum() / 1000))
    return img, changed

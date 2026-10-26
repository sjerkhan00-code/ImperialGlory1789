"""Re-synthesise the blurred fills of the frame-cleaned old tiles (build/art/deframe) in the north margin / burnt
corner (tile row 0): where deframe.py replaced the sheet's frame or burnt corner it left smooth, grain-less patches.

For every row-0 tile: the filled area is where the deframed tile differs from the original tile; inside it the
pixels whose fine-texture energy is well below that of the real art of the same class (land / sea) are blurred.
Those get the deframed tile's broad colour (sigma 24 low-pass, so no blotches) plus real grain: high-pass patches
cut from the untouched art of the same tile row (deframe.local_patches / quilt, amplitude matched to the real art)
and the parchment's mid-scale mottle.  Also flattens the tonal step at the old/new art seam (x = 19930).

Then two leftovers of the sheet's top edge: the soft shadow the neatline cast on the art just inside it (a straight
dark band at y 266..330, worst over Finland / Karelia) is evened out (neat_shadow), and the White Sea, which the
neatline cut off straight, is opened to the Barents Sea through the Gorlo strait (white_sea, re-using deframe's
fill with a forced sea class so the new coast gets the same treatment as the other margin coasts).

python northfix.py        -> build/oldarea/tiles/tile_<c>_0.png for the changed tiles (also kept in
                             build/oldarea/north/, the clean base render_borders.py draws on) + northfix_before_after.png
"""
import os, sys
import numpy as np
from PIL import Image
from scipy import ndimage
import common as C
sys.path.insert(0, os.path.join(C.TOOLS, 'art'))
import deframe as DF

TS = C.TS
PAD = 192
OUT_TILES = os.path.join(C.OUT, 'tiles')
NORTH = os.path.join(C.OUT, 'north')                      # northfix output only (render_borders' base for row 0)
NEAT_X0, NEAT_Y0, NEAT_X1, NEAT_Y1 = 192, 266, 3904, 3830
# the White Sea's outlet (composite px): the neatline cut off the Gorlo (x 2335..2392 at y 266) and the Mezen bay
# (x 2427..2492); both now open into one funnel (the Voronka) that reaches the Barents Sea coast (y ~200) between
# Kola (west) and Kanin (east).  The strip of land between them ends in a small cape just north of the cut.
WHITE_SEA_STRAIT = [(2333, 300), (2331, 280), (2336, 258), (2350, 240), (2373, 222), (2398, 204), (2420, 186),
                    (2540, 205), (2508, 224), (2497, 246), (2492, 268), (2451, 289), (2424, 268), (2416, 261),
                    (2405, 261), (2397, 268), (2395, 300)]


def neat_shadow(out):
    """Even out the neatline's shadow on the art just inside the sheet's top edge (rows ~262..345): per column
    (smoothed over 40 px) and per class, the row profile is pulled onto the straight line between the level above
    the seam and the level below the shadow.  Multiplicative, so ink, grain and coasts are kept."""
    y0, y1 = 228, 380
    S = out[y0:y1]
    lum = S.mean(-1)
    sea = DF.sea_class(S)
    plain = lum > ndimage.median_filter(lum, 15) - 14                 # no ink strokes / glyphs
    ys = np.arange(y0, y1)[:, None]
    t = np.clip((ys - 258) / 6.0, 0, 1) * np.clip((350 - ys) / 10.0, 0, 1)         # 0 outside the shadow band
    xs = np.arange(out.shape[1])[None, :]
    t = t * np.clip((xs - NEAT_X0) / 30.0, 0, 1) * np.clip((NEAT_X1 - xs) / 30.0, 0, 1)
    top = (ys >= 232) & (ys < 256); bot = (ys >= 345) & (ys < 376)
    gains = []
    for cls in (sea, ~sea):
        w = (cls & plain).astype(np.float32)
        den = ndimage.gaussian_filter(w, (2, 40))
        P = np.stack([ndimage.gaussian_filter(S[..., k] * w, (2, 40)) for k in range(3)], -1) / np.maximum(den, 1e-3)[..., None]
        def level(rows):
            wr = den * rows
            return (P * wr[..., None]).sum(0) / np.maximum(wr.sum(0), 1e-3)[..., None], wr.sum(0) / rows.sum()
        lt, ct = level(top); lb, cb = level(bot)
        lt = np.where((ct > 0.15)[:, None], lt, lb); lb = np.where((cb > 0.15)[:, None], lb, lt)
        f = np.clip((ys - 256) / (345.0 - 256), 0, 1)[..., None]
        e = lt[None] * (1 - f) + lb[None] * f
        g = np.clip(e / np.maximum(P, 20), 0.85, 1.4)
        g = np.where((den > 0.05)[..., None], g, 1.0)
        gains.append(1 + (g - 1) * t[..., None])
    ps = ndimage.gaussian_filter(sea.astype(np.float32), 3)[..., None]
    g = gains[0] * ps + gains[1] * (1 - ps)
    out[y0:y1] = S * g
    return out


# exemplar of the original coast style (hatched ripple lines, crimson shore line, jagged brown land rim): the west
# coast of the painted White Sea, composite px box (x0, y0, x1, y1)
COAST_EXEMPLAR = (2110, 300, 2500, 660)


def _coast_runs(sea, margin):
    """Ordered coast points (sub-pixel, marching squares) of a sea mask with their arclength, normals pointing to
    land, as one array per contiguous run away from the window border (margin px)."""
    import geo
    from scipy import ndimage as nd
    h, w = sea.shape
    out = []
    for ring in geo._trace_boundaries(~sea):
        r = np.array(ring, np.float64)
        ok = (r[:, 0] > margin) & (r[:, 0] < w - margin) & (r[:, 1] > margin) & (r[:, 1] < h - margin)
        # contiguous runs of ok points (the ring wraps)
        idx = np.nonzero(ok)[0]
        if len(idx) < 20:
            continue
        breaks = np.nonzero(np.diff(idx) > 1)[0]
        starts = np.r_[idx[0], idx[breaks + 1]]; ends = np.r_[idx[breaks], idx[-1]]
        for a, b in zip(starts, ends):
            pts = r[a:b + 1]
            if len(pts) < 20:
                continue
            t = np.gradient(nd.gaussian_filter1d(pts, 3.0, axis=0), axis=0)
            t /= np.maximum(np.linalg.norm(t, axis=1), 1e-6)[:, None]
            nrm = np.stack([-t[:, 1], t[:, 0]], 1)
            probe = np.clip(np.round(pts + nrm * 4).astype(int), 0, [w - 1, h - 1])
            flip = sea[probe[:, 1], probe[:, 0]]                       # normal must point to land
            nrm[flip] *= -1
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
            out.append((pts, nrm, s))
    return out


def old_style_coast(res, sea, hole, X0, Y0, band=34.0):
    """Repaint the coasts inside `hole` in the original hatched style.  The exemplar coast (COAST_EXEMPLAR, original
    tiles; clean stretches only) gives the colour profile across the shore as a function of the signed distance
    (median per 0.5 px: water, grey ripple hatching, crimson shore line, jagged brown rim, parchment); the target
    coast gets that profile at its own signed distance, perturbed by noise on the land side (jagged rim) and with
    the ripple lines broken into dashes, plus the fill's own fine grain.  Fades to the deframe coast style where the
    funnel opens into the Barents Sea (y < 200), where the margin's other coasts are in that style."""
    from scipy import ndimage as nd
    O = C.comp(False).astype(np.float32)
    ex0, ey0, ex1, ey1 = COAST_EXEMPLAR
    E = O[ey0:ey1, ex0:ex1]
    # the painted shore is the crimson line: water (with its grey hatching) starts where blue catches up with red
    eb = nd.gaussian_filter(E, (2, 2, 0))
    esea = nd.binary_closing(nd.binary_opening(eb[..., 0] - eb[..., 2] < 20, iterations=2), iterations=2)
    lab, k = nd.label(esea)
    esea = lab == (1 + int(np.argmax(nd.sum(esea, lab, range(1, k + 1)))))
    eh, ew = esea.shape
    # clean stretches: open water and plain land for `band` px along the normal
    okmask = np.zeros_like(esea)
    for pts, nrm, s_ in _coast_runs(esea, 40):
        ok = np.ones(len(pts), bool)
        for d in np.arange(-band, band + 1, 3.0):
            pp = np.clip(np.round(pts + nrm * d).astype(int), 0, [ew - 1, eh - 1])
            ok &= (esea[pp[:, 1], pp[:, 0]] == (d < -2)) | (abs(d) <= 2)
        ok = nd.binary_opening(ok, iterations=3)
        q = np.round(pts[ok]).astype(int)
        okmask[np.clip(q[:, 1], 0, eh - 1), np.clip(q[:, 0], 0, ew - 1)] = True
    shore = esea & ~nd.binary_erosion(esea)
    esd = np.where(esea, -nd.distance_transform_edt(esea), nd.distance_transform_edt(~esea))
    _, (iy, ix) = nd.distance_transform_edt(~shore, return_indices=True)
    good = nd.binary_dilation(okmask, iterations=2)[iy, ix]
    bins = np.arange(-24.0, band + 0.5, 0.5)
    profs = {q: np.zeros((len(bins), 3), np.float32) for q in (12, 50, 82)}
    red = np.zeros((len(bins), 3), np.float32)
    for bi, b in enumerate(bins):
        m = good & (np.abs(esd - b) <= 0.5)
        for q, pr in profs.items():
            pr[bi] = np.percentile(E[m], q, axis=0) if m.sum() > 20 else (pr[bi - 1] if bi else np.median(E[esea], 0))
        if m.sum() > 20:                                                # the rim's own colour: the reddest fifth
            v = E[m]; r = v[:, 0] - v[:, 2]
            red[bi] = v[np.argsort(-r)[:max(1, len(r) // 5)]].mean(0)
        else:
            red[bi] = red[bi - 1] if bi else np.median(E[esea], 0)
    profs = {q: nd.gaussian_filter1d(pr, 0.8, axis=0) for q, pr in profs.items()}
    profs['red'] = nd.gaussian_filter1d(red, 0.8, axis=0)
    # target signed distance (+ land, - water)
    tsea = nd.gaussian_filter(sea.astype(np.float32), 1.0) > 0.5
    sd = np.where(tsea, -nd.distance_transform_edt(tsea), nd.distance_transform_edt(~tsea))
    sd = nd.gaussian_filter(sd, 1.0)
    h, w = sea.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rng = np.random.default_rng(7)
    nz = nd.gaussian_filter(rng.standard_normal((h, w)), 2.5); nz /= nz.std()
    nz2 = nd.gaussian_filter(rng.standard_normal((h, w)), 1.2); nz2 /= nz2.std()
    sdp = sd + np.where(sd > 0, 1.5 * nz * np.clip(sd / 6.0, 0, 1), 0.0)          # a little irregularity
    fi = np.clip((sdp - bins[0]) / 0.5, 0, len(bins) - 1.001)
    i0 = fi.astype(int); t = (fi - i0)[..., None]
    look = lambda pr: pr[i0] * (1 - t) + pr[i0 + 1] * t
    col = look(profs[50])
    # land side: crimson shore line and the orange-tan rim (the exemplar's reddest pixels at each distance) out to
    # a jagged edge (noise-displaced, spiky) where the parchment begins
    edge = np.clip((sd + 6.0 * nz - 16.0) / 3.0, 0, 1)[..., None]
    col = np.where((sd > 0)[..., None], look(profs['red']) * (1 - edge) + col * edge, col)
    # water side: the hatching is a grey band of fine, wavering, broken ripple lines parallel to the shore (the
    # light ground and the line colour are the exemplar's 82nd / 12th percentiles at each distance)
    light, dark = look(profs[82]), look(profs[12])
    wob = nd.gaussian_filter(rng.standard_normal((h, w)), 6.0); wob /= wob.std()
    ph = (-(sd + 0.8 * wob) - 1.5) / 2.2                               # a line every 2.2 px from 1.5 px off the shore
    line = np.exp(-(((ph - np.round(ph)) * 2.2) / 0.55) ** 2)
    nz3 = nd.gaussian_filter(rng.standard_normal((h, w)), 1.6); nz3 /= nz3.std()
    dash = np.clip((nz3 + 0.3) / 0.45, 0, 1)                          # short dashes, as drawn
    zone = np.clip((sd + 14.5) / 2.0, 0, 1) * np.clip(-sd / 1.0, 0, 1)
    k = (line * dash * zone)[..., None]
    col = np.where((sd < 0)[..., None], light * (1 - k) + dark * k, col)
    # fine grain: the game's own parchment / sea grain (deframe's quilt), not the fill's (it holds the margin-style
    # rim and ripple lines)
    sea_lib, land_lib = DF._lib()
    n_ = max(h, w)
    gs = DF.quilt(X0, Y0, n_, sea_lib, 51)[:h, :w]; gl = DF.quilt(X0, Y0, n_, land_lib, 52)[:h, :w]
    grain = np.where((sd < 0)[..., None], gs, gl) * 0.8
    ex = col + grain
    sel = (sd < band) & (sd > -24.0)
    wband = np.clip((band - sd) / 8.0, 0, 1) * np.clip((24.0 + sd) / 7.0, 0, 1)
    wy = np.clip((yy + Y0 - 176.0) / 26.0, 0, 1)                      # full style in the funnel, none in the open sea
    wh = nd.gaussian_filter(hole.astype(np.float32), 3.0)
    # 2026-10-22 (shore-halo fix): only the LAND side (crimson shore line, tan rim) is painted from the exemplar; the
    # water side keeps deframe.fill_holes' coast treatment (styled2._coast_water: the original's water darkening
    # towards the shore with dotted ripple rings).  The exemplar's water side (82nd percentile ground, sparse dashes)
    # left a pale band along the shore.
    a = (wband * wy * wh * sel * (sd > 0))[..., None]
    return res * (1 - a) + ex * a


def white_sea(out):
    """Open the White Sea through the Gorlo (WHITE_SEA_STRAIT) with deframe's fill and coast treatment."""
    from PIL import ImageDraw
    X0, Y0, n = 2048, 0, 640
    win = out[Y0:Y0 + n, X0:X0 + n].copy()
    m = Image.new('L', (n, n), 0)
    ImageDraw.Draw(m).polygon([(x - X0, y - Y0) for x, y in WHITE_SEA_STRAIT], fill=255)
    strait = np.asarray(m) > 0
    sea = DF.sea_class(win) | strait
    ys = np.arange(n)[:, None] + Y0
    hole = ndimage.binary_dilation(strait, iterations=28) & (ys < 304)
    res = DF.fill_holes(win, hole, X0, Y0, cls_force=sea)
    res = old_style_coast(res, sea, hole, X0, Y0)
    # cross-fade into the painted White Sea below the cut, so its hatched coasts run on into the new ones
    a = np.clip((302 - ys) / 22.0, 0, 1)[..., None].astype(np.float32)
    out[Y0:Y0 + n, X0:X0 + n] = win * (1 - a) + res * a
    return out


def energy(img, s_hp=2.5, s_win=10):
    hp = img.mean(-1) - ndimage.gaussian_filter(img.mean(-1), s_hp)
    return np.sqrt(ndimage.gaussian_filter(hp * hp, s_win))


def clean_patches(O, ok, P=128, step=48):
    """High-pass (sigma 10) patches of plain art: one class only, no ink strokes, little tonal variation."""
    hp = O - ndimage.gaussian_filter(O, (10, 10, 0))
    lum = O.mean(-1)
    dark = lum < ndimage.median_filter(lum, 21) - 38
    lp = ndimage.gaussian_filter(lum, 12)
    out = []
    h, w = ok.shape
    for y in range(0, h - P + 1, step):
        for x in range(0, w - P + 1, step):
            if ok[y:y + P, x:x + P].mean() < 0.995 or dark[y:y + P, x:x + P].mean() > 0.02:
                continue
            if lp[y:y + P, x:x + P].std() > 7.0:
                continue
            q = hp[y:y + P, x:x + P].astype(np.float32)
            out.append(q); out.append(q[::-1, ::-1])
    return out


def fix_row0(write=True):
    orig = C.comp(False).astype(np.float32)
    defr = C.comp(True).astype(np.float32)
    H, W = orig.shape[:2]
    y1 = TS + PAD                                             # rows 0..y1 of the composite (tile row 0 + context)
    O = orig[:y1]; D = defr[:y1].copy()
    sea = DF.sea_class(D)
    # the filled area: where deframe changed the tile (plus the burnt corner's dark original is also 'hole')
    diff = np.abs(D - O).mean(-1)
    hole = ndimage.gaussian_filter(diff, 3) > 28.0                 # (the vignette flattening alone changes < 20)
    ys, xs = np.mgrid[0:y1, 0:W]
    inside = (xs >= NEAT_X0) & (xs < NEAT_X1) & (ys >= NEAT_Y0)
    hole |= ~inside & (ys < y1)                               # the whole margin is synthetic
    hole = ndimage.binary_opening(hole, iterations=2)
    # fine-texture energy vs the real art of each class (untouched pixels inside the neatline)
    en = energy(D)
    real = inside & ~ndimage.binary_dilation(hole, iterations=20)
    ref = {}
    for cls, m in (('sea', sea), ('land', ~sea)):
        sel = real & m
        ref[cls] = np.median(en[sel]) if sel.sum() > 1000 else 6.0
    print('  texture energy of the real art: land %.1f sea %.1f' % (ref['land'], ref['sea']))
    thr = np.where(sea, 0.62 * ref['sea'], 0.62 * ref['land'])
    blurred = hole & (en < thr)
    blurred = ndimage.binary_opening(blurred, iterations=3)
    blurred = ndimage.binary_dilation(blurred, iterations=10)
    blurred &= hole
    lab, n = ndimage.label(blurred)
    sizes = ndimage.sum(blurred, lab, range(1, n + 1))
    blurred = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 600])
    print('  blurred area: %.0f k px in %d regions' % (blurred.sum() / 1000, len([s for s in sizes if s >= 600])))
    # colour: broad low-pass of the deframed art, per class (no blotches)
    def lp(img, w, sigma):
        wf = ndimage.gaussian_filter(w.astype(np.float32), sigma)
        return np.stack([ndimage.gaussian_filter(img[..., k] * w, sigma) for k in range(3)], -1) / np.maximum(wf, 1e-3)[..., None]
    base = np.where(sea[..., None], lp(D, sea, 24), lp(D, ~sea, 24))
    # grain: high-pass patches of the real art of this row (land / sea), quilted on the global grid
    loc_land = clean_patches(O, real & ~sea)
    loc_sea = clean_patches(O, real & sea)
    sea_lib, land_lib = DF._lib()
    print('  patches: land %d sea %d' % (len(loc_land), len(loc_sea)))
    # quilt works on square windows: do it per 1024 window across the strip
    tex = np.zeros((y1, W, 3), np.float32)
    for c in range(4):
        X0 = c * TS
        tl = DF.quilt(X0, 0, max(y1, TS), loc_land if len(loc_land) >= 8 else land_lib, 31)[:y1, :TS]
        tsq = DF.quilt(X0, 0, max(y1, TS), loc_sea if len(loc_sea) >= 8 else sea_lib, 32)[:y1, :TS]
        tex[:, X0:X0 + TS] = np.where(sea[:, X0:X0 + TS, None], tsq, tl)
    # amplitude match: high-pass std of the real art per class vs the quilt
    hpD = O - ndimage.gaussian_filter(O, (10, 10, 0))
    lum = O.mean(-1)
    plain = lum > ndimage.median_filter(lum, 21) - 12                 # no ink strokes / glyphs
    for cls, m in (('sea', sea), ('land', ~sea)):
        sel = real & m & plain
        if sel.sum() < 1000:
            continue
        a_real = 1.4826 * np.median(np.abs(hpD[sel]), 0); a_tex = 1.4826 * np.median(np.abs(tex[m]), 0) + 1e-3
        print('  %s grain amplitude: real %s quilt %s' % (cls, a_real.round(1), a_tex.round(1)))
        tex[m] *= (a_real / a_tex)
    bp = ndimage.gaussian_filter(O, (11, 11, 0)) - ndimage.gaussian_filter(O, (45, 45, 0))
    amp = np.array([bp[..., k][real].std() for k in range(3)], np.float32)
    mott = np.zeros((y1, W), np.float32)
    for c in range(4):
        mott[:, c * TS:(c + 1) * TS] = DF.mottle(c * TS, 0, max(y1, TS))[:y1, :TS]
    fill = base + tex + mott[..., None] * amp * 0.5
    a = ndimage.gaussian_filter(blurred.astype(np.float32), 4.0)[..., None]
    out = D * (1 - a) + fill * a
    # tonal step at the old/new art seam (x = 19930 world): equalise the low-pass across it with a smooth gain
    sx = int(C.w2p(19930, 0)[0])
    band = 90
    left = out[:, sx - band:sx]; right = out[:, sx:sx + band]
    gl = ndimage.gaussian_filter(left.mean(1), 40, axes=(0,)); gr = ndimage.gaussian_filter(right.mean(1), 40, axes=(0,))
    gain = np.clip((gl + gr) / 2 / np.maximum(gr, 1), 0.7, 1.4)        # per row, per channel
    t = np.clip(1 - (xs[:, sx:sx + 2 * band] - sx) / (2.0 * band), 0, 1)
    out[:, sx:sx + 2 * band] = out[:, sx:sx + 2 * band] * (1 + (gain[:, None, :] - 1) * t[..., None])
    gain2 = np.clip((gl + gr) / 2 / np.maximum(gl, 1), 0.7, 1.4)
    t2 = np.clip((xs[:, sx - 2 * band:sx] - (sx - 2 * band)) / (2.0 * band), 0, 1)
    out[:, sx - 2 * band:sx] = out[:, sx - 2 * band:sx] * (1 + (gain2[:, None, :] - 1) * t2[..., None])
    out = neat_shadow(out)
    out = white_sea(out)
    out = np.clip(out, 0, 255)
    changed = (np.abs(out - D).mean(-1) > 0.5)
    written = []
    if write:
        os.makedirs(OUT_TILES, exist_ok=True); os.makedirs(NORTH, exist_ok=True)
        for c in range(4):
            if changed[:TS, c * TS:(c + 1) * TS].any():
                t = Image.fromarray(out[:TS, c * TS:(c + 1) * TS].astype(np.uint8))
                p = os.path.join(OUT_TILES, 'tile_%d_0.png' % c)
                t.save(p); t.save(os.path.join(NORTH, 'tile_%d_0.png' % c))
                written.append(p)
        # before / after crop of the worst area (north-east: burnt corner + Arctic margin)
        x0, x1, y0, y1c = 2900, 4096, 0, 700
        b = Image.fromarray(D[y0:y1c, x0:x1].astype(np.uint8)); a2 = Image.fromarray(out[y0:y1c, x0:x1].astype(np.uint8))
        Wimg = Image.new('RGB', (b.width, b.height * 2 + 12), (255, 255, 255)); Wimg.paste(b, (0, 0)); Wimg.paste(a2, (0, b.height + 12))
        Wimg.save(os.path.join(C.OUT, 'northfix_before_after.png'))
        Image.fromarray((blurred[:TS] * 255).astype(np.uint8)).resize((1024, 256)).save(os.path.join(C.OUT, 'work', 'northfix_mask.png'))
    return out[:TS], written


if __name__ == '__main__':
    out, written = fix_row0()
    print('\n'.join(written))

"""Battle-map textures and previews (numpy). Companion of tools/lvl.py.

The battle terrain is textured by ONE painted 4096 x 4096 image per map, cut into 4 x 4 tiles
Models/T00<r>00<c>.tga (really DDS DXT1 1024^2 with 11 mips). Tile (r, c) covers world x in [c, c+1) * 18750 cm and
z in [r, r+1) * 18750 cm; image row 0 is the tile's HIGH z edge (terrain UV1 v = 1 - (z - z0) / 18750). A tiled
detail texture (Detalle.dds, 30 repeats over the map, UV0) is multiplied on top, and the terrain vertex colour
(grey 63..255) carries the baked sun shading. Trees are separate meshes (Models/Arboles.V3D), buildings are V3D
objects with their own lightmaps.
"""
import os
import struct

import numpy as np

TILE_CM = 18750.0


def dxt1_decode(data, w, h):
    """DXT1 blocks -> (h, w, 3) uint8 (alpha ignored)."""
    nb = (w // 4) * (h // 4)
    blk = np.frombuffer(data[:nb * 8], dtype=[('c0', '<u2'), ('c1', '<u2'), ('bits', '<u4')])
    c0 = blk['c0'].astype(np.int32); c1 = blk['c1'].astype(np.int32)

    def unpack(c):
        return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], 1)
    p0, p1 = unpack(c0), unpack(c1)
    four = (c0 > c1)[:, None]
    p2 = np.where(four, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four, (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)                                   # N x 4 x 3
    idx = (blk['bits'][:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3   # N x 16
    px = pal[np.arange(nb)[:, None], idx]                                 # N x 16 x 3
    px = px.reshape(h // 4, w // 4, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, 3)
    return px.astype(np.uint8)


def read_dds(path, mip=0):
    """A DXT1 .dds (or a Pyro .tga that is really a DDS) -> (h, w, 3) uint8 of mip level `mip`."""
    d = open(path, 'rb').read()
    assert d[:4] == b'DDS ', path
    h, w = struct.unpack_from('<II', d, 12)
    assert d[84:88] == b'DXT1', (path, d[84:88])
    nmips = max(1, struct.unpack_from('<I', d, 28)[0])
    mip = min(mip, nmips - 1)
    p = 128
    for _ in range(mip):
        p += max(1, w // 4) * max(1, h // 4) * 8
        w, h = max(1, w // 2), max(1, h // 2)
    return dxt1_decode(d[p:], max(4, w), max(4, h))[:h, :w]


def read_tga(path):
    """Uncompressed 24/32-bit TGA -> (h, w, 4) uint8 RGBA, top row first."""
    d = open(path, 'rb').read()
    idl, typ = d[0], d[2]
    w, h, bpp, desc = struct.unpack_from('<HHBB', d, 12)
    assert typ == 2, (path, typ)
    bp = bpp // 8
    a = np.frombuffer(d[18 + idl:18 + idl + w * h * bp], np.uint8).reshape(h, w, bp)
    out = np.full((h, w, 4), 255, np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = a[..., 2], a[..., 1], a[..., 0]
    if bp == 4:
        out[..., 3] = a[..., 3]
    if not desc & 0x20:
        out = out[::-1]
    return out


def write_tga32(path, rgba):
    """(h, w, 4) uint8 -> uncompressed 32-bit TGA, bottom-up, alpha 8 bits (as the game's minimaps)."""
    h, w = rgba.shape[:2]
    hdr = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8)
    bgra = rgba[::-1][..., [2, 1, 0, 3]]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'wb').write(hdr + np.ascontiguousarray(bgra).tobytes())


def write_tga24(path, rgb):
    """(h, w, 3) uint8 -> uncompressed 24-bit TGA, bottom-up (as the game's Comun/Minimapas images)."""
    h, w = rgb.shape[:2]
    hdr = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, w, h, 24, 0)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'wb').write(hdr + np.ascontiguousarray(rgb[::-1][..., [2, 1, 0]]).tobytes())


def tile_name(r, c):
    return 'T%03d%03d.tga' % (r, c)


def map_texture(models_dir, mip=2, ntiles=4, names=None):
    """Composite of the 4 x 4 tiles, NORTH-UP image: image row 0 = high z, column 0 = x 0. `names`: the tile file
    of material r * 4 + c (the TERRAIN chunk's materials[i][2]; some maps name them .dds)."""
    names = names or [tile_name(r, c) for r in range(ntiles) for c in range(ntiles)]
    tiles = [[read_dds(os.path.join(models_dir, names[r * ntiles + c]), mip) for c in range(ntiles)]
             for r in range(ntiles)]
    rows = [np.concatenate(tiles[r], 1) for r in range(ntiles)]
    return np.concatenate(rows[::-1], 0)


def write_tiles(models_dir, img, ntiles=4):
    """Inverse of map_texture: north-up (4096, 4096, 3) image -> 16 DXT1 tiles with full mips (named .tga)."""
    import tga
    n = img.shape[0] // ntiles
    for r in range(ntiles):
        for c in range(ntiles):
            y0 = (ntiles - 1 - r) * n
            tga.write_dds_dxt1_mips_np(os.path.join(models_dir, tile_name(r, c)),
                                       np.ascontiguousarray(img[y0:y0 + n, c * n:(c + 1) * n]))


def hillshade(h, cell, light=(0.45, 0.80, 0.40)):
    """N.L shading of a (nz, nx) height grid (row = z), light vector (x, y, z), north-up output (row 0 = high z)."""
    gz, gx = np.gradient(h.astype(np.float64), cell)
    n = np.stack([-gx, np.ones_like(gx), -gz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    l = np.asarray(light, float); l /= np.linalg.norm(l)
    return np.clip((n * l).sum(-1), 0, 1)[::-1]


def save_png(path, img):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Image.fromarray(np.asarray(img, np.uint8)).save(path)


# ------------------------------------------------------------------ synthesis helpers (new maps from original art)
def window(n):
    """Raised-cosine weight window (n x n) for overlapping patches."""
    w = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(n) + 0.5) / n)
    return np.outer(w, w).astype(np.float32) + 1e-4


def patch_synth(shape, srcs, rng, patch=384, step=256, orient=True):
    """Fill an (h, w, 3) float32 image with randomly chosen, randomly placed patches cut from original textures.
    srcs: [(image uint8 (H, W, 3), (x0, y0, x1, y1) box in that image)], chosen by box area."""
    h, w = shape
    acc = np.zeros((h + 2 * patch, w + 2 * patch, 3), np.float32)
    wsum = np.zeros((h + 2 * patch, w + 2 * patch), np.float32)
    win = window(patch)
    areas = np.array([(b[2] - b[0]) * (b[3] - b[1]) for _, b in srcs], float)
    for y in range(-patch // 2, h, step):
        for x in range(-patch // 2, w, step):
            img, (x0, y0, x1, y1) = srcs[rng.choice(len(srcs), p=areas / areas.sum())]
            pw, ph = min(patch, x1 - x0), min(patch, y1 - y0)
            sx = rng.integers(x0, x1 - pw + 1)
            sy = rng.integers(y0, y1 - ph + 1)
            p = img[sy:sy + ph, sx:sx + pw].astype(np.float32)
            if pw != patch or ph != patch:                   # small source box: tile it
                p = np.tile(p, (patch // ph + 1, patch // pw + 1, 1))[:patch, :patch]
            if orient:
                k = rng.integers(0, 4)
                p = np.rot90(p, k)
                if rng.random() < 0.5:
                    p = p[:, ::-1]
            yy, xx = y + patch // 2, x + patch // 2
            acc[yy:yy + patch, xx:xx + patch] += p * win[..., None]
            wsum[yy:yy + patch, xx:xx + patch] += win
    out = acc / wsum[..., None]
    o = patch // 2
    return out[o:o + h, o:o + w]


def world_to_px(x, z, size_cm, px):
    """North-up texture pixel (col, row) of world (x, z)."""
    return np.asarray(x) / size_cm * px, (size_cm - np.asarray(z)) / size_cm * px


def bilinear(img, cols, rows):
    """Sample an (H, W, C) image at float pixel coords (clamped)."""
    H, W = img.shape[:2]
    c = np.clip(cols, 0, W - 1.001); r = np.clip(rows, 0, H - 1.001)
    c0, r0 = c.astype(int), r.astype(int)
    fc, fr = (c - c0)[..., None], (r - r0)[..., None]
    a = img[r0, c0].astype(np.float32); b = img[r0, c0 + 1].astype(np.float32)
    cc = img[r0 + 1, c0].astype(np.float32); d = img[r0 + 1, c0 + 1].astype(np.float32)
    return (a * (1 - fc) + b * fc) * (1 - fr) + (cc * (1 - fc) + d * fc) * fr


def polyline_frame(px_cols, px_rows, pts):
    """For pixel coords: (distance, arc length, signed offset) to a polyline given in the same pixel space."""
    best = np.full(px_cols.shape, 1e18); s_at = np.zeros(px_cols.shape); side = np.zeros(px_cols.shape)
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        L = L2 ** 0.5
        t = np.clip(((px_cols - x0) * dx + (px_rows - y0) * dy) / L2, 0, 1)
        qx, qy = x0 + t * dx, y0 + t * dy
        d = np.hypot(px_cols - qx, px_rows - qy)
        sgn = np.sign((px_cols - x0) * dy - (px_rows - y0) * dx)
        m = d < best
        best = np.where(m, d, best); s_at = np.where(m, acc + t * L, s_at); side = np.where(m, sgn * d, side)
        acc += L
    return best, s_at, side


def curve_transfer(img_src, src_pts, cols, rows, dst_pts, scale_offset=1.0):
    """Copy the look of a feature along a source curve (e.g. an original stream bed) onto a destination curve:
    each destination pixel takes the source pixel at the same arc length (ping-pong repeated) and offset."""
    d, s, off = polyline_frame(cols, rows, dst_pts)
    seg = np.hypot(np.diff(np.array(src_pts)[:, 0]), np.diff(np.array(src_pts)[:, 1]))
    Ls = seg.sum()
    ss = np.mod(s, 2 * Ls)
    ss = np.where(ss > Ls, 2 * Ls - ss, ss)
    cum = np.concatenate([[0], np.cumsum(seg)])
    P = np.array(src_pts, float)
    k = np.clip(np.searchsorted(cum, ss) - 1, 0, len(seg) - 1)
    t = (ss - cum[k]) / seg[k]
    bx = P[k, 0] + t * (P[k + 1, 0] - P[k, 0]); by = P[k, 1] + t * (P[k + 1, 1] - P[k, 1])
    tx, ty = (P[k + 1, 0] - P[k, 0]) / seg[k], (P[k + 1, 1] - P[k, 1]) / seg[k]
    nx, ny = ty, -tx                                     # normal (same handedness as polyline_frame's sign)
    o = off * scale_offset
    return bilinear(img_src, bx + nx * o, by + ny * o), d


def tree_shadows(shape, trees_px, rng, length=78.0, width=26.0, direction=(-0.55, -0.83), strength=0.5):
    """Multiplicative shadow mask (1 = lit) with soft canopy shadows cast from tree bases (pixel coords),
    in the style of the originals' painted tree shadows (canopy blob offset away from the sun, thin trunk)."""
    h, w = shape
    m = np.ones((h, w), np.float32)
    ux, uy = direction
    r = int(length + width) + 4
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    along = xx * ux + yy * uy
    across = -xx * uy + yy * ux
    for (cx, cy) in trees_px:
        L = length * rng.uniform(0.75, 1.25); W = width * rng.uniform(0.8, 1.3)
        a0 = L * 0.35
        blob = np.exp(-(((along - a0 - L * 0.25) / (L * 0.42)) ** 2 + (across / W) ** 2) * 2.2)
        trunk = np.exp(-((across / 2.2) ** 2)) * (along > 0) * (along < a0)
        s = np.clip(np.maximum(blob, 0.8 * trunk) * strength, 0, strength)
        x0, y0 = int(cx) - r, int(cy) - r
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(w, x0 + 2 * r + 1), min(h, y0 + 2 * r + 1)
        if xa >= xb or ya >= yb:
            continue
        m[ya:yb, xa:xb] *= 1 - s[ya - y0:yb - y0, xa - x0:xb - x0]
    return m

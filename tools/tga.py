"""Minimal TGA (uncompressed 24/32-bit) and DXT1 DDS read/write, pure Python."""
import struct


def read_tga(path):
    """-> (w, h, rows) with rows top-down, each a bytearray of RGBA."""
    d = open(path, 'rb').read()
    idl, cmt, typ = d[0], d[1], d[2]
    w, h, bpp, desc = struct.unpack_from('<HHBB', d, 12)
    assert typ == 2 and cmt == 0, (path, typ)
    p = 18 + idl
    bp = bpp // 8
    rows = []
    for y in range(h):
        src = d[p + y * w * bp:p + (y + 1) * w * bp]
        row = bytearray(w * 4)
        for x in range(w):
            b, g, r = src[x * bp], src[x * bp + 1], src[x * bp + 2]
            a = src[x * bp + 3] if bp == 4 else 255
            row[x * 4:x * 4 + 4] = bytes((r, g, b, a))
        rows.append(row)
    if not desc & 0x20:            # bottom-left origin
        rows.reverse()
    return w, h, rows


def write_tga(path, w, h, rows, alpha=True):
    """rows top-down RGBA; written bottom-up like the game's own files."""
    bp = 4 if alpha else 3
    out = bytearray(struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, w, h, bp * 8, 8 if alpha else 0))
    for row in reversed(rows):
        for x in range(w):
            r, g, b, a = row[x * 4:x * 4 + 4]
            out += bytes((b, g, r, a)) if alpha else bytes((b, g, r))
    open(path, 'wb').write(out)


def crop(rows, u, v, sx, sy):
    return [bytearray(r[u * 4:(u + sx) * 4]) for r in rows[v:v + sy]]


def _565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def write_dds_dxt1(path, w, h, rows):
    """DXT1 without mipmaps. Each 4x4 block uses its darkest and brightest pixel as end points."""
    hdr = bytearray(128)
    hdr[0:4] = b'DDS '
    struct.pack_into('<7I', hdr, 4, 124, 0x1007, h, w, w * h // 2, 0, 0)
    struct.pack_into('<2I', hdr, 76, 32, 4)
    hdr[84:88] = b'DXT1'
    struct.pack_into('<I', hdr, 108, 0x1000)
    out = bytearray(hdr)
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            px = [tuple(rows[by + j][(bx + i) * 4:(bx + i) * 4 + 3]) for j in range(4) for i in range(4)]
            lum = [p[0] * 3 + p[1] * 6 + p[2] for p in px]
            hi, lo = px[lum.index(max(lum))], px[lum.index(min(lum))]
            c0, c1 = _565(*hi), _565(*lo)
            if c0 < c1:
                c0, c1, hi, lo = c1, c0, lo, hi
            pal = [hi, lo, tuple((2 * a + b) // 3 for a, b in zip(hi, lo)), tuple((a + 2 * b) // 3 for a, b in zip(hi, lo))]
            bits = 0
            for k, p in enumerate(px):
                best = min(range(4), key=lambda n: sum((p[i] - pal[n][i]) ** 2 for i in range(3))) if c0 != c1 else 0
                bits |= best << (2 * k)
            out += struct.pack('<HHI', c0, c1, bits)
    open(path, 'wb').write(out)


def _dxt1_blocks(w, h, rows):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            px = [tuple(rows[min(h - 1, by + j)][min(w - 1, bx + i) * 4:min(w - 1, bx + i) * 4 + 3]) for j in range(4) for i in range(4)]
            lum = [p[0] * 3 + p[1] * 6 + p[2] for p in px]
            hi, lo = px[lum.index(max(lum))], px[lum.index(min(lum))]
            c0, c1 = _565(*hi), _565(*lo)
            if c0 < c1:
                c0, c1, hi, lo = c1, c0, lo, hi
            pal = [hi, lo, tuple((2 * a + b) // 3 for a, b in zip(hi, lo)), tuple((a + 2 * b) // 3 for a, b in zip(hi, lo))]
            bits = 0
            if c0 != c1:
                for k, p in enumerate(px):
                    best = min(range(4), key=lambda n: (p[0] - pal[n][0]) ** 2 + (p[1] - pal[n][1]) ** 2 + (p[2] - pal[n][2]) ** 2)
                    bits |= best << (2 * k)
            out += struct.pack('<HHI', c0, c1, bits)
    return out


def write_dds_dxt1_mips(path, w, h, rows):
    """DXT1 with a full mipmap chain, laid out like the game's own map tiles."""
    levels = []
    cw, ch, cur = w, h, rows
    while True:
        levels.append(_dxt1_blocks(cw, ch, cur))
        if cw == 1 and ch == 1:
            break
        nw, nh = max(1, cw // 2), max(1, ch // 2)
        nxt = []
        for y in range(nh):
            r0, r1 = cur[min(ch - 1, 2 * y)], cur[min(ch - 1, 2 * y + 1)]
            row = bytearray(nw * 4)
            for x in range(nw):
                a, b = min(cw - 1, 2 * x) * 4, min(cw - 1, 2 * x + 1) * 4
                for k in range(4):
                    row[x * 4 + k] = (r0[a + k] + r0[b + k] + r1[a + k] + r1[b + k]) // 4
            nxt.append(row)
        cw, ch, cur = nw, nh, nxt
    hdr = bytearray(128)
    hdr[0:4] = b'DDS '
    struct.pack_into('<7I', hdr, 4, 124, 0xA1007, h, w, w * h // 2, 0, len(levels))
    struct.pack_into('<2I', hdr, 76, 32, 4)
    hdr[84:88] = b'DXT1'
    struct.pack_into('<I', hdr, 108, 0x1000 | 0x400000 | 0x8)
    open(path, 'wb').write(bytes(hdr) + b''.join(levels))


def _dxt1_np(img):
    """img: HxWx3 uint8 numpy array (H, W multiples of 4) -> DXT1 bytes. Endpoints = darkest and brightest pixel."""
    import numpy as np
    h, w = img.shape[:2]
    b = img.reshape(h // 4, 4, w // 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3).astype(np.int32)
    lum = b[..., 0] * 3 + b[..., 1] * 6 + b[..., 2]
    hi = b[np.arange(len(b)), lum.argmax(1)]; lo = b[np.arange(len(b)), lum.argmin(1)]
    def c565(c):
        return ((c[:, 0] >> 3) << 11) | ((c[:, 1] >> 2) << 5) | (c[:, 2] >> 3)
    c0 = c565(hi); c1 = c565(lo)
    swap = c0 < c1
    c0s = np.where(swap, c1, c0); c1s = np.where(swap, c0, c1)
    hi2 = np.where(swap[:, None], lo, hi); lo2 = np.where(swap[:, None], hi, lo)
    def unpack(c):
        return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], 1)
    p0 = unpack(c0s); p1 = unpack(c1s)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)            # N x 4 x 3
    dist = ((b[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)                 # N x 16 x 4
    idx = dist.argmin(-1).astype(np.uint32)
    idx[c0s == c1s] = 0
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))).sum(1).astype(np.uint32)
    out = np.zeros(len(b), dtype=[('c0', '<u2'), ('c1', '<u2'), ('bits', '<u4')])
    out['c0'] = c0s; out['c1'] = c1s; out['bits'] = bits
    return out.tobytes()


def write_dds_dxt1_mips_np(path, img):
    """img: 1024x1024x3 uint8 numpy array. DXT1 with a full mip chain, header like the game's tiles."""
    import numpy as np
    h, w = img.shape[:2]
    levels = []
    cur = img.astype(np.float32)
    while True:
        lv = np.clip(cur + 0.5, 0, 255).astype(np.uint8)
        ph, pw = max(4, lv.shape[0]), max(4, lv.shape[1])
        if lv.shape[0] < 4 or lv.shape[1] < 4:
            pad = np.zeros((ph, pw, 3), np.uint8); pad[:lv.shape[0], :lv.shape[1]] = lv
            pad[lv.shape[0]:, :] = pad[lv.shape[0] - 1:lv.shape[0], :]; pad[:, lv.shape[1]:] = pad[:, lv.shape[1] - 1:lv.shape[1]]
            lv = pad
        levels.append(_dxt1_np(lv))
        if cur.shape[0] == 1 and cur.shape[1] == 1:
            break
        cur = cur.reshape(max(1, cur.shape[0] // 2), 2 if cur.shape[0] > 1 else 1, max(1, cur.shape[1] // 2), 2 if cur.shape[1] > 1 else 1, 3).mean((1, 3))
    hdr = bytearray(128)
    hdr[0:4] = b'DDS '
    struct.pack_into('<7I', hdr, 4, 124, 0xA1007, h, w, w * h // 2, 0, len(levels))
    struct.pack_into('<2I', hdr, 76, 32, 4)
    hdr[84:88] = b'DXT1'
    struct.pack_into('<I', hdr, 108, 0x1000 | 0x400000 | 0x8)
    open(path, 'wb').write(bytes(hdr) + b''.join(levels))

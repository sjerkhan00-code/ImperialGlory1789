"""Full DXT1/DXT3/DXT5 DDS decoder (pure Python) and a small PNG writer. Read-only use of game textures."""
import struct, zlib


def _565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def read_dds(path):
    """-> (w, h, rows) with rows top-down RGBA bytearrays (first mip level only)."""
    d = open(path, 'rb').read()
    assert d[:4] == b'DDS '
    h, w = struct.unpack_from('<II', d, 12)
    four = d[84:88]
    rows = [bytearray(w * 4) for _ in range(h)]
    p = 128
    bs = 8 if four == b'DXT1' else 16
    assert four in (b'DXT1', b'DXT3', b'DXT5'), four
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            alpha = [255] * 16
            if four == b'DXT3':
                a64 = int.from_bytes(d[p:p + 8], 'little')
                alpha = [((a64 >> (4 * i)) & 15) * 17 for i in range(16)]
                q = p + 8
            elif four == b'DXT5':
                a0, a1 = d[p], d[p + 1]
                bits = int.from_bytes(d[p + 2:p + 8], 'little')
                if a0 > a1:
                    pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
                else:
                    pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
                alpha = [pal[(bits >> (3 * i)) & 7] for i in range(16)]
                q = p + 8
            else:
                q = p
            c0, c1, idx = struct.unpack_from('<HHI', d, q)
            a, b = _565(c0), _565(c1)
            if c0 > c1 or four != b'DXT1':
                cols = [a + (255,), b + (255,), tuple((2 * a[k] + b[k]) // 3 for k in range(3)) + (255,),
                        tuple((a[k] + 2 * b[k]) // 3 for k in range(3)) + (255,)]
            else:
                cols = [a + (255,), b + (255,), tuple((a[k] + b[k]) // 2 for k in range(3)) + (255,), (0, 0, 0, 0)]
            for i in range(16):
                y, x = by + i // 4, bx + i % 4
                if y < h and x < w:
                    r, g, bb, aa = cols[(idx >> (2 * i)) & 3]
                    if four != b'DXT1':
                        aa = alpha[i]
                    rows[y][x * 4:x * 4 + 4] = bytes((r, g, bb, aa))
            p += bs
    return w, h, rows


def write_png(path, rows, alpha=True):
    w, h = len(rows[0]) // 4, len(rows)
    if alpha:
        raw = b''.join(b'\0' + bytes(r) for r in rows)
        ct = 6
    else:
        raw = b''.join(b'\0' + bytes(b for i, b in enumerate(r) if i % 4 != 3) for r in rows)
        ct = 2
    def ch(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, ct, 0, 0, 0))
                           + ch(b'IDAT', zlib.compress(raw, 9)) + ch(b'IEND', b''))


def crop(rows, x, y, w, h):
    return [bytearray(r[x * 4:(x + w) * 4]) for r in rows[y:y + h]]

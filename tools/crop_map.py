"""Crop the north-up map background with province outlines and a labelled world grid (every 500 units).
usage: crop_map.py x0 x1 z0 z1 scale out.png"""
import sys, os, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_map as R

DIGITS = {  # 3x5 bitmap font
    '0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111', '4': '101101111001001',
    '5': '111100111001111', '6': '111100111101111', '7': '111001001001001', '8': '111101111101111', '9': '111101111001111', '-': '000000111000000'}

def load_bg():
    raw = open(os.path.join(R.OUT, 'map_background.png'), 'rb').read(); i = 8; idat = b''
    while i < len(raw):
        n = struct.unpack('>I', raw[i:i + 4])[0]; t = raw[i + 4:i + 8]
        if t == b'IDAT': idat += raw[i + 8:i + 8 + n]
        i += 12 + n
    d = zlib.decompress(idat); W = 1024
    return [d[y * (W * 3 + 1) + 1:(y + 1) * (W * 3 + 1)] for y in range(W)]

def main(x0, x1, z0, z1, scale, out, extra=None, labels=None):
    rows = load_bg(); W = 1024
    def bgpx(x, z): return (x - R.X0) / (R.TILE_W * 4) * W, (R.Z0 - z) / (R.TILE_H * 4) * W
    ow, oh = int((x1 - x0) / scale), int((z1 - z0) / scale)
    img = bytearray(ow * oh * 3)
    for j in range(oh):
        z = z1 - j * scale
        for i in range(ow):
            x = x0 + i * scale; px, py = bgpx(x, z); px, py = int(px), int(py)
            if 0 <= px < W and 0 <= py < W: img[(j * ow + i) * 3:(j * ow + i) * 3 + 3] = rows[py][px * 3:px * 3 + 3]
    def put(i, j, c):
        if 0 <= i < ow and 0 <= j < oh: img[(j * ow + i) * 3:(j * ow + i) * 3 + 3] = c
    def to(x, z): return (x - x0) / scale, (z1 - z) / scale
    def seg(a, b, c):
        (i0, j0), (i1, j1) = to(*a), to(*b); n = int(max(abs(i1 - i0), abs(j1 - j0))) + 1
        for k in range(n + 1): put(int(i0 + (i1 - i0) * k / n), int(j0 + (j1 - j0) * k / n), c)
    def text(s, i, j, c=b'\xff\xff\x00'):
        for n, ch in enumerate(s):
            g = DIGITS.get(ch)
            if g:
                for k, bit in enumerate(g):
                    if bit == '1':
                        for dy in range(2):
                            for dx in range(2): put(i + n * 8 + (k % 3) * 2 + dx, j + (k // 3) * 2 + dy, c)
    for gx in range(int(x0 // 500 * 500), int(x1) + 1, 500):
        seg((gx, z0), (gx, z1), b'\x60\x60\x60' if gx % 1000 else b'\xa0\xa0\xa0')
        if gx % 1000 == 0: text(str(gx), int(to(gx, 0)[0]) + 2, 2)
    for gz in range(int(z0 // 500 * 500), int(z1) + 1, 500):
        seg((x0, gz), (x1, gz), b'\x60\x60\x60' if gz % 1000 else b'\xa0\xa0\xa0')
        if gz % 1000 == 0: text(str(gz), 2, int(to(0, gz)[1]) + 2)
    for e in R.province_outlines(os.path.join(R.MAPA, 'MapaGestionVolumenes.V3D')).values():
        for a, b in e: seg(a, b, b'\xff\x00\x00')
    if extra:
        for poly in extra:
            for k in range(len(poly)): seg(poly[k], poly[(k + 1) % len(poly)], b'\x00\xff\xff')
    for s, x, z in labels or []:
        i, j = to(x, z); text(s, int(i) - 4 * len(s), int(j) - 5, b'\x00\xff\xff')
    R.png(out, ow, oh, img)

if __name__ == '__main__':
    a = sys.argv[1:]
    main(float(a[0]), float(a[1]), float(a[2]), float(a[3]), float(a[4]), a[5])

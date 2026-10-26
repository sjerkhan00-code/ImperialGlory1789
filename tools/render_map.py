"""Render the campaign map: the 16 painted tiles plus every province outline and name.

Writes build/map_background.png and build/campaign_map.svg (outlines + labels over the PNG).
Pure Python (no PIL): DXT1 decoded at 1/4 resolution (one pixel per 4x4 block).
"""
import sys, os, struct, zlib, base64, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igmod import V3D, Mng, Gp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPA = os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Gestion', 'Mapa')
OUT = os.path.join(ROOT, 'build')

# world -> texture: u = 0.0001854 x + c_u, v = -0.0002615 z + c_v (fitted from all province meshes)
TILE_W, TILE_H = 1 / 0.0001854, 1 / 0.0002615
X0 = -0.0929299 * TILE_W                 # world x at the left edge of column 0
Z0 = 3.5153 * TILE_H                     # world z at the top edge of row 0
NT = 4                                   # 4 x 4 tiles


def rgb565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def dxt1_thumb(path):
    """1024x1024 DXT1 -> 256x256 RGB (average of the two endpoint colours per block)."""
    d = open(path, 'rb').read()
    w = struct.unpack_from('<I', d, 16)[0]
    nb = w // 4
    out = bytearray(nb * nb * 3)
    p = 128
    for i in range(nb * nb):
        c0, c1 = struct.unpack_from('<HH', d, p)
        a, b = rgb565(c0), rgb565(c1)
        out[3 * i:3 * i + 3] = bytes(((a[0] + b[0]) // 2, (a[1] + b[1]) // 2, (a[2] + b[2]) // 2))
        p += 8
    return nb, out


def png(path, w, h, rgb):
    raw = b''.join(b'\0' + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    def chunk(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def province_outlines(v3d_path):
    """name -> list of boundary edges in world (x, z); edges used by exactly one triangle."""
    d = open(v3d_path, 'rb').read()
    v = V3D(d)
    out = {}
    for st, en, name in v.blocks:
        b = d[st:en]
        f = V3D.mesh_fields(b)
        tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]
        pts = [(x + tx, z + tz) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        cnt = collections.Counter()
        for t in range(0, len(idx), 3):
            a, bb, c = idx[t:t + 3]
            for e in ((a, bb), (bb, c), (c, a)):
                # vertices are duplicated at UV seams: key edges by position, not index
                k = tuple(sorted((tuple(round(q, 1) for q in pts[e[0]]), tuple(round(q, 1) for q in pts[e[1]]))))
                cnt[k] += 1
        out[name] = [k for k, n in cnt.items() if n == 1]
    return out


def main(v3d_path=None, mng_path=None, svg_name='campaign_map.svg'):
    os.makedirs(OUT, exist_ok=True)
    bg = os.path.join(OUT, 'map_background.png')
    S = 256
    W = H = S * NT
    if not os.path.exists(bg):
        img = bytearray(W * H * 3)
        for r in range(NT):
            for c in range(NT):
                # tile row 0 is the southern strip of the map (rows are stored south to north)
                nb, t = dxt1_thumb(os.path.join(MAPA, 'T%03d%03d.tga' % (r, c)))
                for y in range(S):
                    row = ((NT - 1 - r) * S + y) * W + c * S
                    img[row * 3:(row + S) * 3] = t[y * S * 3:(y + 1) * S * 3]
        png(bg, W, H, img)

    v3d_path = v3d_path or os.path.join(MAPA, 'MapaGestionVolumenes.V3D')
    mng_path = mng_path or os.path.join(ROOT, 'data', 'Game', 'GameModes', 'DefModeloGestion.mng')
    outlines = province_outlines(v3d_path)

    m = Mng(open(mng_path, 'rb').read())
    provs = Mng.parse_provinces(m.section(4))
    countries = Mng.parse_countries(m.section(3))
    owner = {}
    for c in countries:
        for p in c['provs']:
            owner[p] = c
    sea = {r['name']: r['sea'] for r in provs}
    pidx = {r['name']: r['idx'] for r in provs}

    def px(x, z):
        return (x - X0) / (TILE_W * NT) * W, (Z0 - z) / (TILE_H * NT) * H

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W * 2, H * 2),
           '<image href="data:image/png;base64,%s" width="%d" height="%d"/>' % (base64.b64encode(open(bg, 'rb').read()).decode(), W, H)]
    for name, edges in outlines.items():
        if not edges:
            continue
        c = owner.get(pidx.get(name))
        col = c['colours'][:3] if c else b'\x80\x80\x80'
        stroke = '#%02x%02x%02x' % (col[0], col[1], col[2]) if not sea.get(name) else '#3a6fb0'
        dash = ' stroke-dasharray="3,2"' if sea.get(name) else ''
        path = ' '.join('M%.1f %.1fL%.1f %.1f' % (*px(*a), *px(*b)) for a, b in edges)
        svg.append('<path d="%s" fill="none" stroke="#000" stroke-width="2.2" opacity="0.6"/>' % path)
        svg.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.2"%s/>' % (path, stroke, dash))
        xs = [px(*p) for e in edges for p in e]
        cx = sum(p[0] for p in xs) / len(xs)
        cy = sum(p[1] for p in xs) / len(xs)
        label = name + ('' if sea.get(name) else ' (%s)' % (c['ltext'].replace('LTEXT_PAIS_', '').title() if c else '?'))
        svg.append('<text x="%.1f" y="%.1f" font-family="Arial" font-size="7" text-anchor="middle" fill="#fff" '
                   'stroke="#000" stroke-width="2" paint-order="stroke">%s</text>' % (cx, cy, label))
    # world grid every 1000 units, to read coordinates off the picture
    for gx in range(0, 21001, 1000):
        x, _ = px(gx, 0)
        svg.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%d" stroke="#fff" stroke-width="0.3" opacity="0.35"/>' % (x, x, H))
        svg.append('<text x="%.1f" y="8" font-size="6" fill="#fff">%d</text>' % (x + 1, gx))
    for gz in range(-1000, 13001, 1000):
        _, y = px(0, gz)
        svg.append('<line x1="0" y1="%.1f" x2="%d" y2="%.1f" stroke="#fff" stroke-width="0.3" opacity="0.35"/>' % (y, W, y))
        svg.append('<text x="1" y="%.1f" font-size="6" fill="#fff">%d</text>' % (y - 1, gz))
    svg.append('</svg>')
    path = os.path.join(OUT, svg_name)
    open(path, 'w', encoding='utf-8').write('\n'.join(svg))
    print('wrote', path, 'and', bg)


if __name__ == '__main__':
    main(*sys.argv[1:])

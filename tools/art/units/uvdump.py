"""Unit model/texture inspection: decode game textures to PNG and draw a model's UV atlas on top of them.

Rubo V3D unit files: material table (0x1000/0x1100 chunks), then one 0x2000 block per mesh (name string right
after the 40-byte header).  Inside a mesh block: 0x2100 {fmt 0x100, stride 8, n} = UVs, 0x2300 = u16 triangle
indices, 0x7000 = rest-pose positions (fmt 2, stride 12).  Cavalry files hold two meshes: the mount
('CaballoEscocesGris' / camel, textured by .TEX) and the rider (textured by .TEX2).

Usage (from the project root):
    python tools/art/units/uvdump.py decode  <texture.dds|.tga> <out.png>
    python tools/art/units/uvdump.py uv      <model.V3D> <out.png> <tex for mesh 0> [<tex for mesh 1> ...]
"""
import os, struct, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import dds as DDS
import tga as TGA


def load_tex(path):
    """Game texture (DDS, or TGA that may really be a DDS) -> PIL RGBA image."""
    with open(path, 'rb') as f:
        magic = f.read(4)
    if magic == b'DDS ':
        w, h, rows = DDS.read_dds(path)
    else:
        w, h, rows = TGA.read_tga(path)
    return Image.frombytes('RGBA', (w, h), b''.join(bytes(r) for r in rows))


def meshes(path):
    """-> list of dict(name, uv=[(u,v)...], tris=[(a,b,c)...], pos=[(x,y,z)...]) in file order."""
    d = open(path, 'rb').read()
    out = []
    p = 0
    while p + 8 <= len(d):
        tag, size = struct.unpack_from('<II', d, p)
        if tag == 0x2000 and 40 < size < len(d) - p + 1:
            n = struct.unpack_from('<H', d, p + 40)[0]
            name = d[p + 42:p + 42 + n - 1].decode('latin1')
            m = dict(name=name, uv=[], tris=[], pos=[])
            q, end = p + 42 + n, p + size
            while q + 20 <= end:
                t, s = struct.unpack_from('<II', d, q)
                if t == 0x2100:
                    fmt, stride, cnt = struct.unpack_from('<3I', d, q + 8)
                    if fmt == 0x100 and stride == 8:
                        m['uv'] = [struct.unpack_from('<2f', d, q + 20 + 8 * i) for i in range(cnt)]
                    elif fmt == 2 and stride == 12:
                        m['pos'] = [struct.unpack_from('<3f', d, q + 20 + 12 * i) for i in range(cnt)]
                    q += s
                elif t == 0x2300:
                    _, cnt = struct.unpack_from('<2I', d, q + 8)
                    idx = struct.unpack_from('<%dH' % cnt, d, q + 16)
                    m['tris'] = [idx[i:i + 3] for i in range(0, cnt - 2, 3)]
                    q += s
                elif t in (0x2400, 0x7000) and s > 8:
                    if t == 0x7000:
                        q += 8          # container: its inner 0x2100 holds the rest positions
                    else:
                        q += s
                else:
                    q += 1          # chunks are not 4-aligned after the name string
            out.append(m)
            p += size
        elif tag == 0x7000 and out and 48 < size < len(d) - p + 1:
            # rest-pose block that follows a mesh block: inner 0x2100 {fmt 2, stride 12} holds positions
            q, end = p + 8, p + size
            while q + 20 <= end:
                t, fmt, stride, cnt = struct.unpack_from('<I4xIII', d, q)
                if t == 0x2100 and fmt == 2 and stride == 12:
                    out[-1]['pos'] = [struct.unpack_from('<3f', d, q + 20 + 12 * i) for i in range(cnt)]
                    break
                q += 1
            p += size
        else:
            p += 1
    return out


def silhouettes(models, out_png, cell=200):
    """Side and front orthographic wireframes of the rest pose, one row per model (name, path, [mesh filter])."""
    rows = []
    for name, path in models:
        ms = [m for m in meshes(path) if m['pos'] and len(m['pos']) == len(m['uv'])]
        pts = [p for m in ms for p in m['pos']]
        if not pts:
            continue
        lo = [min(p[i] for p in pts) for i in range(3)]; hi = [max(p[i] for p in pts) for i in range(3)]
        span = max(hi[i] - lo[i] for i in range(3)) or 1
        s = (cell - 20) / span
        img = Image.new('RGB', (cell * 2, cell), (24, 24, 24))
        dr = ImageDraw.Draw(img)
        for view, ox in (((2, 1), 0), ((0, 1), cell)):   # side: z/y, front: x/y
            a, b = view
            for m in ms:
                for t in m['tris']:
                    poly = [(ox + 10 + (m['pos'][k][a] - lo[a]) * s, cell - 10 - (m['pos'][k][b] - lo[b]) * s) for k in t]
                    dr.polygon(poly, outline=(90, 200, 255))
        dr.text((4, 2), '%s  h=%.0f' % (name, hi[1] - lo[1]), fill=(255, 255, 0))
        rows.append(img)
    sheet = Image.new('RGB', (cell * 2, cell * len(rows)), (24, 24, 24))
    for i, r in enumerate(rows):
        sheet.paste(r, (0, i * cell))
    sheet.save(out_png)


def contact_sheet(items, out_png, size=256, cols=6):
    """items: (label, texture path). Decoded textures in a grid with labels."""
    n = len(items)
    rowsn = (n + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (size + 4), rowsn * (size + 16)), (24, 24, 24))
    dr = ImageDraw.Draw(sheet)
    for i, (label, path) in enumerate(items):
        x, y = (i % cols) * (size + 4), (i // cols) * (size + 16)
        try:
            im = load_tex(path).convert('RGB').resize((size, size))
            sheet.paste(im, (x, y + 14))
        except Exception as e:
            dr.text((x, y + 20), 'ERR %s' % e, fill=(255, 80, 80))
        dr.text((x + 2, y + 1), label, fill=(255, 255, 0))
    sheet.save(out_png)


def uv_overlay(model, textures, out_png, scale=2):
    ms = meshes(model)
    tiles = []
    for i, m in enumerate(ms):
        if not m['uv'] or max(max(t) for t in m['tris']) >= len(m['uv']):
            continue                       # shadow / base meshes without a texture atlas
        tex = textures[min(i, len(textures) - 1)]
        img = load_tex(tex).convert('RGB').resize((256 * scale, 256 * scale), Image.NEAREST)
        dr = ImageDraw.Draw(img, 'RGBA')
        W, H = img.size
        for a, b, c in m['tris']:
            pts = [(m['uv'][k][0] * W, m['uv'][k][1] * H) for k in (a, b, c)]
            dr.polygon(pts, outline=(0, 255, 255, 110))
        dr.text((4, 4), '%s  %s  %d verts %d tris' % (os.path.basename(model), m['name'], len(m['uv']), len(m['tris'])),
                fill=(255, 255, 0, 255))
        tiles.append(img)
    sheet = Image.new('RGB', (sum(t.width for t in tiles) + 4 * (len(tiles) - 1), max(t.height for t in tiles)), (30, 30, 30))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0)); x += t.width + 4
    sheet.save(out_png)
    return ms


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'decode':
        load_tex(sys.argv[2]).save(sys.argv[3])
    elif cmd == 'sil':          # sil <out.png> name=path ...
        silhouettes([a.split('=', 1) for a in sys.argv[3:]], sys.argv[2])
    elif cmd == 'sheet':        # sheet <out.png> label=path ...
        contact_sheet([a.split('=', 1) for a in sys.argv[3:]], sys.argv[2])
    elif cmd == 'uv':
        ms = uv_overlay(sys.argv[2], sys.argv[4:], sys.argv[3])
        for m in ms:
            ys = [p[1] for p in m['pos']] or [0]
            print(m['name'], len(m['uv']), 'verts', len(m['tris']), 'tris, height %.0f..%.0f' % (min(ys), max(ys)))

"""Re-tile the whole campaign map into the game's 4 x 4 texture grid (T00RR0CC.tga, materials 0..15).

The game draws province meshes only with the 16 tile materials, so the bigger map (9 x 7 old tiles) is covered by
16 bigger tiles of 2048 x 2048 px. Every mesh that uses the tile materials (provinces in MapaGestion*.V3D, the
Decorado planes in MapaDecoracion.V3D) is rebuilt: its triangles are clipped to the new tile grid and the texture
coordinates recomputed. The detail coordinates (u2, v2) stay as they are (linear in world position, game formula).
"""
import struct, math, os
import numpy as np
import meshgen as MG
from igmod import v3d_objects, v3d_root

N = 4
X0 = MG.COLS[0]
X1 = MG.COLS[0] + 9 * MG.TILE_W
Z1 = MG.ROWS[4]
Z0 = MG.ROWS[0] - 3 * MG.TILE_H
TW = (X1 - X0) / N
TH = (Z1 - Z0) / N
TEX = 2048


def uv(x, z, r, c):
    """r counted from the south, as in the tile names; v = 0 at the north edge of the tile."""
    return (x - X0) / TW - c, (Z0 + (r + 1) * TH - z) / TH


def uv2(x, z):
    return MG.K2U * x + MG.C2U, MG.C2V - MG.K2V * z


def _clip3(poly, axis, value, keep_greater):
    """Clip a polygon of (x, y, z) points against x (axis 0) or z (axis 2) = value."""
    out = []
    for k in range(len(poly)):
        p, q = poly[k - 1], poly[k]
        pin = (p[axis] >= value) if keep_greater else (p[axis] <= value)
        qin = (q[axis] >= value) if keep_greater else (q[axis] <= value)
        if qin != pin:
            t = (value - p[axis]) / (q[axis] - p[axis])
            out.append(tuple(p[i] + t * (q[i] - p[i]) for i in range(3)))
        if qin:
            out.append(q)
    return out


def split(tris):
    """[(p0, p1, p2)] with p = (x, y, z) world -> {(r, c): [triangles]} on the 4 x 4 grid."""
    res = {}
    e = 1e-6
    for tri in tris:
        xs = [p[0] for p in tri]; zs = [p[2] for p in tri]
        c0 = max(0, int(math.floor((min(xs) - X0) / TW + e))); c1 = min(N - 1, int(math.floor((max(xs) - X0) / TW - e)))
        r0 = max(0, int(math.floor((min(zs) - Z0) / TH + e))); r1 = min(N - 1, int(math.floor((max(zs) - Z0) / TH - e)))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                p = list(tri)
                bx, bz = X0 + c * TW, Z0 + r * TH
                for axis, val, g in ((0, bx, True), (0, bx + TW, False), (2, bz, True), (2, bz + TH, False)):
                    if c == 0 and axis == 0 and g:
                        continue                         # keep geometry beyond the outer map edge in the edge tile
                    if c == N - 1 and axis == 0 and not g:
                        continue
                    if r == 0 and axis == 2 and g:
                        continue
                    if r == N - 1 and axis == 2 and not g:
                        continue
                    p = _clip3(p, axis, val, g)
                    if len(p) < 3:
                        break
                if len(p) >= 3:
                    a = 0.0
                    for k in range(len(p)):
                        a += p[k - 1][0] * p[k][2] - p[k][0] * p[k - 1][2]
                    if abs(a) > 1e-4:
                        for k in range(1, len(p) - 1):
                            res.setdefault((r, c), []).append((p[0], p[k], p[k + 1]))
    return res


def _mesh_layout(d, off):
    p = off + 40
    n = struct.unpack_from('<H', d, p)[0]; p += 2 + n
    n = struct.unpack_from('<H', d, p)[0]; p += 2 + n
    body = p
    vh = body + 252
    group = struct.unpack_from('<I', d, vh - 4)[0]
    flag, size, fmt, stride, nv = struct.unpack_from('<5I', d, vh)
    return body, vh, group, fmt, stride, nv


def rebuild_mesh(blob):
    """Rebuild one tile-material mesh block. Returns (new blob, vertex delta, triangle delta)."""
    d = blob
    body, vh, group, fmt, stride, nv = _mesh_layout(d, 0)
    assert group == 0 and stride == 28 and fmt == 514
    tx, ty, tz = struct.unpack_from('<3f', d, body + 64 + 48)
    verts = [struct.unpack_from('<7f', d, vh + 20 + 28 * k) for k in range(nv)]
    ih = vh + 20 + 28 * nv
    f2, s2, isz, ni = struct.unpack_from('<4I', d, ih)
    assert f2 == 0x2300 and isz == 2
    idx = struct.unpack_from('<%dH' % ni, d, ih + 16)
    th = ih + 16 + 2 * ni
    f3, s3, ns = struct.unpack_from('<3I', d, th)
    assert f3 == 0x2400
    tail = d[th + s3:]
    tris = []
    for t in range(0, ni, 3):
        tris.append(tuple((verts[i][0] + tx, verts[i][1] + ty, verts[i][2] + tz) for i in idx[t:t + 3]))
    pieces = split(tris)
    nverts, nidx, subs = [], [], []
    for (r, c) in sorted(pieces):
        vstart, istart, local = len(nverts), len(nidx), {}
        for tri in pieces[(r, c)]:
            for (x, y, z) in tri:
                key = (round(x, 3), round(y, 3), round(z, 3))
                if key not in local:
                    local[key] = len(nverts)
                    u, v = uv(x, z, r, c)
                    u2, v2 = uv2(x, z)
                    nverts.append((x - tx, y - ty, z - tz, u, v, u2, v2))
                nidx.append(local[key])
        subs.append((vstart, len(nverts) - vstart, istart, (len(nidx) - istart) // 3, r * N + c))
    assert len(nverts) < 65536, len(nverts)
    head = bytearray(d[:vh])
    lx = [q[0] for q in nverts]; ly = [q[1] for q in nverts]; lz = [q[2] for q in nverts]
    struct.pack_into('<6f', head, body + 208, min(lx), min(ly), min(lz), max(lx), max(ly), max(lz))
    cx, cy, cz = (min(lx) + max(lx)) / 2, (min(ly) + max(ly)) / 2, (min(lz) + max(lz)) / 2
    rad = max(math.sqrt((q[0] - cx) ** 2 + (q[1] - cy) ** 2 + (q[2] - cz) ** 2) for q in nverts)
    struct.pack_into('<4f', head, body + 232, cx, cy, cz, rad)
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(nverts), 514, 28, len(nverts)) + b''.join(struct.pack('<7f', *q) for q in nverts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(nidx), 2, len(nidx)) + struct.pack('<%dH' % len(nidx), *nidx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20 * len(subs), len(subs)) + b''.join(struct.pack('<5I', *s) for s in subs)
    out = bytearray(bytes(head) + vsec + isec + tsec + tail)
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out), len(nverts) - nv, len(nidx) // 3 - ni // 3


def rebuild_model(d):
    """Rebuild every tile-material mesh of a map V3D (group 0, 28-byte vertices). Returns (data, count)."""
    d = bytearray(d)
    objs = v3d_objects(bytes(d))
    out = bytearray(d[:v3d_root(bytes(d))])
    dv = dt = n = 0
    for o, cid, size, name, parent in objs:
        blob = bytes(d[o:o + size])
        if cid == 0x2000:
            body, vh, group, fmt, stride, nv = _mesh_layout(blob, 0)
            if group == 0 and stride == 28 and fmt == 514:
                blob, a, b = rebuild_mesh(blob)
                dv += a; dt += b; n += 1
        out += blob
    out += d[objs[-1][0] + objs[-1][2]:]
    for off, delta in ((62, dv), (66, dv), (70, dt)):
        struct.pack_into('<I', out, off, struct.unpack_from('<I', out, off)[0] + delta)
    return bytes(out), n


def mosaic_tile(r, c, tile_png):
    """Image (numpy RGB, TEX x TEX) of new tile (r from the south, c) cut from the 9 x 7 mosaic of 1024 px old tiles.
    tile_png(col, row_from_top) -> path of that old tile's image."""
    from PIL import Image
    S = 1024
    px_w = TW / MG.TILE_W * S; px_h = TH / MG.TILE_H * S        # 2304 x 1792 mosaic px
    left = c * px_w; top = (N - 1 - r) * px_h
    c0, c1 = int(left // S), int(math.ceil((left + px_w) / S)) - 1
    t0, t1 = int(top // S), int(math.ceil((top + px_h) / S)) - 1
    canvas = Image.new('RGB', ((c1 - c0 + 1) * S, (t1 - t0 + 1) * S))
    for row in range(t0, t1 + 1):
        for col in range(c0, c1 + 1):
            canvas.paste(Image.open(tile_png(col, row)).convert('RGB'), ((col - c0) * S, (row - t0) * S))
    box = (left - c0 * S, top - t0 * S, left - c0 * S + px_w, top - t0 * S + px_h)
    img = canvas.crop(tuple(int(round(v)) for v in box)).resize((TEX, TEX), Image.LANCZOS)
    return np.asarray(img)

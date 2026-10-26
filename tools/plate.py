"""Grow the campaign map plate: extra texture tiles and background planes.

V3D facts used (MapaGestion*.V3D, MapaDecoracion.V3D):
  header u32 @4 = header size (234); @62/@66/@70 vertex/vertex/triangle totals, @74 meshes, @90 objects,
  @94 texture-stage refs, @98 material groups, @102 materials; 6 floats @146 = scene bbox (min xyz, max xyz).
  At the header end: {0x1000, size, groups} holding one {0x1100, size, 0, count} per group, each holding
  {0x1110, size, flag u8, index u32, name, ...two texture stages (full path + short name)}.
  A mesh selects its group with the u32 just before its 0x2100 vertex chunk; sub-mesh tile ids are indices
  inside that group. Group 0 holds the 16 map tiles T00RRCC (RR = row from the south, CC = column).
"""
import struct, math
import meshgen as MG
from igmod import ws

TILE_W = MG.COLS[1] - MG.COLS[0]
TILE_H = MG.ROWS[1] - MG.ROWS[0]


def tile_rect(r, c):
    """World rectangle (x0, x1, z0, z1) of tile row r (from the south, may be negative) and column c."""
    x0 = MG.COLS[0] + c * TILE_W
    z0 = MG.ROWS[0] + r * TILE_H
    return x0, x0 + TILE_W, z0, z0 + TILE_H


def root_offset(d):
    hs = struct.unpack_from('<I', d, 4)[0]
    return hs + struct.unpack_from('<I', d, hs + 4)[0]


def add_tile_materials(d, new):
    """new: list of (source material index in group 0, new texture file name of the same length).
    Returns (data, {name: new index})."""
    d = bytearray(d)
    hs = struct.unpack_from('<I', d, 4)[0]
    g0 = hs + 12
    cid, gsize, _z, count = struct.unpack_from('<IIII', d, g0)
    assert cid == 0x1100
    mats, p = {}, g0 + 16
    for _ in range(count):
        c, s = struct.unpack_from('<II', d, p)
        assert c == 0x1110
        mats[struct.unpack_from('<I', d, p + 9)[0]] = bytes(d[p:p + s])
        p += s
    end = p
    add, out = b'', {}
    for k, (src, name) in enumerate(new):
        blob = bytearray(mats[src])
        old = None
        for o in range(len(blob) - 11):
            if blob[o:o + 1] == b'T' and blob[o + 7:o + 11] == b'.tga' and blob[o + 1:o + 7].isdigit():
                old = bytes(blob[o:o + 11]); break
        assert old and len(name) == len(old), (old, name)
        blob = bytearray(bytes(blob).replace(old, name.encode()))
        idx = count + k
        struct.pack_into('<I', blob, 9, idx)
        add += bytes(blob)
        out[name] = idx
    d[end:end] = add
    struct.pack_into('<I', d, g0 + 4, gsize + len(add))
    struct.pack_into('<I', d, g0 + 12, count + len(new))
    struct.pack_into('<I', d, hs + 4, struct.unpack_from('<I', d, hs + 4)[0] + len(add))
    struct.pack_into('<I', d, 102, struct.unpack_from('<I', d, 102)[0] + len(new))
    struct.pack_into('<I', d, 94, struct.unpack_from('<I', d, 94)[0] + 2 * len(new))
    return bytes(d), out


def find_mesh(d, name, parent):
    key = struct.pack('<H', len(name) + 1) + name.encode() + b'\0' + struct.pack('<H', len(parent) + 1) + parent.encode() + b'\0'
    i = d.find(key)
    assert i > 0, name
    st = i - 40
    assert struct.unpack_from('<I', d, st)[0] == 0x2000
    return st, st + struct.unpack_from('<I', d, st + 4)[0], i + len(key)


def plane_mesh(template, name, parent, rects, y, index, step=8):
    """A flat mesh made of tile rectangles: rects = [(r, c, material index)]. Returns (blob, nv, nt)."""
    f = template
    p = 40
    n = struct.unpack_from('<H', f, p)[0]; p += 2 + n
    n = struct.unpack_from('<H', f, p)[0]; p += 2 + n
    body_at = p
    vh = body_at + 252
    allx = [tile_rect(r, c)[k] for r, c, _ in rects for k in (0, 1)]
    allz = [tile_rect(r, c)[k] for r, c, _ in rects for k in (2, 3)]
    tx, tz = (min(allx) + max(allx)) / 2, (min(allz) + max(allz)) / 2
    verts, idx, subs = [], [], []
    for r, c, mat in rects:
        x0, x1, z0, z1 = tile_rect(r, c)
        vstart, istart = len(verts), len(idx)
        for j in range(step + 1):
            for i in range(step + 1):
                x = x0 + (x1 - x0) * i / step
                z = z0 + (z1 - z0) * j / step
                verts.append((x - tx, 0.0, z - tz, MG.KU * x + MG.CU - c, MG.CV + r - MG.KV * z,
                              MG.K2U * x + MG.C2U, MG.C2V - MG.K2V * z))
        for j in range(step):
            for i in range(step):
                a = vstart + j * (step + 1) + i
                b, cc, dd = a + 1, a + step + 1, a + step + 2
                idx += [a, cc, b, b, cc, dd]           # same winding as the game's planes (checked against Decorado06)
        subs.append((vstart, len(verts) - vstart, istart, (len(idx) - istart) // 3, mat))
    head = bytearray(f[:40])
    body = bytearray(f[body_at:vh])
    for mo in (64, 128):
        struct.pack_into('<3f', body, mo + 48, tx, y, tz)
    lx = [v[0] for v in verts]; lz = [v[2] for v in verts]
    struct.pack_into('<6f', body, 208, min(lx), 0.0, min(lz), max(lx), 0.0, max(lz))
    rad = max(math.hypot(v[0], v[2]) for v in verts)
    struct.pack_into('<4f', body, 232, 0.0, 0.0, 0.0, rad)
    vsec = struct.pack('<5I', 0x2100, 20 + 28 * len(verts), 514, 28, len(verts)) + b''.join(struct.pack('<7f', *v) for v in verts)
    isec = struct.pack('<4I', 0x2300, 16 + 2 * len(idx), 2, len(idx)) + struct.pack('<%dH' % len(idx), *idx)
    tsec = struct.pack('<3I', 0x2400, 12 + 20 * len(subs), len(subs)) + b''.join(struct.pack('<5I', *s) for s in subs)
    blob = bytearray(head + ws(name) + ws(parent) + body + vsec + isec + tsec)
    struct.pack_into('<I', blob, 4, len(blob))
    struct.pack_into('<I', blob, 32, 0)
    struct.pack_into('<I', blob, 36, index)
    assert len(verts) < 65536
    return bytes(blob), len(verts), len(idx) // 3


def append_object(d, blob, nv, nt):
    """Append a mesh block before the {0xff, 8} end marker and update the header and root counters."""
    d = bytearray(d)
    assert d[-8:] == b'\xff\x00\x00\x00\x08\x00\x00\x00'
    d[-8:-8] = blob
    for off, delta in ((62, nv), (66, nv), (70, nt), (74, 1), (90, 1)):
        struct.pack_into('<I', d, off, struct.unpack_from('<I', d, off)[0] + delta)
    ro = root_offset(d)
    struct.pack_into('<I', d, ro + 12, struct.unpack_from('<I', d, ro + 12)[0] + 1)
    return bytes(d)


def grow_bbox(d, x0=None, z0=None, x1=None, z1=None):
    d = bytearray(d)
    b = list(struct.unpack_from('<6f', d, 146))
    if x0 is not None: b[0] = min(b[0], x0)
    if z0 is not None: b[2] = min(b[2], z0)
    if x1 is not None: b[3] = max(b[3], x1)
    if z1 is not None: b[5] = max(b[5], z1)
    struct.pack_into('<6f', d, 146, *b)
    return bytes(d)


def mesh_count(d):
    return struct.unpack_from('<I', d, 74)[0]


def test_tile(c, grain, sea, land, edge):
    """1024x1024 RGBA rows: the game's sea with a parchment island and c+1 ink dots (to tell the columns apart)."""
    rows = []
    for y in range(1024):
        row = bytearray(4096)
        g = grain[y]
        for x in range(1024):
            d = math.hypot(x - 512, y - 512) + 18 * math.sin(x / 37.0) * math.cos(y / 29.0)
            if d < 330:
                col = land
            elif d < 352:
                t = (d - 330) / 22
                col = tuple(int(land[k] * (1 - t) + edge[k] * t) for k in range(3))
            else:
                col = sea
            dots = any(math.hypot(x - (512 - 60 * c + 120 * k), y - 512) < 22 for k in range(c + 1))
            if dots:
                col = (60, 40, 25)
            gv = g[x * 4] / 255.0
            row[x * 4:x * 4 + 4] = bytes((int(col[0] * gv), int(col[1] * gv), int(col[2] * gv), 255))
        rows.append(row)
    return rows


def objects(d):
    import igmod as G
    return G.v3d_objects(d, start=root_offset(d))


def mesh_parts(d, off):
    """Offsets inside the mesh block at off: body, vertex header, stride, count."""
    p = off + 40
    n = struct.unpack_from('<H', d, p)[0]; p += 2 + n
    n = struct.unpack_from('<H', d, p)[0]; p += 2 + n
    body = p
    vh = body + 252
    flag, size, fmt, stride, nv = struct.unpack_from('<5I', d, vh)
    assert flag == 0x2100, hex(flag)
    return body, vh, stride, nv


def transform_mesh(d, name, dx=0.0, dz=0.0, sx=1.0, sz=1.0, anchor=None, dy=0.0):
    """Move a mesh by (dx, dz) and scale it in x/z around `anchor` (world x, z; default: its own position)."""
    d = bytearray(d)
    off = next(o for o, cid, sz_, nm, par in objects(d) if nm == name and cid == 0x2000)
    body, vh, stride, nv = mesh_parts(d, off)
    tx, ty, tz = struct.unpack_from('<3f', d, body + 64 + 48)
    ax, az = anchor if anchor else (tx, tz)
    ntx = ax + (tx - ax) * sx + dx
    ntz = az + (tz - az) * sz + dz
    for mo in (64, 128):
        x, y, z = struct.unpack_from('<3f', d, body + mo + 48)
        struct.pack_into('<3f', d, body + mo + 48, x - tx + ntx, y + dy, z - tz + ntz)
    for k in range(nv):
        o = vh + 20 + stride * k
        x, y, z = struct.unpack_from('<3f', d, o)
        struct.pack_into('<3f', d, o, x * sx, y, z * sz)
    bb = list(struct.unpack_from('<6f', d, body + 208))
    struct.pack_into('<6f', d, body + 208, bb[0] * sx, bb[1], bb[2] * sz, bb[3] * sx, bb[4], bb[5] * sz)
    sp = list(struct.unpack_from('<4f', d, body + 232))
    struct.pack_into('<4f', d, body + 232, sp[0] * sx, sp[1], sp[2] * sz, sp[3] * max(sx, sz))
    return bytes(d)


def mesh_world_box(d, name):
    off = next(o for o, cid, sz_, nm, par in objects(d) if nm == name and cid == 0x2000)
    body, vh, stride, nv = mesh_parts(d, off)
    tx, ty, tz = struct.unpack_from('<3f', d, body + 64 + 48)
    bb = struct.unpack_from('<6f', d, body + 208)
    return tx + bb[0], tx + bb[3], tz + bb[2], tz + bb[5]


def stretch_fog(d, new_x1, new_z0):
    """Stretch Niebla.V3D (fog plane: Plane02 with uv only, a 0x6000 object with 46 animation frames of positions,
    a 0x7000 object with the rest positions) from its old extent to x ..new_x1 and z new_z0.., anchored at the
    north-west corner. Every frame is {flag u8 (first only), 4x4 matrix, bbox 6f, sphere 4f, {0x2100,..,2,12,n} xyz}."""
    import igmod as G
    d = bytearray(d)
    ox0, oy0, oz0, ox1, oy1, oz1 = struct.unpack_from('<6f', d, 146)
    sx = (new_x1 - ox0) / (ox1 - ox0); sz = (oz1 - new_z0) / (oz1 - oz0)
    fx = lambda x: ox0 + (x - ox0) * sx
    fz = lambda z: oz1 + (z - oz1) * sz
    def box(o):
        a = list(struct.unpack_from('<6f', d, o))
        struct.pack_into('<6f', d, o, fx(a[0]), a[1], fz(a[2]), fx(a[3]), a[4], fz(a[5]))
        c = list(struct.unpack_from('<4f', d, o + 24))
        struct.pack_into('<4f', d, o + 24, fx(c[0]), c[1], fz(c[2]), c[3] * max(sx, sz))
    def positions(o):
        cid, size, fmt, stride, n = struct.unpack_from('<5I', d, o)
        assert cid == 0x2100 and stride == 12, (hex(cid), stride)
        for k in range(n):
            q = o + 20 + 12 * k
            x, y, z = struct.unpack_from('<3f', d, q)
            struct.pack_into('<3f', d, q, fx(x), y, fz(z))
        return o + size
    objs = G.v3d_objects(bytes(d))
    o6 = next(x for x in objs if x[1] == 0x6000); o7 = next(x for x in objs if x[1] == 0x7000)
    p, end = o6[0] + 21, o6[0] + o6[2]
    frames = 0
    while p < end - 100:
        box(p + 64)
        p = positions(p + 104)
        frames += 1
    box(o7[0] + 8)
    positions(o7[0] + 48)
    plane = next(x for x in objs if x[1] == 0x2000)
    body, vh, stride, nv = mesh_parts(bytes(d), plane[0])
    box(body + 208)
    struct.pack_into('<6f', d, 146, ox0, oy0, fz(oz0), fx(ox1), oy1, oz1)
    return bytes(d), frames

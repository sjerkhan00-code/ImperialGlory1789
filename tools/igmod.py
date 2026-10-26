"""Imperial Glory modding helpers: parsers/serializers for the binary formats.

Formats handled
  DefModeloGestion.mng  - campaign database (chunks of {id,size,count})
  PosicionesMapa.gp     - province click masks on a 70-unit grid
  *.V3D (Rubo)          - map models; per-mesh blocks, copy/transform support
  Text*.sb              - localisation lists (latin1 or UTF-16LE)
  *.pak                 - plain zip archives
"""
import struct, re, zipfile, os, math

# ---------------------------------------------------------------- strings
def rs(d, p):
    n = struct.unpack_from('<H', d, p)[0]
    return d[p + 2:p + 2 + n - 1].decode('latin1'), p + 2 + n

def ws(s):
    b = s.encode('latin1') + b'\0'
    return struct.pack('<H', len(b)) + b

# ---------------------------------------------------------------- .mng
class Chunk:
    def __init__(self, cid, body, cnt):
        self.id, self.body, self.cnt = cid, body, cnt   # cnt None -> 8-byte header only
    def pack(self):
        if self.cnt is None:
            return struct.pack('<II', self.id, 8 + len(self.body)) + self.body
        return struct.pack('<III', self.id, 12 + len(self.body), self.cnt) + self.body

class Mng:
    HDR = 20
    def __init__(self, data):
        self.head = bytes(data[:self.HDR])
        self.chunks = []
        off = self.HDR
        while off < len(data):
            cid, size = struct.unpack_from('<II', data, off)
            if size == 8:
                self.chunks.append(Chunk(cid, b'', None)); off += 8; continue
            cnt = struct.unpack_from('<I', data, off + 8)[0]
            self.chunks.append(Chunk(cid, bytes(data[off + 12:off + size]), cnt))
            off += size
        assert off == len(data)

    def pack(self):
        # head = u32 0, u32 12, f32 version, then group {u32 1, u32 size} whose size spans
        # the 14 enum tables plus their 8-byte end marker (id 14); it must follow their length
        body = [c.pack() for c in self.chunks]
        end = next(i for i, c in enumerate(self.chunks) if c.cnt is None)
        group = 8 + sum(len(b) for b in body[:end + 1])
        return self.head[:16] + struct.pack('<I', group) + b''.join(body)

    # the first 14 chunks are enum tables, the rest are record sections
    def table(self, tid):
        return next(c for c in self.chunks[:14] if c.id == tid)
    def section(self, sid):
        return next(c for c in self.chunks[14:] if c.id == sid)

    @staticmethod
    def parse_enum(chunk):
        p, out = 0, {}
        for _ in range(chunk.cnt):
            idx = struct.unpack_from('<I', chunk.body, p)[0]
            name, p = rs(chunk.body, p + 4)
            out[idx] = name
        assert p == len(chunk.body)
        return out

    @staticmethod
    def enum_add(chunk, idx, name):
        chunk.body += struct.pack('<I', idx) + ws(name); chunk.cnt += 1

    # --- province section (id 4)
    @staticmethod
    def parse_provinces(chunk):
        d, p, recs = chunk.body, 0, []
        for _ in range(chunk.cnt):
            r = {}
            r['idx'] = struct.unpack_from('<I', d, p)[0]
            r['ltext'], p = rs(d, p + 4)
            r['ldesc'], p = rs(d, p)
            r['vals'] = list(struct.unpack_from('<14I', d, p)); p += 56
            r['name'], p = rs(d, p)
            r['model'], p = rs(d, p)
            r['volumes'], p = rs(d, p)
            r['scenario'], p = rs(d, p)
            r['sea'], r['f'], n = struct.unpack_from('<IfI', d, p); p += 12
            r['nb'] = list(struct.unpack_from('<%dI' % n, d, p)); p += 4 * n
            recs.append(r)
        assert p == len(d)
        return recs

    @staticmethod
    def pack_province(r):
        return (struct.pack('<I', r['idx']) + ws(r['ltext']) + ws(r['ldesc'])
                + struct.pack('<14I', *r['vals']) + ws(r['name']) + ws(r['model'])
                + ws(r['volumes']) + ws(r['scenario'])
                + struct.pack('<IfI', r['sea'], r['f'], len(r['nb']))
                + struct.pack('<%dI' % len(r['nb']), *r['nb']))

    @staticmethod
    def set_provinces(chunk, recs):
        chunk.body = b''.join(Mng.pack_province(r) for r in recs); chunk.cnt = len(recs)

    # --- country section (id 3)
    @staticmethod
    def parse_countries(chunk):
        d, p, recs = chunk.body, 0, []
        for _ in range(chunk.cnt):
            r = {}
            r['idx'] = struct.unpack_from('<I', d, p)[0]
            r['ltext'], p = rs(d, p + 4)
            r['flags'] = d[p:p + 3]; p += 3
            n = struct.unpack_from('<I', d, p)[0]; p += 4
            r['provs'] = list(struct.unpack_from('<%dI' % n, d, p)); p += 4 * n
            r['colours'] = d[p:p + 24]; p += 24
            lists = []
            for _ in range(2):
                n = struct.unpack_from('<I', d, p)[0]; p += 4
                lists.append(list(struct.unpack_from('<%dI' % n, d, p))); p += 4 * n
            r['lists'] = lists
            recs.append(r)
        assert p == len(d)
        return recs

    @staticmethod
    def pack_country(r):
        out = struct.pack('<I', r['idx']) + ws(r['ltext']) + r['flags']
        out += struct.pack('<I', len(r['provs'])) + struct.pack('<%dI' % len(r['provs']), *r['provs'])
        out += r['colours']
        for l in r['lists']:
            out += struct.pack('<I', len(l)) + struct.pack('<%dI' % len(l), *l)
        return out

    @staticmethod
    def set_countries(chunk, recs):
        chunk.body = b''.join(Mng.pack_country(r) for r in recs); chunk.cnt = len(recs)

    # --- map object positions (id 13): (type, province, x, y, z, 0)
    @staticmethod
    def parse_positions(chunk):
        return [struct.unpack_from('<IIfffI', chunk.body, 24 * i) for i in range(chunk.cnt)]
    @staticmethod
    def add_position(chunk, typ, prov, x, y, z):
        chunk.body += struct.pack('<IIfffI', typ, prov, x, y, z, 0); chunk.cnt += 1

# ---------------------------------------------------------------- .gp
class Gp:
    def __init__(self, data):
        self.head = bytes(data[:16])
        cnt = struct.unpack_from('<I', data, 16)[0]
        off, self.recs = 20, []
        for _ in range(cnt):
            name, p = rs(data, off)
            pid = struct.unpack_from('<I', data, p)[0]
            x, y, w, h = struct.unpack_from('<4f', data, p + 4)
            c1, c2 = struct.unpack_from('<II', data, p + 20); p += 28
            mask = bytes(data[p:p + c1 * c2]); p += c1 * c2
            self.recs.append(dict(name=name, pid=pid, x=x, y=y, w=w, h=h, c1=c1, c2=c2, mask=mask))
            off = p
        assert off == len(data)

    def pack(self):
        out = self.head + struct.pack('<I', len(self.recs))
        for r in self.recs:
            out += ws(r['name']) + struct.pack('<I4fII', r['pid'], r['x'], r['y'], r['w'], r['h'], r['c1'], r['c2']) + r['mask']
        return out

    def add(self, name, x, y, w, h, shape):
        """shape(u, v) -> bool, u/v in 0..1 from west/south (mask row 0 = z0, as the engine reads it)."""
        c1, c2 = math.ceil(w / 70), math.ceil(h / 70)
        mask = bytearray(c1 * c2)
        for r in range(c2):
            for c in range(c1):
                if shape((c + 0.5) / c1, (r + 0.5) / c2):
                    mask[r * c1 + c] = 1
        self.recs.append(dict(name=name, pid=len(self.recs), x=float(x), y=float(y), w=float(w), h=float(h), c1=c1, c2=c2, mask=bytes(mask)))

# ---------------------------------------------------------------- .V3D
class V3D:
    """Rubo V3D with meshes parented to 'MapaGestion'. Only the needed parts are modelled."""
    ROOT_CHILDCOUNT = 5249      # u32: number of province meshes under the root
    H_A, H_VERTS, H_TRIS, H_MESHES, H_OBJS = 62, 66, 70, 74, 90

    def __init__(self, data):
        self.d = bytearray(data)
        self.blocks = []            # (start, end, name)
        marks = []
        for m in re.finditer(rb'\x0c\x00MapaGestion\x00', self.d):
            e = m.start() - 1; s = e
            while 0x20 <= self.d[s - 1] < 0x7f: s -= 1
            name = self.d[s:e].decode()
            lo = s - 2
            if struct.unpack_from('<H', self.d, lo)[0] == len(name) + 1:
                marks.append((lo - 40, name))
        for st, name in marks:
            assert struct.unpack_from('<I', self.d, st)[0] == 0x2000
            size = struct.unpack_from('<I', self.d, st + 4)[0]
            self.blocks.append((st, st + size, name))
        # objects (meshes, fog dummies in MapaGestion.V3D) run up to the {0xff, 8} end marker;
        # new meshes are appended just before it
        assert self.d[-8:] == b'\xff\x00\x00\x00\x08\x00\x00\x00'
        self.tail = bytes(self.d[-8:])
        del self.d[-8:]

    def block(self, name):
        return next(b for b in self.blocks if b[2] == name)

    @staticmethod
    def mesh_fields(blob):
        """Offsets inside a block blob (after the 40-byte header + two strings)."""
        p = 40
        n = struct.unpack_from('<H', blob, p)[0]; p += 2 + n
        n = struct.unpack_from('<H', blob, p)[0]; p += 2 + n
        body = p
        vh = body + 252
        flag, size, fmt, stride, nv = struct.unpack_from('<5I', blob, vh)
        assert flag == 0x2100 and stride == 28
        ih = vh + 20 + stride * nv
        f2, s2, isz, ni = struct.unpack_from('<4I', blob, ih)
        assert f2 == 0x2300
        return dict(body=body, vh=vh, vdata=vh + 20, nv=nv, ih=ih, ni=ni)

    def clone_mesh(self, src_name, new_name, tx, tz, sx, sz, dy=0.0):
        """Append a copy of mesh src_name, renamed, scaled (sx, sz) in local space and placed at (tx, tz)."""
        st, en, _ = self.block(src_name)
        src = bytes(self.d[st:en])
        f = self.mesh_fields(src)
        hdr = bytearray(src[:40])
        body = bytearray(src[f['body']:])
        # matrices: m1 at 0, m2 at 64, m3 at 128; translation row at +48 (x), +52 (y), +56 (z)
        for mo in (64, 128):
            struct.pack_into('<f', body, mo + 48, tx)
            struct.pack_into('<f', body, mo + 56, tz)
            struct.pack_into('<f', body, mo + 52, struct.unpack_from('<f', body, mo + 52)[0] + dy)
        # bbox at 208 (6f), sphere at 232 (4f)
        bb = list(struct.unpack_from('<6f', body, 208))
        bb = [bb[0] * sx, bb[1], bb[2] * sz, bb[3] * sx, bb[4], bb[5] * sz]
        struct.pack_into('<6f', body, 208, *bb)
        sc = list(struct.unpack_from('<4f', body, 232))
        struct.pack_into('<4f', body, 232, sc[0] * sx, sc[1], sc[2] * sz, sc[3] * max(sx, sz))
        vd = f['vdata'] - f['body']
        for i in range(f['nv']):
            o = vd + 28 * i
            x, y, z = struct.unpack_from('<3f', body, o)
            struct.pack_into('<3f', body, o, x * sx, y, z * sz)
        blob = bytes(hdr) + ws(new_name) + ws('MapaGestion') + bytes(body)
        blob = bytearray(blob)
        struct.pack_into('<I', blob, 4, len(blob))                 # block size
        struct.pack_into('<I', blob, 36, len(self.blocks))         # mesh index
        self.d += blob
        self.blocks.append((len(self.d) - len(blob), len(self.d), new_name))
        # global counters
        for off, delta in ((self.H_A, f['nv']), (self.H_VERTS, f['nv']), (self.H_TRIS, f['ni'] // 3),
                           (self.H_MESHES, 1), (self.H_OBJS, 1), (v3d_root(self.d) + 12, 1)):
            struct.pack_into('<I', self.d, off, struct.unpack_from('<I', self.d, off)[0] + delta)
        return f['nv'], f['ni'] // 3

    def pack(self):
        return bytes(self.d) + self.tail

# ---------------------------------------------------------------- text .sb
def text_add_entries(raw, entries):
    """Append [ .KEY "value" ] lines before the final ']' of a localisation file. Keeps encoding."""
    if raw[:2] == b'\xff\xfe':
        enc, bom = 'utf-16-le', b'\xff\xfe'; txt = raw[2:].decode(enc)
    else:
        enc, bom = 'latin1', b''; txt = raw.decode(enc)
    i = txt.rstrip().rfind(']')
    lines = ''.join('\t[ .%s\t"%s" ]\r\n' % (k, v) for k, v in entries)
    txt = txt[:i] + lines + txt[i:]
    return bom + txt.encode(enc)

# ---------------------------------------------------------------- script .sb blocks
def find_block(txt, start):
    """Return (a, b) of the bracket block starting at the first '[' at/after start; comments ignored."""
    a = txt.index('[', start)
    depth, i = 0, a
    while i < len(txt):
        c = txt[i]
        if c == '#':
            i = txt.index('\n', i)
        elif c == '"':
            i = txt.index('"', i + 1)
        elif c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return a, i + 1
        i += 1
    raise ValueError('unbalanced')

# ---------------------------------------------------------------- pak
def write_pak(path, root):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, dns, fns in os.walk(root):
            rel = os.path.relpath(dp, root).replace('\\', '/')
            if rel != '.':
                z.writestr(rel + '/', b'')
            for fn in sorted(fns):
                full = os.path.join(dp, fn)
                z.write(full, (rel + '/' + fn) if rel != '.' else fn)


def v3d_root(d):
    """Offset of the root object: header size + size of the material chunk that follows the header."""
    hs = struct.unpack_from('<I', d, 4)[0]
    return hs + struct.unpack_from('<I', d, hs + 4)[0]


def v3d_objects(d, start=None):
    """Walk the object chunks of a map V3D from the root to the {0xff, 8} end marker.
    Returns (offset, chunk id, size, name, parent)."""
    o, out = (v3d_root(d) if start is None else start), []
    while True:
        cid, sz = struct.unpack_from('<II', d, o)
        if cid == 0xff:
            return out
        p = o + (40 if cid == 0x2000 else 20)
        name, p = rs(d, p)
        parent, p = rs(d, p)
        out.append((o, cid, sz, name, parent))
        o += sz


def clone_fog_dummies(v, src_parent, new_parent, tx, tz, sx, sz, dy, first_index):
    """Copy the fog-of-war control points (Dummy objects) of src_parent onto new_parent in a
    MapaGestion.V3D (V3D instance), applying the same placement as clone_mesh. Returns the count."""
    d = bytes(v.d) + v.tail
    objs = v3d_objects(d)
    next_id = len(objs)                          # ids are sequential from the root (0), so the next one is the count
    src = [o for o in objs if o[1] == 0x5000 and o[4] == src_parent]
    added = 0
    for k, (o, cid, size, name, parent) in enumerate(src):
        blob = bytearray(d[o:o + size])
        p = 20 + 2 + len(name) + 1 + 2 + len(parent) + 1
        body = bytearray(blob[p:])
        lx, ly, lz = struct.unpack_from('<3f', body, 128 + 48)          # matrix 3 = local offset
        ox, oy, oz = struct.unpack_from('<3f', body, 64 + 48)           # matrix 2 = world position
        nl = (lx * sx, ly, lz * sz)
        nw = (tx + nl[0], oy + dy, tz + nl[2])
        struct.pack_into('<3f', body, 128 + 48, *nl)
        struct.pack_into('<3f', body, 64 + 48, *nw)
        # after the matrices: STR 'Dummy', 6f local box, 6f world box stored as (x, z, y)
        q = 192 + 2 + struct.unpack_from('<H', body, 192)[0] + 24
        wb = list(struct.unpack_from('<6f', body, q))
        dx, dz, dyy = nw[0] - ox, nw[2] - oz, nw[1] - oy
        wb = [wb[0] + dx, wb[1] + dz, wb[2] + dyy, wb[3] + dx, wb[4] + dz, wb[5] + dyy]
        struct.pack_into('<6f', body, q, *wb)
        head = bytearray(blob[:20])
        struct.pack_into('<I', head, 16, next_id + k)
        new = head + ws('Niebla%d' % (first_index + k)) + ws(new_parent) + body
        struct.pack_into('<I', new, 4, len(new))
        v.d += new
        added += 1
    for off in (V3D.H_OBJS, 86):                 # object count, dummy count
        struct.pack_into('<I', v.d, off, struct.unpack_from('<I', v.d, off)[0] + added)
    return added


def v3d_canonical(v):
    """Rewrite the object list of a map V3D the way the exporter writes it: root, then every province mesh in
    case-insensitive name order, each followed directly by its own Dummy children. Mesh index (+36) = rank in
    that order, child count (+32) = number of dummies that follow, dummy id (+16) = position in the file.
    The game relies on this layout (wrong child counts make it read the next mesh as a child, and the mesh
    index order is used as a sorted name table)."""
    d = bytes(v.d) + v.tail
    objs = v3d_objects(d)
    root, rest = objs[0], objs[1:]
    assert root[1] == 0x5000 and root[3] == 'MapaGestion'
    meshes = [o for o in rest if o[1] == 0x2000]
    kids = {}
    for o in rest:
        if o[1] == 0x5000:
            kids.setdefault(o[4], []).append(o)
    assert all(p in {m[3] for m in meshes} for p in kids), 'dummy with unknown parent'
    meshes.sort(key=lambda o: o[3].lower())
    out = bytearray(d[:root[0]]) + d[root[0]:root[0] + root[2]]
    pos = 1
    for rank, m in enumerate(meshes):
        blob = bytearray(d[m[0]:m[0] + m[2]])
        ch = kids.get(m[3], [])
        struct.pack_into('<I', blob, 32, len(ch))
        struct.pack_into('<I', blob, 36, rank)
        out += blob; pos += 1
        for c in ch:
            cb = bytearray(d[c[0]:c[0] + c[2]])
            struct.pack_into('<I', cb, 16, pos)
            out += cb; pos += 1
    assert pos == len(objs)
    struct.pack_into('<I', out, root[0] + 12, len(meshes))
    v.d = out
    v.blocks = []                                   # offsets changed; rebuild if needed
    return len(meshes)


# ---------------------------------------------------------------- .mng players (section 2)
def parse_players(chunk):
    d, p, recs = chunk.body, 0, []
    for _ in range(chunk.cnt):
        r = {}
        r['idx'] = struct.unpack_from('<I', d, p)[0]
        r['ltext'], p = rs(d, p + 4)
        r['info'], p = rs(d, p)
        r['country'] = struct.unpack_from('<I', d, p)[0]
        r['start'] = list(struct.unpack_from('<5I', d, p + 4)); p += 24
        n = struct.unpack_from('<I', d, p)[0]; p += 4
        r['objects'] = [list(struct.unpack_from('<5I', d, p + 20 * k)) for k in range(n)]; p += 20 * n
        n = struct.unpack_from('<I', d, p)[0]; p += 4
        armies = []
        for _ in range(n):
            a = {'province': struct.unpack_from('<I', d, p)[0]}
            a['name'], p = rs(d, p + 4)
            a['officer_name'], p = rs(d, p)
            a['officer'], a['zero'], nu = struct.unpack_from('<3I', d, p); p += 12
            units = []
            for _ in range(nu):
                un, p = rs(d, p)
                t, z = struct.unpack_from('<2I', d, p); p += 8
                units.append([un, t, z])
            a['units'] = units
            armies.append(a)
        r['armies'] = armies
        r['tail'] = d[p:p + 8]; p += 8
        recs.append(r)
    assert p == len(d), (p, len(d))
    return recs


def pack_players(chunk, recs):
    out = b''
    for r in recs:
        out += struct.pack('<I', r['idx']) + ws(r['ltext']) + ws(r['info']) + struct.pack('<I5I', r['country'], *r['start'])
        out += struct.pack('<I', len(r['objects'])) + b''.join(struct.pack('<5I', *o) for o in r['objects'])
        out += struct.pack('<I', len(r['armies']))
        for a in r['armies']:
            out += struct.pack('<I', a['province']) + ws(a['name']) + ws(a['officer_name'])
            out += struct.pack('<3I', a['officer'], a['zero'], len(a['units']))
            out += b''.join(ws(u[0]) + struct.pack('<2I', u[1], u[2]) for u in a['units'])
        out += r['tail']
    chunk.body = out; chunk.cnt = len(recs)


# ---------------------------------------------------------------- .mng capitals (section 5)
def parse_capitals(chunk):
    d, p, recs = chunk.body, 0, []
    for _ in range(chunk.cnt):
        r = {'idx': struct.unpack_from('<I', d, p)[0]}
        r['ltext'], p = rs(d, p + 4)
        r['s1'], p = rs(d, p)
        r['s2'], p = rs(d, p)
        r['pos'] = list(struct.unpack_from('<3f', d, p))
        r['level'], n = struct.unpack_from('<2I', d, p + 12)
        r['blds'] = list(struct.unpack_from('<%dI' % n, d, p + 20)); p += 20 + 4 * n
        recs.append(r)
    assert p == len(d)
    return recs


def pack_capitals(chunk, recs):
    chunk.body = b''.join(struct.pack('<I', r['idx']) + ws(r['ltext']) + ws(r['s1']) + ws(r['s2'])
                          + struct.pack('<3f2I', *r['pos'], r['level'], len(r['blds']))
                          + struct.pack('<%dI' % len(r['blds']), *r['blds']) for r in recs)
    chunk.cnt = len(recs)


def text_set_values(raw, values):
    """Replace the values of existing [ .KEY "value" ] entries (dict key -> new value). Keeps encoding."""
    if raw[:2] == b'\xff\xfe':
        enc, bom = 'utf-16-le', b'\xff\xfe'; txt = raw[2:].decode(enc)
    else:
        enc, bom = 'latin1', b''; txt = raw.decode(enc)
    found = set()
    for key, val in values.items():
        pat = re.compile(r'(\[\s*\.' + re.escape(key) + r'\s+")[^"]*(")')
        txt, n = pat.subn(lambda m: m.group(1) + val + m.group(2), txt)
        if n:
            found.add(key)
    return bom + txt.encode(enc), found


# ---------------------------------------------------------------- .mng generic records (sections 7, 9, 15)
def _rec_troop(d, p):
    s = p; p += 4
    for _ in range(4):
        _, p = rs(d, p)
    return p + 4 + 23 * 4


def _rec_ship(d, p):
    p += 4
    for _ in range(4):
        _, p = rs(d, p)
    return p + 30 * 4


def _rec_building(d, p):
    p += 4
    for _ in range(3):
        _, p = rs(d, p)
    p += 11 * 4
    _, p = rs(d, p)
    for _ in range(2):
        n = struct.unpack_from('<I', d, p)[0]; p += 4 + 4 * n
    return p


def split_records(chunk, kind):
    f = {'troop': _rec_troop, 'ship': _rec_ship, 'building': _rec_building}[kind]
    d, p, out = chunk.body, 0, []
    for _ in range(chunk.cnt):
        q = f(d, p); out.append(bytearray(d[p:q])); p = q
    assert p == len(d), (kind, p, len(d))
    return out


def rec_strings(rec, n):
    """(list of the first n strings, offset after them) of a record that starts with u32 idx."""
    p, out = 4, []
    for _ in range(n):
        s, p = rs(rec, p); out.append(s)
    return out, p


def rec_rebuild(rec, n, strings, idx=None):
    """Replace the first n strings (and optionally idx) of a record, keeping the rest."""
    _, p = rec_strings(rec, n)
    head = struct.pack('<I', struct.unpack_from('<I', rec, 0)[0] if idx is None else idx)
    return bytearray(head + b''.join(ws(s) for s in strings) + rec[p:])

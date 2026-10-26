"""Imperial Glory battle map (.lvl, LVLFMT 186) parser and writer.

Exact byte round trip: every chunk is decoded into plain Python data and encoded back; `selftest()` checks
encode(decode(x)) == x for each chunk of every original map.

Format sources (2026-10-21):
  [W] Pyro's own loader source, github.com/chnickiz/Imperial-Glory sourceloaderlvl/ (LVLFormat.h, svcEscenario,
      svcMapaFisico, svcMapaLogico, svcMapaSegmentos, svcObjetosMapa, CommonDataSonido), v186 = 11 Feb 2005.
  [V] the retail exe (re_tools/target/ImperialGlory.exe) where the public source stops:
      scenario loader FUN_00524xxx (chunk loop at 0x5243xx), terrain ITerrain::load FUN_00460d80 (+ octree reader
      FUN_0047b750), object instance loaders = vtable slot +0x18: CObjetoBase 0x4d1f60, CConstruccion 0x4a7720,
      CWater 0x528ef0 (+ vertex colours 0x528d30), CIce 0x5288c0; sector map FUN_0048e7e0 (+ special height geometry
      FUN_004af000); AI graph FUN_00499230; victory conditions FUN_004ad420.

Chunk = {u32 id, u32 size incl. the 8-byte header}; containers 0xA000 / 0xB000 / 0xB100 nest; strings are
{u16 n, n bytes incl. the NUL}.

Usage:
    import lvl
    m = lvl.load(path)                  # Lvl
    m.heights()                         # numpy (181, 181) float32, cm, [z][x]
    m.set_heights(h, shade)             # HEIGHTMAP, terrain VB y (+ vertex shade), picking-tree bounds,
                                        # (carry=True) troop areas / locations / objects follow the ground
    m.cells(); m.set_cells(t, p)        # cell grid (all originals: one type, only the border ring blocked)
    shift_instance(o, dx, dy, dz)       # move an object incl. every position a construction stores
    m.remove_instances([...])           # delete objects, renumber building ids in the victory conditions
    m.remap_sector_ids({old: new})      # after a new sector map (tools/lvl_nav.py): construction sector lists
    m.save(path)
    python tools/lvl.py selftest        # round trip of every original map (56 files, byte-exact)
    python tools/lvl.py info <map.lvl>
    python tools/lvl.py check <map.lvl> # consistency of a new map and its scenario folder
Companions: lvl_nav.py (sector map / navmesh + AI graph), lvl_tex.py (tiles, previews, texture synthesis),
lvl_v3d.py (move trees in Arboles.V3D), lvl_caucasus.py (prototype map), lvl_region.py (regional maps from recipes),
battlemaps.py (make_map step).
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# chunk ids (LVLFormat.h)
HEADER, PHYSICMAP, TERRAIN, HEIGHTMAP, ENDPHYSIC = 0xEBAC, 0xA000, 0xA100, 0xA300, 0xAFFF
OBJECTLIST = 0x1000
LOGIC, LOGICMAP, TERRAINLOGIC, POSTROOPER, LOCATIONS, ZONES, ARBZONES, SEGMENTMAP, SECTORMAP, GRAFOIA = \
    0xB000, 0xB100, 0xB200, 0xB210, 0xB220, 0xB230, 0xB240, 0xB250, 0xB260, 0xB270
ENDLOGICMAP, ENDLOGIC, ENVIRONMENT, SOUND, CONDICIONES, END = 0xB1FF, 0xBFFF, 0xC000, 0xD000, 0xE000, 0xFF
CONTAINERS = {PHYSICMAP, LOGIC, LOGICMAP}
NAMES = {HEADER: 'HEADER', PHYSICMAP: 'PHYSICMAP', TERRAIN: 'TERRAIN', HEIGHTMAP: 'HEIGHTMAP', ENDPHYSIC: 'ENDPHYSIC',
         OBJECTLIST: 'OBJECTLIST', LOGIC: 'LOGIC', LOGICMAP: 'LOGICMAP', TERRAINLOGIC: 'TERRAINLOGIC',
         POSTROOPER: 'POSTROOPER', LOCATIONS: 'LOCATIONS', ZONES: 'ZONES', ARBZONES: 'ARBZONES',
         SEGMENTMAP: 'SEGMENTMAP', SECTORMAP: 'SECTORMAP', GRAFOIA: 'GRAFOIA', ENDLOGICMAP: 'ENDLOGICMAP',
         ENDLOGIC: 'ENDLOGIC', ENVIRONMENT: 'ENVIRONMENT', SOUND: 'SOUND', CONDICIONES: 'CONDICIONES', END: 'END'}

# object types (svcObjetosMapa.h eTipoObjeto: "do not change the order, read from the .LVL")
TO_DECORADO, TO_CONSTRUCCION, TO_ARBOL, TO_AGUA, TO_HIELO = 0, 1, 2, 3, 4
# victory sub-condition types [V FUN_004ad420]: 1 annihilation %, 2 protect zone (ARBZONES name), 3/4 destroy /
# protect building (object instance index), 5 keep troops %
SUB_NONE, SUB_ANIQUILACION, SUB_PROTECCION_ZONA, SUB_DESTRUCCION_EDIF, SUB_PROTECCION_EDIF, SUB_MANTENER_TROPAS = range(6)
# troop position flags [W svcEscenario findPosInicioTropa; values V from the maps]
FPT_INICIO, FPT_REFUERZOS = 0x1, 0x2


class Str(str):
    """A string field whose raw bytes are not 'text + one NUL' (kept verbatim for the round trip)."""
    raw = b''


# ------------------------------------------------------------------ binary reader / writer
class R:
    def __init__(self, b, o=0, end=None):
        self.b, self.o, self.end = b, o, len(b) if end is None else end

    def take(self, n):
        v = self.b[self.o:self.o + n]
        assert len(v) == n and self.o + n <= self.end, 'read past end'
        self.o += n
        return v

    def u8(self): return self.take(1)[0]
    def u16(self): return struct.unpack('<H', self.take(2))[0]
    def u32(self): return struct.unpack('<I', self.take(4))[0]
    def i32(self): return struct.unpack('<i', self.take(4))[0]
    def f32(self): return struct.unpack('<f', self.take(4))[0]
    def fs(self, n): return list(struct.unpack('<%df' % n, self.take(4 * n)))
    def us(self, n): return list(struct.unpack('<%dI' % n, self.take(4 * n)))

    def s(self):
        n = self.u16()
        raw = self.take(n)
        if n and raw[-1] == 0 and 0 not in raw[:-1]:
            return raw[:-1].decode('latin1')
        v = Str(raw.decode('latin1'))
        v.raw = raw
        return v

    def left(self): return self.end - self.o


class W:
    def __init__(self):
        self.p = []

    def raw(self, b): self.p.append(bytes(b))
    def u8(self, v): self.p.append(bytes((v,)))
    def u16(self, v): self.p.append(struct.pack('<H', v))
    def u32(self, v): self.p.append(struct.pack('<I', v))
    def i32(self, v): self.p.append(struct.pack('<i', v))
    def f32(self, v): self.p.append(struct.pack('<f', v))
    def fs(self, v): self.p.append(struct.pack('<%df' % len(v), *v))
    def us(self, v): self.p.append(struct.pack('<%dI' % len(v), *v))

    def s(self, v):
        raw = v.raw if isinstance(v, Str) else v.encode('latin1') + b'\0'
        self.u16(len(raw)); self.p.append(raw)

    def bytes(self): return b''.join(self.p)


# ------------------------------------------------------------------ chunk codecs
# each: dec(R, version) -> dict ; enc(W, dict, version)

def dec_header(r, v):
    return dict(version=r.u32(), reserved=r.take(124))


def enc_header(w, d, v):
    w.u32(d['version']); w.raw(d['reserved'])


def _dec_octree(r):
    n = r.u32()
    node = dict(bbox=r.fs(6), sphere=r.fs(4))
    nf = r.u32()
    node['items'] = r.us(nf)
    node['children'] = [_dec_octree(r) for _ in range(n)]
    return node


def _enc_octree(w, node):
    w.u32(len(node['children'])); w.fs(node['bbox']); w.fs(node['sphere'])
    w.u32(len(node['items'])); w.us(node['items'])
    for c in node['children']:
        _enc_octree(w, c)


def dec_terrain(r, v):
    """ITerrain::load [V FUN_00460d80]: grid, VB (fvf 0x242 = XYZ|DIFFUSE|TEX2, stride 32), 16-bit IB, subsets
    {firstVertex, numVertices, startIndex, numPrims, material}, a binary space tree whose leaves list subset
    indices (ray picking), materials {detail, detail, tile texture}."""
    d = dict(cells=r.us(3), tiles=r.us(2), cell_size=r.fs(2), origin=r.fs(3), size=r.fs(2))
    fvf, stride, n = r.u32(), r.u32(), r.u32()
    d['vb'] = dict(fvf=fvf, stride=stride, data=bytearray(r.take(stride * n)))
    isz, ni = r.u32(), r.u32()
    d['ib'] = dict(isize=isz, data=bytearray(r.take(isz * ni)))
    d['subsets'] = [r.us(5) for _ in range(r.u32())]
    d['octree'] = _dec_octree(r)
    d['materials'] = [[r.s(), r.s(), r.s()] for _ in range(r.u32())]
    return d


def enc_terrain(w, d, v):
    w.us(d['cells']); w.us(d['tiles']); w.fs(d['cell_size']); w.fs(d['origin']); w.fs(d['size'])
    vb = d['vb']
    w.u32(vb['fvf']); w.u32(vb['stride']); w.u32(len(vb['data']) // vb['stride']); w.raw(vb['data'])
    ib = d['ib']
    w.u32(ib['isize']); w.u32(len(ib['data']) // ib['isize']); w.raw(ib['data'])
    w.u32(len(d['subsets']))
    for s in d['subsets']:
        w.us(s)
    _enc_octree(w, d['octree'])
    w.u32(len(d['materials']))
    for m in d['materials']:
        for s in m:
            w.s(s)


def dec_heightmap(r, v):
    nx, nz = r.u32(), r.u32()
    return dict(nx=nx, nz=nz, data=bytearray(r.take(4 * nx * nz)))


def enc_heightmap(w, d, v):
    w.u32(d['nx']); w.u32(d['nz']); w.raw(d['data'])


def _dec_volume(r, v):
    vol = dict(use_previous=r.u8() if v >= 150 else 0)
    if vol['use_previous']:
        return vol
    vol['name'] = r.s()
    vol['sphere'] = r.fs(4)
    vol['bbox'] = r.fs(6)
    nv, ni = r.u32(), r.u32()
    vol['verts'] = r.fs(3 * nv)
    vol['idx'] = list(struct.unpack('<%dH' % ni, r.take(2 * ni)))
    return vol


def _enc_volume(w, vol, v):
    if v >= 150:
        w.u8(vol['use_previous'])
    if vol['use_previous']:
        return
    w.s(vol['name']); w.fs(vol['sphere']); w.fs(vol['bbox'])
    w.u32(len(vol['verts']) // 3); w.u32(len(vol['idx'])); w.fs(vol['verts'])
    w.raw(struct.pack('<%dH' % len(vol['idx']), *vol['idx']))


def _pos(r):
    """TPosMundo-like record read by CConstruccion: vec3, u32 (sector id), bool."""
    return [r.fs(3), r.u32(), r.u8()]


def _wpos(w, p):
    w.fs(p[0]); w.u32(p[1]); w.u8(p[2])


def _dec_colours(r):
    """CWater/CIce per-vertex colours [V 0x528d30]: per mesh, per subset {first, n, n colours}."""
    return [[[r.u32(), r.us(r.u32())] for _ in range(r.u32())] for _ in range(r.u32())]


def _enc_colours(w, c):
    w.u32(len(c))
    for mesh in c:
        w.u32(len(mesh))
        for first, cols in mesh:
            w.u32(first); w.u32(len(cols)); w.us(cols)


def _dec_flank(r, v):
    f = dict(a=r.u32(), b=list(r.take(3)))
    f['c'] = r.u8() if v == 0x83 else r.u32()
    f['d'] = list(r.take(2))
    f['ids'] = r.us(r.u32())
    return f


def _enc_flank(w, f, v):
    w.u32(f['a']); w.raw(bytes(f['b']))
    (w.u8 if v == 0x83 else w.u32)(f['c'])
    w.raw(bytes(f['d'])); w.u32(len(f['ids'])); w.us(f['ids'])


def _dec_module(r, v):
    """One module of a construction instance [V CConstruccion::load 0x4a7b10..0x4a832a]."""
    m = dict(name=r.s(), life=r.i32())
    if v >= 0x6d:
        m['a'] = r.us(2)
    m['b'] = r.us(2)
    if v >= 0xb4:
        m['posts1'] = [_pos(r) for _ in range(r.u32())]
    m['p1'] = _pos(r)
    if v >= 0x67:
        if v >= 0xb4:
            m['posts2'] = [_pos(r) for _ in range(r.u32())]
        m['p2'] = _pos(r)
    if v >= 0xb4:
        m['p3'] = _pos(r)
    if v >= 0x6e:
        m['c'] = r.us(3)
    if v >= 0x83:
        m['flanks'] = [_dec_flank(r, v) for _ in range(2)]
    if v >= 0xaa:
        m['d'] = r.fs(3)
    return m


def _enc_module(w, m, v):
    w.s(m['name']); w.i32(m['life'])
    if v >= 0x6d:
        w.us(m['a'])
    w.us(m['b'])
    if v >= 0xb4:
        w.u32(len(m['posts1']))
        for p in m['posts1']:
            _wpos(w, p)
    _wpos(w, m['p1'])
    if v >= 0x67:
        if v >= 0xb4:
            w.u32(len(m['posts2']))
            for p in m['posts2']:
                _wpos(w, p)
        _wpos(w, m['p2'])
    if v >= 0xb4:
        _wpos(w, m['p3'])
    if v >= 0x6e:
        w.us(m['c'])
    if v >= 0x83:
        for f in m['flanks']:
            _enc_flank(w, f, v)
    if v >= 0xaa:
        w.fs(m['d'])


def _dec_instance(r, v):
    t = r.u32()
    o = dict(type=t, cls=r.u32(), matrix=r.fs(16), flags=r.u32())
    if t in (TO_DECORADO, TO_ARBOL):
        o['res'] = r.us(2)
    elif t == TO_CONSTRUCCION:
        assert v >= 150, 'pre-v150 constructions not modelled'
        o['name'] = r.s()
        o['ctype'] = r.u32()
        o['e'] = r.us(2)
        o['f'] = r.us(2)                              # (v >= 0x66) local (default 100), +0xb0
        o['g'] = list(r.take(2))                      # +0x60, +0xf9 (second list present)
        o['lists'] = [[_pos(r) for _ in range(r.u32())] for i in range(2 if o['g'][1] else 1)]
        o['list3'] = [_pos(r) for _ in range(r.u32())]
        o['p'] = [_pos(r), _pos(r)]
        o['modules'] = [_dec_module(r, v) for _ in range(r.u32())]
        o['res'] = r.us(2)
    elif t == TO_AGUA:
        o['h'] = r.us(2)
        o['w'] = r.take(16)
        o['banks'] = [[r.take(8), r.us(3)] for _ in range(2)]
        o['colours'] = _dec_colours(r) if r.u8() else None
        o['res'] = r.us(2)
    elif t == TO_HIELO:
        o['colours'] = _dec_colours(r) if r.u8() else None
        o['res'] = r.us(2)
    else:
        raise ValueError('object type %d' % t)
    return o


def _enc_instance(w, o, v):
    t = o['type']
    w.u32(t); w.u32(o['cls']); w.fs(o['matrix']); w.u32(o['flags'])
    if t == TO_CONSTRUCCION:
        w.s(o['name']); w.u32(o['ctype']); w.us(o['e']); w.us(o['f']); w.raw(bytes(o['g']))
        for lst in o['lists']:
            w.u32(len(lst))
            for p in lst:
                _wpos(w, p)
        w.u32(len(o['list3']))
        for p in o['list3']:
            _wpos(w, p)
        for p in o['p']:
            _wpos(w, p)
        w.u32(len(o['modules']))
        for m in o['modules']:
            _enc_module(w, m, v)
    elif t == TO_AGUA:
        w.us(o['h']); w.raw(o['w'])
        for b8, u3 in o['banks']:
            w.raw(b8); w.us(u3)
    if t in (TO_AGUA, TO_HIELO):
        w.u8(1 if o['colours'] is not None else 0)
        if o['colours'] is not None:
            _enc_colours(w, o['colours'])
    w.us(o['res'])


def dec_objects(r, v):
    """svcObjetosMapa::init (class library) [W] + load (instances) [V]."""
    lib = []
    for _ in range(r.u32()):
        c = dict(type=r.u32(), model=r.s())
        if c['type'] == TO_CONSTRUCCION:
            c['modules'] = []
            for _ in range(r.u32()):
                md = dict(anis=[r.s() for _ in range(r.u32())])
                md['volumes'] = None
                if r.u8():
                    md['volumes'] = [_dec_volume(r, v) for _ in range(r.u32() if v >= 150 else 1)]
                c['modules'].append(md)
        c['res'] = r.us(2)
        lib.append(c)
    inst = [_dec_instance(r, v) for _ in range(r.u32())]
    return dict(library=lib, instances=inst)


def enc_objects(w, d, v):
    w.u32(len(d['library']))
    for c in d['library']:
        w.u32(c['type']); w.s(c['model'])
        if c['type'] == TO_CONSTRUCCION:
            w.u32(len(c['modules']))
            for md in c['modules']:
                w.u32(len(md['anis']))
                for a in md['anis']:
                    w.s(a)
                w.u8(0 if md['volumes'] is None else 1)
                if md['volumes'] is not None:
                    if v >= 150:
                        w.u32(len(md['volumes']))
                    for vol in md['volumes']:
                        _enc_volume(w, vol, v)
        w.us(c['res'])
    w.u32(len(d['instances']))
    for o in d['instances']:
        _enc_instance(w, o, v)


def dec_terrainlogic(r, v):
    """Cell grid [W]: per cell {u16 terrain type, u8 passable (0 = free)}; v185 height planes min/max."""
    d = dict(name=r.s(), id=r.u32(), cells=r.us(3), cell_size=r.fs(2), origin=r.fs(3), size=r.fs(2))
    d['data'] = bytearray(r.take(3 * d['cells'][2]))
    if v >= 185:
        d['planes'] = r.fs(2)
    return d


def enc_terrainlogic(w, d, v):
    w.s(d['name']); w.u32(d['id']); w.us(d['cells']); w.fs(d['cell_size']); w.fs(d['origin']); w.fs(d['size'])
    w.raw(d['data'])
    if v >= 185:
        w.fs(d['planes'])


def dec_postrooper(r, v):
    """Troop start / reinforcement areas [W svcMapaLogico]: grid of Filas x Columnas slots of Size, rotated."""
    out = []
    for _ in range(r.u32()):
        p = dict(type_id=r.u32(), pos=r.fs(3), angle=r.f32(), allow=r.u32(), flags=r.u32())
        if v >= 108:
            p['name'] = r.s(); p['filas'] = r.u32(); p['columnas'] = r.u32(); p['size'] = r.fs(2)
            p['res'] = r.us(4)
        p['route'] = None
        if r.u8():
            nodes = [[r.fs(3), r.f32()] for _ in range(r.u32())]
            links = [[r.us(r.u32()), r.us(r.u32())] for _ in range(r.u32())]
            p['route'] = dict(nodes=nodes, links=links)
        out.append(p)
    return out


def enc_postrooper(w, d, v):
    w.u32(len(d))
    for p in d:
        w.u32(p['type_id']); w.fs(p['pos']); w.f32(p['angle']); w.u32(p['allow']); w.u32(p['flags'])
        if v >= 108:
            w.s(p['name']); w.u32(p['filas']); w.u32(p['columnas']); w.fs(p['size']); w.us(p['res'])
        w.u8(0 if p['route'] is None else 1)
        if p['route'] is not None:
            w.u32(len(p['route']['nodes']))
            for pos, ang in p['route']['nodes']:
                w.fs(pos); w.f32(ang)
            w.u32(len(p['route']['links']))
            for par, ch in p['route']['links']:
                w.u32(len(par)); w.us(par); w.u32(len(ch)); w.us(ch)


def dec_locations(r, v):
    """SLocation [W]: type, name (v172), id (creature species ...), pos, angles, particle file, cyclic, fade
    frames, scale, YBias (v186). Building locations (LOC_*) are camera / intro targets."""
    out = []
    for _ in range(r.u32()):
        l = dict(type=r.u32())
        if v >= 172:
            l['name'] = r.s()
        l['uid'] = r.u32(); l['pos'] = r.fs(3)
        l['angles'] = r.fs(2) if v >= 150 else [0.0, r.f32()]
        l['particles'] = r.s()
        if v >= 150:
            l['ciclico'] = r.u8(); l['frames'] = r.u32(); l['escala'] = r.f32()
        if v >= 186:
            l['ybias'] = r.f32()
        out.append(l)
    return out


def enc_locations(w, d, v):
    w.u32(len(d))
    for l in d:
        w.u32(l['type'])
        if v >= 172:
            w.s(l['name'])
        w.u32(l['uid']); w.fs(l['pos'])
        if v >= 150:
            w.fs(l['angles'])
        else:
            w.f32(l['angles'][1])
        w.s(l['particles'])
        if v >= 150:
            w.u8(l['ciclico']); w.u32(l['frames']); w.f32(l['escala'])
        if v >= 186:
            w.f32(l['ybias'])


def dec_zones(r, v):
    return [dict(color=r.u32(), name=r.s(), cells=r.us(r.u32())) for _ in range(r.u32())]


def enc_zones(w, d, v):
    w.u32(len(d))
    for z in d:
        w.u32(z['color']); w.s(z['name']); w.u32(len(z['cells'])); w.us(z['cells'])


def dec_arbzones(r, v):
    """SLogicArea [W]: name, type, side, polygon (x, z). PROTECCION_ZONA victory conditions name one."""
    out = []
    for _ in range(r.u32()):
        a = dict(name=r.s(), type=r.u32(), bando=r.u32())
        a['poly'] = [r.fs(2) for _ in range(r.u32())]
        out.append(a)
    return out


def enc_arbzones(w, d, v):
    w.u32(len(d))
    for a in d:
        w.s(a['name']); w.u32(a['type']); w.u32(a['bando']); w.u32(len(a['poly']))
        for p in a['poly']:
            w.fs(p)


def dec_segmentmap(r, v):
    """Collision outlines [W svcMapaSegmentos]: closed polylines (first point stored twice) with normals."""
    out = []
    for _ in range(r.u32()):
        s = dict(diffuse=r.u32(), center=r.fs(3))
        s['radius'] = r.f32() if v >= 103 else None
        s['closed'] = r.u8()
        s['points'] = [r.fs(3) for _ in range(r.u32())]
        s['infos'] = [r.fs(3 if v >= 103 else 2) for _ in range(r.u32())]
        out.append(s)
    # the editor writes 4 more bytes (always 0) that the retail reader FUN_004d2d30 never reads
    return dict(sectors=out, tail=r.take(r.left()))


def enc_segmentmap(w, d, v):
    w.u32(len(d['sectors']))
    for s in d['sectors']:
        w.u32(s['diffuse']); w.fs(s['center'])
        if v >= 103:
            w.f32(s['radius'])
        w.u8(s['closed'])
        w.u32(len(s['points']))
        for p in s['points']:
            w.fs(p)
        w.u32(len(s['infos']))
        for p in s['infos']:
            w.fs(p)
    w.raw(d['tail'])


def dec_sectormap(r, v):
    """Sector map [V FUN_0048e7e0]: shared points, sectors (polygon of point indices + passability / occlusion
    data), links between sectors across a shared edge (two point indices)."""
    pts = [r.fs(3) for _ in range(r.u32())]
    secs = []
    for _ in range(r.u32()):
        s = dict(id=r.u32())
        assert v >= 0xa0
        s['a'] = r.u8(); s['type'] = r.u32(); s['b'] = r.u8()
        s['special'] = None
        if r.u8():
            sv = [r.fs(3) for _ in range(r.u32())]
            s['special'] = dict(verts=sv, idx=r.us(r.u32()))
        s['p1'] = r.fs(3); s['p2'] = r.fs(3)
        s['c'] = r.u8(); s['center'] = r.fs(3)
        s['occl'] = r.u32()
        s['poly'] = r.us(r.u32())
        secs.append(s)
    links = [r.us(4) for _ in range(r.u32())]
    return dict(points=pts, sectors=secs, links=links)


def enc_sectormap(w, d, v):
    w.u32(len(d['points']))
    for p in d['points']:
        w.fs(p)
    w.u32(len(d['sectors']))
    for s in d['sectors']:
        w.u32(s['id']); w.u8(s['a']); w.u32(s['type']); w.u8(s['b'])
        w.u8(0 if s['special'] is None else 1)
        if s['special'] is not None:
            w.u32(len(s['special']['verts']))
            for p in s['special']['verts']:
                w.fs(p)
            w.u32(len(s['special']['idx'])); w.us(s['special']['idx'])
        w.fs(s['p1']); w.fs(s['p2']); w.u8(s['c']); w.fs(s['center']); w.u32(s['occl'])
        w.u32(len(s['poly'])); w.us(s['poly'])
    w.u32(len(d['links']))
    for l in d['links']:
        w.us(l)


def dec_grafoia(r, v):
    """Battle-AI graph [V FUN_00499230 aiUtils::loadGraphInfo]: regions (polygon x/z + neighbour ids)."""
    d = dict(head=r.u32(), nodes=[])
    for _ in range(r.u32()):
        n = dict(id=r.u32(), kind=r.u32())
        n['poly'] = [r.fs(2) for _ in range(r.u32())]
        n['nb'] = r.us(r.u32())
        d['nodes'].append(n)
    return d


def enc_grafoia(w, d, v):
    w.u32(d['head']); w.u32(len(d['nodes']))
    for n in d['nodes']:
        w.u32(n['id']); w.u32(n['kind']); w.u32(len(n['poly']))
        for p in n['poly']:
            w.fs(p)
        w.u32(len(n['nb'])); w.us(n['nb'])


def dec_sound(r, v):
    """CSonidoMapa::load [W]: music id, ambient {id, volume}, positional {id, volume, max r, min r, pos}."""
    d = dict(music=r.s())
    d['ambient'] = [[r.s(), r.u32()] for _ in range(r.u32())]
    d['positional'] = [[r.s(), r.u32(), r.f32(), r.f32(), r.fs(3)] for _ in range(r.u32())]
    return d


def enc_sound(w, d, v):
    w.s(d['music'])
    w.u32(len(d['ambient']))
    for s, vol in d['ambient']:
        w.s(s); w.u32(vol)
    w.u32(len(d['positional']))
    for s, vol, a, b, p in d['positional']:
        w.s(s); w.u32(vol); w.f32(a); w.f32(b); w.fs(p)


def _dec_conds(r):
    out = []
    for _ in range(r.u32()):
        subs = []
        for _ in range(r.u32()):
            t = r.u32()
            if t == SUB_PROTECCION_ZONA:
                subs.append([t, r.s()])
            elif t in (SUB_ANIQUILACION, SUB_DESTRUCCION_EDIF, SUB_PROTECCION_EDIF, SUB_MANTENER_TROPAS):
                subs.append([t, r.u32()])
            else:
                subs.append([t, None])
        out.append(subs)
    return out


def _enc_conds(w, c):
    w.u32(len(c))
    for subs in c:
        w.u32(len(subs))
        for t, val in subs:
            w.u32(t)
            if t == SUB_PROTECCION_ZONA:
                w.s(val)
            elif val is not None:
                w.u32(val)


def dec_condiciones(r, v):
    """Victory conditions [W + V FUN_004ad420]: attacker list, defender list (OR of AND lists), duration in
    minutes, countdown (v171)."""
    d = dict(attacker=_dec_conds(r), defender=_dec_conds(r), duration=r.f32())
    if v >= 171:
        d['countdown'] = r.f32()
    return d


def enc_condiciones(w, d, v):
    _enc_conds(w, d['attacker']); _enc_conds(w, d['defender']); w.f32(d['duration'])
    if v >= 171:
        w.f32(d['countdown'])


def dec_environment(r, v):
    """[W svcEscenario]: skybox on, skybox model, fog on, fog colour, start, end, density, background colour,
    z near, z far, FOV."""
    return dict(sky_on=r.u8(), skybox=r.s(), fog_on=r.u8(), fog_color=r.u32(), fog=r.fs(3), bg_color=r.u32(),
                clip=r.fs(3))


def enc_environment(w, d, v):
    w.u8(d['sky_on']); w.s(d['skybox']); w.u8(d['fog_on']); w.u32(d['fog_color']); w.fs(d['fog'])
    w.u32(d['bg_color']); w.fs(d['clip'])


CODECS = {HEADER: (dec_header, enc_header), TERRAIN: (dec_terrain, enc_terrain),
          HEIGHTMAP: (dec_heightmap, enc_heightmap), OBJECTLIST: (dec_objects, enc_objects),
          TERRAINLOGIC: (dec_terrainlogic, enc_terrainlogic), POSTROOPER: (dec_postrooper, enc_postrooper),
          LOCATIONS: (dec_locations, enc_locations), ZONES: (dec_zones, enc_zones),
          ARBZONES: (dec_arbzones, enc_arbzones), SEGMENTMAP: (dec_segmentmap, enc_segmentmap),
          SECTORMAP: (dec_sectormap, enc_sectormap), GRAFOIA: (dec_grafoia, enc_grafoia),
          SOUND: (dec_sound, enc_sound), CONDICIONES: (dec_condiciones, enc_condiciones),
          ENVIRONMENT: (dec_environment, enc_environment)}


# ------------------------------------------------------------------ tree
class Chunk:
    def __init__(self, cid, payload=b'', children=None):
        self.id, self.payload, self.children, self.data = cid, payload, children, None

    def __repr__(self):
        return '<%s %s>' % (NAMES.get(self.id, hex(self.id)), len(self.children) if self.children is not None
                            else len(self.payload))


def parse_chunks(b, o, end):
    out = []
    while o < end:
        cid, sz = struct.unpack_from('<II', b, o)
        assert sz >= 8 and o + sz <= end, ('bad chunk', hex(o), hex(cid), sz)
        if cid in CONTAINERS:
            out.append(Chunk(cid, children=parse_chunks(b, o + 8, o + sz)))
        else:
            out.append(Chunk(cid, payload=bytes(b[o + 8:o + sz])))
        o += sz
    return out


def pack_chunks(chunks, version):
    out = []
    for c in chunks:
        if c.children is not None:
            body = pack_chunks(c.children, version)
        elif c.data is not None:
            w = W(); CODECS[c.id][1](w, c.data, version); body = w.bytes()
        else:
            body = c.payload
        out.append(struct.pack('<II', c.id, len(body) + 8) + body)
    return b''.join(out)


class Lvl:
    def __init__(self, data):
        self.chunks = parse_chunks(data, 0, len(data))
        assert self.chunks[0].id == HEADER
        self.version = struct.unpack_from('<I', self.chunks[0].payload, 0)[0]

    def walk(self, chunks=None):
        for c in self.chunks if chunks is None else chunks:
            yield c
            if c.children is not None:
                yield from self.walk(c.children)

    def chunk(self, cid):
        return next(c for c in self.walk() if c.id == cid)

    def has(self, cid):
        return any(c.id == cid for c in self.walk())

    def get(self, cid):
        """Decoded data of a chunk (decoded once, then edited in place; pack() re-encodes it)."""
        c = self.chunk(cid)
        if c.data is None:
            r = R(c.payload)
            c.data = CODECS[cid][0](r, self.version)
            assert r.left() == 0, ('%s: %d bytes left' % (NAMES[cid], r.left()))
        return c.data

    def pack(self):
        return pack_chunks(self.chunks, self.version)

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        open(path, 'wb').write(self.pack())

    # -------------------------------------------------------------- helpers (numpy)
    def heights(self):
        import numpy as np
        hm = self.get(HEIGHTMAP)
        return np.frombuffer(bytes(hm['data']), '<f4').reshape(hm['nz'], hm['nx']).copy()

    def vertices(self):
        """Terrain VB as a numpy structured array (x, y, z, diffuse, u0, v0, u1, v1)."""
        import numpy as np
        t = self.get(TERRAIN)
        dt = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('c', '<u4'), ('u0', '<f4'), ('v0', '<f4'),
                       ('u1', '<f4'), ('v1', '<f4')])
        assert t['vb']['stride'] == 32 and t['vb']['fvf'] == 0x242
        return np.frombuffer(bytes(t['vb']['data']), dt).copy()

    def set_vertices(self, vtx):
        self.get(TERRAIN)['vb']['data'] = bytearray(vtx.tobytes())

    def cells(self):
        import numpy as np
        tl = self.get(TERRAINLOGIC)
        cx, cy, n = tl['cells']
        a = np.frombuffer(bytes(tl['data']), np.dtype([('t', '<u2'), ('p', 'u1')])).reshape(cy, cx)
        return a['t'].copy(), a['p'].copy()

    def set_cells(self, types, passable):
        import numpy as np
        tl = self.get(TERRAINLOGIC)
        a = np.zeros(types.shape, np.dtype([('t', '<u2'), ('p', 'u1')]))
        a['t'], a['p'] = types, passable
        tl['data'] = bytearray(a.tobytes())

    def height_at(self, x, z, h=None):
        """Bilinear terrain height at world (x, z) from the heightmap (cm)."""
        import numpy as np
        h = self.heights() if h is None else h
        t = self.get(TERRAIN)
        cw, ch = t['cell_size']
        ox, oz = t['origin'][0], t['origin'][2]
        fx = np.clip((np.asarray(x, float) - ox) / cw, 0, h.shape[1] - 1.001)
        fz = np.clip((np.asarray(z, float) - oz) / ch, 0, h.shape[0] - 1.001)
        ix, iz = fx.astype(int), fz.astype(int)
        ax, az = fx - ix, fz - iz
        return ((h[iz, ix] * (1 - ax) + h[iz, ix + 1] * ax) * (1 - az) +
                (h[iz + 1, ix] * (1 - ax) + h[iz + 1, ix + 1] * ax) * az)

    def grid_index(self, vtx):
        """(iz, ix) heightmap indices of terrain vertices (they lie exactly on the 181 x 181 grid)."""
        import numpy as np
        t = self.get(TERRAIN)
        cw, ch = t['cell_size']
        return (np.round((vtx['z'] - t['origin'][2]) / ch).astype(int),
                np.round((vtx['x'] - t['origin'][0]) / cw).astype(int))

    def recompute_octree(self):
        """Picking-tree bounds after a height change. Verified rule (all 56 maps reproduce bit-exact): a leaf that
        lists subsets gets the exact y range of their vertices; an empty leaf keeps its stored default box
        (y -1325.8 .. 13258.3); an inner node's y range is the union of its children; x/z never change; the sphere
        is the box centre with half the box diagonal as radius."""
        import numpy as np
        t = self.get(TERRAIN)
        vtx = self.vertices()
        sub = [(int(s[0]), int(s[1])) for s in t['subsets']]

        def walk(n):
            bb = n['bbox']
            rng = [walk(c) for c in n['children']]
            if n['items']:
                ys = np.concatenate([vtx['y'][a:a + k] for a, k in (sub[i] for i in n['items'])])
                rng.append((np.float32(ys.min()), np.float32(ys.max())))
            if not rng:                                   # empty leaf: default box
                rng.append((np.float32(bb[1]), np.float32(bb[4])))
            lo, hi = min(r[0] for r in rng), max(r[1] for r in rng)
            bb[1], bb[4] = float(lo), float(hi)
            b = np.array(bb, np.float32)
            c = (b[:3] + b[3:]) * np.float32(0.5)
            d = (b[3:] - b[:3]) * np.float32(0.5)
            n['sphere'] = [float(c[0]), float(c[1]), float(c[2]), float(np.sqrt(np.float32((d * d).sum())))]
            return lo, hi
        walk(t['octree'])

    def set_heights(self, h, shade=None, carry=True):
        """Replace the terrain heights everywhere they are stored: HEIGHTMAP, the terrain VB y (vertices sit on
        the grid), optionally the vertex shade colours (shade(vtx, h) -> u32 colours), the picking tree bounds,
        and (carry=True) the y of troop positions, locations and placed object instances by the height change
        under them."""
        import numpy as np
        old = self.heights()
        hm = self.get(HEIGHTMAP)
        assert h.shape == (hm['nz'], hm['nx'])
        h = h.astype('<f4')
        hm['data'] = bytearray(h.tobytes())
        vtx = self.vertices()
        iz, ix = self.grid_index(vtx)
        vtx['y'] = h[iz, ix]
        if shade is not None:
            vtx['c'] = shade(vtx, h)
        self.set_vertices(vtx)
        self.recompute_octree()
        if not carry:
            return h

        def dy(x, z):
            return float(self.height_at(x, z, h) - self.height_at(x, z, old))
        for p in self.get(POSTROOPER):
            p['pos'][1] += dy(p['pos'][0], p['pos'][2])
        for l in self.get(LOCATIONS):
            l['pos'][1] += dy(l['pos'][0], l['pos'][2])
        for o in self.get(OBJECTLIST)['instances']:
            m = o['matrix']
            if abs(m[12]) + abs(m[14]) > 0:              # world-placed objects (not the identity scatter sets)
                shift_instance(o, 0.0, dy(m[12], m[14]), 0.0)
        return h

    # -------------------------------------------------------------- objects
    def construction_sectors(self, o):
        """Sector ids a construction instance owns (its modules' flank lists)."""
        return sorted({i for md in o.get('modules', []) for f in md.get('flanks', []) for i in f['ids']})

    def remap_sector_ids(self, mapping):
        """After a sector renumbering: rewrite the construction modules' sector lists (ids missing from the
        mapping are dropped)."""
        for o in self.get(OBJECTLIST)['instances']:
            for md in o.get('modules', []):
                for f in md.get('flanks', []):
                    f['ids'] = [mapping[i] for i in f['ids'] if i in mapping]

    def remove_instances(self, idxs):
        """Delete object instances; building ids in the victory conditions (= instance index) are renumbered,
        conditions on a removed building are dropped (empty condition lists too)."""
        ob = self.get(OBJECTLIST)
        idxs = set(idxs)
        new_index, k = {}, 0
        for i in range(len(ob['instances'])):
            if i not in idxs:
                new_index[i] = k
                k += 1
        ob['instances'] = [o for i, o in enumerate(ob['instances']) if i not in idxs]
        if self.has(CONDICIONES):
            c = self.get(CONDICIONES)
            for side in ('attacker', 'defender'):
                out = []
                for subs in c[side]:
                    ns = []
                    for t, v in subs:
                        if t in (SUB_DESTRUCCION_EDIF, SUB_PROTECCION_EDIF):
                            if v not in new_index:
                                continue
                            v = new_index[v]
                        ns.append([t, v])
                    if ns:
                        out.append(ns)
                c[side] = out


def shift_instance(o, dx, dy, dz):
    """Translate a decoded object instance, including every position a construction stores (garrison posts,
    entry points, module centres)."""
    m = o['matrix']
    m[12] += dx; m[13] += dy; m[14] += dz

    def mv(p):
        p[0][0] += dx; p[0][1] += dy; p[0][2] += dz
    if o['type'] == TO_CONSTRUCCION:
        for lst in o['lists'] + [o['list3']]:
            for p in lst:
                mv(p)
        for p in o['p']:
            mv(p)
        for md in o['modules']:
            for key in ('posts1', 'posts2'):
                for p in md.get(key, []):
                    mv(p)
            for key in ('p1', 'p2', 'p3'):
                if key in md:
                    mv(md[key])


# ------------------------------------------------------------------ files
def original_maps():
    """All original .lvl files, data1 (official patch) overriding data."""
    import glob
    seen = {}
    for base in ('data', 'data1'):
        for p in sorted(glob.glob(os.path.join(ROOT, base, 'Game', 'GameModes', 'Batalla', 'Escenarios', '*', '*.lvl'))):
            seen[os.path.relpath(p, os.path.join(ROOT, base)).lower()] = p
    return [seen[k] for k in sorted(seen)]


def load(path):
    return Lvl(open(path, 'rb').read())


def selftest(paths=None, verbose=True):
    """Decode + encode every chunk of every map; True if all are byte-identical."""
    ok = True
    for p in paths or original_maps():
        raw = open(p, 'rb').read()
        m = Lvl(raw)
        bad = []
        for c in m.walk():
            if c.id in CODECS:
                try:
                    m.get(c.id)
                except Exception as e:                      # noqa
                    bad.append('%s: %s' % (NAMES[c.id], e))
        out = m.pack()
        same = out == raw
        ok &= same and not bad
        if verbose:
            print('%-60s %s %s' % (os.path.relpath(p, ROOT), 'OK ' if same and not bad else 'BAD', ' '.join(bad)))
    return ok


def info(path):
    m = load(path)
    print(path, 'version', m.version)
    for c in m.walk():
        if c.children is None:
            print('  %-12s %8d' % (NAMES.get(c.id, hex(c.id)), len(c.payload)))
    t = m.get(TERRAIN)
    print('  terrain cells', t['cells'], 'tiles', t['tiles'], 'cell', t['cell_size'], 'size', t['size'],
          'verts', len(t['vb']['data']) // 32, 'subsets', len(t['subsets']), 'materials', len(t['materials']))
    h = m.heights()
    print('  heights %.0f .. %.0f cm' % (h.min(), h.max()))
    ob = m.get(OBJECTLIST)
    print('  library', [(c['type'], c['model']) for c in ob['library']])
    print('  instances', len(ob['instances']), [o['type'] for o in ob['instances']])
    for p in m.get(POSTROOPER):
        print('  post %-10s flags %#x allow %#x pos (%.0f, %.0f) ang %.2f %dx%d size %s route %s' % (
            p['name'], p['flags'], p['allow'], p['pos'][0], p['pos'][2], p['angle'], p['filas'], p['columnas'],
            [round(x) for x in p['size']], p['route'] is not None))
    print('  conditions', m.get(CONDICIONES))
    print('  arbzones', [(a['name'], a['type'], a['bando'], len(a['poly'])) for a in m.get(ARBZONES)])
    print('  locations', [(l['type'], l['name'], l['uid']) for l in m.get(LOCATIONS)])
    sm = m.get(SECTORMAP)
    print('  sectors', len(sm['sectors']), 'points', len(sm['points']), 'links', len(sm['links']))
    g = m.get(GRAFOIA)
    print('  ai graph head', g['head'], 'nodes', len(g['nodes']))
    print('  sound', m.get(SOUND)['music'], len(m.get(SOUND)['ambient']), len(m.get(SOUND)['positional']))
    print('  environment', m.get(ENVIRONMENT))


def check(path):
    """Consistency checks of a (new) map and its scenario folder. Returns a list of problems (empty = OK)."""
    import math
    import re
    import lvl_nav
    from shapely.geometry import Point
    probs = []
    raw = open(path, 'rb').read()
    m = Lvl(raw)
    if m.pack() != raw:
        probs.append('pack() is not byte-identical')
    for c in m.walk():
        if c.id in CODECS:
            try:
                m.get(c.id)
            except Exception as e:                          # noqa
                probs.append('%s: %s' % (NAMES[c.id], e))
    t = m.get(TERRAIN)
    size = t['size'][0]
    sm = m.get(SECTORMAP)
    probs += ['sectors: ' + p for p in lvl_nav.validate(sm, size)]
    polys = lvl_nav.sector_polygons(sm)
    byid = {s['id']: s for s in sm['sectors']}

    def owner(x, z):
        pt = Point(x, z)
        return next((byid[i] for i, pg in polys.items() if pg.covers(pt)), None)
    for p in m.get(POSTROOPER):
        # the angle turns CLOCKWISE in (x, z): facing = (sin a, cos a). Verified 2026-10-21 on the originals: with this
        # rule the rotated troop areas of 41/42/57/58 tile without overlap (the counter-clockwise reading overlaps
        # ~1200 m2 per side); 0 / pi maps (51, the Caucasus) read the same either way.
        ca, sa = math.cos(p['angle']), math.sin(p['angle'])
        w, h = p['size']
        hx, hz, vx, vz = w * ca, -w * sa, h * sa, h * ca
        for f in range(p['filas']):
            for col in range(p['columnas']):
                x = p['pos'][0] - hx / 2 + vx / 2 + hx / p['columnas'] * (col + 0.5) - vx / p['filas'] * f
                z = p['pos'][2] - hz / 2 + vz / 2 + hz / p['columnas'] * (col + 0.5) - vz / p['filas'] * f
                s = owner(x, z)
                if s is None or not s['a']:
                    probs.append('troop slot of %s at (%.0f, %.0f) on impassable ground' % (p['name'], x, z))
    zones = {a['name'] for a in m.get(ARBZONES)}
    ob = m.get(OBJECTLIST)
    for side in ('attacker', 'defender'):
        for subs in m.get(CONDICIONES)[side]:
            for typ, v in subs:
                if typ == SUB_PROTECCION_ZONA and v not in zones:
                    probs.append('condition zone %s missing' % v)
                if typ in (SUB_DESTRUCCION_EDIF, SUB_PROTECCION_EDIF) and \
                        (v >= len(ob['instances']) or ob['instances'][v]['type'] != TO_CONSTRUCCION):
                    probs.append('condition building %d is not a construction' % v)
    for o in ob['instances']:
        for sid in m.construction_sectors(o):
            if sid not in byid:
                probs.append('construction %s lists missing sector %d' % (o.get('name'), sid))
    d = os.path.dirname(os.path.abspath(path))
    md = os.path.join(d, 'Models')
    if os.path.isdir(md):
        have = {f.lower() for f in os.listdir(md)}
        need = [c['model'] for c in ob['library']] + [a for c in ob['library'] for md_ in c.get('modules', [])
                                                       for a in md_['anis']]
        need += [mt[k] for mt in t['materials'] for k in (0, 2)] + [m.get(ENVIRONMENT)['skybox']]
        probs += ['missing Models/%s' % n for n in need if n.lower() not in have]
    locs = {l.get('name') for l in m.get(LOCATIONS)}
    for fn in ('introAtacante.lua', 'introDefensor.lua'):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            for name in re.findall(r'"(LOC_\w+)"', open(p, encoding='latin1').read()):
                if name not in locs:
                    probs.append('%s uses %s, not in LOCATIONS' % (fn, name))
    return probs


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'selftest':
        sys.exit(0 if selftest(sys.argv[2:] or None) else 1)
    elif len(sys.argv) > 2 and sys.argv[1] == 'info':
        info(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == 'check':
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        pr = check(sys.argv[2])
        print('\n'.join(pr) if pr else 'OK')
        sys.exit(1 if pr else 0)
    else:
        print(__doc__)

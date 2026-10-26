"""Small editor for battle-map V3D models (tree sets): move whole nodes by changing their transforms.

V3D object chunk 0x2000 (GEOMOBJECT) [W spec + V on 51/Models/Arboles.V3D]: 40-byte header, name, parent, then
three 4x4 matrices: m1 vertex TM (identity in the tree sets), m2 = WORLD TM, m3 = LOCAL TM (relative to the
parent); translation in floats 12..14 of each. A tree set (Arboles.V3D) = helper 'Arboles' (identity) with one
'ScatterNN' trunk mesh per tree and a 'CopaNN' canopy billboard as its child. Moving a tree by d: the trunk's m2
and m3 += d, the canopy's m2 += d (its m3 is relative to the trunk). The file header holds the model's global
bounding box (min at byte 146, max at 158) which is kept covering all nodes.
"""
import struct


def _rs(d, p):
    n = struct.unpack_from('<H', d, p)[0]
    return d[p + 2:p + 2 + n].rstrip(b'\0').decode('latin1'), p + 2 + n


def root_offset(d):
    hs = struct.unpack_from('<I', d, 4)[0]
    return hs + struct.unpack_from('<I', d, hs + 4)[0]


def objects(d):
    """[{off, cid, size, name, parent, m2, m3}] for the object chunks after the material list (m2/m3 = byte
    offsets of the world / local matrices, None for helpers)."""
    o, out = root_offset(d), []
    while True:
        cid, sz = struct.unpack_from('<II', d, o)
        if cid == 0xff:
            return out
        p = o + (40 if cid == 0x2000 else 20)
        name, p = _rs(d, p)
        parent, p = _rs(d, p)
        rec = dict(off=o, cid=cid, size=sz, name=name, parent=parent, m2=None, m3=None)
        if cid == 0x2000:
            rec['m2'], rec['m3'] = p + 64, p + 128
        out.append(rec)
        o += sz


def translation(d, moff):
    return list(struct.unpack_from('<3f', d, moff + 48))


def trees(d):
    """[(trunk record, [canopy records])] of a tree set: nodes whose parent is a helper (the set root), or mesh
    nodes at the top level (58Tripolitania's palms 'ScatterNN' have no parent; their m3 is then the world TM)."""
    objs = objects(d)
    helpers = {o['name'] for o in objs if o['cid'] != 0x2000}
    by_parent = {}
    for o in objs:
        by_parent.setdefault(o['parent'], []).append(o)
    return [(o, [c for c in by_parent.get(o['name'], []) if c['cid'] == 0x2000])
            for o in objs if o['cid'] == 0x2000 and (o['parent'] in helpers or o['parent'] == '')]


def move_tree(d, trunk, canopies, dx, dy, dz):
    """Translate one tree (bytearray d edited in place)."""
    for moff in (trunk['m2'], trunk['m3']):
        x, y, z = translation(d, moff)
        struct.pack_into('<3f', d, moff + 48, x + dx, y + dy, z + dz)
    for c in canopies:
        x, y, z = translation(d, c['m2'])
        struct.pack_into('<3f', d, c['m2'] + 48, x + dx, y + dy, z + dz)


def global_bbox(d):
    return list(struct.unpack_from('<3f', d, 146)), list(struct.unpack_from('<3f', d, 158))


def set_global_bbox(d, mn, mx):
    struct.pack_into('<3f', d, 146, *mn)
    struct.pack_into('<3f', d, 158, *mx)

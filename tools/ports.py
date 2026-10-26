"""Ports (DefModeloGestion.mng section 6) and AI graphs (GraphJUG_*.GRF) — see re_tools/report_ports.md.

The engine links land and sea only through ports: a land province's vals[13] is its port id (enum table 4,
PUE_*), and the port record lists its own sea zone (ring 1) and the sea zones reached at lighthouse levels 1/2
(rings 2/3, BFS layers over the sea neighbour lists). The AI graph (one GRF per player, version 2.3) holds every
province as a node with land/sea/port edges; the shipped files only know the 82 original provinces.
"""
import struct
import igmod

# new ports: world province key -> (own sea zone key, harbour name as in TextPuertos.sb "<name> Harbour")
# The port enum ids (table 4) follow this order and save games store them raw: ADD NEW PORTS ONLY AT THE END,
# never insert, reorder or remove (the 01:09 build of 2026-10-21 has ids 1..56; Kororareka is 57).
NEW_PORTS = {
    'senegal': ('senegambia', 'Saint-Louis'), 'ivory': ('guinea', 'Cape Coast'), 'loango': ('loango', 'Loango'),
    'angola': ('angola', 'Luanda'), 'cape': ('goodhope', 'Cape Town'), 'mozambique': ('mozambique', 'Mozambique'),
    'swahili': ('zanzibar', 'Zanzibar'), 'somalisor': ('somali', 'Mogadishu'), 'massawa': ('redsea', 'Massawa'),
    'hejaz': ('redsea', 'Jeddah'), 'yemen': ('aden', 'Mocha'), 'muscat': ('gulf', 'Muscat'),
    'madagascar': ('indian', 'Foulpointe'), 'bombay': ('malabar', 'Bombay'), 'carnatic': ('coromandel', 'Madras'),
    'ceylon': ('coromandel', 'Trincomalee'), 'bengal': ('bengal', 'Calcutta'), 'pegu': ('andaman', 'Rangoon'),
    'siam': ('siam', 'Bangkok'), 'malaya': ('malacca', 'Malacca'), 'sumatra': ('sunda', 'Bencoolen'),
    'java': ('java', 'Batavia'), 'cochin': ('scs_s', 'Saigon'), 'guangdong': ('scs_n', 'Canton'),
    'fujian': ('formosa', 'Amoy'), 'luzon': ('scs_n', 'Manila'), 'moluccas': ('banda', 'Amboina'),
    'celebes': ('flores', 'Makassar'), 'timor': ('timor', 'Kupang'), 'kyushu': ('ecs', 'Nagasaki'),
    'korea': ('japan_sea', 'Pusan'), 'honshu': ('japan_pac', 'Edo'), 'kamchatka': ('kamchatka', 'Petropavlovsk'),
    'okhotsk': ('okhotsk', 'Okhotsk'), 'nsw': ('nsw', 'Sydney'),
}
# New Zealand (PACIFIC capital) is unreachable by sea without this port. Starting buildings (the quay) are only made at
# campaign start, so a running save would get a port without a quay (a missing quay crashed the game before): turn it on
# when the user starts a NEW campaign.
NZ_PORT = False
if NZ_PORT:
    NEW_PORTS['nznorth'] = ('nz_e', 'Kororareka')

# enum / text tag of a new port when its harbour name would repeat an original port's key (make_map.add_ports asserts
# that every PUE_<tag> and LTEXT_PUERTO_<tag> is new). The Dutch home port is PUE_BATAVIA / LTEXT_PUERTO_BATAVIA
# ("Amsterdam Harbour"); Java's port showed "Batavia" in its place (re_tools/report_full_review.md G2).
PORT_TAGS = {'java': 'BATAVIA_JAVA'}


def parse_ports(chunk):
    b, p, out = chunk.body, 0, []
    for _ in range(chunk.cnt):
        r = {'idx': struct.unpack_from('<I', b, p)[0]}
        r['ltext'], p = igmod.rs(b, p + 4)
        r['ldesc'], p = igmod.rs(b, p)
        r['cat'] = struct.unpack_from('<I', b, p)[0]; p += 4
        for k in ('nb', 'r1', 'r2', 'r3'):
            n = struct.unpack_from('<I', b, p)[0]
            r[k] = list(struct.unpack_from('<%dI' % n, b, p + 4)); p += 4 + 4 * n
        out.append(r)
    assert p == len(b)
    return out


def pack_port(r):
    o = struct.pack('<I', r['idx']) + igmod.ws(r['ltext']) + igmod.ws(r['ldesc']) + struct.pack('<I', r['cat'])
    for k in ('nb', 'r1', 'r2', 'r3'):
        o += struct.pack('<I', len(r[k])) + struct.pack('<%dI' % len(r[k]), *r[k])
    return o


def set_ports(chunk, recs):
    chunk.body = b''.join(pack_port(r) for r in recs); chunk.cnt = len(recs)


def rings(provs, sea_zone):
    r1 = {sea_zone}
    r2 = {x for z in r1 for x in provs[z]['nb']} - r1
    r3 = {x for z in r2 for x in provs[z]['nb']} - r1 - r2
    return [sea_zone], sorted(r2), sorted(r3)


def graph_neighbours(provs, ports):
    """FUN_00663b30(prov, land ? 0x9e : 0x6e, 1) as used by the graph builder FUN_00747570."""
    pseas = lambda q: set(ports[q['vals'][13]]['r1']) if q['sea'] == 0 and q['vals'][13] in ports else set()
    port_land = {}
    for l, ql in provs.items():
        for z in pseas(ql):
            port_land.setdefault(z, set()).add(l)
    out = {}
    for pid, q in provs.items():
        s = set()
        for x in [pid] + q['nb']:
            qx = provs[x]
            if qx['sea'] != q['sea']:
                continue
            if x != pid:
                s.add(x)
            if q['sea'] == 0:
                s |= pseas(qx)
            else:
                s |= port_land.get(x, set())
        out[pid] = s
    return out


def build_grf(provs, ports, capitals, pos):
    order = [i for i in provs if provs[i]['sea'] == 0] + [i for i in provs if provs[i]['sea'] == 1]
    index = {pid: k for k, pid in enumerate(order)}
    nodes = b''
    for k, pid in enumerate(order):
        x, z = pos[pid]
        nodes += struct.pack('<IIIfffII', 3, 33, k, x, 50.0, z, provs[pid]['sea'], pid) + bytes([pid in capitals])
    nb = graph_neighbours(provs, ports)
    edges = []
    for pid in order:
        for x in sorted(nb[pid]):
            a, b = provs[pid]['sea'], provs[x]['sea']
            edges.append(struct.pack('<IIIII', 4, 20, index[pid], index[x], 2 if a != b else (1 if a == 0 else 0)))
    return (struct.pack('<IIf', 0, 12, 2.3)
            + struct.pack('<III', 1, 12 + len(nodes), len(order)) + nodes
            + struct.pack('<III', 2, 12 + 20 * len(edges), len(edges)) + b''.join(edges))


def read_grf_nodes(data):
    """{prov id: (x, z)} and the capital provinces of a GRF file."""
    n = struct.unpack_from('<I', data, 20)[0]; pos, caps = {}, set()
    for k in range(n):
        _, _, _, x, y, z, sea, pid = struct.unpack_from('<IIIfffII', data, 24 + 33 * k)
        pos[pid] = (x, z)
        if data[24 + 33 * k + 32]:
            caps.add(pid)
    return pos, caps

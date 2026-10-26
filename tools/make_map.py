"""Build Data2.pak with the new provinces from build/forslag_former.json (made by free_land.py).

Step 1 of the map expansion: provinces only, owned by existing nations. Nothing in data/, data1/
or text/ is modified; outputs go to mod/ and build/, inputs are backed up to backups/<time>/.
"""
import sys, os, shutil, struct, time, re, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# --public: the public (Nexus) release without Chechenya, built into build/public/ (staging tree build/public/mod/).
# Set before nations.py is imported: it reads IG_PUBLIC (nations.PUBLIC). Without the flag the build is unchanged.
PUBLIC = '--public' in sys.argv[1:]
if PUBLIC:
    os.environ['IG_PUBLIC'] = '1'
else:
    os.environ.pop('IG_PUBLIC', None)       # a stray IG_PUBLIC in the shell must never make the father's build public
from igmod import *
import meshgen as MG
import render_map as RM
import nations as NT
import flags as FL
import tga

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, DATA1, TEXT = [os.path.join(ROOT, d) for d in ('data', 'data1', 'text')]
MOD, BUILD = os.path.join(ROOT, 'mod'), os.path.join(ROOT, 'build')
OUT_DIR = BUILD                  # Data2.pak, the patched exe and its patch list
if PUBLIC:
    OUT_DIR = os.path.join(BUILD, 'public')
    MOD = os.path.join(OUT_DIR, 'mod')
BK = os.path.join(ROOT, 'backups', time.strftime('%Y%m%d-%H%M%S'))
LIFT = 0.97              # height of the original province meshes (figures stand at LIFT - 0.0147, as in the original data)

# id in forslag_former.json: (enum key, mesh name, display name, owner, template province, battle scenario, description)
PROVINCES = {
    1: ('SAHARA_OCCIDENTAL', 'SaharaOccidental', 'Western Sahara', 'SAJONIA', 'Cirenaica', '43',
        'Endless dunes and caravan routes south of the Atlas, crossed by Berber traders.'),
    2: ('TUAT', 'Tuat', 'Tuat', 'SAJONIA', 'Cirenaica', '43',
        'A chain of desert oases in the heart of the Sahara, a crossroads of the trans-Saharan trade.'),
    3: ('ARABIA', 'Arabia', 'Arabia', 'OTOMANO', 'Egipto', '42',
        'The great peninsula of sand and holy cities, nominally under the Sultan in Constantinople.'),
    4: ('OMAN', 'Oman', 'Oman', 'OTOMANO', 'Egipto', '42',
        'A seafaring land guarding the mouth of the Persian Gulf and its rich trade.'),
    5: ('PERSIA', 'Persia', 'Persia', 'OTOMANO', 'Anatolia', '30',
        'The ancient heartland of the Persian empire, of mountains, high plateaus and old cities.'),
    6: ('KHORASAN', 'Khorasan', 'Khorasan', 'OTOMANO', 'Anatolia', '30',
        'The eastern marches of Persia, land of the rising sun and the road to India.'),
    7: ('TURKESTAN', 'Turkestan', 'Turkestan', 'RUSIA', 'Kursk', '19',
        'Steppes and deserts east of the Caspian, home of khanates and the old Silk Road.'),
    8: ('KAZAKHSTAN', 'Kazakhstan', 'Kazakh Steppe', 'HANNOVER', 'Kursk', '19',
        'The endless grass sea of the Kazakh hordes, stretching from the Caspian to the east.'),
    9: ('URAL', 'Ural', 'Ural', 'RUSIA', 'Moscu', '18',
        'The mountains that divide Europe from Asia, rich in iron, copper and timber.'),
    10: ('SIBERIA', 'Siberia', 'Siberia', 'RUSIA', 'Finlandia', '39',
         'A vast frozen wilderness of forests and rivers beyond the Urals.'),
    # battle map '51' (Republica Helvetica: an Alpine highland ringed by mountains, the most rugged original land map by
    # heightmap measurement) instead of '19' (Kursk, a flat frozen steppe). The province record still comes from the
    # Kursk template, so the campaign data and the unique scenario id (str(idx)) are unchanged.
    11: ('CHECHNYA', 'Chechenya', 'Chechenya', 'RUSIA', 'Kursk', '51',
         'Forested gorges and high villages of the North Caucasus, where Sheikh Mansur calls the mountaineers to arms.'),
}
# --public: no Chechen nation (nations.PUBLIC_DROP). The province keeps its key, mesh, art and Caucasus battlefield, takes the
# common English name and its 1789 owner: the Ottoman Empire, patron of Sheikh Mansur's holy war (1785-91, arms and
# officers through Anapa) and Russia's enemy in the war of 1787-92; Russia held only the Terek line (Kizlyar-Mozdok,
# Vladikavkaz 1784), the Kursk border. Mansur's starting army goes with it (start1789.apply reassign).
PUBLIC_PROVINCE_OWNER = {11: 'OTOMANO'}
PUBLIC_PROVINCE_NAME = {11: 'Chechnya'}
PUBLIC_ARMY_TO = {'JUG_CHECHNYA': 'JUG_OTOMANO'}
if PUBLIC:
    for _p, _o in PUBLIC_PROVINCE_OWNER.items():
        _e = PROVINCES[_p]
        PROVINCES[_p] = _e[:2] + (PUBLIC_PROVINCE_NAME.get(_p, _e[2]), _o) + _e[4:]
# Step 2: minor nations moved onto new land. Their old province goes to a neighbour.
RESKIN = [
    dict(country='MOLDAVIA', player='JUG_MOLDAVIA', old_prov='MOLDAVIA', give_to='OTOMANO', capital_world='rozvi',
         capital_building='CAPITAL_BASE_MOLDAVIA', name='Southern Kingdoms', adjective='Southern', capital='Danangombe'),
    dict(country='SAJONIA', player='JUG_SAJONIA', old_prov='SAJONIA', give_to='PRUSIA', capital_prov=2,
         capital_building='CAPITAL_BASE_SAJONIA', name='Sahel Kingdoms', adjective='Sahelian', capital='Tamentit'),
    dict(country='HANNOVER', player='JUG_HANNOVER', old_prov='HANNOVER', give_to='GRAN_BRETANYA', capital_prov=8,
         capital_building='CAPITAL_BASE_HANOVER', name='Kazakh Khanate', adjective='Kazakh', capital='Kokshetau'),
]
LANGS = ['english', 'spanish', 'French', 'German', 'Italian', 'Polish', 'Czech', 'Russian']
UI_MAPS = ['Game/UI/Comun/UIDefs_MapaPaises.sb',
           'Game/UI/MainMenu/UIDefs_MapaPaisesSelectEmpire.sb',
           'Game/UI/MainMenu/SelectEmpire/UIDefs_MapaPaisesSelectEmpire.sb',
           'Game/UI/MainMenu/UIDefs_MapaPaisesSelectEscenario.sb',
           'Game/UI/ModeloGestion/Diplomacia/UIDefs_MapaPaisesSeleccion.sb']
UI_INITVENT = 'Game/UI/ModeloBatalla/UIDefs_VentanaInicioBatallaInfoProvConflictos.sb'


def src(rel):
    for base in (DATA1, DATA):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)


def src_text(lang, rel):
    p = os.path.join(DATA1, 'Texto', lang, rel)
    return p if os.path.exists(p) else os.path.join(TEXT, 'texto', lang, rel)


def read(path):
    bk = os.path.join(BK, os.path.relpath(path, ROOT))
    if not os.path.exists(bk):
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        shutil.copy2(path, bk)
    return open(path, 'rb').read()


def out(rel, data):
    p = os.path.join(MOD, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(data)
    print('  wrote', rel, len(data), 'bytes')


def _samples(edges, step=40.0):
    pts = []
    for (ax, az), (bx, bz) in edges:
        n = max(1, int(math.hypot(bx - ax, bz - az) / step))
        pts += [(ax + (bx - ax) * k / n, az + (bz - az) * k / n) for k in range(n)]
    return pts


def _near(p, edges, tol):
    for (ax, az), (bx, bz) in edges:
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / (dx * dx + dz * dz or 1)))
        if math.hypot(p[0] - ax - t * dx, p[1] - az - t * dz) <= tol:
            return True
    return False


# natural-border extensions of the old edge provinces (tools/art/extend/extend.py): old mesh name -> [polygons]
EXTENSIONS = json.load(open(os.path.join(BUILD, 'extend', 'extensions.json'), encoding='utf8')) \
    if os.path.exists(os.path.join(BUILD, 'extend', 'extensions.json')) else {}


# strait links of the islands without a land neighbour (mesh -> mesh), as every build since 2026-10-20 made them
# (build logs log_full17..27); frozen so finer coast geometry cannot move a link (neighbour lists are save data)
STRAIT_LINKS = {'WCelebes': 'WSouthBorneo', 'WCeylon': 'WMadras', 'WEzo': 'WHonshu', 'WFormosa': 'WFujian',
                'WJava': 'WSouthSumatra', 'WLuzon': 'WVisayas', 'WMadagascar': 'WMozambique', 'WMindanao': 'WVisayas',
                'WNorthIsland': 'WSouthIsland', 'WVanDiemensLand': 'WNewSouthWales'}


def neighbours(shapes, min_shared=200.0, tol=60.0):
    """Provinces whose borders run along each other for at least min_shared world units."""
    outlines = RM.province_outlines(src('Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D'))
    new_edges = {pid: [(poly[k - 1], poly[k]) for k in range(len(poly))] for pid, poly in shapes.items()}
    pid_of_mesh = {PROVINCES[p][1]: p for p in shapes if p in PROVINCES}
    for name, polys in EXTENSIONS.items():
        edges = [(tuple(poly[k - 1]), tuple(poly[k])) for poly in polys for k in range(len(poly))]
        if name in pid_of_mesh:
            new_edges[pid_of_mesh[name]] = new_edges[pid_of_mesh[name]] + edges
        else:
            outlines[name] = list(outlines.get(name, [])) + edges
    res = {}
    for pid, edges in new_edges.items():
        smp = _samples(edges)
        xs = [p[0] for p in shapes[pid]]; zs = [p[1] for p in shapes[pid]]
        box = (min(xs) - tol, max(xs) + tol, min(zs) - tol, max(zs) + tol)
        hits = []
        cands = list(outlines.items()) + [(('NEW', o), e) for o, e in new_edges.items() if o != pid]
        for name, oe in cands:
            oe = [e for e in oe if box[0] <= max(e[0][0], e[1][0]) and min(e[0][0], e[1][0]) <= box[1]
                  and box[2] <= max(e[0][1], e[1][1]) and min(e[0][1], e[1][1]) <= box[3]]
            if oe and sum(40.0 for p in smp if _near(p, oe, tol)) >= min_shared:
                hits.append(name)
        res[pid] = hits
    return res


def country_lists(provs, owner, land):
    """ring1 = countries owning land next to a country's land, ring2 = their land neighbours."""
    ring1 = {}
    for c in set(owner.values()):
        ring1[c] = []
        for p, o in owner.items():
            if o != c:
                continue
            for q in provs[p]['nb']:
                oc = owner.get(q)
                if q in land and oc is not None and oc != c and oc not in ring1[c]:
                    ring1[c].append(oc)
    ring2 = {}
    for c, r1 in ring1.items():
        ring2[c] = []
        for n in r1:
            for x in ring1.get(n, []):
                if x != c and x not in r1 and x not in ring2[c]:
                    ring2[c].append(x)
    return ring1, ring2


I18N_CODES = (('spanish', 'es'), ('French', 'fr'), ('German', 'de'), ('Italian', 'it'), ('Polish', 'pl'),
              ('Czech', 'cs'), ('Russian', 'ru'))    # build/i18n/<code>_*.json per game language (English is the source)


def apply_translations():
    """Translations of the mod's own texts for every language in I18N_CODES: build/i18n/<code>_*.json, each
    {text file relative to Texto/<lang>: {LTEXT key: value}}; replaces the English placeholder or adds the key.
    Files are merged in sorted order, so a later file wins for the same key (ru_texts over ru_quests / ru_tech)."""
    import glob
    for lang, code in I18N_CODES:
        table = {}
        for jp in sorted(glob.glob(os.path.join(BUILD, 'i18n', code + '_*.json'))):
            for rel, kv in json.load(open(jp, encoding='utf8')).items():
                table.setdefault(rel.replace(chr(92), '/'), {}).update(kv)
        if PUBLIC:                  # no texts of the left-out nations (a missing key would be appended)
            table = {rel: kv2 for rel, kv in table.items()
                     for kv2 in [{k: v for k, v in kv.items() if not NT.public_drops_text(k)}] if kv2}
        n = 0
        for rel, kv in table.items():
            p = os.path.join(MOD, 'Texto', lang, rel)
            if not os.path.exists(p):
                p0 = src_text(lang, rel)
                if not os.path.exists(p0):
                    continue
                os.makedirs(os.path.dirname(p), exist_ok=True); shutil.copyfile(p0, p)
            raw = open(p, 'rb').read()
            u16 = raw[:2] == bytes([0xff, 0xfe])
            txt = raw[2:].decode('utf-16-le') if u16 else raw.decode('latin1')
            if not u16 and any(ord(ch) > 255 for v in kv.values() for ch in v):
                print('  translations %s: %s skipped (latin1 file, non-latin1 text)' % (lang, rel))
                continue                                    # a latin1 file cannot hold Cyrillic: leave it
            missing = []
            for k, v in kv.items():
                assert '"' not in v, (k, v)
                txt, c = re.subn(r'(\.%s\s+")[^"]*(")' % re.escape(k), lambda m: m.group(1) + v + m.group(2), txt, count=1)
                if not c:
                    missing.append((k, v))
                n += 1
            data = (bytes([0xff, 0xfe]) + txt.encode('utf-16-le')) if u16 else txt.encode('latin1')
            if missing:
                data = text_add_entries(data, missing)
            open(p, 'wb').write(data)
        print('  translations %s: %d texts' % (lang, n))


def island_neighbours(m):
    """Countries without a land neighbour (Japan) meet the countries whose ports open on the same or an adjacent
    sea zone, as the original links Britain across the Channel; without it they start with no diplomacy at all."""
    import ports as PT
    recs = Mng.parse_provinces(m.section(4)); provs = {r['idx']: r for r in recs}
    prts = {r['idx']: r for r in PT.parse_ports(m.section(6))}
    cs = Mng.parse_countries(m.section(3))
    real = [c for c in cs if c['ltext'] != 'LTEXT_PAIS_PLIBREDUMMY']
    zones = {}
    for c in real:
        z = set()
        for p in c['provs']:
            pid = provs[p]['vals'][13]
            if pid in prts:
                z |= set(prts[pid]['r1'])
        zones[c['idx']] = z
    for c in real:
        if c['lists'][0] or not zones[c['idx']]:
            continue
        near = set(zones[c['idx']])
        for s in list(near):
            near |= {n for n in provs[s]['nb'] if provs[n]['sea']}
        r1 = [o['idx'] for o in real if o is not c and zones[o['idx']] & near]
        r2 = sorted({x for o in real if o['idx'] in r1 for x in o['lists'][0]} - set(r1) - {c['idx']})
        c['lists'] = [r1, r2]
        for o in real:
            if o['idx'] in r1 and c['idx'] not in o['lists'][0]:
                o['lists'][0].append(c['idx'])
        print('  sea neighbours for %s: %s' % (c['ltext'][11:], [o['ltext'][11:] for o in real if o['idx'] in r1]))
    Mng.set_countries(m.section(3), cs)


def apply_reskins(m, idx_of, shapes):
    """Move each RESKIN nation onto its new provinces: capital, map buildings, armies, neighbour lists."""
    cenum = {v: k for k, v in Mng.parse_enum(m.table(1)).items()}
    benum = {v: k for k, v in Mng.parse_enum(m.table(7)).items()}
    recs = Mng.parse_provinces(m.section(4)); provs = {r['idx']: r for r in recs}
    pkey = {v: k for k, v in Mng.parse_enum(m.table(2)).items()}
    cs = Mng.parse_countries(m.section(3)); cby = {c['idx']: c for c in cs}
    players = parse_players(m.section(2))
    caps = parse_capitals(m.section(5)); capby = {c['idx']: c for c in caps}
    pos = Mng.parse_positions(m.section(13))
    land = {r['idx'] for r in recs if not r['sea']}
    def owners():
        return {p: c['idx'] for c in cs for p in c['provs'] if c['ltext'] != 'LTEXT_PAIS_PLIBREDUMMY'}
    new_ids = set(idx_of.values())
    owner_before = {p: o for p, o in owners().items() if p not in new_ids}     # the original map
    texts = {}
    for rk in RESKIN:
        c = cby[cenum[rk['country']]]
        old = pkey[rk['old_prov']]
        if 'capital_world' in rk:
            rk['capital_prov'] = WORLD_PID[rk['capital_world']]
        new_cap_prov = idx_of[rk['capital_prov']]
        c['provs'] = [p for p in c['provs'] if p != old]
        cby[cenum[rk['give_to']]]['provs'].append(old)
        cap_id = provs[old]['vals'][12]
        provs[new_cap_prov]['vals'][4] = provs[old]['vals'][4]
        provs[new_cap_prov]['vals'][12] = cap_id
        provs[old]['vals'][4] = 0
        provs[old]['vals'][12] = 0
        poly = shapes[rk['capital_prov']]
        cx, cz = MG.centre_point(poly)
        spots = sorted(MG.interior_points(poly, 220, 120), key=lambda q: math.hypot(q[0] - cx, q[1] - cz))[1:12] or [(cx, cz)]
        capby[cap_id]['pos'] = [cx, LIFT - 0.0147, cz]
        capb = benum[rk['capital_building']]
        k = 0
        for i, (typ, prov, x, y, z, zero) in enumerate(pos):
            if prov == old and typ in (capb, benum['DELEGACION_COMERCIAL'], benum['CUARTEL_BASICO']):
                if typ == capb:
                    sx, sz = cx, cz
                else:
                    sx, sz = spots[k % len(spots)]
                    k += 1
                pos[i] = (typ, new_cap_prov, sx, LIFT - 0.0147, sz, zero)
        pl = next(q for q in players if q['ltext'] == 'LTEXT_JUGADOR_' + rk['player'][4:])
        for a in pl['armies']:
            if a['province'] == old:
                a['province'] = new_cap_prov
        texts['LTEXT_JUGADOR_' + rk['player'][4:]] = rk['name']
        texts['LTEXT_PAIS_' + rk['country']] = rk['name']
        texts[capby[cap_id]['ltext']] = rk['capital']
        texts['LTEXT_GESTION_NOMBRE_FLOTA_' + rk['player']] = rk['adjective'] + ' Fleet%s'
        print('  %s -> %s: capital %s in %s, old province %s -> %s, %d armies moved'
              % (rk['country'], rk['name'], rk['capital'], PROVINCES[rk['capital_prov']][2], rk['old_prov'], rk['give_to'], len(pl['armies'])))
    r1b, r2b = country_lists(provs, owner_before, land)
    r1, r2 = country_lists(provs, owners(), land)
    # only apply the difference to the original lists, which also hold links across straits etc.
    changed = []
    for c in cs:
        i = c['idx']
        if i not in r1:
            continue
        new = []
        for k, (before, after) in enumerate(((r1b.get(i, []), r1[i]), (r2b.get(i, []), r2[i]))):
            lst = [x for x in c['lists'][k] if not (x in before and x not in after)]
            lst += [x for x in after if x not in before and x not in lst]
            new.append(lst)
        new[1] = [x for x in new[1] if x not in new[0]]
        if new != c['lists']:
            c['lists'] = new
            changed.append(c['ltext'][11:])
    print('  neighbour lists updated for:', changed)
    Mng.set_countries(m.section(3), cs)
    Mng.set_provinces(m.section(4), recs)
    pack_players(m.section(2), players)
    pack_capitals(m.section(5), caps)
    m.section(13).body = b''.join(struct.pack('<IIfffI', *q) for q in pos)
    return texts


def mod_or_src(rel):
    """Text of a data file, from mod/ if this build already changed it."""
    p = os.path.join(MOD, rel)
    return open(p, 'rb').read() if os.path.exists(p) else read(src(rel))


# --- campaign cheats (exe patches 18+, re_tools/report_cheats.md): 'Cheats' button in the ESC menu and the cheat panel
INGAME_MENU = 'Game/UI/ModeloGestion/UIDefs_IngameMenu.sb'
# panel pages: (menu id, [(button id, text key)]); the exe dispatcher (patch 18) runs table['CH_A'..'CH_Z'] on a click
CHEAT_PAGES = [   # every page but the last gets 'More...' (to the next page); 'Back' goes to the previous page / ESC menu
    ('EM_4', [('CH_A', 'LTEXT_UI_CHEAT_GOLD'), ('CH_B', 'LTEXT_UI_CHEAT_FOOD'), ('CH_C', 'LTEXT_UI_CHEAT_RAW'),
              ('CH_D', 'LTEXT_UI_CHEAT_MEN'), ('CH_E', 'LTEXT_UI_CHEAT_FASTBUILD'), ('CH_F', 'LTEXT_UI_CHEAT_FASTTRAIN'),
              ('CH_G', 'LTEXT_UI_CHEAT_FASTRESEARCH')]),
    ('EM_5', [('CH_H', 'LTEXT_UI_CHEAT_GODMODE'), ('CH_I', 'LTEXT_UI_CHEAT_MOVE'), ('CH_J', 'LTEXT_UI_CHEAT_QUEUES'),
              ('CH_K', 'LTEXT_UI_CHEAT_REVEAL'), ('CH_L', 'LTEXT_UI_CHEAT_SPAWN'), ('CH_M', 'LTEXT_UI_CHEAT_FREE'),
              ('CH_N', 'LTEXT_UI_CHEAT_PEACE'), ('CH_O', 'LTEXT_UI_CHEAT_FRIENDLY')]),
    ('EM_6', [('CH_P', 'LTEXT_UI_CHEAT_SUPER'), ('CH_Q', 'LTEXT_UI_CHEAT_HEAL'), ('CH_R', 'LTEXT_UI_CHEAT_VETS'),   # patches 32-39
              ('CH_S', 'LTEXT_UI_CHEAT_INTEL'), ('CH_T', 'LTEXT_UI_CHEAT_UPKEEP'), ('CH_U', 'LTEXT_UI_CHEAT_GENERAL'),
              ('CH_V', 'LTEXT_UI_CHEAT_FLEET'), ('CH_W', 'LTEXT_UI_CHEAT_COWS')]),
]
_BTN_SOUNDS = '.STYLE ESC_MENU_BUTTON .IDSELECTSOUND "S_FXUI_CLICKBUTTON" .IDHIGHLIGHTSOUND "S_FXSELECCION_RESALTE_ELEMENTO"'


CHEAT_PANEL_BOTTOM = 586   # lowest parchment edge of a cheat page: the province-name banner of the 1024x768 map starts at y 589


def esc_parchment(n, centre=410, bottom=None):
    """The ESC-menu parchment (Game/UI/Comun/PIngame0030.tga) for n buttons at the original 40 px pitch, centred like the
    original. Returns ([(V, SY, Y)] of the bitmap pieces at X 256, [button Y]); n = 5 is exactly the original
    (one piece, rows 0-374 at Y 156; buttons 310..470). Longer: the top part (rows 0-243), then 40 px bands of rows
    204-243, then the bottom part (rows 204-374). The pieces do not overlap, so their draw order does not matter.
    bottom: the panel moves up (keeping the pitch) so that its lower edge stays at or above this y."""
    h_ = 236 + 40 * (n - 5)                           # visible parchment: texture rows 136-372 (236 px) for 5 buttons
    if bottom is not None:
        centre = min(centre, bottom - h_ // 2)
    top = centre - h_ // 2
    fy = top - 136
    if n <= 5:
        pieces = [(0, 375, fy)]
    else:
        pieces = [(0, 244, fy)] + [(204, 40, fy + 204 + 40 * k) for k in range(1, n - 5)] + \
                 [(204, 171, fy + 204 + 40 * (n - 5))]
    return pieces, [top + 18 + 40 * k for k in range(n)]


def _bitmaps(pieces, ids):
    return ''.join('    [ .TIPO UIC_BITMAP .ID \'%s\' .PARAMS [ .FILE "Game/UI/Comun/PIngame0030.tga" .X 256 .Y %d '
                   '.SX 512 .SY %d .U 0 .V %d .ALPHA TRUE] ]\r\n' % (i, y, sy, v) for i, (v, sy, y) in zip(ids, pieces))


def cheat_menu():
    """ESC menu: 'Cheats' (EMCH) under 'Save Game' (Exit moves down one slot; the parchment grows by one row) and the
    cheat panel menus of CHEAT_PAGES, each with a 'Back' button (to the ESC menu) and ESC (resumes the game)."""
    rel = INGAME_MENU
    txt = mod_or_src(rel).decode('latin1')
    em1_a, em1_b = find_block(txt, txt.index("[ ####", txt.index('.MENUS')))      # menu 'EM_1'
    em1 = txt[em1_a:em1_b]
    assert "'EM_1'" in em1 and "'EMCH'" not in em1
    pieces, ys = esc_parchment(6)                                     # Resume, Options, Load, Save, Cheats, Exit
    m = re.search(r"[ \t]*\[ \.TIPO UIC_BITMAP \.ID 'FOND'[^\n]*\n", em1)
    assert '.Y 156 .SX 512 .SY 375' in m.group(0)
    em1 = em1[:m.start()] + _bitmaps(pieces, ['FOND', 'FON2']) + em1[m.end():]
    old_y = {'EMOV': 310, 'EMOO': 350, 'EMOC': 390, 'EMOG': 430, 'EMOX': 470}
    for bid, y in (('EMOV', ys[0]), ('EMOO', ys[1]), ('EMOC', ys[2]), ('EMOG', ys[3]), ('EMOX', ys[5])):
        i = em1.index(".ID '%s'" % bid)
        j = em1.index('.FONDO', i)
        k = em1.index(']', j)
        assert re.fullmatch(r'\.FONDO \[ \.X 381 \.Y %d ' % old_y[bid], em1[j:k]), (bid, em1[j:k])
        em1 = em1[:j] + '.FONDO [ .X 381 .Y %d ' % y + em1[k:]
    i = em1.rindex('[', 0, em1.index(".ID 'EMOX'"))                 # the EMOX option block starts here
    line0 = em1.rindex('\n', 0, i) + 1
    ind = em1[line0:i]
    emch = (ind + "[ .TIPO_OPCION UIC_BOTONTEXTO .ID 'EMCH'\r\n" +
            ind + "  .PARAMS [ .TEXT LTEXT_UI_ESCMENU_CHEATS .FONDO [ .X 381 .Y %d ] %s ]\r\n" % (ys[4], _BTN_SOUNDS) +
            ind + "]\r\n\r\n")
    em1 = em1[:line0] + emch + em1[line0:]
    links = "[ .CONTROL_ID 'EMOO' .MENU_ID 'OPCS' ]"
    assert em1.count(links) == 1
    em1 = em1.replace(links, links + "\r\n   [ .CONTROL_ID 'EMCH' .MENU_ID '%s' ]" % CHEAT_PAGES[0][0])
    # The menu manager (UIC_GESTORMENUS, loader FUN_0076fe90) keeps ONE link list for all its menus (manager+0x84) and a
    # click follows the FIRST link with that control id (FUN_0076fd60), so a control id may link to one target only:
    # each 'More...' gets its own id ('CHMA', 'CHMB', ... - outside the dispatcher's 'CH_A'..'CH_Z'). MENU_ID 0 goes
    # back to the previous menu (FUN_0076fc80 pops its history; a named menu is pushed), so every 'Back' is 'CHBK' -> 0.
    pages = ''
    for n_, (menu_id, buttons) in enumerate(CHEAT_PAGES):
        rows, links = list(buttons), []
        if n_ + 1 < len(CHEAT_PAGES):
            more = 'CHM' + chr(ord('A') + n_)
            rows.append((more, 'LTEXT_UI_CHEAT_MORE')); links.append((more, "'%s'" % CHEAT_PAGES[n_ + 1][0]))
        rows.append(('CHBK', 'LTEXT_UI_CHEAT_BACK'))
        links.append(('CHBK', '0'))
        pieces, ys = esc_parchment(len(rows), bottom=CHEAT_PANEL_BOTTOM)
        opts = ''.join("        [ .TIPO_OPCION UIC_BOTONTEXTO .ID '%s' .PARAMS [ %s.TEXT %s .FONDO [ .X 381 .Y %d ] %s ] ]\r\n"
                       % (bid, '.BOTON 0 ' if k == 0 else '', key, y, _BTN_SOUNDS)
                       for k, ((bid, key), y) in enumerate(zip(rows, ys)))
        pages += ('\r\n[ ######################################################################### CHEATS %s ##\r\n'
                  "  .ID '%s'\r\n  .CONTROLES\r\n  [\r\n"
                  "    [ .TIPO UIC_TECLA .ID 'MESC' .PARAMS [ .TECLA KEY_ESCAPE .MKEYS [ ] .EVENTOS [ KEY_DOWN KEY_UP ] ] ]\r\n"
                  % (menu_id, menu_id) +
                  _bitmaps(pieces, ['FOND'] + ['FON%d' % (k + 2) for k in range(len(pieces) - 1)]) +
                  "    [ .TIPO UIC_GESTOROPCIONES .ID 'CHGO'\r\n      .PARAMS\r\n      [\r\n       .OPCIONES\r\n       [\r\n" +
                  opts +
                  "       ]\r\n       .TECLAS [ .TECLA_SUBIR KEY_UP .TECLA_BAJAR KEY_DOWN .TECLA_CLICK KEY_RETURN .GESTION_CIRCULAR TRUE ]\r\n"
                  "      ]\r\n    ]\r\n  ]\r\n  .ENLACES\r\n  [\r\n" +
                  ''.join("    [ .CONTROL_ID '%s' .MENU_ID %s ]\r\n" % lk for lk in links) + "  ]\r\n]\r\n")
    txt = txt[:em1_a] + em1 + txt[em1_b:]
    nl = txt.index('\n', em1_a + len(em1)) + 1                       # after the '#MENU 1' comment of that line
    txt = txt[:nl] + pages + txt[nl:]
    out(rel, txt.encode('latin1'))


def production_queue_ui():
    """Production dialogs (buildings / troops+ships): the human's queues hold up to 12 waiting items (exe patch 27),
    the queue viewers show 5 resp. 6 cards. Their own definitions carry the original vertical scroll bar commented
    out ('#.SLIDER'), the same one the dialog uses for its list of buildings: switch it on so every queued card can be
    scrolled to (one row of cards per step), and centre cards + scroll bar in the queue box of the dialog art
    (inner box x 233-706 in both MenuComprar*.tga; cards 5 x 87 / 6 x 72, scroll bar 3 + 20 px)."""
    base = 'Game/UI/ModeloGestion/UIDefsInfoProduccion/'
    for fn, old_x, new_x in (('UIDefs_VisorMatrizProduciendoseEdificios.sb', 252, 241),
                             ('UIDefs_VisorMatrizProduciendoseEfectivos.sb', 250, 242)):
        txt = mod_or_src(base + fn).decode('latin1')
        txt, n1 = re.subn(r'^(\s*)\.X %d\b' % old_x, r'\g<1>.X %d' % new_x, txt, count=1, flags=re.M)
        txt, n2 = re.subn(r'^(\s*)#\s*\.SLIDER \[', r'\g<1>.SLIDER [', txt, count=1, flags=re.M)
        assert n1 == 1 and n2 == 1, (fn, n1, n2)
        out(base + fn, txt.encode('latin1'))


# texts of the cheat menu; the resource buttons use each language's own resource names (LTEXT_LEYENDA_BARRA_*)
CHEAT_TEXTS = {
    'english': dict(CHEATS='Cheats', FASTBUILD='Fast Construction', FASTTRAIN='Fast Recruitment', FASTRESEARCH='Fast Research',
                    BACK='Back',
                    FASTBUILD_ON="Fast construction is ON. At the start of each of your turns the first building in every province's queue is completed.",
                    FASTBUILD_OFF='Fast construction is OFF.',
                    FASTTRAIN_ON='Fast recruitment is ON. At the start of each of your turns the first unit in every barracks and shipyard queue is completed.',
                    FASTTRAIN_OFF='Fast recruitment is OFF.',
                    FASTRESEARCH_ON='Fast research is ON. The technologies you are researching are completed at the start of your next turn.',
                    FASTRESEARCH_OFF='Fast research is OFF.'),
    'Russian': dict(CHEATS='Читы', FASTBUILD='Быстрое строительство', FASTTRAIN='Быстрый набор', FASTRESEARCH='Быстрые исследования',
                    BACK='Назад',
                    FASTBUILD_ON='Быстрое строительство ВКЛЮЧЕНО. В начале каждого вашего хода первое здание в очереди каждой провинции будет построено.',
                    FASTBUILD_OFF='Быстрое строительство ВЫКЛЮЧЕНО.',
                    FASTTRAIN_ON='Быстрый набор ВКЛЮЧЕН. В начале каждого вашего хода первый отряд в очереди каждой казармы и верфи будет готов.',
                    FASTTRAIN_OFF='Быстрый набор ВЫКЛЮЧЕН.',
                    FASTRESEARCH_ON='Быстрые исследования ВКЛЮЧЕНЫ. Изучаемые технологии будут завершены в начале вашего следующего хода.',
                    FASTRESEARCH_OFF='Быстрые исследования ВЫКЛЮЧЕНЫ.'),
    'German': dict(CHEATS='Cheats', FASTBUILD='Schneller Bau', FASTTRAIN='Schnelle Rekrutierung', FASTRESEARCH='Schnelle Forschung',
                   BACK='Zurück',
                   FASTBUILD_ON='Schneller Bau ist AN. Zu Beginn jeder Ihrer Runden wird das erste Gebäude in der Bauliste jeder Provinz fertiggestellt.',
                   FASTBUILD_OFF='Schneller Bau ist AUS.',
                   FASTTRAIN_ON='Schnelle Rekrutierung ist AN. Zu Beginn jeder Ihrer Runden wird die erste Einheit jeder Kaserne und Werft fertiggestellt.',
                   FASTTRAIN_OFF='Schnelle Rekrutierung ist AUS.',
                   FASTRESEARCH_ON='Schnelle Forschung ist AN. Die erforschten Technologien werden zu Beginn Ihrer nächsten Runde abgeschlossen.',
                   FASTRESEARCH_OFF='Schnelle Forschung ist AUS.'),
    'French': dict(CHEATS='Triches', FASTBUILD='Construction rapide', FASTTRAIN='Recrutement rapide', FASTRESEARCH='Recherche rapide',
                   BACK='Retour',
                   FASTBUILD_ON='Construction rapide ACTIVÉE. Au début de chacun de vos tours, le premier bâtiment de la file de chaque province est achevé.',
                   FASTBUILD_OFF='Construction rapide DÉSACTIVÉE.',
                   FASTTRAIN_ON='Recrutement rapide ACTIVÉ. Au début de chacun de vos tours, la première unité de chaque caserne et chantier naval est prête.',
                   FASTTRAIN_OFF='Recrutement rapide DÉSACTIVÉ.',
                   FASTRESEARCH_ON='Recherche rapide ACTIVÉE. Les technologies en cours de recherche sont terminées au début de votre prochain tour.',
                   FASTRESEARCH_OFF='Recherche rapide DÉSACTIVÉE.'),
    'spanish': dict(CHEATS='Trucos', FASTBUILD='Construcción rápida', FASTTRAIN='Reclutamiento rápido', FASTRESEARCH='Investigación rápida',
                    BACK='Volver',
                    FASTBUILD_ON='Construcción rápida ACTIVADA. Al comienzo de cada uno de tus turnos se termina el primer edificio de la cola de cada provincia.',
                    FASTBUILD_OFF='Construcción rápida DESACTIVADA.',
                    FASTTRAIN_ON='Reclutamiento rápido ACTIVADO. Al comienzo de cada uno de tus turnos se termina la primera unidad de cada cuartel y astillero.',
                    FASTTRAIN_OFF='Reclutamiento rápido DESACTIVADO.',
                    FASTRESEARCH_ON='Investigación rápida ACTIVADA. Las tecnologías en investigación se completan al comienzo de tu próximo turno.',
                    FASTRESEARCH_OFF='Investigación rápida DESACTIVADA.'),
    'Italian': dict(CHEATS='Trucchi', FASTBUILD='Costruzione rapida', FASTTRAIN='Reclutamento rapido', FASTRESEARCH='Ricerca rapida',
                    BACK='Indietro',
                    FASTBUILD_ON="Costruzione rapida ATTIVA. All'inizio di ogni tuo turno viene completato il primo edificio in coda in ogni provincia.",
                    FASTBUILD_OFF='Costruzione rapida DISATTIVATA.',
                    FASTTRAIN_ON="Reclutamento rapido ATTIVO. All'inizio di ogni tuo turno viene completata la prima unità di ogni caserma e cantiere navale.",
                    FASTTRAIN_OFF='Reclutamento rapido DISATTIVATO.',
                    FASTRESEARCH_ON="Ricerca rapida ATTIVA. Le tecnologie in ricerca vengono completate all'inizio del tuo prossimo turno.",
                    FASTRESEARCH_OFF='Ricerca rapida DISATTIVATA.'),
    'Polish': dict(CHEATS='Kody', FASTBUILD='Szybka budowa', FASTTRAIN='Szybka rekrutacja', FASTRESEARCH='Szybkie badania',
                   BACK='Wstecz',
                   FASTBUILD_ON='Szybka budowa WŁĄCZONA. Na początku każdej twojej tury pierwszy budynek w kolejce każdej prowincji zostaje ukończony.',
                   FASTBUILD_OFF='Szybka budowa WYŁĄCZONA.',
                   FASTTRAIN_ON='Szybka rekrutacja WŁĄCZONA. Na początku każdej twojej tury pierwszy oddział w kolejce każdych koszar i stoczni jest gotowy.',
                   FASTTRAIN_OFF='Szybka rekrutacja WYŁĄCZONA.',
                   FASTRESEARCH_ON='Szybkie badania WŁĄCZONE. Badane technologie zostają ukończone na początku twojej następnej tury.',
                   FASTRESEARCH_OFF='Szybkie badania WYŁĄCZONE.'),
    'Czech': dict(CHEATS='Cheaty', FASTBUILD='Rychlá stavba', FASTTRAIN='Rychlý nábor', FASTRESEARCH='Rychlý výzkum',
                  BACK='Zpět',
                  FASTBUILD_ON='Rychlá stavba ZAPNUTA. Na začátku každého vašeho tahu se dokončí první budova ve frontě každé provincie.',
                  FASTBUILD_OFF='Rychlá stavba VYPNUTA.',
                  FASTTRAIN_ON='Rychlý nábor ZAPNUT. Na začátku každého vašeho tahu se dokončí první jednotka ve frontě každých kasáren a loděnice.',
                  FASTTRAIN_OFF='Rychlý nábor VYPNUT.',
                  FASTRESEARCH_ON='Rychlý výzkum ZAPNUT. Zkoumané technologie se dokončí na začátku vašeho příštího tahu.',
                  FASTRESEARCH_OFF='Rychlý výzkum VYPNUT.'),
}


# second panel page (exe patches 19+): key suffix -> text; every key becomes LTEXT_UI_CHEAT_<key>
CHEAT_TEXTS_2 = {
    'english': dict(MORE='More...', GODMODE='Godmode', GODMODE_OFF='Godmode is OFF.',
                    GODMODE_ON='Godmode is ON. Your armies and fleets lose no men in battles that are resolved automatically, and they win them.',
                    MOVE='Unlimited Movement', MOVE_OFF='Unlimited movement is OFF.',
                    MOVE_ON='Unlimited movement is ON. Your armies and fleets can move up to 8 provinces per turn, through any territory.',
                    QUEUES='Finish All Queues',
                    QUEUES_DONE='All buildings and units in your construction and recruitment queues have been completed, as far as you could pay for them.',
                    REVEAL='Reveal Map', REVEAL_ON='The whole map is revealed.', REVEAL_OFF='The map is covered by the fog of war again.'),
    'Russian': dict(MORE='Далее...', GODMODE='Режим бога', GODMODE_OFF='Режим бога ВЫКЛЮЧЕН.',
                    GODMODE_ON='Режим бога ВКЛЮЧЕН. Ваши армии и флоты не теряют людей в автоматических сражениях и побеждают в них.',
                    MOVE='Неограниченное движение', MOVE_OFF='Неограниченное движение ВЫКЛЮЧЕНО.',
                    MOVE_ON='Неограниченное движение ВКЛЮЧЕНО. Ваши армии и флоты могут пройти за ход до 8 провинций по любой территории.',
                    QUEUES='Завершить все очереди',
                    QUEUES_DONE='Все здания и отряды в ваших очередях строительства и набора завершены (насколько хватило средств).',
                    REVEAL='Открыть карту', REVEAL_ON='Вся карта открыта.', REVEAL_OFF='Карта снова скрыта туманом войны.'),
    'German': dict(MORE='Mehr...', GODMODE='Gottmodus', GODMODE_OFF='Gottmodus ist AUS.',
                   GODMODE_ON='Gottmodus ist AN. Ihre Armeen und Flotten verlieren in automatisch berechneten Schlachten keine Männer und gewinnen sie.',
                   MOVE='Unbegrenzte Bewegung', MOVE_OFF='Unbegrenzte Bewegung ist AUS.',
                   MOVE_ON='Unbegrenzte Bewegung ist AN. Ihre Armeen und Flotten können pro Runde bis zu 8 Provinzen durch jedes Gebiet ziehen.',
                   QUEUES='Alle Aufträge abschließen',
                   QUEUES_DONE='Alle Gebäude und Einheiten in Ihren Bau- und Rekrutierungslisten wurden fertiggestellt, soweit Sie sie bezahlen konnten.',
                   REVEAL='Karte aufdecken', REVEAL_ON='Die ganze Karte ist aufgedeckt.', REVEAL_OFF='Die Karte ist wieder vom Nebel des Krieges bedeckt.'),
    'French': dict(MORE='Plus...', GODMODE='Mode dieu', GODMODE_OFF='Mode dieu DÉSACTIVÉ.',
                   GODMODE_ON='Mode dieu ACTIVÉ. Vos armées et flottes ne perdent aucun homme dans les batailles résolues automatiquement et les remportent.',
                   MOVE='Mouvement illimité', MOVE_OFF='Mouvement illimité DÉSACTIVÉ.',
                   MOVE_ON="Mouvement illimité ACTIVÉ. Vos armées et flottes peuvent parcourir jusqu'à 8 provinces par tour, à travers n'importe quel territoire.",
                   QUEUES='Terminer toutes les files',
                   QUEUES_DONE='Tous les bâtiments et unités de vos files de construction et de recrutement sont terminés, dans la limite de vos moyens.',
                   REVEAL='Révéler la carte', REVEAL_ON='Toute la carte est révélée.', REVEAL_OFF='La carte est de nouveau couverte par le brouillard de guerre.'),
    'spanish': dict(MORE='Más...', GODMODE='Modo dios', GODMODE_OFF='Modo dios DESACTIVADO.',
                    GODMODE_ON='Modo dios ACTIVADO. Tus ejércitos y flotas no pierden hombres en las batallas resueltas automáticamente y las ganan.',
                    MOVE='Movimiento ilimitado', MOVE_OFF='Movimiento ilimitado DESACTIVADO.',
                    MOVE_ON='Movimiento ilimitado ACTIVADO. Tus ejércitos y flotas pueden recorrer hasta 8 provincias por turno, a través de cualquier territorio.',
                    QUEUES='Terminar todas las colas',
                    QUEUES_DONE='Todos los edificios y unidades de tus colas de construcción y reclutamiento se han completado, en la medida en que pudiste pagarlos.',
                    REVEAL='Revelar mapa', REVEAL_ON='Todo el mapa está revelado.', REVEAL_OFF='El mapa vuelve a estar cubierto por la niebla de guerra.'),
    'Italian': dict(MORE='Altro...', GODMODE='Modalità dio', GODMODE_OFF='Modalità dio DISATTIVATA.',
                    GODMODE_ON='Modalità dio ATTIVA. I tuoi eserciti e le tue flotte non perdono uomini nelle battaglie risolte automaticamente e le vincono.',
                    MOVE='Movimento illimitato', MOVE_OFF='Movimento illimitato DISATTIVATO.',
                    MOVE_ON='Movimento illimitato ATTIVO. I tuoi eserciti e le tue flotte possono percorrere fino a 8 province per turno, attraverso qualsiasi territorio.',
                    QUEUES='Completa tutte le code',
                    QUEUES_DONE='Tutti gli edifici e le unità nelle tue code di costruzione e reclutamento sono stati completati, nei limiti di quanto potevi pagare.',
                    REVEAL='Rivela la mappa', REVEAL_ON="L'intera mappa è rivelata.", REVEAL_OFF='La mappa è di nuovo coperta dalla nebbia di guerra.'),
    'Polish': dict(MORE='Więcej...', GODMODE='Tryb boga', GODMODE_OFF='Tryb boga WYŁĄCZONY.',
                   GODMODE_ON='Tryb boga WŁĄCZONY. Twoje armie i floty nie tracą ludzi w bitwach rozstrzyganych automatycznie i wygrywają je.',
                   MOVE='Nieograniczony ruch', MOVE_OFF='Nieograniczony ruch WYŁĄCZONY.',
                   MOVE_ON='Nieograniczony ruch WŁĄCZONY. Twoje armie i floty mogą przejść w jednej turze do 8 prowincji przez dowolne terytorium.',
                   QUEUES='Ukończ wszystkie kolejki',
                   QUEUES_DONE='Wszystkie budynki i oddziały w twoich kolejkach budowy i rekrutacji zostały ukończone, na ile było cię stać.',
                   REVEAL='Odkryj mapę', REVEAL_ON='Cała mapa jest odkryta.', REVEAL_OFF='Mapę znów pokrywa mgła wojny.'),
    'Czech': dict(MORE='Další...', GODMODE='Režim boha', GODMODE_OFF='Režim boha VYPNUT.',
                  GODMODE_ON='Režim boha ZAPNUT. Vaše armády a loďstva neztrácejí v automaticky vyhodnocených bitvách žádné muže a vítězí v nich.',
                  MOVE='Neomezený pohyb', MOVE_OFF='Neomezený pohyb VYPNUT.',
                  MOVE_ON='Neomezený pohyb ZAPNUT. Vaše armády a loďstva mohou za tah projít až 8 provincií jakýmkoli územím.',
                  QUEUES='Dokončit všechny fronty',
                  QUEUES_DONE='Všechny budovy a jednotky ve vašich frontách stavby a náboru byly dokončeny, pokud jste je mohli zaplatit.',
                  REVEAL='Odhalit mapu', REVEAL_ON='Celá mapa je odhalena.', REVEAL_OFF='Mapu opět zakrývá mlha války.'),
}


# exe patches 23-26: raise an army, free construction, peace with all, everyone friendly
CHEAT_TEXTS_3 = {
    'english': dict(SPAWN='Raise Army', FREE='Free Construction', PEACE='Peace with All', FRIENDLY='Everyone Friendly',
                    SPAWN_DONE='A new army (a marshal with six battalions of your best troops) has been raised in your capital, or in another of your provinces with room for it.',
                    SPAWN_FAIL='No army could be raised: none of your provinces has room for another army.',
                    FREE_ON='Free construction is ON. Your buildings, troops and ships cost nothing.', FREE_OFF='Free construction is OFF.',
                    PEACE_DONE='You are now at peace with every nation that was at war with you.',
                    FRIENDLY_DONE='Every nation is now friendly towards you.'),
    'Russian': dict(SPAWN='Собрать армию', FREE='Бесплатное строительство', PEACE='Мир со всеми', FRIENDLY='Все дружелюбны',
                    SPAWN_DONE='Новая армия (маршал и шесть батальонов ваших лучших войск) собрана в вашей столице или в другой провинции, где есть место.',
                    SPAWN_FAIL='Армию собрать не удалось: ни в одной вашей провинции нет места для еще одной армии.',
                    FREE_ON='Бесплатное строительство ВКЛЮЧЕНО. Здания, войска и корабли ничего не стоят.',
                    FREE_OFF='Бесплатное строительство ВЫКЛЮЧЕНО.',
                    PEACE_DONE='Теперь вы в мире со всеми странами, которые воевали с вами.',
                    FRIENDLY_DONE='Все страны теперь дружелюбны к вам.'),
    'German': dict(SPAWN='Armee aufstellen', FREE='Kostenloser Bau', PEACE='Frieden mit allen', FRIENDLY='Alle freundlich',
                   SPAWN_DONE='Eine neue Armee (ein Marschall mit sechs Bataillonen Ihrer besten Truppen) wurde in Ihrer Hauptstadt oder einer anderen Provinz mit freiem Platz aufgestellt.',
                   SPAWN_FAIL='Es konnte keine Armee aufgestellt werden: In keiner Ihrer Provinzen ist Platz für eine weitere Armee.',
                   FREE_ON='Kostenloser Bau ist AN. Gebäude, Truppen und Schiffe kosten nichts.', FREE_OFF='Kostenloser Bau ist AUS.',
                   PEACE_DONE='Sie haben jetzt Frieden mit allen Nationen, die mit Ihnen im Krieg waren.',
                   FRIENDLY_DONE='Alle Nationen sind Ihnen jetzt freundlich gesinnt.'),
    'French': dict(SPAWN='Lever une armée', FREE='Construction gratuite', PEACE='Paix avec tous', FRIENDLY='Tous amicaux',
                   SPAWN_DONE='Une nouvelle armée (un maréchal et six bataillons de vos meilleures troupes) a été levée dans votre capitale ou dans une autre province ayant de la place.',
                   SPAWN_FAIL="Aucune armée n'a pu être levée : aucune de vos provinces n'a de place pour une armée de plus.",
                   FREE_ON='Construction gratuite ACTIVÉE. Bâtiments, troupes et navires ne coûtent rien.',
                   FREE_OFF='Construction gratuite DÉSACTIVÉE.',
                   PEACE_DONE='Vous êtes maintenant en paix avec toutes les nations qui étaient en guerre contre vous.',
                   FRIENDLY_DONE='Toutes les nations vous sont maintenant amicales.'),
    'spanish': dict(SPAWN='Reclutar ejército', FREE='Construcción gratuita', PEACE='Paz con todos', FRIENDLY='Todos amistosos',
                    SPAWN_DONE='Se ha reclutado un nuevo ejército (un mariscal y seis batallones de tus mejores tropas) en tu capital o en otra provincia con espacio.',
                    SPAWN_FAIL='No se pudo reclutar ningún ejército: ninguna de tus provincias tiene espacio para otro ejército.',
                    FREE_ON='Construcción gratuita ACTIVADA. Edificios, tropas y barcos no cuestan nada.',
                    FREE_OFF='Construcción gratuita DESACTIVADA.',
                    PEACE_DONE='Ahora estás en paz con todas las naciones que estaban en guerra contigo.',
                    FRIENDLY_DONE='Todas las naciones son ahora amistosas contigo.'),
    'Italian': dict(SPAWN='Arruola esercito', FREE='Costruzione gratuita', PEACE='Pace con tutti', FRIENDLY='Tutti amichevoli',
                    SPAWN_DONE="Un nuovo esercito (un maresciallo e sei battaglioni delle tue truppe migliori) è stato arruolato nella tua capitale o in un'altra provincia con spazio libero.",
                    SPAWN_FAIL='Non è stato possibile arruolare un esercito: nessuna delle tue province ha spazio per un altro esercito.',
                    FREE_ON='Costruzione gratuita ATTIVA. Edifici, truppe e navi non costano nulla.',
                    FREE_OFF='Costruzione gratuita DISATTIVATA.',
                    PEACE_DONE='Ora sei in pace con tutte le nazioni che erano in guerra con te.',
                    FRIENDLY_DONE='Tutte le nazioni ora sono amichevoli verso di te.'),
    'Polish': dict(SPAWN='Zbierz armię', FREE='Darmowa budowa', PEACE='Pokój ze wszystkimi', FRIENDLY='Wszyscy przyjaźni',
                   SPAWN_DONE='Nowa armia (marszałek i sześć batalionów twoich najlepszych wojsk) została zebrana w twojej stolicy lub w innej prowincji z wolnym miejscem.',
                   SPAWN_FAIL='Nie udało się zebrać armii: w żadnej z twoich prowincji nie ma miejsca na kolejną armię.',
                   FREE_ON='Darmowa budowa WŁĄCZONA. Budynki, wojska i okręty nic nie kosztują.', FREE_OFF='Darmowa budowa WYŁĄCZONA.',
                   PEACE_DONE='Masz teraz pokój ze wszystkimi narodami, które były z tobą w stanie wojny.',
                   FRIENDLY_DONE='Wszystkie narody są teraz do ciebie przyjaźnie nastawione.'),
    'Czech': dict(SPAWN='Postavit armádu', FREE='Stavba zdarma', PEACE='Mír se všemi', FRIENDLY='Všichni přátelští',
                  SPAWN_DONE='Nová armáda (maršál a šest praporů vašich nejlepších vojsk) byla postavena ve vašem hlavním městě nebo v jiné provincii s volným místem.',
                  SPAWN_FAIL='Armádu se nepodařilo postavit: v žádné vaší provincii není místo pro další armádu.',
                  FREE_ON='Stavba zdarma ZAPNUTA. Budovy, vojska a lodě nic nestojí.', FREE_OFF='Stavba zdarma VYPNUTA.',
                  PEACE_DONE='Nyní máte mír se všemi národy, které s vámi válčily.',
                  FRIENDLY_DONE='Všechny národy jsou k vám nyní přátelské.'),
}


# third panel page 'EM_6' (exe patches 32-39): super troops, heal, veterans, intelligence, upkeep, general, fleet, cows
CHEAT_TEXTS_4 = {
    'english': dict(SUPER='Super Troops', SUPER_OFF='Super troops are OFF.',
                    SUPER_ON='Super troops are ON. In every battle, real-time or resolved automatically, your battalions deal three times the damage and take a third of it.',
                    HEAL='Heal All Armies', HEAL_DONE='All your battalions are back at full strength, free of charge.',
                    VETS='Elite Veterans', VETS_DONE='All your battalions now have the highest experience rank.',
                    INTEL='Full Intelligence', INTEL_OFF='Full intelligence is OFF.',
                    INTEL_ON='Full intelligence is ON. You see everything a spy network and a foreign ministry can reveal, on land and at sea.',
                    UPKEEP='No Army Upkeep', UPKEEP_OFF='No army upkeep is OFF.',
                    UPKEEP_ON='No army upkeep is ON. Your armies and fleets cost nothing to maintain.',
                    GENERAL='Free General',
                    GENERAL_DONE='A new general (a marshal without troops) is waiting in your capital, or in another of your provinces with room for an army.',
                    GENERAL_FAIL='No general could be placed: none of your provinces has room for another army.',
                    FLEET='Free Fleet',
                    FLEET_DONE='Four warships of your best class have been launched in one of your ports. They form a new fleet if there is room for one; otherwise they wait in the port.',
                    FLEET_FAIL='No ships could be launched: you have no port.',
                    COWS='Cow Cavalry', COWS_OFF='Cow cavalry is OFF.',
                    COWS_ON='Cow cavalry is ON. In real-time battles all cavalry, on every side, rides cows.'),
    'Russian': dict(SUPER='Супервойска', SUPER_OFF='Супервойска ВЫКЛЮЧЕНЫ.',
                    SUPER_ON='Супервойска ВКЛЮЧЕНЫ. В каждом сражении, в реальном времени или автоматическом, ваши батальоны наносят втрое больше урона и получают лишь треть.',
                    HEAL='Вылечить все армии', HEAL_DONE='Все ваши батальоны бесплатно восстановлены до полной численности.',
                    VETS='Элитные ветераны', VETS_DONE='Все ваши батальоны получили высший ранг опыта.',
                    INTEL='Полная разведка', INTEL_OFF='Полная разведка ВЫКЛЮЧЕНА.',
                    INTEL_ON='Полная разведка ВКЛЮЧЕНА. Вы видите все, что могут раскрыть шпионская сеть и министерство иностранных дел, на суше и на море.',
                    UPKEEP='Бесплатное содержание', UPKEEP_OFF='Бесплатное содержание армии ВЫКЛЮЧЕНО.',
                    UPKEEP_ON='Бесплатное содержание армии ВКЛЮЧЕНО. Содержание ваших армий и флотов ничего не стоит.',
                    GENERAL='Бесплатный генерал',
                    GENERAL_DONE='Новый генерал (маршал без войск) ждет в вашей столице или в другой провинции, где есть место для армии.',
                    GENERAL_FAIL='Генерала разместить не удалось: ни в одной вашей провинции нет места для еще одной армии.',
                    FLEET='Бесплатный флот',
                    FLEET_DONE='В одном из ваших портов спущены на воду четыре военных корабля лучшего класса. Если есть место, они образуют новый флот, иначе ждут в порту.',
                    FLEET_FAIL='Спустить корабли на воду не удалось: у вас нет порта.',
                    COWS='Коровья кавалерия', COWS_OFF='Коровья кавалерия ВЫКЛЮЧЕНА.',
                    COWS_ON='Коровья кавалерия ВКЛЮЧЕНА. В сражениях в реальном времени вся кавалерия всех сторон скачет на коровах.'),
    'German': dict(SUPER='Supertruppen', SUPER_OFF='Supertruppen sind AUS.',
                   SUPER_ON='Supertruppen sind AN. In jeder Schlacht, ob in Echtzeit oder automatisch berechnet, richten Ihre Bataillone dreifachen Schaden an und erleiden nur ein Drittel.',
                   HEAL='Alle Armeen heilen', HEAL_DONE='Alle Ihre Bataillone sind kostenlos wieder auf voller Stärke.',
                   VETS='Elite-Veteranen', VETS_DONE='Alle Ihre Bataillone haben jetzt den höchsten Erfahrungsrang.',
                   INTEL='Volle Aufklärung', INTEL_OFF='Volle Aufklärung ist AUS.',
                   INTEL_ON='Volle Aufklärung ist AN. Sie sehen alles, was ein Spionagenetz und ein Außenministerium aufdecken können, zu Land und zur See.',
                   UPKEEP='Kein Armeeunterhalt', UPKEEP_OFF='Kein Armeeunterhalt ist AUS.',
                   UPKEEP_ON='Kein Armeeunterhalt ist AN. Ihre Armeen und Flotten kosten keinen Unterhalt.',
                   GENERAL='Kostenloser General',
                   GENERAL_DONE='Ein neuer General (ein Marschall ohne Truppen) wartet in Ihrer Hauptstadt oder in einer anderen Provinz mit Platz für eine Armee.',
                   GENERAL_FAIL='Es konnte kein General aufgestellt werden: In keiner Ihrer Provinzen ist Platz für eine weitere Armee.',
                   FLEET='Kostenlose Flotte',
                   FLEET_DONE='Vier Kriegsschiffe Ihrer besten Klasse sind in einem Ihrer Häfen vom Stapel gelaufen. Sie bilden eine neue Flotte, wenn Platz dafür ist; sonst warten sie im Hafen.',
                   FLEET_FAIL='Es konnten keine Schiffe vom Stapel laufen: Sie haben keinen Hafen.',
                   COWS='Kuh-Kavallerie', COWS_OFF='Kuh-Kavallerie ist AUS.',
                   COWS_ON='Kuh-Kavallerie ist AN. In Echtzeitschlachten reitet die gesamte Kavallerie aller Seiten auf Kühen.'),
    'French': dict(SUPER='Super troupes', SUPER_OFF='Super troupes DÉSACTIVÉES.',
                   SUPER_ON="Super troupes ACTIVÉES. Dans chaque bataille, en temps réel ou résolue automatiquement, vos bataillons infligent trois fois plus de dégâts et n'en subissent qu'un tiers.",
                   HEAL='Soigner les armées', HEAL_DONE='Tous vos bataillons ont retrouvé leur pleine force, gratuitement.',
                   VETS="Vétérans d'élite", VETS_DONE="Tous vos bataillons ont maintenant le rang d'expérience le plus élevé.",
                   INTEL='Renseignement total', INTEL_OFF='Renseignement total DÉSACTIVÉ.',
                   INTEL_ON="Renseignement total ACTIVÉ. Vous voyez tout ce qu'un réseau d'espions et un ministère des Affaires étrangères peuvent révéler, sur terre comme sur mer.",
                   UPKEEP='Armée sans entretien', UPKEEP_OFF='Armée sans entretien DÉSACTIVÉE.',
                   UPKEEP_ON='Armée sans entretien ACTIVÉE. Vos armées et flottes ne coûtent rien à entretenir.',
                   GENERAL='Général gratuit',
                   GENERAL_DONE='Un nouveau général (un maréchal sans troupes) attend dans votre capitale ou dans une autre province ayant de la place pour une armée.',
                   GENERAL_FAIL="Aucun général n'a pu être placé : aucune de vos provinces n'a de place pour une armée de plus.",
                   FLEET='Flotte gratuite',
                   FLEET_DONE="Quatre navires de guerre de votre meilleure classe ont été lancés dans l'un de vos ports. Ils forment une nouvelle flotte s'il y a de la place ; sinon ils attendent au port.",
                   FLEET_FAIL="Aucun navire n'a pu être lancé : vous n'avez aucun port.",
                   COWS='Cavalerie bovine', COWS_OFF='Cavalerie bovine DÉSACTIVÉE.',
                   COWS_ON='Cavalerie bovine ACTIVÉE. Dans les batailles en temps réel, toute la cavalerie, de tous les camps, monte des vaches.'),
    'spanish': dict(SUPER='Supertropas', SUPER_OFF='Supertropas DESACTIVADAS.',
                    SUPER_ON='Supertropas ACTIVADAS. En cada batalla, en tiempo real o resuelta automáticamente, tus batallones causan el triple de daño y reciben solo un tercio.',
                    HEAL='Curar ejércitos', HEAL_DONE='Todos tus batallones vuelven a estar al completo, gratis.',
                    VETS='Veteranos de élite', VETS_DONE='Todos tus batallones tienen ahora el rango de experiencia más alto.',
                    INTEL='Inteligencia total', INTEL_OFF='Inteligencia total DESACTIVADA.',
                    INTEL_ON='Inteligencia total ACTIVADA. Ves todo lo que una red de espionaje y un ministerio de asuntos exteriores pueden revelar, en tierra y en el mar.',
                    UPKEEP='Sin mantenimiento', UPKEEP_OFF='Sin mantenimiento DESACTIVADO.',
                    UPKEEP_ON='Sin mantenimiento ACTIVADO. Mantener tus ejércitos y flotas no cuesta nada.',
                    GENERAL='General gratuito',
                    GENERAL_DONE='Un nuevo general (un mariscal sin tropas) espera en tu capital o en otra de tus provincias con espacio para un ejército.',
                    GENERAL_FAIL='No se pudo colocar ningún general: ninguna de tus provincias tiene espacio para otro ejército.',
                    FLEET='Flota gratuita',
                    FLEET_DONE='Se han botado cuatro buques de guerra de tu mejor clase en uno de tus puertos. Forman una nueva flota si hay espacio; si no, esperan en el puerto.',
                    FLEET_FAIL='No se pudo botar ningún barco: no tienes ningún puerto.',
                    COWS='Caballería vacuna', COWS_OFF='Caballería vacuna DESACTIVADA.',
                    COWS_ON='Caballería vacuna ACTIVADA. En las batallas en tiempo real toda la caballería, de todos los bandos, monta vacas.'),
    'Italian': dict(SUPER='Super truppe', SUPER_OFF='Super truppe DISATTIVATE.',
                    SUPER_ON='Super truppe ATTIVE. In ogni battaglia, in tempo reale o risolta automaticamente, i tuoi battaglioni infliggono il triplo dei danni e ne subiscono un terzo.',
                    HEAL='Cura gli eserciti', HEAL_DONE='Tutti i tuoi battaglioni sono tornati al completo, gratuitamente.',
                    VETS="Veterani d'élite", VETS_DONE='Tutti i tuoi battaglioni hanno ora il grado di esperienza più alto.',
                    INTEL='Spionaggio totale', INTEL_OFF='Spionaggio totale DISATTIVATO.',
                    INTEL_ON='Spionaggio totale ATTIVO. Vedi tutto ciò che una rete di spie e un ministero degli esteri possono rivelare, per terra e per mare.',
                    UPKEEP='Nessun mantenimento', UPKEEP_OFF='Nessun mantenimento DISATTIVATO.',
                    UPKEEP_ON='Nessun mantenimento ATTIVO. Mantenere i tuoi eserciti e le tue flotte non costa nulla.',
                    GENERAL='Generale gratuito',
                    GENERAL_DONE="Un nuovo generale (un maresciallo senza truppe) ti attende nella capitale o in un'altra tua provincia con spazio per un esercito.",
                    GENERAL_FAIL='Non è stato possibile schierare un generale: nessuna delle tue province ha spazio per un altro esercito.',
                    FLEET='Flotta gratuita',
                    FLEET_DONE="Quattro navi da guerra della tua classe migliore sono state varate in uno dei tuoi porti. Formano una nuova flotta se c'è spazio; altrimenti restano in porto.",
                    FLEET_FAIL='Non è stato possibile varare alcuna nave: non hai porti.',
                    COWS='Cavalleria bovina', COWS_OFF='Cavalleria bovina DISATTIVATA.',
                    COWS_ON='Cavalleria bovina ATTIVA. Nelle battaglie in tempo reale tutta la cavalleria, di ogni schieramento, cavalca mucche.'),
    'Polish': dict(SUPER='Superwojska', SUPER_OFF='Superwojska WYŁĄCZONE.',
                   SUPER_ON='Superwojska WŁĄCZONE. W każdej bitwie, w czasie rzeczywistym lub rozstrzyganej automatycznie, twoje bataliony zadają trzykrotnie większe straty i ponoszą tylko jedną trzecią.',
                   HEAL='Ulecz wszystkie armie', HEAL_DONE='Wszystkie twoje bataliony bezpłatnie odzyskały pełną siłę.',
                   VETS='Elitarni weterani', VETS_DONE='Wszystkie twoje bataliony mają teraz najwyższy stopień doświadczenia.',
                   INTEL='Pełny wywiad', INTEL_OFF='Pełny wywiad WYŁĄCZONY.',
                   INTEL_ON='Pełny wywiad WŁĄCZONY. Widzisz wszystko, co mogą ujawnić siatka szpiegowska i ministerstwo spraw zagranicznych, na lądzie i na morzu.',
                   UPKEEP='Bez utrzymania armii', UPKEEP_OFF='Bez utrzymania armii WYŁĄCZONE.',
                   UPKEEP_ON='Bez utrzymania armii WŁĄCZONE. Utrzymanie twoich armii i flot nic nie kosztuje.',
                   GENERAL='Darmowy generał',
                   GENERAL_DONE='Nowy generał (marszałek bez wojsk) czeka w twojej stolicy lub w innej prowincji z miejscem na armię.',
                   GENERAL_FAIL='Nie udało się umieścić generała: w żadnej z twoich prowincji nie ma miejsca na kolejną armię.',
                   FLEET='Darmowa flota',
                   FLEET_DONE='W jednym z twoich portów zwodowano cztery okręty wojenne najlepszej klasy. Tworzą nową flotę, jeśli jest na nią miejsce; w przeciwnym razie czekają w porcie.',
                   FLEET_FAIL='Nie udało się zwodować żadnego okrętu: nie masz portu.',
                   COWS='Krowia kawaleria', COWS_OFF='Krowia kawaleria WYŁĄCZONA.',
                   COWS_ON='Krowia kawaleria WŁĄCZONA. W bitwach w czasie rzeczywistym cała kawaleria wszystkich stron jeździ na krowach.'),
    'Czech': dict(SUPER='Supervojska', SUPER_OFF='Supervojska VYPNUTA.',
                  SUPER_ON='Supervojska ZAPNUTA. V každé bitvě, v reálném čase i automaticky vyhodnocené, způsobují vaše prapory trojnásobné ztráty a samy utrpí jen třetinu.',
                  HEAL='Vyléčit všechny armády', HEAL_DONE='Všechny vaše prapory mají zdarma opět plný stav.',
                  VETS='Elitní veteráni', VETS_DONE='Všechny vaše prapory mají nyní nejvyšší stupeň zkušeností.',
                  INTEL='Úplná rozvědka', INTEL_OFF='Úplná rozvědka VYPNUTA.',
                  INTEL_ON='Úplná rozvědka ZAPNUTA. Vidíte vše, co může odhalit špionážní síť a ministerstvo zahraničí, na souši i na moři.',
                  UPKEEP='Bez údržby armády', UPKEEP_OFF='Bez údržby armády VYPNUTO.',
                  UPKEEP_ON='Bez údržby armády ZAPNUTO. Údržba vašich armád a loďstev nic nestojí.',
                  GENERAL='Generál zdarma',
                  GENERAL_DONE='Nový generál (maršál bez vojsk) čeká ve vašem hlavním městě nebo v jiné provincii s místem pro armádu.',
                  GENERAL_FAIL='Generála se nepodařilo umístit: v žádné vaší provincii není místo pro další armádu.',
                  FLEET='Loďstvo zdarma',
                  FLEET_DONE='V jednom z vašich přístavů byly spuštěny na vodu čtyři válečné lodě vaší nejlepší třídy. Pokud je místo, tvoří nové loďstvo; jinak čekají v přístavu.',
                  FLEET_FAIL='Nepodařilo se spustit na vodu žádnou loď: nemáte žádný přístav.',
                  COWS='Kraví jízda', COWS_OFF='Kraví jízda VYPNUTA.',
                  COWS_ON='Kraví jízda ZAPNUTA. V bitvách v reálném čase jezdí veškerá jízda všech stran na kravách.'),
}


def cheat_texts():
    """LTEXT keys of the cheat menu in Management/TextUIGestionMapa.sb of every language (latin1 or UTF-16 kept)."""
    frel = 'Management/TextUIGestionMapa.sb'
    for lang in LANGS:
        p_ = os.path.join(MOD, 'Texto', lang, frel)
        raw = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text(lang, frel))
        u16 = raw[:2] == b'\xff\xfe'
        txt = raw[2:].decode('utf-16-le') if u16 else raw.decode('latin1')
        if 'LTEXT_UI_ESCMENU_CHEATS' in txt:
            continue
        res = dict(re.findall(r'\.(LTEXT_LEYENDA_BARRA_\w+)\s+"([^"]*)"', txt))
        t = CHEAT_TEXTS[lang]
        entries = [('LTEXT_UI_ESCMENU_CHEATS', t['CHEATS']), ('LTEXT_UI_CHEATS_TITLE', t['CHEATS']), ('LTEXT_UI_CHEAT_BACK', t['BACK'])]
        for key, bar in (('GOLD', 'DINERO'), ('FOOD', 'COMIDA'), ('RAW', 'MAT_PRIMAS'), ('MEN', 'POBLACION')):
            entries.append(('LTEXT_UI_CHEAT_' + key, res['LTEXT_LEYENDA_BARRA_' + bar] + ' +10000'))
        for k, v in (list(t.items()) + list(CHEAT_TEXTS_2[lang].items()) + list(CHEAT_TEXTS_3[lang].items()) +
                     list(CHEAT_TEXTS_4[lang].items())):
            if k not in ('CHEATS', 'BACK'):
                entries.append(('LTEXT_UI_CHEAT_' + k, v))
        for k_, v_ in entries:
            assert '"' not in v_ and (u16 or all(ord(ch) < 256 for ch in v_)), (lang, k_)
        out('Texto/%s/%s' % (lang, frel), text_add_entries(raw, entries))


def quest_texts():
    """Six quests with names of a later age (Simon Bolivar, Railway, World Fair, 100,000 Sons of St. Louis, Treaty of Amiens,
    Universal Declaration of Human Rights) re-themed to 1789 in Management/TextQuests.sb of every language (tools/quest_texts.py).
    TEXT ONLY: no .mng record or enum entry, DefQuest.sb, requirement or reward changes, so running campaigns stay valid.
    All languages get the English text (as nations.texts_new does for the other new texts); Russian replaces it from
    build/i18n/ru_quests.json in apply_translations()."""
    import quest_texts as QT
    for lang in LANGS:
        p_ = os.path.join(MOD, 'Texto', lang, QT.QUEST_REL)
        fresh = not os.path.exists(p_)
        raw = read(src_text(lang, QT.QUEST_REL)) if fresh else open(p_, 'rb').read()
        if fresh and lang == 'english':           # lengths and placeholders against the original English texts
            QT.check(dict(re.findall(r'\[\s*\.(LTEXT_\w+)\s+"([^"]*)"', raw.decode('latin1'))))
        out('Texto/%s/%s' % (lang, QT.QUEST_REL), QT.apply(raw))


def reskin_officer_texts():
    """Officer names of the reskinned slots: the Southern Kingdoms (Moldavia's slot) read the Moldavian pool, the Kazakh
    Khanate (Hanover's slot) and the Sahel Kingdoms (Saxony's slot) share the Germanic pool (exe: player -> pool mapping).
    The original pool texts are replaced in place, whole pools, in all 8 languages (English; Russian from ru_names.json).
    TEXT ONLY: the keys stay, so no enum, record or id changes (tools/nations.py RESKIN_POOL / RESKIN_OFFICERS).
    Exe patch 47: the Sahel Kingdoms then get their OWN officer names, NEW keys ..._MANDO_JUG_SAJONIA<n> appended to the same
    file (NT.sahel_officer_texts: English, Russian names in the Russian file; not in ru_names.json)."""
    for frel, values in NT.reskin_officer_texts().items():
        for lang in LANGS:
            p_ = os.path.join(MOD, 'Texto', lang, frel)
            raw = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text(lang, frel))
            new, found = text_set_values(raw, values)
            assert found == set(values), (lang, frel, sorted(set(values) - found))
            out('Texto/%s/%s' % (lang, frel), new)
    for lang in LANGS:
        for frel, values in NT.sahel_officer_texts(lang).items():
            p_ = os.path.join(MOD, 'Texto', lang, frel)
            raw = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text(lang, frel))
            new, found = text_set_values(raw, values)          # set if present, else append (keeps the file's encoding)
            out('Texto/%s/%s' % (lang, frel), text_add_entries(new, [(k, v) for k, v in values.items() if k not in found]))


# --- Quick Game for every playable nation (user 2026-10-21: a new nation showed white troop buttons, Auto-Buy did
#     nothing). The original data covers only the five empires; quick_game_ui adds, for every other PLAYABLE nation:
#     - the bought-troop cards <COUNTRY>_<TYPE>_BTN_SOLTADO / _PULSADO (57x79; exe FUN_007ce640 builds the key from the
#       troop record's country; a missing key silently refuses the purchase). Each card is the nation's own battle
#       button (57x91, the one the battle UI shows: <COUNTRY>_ / ARABE_ / NEUTRAL_<TYPE>_BTN_INFO_TROPA, i.e. the
#       painted art of make_icons' EspecialesMod atlases) rows 0..70 plus the original card's closing bottom rows
#       71..78: exactly how Pyro's own cards relate to their battle buttons (rows 0..70 pixel-identical for the five);
#     - the troop-type button atlas Plantilla<COUNTRY>.tga (76x80 cells at the template UVs of
#       UI_DefsSelectArmyButtons.sb; read through exe patch 42): the nation's card in each cell;
#     - Auto-Buy .PAIS blocks (army and navy) copied from France's 15 configurations, each type mapped to the
#       nation's own roster (QG_TROOP_SUB / QG_SHIP_SUB), prices and experience as in the original.
#     The header (patch 41) and the Select Empire text (patch 43) are exe-only. The five keep every original byte.
QG_ICONS, QG_BUTTONS = 'Game/UI/MainMenu/Tropas/Iconos/', 'Game/UI/MainMenu/Tropas/Botones/'
QG_ORIG = ('GRAN_BRETANYA', 'FRANCIA', 'AUSTRIA', 'RUSIA', 'PRUSIA')
QG_ARAB = ('EGIPTO', 'OTOMANO', 'TUNEZ', 'TRIPOLITANIA', 'MARRUECOS')   # battle buttons 'ARABE_' (exe FUN_005bca90)
QG_TROOP_SUB = {      # a France Auto-Buy type the nation lacks -> the first of these it has (same arm, nearest role)
    'MILICIA': ['FUSILERO', 'TIRADOR'], 'FUSILERO': ['MILICIA', 'TIRADOR', 'CAZADOR'],
    'TIRADOR': ['CAZADOR', 'FUSILERO', 'MILICIA'], 'CAZADOR': ['TIRADOR', 'FUSILERO', 'MILICIA'],
    'GRANADERO': ['ELITE', 'FUSILERO', 'TIRADOR'], 'ELITE': ['GRANADERO', 'FUSILERO', 'TIRADOR'],
    'CAB_HUSAR': ['CAB_LANCERO', 'CAM_TIRADOR', 'CAB_DRAGON', 'CAM_LANCERO'],
    'CAB_LANCERO': ['CAM_LANCERO', 'CAB_HUSAR', 'CAM_TIRADOR', 'CAB_DRAGON'],
    'CAB_DRAGON': ['CAM_TIRADOR', 'CAB_HUSAR', 'CAB_LANCERO', 'CAM_LANCERO'],
    'CAB_CORACERO': ['CAB_ELITE', 'CAB_DRAGON', 'CAM_LANCERO', 'CAB_LANCERO', 'CAB_HUSAR'],
    'CANON_CAB': ['CANON_CAMP', 'CANON'], 'OBUS_CAB': ['OBUS', 'CANON_CAMP', 'CANON'],
    'CANON_CAMP': ['CANON', 'CANON_CAB'], 'CANON': ['CANON_CAMP', 'CANON_CAB'],
    'OBUS': ['MORTERO', 'OBUS_CAB', 'CANON'], 'MORTERO': ['OBUS', 'OBUS_CAB', 'CANON']}
QG_SHIP_SUB = {'NAVIO': ['FRAGATA', 'CORBETA'], 'FRAGATA': ['CORBETA', 'NAVIO'], 'CORBETA': ['FRAGATA', 'NAVIO']}
QG_CARD, QG_CELL = (57, 79), (76, 80)
QG_SEL_GAIN = 1.24     # the originals' SELECCIONADO band is the SOLTADO figure x ~1.24 (PlantillaFrancia.tga)


def _qg_path(rel):
    """Case-insensitive file of a game path ('/' or '\\'): mod/ first, then data1/, data/ (like the paks)."""
    parts = [p for p in rel.replace('\\', '/').split('/') if p]
    for base in (MOD, DATA1, DATA):
        cur = base
        for p in parts:
            if not os.path.isdir(cur):
                cur = None; break
            names = {n.lower(): n for n in os.listdir(cur)}
            if p.lower() not in names:
                cur = None; break
            cur = os.path.join(cur, names[p.lower()])
        if cur and os.path.isfile(cur):
            return cur
    raise FileNotFoundError(rel)


def _qg_tga(img):
    """32-bit uncompressed TGA, bottom-up with the TGA 2.0 footer, as the game's own files (make_icons.save_tga)."""
    import numpy as np
    a = np.asarray(img.convert('RGBA'))
    hdr = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, a.shape[1], a.shape[0], 32, 8)
    return hdr + np.ascontiguousarray(a[::-1, :, [2, 1, 0, 3]]).tobytes() + b'\0' * 8 + b'TRUEVISION-XFILE.\0'


def quick_game_ui():
    import numpy as np
    from PIL import Image
    BS, CRLF_ = '\\', '\r\n'
    m = Mng(open(os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read())
    penum, cenum = Mng.parse_enum(m.table(0)), Mng.parse_enum(m.table(1))
    tenum, senum = Mng.parse_enum(m.table(5)), Mng.parse_enum(m.table(13))
    countries = []                                       # playable countries other than the five, in player order
    for p in parse_players(m.section(2)):
        k = cenum.get(p['country'])
        if penum.get(p['idx']) in NT.PLAYABLE and k not in QG_ORIG and k not in countries:
            countries.append(k)
    roster, ships = {}, {}
    for r in split_records(m.section(7), 'troop'):
        t = tenum[struct.unpack_from('<I', r, 0)[0]]
        k = cenum.get(struct.unpack_from('<I', r, NT._owner_field(r, 23, 13))[0])
        if t not in NT.OFFICER_TYPES and t not in roster.setdefault(k, []):
            roster[k].append(t)
    for r in split_records(m.section(15), 'ship'):
        t = senum[struct.unpack_from('<I', r, 0)[0]]
        k = cenum.get(struct.unpack_from('<I', r, NT._owner_field(r, 30, 10))[0])
        if t not in ships.setdefault(k, []):
            ships[k].append(t)
    assert all(len(k) <= 60 for k in countries), 'exe patch 42 builds the atlas name in a 128-byte buffer'

    # original Quick Game card pools (the seven registered in UICParams.sb) and battle-button pools (Batalla)
    pools = ['Austria', 'Francia', 'Inglaterra', 'Prusia', 'Rusia', 'Especiales', 'Genericos']
    qg = {}
    for n in pools:
        t = mod_or_src(QG_ICONS + n + '/UIDefs_PoolTropasIcons.sb').decode('latin1')
        for mm in re.finditer(r'\.KEY (\w+)\s+\.PARAMS \[ \.FILE "([^"]+)" \.U (\d+) \.V (\d+) \.SX (\d+) \.SY (\d+)', t):
            qg[mm.group(1)] = (mm.group(2), int(mm.group(3)), int(mm.group(4)))
    btn = {}
    for n in ('Default', 'Francia', 'Inglaterra', 'Austria', 'Prusia', 'Rusia', 'Especiales'):
        t = mod_or_src('Game/UI/ModeloBatalla/InterfazPaises/%s/UIDefs_BtnTropas.sb' % n).decode('latin1')
        for mm in re.finditer(r'\.KEY (\w+)_BTN_INFO_TROPA\s+\.PARAMS\s*\[[^\]]*?\.FONDO\s*\[\s*\.SX 57 \.SY 91'
                              r'((?:[^\[\]]*\[[^\[\]]*\])+)', t):       # the FONDO's state entries (either order)
            st = {s: (f, int(u), int(v)) for s, f, u, v in
                  re.findall(r'\.(SOLTADO|PULSADO)\s*\[\s*\.FILE "([^"]+)"\s*\.U (\d+)\s*\.V (\d+)\s*\]', mm.group(2))}
            if len(st) == 2:
                btn[mm.group(1)] = (st['SOLTADO'], st['PULSADO'])
    assert 'NEUTRAL_FUSILERO' in btn and 'DEFAULT' in btn, sorted(btn)[:8]
    cache = {}

    def pix(rel):
        if rel not in cache:
            cache[rel] = np.asarray(Image.open(_qg_path(rel)).convert('RGBA'))
        return cache[rel]
    # the closing bottom rows 71..78 of the originals' cards (per-pixel median of four empires' cards, per state)
    bottom = {}
    for st in ('SOLTADO', 'PULSADO'):
        bots = [pix(f)[v + 71:v + 79, u:u + 57] for kk, (f, u, v) in qg.items()
                if kk.endswith('_BTN_' + st) and kk.split('_')[0] in ('AUSTRIA', 'FRANCIA', 'GRAN', 'RUSIA')]
        assert len(bots) >= 60, (st, len(bots))
        bottom[st] = np.median(np.stack(bots), axis=0).round().astype(np.uint8)

    def source(k, t):
        for b in (('ARABE' if k in QG_ARAB else k) + '_' + t, 'NEUTRAL_' + t, 'ARABE_' + t, 'DEFAULT'):
            if b in btn:
                return b
    # cards to make: one per distinct battle button
    need, src_of = [], {}
    for k in countries:
        for t in roster.get(k, []):
            if '%s_%s_BTN_SOLTADO' % (k, t) in qg:
                continue                                 # Pyro's own card (Especiales / Genericos minors)
            b = source(k, t); src_of[(k, t)] = b
            if b not in need:
                need.append(b)
    per_row, pairs = (1024 - 1) // 58, (1024 - 1) // 158
    cells, atlases = {}, []
    for i, b in enumerate(need):
        n, j = divmod(i, per_row * pairs)
        if j == 0:
            atlases.append(Image.new('RGBA', (1024, 1024), (0, 0, 0, 0)))
        rel = QG_ICONS + 'Mod/IconosMod%d.tga' % (n + 1)
        u, v = 1 + (j % per_row) * 58, 1 + (j // per_row) * 158
        for si, st in enumerate(('SOLTADO', 'PULSADO')):
            f, bu, bv = btn[b][si]
            card = np.concatenate([pix(f)[bv:bv + 71, bu:bu + 57], bottom[st]], 0)
            atlases[-1].paste(Image.fromarray(card, 'RGBA'), (u, v + 79 * si))
        cells[b] = (rel, u, v)
    for n, im in enumerate(atlases):
        out(QG_ICONS + 'Mod/IconosMod%d.tga' % (n + 1), _qg_tga(im))
    sb = ('###############################################################################################################'
          + CRLF_ + '# Tropas de las naciones del mod (generado por tools/make_map.py quick_game_ui): carta = boton de batalla'
          + CRLF_ + '# de la nacion (filas 0..70) + cierre inferior de las cartas originales' + CRLF_
          + '###############################################################################################################'
          + CRLF_ + CRLF_)
    keys = set()
    for (k, t), b in src_of.items():
        rel, u, v = cells[b]
        for si, st in enumerate(('SOLTADO', 'PULSADO')):
            key = '%s_%s_BTN_%s' % (k, t, st)
            assert key not in keys and key not in qg, key
            keys.add(key)
            sb += ('[' + CRLF_ + ' .KEY %s' % key + CRLF_ + ' .PARAMS [ .FILE "%s" .U %d .V %d .SX 57 .SY 79 .ALPHA TRUE'
                   ' .PRIORITY 40 ]' % (rel.replace('/', BS), u, v + 79 * si) + CRLF_ + ']' + CRLF_ + CRLF_)
    out(QG_ICONS + 'Mod/UIDefs_PoolTropasIcons.sb', sb.encode('latin1'))
    rel = 'Game/GameModes/MainMenu/UICParams.sb'
    t = mod_or_src(rel).decode('latin1')
    anchor = '%Game' + BS + 'UI' + BS + 'MainMenu' + BS + 'Tropas' + BS + 'Iconos' + BS + 'Genericos' + BS + 'UIDefs_PoolTropasIcons.sb'
    line = '%' + (QG_ICONS + 'Mod/UIDefs_PoolTropasIcons.sb').replace('/', BS)
    if line not in t:
        i = t.index(anchor) + len(anchor)
        t = t[:i] + CRLF_ + '    ' + line + t[i:]
    out(rel, t.encode('latin1'))

    # troop-type button atlases (exe patch 42): the nation's card in each template cell, 3 states
    tb = read(src('Game/UI/MainMenu/UI_DefsSelectArmyButtons.sb')).decode('latin1')
    tpl = {}
    for mm in re.finditer(r'\.(\w+)\s*\[\s*\.IDSELECTSOUND[^\[]*\.FONDO\s*\[[^\[]*?\.SX (\d+) \.SY (\d+)[^\[]*'
                          r'\.SOLTADO\s*\[[^\]]*?\.U (\d+) \.V (\d+) \]\s*\.SELECCIONADO\s*\[[^\]]*?\.U (\d+) \.V (\d+)\s*\]\s*'
                          r'\.PULSADO\s*\[[^\]]*?\.U (\d+) \.V (\d+)\s*\]', tb):
        assert (int(mm.group(2)), int(mm.group(3))) == QG_CELL, mm.group(1)
        tpl[mm.group(1)] = [(int(mm.group(i)), int(mm.group(i + 1))) for i in (4, 6, 8)]
    assert len(tpl) == 16, sorted(tpl)

    def card(k, t, st):                                  # the 57x79 card the pool gives (k, t) in state st
        f, u, v = qg.get('%s_%s_BTN_%s' % (k, t, st)) or (None, None, None)
        if f is None:
            f, u, v = cells[src_of[(k, t)]]
            v += 79 * (st == 'PULSADO')
        return Image.fromarray(np.ascontiguousarray(pix(f)[v:v + 79, u:u + 57]), 'RGBA')
    ox, oy = (QG_CELL[0] - QG_CARD[0]) // 2, QG_CELL[1] - QG_CARD[1]
    for k in countries:
        im = Image.new('RGBA', (512, 1024), (0, 0, 0, 0))
        for t in roster.get(k, []):
            if t not in tpl:
                continue                                 # no troop-type button in the original screen (camels, ...)
            sol, pul = card(k, t, 'SOLTADO'), card(k, t, 'PULSADO')
            a = np.asarray(sol).astype(np.float64)
            a[..., :3] = np.clip(a[..., :3] * QG_SEL_GAIN, 0, 255)
            sel = Image.fromarray(a.round().astype(np.uint8), 'RGBA')
            for (u, v), c in zip(tpl[t], (sol, sel, pul)):
                im.paste(c, (u + ox, v + oy))
        out(QG_BUTTONS + 'Plantilla%s.tga' % k, _qg_tga(im))

    # Auto-Buy: France's block per nation, types mapped to the nation's roster; configs left empty are dropped
    def autobuy(rel, rost, sub):
        t = read(src(rel)).decode('latin1')
        pais = t.index('.PAIS "FRANCIA"')
        a0, b0 = find_block(t, t.rfind('[', 0, pais))
        tmpl = t[a0:b0]
        add, done = '', {}
        for k in countries:
            have = rost.get(k, [])
            if not have or re.search(r'\.PAIS\s+"%s"' % k, t):
                continue
            lines, n_drop = [], 0
            for ln in tmpl.split(CRLF_):
                mm = re.search(r'\.TIPO\s+"(\w+)"', ln)
                if mm:
                    nt = next((c for c in [mm.group(1)] + sub.get(mm.group(1), []) if c in have), None)
                    if nt is None:
                        n_drop += 1; continue
                    ln = ln[:mm.start(1)] + nt + ln[mm.end(1):]
                elif ln.lstrip().startswith('#'):
                    ln = ln.replace('FRANCIA', k)
                lines.append(ln)
            blk = CRLF_.join(lines).replace('.PAIS "FRANCIA"', '.PAIS "%s"' % k)
            ca, cb = find_block(blk, blk.index('.CONFIGS'))
            body, j, kept, n_cfg = blk[ca + 1:cb - 1], 0, '', 0
            while True:
                try:
                    xa, xb = find_block(body, j)
                except ValueError:
                    break
                seg = body[j:xb]
                if '.TIPO' in body[xa:xb]:
                    kept += seg; n_cfg += 1
                j = xb
            blk = blk[:ca + 1] + kept + body[j:] + blk[cb - 1:]
            assert n_cfg, (rel, k, 'no Auto-Buy configuration left')
            add += CRLF_ + '#------------------------------------------------ %s (make_map.quick_game_ui, from FRANCIA) ' % k \
                + '-' * max(3, 40 - len(k)) + ' ' + CRLF_ + blk + CRLF_
            done[k] = (n_cfg, len(re.findall(r'\.TIPO', blk)), n_drop)
        A, B = find_block(t, t.index('.AUTOBUY'))
        out(rel, (t[:B - 1] + add + CRLF_ + t[B - 1:]).encode('latin1'))
        return done
    ab_army = autobuy('Game/UI/MainMenu/UIDefs_SelectArmyAutoBuy.sb', roster, QG_TROOP_SUB)
    ab_navy = autobuy('Game/UI/MainMenu/UIDefs_SelectNavyAutoBuy.sb', ships, QG_SHIP_SUB)

    # texts the exe patches read: LTEXT_PAIS_<country> (header, 41) and the player's info key (Select Empire, 43)
    def keys_of(frel):
        p_ = os.path.join(MOD, 'Texto', 'english', frel)
        raw = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text('english', frel))
        txt = raw[2:].decode('utf-16-le') if raw[:2] == b'\xff\xfe' else raw.decode('latin1')
        return {mm.group(1): mm.group(2) for mm in re.finditer(r'\.(\w+)\s+"([^"]*)"', txt)}
    pais_t, info_t = keys_of('Management/TextPaises.sb'), keys_of('Others/TextUIMainMenu.sb')
    info_of = {cenum.get(p['country']): p['info'] for p in parse_players(m.section(2))}
    # a country whose record names another key (EPAPALES -> LTEXT_PAIS_E_PAPALES): LTEXT_PAIS_<country> gets a copy of
    # that text in every language (same words, so no new translation)
    rec_key = {cenum.get(c['idx']): c['ltext'] for c in Mng.parse_countries(m.section(3))}
    alias = {k: rec_key[k] for k in countries if not pais_t.get('LTEXT_PAIS_' + k) and pais_t.get(rec_key.get(k))}
    frel = 'Management/TextPaises.sb'
    for lang in LANGS if alias else ():
        p_ = os.path.join(MOD, 'Texto', lang, frel)
        raw = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text(lang, frel))
        txt = raw[2:].decode('utf-16-le') if raw[:2] == b'\xff\xfe' else raw.decode('latin1')
        vals = {mm.group(1): mm.group(2) for mm in re.finditer(r'\.(\w+)\s+"([^"]*)"', txt)}
        add_ = [('LTEXT_PAIS_' + k, vals[r]) for k, r in alias.items() if r in vals and 'LTEXT_PAIS_' + k not in vals]
        if add_:
            out('Texto/%s/%s' % (lang, frel), text_add_entries(raw, add_))
    pais_t = keys_of(frel)
    miss = [k for k in countries if not pais_t.get('LTEXT_PAIS_' + k)]
    miss_info = [k for k in countries if not info_t.get(info_of.get(k) or '-')]
    print('  quick game: %d nations, %d cards (%d distinct, %d atlas), %d button atlases, Auto-Buy army %d / navy %d'
          % (len(countries), len(src_of), len(need), len(atlases), len(countries), len(ab_army), len(ab_navy)))
    if miss or miss_info:
        print('  quick game: WARNING texts missing: LTEXT_PAIS_', miss, 'info', miss_info)
    return {'countries': countries, 'roster': roster, 'ships': ships, 'src_of': src_of, 'qg': qg, 'tpl': tpl,
            'army': ab_army, 'navy': ab_navy, 'miss_pais': miss, 'miss_info': miss_info}


AI_SKIP_QUESTS = False  # True = the AI ignores the 16 quests (faster AI, but not original)
AI_PLANNING_TWEAK = False  # True = shorter AI military planning horizon and fewer scouts (faster, but weaker AI)
# True = scripted historical events (tools/historical_events.py, prepared 2026-10-22): campaign sequence Lua + 8-language
# texts, together with the exe patches 48-50 (nations.HISTORICAL_EVENTS is set from this; hook eh_inicio_turno, get_turno_actual,
# firma_paz_entre). Messages only, effects off (EH_PERMITE_* in the Lua). False = byte-identical build; Lua only, save-safe.
HISTORICAL_EVENTS = False
AUTOSAVE_EVERY, AUTOSAVE_FILES = 1, 8   # autosave every turn, keep 8 (original: every 3rd turn, 5 files)
PLATE_TEST = False     # one extra row of test tiles south of the map (engine test, worked 2026-10-15)
PLATE_WORLD = True     # the extended 9 x 7 tile map painted by tools/styled.py (build/tiles_new)
NEW_COLS, NEW_ROWS_SOUTH = 9, 3
ORIGINAL_FOG_TEST = False   # test build: keep the original fog plane
# fog points of the new provinces / sea zones / extension pieces: start density (area per point = spacing^2) for
# meshgen.fog_positions, which adds points to thin shapes until 90 % of the area is at least half cleared
# (2026-10-23; was a 420 grid with a 150 margin + a 60 cap, which left many provinces with 2 points). Total Dummies
# 3786 -> 4247: every province clones the whole model, so raise these to trade clarity for memory / load time.
FOG_LAND_SPACING, FOG_SEA_SPACING = 520.0, 540.0
SWAP_TEST = False          # test build: Venecia moved east, New South Wales moved into Europe
NO_BACKGROUND_TEST = False  # test build: leave out the new background plane (are province meshes drawn?)


def world_tiles():
    """(r, c, texture name) of every tile of the bigger map that is not one of the original 16."""
    res = []
    for row in range(4 + NEW_ROWS_SOUTH):
        for col in range(NEW_COLS):
            r = 3 - row
            if not (0 <= r <= 3 and col <= 3) and os.path.exists(os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))):
                res.append((r, col, 'T0%02d%03d.tga' % (r + 10, col)))
    return res


SCEN_TEMPLATE = {}         # new scenario name -> battle scenario it reuses
SCEN_PROV = {}             # new scenario name -> province enum key (land provinces)
# new battlefields generated by tools/lvl_caucasus.py (and later regions) into build/battlemaps/: their scenario
# names (e.g. "93" Chechenya) get their own .lvl, minimap and intro texts (tools/battlemaps.py). Data only, no
# mng/id change. The first in-game test (2026-10-21 13:47) crashed at load (0x4d3017: casilla centres on sector
# edges); fixed in lvl_nav.py and checked by tools/lvl_audit.py. Second in-game test with this on.
# 2026-10-21: + three shared regional maps from tools/lvl_region.py (NBDesierto / NBIndia / NBEstepa): each serves
# the provinces listed in its battlemap.json (their scenario names point at the one .lvl; not yet tested in game).
NEW_BATTLE_MAPS = True
WORLD_PROVINCES = True     # provinces of the 1789 proposal on the bigger map (tools/world_provinces.py)
WORLD_OWNER = {'GB': 'GRAN_BRETANYA', 'FR': 'FRANCIA', 'NL': 'BATAVIA', 'PT': 'PORTUGAL', 'ES': 'ESPANYA', 'RU': 'RUSIA',
               'OT': 'OTOMANO', 'KZ': 'HANNOVER'}          # everything else (also Omani Swahili coast): free for now
# battle map (template province) per region: several originals of a similar landscape, picked per province, so the
# 195 land provinces do not all fight on the same few fields (the first entry was the only one before)
WORLD_TEMPLATE = {'Vest-Afrika': ['Marruecos', 'Tunez', 'Tripolitania', 'Algarbe', 'Andalucia'],
                  'Sentral- og Øst-Afrika': ['Egipto', 'Cirenaica', 'Tripolitania', 'Anatolia', 'Grecia'],
                  'Sør-Afrika': ['Andalucia', 'Castilla', 'Aragon', 'Alentejo', 'Algarbe'],
                  'Midtøsten og Sentral-Asia': ['Anatolia', 'Egipto', 'Cirenaica', 'RegionBalcanica', 'Kursk'],
                  'India': ['Andalucia', 'Napoles', 'Sicilia', 'Cataluna', 'Grecia', 'Castilla'],
                  'Sørøst-Asia': ['Sicilia', 'Napoles', 'Venecia', 'Lombardia', 'Grecia'],
                  'Øst-Asia': ['Hungria', 'Bohemia', 'Kiev', 'Silesia', 'Galicia', 'Lombardia'],
                  'Sibir': ['Finlandia', 'Noruega', 'Suecia', 'Letonia', 'Moscu'],
                  'Australia og Oseania': ['Castilla', 'Aragon', 'Andalucia', 'Alentejo']}
WORLD_NAMES = {'Elfenbenskysten': 'Ivory Coast', 'Oyo og Dahomey': 'Oyo and Dahomey', 'Nord-Somalia': 'North Somalia',
               'Sør-Somalia': 'South Somalia', 'Kamerun': 'Cameroon', 'Swahilikysten': 'Swahili Coast',
               'Kappkolonien': 'Cape Colony', 'Madagaskar': 'Madagascar', 'Jemen': 'Yemen', 'Semiretsje': 'Semirechye',
               'Kambodsja': 'Cambodia', 'Kokinkina': 'Cochinchina', 'Sør-Sumatra': 'South Sumatra',
               'Små Sundaøyene': 'Lesser Sunda Islands', 'Nord-Borneo': 'North Borneo', 'Sør-Borneo': 'South Borneo',
               'Molukkene': 'Moluccas', 'Vest-Ny-Guinea': 'West New Guinea', 'Øst-Ny-Guinea': 'East New Guinea',
               'Øst-Turkestan': 'East Turkestan', 'Dsungaria': 'Dzungaria', 'Ytre Mongolia': 'Outer Mongolia',
               'Indre Mongolia': 'Inner Mongolia', 'Mandsjuria': 'Manchuria', 'Kyushu og Shikoku': 'Kyushu and Shikoku',
               'Jenisej': 'Yenisei', 'Jakutsk': 'Yakutsk', 'Kamtsjatka': 'Kamchatka', 'Tsjukotka': 'Chukotka',
               'Nordøst-Australia': 'North-East Australia', 'Nord-Australia': 'North Australia',
               'Sør-Australia': 'South Australia', 'Vest-Australia': 'West Australia', 'Van Diemens land': "Van Diemen's Land",
               'Nordøya': 'North Island', 'Sørøya': 'South Island', 'Etiopia': 'Ethiopia', 'Mysore': 'Mysore',
               'Futa Jallon': 'Futa Jallon', 'Mosambik': 'Mozambique', 'Kongo': 'Kongo', 'Jenisej': 'Yenisei'}
WORLD_DESC = {'GRAN_BRETANYA': 'held by the British East India Company and the Crown',
              'BATAVIA': 'a Dutch colonial possession', 'PORTUGAL': 'a Portuguese colony', 'ESPANYA': 'a Spanish colony',
              'FRANCIA': 'a French trading colony', 'RUSIA': 'part of Russian Siberia', 'OTOMANO': 'under the Ottoman Sultan',
              'ARABIA': 'under the Saudi emirs of Diriyah', 'HANNOVER': 'roamed by the Kazakh hordes',
              'PLIBREDUMMY': 'ruled by local princes, chiefs and khans'}
WORLD_DESC.update({'EGIPTO': 'ruled by the Mamluk beys of Egypt', 'TRIPOLITANIA': 'tributary to the Pasha of Tripoli',
                   'SAJONIA': 'roamed by the Tuareg of the Sahara'})
WORLD_DESC.update({'QING': 'ruled by the Qianlong Emperor of the Qing', 'JAPAN': 'under the Tokugawa shogunate',
                   'MARATHA': 'held by the chiefs of the Maratha Confederacy', 'ETHIOPIA': 'under the Solomonic emperors at Gondar',
                   'TURKESTAN': 'ruled by the emirs of Bukhara', 'PERSIA': 'under the Qajar shahs of Persia',
                   'CHECHNYA': 'in arms with Sheikh Mansur', 'INDEPENDENT': 'ruled by local princes, chiefs and khans'})
for _k in ('PRINCES', 'SHEIKHS', 'NILE', 'PACIFIC', 'MOLDAVIA'):
    WORLD_DESC[_k] = WORLD_DESC['INDEPENDENT']
WORLD_DESC['SAJONIA'] = 'ruled by Tuareg chiefs and the kings of the Sahel'
# 1789 names (re_tools/report_history.md)
WORLD_NAMES.update({'Aïr': 'Agadez', 'Air': 'Agadez', 'Nord-Somalia': 'Adal', 'Sør-Somalia': 'Benadir', 'Namibia': 'Namaqualand',
                    'Semiretsje': 'Middle Horde', 'Pune': 'Poona', 'Awadh': 'Oudh', 'Tomsk': 'Tobolsk',
                    'Øst-Turkestan': 'Kashgaria', 'Kokinkina': 'Saigon', 'Swahilikysten': 'Zanzibar Coast',
                    'Nord-Australia': 'Arnhem Land', 'Nordøst-Australia': 'Carpentaria', 'Vest-Australia': 'New Holland',
                    'Sør-Australia': 'Nuyts Land', 'Vest-Ny-Guinea': 'New Guinea', 'Øst-Ny-Guinea': 'Papua'})


WORLD_PID = {}             # world province key -> pid
SEA_PID = {}               # sea zone key -> pid
PROV_POS = {}              # province idx -> (x, z) inside it (AI graph node position)
PORT_TEXTS = []            # (LTEXT_PUERTO_*, harbour name) of the new ports
NEW_PORTS = True           # ports of the new coastal provinces (tools/ports.py)
SEA_ZONES = True           # sea zones of the bigger map (build/sea/sea_zones.json, tools/art/sea/sea_zones.py)
SEA_PIDS = set()
SEA_NB = {}                # pid -> neighbouring sea zones: ('NEW', pid) or original mesh names
SEA_SCEN = {}              # new scenario name -> naval battle scenery it reuses (Sceneries.sb)
OPEN_OCEAN = {'ethiopic', 'southern_w', 'southern_m', 'southern_e', 'indian', 'pacific_n', 'pacific_w', 'pacific_s'}


def add_sea_zones(shapes):
    """Maritime provinces for the new oceans (pids 400..), cloned from the original Atlantic zones."""
    data = json.load(open(os.path.join(BUILD, 'sea', 'sea_zones.json'), encoding='utf8'))
    pid_of, pid = {}, 400
    for key in sorted(data):
        z = data[key]
        disp = __import__('unicodedata').normalize('NFKD', z['name']).encode('ascii', 'ignore').decode()
        mesh = 'S' + re.sub(r'[^A-Za-z]', '', disp)
        ekey = 'S_' + re.sub(r'[^A-Z]', '_', disp.upper()).strip('_')
        tmpl = 'OceanoAtlantico' if key in OPEN_OCEAN else 'CostaMarroqui'
        PROVINCES[pid] = (ekey, mesh, disp, 'PLIBREDUMMY', tmpl, None, '%s, open to all flags in 1789.' % disp)
        bx0, bx1 = MG.COLS[0] + 1.0, MG.COLS[0] + 9 * MG.TILE_W - 1.0           # keep inside the map's tile grid
        bz0, bz1 = MG.ROWS[0] - 3 * MG.TILE_H + 1.0, MG.ROWS[4] - 1.0
        poly = [(min(max(q[0], bx0), bx1), min(max(q[1], bz0), bz1)) for q in z['poly']]
        shapes[pid] = [q for k, q in enumerate(poly) if q != poly[k - 1]]
        assert MG.is_simple(shapes[pid]), disp
        SEA_PIDS.add(pid); pid_of[key] = pid; SEA_PID[key] = pid
        pid += 1
    for key, z in data.items():
        SEA_NB[pid_of[key]] = [('NEW', pid_of[n]) if n in pid_of else n for n in z['neighbours_sea']]
    print('  sea zones:', len(pid_of))


def on_map_tiles(poly):
    """False for a polygon reaching beyond the map's tile grid (remote extension specks such as WYenisei's): no
    mesh piece is made for it, so it gets no fog points either."""
    try:
        MG.tiles_of(MG.triangulate(MG.ccw([tuple(q) for q in poly])))
        return True
    except AssertionError:
        return False


def fog_stretch_target():
    """(east x, south z) the fog plane is stretched to in plate_world: the new map edge, same margins as the old."""
    import plate as PL
    x1 = PL.tile_rect(0, NEW_COLS - 1)[1]
    z0 = PL.tile_rect(-NEW_ROWS_SOUTH, 0)[2]
    old_x1, old_z0 = PL.tile_rect(0, 3)[1], PL.tile_rect(0, 0)[2]
    return x1 - (old_x1 - 20222.0), z0 + (-996.4 - old_z0)


def fog_plane_box():
    """World box (x0, x1, z0, z1) of the fog plane the build ships (Niebla.V3D header box at offset 146, where the
    engine computes the fog texture): fog points outside it clear nothing."""
    x0, _, z0, x1, _, z1 = struct.unpack_from('<6f', open(src('Game/GameModes/Gestion/Mapa/Niebla/Niebla.V3D'), 'rb').read(), 146)
    if PLATE_WORLD and not ORIGINAL_FOG_TEST:
        x1, z0 = fog_stretch_target()
    return x0, x1, z0, z1


def add_ports(m, idx_of, shapes, bld):
    """Ports of the new coastal provinces (section 6): the only land-sea link the engine knows."""
    import ports as PT
    recs = Mng.parse_provinces(m.section(4)); provs = {r['idx']: r for r in recs}
    c6 = m.section(6); prts = PT.parse_ports(c6)
    t4 = m.table(4); nxt = max(Mng.parse_enum(t4)) + 1
    used = set(Mng.parse_enum(t4).values()) | {r['ltext'] for r in prts}     # every PUE_* / LTEXT_PUERTO_* so far
    new = []
    for key, (zone, name) in PT.NEW_PORTS.items():
        if key not in WORLD_PID or zone not in SEA_PID:
            print('  port skipped (no province / zone):', key, zone); continue
        lpid, spid = WORLD_PID[key], SEA_PID[zone]
        land, sidx = provs[idx_of[lpid]], idx_of[spid]
        etag = re.sub(r'[^A-Z]', '_', __import__('unicodedata').normalize('NFKD', name).encode('ascii', 'ignore').decode().upper())
        tag = PT.PORT_TAGS.get(key) or etag
        # a repeated text key renames an existing port (Java's 'Batavia' turned the Dutch home port's texts into
        # Batavia): such a port gets its own TEXT tag in ports.PORT_TAGS. Its ENUM name stays as it was in the builds
        # the user's saves were made with (renaming enum keys is not save-safe), so PUE_BATAVIA stays duplicated.
        assert 'LTEXT_PUERTO_' + tag not in used, ('port text key not unique', key, tag)
        assert 'PUE_' + etag not in used or key in PT.PORT_TAGS, ('port enum not unique', key, etag)
        used |= {'PUE_' + etag, 'LTEXT_PUERTO_' + tag}
        Mng.enum_add(t4, nxt, 'PUE_' + etag)
        r1, r2, r3 = PT.rings(provs, sidx)
        r = dict(idx=nxt, ltext='LTEXT_PUERTO_' + tag, ldesc='', cat=1, nb=[], r1=r1, r2=r2, r3=r3)
        prts.append(r); new.append(r)
        land['vals'][13] = nxt
        PORT_TEXTS.append((r['ltext'], name + ' Harbour'))
        PORT_TEXTS.append((r['ltext'] + '_SHORT', name))
        # quay and lighthouse on the coast that faces the port's sea zone
        lp, zp = shapes[lpid], shapes[spid]
        dist = lambda q: min((q[0] - s[0]) ** 2 + (q[1] - s[1]) ** 2 for s in zp[::2])
        ranked = sorted(lp, key=dist)
        c = MG.centre_point(lp)
        q1 = ranked[0]
        q2 = next((q for q in ranked[1:] if math.hypot(q[0] - q1[0], q[1] - q1[1]) > 300), ranked[min(1, len(ranked) - 1)])
        inward = lambda q, d: (q[0] + (c[0] - q[0]) * d / max(1.0, math.hypot(c[0] - q[0], c[1] - q[1])),
                               q[1] + (c[1] - q[1]) * d / max(1.0, math.hypot(c[0] - q[0], c[1] - q[1])))
        e = inward(q1, 140.0); f = inward(q2, 120.0)
        if not MG.point_in(lp, *e):
            e = c
        if not MG.point_in(lp, *f):
            f = e
        Mng.add_position(m.section(13), bld['EMBARCADERO'], land['idx'], e[0], LIFT - 0.0147, e[1])
        Mng.add_position(m.section(13), bld['FARO_ARGAND'], land['idx'], f[0], LIFT - 0.0147, f[1])
        nxt += 1
    for r in new:
        reach = set(r['r1'] + r['r2'] + r['r3'])
        r['nb'] = [o['idx'] for o in prts if o is not r and o['r1'][0] in reach]
    PT.set_ports(c6, prts)
    Mng.set_provinces(m.section(4), recs)
    # every port province starts with its quay (EMBARCADERO, building 33) in the owner player's starting buildings
    # (section 2, entry (33, 0, 0, province, 0)); without it the port network lookup returns null and the game crashes
    players = parse_players(m.section(2))
    cs = Mng.parse_countries(m.section(3))
    owner = {pv: c['idx'] for c in cs for pv in c['provs']}
    port_prov = {r['idx'] for r in recs if r['vals'][13]}
    for pl in players:                                  # drop quays copied from a template into provinces it does not own
        pl['objects'] = [o for o in pl['objects'] if not (o[0] == 33 and (o[3] not in port_prov or owner.get(o[3]) != pl['country']))]
    have = {o[3] for pl in players for o in pl['objects'] if o[0] == 33}
    for r in recs:
        if r['vals'][13] and r['idx'] not in have:
            pl = next(q for q in players if q['country'] == owner[r['idx']])
            pl['objects'].append([33, 0, 0, r['idx'], 0])
    pack_players(m.section(2), players)
    print('  ports added:', len(new))


def provincial_military(m, shapes, idx_of):
    """Data part of exe patch 40 (NT.PROVINCIAL_MILITARY): the human may build the basic military buildings outside
    capitals. 1) The NT.PROVINCIAL_BUILDINGS records get location bit NT.PROVINCIAL_MASK in int 4 (def +0xac): a value
    change only, record ids and order unchanged (save-safe). 2) Every land province without a CUARTEL_BASICO map
    position (mng s13; in the original only capitals have one) gets one, appended at the end of s13: the engine places
    the cuartel model at the (type, province) pair, the barracks / stables / foundry through their prerequisite chain
    at the cuartel's spot (FUN_005d5780), else at the zero vector. The spot is inside the province (new provinces:
    their polygon; original ones: their volume mesh plus extensions, minus land of the new provinces), about 320 units
    from the resource-bar marker and clear of the other markers, at the bar marker's height."""
    if not NT.PROVINCIAL_MILITARY:
        return
    benum = {v: k for k, v in Mng.parse_enum(m.table(7)).items()}
    want = {benum[k] for k in NT.PROVINCIAL_BUILDINGS}
    blds = split_records(m.section(9), 'building')
    ids_before = [struct.unpack_from('<I', r, 0)[0] for r in blds]
    done = 0
    for r in blds:
        if struct.unpack_from('<I', r, 0)[0] in want:
            _, p = rec_strings(r, 3)
            mask = struct.unpack_from('<I', r, p + 16)[0]
            assert mask & 3 and not mask & 4, ('expected a capital-only building', mask)
            struct.pack_into('<I', r, p + 16, mask | NT.PROVINCIAL_MASK)
            done += 1
    assert done == len(want) and [struct.unpack_from('<I', r, 0)[0] for r in blds] == ids_before
    m.section(9).body = b''.join(bytes(r) for r in blds)

    cu, bar_t = benum['CUARTEL_BASICO'], benum['DUMMY_BARRARECURSOS']
    pos = Mng.parse_positions(m.section(13))
    have = {q[1] for q in pos if q[0] == cu}
    bar = {q[1]: q[2:5] for q in pos if q[0] == bar_t}
    marks = {}
    for q in pos:
        marks.setdefault(q[1], []).append((q[2], q[4]))
    pid_of = {v: k for k, v in idx_of.items()}
    new_land = [shapes[p] for p in shapes if p not in SEA_PIDS]
    nbox = [(min(q[0] for q in c), max(q[0] for q in c), min(q[1] for q in c), max(q[1] for q in c)) for c in new_land]
    vol = read(src('Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D'))
    mesh_at = {n: (o, s) for (o, c, s, n, par) in v3d_objects(vol) if c == 0x2000}
    RADII, ANGLES = (320, 260, 380, 200, 450, 520, 150, 600, 700, 100, 800), [math.radians(20 * k) for k in range(18)]
    LEVELS = ((150, 220), (110, 170), (70, 120), (40, 80), (0, 0))       # (clearance from the edge, from other markers)
    added, from_mesh, levels = 0, 0, {}
    for rec in Mng.parse_provinces(m.section(4)):
        i = rec['idx']
        if rec['sea'] or i in have or i not in bar:
            continue
        bx, by, bz = bar[i]
        reach = RADII[-1] + 200
        if i in pid_of:                                  # a province of this mod: its polygon
            poly = shapes[pid_of[i]]

            def inside(x, z, c, poly=poly):
                return MG.point_in(poly, x, z) and (c == 0 or MG.edge_distance(poly, x, z) >= c)
        else:                                            # an original province: volume mesh + extension pieces
            o, s = mesh_at[rec['name']]
            tris = [t for t in MG.mesh_triangles(vol[o:o + s])
                    if max(q[0] for q in t) > bx - reach and min(q[0] for q in t) < bx + reach
                    and max(q[1] for q in t) > bz - reach and min(q[1] for q in t) < bz + reach]
            ext = [[tuple(q) for q in pl] for pl in EXTENSIONS.get(rec['name'], [])]
            cut = [c for c, b in zip(new_land, nbox) if b[0] < bx + reach and b[1] > bx - reach
                   and b[2] < bz + reach and b[3] > bz - reach]

            def on(x, z, tris=tris, ext=ext, cut=cut):
                return ((MG.on_triangles(tris, x, z) or any(MG.point_in(e, x, z) for e in ext))
                        and not any(MG.point_in(c, x, z) for c in cut))

            def inside(x, z, c, on=on):
                return on(x, z) and all(on(x + c * math.cos(a), z + c * math.sin(a)) for a in ANGLES[::2]) if c else on(x, z)
            from_mesh += 1
        others = marks.get(i, [])
        spot = None
        for k, (clear, sep) in enumerate(LEVELS):
            for rad in RADII:
                cand = [(bx + rad * math.cos(a), bz + rad * math.sin(a)) for a in ANGLES]
                cand.sort(key=lambda q: -min([math.hypot(q[0] - ox, q[1] - oz) for ox, oz in others] or [1e9]))
                for x, z in cand:
                    if all(math.hypot(x - ox, z - oz) >= sep for ox, oz in others) and inside(x, z, clear):
                        spot = (x, z); break
                if spot:
                    break
            if spot:
                levels[k] = levels.get(k, 0) + 1
                break
        if spot is None:                                 # nowhere better: at the bar marker itself (inside by design)
            spot = (bx, bz); levels['bar'] = levels.get('bar', 0) + 1
        Mng.add_position(m.section(13), cu, i, spot[0], by, spot[1])
        added += 1
    print('  provincial military: %d records + location bit %#x; %d cuartel spots appended (%d original meshes), '
          'levels %s' % (done, NT.PROVINCIAL_MASK, added, from_mesh, levels))


def add_world_provinces(shapes):
    """Add the provinces of build/world_provinces.json to PROVINCES (pids 101..) and shapes."""
    import world_nations as WN
    data = json.load(open(os.path.join(BUILD, 'world_provinces.json'), encoding='utf8'))
    pid = 101
    pid_of = {}
    for key in sorted(data):
        w = data[key]
        disp = WORLD_NAMES.get(w['name'], w['name'])
        disp = __import__('unicodedata').normalize('NFKD', disp).encode('ascii', 'ignore').decode()
        assert all(ord(ch) < 128 for ch in disp), disp
        owner = WN.EXTRA_OWNER.get(key, WORLD_OWNER.get(w['owner'], 'PLIBREDUMMY'))   # nation provinces: moved later
        mesh = 'W' + re.sub(r'[^A-Za-z]', '', disp)
        ekey = 'W_' + re.sub(r'[^A-Z]', '_', disp.upper()).strip('_')
        choices = WORLD_TEMPLATE[w['region']]
        tmpl = choices[__import__('zlib').crc32(key.encode()) % len(choices)]
        desc = '%s, %s in 1789.' % (disp, WORLD_DESC[owner])
        PROVINCES[pid] = (ekey, mesh, disp, owner, tmpl, None, desc)
        shapes[pid] = [tuple(p) for p in w['poly']]
        assert MG.is_simple(shapes[pid]), disp
        pid_of[key] = pid
        WORLD_PID[key] = pid
        pid += 1
    for nn in NT.NEW_NATIONS:
        if nn.get('world_provinces'):
            nn['provinces'] = [pid_of[k] for k in nn['world_provinces']]
            nn['capital_prov'] = nn['provinces'][0]
    for k, nation in WN.EXTRA_TO_NATION.items():
        next(nn for nn in NT.NEW_NATIONS if nn['key'] == nation)['provinces'].append(pid_of[k])
    # descriptions follow the 1789 ruler, also for provinces that moved to a new nation
    for nn in NT.NEW_NATIONS:
        for p in nn['provinces']:
            if p >= 101 and nn['key'] in WORLD_DESC:
                e = PROVINCES[p]
                PROVINCES[p] = e[:6] + ('%s, %s in 1789.' % (e[2], WORLD_DESC[nn['key']]),)
    # a province still owned by PLIBREDUMMY would crash the game (land provinces need a player)
    moved = {p for nn in NT.NEW_NATIONS for p in nn['provinces']}
    left = [PROVINCES[p][2] for p in PROVINCES if p >= 101 and PROVINCES[p][3] == 'PLIBREDUMMY' and p not in moved]
    assert not left, left
    print('  world provinces:', pid - 101)


def tile_src(col, row):
    """Picture of map tile (col, row from the top): frame-cleaned original (tools/art/deframe.py), new art
    (tools/art/styled2.py via build/tiles_new), else the original tile."""
    for p in (os.path.join(BUILD, 'oldarea', 'tiles', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'art', 'deframe', 'tile_%d_%d.png' % (col, row)),
              os.path.join(BUILD, 'tiles_new', 'tile_%d_%d.png' % (col, row))):
        if os.path.exists(p):
            return p
    return os.path.join(BUILD, 'tiles_png', 'T00%d00%d.png' % (3 - row, col))


def plate_world():
    import plate as PL
    M = 'Game/GameModes/Gestion/Mapa/'
    TN = os.path.join(BUILD, 'tiles_new')
    rects, mats_new, overwrite = [], [], []
    for row in range(4 + NEW_ROWS_SOUTH):
        for col in range(NEW_COLS):
            p = tile_src(col, row)                        # every tile: the background plane covers the whole map
            r = 3 - row                                    # tile row counted from the south, as the game does
            if 0 <= r <= 3 and col <= 3:
                overwrite.append((r, col, p))
            else:
                mats_new.append((r, col, 'T0%02d%03d.tga' % (r + 10, col), p))
    # map plate model: one background plane over every new or repainted area (tile ids fixed by retile below)
    dec = read(src(M + 'MapaDecoracion.V3D'))
    for r, c, name, p in mats_new:
        rects.append((r, c, 0))
    for r, c, p in overwrite:
        rects.append((r, c, 0))
    st, en, _ = PL.find_mesh(dec, 'Decorado06', 'MapaDecoracion')
    blob, nv, nt = PL.plane_mesh(dec[st:en], 'Decorado10', 'MapaDecoracion', rects, 0.80, PL.mesh_count(dec), step=6)   # under the provinces (0.95..0.98) so their tint shows
    if not NO_BACKGROUND_TEST:
        dec = PL.append_object(dec, blob, nv, nt)
    import retile as RT
    dec, nre = RT.rebuild_model(dec)
    print('  retiled %d planes in MapaDecoracion.V3D' % nre)
    x1 = PL.tile_rect(0, NEW_COLS - 1)[1]
    z0 = PL.tile_rect(-NEW_ROWS_SOUTH, 0)[2]
    old_x1, old_z0 = PL.tile_rect(0, 3)[1], PL.tile_rect(0, 0)[2]
    dx, dz = x1 - old_x1, z0 - old_z0
    # desk objects: east side moves with the new east edge, the compass with the south-west corner
    for name in ('Espada', 'fundaespada', 'Tintero', 'Pluma'):
        dec = PL.transform_mesh(dec, name, dx=dx)
    dec = PL.transform_mesh(dec, 'Brujula', dz=dz)
    # the parchment sheet under the map grows with the map
    bx0, bx1, bz0, bz1 = PL.mesh_world_box(dec, 'PergaminosMesa')
    sx = (bx1 - bx0 + dx) / (bx1 - bx0); sz = (bz1 - bz0 - dz) / (bz1 - bz0)
    dec = PL.transform_mesh(dec, 'PergaminosMesa', sx=sx, sz=sz, anchor=(bx0, bz1))
    # Decorado05 is the torn, curled-up paper edge of the old sheet (rises to y 296, above the fog); on the big
    # map it showed slivers of art along the old edges in Kazakhstan and the Sahara: sink it under the table
    dec = PL.transform_mesh(dec, 'Decorado05', dy=-600.0)
    # the old art planes lie at the provinces' height (0.95..1.00); provinces added in the old area z-fight with
    # them (striped Kazakhstan), so they go a little lower, still above the new background plane (0.80)
    for k in (1, 2, 3, 4, 6, 7, 8, 9):
        dec = PL.transform_mesh(dec, 'Decorado%02d' % k, dy=-0.1)
    dec = PL.grow_bbox(dec, x1=x1 + 4000, z0=z0 - 4000)
    out(M + 'MapaDecoracion.V3D', dec)
    # the table under everything
    mesa = read(src(M + 'MapaDecoracion2.V3D'))
    mx0, mx1, mz0, mz1 = PL.mesh_world_box(mesa, 'Mesa')
    mesa = PL.transform_mesh(mesa, 'Mesa', sx=(mx1 - mx0 + dx) / (mx1 - mx0), sz=(mz1 - mz0 - dz) / (mz1 - mz0), anchor=(mx0, mz1))
    mesa = PL.grow_bbox(mesa, x1=mx1 + dx, z0=mz0 + dz)
    out(M + 'MapaDecoracion2.V3D', mesa)
    for f in ('MapaGestion.V3D', 'MapaGestionVolumenes.V3D'):
        pth = os.path.join(MOD, M + f)
        out(M + f, PL.grow_bbox(open(pth, 'rb').read(), x1=x1, z0=z0))
    # fog of war plane (all 46 animation frames) over the whole map, same margins as on the old map
    if not ORIGINAL_FOG_TEST:
        fog, frames = PL.stretch_fog(read(src(M + 'Niebla/Niebla.V3D')), *fog_stretch_target())   # = fog_plane_box()
        out(M + 'Niebla/Niebla.V3D', fog)
        # the fog alpha is computed on the CPU per texel of the plane's second texture (NieblaOpac.tga, 64 x 64),
        # spread over the plane's box: on the bigger map that is coarser than D2, so give it 256 x 128 texels
        from PIL import Image
        op = Image.open(src(M + 'Niebla/NieblaOpac.tga')).convert('RGBA').resize((256, 128), Image.BILINEAR)
        p = os.path.join(MOD, M + 'Niebla/NieblaOpac.tga')
        tga.write_tga(p, 256, 128, [bytearray(op.tobytes()[r * 1024:(r + 1) * 1024]) for r in range(128)])
        print('  wrote', M + 'Niebla/NieblaOpac.tga', '256 x 128')
    # textures (DXT1 with mipmaps, like the game's tiles)
    from PIL import Image
    # textures: the 16 tiles of the game, each now covering 2.25 x 1.75 of the old tiles, 2048 px
    def old_tile(col, row):
        return tile_src(col, row)
    for r in range(4):
        for c in range(4):
            full = os.path.join(MOD, M + 'T00%d00%d.tga' % (r, c)); os.makedirs(os.path.dirname(full), exist_ok=True)
            tga.write_dds_dxt1_mips_np(full, RT.mosaic_tile(r, c, old_tile))
    print('  world plate: 16 tiles of %d px over the whole map, x ..%.0f z %.0f..' % (RT.TEX, x1, z0))



def plate_test():
    import plate as PL, dds
    M = 'Game/GameModes/Gestion/Mapa/'
    r = -1
    names = ['T009%03d.tga' % c for c in range(4)]
    # map plate: four new tile materials in group 0 and a background plane over the new row
    dec = read(src(M + 'MapaDecoracion.V3D'))
    dec, ids = PL.add_tile_materials(dec, [(c, names[c]) for c in range(4)])
    st, en, _ = PL.find_mesh(dec, 'Decorado06', 'MapaDecoracion')
    blob, nv, nt = PL.plane_mesh(dec[st:en], 'Decorado10', 'MapaDecoracion', [(r, c, ids[names[c]]) for c in range(4)],
                                 1.0, PL.mesh_count(dec))
    dec = PL.append_object(dec, blob, nv, nt)
    x0, _, z0, _ = PL.tile_rect(r, 0)
    dec = PL.grow_bbox(dec, z0=z0)
    out(M + 'MapaDecoracion.V3D', dec)
    for f in ('MapaGestion.V3D', 'MapaGestionVolumenes.V3D'):
        p = os.path.join(MOD, M + f)
        out(M + f, PL.grow_bbox(open(p, 'rb').read(), z0=z0))
    # textures: game colours and parchment grain
    w, h, grain = dds.read_dds(os.path.join(DATA, M + 'Detalle2.tga'))
    lum = []
    for r_ in grain:                       # grain as brightness around 0.78..1.0
        row = bytearray(4096)
        for i in range(1024):
            v = (r_[i * 4] * 3 + r_[i * 4 + 1] * 6 + r_[i * 4 + 2]) / 10
            row[i * 4] = min(255, max(0, int(200 + 0.45 * (v - 150))))
        lum.append(row)
    sea, land, edge = (128, 152, 168), (226, 212, 176), (120, 84, 50)
    for c in range(4):
        rows = PL.test_tile(c, lum, sea, land, edge)
        pth = os.path.join(MOD, M + names[c]); os.makedirs(os.path.dirname(pth), exist_ok=True)
        tga.write_dds_dxt1_mips(pth, 1024, 1024, rows)
    print('  plate test: row %d below the map, z %.0f..%.0f, tiles %s' % (r, z0, z0 + PL.TILE_H, names))


def nation_files():
    """Every non-database file the new nations, the flags and the playable list need."""
    new_players = ['JUG_' + nn['key'] for nn in NT.NEW_NATIONS]
    playable_new = [p for p in NT.PLAYABLE if p not in ('JUG_FRANCIA', 'JUG_AUSTRIA', 'JUG_PRUSIA', 'JUG_RUSIA', 'JUG_GRAN_BRETANYA')]
    G = 'Game/GameModes/Gestion/'

    # turn order, hostility, heirs, cost balance
    rel = G + 'DefOrdenTurnos.sb'
    txt = NT.turn_order(mod_or_src(rel).decode('latin1'), new_players, playable_new)
    out(rel, txt.encode('latin1'))
    all_players = re.findall(r'^\s+(JUG_\w+)', txt, re.M)
    all_players = sorted(set(all_players) | set(re.findall(r'^\.(JUG_\w+)', txt, re.M)))
    for f in ('defsInicialesJugadores.sb', 'defsInicialesLocalEasy.sb', 'defsInicialesLocalMedium.sb', 'defsInicialesLocalHard.sb'):
        out(G + f, NT.hostility(mod_or_src(G + f).decode('latin1'), new_players, all_players).encode('latin1'))
    out(G + 'DefHerederos.sb', NT.heirs(mod_or_src(G + 'DefHerederos.sb').decode('latin1'), new_players).encode('latin1'))
    rel = G + 'Balanceo/DefsBalanceoJugadores.sb'
    txt = mod_or_src(rel).decode('latin1')
    add = ''.join('\r\n .%s\r\n [\r\n  .MILITAR   0.7\r\n  .COMERCIAL 0.7\r\n  .RECURSOS  0.7\r\n  .POLITICA  0.7\r\n'
                  '  .TROPAS    0.7\r\n  .BARCOS    0.7\r\n ]\r\n' % p for p in playable_new if ('.' + p) not in txt)
    m0 = re.search(r'^\.COSTES', txt, re.M); a, e = find_block(txt, m0.start())
    out(rel, (txt[:e - 1] + add + txt[e - 1:]).encode('latin1'))

    # AI graphs (GraphJUG_*.GRF, version 2.3): every province is a node, edges land-land, sea-sea and
    # land-sea through ports. The shipped files know only the 82 original provinces, so build them for every player.
    import ports as PT
    mm = Mng(open(os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read())
    provs = {r['idx']: r for r in Mng.parse_provinces(mm.section(4))}
    prts = {r['idx']: r for r in PT.parse_ports(mm.section(6))}
    pos, caps = PT.read_grf_nodes(read(os.path.join(DATA, G, 'IA/Datos_Precalculados/GraphJUG_FRANCIA.GRF')))
    types = Mng.parse_enum(mm.table(7))
    b13 = mm.section(13).body
    for k in range(mm.section(13).cnt):
        typ, prov = struct.unpack_from('<II', b13, 24 * k)
        if types.get(typ, '').startswith('CAPITAL_BASE'):
            caps.add(prov)
    # capitals = this mod's capital buildings only (France's 1805 graph also flags Moldavia, Hanover and Saxony)
    caps = {p for p in caps if any(types.get(struct.unpack_from('<II', b13, 24 * k)[0], '').startswith('CAPITAL_BASE')
                                   and struct.unpack_from('<II', b13, 24 * k)[1] == p for k in range(mm.section(13).cnt))}
    print('  AI graph capitals:', len(caps))
    for i in provs:
        if i not in pos:
            pos[i] = PROV_POS[i]
    grf = PT.build_grf(provs, prts, caps, pos)
    gdir = os.path.join(DATA, G, 'IA/Datos_Precalculados')
    players = sorted({f[5:-4] for f in os.listdir(gdir) if f.startswith('Graph') and f.endswith('.GRF')}
                     | {'JUG_' + nn['key'] for nn in NT.NEW_NATIONS})
    for pk in players:
        out(G + 'IA/Datos_Precalculados/Graph%s.GRF' % pk, grf)
    print('  AI graphs:', len(players), 'players,', len(provs), 'nodes')

    # battle units, ships, unit/ship textures
    rel = 'Game/GameModes/Batalla/DefTropas.sb'
    out(rel, NT.def_tropas(mod_or_src(rel).decode('latin1')).encode('latin1'))
    rel = 'Game/GameModes/NavalBattleMode/DefBarcos.sb'
    out(rel, NT.def_barcos(mod_or_src(rel).decode('latin1')).encode('latin1'))
    for nn in NT.NEW_NATIONS:
        base = os.path.join(DATA, 'Models', nn['models'])
        for dp, dns, fns in os.walk(base):
            for fn in fns:
                if fn.lower() == 'vssver.scc':
                    continue
                relp = os.path.relpath(os.path.join(dp, fn), base).replace(os.sep, '/')
                out('Models/%s/%s' % (nn['folder'], relp), open(os.path.join(dp, fn), 'rb').read())

    # flags: 3D map flags, figure flags, battle standards, UI atlas
    flag_files = {c: c.title() for c in NT.FLAG_KEYS}
    folders = {nn['key']: (nn['folder'], nn['folder']) for nn in NT.NEW_NATIONS}
    folders.update({'MOLDAVIA': ('21Moldavia', '21Moldavia'), 'SAJONIA': ('19Sajonia', '19Sajonia'), 'HANNOVER': ('17Hanover', '17Hannover')})
    atlas_path = os.path.join(MOD, NT.ATLAS)
    where, big = NT.build_atlas(atlas_path)
    print('  wrote', NT.ATLAS)
    for c in NT.FLAG_KEYS:
        v = big[c]
        p = os.path.join(MOD, 'Models', 'BANDERAS', flag_files[c] + '.tga'); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, 128, 64, v['map'], alpha=False)
        fig_folder, model_folder = folders[c]
        p = os.path.join(MOD, G + 'Figuras', fig_folder, 'Bandera.tga'); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, 256, 256, v['figure'], alpha=False)
        p = os.path.join(MOD, 'Models', model_folder, 'Bandera.dds'); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_dds_dxt1_mips(p, 128, 64, v['standard'])     # 8 mip levels like the originals (5608 bytes)
    print('  wrote flags for', sorted(NT.FLAG_KEYS))

    # welcome-message pictures: the game builds ICON_NOTIFICACION_<player> and crashes if it is missing
    rel = 'Game/UI/ModeloGestion/Iconos/UIDefs_PoolIconosNotificaciones.sb'
    txt = mod_or_src(rel).decode('latin1')
    for c, design in NT.FLAG_KEYS.items():
        pk = NT.PLAYER_OF[c]
        f = 'Game/UI/ModeloGestion/Iconos/Notificaciones/NotificacionInicio%s.tga' % c.title()
        p = os.path.join(MOD, f); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, 256, 256, FL.notification(design))
        lines = ['', '[', '  .KEY ICON_NOTIFICACION_%s' % pk, '  .PARAMS', '  [', '    .FILE "%s"' % f,
                 '    .U 1 .V 1 .SX 147 .SY 160', '    .ALPHA TRUE', '  ]', ']', '']
        e = "".join(x + chr(13) + chr(10) for x in lines)
        txt = NT.set_sprite(txt, 'ICON_NOTIFICACION_' + pk, e)
    out(rel, txt.encode('latin1'))

    ui = {}
    for rel in ('Game/UI/ModeloGestion/UIDefs_Banderas.sb', 'Game/UI/ModeloBatalla/UIDefs_Banderas.sb', 'Game/UI/ModeloNaval/UIDefs_Banderas.sb',
                'Game/UI/ModeloGestion/Iconos/UIDefs_FlagIcons.sb', 'Game/UI/MainMenu/SelectEmpire/UIDefs_Banderas.sb'):
        ui[rel] = mod_or_src(rel).decode('latin1')
    NT.ui_flags(ui, where, None)
    # the original minor nations: Select Empire strips and welcome pictures made from their own flag pictures
    atlas2 = 'Game/UI/Mod/BanderasMod2.tga'
    sheet = FL.blank(1024, 1024)
    x = y = rowh = 0
    pool_rel = 'Game/UI/ModeloGestion/Iconos/UIDefs_PoolIconosNotificaciones.sb'
    pool = mod_or_src(pool_rel).decode('latin1')
    sel_rel = 'Game/UI/MainMenu/SelectEmpire/UIDefs_Banderas.sb'
    atlas_s = 'Game/UI/Mod/BanderasStrips.tga'
    strips, strips_at = FL.blank(1024, 1024), {}
    for pk, (flagfile, _text) in NT.MINORS_PLAYABLE.items():
        w0, h0, img = tga.read_tga(os.path.join(DATA, 'Models', 'BANDERAS', flagfile + '.tga'))
        v = FL.derive_image(img)
        spot = {}
        for name in ('e57', 'b297_fondo', 'b297_sel'):
            im = v[name]; iw, ih = len(im[0]) // 4, len(im)
            if x + iw > 1024:
                x = 0; y += rowh + 2; rowh = 0
            FL.paste(sheet, im, x, y); spot[name] = (atlas2, x, y, iw, ih)
            x += iw + 2; rowh = max(rowh, ih)
        k = len(strips_at)                                   # disabled strips: own atlas, 3 x 17 slots
        FL.paste(strips, v['b297_disable'], (k % 3) * 299, (k // 3) * 59)
        spot['b297_disable'] = strips_at[pk] = (atlas_s, (k % 3) * 299, (k // 3) * 59, 297, 57)
        for suf, var, pr in NT.SE_VARIANTS:
            key = '%s_BANDERA_%s' % (pk, suf)
            ui[sel_rel] = NT.set_sprite(ui[sel_rel], key, NT._entry(key, *spot[var], pr))
        f = 'Game/UI/ModeloGestion/Iconos/Notificaciones/NotificacionInicio%s.tga' % flagfile.replace('_', '')
        p = os.path.join(MOD, f); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, 256, 256, v['notification'])
        lines = ['', '[', '  .KEY ICON_NOTIFICACION_%s' % pk, '  .PARAMS', '  [', '    .FILE "%s"' % f,
                 '    .U 1 .V 1 .SX 147 .SY 160', '    .ALPHA TRUE', '  ]', ']', '']
        pool = NT.set_sprite(pool, 'ICON_NOTIFICACION_' + pk, ''.join(s + chr(13) + chr(10) for s in lines))
    assert y + rowh <= 1024, 'atlas 2 full'
    p = os.path.join(MOD, atlas2); os.makedirs(os.path.dirname(p), exist_ok=True)
    tga.write_tga(p, 1024, 1024, sheet)
    assert len(strips_at) <= 51
    tga.write_tga(os.path.join(MOD, atlas_s), 1024, 1024, strips)
    out(pool_rel, pool.encode('latin1'))
    print('  wrote', atlas2, 'and welcome pictures for', len(NT.MINORS_PLAYABLE), 'minor nations')
    rel = 'Game/UI/ModeloGestion/Diplomacia/UIDefs_Banderas.sb'
    ui[rel] = NT.diplomacy_flags(mod_or_src(rel).decode('latin1'), where)
    rel = 'Game/UI/ModeloGestion/UIDefs_CheckBoxesDestinatarioDiplomacia.sb'
    ui[rel] = NT.recipient_checkboxes(mod_or_src(rel).decode('latin1'))
    for f in ('UI_DefsSeleccionBandoHistoricaTerrestre.sb', 'UI_DefsSeleccionBandoHistoricaNaval.sb', 'UI_DefsSeleccionBandoHistoricaTerrestreM.sb'):
        rel = 'Game/UI/MainMenu/' + f
        ui[rel] = NT.historical_flags(mod_or_src(rel).decode('latin1'), where)
    rel = 'Game/UI/Comun/UIDefs_IdentificadoresColorPaises.sb'
    ui[rel] = NT.colour_ids(mod_or_src(rel).decode('latin1'))
    rel = 'Game/UI/MainMenu/UIDefs_SelectEmpire.sb'
    txt = mod_or_src(rel).decode('latin1')
    # original layout (rows 60 px apart, stars shown); the patched exe shows 6 rows at a time and scrolls
    # with two round arrow buttons beside the list (also on the up/down arrow keys)
    arrows = ''.join(
        '\t[ .TIPO UIC_BOTONTEXTO .ID \'%s\'\r\n'
        '\t  .PARAMS\r\n'
        '\t  [\r\n'
        '\t    .FONDO\r\n'
        '\t    [\r\n'
        '\t      .X 318 .Y %d .SX 32 .SY 33 .ALPHA TRUE .PRIORITY 40\r\n'
        '\t      .SOLTADO      [ .FILE "Game/UI/Comun/ControlesStandard.tga" .U 4  .V %d ]\r\n'
        '\t      .SELECCIONADO [ .FILE "Game/UI/Comun/ControlesStandard.tga" .U 41 .V %d ]\r\n'
        '\t      .PULSADO      [ .FILE "Game/UI/Comun/ControlesStandard.tga" .U 78 .V %d ]\r\n'
        '\t    ]\r\n'
        '\t    .IDSELECTSOUND "S_FXUI_CLICKBUTTON"\r\n'
        '\t    .IDHIGHLIGHTSOUND "S_FXSELECCION_RESALTE_ELEMENTO"\r\n'
        '\t    .KEY [ .TECLA %s .EVENTOS [ KEY_DOWN KEY_UP ] ]\r\n'
        '\t  ]\r\n'
        '\t]\r\n' % (bid, y, v, v, v, key)
        for bid, y, v, key in (('BTUP', 133, 124, 'LKEY_MAINMENU_OPTION_UP'),
                               ('BTDN', 400, 162, 'LKEY_MAINMENU_OPTION_DOWN')))
    i = txt.rindex(']')            # closing bracket of .CONTROLES
    txt = txt[:i] + '\t#---- scroll buttons (mod)\r\n' + arrows + txt[i:]
    ui[rel] = txt
    for rel, txt in ui.items():
        out(rel, txt.encode('latin1'))

    # localisation for the new nations and the playable descriptions
    add = NT.texts_new(None)
    for lang in LANGS:
        for frel, entries in add.items():
            done = os.path.join(MOD, 'Texto', lang, frel)
            p = done if os.path.exists(done) else src_text(lang, frel)
            raw = open(p, 'rb').read() if p == done else read(p)
            out('Texto/%s/%s' % (lang, frel), text_add_entries(raw, entries))

    # patched exe copy (the original is only read)
    # the build patches our master copy of the original exe (MD5 e8db9ab5..., the user's install before any Steam
    # "verify integrity", which would replace the Steam copy with the stock exe whose fullscreen table differs)
    exe_src = os.path.join(ROOT, 're_tools', 'target', 'ImperialGlory.exe')
    if not os.path.exists(exe_src):
        exe_src = os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Steam', 'steamapps',
                               'common', 'Imperial Glory', 'ImperialGlory.exe')
    exe_dst = os.path.join(OUT_DIR, 'ImperialGlory_ModNations.exe')
    mm = Mng(open(os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read())
    pid_of = {p['ltext'][len('LTEXT_JUGADOR_'):]: p['idx'] for p in parse_players(mm.section(2))}
    NT.AI_SKIP_IDS[:] = [pid_of[k] for k in NT.AI_SKIP]
    print('  AI planning skipped for', len(NT.AI_SKIP_IDS), 'small nations')
    NT.HISTORICAL_EVENTS = HISTORICAL_EVENTS          # exe patches 48-50 only together with the event Lua and texts
    changes = NT.patch_exe(exe_src, exe_dst, os.path.join(MOD, 'Game', 'GameModes', 'DefModeloGestion.mng'))   # patch 29 table
    with open(os.path.join(OUT_DIR, 'ImperialGlory_ModNations_patch.txt'), 'w') as f:
        f.write('Patched copy of ImperialGlory.exe (Steam). Original untouched.\n')
        for off, old, new in changes:
            f.write('file offset 0x%06x: %d bytes\n  old %s\n  new %s\n' % (off, len(new), old.hex(), new.hex()))
    print('  wrote', exe_dst, len(changes), 'patches')


LOCK = os.path.join(BUILD, '.build.lock')
LOCK_MAX_AGE = 2 * 3600       # an older lock is left over from a killed build and is taken over
# generated art that the build only copies (B2): output folder -> the generators it depends on (both import nations.py)
ART_OUTPUTS = {
    os.path.join(BUILD, 'units', 'out'): ['tools/nations.py', 'tools/art/units/cultures.py'],
    os.path.join(BUILD, 'icons', 'out'): ['tools/nations.py', 'tools/art/units/cultures.py', 'tools/art/icons/make_icons.py'],
}


def check_art_outputs():
    """Fail when a unit/icon generator is newer than the newest file of its output folder (the build copies these
    folders as they are; it does not run the slow, art-sensitive generators). --allow-stale-art only warns."""
    stale = []
    for outdir, gens in ART_OUTPUTS.items():
        if PUBLIC and outdir == os.path.join(BUILD, 'icons', 'out'):
            continue                                    # --public regenerates the icons itself (public_icons)
        newest = max((os.path.getmtime(os.path.join(dp, f)) for dp, dns, fns in os.walk(outdir) for f in fns), default=0)
        for g in gens:
            if os.path.getmtime(os.path.join(ROOT, g)) > newest:
                stale.append('%s is newer than %s (newest file %s)' % (
                    g, os.path.relpath(outdir, ROOT), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(newest)) if newest else 'none'))
    if not stale:
        return
    msg = ('STALE ART OUTPUTS:\n  ' + '\n  '.join(stale) +
           '\nRegenerate them first:  python tools/art/units/cultures.py  then  python tools/art/icons/make_icons.py'
           '\n(or build with --allow-stale-art if the generator change cannot affect the art)')
    if '--allow-stale-art' in sys.argv[1:]:
        print('WARNING: ' + msg)
        return
    raise SystemExit(msg)


def public_skips(relp):
    """--public: True for a generated culture file (build/units/out, path relative to the game root) of a nation left out
    of the public build: its model / figure folders and a unit file no remaining nation uses (DefUnidadesCaucaso.sb)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools', 'art', 'units'))
    import cultures as CU
    folders = {nn['folder'] for nn in NT.PUBLIC_DROPPED}
    units = {CU.RECIPES[k]['units'] for k in NT.PUBLIC_DROP if k in CU.RECIPES} - set(CU.UNIT_FILE_OF.values())
    drop = (['Models/%s/' % f for f in folders] + ['Game/GameModes/Gestion/Figuras/%s/' % f for f in folders]
            + ['Game/GameModes/Batalla/' + u for u in units])
    return any(relp == d or (d.endswith('/') and relp.startswith(d)) for d in drop)


def public_icons():
    """--public: the troop icons, portraits and battle buttons regenerated without the left-out nations, by
    tools/art/icons/make_icons.py in this process (rosters from the public .mng). Painted overrides are switched off, so
    nothing of build/chatgpt_portraits can reach the public pak. Returns the output folder build/public/icons/out."""
    sys.path.insert(0, os.path.join(ROOT, 'tools', 'art', 'icons'))
    import make_icons as MI
    MI.MOD, MI.OUT, MI.OVERRIDES = MOD, os.path.join(OUT_DIR, 'icons', 'out'), None
    if os.path.exists(MI.OUT):
        shutil.rmtree(MI.OUT)
    items = MI.collect()
    assert items and not any(k in NT.PUBLIC_DROP for k, t, i in items), 'public icons: a left-out nation is listed'
    maker = MI.PaintedArt(MI.Art())
    assert not maker.p.overrides, 'public icons: painted overrides must be off'
    MI.build(maker, items)
    return MI.OUT


def main():
    """One build at a time (B3): build/.build.lock guards the rmtree(mod/) and the whole rebuild."""
    os.makedirs(BUILD, exist_ok=True)
    if os.path.exists(LOCK):
        age = time.time() - os.path.getmtime(LOCK)
        if age < LOCK_MAX_AGE:
            raise SystemExit('BUILD LOCKED: %s exists (%d min old: %s). Another build is running; wait for it, or '
                             'delete the lock if that build is dead.' % (LOCK, age // 60, open(LOCK).read().strip()))
        print('  taking over a stale build lock (%d min old)' % (age // 60))
        os.remove(LOCK)
    me = 'pid %d, started %s' % (os.getpid(), time.strftime('%Y-%m-%d %H:%M:%S'))
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)   # fails if another build created it meanwhile
    os.write(fd, me.encode())
    os.close(fd)
    try:
        check_art_outputs()
        build_mod()
    finally:
        try:
            if open(LOCK).read().strip() == me:          # never remove a lock that another build took over
                os.remove(LOCK)
        except OSError:
            pass


def build_mod():
    if os.path.exists(MOD):
        shutil.rmtree(MOD)
    os.makedirs(OUT_DIR, exist_ok=True)                 # = BUILD, or build/public with --public
    # old-area provinces (pids 1-11) redrawn to fit the painted map (tools/art/oldarea), else the first versions
    po = os.path.join(BUILD, 'oldarea', 'provinces.json')
    if os.path.exists(po):
        shapes = {int(k): [tuple(p) for p in v] for k, v in json.load(open(po)).items()}
    else:
        shapes = {int(k): [tuple(p) for p in v] for k, v in json.load(open(os.path.join(BUILD, 'forslag_former.json'))).items()}
        shapes[11] = [tuple(p) for p in json.load(open(os.path.join(BUILD, 'chechnya_poly.json')))]
    for pid, poly in shapes.items():
        assert MG.is_simple(poly), pid
    if WORLD_PROVINCES:
        add_world_provinces(shapes)
    if SEA_ZONES:
        add_sea_zones(shapes)

    # --- database
    rel = 'Game/GameModes/DefModeloGestion.mng'
    m = Mng(read(src(rel)))
    enum = Mng.parse_enum(m.table(2))
    recs = Mng.parse_provinces(m.section(4))
    by_mesh = {r['name']: r for r in recs}
    next_idx = max(enum) + 1
    idx_of = {}
    for pid in sorted(PROVINCES):
        key = PROVINCES[pid][0]
        assert key not in enum.values(), key
        idx_of[pid] = next_idx
        Mng.enum_add(m.table(2), next_idx, key)
        next_idx += 1
    land_shapes = {k: v for k, v in shapes.items() if k not in SEA_PIDS}
    nb = neighbours(land_shapes)
    for a_, lst in list(nb.items()):                    # make new-new links mutual (extensions change one side only)
        for n_ in lst:
            if isinstance(n_, tuple) and ('NEW', a_) not in nb.get(n_[1], []) and n_[1] in nb:
                nb[n_[1]].append(('NEW', a_))
    for pid in SEA_PIDS:
        nb[pid] = list(SEA_NB[pid])
    # islands of the bigger map have no land neighbour until the new sea zones exist: link each to the closest
    # province across the strait (both ways), if it is near enough.  The pairs are frozen (STRAIT_LINKS): the
    # 'closest' by every second outline vertex depends on the vertex density, and the coast fit (2026-10-22,
    # tools/art/islands/coastfit.py) made Java's nearest Bali (Lesser Sundas) instead of South Sumatra
    def gap(a, b):
        return min(math.hypot(p[0] - q[0], p[1] - q[1]) for p in shapes[a][::2] for q in shapes[b][::2])
    pid_of_mesh = {PROVINCES[p][1]: p for p in land_shapes}
    for pid in sorted(land_shapes):
        if pid >= 101 and not nb[pid]:
            frozen = STRAIT_LINKS.get(PROVINCES[pid][1])
            if frozen in pid_of_mesh:
                best = (gap(pid, pid_of_mesh[frozen]), pid_of_mesh[frozen])
            else:
                best = min((gap(pid, o), o) for o in land_shapes if o != pid)
            if best[0] < 2500.0:
                nb[pid].append(('NEW', best[1]))
                if not any(isinstance(n, tuple) and n[1] == pid for n in nb[best[1]]):
                    nb[best[1]].append(('NEW', pid))
                print('  strait link', PROVINCES[pid][2], '-', PROVINCES[best[1]][2], int(best[0]))
    for pid in sorted(PROVINCES):
        key, mesh, disp, owner, tmpl_name, scen, desc = PROVINCES[pid]
        tmpl = by_mesh[tmpl_name]
        sea = pid in SEA_PIDS
        nb[pid] = [n for n in nb[pid] if (n[1] in SEA_PIDS if isinstance(n, tuple) else bool(by_mesh[n]['sea'])) == sea]
        ids = []
        for n in nb[pid]:
            ids.append(idx_of[n[1]] if isinstance(n, tuple) else by_mesh[n]['idx'])
        # every province needs its own battle scenario name: the game finds provinces by it (a shared name gave
        # Kazakhstan Kursk's colour and put Turkestan's army there). The new name points to the same battle map.
        sid = str(idx_of[pid])
        if any(r['scenario'] == sid for r in recs):      # taken by an original (0..89): move to a free number
            sid = str(idx_of[pid] + 300)
        if sea:
            SEA_SCEN[sid] = tmpl['scenario']
            rec = dict(tmpl, idx=idx_of[pid], ltext='LTEXT_PROVINCIA_' + key, ldesc='LTEXT_DESC_' + key,
                       vals=list(tmpl['vals']), name=mesh, scenario=sid, sea=tmpl['sea'], f=tmpl['f'], nb=ids)
        else:
            SCEN_TEMPLATE[sid] = scen or tmpl['scenario']
            SCEN_PROV[sid] = key                         # (battlemaps.bind: provinces on a shared new battlefield)
            rec = dict(tmpl, idx=idx_of[pid], ltext='LTEXT_PROVINCIA_' + key, ldesc='LTEXT_DESC_' + key,
                       vals=tmpl['vals'][:4] + [0, tmpl['vals'][5]] + [0] * 8, name=mesh, scenario=sid,
                       sea=0, f=1.5, nb=ids)
        for n in nb[pid]:
            if not isinstance(n, tuple) and idx_of[pid] not in by_mesh[n]['nb']:
                by_mesh[n]['nb'].append(idx_of[pid])
        assert all(r['scenario'] != sid for r in recs), (mesh, sid)
        recs.append(rec)
        print('  %-18s idx %d owner %-9s neighbours %s' % (disp, idx_of[pid], owner,
              [n if not isinstance(n, tuple) else PROVINCES[n[1]][2] for n in nb[pid]]))
    Mng.set_provinces(m.section(4), recs)
    cs = Mng.parse_countries(m.section(3))
    for pid, p in PROVINCES.items():
        next(c for c in cs if c['ltext'] == 'LTEXT_PAIS_' + p[3])['provs'].append(idx_of[pid])
    Mng.set_countries(m.section(3), cs)
    bld = {v: k for k, v in Mng.parse_enum(m.table(7)).items()}
    for pid, poly in shapes.items():
        if pid in SEA_PIDS:
            continue
        c = MG.centre_point(poly)
        second = MG.second_point(poly, c)
        Mng.add_position(m.section(13), bld['DUMMY_BARRARECURSOS'], idx_of[pid], c[0], LIFT - 0.0147, c[1])
        Mng.add_position(m.section(13), bld['DUMMY_BANDERAOCUPACION'], idx_of[pid], second[0], LIFT - 0.0147, second[1])
    texts = apply_reskins(m, idx_of, shapes)
    NT.add_nations(m, idx_of, shapes, LIFT)
    # neighbour lists: new nations get computed lists, everyone else gains the new nations they border
    recs = Mng.parse_provinces(m.section(4)); provs = {r['idx']: r for r in recs}
    cs = Mng.parse_countries(m.section(3))
    land = {r['idx'] for r in recs if not r['sea']}
    owner = {p: c['idx'] for c in cs for p in c['provs'] if c['ltext'] != 'LTEXT_PAIS_PLIBREDUMMY'}
    r1, r2 = country_lists(provs, owner, land)
    new_cids = {c['idx'] for c in cs if c['ltext'][11:] in [nn['key'] for nn in NT.NEW_NATIONS]}
    for c in cs:
        i = c['idx']
        if i in new_cids:
            c['lists'] = [r1.get(i, []), r2.get(i, [])]
        elif i in r1:
            c['lists'][0] += [x for x in r1[i] if x in new_cids and x not in c['lists'][0]]
            c['lists'][1] += [x for x in r2[i] if x in new_cids and x not in c['lists'][1] and x not in c['lists'][0]]
    Mng.set_countries(m.section(3), cs)
    if NEW_PORTS:
        add_ports(m, idx_of, shapes, bld)
        island_neighbours(m)
    import start1789                                   # 1789 economy and starting armies (build/start1789)
    start1789.apply(m, WORLD_PID, idx_of, reassign=PUBLIC_ARMY_TO if PUBLIC else None)
    frel = 'Game/GameModes/Gestion/dbgDefFlotasIniciales.sb'
    out(frel, start1789.fleets(read(src(frel)).decode('latin1'), set(Mng.parse_enum(m.table(0)).values())).encode('latin1'))
    provincial_military(m, shapes, idx_of)             # exe patch 40: basic military buildings outside capitals
    for pid, poly in shapes.items():
        PROV_POS[idx_of[pid]] = MG.centre_point(poly)
    out(rel, m.pack())

    # --- click masks
    rel = 'Game/GameModes/Gestion/Mapa/PosicionesMapa.gp'
    g = Gp(read(src(rel)))
    for pid in sorted(PROVINCES):
        poly = shapes[pid]
        xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
        x0, z0, w, h = min(xs), min(zs), max(xs) - min(xs), max(zs) - min(zs)
        g.add(PROVINCES[pid][1], x0, z0, w, h, shape=lambda u, v, poly=poly, x0=x0, z0=z0, w=w, h=h:
              MG.point_in(poly, x0 + u * w, z0 + v * h))   # gp rows start at the south edge (z0)
    # originals that new provinces were carved from (Kursk->Chechenya, Moscu->Ural, Marruecos->SaharaOccidental ...)
    # keep their old figure masks, so their armies were drawn on the new province; the engine places a figure at the
    # cell corner x0+col*w/cols, z0+row*h/rows (FUN_006594c0): clear original cells whose corner lies in new land
    mine = {PROVINCES[p_][1] for p_ in PROVINCES}
    new_land = [shapes[p_] for p_ in PROVINCES if p_ not in SEA_PIDS]
    nbox = [(min(q[0] for q in c), max(q[0] for q in c), min(q[1] for q in c), max(q[1] for q in c)) for c in new_land]
    for r in g.recs:
        if r['name'] in mine:
            continue
        cw, ch = r['w'] / r['c1'], r['h'] / r['c2']
        mk = bytearray(r['mask']); n0 = sum(mk)
        for k in range(len(mk)):
            if mk[k]:
                x, z = r['x'] + (k % r['c1']) * cw, r['y'] + (k // r['c1']) * ch
                if any(b[0] <= x <= b[1] and b[2] <= z <= b[3] and MG.point_in(c, x, z) for c, b in zip(new_land, nbox)):
                    mk[k] = 0
        if sum(mk) != n0:
            assert sum(mk) > 0, r['name']
            print('  gp: %s loses %d of %d figure cells to new provinces' % (r['name'], n0 - sum(mk), n0))
            r['mask'] = bytes(mk)
    out(rel, g.pack())

    # --- province meshes in both models, fog points in the terrain model
    fog_index = 1000
    fog_box = fog_plane_box()                            # fog points only where the fog plane is (review V7)
    # the land the sea zones are cut by below (land_all): no sea fog point there (it would only be pruned)
    fog_land = [shapes[p_] for p_ in shapes if p_ not in SEA_PIDS] + [[tuple(q) for q in pl] for pls in EXTENSIONS.values() for pl in pls]
    fog_new = {PROVINCES[p_][1] for p_ in PROVINCES}    # meshes made here: their extension specks may share points
    for rel in ('Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D', 'Game/GameModes/Gestion/Mapa/MapaGestion.V3D'):
        data = read(src(rel))
        if PLATE_WORLD:
            for r in range(-NEW_ROWS_SOUTH, 4):
                for c in range(NEW_COLS):
                    MG.TILE_MAT.setdefault((r, c), 0)      # placeholder: retile.rebuild_model sets the real tiles
        v = V3D(data)
        y = struct.unpack_from('<f', v.d, v.block('Cirenaica')[0] + 40 + 2 + len('Cirenaica') + 1 + 2 + 12 + 64 + 52)[0] + 0.035   # just above the original provinces (some overlap them, e.g. Kazakhstan over Kursk), background at 0.80
        for pid in sorted(PROVINCES):
            ym = y - 0.035 if pid in SEA_PIDS else y          # sea zones under the land: coasts overlap a little
            nv, nt = MG.add_mesh(v, PROVINCES[pid][4] if pid in SEA_PIDS else 'Cirenaica', PROVINCES[pid][1], shapes[pid], ym)
            msg = '  %s %-16s %3d verts %3d tris' % (rel.split('/')[-1][:14], PROVINCES[pid][1], nv, nt)
            if rel.endswith('/MapaGestion.V3D'):
                sea_ = pid in SEA_PIDS
                n = MG.add_fog_points(v, 'Cirenaica', PROVINCES[pid][1], shapes[pid], y, fog_index, box=fog_box,
                                      spacing=FOG_SEA_SPACING if sea_ else FOG_LAND_SPACING, exclude=fog_land if sea_ else None)
                fog_index += n
                msg += ', %d fog points' % n
            print(msg)
        if rel.endswith('/MapaGestion.V3D'):
            for name, polys in EXTENSIONS.items():          # fog points for the extension pieces
                for poly in polys:
                    if on_map_tiles(poly):                  # the same pieces the mesh step below keeps
                        fog_index += MG.add_fog_points(v, 'Cirenaica', name, [tuple(q) for q in poly], y, fog_index,
                                                       spacing=FOG_LAND_SPACING, box=fog_box, piece=True,
                                                       skip_covered=name in fog_new)
        G_canon = __import__('igmod').v3d_canonical(v)   # sorted meshes, correct child counts and ids
        packed = v.pack()
        pre_cut, cut_names = packed, []                  # meshes cut below lose the fog points on the cut land
        # provinces added in the old area overlap original meshes (Kazakhstan over Kursk/Moscu, Siberia/Ural over
        # Moscu, Turkestan over Kursk, Sahara Occidental over Marruecos): cut the overlap out of the originals,
        # z offsets alone flicker when zoomed out
        cut_polys = [shapes[p_] for p_ in PROVINCES if p_ < 101 and p_ in shapes]
        cut_polys += [[tuple(q) for q in pl] for n_, pls in EXTENSIONS.items() if n_ in {PROVINCES[p_][1] for p_ in PROVINCES if p_ < 101} for pl in pls]
        land_world = [shapes[p_] for p_ in shapes if 101 <= p_ and p_ not in SEA_PIDS]
        cut_polys += land_world                          # originals reaching past the old edge (Moscu, Kursk)
        cbox = [(min(q[0] for q in c), max(q[0] for q in c), min(q[1] for q in c), max(q[1] for q in c)) for c in cut_polys]
        orig_names = [n_ for (o_, c_, s_, n_, p_) in v3d_objects(read(src(rel))) if c_ == 0x2000]
        mine = {PROVINCES[p_][1] for p_ in PROVINCES}
        for name in orig_names:
            if name in mine:
                continue
            o_ = next(t_ for t_ in v3d_objects(packed) if t_[3] == name and t_[1] == 0x2000)
            mb = MG.mesh_world_box(packed[o_[0]:o_[0] + o_[2]])
            hit = [c for c, b in zip(cut_polys, cbox) if b[0] < mb[1] and b[1] > mb[0] and b[2] < mb[3] and b[3] > mb[2]]
            if not hit:
                continue
            new_b, dv_, dt_, removed = MG.subtract_mesh_bytes(packed, name, hit)
            if removed > 5000.0:                            # real overlaps, not hairline border slivers
                packed = new_b; cut_names.append(name)
                print('  cut %.0f units2 of overlap out of %s (%s)' % (removed, name, rel.split('/')[-1]))
        for name, polys in EXTENSIONS.items():              # old edge provinces grow to natural borders
            ok_polys = []
            for poly in polys:                              # pieces beyond the map tiles (remote specks) are skipped
                if on_map_tiles(poly):
                    ok_polys.append(poly)
                else:
                    print('  extension piece of %s outside the map tiles, skipped' % name)
            if ok_polys:
                packed, dv_, dt_ = MG.extend_mesh_bytes(packed, name, ok_polys)
        if EXTENSIONS:
            print('  extended %d old provinces in %s' % (len(EXTENSIONS), rel.split('/')[-1]))
        # new sea zones must not run under any land (coastal slivers, the Canary edge corridor): cut the land out
        land_all = [shapes[p_] for p_ in shapes if p_ not in SEA_PIDS] +             [[tuple(q) for q in pl] for pls in EXTENSIONS.values() for pl in pls]
        lbox = [(min(q[0] for q in c), max(q[0] for q in c), min(q[1] for q in c), max(q[1] for q in c)) for c in land_all]
        ncut = 0
        for pid_ in sorted(SEA_PIDS):
            name = PROVINCES[pid_][1]
            o_ = next(t_ for t_ in v3d_objects(packed) if t_[3] == name and t_[1] == 0x2000)
            mb = MG.mesh_world_box(packed[o_[0]:o_[0] + o_[2]])
            hit = [c for c, b in zip(land_all, lbox) if b[0] < mb[1] and b[1] > mb[0] and b[2] < mb[3] and b[3] > mb[2]]
            if hit:                                       # (one constrained triangulation: no sliver explosion)
                new_b, dv_, dt_, removed = MG.subtract_mesh_bytes_cdt(packed, name, hit)
                if removed > 50.0:
                    packed = new_b; ncut += 1; cut_names.append(name)
        print('  sea zones cleared of land overlap: %d (%s)' % (ncut, rel.split('/')[-1]))
        if rel.endswith('/MapaGestion.V3D'):              # review V4: no fog point left on land cut from its mesh
            packed, nd_, nm_ = MG.prune_fog_points(pre_cut, packed, cut_names)
            print('  fog points on cut-away land dropped: %d (%d moved to keep one per mesh)' % (nd_, nm_))
            # enclosed areas without any mesh (Caspian, the Bass Strait gap) never cleared: points for the nearest mesh
            hp_ = MG.fog_hole_points(packed, fog_box, FOG_SEA_SPACING)
            if hp_:
                vh_ = V3D(packed)
                for name, pts_ in hp_:
                    fog_index += MG.add_fog_points(vh_, 'Cirenaica', name, None, y, fog_index, points=pts_)
                __import__('igmod').v3d_canonical(vh_)
                packed = vh_.pack()
            print('  fog points for mesh-less lakes / gaps: %d (%s)' % (sum(len(p_) for n_, p_ in hp_), ', '.join('%s %d' % (n_, len(p_)) for n_, p_ in hp_)))
        if PLATE_WORLD:
            import retile as RT
            packed, nre = RT.rebuild_model(packed)
            print('  retiled %d meshes in %s' % (nre, rel.split('/')[-1]))
        if SWAP_TEST:     # engine test: an old province in the new area, a new one in the old area
            import plate as PL2
            packed = PL2.transform_mesh(packed, 'Venecia', dx=25000.0)
            packed = PL2.transform_mesh(packed, 'WNewSouthWales', dx=-30000.0, dz=15000.0)
        out(rel, packed)
    if PLATE_WORLD:
        plate_world()
    elif PLATE_TEST:
        plate_test()
    # campaign camera: exactly the original (it handled well), only ZOOM_MIN lower so one can zoom further out on the
    # bigger map. With the original 10 deg pitch per level, -4 looks down at ~77 deg (at -5 it would pass 90).
    # The auto-focus level (exe patch 10) is matched to this range in nations.patch_exe.
    rel = 'Game/GameModes/Gestion/Camara.sb'
    cam = read(src(rel)).decode('latin1')
    cam, n = re.subn(r'(\.ZOOM_MIN\s+)[-\d.]+', lambda m: m.group(1) + '%.1f' % NT.CAMERA_ZOOM_MIN, cam, count=1)
    assert n == 1
    out(rel, cam.encode('latin1'))
    # province info dialog: hidden dummy bar / image button / text for nations other than the 5 empires (exe patch 11
    # points them here; without it the dialog crashed at 0x552074 once e.g. Chechenya held a share of a province)
    TGA_IT = 'Game/UI/ModeloGestion/UIDefsDlgInfoGestion/InformacionTerritorios.tga'
    dummies = {
        'Game/UI/ModeloGestion/UIDefsDlgInfoGestion/UIDefs_BarrasPorcentajeDlgInfoEdificio.sb':
            '\r\n[\r\n  .TIPO UIC_BARRAPORCENTAJE .ID \'BPXX\'\r\n  .PARAMS\r\n  [\r\n    .X 3000 .Y 3000\r\n    .PRIORITY 205\r\n'
            '    .SUPERIOR [ .FILE "%s" .U 131 .V 610 .ALPHA TRUE ]\r\n    .SX 1 .SY 1\r\n  ]\r\n]\r\n'
            '\r\n[\r\n .TIPO UIC_WRAPTEXT .ID \'WTXX\'\r\n .PARAMS\r\n [\r\n  .X 3000 .Y 3000 .SX 1 .SY 1\r\n  .ALIGN CENTER\r\n'
            '  .PRIORITY 203\r\n  .TEXT\r\n  [\r\n   .FONT "Fonts/Times9.fnt"\r\n   .COLOR [ .R 255 .G 255 .B 255 ]\r\n'
            '   .MSG  " "\r\n  ]\r\n ]\r\n]\r\n' % TGA_IT,
        'Game/UI/ModeloGestion/UIDefsDlgInfoGestion/UIDefs_ImagenesImperiosDlgInfoEdificio.sb':
            '\r\n[\r\n  .TIPO UIC_BOTONTEXTO .ID \'BTXX\'\r\n  .PARAMS\r\n  [\r\n    .COMPORTAMIENTO MANUAL\r\n    .FONDO\r\n    [\r\n'
            '      .X 3000 .Y 3000\r\n      .SX 1 .SY 1\r\n      .ALPHA TRUE\r\n      .SOLTADO [ .FILE "%s" .U 58 .V 611 ]\r\n'
            '      .PULSADO [ .FILE "%s" .U 15 .V 611 ]\r\n      .PRIORITY 204\r\n    ]\r\n  ]\r\n]\r\n' % (TGA_IT, TGA_IT)}
    for rel, add in dummies.items():
        txt = mod_or_src(rel).decode('latin1')
        assert "'%s'" % add.split("'")[1] not in txt
        out(rel, (txt.rstrip('\r\n') + '\r\n' + add).encode('latin1'))
    # faster AI turns, data side (re_tools: AI speed research 2026-10-17)
    # 1) optional: the AI does not plan the 16 quests (Rosetta Stone, Bolivar, ...). OFF since 2026-10-20: the user
    #    wants the original systems kept, and the real AI time sink (route table) is fixed by exe patches 12-14
    if AI_SKIP_QUESTS:
      rel = 'Game/LuaScripts/IA_Gestion/Iniciativas/Iniciativas.lua'
      lua = read(src(rel)).decode('latin1')
      quests = sorted(set(re.findall(r'TINI_QUEST_\w+', lua)))
      assert len(quests) == 16, quests
      skip = 'iniciativas_mod_desactivadas = {' + ', '.join('[%s] = true' % q for q in quests) + '}\r\n\r\n'
      i = lua.index('function update_iniciativas(')
      lua = lua[:i] + skip + lua[i:]
      for a, b in (('if (iniciativas[iniciativa_enum].enabled or force_regenerar) then',
                    'if (not iniciativas_mod_desactivadas[iniciativa_enum]) and (iniciativas[iniciativa_enum].enabled or force_regenerar) then'),
                   ('if iniciativas[iniciativa_enum].enabled then',
                    'if (not iniciativas_mod_desactivadas[iniciativa_enum]) and iniciativas[iniciativa_enum].enabled then')):
          assert lua.count(a) == 1, a
          lua = lua.replace(a, b)
      out(rel, lua.encode('latin1'))
    # 2) military planning looks 3 turns ahead instead of 5 (the map is far bigger than 1805 Europe); fewer scout fleets.
    #    OFF since 2026-10-21: it weakens the AI and the user said the AI must not be weakened; the route-table exe
    #    patches 12-14 fixed the real cost.
    for folder in (('Default', 'Lombardia', 'Otomano', 'Polonia') if AI_PLANNING_TWEAK else ()):
        rel = 'Game/GameModes/Gestion/IA/%s/IADefsMinistroMilitar.sb' % folder
        mil = read(src(rel)).decode('latin1')
        blk = re.search(r'\.DISTANCIA_EXPANSION\s*\[[^\]]*\]', mil)
        new = re.sub(r'(\.(?:AMISTAD|NEUTRALIDAD)\s+)5\b', r'\g<1>2', blk.group(0))
        new = re.sub(r'(\.(?:ENEMISTAD|GUERRA|PROPIO)\s+)5\b', r'\g<1>3', new)
        mil = mil[:blk.start()] + new + mil[blk.end():]
        mil = re.sub(r'(\.NUM_MAX_SCOUTS\s+)\d+', r'\g<1>1', mil, count=1)
        mil = re.sub(r'(\.PORCENTAJE_SCOUTS\s+)[\d.]+', r'\g<1>0.2', mil, count=1)
        out(rel, mil.encode('latin1'))
    # turn visor: 3 rows of 22 flags instead of one row of 24 (exe patch 7 caps the centring), same bottom edge
    rel = 'Game/UI/ModeloGestion/UIDefs_VisorTurnos.sb'
    vt = mod_or_src(rel).decode('latin1')
    for key, val in (('FILAS', '3'), ('COLUMNAS', '22'), ('Y', '469')):
        vt, n = re.subn(r'(^\s*\.%s\s+)\d+' % key, lambda m: m.group(1) + val, vt, count=1, flags=re.M)
        assert n == 1, key
    out(rel, vt.encode('latin1'))
    rel = 'Game/UI/ModeloGestion/UI_ModeloGestion.sb'
    ui = mod_or_src(rel).decode('latin1')
    i = ui.index("'WTVT'")
    ui, n = ui[:i] + re.sub(r'\.Y 515', '.Y 439', ui[i:], count=1), 1
    out(rel, ui.encode('latin1'))

    # --- localisation
    # the game builds the objective key from the province's MESH name, upper-cased (FUN_005a83c0: prefix + def+0x58,
    # toupper; originals: KURSK, REINAHELVETICA, ISLADEFRANCIA), not from the province key: LTEXT_OBJETIVOS_*_CHECHENYA
    OBJ_KEY = {e[0]: e[1].upper() for e in PROVINCES.values()}
    files = {
        'Management/TextProvincias.sb': lambda k, d, s: [('LTEXT_PROVINCIA_' + k, d)],
        'Management/TextDescripcionesProvincias.sb': lambda k, d, s: [('LTEXT_DESC_' + k, s)],
        'Others/TextUIObjetivos.sb': lambda k, d, s: [('LTEXT_OBJETIVOS_ATACANTE_' + OBJ_KEY[k], 'Total Victory'),
                                                       ('LTEXT_OBJETIVOS_DEFENSOR_' + OBJ_KEY[k], 'Total Victory')],
        'Battle/TextUIBatallaVentanaInicioBatalla.sb': lambda k, d, s: [('LTEXT_UI_BATALLA_INITVENT_%s_TITLE' % k, d.upper()),
                                                                         ('LTEXT_UI_BATALLA_INITVENT_%s_TEXT' % k, 'What are your orders?')],
    }
    # objectives and the battle intro text belong to the battle map: take them (in each language) from the original
    # province whose map the new province borrows (else a map with villages to hold would say only 'Total Victory')
    orig = Mng.parse_provinces(Mng(open(os.path.join(DATA, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read()).section(4))
    key_of_scen = {r['scenario']: r['ltext'][len('LTEXT_PROVINCIA_'):] for r in orig if not r['sea']}
    key_of_mesh = {r['name']: r['ltext'][len('LTEXT_PROVINCIA_'):] for r in orig if not r['sea']}
    def map_key(pid):
        e = PROVINCES[pid]
        if NEW_BATTLE_MAPS:             # a province on a shared new battlefield (tools/lvl_region.py) borrows the
            import battlemaps           # objectives of the original whose victory conditions its map uses
            ok = battlemaps.objective_key(e[0])
            if ok:
                return ok
        return key_of_scen.get(e[5]) if e[5] else key_of_mesh.get(e[4])
    def lang_values(raw):
        txt = raw[2:].decode('utf-16-le') if raw[:2] == bytes([0xff, 0xfe]) else raw.decode('latin1')
        return dict(re.findall(r'\.(LTEXT_\w+)\s+"([^"]*)"', txt))
    BORROWED = {'Others/TextUIObjetivos.sb': ('LTEXT_OBJETIVOS_ATACANTE_%s', 'LTEXT_OBJETIVOS_DEFENSOR_%s'),
                'Battle/TextUIBatallaVentanaInicioBatalla.sb': ('LTEXT_UI_BATALLA_INITVENT_%s_TEXT',)}
    # the original objective texts are spelled differently from the province keys for these 8 provinces (so the borrowed
    # text was missing and fell back to 'Total Victory': wrong for the Helvetic map, which says 'Control the Village').
    # The four 'Total Victory'-only ones read the same as the fallback in all 8 languages; I_FRANCIA, E_PAPALES and
    # HANNOVER maps have real objectives but no new province borrows them yet.
    OBJ_KEY_ALIAS = {'R_HELVETICA': 'REINAHELVETICA', 'KURKS': 'KURSK', 'BRETANYA': 'BRETANA', 'TOULOUSE': 'TOULOSE',
                     'CATALUNYA': 'CATALUNA', 'I_FRANCIA': 'ISLADEFRANCIA', 'E_PAPALES': 'ESTADOSPAPALES',
                     'HANNOVER': 'HANOVER'}
    for lang in LANGS:
        for frel, fn in files.items():
            p = src_text(lang, frel)
            raw = read(p)
            entries = [e for pid in sorted(PROVINCES) for e in fn(PROVINCES[pid][0], PROVINCES[pid][2], PROVINCES[pid][6])]
            if frel in BORROWED:
                vals = lang_values(raw)
                fixed = {}
                for pid in sorted(PROVINCES):
                    mk = map_key(pid)
                    for pat in BORROWED[frel]:
                        mk_ = OBJ_KEY_ALIAS.get(mk, mk) if frel.startswith('Others/') else mk
                        v = vals.get(pat % mk_) if mk_ else None
                        if v is None:                       # sea zones / unknown map: the language's own 'Total Victory'
                            v = vals.get(pat % 'ANDALUCIA')
                        if v is not None:
                            fixed[pat % (OBJ_KEY[PROVINCES[pid][0]] if frel.startswith('Others/') else PROVINCES[pid][0])] = v
                entries = [(k, fixed.get(k, v)) for k, v in entries]
            out('Texto/%s/%s' % (lang, frel), text_add_entries(raw, entries))

    for lang in LANGS:
        frel = 'Management/TextPuertos.sb'
        out('Texto/%s/%s' % (lang, frel), text_add_entries(read(src_text(lang, frel)), PORT_TEXTS))

    # label of the 'Skip all' button on campaign notifications (exe patch 17)
    SKIP_ALL = {'english': 'Skip all', 'spanish': 'Omitir todo', 'French': 'Tout passer', 'German': 'Alle überspringen',
                'Italian': 'Salta tutto', 'Polish': 'Pomiń wszystko', 'Czech': 'Přeskočit vše',
                'Russian': 'Пропустить все'}
    for lang in LANGS:
        frel = 'Others/TextUI.sb'
        p_ = os.path.join(MOD, 'Texto', lang, frel)
        raw_ = open(p_, 'rb').read() if os.path.exists(p_) else read(src_text(lang, frel))
        if b'LTEXT_UI_NOTIF_SKIP_ALL' not in raw_ and 'LTEXT_UI_NOTIF_SKIP_ALL'.encode('utf-16-le') not in raw_:
            out('Texto/%s/%s' % (lang, frel), text_add_entries(raw_, [('LTEXT_UI_NOTIF_SKIP_ALL', SKIP_ALL[lang])]))

    # 'Cheats' button in the campaign ESC menu and the cheat panel (exe patches 18+)
    cheat_menu()
    cheat_texts()
    # 1789 quest names and the officer pools of the reskinned slots (text only; Russian: apply_translations below)
    quest_texts()
    reskin_officer_texts()
    # scroll bars on the production queues (the human's queues are longer with exe patch 27)
    production_queue_ui()
    # autosave every turn instead of every 3rd, keeping 8 files: cheap insurance against the community's most common
    # crash (loading screen after a battle) on our much bigger map (re_tools/report_ideas_research.md tip 1)
    rel = 'Game/GameModes/Gestion/ModeloGestion.sb'
    txt = read(src(rel)).decode('latin1')
    old_as = '.DEFS_AUTOSAVE  [ .MAX_AUTOSAVE_FILES 5 .TURNOS_AUTOSAVE_UPDATES 3 ]'
    assert txt.count(old_as) == 1, 'autosave block changed'
    out(rel, txt.replace(old_as, '.DEFS_AUTOSAVE  [ .MAX_AUTOSAVE_FILES %d .TURNOS_AUTOSAVE_UPDATES %d ]'
                         % (AUTOSAVE_FILES, AUTOSAVE_EVERY)).encode('latin1'))
    # officer / ship name pool sizes of the new nations: they share counter slot 0xf with the Arab five, and the loader
    # (FUN_00657b90) writes each player's MANDO_/BARCO_ sizes into the slot in player order, so the LAST player wins. The
    # new nations had no blocks -> size 0 -> every officer and ship got name 0 and no numeral (RE 2026-10-22). Give each
    # the same size as JUG_ARABE (48 officers / 55 ships, which texts_new emits for every new nation).
    rel = 'Game/GameModes/Gestion/DefInfoNombres.sb'
    txt = read(src(rel)).decode('latin1')
    nl = '\r\n' if '\r\n' in txt else '\n'
    add = ''.join('%s.%s_JUG_%s%s[%s  .NUM_NOMBRES %d%s  .NUM_TITULOS 10 %s]%s' % (nl, kind, nn['key'], nl, nl, n, nl, nl, nl)
                  for nn in NT.NEW_NATIONS for kind, n in (('MANDO', 48), ('BARCO', 55))
                  if '.%s_JUG_%s' % (kind, nn['key']) not in txt)
    out(rel, (txt.rstrip('\r\n') + nl + add).encode('latin1'))

    # --- renamed nations, capitals and fleets (every Management text file that holds one of the keys)
    seen = set()
    for lang in LANGS:
        base = os.path.join(TEXT, 'texto', lang, 'Management')
        for dp, dns, fns in os.walk(base):
            for fn in fns:
                if not fn.endswith('.sb'):
                    continue
                frel = os.path.relpath(os.path.join(dp, fn), os.path.join(TEXT, 'texto', lang)).replace(os.sep, '/')
                done = os.path.join(MOD, 'Texto', lang, frel)
                p = done if os.path.exists(done) else src_text(lang, frel)
                new, found = text_set_values(open(p, 'rb').read(), texts)
                if found:
                    if p != done:
                        read(p)
                    out('Texto/%s/%s' % (lang, frel), new)
                    seen |= found
    print('  renamed keys found:', sorted(seen), 'missing:', sorted(set(texts) - seen))

    # --- 2D province maps (diplomacy window and menus): whole map, new background and atlases (make_diplo.py)
    import make_diplo
    make_diplo.MOD = MOD                                # the staging tree (build/public/mod with --public)

    def write_img(rel, data, img):
        p = os.path.join(MOD, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        tga.write_tga(p, *img)
        print('  wrote', rel)
    sb = make_diplo.build(write_img, {rel: read(src(rel)).decode('latin1') for rel in UI_MAPS})[0]
    for rel, txt in sb.items():
        out(rel, txt.encode('latin1'))
    txt = read(src(UI_INITVENT)).decode('latin1')
    m0 = re.search(r'^\.CIRENAICA[ \t]*\r?\n', txt, re.M)
    a, b = find_block(txt, m0.end())
    unit = txt[m0.start():b]
    add = ''.join('\r\n\r\n' + unit.replace('CIRENAICA', PROVINCES[pid][0]) for pid in sorted(PROVINCES))
    out(UI_INITVENT, (txt[:b] + add + txt[b:]).encode('latin1'))

    CRLF = chr(13) + chr(10)
    # battle scenarios: one entry per new name, reusing the template's battle map and mini map
    rel = 'Game/GameModes/Batalla/Escenarios.sb'
    txt = read(src(rel)).decode('latin1')
    add = ''
    for new, old_s in sorted(SCEN_TEMPLATE.items(), key=lambda kv: int(kv[0])):
        mm = re.search(r'\.NAME\s+"%s"\s+\.MAPA\s+("[^"]+")' % old_s, txt)
        add += CRLF + '[' + CRLF + '  .NAME "%s"' % new + CRLF + '  .MAPA %s' % mm.group(1) + CRLF + ']'
    if NEW_BATTLE_MAPS:
        import battlemaps
        battlemaps.bind(SCEN_PROV)      # many provinces -> one shared map (battlemap.json 'provinces')
        out(rel, battlemaps.patch_escenarios(txt.rstrip() + add + CRLF).encode('latin1'))
    else:
        out(rel, (txt.rstrip() + add + CRLF).encode('latin1'))
    rel = 'Game/UI/ModeloBatalla/UIDefs_MinBattleMapInfo.sb'
    txt = read(src(rel)).decode('latin1')
    add = ''
    for new, old_s in sorted(SCEN_TEMPLATE.items(), key=lambda kv: int(kv[0])):
        m0 = re.search(r'\[\s*\.NAME\s+"%s"' % old_s, txt)
        a, b = find_block(txt, m0.start())
        add += CRLF + CRLF + txt[a:b].replace('"%s"' % old_s, '"%s"' % new, 1)
    # the new entries go INSIDE the .ESCENARIOS block, before its closing bracket. Until 2026-10-21 they were added
    # before the file's last ']', i.e. inside the .TROPAS block: the minimap lookup FUN_0082ba00 (entries of
    # ESCENARIOS by .NAME = the province's scenario name, FUN_00593a30) never found them and every new province
    # showed the DEFAULT minimap 02Escocia (in-game test log_full16: steppe/desert/India all showed it)
    i = find_block(txt, txt.index('.ESCENARIOS'))[1] - 1
    if NEW_BATTLE_MAPS:
        out(rel, battlemaps.patch_minimap_info(txt[:i] + add + CRLF + txt[i:]).encode('latin1'))
    else:
        out(rel, (txt[:i] + add + CRLF + txt[i:]).encode('latin1'))
    print('  battle scenarios added:', len(SCEN_TEMPLATE))
    # quick game 'select your map': a clicked province is only kept if UIDefs_PoolBitmapEscenario.sb has its preview
    # ESCENARIO_<province key> (FUN_007cc5c0 skips the store otherwise, so the battle ran in the previous province,
    # e.g. Kursk for Chechenya); network games show ESCENARIO_RED_<key>. Each new province borrows its template's.
    rel = 'Game/UI/MainMenu/UIDefs_PoolBitmapEscenario.sb'
    txt = read(src(rel)).decode('latin1')
    key_all_scen = {r['scenario']: r['ltext'][len('LTEXT_PROVINCIA_'):] for r in orig}
    key_all_mesh = {r['name']: r['ltext'][len('LTEXT_PROVINCIA_'):] for r in orig}
    add, n_pool = '', 0
    for pid in sorted(PROVINCES):
        e = PROVINCES[pid]
        tk = key_all_scen.get(e[5]) if e[5] else key_all_mesh.get(e[4])
        for pre in ('ESCENARIO_', 'ESCENARIO_RED_'):
            m0 = re.search(r'\[\s*\.KEY\s+%s%s\s' % (pre, tk), txt) if tk else None
            if m0 is None or re.search(r'\.KEY\s+%s%s\s' % (pre, e[0]), txt):
                continue
            a, b = find_block(txt, m0.start())
            add += CRLF + CRLF + txt[a:b].replace(pre + tk, pre + e[0], 1)
            n_pool += 1
    txt = txt.rstrip() + add + CRLF
    if NEW_BATTLE_MAPS:
        txt = battlemaps.patch_pool(txt)
    out(rel, txt.encode('latin1'))
    print('  quick-game map previews added:', n_pool)
    rel = 'Game/GameModes/NavalBattleMode/Sceneries/Sceneries.sb'
    txt = read(src(rel)).decode('latin1')
    add = ''
    for new, old_s in sorted(SEA_SCEN.items(), key=lambda kv: int(kv[0])):
        mm = re.search(r'\.NAME\s+"%s"\s+\.MAPA\s+("[^"]+")' % old_s, txt)
        add += CRLF + '[' + CRLF + '  .NAME "%s"' % new + CRLF + '  .MAPA %s' % mm.group(1) + CRLF + ']'
    out(rel, (txt.rstrip() + add + CRLF).encode('latin1'))
    print('  naval sceneries added:', len(SEA_SCEN))

    # technology tree: 1789-1815 names and descriptions, nation start techs, one prerequisite fix (tools/techtree.py)
    import techtree
    rel = 'Game/GameModes/Gestion/ArbolTecnologias/DefGrafos.def'
    out(rel, techtree.build(src(rel), techtree.player_keys(os.path.join(MOD, 'Game', 'GameModes', 'DefModeloGestion.mng'))))
    rel = 'Game/GameModes/DefModeloGestion.mng'
    out(rel, techtree.split_era_ltext(open(os.path.join(MOD, rel), 'rb').read()))
    tt, td = 'Management/TextTecnologias.sb', 'Management/TextDescripcionesTecnologias.sb'
    pt = os.path.join(MOD, 'Texto', 'english', tt); pt = pt if os.path.exists(pt) else src_text('english', tt)
    pd = os.path.join(MOD, 'Texto', 'english', td); pd = pd if os.path.exists(pd) else src_text('english', td)
    raw_t, raw_d = techtree.apply_text(open(pt, 'rb').read(), open(pd, 'rb').read(), split_era=True)
    out('Texto/english/' + tt, raw_t); out('Texto/english/' + td, raw_d)
    # the other languages need the Era II key too (else a raw key shows): their own name of the era advance
    for lang in LANGS[1:]:
        p = os.path.join(MOD, 'Texto', lang, tt); p = p if os.path.exists(p) else src_text(lang, tt)
        raw = open(p, 'rb').read()
        enc = 'utf-16-le' if raw[:2] == bytes([0xff, 0xfe]) else 'latin1'
        txt = raw.decode(enc)
        if 'LTEXT_CAMBIO_ERA2' in txt:
            continue
        mm_ = re.search(r'\.LTEXT_CAMBIO_ERA\s+"([^"]*)"', txt)
        assert mm_, lang
        out('Texto/%s/%s' % (lang, tt), text_add_entries(raw, [('LTEXT_CAMBIO_ERA2', mm_.group(1) + ' II')]))
    nation_files()

    # retextured units, officer figures and ship hulls per culture (generated by tools/art/units/cultures.py)
    uout = os.path.join(BUILD, 'units', 'out'); nu = 0
    for dp, dns, fns in os.walk(uout):
        for fn in fns:
            relp = os.path.relpath(os.path.join(dp, fn), uout).replace(os.sep, '/')
            if PUBLIC and public_skips(relp):
                continue
            p = os.path.join(MOD, relp); os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(os.path.join(dp, fn), p); nu += 1
    print('  culture units/figures/hulls:', nu, 'files')
    # 1789 diplomacy: starting alliances/wars/hostility for all 40 players and a more active AI diplomacy
    # (generated by build/diplo1789/make_diplo1789.py; replaces the hostility files written by nation_files)
    # regenerated every build from the fresh mod tree, so it always matches the current player set
    import subprocess
    if PUBLIC:                          # reads the public tree, writes build/public/diplo1789 (not the father's out/)
        dout = os.path.join(OUT_DIR, 'diplo1789', 'out')
        if os.path.exists(dout):
            shutil.rmtree(dout)
        subprocess.run([sys.executable, os.path.join(BUILD, 'diplo1789', 'make_diplo1789.py'), '--mod', MOD, '--out', dout,
                        '--json', os.path.join(OUT_DIR, 'diplo1789', 'diplomacy.json')], check=True)
    else:
        subprocess.run([sys.executable, os.path.join(BUILD, 'diplo1789', 'make_diplo1789.py')], check=True)
        dout = os.path.join(BUILD, 'diplo1789', 'out')
    nd = 0
    for dp, dns, fns in os.walk(dout):
        for fn in fns:
            relp = os.path.relpath(os.path.join(dp, fn), dout).replace(os.sep, '/')
            p = os.path.join(MOD, relp); os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(os.path.join(dp, fn), p); nd += 1
    print('  diplomacy 1789:', nd, 'files')
    # troop icons, portraits and battle buttons of the new nations (tools/art/icons/make_icons.py)
    iout = public_icons() if PUBLIC else os.path.join(BUILD, 'icons', 'out'); ni_ = 0
    for dp, dns, fns in os.walk(iout):
        for fn in fns:
            relp = os.path.relpath(os.path.join(dp, fn), iout).replace(os.sep, '/')
            p = os.path.join(MOD, relp); os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(os.path.join(dp, fn), p); ni_ += 1
    print('  troop icons:', ni_, 'files')
    quick_game_ui()                     # Quick Game cards / buttons / Auto-Buy of every playable nation (needs the icons)
    if NEW_BATTLE_MAPS:                 # scenario folders, minimaps and intro texts of the new battlefields
        import battlemaps
        battlemaps.install(MOD, LANGS, src_text, read, out, text_add_entries)
    if HISTORICAL_EVENTS:               # dated event messages through the campaign sequence Lua (tools/historical_events.py)
        import historical_events
        historical_events.install(MOD, LANGS, src_text, read, out, text_add_entries, mod_or_src)
    apply_translations()
    pak = os.path.join(OUT_DIR, 'Data2.pak')
    write_pak(pak, MOD)
    print('built', pak, os.path.getsize(pak), 'bytes; backups in', BK)


if __name__ == '__main__':
    main()

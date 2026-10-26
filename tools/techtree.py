"""Imperial Glory technology tree: DefGrafos.def reader/writer + 1789-1815 data revision (phase 1, data only).

DefGrafos.def  (Game/GameModes/Gestion/ArbolTecnologias/, loaded via .SVC_ARBOLTECNOLOGIAS; loaders in the exe at
0x617120 / 0x618200 / 0x61a110 / 0x656990):
  chunk {u32 0, u32 filesize}: u32 next_free_id, u32 n_groups
    n x chunk {u32 1, u32 size}  GROUP
  chunk {u32 2, u32 size}: u32 n, n x str                (the 7 LTEXT_RAMA_* regime keys)
  GROUP: str name, str ltext, 4 x i32, u8, u32 n + NODE*, u32 n + EDGE*, u32 n + str* (next-era groups),
         u32 n + {u32 node_id, u32 m, m x u32}* (era links: Advance Era node -> roots of the next-era groups)
  NODE : u32 id, u32 type, u8, u32 f74, u8 f70, i32 x, i32 y, str tec (Spanish key of RepresentacionVisual.sb),
         str atlas, str path, i32 u, i32 v (85x34 cell), str mng (.mng table 8 tech name),
         listA: u32 n + str*  extra prerequisites by tech name (cross-group; empty in vanilla)
         listB: u32 n + str*  JUG_ keys that START with this tech researched (0x67ac90 -> 0x67a680)
         listC: u32 n + u32*  prerequisite node ids (same group, ALL must be researched)
         listD: u32 n + u32*  successor node ids
  EDGE : u32 id, u32 type, u8, 4 x f32 (x1, y1, x2, y2) = positions of the two nodes (drawn arrow only)
Strings: u16 length incl. NUL + latin1 bytes + NUL.

Usage
  import techtree
  data = techtree.build(r'...\\data\\Game\\GameModes\\Gestion\\ArbolTecnologias\\DefGrafos.def')   # bytes
  raw_t, raw_d = techtree.apply_text(raw_TextTecnologias, raw_TextDescripcionesTecnologias)
  (optional) mng_bytes = techtree.split_era_ltext(mng_bytes) + apply_text(..., split_era=True)
"""
import struct, os

# ============================================================================ binary format
def _rs(d, p):
    n = struct.unpack_from('<H', d, p)[0]
    return d[p + 2:p + 2 + n - 1].decode('latin1'), p + 2 + n

def _ws(s):
    b = s.encode('latin1') + b'\0'
    return struct.pack('<H', len(b)) + b

class _R:
    def __init__(s, d): s.d, s.p = d, 0
    def u(s): v = struct.unpack_from('<I', s.d, s.p)[0]; s.p += 4; return v
    def i(s): v = struct.unpack_from('<i', s.d, s.p)[0]; s.p += 4; return v
    def b(s): v = s.d[s.p]; s.p += 1; return v
    def s(s): v, s.p = _rs(s.d, s.p); return v
    def strs(s): return [s.s() for _ in range(s.u())]
    def ints(s): return [s.u() for _ in range(s.u())]

def read(data):
    """bytes -> dict {nextid, groups:[...], tail:[...]} (see module doc for field names)."""
    r = _R(data)
    cid, size = r.u(), r.u(); assert cid == 0 and size == len(data), 'not a DefGrafos.def'
    t = {'nextid': r.u(), 'groups': [], 'tail': []}
    for _ in range(r.u()):
        cid, size = r.u(), r.u(); start = r.p - 8; assert cid == 1
        g = {'name': r.s(), 'ltext': r.s(), 'rect': [r.i() for _ in range(4)], 'flag': r.b(), 'nodes': [], 'edges': []}
        for _ in range(r.u()):
            n = {'id': r.u(), 'type': r.u(), 'bflag': r.b(), 'f74': r.u(), 'f70': r.b(), 'x': r.i(), 'y': r.i(),
                 'tec': r.s(), 'atlas': r.s(), 'path': r.s(), 'u': r.i(), 'v': r.i(), 'mng': r.s()}
            n['listA'] = r.strs(); n['listB'] = r.strs(); n['listC'] = r.ints(); n['listD'] = r.ints()
            g['nodes'].append(n)
        for _ in range(r.u()):
            e = {'id': r.u(), 'type': r.u(), 'bflag': r.b(), 'xy': list(struct.unpack_from('<4f', r.d, r.p))}
            r.p += 16; g['edges'].append(e)
        g['succ'] = r.strs()
        g['links'] = []
        for _ in range(r.u()):
            a = r.u(); g['links'].append({'id': a, 'list': r.ints()})
        assert r.p == start + size, (g['name'], r.p, start + size)
        t['groups'].append(g)
    if r.p < len(data):
        cid, size = r.u(), r.u(); assert cid == 2
        t['tail'] = r.strs()
        assert r.p == len(data)
    return t

def _strs(l): return struct.pack('<I', len(l)) + b''.join(_ws(s) for s in l)
def _ints(l): return struct.pack('<I', len(l)) + struct.pack('<%dI' % len(l), *l)

def write(t):
    """dict -> bytes (exact inverse of read)."""
    body = b''
    for g in t['groups']:
        gb = _ws(g['name']) + _ws(g['ltext']) + struct.pack('<4iB', *g['rect'], g['flag'])
        gb += struct.pack('<I', len(g['nodes']))
        for n in g['nodes']:
            gb += struct.pack('<IIBIBii', n['id'], n['type'], n['bflag'], n['f74'], n['f70'], n['x'], n['y'])
            gb += _ws(n['tec']) + _ws(n['atlas']) + _ws(n['path']) + struct.pack('<ii', n['u'], n['v']) + _ws(n['mng'])
            gb += _strs(n['listA']) + _strs(n['listB']) + _ints(n['listC']) + _ints(n['listD'])
        gb += struct.pack('<I', len(g['edges']))
        for e in g['edges']:
            gb += struct.pack('<IIB4f', e['id'], e['type'], e['bflag'], *e['xy'])
        gb += _strs(g['succ']) + struct.pack('<I', len(g['links']))
        for L in g['links']:
            gb += struct.pack('<I', L['id']) + _ints(L['list'])
        body += struct.pack('<II', 1, 8 + len(gb)) + gb
    out = struct.pack('<II', t['nextid'], len(t['groups'])) + body
    if t['tail']:
        tb = _strs(t['tail']); out += struct.pack('<II', 2, 8 + len(tb)) + tb
    return struct.pack('<II', 0, 8 + len(out)) + out

# ============================================================================ helpers
def nodes_by_mng(t, mng):
    """All (group, node) pairs for a tech name (a tech appears once per regime graph it belongs to)."""
    return [(g, n) for g in t['groups'] for n in g['nodes'] if n['mng'] == mng]

def add_start_tech(t, mng, jug):
    """Add a JUG_ key to listB of every node of tech `mng`. Returns number of nodes changed."""
    k = 0
    for g, n in nodes_by_mng(t, mng):
        if jug not in n['listB']:
            n['listB'].append(jug); k += 1
    return k

def prereq_closure(t, mng):
    """Tech plus all its (same-group, listC) ancestors, in research order. Uses the first graph containing it."""
    gn = nodes_by_mng(t, mng)
    if not gn: return []
    g = gn[0][0]; byid = {n['id']: n for n in g['nodes']}
    out = []
    def visit(n):
        for i in n['listC']: visit(byid[i])
        if n['mng'] not in out: out.append(n['mng'])
    visit(gn[0][1])
    return out

def retarget_prereq(t, node_mng, old_pre_mng, new_pre_mng):
    """Replace prerequisite old->new of `node_mng` in every group that holds all three: updates listC of the node,
    listD of old and new prerequisite, and moves the arrow (edge whose coords join old->node) to new->node."""
    done = 0
    for g in t['groups']:
        by = {n['mng']: n for n in g['nodes']}
        if not all(k in by for k in (node_mng, old_pre_mng, new_pre_mng)): continue
        n, o, w = by[node_mng], by[old_pre_mng], by[new_pre_mng]
        if o['id'] not in n['listC']: continue
        assert w['id'] not in n['listC']
        n['listC'][n['listC'].index(o['id'])] = w['id']
        o['listD'].remove(n['id']); w['listD'].append(n['id'])
        hits = [e for e in g['edges'] if e['xy'] == [float(o['x']), float(o['y']), float(n['x']), float(n['y'])]]
        assert len(hits) == 1, ('arrow not found', g['name'], node_mng, old_pre_mng)
        hits[0]['xy'] = [float(w['x']), float(w['y']), float(n['x']), float(n['y'])]
        done += 1
    return done

def check(t):
    """Consistency: listC/listD mirror each other and every prerequisite has exactly one arrow."""
    for g in t['groups']:
        byid = {n['id']: n for n in g['nodes']}
        arrows = {tuple(e['xy']) for e in g['edges']}
        for n in g['nodes']:
            for i in n['listC']:
                p = byid[i]; assert n['id'] in p['listD'], (g['name'], n['mng'], p['mng'])
                assert (float(p['x']), float(p['y']), float(n['x']), float(n['y'])) in arrows, (g['name'], p['mng'], n['mng'])
            for i in n['listD']:
                assert n['id'] in byid[i]['listC'], (g['name'], n['mng'], byid[i]['mng'])
    return True

# ============================================================================ 1789-1815 revision
# Prerequisite fixes (node, old prerequisite, new prerequisite). Era I only; listC, listD and the arrow are moved together.
# Harbour Works (Harbour Infrastructure) grew out of overseas trade, not out of dynastic diplomacy.
# Journalism <- Basic Education was NOT applied: the arrow would cross the whole Era I panel (570,300)->(735,540).
PREREQ_FIXES = [
    ('INFRAESTRUCTURA_PORTUARIA', 'ANEXION_PACIFICA', 'COMERCIO_INTERNACIONAL'),
]

# Starting techs (listB). Vanilla entries are kept. Prerequisites inside the graph are added automatically
# (START_WITH_PREREQS) so no nation owns a tech without its parents. Keys checked against .mng table 0.
START_TECHS = {
    'JUG_GRAN_BRETANYA': ['COMERCIO_INTERNACIONAL', 'INFRAESTRUCTURA_PORTUARIA'],   # chartered companies, harbour works
    'JUG_FRANCIA':       ['CARRERA_MILITAR', 'INFANTERIA_BASICA'],                 # Ecole Militaire, drill of 1791
    'JUG_PRUSIA':        ['CARRERA_MILITAR', 'INFANTERIA_BASICA'],                 # Frederician drill
    'JUG_AUSTRIA':       ['ANEXION_PACIFICA', 'CARRERA_MILITAR'],                  # dynastic marriages, Theresian academy
    'JUG_RUSIA':         ['CONSERVACION_ALIMENTOS', 'CARRERA_MILITAR', 'CABALLERIA_BASICA'],  # magazines, Cossacks
    'JUG_OTOMANO':       ['CABALLERIA_BASICA'],                                    # sipahi (no VACUNACION: see Qing)
    'JUG_MARATHA':       ['CABALLERIA_BASICA'],                                    # Maratha light horse
    'JUG_PERSIA':        ['CABALLERIA_BASICA'],                                    # Qajar tribal cavalry
    # Qing: no VACUNACION (2026-10-23): it unlocks the Medical Revolution quest (DefQuest .POBLACION 2500) and Qing starts
    # with 2800 population, so the AI completed it in turn 1 (Local Hospitals everywhere)
    'JUG_QING':          ['CONSERVACION_ALIMENTOS'],                               # ever-normal granaries
    'JUG_JAPAN':         ['CONSERVACION_ALIMENTOS', 'SIERRA_CIRCULAR'],            # rice storehouses, Tokugawa forestry
    # (Durrani, Joseon and Mysore were merged into the regional peoples on 2026-10-17: world_nations.MERGED)
    'JUG_CHECHNYA':      ['INFANTERIA_BASICA', 'CABALLERIA_BASICA'],               # Sheikh Mansur's murids, mountain horsemen
}
START_WITH_PREREQS = True

# Tech names (LTEXT_<tech> in text/texto/<lang>/Management/TextTecnologias.sb). Buildings keep their names.
RENAMES = {
    # --- Era I, 1789-1799
    'LTEXT_CONSERVACION_ALIMENTOS': 'Magazine System',
    'LTEXT_SIERRA_CIRCULAR': 'Mechanised Sawmilling',
    'LTEXT_VACUNACION': 'Smallpox Inoculation',
    'LTEXT_EDUCACION_BASICA': 'Elementary Schooling',
    'LTEXT_CARRERA_MILITAR': 'Military Academies',
    'LTEXT_INFANTERIA_BASICA': 'Line Infantry Drill',
    'LTEXT_CABALLERIA_BASICA': 'Hussars and Light Horse',
    'LTEXT_CONSTRUCCION_ARTILLERIA': 'Gribeauval System',
    'LTEXT_INFRAESTRUCTURA_NAVAL': 'Copper Sheathing',
    'LTEXT_MANIOBRAS_MILITARES': 'Divisional System',
    'LTEXT_COMERCIO_INTERNACIONAL': 'Chartered Companies',
    'LTEXT_INFRAESTRUCTURA_PORTUARIA': 'Harbour Works',
    'LTEXT_MERCADO_DOMESTICO': 'Free Trade Doctrine',
    'LTEXT_ANEXION_PACIFICA': 'Dynastic Diplomacy',
    'LTEXT_PERIODISMO': 'Revolutionary Press',
    'LTEXT_SERVICIO_SECRETO': 'Cabinet Noir',
    # --- Era II, 1799-1807
    'LTEXT_AGRICULTURA_MODERNA': 'Improved Husbandry',
    'LTEXT_BOMBA_VAPOR': 'Watt Steam Engine',
    'LTEXT_ASISTENCIA_SANITARIA': 'Cowpox Vaccination',
    'LTEXT_EDUCACION_MODERNA': 'Polytechnic Schools',
    'LTEXT_INSTRUCCION_OFICIALES': 'General Staff',
    'LTEXT_INFANTERIA_AVANZADA': 'Tirailleurs and Rifles',
    'LTEXT_CABALLERIA_AVANZADA': 'Cuirassier Reserve',
    'LTEXT_MANUFACTURA_ARTILLERIA': 'Horse Artillery',
    'LTEXT_MANIOBRAS_NACIONALES': "Corps d'Armée System",
    'LTEXT_ORGANIZACION_NAVAL': 'Popham Signal Code',
    'LTEXT_MANIOBRAS_NAVALES': 'Breaking the Line',
    'LTEXT_PUERTOS_INDUSTRIALIZADOS': 'Wet Docks',
    'LTEXT_GUARDACOSTAS': 'Coastal Lights Service',
    'LTEXT_IMPUESTO_RENTAS': "Pitt's Income Tax",
    'LTEXT_RED_ESPIONAJE': "Fouché's Spy Network",
    'LTEXT_CIRUGIA': 'Flying Ambulances',
    'LTEXT_PROPAGANDA': 'Imperial Bulletins',
    # --- Era III, 1807-1815
    'LTEXT_REFORMA_AGRARIA': 'Emancipation Edicts',
    'LTEXT_SIDERURGIA': 'Puddling and Rolling',
    'LTEXT_SERVICIO_MILITAR': 'Krümper System',
    'LTEXT_INFANTERIA_ELITE': 'Imperial Guard',
    'LTEXT_CABALLERIA_ELITE': 'Lancer Regiments',
    'LTEXT_PROD_IND_ARTILLERIA': 'Grand Battery',
    'LTEXT_ARMADA_MODERNA': 'Standard Ship Designs',
    'LTEXT_MODERNIZACION_PUERTOS': 'Enclosed Dockyards',
    'LTEXT_RECONOCIMIENTO_NAVAL': 'Rock Lighthouses',
    'LTEXT_EDUCACION_AVANZADA': 'Humboldtian University',
    'LTEXT_ALTO_MANDO': 'Scharnhorst Reforms',
    'LTEXT_POLICIA_SECRETA': 'Ministry of Police',
    'LTEXT_SUBVERSION': 'Guerrilla Warfare',
    'LTEXT_PIRATERIA': 'Privateering',
    'LTEXT_INGENIERIA_FISCAL': 'Public Credit',
    'LTEXT_PRESION_FISCAL': 'Fiscal Centralisation',
    'LTEXT_SINDICALISMO': 'Sans-culotte Sections',
    'LTEXT_ILUSTRACION': 'Enlightened Absolutism',
    'LTEXT_CATASTRO': 'Cadastral Survey',
    'LTEXT_CUERPO_VOLUNTARIOS': 'Landwehr',
    'LTEXT_CAPITALISMO': 'Funded National Debt',
    'LTEXT_REVOLUCION_INDUSTRIAL': 'Factory System',
    'LTEXT_RECLUTAMIENTO_FORZOSO': 'Jourdan Conscription Law',
    'LTEXT_PREFECTURA': 'Prefects',
}
# Both Advance Era nodes share LTEXT_CAMBIO_ERA in the .mng. Without split_era_ltext() they get ERA_SHARED_NAME;
# with it, Era I keeps LTEXT_CAMBIO_ERA and Era II's record points to the new key LTEXT_CAMBIO_ERA2.
ERA_SHARED_NAME = 'March of the Age'
ERA_NAMES = {'LTEXT_CAMBIO_ERA': 'War of the First Coalition', 'LTEXT_CAMBIO_ERA2': 'The Continental System'}

H = r'\cFFFF61'          # highlight colour code used by the game's texts
E = r'\c'
Q = r' \n \n\cE61414'    # quest line prefix
DESCS = {
    # --- Era I
    'LTEXT_DESC_CONSERVACION_ALIMENTOS': r"Since the wars of Louis XIV, armies have marched on chains of supply depots. Organise a Magazine System of salted provisions, biscuit and grain and we will be able to build " + H + r"Rations Warehouses" + E + r".",
    'LTEXT_DESC_SIERRA_CIRCULAR': r"Samuel Miller's circular saw of 1777, driven by water wheels, cuts timber far faster than the pit saw. Development of this Advance will enable us to build " + H + r"Saw Mills" + E + r".",
    'LTEXT_DESC_VACUNACION': r"Inoculation with smallpox matter, long practised in China and the Ottoman Empire, protects our people from the deadliest disease of the age. Research Smallpox Inoculation to build " + H + r"Local Hospitals" + E + r"." + Q + r"Also activates the Medical Revolution Quest." + E,
    'LTEXT_DESC_EDUCACION_BASICA': r"Prussia's school law of 1763 showed that every parish can teach its children to read. Research Elementary Schooling and we will be able to build " + H + r"Primary Schools" + E + r"." + Q + r"Also activates the Steam Quest." + E,
    'LTEXT_DESC_CARRERA_MILITAR': r"Royal military schools such as the Ecole Militaire (1750) and the Theresian Academy (1751) turn noble sons into professional officers. Once this programme is in place, we may build the " + H + r"Military Academy" + E + r".",
    'LTEXT_DESC_INFANTERIA_BASICA': r"Drilled to the regulations of the 1790s, line infantry delivers volley fire shoulder to shoulder. Research Line Infantry Drill and we will be able to build " + H + r"Basic Barracks" + E + r".",
    'LTEXT_DESC_CABALLERIA_BASICA': r"Hussars, chasseurs and Cossacks screen the army, scout and pursue a broken enemy. Research Hussars and Light Horse in order to build the " + H + r"Basic Stables" + E + r" and start recruiting such units. This will also activate the possibility of " + H + r"capturing prisoners" + E + r" in battle.",
    'LTEXT_DESC_CONSTRUCCION_ARTILLERIA': r"Gribeauval's system of 1765 gave France light, standardised guns with interchangeable parts. Adopting it and constructing " + H + r"Basic Foundries" + E + r" will allow us to build Cannons for our army. This also activates the ability to " + H + r"capture artillery" + E + r" during battles.",
    'LTEXT_DESC_INFRAESTRUCTURA_NAVAL': r"Since the 1780s the Royal Navy sheathes its hulls in copper, keeping them fast and free of shipworm. Copper Sheathing will allow construction of a " + H + r"Military Harbour" + E + r" at our wharves. This also activates the ability to " + H + r"capture ships" + E + r" after battles." + Q + r"Also activates the Ruler of the Seas Quest." + E,
    'LTEXT_DESC_MANIOBRAS_MILITARES': r"Guibert's Essai general de tactique (1772) split armies into divisions that march apart and fight together. Adopting the Divisional System will increase infantry and cavalry " + H + r"resistance" + E + r" to Mel\xe9e attacks, and " + H + r"damage" + E + r" caused by their Ranged attacks." + Q + r"Also activates the Exposition Quest." + E,
    'LTEXT_DESC_COMERCIO_INTERNACIONAL': r"East India and Levant companies with royal charters carry our flag to distant markets. Establish such Chartered Companies and we will be able to build a " + H + r"Trade Branch" + E + r"." + Q + r"Also activates the Agrarian Revolution Quest." + E,
    'LTEXT_DESC_INFRAESTRUCTURA_PORTUARIA': r"Breakwaters, quays and dredged channels, like those built at Cherbourg from 1783, are vital if we wish to create commercial sea routes, as they allow construction of " + H + r"Merchant Harbours" + E + r".",
    'LTEXT_DESC_MERCADO_DOMESTICO': r"Adam Smith's Wealth of Nations (1776) and Turgot's reforms argue for the free movement of grain and goods. The Free Trade Doctrine will allow our Empire to construct the " + H + r"Department of Trade" + E + r" and also activate the " + H + r"Right of Passage" + E + r" diplomacy option.",
    'LTEXT_DESC_ANEXION_PACIFICA': r"Let others wage war; marriages, inheritances and treaties have built the greatest houses of Europe. Master Dynastic Diplomacy and we may build the " + H + r"Consulate" + E + r". This will also activate the " + H + r"Commercial Treaty" + E + r" diplomacy option.",
    'LTEXT_DESC_PERIODISMO': r"In 1789 hundreds of newspapers and pamphlets appeared in Paris alone. A Revolutionary Press promotes our image in foreign countries: it activates the " + H + r"Improve Relations" + E + r" diplomacy option, and lets us build the " + H + r"Newspaper Office" + E + r"." + Q + r"Also activates the Rosetta Stone Quest." + E,
    'LTEXT_DESC_SERVICIO_SECRETO': r"The Cabinet Noir secretly opens and copies the letters of ambassadors and conspirators. Developing it and constructing the " + H + r"Department of Information" + E + r" will provide our Empire with valuable information on surrounding countries.",
    # --- Era II
    'LTEXT_DESC_AGRICULTURA_MODERNA': r"Bakewell's selective breeding, Norfolk crop rotation and the new agricultural societies raise yields everywhere. With Improved Husbandry our Empire will be able to build " + H + r"Subsidised Farms" + E + r" and thus improve production of Food.",
    'LTEXT_DESC_BOMBA_VAPOR': r"James Watt's engine with separate condenser (1776) pumps water from mines far below the old workings, and allows us to construct " + H + r"Deep-shaft Mines" + E + r", which will increase our production of Raw Materials.",
    'LTEXT_DESC_ASISTENCIA_SANITARIA': r"Edward Jenner's cowpox vaccine of 1796 is safer than inoculation, and Napoleon had his whole army vaccinated in 1805. Cowpox Vaccination will increase life expectancy and thus our population. Develop it in order to build " + H + r"Modern Hospitals" + E + r".",
    'LTEXT_DESC_EDUCACION_MODERNA': r"The Ecole Polytechnique (1794) trains engineers and artillerists in mathematics and science. Found Polytechnic Schools to build " + H + r"Specialised Schools" + E + r"." + Q + r"Also activates the Metric System Quest." + E,
    'LTEXT_DESC_INSTRUCCION_OFICIALES': r"Berthier's staff and the Prussian General Staff of 1803 turn a general's will into orders for a hundred thousand men. A General Staff grants our cavalry increased damage to its " + H + r"Charge" + E + r" attacks, enables us to build the " + H + r"Advanced Military Academy" + E + r", and enables our infantry to use the " + H + r"Double Line formation" + E + r"." + Q + r"Also activates the Treaty of Jassy Quest." + E,
    'LTEXT_DESC_INFANTERIA_AVANZADA': r"French tirailleurs and the British 95th Rifles fight in open order, yet must still form square against horsemen. Drill your troops so that they may learn the " + H + r"Square formation" + E + r" - invaluable against cavalry charges. With training concluded, " + H + r"Advanced Barracks" + E + r" may then be built in all capital cities with a " + H + r"Basic Barracks" + E + r".",
    'LTEXT_DESC_CABALLERIA_AVANZADA': r"Armoured cuirassiers held in reserve deliver the decisive charge, as at Eylau in 1807. Forming a Cuirassier Reserve will allow us to construct " + H + r"Advanced Stables" + E + r", which may be built in all capital cities which have " + H + r"Basic Stables" + E + r"." + Q + r"Also activates the Army Reform Quest." + E,
    'LTEXT_DESC_MANUFACTURA_ARTILLERIA': r"Horse artillery, with every gunner mounted, keeps pace with the cavalry and gallops into firing range. Researching it will allow our Empire to build " + H + r"Advanced Foundries" + E + r" and so equip our Army with larger and more effective Cannons.",
    'LTEXT_DESC_MANIOBRAS_NACIONALES': r"From 1800 Napoleon's armies march as self-contained corps of all arms that can fight alone for a day. The Corps d'Armée System increases our Artillery's effective " + H + r"Impact area" + E + r" and its resistance to Ranged attacks. This Advance also allows us to build " + H + r"Firing Ranges" + E + r".",
    'LTEXT_DESC_ORGANIZACION_NAVAL': r"Home Popham's signal code of 1800 lets an admiral speak to his whole fleet with flags. This Advance makes it possible for our Empire to build the " + H + r"Military Port" + E + r" - an important milestone in the formation of a strong Navy.",
    'LTEXT_DESC_MANIOBRAS_NAVALES': r"At the Nile and Trafalgar Nelson broke through the enemy line instead of fighting it ship for ship. Learning to Break the Line will allow us to build the " + H + r"Naval Academy" + E + r" and increase Crew experience.",
    'LTEXT_DESC_PUERTOS_INDUSTRIALIZADOS': r"London's West India Docks (1802) lock ships into guarded basins, safe from tides and thieves. Building Wet Docks and constructing " + H + r"Merchant Ports" + E + r" is an important step in increasing the profitability of commercial sea routes.",
    'LTEXT_DESC_GUARDACOSTAS': r"Aimé Argand's oil lamp of 1780, set before polished reflectors, makes lights visible far out to sea. A Coastal Lights Service, when coupled with the latest " + H + r"Argand Lighthouse" + E + r" technology, can be a useful tool for improving our knowledge of the surrounding seas." + Q + r"Also activates the Cartography Quest." + E,
    'LTEXT_DESC_IMPUESTO_RENTAS': r"In 1799 William Pitt introduced the first income tax to pay for the war against France. Establishing such a tax allows Democratic governments to build " + H + r"Tax Collection Buildings" + E + r", and so improve their production of Gold.",
    'LTEXT_DESC_RED_ESPIONAJE': r"Joseph Fouché's agents and informers reach into every salon and every foreign court. Fouché's Spy Network allows us to build the " + H + r"Ministry of Foreign Affairs" + E + r". It also grants the " + H + r"Industrial Espionage" + E + r" feature, which informs us of what other countries are building." + Q + r"Also activates the Continental Blockade Quest." + E,
    'LTEXT_DESC_CIRUGIA': r"Dominique-Jean Larrey's flying ambulances of 1792 carry the wounded from the field while the battle still rages. Develop them to build " + H + r"Military Hospitals" + E + r".",
    'LTEXT_DESC_PROPAGANDA': r"The Bulletins of the Grande Armée told Europe of every victory - and of few defeats. Imperial Bulletins, distributed across lands intended to be annexed, strengthen our influence on their populace and let us create the " + H + r"Army Bulletin" + E + r".",
    # --- Era III
    'LTEXT_DESC_REFORMA_AGRARIA': r"The Prussian October Edict of 1807 freed the peasants and opened the land market. Emancipation Edicts raise agricultural productivity and allow us to construct the " + H + r"Ministry of Agriculture" + E + r".",
    'LTEXT_DESC_SIDERURGIA': r"Henry Cort's puddling furnace and grooved rolls (1784) turn coal-smelted pig iron into bar iron in great quantity. Puddling and Rolling will allow us to build " + H + r"Steel Mills" + E + r", thus increasing our output of Raw Materials.",
    'LTEXT_DESC_SERVICIO_MILITAR': r"After 1807 Prussia, limited to 42,000 soldiers, trained men in short turns and sent them home as a hidden reserve. The Krümper System is an extremely useful tool for increasing our Empire's population, when used in conjunction with " + H + r"Enlistment Offices" + E + r".",
    'LTEXT_DESC_INFANTERIA_ELITE': r"The Imperial Guard, veterans of a dozen campaigns, is committed only when the battle must be won. Raising such a Guard will enable us to build the " + H + r"Elite Barracks" + E + r".",
    'LTEXT_DESC_CABALLERIA_ELITE': r"The Polish lancers of the Guard (1807) made the lance feared again, and every army copied them. Raising Lancer Regiments will enable us to build the " + H + r"Elite Stables" + E + r".",
    'LTEXT_DESC_PROD_IND_ARTILLERIA': r"At Wagram in 1809 a battery of more than a hundred guns smashed the Austrian centre. The Grand Battery represents the final step in the development of our Artillery industry, allowing us to build " + H + r"Elite Foundries" + E + r".",
    'LTEXT_DESC_ARMADA_MODERNA': r"Sané's standard 74-gun design let French yards build identical ships of the line in series. Standard Ship Designs will allow our Empire to build a " + H + r"Military Dockyard" + E + r", complete with the latest equipment and facilities needed to build the finest vessels.",
    'LTEXT_DESC_MODERNIZACION_PUERTOS': r"Enclosed dockyards with new quays, loading docks and bonded warehouses, as at Liverpool and Antwerp, are vital for commercial sea routes. Research them to build " + H + r"Merchant Dockyards" + E + r".",
    'LTEXT_DESC_RECONOCIMIENTO_NAVAL': r"Robert Stevenson's Bell Rock Lighthouse (1810) stands on a reef covered by every tide. Rock Lighthouses represent the final step in the development of our Harbours. With them, we may construct the " + H + r"Fresnel Lighthouse" + E + r" and increase our knowledge of surrounding waters.",
    'LTEXT_DESC_EDUCACION_AVANZADA': r"Wilhelm von Humboldt's University of Berlin (1810) unites teaching with research. By founding a Humboldtian University, we will be able to build " + H + r"Universities" + E + r", and so improve our production of Research Points.",
    'LTEXT_DESC_ALTO_MANDO': r"Scharnhorst and Gneisenau rebuilt the Prussian army after Jena: promotion by merit, a trained staff, a nation in arms. The Scharnhorst Reforms let us build the " + H + r"Elite Military Academy" + E + r". They also increase the damage caused by your infantry's mel\xe9e and cavalry's " + H + r"Charge" + E + r" attacks.",
    'LTEXT_DESC_POLICIA_SECRETA': r"Napoleon's Ministry of Police watches émigrés, royalists and Jacobins alike. It is a powerful tool for obtaining information and for suppressing any opposition. Develop it to build " + H + r"Police Stations" + E + r".",
    'LTEXT_DESC_SUBVERSION': r"The Spanish guerrilla from 1808 showed how a people in arms can bleed an occupying army. Promote such uprisings in regions controlled by a rival Empire: research Guerrilla Warfare to build the " + H + r"Resistance Cell" + E + r".",
    'LTEXT_DESC_PIRATERIA': r"Letters of marque turn merchant captains into privateers - Surcouf alone took dozens of British ships. By encouraging Privateering we will be able to build facilities which will allow us to continue trading, even when our harbours suffer blockades.",
    'LTEXT_DESC_INGENIERIA_FISCAL': r"The Banque de France (1800) and a sound public credit pay for armies without ruinous loans. Developing Public Credit is exclusive to " + H + r"Republics" + E + r". It will enable us to build the " + H + r"Central Bank" + E + r" and thus, improve our economy.",
    'LTEXT_DESC_PRESION_FISCAL': r"The Republic replaced the tax farmers with one national administration of direct taxes. Fiscal Centralisation increases the amount of tax collected by our officials and lets us build the " + H + r"Treasury Department" + E + r". This is exclusive to " + H + r"Republics" + E + r".",
    'LTEXT_DESC_SINDICALISMO': r"Exclusive to " + H + r"Republics" + E + r", the Sans-culotte Sections of Paris gave artisans and workers a voice in the Revolution. They will improve Population production by " + H + r"25%" + E + r"." + Q + r"Also activates the Declaration of the Rights of Man." + E,
    'LTEXT_DESC_ILUSTRACION': r"Exclusive to " + H + r"Absolute Monarchies" + E + r", Enlightened Absolutism - the way of Frederick II, Joseph II and Catherine II - puts reason and science at the service of the crown. It will increase production of Research Points by " + H + r"10%" + E + r"." + Q + r"Also activates the Army of Condé Quest." + E,
    'LTEXT_DESC_CATASTRO': r"Exclusive to " + H + r"Absolute Monarchies" + E + r", a Cadastral Survey, like the Theresian and Josephine cadastres, measures every field so that every subject pays his taxes. It increases production of Gold by " + H + r"10%" + E + r".",
    'LTEXT_DESC_CUERPO_VOLUNTARIOS': r"Exclusive to " + H + r"Absolute Monarchies" + E + r", the Landwehr militia raised in Austria (1808) and Prussia (1813) swells the ranks of our armies, as military units will become " + H + r"10%" + E + r" cheaper to recruit and train.",
    'LTEXT_DESC_CAPITALISMO': r"Exclusive to " + H + r"Constitutional Monarchies" + E + r", a Funded National Debt, backed by Parliament and the Bank of England, lets the state borrow cheaply in any war, giving the Treasury an additional " + H + r"20%" + E + r" over our initial Gold production without the need for any accompanying construction.",
    'LTEXT_DESC_REVOLUCION_INDUSTRIAL': r"Exclusive to " + H + r"Constitutional Monarchies" + E + r", the Factory System of Arkwright's mills gathers workers and machines under one roof. Thus, the production of Raw Materials will increase by " + H + r"10%" + E + r" from its initial rate.",
    'LTEXT_DESC_RECLUTAMIENTO_FORZOSO': r"Exclusive to " + H + r"Dictatorships" + E + r", the Jourdan Law of 1798 makes every young man liable to serve. It will grant our Empire a period of " + H + r"6" + E + r" turns during which we may recruit basic infantry " + H + r"50%" + E + r" cheaper. This opportunity will then reoccur every " + H + r"20" + E + r" turns.",
    'LTEXT_DESC_PREFECTURA': r"Exclusive to " + H + r"Dictatorships" + E + r", the Prefects created by Napoleon in 1800 govern each department for Paris, centralising the administration of agricultural output and increasing the production of Food across the Empire by " + H + r"50%" + E + r" from its initial rate.",
    # --- Advance Era (separate desc keys already exist in the game)
    'LTEXT_DESC_CAMBIO_ERA1': r"In 1792 revolutionary France went to war with the crowned heads of Europe. As we advance to the next Era of our Times, you will be able to choose for our Empire, one of two political systems - " + H + r"Autocratic" + E + r" or " + H + r"Democratic" + E + r".",
    'LTEXT_DESC_CAMBIO_ERA2': r"With the Berlin Decree of 1806 Napoleon closed the continent to British trade, and every state had to take a side. As we advance to the final Era of our Times, you will be able to choose one of the following political ideals - " + H + r"Dictatorship" + E + r", " + H + r"Absolute Monarchy" + E + r", " + H + r"Republic" + E + r" or " + H + r"Constitutional Monarchy" + E + r".",
}
# r'' strings keep \c and \n literal as the game expects; \xe9 above is written literally, fix it to the real char:
DESCS = {k: v.replace(r'\xe9', '\xe9') for k, v in DESCS.items()}

# ============================================================================ build
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_MNG = os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'DefModeloGestion.mng')

def player_keys(mng_path=MOD_MNG):
    """JUG_ keys of .mng table 0 (nation roster)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import igmod
    m = igmod.Mng(open(mng_path, 'rb').read())
    return set(igmod.Mng.parse_enum(m.chunks[0]).values())

def apply(defgrafos_bytes, players=None, start_techs=None, with_prereqs=START_WITH_PREREQS, fixes=True, log=None):
    """Return modified DefGrafos bytes: prerequisite fixes + starting techs (listB). `players` = set of valid JUG_
    keys (default: read from the mod .mng); keys not in it are skipped."""
    t = read(defgrafos_bytes)
    players = player_keys() if players is None else set(players)
    log = log if log is not None else []
    if fixes:
        for f in PREREQ_FIXES:
            k = retarget_prereq(t, *f); log.append('prereq %s: %s -> %s (%d graph)' % (f[0], f[1], f[2], k))
    for jug, techs in (start_techs or START_TECHS).items():
        if jug not in players:
            log.append('skip %s (no such player key)' % jug); continue
        all_t = []
        for tech in techs:
            assert nodes_by_mng(t, tech), tech
            for x in (prereq_closure(t, tech) if with_prereqs else [tech]):
                if x not in all_t: all_t.append(x)
        for x in all_t:
            add_start_tech(t, x, jug)
        log.append('%s starts with %s' % (jug, ', '.join(all_t)))
    check(t)
    out = write(t)
    read(out)
    return out

def build(src_defgrafos_path, players=None, log=None):
    """Read the original DefGrafos.def, verify the writer round-trips it, return the revised bytes."""
    src = open(src_defgrafos_path, 'rb').read()
    assert write(read(src)) == src, 'DefGrafos writer does not round-trip'
    return apply(src, players, log=log)

def apply_text(raw_tecnologias, raw_descripciones, split_era=False):
    """Apply RENAMES / ERA names and DESCS to TextTecnologias.sb and TextDescripcionesTecnologias.sb (raw bytes,
    encoding kept). split_era=True only together with split_era_ltext() on the .mng."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import igmod
    names = dict(RENAMES)
    names['LTEXT_CAMBIO_ERA'] = ERA_NAMES['LTEXT_CAMBIO_ERA'] if split_era else ERA_SHARED_NAME
    t, found = igmod.text_set_values(raw_tecnologias, names)
    missing = set(names) - found; assert not missing, missing
    if split_era:
        t = igmod.text_add_entries(t, [('LTEXT_CAMBIO_ERA2', ERA_NAMES['LTEXT_CAMBIO_ERA2'])])
    d, found = igmod.text_set_values(raw_descripciones, DESCS)
    missing = set(DESCS) - found; assert not missing, missing
    return t, d

def split_era_ltext(mng_bytes):
    """Optional: give the Era II Advance Era tech (CAMBIO_ERA_2, .mng section 10) its own name key LTEXT_CAMBIO_ERA2."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import igmod
    m = igmod.Mng(mng_bytes)
    te = {v: k for k, v in igmod.Mng.parse_enum(m.table(8)).items()}
    sec = m.section(10); b = sec.body; p = 0; out = b''
    for _ in range(sec.cnt):
        idx = struct.unpack_from('<I', b, p)[0]
        lt, q = _rs(b, p + 4); ld, q = _rs(b, q); end = q + 48
        if idx == te['CAMBIO_ERA_2']:
            lt = 'LTEXT_CAMBIO_ERA2'
        out += struct.pack('<I', idx) + _ws(lt) + _ws(ld) + b[q:end]; p = end
    assert p == len(b)
    sec.body = out
    return m.pack()

if __name__ == '__main__':
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Gestion', 'ArbolTecnologias', 'DefGrafos.def')
    log = []
    data = build(src, log=log)
    print('\n'.join(log)); print('ok, %d bytes' % len(data))

"""Imperial Glory 1789 - historical starting diplomacy + more active AI diplomacy.

Read-only on the game/mod tree. Writes, next to this script:
  diplomacy.json                      machine-readable proposal (source table + expanded per-file blocks)
  out/Game/GameModes/Gestion/...      drop-in replacement files with the same paths as inside the pak

Usage:
  python make_diplo1789.py                 # historical variant (default)
  python make_diplo1789.py --variant soft  # wars at turn 1 replaced by high hostility (no GUERRA)
  python make_diplo1789.py --lua           # also emit the optional Lua threshold patch
  python make_diplo1789.py --from-json     # regenerate out/ from an edited diplomacy.json

Format facts this relies on (see proposal.md for the evidence):
  * defsInicialesJugadores.sb / defsInicialesLocal{Easy,Medium,Hard}.sb:
      .JUG_A [ .JUG_B [ .HOSTILIDAD v .ESTADO_DIPLOMATICO [ .ESTADO X .TURNOS n ] ] ]
    X in {GUERRA, PROTECCION_MUTUA, PERMISO_PASO}; nothing else is parsed (FUN_0061bf90).
  * HOSTILIDAD is written to BOTH directions (FUN_00596d10 a,b and b,a) -> later blocks overwrite earlier
    ones, so every pair is written with the same value in both blocks (order independent).
  * GUERRA sets state 0 both ways. PROTECCION_MUTUA joins B to A *and all of A's current allies*
    (state 3 + turns). PERMISO_PASO sets record(A,B).turns in one direction only -> written in both blocks.
  * The human's own block comes from the Local<difficulty> file, every AI block from Jugadores ->
    all four files get identical content.
"""
import json, os, re, sys, struct, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
DATA = os.path.join(ROOT, 'data')
MOD = os.path.join(ROOT, 'mod')
OUT = os.path.join(HERE, 'out')
G = 'Game/GameModes/Gestion/'

# ------------------------------------------------------------------ players (mng table 0 order)
IMPERIAL = {'GRAN_BRETANYA', 'FRANCIA', 'AUSTRIA', 'PRUSIA', 'RUSIA'}   # original imperial five
RESKINS = {'HANNOVER': 'Kazakh Khanate', 'SAJONIA': 'Sahel Kingdoms', 'MOLDAVIA': 'Southern Kingdoms'}
PASSIVE = {'INDEPENDENT', 'PRINCES', 'SHEIKHS', 'NILE', 'PACIFIC', 'MOLDAVIA', 'SAJONIA'}   # regional independent peoples


def load_players():
    """Player keys in .mng table 0 order, from the mod tree that tools/make_map.py has just written (it runs this
    script after the .mng is in mod/). Fails loudly: no built-in fallback list, which could silently give the
    diplomacy files a wrong player set (review B3)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    from igmod import Mng
    path = os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng')
    if not os.path.exists(path):
        sys.exit('make_diplo1789: %s is missing. Run this from tools/make_map.py, after the mod .mng is written.' % path)
    m = Mng(open(path, 'rb').read())
    e = Mng.parse_enum(m.table(0))
    keys = [e[i][4:] for i in sorted(e)]
    if len(keys) <= 24 or 'INDEPENDENT' not in keys or not all(e[i].startswith('JUG_') for i in e):
        sys.exit('make_diplo1789: %s does not hold the 1789 player set (%d players: %s). Is the mod tree '
                 'mid-rebuild?' % (path, len(keys), ', '.join(keys)))
    return keys


# ------------------------------------------------------------------ the 1789 table
# Hostility 0..100, lower = friendlier (allies in the original files: 40-45, rivals 55-60).
# > = 90 is the game's "war situation" (DefReglasGenerales MISC.PORCENTAJE_HOSTILIDAD_SITUACION_GUERRA),
# so only GUERRA pairs go to 90+; everything else stays <= 88.
DEFAULT_HOSTILITY = 50.0
ISOLATED_DEFAULT = {'JAPAN': 65.0, 'ETHIOPIA': 58.0}   # sakoku / Zemene Mesafint (Joseon merged into Independent)

H = [
    # --- Atlantic & western Europe
    ('GRAN_BRETANYA', 'PORTUGAL', 30, 'Anglo-Portuguese Alliance (Windsor 1386, renewed 1703)'),
    ('GRAN_BRETANYA', 'PRUSIA', 35, 'Triple Alliance 1788'),
    ('GRAN_BRETANYA', 'BATAVIA', 35, 'Triple Alliance 1788; Orangist restoration 1787 backed by GB/Prussia'),
    ('PRUSIA', 'BATAVIA', 35, 'Triple Alliance 1788; Prussian invasion restored the Stadtholder 1787'),
    ('PRUSIA', 'PORTUGAL', 45, 'indirect (GB system)'),
    ('BATAVIA', 'PORTUGAL', 45, 'indirect (GB system)'),
    ('GRAN_BRETANYA', 'FRANCIA', 65, 'hereditary rivals; American war 1778-83'),
    ('GRAN_BRETANYA', 'ESPANYA', 65, 'Gibraltar; Nootka Sound crisis 1789-90'),
    ('GRAN_BRETANYA', 'RUSIA', 60, 'Armed Neutrality 1780; Ochakov crisis 1791'),
    ('GRAN_BRETANYA', 'AUSTRIA', 50, ''),
    ('GRAN_BRETANYA', 'OTOMANO', 50, 'GB+Prussia mediating for the Porte (Sistova/Jassy)'),
    ('GRAN_BRETANYA', 'DINAMARCA', 50, ''),
    ('GRAN_BRETANYA', 'SUECIA', 45, 'GB/Prussia forced Denmark out of the war on Sweden 1788'),
    ('GRAN_BRETANYA', 'DOS_SICILIAS', 45, 'Acton ministry leaned to Britain'),
    ('GRAN_BRETANYA', 'MARRUECOS', 45, 'Gibraltar supply treaties'),
    ('GRAN_BRETANYA', 'OMAN', 35, 'friendly trade; Anglo-Omani treaty 1798'),
    ('GRAN_BRETANYA', 'MYSORE', 85, 'Second Anglo-Mysore War 1780-84; Tipu attacks Travancore 29 Dec 1789 -> Third war 1790'),
    ('GRAN_BRETANYA', 'MARATHA', 45, 'Treaty of Salbai 1782; Marathas join GB against Tipu 1790'),
    ('GRAN_BRETANYA', 'QING', 50, 'Canton system trade; Macartney embassy 1793'),
    ('GRAN_BRETANYA', 'BURMA', 55, ''),
    ('GRAN_BRETANYA', 'DURRANI', 55, ''),
    ('GRAN_BRETANYA', 'PERSIA', 50, ''),
    ('GRAN_BRETANYA', 'JAPAN', 65, 'sakoku: only Dutch and Chinese admitted'),
    ('FRANCIA', 'ESPANYA', 30, 'Third Family Compact 1761 (Bourbon)'),
    ('FRANCIA', 'AUSTRIA', 40, 'Franco-Austrian alliance 1756, still formally in force (Marie-Antoinette)'),
    ('FRANCIA', 'PRUSIA', 55, ''),
    ('FRANCIA', 'RUSIA', 55, 'commercial treaty 1787'),
    ('FRANCIA', 'BATAVIA', 60, 'France abandoned the Dutch Patriots 1787'),
    ('FRANCIA', 'OTOMANO', 45, 'traditional Franco-Ottoman friendship'),
    ('FRANCIA', 'RHELVETICA', 40, 'Swiss regiments in French service; perpetual alliance'),
    ('FRANCIA', 'PIAMONTE', 50, ''),
    ('FRANCIA', 'SUECIA', 40, 'French subsidies to Gustav III'),
    ('FRANCIA', 'MYSORE', 40, "Tipu's embassy to Louis XVI 1788"),
    ('FRANCIA', 'VIETNAM', 60, 'Treaty of Versailles 1787 with Nguyen Anh, the Tay Son enemy'),
    ('FRANCIA', 'OMAN', 45, 'French trade at Muscat'),
    ('FRANCIA', 'EGIPTO', 55, ''),
    ('FRANCIA', 'PORTUGAL', 55, ''),
    ('ESPANYA', 'PORTUGAL', 45, 'San Ildefonso 1777 / El Pardo 1778'),
    ('ESPANYA', 'DOS_SICILIAS', 40, 'Bourbon cousins'),
    ('ESPANYA', 'EPAPALES', 45, ''),
    ('ESPANYA', 'MARRUECOS', 55, 'peace since 1780; Ceuta besieged again 1790-91'),
    ('ESPANYA', 'OTOMANO', 50, 'peace treaty 1782'),
    ('ESPANYA', 'BATAVIA', 50, ''),
    ('PORTUGAL', 'MARRUECOS', 50, ''),
    ('PORTUGAL', 'OMAN', 60, 'old rivalry over Muscat (expelled 1650)'),
    ('PORTUGAL', 'QING', 45, 'Macau'),
    ('PORTUGAL', 'MARATHA', 55, 'Bassein lost 1739'),
    ('PORTUGAL', 'ETHIOPIA', 45, '16th-century alliance'),
    ('PORTUGAL', 'JAPAN', 75, 'expelled 1639'),
    ('BATAVIA', 'JAPAN', 35, 'Dejima: the only European trade with Japan'),
    ('BATAVIA', 'QING', 45, 'Canton trade (VOC)'),
    ('BATAVIA', 'MYSORE', 55, ''),
    ('BATAVIA', 'OMAN', 50, ''),
    # --- Central / eastern Europe
    ('AUSTRIA', 'RUSIA', 30, 'Austro-Russian alliance 1781; joint war on the Ottomans'),
    ('AUSTRIA', 'PRUSIA', 70, 'Habsburg-Hohenzollern rivalry; Prussian mobilisation, Reichenbach 1790'),
    ('AUSTRIA', 'POLONIA', 50, ''),
    ('AUSTRIA', 'LOMBARDIA', 35, 'Austrian Lombardy (Habsburg possession)'),
    ('AUSTRIA', 'PIAMONTE', 50, ''),
    ('AUSTRIA', 'RHELVETICA', 45, 'neutral neighbour'),
    ('AUSTRIA', 'EPAPALES', 50, "Josephinism vs the Papacy"),
    ('AUSTRIA', 'DOS_SICILIAS', 40, 'Maria Carolina, sister of Joseph II'),
    ('AUSTRIA', 'SUECIA', 60, 'Sweden at war with Austria\'s ally'),
    ('PRUSIA', 'RUSIA', 65, 'Prussia backs Poland, Sweden and the Porte against Russia'),
    ('PRUSIA', 'POLONIA', 40, 'Polish-Prussian alliance March 1790'),
    ('PRUSIA', 'OTOMANO', 40, 'Prussian-Ottoman alliance January 1790'),
    ('PRUSIA', 'SUECIA', 40, ''),
    ('PRUSIA', 'DINAMARCA', 50, ''),
    ('RUSIA', 'POLONIA', 70, 'Great Sejm 1788-92 breaks with Russia'),
    ('RUSIA', 'DINAMARCA', 35, 'alliance 1773; Denmark attacked Sweden for Russia 1788'),
    ('RUSIA', 'SUECIA', 92, 'Russo-Swedish War 1788-90 (GUERRA)'),
    ('RUSIA', 'OTOMANO', 95, 'Russo-Turkish War 1787-92 (GUERRA)'),
    ('AUSTRIA', 'OTOMANO', 92, 'Austro-Turkish War 1788-91 (GUERRA)'),
    ('RUSIA', 'PERSIA', 75, 'Georgia under Russian protection (Georgievsk 1783)'),
    ('RUSIA', 'CHECHNYA', 88, "Sheikh Mansur's holy war 1785-91 (hostile, not at war: one-province nation)"),
    ('RUSIA', 'QING', 60, 'Kyakhta trade closed 1785-92'),
    ('RUSIA', 'HANNOVER', 60, 'Kazakh Junior Zhuz under nominal Russian suzerainty; Srym Datuly revolt 1783-97'),
    ('RUSIA', 'TURKESTAN', 55, ''),
    ('RUSIA', 'JAPAN', 70, 'Laxman mission 1792 refused'),
    ('RUSIA', 'FRANCIA', 55, ''),
    ('DINAMARCA', 'SUECIA', 70, 'Theatre War 1788 (armistice)'),
    ('DINAMARCA', 'QING', 45, 'Danish Asiatic Company at Canton'),
    ('SUECIA', 'OTOMANO', 30, 'Swedish-Ottoman alliance 11 July 1789'),
    ('SUECIA', 'QING', 45, 'Swedish East India Company at Canton'),
    ('SUECIA', 'POLONIA', 45, ''),
    ('POLONIA', 'OTOMANO', 45, 'common enemy Russia'),
    # --- Italy, Barbary, Egypt
    ('DOS_SICILIAS', 'EPAPALES', 60, 'Naples refuses the chinea tribute 1788'),
    ('DOS_SICILIAS', 'TUNEZ', 75, 'Barbary corsairs'),
    ('DOS_SICILIAS', 'TRIPOLITANIA', 70, 'Barbary corsairs'),
    ('EPAPALES', 'TUNEZ', 70, 'Barbary corsairs'),
    ('PIAMONTE', 'TUNEZ', 70, 'Sardinian coast raided'),
    ('PIAMONTE', 'LOMBARDIA', 55, ''),
    ('OTOMANO', 'EGIPTO', 40, 'Mamluk Egypt under Ottoman suzerainty; Ottoman expedition 1786'),
    ('OTOMANO', 'TUNEZ', 40, 'autonomous Ottoman regency'),
    ('OTOMANO', 'TRIPOLITANIA', 40, 'autonomous Ottoman regency (Karamanli)'),
    ('OTOMANO', 'MARRUECOS', 55, ''),
    ('OTOMANO', 'DOS_SICILIAS', 55, ''),
    ('OTOMANO', 'LOMBARDIA', 55, ''),
    ('OTOMANO', 'PERSIA', 60, 'Ottoman-Persian frontier wars'),
    ('OTOMANO', 'ARABIA', 75, 'Wahhabi First Saudi State defies the Porte'),
    ('OTOMANO', 'CHECHNYA', 25, 'Ottoman backing from 1787 via the Pashas of Anapa; joint operations 1788-91'),
    ('OTOMANO', 'ETHIOPIA', 65, 'Ottoman Massawa'),
    ('OTOMANO', 'MYSORE', 45, "Tipu's embassy to Istanbul 1787"),
    ('MARRUECOS', 'TUNEZ', 50, ''),
    ('TUNEZ', 'TRIPOLITANIA', 50, ''),
    ('EGIPTO', 'TRIPOLITANIA', 50, ''),
    ('EGIPTO', 'ARABIA', 60, 'Hejaz'),
    ('EGIPTO', 'ETHIOPIA', 55, ''),
    ('EGIPTO', 'GRAN_BRETANYA', 55, ''),
    # --- reskins (no 1799-era German/Moldavian values any more)
    ('HANNOVER', 'QING', 50, 'Ablai Khan paid tribute to Qing'),
    ('HANNOVER', 'TURKESTAN', 60, 'Kazakh-Kokand/Bukhara frontier'),
    # --- Middle East & Central Asia
    ('PERSIA', 'DURRANI', 65, 'Durrani protectorate over Khorasan'),
    ('PERSIA', 'TURKESTAN', 65, 'Bukhara took Merv 1785'),
    ('PERSIA', 'ARABIA', 60, ''),
    ('PERSIA', 'OMAN', 55, ''),
    ('PERSIA', 'CHECHNYA', 55, ''),
    ('PERSIA', 'FRANCIA', 50, ''),
    ('ARABIA', 'OMAN', 70, 'Wahhabi pressure on Oman'),
    ('ARABIA', 'GRAN_BRETANYA', 55, ''),
    ('TURKESTAN', 'DURRANI', 70, 'Balkh frontier war with Bukhara'),
    ('TURKESTAN', 'QING', 50, 'Kokand a nominal Qing tributary'),
    ('OMAN', 'ETHIOPIA', 55, ''),
    ('OMAN', 'MARATHA', 50, ''),
    ('OMAN', 'MYSORE', 45, 'Tipu-Muscat trade'),
    # --- India
    ('MARATHA', 'MYSORE', 80, 'Maratha-Mysore War 1785-87 (Gajendragad); Marathas join GB 1790'),
    ('MARATHA', 'DURRANI', 75, 'Panipat 1761; Mahadji Scindia holds Delhi 1788'),
    ('MARATHA', 'QING', 55, ''),
    ('MARATHA', 'FRANCIA', 50, ''),
    ('MARATHA', 'BURMA', 50, ''),
    ('MYSORE', 'DURRANI', 45, 'Tipu sought an Afghan alliance'),
    ('MYSORE', 'PORTUGAL', 55, ''),
    ('DURRANI', 'QING', 55, ''),
    # --- East & South-East Asia
    ('QING', 'JOSEON', 25, 'model tributary; Qing as protector'),
    ('QING', 'SIAM', 35, 'regular tributary of Rama I'),
    ('QING', 'VIETNAM', 45, 'Qing invasion defeated Jan 1789, Quang Trung invested as tributary king 1789'),
    ('QING', 'BURMA', 45, 'tribute resumed 1788-90 after the 1765-69 war'),
    ('QING', 'JAPAN', 55, 'Chinese junk trade at Nagasaki'),
    ('QING', 'FRANCIA', 50, 'Canton trade'),
    ('QING', 'ESPANYA', 50, 'Canton/Manila trade'),
    ('JAPAN', 'JOSEON', 45, 'Tsushima trade, Joseon embassies'),
    ('JOSEON', 'RUSIA', 60, ''),
    ('BURMA', 'SIAM', 80, 'Burmese-Siamese wars 1785-86, 1792'),
    ('SIAM', 'VIETNAM', 70, 'Siam backed Nguyen Anh; Rach Gam-Xoai Mut 1785'),
    ('VIETNAM', 'PORTUGAL', 50, ''),
    ('VIETNAM', 'ESPANYA', 55, ''),
    ('ETHIOPIA', 'GRAN_BRETANYA', 58, ''),
]

# Treaties. anchor = the block the ESTADO_DIPLOMATICO line is written in.
# PROTECCION_MUTUA: max 4 players per bloc (CFG_PROTECCION_MUTUA.MAX_JUGADORES), max 12 turns.
# PERMISO_PASO: max 8 turns (TURNOS_TRATADOS_DIPLOMATICOS) - written in both blocks (one-directional field).
T = [
    ('GRAN_BRETANYA', 'PORTUGAL', 'PROTECCION_MUTUA', 12, 'Anglo-Portuguese Alliance'),
    ('GRAN_BRETANYA', 'PRUSIA', 'PROTECCION_MUTUA', 12, 'Triple Alliance 1788'),
    ('GRAN_BRETANYA', 'BATAVIA', 'PROTECCION_MUTUA', 12, 'Triple Alliance 1788'),
    ('FRANCIA', 'ESPANYA', 'PROTECCION_MUTUA', 12, 'Family Compact'),
    ('RUSIA', 'AUSTRIA', 'PROTECCION_MUTUA', 12, 'Austro-Russian alliance 1781'),
    ('OTOMANO', 'SUECIA', 'PROTECCION_MUTUA', 12, 'Swedish-Ottoman treaty July 1789'),
    ('QING', 'JOSEON', 'PROTECCION_MUTUA', 12, 'tributary protection (closest game equivalent of vassalage)'),
    ('OTOMANO', 'EGIPTO', 'PERMISO_PASO', 8, 'Ottoman suzerainty over Egypt'),
    ('AUSTRIA', 'LOMBARDIA', 'PERMISO_PASO', 8, 'Habsburg Lombardy'),
    ('QING', 'SIAM', 'PERMISO_PASO', 8, 'tributary relation'),
    ('RUSIA', 'OTOMANO', 'GUERRA', 0, 'Russo-Turkish War 1787-92'),
    ('AUSTRIA', 'OTOMANO', 'GUERRA', 0, 'Austro-Turkish War 1788-91'),
    ('RUSIA', 'SUECIA', 'GUERRA', 0, 'Russo-Swedish War 1788-90'),
]
SOFT_WAR_HOSTILITY = 88.0   # --variant soft: GUERRA dropped, pair kept just under the war threshold


# ------------------------------------------------------------------ build the table
def parse_original(path, players):
    """Hostility pairs of the shipped file (first entry per block wins, later blocks overwrite)."""
    txt = open(path, 'rb').read().decode('latin1')
    txt = re.sub(r'#[^\n]*', '', txt)
    out = {}
    for m in re.finditer(r'^\.JUG_(\w+)\s*\[(.*?)^\]', txt, re.M | re.S):
        a, body = m.group(1), m.group(2)
        seen = set()
        for e in re.finditer(r'\.JUG_(\w+)\s*\[\s*\.HOSTILIDAD\s+([0-9.]+)', body):
            b, v = e.group(1), float(e.group(2))
            if b in seen or b == a:
                continue
            seen.add(b)
            out[frozenset((a, b))] = v
    return out


def build(variant, players):
    pairs = {}
    orig = parse_original(os.path.join(DATA, G, 'defsInicialesJugadores.sb'), players)
    for k, v in orig.items():
        if not (k & set(RESKINS)):
            pairs[k] = {'value': v, 'source': 'original'}
    for a, b, v, why in H:
        if a not in players or b not in players: continue   # nation merged into Independent Peoples
        assert a != b, (a, b)
        pairs[frozenset((a, b))] = {'value': float(v), 'source': '1789', 'why': why}
    treaties = []
    for a, b, est, turns, why in T:
        if a not in players or b not in players: continue
        if est == 'GUERRA' and variant == 'soft':
            pairs[frozenset((a, b))] = {'value': SOFT_WAR_HOSTILITY, 'source': '1789-soft', 'why': why + ' (soft: no war at turn 1)'}
            continue
        treaties.append({'anchor': a, 'other': b, 'estado': est, 'turnos': turns, 'why': why})
    # fill the rest
    for i, a in enumerate(players):
        for b in players[i + 1:]:
            k = frozenset((a, b))
            if k in pairs:
                continue
            v = DEFAULT_HOSTILITY
            for iso in (a, b):
                if iso in ISOLATED_DEFAULT:
                    v = max(v, ISOLATED_DEFAULT[iso])
            if a in PASSIVE or b in PASSIVE:
                v = DEFAULT_HOSTILITY
            pairs[k] = {'value': v, 'source': 'default'}
    validate(pairs, treaties, players)
    return pairs, treaties


def validate(pairs, treaties, players):
    wars = {frozenset((t['anchor'], t['other'])) for t in treaties if t['estado'] == 'GUERRA'}
    for k, p in pairs.items():
        v = p['value']
        assert 0.0 <= v <= 100.0
        if k in wars:
            assert v >= 90.0, ('war pair below 90', sorted(k), v)
        else:
            assert v < 90.0, ('non-war pair at war threshold', sorted(k), v)
        imp = k & IMPERIAL
        if len(imp) == 1 and v < 25.0:
            raise AssertionError(('imperial-neutral pair so friendly it invites peaceful annexation', sorted(k), v))
    # alliance blocs: union of PROTECCION_MUTUA edges, max 4 each, anchors must not chain blocs
    parent = {}
    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    for t in treaties:
        if t['estado'] == 'PROTECCION_MUTUA':
            assert t['turnos'] <= 12
            parent[find(t['other'])] = find(t['anchor'])
        if t['estado'] == 'PERMISO_PASO':
            assert t['turnos'] <= 8
    blocs = {}
    for x in list(parent) + [y for y in parent.values()]:
        blocs.setdefault(find(x), set()).add(x)
    for r, members in blocs.items():
        assert len(members) <= 4, ('alliance bloc larger than MAX_JUGADORES 4', members)
    for t in treaties:
        if t['estado'] == 'GUERRA':
            assert find(t['anchor']) != find(t['other']), ('war inside an alliance bloc', t)
    return blocs


def expand(pairs, treaties, players):
    """Per-file blocks exactly as written: {JUG_A: {JUG_B: {HOSTILIDAD, ESTADO_DIPLOMATICO?}}}."""
    blocks = {}
    for a in players:
        blk = {}
        for b in players:
            if a == b:
                continue
            e = {'HOSTILIDAD': pairs[frozenset((a, b))]['value']}
            for t in treaties:
                both = t['estado'] == 'PERMISO_PASO'
                if (t['anchor'] == a and t['other'] == b) or (both and t['anchor'] == b and t['other'] == a):
                    e['ESTADO_DIPLOMATICO'] = {'ESTADO': t['estado']}
                    if t['estado'] != 'GUERRA':
                        e['ESTADO_DIPLOMATICO']['TURNOS'] = t['turnos']
            blk['JUG_' + b] = e
        blocks['JUG_' + a] = blk
    return blocks


def render_defs(blocks, header):
    lines = [header.rstrip('\r\n'), '',
             '# Imperial Glory 1789: generated by build/diplo1789/make_diplo1789.py - every pair is written',
             '# in both blocks with the same HOSTILIDAD (the loader sets both directions, last block wins).', '']
    for a, blk in blocks.items():
        lines.append('.' + a)
        lines.append('[')
        w = max(len(b) for b in blk) + 1
        for b, e in blk.items():
            s = '  .%-*s [ .HOSTILIDAD %.1f' % (w, b, e['HOSTILIDAD'])
            if 'ESTADO_DIPLOMATICO' in e:
                d = e['ESTADO_DIPLOMATICO']
                s += ' .ESTADO_DIPLOMATICO [ .ESTADO %s%s ]' % (d['ESTADO'], (' .TURNOS %d' % d['TURNOS']) if 'TURNOS' in d else '')
            lines.append(s + ' ]')
        lines.append(']')
        lines.append('')
    return '\r\n'.join(lines) + '\r\n'


# ------------------------------------------------------------------ AI / rules edits (numbers only)
PRES = 'Game/GameModes/Gestion/IA/%s/IADefsPresidente.sb'
FACETS = ('MILITAR', 'ECONOMICO', 'DIPLOMATICO', 'TECNOLOGICO')
AI_PROFILES = {   # (MILITAR, ECONOMICO, DIPLOMATICO, TECNOLOGICO); old values in the comment
    'Default':    (0.32, 0.30, 0.38, 0.00),   # 0.40 0.35 0.25 0.00 - all neutrals and all 15 new nations
    'Inglaterra': (0.18, 0.30, 0.35, 0.17),   # 0.20 0.35 0.25 0.20
    'Francia':    (0.22, 0.28, 0.40, 0.10),   # 0.25 0.30 0.33 0.12
    'Austria':    (0.35, 0.20, 0.37, 0.08),   # 0.4  0.2  0.3  0.1
    'Prusia':     (0.33, 0.18, 0.32, 0.17),   # 0.35 0.20 0.25 0.20
    'Rusia':      (0.38, 0.26, 0.28, 0.08),   # 0.40 0.30 0.20 0.10
}
ISOLATED_PROFILE = (0.45, 0.45, 0.10, 0.00)   # new folder IA/Aislado: Japan, Joseon, Ethiopia
ISOLATED_NATIONS = ('JAPAN', 'JOSEON', 'ETHIOPIA')

DIPLO_MIN = 'Game/GameModes/Gestion/IA/Default/IADefsMinistroDiplomatico.sb'
DIPLO_MIN_EDITS = [   # (regex with the old value, new value)
    (r'(\.PERMISO_DE_PASO\s+)40\.0', '30.0'),
    (r'(\.MEJORA_RELACIONES\s+)300\.0', '200.0'),
    (r'(\.ALIANZA_DEFENSIVA\s+)40\.0', '25.0'),
    (r'(\.COALICION\s+)40\.0', '30.0'),
    (r'(\.PERMISO_DE_PASO\s+)200\b', '150'),
    (r'(\.MEJORA_RELACIONES\s+)500\b', '350'),
    (r'(\.ALIANZA_DEFENSIVA\s+)200\b', '150'),
    (r'(\.MODIFICADOR_POR_RELACION\s+)400\.0', '300.0'),
    (r'(\.NUMERO_RECHAZOS_PARA_BLOQUEO\s+)1\b', '2'),
    (r'(\.TURNOS_BASE_BLOQUEO\s+)6\b', '3'),
    (r'(\.MODIFICADOR_TURNOS_BLOQUEO\s+)1\.5', '1.25'),
    (r'(\.DURACION_MAXIMA_BLOQUEO\s+)30\b', '12'),
]
RULES = 'Game/GameModes/Gestion/Reglas/DefReglasGenerales.sb'
RULES_EDITS = [
    (r'(\.PERMISO_PASO\s+)0\.5\b', '1.5'),
    (r'(\.PROTECCION_MUTUA\s+)2\.5\b', '5.0'),
    (r'(\.TRATO_COMERCIAL_ESPECIAL\s+)0\.1\b', '1.0'),
]
TRADE = 'Game/GameModes/Gestion/Reglas/DefReglasComercio.sb'
TRADE_EDITS = [
    (r'(\.BONUS_AMISTAD_TURNO_RUTA_SIMPLE\s+)0\.0\b', '0.1'),
    (r'(\.BONUS_AMISTAD_TURNO_RUTA_DOBLE\s+)0\.0\b', '0.2'),
]
LUA = 'Game/LuaScripts/IA_Gestion/Iniciativas/Iniciativas_generate.lua'
LUA_EDITS = [
    (r'(\["alianza"\]\s*=\s*)0\.05', '0.02'),
    (r'(\["paz"\]\s*=\s*)0\.05', '0.03'),
    (r'(\["permiso_paso"\]\s*=\s*)0\.1\b', '0.05'),
]


def src(rel):
    for base in (MOD, DATA):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return open(p, 'rb').read()
    raise FileNotFoundError(rel)


def sub_all(raw, edits, rel):
    txt = raw.decode('latin1')
    for pat, new in edits:
        txt, n = re.subn(pat, lambda m: m.group(1) + new, txt, count=1)
        assert n == 1, ('pattern not found', rel, pat)
    return txt.encode('latin1')


def set_facets(raw, vals, rel):
    assert abs(sum(vals) - 1.0) < 1e-6, (rel, vals)
    edits = [(r'(\.PORCENTAJE_%s\s+)[0-9.]+' % f, '%.2f' % v) for f, v in zip(FACETS, vals)]
    return sub_all(raw, edits, rel)


def write(rel, data, written):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(data)
    written.append(rel)


def ai_files(written, with_lua):
    changes = {}
    for folder, vals in AI_PROFILES.items():
        rel = PRES % folder
        write(rel, set_facets(src(rel), vals, rel), written)
        changes[rel] = dict(zip(['PORCENTAJE_' + f for f in FACETS], vals))
    rel = PRES % 'Aislado'
    write(rel, set_facets(src(PRES % 'Default'), ISOLATED_PROFILE, rel), written)
    changes[rel] = dict(zip(['PORCENTAJE_' + f for f in FACETS], ISOLATED_PROFILE))
    rel = G + 'IA/IADefs.sb'
    txt = src(rel).decode('latin1')
    add = ''
    for n in ISOLATED_NATIONS:
        if re.search(r'^\.JUG_%s\b' % n, txt, re.M):
            continue
        add += ('\r\n.JUG_%s\r\n[\r\n'
                ' .DEFS_PRESIDENTE                   "Game/GameModes/Gestion/IA/Aislado/IADefsPresidente.sb"\r\n'
                ' .DEFS_MINISTRO_TECNOLOGICO         "Game/GameModes/Gestion/IA/Default/IADefsMinistroTecnologico.sb"\r\n'
                ' .DEFS_MINISTRO_ECONOMIA_INTERIOR   "Game/GameModes/Gestion/IA/Default/IADefsMinistroEconomiaInterior.sb"\r\n'
                ' .DEFS_MINISTRO_MILITAR             "Game/GameModes/Gestion/IA/Default/IADefsMinistroMilitar.sb"\r\n'
                ' .DEFS_MINISTRO_DIPLOMATICO         "Game/GameModes/Gestion/IA/Default/IADefsMinistroDiplomatico.sb"\r\n'
                ']\r\n') % n
    write(rel, (txt.rstrip('\r\n') + '\r\n' + add).encode('latin1'), written)
    changes[rel] = {'append_entries': ['JUG_' + n for n in ISOLATED_NATIONS], 'profile': PRES % 'Aislado'}
    for rel, edits in ((DIPLO_MIN, DIPLO_MIN_EDITS), (RULES, RULES_EDITS), (TRADE, TRADE_EDITS)) + (((LUA, LUA_EDITS),) if with_lua else ()):
        write(rel, sub_all(src(rel), edits, rel), written)
        changes[rel] = [{'pattern': p, 'new': v} for p, v in edits]
    return changes


# ------------------------------------------------------------------ main
def main():
    global MOD, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', choices=('historical', 'soft'), default='historical')
    ap.add_argument('--lua', action='store_true')
    ap.add_argument('--from-json', action='store_true')
    # make_map --public: read the public staging tree, write into build/public (the defaults are the father's build)
    ap.add_argument('--mod', default=MOD)
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--json', default=os.path.join(HERE, 'diplomacy.json'))
    a = ap.parse_args()
    MOD, OUT = a.mod, a.out
    players = load_players()
    jpath = a.json
    written = []
    if a.from_json:
        J = json.load(open(jpath, encoding='utf-8'))
        blocks = J['defsIniciales']['blocks']
    else:
        pairs, treaties = build(a.variant, players)
        blocks = expand(pairs, treaties, players)
    header = src(G + 'defsInicialesJugadores.sb').decode('latin1')
    header = header[:re.search(r'^\.JUG_', header, re.M).start()]
    body = render_defs(blocks, header).encode('latin1')
    files = [G + f for f in ('defsInicialesJugadores.sb', 'defsInicialesLocalEasy.sb',
                             'defsInicialesLocalMedium.sb', 'defsInicialesLocalHard.sb')]
    for rel in files:
        write(rel, body, written)
    global ISOLATED_NATIONS
    ISOLATED_NATIONS = tuple(n for n in ISOLATED_NATIONS if n in players)   # skip nations merged into Independent Peoples
    ai = ai_files(written, a.lua)
    if not a.from_json:
        J = {
            'meta': {'game': 'Imperial Glory (2005), 1789 mod', 'variant': a.variant,
                     'scale': 'HOSTILIDAD 0..100, lower = friendlier; >=90 = war situation',
                     'default_hostility': DEFAULT_HOSTILITY, 'isolated_default': ISOLATED_DEFAULT,
                     'player_order': ['JUG_' + p for p in players]},
            'defsIniciales': {
                'files': files,
                'format': '.JUG_A [ .JUG_B [ .HOSTILIDAD v .ESTADO_DIPLOMATICO [ .ESTADO GUERRA|PROTECCION_MUTUA|PERMISO_PASO .TURNOS n ] ] ]',
                'pairs': sorted(({'a': 'JUG_' + sorted(k)[0], 'b': 'JUG_' + sorted(k)[1], 'hostilidad': p['value'],
                                  'source': p['source'], **({'why': p['why']} if p.get('why') else {})}
                                 for k, p in pairs.items()), key=lambda d: (d['a'], d['b'])),
                'treaties': [{**t, 'anchor': 'JUG_' + t['anchor'], 'other': 'JUG_' + t['other']} for t in treaties],
                'blocks': blocks,
            },
            'ai_and_rules': ai,
        }
        json.dump(J, open(jpath, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('wrote %d files under %s' % (len(written), OUT))
    for r in written:
        print('  ' + r)


if __name__ == '__main__':
    main()

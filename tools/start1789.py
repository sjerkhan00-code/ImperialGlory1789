"""1789 start: province economy, starting armies and fleets (proposal data in build/start1789/, see its *.md).

Province vals (mng section 4): [gold, raw materials, food, population, science, commerce, 0 x 6, capital id, port id].
Armies (section 2 player records): province, '', '', officer troop type, 0, units [['', troop type, 0], ...] with
the officer as first unit; troop types are per country (troop record field 14). Fleets come from
Game/GameModes/Gestion/dbgDefFlotasIniciales.sb (one .JUG_x block per player, entries .NOMBRE/.PROVINCIA/.BARCO_INICIAL).
"""
import os, json, struct, collections, re
import igmod
from igmod import Mng, parse_players, pack_players, find_block

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'build', 'start1789')


def apply(m, world_pid, idx_of, reassign=None):
    """Province values and starting armies into the in-memory mng m. reassign {old player key: new player key}: the
    armies of a nation left out of the build go to the new owner of their province (make_map --public)."""
    recs = Mng.parse_provinces(m.section(4)); by_idx = {r['idx']: r for r in recs}; by_mesh = {r['name']: r for r in recs}
    vals = json.load(open(os.path.join(DIR, 'province_vals.json'), encoding='utf8'))
    n = 0
    for key, v in vals.items():
        if key not in world_pid:
            continue
        r = by_idx[idx_of[world_pid[key]]]
        science = v[4] if v[4] else r['vals'][4]
        r['vals'][:12] = list(v[:12]); r['vals'][4] = science
        n += 1
    Mng.set_provinces(m.section(4), recs)
    # armies
    penum = Mng.parse_enum(m.table(0))
    tenum = Mng.parse_enum(m.table(5))
    group = collections.defaultdict(dict)
    for rec in igmod.split_records(m.section(7), 'troop'):
        _, p = igmod.rec_strings(rec, 4)
        idx = struct.unpack_from('<I', rec, 0)[0]
        country = struct.unpack_from('<24I', rec, p)[14]
        group[country].setdefault(tenum[idx], idx)
    players = parse_players(m.section(2))
    by_key = {penum[p['idx']]: p for p in players}
    sym = json.load(open(os.path.join(DIR, 'armies_symbolic.json'), encoding='utf8'))
    for old, new in (reassign or {}).items():
        if old in sym:
            sym.setdefault(new, {'mode': 'append', 'armies': []})['armies'] += sym.pop(old)['armies']
    added, skipped = 0, []
    for pk, spec in sym.items():
        pl = by_key.get(pk)
        if pl is None:
            skipped.append(pk); continue
        g = group[pl['country']]
        new = []
        for a in spec['armies']:
            if a.get('existing'):
                continue
            mesh = a['mesh']
            if mesh not in by_mesh or any(u not in g for u in a['units']):
                skipped.append('%s:%s' % (pk, mesh)); continue
            new.append({'province': by_mesh[mesh]['idx'], 'name': '', 'officer_name': '', 'officer': g[a['officer']],
                        'zero': 0, 'units': [['', g[u], 0] for u in a['units']]})
        pl['armies'] = (pl['armies'] if spec['mode'] == 'append' else []) + new
        added += len(new)
    pack_players(m.section(2), players)
    print('  1789 start: %d province economies, %d armies added, skipped %s' % (n, added, skipped))


def fleets(src_text, players=None):
    """Original dbgDefFlotasIniciales.sb text + the 1789 fleets merged into one block per player."""
    add = open(os.path.join(DIR, 'dbgDefFlotasIniciales_1789.sb'), encoding='latin1').read()
    add = re.sub(r"^[ \t]*\.BARCOS\s*\[[^\]]*\][ \t]*\n", "", add, flags=re.M)   # extra-ship lists: never used in the original, syntax untested
    txt = src_text
    CR = '\r\n'
    for m0 in re.finditer(r'^\.(JUG_\w+)\s*$', add, re.M):
        a, b = find_block(add, m0.end())
        if players is not None and m0.group(1) not in players:
            continue                                    # nation not in the game (merged into Independent Peoples)
        inner = add[a + 1:b - 1].strip('\r\n')
        e = re.search(r'^\.%s\s*$' % m0.group(1), txt, re.M)
        if e:
            ta, tb = find_block(txt, e.end())
            txt = txt[:tb - 1] + inner.replace('\n', CR).replace('\r\r', '\r') + CR + txt[tb - 1:]
        else:
            txt = txt.rstrip() + CR + CR + add[m0.start():b].replace('\n', CR).replace('\r\r', '\r') + CR
    return txt

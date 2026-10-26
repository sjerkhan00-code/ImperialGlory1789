"""Consistency checks on the built mod tree (mod/), read-only. Run after tools/make_map.py:  python tools/validate_build.py
Exit code 1 if a check fails; WARN lines do not fail the run.
  (i) texts: the name, description and (troops) _SHORT tooltip key of every troop, building and tech record exist and are
      not blank in all 8 language text files of the tree (also with --public); gaps the original game has are ignored.
  --public  check the public (Nexus) build instead (make_map.py --public): build/public/mod, nations.py in its public
             variant, no save-prefix check (the public build needs a new campaign), plus check (h): no trace of the
             nations left out (nations.PUBLIC_DROP)."""
import os, re, sys, glob, collections, struct, zipfile, math, time
PUBLIC = '--public' in sys.argv[1:]
if PUBLIC:
    os.environ['IG_PUBLIC'] = '1'           # before nations.py is imported (check_playable, check_public)
else:
    os.environ.pop('IG_PUBLIC', None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igmod import Mng, parse_players, find_block, split_records, rec_strings, rs, V3D, v3d_objects
import world_nations as WN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, 'build', 'public', 'mod') if PUBLIC else os.path.join(ROOT, 'mod')
ORIG =[os.path.join(ROOT, 'data1'), os.path.join(ROOT, 'data')]      # extracted original paks, data1 overrides data
# the build installed in the game folder (read only): new builds must keep its mng ids so a running campaign loads
INSTALLED_PAK = os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Steam', 'steamapps',
                             'common', 'Imperial Glory', 'Data2.pak')
# the user's running campaign was saved with the 01:09 build of 2026-10-21: check against that one when it is kept
SAVE_REFERENCE = os.path.join(ROOT, 'backups', 'SAVE_REFERENCE_install_20261021-054604', 'Data2.pak')
if os.path.exists(SAVE_REFERENCE):
    INSTALLED_PAK = SAVE_REFERENCE
SAVE_RENAMES_OK = set()   # {(enum table, idx)}: deliberate renames that keep the id. Keep EMPTY: renaming enum keys is
                          # not save-safe (RE 2026-10-21: lookup fails, crash at 0x59a9a0)
DUP_ENUMS_OK = {(4, 'PUE_BATAVIA')}   # Java's port enum duplicates the Dutch one since the 01:09 build; kept for saves
# (4, 43): Java's port PUE_BATAVIA -> PUE_BATAVIA_JAVA (it repeated the Dutch port's name; ports.PORT_TAGS)
ENUM_NAMES = {0: 'players', 1: 'countries', 2: 'provinces', 3: 'capitals', 4: 'ports', 5: 'troops', 7: 'buildings',
              8: 'techs', 9: 'events', 12: 'officers', 13: 'ships'}
BS = chr(92)


def text_values(p):
    raw = open(p, 'rb').read()
    t = raw[2:].decode('utf-16-le') if raw[:2] == b'\xff\xfe' else raw.decode('latin1')
    return dict(re.findall(r'\.(LTEXT_\w+)\s+"([^"]*)"', t))


def game_file(rel, bases=None):
    """Path of a game file as the game resolves it (mod/ = Data2.pak over data1/ over data/), or None."""
    rel = rel.replace(BS, '/').strip('/')
    for b in (bases or [MOD] + ORIG):
        p = os.path.join(b, rel)
        if os.path.exists(p):
            return p
    return None


def enum_list(chunk):
    """[(idx, name)] of an mng enum table in file order."""
    p, out = 0, []
    for _ in range(chunk.cnt or 0):
        idx = struct.unpack_from('<I', chunk.body, p)[0]
        name, p = rs(chunk.body, p + 4)
        out.append((idx, name))
    return out


def troop_ids(m):
    """[(record id, troop enum name, country)] of mng section 7 in file order (saves store the record id)."""
    te = Mng.parse_enum(m.table(5))
    out = []
    for r in split_records(m.section(7), 'troop'):
        idx = struct.unpack_from('<I', r, 0)[0]
        _, p = rec_strings(r, 4)
        out.append((idx, te.get(idx), struct.unpack_from('<24I', r, p)[14]))
    return out


def port_seas(chunk):
    """{port id: own sea zones (ring 1)} of mng section 6 (format as tools/ports.py parse_ports)."""
    b, p, out = chunk.body, 0, {}
    for _ in range(chunk.cnt):
        idx = struct.unpack_from('<I', b, p)[0]
        _, p = rs(b, p + 4)
        _, p = rs(b, p)
        p += 4
        rings = []
        for _ in range(4):                            # nb, ring 1, ring 2, ring 3
            n = struct.unpack_from('<I', b, p)[0]
            rings.append(list(struct.unpack_from('<%dI' % n, b, p + 4))); p += 4 + 4 * n
        out[idx] = rings[1]
    assert p == len(b)
    return out


def check_connectivity(m, recs, fails):
    """(a) Every land province can reach every other one over land neighbours, sea zones and ports. The engine links
    land and sea only through ports: a land province's vals[13] is its port id, the port's ring 1 its sea zone."""
    seas = port_seas(m.section(6))
    g = collections.defaultdict(set)
    for pid, r in recs.items():
        for x in r['nb']:
            if x not in recs:
                fails.append(('neighbour list points at a missing province', r['name'], x))
            elif recs[x]['sea'] == r['sea']:
                g[pid].add(x)
        if not r['sea'] and r['vals'][13]:
            if r['vals'][13] not in seas:
                fails.append(('port id without port record', r['name'], r['vals'][13]))
                continue
            for z in seas[r['vals'][13]]:
                g[pid].add(z); g[z].add(pid)
    rg = collections.defaultdict(set)
    for a, s in list(g.items()):
        for b in s:
            rg[b].add(a)

    def reach(start, G):
        seen, todo = {start}, [start]
        while todo:
            for b in G[todo.pop()]:
                if b not in seen:
                    seen.add(b); todo.append(b)
        return seen
    land = sorted(p for p in recs if not recs[p]['sea'])
    # reference: the province joined both ways to the most land (the main world), so the report names the cut-off ones
    ref, fw, bw = max(((p, reach(p, g), reach(p, rg)) for p in land), key=lambda t: (len(t[1] & t[2]), -t[0]))
    import ports
    known = set() if ports.NZ_PORT else {'WNorthIsland', 'WSouthIsland'}   # ports.NZ_PORT: off until a new campaign
    to = sorted(recs[p]['name'] for p in land if p not in fw and recs[p]['name'] not in known)
    back = sorted(recs[p]['name'] for p in land if p not in bw and recs[p]['name'] not in known)
    if to or back:
        fails.append(('land provinces cut off from %s (no path over land, sea and ports; add a port or a neighbour)'
                      % recs[ref]['name'], 'unreachable: %s' % (to or '-'), 'cannot get back: %s' % (back or '-')))


def check_duplicate_enums(m, fails):
    """(b) Enum names must be unique in the provinces, capitals, ports and buildings tables (troop names repeat
    per nation by design)."""
    for t in (2, 3, 4, 7):
        dup = sorted(k for k, v in collections.Counter(n for _, n in enum_list(m.table(t))).items()
                     if v > 1 and (t, k) not in DUP_ENUMS_OK)
        if dup:
            fails.append(('duplicate enum names in mng table %d (%s)' % (t, ENUM_NAMES[t]), dup))


def check_save_compat(m, fails, warns):
    """(c) Every mng enum table and the troop record ids (section 7) must extend the INSTALLED build: same ids and
    names in the same order, new entries only at the end. Otherwise the user's running campaign breaks."""
    if not os.path.exists(INSTALLED_PAK):
        warns.append(('save compatibility not checked: no installed build', INSTALLED_PAK))
        return
    with zipfile.ZipFile(INSTALLED_PAK) as z:
        rel = next((n for n in z.namelist() if n.lower() == 'game/gamemodes/defmodelogestion.mng'), None)
        if rel is None:
            warns.append(('save compatibility not checked: the installed Data2.pak has no DefModeloGestion.mng',))
            return
        old = Mng(z.read(rel))
    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(INSTALLED_PAK)))

    def compare(what, a, b, same):
        bad = [i for i in range(len(a)) if i >= len(b) or not same(a[i], b[i])]
        if bad:
            i = bad[0]
            fails.append(('save compatibility: %s is not an extension of the installed build (%s)' % (what, when),
                          'first mismatch at position %d: installed %s, new %s' % (i, a[i], b[i] if i < len(b) else 'missing'),
                          '%d of %d installed entries differ' % (len(bad), len(a))))
    for co in old.chunks[:14]:
        if co.cnt is None:
            continue
        t = co.id
        compare('mng enum table %d (%s)' % (t, ENUM_NAMES.get(t, '?')), enum_list(co), enum_list(m.table(t)),
                lambda x, y, t=t: x == y or (x[0] == y[0] and (t, x[0]) in SAVE_RENAMES_OK))
    compare('troop records, mng section 7 (id, troop, country)', troop_ids(old), troop_ids(m), lambda x, y: x == y)


def check_unit_files(m, fails):
    """(d) DefTropas: every DEFTROPAS / DEFUNIDADES file and PATHTEX folder exists, and so does every model and texture
    that the unit file gives the troops a nation can raise (mng section 7), including their crew sub-units. Files may
    come from mod/ or the original paks. RANDOMTEX "X.dds" means X1.dds.. (one of three random variants)."""
    ce = Mng.parse_enum(m.table(1))
    used = collections.defaultdict(set)
    for idx, troop, country in troop_ids(m):
        used[ce.get(country)].add(troop)
    rel = 'Game/GameModes/Batalla/DefTropas.sb'
    dt = re.sub(r'#[^\n]*', '', open(game_file(rel), encoding='latin1').read())
    names, units_cache = set(), {}
    for blk in re.findall(r'\[(.*?)\]', dt, re.S):
        kv = dict(re.findall(r'\.(\w+)\s+"([^"]*)"', blk))
        name, pt = kv.get('NAME'), kv.get('PATHTEX', '')
        names.add(name)
        miss = ['%s %s' % (k, kv[k]) for k in ('DEFTROPAS', 'DEFUNIDADES') if kv.get(k) and not game_file(kv[k])]
        if pt and not game_file(pt):
            miss.append('PATHTEX folder ' + pt)
        uf = game_file(kv['DEFUNIDADES']) if kv.get('DEFUNIDADES') else None
        if uf:
            if uf not in units_cache:
                u = re.sub(r'#[^\n]*', '', open(uf, encoding='latin1').read())
                units = {}
                for mm in re.finditer(r'^\.(\w+)\s*\[', u, re.M):
                    a, b = find_block(u, mm.end() - 1)
                    body = u[a:b]
                    units[mm.group(1)] = (re.findall(r'\.(GRX|ANM|SHADOW|TEX2?|RANDOMTEX2?)\s+"([^"]*)"', body),
                                          re.findall(r'\.UNI\s+"(\w+)"', body))
                units_cache[uf] = units
            units = units_cache[uf]
            todo, seen = [t for t in used.get(name, ()) if t in units], set()
            while todo:                                   # troops of this nation + their crew sub-units (.UNI)
                t = todo.pop()
                if t in seen:
                    continue
                seen.add(t)
                refs, subs = units[t]
                for k, v in refs:
                    p = v if k in ('GRX', 'ANM', 'SHADOW') else pt + v
                    alt = '%s1%s' % os.path.splitext(p) if k.startswith('RANDOMTEX') else None
                    if not game_file(p) and not (alt and game_file(alt)):
                        miss.append('%s %s: %s' % (t, k, p))
                for s_ in subs:
                    if s_ in units:
                        todo.append(s_)
                    else:
                        miss.append('%s: crew unit %s not in %s' % (t, s_, kv['DEFUNIDADES']))
        if miss:
            fails.append(('DefTropas %s: missing unit files or textures' % name, len(miss), sorted(miss)[:8]))
    nob = sorted(c for c in used if c not in names)
    if nob:
        fails.append(('countries with troops but no DefTropas block', nob))


def check_playable(ps, pe, keys, fails):
    """(e) Every PLAYABLE nation (tools/nations.py) is a player, has a DefOrdenTurnos block (the turn order used when
    a human plays it) and a non-empty player 'info' key that exists in the English Select Empire texts."""
    try:
        import nations as NT
    except Exception as ex:
        fails.append(('playable nations not checked: tools/nations.py does not import', repr(ex)))
        return
    t = open(os.path.join(MOD, 'Game/GameModes/Gestion/DefOrdenTurnos.sb'), encoding='latin1').read()
    blocks = set(re.findall(r'^\.(JUG_\w+)\s*$', t, re.M))
    rel = 'Others/TextUIMainMenu.sb'
    tp = game_file(rel, [os.path.join(MOD, 'Texto', 'english'), os.path.join(ROOT, 'data1', 'Texto', 'english'),
                         os.path.join(ROOT, 'text', 'texto', 'english')])
    texts = text_values(tp) if tp else {}
    info = {pe[p['idx']]: p['info'] for p in ps}
    bad = collections.defaultdict(list)
    for k in NT.PLAYABLE:
        if k not in keys:
            bad['PLAYABLE nations that are not players in the mng'].append(k)
            continue
        if k not in blocks:
            bad['PLAYABLE nations without a DefOrdenTurnos block'].append(k)
        if not info[k]:
            bad["PLAYABLE nations with an empty player 'info' key (blank Select Empire panel)"].append(k)
        elif info[k] not in texts:
            bad["PLAYABLE nations whose 'info' key has no English text in " + rel].append('%s %s' % (k, info[k]))
    for what, l in bad.items():
        fails.append((what, l))


TEXT_LANGS = ('english', 'spanish', 'French', 'German', 'Italian', 'Polish', 'Czech', 'Russian')   # the 8 Texto/<dir> names
_TEXT_CACHE = {}


def lang_texts(lang, roots):
    """{LTEXT key: value} of the language dir `lang` as the game sees it: every .sb text file under the roots (mod Texto,
    data1 Texto, text.pak texto; the first root that has a file wins, by relative path), keys of all files merged. A key
    defined twice counts as filled when one definition is filled."""
    ck = (lang, tuple(roots))
    if ck not in _TEXT_CACHE:
        files = {}
        for r in roots:
            d = os.path.join(r, lang)
            for dp, _, fns in os.walk(d):
                for fn in fns:
                    if fn.lower().endswith('.sb'):
                        files.setdefault(os.path.relpath(os.path.join(dp, fn), d).replace(os.sep, '/').lower(),
                                         os.path.join(dp, fn))
        out = {}
        for p in files.values():
            for k, v in text_values(p).items():
                if k not in out or (not out[k].strip() and v.strip()):
                    out[k] = v
        _TEXT_CACHE[ck] = out
    return _TEXT_CACHE[ck]


def text_refs(m):
    """[(kind, enum name, name key, description key)] of every troop (mng section 7), building (section 9) and tech
    (section 10) record: strings 0 and 1 are the text keys the game shows. Tech record = idx, 2 strings, 48 bytes."""
    te, be, ae = (Mng.parse_enum(m.table(t)) for t in (5, 7, 8))
    out = []
    for r in split_records(m.section(7), 'troop'):
        s, _ = rec_strings(r, 4)
        out.append(('troop', te.get(struct.unpack_from('<I', r, 0)[0]), s[0], s[1]))
    for r in split_records(m.section(9), 'building'):
        s, _ = rec_strings(r, 3)
        out.append(('building', be.get(struct.unpack_from('<I', r, 0)[0]), s[0], s[1]))
    sec = m.section(10)
    b, p = sec.body, 0
    for _ in range(sec.cnt):
        idx = struct.unpack_from('<I', b, p)[0]
        nk, q = rs(b, p + 4)
        dk, q = rs(b, q)
        out.append(('tech', ae.get(idx), nk, dk))
        p = q + 48
    assert p == len(b), ('tech section length', p, len(b))
    return out


def text_gaps(refs, roots):
    """{(kind, role, key, language)} for every key the records point at that is missing or blank in a language. role:
    name, desc, and short (<description key>_SHORT, the tooltip text of troops and buildings; techs have none). An empty
    key in the record itself is a gap too ('(empty name key of ENUM)')."""
    gaps = set()
    for lang in TEXT_LANGS:
        K = lang_texts(lang, roots)
        for kind, name, nk, dk in refs:
            keys = [('name', nk), ('desc', dk)]
            if dk and kind in ('troop', 'building'):
                keys.append(('short', dk + '_SHORT'))
            for role, key in keys:
                if not key:
                    gaps.add((kind, role, '(empty %s key of %s)' % (role, name), lang))
                elif not K.get(key, '').strip():
                    gaps.add((kind, role, key, lang))
    return gaps


def check_texts(m, fails, warns):
    """(i) Every text key that a troop, building or tech record of the built mng points at exists and is not blank in all 8
    language text files of the built tree (Texto/<language> of the mod over data1 over text.pak): name and description
    (strings 0 and 1) of every record, plus <description key>_SHORT of every troop (the unit tooltip; blank without it).
    A missing _SHORT of a building is only a warning (the original wonders and capital buildings lack it too). A gap that
    the ORIGINAL game has as well (same key and language: the officers' LTEXT_MARISCAL_RED, the hidden dummy buildings,
    the capital buildings' _SHORT, ...) is not ours: it is counted, not reported."""
    roots = [os.path.join(MOD, 'Texto'), os.path.join(ROOT, 'data1', 'Texto'), os.path.join(ROOT, 'text', 'texto')]
    empty = [l for l in TEXT_LANGS if not lang_texts(l, roots)]
    if empty:
        fails.append(('text tree has no text files for these languages', empty))
    refs = text_refs(m)
    gaps = text_gaps(refs, roots)
    omng = game_file('Game/GameModes/DefModeloGestion.mng', ORIG)
    if omng:
        old = text_gaps(text_refs(Mng(open(omng, 'rb').read())), roots[1:])
    else:
        old = set()
        warns.append(('texts: no original DefModeloGestion.mng, gaps that the original game has are not told apart',))
    new = gaps - old
    cnt = collections.Counter(r[0] for r in refs)
    print('texts: %d troop, %d building, %d tech records x %d languages checked; %d gaps ignored (the original game has them too)'
          % (cnt['troop'], cnt['building'], cnt['tech'], len(TEXT_LANGS), len(gaps & old)))
    what = {'name': 'name key (string 0)', 'desc': 'description key (string 1)',
            'short': '_SHORT tooltip key (description key + _SHORT)'}
    for kind in ('troop', 'building', 'tech'):
        for role in ('name', 'desc', 'short'):
            sel = {g for g in new if g[0] == kind and g[1] == role}
            if not sel:
                continue
            per = collections.defaultdict(list)
            for _, _, key, lang in sel:
                per[key].append(lang)
            lines = ['%s [%s]' % (k, 'all %d languages' % len(v) if len(v) == len(TEXT_LANGS) else ', '.join(sorted(v)))
                     for k, v in sorted(per.items())]
            msg = ('texts: %s %s missing or empty' % (kind, what[role]), '%d keys, %d gaps' % (len(per), len(sel)),
                   lines[:12] + (['... %d more' % (len(lines) - 12)] if len(lines) > 12 else []))
            (warns if (kind == 'building' and role == 'short') else fails).append(msg)


def check_fog(warns):
    """(g) Fog Dummies must lie on their parent province mesh (MapaGestion.V3D), else they clear the fog somewhere
    else. Dummies that were already off their mesh in the original game are ignored, and so are the 'NieblaLago'
    points on no mesh within 2500 of their parent (lakes / sea gaps, meshgen.fog_hole_points). WARNING only."""
    def outside(path):
        d = open(path, 'rb').read()
        objs = v3d_objects(d)
        tris, trans = {}, {}
        for o, cid, size, name, par in objs:
            if cid == 0x2000:
                blob = d[o:o + size]
                f = V3D.mesh_fields(blob)
                tx, ty, tz = struct.unpack_from('<3f', blob, f['body'] + 128 + 48)
                trans[name] = (tx, tz)
                vs = [struct.unpack_from('<3f', blob, f['vdata'] + 28 * k) for k in range(f['nv'])]
                idx = struct.unpack_from('<%dH' % f['ni'], blob, f['ih'] + 16)
                L = []
                for k in range(0, f['ni'], 3):
                    tr = [(vs[i][0] + tx, vs[i][2] + tz) for i in idx[k:k + 3]]
                    xs, zs = [q[0] for q in tr], [q[1] for q in tr]
                    L.append((tr, min(xs), max(xs), min(zs), max(zs)))
                tris[name] = L

        def on_mesh(x, z, L, tol=1.0):
            for tr, x0, x1, z0, z1 in L:
                if x0 - tol <= x <= x1 + tol and z0 - tol <= z <= z1 + tol:
                    (ax, az), (bx, bz), (cx, cz) = tr
                    s = [(bx - ax) * (z - az) - (bz - az) * (x - ax), (cx - bx) * (z - bz) - (cz - bz) * (x - bx),
                         (ax - cx) * (z - cz) - (az - cz) * (x - cx)]
                    if min(s) >= 0 or max(s) <= 0:
                        return True
                    for (px, pz), (qx, qz) in ((tr[0], tr[1]), (tr[1], tr[2]), (tr[2], tr[0])):
                        dx, dz = qx - px, qz - pz
                        u = max(0.0, min(1.0, ((x - px) * dx + (z - pz) * dz) / ((dx * dx + dz * dz) or 1.0)))
                        if math.hypot(x - px - u * dx, z - pz - u * dz) <= tol:
                            return True
            return False
        out = set()
        for o, cid, size, name, par in objs:
            if cid == 0x5000 and par in tris:
                # the engine places a Dummy at parent mesh transform x Dummy matrix 3 (helper loader FUN_00471f30,
                # vtable 0x8b6800 +0x6c); the matrix-2 'world' copy is ignored (2026-10-23, ig-map-engineer)
                p = o + 20 + 2 + len(name) + 1 + 2 + len(par) + 1 + 128 + 48      # matrix 3 = offset from parent
                lx, ly, lz = struct.unpack_from('<3f', d, p)
                x, z = lx + trans[par][0], lz + trans[par][1]
                if not on_mesh(x, z, tris[par]):
                    # meshgen.fog_hole_points ('NieblaLago<n>'): a lake / sea-gap point on NO mesh near its parent
                    if name.startswith('NieblaLago') and not any(on_mesh(x, z, L) for L in tris.values()) and min(
                            math.hypot(x - q[0], z - q[1]) for tr in tris[par] for q in tr[0]) < 2500.0:
                        continue
                    out.add((par, name, round(x), round(z)))
        return out
    rel = 'Game/GameModes/Gestion/Mapa/MapaGestion.V3D'
    new = outside(os.path.join(MOD, rel))
    bad = new - outside(game_file(rel, ORIG))
    if bad:
        per = collections.Counter(b[0] for b in bad)
        warns.append(('fog Dummies outside their parent province mesh (%d)' % len(bad),
                      ', '.join('%s %d' % kv for kv in per.most_common())))


def check_public(m, keys, ce, recs, cs, fails):
    """(h) --public: nothing of the nations left out of the public build (nations.PUBLIC_DROP) remains: no player or
    country, no file of their own (model / figure folders, unit file, flag, welcome picture, troop icons, AI graph) and no
    key of theirs in a text, UI, script or database file. Their provinces stay on the map, each with an owner."""
    import nations as NT
    sys.path.insert(0, os.path.join(ROOT, 'tools', 'art', 'units'))
    import cultures as CU
    drop = NT.PUBLIC_DROP
    left = [k for k in drop if 'JUG_' + k in keys or k in ce.values()]
    if left:
        fails.append(('public: left-out nations are still players or countries', left))
    pre = Mng.parse_enum(m.table(2))
    owner = {p: ce.get(c) for c in cs for p in cs[c]['provs']}
    for idx, k in sorted(pre.items()):
        if k in drop:
            print('public: province %s (idx %d, mesh %s) owner %s' % (k, idx, recs[idx]['name'], owner.get(idx)))
    print('public: %d players, %d playable (nations.PLAYABLE)' % (len(keys), len(NT.PLAYABLE)))
    units = {CU.RECIPES[k]['units'] for k in drop if k in CU.RECIPES} - set(CU.UNIT_FILE_OF.values())
    folders = {nn['folder'] for nn in NT.PUBLIC_DROPPED}
    tok = re.compile('|'.join(p % k for k in drop for p in (
        r'JUG_%s', r'\bBANDERA_(?:ICONO_)?%s\b', r'\b%s_[A-Z_]+?_(?:IMG|BTN)', r'\.NAME\s+"%s"', r'\.%s_(?:NAVIO|FRAGATA|CORBETA)\b',
        r'\.DESC\s+%s\b', r'\bCAP_%s\b', r'\bCAPITAL_BASE_%s\b', r'VentanaInfo/%s/')))
    bad_files, bad_text = [], collections.defaultdict(set)
    for dp, dns, fns in os.walk(MOD):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, MOD).replace(os.sep, '/')
            parts = rel.split('/')
            if (any(f in parts for f in folders) or fn in units or tok.search(rel)
                    or any(fn.lower() == ('NotificacionInicio%s.tga' % k.title()).lower() or rel.lower() == 'models/banderas/%s.tga' % k.lower()
                           for k in drop)):
                bad_files.append(rel)
            if os.path.splitext(fn)[1].lower() not in ('.sb', '.lua', '.def', '.txt', '.mng', '.ini'):
                continue
            raw = open(p, 'rb').read()
            t = raw[2:].decode('utf-16-le', 'replace') if raw[:2] == b'\xff\xfe' else raw.decode('latin1')
            for mm in tok.finditer(t):
                bad_text[rel].add(mm.group(0))
            for k in set(re.findall(r'LTEXT_\w+', t)):
                if NT.public_drops_text(k):
                    bad_text[rel].add(k)
    if bad_files:
        fails.append(('public: files of left-out nations in the tree', len(bad_files), sorted(bad_files)[:8]))
    if bad_text:
        fails.append(('public: keys of left-out nations in %d files' % len(bad_text),
                      sorted('%s: %s' % (r, sorted(v)[:4]) for r, v in bad_text.items())[:8]))


def check_historical_events(fails, warns):
    """Scripted historical events (make_map.HISTORICAL_EVENTS, tools/historical_events.py): only checked when the built tree
    holds them; then Lua balance, the .SECUENCIA_TUTORIAL path, and the text keys in all 8 languages."""
    # the exe built together with this tree (exe patches 48-50 exist only with HISTORICAL_EVENTS = True): hook and native names
    exe = os.path.join(ROOT, 'build', 'public' if PUBLIC else '', 'ImperialGlory_ModNations.exe')
    names = [b'eh_inicio_turno\0', b'get_turno_actual\0', b'firma_paz_entre\0']
    try:
        import nations as NT_
        if not getattr(NT_, 'HIST_PEACE_NATIVE', True):
            names = names[:2]               # patch 50 switched off: the Lua guards firma_paz_entre
    except Exception:
        pass
    have = None
    if os.path.exists(exe):
        raw = open(exe, 'rb').read()
        have = [n for n in names if n in raw]
    if not os.path.exists(os.path.join(MOD, 'Game', 'LuaScripts', 'Secuencias', 'EventosHistoricos1789.lua')):
        print('historical events: not in this build (make_map.HISTORICAL_EVENTS = False)')
        ui = open(os.path.join(MOD, 'Game/UI/ModeloGestion/UI_ModeloGestion.sb'), 'rb').read().decode('latin1')
        if 'SecuenciaTutorialGestion.lua' not in ui:
            fails.append(('.SECUENCIA_TUTORIAL no longer points at the original tutorial script, events not built',))
        if have:
            warns.append('historical events: the exe holds the patch 48-50 names %s but the tree has no events (stale exe?)' % have)
        return
    import historical_events as HE
    HE.validate_tree(MOD, fails, warns)
    if have is None:
        warns.append('historical events: %s not found, exe patches 48-50 not checked' % exe)
    elif have != names:
        fails.append(('historical events: the exe lacks the patch 48-50 names (built with HISTORICAL_EVENTS = False?)',
                      [n[:-1].decode() for n in names if n not in have]))
    print('historical events: %d events checked' % len(HE.EVENTS))


def main():
    fails = []
    m = Mng(open(os.path.join(MOD, 'Game/GameModes/DefModeloGestion.mng'), 'rb').read())
    pe = Mng.parse_enum(m.table(0)); ce = Mng.parse_enum(m.table(1))
    recs = {r['idx']: r for r in Mng.parse_provinces(m.section(4))}
    cs = {c['idx']: c for c in Mng.parse_countries(m.section(3))}
    ps = parse_players(m.section(2))
    owner = {p: c for c in cs for p in cs[c]['provs'] if ce.get(c) != 'PLIBREDUMMY'}
    keys = [pe[p['idx']] for p in ps]
    print('players', len(ps))
    # provinces
    land = [r for r in recs.values() if not r['sea']]
    unowned = [r['name'] for r in land if r['idx'] not in owner]
    if unowned: fails.append(('land without owner', unowned))
    dup = [k for k, v in collections.Counter(r['scenario'] for r in recs.values()).items() if v > 1]
    if dup: fails.append(('duplicate battle scenario ids', dup))
    # players
    for p in ps:
        k = pe[p['idx']]; c = cs[p['country']]
        caps = [q for q in c['provs'] if recs[q]['vals'][12]]
        if len(caps) != 1: fails.append((k, 'capitals', [recs[q]['name'] for q in caps]))
        if not c['lists'][0]: fails.append((k, 'no neighbour countries'))
        for a in p['armies']:
            if owner.get(a['province']) != p['country']:
                fails.append((k, 'army outside own land', recs[a['province']]['name']))
        quays = {(o[0], o[3]) for o in p['objects'] if len(o) > 3}
        for q in c['provs']:
            if recs[q]['vals'][13] and (33, q) not in quays:
                fails.append((k, 'port without quay', recs[q]['name']))
    # turn order: every block lists every player once
    t = open(os.path.join(MOD, 'Game/GameModes/Gestion/DefOrdenTurnos.sb'), encoding='latin1').read()
    for mm in re.finditer(r'^\.(JUG_\w+)\s*$', t, re.M):
        a, b = find_block(t, mm.end()); l = re.findall(r'JUG_\w+', t[a:b])
        if len(l) != len(set(l)) or set(l) | {mm.group(1)} != set(keys):
            fails.append(('turn order block', mm.group(1)))
    # diplomacy: one block per player
    t = open(os.path.join(MOD, 'Game/GameModes/Gestion/defsInicialesJugadores.sb'), encoding='latin1').read()
    tops = set('JUG_' + x for x in re.findall(r'^\.JUG_(\w+)', t, re.M))
    if tops != set(keys): fails.append(('diplomacy blocks', sorted(tops ^ set(keys))))
    # AI graphs
    graphs = {os.path.basename(f)[5:-4] for f in glob.glob(os.path.join(MOD, 'Game/GameModes/Gestion/IA/Datos_Precalculados/Graph*.GRF'))}
    if not set(keys) <= graphs: fails.append(('missing AI graphs', sorted(set(keys) - graphs)))
    # (f) removed nations (all merged into the regional peoples, world_nations.MERGED): no player keys or IA entries left
    iad = open(os.path.join(MOD, 'Game/GameModes/Gestion/IA/IADefs.sb'), encoding='latin1').read()
    left = [n for n in WN.MERGED if re.search(r'\bJUG_%s\b' % n, iad) or 'JUG_' + n in keys]
    if left: fails.append(('removed nations still referenced', left))
    # (a)-(e), (g); a crashing check is reported as a failure and the others still run
    warns = []
    checks = [('connectivity through ports', lambda: check_connectivity(m, recs, fails)),
              ('duplicate enum names', lambda: check_duplicate_enums(m, fails)),
              ('save compatibility with the installed build', lambda: check_save_compat(m, fails, warns)),
              ('DefTropas unit files and textures', lambda: check_unit_files(m, fails)),
              ('playable nations', lambda: check_playable(ps, pe, keys, fails)),
              ('text keys of troops, buildings and techs', lambda: check_texts(m, fails, warns)),
              ('fog Dummies on their mesh', lambda: check_fog(warns)),
              ('scripted historical events (only when built)', lambda: check_historical_events(fails, warns))]
    if PUBLIC:                  # a new campaign is required: no save-prefix check; (h) instead
        print('public build %s: save compatibility not checked (new campaign)' % MOD)
        checks = [c for c in checks if not c[0].startswith('save compatibility')]
        checks.append(('public: left-out nations', lambda: check_public(m, keys, ce, recs, cs, fails)))
    for what, fn in checks:
        try:
            fn()
        except Exception as ex:
            fails.append(('check crashed: ' + what, repr(ex)))
    # texts: every player/country has a name in every language
    for lang in sorted(os.listdir(os.path.join(MOD, 'Texto'))):
        pj = os.path.join(MOD, 'Texto', lang, 'Management', 'TextJugadores.sb')
        if os.path.exists(pj):
            v = text_values(pj)
            miss = [k for k in keys if 'LTEXT_JUGADOR_' + k[4:] not in v]
            if miss: fails.append((lang, 'player names missing', miss))
    for w in warns:
        print('WARN', w)
    for f in fails:
        print('FAIL', f)
    print(('OK' if not fails else '%d problems' % len(fails)) + (' (%d warnings)' % len(warns) if warns else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())

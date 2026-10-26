"""New battlefields for the new regions: registry and the make_map build step (behind make_map.NEW_BATTLE_MAPS).

Each new map is generated beforehand into build/battlemaps/<folder>/ (a mirror of
Game/GameModes/Batalla/Escenarios/<folder>/: the .lvl, Models/, Camara.sb, Clima.sb, intro Lua) plus
build/battlemaps/minimap[_red]/<file>.tga and a battlemap.json:
    tools/lvl_caucasus.py   -> "93"          scenario "93" (Chechenya), template 51 Republica Helvetica
    tools/lvl_region.py     -> "NBDesierto"  Arabian desert, template 58 Tripolitania
                               "NBIndia"     Indian river plain, template 41 Venecia
                               "NBEstepa"    Central Asian steppe, template 42 Egipto
                               "NBArrozal"   East Asian rice country, template 44 Piamonte
                               "NBJapon"     Japanese valley with a castle, template 16 Hungria
                               "NBSabana"    African savanna, template 28 Alentejo
                               "NBTaiga"     Siberian taiga, template 21 Kiev
                               "NBSelva"     tropical jungle, template 02 Escocia (+ palms of 57 Tunez)
                               "NBTundra"    Arctic tundra, template 39 Finlandia (+ the frozen lake of 17 Minsk)
A map is used by
  - 'scenario': one scenario name whose folder it is (the Caucasus: "93");
  - 'provinces': province enum keys. ONE map serves MANY provinces: each province keeps its own scenario name
    (str(idx), make_map) and that name's .MAPA points at the shared .lvl, so the pak holds the map once.
    make_map passes {scenario name: province key} with bind() before the patch functions run.

What the step changes (data only; save-safe: no mng record, enum or id changes, the province records keep their
scenario-name strings):
  - Escenarios.sb: .MAPA of every scenario name that uses a map -> Game\\GameModes\\Batalla\\Escenarios\\<folder>\\<lvl>;
  - UIDefs_MinBattleMapInfo.sb: those names show the new minimap (and the map's minimap rotation);
  - UIDefs_PoolBitmapEscenario.sb: ESCENARIO_RED_<province key> = the network-game minimap; ESCENARIO_<province key>
    (quick-game picture) = the picture of an original province whose map looks alike ('preview_key');
  - objective texts: objective_key(province key) names the original province whose LTEXT_OBJETIVOS_* match the
    map's victory conditions; make_map.map_key borrows them in all 8 languages for the province's mesh key;
  - copies each map folder and its minimaps into mod/ once; adds the intro texts (new LTEXT keys) to
    Battle/TextUISecuencias.sb in every language (English until translated; Russian via build/i18n as usual).
"""
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BM = os.path.join(ROOT, 'build', 'battlemaps')
SCEN_DIR = 'Game/GameModes/Batalla/Escenarios/'
MINIMAP_DIR = 'Game/UI/ModeloBatalla/MinBattleMap/'
_BOUND = {}                    # scenario name -> province key (from make_map, see bind)
# generated maps not yet tested in game: built by lvl_region.py but left out of the pak until a Quick Game test passes
UNTESTED = set()   # NBSelva and NBTundra were held back on 2026-10-22 (no in-game test possible); Quick Game test 2026-10-23


def maps():
    """{folder: battlemap.json dict} of every generated map (folder = 'folder' or, for the Caucasus, 'scenario')."""
    out = {}
    if not os.path.isdir(BM):
        return out
    for d in sorted(os.listdir(BM)):
        p = os.path.join(BM, d, 'battlemap.json')
        if os.path.exists(p):
            info = json.load(open(p, encoding='utf8'))
            info.setdefault('folder', info.get('scenario', d))
            if info['folder'] in UNTESTED:
                continue
            if os.path.exists(os.path.join(BM, d, info['lvl'])):
                out[info['folder']] = info
    by_prov = {}
    for f, info in out.items():
        for k in info.get('provinces', []):
            assert k not in by_prov, 'province %s on two new maps (%s, %s)' % (k, by_prov[k], f)
            by_prov[k] = f
    return out


def bind(scen_prov):
    """make_map: {scenario name: province enum key} of the land provinces (before the patch functions)."""
    _BOUND.clear()
    _BOUND.update(scen_prov)


def map_of_province(key):
    return next((info for info in maps().values() if key in info.get('provinces', [])), None)


def objective_key(key):
    """Original province whose objective texts fit the new map of province `key` (None: not on a new map)."""
    info = map_of_province(key)
    return info.get('objective_key') if info else None


def targets(only=None):
    """[(scenario name, info)] of every scenario name that fights on a new map."""
    out = []
    ms = maps()
    for f, info in ms.items():
        if only is not None and f not in only:
            continue
        if info.get('scenario'):
            out.append((info['scenario'], info))
        provs = set(info.get('provinces', []))
        out += [(sid, info) for sid, key in sorted(_BOUND.items()) if key in provs and sid != info.get('scenario')]
    return out


def mapa_path(info):
    return 'Game\\GameModes\\Batalla\\Escenarios\\%s\\%s' % (info['folder'], info['lvl'])


def patch_escenarios(txt, only=None):
    """Point the .MAPA of each scenario name on a new map at its .lvl (Escenarios.sb text, latin1 str)."""
    for scen, info in targets(only):
        pat = re.compile(r'(\.NAME\s+"%s"\s+\.MAPA\s+)"[^"]+"' % re.escape(scen))
        assert pat.search(txt), 'scenario %s missing from Escenarios.sb' % scen
        txt = pat.sub(lambda m_: m_.group(1) + '"%s"' % mapa_path(info), txt, count=1)
    return txt


def patch_minimap_info(txt, only=None):
    """Show the new minimap (and its rotation) for each scenario name on a new map (UIDefs_MinBattleMapInfo.sb)."""
    from igmod import find_block
    for scen, info in targets(only):
        blk = find_block(txt, txt.index('.ESCENARIOS'))               # the engine only reads entries in here
        m = re.search(r'\[\s*\.NAME\s+"%s"\s*\.IMG\s*\[\s*\.FILE\s+"([^"]+)"' % re.escape(scen), txt)
        assert m, 'scenario %s missing from UIDefs_MinBattleMapInfo.sb' % scen
        assert blk[0] < m.start() < blk[1], 'minimap entry %s is outside the .ESCENARIOS block' % scen
        new = 'Game\\UI\\ModeloBatalla\\MinBattleMap\\' + info['minimap']
        txt = txt[:m.start(1)] + new + txt[m.end(1):]
        if info.get('rotacion'):
            r = re.compile(r'(\.ROTACION\s*\[)[^\]]*(\])')
            mr = r.search(txt, m.start())
            nxt = re.search(r'\.NAME\s+"', txt[m.end():])
            if mr and (nxt is None or mr.start() < m.end() + nxt.start()):
                txt = txt[:mr.start()] + mr.group(1) + ' %s ' % info['rotacion'] + mr.group(2) + txt[mr.end():]
    return txt


def patch_pool(txt, only=None):
    """UIDefs_PoolBitmapEscenario.sb: per province of a new map, ESCENARIO_RED_<key> shows the map's network-game
    minimap (Game/UI/Comun/Minimapas/<minimap_red>) and ESCENARIO_<key> the quick-game picture of preview_key."""
    for f, info in maps().items():
        if only is not None and f not in only:
            continue
        keys = ([info['pool_key']] if info.get('pool_key') else []) + list(info.get('provinces', []))
        pv = None
        if info.get('preview_key'):
            mp = re.search(r'\.KEY\s+ESCENARIO_%s\s+\.PARAMS\s*(\[[^\]]*\])' % re.escape(info['preview_key']), txt)
            pv = mp.group(1) if mp else None
        for k in keys:
            if info.get('minimap_red'):
                m = re.search(r'\.KEY\s+ESCENARIO_RED_%s\s+\.PARAMS\s*\[\s*\.FILE\s+"([^"]+)"' % re.escape(k), txt)
                if m:
                    txt = txt[:m.start(1)] + 'Game/UI/Comun/Minimapas/' + info['minimap_red'] + txt[m.end(1):]
            if pv and k != info.get('pool_key'):
                m = re.search(r'(\.KEY\s+ESCENARIO_%s\s+\.PARAMS\s*)(\[[^\]]*\])' % re.escape(k), txt)
                if m:
                    txt = txt[:m.start(2)] + pv + txt[m.end(2):]
    return txt


def install(mod, langs, src_text, read, out, text_add_entries, only=None):
    """Copy the map folders and minimaps into mod/ and add the intro texts. Returns the folders done."""
    done = []
    texts = []
    for f, info in maps().items():
        if only is not None and f not in only:
            continue
        src = os.path.join(BM, f)
        for dp, dns, fns in os.walk(src):
            for fn in fns:
                if fn == 'battlemap.json':
                    continue
                rel = os.path.relpath(os.path.join(dp, fn), src).replace(os.sep, '/')
                p = os.path.join(mod, SCEN_DIR + info['folder'], rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                shutil.copyfile(os.path.join(dp, fn), p)
        mm = os.path.join(BM, 'minimap', info['minimap'])
        p = os.path.join(mod, MINIMAP_DIR + info['minimap'])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(mm, p)
        if info.get('minimap_red'):
            p = os.path.join(mod, 'Game/UI/Comun/Minimapas/' + info['minimap_red'])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            shutil.copyfile(os.path.join(BM, 'minimap_red', info['minimap_red']), p)
        texts += sorted(info.get('texts', {}).items())
        done.append(f)
    if texts:
        frel = 'Battle/TextUISecuencias.sb'
        for lang in langs:
            pm = os.path.join(mod, 'Texto', lang, frel)
            raw = open(pm, 'rb').read() if os.path.exists(pm) else read(src_text(lang, frel))
            have = raw.decode('utf-16-le', 'ignore') if raw[:2] == bytes([0xff, 0xfe]) else raw.decode('latin1')
            add = [(k, v) for k, v in texts if '.' + k not in have]
            if add:
                out('Texto/%s/%s' % (lang, frel), text_add_entries(raw, add))
    print('  new battle maps:', done)
    for f, info in maps().items():
        sids = [s for s, i in targets() if i['folder'] == f]
        print('    %-11s %-16s %d scenario names: %s' % (f, info['lvl'], len(sids), ' '.join(sids)))
    return done

"""Build Data2.pak adding one test province (Fezzan) to the campaign map.

Nothing in data/, data1/ or text/ is modified; all outputs go to mod/ and build/.
"""
import sys, os, shutil, struct, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from igmod import *

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, DATA1, TEXT = [os.path.join(ROOT, d) for d in ('data', 'data1', 'text')]
MOD, BUILD = os.path.join(ROOT, 'mod'), os.path.join(ROOT, 'build')
BK = os.path.join(ROOT, 'backups', time.strftime('%Y%m%d-%H%M%S'))

# ------------------------------------------------------------------ the province
NAME, DISP, IDX = 'FEZZAN', 'Fezzan', 83
OWNER = 'LTEXT_PAIS_FRANCIA'          # test owner so the player can see it (was LTEXT_PAIS_TRIPOLITANIA)
NEIGHBOURS = ['TRIPOLITANIA', 'MARRUECOS', 'TUNEZ']
PRODUCTION = [20, 50, 25, 25, 0, 25]          # same as Cyrenaica
SCENARIO = '43'                               # Cyrenaica desert battlefield
BOX = (700.0, -800.0, 3400.0, 1550.0)         # world x, y(south edge), width, height
LIFT = 4.0                                    # raise above the background map, which has land here (stops z-fighting)
TEXTS = {
    'Management/TextProvincias.sb': [('LTEXT_PROVINCIA_' + NAME, DISP)],
    'Management/TextDescripcionesProvincias.sb': [('LTEXT_DESC_' + NAME,
        'A harsh desert of oases and caravan routes south of Tripoli. (Test province added by the map mod.)')],
    'Others/TextUIObjetivos.sb': [('LTEXT_OBJETIVOS_ATACANTE_' + NAME, 'Total Victory'),
                                  ('LTEXT_OBJETIVOS_DEFENSOR_' + NAME, 'Total Victory')],
    'Battle/TextUIBatallaVentanaInicioBatalla.sb': [('LTEXT_UI_BATALLA_INITVENT_%s_TITLE' % NAME, NAME),
                                                     ('LTEXT_UI_BATALLA_INITVENT_%s_TEXT' % NAME, 'What are your orders?')],
}
LANGS = ['english', 'spanish', 'French', 'German', 'Italian', 'Polish', 'Czech', 'Russian']
UI_MAPS = ['Game/UI/Comun/UIDefs_MapaPaises.sb',
           'Game/UI/MainMenu/UIDefs_MapaPaisesSelectEmpire.sb',
           'Game/UI/MainMenu/SelectEmpire/UIDefs_MapaPaisesSelectEmpire.sb',
           'Game/UI/MainMenu/UIDefs_MapaPaisesSelectEscenario.sb',
           'Game/UI/ModeloGestion/Diplomacia/UIDefs_MapaPaisesSeleccion.sb']
UI_INITVENT = 'Game/UI/ModeloBatalla/UIDefs_VentanaInicioBatallaInfoProvConflictos.sb'

# ------------------------------------------------------------------ helpers
def src(rel):
    """Pick the patched (data1) copy when it exists, else the base one."""
    for base in (DATA1, DATA):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)

def src_text(lang, rel):
    p = os.path.join(DATA1, 'Texto', lang, rel)
    if os.path.exists(p):
        return p
    return os.path.join(TEXT, 'texto', lang, rel)

def read(path):
    bk = os.path.join(BK, os.path.relpath(path, ROOT))
    os.makedirs(os.path.dirname(bk), exist_ok=True)
    shutil.copy2(path, bk)
    with open(path, 'rb') as f:
        return f.read()

def out(rel, data):
    p = os.path.join(MOD, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data)
    print('  wrote', rel, len(data), 'bytes')

# ------------------------------------------------------------------ build
def main():
    if os.path.exists(MOD):
        shutil.rmtree(MOD)
    os.makedirs(BUILD, exist_ok=True)
    cx, cz = BOX[0] + BOX[2] / 2, BOX[1] + BOX[3] / 2

    # --- campaign database
    rel = 'Game/GameModes/DefModeloGestion.mng'
    m = Mng(read(src(rel)))
    enum = Mng.parse_enum(m.table(2))
    byname = {v: k for k, v in enum.items()}
    assert IDX not in enum and NAME not in byname
    Mng.enum_add(m.table(2), IDX, NAME)

    recs = Mng.parse_provinces(m.section(4))
    tmpl = next(r for r in recs if r['ltext'] == 'LTEXT_PROVINCIA_CIRENAICA')
    nb = [byname[n] for n in NEIGHBOURS]
    new = dict(tmpl, idx=IDX, ltext='LTEXT_PROVINCIA_' + NAME, ldesc='LTEXT_DESC_' + NAME,
               vals=PRODUCTION + [0] * 6 + [0, 0], name=DISP, scenario=SCENARIO, sea=0, f=1.5, nb=nb)
    for r in recs:
        if r['idx'] in nb:
            r['nb'].append(IDX)
    recs.append(new)
    Mng.set_provinces(m.section(4), recs)

    cs = Mng.parse_countries(m.section(3))
    owner = next(c for c in cs if c['ltext'] == OWNER)
    owner['provs'].append(IDX)
    Mng.set_countries(m.section(3), cs)

    pos = m.section(13)
    y = -0.0147
    Mng.add_position(pos, 59, IDX, cx - 300, y, cz)
    Mng.add_position(pos, 93, IDX, cx + 300, y, cz)
    out(rel, m.pack())

    # --- click masks
    rel = 'Game/GameModes/Gestion/Mapa/PosicionesMapa.gp'
    g = Gp(read(src(rel)))
    g.add(DISP, *BOX, shape=lambda u, v: abs(2 * u - 1) ** 4 + abs(2 * v - 1) ** 4 <= 1.0)
    out(rel, g.pack())

    # --- province mesh in both map models: the selection/colour volumes and the visible
    # terrain (the province record names its mesh in both; a missing one crashes the campaign)
    for rel in ('Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D',
                'Game/GameModes/Gestion/Mapa/MapaGestion.V3D'):
        v = V3D(read(src(rel)))
        st, en, _ = v.block('Cirenaica')
        f = V3D.mesh_fields(bytes(v.d[st:en]))
        bb = struct.unpack_from('<6f', v.d, st + f['body'] + 208)
        sx, sz = BOX[2] / (bb[3] - bb[0]), BOX[3] / (bb[5] - bb[2])
        tx, tz = BOX[0] - bb[0] * sx, BOX[1] - bb[2] * sz
        nv, nt = v.clone_mesh('Cirenaica', DISP, tx, tz, sx, sz, LIFT)
        print('  %s mesh: %d verts %d tris, scale %.3f x %.3f, placed at %.0f,%.0f'
              % (rel.split('/')[-1], nv, nt, sx, sz, tx, tz))
        if rel.endswith('/MapaGestion.V3D'):
            n = clone_fog_dummies(v, 'Cirenaica', DISP, tx, tz, sx, sz, LIFT, 900)
            print('  fog points copied:', n)
        out(rel, v.pack())

    # --- localisation
    for lang in LANGS:
        for frel, entries in TEXTS.items():
            p = src_text(lang, frel)
            if not os.path.exists(p):
                print('  !! missing', p); continue
            out('Texto/%s/%s' % (lang, frel), text_add_entries(read(p), entries))

    # --- 2D maps in the UI (copy Cyrenaica's entry with the new index)
    for rel in UI_MAPS:
        p = src(rel)
        txt = read(p).decode('latin1')
        m0 = re.search(r'^[ \t]*#-+ CIRENAICA -+.*$', txt, re.M)
        if not m0:
            print('  !! no CIRENAICA block in', rel); continue
        a, b = find_block(txt, m0.end())
        unit = txt[m0.start():b]
        unit = unit.replace('CIRENAICA', NAME)
        unit = re.sub(r'\.IDX\s+30\b', '.IDX %d' % IDX, unit)
        txt = txt[:b] + '\r\n\r\n' + unit + txt[b:]
        out(rel, txt.encode('latin1'))

    p = src(UI_INITVENT)
    txt = read(p).decode('latin1')
    m0 = re.search(r'^\.CIRENAICA[ \t]*\r?\n', txt, re.M)
    a, b = find_block(txt, m0.end())
    unit = txt[m0.start():b].replace('CIRENAICA', NAME)
    txt = txt[:b] + '\r\n\r\n' + unit + txt[b:]
    out(UI_INITVENT, txt.encode('latin1'))

    # --- pack
    pak = os.path.join(BUILD, 'Data2.pak')
    write_pak(pak, MOD)
    print('built', pak, os.path.getsize(pak), 'bytes; backups in', BK)

if __name__ == '__main__':
    main()

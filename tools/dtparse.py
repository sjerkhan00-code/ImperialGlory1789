"""Parser and writer for Imperial Glory's combat tables (*.dt).

Files
  Game/GameModes/ModeloCombate.dt                                   real-time battle (data1/ overrides data/)
  Game/GameModes/Gestion/CombateAutomatico/ModeloCombateAutomatico.dt   auto-resolve (same format; the game falls
                                                                    back to the battle table when it is missing)

Format (Pyro's own loader, svcModeloCombate::init, github.com/chnickiz/Imperial-Glory/sourceloaderdt):
  u32 version (130).  version >= 120 -> 5 rank blocks (else 1).  Each rank block holds, in this order,
  tables {u32 typeId, u32 rows, u32 structSize, rows x struct}:
     0 infantry  TDescTropa        6 x 176      5 inf formation TModifFormacion  10 x 92
     1 cavalry   TDescTropa        7 x 176      6 cav formation TModifFormacion  10 x 92
     2 artillery TDescTropa        6 x 176      7 inf charge-vs-square TCargasVsCuadro 1 x 20   (v >= 110)
     3 inf damage TDescDanTropa    9 x 108      8 cav charge-vs-square TCargasVsCuadro 1 x 20   (v >= 110)
     4 cav damage TDescDanTropa    8 x 108      9 charge properties TCargasPropiedades 2 x 80 (v >= 110)
                                               10 artillery damage TInfoDanArtilleria 6 x 80 (v >= 120)
  Damage tables are per CLASS, not per troop type: rows are soldier-count bands (m_Soldados, descending);
  getDescDan picks the band and linearly interpolates melee/charge between bands.

Troop type mask -> table row (exe FUN_0058f480 class, FUN_0058f320 inf, FUN_0058f3b0 cav, FUN_0058f420 art):
  officers (mask & 0x3c0000) use the FUSILERO infantry row.

Usage
  python tools/dtparse.py              round-trip test + write build/dt_dump.txt
  python tools/dtparse.py test         round-trip test only
  python tools/dtparse.py panel        info-panel values (defence / ranged / melee / range) per type, rank 0..4
  API: d = Dt.load(path); d.ranks[r].inf[i]['uResCue'] = 40; open(out, 'wb').write(d.pack())
"""
import os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

BATTLE_REL = 'Game/GameModes/ModeloCombate.dt'
AUTO_REL = 'Game/GameModes/Gestion/CombateAutomatico/ModeloCombateAutomatico.dt'
MNG_REL = 'Game/GameModes/DefModeloGestion.mng'


def orig_path(rel):
    """data1/ overrides data/ (pak order)."""
    for base in ('data1', 'data'):
        p = os.path.join(ROOT, base, rel)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(rel)


# ---------------------------------------------------------------- struct specs (Pyro CommonData.h, pack 4)
# (name, struct code[, count]); Pyro's UINT counters that are percentages are read signed for readability
TDescTropa = [
    ('uValTropa', 'I'), ('uUnidades', 'I'), ('VidaTotal', 'i'), ('VidaActual', 'i'),
    ('uResDis', 'i'), ('uResCar', 'i'), ('uResCue', 'i'),          # resistance % vs ranged / charge / melee
    ('uTieRec', 'I'),                                              # reload time
    ('fRngDet', 'f'),                                              # detection range (cm)
    ('fRngDis1', 'f'), ('fRngDis2', 'f'), ('fRngDis3', 'f'),       # firing ranges (cm)
    ('uPrecDis1', 'i'), ('uPrecDis2', 'i'), ('uPrecDis3', 'i'),    # accuracy % per range
    ('uPrecCue', 'i'), ('uPrecCar', 'i'),                          # melee / charge accuracy %
    ('fVelNor', 'f'), ('fVelForColumna', 'f'), ('fVelCor', 'f'), ('fVelCar', 'f'),
    ('SepNormal_x', 'f'), ('SepNormal_y', 'f'), ('SepExpandida_x', 'f'), ('SepExpandida_y', 'f'),
    ('unused', 'I'),
    ('uFlagsAccionesDisponiblesIniciales', 'I'), ('uFlagsAccionesDisponibles', 'I'),
    ('uModDanDis', 'i'), ('uModDanCar', 'i'), ('uModDanCue', 'i'),  # damage modifiers %
    ('fVelForLinea', 'f'), ('fVelForCuadro', 'f'),
    ('fGastoResistPorSegundo', 'f'), ('fGananciaResistPorSegundo', 'f'),   # stamina loss / gain per s
    ('fDuracionFatiga', 'f'), ('fPenalizacionMelee', 'f'),
    ('Placeholder', 'f', 7),
]
TDescDanTropa = [
    ('Soldados', 'i'),
    ('DisRng1_Min', 'i'), ('DisRng1_Max', 'i'), ('DisRng2_Min', 'i'), ('DisRng2_Max', 'i'),
    ('DisRng3_Min', 'i'), ('DisRng3_Max', 'i'),
    ('Cue_Min', 'i'), ('Cue_Max', 'i'), ('Car_Min', 'i'), ('Car_Max', 'i'),
    ('Placeholder', 'f', 16),
]
TModifFormacion = [
    ('ResDis', 'i'), ('ResCar', 'i'), ('ResCue', 'i'), ('DanDis', 'i'), ('DanCar', 'i'), ('DanCue', 'i'),
    ('Vel', 'i'), ('Placeholder', 'f', 16),
]
TCargasVsCuadro = [('MultVsNovata', 'f'), ('MultVsMedia', 'f'), ('MultVsExperimentada', 'f'),
                   ('MultVsVeterana', 'f'), ('MultVsElite', 'f')]
TCargasPropiedades = [('DistMin', 'f'), ('DistMax', 'f'), ('MultNumUnidadesReq_AtaqueDist', 'f'),
                      ('MultNumUnidadesReq_Carga', 'f'), ('Placeholder', 'f', 16)]
TInfoDanArtilleria = [('DamageRng1', 'I'), ('DamageRng2', 'I'), ('DamageRng3', 'I'), ('PrecisionVsEdif', 'f'),
                      ('Cue_Min', 'i'), ('Cue_Max', 'i'), ('Placeholder', 'f', 14)]


def _fmt(spec):
    return '<' + ''.join('%d%s' % (s[2], s[1]) if len(s) > 2 else s[1] for s in spec)


# typeId -> (TTT name, attribute on Rank, spec, row names)
RANKS = ['NOVATO', 'MEDIO', 'EXPERIMENTADO', 'VETERANO', 'ELITE']
INF_ROWS = ['MILICIA', 'FUSILERO', 'TIRADOR', 'CAZADOR', 'GRANADERO', 'ELITE']            # FUN_0058f320
CAV_ROWS = ['CAB_HUSAR', 'CAB_LANCERO', 'CAB_DRAGON', 'CAB_CORACERO', 'CAM_TIRADOR', 'CAM_LANCERO',
            'CAB_ELITE']                                                                   # FUN_0058f3b0
ART_ROWS = ['MORTERO', 'CANON', 'OBUS', 'CANON_CAB', 'OBUS_CAB', 'CANON_CAMP']              # FUN_0058f420
FORM_ROWS = ['NULL', 'LINEA_SIMPLE', 'LINEA_DOBLE', 'LINEA_TRIPLE', 'COLUMNA', 'CUADRO', 'CARGA', 'MELEE',
             'HUIDA', 'APOSTADO']                                                          # eModifFormacion
CHARGE_ROWS = ['INFANTERIA', 'CABALLERIA']                                                 # CT_* index
TABLES = {
    0: ('TTT_INFANTERIA', 'inf', TDescTropa, INF_ROWS),
    1: ('TTT_CABALLERIA', 'cav', TDescTropa, CAV_ROWS),
    2: ('TTT_ARTILLERIA', 'art', TDescTropa, ART_ROWS),
    3: ('TTT_DAN_INFANTERIA', 'dan_inf', TDescDanTropa, None),
    4: ('TTT_DAN_CABALLERIA', 'dan_cav', TDescDanTropa, None),
    5: ('TTT_MODIF_FORM_INFANTERIA', 'form_inf', TModifFormacion, FORM_ROWS),
    6: ('TTT_MODIF_FORM_CABALLERIA', 'form_cav', TModifFormacion, FORM_ROWS),
    7: ('TTT_CARGAS_CUADRO_INF', 'sq_inf', TCargasVsCuadro, None),
    8: ('TTT_CARGAS_CUADRO_CAB', 'sq_cav', TCargasVsCuadro, None),
    9: ('TTT_CARGAS_PROPIEDADES', 'charge', TCargasPropiedades, CHARGE_ROWS),
    10: ('TTT_INFO_DAN_ARTILLERIA', 'art_dan', TInfoDanArtilleria, ART_ROWS),
}
CLASS_ATTR = {0: 'inf', 1: 'cav', 2: 'art'}
# uFlagsAccionesDisponibles bits (exe: ranged FUN_00591290/FUN_00590210, melee FUN_00590930, charge in the
# battle-AI max scan that also reads uPrecCar)
F_RANGED, F_MELEE, F_CHARGE = 0x40, 0x80, 0x100

# troop type masks (mng section-7 int 0); names are confirmed against the mng by mask_names()
MASKS = {0x1: 'FUSILERO', 0x2: 'TIRADOR', 0x4: 'CAZADOR', 0x8: 'GRANADERO', 0x10: 'MILICIA', 0x20: 'ELITE',
         0x80: 'CAB_HUSAR', 0x100: 'CAB_LANCERO', 0x200: 'CAB_DRAGON', 0x400: 'CAB_CORACERO',
         0x800: 'CAM_TIRADOR', 0x400000: 'CAM_LANCERO', 0x800000: 'CAB_ELITE',
         0x1000: 'MORTERO', 0x2000: 'CANON', 0x4000: 'OBUS', 0x8000: 'CANON_CAB', 0x10000: 'OBUS_CAB',
         0x20000: 'CANON_CAMP',
         0x40000: 'TENIENTE', 0x80000: 'CAPITAN', 0x100000: 'GENERAL', 0x200000: 'MARISCAL'}
OFFICERS = 0x3c0000


def mask_class_row(mask):
    """(class 0 inf / 1 cav / 2 art, row) exactly as the exe maps an eTipoTropa mask."""
    if mask & OFFICERS or mask & 0x3f:                       # FUN_0058f480
        cls = 0
    elif mask & 0xc00f80:
        cls = 1
    elif mask & 0x3f000:
        cls = 2
    else:
        return None
    if cls == 0:                                             # FUN_0058f320
        if mask & OFFICERS:
            return 0, 1
        return 0, {0x2: 2, 0x4: 3, 0x8: 4, 0x10: 0, 0x20: 5}.get(mask, 1)
    if cls == 1:                                             # FUN_0058f3b0
        return 1, {0x100: 1, 0x200: 2, 0x400: 3, 0x800: 4, 0x400000: 5, 0x800000: 6}.get(mask, 0)
    return 2, {0x2000: 1, 0x4000: 2, 0x8000: 3, 0x10000: 4, 0x20000: 5}.get(mask, 0)   # FUN_0058f420


def mask_names(mng_path=None):
    """{type mask: name} from the mng troop records: section 7 int 0 = mask, enum table 5 = record name."""
    from igmod import Mng, split_records, rec_strings
    m = Mng(open(mng_path or orig_path(MNG_REL), 'rb').read())
    names = Mng.parse_enum(m.table(5))
    out = {}
    for r in split_records(m.section(7), 'troop'):
        idx = struct.unpack_from('<I', r, 0)[0]
        _, p = rec_strings(r, 4)
        mask = struct.unpack_from('<i', r, p)[0]
        nm = names.get(idx, '?')
        cnt = out.setdefault(mask, {})
        cnt[nm] = cnt.get(nm, 0) + 1
    # most common name per mask (one CAB_LANCERO record carries the CAM_LANCERO mask, MARISCAL_RED shares 0x200000)
    return {k: max(v.items(), key=lambda kv: (kv[1], -len(kv[0])))[0] for k, v in out.items()}


# ---------------------------------------------------------------- tables
class Table:
    def __init__(self, tid, size, rows, raw_rows=None):
        self.tid, self.size, self.rows, self.raw_rows = tid, size, rows, raw_rows

    @property
    def spec(self):
        t = TABLES.get(self.tid)
        return t[2] if t and struct.calcsize(_fmt(t[2])) == self.size else None

    @classmethod
    def read(cls, d, p):
        tid, n, size = struct.unpack_from('<3I', d, p); p += 12
        t = cls(tid, size, [], None)
        spec = t.spec
        if spec is None:                                     # unknown table: keep raw bytes
            t.raw_rows = [bytes(d[p + i * size:p + (i + 1) * size]) for i in range(n)]
        else:
            fmt = _fmt(spec)
            for i in range(n):
                vals = list(struct.unpack_from(fmt, d, p + i * size))
                row, k = {}, 0
                for s in spec:
                    if len(s) > 2:
                        row[s[0]] = vals[k:k + s[2]]; k += s[2]
                    else:
                        row[s[0]] = vals[k]; k += 1
                t.rows.append(row)
        return t, p + n * size

    def pack(self):
        if self.raw_rows is not None:
            return struct.pack('<3I', self.tid, len(self.raw_rows), self.size) + b''.join(self.raw_rows)
        spec, fmt = self.spec, _fmt(self.spec)
        out = [struct.pack('<3I', self.tid, len(self.rows), self.size)]
        for row in self.rows:
            vals = []
            for s in spec:
                v = row[s[0]]
                if len(s) > 2:
                    assert len(v) == s[2], (s[0], len(v)); vals.extend(v)
                else:
                    vals.append(v)
            out.append(struct.pack(fmt, *vals))
        return b''.join(out)

    def __len__(self):
        return len(self.rows) if self.raw_rows is None else len(self.raw_rows)

    def __getitem__(self, i):
        return self.rows[i]


class Rank:
    def __init__(self, tables):
        self.tables = tables
        for t in tables:
            if t.tid in TABLES:
                setattr(self, TABLES[t.tid][1], t)


class Dt:
    def __init__(self, data):
        d = bytes(data)
        self.version = struct.unpack_from('<I', d, 0)[0]
        p = 4
        n_ranks = len(RANKS) if self.version >= 120 else 1
        n_tables = 7 + (3 if self.version >= 110 else 0) + (1 if self.version >= 120 else 0)
        self.ranks = []
        for _ in range(n_ranks):
            tabs = []
            for _ in range(n_tables):
                t, p = Table.read(d, p); tabs.append(t)
            self.ranks.append(Rank(tabs))
        self.trailer = d[p:]                                 # nothing in the shipped files

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read())

    def pack(self):
        return (struct.pack('<I', self.version) + b''.join(t.pack() for r in self.ranks for t in r.tables)
                + self.trailer)

    def troop(self, mask, rank=0):
        cls, row = mask_class_row(mask)
        return getattr(self.ranks[rank], CLASS_ATTR[cls])[row]

    # --- info-panel values, as the RETAIL exe computes them (Pyro's 2003 source truncates; the 2005 exe ROUNDs):
    #     management army panel FUN_007f3780 shows WTDE defence FUN_00590580, WTCA melee FUN_00590930,
    #     WTPU ranged FUN_00591290, WTRA range FUN_00590210; maxima at model +0x70c8/cc/d0/d4 (FUN_005902d0 etc.)
    def desc_dan(self, cls, soldiers, rank):
        """getDescDan (FUN_00590610): soldier band, melee/charge interpolated from the band above."""
        tab = (self.ranks[rank].dan_inf if cls == 0 else self.ranks[rank].dan_cav).rows
        i = 0
        while i < len(tab) and soldiers < tab[i]['Soldados']:
            i += 1
        if i >= len(tab):
            return dict(tab[-1])
        r = dict(tab[i])
        if i <= 0 or r['Soldados'] == soldiers:
            return r
        prev = tab[i - 1]
        f = (soldiers - r['Soldados']) / (prev['Soldados'] - r['Soldados'])
        for k in ('Car_Min', 'Car_Max', 'Cue_Min', 'Cue_Max'):
            r[k] = round(f * prev[k] + (1.0 - f) * r[k])
        r['Soldados'] = soldiers
        return r

    def _form(self, cls, rank, name):
        t = self.ranks[rank].form_inf if cls == 0 else self.ranks[rank].form_cav
        return t[FORM_ROWS.index(name)]

    def _prom_dis(self, dan, p1, p2, p3, mod, cls, rank):        # FUN_00590390
        pd = int((dan['DisRng1_Max'] + dan['DisRng2_Max'] + dan['DisRng3_Max']) / 3)
        pd += self._form(cls, rank, 'LINEA_SIMPLE')['DanDis']
        pp = (p1 + p2 + p3) / 3
        if pp == 0.0 and pd > 0:
            pp = 0.1
        return max(0, round(pd * pp + pd * mod))

    def _prom_cac(self, dan, prec, mod, cls, rank):              # FUN_00590450
        pd = dan['Cue_Max'] + self._form(cls, rank, 'LINEA_SIMPLE')['DanCue'] + self._form(cls, rank, 'MELEE')['DanCue']
        if prec == 0.0 and pd > 0:
            prec = 0.1
        return max(0, round(pd * prec + pd * mod))

    def panel_max(self):
        """(defence, ranged, melee, artillery) 100% values. Like the exe, the defence max only scans rows 0..5 of
        each class (cavalry row 6 CAB_ELITE is skipped)."""
        arm = max(t[j]['uResDis'] + t[j]['uResCue'] + t[j]['uResCar']
                  for r in self.ranks for t in (r.inf, r.cav, r.art) for j in range(len(INF_ROWS)))
        dis = cac = 0
        for i, r in enumerate(self.ranks):
            for cls, tab in ((0, r.dan_inf), (1, r.dan_cav)):
                for dan in tab.rows:
                    dis = max(dis, self._prom_dis(dan, 1.0, 1.0, 1.0, 1.0, cls, i))
                    cac = max(cac, self._prom_cac(dan, 1.0, 1.0, cls, i))
        art = max(round((a['DamageRng1'] + a['DamageRng2'] + a['DamageRng3']) // 3)
                  for r in self.ranks for a in r.art_dan.rows)
        return arm, dis, cac, art

    def panel(self, mask, rank=0, units=None):
        """{'defence','ranged','melee','range'} as the info panel shows them (0 = bar/field empty)."""
        cls, row = mask_class_row(mask)
        t = self.troop(mask, rank)
        arm, dis, cac, art = self.panel_max()
        flags = t['uFlagsAccionesDisponibles']
        n = units or t['uUnidades']
        out = {'defence': round((t['uResDis'] + t['uResCar'] + t['uResCue']) * (100.0 / arm)),
               'range': round(t['fRngDis3'] * 0.01) if (flags & F_RANGED or cls == 2) else 0,
               'ranged': 0, 'melee': 0}
        if flags & F_RANGED:
            if cls == 2:                                          # FUN_00590f60 / FUN_0058f6d0
                ad = self.ranks[rank].art_dan[row]
                pd = (ad['DamageRng1'] + ad['DamageRng2'] + ad['DamageRng3']) // 3
                pp = (t['uPrecDis1'] + t['uPrecDis2'] + t['uPrecDis3']) * 0.01 / 3
                if pp == 0.0 and pd:
                    pp = 0.1
                out['ranged'] = round(round(pd * pp) * 100.0 / art)
            else:
                pr = self._prom_dis(self.desc_dan(cls, n, rank), t['uPrecDis1'] / 100, t['uPrecDis2'] / 100,
                                    t['uPrecDis3'] / 100, t['uModDanDis'] / 100, cls, rank)
                out['ranged'] = max(1 if pr > 0 else 0, round(pr * 100.0 / dis))
        if flags & F_MELEE and cls != 2:
            pc = self._prom_cac(self.desc_dan(cls, n, rank), t['uPrecCue'] / 100, t['uModDanCue'] / 100, cls, rank)
            out['melee'] = max(1 if pc > 0 else 0, round(pc * 100.0 / cac))
        return out


# ---------------------------------------------------------------- CLI
def roundtrip(paths):
    ok = True
    for p in paths:
        raw = open(p, 'rb').read()
        d = Dt(raw)
        same = d.pack() == raw
        ok &= same
        print('%-90s %6d bytes v%d %d ranks x %d tables  round-trip %s' % (
            os.path.relpath(p, ROOT), len(raw), d.version, len(d.ranks), len(d.ranks[0].tables),
            'OK' if same else 'FAIL'))
    return ok


def _g(v):
    return ('%g' % v) if isinstance(v, float) else str(v)


COLS = [('men', 'uUnidades'), ('hp', 'VidaTotal'), ('resD', 'uResDis'), ('resC', 'uResCar'), ('resM', 'uResCue'),
        ('reld', 'uTieRec'), ('rng1', 'fRngDis1'), ('rng2', 'fRngDis2'), ('rng3', 'fRngDis3'),
        ('acc1', 'uPrecDis1'), ('acc2', 'uPrecDis2'), ('acc3', 'uPrecDis3'), ('accM', 'uPrecCue'),
        ('accC', 'uPrecCar'), ('dmgD', 'uModDanDis'), ('dmgC', 'uModDanCar'), ('dmgM', 'uModDanCue'),
        ('vNor', 'fVelNor'), ('vRun', 'fVelCor'), ('vChg', 'fVelCar'), ('stLos', 'fGastoResistPorSegundo'),
        ('stGan', 'fGananciaResistPorSegundo'), ('fatig', 'fDuracionFatiga'), ('mPen', 'fPenalizacionMelee'),
        ('val', 'uValTropa'), ('flags', 'uFlagsAccionesDisponibles')]


def dump_file(d, title, names):
    L = ['=' * 160, '%s   (version %d)' % (title, d.version), '=' * 160,
         'Troops (TDescTropa), one row per type and rank.  res* = resistance % vs ranged/charge/melee; '
         'acc = accuracy %; dmg* = damage modifier %; reld = reload;',
         'rng in cm; v* = speed per s; st* = stamina loss/gain per s; fatig = fatigue s; mPen = melee penalty %; '
         'flags: 0x40 can fire, 0x80 melee, 0x100 charge.',
         'Panel (p*) = army info panel Defence / Ranged / Melee / Range m, recomputed with the retail exe formula '
         '(FUN_00590580/00591290/00590930/00590210); 0 = empty.', '']
    hdr = '%-13s %-8s %-5s ' % ('type', 'mask', 'rank') + ' '.join('%6s' % c for c, _ in COLS) + \
          ' |  pDef pRng pMel pRm'
    L.append(hdr); L.append('-' * len(hdr))
    order = [m for m in MASKS if not m & OFFICERS]
    order.sort(key=lambda m: mask_class_row(m))
    for m in order:
        for r in range(len(d.ranks)):
            t = d.troop(m, r)
            pv = d.panel(m, r)
            L.append('%-13s %-8s %-5s ' % (names.get(m, MASKS[m]), hex(m), RANKS[r][:5]) +
                     ' '.join('%6s' % (hex(t[f]) if c == 'flags' else _g(round(t[f], 3) if isinstance(t[f], float)
                                                                          else t[f])) for c, f in COLS) +
                     ' | %5d %4d %4d %4d' % (pv['defence'], pv['ranged'], pv['melee'], pv['range']))
        L.append('')
    arm, dis, cac, art = d.panel_max()
    L.append('Panel maxima (100%%): defence sum %d, ranged %d, melee %d, artillery %d' % (arm, dis, cac, art))
    L.append('Officers (mask & 0x3c0000) use the FUSILERO row.')
    L.append('')
    for r, rk in enumerate(d.ranks):
        L.append('-- rank %d %s --' % (r, RANKS[r]))
        for cls_name, tab in (('infantry', rk.dan_inf), ('cavalry', rk.dan_cav)):
            L.append('  %s damage bands (TDescDanTropa; soldiers >= Soldados): ' % cls_name +
                     '  '.join('%d:[%d-%d|%d-%d|%d-%d] mel %d-%d chg %d-%d' % (
                         x['Soldados'], x['DisRng1_Min'], x['DisRng1_Max'], x['DisRng2_Min'], x['DisRng2_Max'],
                         x['DisRng3_Min'], x['DisRng3_Max'], x['Cue_Min'], x['Cue_Max'], x['Car_Min'],
                         x['Car_Max']) for x in tab.rows))
        for cls_name, tab in (('inf', rk.form_inf), ('cav', rk.form_cav)):
            L.append('  %s formations (resD,resC,resM,dmgD,dmgC,dmgM,vel): ' % cls_name +
                     '  '.join('%s(%d,%d,%d,%d,%d,%d,%d)' % (FORM_ROWS[i], x['ResDis'], x['ResCar'], x['ResCue'],
                                                              x['DanDis'], x['DanCar'], x['DanCue'], x['Vel'])
                               for i, x in enumerate(tab.rows)))
        for cls_name, tab in (('inf', rk.sq_inf), ('cav', rk.sq_cav)):
            x = tab[0]
            L.append('  %s charge vs square (mult vs defender rank N/M/X/V/E): %g %g %g %g %g' % (
                cls_name, x['MultVsNovata'], x['MultVsMedia'], x['MultVsExperimentada'], x['MultVsVeterana'],
                x['MultVsElite']))
        L.append('  charge props (distMin, distMax, multReqRanged, multReqCharge): ' + '  '.join(
            '%s(%g,%g,%g,%g)' % (CHARGE_ROWS[i], x['DistMin'], x['DistMax'], x['MultNumUnidadesReq_AtaqueDist'],
                                 x['MultNumUnidadesReq_Carga']) for i, x in enumerate(rk.charge.rows)))
        L.append('  artillery damage (rng1/2/3, precVsBuild, melee): ' + '  '.join(
            '%s(%d/%d/%d,%g,%d-%d)' % (ART_ROWS[i], x['DamageRng1'], x['DamageRng2'], x['DamageRng3'],
                                       x['PrecisionVsEdif'], x['Cue_Min'], x['Cue_Max'])
            for i, x in enumerate(rk.art_dan.rows)))
    L.append('')
    return L


def diff(a, b, la, lb):
    out = []
    for r in range(len(a.ranks)):
        for ta, tb in zip(a.ranks[r].tables, b.ranks[r].tables):
            nm = TABLES[ta.tid][1]
            rows = TABLES[ta.tid][3]
            for i, (ra, rb) in enumerate(zip(ta.rows, tb.rows)):
                for k in ra:
                    if k != 'Placeholder' and ra[k] != rb[k]:          # placeholders = uninitialised editor memory
                        out.append('  rank %d %-8s %-13s %-28s %s: %s  %s: %s' % (
                            r, nm, rows[i] if rows else str(i), k, la, _g(ra[k]) if not isinstance(ra[k], list)
                            else ra[k], lb, _g(rb[k]) if not isinstance(rb[k], list) else rb[k]))
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else 'dump'
    battle0 = os.path.join(ROOT, 'data', BATTLE_REL)
    battle = orig_path(BATTLE_REL)
    auto = orig_path(AUTO_REL)
    ok = roundtrip([battle0, battle, auto])
    if cmd == 'test':
        return 0 if ok else 1
    names = mask_names()
    bad = {m: (MASKS[m], names.get(m)) for m in MASKS if names.get(m) != MASKS[m]}
    if bad:
        print('mask/name mismatch vs mng:', bad)
    db, da, d0 = Dt.load(battle), Dt.load(auto), Dt.load(battle0)
    if cmd == 'panel':
        for m in sorted((m for m in MASKS if not m & OFFICERS), key=mask_class_row):
            print('%-13s' % names.get(m, MASKS[m]), '  '.join(
                'r%d D%3d R%3d M%3d %4dm' % ((r,) + tuple(db.panel(m, r)[k] for k in ('defence', 'ranged',
                                                                                  'melee', 'range')))
                for r in range(5)))
        return 0
    L = ['dt_dump.txt: written by tools/dtparse.py (read-only view of the original combat tables)', '']
    L += dump_file(db, os.path.relpath(battle, ROOT) + '  [real-time battle; data1 overrides data]', names)
    L += dump_file(da, os.path.relpath(auto, ROOT) + '  [auto-resolve]', names)
    L += ['=' * 160, 'Differences data/ -> data1/ (official patch) battle table:'] + diff(d0, db, 'data', 'data1')
    dd = diff(db, da, 'battle', 'auto')
    L += ['', 'Differences battle (data1) -> auto-resolve: %d fields' % len(dd)] + dd
    out = os.path.join(ROOT, 'build', 'dt_dump.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print('wrote', os.path.relpath(out, ROOT), len(L), 'lines')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))

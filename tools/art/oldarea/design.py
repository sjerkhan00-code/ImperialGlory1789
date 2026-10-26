"""Redesigned polygons for the 11 provinces added inside the original hand-painted map.

Every border is derived from the art: coasts from the painted sea (geo.land_polys pulled in by COAST_IN to the
coast ink, where the original meshes end), shared borders with original provinces from their mesh outlines
(geo.chain), and the new inland borders hand-placed on the painted rivers / mountain glyphs / caravan routes.
Shared borders between two new provinces are the same vertex lists in both polygons (the *_LINE constants).

The straight old-edge borders against the 1789 provinces of the bigger map (Hejaz, Najd, Kandahar, Kabul, Timbuktu)
are replaced by natural lines; the matching new provinces and extension pieces are rewritten accordingly.

python design.py  ->  build/oldarea/provinces.json, world_provinces_fixed.json, extensions_fixed.json (+ checks)
"""
import os, sys, json, math, copy
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, LinearRing
from shapely.ops import unary_union
import common as C, geo

OUT = C.OUT
EDGE_E, EDGE_S = 19930.0, -880.0          # old map edge where the extension pieces attach
COAST_IN = 48.0                            # world units the mesh edge lies inside the painted sea-mask boundary
_c = {}


def coast():
    """Painted coastline as the original meshes use it: land pulled in by COAST_IN (the ink line)."""
    if 'coast' not in _c:
        L = geo.land_polys()
        _c['coast'] = L.buffer(-COAST_IN).buffer(0).simplify(10.0, preserve_topology=True)
    return _c['coast']


def _rings():
    if 'rings' not in _c:
        rs = []
        for g in coast().geoms:
            rs.append(LinearRing(g.exterior.coords))
            rs += [LinearRing(h.coords) for h in g.interiors]
        _c['rings'] = rs
    return _c['rings']


def coast_pt(p):
    """Nearest point on the painted coast to p."""
    r = min(_rings(), key=lambda r: r.distance(Point(p)))
    q = r.interpolate(r.project(Point(p)))
    return (round(q.x, 1), round(q.y, 1))


def coast_chain(a, b):
    """Coast vertices from a to b (both projected onto the coast ring nearest to a), the shorter way round.
    Returns [a', v1, ..., vn, b']."""
    r = min(_rings(), key=lambda r: r.distance(Point(a)))
    L = r.length
    da, db = r.project(Point(a)), r.project(Point(b))
    pa = r.interpolate(da); pb = r.interpolate(db)
    coords = list(r.coords)[:-1]
    dist = [r.project(Point(c)) for c in coords]
    def between(d0, d1):          # vertices with d0 < d < d1 going forward (mod L)
        out = []
        span = (d1 - d0) % L
        for c, d in zip(coords, dist):
            t = (d - d0) % L
            if 0 < t < span:
                out.append((t, c))
        out.sort()
        return [c for _, c in out], span
    fwd, lf = between(da, db)
    bwd, lb = between(db, da)
    pts = fwd if lf <= lb else bwd[::-1]
    pts = [(round(x, 1), round(y, 1)) for x, y in pts]
    a = (round(a[0], 1), round(a[1], 1)); b = (round(b[0], 1), round(b[1], 1))
    pts = [p for p in pts if math.hypot(p[0] - a[0], p[1] - a[1]) > 1.0 and math.hypot(p[0] - b[0], p[1] - b[1]) > 1.0]
    return [a] + pts + [b]          # the given end points verbatim (they come from coast_pt / shared constants)


INKED = {'Anatolia', 'Marruecos', 'Tunez', 'Tripolitania'}      # originals whose outer edge is a painted ink line


def _inkmask():
    if 'ink' not in _c:
        from scipy import ndimage
        img = C.comp(False).astype(np.float32)
        lum = img.mean(-1)
        m = (img[..., 0] - img[..., 1] > 16) & (img[..., 0] - img[..., 2] > 22) & (lum < 150)
        _c['ink'] = ndimage.binary_opening(m, iterations=1)
    return _c['ink']


def snap_to_ink(ch, step=50.0, reach=40):
    """Densify a mesh-outline chain and move the new points onto the painted ink line (nearest ink run along the
    local normal, within `reach` px); the mesh's own vertices stay.  The original meshes are coarse polylines and the
    painted border curves between their vertices."""
    ink = _inkmask()
    out = [ch[0]]
    for i in range(1, len(ch)):
        a, b = ch[i - 1], ch[i]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L / step))
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        for k in range(1, n):
            t = k / n
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            px, py = C.w2p(*p)
            best = None
            for d in range(-reach, reach + 1):
                x, y = int(round(px + nx * d)), int(round(py - ny * d))
                if 0 <= x < 4096 and 0 <= y < 4096 and ink[y, x] and (best is None or abs(d) < abs(best)):
                    best = d
            if best is not None:
                # centre of that ink run
                lo = hi = best
                while lo > -reach and ink[int(round(py - ny * (lo - 1))), int(round(px + nx * (lo - 1)))]:
                    lo -= 1
                while hi < reach and ink[int(round(py - ny * (hi + 1))), int(round(px + nx * (hi + 1)))]:
                    hi += 1
                d = (lo + hi) / 2.0
                wd = d * C.TILE_W / C.TS            # px -> world (same scale both axes, approximately)
                p = (p[0] + nx * wd, p[1] + ny * wd)
            out.append((round(p[0], 1), round(p[1], 1)))
        out.append(b)
    ls = LineString(out).simplify(6.0, preserve_topology=True)
    return [(round(x, 1), round(y, 1)) for x, y in ls.coords]


def chain(name, a, b):
    ch = [(round(x, 1), round(y, 1)) for x, y in geo.chain(name, a, b)]
    return snap_to_ink(ch) if name in INKED else ch


def on_segment(a, b, x=None, z=None):
    if x is not None:
        t = (x - a[0]) / (b[0] - a[0])
    else:
        t = (z - a[1]) / (b[1] - a[1])
    return (round(a[0] + (b[0] - a[0]) * t, 1), round(a[1] + (b[1] - a[1]) * t, 1))


def dedupe(pts):
    out = []
    for p in pts:
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) <= 1.0:
            continue
        if len(out) > 1 and math.hypot(p[0] - out[-2][0], p[1] - out[-2][1]) <= 1.0:
            out.pop()                                   # spike A -> B -> A
            continue
        out.append(p)
    while len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1.0:
        out.pop()
    return out


def area(poly):
    return abs(Polygon(poly).area)


def wander(line, amp, waves, seed, step=60.0, taper=700.0, simplify=5.0):
    """A ruler-straight polyline made to wander like a hand-drawn border: resampled every `step` units and pushed
    along its normal by a sum of smooth sine waves (`waves`: (wavelength, amplitude) in world units, the shortest
    one as a little jitter), tapered to zero at both ends (the end points stay exact).  Deterministic (seed)."""
    base = [tuple(q) for q in line]
    for _ in range(3):                            # Chaikin: round the corners first, so the normals turn smoothly
        if len(base) < 3:
            break
        sm = [base[0]]
        for a, b in zip(base[:-1], base[1:]):
            sm += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        base = sm[:1] + sm[2:-1] + [base[-1]]
    ls = LineString(base)
    L = ls.length
    n = max(2, int(L / step))
    rng = np.random.default_rng(seed)
    comps = [(amp * w[1], w[0], rng.uniform(0, 2 * math.pi)) for w in waves]
    pts = []
    for k in range(n + 1):
        d = L * k / n
        p = ls.interpolate(d)
        q = ls.interpolate(min(L, d + 1.0)) if d < L else p
        r = ls.interpolate(max(0.0, d - 1.0))
        tx, tz = q.x - r.x, q.y - r.y
        tl = math.hypot(tx, tz) or 1.0
        nx, nz = -tz / tl, tx / tl
        t = min(1.0, d / taper, (L - d) / taper)
        t = 0.5 - 0.5 * math.cos(math.pi * max(0.0, t))
        off = sum(a * math.sin(2 * math.pi * d / wl + ph) for a, wl, ph in comps) * t
        pts.append((p.x + nx * off, p.y + nz * off))
    out = LineString(pts).simplify(simplify, preserve_topology=True)
    pts = [(round(x, 1), round(z, 1)) for x, z in out.coords]
    pts[0], pts[-1] = tuple(line[0]), tuple(line[-1])
    return pts


# ------------------------------------------------------------------------------------- key points (world units)
# painted coast points (projected onto the coast ring)
UC = coast_pt((16500, 12950))         # Urals reach the Arctic coast (Kara Sea), Ural | Siberia
AN = coast_pt((14103, 12800))         # Arctic coast north of Moscu's NE corner
VM = chain('Kursk', (15954, 6917), (16146, 7354))[0]   # Volga mouth: Kursk's mesh corner on the Caspian north coast
UM = coast_pt((16336, 6505))          # Ural river mouth on the Caspian NE coast, Ural | Kazakhstan
KB = coast_pt((16298, 5600))          # north shore of the Kara-Bogaz bay, Kazakhstan | Turkestan
CS = coast_pt((17149, 4064))          # Caspian SE corner (Astrabad bay), Persia | Khorasan | Turkestan
GH = coast_pt((16767, 1187))          # head of the Persian Gulf (Shatt al-Arab), Arabia | Persia
PG = coast_pt((18005, 759))           # Gulf north coast, Persia | Khorasan
OB = coast_pt((18098, -374))          # west shore of the Gulf's southern bay, Arabia | Oman
OE = coast_pt((19930, -240))          # Gulf of Oman south coast at the old east edge
KE = coast_pt((19930, 368))           # Gulf of Oman / Makran coast at the old east edge
OBX = coast_pt((19930, 12621))        # Ob estuary at the old east edge (Arctic coast)

# shared inland lines between new provinces (each used by both neighbours, same vertices)
# (URAL_RIVER, KAZ_SIB, KAZ_TURK, KABUL_LINE: the first, ruler-straight versions; the natural lines that replace
# them are defined after NATURAL below, 2026-10-23)
URAL_RIVER = [UM, (16400.0, 7400.0), (16650.0, 7850.0), (16900.0, 8300.0)]        # Ural | Kazakhstan (Orenburg)
URALS_CREST_BASE = [(16900.0, 8300.0), (16450.0, 8900.0), (16250.0, 9500.0), (16450.0, 10200.0), (16800.0, 10900.0),
               (16700.0, 11600.0), (16560.0, 12300.0), UC]                           # Ural | Siberia (mountain glyphs)
KAZ_SIB = [(16900.0, 8300.0), (17400.0, 8550.0), (18000.0, 8700.0), (18800.0, 8850.0), (19930.0, 8995.0)]  # Orenburg road
# the Ural | Siberia line wanders along the painted mountain glyphs instead of running ruler-straight
URALS_CREST = wander(URALS_CREST_BASE, 1.0, [(1700.0, 95.0), (830.0, 55.0), (390.0, 22.0)], seed=59)
# Moscu's east edge (the 2005 map's edge) as a natural line, Kama-Vychegda watershed style.  Where it bulges west
# Ural overlaps the original Moscu mesh (cut out of Moscu at build time, as Chechenya out of Kursk); where it bulges
# east the land between the old edge and the line becomes a Moscu extension piece (extensions.json 'Moscu').
MOSCU_EDGE = wander(chain('Moscu', (15669, 8608), (14103, 12506)), 1.0,
                    [(2300.0, 150.0), (1150.0, 85.0), (520.0, 30.0)], seed=1789)
KAZ_TURK = [KB, (17000.0, 5900.0), (17600.0, 6150.0), (18400.0, 6250.0), (19200.0, 6200.0), (19930.0, 6083.0)]  # N of the Silk Road
# (ends where the Kazakhstan | Turkestan extension pieces meet the old edge, z = 6083, so the border runs on without a step)
# Turkestan | Khorasan and Persia | Khorasan as natural lines (2026-10-21; first version: 5 / 6 ruler-straight segments).
# Base polylines on the painted 2005 features where the old art has them (it lies ~300-400 units NE of
# warp.game_to_lonlat near the Caspian: the painted Kopet Dag runs from x 17700, z 4950 to x 18950, z 4350), on warp
# landmarks east of x 18900 (no painted features there).  Made to wander below (after NATURAL), end points exact.
# Turkestan | Khorasan: lower Atrek from the Astrabad bay, up the Sumbar to the Kopet Dag, along its northern foothills
# (Akhal and Merv with Bukhara; the range, Dargaz, Kalat, Sarakhs with Afsharid Khorasan), over the Badkhyz to the
# Murghab at Panjdeh (Tagtabazar), then along the Band-e Turkestan crest (Maimana north of it) to the Kabul junction.
TURK_KHOR_BASE = [CS, (17255.0, 4175.0), (17370.0, 4290.0), (17470.0, 4420.0), (17545.0, 4570.0), (17605.0, 4730.0),
                  (17680.0, 4885.0), (17795.0, 4970.0), (17920.0, 5005.0), (18040.0, 4985.0), (18145.0, 4915.0),
                  (18245.0, 4825.0), (18345.0, 4730.0), (18450.0, 4640.0), (18565.0, 4565.0), (18690.0, 4510.0),
                  (18810.0, 4450.0), (18930.0, 4375.0), (19045.0, 4325.0), (19140.0, 4300.0), (19290.0, 4272.0),
                  (19445.0, 4265.0), (19580.0, 4280.0), (19705.0, 4305.0), (19826.0, 4340.0), (19930.0, 4370.0)]
# Persia | Khorasan (Qajar / Zand Persia | Afsharid Khorasan with Kerman): through the south side of the painted
# eastern Alborz east of the Astrabad bay (Shahrud, Bastam with the Qajars; Jajarm, Sabzevar with Khorasan), south down the Dasht-e
# Kavir's east rim (west foot of the painted Khorasan ranges: Khur, Jandaq Persian, Tabas Khorasani), over the Yazd |
# Kerman divide (Bafq, Mehriz Persian; Kuhbanan, Rafsanjan, Shahr-e Babak Kermani), between Fars (Neyriz, Darab,
# Jahrom) and Kerman / Laristan (Sirjan, Lar) to the Gulf coast at PG
# (it leaves the bay south-eastwards: at a sharper angle to the Turkestan line Persia's dense vertices near CS came
# within make_map.neighbours' 60-unit reach of Turkestan for 160 of the 200 units that make a neighbour; now 80)
PERS_KHOR_BASE = [CS, (17220.0, 3990.0), (17335.0, 4000.0), (17450.0, 3995.0), (17545.0, 3975.0), (17610.0, 3905.0),
                  (17640.0, 3780.0), (17660.0, 3610.0), (17685.0, 3440.0), (17715.0, 3280.0), (17760.0, 3120.0),
                  (17825.0, 2960.0), (17905.0, 2800.0), (18000.0, 2645.0), (18100.0, 2500.0), (18170.0, 2340.0),
                  (18185.0, 2170.0), (18160.0, 2000.0), (18170.0, 1830.0), (18255.0, 1665.0), (18365.0, 1505.0),
                  (18465.0, 1360.0), (18495.0, 1235.0), (18420.0, 1110.0), (18300.0, 1000.0), (18160.0, 880.0), PG]
ARAB_PERS = [(16074.4, 1254.0), (16400.0, 1300.0), GH]                              # Shatt al-Arab


def tuat_south_corner():
    """Point of the old Tuat south edge (5805,-970)-(3305,-880) at x = 4059, where its extension piece starts."""
    return on_segment((5805.0, -970.0), (3305.0, -880.0), x=4059.0)


# Natural lines replacing the straight old-edge borders (x = 19930 / z = -880) against the 1789 provinces of the
# bigger map (2026-10-21; the first version only zigzagged along the edge).  Each base polyline is laid on the real
# landmarks (lon/lat through warp.game_to_lonlat, the same mapping the art uses) and then made to wander like the
# hand-drawn ones; the end points are existing junction vertices, so the neighbours keep their shared borders
# (fix_new_provinces / fix_extension_runs rewrite the other side).  Dense and smooth (step 20, simplify 0.6): the ink
# is drawn along the polygon edges, and coarser polylines showed as kinked lines.
NATURAL = dict(step=20.0, simplify=0.6)
TURK_KHOR = wander(TURK_KHOR_BASE, 1.0, [(560.0, 28.0), (240.0, 11.0)], seed=1785, taper=140.0, **NATURAL)
PERS_KHOR = wander(PERS_KHOR_BASE, 1.0, [(560.0, 28.0), (240.0, 11.0)], seed=1781, taper=140.0, **NATURAL)
H0 = (13576.8, -886.7)                    # Arabia | Anatolia | Hejaz (Anatolia mesh corner on the Red Sea coast)
T1 = (15378.759978425027, -1196.9789674952208)   # Hejaz | Najd | Arabia (Hejaz-Najd border of the bigger map)
J_O = (18005.0, -880.0)                    # Arabia | Oman | Najd
M1 = (19858.759978425027, -1196.9789674952208)   # Najd | Muscat | Oman (Oman's extension piece)
# Arabia | Hejaz: north of the Khaybar / Henakiyah harrats (Hejaz), Tabuk-Tayma desert edge to Arabia
HEJAZ_LINE = wander([H0, (13760.0, -930.0), (13980.0, -1010.0), (14200.0, -990.0), (14420.0, -900.0), (14640.0, -930.0),
                     (14880.0, -1040.0), (15120.0, -1100.0), T1], 1.0, [(520.0, 30.0), (230.0, 12.0)],
                    seed=1786, taper=120.0, **NATURAL)
# Arabia | Najd: Qassim, al-Arid (Diriyah) and al-Kharj stay with Arabia; Duwadmi, Hawta, Aflaj and Yabrin with Najd
NAJD_LINE = wander([T1, (15600.0, -1150.0), (15850.0, -1040.0), (16080.0, -960.0), (16330.0, -1000.0), (16560.0, -1110.0),
                    (16820.0, -1190.0), (17080.0, -1180.0), (17330.0, -1090.0), (17580.0, -1000.0), (17820.0, -940.0), J_O],
                   1.0, [(560.0, 32.0), (250.0, 13.0)], seed=1745, taper=140.0, **NATURAL)
# Oman | Najd: the northern edge of the Rub' al Khali; Sabkha Matti and the Liwa oases are Omani (Trucial coast)
OMAN_NAJD_LINE = wander([J_O, (18200.0, -960.0), (18450.0, -1020.0), (18700.0, -1000.0), (18950.0, -1060.0),
                         (19200.0, -1120.0), (19450.0, -1110.0), (19680.0, -1150.0), M1],
                        1.0, [(540.0, 30.0), (240.0, 12.0)], seed=1792, taper=140.0, **NATURAL)
# Arabia | Oman: Salwa and the base of Qatar with al-Hasa, the Trucial coast with Oman (end on the painted coast)
ARAB_OMAN = wander([J_O, (18050.0, -760.0), (18060.0, -600.0), (18040.0, -470.0), OB], 1.0,
                   [(300.0, 16.0), (130.0, 6.0)], seed=1771, taper=80.0, **NATURAL)
# Khorasan | Kandahar: west of the Sistan basin (Hamun lakes, Zaranj, Lash, Farah with Kandahar), Harut valley north to
# the Herat road (Shindand, Nehbandan, Birjand stay Persian)
KANDAHAR_LINE = wander([(19930.0, 2283.0), (19740.0, 2330.0), (19560.0, 2440.0), (19420.0, 2560.0), (19330.0, 2700.0),
                        (19300.0, 2880.0), (19330.0, 3060.0), (19400.0, 3260.0), (19520.0, 3400.0), (19680.0, 3500.0),
                        (19830.0, 3560.0), (19930.0, 3603.0)],
                       1.0, [(560.0, 30.0), (250.0, 12.0)], seed=1747, taper=140.0, **NATURAL)
KABUL_LINE = [(19930.0, 4370.0), (20150.0, 4500.0), (20250.0, 4750.0), (19930.0, 4923.0)]                        # Amu Darya (Balkh)
# Sahara | Timbuktu: the Azawad (Araouane, Bou Djebeha) with Timbuktu up to ~20 N; the El Djouf, Taoudenni and the
# Tanezrouft (Bordj Mokhtar) with the Sahara provinces; Oualata (the Hodh) stays Western Saharan
TS = (2860.0, -770.0)                      # Sahara Occidental | Tuat | Timbuktu
TIMB_W = wander([(2259.0, -880.0), (2330.0, -1010.0), (2300.0, -1180.0), (2370.0, -1350.0), (2460.0, -1480.0),
                 (2418.759978425027, -1596.9789674952208)], 1.0, [(420.0, 22.0), (190.0, 9.0)],
                seed=1768, taper=100.0, **NATURAL)                                   # Sahara Occidental (ext) | Timbuktu
TIMB_SO = wander([(2259.0, -880.0), (2400.0, -830.0), (2580.0, -790.0), (2720.0, -735.0), TS], 1.0,
                 [(380.0, 18.0), (170.0, 7.0)], seed=1769, taper=90.0, **NATURAL)   # Sahara Occidental | Timbuktu
TIMB_TU = wander([TS, (3080.0, -700.0), (3290.0, -770.0), (3500.0, -705.0), (3720.0, -800.0), (3900.0, -870.0),
                  tuat_south_corner()], 1.0,
                 [(480.0, 26.0), (220.0, 10.0)], seed=1770, taper=110.0, **NATURAL)  # Tuat | Timbuktu
TIMBUKTU_LINE = TIMB_W[::-1] + TIMB_SO[1:] + TIMB_TU[1:]          # Timbuktu's whole north run: W0 .. TS .. Tuat corner
SAH_TUAT = wander([TS, (2950.0, -200.0), (3150.0, 500.0), (3254.5, 1068.6)], 1.0, [(620.0, 34.0), (270.0, 13.0)],
                  seed=1772, taper=160.0, **NATURAL)                               # Draa / Tuat oases

# ----------------------------------------------------------------- the last straight runs as natural lines (2026-10-23)
# (ig-map-engineer, the user's "no straight borders left")  Same method as above: base polylines on 1789 landmarks
# (lon/lat through warp.game_to_lonlat), made to wander (NATURAL), end points = the existing junction vertices, so the
# neighbours keep their shared borders.  Where the 2005 painting has features they win: it has no Ural river, and its
# Volga (the Kursk | Ural border) runs up to x ~16170 near z 7400, so the Ural line keeps Ural's Volga-Ural tail at
# least ~280 units wide instead of following the warp's river course.
def _dense_ends(line, reach=70.0, step=10.0):
    """Collinear points every `step` units over the first and last `reach` units of a line.  render_borders.py skips
    an extension-piece segment that already shows ink for > 40 % of its length; a long end segment touching a painted
    border at the junction (Kabul | Turkestan piece: 63 units, half under the styled2 line's cap) was skipped whole,
    leaving a gap.  Short end segments keep the skipped part under the other line's ink."""
    def split(a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = int(math.ceil(L / step))
        return [(round(a[0] + (b[0] - a[0]) * t / k, 1), round(a[1] + (b[1] - a[1]) * t / k, 1)) for t in range(1, k)]
    def head(pts):
        out, d = [pts[0]], 0.0
        for a, b in zip(pts[:-1], pts[1:]):
            if d < reach:
                out += split(a, b)
            out.append(b)
            d += math.hypot(b[0] - a[0], b[1] - a[1])
        return out
    pts = head([tuple(q) for q in line])
    return head(pts[::-1])[::-1]


# Ural | Kazakhstan: the Yaik (Ural) from its mouth up to Orenburg
URAL_RIVER = wander([UM, (16400.0, 6760.0), (16380.0, 6980.0), (16440.0, 7200.0), (16460.0, 7420.0), (16540.0, 7600.0),
                     (16600.0, 7800.0), (16720.0, 7960.0), (16790.0, 8130.0), (16900.0, 8300.0)], 1.0,
                    [(520.0, 26.0), (230.0, 11.0)], seed=1801, taper=130.0, **NATURAL)
# Kazakhstan | Siberia: the Orenburg line, up the Ural to Orsk, then the Uy / upper Tobol steppe frontier (Troitsk and
# the Tobol headwaters Russian) to the old edge (the real shape fitted between Orenburg and the edge junction)
KAZ_SIB = wander([(16900.0, 8300.0), (17213.0, 8269.0), (17463.0, 8253.0), (17663.0, 8314.0), (18009.0, 8576.0),
                  (18314.0, 8834.0), (18688.0, 9016.0), (19095.0, 9077.0), (19511.0, 9056.0), (19930.0, 8995.0)],
                 1.0, [(560.0, 30.0), (250.0, 12.0)], seed=1802, taper=140.0, **NATURAL)
# Kazakhstan | Turkestan: the Ustyurt's southern escarpment and the Aral's south shore (the Amu Darya delta Khivan),
# then across the Kyzylkum north of Bukhara to the old edge
KAZ_TURK = wander([KB, (16600.0, 5760.0), (16850.0, 5920.0), (17100.0, 5960.0), (17350.0, 6110.0), (17600.0, 6230.0),
                   (17850.0, 6360.0), (18100.0, 6330.0), (18400.0, 6260.0), (18700.0, 6290.0), (19000.0, 6210.0),
                   (19300.0, 6150.0), (19620.0, 6060.0), (19930.0, 6083.0)], 1.0, [(560.0, 32.0), (250.0, 13.0)],
                  seed=1803, taper=140.0, **NATURAL)
# ... and its continuation between the two extension pieces, towards the Syr Darya below Chinaz
KAZ_TURK_EXT = wander([(19930.0, 6083.0), (20020.0, 6040.0), (20100.0, 5975.0), (20178.76, 5923.021)], 1.0,
                      [(260.0, 12.0), (120.0, 5.0)], seed=1804, taper=60.0, **NATURAL)
# Kazakhstan | Kokand: the Chirchiq - Keles watershed north-east past Tashkent (independent under Yunus Khoja)
KOKAND_LINE = wander([(20178.76, 5923.021), (20290.0, 6010.0), (20380.0, 6110.0), (20470.0, 6230.0), (20590.0, 6360.0),
                      (20738.76, 6483.021)], 1.0, [(420.0, 22.0), (190.0, 9.0)], seed=1805, taper=100.0, **NATURAL)
# Turkestan | Kabul: Bukhara's Shibarghan / Andkhoy steppe west of the line, Durrani Balkh east of it (first version:
# 4 straight segments bulging east), then the Amu Darya from Kelif towards Termez between the Turkestan piece and Kabul
KABUL_LINE = wander([(19930.0, 4370.0), (19905.0, 4500.0), (19875.0, 4640.0), (19895.0, 4790.0), (19930.0, 4923.0)],
                    1.0, [(300.0, 16.0), (140.0, 7.0)], seed=1806, taper=80.0, **NATURAL)
KABUL_AMU = wander([(19930.0, 4923.0), (20030.0, 4895.0), (20140.0, 4905.0), (20260.0, 4935.0), (20390.0, 4912.0),
                    (20510.0, 4942.0), (20620.0, 4952.0), (20698.76, 4993.021)], 1.0,
                   [(300.0, 14.0), (130.0, 6.0)], seed=1807, taper=70.0, **NATURAL)   # (to the Kokcha bend)
# Sahara Occidental (Trarza, Brakna, the Hodh) | Senegal: the Senegal river from Kaedi past Matam and Bakel to the
# Faleme confluence
SAH_SEN = wander([(578.7599784250269, -880.0), (600.0, -940.0), (630.0, -1010.0), (610.0, -1060.0), (660.0, -1110.0),
                  (720.0, -1150.0), (760.0, -1210.0), (820.0, -1250.0), (850.0, -1310.0),
                  (898.759978425027, -1356.9789674952208)], 1.0, [(300.0, 14.0), (130.0, 6.0)],
                 seed=1808, taper=70.0, **NATURAL)
# Sahara Occidental | Segu (Kaarta, Bambara): the Sahel's edge, Kayes and Nioro to the south, Timbedra / Nema (the
# Hodh) to the north, to the Timbuktu junction W0
SAH_SEGU = wander([(898.759978425027, -1356.9789674952208), (1000.0, -1390.0), (1120.0, -1405.0), (1250.0, -1370.0),
                   (1400.0, -1345.0), (1560.0, -1335.0), (1720.0, -1350.0), (1880.0, -1375.0), (2050.0, -1420.0),
                   (2230.0, -1500.0), TIMB_W[-1]], 1.0, [(480.0, 24.0), (220.0, 10.0)], seed=1809, taper=110.0, **NATURAL)
# render_borders.py draws these extension-piece lines and they end on painted borders: short end segments
KAZ_TURK_EXT, KOKAND_LINE, KABUL_AMU, SAH_SEN, SAH_SEGU = (_dense_ends(ln) for ln in
                                                           (KAZ_TURK_EXT, KOKAND_LINE, KABUL_AMU, SAH_SEN, SAH_SEGU))
# Egypt's and Cyrenaica's extension pieces (2005 provinces) against the 1789 provinces south of them.  The old lines
# were the modern 22 N / 25 E / 19 E survey lines; now: Egypt | Nubia from Jebel Uweinat (U) along the Sand Sea's
# south rim, north of Selima, to the Nile at the Second Cataract and the Nubia | Sennar junction (N3); Egypt | Sennar
# from there over the Red Sea hills to Gebel Elba on the coast; Cyrenaica | Wadai along the north-east foot of the
# Tibesti to the Ennedi junction (WJ); Cyrenaica | Fezzan south past Rebiana; Cyrenaica | Nubia south from Uweinat.
_U, _N3 = (10538.759978425027, -1316.9789674952208), (12698.759978425027, -1916.9789674952208)
_F1, _F2 = (8938.8625, -460.266), (8938.759978425027, -1116.9789674952208)
_WJ, _NC = (10338.759978425027, -1876.9789674952208), (10618.759978425027, -1796.9789674952208)
EGY_NUB = wander([_U, (10720.0, -1300.0), (10900.0, -1330.0), (11080.0, -1440.0), (11250.0, -1470.0), (11420.0, -1580.0),
                  (11600.0, -1700.0), (11760.0, -1690.0), (11930.0, -1640.0), (12100.0, -1720.0), (12260.0, -1850.0),
                  (12380.0, -1880.0), (12520.0, -1855.0), (12620.0, -1890.0), _N3], 1.0,
                 [(560.0, 32.0), (250.0, 13.0)], seed=1810, taper=140.0, **NATURAL)
EGY_SEN = wander([_N3, (12820.0, -1880.0), (12980.0, -1860.0), (13150.0, -1905.0), (13330.0, -1990.0), (13520.0, -2010.0),
                  (13700.0, -1985.0), (13860.0, -2030.0), (13960.0, -2085.0), (14058.759978425027, -2116.9789674952208)],
                 1.0, [(480.0, 24.0), (220.0, 10.0)], seed=1811, taper=110.0, **NATURAL)
EGY_SEN_S = EGY_SEN[:-1] + [(14055.107, -2116.4418)]   # Sennar's own coast vertex (the coast fit moved it 3.7 units)
CIR_WAD = wander([_F2, (9080.0, -1150.0), (9230.0, -1240.0), (9380.0, -1270.0), (9520.0, -1350.0), (9640.0, -1470.0),
                  (9790.0, -1570.0), (9950.0, -1600.0), (10100.0, -1700.0), (10230.0, -1820.0), _WJ], 1.0,
                 [(520.0, 28.0), (230.0, 11.0)], seed=1812, taper=130.0, **NATURAL)
CIR_FEZ = wander([_F1, (8990.0, -580.0), (8960.0, -700.0), (8880.0, -820.0), (8900.0, -950.0), (8975.0, -1040.0), _F2],
                 1.0, [(300.0, 14.0), (130.0, 6.0)], seed=1813, taper=70.0, **NATURAL)
CIR_NUB = wander([_U, (10600.0, -1440.0), (10560.0, -1570.0), (10600.0, -1700.0), _NC], 1.0,
                 [(260.0, 12.0), (120.0, 5.0)], seed=1814, taper=60.0, **NATURAL)


# ------------------------------------------------------------------------------------------------- provinces
def sahara_occidental():
    return dedupe(chain('Marruecos', (474, 1137), (3254.5, 1068.6)) + SAH_TUAT[::-1] + TIMB_SO[::-1]
                  + [(474.0, -880.0)])


def tuat():
    return dedupe(SAH_TUAT + chain('Marruecos', (3254.5, 1068.6), (3832, 1660)) + chain('Tunez', (3832, 1660), (5451, 605))
                  + chain('Tripolitania', (5451, 605), (5805, -970)) + [tuat_south_corner()] + TIMB_TU[::-1])


def arabia():
    return dedupe(chain('Anatolia', (13577, -887), (16074, 1254)) + ARAB_PERS + coast_chain(GH, OB) + ARAB_OMAN[::-1]
                  + NAJD_LINE[::-1] + HEJAZ_LINE[::-1][1:])


def oman():
    return dedupe(ARAB_OMAN + coast_chain(OB, OE) + [(19930.0, -880.0)])


def persia():
    return dedupe(chain('Anatolia', (16074, 1254), (16598, 3723)) + coast_chain((16598, 3723), CS) + PERS_KHOR[1:]
                  + coast_chain(PG, GH) + ARAB_PERS[::-1][1:])


def khorasan():
    return dedupe(PERS_KHOR[::-1] + TURK_KHOR[1:] + [(19930.0, 3603.0)] + KANDAHAR_LINE[::-1][1:]
                  + [(19930.0, 1923.0), (19930.0, 645.0)] + coast_chain(KE, PG))


def turkestan():
    return dedupe(coast_chain(KB, CS) + TURK_KHOR[1:] + KABUL_LINE[1:] + KAZ_TURK[::-1])


def kazakhstan():
    return dedupe(KAZ_SIB + KAZ_TURK[::-1] + coast_chain(KB, UM) + URAL_RIVER[1:-1])


def ural(natural=True):
    return dedupe([(14103.0, 12506.0), (14103.0, 12700.0)] + coast_chain(AN, UC) + URALS_CREST[::-1][1:]
                  + URAL_RIVER[::-1][1:] + coast_chain(UM, VM) + chain('Kursk', (15954, 6917), (15669, 8608))
                  + (MOSCU_EDGE if natural else chain('Moscu', (15669, 8608), (14103, 12506))))


def siberia():
    return dedupe(URALS_CREST[::-1] + KAZ_SIB[1:] + coast_chain(OBX, UC)[:-1])


def chechenya():
    """North-east Caucasus: south edge = the Kursk|Anatolia ridge border (original vertices), east edge = the
    Caspian west coast as the Kursk mesh follows it, north edge a curved line through the Terek/Kuma steppe."""
    ridge = chain('Kursk', (14578, 4706), (15006, 4674))
    west_end = on_segment(ridge[0], ridge[1], x=14660.0)
    south_and_coast = [west_end] + chain('Kursk', (15006, 4674), (15266, 5149))
    north = [(15085.0, 5240.0), (14880.0, 5250.0), (14715.0, 5170.0), (14615.0, 5020.0), (14595.0, 4860.0)]
    return dedupe(south_and_coast + north)


# new provinces that keep a deliberate overlap with an original mesh: make_map cuts it out of the original
CARVED = {(11, 'Kursk'), (9, 'Moscu')}

PROV_FUNCS = {1: sahara_occidental, 2: tuat, 3: arabia, 4: oman, 5: persia, 6: khorasan, 7: turkestan,
              8: kazakhstan, 9: ural, 10: siberia, 11: chechenya}


# --------------------------------------------------------------------------------------------- post-processing
def snap_shared(polys, tol=0.6):
    """Insert every vertex of a neighbour that lies on an edge of a polygon (T-junctions -> shared vertices)."""
    allv = sorted({v for p in polys.values() for v in p})
    out = {}
    for pid, poly in polys.items():
        res = []
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            res.append(a)
            seg = LineString([a, b])
            ins = []
            for v in allv:
                if v == a or v == b:
                    continue
                if min(a[0], b[0]) - tol <= v[0] <= max(a[0], b[0]) + tol and min(a[1], b[1]) - tol <= v[1] <= max(a[1], b[1]) + tol \
                        and seg.distance(Point(v)) < tol:
                    ins.append((seg.project(Point(v)), v))
            ins.sort()
            res += [v for _, v in ins]
        out[pid] = dedupe(res)
    return out


def replace_edge_run(poly, a, b, line, tol=2.0):
    """In polygon `poly` replace the run of vertices from a to b (inclusive, along the polygon) with `line`
    (which starts at a and ends at b)."""
    n = len(poly)
    def idx(p):
        return min(range(n), key=lambda i: (poly[i][0] - p[0]) ** 2 + (poly[i][1] - p[1]) ** 2)
    ia, ib = idx(a), idx(b)
    assert math.hypot(poly[ia][0] - a[0], poly[ia][1] - a[1]) < tol and math.hypot(poly[ib][0] - b[0], poly[ib][1] - b[1]) < tol, (a, b, poly[ia], poly[ib])
    # the run a..b must not contain the polygon's interior part: pick the direction with the shorter length
    def run(i, j, step):
        out = [poly[i]]
        k = i
        while k != j:
            k = (k + step) % n
            out.append(poly[k])
        return out
    fwd, bwd = run(ia, ib, 1), run(ia, ib, -1)
    L = lambda r: sum(math.hypot(r[k][0] - r[k - 1][0], r[k][1] - r[k - 1][1]) for k in range(1, len(r)))
    use_fwd = L(fwd) <= L(bwd)
    r = fwd if use_fwd else bwd
    rest = run(ib, ia, 1 if use_fwd else -1)[1:-1]        # from b onwards to a, exclusive
    new = list(line) + rest
    if not use_fwd:
        new = new[::-1]
    return dedupe(new)


# 1789 provinces of the bigger map whose old-edge run is replaced by a natural line (the line runs from one end of the
# run to the other; the hejaz vertex at H0 lies 1.8 units off the Anatolia corner, hence tol 3 in replace_edge_run).
# tools/art/islands/islands.py must not trim these (its NO_TRIM), or render_borders.py loses the old lines to erase.
WORLD_JOBS = [('najd', NAJD_LINE + OMAN_NAJD_LINE[1:]), ('hejaz', HEJAZ_LINE), ('kandahar', KANDAHAR_LINE),
              ('kabul', KABUL_LINE + KABUL_AMU[1:]), ('timbuktu', TIMBUKTU_LINE),
              ('kokand', KOKAND_LINE), ('senegal', SAH_SEN), ('segu', SAH_SEGU)]                    # (2026-10-23)
# 1789 provinces whose border with an extension piece of a 2005 province (Egipto, Cirenaica) became natural
# (2026-10-23).  render_borders.py draws neither side of those (it handles the old-area provinces and their pieces),
# and the lines reach below the old 4 x 4 tiles (z < -1853, its canvas): tools/art/styled2.py draws them, from
# build/art/styled2_edges.json, like every other border of the new art.  So their pre-design snapshot
# (oldarea/world_provinces_orig.json) carries these lines too: they are not "moved borders" for render_borders,
# and islands.NO_TRIM must not list them (WORLD_JOBS keys only).
STYLED_JOBS = [('nubia', CIR_NUB[::-1] + EGY_NUB[1:]), ('sennar', EGY_SEN_S), ('wadai', CIR_WAD), ('fezzan', CIR_FEZ)]
WORLD_JOB_KEYS = [k for k, _ in WORLD_JOBS + STYLED_JOBS]
# extension pieces of the old-area provinces whose border with those provinces moves: (mesh name, a, b, keep, line)
# -> in the piece that has vertices a and b, the run a..b that does not pass `keep` becomes `line` (a .. b)
EXT_RUNS = [
    ('Oman', (19930.0, -880.0), M1, (19930.0, -205.0), [(19930.0, -880.0)] + OMAN_NAJD_LINE),   # grows west to J_O
    ('SaharaOccidental', (2259.0, -880.0), TIMB_W[-1], (578.7599784250269, -880.0), TIMB_W),
    # (2026-10-23)
    ('SaharaOccidental', (578.7599784250269, -880.0), TIMB_W[-1], (2259.0, -880.0), SAH_SEN + SAH_SEGU[1:]),
    ('Turkestan', (19930.0, 4923.0), KABUL_AMU[-1], (19930.0, 5795.0), KABUL_AMU),
    ('Turkestan', (19930.0, 6083.0), KAZ_TURK_EXT[-1], (19930.0, 5795.0), KAZ_TURK_EXT),
    ('Kazakhstan', (19930.0, 6083.0), KAZ_TURK_EXT[-1], (19930.0, 6870.0), KAZ_TURK_EXT),
    ('Kazakhstan', KOKAND_LINE[0], KOKAND_LINE[-1], (19930.0, 6870.0), KOKAND_LINE),
    ('Egipto', _U, EGY_SEN[-1], (12787.0, -970.0), EGY_NUB + EGY_SEN[1:]),
    ('Cirenaica', _F1, _WJ, _U, CIR_FEZ + CIR_WAD[1:]),
    ('Cirenaica', _NC, _U, _F1, CIR_NUB[::-1]),
]


def fix_extension_runs(E2):
    """Apply EXT_RUNS to the extension pieces (idempotent: the run is found by its end points and `keep`)."""
    for name, a, b, keep, line in EXT_RUNS:
        done = 0
        for k, pl in enumerate(E2.get(name, [])):
            ring = [tuple(p) for p in pl]
            ring = [p for i, p in enumerate(ring) if p != ring[i - 1]]
            ia, ib, ik = _find(ring, a, 3.0), _find(ring, b, 3.0), _find(ring, keep, 3.0)
            if None in (ia, ib, ik):
                continue
            n = len(ring)
            st = 1 if ik not in _run(n, ia, ib, 1) else -1
            P0 = Polygon(ring)
            new = dedupe(_replace_run(ring, ia, ib, st, [tuple(q) for q in line]))
            P1 = Polygon(new)
            assert P1.is_valid, ('extension piece invalid after the natural line', name, k)
            E2[name][k] = [list(q) for q in geo.ccw(new)]
            done += 1
            print('  extension %s piece %d: natural line, area %.0f -> %.0f' % (name, k, P0.area, P1.area))
        assert done == 1, ('EXT_RUNS piece not found', name, done)
    return E2


def _has_run(poly, line, tol=0.06, end_tol=8.0):
    """True when `line` already is a run of consecutive vertices of `poly` (either direction): a re-run of design.py
    on its own (coast-fitted) output must not touch it (2026-10-23: replace_edge_run picked coast-fit vertices near
    the end points and shaved 18 units2 off Hejaz).  The end points may differ by end_tol: the coast fit moves a line's
    end where it meets the coast (Sennar's at the Red Sea by 1-4 units)."""
    n = len(poly)
    m = len(line)
    if m > n:
        return False
    def close(q, p, t):
        return abs(q[0] - p[0]) <= t and abs(q[1] - p[1]) <= t
    for i0 in (i for i, q in enumerate(poly) if close(q, line[0], end_tol)):
        for step in (1, -1):
            if all(close(poly[(i0 + step * k) % n], p, end_tol if k in (0, m - 1) else tol) for k, p in enumerate(line)):
                return True
    return False


def fix_new_provinces(polys):
    """Rewrite the neighbouring 1789 provinces of build/world_provinces.json so the natural lines are shared."""
    W = json.load(open(os.path.join(C.BUILD, 'world_provinces.json'), encoding='utf8'))
    W2 = copy.deepcopy(W)
    for key, line in WORLD_JOBS + STYLED_JOBS:
        poly = [tuple(p) for p in W2[key]['poly']]
        if _has_run(poly, line):
            print('  new province %-9s: natural line already in place' % key)
            continue
        poly = replace_edge_run(poly, line[0], line[-1], line, tol=3.0)
        poly = geo.ccw(poly)
        W2[key]['poly'] = [list(p) for p in poly]
        print('  new province %-9s: %d verts, area %.0f -> %.0f' % (key, len(poly), Polygon(W[key]['poly']).area, Polygon(poly).area))
    return W, W2


def fix_extensions(polys, W2=None):
    """Extension pieces minus the new polygons (pieces lying inside a new province are dropped), and minus the 1789
    provinces whose old-edge run became a natural line (Arabia's piece between Hejaz and Najd now lies on both sides
    of the new lines)."""
    E = geo_ext = json.load(open(os.path.join(C.BUILD, 'extend', 'extensions.json'), encoding='utf8'))
    if W2:
        E = fix_extension_runs(E)               # first, so the moved runs are shared exactly (nothing left to cut)
    mine = unary_union([Polygon(p) for p in polys.values()]
                       + ([Polygon(W2[k]['poly']).buffer(0) for k in WORLD_JOB_KEYS] if W2 else []))
    E2 = {}
    for name, pieces in E.items():
        keep = []
        for pl in pieces:
            P = Polygon(pl)
            # a piece of an old-area province inside the old map that lies mostly on the painted water: Oman's piece on
            # the Musandam's east side followed the new tiles' coast, which oldedge.restore_gulf replaced by the 2005
            # painting of the Gulf of Oman
            if name in C.NAMES.values() and P.bounds[2] <= EDGE_E + 1.0 and P.intersection(coast()).area < 0.5 * P.area:
                print('  extension %s piece dropped (on the painted water: %.0f of %.0f units2 on land)'
                      % (name, P.intersection(coast()).area, P.area))
                continue
            if P.intersection(mine).area < 1.0:
                keep.append(pl)                         # (2026-10-23) not under the new polygons: leave it, e.g. the
                continue                                # coast fit's islets < 1000 units2 (a re-run dropped 60 of them)
            D = P.difference(mine)
            if D.area < 1000:
                print('  extension %s piece dropped (inside the new polygons, %.0f left)' % (name, D.area))
                continue
            if D.area < P.area - 1:
                print('  extension %s piece cut by %.0f units2' % (name, P.area - D.area))
                parts = list(D.geoms) if D.geom_type == 'MultiPolygon' else [D]
                for q in parts:
                    if q.area > 1000:
                        keep.append([list(v) for v in geo.to_list(q)])
            else:
                keep.append(pl)
        if keep:
            E2[name] = keep
    return E2


def moscu_extension(ural_mesh):
    """Moscu extension pieces: the land between Moscu's old (straight) east edge and MOSCU_EDGE where the natural
    line lies east of it (the part of the first-version Ural that Moscu now keeps).  Cut against the final Ural
    mesh polygon so the two share the line exactly."""
    old = Polygon(ural(natural=False)).buffer(0)
    new = Polygon(ural_mesh).buffer(0)
    D = old.difference(new).intersection(LineString(MOSCU_EDGE).buffer(400.0))
    parts = [g for g in (D.geoms if hasattr(D, 'geoms') else [D]) if g.geom_type == 'Polygon' and g.area > 1000]
    out = []
    for g in parts:
        g = g.difference(new.buffer(0.02))                                 # no overlap left by the crossings
        g = max(g.geoms, key=lambda q: q.area) if hasattr(g, 'geoms') else g
        pts = [(x, z) for x, z in g.exterior.coords[:-1]]
        out.append([list(v) for v in geo.ccw(pts)])
    print('  Moscu extension: %d pieces, %.0f units2; Ural carves %.0f units2 out of Moscu'
          % (len(out), sum(Polygon(q).area for q in out), new.difference(old).area))
    return out


# The Arctic strip north of the old top edge (z > 12506, from the North Cape to Moscu's NE corner x = 14103, where
# Ural begins) was unowned.  1789 split, so that no border runs along the old edge: Suecia and Finlandia continue
# northwards as 'Lapland' pieces (same province on both sides of the old edge), Noruega gets Finnmark as a coastal
# band from the North Cape to the Varanger fjord, Moscu gets Kola / Tersky east of the common-district line.  Every
# new line wanders and starts exactly at an existing mesh vertex on the old edge.
ARCTIC_STRIP = True
J_NS = (8888.5, 12505.4)          # Noruega | Suecia on the old top edge (mesh vertex)
J_SF = (9488.3, 12505.4)          # Suecia | Finlandia on the old top edge (mesh vertex)
J_FW = (11647.3, 12505.6)         # Finlandia's NE corner at the White Sea (mesh vertex)
ARCTIC_V = (10650.0, 12780.0)     # Noruega | Finlandia | Moscu (inland from the Varanger fjord)
ARCTIC_W = (9400.0, 12740.0)      # Noruega | Suecia | Finlandia (Torne line meets the Finnmark line)
# Finnmark's inland border (Noruega | Lapland), ~60 km inland, from the old edge up to the triple point V
FINN_BASE = [J_NS, (9000.0, 12600.0), (9200.0, 12690.0), ARCTIC_W, (9650.0, 12790.0), (9900.0, 12850.0),
             (10200.0, 12875.0), (10450.0, 12845.0), ARCTIC_V]
# Norway / Sweden-Finland | Russia: from the Varanger fjord (north of the coast, clipped by it) over V to the
# White Sea at Finlandia's corner
RUS_BASE_N = [(10760.0, 13400.0), (10730.0, 12960.0), ARCTIC_V]
RUS_BASE_S = [ARCTIC_V, (10760.0, 12690.0), (10960.0, 12620.0), (11250.0, 12565.0), J_FW]
# Suecia | Finlandia: continues the mesh border's NNW direction (Torne valley) from the old edge to W
SF_BASE = [J_SF, (9445.0, 12620.0), ARCTIC_W]


def arctic_lines():
    fa = wander(FINN_BASE[:4], 1.0, [(420.0, 34.0), (190.0, 14.0)], seed=69, step=25.0, taper=120.0, simplify=2.0)
    fb = wander(FINN_BASE[3:], 1.0, [(520.0, 40.0), (230.0, 16.0)], seed=70, step=25.0, taper=150.0, simplify=2.0)
    rn = wander(RUS_BASE_N, 1.0, [(300.0, 18.0), (140.0, 8.0)], seed=31, step=25.0, taper=90.0, simplify=2.0)
    rs = wander(RUS_BASE_S, 1.0, [(480.0, 38.0), (210.0, 15.0)], seed=32, step=25.0, taper=140.0, simplify=2.0)
    sf = wander(SF_BASE, 1.0, [(260.0, 16.0), (120.0, 7.0)], seed=66, step=20.0, taper=70.0, simplify=2.0)
    return fa, fb, rn, rs, sf


def arctic_strip(polys, E2, W2):
    """Unowned land north of the old top edge -> {'Noruega': [...], 'Suecia': [...], 'Finlandia': [...],
    'Moscu': [...]} extension pieces (world)."""
    from shapely.geometry import box
    owned = unary_union([Polygon(p) for p in polys.values()] + [Polygon(p) for v in E2.values() for p in v]
                        + [Polygon(v['poly']) for v in W2.values()] + list(geo.original_polys().values())).buffer(0)
    free = coast().difference(owned).intersection(box(7000.0, 12300.0, 14103.0, 14000.0))
    # the White Sea outlet opened by northfix.py is water although the cached sea mask predates it
    from northfix import WHITE_SEA_STRAIT
    free = free.difference(Polygon([C.p2w(x, y) for x, y in WHITE_SEA_STRAIT]).buffer(COAST_IN))
    # unowned coastal slivers below the old edge along the White Sea (the 2005 coast inset) stay unowned
    free = free.difference(box(11600.0, 12000.0, 12700.0, 12505.0))
    fa, fb, rn, rs, sf = arctic_lines()
    finn = fa + fb[1:]                                       # J_NS .. W .. V
    rus = rn + rs[1:]                                        # north of the coast .. V .. J_FW
    lo, hi = 12000.0, 14000.0
    R = {
        'Noruega': Polygon([(7000.0, lo), (J_NS[0], lo)] + finn + rn[::-1][1:] + [(rn[0][0], hi), (7000.0, hi)]),
        'Moscu': Polygon(rus + [(J_FW[0], lo), (14103.0, lo), (14103.0, hi), (rus[0][0], hi)]),
        'Suecia': Polygon([J_NS, (J_NS[0], lo), (J_SF[0], lo)] + sf + fa[::-1][1:-1]),
    }
    for k_, g in R.items():
        assert g.is_valid, ('arctic region', k_)
    R['Finlandia'] = box(7000.0, lo, 14103.0, hi).difference(unary_union(list(R.values())))
    out = {}
    for name, reg in R.items():
        part = free.intersection(reg)
        for g in (part.geoms if hasattr(part, 'geoms') else [part]):
            if g.geom_type == 'Polygon' and g.area > 20000:
                pts = dedupe([(round(x, 1), round(z, 1)) for x, z in g.exterior.coords[:-1]])
                out.setdefault(name, []).append([list(v) for v in geo.ccw(pts)])
    for name, pcs in out.items():
        print('  Arctic strip -> %-9s %d piece(s), %.0f units2' % (name, len(pcs), sum(Polygon(q).area for q in pcs)))
    return out


# junctions on the old east edge (x = 19930) where an old-area border and the matching border between the pieces
# east of the edge met the edge at different points (a step along the straight edge).  The region between the edge
# step and a vertex V of the eastern border moves from `loser` to `winner`, so the eastern border starts at A, the
# old-area junction:  (loser, winner, A, B = eastern junction, V)
EDGE_JUNCTIONS = [
    (('ext', 'Kazakhstan', 0), ('ext', 'Siberia', 0), (19930.0, 8995.0), (19930.0, 9403.0), (20978.8, 9163.0)),   # Orenburg road
    (('w', 'kabul'), ('ext', 'Khorasan', 0), (19930.0, 4370.0), (19930.0, 4203.0), (20222.5, 4118.0)),            # Khorasan | Kabul
    (('w', 'baluch'), ('ext', 'Khorasan', 1), (19930.0, 2283.0), (19930.0, 1923.0), (20295.0, 1788.0)),           # Khorasan | Baluchistan
]


def _ring_get(E2, W2, ref):
    ring = [tuple(p) for p in (E2[ref[1]][ref[2]] if ref[0] == 'ext' else W2[ref[1]]['poly'])]
    out = [p for k, p in enumerate(ring) if p != ring[k - 1]]      # (some pieces repeat a vertex)
    return out


def _ring_set(E2, W2, ref, ring):
    ring = [list(p) for p in ring]
    if ref[0] == 'ext':
        E2[ref[1]][ref[2]] = ring
    else:
        W2[ref[1]]['poly'] = ring


def _find(ring, p, tol=1.5):
    d = [math.hypot(q[0] - p[0], q[1] - p[1]) for q in ring]
    i = int(np.argmin(d))
    return i if d[i] <= tol else None


def _insert_on_edge(ring, p, tol=1.0):
    """Index of p in ring, inserting it into the edge it lies on if it is not a vertex yet (None if on no edge)."""
    i = _find(ring, p)
    if i is not None:
        return ring, i
    n = len(ring)
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        if LineString([a, b]).distance(Point(p)) < tol:
            ring = ring[:k + 1] + [tuple(p)] + ring[k + 1:]
            return ring, k + 1
    return ring, None


def _replace_run(ring, i0, i1, step, new_run):
    """Ring with the run i0 -> i1 (walking by `step`, ends inclusive) replaced by new_run; orientation kept."""
    n = len(ring)
    seq, k = [], i1
    while True:                                   # the rest of the ring: i1 (exclusive) .. i0 (exclusive)
        k = (k + step) % n
        if k == i0:
            break
        seq.append(ring[k])
    out = list(new_run) + seq
    return out if step == 1 else out[::-1]


def _run(n, i0, i1, step):
    out = [i0]
    while out[-1] != i1:
        out.append((out[-1] + step) % n)
    return out


def snap_edge_junctions(E2, W2):
    """Apply EDGE_JUNCTIONS (idempotent: a junction whose step is gone is skipped)."""
    for loser, winner, A, B, V in EDGE_JUNCTIONS:
        L = _ring_get(E2, W2, loser); Wr = _ring_get(E2, W2, winner)
        if None in (_find(L, B), _find(Wr, B), _find(L, V), _find(Wr, V)):
            print('  edge junction %s | %s: already continuous' % (loser[1], winner[1]))
            continue
        PL, PW = Polygon(L), Polygon(Wr)
        a0, w0 = PL.area, PW.area
        L, iA = _insert_on_edge(L, A)
        assert iA is not None, ('A not on', loser)
        n = len(L); iB = _find(L, B); iV = _find(L, V)
        # loser: the run A -> B -> ... -> V becomes the chord A -> V
        st = 1 if iB in _run(n, iA, iV, 1) else -1
        assert iB in _run(n, iA, iV, st)
        # the new border A -> V wanders a little like the hand-drawn ones (end points exact)
        cl = math.hypot(L[iV][0] - A[0], L[iV][1] - A[1])
        chord = wander([tuple(A), L[iV]], 1.0, [(cl * 1.1, 0.035 * cl), (cl * 0.45, 0.012 * cl)], seed=int(A[1]),
                       step=30.0, taper=cl * 0.3, simplify=2.0)
        chord = [tuple(A)] + chord[1:-1] + [L[iV]]
        L2 = _replace_run(L, iA, iV, st, chord)
        # winner: its run V -> ... -> B (the old shared border, on the loser's boundary) becomes V -> A -> B
        m = len(Wr); jB = _find(Wr, B); jV = _find(Wr, V)
        on_loser = lambda r: all(PL.boundary.distance(Point(Wr[k])) < 1.0 for k in r)
        rl = _run(n, iB, iV, 1 if iV in _run(n, iA, iV, 1) and iB in _run(n, iA, iV, 1) else -1)
        target = LineString([L[k] for k in rl]).length                 # the loser's B .. V border
        rlen = lambda r: LineString([Wr[k] for k in r]).length
        cands = [s_ for s_ in (1, -1) if on_loser(_run(m, jV, jB, s_))]
        assert cands, ('shared run not found', winner)
        st = min(cands, key=lambda s_: abs(rlen(_run(m, jV, jB, s_)) - target))
        W2r = _replace_run(Wr, jV, jB, st, [Wr[jV]] + chord[1:-1][::-1] + [tuple(A), Wr[jB]])
        # B is now a plain point of the straight edge: drop it when collinear
        jb = W2r.index(Wr[jB]); pb, nb = W2r[jb - 1], W2r[(jb + 1) % len(W2r)]
        if abs(pb[0] - 19930.0) < 0.5 and abs(nb[0] - 19930.0) < 0.5 and abs(Wr[jB][0] - 19930.0) < 0.5:
            W2r.pop(jb)
        P1, P2 = Polygon(L2), Polygon(W2r)
        assert P1.is_valid and P2.is_valid, ('invalid after junction fix', loser, winner, P1.is_valid, P2.is_valid)
        ov0 = PL.intersection(PW).area                                  # (some pieces overlap a little already)
        ov1 = P1.intersection(P2).area
        assert abs((P1.area + P2.area - ov1) - (a0 + w0 - ov0)) < 25.0 and ov1 <= ov0 + 1.0,             ('area not conserved', loser, winner, P1.area + P2.area - ov1, a0 + w0 - ov0, ov0, ov1)
        _ring_set(E2, W2, loser, L2); _ring_set(E2, W2, winner, W2r)
        print('  edge junction %s | %s: %.0f units2 moved, border now starts at z = %.0f' % (loser[1], winner[1], a0 - P1.area, A[1]))
    return E2, W2


def check(polys, W2=None, E2=None, S2=None):
    import meshgen as MG
    ok = True
    for pid, p in polys.items():
        P = Polygon(p)
        if not (P.is_valid and MG.is_simple(p) and MG.area(p) > 0):
            print('  BAD polygon', pid, P.is_valid, MG.is_simple(p), MG.area(p)); ok = False
        print('  pid %2d %-16s %3d verts  area %8.0f  bbox %s' % (pid, C.NAMES[pid], len(p), P.area,
              tuple(round(v) for v in P.bounds)))
    pids = sorted(polys)
    for i in pids:
        for j in pids:
            if i < j:
                A, B = Polygon(polys[i]), Polygon(polys[j])
                ov = A.intersection(B).area
                if ov > 1.0:
                    print('  OVERLAP %d %d: %.0f' % (i, j, ov)); ok = False
                shared = A.boundary.intersection(B.boundary)
                if shared.length > 1:
                    sa = set(polys[i]); sb = set(polys[j])
                    miss = [v for v in polys[i] if Point(v).distance(B.boundary) < 0.1 and v not in sb] + \
                           [v for v in polys[j] if Point(v).distance(A.boundary) < 0.1 and v not in sa]
                    print('  shared %-12s|%-12s %6.0f units, %d unshared vertices' % (C.NAMES[i], C.NAMES[j], shared.length, len(miss)))
                    if miss:
                        ok = False
    O = geo.original_polys()
    for pid in pids:
        P = Polygon(polys[pid])
        for name, G in O.items():
            ov = P.intersection(G).area
            carve = (pid, name) in CARVED or (name in INKED and ov < 60000)   # ink-line wedges, cut at build time
            if ov > 500:
                print('  overlaps original %-12s pid %2d (%s): %.0f%s' % (name, pid, C.NAMES[pid], ov, '  (carved at build time)' if carve else '  <-- !'))
                if not carve:
                    ok = False
    S = S2 or json.load(open(os.path.join(C.BUILD, 'sea', 'sea_zones.json'), encoding='utf8'))
    for pid in pids:
        P = Polygon(polys[pid])
        for key, z in S.items():
            ov = P.intersection(Polygon(z['poly'])).area
            if ov > 1.0:
                print('  overlaps sea zone %-12s pid %2d: %.0f  <-- !' % (key, pid, ov)); ok = False
    if W2:
        for key, v in W2.items():
            Q = Polygon(v['poly'])
            for pid in pids:
                ov = Q.intersection(Polygon(polys[pid])).area
                if ov > 1.0:
                    print('  overlaps new province %-12s pid %2d: %.0f  <-- !' % (key, pid, ov)); ok = False
            for key2, v2 in W2.items():
                if key < key2:
                    ov = Q.intersection(Polygon(v2['poly'])).area
                    if ov > 1.0 and (key in WORLD_JOB_KEYS or key2 in WORLD_JOB_KEYS):
                        print('  new provinces overlap %s %s: %.0f  <-- !' % (key, key2, ov)); ok = False
    if E2:
        for name, pieces in E2.items():
            for pl in pieces:
                Q = Polygon(pl)
                for pid in pids:
                    ov = Q.intersection(Polygon(polys[pid])).area
                    if ov > 5.0:
                        print('  extension %s overlaps pid %d: %.0f  <-- !' % (name, pid, ov)); ok = False
                for key in (WORLD_JOB_KEYS if W2 else []):
                    ov = Q.intersection(Polygon(W2[key]['poly'])).area
                    if ov > 5.0:
                        print('  extension %s overlaps new province %s: %.0f  <-- !' % (name, key, ov)); ok = False
    print('CHECK', 'OK' if ok else 'PROBLEMS')
    return ok


def subtract_others(polys, others, label):
    """Cut sea zones / new-area provinces out of the polygons (only slivers along the coasts and the old edge)."""
    out = {}
    for pid, p in polys.items():
        P = Polygon(p)
        for key, Q in others:
            if P.intersection(Q).area > 1.0:
                D = P.difference(Q)
                D = max(D.geoms, key=lambda g: g.area) if D.geom_type == 'MultiPolygon' else D
                print('  %s cut %.0f units2 of %s out of %s' % (label, P.area - D.area, key, C.NAMES[pid]))
                P = D
        out[pid] = [(round(x, 1), round(y, 1)) for x, y in P.exterior.coords[:-1]]
    return out


def fix_sea_zones(polys):
    """The sea-zone polygons of build/sea/sea_zones.json are coarse (grid cells) and run over the painted land in
    the Gulf (Musandam peninsula, Makran coast): cut the new land polygons out of them -> sea_zones_fixed.json."""
    S = json.load(open(os.path.join(C.BUILD, 'sea', 'sea_zones.json'), encoding='utf8'))
    S2 = copy.deepcopy(S)
    mine = unary_union([Polygon(p) for p in polys.values()])
    for key, z in S.items():
        Z = Polygon(z['poly'])
        ov = Z.intersection(mine).area
        if ov > 1.0:
            D = Z.difference(mine)
            D = max(D.geoms, key=lambda g: g.area) if D.geom_type == 'MultiPolygon' else D
            S2[key]['poly'] = [list(v) for v in geo.to_list(D)]
            S2[key]['simple'] = Polygon(S2[key]['poly']).is_valid
            print('  sea zone %-8s cut by %.0f units2 (%d -> %d verts)' % (key, ov, len(z['poly']), len(S2[key]['poly'])))
    return S2


def sync_styled_snapshots(W2, E2):
    """STYLED_JOBS lines are drawn by styled2 (build/art/styled2_edges.json, tools/art/styled_edges.py), not by
    render_borders.py: give the pre-design snapshots the same geometry for those provinces and for the extension pieces
    of the 2005 provinces the EXT_RUNS touch (Egipto, Cirenaica), so render_borders neither erases nor redraws them."""
    f3, fo = os.path.join(OUT, 'world_provinces_orig.json'), os.path.join(OUT, 'extensions_orig.json')
    styled_ext = {name for name, *_ in EXT_RUNS if name not in C.NAMES.values()}
    for path, keys, src, kw in ((f3, [k for k, _ in STYLED_JOBS], {k: v for k, v in W2.items()}, dict(ensure_ascii=False)),
                                (fo, sorted(styled_ext), E2, {})):
        if not os.path.exists(path):
            continue
        S = json.load(open(path, encoding='utf8'))
        n = 0
        for k in keys:
            if k in S and k in src:
                new = src[k] if path == fo else dict(S[k], poly=src[k]['poly'])
                if S[k] != new:
                    S[k] = new; n += 1
        if n:
            json.dump(S, open(path, 'w', encoding='utf8'), indent=0, **kw)
        print('  %s: %d styled-line entries brought in step' % (os.path.basename(path), n))


def build(W2=None):
    polys = {pid: fn() for pid, fn in PROV_FUNCS.items()}
    if W2:
        polys = subtract_others(polys, [(k, Polygon(v['poly'])) for k, v in W2.items()], 'new province')
    polys = snap_shared(polys)
    polys = {pid: geo.ccw(dedupe(p)) for pid, p in polys.items()}
    return polys


def clip_to_meshes(polys):
    """Mesh polygons: the ink polygons minus the original meshes (make_map only cuts overlaps > 100000 units2 out
    of the originals, so the small wedges where the painted line bulges into an original mesh must not overlap).
    Chechenya keeps its (large, carved) overlap with Kursk."""
    O = geo.original_polys()
    out = {}
    for pid, p in polys.items():
        P = Polygon(p)
        for name, G in O.items():
            if (pid, name) in CARVED:
                continue
            if P.intersection(G).area > 1.0:
                D = P.difference(G).buffer(0)
                D = max(D.geoms, key=lambda g: g.area) if D.geom_type == 'MultiPolygon' else D
                P = D
        pts = dedupe([(round(x, 1), round(y, 1)) for x, y in P.exterior.coords[:-1]])
        if not Polygon(pts).is_valid:                 # a ring touching itself at one vertex: nudge it apart
            from shapely.validation import explain_validity
            print('  mesh polygon %s: %s -> shrink-fixed' % (C.NAMES[pid], explain_validity(Polygon(pts))))
            Q = Polygon(pts).buffer(-0.5).buffer(0.5)
            Q = max(Q.geoms, key=lambda g: g.area) if Q.geom_type == 'MultiPolygon' else Q
            pts = dedupe([(round(x, 1), round(y, 1)) for x, y in Q.simplify(0.3).exterior.coords[:-1]])
        out[pid] = geo.ccw(pts)
    return out


if __name__ == '__main__':
    cur = C.current_polys()
    polys = build()
    W, W2 = fix_new_provinces(polys)
    polys = build(W2)
    json.dump({str(k): [list(p) for p in v] for k, v in polys.items()}, open(os.path.join(OUT, 'provinces_ink.json'), 'w'), indent=0)
    polys = clip_to_meshes(polys)
    polys = snap_shared(polys)
    for pid in sorted(polys):
        print('%-16s area ratio vs current %.2f' % (C.NAMES[pid], area(polys[pid]) / area(cur[pid])))
    E2 = fix_extensions(polys, W2)
    for name in ('Noruega', 'Suecia', 'Finlandia'):           # previous Arctic pieces (recomputed below)
        if name in E2:
            E2[name] = [pl for pl in E2[name] if max(q[1] for q in pl) <= 12520.0]
            if not E2[name]:
                del E2[name]
    E2['Moscu'] = moscu_extension(polys[9])
    E2, W2 = snap_edge_junctions(E2, W2)
    if ARCTIC_STRIP:
        for name, pieces in arctic_strip(polys, E2, W2).items():
            E2.setdefault(name, []).extend(pieces)
    S2 = fix_sea_zones(polys)
    json.dump(S2, open(os.path.join(OUT, 'sea_zones_fixed.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    check(polys, W2, E2, S2)
    json.dump({str(k): [list(p) for p in v] for k, v in polys.items()}, open(os.path.join(OUT, 'provinces.json'), 'w'), indent=0)
    json.dump(W2, open(os.path.join(OUT, 'world_provinces_fixed.json'), 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    json.dump(E2, open(os.path.join(OUT, 'extensions_fixed.json'), 'w', encoding='utf8'), indent=0)
    sync_styled_snapshots(W2, E2)
    print('wrote provinces.json, world_provinces_fixed.json, extensions_fixed.json in', OUT)

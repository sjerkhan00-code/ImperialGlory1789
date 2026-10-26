"""Battle maps for the new regions, generated from original maps in the Pyro style (generalised lvl_caucasus.py).

    python tools/lvl_region.py                 # all recipes
    python tools/lvl_region.py desert india    # some of them (desert, india, steppe, eastasia, japan, savanna, taiga)

A recipe = one original map as template + a new relief + a new texture painted from original terrain art + a new
layout. From the template the map keeps its chunk set, sky, climate, outside scenery (TerrenoContiguo: it re-uses
the map's own tiles, mirrored, so it follows the new texture) and a CORE kept verbatim: the water objects with their
banks and bridges, the buildings with their interior sectors and the objective zone, i.e. every template sector that
lies inside the core keeps its polygon, type and heights (the heightmap equals the template's there and blends out
over a few hundred metres). Buildings outside the core can be moved horizontally (multiples of 1000 cm, so the
casilla-edge rule of lvl_nav.py still holds for their kept sectors) onto a copy of their template ground.
Everything else is generated: heights (recipe.design), sector map (lvl_nav.build, same rules as the Caucasus map),
AI graph, troop areas and deployment zones (rotated to face the enemy), locations, sounds, trees and scatter decor
(moved node by node), victory conditions (template or recipe), intro, camera, minimaps, previews.

Output (nothing here touches the game, the paks or save data):
    build/battlemaps/<FOLDER>/                 mirror of Game/GameModes/Batalla/Escenarios/<FOLDER>/
    build/battlemaps/<FOLDER>/battlemap.json   lvl, minimaps, texts, the PROVINCES that fight on this map
                                               (tools/battlemaps.py points their scenario names at it)
    build/battlemaps/minimap/, minimap_red/    battle and network-game minimaps
    build/preview/lvl_<name>_*.png             heightmap, top-down, overlay, minimap, comparison, detail

Recipes (2026-10-21):
    desert  NBDesierto  template 58 Tripolitania (oasis village)   Arabia, Hejaz, Najd, Oman, Sheikhs
    india   NBIndia     template 41 Venecia (river plain, domed villa as the temple, bridges)   Marathas, Princes
    steppe  NBEstepa    template 42 Egipto (walled village = caravanserai, river at the west edge)
                        Turkestan, Kazakh Khanate, southern Siberia; + Mongolia, Dzungaria, Qinghai, Tibet
Second batch (2026-10-21, not yet tested in game):
    eastasia NBArrozal  template 44 Piamonte (terraced hill with the fenced village, paddies by the river, 3 bridges)
                        Qing China proper, Manchuria, Formosa, Korea, mainland South-East Asia, Java, Luzon, Visayas, Bali
    japan    NBJapon    template 16 Hungria (the ruined keep as the castle, inn and walls moved beside it; wooded
                        mountains round two valleys)                Honshu, Kyushu-Shikoku, Ezo, Nepal, Kashmir
    savanna  NBSabana   template 28 Alentejo (dry grass, scattered holm oaks, kopjes, dry riverbed; village + chapel)
                        Ethiopia, Nile and Sahel kingdoms, Southern Kingdoms, Senegal, Angola, Mozambique
    taiga    NBTaiga    template 21 Kiev (fir belts, frozen river and bridge, the palisaded log farm as the ostrog)
                        Ural, Siberia, Yenisei, Yakutsk, Okhotsk, Kamchatka, Amur, Sakhalin
Third batch (2026-10-21, not yet tested in game): the first recipes that ship original models of ANOTHER map
(add_object / ship_borrowed: a class + instance appended at the end of the object list, the files copied in)
    jungle   NBSelva    template 02 Escocia (river, lake and two bridges kept; the hamlet at the river mouth as the
                        trading post; leafy jungle belts from the map's own trees + 45% of its outside woods, palms and
                        palm shrubs borrowed from 57 Tunez (Arbolesdeentorno.V3D -> PalmerasSelva.V3D); swamps = mud;
                        the hermitage removed)     Aceh, South Sumatra, both Borneos, Celebes, Moluccas, Mindanao,
                        Timor, New Guinea, Papua, Madagascar, Sierra Leone, Ivory Coast, Loango, Zanzibar Coast
    tundra   NBTundra   template 39 Finlandia (flat snow, low ridges, only the small trees and shrubs, the frozen
                        streams kept; the log farm and wooden church as the settlement; a frozen lake borrowed from
                        17 Minsk: its 17Laguna ice instance, basin heights, ice sector and painting moved over)
                        Chukotka
"""
import json
import math
import os
import shutil
import sys

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lvl            # noqa: E402
import lvl_nav        # noqa: E402
import lvl_tex        # noqa: E402
import lvl_v3d        # noqa: E402
from lvl_caucasus import (fbm, smoothstep, polyline_dist, slope_deg, normals, fit_shade, make_shade,   # noqa: E402
                          mask_polygons, height_image, topdown, minimap, overlay)

ROOT = os.path.dirname(HERE)
BM = os.path.join(ROOT, 'build', 'battlemaps')
PREVIEW = os.path.join(ROOT, 'build', 'preview')
SIZE = 75000.0
N = 181
CELL = SIZE / (N - 1)
TEX = 4096
TT = lvl_nav.TT
AX = np.arange(N) * CELL
GX, GZ = np.meshgrid(AX, AX)


# ------------------------------------------------------------------ small helpers
def scen_dir(scen):
    """Folder of an original scenario (data1 overrides data)."""
    for base in ('data1', 'data'):
        p = os.path.join(ROOT, base, 'Game', 'GameModes', 'Batalla', 'Escenarios', scen)
        if os.path.isdir(p) and any(f.lower().endswith('.lvl') and 'historica' not in f.lower() for f in os.listdir(p)):
            return p
    raise FileNotFoundError(scen)


def scen_lvl(scen):
    d = scen_dir(scen)
    return os.path.join(d, next(f for f in sorted(os.listdir(d)) if f.lower().endswith('.lvl') and 'historica' not in f.lower()))


def find_file(folder, name):
    """Case-insensitive file lookup (clima.sb / Clima.sb)."""
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


_COMP = {}


def composite(scen):
    """Full-resolution (4096^2, north-up) terrain texture of an original map."""
    if scen not in _COMP:
        m = lvl.load(scen_lvl(scen))
        t = m.get(lvl.TERRAIN)
        _COMP[scen] = lvl_tex.map_texture(os.path.join(scen_dir(scen), 'Models'), mip=0,
                                          names=[mt[2] for mt in t['materials']])
    return _COMP[scen]


def band(X, Z, e0, e1):
    return smoothstep(e0, e1, X) * smoothstep(e0, e1, SIZE - X) * smoothstep(e0, e1, Z) * smoothstep(e0, e1, SIZE - Z)


def flatten(img, sigma=24.0):
    """Remove the low-frequency light (painted relief shading, big shadows) of a texture crop, keep its grain and
    its mean colour."""
    f = img.astype(np.float32)
    lum = f.mean(-1)
    low = ndimage.gaussian_filter(lum, sigma)
    return np.clip(f * (lum.mean() / (low + 1.0))[..., None], 0, 255)


def pick_boxes(img, pred, k=6, win=320, step=96, avoid=None):
    """The k most uniform windows (low variance of the blurred luminance) of an image whose mean colour satisfies
    pred(r, g, b): automatic source selection for patch synthesis (avoids tracks, buildings, tree shadows)."""
    sm = ndimage.zoom(img.astype(np.float32), (0.25, 0.25, 1), order=1)
    lum = ndimage.gaussian_filter(sm.mean(-1), 2.0)
    w4, s4 = win // 4, step // 4
    cands = []
    for y in range(0, sm.shape[0] - w4, s4):
        for x in range(0, sm.shape[1] - w4, s4):
            r, g, b = sm[y:y + w4, x:x + w4].reshape(-1, 3).mean(0)
            if not pred(r, g, b):
                continue
            if avoid is not None and avoid(x * 4, y * 4, x * 4 + win, y * 4 + win):
                continue
            cands.append((float(lum[y:y + w4, x:x + w4].std()), x * 4, y * 4))
    cands.sort()
    out = []
    for sd, x, y in cands:
        if all(abs(x - a) >= win * 0.8 or abs(y - b) >= win * 0.8 for a, b, _, _ in out):
            out.append((x, y, x + win, y + win))
            if len(out) >= k:
                break
    assert out, 'no source window matches'
    return out


def synth(shape, img, boxes, rng, flat=24.0, patch=384, step=256, orient=True):
    """Patch synthesis from crops of an original texture (optionally flattened first)."""
    srcs = []
    for b in boxes:
        crop = img[b[1]:b[3], b[0]:b[2]]
        crop = flatten(crop, flat) if flat else crop.astype(np.float32)
        srcs.append((crop.astype(np.uint8), (0, 0, crop.shape[1], crop.shape[0])))
    with np.errstate(invalid='ignore', divide='ignore'):            # (0/0 only in the cropped-off padding)
        return lvl_tex.patch_synth(shape, srcs, rng, patch=patch, step=step, orient=orient)


def raster(geom, px, pad=0.0):
    """Boolean (px, px) mask of a shapely geometry, NORTH-UP (row 0 = high z), pixel centres."""
    import shapely
    c = (np.arange(px) + 0.5) / px * SIZE
    xx, rr = np.meshgrid(c, c)
    zz = SIZE - rr
    g = geom.buffer(pad) if pad else geom
    return shapely.contains_xy(g, xx.ravel(), zz.ravel()).reshape(px, px)


def grid_mask(geom, pad=0.0):
    """Boolean (N, N) mask of a shapely geometry on the height grid (row = z)."""
    import shapely
    g = geom.buffer(pad) if pad else geom
    return shapely.contains_xy(g, GX.ravel(), GZ.ravel()).reshape(N, N)


def up(a, n=TEX):
    """Field at a coarser north-up resolution -> TEX x TEX (bilinear)."""
    return np.asarray(ndimage.zoom(a.astype(np.float32), n / a.shape[0], order=1))[:n, :n]


def chaikin(line, rng=None, wander=0.0, step=2500.0, rounds=4):
    pts = np.array(line, float)
    if wander:
        dense = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            n = max(1, int(np.hypot(*(b - a)) / step))
            dense += [a + (b - a) * k / n + (rng.normal(0, wander, 2) if k < n else 0) for k in range(1, n + 1)]
        pts = np.array(dense)
    for _ in range(rounds):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        q.append(pts[-1])
        pts = np.array(q)
    return [tuple(p) for p in pts]


def scatter(prob, n, rng, min_dist=600.0, jitter=True):
    """Up to n world positions drawn with weights prob (N x N grid, row = z), at least min_dist apart."""
    p = np.clip(prob, 0, None).ravel()
    if p.sum() <= 0:
        return []
    idx = rng.choice(p.size, size=min(p.size, n * 6), replace=True, p=p / p.sum())
    pts = []
    for k in idx:
        iz, ix = divmod(int(k), N)
        x = ix * CELL + (rng.uniform(-CELL / 2, CELL / 2) if jitter else 0)
        z = iz * CELL + (rng.uniform(-CELL / 2, CELL / 2) if jitter else 0)
        if not (300 < x < SIZE - 300 and 300 < z < SIZE - 300):
            continue
        if all((x - a) ** 2 + (z - b) ** 2 > min_dist ** 2 for a, b in pts[-600:]):
            pts.append((x, z))
            if len(pts) >= n:
                break
    return pts


def palm_shadows(shape, pts, rng, length=70.0, strength=0.32, direction=(-0.55, -0.83)):
    """Multiplicative shadow mask of palms (texture px): a thin trunk stroke and a star of fronds at its end, cast
    away from the sun like the palms painted on 42 / 58."""
    h, w = shape
    m = np.ones((h, w), np.float32)
    ux, uy = direction
    r = int(length + 40)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    along = xx * ux + yy * uy
    across = -xx * uy + yy * ux
    for (cx, cy) in pts:
        L = length * rng.uniform(0.7, 1.2)
        trunk = np.exp(-(across / 1.6) ** 2) * (along > 2) * (along < L)
        fx, fy = xx - ux * L, yy - uy * L
        ang = np.arctan2(fy, fx)
        rad = np.hypot(fx, fy)
        k = rng.integers(6, 9)
        star = np.clip(np.cos((ang + rng.uniform(0, 6.3)) * k / 2.0) ** 4, 0, 1) * np.exp(-(rad / 20.0) ** 2)
        star = np.maximum(star, np.exp(-(rad / 9.0) ** 2))
        s_ = np.clip(np.maximum(0.45 * trunk, star) * strength, 0, strength)
        x0, y0 = int(cx) - r, int(cy) - r
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + 2 * r + 1), min(h, y0 + 2 * r + 1)
        if xa < xb and ya < yb:
            m[ya:yb, xa:xb] *= 1 - s_[ya - y0:yb - y0, xa - x0:xb - x0]
    return m


def fir_shadows(shape, pts, rng, length=270.0, width=24.0, direction=(-0.998, 0.06), strength=1.0, tiers=7, **_):
    """Shadow intensity 0..1 (union, texture px) of firs painted on snow like 21 Kiev / 39 Finlandia / 19 Kursk:
    a thin trunk line from the base, then a long tapering silhouette with serrated branch tiers, cast away from
    the painted sun (west on those maps)."""
    h, w = shape
    S = np.zeros((h, w), np.float32)
    ux, uy = np.asarray(direction, float) / np.hypot(*direction)
    jag = ndimage.gaussian_filter(rng.standard_normal((h // 4, w // 4)).astype(np.float32), 1.2)
    jag = np.asarray(ndimage.zoom(jag / (jag.std() + 1e-6), 4, order=1))[:h, :w]     # ragged branch tips
    for (cx, cy) in pts:
        L = length * rng.uniform(0.7, 1.3)
        W = width * rng.uniform(0.75, 1.3)
        a0 = L * rng.uniform(0.06, 0.14)
        n = tiers + int(rng.integers(-1, 4))
        ph = rng.uniform(0.0, 1.0, 2)
        amps = rng.uniform(0.2, 0.6, (2, n + 3))
        ex, ey = cx + ux * L, cy + uy * L
        xa, xb = int(min(cx, ex) - W - 6), int(max(cx, ex) + W + 6)
        ya, yb = int(min(cy, ey) - W - 6), int(max(cy, ey) + W + 6)
        xa, ya, xb, yb = max(0, xa), max(0, ya), min(w, xb), min(h, yb)
        if xa >= xb or ya >= yb:
            continue
        yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
        along = (xx - cx) * ux + (yy - cy) * uy
        across = -(xx - cx) * uy + (yy - cy) * ux
        t = (along - a0) / (L - a0)                                   # 0 crown base .. 1 tip
        side = (across > 0).astype(int)                               # the two sides branch differently
        f = t * n + ph[side]
        k = np.clip(np.floor(f).astype(int), 0, n + 2)
        tooth = 1.0 - amps[side, k] * np.mod(f, 1.0) / 0.6            # branches widest at each tier's base
        prof = W * np.clip(1.0 - t, 0, 1) ** 0.8 * (0.5 + 0.5 * tooth) + 2.2 * jag[ya:yb, xa:xb]
        crown = smoothstep(-2.0, 2.0, prof - np.abs(across)) * smoothstep(-0.02, 0.02, t) * (t <= 1)
        trunk = np.exp(-(across / 1.3) ** 2) * (along > 0) * (along < a0 + 2) * 0.8
        S[ya:yb, xa:xb] = np.maximum(S[ya:yb, xa:xb], np.maximum(crown, trunk) * strength * rng.uniform(0.85, 1.0))
    return ndimage.gaussian_filter(S, 0.8)


def facing_angle(frm, to):
    """POSTROOPER / location angle whose facing points from frm to to. The angle turns clockwise in (x, z):
    facing = (sin a, cos a) (see lvl.check; e.g. 58's attacker in the south-east has -0.68, facing north-west)."""
    fx, fz = to[0] - frm[0], to[1] - frm[1]
    return math.atan2(fx, fz)


def blob(X, Z, cx, cz, rx, rz, ang=0.0, power=2.0):
    """Smooth super-ellipse bump 0..1 (1 inside, falling to 0 at the rim)."""
    ca, sa = math.cos(ang), math.sin(ang)
    u = ((X - cx) * ca + (Z - cz) * sa) / rx
    v = (-(X - cx) * sa + (Z - cz) * ca) / rz
    r = (np.abs(u) ** power + np.abs(v) ** power) ** (1.0 / power)
    return 1.0 - smoothstep(0.55, 1.0, r)


def _newell(pts):
    q = np.array(pts, float)
    n = np.zeros(3)
    for i in range(len(q)):
        a, b = q[i], q[(i + 1) % len(q)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2]); n[1] += (a[2] - b[2]) * (a[0] + b[0]); n[2] += (a[0] - b[0]) * (a[1] + b[1])
    ln = np.linalg.norm(n)
    return n / ln if ln > 0 else np.array([0.0, 1.0, 0.0])


def split_big(sm, protected=(), maxv=12, min_area=2e4):
    """Split generated convex sectors with more than maxv vertices along a diagonal (both halves stay convex and
    clockwise; the diagonal becomes a new link, the other links follow their edge). Kept template sectors
    (protected ids) are left alone. New sectors are appended, so ids stay 0..n-1."""
    P = sm['points']
    changed = True
    while changed:
        changed = False
        for s in list(sm['sectors']):
            q = s['poly']
            if s['id'] in protected or len(q) <= maxv or s.get('special'):
                continue
            n = len(q)
            best = None
            for i in range(n):
                for k in range(max(3, n // 2 - 2), min(n - 2, n // 2 + 3)):
                    j = (i + k) % n
                    a = [q[(i + t) % n] for t in range(k + 1)]
                    b = [q[(j + t) % n] for t in range(n - k + 1)]
                    if len(a) > maxv or len(b) > maxv:
                        continue
                    ar = [abs(sum(P[u][0] * P[v][2] - P[v][0] * P[u][2] for u, v in zip(x, x[1:] + x[:1]))) / 2 for x in (a, b)]
                    if min(ar) < min_area:
                        continue
                    score = min(ar) / max(ar)
                    if best is None or score > best[0]:
                        best = (score, a, b, q[i], q[j])
            if best is None:
                continue
            _, a, b, vi, vj = best
            new = dict(s, id=len(sm['sectors']), poly=b)
            s['poly'] = a
            for t in (s, new):
                pts = [P[u] for u in t['poly']]
                t['p1'] = [float(v) for v in pts[0]]
                t['p2'] = [float(v) for v in _newell(pts)]
            sm['sectors'].append(new)

            def owner(i_, j_, sid):                                   # which half has edge i_ -> j_
                for t in (s, new):
                    pp = t['poly']
                    for u in range(len(pp)):
                        if pp[u] == i_ and pp[(u + 1) % len(pp)] == j_:
                            return t['id']
                return sid
            for l in sm['links']:
                if l[0] == s['id']:
                    l[0] = owner(l[2], l[3], s['id'])
                elif l[1] == s['id']:
                    l[1] = owner(l[3], l[2], s['id'])
            sm['links'].append([s['id'], new['id'], vj, vi])          # a ends with vj, wraps to vi
            changed = True


def sector_metrics(sm):
    P = sm['points']
    edges = []
    for s in sm['sectors']:
        q = s['poly']
        edges += [math.hypot(P[q[k]][0] - P[q[(k + 1) % len(q)]][0], P[q[k]][2] - P[q[(k + 1) % len(q)]][2])
                  for k in range(len(q))]
    deg = np.zeros(len(sm['sectors']), int)
    for a, b, i, j in sm['links']:
        deg[a] += 1; deg[b] += 1
    return dict(min_edge=min(edges), max_v=max(len(s['poly']) for s in sm['sectors']), max_links=int(deg.max()))


# ------------------------------------------------------------------ the generator
class Recipe:
    name = 'region'                 # preview / json name
    key = 'REGION'                  # LTEXT key part of the intro texts
    folder = 'NBRegion'             # Escenarios/<folder>/
    lvl_name = 'Region.lvl'
    template = '58'
    seed = 1789
    att = (37500.0, 12000.0)        # attacker / defender deployment centres
    dfn = (37500.0, 63000.0)
    remove_models = ()              # object classes whose instances are removed
    move = {}                       # construction model -> (dx, dz), multiples of 1000 cm
    relocate_sets = ()              # scatter decor V3D (instance at the origin) moved like trees
    default_attrs = dict(type=TT['ZONA_VERDE'], a=1)
    clima_from = None               # scenario whose Clima.sb / DatosBatalla.sb are used (default template)
    sky_from = None                 # scenario whose skybox.V3D (+ texture) and fog colour are used
    provinces = ()                  # province enum keys that fight on this map
    objective_key = None            # original province whose objective texts match the conditions
    preview_key = None              # original province whose quick-game picture fits the map
    obj_loc = 'LOC_Aldea'           # location of the objective (intro camera 2)
    pano = (37500.0, 37500.0)       # intro camera 1
    texts = {}
    blend = 3500.0                  # height blend from the kept core into the new relief (cm)
    tex_core = (500.0, 1400.0)      # texture blend from the kept core into the new texture
    core_tint = 0.0                 # 0..1: colour of the kept core's texture pulled to the new surroundings
    steep_deg = 40.0                # impassable above this slope (outside the core)
    block = 25000.0                 # sector map pre-cut (largest original sector: 11 ha)
    palms = False                   # palm-crown shadows instead of round canopies
    fir_shadows = False             # long fir silhouettes in snow (the 21 / 39 / 19 painting) instead of canopies
    shadow = dict(length=92.0, width=21.0, strength=0.42, direction=(-0.55, -0.83))   # canopy shadows (texture px)
    details = ()                    # extra detail previews: world (x, z)
    core_free = {}                  # V3D set -> share of its nodes inside the core that are moved anyway
    outside_take = {}               # V3D set -> share of its nodes OUTSIDE the map moved in (outside scenery sets)
    retype = {}                     # kept template sector type -> type (cosmetic ARIDO / ZONA_VERDE only)

    # ---- hooks
    def core_shapes(self, ctx):
        """Shapely geometries (template coords) whose template sectors are kept verbatim."""
        return []

    def design(self, ctx):
        raise NotImplementedError

    def regions(self, ctx):
        return []

    def tree_prob(self, ctx, model):
        """N x N weights for new tree / decor positions of a V3D set."""
        return np.ones((N, N))

    def conditions(self, ctx):
        """Return None to keep the template's victory conditions and zones."""
        return None

    def texture(self, ctx):
        raise NotImplementedError

    def sounds(self, ctx):
        return []

    def tex_core_geom(self, ctx):
        """Where the template's own painting is kept (default: the whole kept core)."""
        return ctx.core_union

    # ---- helpers (template coordinates; for core_shapes / conditions)
    @staticmethod
    def water_geom(ctx, types=('RIO_PROFUNDO', 'RIO_POCO_PROFUNDO', 'TERRENO_HELADO'), special=True):
        """Union of the template's water / ice sectors and (special=True) the walk-geometry sectors (bridges)."""
        from shapely.ops import unary_union
        sm0 = ctx.m.get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        tt = {TT[t] for t in types}
        return unary_union([P[s['id']] for s in sm0['sectors'] if s['type'] in tt or (special and s.get('special'))])

    @staticmethod
    def cons_geom(ctx, models, pad=0.0):
        """Footprint of the instances of some object models: their construction sectors and their origin."""
        from shapely.geometry import Point
        from shapely.ops import unary_union
        m = ctx.m
        sm0 = m.get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        ob = m.get(lvl.OBJECTLIST)
        out = []
        for o in ob['instances']:
            if ob['library'][o['cls']]['model'] in models:
                out += [P[s] for s in m.construction_sectors(o) if s in P]
                out.append(Point(o['matrix'][12], o['matrix'][14]).buffer(600.0))
        g = unary_union(out)
        return g.buffer(pad) if pad else g

    @staticmethod
    def zone_conditions(ctx, models, name='AreaAldea', r=2600.0, duration=25.0):
        """One objective zone (clockwise hull of circles around the instances of some models) and the victory
        conditions 'annihilation OR hold the zone' for both sides (as the Egypt map: 'Control the Village')."""
        from shapely.geometry import MultiPoint
        ob = ctx.m.get(lvl.OBJECTLIST)
        pts = []
        for o in ob['instances']:
            if ob['library'][o['cls']]['model'] in models:
                x, z = o['matrix'][12], o['matrix'][14]
                pts += [(x + r * math.cos(k * math.pi / 6), z + r * math.sin(k * math.pi / 6)) for k in range(12)]
        hull = MultiPoint(pts).convex_hull.simplify(300)
        ring = [[float(x), float(z)] for x, z in list(hull.exterior.coords)[:-1]]
        if hull.exterior.is_ccw:
            ring = ring[::-1]
        zone = dict(name=name, type=1, bando=3, poly=ring)
        return [zone], dict(attacker=[[[lvl.SUB_ANIQUILACION, 100]], [[lvl.SUB_PROTECCION_ZONA, name]]],
                            defender=[[[lvl.SUB_ANIQUILACION, 100]], [[lvl.SUB_PROTECCION_ZONA, name]]],
                            duration=duration, countdown=duration)

    # ---- pipeline
    def build(self):
        from shapely.geometry import Point, Polygon, box
        from shapely.ops import unary_union
        import shapely.affinity as aff
        rng = np.random.default_rng(self.seed)
        ctx = type('Ctx', (), {})()
        ctx.rng = rng
        ctx.m = m = lvl.load(scen_lvl(self.template))
        ctx.h0 = h0 = m.heights().astype(float)
        ctx.k0, ctx.L = fit_shade(m)
        ob = m.get(lvl.OBJECTLIST)
        sm0 = m.get(lvl.SECTORMAP)
        P0 = sm0['points']
        polys0 = lvl_nav.sector_polygons(sm0)
        model = lambda o: ob['library'][o['cls']]['model']             # noqa: E731
        # --- removed instances (their interior sectors go with them)
        rem = [i for i, o in enumerate(ob['instances']) if model(o) in self.remove_models]
        rem_sids = {s for i in rem for s in m.construction_sectors(ob['instances'][i])}
        cons = [o for i, o in enumerate(ob['instances']) if o['type'] == lvl.TO_CONSTRUCCION and i not in rem]
        # --- the core: template sectors inside it are kept verbatim
        core_geom = unary_union(self.core_shapes(ctx) or [Point(-9e5, -9e5).buffer(1)])
        keep_ids = {s['id'] for s in sm0['sectors']
                    if s['id'] not in rem_sids and polys0[s['id']].within(core_geom)}
        moved = {}                                                     # sector id -> (dx, dz, dy)
        ctx.moved_cons = []
        for o in cons:
            interior = [s for s in m.construction_sectors(o) if sm0['sectors'][s]['type'] == TT['INTERIOR']]
            if model(o) in self.move:
                dx, dz = self.move[model(o)]
                ctx.moved_cons.append((o, dx, dz, interior))
                for s in interior:
                    moved[s] = (dx, dz)
                    keep_ids.discard(s)
            else:
                keep_ids |= set(interior)                            # unmoved buildings keep their interiors
        # close the core: template sectors mostly inside it, or small ones wedged between kept sectors, are kept
        # too (else thin gaps between kept polygons are left for the generator)
        adj = {}
        for a_, b_, i_, j_ in sm0['links']:
            adj.setdefault(a_, set()).add(b_); adj.setdefault(b_, set()).add(a_)
        movers = set(moved)
        for _ in range(4):
            add = set()
            for s in sm0['sectors']:
                sid = s['id']
                if sid in keep_ids or sid in rem_sids or sid in movers:
                    continue
                pg = polys0[sid]
                nk = len(adj.get(sid, set()) & keep_ids)
                if nk and (pg.intersection(core_geom).area > 0.6 * pg.area or (pg.area < 2e5 and nk >= 2)):
                    add.add(sid)
            if not add:
                break
            keep_ids |= add
        ctx.core_union = unary_union([polys0[s] for s in keep_ids]) if keep_ids else Point(-9e5, -9e5).buffer(1)
        ctx.core_geom = core_geom
        ctx.removed = rem
        # --- heights
        hd = self.design(ctx).astype(float)
        for cx, cz in (self.att, self.dfn):                           # deployment plateaus
            w = 1 - smoothstep(6500, 13000, np.hypot(GX - cx, GZ - cz))
            hd = hd * (1 - 0.85 * w) + ndimage.gaussian_filter(hd, 6) * 0.85 * w
        # moved buildings: a copy of their template ground (shifted), flattened only at the rim
        ctx.pads = []
        for o, dx, dz, interior in ctx.moved_cons:
            foot = unary_union([polys0[s] for s in interior])
            foot_new = aff.translate(foot, dx, dz)
            x0, z0 = o['matrix'][12], o['matrix'][14]
            hp = float(ndimage.map_coordinates(ndimage.gaussian_filter(hd, 2), [[(z0 + dz) / CELL], [(x0 + dx) / CELL]],
                                               order=1)[0])
            dy = hp - o['matrix'][13]
            assert not foot_new.buffer(1000.0).intersects(ctx.core_union), ('moved %s overlaps the kept core' % model(o))
            assert foot_new.bounds[0] > 3000 and foot_new.bounds[1] > 3000 and foot_new.bounds[2] < SIZE - 3000                 and foot_new.bounds[3] < SIZE - 3000
            src = ndimage.map_coordinates(h0, [(GZ - dz) / CELL, (GX - dx) / CELL], order=1, mode='nearest') + dy
            dist = np.hypot(GX - foot_new.centroid.x, GZ - foot_new.centroid.y)
            r = math.sqrt(foot_new.area / math.pi) + 900.0
            w = 1 - smoothstep(r, r + 1800.0, dist)
            hd = hd * (1 - w) + src * w
            ctx.pads.append((o, dx, dz, dy, foot_new))
        # the core: template heights, blended out
        inside = grid_mask(ctx.core_union, pad=CELL * 1.5)
        dist = ndimage.distance_transform_edt(~inside) * CELL
        wk = 1 - smoothstep(0.0, self.blend, dist)
        h = hd * (1 - wk) + h0 * wk
        # map edge: the template's heights (the outside scenery continues them)
        A = band(GX, GZ, 1200.0, 8000.0)
        h = h0 * (1 - A) + h * A
        ctx.wk = wk
        ctx.h = h = h.astype(np.float32)
        m.set_heights(h, make_shade(ctx.k0, ctx.L), carry=False)

        def H(x, z):
            return float(m.height_at(x, z, h))
        ctx.H = H
        # --- constructions follow (moved ones by their pad, the others by the height change under them)
        sec_shift = {}
        core_c = ctx.core_union.buffer(CELL)
        for o in cons:
            mv = next((p for p in ctx.pads if p[0] is o), None)
            if mv:
                _, dx, dz, dy, _ = mv
            else:                                                     # in the core the ground is the template's
                dx = dz = 0.0
                x0, z0 = o['matrix'][12], o['matrix'][14]
                dy = 0.0 if core_c.contains(Point(x0, z0)) else H(x0, z0) - o['matrix'][13]
            if dx or dz or dy:
                lvl.shift_instance(o, dx, dy, dz)
            for s in m.construction_sectors(o):
                if s in keep_ids or s in moved:
                    sec_shift[s] = (dx, dy, dz)
        for s in keep_ids:
            sec_shift.setdefault(s, (0.0, 0.0, 0.0))
        ctx.keep_polys = unary_union([Point(0, 0).buffer(0)] + [
            aff.translate(polys0[s], sec_shift[s][0], sec_shift[s][2]) for s in sec_shift])
        # --- vegetation
        ctx.trees_xyz = []
        ctx.sets = {}
        md = os.path.join(scen_dir(self.template), 'Models')
        sets = [model(o) for o in ob['instances'] if o['type'] == lvl.TO_ARBOL] + list(self.relocate_sets)
        for name in sets:
            tv = bytearray(open(os.path.join(md, name), 'rb').read())
            self.relocate(ctx, name, tv)
            ctx.sets[name] = tv
        # --- sector map
        keep = []
        for s in sorted(sec_shift):
            dx, dy, dz = sec_shift[s]
            sd = dict(sm0['sectors'][s])
            sd['p1'] = [sd['p1'][0] + dx, sd['p1'][1] + dy, sd['p1'][2] + dz]
            if sd.get('special'):
                sd['special'] = dict(verts=[[v[0] + dx, v[1] + dy, v[2] + dz] for v in sd['special']['verts']],
                                     idx=list(sd['special']['idx']))
            keep.append(([(P0[i][0] + dx, P0[i][2] + dz, P0[i][1] + dy) for i in sm0['sectors'][s]['poly']], sd))
        regions = []
        sl = slope_deg(h)
        steep = mask_polygons(ndimage.binary_opening(sl > self.steep_deg, iterations=1), simplify=300.0, min_cells=8)
        if steep is not None:
            regions.append((steep, dict(type=TT['OBSTACULO'], a=0)))
        regions += self.regions(ctx)
        # the originals' ranges (tools/lvl_audit.py): edges >= 29 cm, <= 14 vertices and <= 14 links per sector;
        # outline simplification is varied until the generated pieces fit, big pieces are split along a diagonal
        # pre-cut of the open ground into blocks (as regions of the default type, under every other region), with
        # varying offsets: a cut line ending on a kept polygon's edge next to one of its vertices makes a too short edge
        def blocks(off):
            from shapely.geometry import box as bx
            xs = [0.0] + [off + k * self.block for k in range(1, 5) if 2000 < off + k * self.block < SIZE - 2000] + [SIZE]
            return [(bx(xs[i], xs[j], xs[i + 1], xs[j + 1]), dict(self.default_attrs)) for i in range(len(xs) - 1)
                    for j in range(len(xs) - 1)]
        tries = [(simp, off) for off in (0.0, -4100.0, 3700.0, -8300.0, 7900.0, -1900.0) for simp in (40.0, 55.0)]
        for simp, blk in tries:
            sm, kmap = lvl_nav.build(SIZE, blocks(blk) + regions, keep, height=H,
                                     attrs_default=dict(self.default_attrs, occl=0, c=0), simplify=simp)
            split_big(sm, set(kmap.values()))
            met = sector_metrics(sm)
            bad = lvl_nav.validate(sm, SIZE)
            if bad:
                print('  sector map (simplify %.0f, cut offset %.0f) invalid: %s' % (simp, blk, bad[:2]))
                continue
            print('  sector map (simplify %.0f, cut offset %.0f): %d sectors, min edge %.1f cm, max %d vertices, max %d links'
                  % (simp, blk, len(sm['sectors']), met['min_edge'], met['max_v'], met['max_links']))
            if met['min_edge'] >= 29.1 and met['max_v'] <= 14 and met['max_links'] <= 14:
                break
        else:
            raise AssertionError('no sector map inside the originals\' ranges')
        kept_new = set(kmap.values())
        for s_ in sm['sectors']:
            if s_['id'] in kept_new and s_['type'] in self.retype:     # cosmetic types only (footsteps)
                s_['type'] = self.retype[s_['type']]
            if s_['type'] != TT['INTERIOR'] and not s_.get('special'):
                s_['c'] = 1 if math.degrees(math.acos(max(-1.0, min(1.0, abs(s_['p2'][1]))))) > 10 else 0
        probs = lvl_nav.validate(sm, SIZE)
        assert not probs, probs[:5]
        m.chunk(lvl.SECTORMAP).data = sm
        old_ids = sorted(sec_shift)
        m.remap_sector_ids({old_ids[k]: new for k, new in kmap.items()})
        m.chunk(lvl.GRAFOIA).data = lvl_nav.build_graph(sm, 20)
        if rem:
            m.remove_instances(rem)
            used = sorted({o['cls'] for o in ob['instances']})         # classes without instances go too (their
            remap = {old: i for i, old in enumerate(used)}            # files are not shipped); ctype is not a
            ob['library'] = [ob['library'][i] for i in used]          # class index, nothing else refers to it
            for o in ob['instances']:
                o['cls'] = remap[o['cls']]
        # --- logic
        tl = m.get(lvl.TERRAINLOGIC)
        inner = h[20:-20, 20:-20]
        tl['planes'] = [float(np.percentile(inner, 50)), float(np.percentile(inner, 95))]
        posts = m.get(lvl.POSTROOPER)
        zones = m.get(lvl.ARBZONES)
        for side, bando, me, enemy in ((4, 1, self.att, self.dfn), (8, 0, self.dfn, self.att)):
            grp = [p for p in posts if p['flags'] & side]
            assert all(p['route'] is None for p in grp)
            c0 = (float(np.mean([p['pos'][0] for p in grp])), float(np.mean([p['pos'][2] for p in grp])))
            a_old = math.atan2(np.mean([math.sin(p['angle']) for p in grp]), np.mean([math.cos(p['angle']) for p in grp]))
            d = facing_angle(me, enemy) - a_old
            cd, sd_ = math.cos(d), math.sin(d)

            def tr(x, z):                                             # clockwise by d, like the angles
                ox, oz = x - c0[0], z - c0[1]
                return me[0] + cd * ox + sd_ * oz, me[1] - sd_ * ox + cd * oz
            for p in grp:
                p['pos'][0], p['pos'][2] = tr(p['pos'][0], p['pos'][2])
                p['pos'][1] = H(p['pos'][0], p['pos'][2])
                p['angle'] = float(p['angle'] + d)
            # deployment zone: like the originals' hand-drawn ones, a loose polygon around the side's troop areas
            from shapely.geometry import MultiPoint
            corners = []
            for p in grp:
                ca, sa = math.cos(p['angle']), math.sin(p['angle'])
                w_, h_ = p['size']
                corners += [(p['pos'][0] + ca * dx_ + sa * dz_, p['pos'][2] - sa * dx_ + ca * dz_)
                            for dx_, dz_ in ((-w_ / 2, -h_ / 2), (w_ / 2, -h_ / 2), (w_ / 2, h_ / 2), (-w_ / 2, h_ / 2))]
            hull = MultiPoint(corners).convex_hull.buffer(3200.0, 2).simplify(900.0)
            ring = [[min(max(float(x), 300.0), SIZE - 300.0), min(max(float(z), 300.0), SIZE - 300.0)]
                    for x, z in list(hull.exterior.coords)[:-1]]
            if Polygon(ring).exterior.is_ccw:                         # same winding as the originals' zones
                ring = ring[::-1]
            for a in zones:
                if a['type'] == 2 and a['bando'] == bando:
                    a['poly'] = ring
        cond = self.conditions(ctx)
        if cond is not None:
            zs, c = cond
            m.get(lvl.ARBZONES)[:] = [a for a in zones if a['type'] == 2] + zs
            m.get(lvl.CONDICIONES).update(c)
        else:                                                         # template zones follow moved buildings
            for a in zones:
                if a['type'] != 2:
                    for o, dx, dz, dy, foot in ctx.pads:
                        if Point(*np.mean(a['poly'], 0)).distance(foot) < 2500:
                            a['poly'] = [[x + dx, z + dz] for x, z in a['poly']]
        locs = m.get(lvl.LOCATIONS)
        for l in locs:
            if l['name'] == 'LOC_Atacante':
                l['pos'][0], l['pos'][2] = self.att
                l['angles'][1] = float(facing_angle(self.att, self.dfn))
            elif l['name'] == 'LOC_Defensor':
                l['pos'][0], l['pos'][2] = self.dfn
                l['angles'][1] = float(facing_angle(self.dfn, self.att))
            else:
                for o, dx, dz, dy, foot in ctx.pads:
                    if Point(l['pos'][0], l['pos'][2]).distance(aff.translate(foot, -dx, -dz)) < 1500:
                        l['pos'][0] += dx
                        l['pos'][2] += dz
            self.place_location(ctx, l)
            l['pos'][1] = H(l['pos'][0], l['pos'][2]) - l.get('ybias', 0.0)
        locs.append(dict(type=0, name='LOC_Panorama', uid=0, pos=[self.pano[0], H(*self.pano) + 1500.0, self.pano[1]],
                         angles=[0.0, 0.0], particles=locs[-1]['particles'], ciclico=0, frames=0, escala=1.0, ybias=0.0))
        snd = m.get(lvl.SOUND)
        for e in snd['positional']:
            e[4][1] = H(e[4][0], e[4][2]) + 300.0
        snd['positional'] += [[n_, v_, r1, r0, [x, H(x, z) + 300.0, z]] for n_, v_, r1, r0, x, z in self.sounds(ctx)]
        if self.sky_from:
            m.get(lvl.ENVIRONMENT)['fog_color'] = lvl.load(scen_lvl(self.sky_from)).get(lvl.ENVIRONMENT)['fog_color']
        ctx.locs = {l['name']: (l['pos'][0], l['pos'][2]) for l in locs if l.get('name')}
        self.ctx = ctx
        return ctx

    def place_location(self, ctx, l):
        pass

    def relocate(self, ctx, name, tv):
        """Move the trees / decor nodes of one V3D set: nodes in the kept core and outside the map stay, the
        others go to new positions drawn from tree_prob (the rest sink out of sight); then the set's box."""
        from shapely.geometry import Point
        from shapely.prepared import prep
        T = lvl_v3d.trees(tv)
        H = ctx.H
        free, stay = [], []
        core = prep(ctx.core_union.buffer(400))
        take = self.outside_take.get(name, 0.0)
        for t, c in T:
            x, y, z = lvl_v3d.translation(tv, t['m2'])
            if not (0 <= x <= SIZE and 0 <= z <= SIZE):
                if take and ctx.rng.random() < take:                  # (no rng draw without outside_take)
                    free.append((t, c))
                else:
                    stay.append((t, c))
            elif core.contains(Point(x, z)) and ctx.rng.random() >= self.core_free.get(name, 0.0):
                stay.append((t, c))
            else:
                free.append((t, c))
        pts = scatter(self.tree_prob(ctx, name), len(free), ctx.rng, min_dist=self.tree_min_dist(name))
        for (trunk, canopies), (x, z) in zip(free, pts):
            x0, y0, z0 = lvl_v3d.translation(tv, trunk['m2'])
            y = H(x, z) - 15.0
            lvl_v3d.move_tree(tv, trunk, canopies, x - x0, y - y0, z - z0)
            if self.shadows(name):                                    # (the core's trees are painted already)
                ctx.trees_xyz.append((x, y, z))
        for trunk, canopies in free[len(pts):]:
            lvl_v3d.move_tree(tv, trunk, canopies, 0.0, -20000.0, 0.0)
        allp = np.array([lvl_v3d.translation(tv, t['m2']) for t, c in T])
        lvl_v3d.set_global_bbox(tv, [float(allp[:, 0].min() - 800), float(allp[:, 1].min() - 50), float(allp[:, 2].min() - 800)],
                                [float(allp[:, 0].max() + 800), float(allp[:, 1].max() + 2500), float(allp[:, 2].max() + 800)])
        print('  %s: %d moved, %d kept, %d sunk' % (name, len(pts), len(stay), len(free) - len(pts)))

    def tree_min_dist(self, name):
        return 650.0

    def shadows(self, name):
        return True

    # ---- texture finishing (shared)
    def finish_texture(self, ctx, img):
        rng = np.random.default_rng(self.seed + 5)
        tmpl = composite(self.template).astype(np.float32)
        # kept core: the template's own painting (water banks, yards, its trees' shadows), optionally tinted
        core = raster(self.tex_core_geom(ctx), 1024)
        dist = ndimage.distance_transform_edt(~core) * (SIZE / 1024)
        w = up(1 - smoothstep(self.tex_core[0], self.tex_core[1], dist))
        if self.core_tint:                                            # colour of the new surroundings
            ring = up(((dist > 1500) & (dist < 6000)).astype(np.float32)) > 0.5
            gain = (img[ring].reshape(-1, 3).mean(0) + 1) / (tmpl[ring].reshape(-1, 3).mean(0) + 1)
            gain = 1 + self.core_tint * (gain - 1)
            tmpl = tmpl * gain[None, None, :].astype(np.float32)
        img = img * (1 - w[..., None]) + tmpl * w[..., None]
        del tmpl
        # tree shadows (cast north-west, as painted in the originals) for the moved trees
        tpx = [tuple(lvl_tex.world_to_px(x, z, SIZE, TEX)) for x, y, z in ctx.trees_xyz]
        if self.palms:
            img *= palm_shadows((TEX, TEX), tpx, rng)[..., None]
        elif self.fir_shadows:
            s = fir_shadows((TEX, TEX), tpx, rng, **self.fir_shadows)
            img *= 1.0 - s[..., None] * np.array(self.fir_shadows.get('tint_k', (0.56, 0.52, 0.38)), np.float32)
        else:
            img *= lvl_tex.tree_shadows((TEX, TEX), tpx, rng, **self.shadow)[..., None]
        return np.clip(img + 0.5, 0, 255).astype(np.uint8)

    def paint_tracks(self, img, tracks, colour, noise, hf, width=(4.0, 11.0), alpha=0.5, rut=0.12):
        """Dirt tracks like the originals' paths: a few metres wide, soft ragged edges, the ground's grain kept,
        two faint ruts."""
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        lum = img.mean(-1, keepdims=True)
        detail = lum / (ndimage.uniform_filter(lum[..., 0], 31)[..., None] + 1.0)
        pc = np.array(colour, np.float32)
        for line in tracks:
            pl = [tuple(lvl_tex.world_to_px(x, z, SIZE, TEX)) for x, z in line]
            dd, _, _ = lvl_tex.polyline_frame(cols, rows, pl)
            dd = up(dd)
            w_p = (1 - smoothstep(width[0], width[1], dd + (noise - 0.5) * 7 + (hf - 0.5) * 7)) * alpha
            r_ = 1 - rut * np.exp(-((np.abs(dd) - width[0] * 0.8) / 1.4) ** 2)
            img = img * (1 - w_p[..., None]) + (pc * (0.6 + 0.4 * detail) * r_[..., None]) * w_p[..., None]
        return img

    def baked_light(self, ctx, strength=1.0):
        """Relief light painted into the texture like the originals: (TEX, TEX) factor around 1 from N.L of the new
        heights (the template's sun), scaled by how much light the template's texture carries."""
        k0, L = ctx.k0, ctx.L
        nl = normals(ctx.h) @ L
        nl0 = normals(ctx.h0) @ L
        lum0 = ndimage.zoom(composite(self.template).astype(np.float32).mean(-1), N / TEX, order=1)[:N, :N][::-1]
        ok = np.isfinite(lum0)
        b = np.polyfit(nl0[ok].ravel(), lum0[ok].ravel(), 1)
        gain = max(0.0, b[0] / max(1.0, lum0.mean()))                  # relative brightness per unit N.L
        f = 1 + strength * gain * (nl - nl.mean())
        return up(np.clip(f, 0.75, 1.2)[::-1].astype(np.float32))

    # ---- scenario folder
    def write(self):
        ctx = self.ctx
        m = ctx.m
        out = os.path.join(BM, self.folder)
        mdir = os.path.join(out, 'Models')
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.makedirs(mdir)
        m.save(os.path.join(out, self.lvl_name))
        src = os.path.join(scen_dir(self.template), 'Models')
        t = m.get(lvl.TERRAIN)
        tiles = {mt[2].lower() for mt in t['materials']}
        ob = m.get(lvl.OBJECTLIST)
        # files only the removed classes need are left out
        lib0 = lvl.load(scen_lvl(self.template)).get(lvl.OBJECTLIST)['library']
        used = {c['model'].lower() for c in ob['library']} | {a.lower() for c in ob['library']
                                                                for md_ in c.get('modules', []) for a in md_['anis']}
        removed = {c['model'].lower() for c in lib0 if c['model'] in self.remove_models}
        removed |= {a.lower() for c in lib0 if c['model'] in self.remove_models for md_ in c.get('modules', [])
                    for a in md_['anis']}

        def refs(fn):
            p = find_file(src, fn)
            if not p:
                return set()
            import re
            return {r.decode('latin1').lower() for r in re.findall(rb'[A-Za-z0-9_ .\-]+\.(?:tga|dds|bmp|jpg)', open(p, 'rb').read())}
        need = set()
        for fn in os.listdir(src):
            if fn.lower().endswith('.v3d') and fn.lower() not in removed:
                need |= refs(fn)
        drop = set(removed)
        for fn in removed:
            drop |= refs(fn) - need
        nb = 0
        for fn in os.listdir(src):
            low = fn.lower()
            if low.endswith('.scc') or low in tiles or fn in ctx.sets or low in drop:
                continue
            shutil.copyfile(os.path.join(src, fn), os.path.join(mdir, fn))
            nb += 1
        for name, tv in ctx.sets.items():
            open(os.path.join(mdir, name), 'wb').write(bytes(tv))
        if self.sky_from:                                             # sky of another map (same skybox name)
            ssrc = os.path.join(scen_dir(self.sky_from), 'Models')
            sky = m.get(lvl.ENVIRONMENT)['skybox']
            old = refs_of(find_file(mdir, sky))
            p = find_file(mdir, sky)
            if p:
                os.remove(p)
            for f in [sky] + sorted(refs_of(find_file(ssrc, sky))):
                p = find_file(ssrc, f)
                if p:
                    shutil.copyfile(p, os.path.join(mdir, os.path.basename(p)))
            still = set()
            for fn in os.listdir(mdir):
                if fn.lower().endswith('.v3d'):
                    still |= refs_of(os.path.join(mdir, fn))
            for f in old - still:                                     # the template's sky texture, now unused
                p = find_file(mdir, f)
                if p:
                    os.remove(p)
        names = [mt[2] for mt in t['materials']]
        n = TEX // 4
        import tga
        for r in range(4):
            for c in range(4):
                y0 = (3 - r) * n
                tga.write_dds_dxt1_mips_np(os.path.join(mdir, names[r * 4 + c]),
                                           np.ascontiguousarray(ctx.tex[y0:y0 + n, c * n:(c + 1) * n]))
        cdir = scen_dir(self.clima_from or self.template)
        shutil.copyfile(find_file(cdir, 'Clima.sb'), os.path.join(out, 'Clima.sb'))
        if find_file(cdir, 'DatosBatalla.sb'):
            shutil.copyfile(find_file(cdir, 'DatosBatalla.sb'), os.path.join(out, 'DatosBatalla.sb'))
        a_att = math.degrees(math.atan2(self.dfn[0] - self.att[0], self.dfn[1] - self.att[1]))
        a_def = math.degrees(math.atan2(self.att[0] - self.dfn[0], self.att[1] - self.dfn[1]))
        fa = np.array(self.dfn) - np.array(self.att)
        fa /= np.linalg.norm(fa)
        ta = np.array(self.att) - 1500 * fa
        td = np.array(self.dfn) + 3000 * fa
        open(os.path.join(out, 'Camara.sb'), 'w', encoding='latin1', newline='\r\n').write(
            CAMARA % (self.name, self.folder, 19.0, a_att, ta[0], ta[1], 24.0, a_def, td[0], td[1]))
        for side, fn in (('ATACANTE', 'introAtacante.lua'), ('DEFENSOR', 'introDefensor.lua')):
            open(os.path.join(out, fn), 'w', encoding='latin1', newline='\r\n').write(
                INTRO % dict(name=self.name, folder=self.folder, side=side, key=self.key, obj=self.obj_loc))
        mm = minimap(ctx.tex, ctx.h, ctx.k0, ctx.L, m)
        red = np.zeros((256, 256, 3), np.uint8)
        red[0:146, 0:146] = (252, 0, 255)
        red[1:145, 1:145] = np.asarray(ndimage.zoom(mm[:231, :231, :3].astype(np.float32), (144 / 231, 144 / 231, 1),
                                                    order=1)).clip(0, 255).astype(np.uint8)[:144, :144]
        mname = self.folder + '.tga'
        lvl_tex.write_tga24(os.path.join(BM, 'minimap_red', mname), red)
        lvl_tex.write_tga32(os.path.join(BM, 'minimap', mname), mm)
        info = dict(folder=self.folder, lvl=self.lvl_name, minimap=mname, minimap_red=mname, template=self.template,
                    texts=self.texts, provinces=list(self.provinces), objective_key=self.objective_key,
                    preview_key=self.preview_key, rotacion='.AT 0  .DF 180', recipe='tools/lvl_region.py ' + self.name)
        json.dump(info, open(os.path.join(out, 'battlemap.json'), 'w', encoding='utf8'), indent=1)
        print('  wrote', out, '(%d template files)' % nb)
        return mm

    def previews(self, mm):
        ctx = self.ctx
        os.makedirs(PREVIEW, exist_ok=True)
        pre = os.path.join(PREVIEW, 'lvl_%s_' % self.name)
        lvl_tex.save_png(pre + 'heightmap.png', height_image(ctx.h))
        td = topdown(ctx.tex, ctx.h, ctx.k0, ctx.L)
        lvl_tex.save_png(pre + 'topdown.png', td)
        td0 = topdown(composite(self.template), ctx.h0, ctx.k0, ctx.L)
        lvl_tex.save_png(pre + 'compare.png', np.concatenate([td0[::2, ::2], np.full((512, 8, 3), 255, np.uint8),
                                                              td[::2, ::2]], 1))
        lvl_tex.save_png(pre + 'overlay.png', overlay(td, ctx.m))
        lvl_tex.save_png(pre + 'minimap.png', mm[..., :3])
        cx, cz = ctx.locs.get(self.obj_loc, (SIZE / 2, SIZE / 2))
        c, r = (int(v) for v in lvl_tex.world_to_px(cx, cz, SIZE, TEX))
        c, r = min(max(c, 600), TEX - 600), min(max(r, 600), TEX - 600)
        sh = ndimage.zoom(np.clip(ctx.k0 + normals(ctx.h) @ ctx.L, 63 / 255.0, 1.0)[::-1], TEX / N, order=1)[:TEX, :TEX]
        crop = ctx.tex[r - 500:r + 500, c - 500:c + 500].astype(np.float32) * sh[r - 500:r + 500, c - 500:c + 500, None] * 1.9
        lvl_tex.save_png(pre + 'detail.png', np.clip(crop, 0, 255).astype(np.uint8))
        for k, (x, z) in enumerate(self.details):
            c, r = (int(v) for v in lvl_tex.world_to_px(x, z, SIZE, TEX))
            c, r = min(max(c, 500), TEX - 500), min(max(r, 500), TEX - 500)
            crop = ctx.tex[r - 500:r + 500, c - 500:c + 500].astype(np.float32) * sh[r - 500:r + 500, c - 500:c + 500, None] * 1.9
            lvl_tex.save_png(pre + 'detail%d.png' % (k + 2), np.clip(crop, 0, 255).astype(np.uint8))
        print('  previews', pre + '*.png')


def refs_of(path):
    import re
    if not path or not os.path.exists(path):
        return set()
    return {r.decode('latin1').lower() for r in re.findall(rb'[A-Za-z0-9_ .\-]+\.(?:tga|dds|bmp|jpg)', open(path, 'rb').read())}


CAMARA = '''#---------------------------------------------
#    Script de definicion de camara de mapa (%s, Escenarios/%s, tools/lvl_region.py)
#---------------------------------------------
.ATACANTE
[
  .ANGLE     [ %.1f    %.1f    ]
  .TARGET    [ %.1f  %.1f   ]

]
.DEFENSOR
[
  .ANGLE     [ %.1f    %.1f    ]
  .TARGET    [ %.1f  %.1f   ]

]
'''
INTRO = '''-- --------------------------------------------
-- %(name)s (Escenarios/%(folder)s, generated by tools/lvl_region.py; same structure as the 93 Caucasus intro)
-- --------------------------------------------
function inicia_secuencia()
  estado_defecto_secuencia()
  secuencia1();
end

-- panorama of the battlefield (a camera relative to a location adapts to the new relief)
function secuencia1 ()
  estado_defecto_secuencia()
  muestra_tropas_amigas()
  local time1 = nil
  local time2 = nil
  local maxTime = nil
  time1 = reproduce_camara_relativa ("game/gameModes/Batalla/Camaraspresentacion/CamaraEdifBg01.V3D", "LOC_Panorama", false, 1.6 )
  time2 = reproduce_texto ("LTEXT_TEXTUISECUENCIAS_%(key)s_%(side)s_1")
  maxTime = max (time1, time2)
  temporizador ( maxTime, "secuencia2" )
  fade_color (0,0,0,150, 0,0,0,0,  -0,0.5)
  fade_color (204,215,228,0, 204,215,228,255,    maxTime-0.5,0.5)
end

-- the objective
function secuencia2 ()
  estado_defecto_secuencia()
  muestra_tropas_amigas()
  local time1 = nil
  local time2 = nil
  local maxTime = nil
  time1 = reproduce_camara_relativa ("game/gameModes/Batalla/Camaraspresentacion/CamaraEdifBg03.V3D", "%(obj)s", false, 0.9 )
  time2 = reproduce_texto ("LTEXT_TEXTUISECUENCIAS_%(key)s_%(side)s_2")
  maxTime = max (time1, time2)
  temporizador ( maxTime, "comenzar_batalla" )
  fade_color (204,215,228,255, 204,215,228,0,0,0.5)
  fade_color (204,215,228,0, 224,235,248,255,maxTime-2,2)
end
'''


# ------------------------------------------------------------------ recipe 1: Arabian desert (58 Tripolitania)
class Desert(Recipe):
    """Dunes in the west, a rocky hamada with mesas in the east, a wadi with rocky banks across the middle and the
    original oasis (pond, palms, two flat-roofed houses, 'oasis' zone) kept in the north."""
    name = 'desert'
    key = 'DESIERTO'
    folder = 'NBDesierto'
    lvl_name = 'NBDesierto.lvl'
    template = '58'
    seed = 1790
    att = (50500.0, 12500.0)
    dfn = (20500.0, 61500.0)
    relocate_sets = ('Arbusto.V3D',)
    core_free = {'Arbusto.V3D': 0.5}                 # half of the oasis scrub goes out into the desert
    default_attrs = dict(type=TT['ARIDO'], a=1)
    provinces = ('ARABIA', 'OMAN', 'W_HEJAZ', 'W_NAJD', 'W_MUSCAT', 'W_YEMEN', 'W_ADAL', 'W_BENADIR',
                 'W_KASHGARIA', 'W_AGADEZ')     # (+ 2026-10-21 second batch: Tarim oases, Air / Agadez)
    objective_key = 'TRIPOLITANIA'
    preview_key = 'TRIPOLITANIA'
    obj_loc = 'LOC_Oasis'
    pano = (40000.0, 31000.0)
    palms = True
    details = ((46500.0, 30000.0), (63000.0, 31000.0))
    OASIS = [(28200, 47200), (31800, 44300), (41200, 43800), (45600, 47200), (46000, 54600), (42400, 59600),
             (36000, 60800), (30200, 59200), (27400, 54200)]
    WADI = [(79000, 25500), (70000, 29000), (61500, 26500), (53000, 30500), (45000, 28500), (37000, 31500),
            (28500, 29500), (19500, 32500), (9500, 30500), (1000, 32500)]
    TRIB = [(76000, 60500), (69500, 53500), (66500, 46500), (61500, 40500), (57500, 35500), (55000, 30500)]
    CROSS = [46500.0, 31000.0]                       # x of the gentle crossings of the main wadi
    BUTTES = [(64500, 15500, 3000, 2100, 0.5, 1200), (69000, 41500, 2400, 3300, -0.3, 1000),
              (51500, 44000, 2300, 1700, 0.9, 900), (11500, 47500, 2100, 1600, 0.2, 700)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_DESIERTO_ATACANTE_1':
            'Sand to the west, rock to the east and a dry wadi between: the desert itself defends these wells. '
            'Cross the wadi where its banks are low.',
        'LTEXT_TEXTUISECUENCIAS_DESIERTO_ATACANTE_2':
            'Our objective is the village by the oasis. Whoever holds the water holds the desert.',
        'LTEXT_TEXTUISECUENCIAS_DESIERTO_DEFENSOR_1':
            'The enemy has marched into the desert, far from any water. Let the sun and the wadi wear them down.',
        'LTEXT_TEXTUISECUENCIAS_DESIERTO_DEFENSOR_2':
            'Hold the village by the oasis. Without its wells they cannot stay here for long.',
    }

    def core_shapes(self, ctx):
        from shapely.geometry import Polygon
        return [Polygon(self.OASIS)]

    def lines(self):
        rng = np.random.default_rng(self.seed + 3)
        return chaikin(self.WADI, rng, 900.0, 3000.0), chaikin(self.TRIB, rng, 700.0, 2500.0)

    def wadi_fields(self, X, Z):
        w1, w2 = self.lines()
        d1, _ = polyline_dist(X, Z, w1)
        d2, _ = polyline_dist(X, Z, w2)
        cross = np.zeros(X.shape)
        for cx in self.CROSS:
            cross = np.maximum(cross, np.exp(-((X - cx) / 3200.0) ** 2) * (Z < 42000))
        return d1, d2, cross

    def masks(self, X, Z, rng_seed=7):
        """Dune sea (west and around the oasis), rocky hamada (south-east), gravel plain (reg) between."""
        rng = np.random.default_rng(self.seed + rng_seed)
        warp = (fbm(X, Z, rng, 22000.0, 4) - 0.5) * 16000.0
        hamada = smoothstep(36000, 46000, X + warp) * (1 - smoothstep(44000, 54000, Z - 0.6 * warp))
        dunes = (1 - smoothstep(22000, 34000, X - 0.7 * warp)) + smoothstep(50000, 60000, Z + 0.5 * warp)
        dunes = np.clip(dunes, 0, 1) * (1 - hamada)
        reg = np.clip(1 - dunes - hamada, 0, 1)
        return dunes, hamada, reg

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        dunes, hamada, reg = self.masks(X, Z)
        base = 800.0 + 600.0 * fbm(X, Z, rng, 30000.0, 3) + 300.0 * (Z / SIZE)
        # transverse dunes: crests across a NNW wind, asymmetric (gentle windward, steep lee), broken and wavy
        t = math.radians(74.0)                                        # crests run WNW-ESE as on 58 / 55
        warp = (fbm(X, Z, rng, 16000.0, 3) - 0.5) * 9000.0
        u = (X * math.cos(t) + Z * math.sin(t)) + warp
        ph = np.mod(u / 9500.0, 1.0)
        prof = np.where(ph < 0.62, ph / 0.62, (1 - ph) / 0.38)
        prof = smoothstep(0.0, 1.0, prof) ** 1.2
        amp = 950.0 * (0.45 + 0.9 * fbm(X, Z, rng, 18000.0, 3)) * (0.55 + 0.45 * fbm(X, Z, rng, 7000.0, 2))
        h = base + dunes * amp * prof + reg * 260.0 * (fbm(X, Z, rng, 6000.0, 3) - 0.5)
        # hamada: a raised rocky table, its edge broken into spurs and bays (thresholded noise)
        rid = fbm(X, Z, rng, 9000.0, 4, ridged=True)
        edge = smoothstep(0.15, 0.85, hamada + 0.3 * (fbm(X, Z, rng, 7000.0, 3) - 0.5))
        h += edge * (1100.0 + 400.0 * rid) + hamada * 250.0 * (rid - 0.5)
        # mesas and buttes: flat tops, steep sides
        for cx, cz, rx, rz, a, hh in self.BUTTES:
            b = blob(X, Z, cx, cz, rx, rz, a, power=3.0)
            h += hh * smoothstep(0.0, 0.6, b) * (0.9 + 0.2 * rid)
        # the wadis: gravel beds 18-28 m wide, ~9 m deep canyons with rock walls in the hamada, fading into the
        # sand in the west; gentle ramps at the two crossings of the main wadi
        d1, d2, cross = self.wadi_fields(X, Z)
        rock = np.clip(edge * 1.3, 0, 1)
        fade = smoothstep(4000.0, 26000.0, X)
        for d, half, depth in ((d1, 1100.0 + 300 * fbm(X, Z, rng, 8000.0, 2), 900.0 * (0.35 + 0.65 * fade)),
                               (d2, 800.0, 650.0)):
            wall = 500.0 + 2600.0 * (1 - rock) + 3400.0 * cross
            prof = 1.0 - smoothstep(half, half + wall, d)
            prof = prof ** (1.0 + 1.4 * rock * (1 - cross))
            rim = ndimage.uniform_filter(h, 9)
            h = h * (1 - prof) + (rim - depth * (1 - 0.3 * cross)) * prof
        return h

    def regions(self, ctx):
        """The wadi beds as BARRANCO (a ravine: no hard-coded troop modifier, own footsteps); their rocky walls
        are impassable through the slope rule, the two crossings stay free."""
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        from shapely.geometry import box
        w1, w2 = self.lines()
        bed = unary_union([LineString(w1).buffer(1050.0, 4), LineString(w2).buffer(750.0, 4)])
        # rock walls of the canyons in the hamada: impassable except at the crossings
        dunes, hamada, reg = self.masks(GX, GZ)
        rockm = mask_polygons(hamada > 0.6, simplify=600.0, min_cells=40)
        walls = unary_union([LineString(w1).buffer(2300.0, 4), LineString(w2).buffer(1900.0, 4)])   # bed painted over
        walls = walls.difference(unary_union([box(cx - 3000, 0, cx + 3000, SIZE) for cx in self.CROSS]))
        out = [(bed.difference(ctx.keep_polys.buffer(500)), dict(type=TT['BARRANCO'], a=1))]
        if rockm is not None:
            out.insert(0, (walls.intersection(rockm).difference(ctx.keep_polys.buffer(500)), dict(type=TT['OBSTACULO'], a=0)))
        return out

    def tree_prob(self, ctx, name):
        X, Z = GX, GZ
        d1, d2, cross = self.wadi_fields(X, Z)
        dunes, hamada, reg = self.masks(X, Z)
        sl = slope_deg(ctx.h)
        dv = np.hypot(X - 36300, Z - 51800)
        ok = (sl < 18) & (band(X, Z, 3000, 6000) > 0.5)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9500
        if name == 'Arboles.V3D':                                      # palms: oasis fringe and wadi bed
            p = 3.0 * np.exp(-((dv - 9500) / 2500.0) ** 2) + 1.2 * np.exp(-(np.minimum(d1, d2) / 1100.0) ** 2) * (1 - cross)
            p *= (1 - dunes * 0.8)
        else:                                                          # scrub: wadi edges, gravel plain, hamada
            p = 0.15 + 1.5 * np.exp(-((np.minimum(d1, d2) - 1600) / 1200.0) ** 2) + 0.5 * reg + 0.4 * hamada
            p *= (1 - 0.85 * dunes)
        return p * ok

    def tree_min_dist(self, name):
        return 900.0 if name == 'Arboles.V3D' else 1500.0

    def shadows(self, name):
        return name == 'Arboles.V3D'

    def sounds(self, ctx):
        return [['S_VIENTO', 25, 22000.0, 1200.0, 30000.0, 32000.0], ['S_VIENTO', 25, 20000.0, 1100.0, 62000.0, 40000.0]]

    WILD = [(30000.0, 18500.0), (24500.0, 22500.0), (36500.0, 20500.0), (28500.0, 14000.0)]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: on the gravel plain
            k = getattr(self, '_wk', 0)
            l['pos'][0], l['pos'][2] = self.WILD[k % len(self.WILD)]
            self._wk = k + 1

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c58, c55, c57, c43 = composite('58'), composite('55'), composite('57'), composite('43')
        sandy = lambda r, g, b: r > 170 and g > 125 and b > 75 and r - b > 55      # noqa: E731
        sand = synth(shape, c58, pick_boxes(c58, sandy, k=8), rng, flat=20.0)
        sand2 = synth(shape, c55, pick_boxes(c55, sandy, k=6), rng, flat=20.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 7000.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 380.0, 3), TEX)
        dunes, hamada, reg = (up(a) for a in self.masks(Xw, Zw))
        w2 = np.clip((noise - 0.4) * 2.0, 0, 1)[..., None]
        img = sand * (1 - w2) + sand2 * w2
        del sand, sand2
        # gravel plain / hamada floor: Cirenaica's scrubby reg
        gravelly = lambda r, g, b: 120 < r < 215 and r - b > 40 and g > 90       # noqa: E731
        reg_t = synth(shape, c43, pick_boxes(c43, gravelly, k=8, win=384), rng, flat=30.0)
        w_reg = np.clip(reg * 0.75 + hamada * 0.95 + (fine - 0.5) * 0.9 + (noise - 0.5) * 1.0, 0, 1)
        w_reg = smoothstep(0.25, 0.75, w_reg + (hf - 0.5) * 0.25)
        img = img * (1 - w_reg[..., None]) + reg_t * w_reg[..., None]
        del reg_t
        # rock with crisp, ragged edges: Tunez's wadi walls and Cirenaica's escarpment on steep ground, mesa tops
        slope = up(ndimage.gaussian_filter(slope_deg(ctx.h)[::-1], 0.6), TEX)
        rocky = lambda r, g, b: r < 175 and r - b > 25                           # noqa: E731
        rock = synth(shape, c57, pick_boxes(c57, rocky, k=6, win=256), rng, flat=0, patch=256, step=160) * 0.5 +             synth(shape, c43, pick_boxes(c43, rocky, k=6, win=256), rng, flat=0, patch=256, step=160) * 0.5
        tops = np.zeros((TEX // 4, TEX // 4), np.float32)
        for cx, cz, rx, rz, a, hh in self.BUTTES:
            tops = np.maximum(tops, blob(Xw, Zw, cx, cz, rx * 1.05, rz * 1.05, a, power=3.0))
        tops = up(tops)
        rough = slope + 10.0 * (hf - 0.5) + 8.0 * (fine - 0.5) + 14.0 * tops + 6.0 * hamada * (noise - 0.3)
        w_rock = smoothstep(19.0, 25.0, rough) * 0.95 * np.clip(1 - dunes * 1.2 + tops, 0, 1)   # not on dune lee faces
        img = img * (1 - w_rock[..., None]) + rock * w_rock[..., None]
        del rock
        # the wadi beds: Tunez's light gravel, a faint darker channel; banks shaded
        d1, d2, cross = self.wadi_fields(Xw, Zw)
        d = up(np.minimum(d1, d2))
        light = lambda r, g, b: r > 205 and g > 170 and b > 120                  # noqa: E731
        gravel = synth(shape, c57, pick_boxes(c57, light, k=6, win=256), rng, flat=24.0, patch=256, step=192) *             np.array([0.9, 0.87, 0.82], np.float32)
        bed = 1 - smoothstep(850, 1250, d + 280 * (fine - 0.5) + 220 * (hf - 0.5))
        img = img * (1 - bed[..., None]) + gravel * bed[..., None]
        chan = (1 - smoothstep(80, 420, d + 260 * (hf - 0.5) + 120 * (fine - 0.5))) * 0.12
        img *= (1 - chan)[..., None]
        del gravel
        # caravan tracks: attacker - crossing - oasis, defender camp - oasis, the western route
        tracks = [chaikin([self.att, (48500, 21000), (46500, 28800), (43000, 36500), (39000, 43000)], rng, 600.0),
                  chaikin([self.dfn, (24500, 56500), (29000, 51500)], rng, 500.0),
                  chaikin([(0, 18000), (12000, 24500), (21000, 29000), (31000, 30200), (34500, 38000), (33000, 44000)], rng, 700.0)]
        img = self.paint_tracks(img, tracks, (212, 184, 138), noise, hf, alpha=0.32, rut=0.06)
        # relief light painted in (the originals' dunes carry painted shading) and soft macro patches
        img *= self.baked_light(ctx, 0.6)[..., None]
        img *= (0.93 + 0.14 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 2: Indian river plain (41 Venecia)
class India(Recipe):
    """A green alluvial plain between a river (north-west, two stone bridges) and a fordable stream (wooden
    bridge), mango groves and scattered trees, field patches; the objective is the domed villa (a temple here)
    with the house moved next to it."""
    name = 'india'
    key = 'INDOSTAN'
    folder = 'NBIndia'
    lvl_name = 'NBIndia.lvl'
    template = '41'
    seed = 1791
    att = (34500.0, 11500.0)
    dfn = (52500.0, 64500.0)
    remove_models = ('vina.V3D',)
    move = {'CasaC.V3D': (7000.0, 13000.0)}          # from its hill next to the temple
    provinces = ('W_POONA', 'W_DELHI', 'W_GUJARAT', 'W_MALWA', 'W_BERAR', 'W_ORISSA', 'W_RAJPUTANA', 'W_HYDERABAD',
                 'W_PUNJAB', 'W_MYSORE', 'W_TRAVANCORE', 'W_ASSAM', 'W_PESHAWAR', 'W_MULTAN', 'W_SINDH')
    objective_key = 'EGIPTO'          # 'Control the Village' (the zone holds the temple and the house)
    preview_key = 'VENECIA'
    obj_loc = 'LOC_Palacete'
    pano = (40000.0, 30000.0)
    core_tint = 0.75
    blend = 4000.0
    FIELDS = [(25000, 40000, 6500, 4200, 0.35), (55500, 44000, 5500, 3600, -0.2), (15500, 17500, 5000, 3500, 0.1),
              (60000, 15000, 6000, 3800, 0.45), (33000, 49500, 4200, 3000, -0.5)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_INDOSTAN_ATACANTE_1':
            'A rich plain of fields and groves between the river and the stream. The stream can be forded, '
            'but it will slow our men; the bridges are few.',
        'LTEXT_TEXTUISECUENCIAS_INDOSTAN_ATACANTE_2':
            'The enemy holds the temple and its village by the river. Take it and the province is ours.',
        'LTEXT_TEXTUISECUENCIAS_INDOSTAN_DEFENSOR_1':
            'The enemy comes across the plain. Let them wade the stream under our guns.',
        'LTEXT_TEXTUISECUENCIAS_INDOSTAN_DEFENSOR_2':
            'Hold the temple and the village around it. While they stand, the province stands.',
    }

    def core_shapes(self, ctx):
        from shapely.geometry import Point
        from shapely.ops import unary_union
        sm0 = ctx.m.get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        water = [P[s['id']] for s in sm0['sectors'] if s['type'] in (TT['RIO_PROFUNDO'], TT['RIO_POCO_PROFUNDO'])
                 or s.get('special')]
        ob = ctx.m.get(lvl.OBJECTLIST)
        out = [unary_union(water).buffer(1600.0)]
        for o in ob['instances']:
            if ob['library'][o['cls']]['model'] in ('Palacete.V3D', '41PuenteA.V3D', '41PuenteB.V3D', 'Puentemadera.V3D'):
                out.append(Point(o['matrix'][12], o['matrix'][14]).buffer(3600.0))
        return out

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        hs = ndimage.gaussian_filter(ctx.h0, 9)
        level = 1000.0
        h = level + 0.28 * (hs - level)
        h += 260.0 * (fbm(X, Z, rng, 9000.0, 4) - 0.5) + 180.0 * (fbm(X, Z, rng, 2600.0, 2) - 0.5)
        # field terraces: very slightly flattened
        for cx, cz, rx, rz, a in self.FIELDS:
            w = blob(X, Z, cx, cz, rx, rz, a, power=4.0)
            h = h * (1 - 0.6 * w) + ndimage.gaussian_filter(h, 4) * 0.6 * w
        return h

    def regions(self, ctx):
        from shapely.geometry import Polygon
        out = []
        for cx, cz, rx, rz, a in self.FIELDS:
            ca, sa = math.cos(a), math.sin(a)
            q = [(cx + ca * u - sa * v, cz + sa * u + ca * v) for u, v in ((-rx * .55, -rz * .55), (rx * .55, -rz * .55),
                                                                           (rx * .55, rz * .55), (-rx * .55, rz * .55))]
            out.append((Polygon(q).difference(ctx.keep_polys.buffer(300)), dict(type=TT['TERRENO_CULTIVADO'], a=1)))
        return out

    def conditions(self, ctx):
        """Objective zone around the temple (domed villa) and the moved house, conditions as on the Egypt map."""
        from shapely.geometry import MultiPoint
        ob = ctx.m.get(lvl.OBJECTLIST)
        pts = []
        for o in ob['instances']:
            if ob['library'][o['cls']]['model'] in ('Palacete.V3D', 'CasaC.V3D'):
                x, z = o['matrix'][12], o['matrix'][14]
                pts += [(x + 2600 * math.cos(k * math.pi / 6), z + 2600 * math.sin(k * math.pi / 6)) for k in range(12)]
        hull = MultiPoint(pts).convex_hull.simplify(300)
        ring = [[float(x), float(z)] for x, z in list(hull.exterior.coords)[:-1]]
        if hull.exterior.is_ccw:                                      # clockwise like the originals' zones
            ring = ring[::-1]
        zone = dict(name='AreaAldea', type=1, bando=3, poly=ring)
        return [zone], dict(attacker=[[[lvl.SUB_ANIQUILACION, 100]], [[lvl.SUB_PROTECCION_ZONA, 'AreaAldea']]],
                            defender=[[[lvl.SUB_ANIQUILACION, 100]], [[lvl.SUB_PROTECCION_ZONA, 'AreaAldea']]],
                            duration=25.0, countdown=25.0)

    def tree_prob(self, ctx, name):
        rng = np.random.default_rng(self.seed + 11)
        X, Z = GX, GZ
        sl = slope_deg(ctx.h)
        groves = smoothstep(0.58, 0.7, fbm(X, Z, rng, 8000.0, 4))
        p = 0.12 + 3.0 * groves
        for cx, cz, rx, rz, a in self.FIELDS:
            p *= 1 - blob(X, Z, cx, cz, rx * 0.65, rz * 0.65, a, power=4.0)
        ok = (sl < 20) & (band(X, Z, 2500, 5000) > 0.5) & ~grid_mask(ctx.keep_polys, 700.0)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9000
        for o, dx, dz, dy, foot in ctx.pads:
            ok &= ~grid_mask(foot, 2200.0)
        ok &= np.hypot(X - 42300, Z - 58500) > 4500
        return p * ok

    def tree_min_dist(self, name):
        return 520.0

    def sounds(self, ctx):
        return [['S_PAJAROS1', 100, 11000.0, 2900.0, 22000.0, 22000.0], ['S_PAJAROS2', 100, 10000.0, 2800.0, 60000.0, 50000.0]]

    def place_location(self, ctx, l):
        if l['name'] == 'LOC_Casa':
            pass

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c40, c16, c36, c41 = composite('40'), composite('16'), composite('36'), composite('41')
        green = lambda r, g, b: g > b + 25 and r - g < 10 and 55 < g < 100                  # noqa: E731
        lush = lambda r, g, b: g > b + 25 and r - g < 7 and g < 95                          # noqa: E731
        g1 = synth(shape, c40, pick_boxes(c40, green, k=8), rng, flat=26.0)
        g2 = synth(shape, c16, pick_boxes(c16, lush, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 6500.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1200.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.4 + (fine - 0.5) * 0.7, 0, 1)
        img = g1 * (1 - w2[..., None]) + g2 * w2[..., None]
        del g1, g2
        img *= np.array([0.96, 1.04, 0.92], np.float32)              # lusher, monsoon green
        # drier, yellower grass in patches (Venice's own meadows) for the variety of the originals
        dryish = lambda r, g, b: r > 95 and g > 75 and r - b > 45                           # noqa: E731
        dr = synth(shape, c41, pick_boxes(c41, dryish, k=6), rng, flat=26.0)
        n2 = up(fbm(Xw, Zw, rng, 11000.0, 3))
        w_d = np.clip((n2 - 0.55) * 2.5 + (fine - 0.5) * 0.5, 0, 0.6)
        img = img * (1 - w_d[..., None]) + dr * w_d[..., None]
        del dr
        # fields: crop patches from the Naples farmland, with darker hedged margins
        fieldy = lambda r, g, b: g > b + 15 and 40 < g < 90                                # noqa: E731
        fl = synth(shape, c36, pick_boxes(c36, fieldy, k=6, win=256), rng, flat=40.0, patch=256, step=192, orient=False)
        fl = fl * (img.reshape(-1, 3).mean(0) / fl.reshape(-1, 3).mean(0))[None, None, :]   # in the plain's colour
        for k, (cx, cz, rx, rz, a) in enumerate(self.FIELDS):
            wob = (fbm(Xw, Zw, rng, 3000.0, 2) - 0.5) * 0.35
            w = up(smoothstep(0.0, 0.25, blob(Xw, Zw, cx, cz, rx, rz, a, power=4.0) + wob))
            stripes = 0.95 + 0.05 * np.sin((cols_full(a) / 16.0) + k)
            tone = np.array([[0.98, 1.05, 0.8], [1.06, 1.02, 0.78], [0.94, 1.03, 0.82]][k % 3], np.float32)
            img = img * (1 - w[..., None] * 0.8) + (fl * tone * stripes[..., None]) * w[..., None] * 0.8
            edge = np.clip(w * (1 - w) * 4.0, 0, 1) * 0.12
            img *= (1 - edge)[..., None]
        del fl
        # tracks: attacker - wooden bridge - temple, the stone bridges - temple
        tracks = [chaikin([self.att, (40000, 20000), (45000, 26500), (45838, 27971), (46500, 33000), (45500, 44000),
                           (44500, 52000), (43000, 56500)], rng, 700.0),
                  chaikin([(29942, 58468), (34000, 58800), (39500, 58200)], rng, 300.0),
                  chaikin([self.dfn, (49000, 61500), (45000, 59500)], rng, 400.0),
                  chaikin([(0, 12000), (14000, 19000), (26000, 21500), (36000, 18500), self.att], rng, 700.0)]
        img = self.paint_tracks(img, tracks, (128, 112, 72), noise, hf, alpha=0.55)
        # the house moved next to the temple: its painted yard comes along from the template
        img = transplant_shading(img, c41, ctx.pads)
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.9 + 0.2 * noise)[..., None]
        return self.finish_texture(ctx, img)


def transplant_shading(img, tmpl, pads, R=170):
    """A moved building takes its painted footprint shadow along: the template's local light variation
    (texture / its blur) around the old place multiplies the new texture around the new place."""
    for o, dx, dz, dy, foot in pads:
        c0, r0 = (int(v) for v in lvl_tex.world_to_px(foot.centroid.x - dx, foot.centroid.y - dz, SIZE, TEX))
        c1, r1 = (int(v) for v in lvl_tex.world_to_px(foot.centroid.x, foot.centroid.y, SIZE, TEX))
        t = tmpl[r0 - R:r0 + R, c0 - R:c0 + R].astype(np.float32).mean(-1)
        ratio = np.clip(t / (ndimage.gaussian_filter(t, 30) + 1.0), 0.35, 1.08)
        ys, xs = np.mgrid[-R:R, -R:R]
        w = 1 - smoothstep(R * 0.5, R * 0.95, np.hypot(xs, ys))
        f = 1 + w * (ratio - 1)
        img[r1 - R:r1 + R, c1 - R:c1 + R] *= f[..., None]
    return img


def field_ids(polys, px):
    """(px, px) int raster, NORTH-UP, of polygon index + 1 (0 = none), each tested only inside its own box."""
    import shapely
    out = np.zeros((px, px), np.int32)
    s = SIZE / px
    for k, q in enumerate(polys):
        x0, z0, x1, z1 = q.bounds
        c0, c1 = max(0, int(x0 / s)), min(px, int(x1 / s) + 1)
        r0, r1 = max(0, int((SIZE - z1) / s)), min(px, int((SIZE - z0) / s) + 1)
        if c0 >= c1 or r0 >= r1:
            continue
        xx, rr = np.meshgrid((np.arange(c0, c1) + 0.5) * s, (np.arange(r0, r1) + 0.5) * s)
        ins = shapely.contains_xy(q, xx.ravel(), (SIZE - rr).ravel()).reshape(xx.shape)
        out[r0:r1, c0:c1][ins] = k + 1
    return out


def cols_full(angle):
    """Coordinate across field stripes (texture pixels) for a field orientation."""
    rows, cols = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    return cols * math.cos(angle) - rows * math.sin(angle)


# ------------------------------------------------------------------ recipe 3: Central Asian steppe (42 Egipto)
class Steppe(Recipe):
    """Open rolling steppe with low hills, kurgans and dry gullies draining to a river at the west edge; the walled
    flat-roofed village of the Egypt map stands on its terrace by the river as the caravanserai."""
    name = 'steppe'
    key = 'ESTEPA'
    folder = 'NBEstepa'
    lvl_name = 'NBEstepa.lvl'
    template = '42'
    seed = 1792
    att = (58500.0, 14500.0)
    dfn = (27500.0, 58500.0)
    remove_models = ('42Arboles.V3D', '42BosqueA.V3D', '42BosqueB.V3D', '42BosqueC.V3D', '42Piramides.V3D',
                     'arbolescontiguo.V3D', 'arbolescontiguo2.V3D')
    relocate_sets = ('42Arbustos.V3D',)
    clima_from = '30'
    sky_from = '30'
    retype = {TT['ARIDO']: TT['ZONA_VERDE']}          # the Egypt map's sand sectors by the river are grass here
    # 2026-10-21 (second batch): SIBERIA moved to the taiga map; the Qing steppe and high plateau provinces added
    provinces = ('TURKESTAN', 'W_KOKAND', 'KAZAKHSTAN', 'W_MIDDLE_HORDE', 'W_TOBOLSK', 'W_IRKUTSK',
                 'W_INNER_MONGOLIA', 'W_OUTER_MONGOLIA', 'W_DZUNGARIA', 'W_QINGHAI', 'W_TIBET')
    objective_key = 'EGIPTO'
    preview_key = 'ANATOLIA'
    obj_loc = 'LOC_Aldea'
    pano = (42000.0, 36000.0)
    core_tint = 0.9
    tex_core = (0.0, 300.0)
    KURGANS = [(35500, 27500, 1300, 480), (47000, 47500, 1100, 380), (52000, 31000, 1500, 560), (26500, 17500, 1000, 320),
               (63500, 55000, 1250, 450), (41000, 63500, 900, 300)]
    GULLIES = [[(70000, 30000), (58000, 26500), (46000, 23500), (34000, 21000), (22000, 24500), (10500, 26000)],
               [(56000, 72000), (50000, 62000), (41000, 52500), (30500, 47500), (21500, 47000)]]
    HILLS = [(45000, 40000, 9000, 6000, 0.4, 900), (64000, 44000, 7000, 9000, -0.2, 1100), (30000, 34000, 6000, 4500, 0.9, 500)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_ESTEPA_ATACANTE_1':
            'Grass to the horizon, low hills and old burial mounds: nowhere to hide on this steppe. '
            'Use the gullies and the mounds well.',
        'LTEXT_TEXTUISECUENCIAS_ESTEPA_ATACANTE_2':
            'The caravanserai by the river is the key to the road. Take it and hold it.',
        'LTEXT_TEXTUISECUENCIAS_ESTEPA_DEFENSOR_1':
            'They come over the open steppe. Our horsemen will find them long before they reach the river.',
        'LTEXT_TEXTUISECUENCIAS_ESTEPA_DEFENSOR_2':
            'Hold the caravanserai and its walls. Whoever holds it holds the crossing.',
    }

    def core_shapes(self, ctx):
        from shapely.geometry import Point
        from shapely.ops import unary_union
        sm0 = ctx.m.get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        water = unary_union([P[s['id']] for s in sm0['sectors'] if s['type'] == TT['RIO_PROFUNDO']])
        return [water.buffer(1200.0), Point(15500, 40000).buffer(4700.0)]

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        h = 2700.0 + 1100.0 * smoothstep(12000, 70000, X) + 1500.0 * (fbm(X, Z, rng, 34000.0, 4) - 0.5)
        h += 300.0 * (fbm(X, Z, rng, 9000.0, 3) - 0.5)
        for cx, cz, rx, rz, a, hh in self.HILLS:                     # low, rounded swells
            ca, sa = math.cos(a), math.sin(a)
            u = ((X - cx) * ca + (Z - cz) * sa) / rx
            v = (-(X - cx) * sa + (Z - cz) * ca) / rz
            h += hh * np.exp(-1.6 * (u * u + v * v))
        for line in self.GULLIES:
            d, s = polyline_dist(X, Z, line)
            depth = 520.0 * (0.6 + 0.4 * smoothstep(0, 40000, s))
            h -= depth * (1 - smoothstep(300.0, 2600.0, d)) ** 1.6
        for cx, cz, r, hh in self.KURGANS:
            rr = np.hypot(X - cx, Z - cz) / r
            h += hh * np.clip(1 - rr ** 2, 0, 1) ** 1.5
        return h

    def tex_core_geom(self, ctx):                                     # only the river banks: the village area
        from shapely.ops import unary_union                           # is repainted (no Egyptian palm shadows)
        sm0 = lvl.load(scen_lvl(self.template)).get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        return unary_union([P[s['id']] for s in sm0['sectors'] if s['type'] == TT['RIO_PROFUNDO']]).buffer(500.0)

    def tree_prob(self, ctx, name):                                    # shrubs: gullies, hollows, river side
        X, Z = GX, GZ
        dg = np.min([polyline_dist(X, Z, l)[0] for l in self.GULLIES], 0)
        sl = slope_deg(ctx.h)
        p = 0.2 + 2.0 * np.exp(-(dg / 1600.0) ** 2) + 1.2 * (X < 22000)
        ok = (sl < 22) & (band(X, Z, 2500, 5000) > 0.5) & ~grid_mask(ctx.keep_polys, 600.0)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9000
        for cx, cz, r, hh in self.KURGANS:
            ok &= np.hypot(X - cx, Z - cz) > r + 300
        return p * ok

    def tree_min_dist(self, name):
        return 900.0

    def shadows(self, name):
        return False

    def sounds(self, ctx):
        return [['S_VIENTO', 25, 24000.0, 1200.0, 45000.0, 30000.0], ['S_VIENTO', 25, 21000.0, 1100.0, 60000.0, 60000.0],
                ['S_PAJAROS3', 90, 11000.0, 2900.0, 30000.0, 45000.0]]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife (uid 12): out on the steppe
            l['pos'][0] = min(max(l['pos'][0] - 2500.0, 8000.0), 67000.0)

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c30, c26, c54 = composite('30'), composite('26'), composite('54')
        yg = lambda r, g, b: g > b + 40 and r - g < 18 and g > 60                           # noqa: E731
        gold = lambda r, g, b: r > 120 and r - b > 70 and g > 80                            # noqa: E731
        dkg = lambda r, g, b: g > b + 25 and g < 75                                         # noqa: E731
        base = synth(shape, c30, pick_boxes(c30, yg, k=8), rng, flat=26.0)
        dry = synth(shape, c26, pick_boxes(c26, gold, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 9000.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1500.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 360.0, 3), TEX)
        hz = up(ctx.h[::-1], TEX)
        slope = up(ndimage.gaussian_filter(slope_deg(ctx.h)[::-1], 0.8), TEX)
        hrel = hz - up(ndimage.gaussian_filter(ctx.h, 10)[::-1], TEX)
        inner = up(band(Xw, Zw, 2500.0, 9000.0))                       # the template's rim at the edge: no frame
        w_dry = np.clip((noise - 0.3) * 1.8 + (fine - 0.5) * 0.8 + (hrel / 900.0 + (slope - 8) / 30.0) * inner, 0, 0.9)
        img = base * (1 - w_dry[..., None]) + dry * w_dry[..., None]
        del base, dry
        # hollows and gullies: greener
        dg = up(np.min([polyline_dist(Xw, Zw, l)[0] for l in self.GULLIES], 0))
        green = synth(shape, c54, pick_boxes(c54, dkg, k=6), rng, flat=26.0) * 1.2
        w_g = np.clip((1 - smoothstep(400, 2400, dg + 500 * (fine - 0.5))) * 0.45 + np.clip(-hrel / 900.0, 0, 0.35)
                      + (fine - 0.65) * 0.4, 0, 0.5)
        img = img * (1 - w_g[..., None]) + green * w_g[..., None]
        del green
        # bare earth on kurgan crowns and steep banks
        earth = lambda r, g, b: r > 125 and r - b > 50 and g > 90                          # noqa: E731
        bare = synth(shape, c26, pick_boxes(c26, earth, k=5, win=256), rng, flat=30.0, patch=256, step=192)
        w_b = np.clip(((slope - 20) / 14.0) * inner + (hf - 0.75) * 0.6, 0, 0.7)
        for cx, cz, r, hh in self.KURGANS:
            dk = up(np.hypot(Xw - cx, Zw - cz) / r)
            w_b = np.maximum(w_b, (1 - smoothstep(0.15, 0.55, dk + (fine - 0.5) * 0.3)) * 0.55)
            img *= (1 - 0.12 * np.exp(-((dk - 1.0) / 0.12) ** 2))[..., None]
        img = img * (1 - w_b[..., None]) + bare * w_b[..., None]
        del bare
        # tracks: the caravan road along the river to the caravanserai, and the road east
        tracks = [chaikin([(9000, 0), (11500, 18000), (12500, 30000), (14200, 36500)], rng, 600.0),
                  chaikin([(17500, 41500), (26000, 44500), (38000, 43500), (52000, 46000), (75000, 52000)], rng, 900.0),
                  chaikin([self.att, (52000, 23000), (42000, 33000), (30000, 39500), (18500, 40500)], rng, 900.0)]
        img = self.paint_tracks(img, tracks, (150, 128, 84), noise, hf, alpha=0.5)
        # the caravanserai: packed earth in and around the walls, the houses' painted shadows taken from the
        # template (only close to the houses: the Egypt map's palms around them are gone)
        houses = ((13789, 37923), (14737, 42358), (16915, 40278))
        dvill = up(np.min([np.hypot(Xw - x, Zw - z) for x, z in houses + ((16929, 43362), (14793, 36092),
                                                                          (17750, 37691))], 0))
        w_y = (1 - smoothstep(1100, 2300, dvill + 400 * (fine - 0.5))) * 0.55
        dust = img * 0.4 + np.array([150, 128, 88], np.float32) * 0.6
        img = img * (1 - w_y[..., None]) + dust * w_y[..., None]
        tm = composite('42').astype(np.float32).mean(-1)
        ratio = np.clip(tm / (ndimage.gaussian_filter(tm, 30) + 1.0), 0.35, 1.05)
        dh = up(np.min([np.hypot(Xw - x, Zw - z) for x, z in houses], 0))
        w_h = 1 - smoothstep(700, 1200, dh)
        img *= (1 + w_h * (ratio - 1))[..., None]
        del tm, ratio, dust
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.9 + 0.2 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 4: East Asian rice country (44 Piamonte)
class EastAsia(Recipe):
    """Rice country: the round hill with the fenced village on its top is terraced for rice down to the river,
    flooded paddies (mud) fill the plain inside the river bend and on the far bank, crossed by firm causeways
    to the three bridges; willows line the river, pines stand on the crests, rice-straw stacks by the fields.
    Objectives as on the Piedmont map (the village and the farm)."""
    name = 'eastasia'
    key = 'ARROZAL'
    folder = 'NBArrozal'
    lvl_name = 'NBArrozal.lvl'
    template = '44'
    seed = 1793
    att = (62500.0, 13000.0)
    dfn = (18500.0, 61000.0)
    remove_models = ('MuroPiedraB.V3D',)
    relocate_sets = ('44HierbasAltas.V3D', '44Hacinas.V3D')
    provinces = ('W_ZHILI', 'W_SHAANXI', 'W_SICHUAN', 'W_HUGUANG', 'W_JIANGNAN', 'W_FUJIAN', 'W_GUANGDONG', 'W_YUNNAN',
                 'W_MANCHURIA', 'W_FORMOSA', 'W_KOREA', 'W_TONKIN', 'W_ANNAM', 'W_SAIGON', 'W_CAMBODIA', 'W_LAOS',
                 'W_SIAM', 'W_AVA', 'W_PEGU', 'W_ARAKAN', 'W_MALAYA', 'W_JAVA', 'W_LUZON', 'W_VISAYAS',
                 'W_LESSER_SUNDA_ISLANDS')
    objective_key = 'PIAMONTE'        # 'Control the Village and the Farm' / 'Control the Village' (template zones)
    preview_key = 'PIAMONTE'
    obj_loc = 'LOC_Aldea'
    pano = (43000.0, 30000.0)
    core_tint = 0.55
    blend = 3000.0
    VILLAGE = ('CasaA.V3D', 'CasaB.V3D', 'CasaC.V3D', 'CasaD.V3D', 'VallaCampoA.V3D', 'VallaCampoB.V3D',
               'VallaCampoC.V3D', 'VallaCampoD.V3D')
    HILL = (28700.0, 43200.0)
    STEP = 330.0                      # terrace riser (cm)
    PADDY_HA = 1.9                    # flooded paddies (BARRIZAL, mud; the 10 originals with mud: ~5 ha of 56)
    FIELDS_HA = 7.5                   # all paddy fields (the rest grown or ripening: TERRENO_CULTIVADO)
    HILLS = [(68500, 61000, 9000, 7000, 0.5, 1300), (71000, 33000, 5000, 8000, 0.1, 700), (8000, 26000, 7000, 9000, 0.0, 900)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_ARROZAL_ATACANTE_1':
            'Rice terraces climb the hill and the flooded paddies reach to the river. Keep to the causeways: '
            'men who wade the paddies cannot run or charge.',
        'LTEXT_TEXTUISECUENCIAS_ARROZAL_ATACANTE_2':
            'The walled village on the hilltop and the farm on its terraces are our objectives. Take them both.',
        'LTEXT_TEXTUISECUENCIAS_ARROZAL_DEFENSOR_1':
            'The river and its bridges cover our front. Let the enemy struggle through the mud of the paddies.',
        'LTEXT_TEXTUISECUENCIAS_ARROZAL_DEFENSOR_2':
            'Hold the village on the hill. From its fences we see every terrace below.',
    }

    def core_shapes(self, ctx):
        ctx.water0 = self.water_geom(ctx, ('RIO_PROFUNDO',))
        ctx.river_mask = grid_mask(self.water_geom(ctx, ('RIO_PROFUNDO',), special=False))
        return [ctx.water0.buffer(1500.0), self.cons_geom(ctx, self.VILLAGE, 1800.0),
                self.cons_geom(ctx, ('44Granja.V3D',), 1700.0)]

    def tracks(self):
        rng = np.random.default_rng(self.seed + 3)
        return [chaikin([self.att, (58000, 19500), (53800, 24500), (51832, 25717), (47000, 30500), (44265, 38000),
                         (38500, 41500), (32500, 42800)], rng, 400.0),            # east bridge - farm - village
                chaikin([(24449, 12343), (25500, 18500), (26500, 26000), (27500, 34000), (28200, 38500)], rng, 400.0),
                chaikin([(59142, 56784), (54500, 54000), (47500, 50000), (40000, 47500), (33000, 45500)], rng, 400.0),
                chaikin([self.dfn, (21500, 54000), (24500, 48500)], rng, 300.0),
                chaikin([(75000, 50000), (68500, 55000), (62500, 56500), (59142, 56784)], rng, 500.0),
                chaikin([(0, 30000), (9000, 24000), (17000, 15500), (24449, 12343)], rng, 500.0)]

    def base(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        h0 = ctx.h0
        hs = ndimage.gaussian_filter(h0, 3)
        h = 600.0 + 0.92 * (hs - 600.0)
        h += 160.0 * (fbm(X, Z, rng, 9000.0, 3) - 0.5)
        for cx, cz, rx, rz, a, hh in self.HILLS:                     # low hills round the plain
            ca, sa = math.cos(a), math.sin(a)
            u = ((X - cx) * ca + (Z - cz) * sa) / rx
            v = (-(X - cx) * sa + (Z - cz) * ca) / rz
            h += hh * np.exp(-1.4 * (u * u + v * v))
        return h

    def fields(self, ctx, hb):
        """Paddy fields: a jittered grid of quads (about 45 x 32 m) on the low flat ground near the river, kept
        clear of the causeways, the core and the deployment areas; nearest the river first, up to PADDY_HA."""
        from shapely.geometry import Polygon, LineString
        from shapely.ops import unary_union
        rng = np.random.default_rng(self.seed + 21)
        dr = ndimage.distance_transform_edt(~ctx.river_mask) * CELL
        low = (hb < 3000.0) & (slope_deg(ndimage.gaussian_filter(hb, 1.5)) < 9.0) & (dr > 2700.0) & (dr < 30000.0)
        low &= ctx.terrace0 < 0.3
        low &= band(GX, GZ, 4000.0, 4500.0) > 0.5
        allowed = mask_polygons(low, simplify=300.0, min_cells=30)
        avoid = unary_union([LineString(t).buffer(1100.0) for t in self.tracks()] + [ctx.core_union.buffer(1500.0)] +
                            [Polygon([(x + 9000 * math.cos(k * 0.3), z + 9000 * math.sin(k * 0.3)) for k in range(21)])
                             for x, z in (self.att, self.dfn)])
        allowed = allowed.difference(avoid)
        ang, cw, ch = 0.55, 4500.0, 3200.0
        ca, sa = math.cos(ang), math.sin(ang)
        jit = {}

        def vtx(i, j):
            if (i, j) not in jit:
                jit[(i, j)] = rng.normal(0, 380.0, 2)
            u, v = i * cw + jit[(i, j)][0], j * ch + jit[(i, j)][1]
            return (40000.0 + u * ca - v * sa, 30000.0 + u * sa + v * ca)
        cand = []
        for i in range(-14, 15):
            for j in range(-20, 21):
                q = Polygon([vtx(i, j), vtx(i + 1, j), vtx(i + 1, j + 1), vtx(i, j + 1)])
                c = q.centroid
                if not (0 < c.x < SIZE and 0 < c.y < SIZE) or not allowed.intersects(q):
                    continue
                part = max(lvl_nav.polys_of(q.intersection(allowed)) or [Polygon()], key=lambda g: g.area)
                if part.area < 0.7 * q.area:
                    continue
                d = dr[min(N - 1, int(round(c.y / CELL))), min(N - 1, int(round(c.x / CELL)))]
                piece = part.simplify(60.0).buffer(-130.0, join_style=2)
                if isinstance(piece, Polygon) and not piece.is_empty:
                    cand.append((d + rng.uniform(0, 2500.0), piece))
        cand.sort(key=lambda t: t[0])
        out, area = [], 0.0
        for d, q in cand:
            if area > self.FIELDS_HA * 1e8:
                break
            out.append(q)
            area += q.area
        # the fields nearest the river are flooded (mud), the others grown or ripening (firm, cultivated)
        acc, self._flooded = 0.0, []
        for q in out:
            self._flooded.append(acc < self.PADDY_HA * 1e8)
            acc += q.area
        return out

    def design(self, ctx):
        hb = self.base(ctx)
        X, Z = GX, GZ
        # rice terraces on the hill flanks: flat treads, steep low risers (contours of the smoothed hill)
        sl = slope_deg(ndimage.gaussian_filter(hb, 2))
        dh = np.hypot(X - self.HILL[0], Z - self.HILL[1])
        inside = grid_mask(ctx.core_union, pad=CELL)
        dcore = ndimage.distance_transform_edt(~inside) * CELL
        tm = smoothstep(2.0, 5.0, sl) * (1 - smoothstep(26.0, 34.0, sl)) * smoothstep(2100.0, 2700.0, hb)
        tm *= (1 - smoothstep(19000.0, 24000.0, dh)) * smoothstep(1200.0, 2800.0, dcore)
        ctx.terrace = ctx.terrace0 = tm = np.clip(ndimage.gaussian_filter(tm, 1.0), 0, 1)
        f = hb / self.STEP
        q = self.STEP * (np.floor(f) + smoothstep(0.68, 1.0, f - np.floor(f)))
        h = hb * (1 - tm) + q * tm
        # paddies: each field flat (its mean height), the bunds between them follow
        self._fields = self.fields(ctx, hb)
        from shapely.geometry import MultiPolygon
        lab = np.zeros((N, N), int)
        for k, q_ in enumerate(self._fields):
            lab[grid_mask(q_.buffer(200.0))] = k + 1
        if self._fields:
            means = ndimage.mean(h, lab, index=np.arange(1, len(self._fields) + 1))
            hf = np.where(lab > 0, np.r_[0.0, means][lab] - 40.0, h)
            w = ndimage.gaussian_filter((lab > 0).astype(float), 0.8)
            h = h * (1 - w) + ndimage.gaussian_filter(hf, 0.6) * w
        return h

    def regions(self, ctx):
        from shapely.ops import unary_union
        if not self._fields:
            return []
        out = []
        for flood, tt in ((False, 'TERRENO_CULTIVADO'), (True, 'BARRIZAL')):
            g = unary_union([q.buffer(150.0, join_style=2) for q, f in zip(self._fields, self._flooded) if f == flood])
            if not g.is_empty:
                out.append((g.buffer(-20.0, join_style=2).difference(ctx.keep_polys.buffer(400)), dict(type=TT[tt], a=1)))
        return out

    def tree_prob(self, ctx, name):
        rng = np.random.default_rng(self.seed + 11)
        X, Z = GX, GZ
        dr = ndimage.distance_transform_edt(~ctx.river_mask) * CELL
        sl = slope_deg(ctx.h)
        paddy = grid_mask(self.paddy_union(), 250.0) if self._fields else np.zeros((N, N), bool)
        ok = (sl < 22) & (band(X, Z, 2500, 5000) > 0.5) & ~grid_mask(ctx.keep_polys, 600.0) & ~paddy
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9000
        if name == '44Arboles.V3D':                                    # willows on the banks, pines on the crests
            crest = smoothstep(2.5, 0.5, slope_deg(ndimage.gaussian_filter(ctx.h, 3))) * smoothstep(2600, 4200, ctx.h)
            grove = smoothstep(0.55, 0.7, fbm(X, Z, rng, 7000.0, 3))
            p = 2.6 * np.exp(-((dr - 2600.0) / 900.0) ** 2) + 1.4 * crest * (0.3 + grove) + 0.25 * grove
            p *= 1 - 0.8 * ctx.terrace
        elif name == '44Hacinas.V3D':                                  # straw stacks by the paddies
            pe = grid_mask(self.paddy_union(), 900.0) & ~paddy if self._fields else np.zeros((N, N), bool)
            p = 0.05 + 3.0 * pe
        else:                                                          # tall grass: field margins, banks, gullies
            pe = grid_mask(self.paddy_union(), 600.0) & ~paddy if self._fields else np.zeros((N, N), bool)
            p = 0.15 + 1.5 * pe + 1.2 * np.exp(-((dr - 2000.0) / 900.0) ** 2) + 0.4 * ctx.terrace
        return p * ok

    def paddy_union(self):
        from shapely.ops import unary_union
        return unary_union(self._fields)

    def tree_min_dist(self, name):
        return {'44Arboles.V3D': 650.0, '44Hacinas.V3D': 1400.0}.get(name, 380.0)

    def shadows(self, name):
        return name == '44Arboles.V3D'

    def sounds(self, ctx):
        return [['S_PAJAROS1', 100, 11000.0, 2900.0, 40000.0, 24000.0], ['S_PAJAROS2', 100, 10000.0, 2800.0, 64000.0, 38000.0]]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: on the firm ground of the hill
            l['pos'][0], l['pos'][2] = 16000.0, 38000.0

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c16, c40, c46, c53 = (composite(s) for s in ('16', '40', '46', '53'))
        green = lambda r, g, b: g > b + 25 and r - g < 12 and 55 < g < 115                  # noqa: E731
        lush = lambda r, g, b: g > b + 35 and g > r + 2 and g > 90                           # noqa: E731
        g1 = synth(shape, c40, pick_boxes(c40, green, k=8), rng, flat=26.0)
        g2 = synth(shape, c16, pick_boxes(c16, green, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 6500.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.4 + (fine - 0.5) * 0.7, 0, 1)
        img = g1 * (1 - w2[..., None]) + g2 * w2[..., None]
        del g1, g2
        img *= np.array([0.95, 1.05, 0.9], np.float32)
        # terraces: each tread a strip of crop (Papal States fields), tones alternating with the terrace index,
        # a light earthen bund on the outer edge and a shaded riser below it
        hz = up(ctx.h[::-1], TEX)
        tm = up(ctx.terrace[::-1], TEX)
        crop = synth(shape, c53, pick_boxes(c53, lambda r, g, b: 60 < g < 120 and g > b + 15, k=6, win=256), rng,
                     flat=30.0, patch=256, step=192)
        crop = crop * (img.reshape(-1, 3).mean(0) / crop.reshape(-1, 3).mean(0))[None, None, :]
        lev = hz / self.STEP
        idx = np.floor(lev)
        fr = lev - idx
        tone = np.where(np.mod(idx, 3) == 0, 1.06, np.where(np.mod(idx, 3) == 1, 0.95, 1.0))
        lush_t = synth(shape, c46, pick_boxes(c46, lush, k=6), rng, flat=26.0)
        wl = np.clip((up(fbm(Xw, Zw, rng, 2500.0, 2)) - 0.45) * 3.0, 0, 1)[..., None]
        tread = (crop * (1 - wl * 0.6) + lush_t * wl * 0.6) * tone[..., None]
        bund = np.exp(-((fr - 0.70) / 0.035) ** 2)                      # top of the riser: dry bund
        riser = smoothstep(0.70, 0.80, fr) * (1 - smoothstep(0.95, 1.0, fr))
        wt = smoothstep(0.15, 0.5, tm)
        img = img * (1 - wt[..., None]) + tread * wt[..., None]
        img *= (1 - 0.22 * riser * wt)[..., None]
        img = img * (1 - (0.5 * bund * wt)[..., None]) + np.array([122, 106, 70], np.float32) * (0.5 * bund * wt)[..., None]
        del crop, tread
        # paddies: flooded (sky in the water), young green rice in rows, a few ripening yellow; earthen bunds
        if self._fields:
            # the Scottish lake's water surface (a tiling original texture), lit by the sky
            wt_ = lvl_tex.read_dds(find_file(os.path.join(scen_dir('02'), 'Models'), 'agualagoescocia.tga'))[..., :3]
            water = np.tile(wt_.astype(np.float32), (TEX // wt_.shape[0], TEX // wt_.shape[1], 1))
            water = water * 0.75 + np.array([92, 100, 100], np.float32) * 0.25
            fid = field_ids(self._fields, TEX // 4)
            fid = np.asarray(ndimage.zoom(fid, 4, order=0))
            kinds = np.r_[1, [0 if f else (1 if rng.random() < 0.7 else 2) for f in self._flooded]]
            kind = kinds[fid]
            stripes = (0.5 + 0.5 * np.sin(cols_full(0.55) / 3.2))[..., None]
            lum = img.mean(-1)
            grain = (lum / (ndimage.gaussian_filter(lum, 6.0) + 1.0))[..., None]   # the grass's own grain
            young = lush_t * np.array([0.78, 0.84, 0.62], np.float32)
            flooded = (water * (0.5 - 0.3 * stripes) + young * (0.5 + 0.3 * stripes)) * (0.72 + 0.2 * grain)
            grown = (img * 0.45 + young * 0.55) * (0.9 + 0.12 * stripes)
            ripe = (img * 0.4 + young * np.array([1.12, 0.95, 0.58], np.float32) * 0.6) * (0.9 + 0.12 * stripes)
            pf = np.where((kind == 0)[..., None], flooded, np.where((kind == 1)[..., None], grown, ripe))
            pf *= (0.9 + 0.2 * up(fbm(Xw, Zw, rng, 900.0, 2)))[..., None]
            inf = (fid > 0).astype(np.float32)
            edge = ndimage.gaussian_filter(inf, 2.0)
            wpad = smoothstep(0.55, 0.85, edge) * 0.9
            img = img * (1 - wpad[..., None]) + pf * wpad[..., None]
            rim = np.clip(edge * (1 - edge) * 4.0, 0, 1) * (1 - inf * 0.5)
            img = img * (1 - 0.5 * rim[..., None]) + np.array([118, 104, 70], np.float32) * (0.5 * rim)[..., None]
            del water, flooded, grown, ripe, pf, young
        del lush_t
        img = self.paint_tracks(img, self.tracks(), (124, 106, 70), noise, hf, alpha=0.55)
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.92 + 0.16 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 5: Japanese valley (16 Hungria)
class Japan(Recipe):
    """Steep wooded mountains round two narrow valleys: the river valley and the valley of its western branch.
    The ruined keep of the Hungary map stands on its spur above the river fork as the castle, the inn and two
    stone walls are moved up beside it (the castle town); the bridges are the only crossings. The attacker comes
    up the southern valley or over the pass to the north bridge."""
    name = 'japan'
    key = 'JAPON'
    folder = 'NBJapon'
    lvl_name = 'NBJapon.lvl'
    template = '16'
    seed = 1794
    att = (60500.0, 17500.0)
    dfn = (14500.0, 53500.0)
    move = {'16Fonda.V3D': (-11000.0, 9000.0), '16MuroPiedraA.V3D': (-29000.0, 10000.0),
            '16MuroPiedraA01.V3D': (-44000.0, -10000.0)}
    relocate_sets = ('Arboles.V3D', 'ArbolesContiguosA.V3D')
    outside_take = {'ArbolesContiguosA.V3D': 0.35}     # thin the outside woods a little for wooded hills inside
    provinces = ('W_HONSHU', 'W_KYUSHU_AND_SHIKOKU', 'W_EZO', 'W_NEPAL', 'W_KASHMIR')
    objective_key = 'EGIPTO'          # 'Control the Village' (the zone holds the castle and its houses)
    preview_key = 'HUNGRIA'
    obj_loc = 'LOC_Torre'
    pano = (36000.0, 36000.0)
    shadow = dict(length=150.0, width=24.0, strength=0.45, direction=(-0.55, -0.83))   # 16's long NW shadows
    blend = 3000.0
    TOWN = ('16Torre.V3D', '16Fonda.V3D', '16MuroPiedraA.V3D', '16MuroPiedraA01.V3D')
    VALLEYS = [[(64000, 16500), (52000, 19000), (42000, 20500), (32000, 22000), (22000, 20000), (12000, 17500),
                (0, 17000)],                                                      # southern valley (W branch)
               [(33600, 75000), (33200, 60000), (32800, 45000), (32200, 30000)],    # the river valley
               [(60000, 24000), (56500, 36000), (50500, 46500), (44000, 55500), (38500, 61500), (34500, 63500)]]  # pass
    WIDTH = [6000.0, 4600.0, 2400.0]
    PLATEAU = [(6000, 28500), (25000, 28500), (27500, 45000), (26500, 61000), (14000, 63000), (5000, 58000)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_JAPON_ATACANTE_1':
            'Wooded mountains close in on both valleys. Only two bridges cross the river below the castle: '
            'take the southern valley, or the pass over the hills to the northern bridge.',
        'LTEXT_TEXTUISECUENCIAS_JAPON_ATACANTE_2':
            'The castle and its little town above the river fork are our objective. Storm them.',
        'LTEXT_TEXTUISECUENCIAS_JAPON_DEFENSOR_1':
            'The river and the mountains guard us. Watch the two bridges and the pass through the woods.',
        'LTEXT_TEXTUISECUENCIAS_JAPON_DEFENSOR_2':
            'Hold the castle and the houses beside it. While its walls stand, the valley is ours.',
    }

    def core_shapes(self, ctx):
        ctx.water0 = self.water_geom(ctx, ('RIO_POCO_PROFUNDO',))
        return [ctx.water0.buffer(1400.0), self.cons_geom(ctx, ('16Torre.V3D',), 1900.0)]

    def valley(self, X, Z):
        """0..1: inside one of the valley floors (1 on its line, fading over its width)."""
        v = np.zeros(X.shape)
        for line, w in zip(self.VALLEYS, self.WIDTH):
            d, _ = polyline_dist(X, Z, line)
            v = np.maximum(v, 1 - smoothstep(w * 0.45, w, d))
        return v

    def open_ground(self):
        """The valley floors, the castle plateau and the attacker's basin (shapely, template coords)."""
        from shapely.geometry import LineString, Polygon, Point
        from shapely.ops import unary_union
        return unary_union([LineString(l).buffer(w * 0.5) for l, w in zip(self.VALLEYS, self.WIDTH)] +
                           [Polygon(self.PLATEAU), Point(*self.att).buffer(9500.0)])

    def mountains(self, X, Z, rng):
        """0 on the open ground, rising to 1 deep in the hills (over ~140 m, warped)."""
        og = grid_mask(self.open_ground())
        d = ndimage.distance_transform_edt(~og) * CELL
        d += (fbm(X, Z, rng, 9000.0, 3) - 0.5) * 5000.0
        return smoothstep(0.0, 12000.0, d)

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        hs = ndimage.gaussian_filter(ctx.h0, 3)
        mt = self.mountains(X, Z, rng)
        rid = fbm(X, Z, rng, 8000.0, 4, ridged=True)
        lump = fbm(X, Z, rng, 16000.0, 3)
        ctx.mt = mt
        # wooded mountains: ridged crests and spurs on a rounded mass, steep but mostly passable flanks
        edge = 0.35 + 0.65 * band(X, Z, 3000.0, 15000.0)           # (the map edge returns to the template's)
        h = ndimage.gaussian_filter(hs, 4) + mt ** 1.25 * (2400.0 + 3400.0 * rid + 1600.0 * lump) * edge
        h += 300.0 * (fbm(X, Z, rng, 5000.0, 3) - 0.5)
        # the castle spur: a rise west of the keep
        h += 1300.0 * blob(X, Z, 9000, 40000, 7000, 9500, 0.3, power=2.0) * (1 - mt)
        return h

    # (no BOSQUE sectors: on the originals forest is a footstep type only, ~2.6 ha per map; wooded mountains of
    # 20 ha cut round every cliff would need more sectors than any original has)

    def conditions(self, ctx):
        return self.zone_conditions(ctx, self.TOWN, 'AreaAldea', 2400.0)

    def tree_prob(self, ctx, name):
        rng = np.random.default_rng(self.seed + 11)
        X, Z = GX, GZ
        sl = slope_deg(ctx.h)
        val = self.valley(X, Z)
        edge = np.clip(ctx.mt * 3.0, 0, 1) * (1 - np.clip((ctx.mt - 0.55) * 2.5, 0, 1))   # wood edges above the valleys
        p = 0.25 + 3.0 * edge + 1.2 * ctx.mt + 0.6 * smoothstep(0.6, 0.75, fbm(X, Z, rng, 5000.0, 3)) * (1 - val)
        ok = (sl < 34) & (band(X, Z, 2500, 4500) > 0.5) & ~grid_mask(ctx.keep_polys, 700.0)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9500
        for o, dx, dz, dy, foot in ctx.pads:
            ok &= ~grid_mask(foot, 1800.0)
        ok &= ~grid_mask(self.town_hull(ctx), 600.0)
        for line in self.tracks():
            from shapely.geometry import LineString
            ok &= ~grid_mask(LineString(line), 500.0)
        return p * ok

    def town_hull(self, ctx):
        from shapely.geometry import MultiPoint
        ob = ctx.m.get(lvl.OBJECTLIST)
        pts = [(o['matrix'][12], o['matrix'][14]) for o in ob['instances'] if ob['library'][o['cls']]['model'] in self.TOWN]
        return MultiPoint(pts).convex_hull.buffer(1500.0)

    def tree_min_dist(self, name):
        return 560.0

    def tracks(self):
        rng = np.random.default_rng(self.seed + 3)
        return [chaikin([self.att, (52000, 19000), (42000, 18000), (31000, 17000), (21000, 16500), (16449, 16200)], rng, 450.0),
                chaikin([(16449, 24500), (17500, 29000), (19500, 32500), (21500, 35000)], rng, 250.0),   # bridge - town
                chaikin([(18500, 39000), (16500, 45000), self.dfn], rng, 300.0),
                chaikin([self.att, (58500, 29000), (53000, 40000), (46500, 51500), (40500, 60000), (36500, 63100)], rng, 600.0),
                chaikin([(30500, 63100), (26000, 58000), (21000, 54000), self.dfn], rng, 450.0)]

    def sounds(self, ctx):
        return [['S_PAJAROS1', 100, 11000.0, 2900.0, 58000.0, 52000.0], ['S_PAJAROS3', 90, 11000.0, 2900.0, 12000.0, 66000.0],
                ['S_VIENTO', 25, 20000.0, 1100.0, 40000.0, 8000.0]]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: up in the woods' clearings
            k = getattr(self, '_wk', 0)
            l['pos'][0], l['pos'][2] = [(44000.0, 30000.0), (26000.0, 50000.0), (50000.0, 25000.0), (12000.0, 25000.0)][k % 4]
            self._wk = k + 1

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c16, c03 = composite('16'), composite('03')
        green = lambda r, g, b: g > b + 20 and r - g < 8 and 50 < g < 110                   # noqa: E731
        g1 = synth(shape, c16, pick_boxes(c16, green, k=8), rng, flat=26.0)
        g2 = synth(shape, c03, pick_boxes(c03, green, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 6500.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.4 + (fine - 0.5) * 0.7, 0, 1)
        img = g1 * (1 - w2[..., None]) + g2 * w2[..., None]
        del g1, g2
        img *= np.array([0.95, 1.04, 0.92], np.float32)
        # forest floor on the mountains: darker, mossy, mottled (the Hungary map's wood shade)
        dark = lambda r, g, b: g > b + 10 and g < 60 and r < 70                                # noqa: E731
        wood = synth(shape, c16, pick_boxes(c16, dark, k=6), rng, flat=0, patch=256, step=192)
        wood = wood * (0.95 + 0.2 * up(fbm(Xw, Zw, rng, 1800.0, 3)))[..., None]
        mt = up(ctx.mt[::-1].astype(np.float32))
        w_w = np.clip(smoothstep(0.22, 0.55, mt + (fine - 0.5) * 0.25 + (hf - 0.5) * 0.15), 0, 0.85)
        img = img * (1 - w_w[..., None]) + wood * w_w[..., None]
        del wood
        # rock on cliffs and crests (the Helvetic map's mossy crags)
        slope = up(ndimage.gaussian_filter(slope_deg(ctx.h)[::-1], 0.7), TEX)
        c51 = composite('51')
        rocky = lambda r, g, b: r > 80 and b > 0.62 * r and abs(r - g) < 25                    # noqa: E731
        rock = synth(shape, c51, pick_boxes(c51, rocky, k=6, win=192), rng, flat=0, patch=192, step=128) * 0.6
        w_r = smoothstep(33.0, 41.0, slope + 8.0 * (hf - 0.5) + 6.0 * (fine - 0.5)) * 0.85 * smoothstep(0.08, 0.3, mt)
        img = img * (1 - w_r[..., None]) + rock * w_r[..., None]
        del rock
        img = self.paint_tracks(img, self.tracks(), (118, 102, 66), noise, hf, alpha=0.55)
        img = transplant_shading(img, c16, ctx.pads)
        img *= self.baked_light(ctx, 0.9)[..., None]
        img *= (0.92 + 0.16 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 6: African savanna (28 Alentejo)
class Savanna(Recipe):
    """Dry golden grass and scattered flat-crowned trees (the Alentejo's holm oaks, the originals' closest to
    acacias), a granite kopje in the west, a sandy dry riverbed with a fringe of trees across the plain, red
    earth tracks. The walled village (the kraal) and the chapel of the Alentejo map are the objectives, with their
    tree clumps; the loose field walls are gone."""
    name = 'savanna'
    key = 'SABANA'
    folder = 'NBSabana'
    lvl_name = 'NBSabana.lvl'
    template = '28'
    seed = 1795
    att = (13000.0, 22500.0)
    dfn = (59000.0, 60000.0)
    remove_models = ('28MuroPiedraA.V3D', '28MuroPiedraB.V3D', '28VallaCampoC.V3D')
    provinces = ('W_ETHIOPIA', 'W_SENNAR', 'W_DARFUR', 'W_WADAI', 'W_BAHR_EL_GHAZAL', 'W_BUGANDA', 'W_TIMBUKTU',
                 'W_SEGU', 'W_MOSSI', 'W_HAUSALAND', 'W_BORNU', 'W_FUTA_JALLON', 'W_OYO_AND_DAHOMEY', 'W_ASHANTI',
                 'W_SENEGAL', 'W_CAMEROON', 'W_UBANGI', 'W_KONGO', 'W_ANGOLA', 'W_LUBA', 'W_LUNDA', 'W_KAZEMBE',
                 'W_ROZVI', 'W_MOZAMBIQUE', 'W_NATAL', 'W_KALAHARI', 'W_NAMAQUALAND')
    objective_key = 'ALENTEJO'        # 'Control the Village and the Hermitage' (template zones and conditions)
    preview_key = 'ALENTEJO'
    obj_loc = 'LOC_Aldea'
    pano = (38000.0, 40000.0)
    core_tint = 0.7
    shadow = dict(length=130.0, width=26.0, strength=0.45, direction=(-0.5, -0.85))   # 28's long NW shadows
    VILLAGE = ('CasaA.V3D', 'CasaB.V3D', 'CasaD.V3D', '28ComplementosPueblo.V3D')
    BOSQUES = ('28BosqueA.V3D', '28BosqueB.V3D', '28BosqueC.V3D', '28BosqueD.V3D')
    KOPJES = [(22500, 45000, 5200, 9000, 0.15, 1500), (67500, 47500, 3600, 4200, 0.6, 1700)]
    RIVER = [(0, 36500), (9000, 33500), (17500, 31500), (26500, 34500), (35000, 33000), (42500, 29500),
             (49500, 32500), (56000, 36500), (63000, 35000), (69500, 38500), (75000, 41000)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_SABANA_ATACANTE_1':
            'Open grassland as far as the eye can see, a few trees, a rocky kopje and a dry riverbed. '
            'There is little cover here: the riverbed and the kopje are the only shelter.',
        'LTEXT_TEXTUISECUENCIAS_SABANA_ATACANTE_2':
            'Take the walled village and the chapel to the south. Both must be ours.',
        'LTEXT_TEXTUISECUENCIAS_SABANA_DEFENSOR_1':
            'The enemy must cross the open grass under our eyes. Let them come.',
        'LTEXT_TEXTUISECUENCIAS_SABANA_DEFENSOR_2':
            'Hold the village or the chapel. As long as one of them is ours, so is this land.',
    }

    def core_shapes(self, ctx):
        return [self.cons_geom(ctx, self.VILLAGE, 1800.0), self.cons_geom(ctx, ('28Ermita.V3D', '28ComplementosErmita.V3D'), 1600.0)]

    def tex_core_geom(self, ctx):                                     # + the painted shade of the tree clumps
        from shapely.geometry import Point
        from shapely.ops import unary_union
        return unary_union([ctx.core_union] + [Point(x, z).buffer(2300.0) for x, z in self._bosques])

    def river(self):
        rng = np.random.default_rng(self.seed + 3)
        return chaikin(self.RIVER, rng, 700.0, 2500.0)

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        ob = ctx.m.get(lvl.OBJECTLIST)
        self._bosques = [(o['matrix'][12], o['matrix'][14]) for o in ob['instances']
                         if ob['library'][o['cls']]['model'] in self.BOSQUES]
        hs = ndimage.gaussian_filter(ctx.h0, 5)
        hill = blob(X, Z, 22500, 45000, 7000, 11500, 0.15)              # the template's western hill
        h = 900.0 + 0.35 * (hs - 900.0) * (1 - hill)
        h += 450.0 * (fbm(X, Z, rng, 14000.0, 3) - 0.5) + 120.0 * (fbm(X, Z, rng, 3000.0, 2) - 0.5)
        # kopjes: piles of granite domes, steep bouldery flanks
        rid = fbm(X, Z, rng, 2200.0, 3, ridged=True)
        ctx.kop = np.zeros((N, N))
        for cx, cz, rx, rz, a, hh in self.KOPJES:
            ca, sa = math.cos(a), math.sin(a)
            u = ((X - cx) * ca + (Z - cz) * sa) / rx
            v = (-(X - cx) * sa + (Z - cz) * ca) / rz
            r = np.hypot(u, v) * (1 + 0.18 * (fbm(X, Z, rng, 3000.0, 2) - 0.5))
            b = 1 - smoothstep(0.05, 1.0, r)                          # a rounded dome, not a mesa
            ctx.kop = np.maximum(ctx.kop, b)
            h += hh * b ** 1.4 * (0.8 + 0.4 * fbm(X, Z, rng, 4000.0, 2)) + 320.0 * b * rid
        # the dry riverbed: a sandy bed 12-16 m wide, about 3 m below gentle banks
        d, s = polyline_dist(X, Z, self.river())
        half = 650.0 + 150.0 * fbm(X, Z, rng, 7000.0, 2)
        prof = 1.0 - smoothstep(half, half + 1800.0, d)
        rim = ndimage.uniform_filter(h, 7)
        h = h * (1 - prof) + (rim - 300.0) * prof
        return h

    def regions(self, ctx):
        from shapely.geometry import LineString
        bed = LineString(self.river()).buffer(700.0, 4)
        return [(bed.difference(ctx.keep_polys.buffer(500)), dict(type=TT['ARIDO'], a=1))]

    def tree_prob(self, ctx, name):
        X, Z = GX, GZ
        d, _ = polyline_dist(X, Z, self.river())
        sl = slope_deg(ctx.h)
        p = 0.35 + 2.2 * np.exp(-((d - 1700.0) / 900.0) ** 2) + 0.9 * smoothstep(0.05, 0.3, ctx.kop) * (1 - smoothstep(0.5, 0.8, ctx.kop))
        ok = (sl < 24) & (band(X, Z, 3000, 5000) > 0.5) & ~grid_mask(ctx.keep_polys, 900.0)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9500
        for x, z in self._bosques:
            ok &= np.hypot(X - x, Z - z) > 3000
        return p * ok

    def tree_min_dist(self, name):
        return 1500.0

    def sounds(self, ctx):
        return [['S_VIENTO', 25, 24000.0, 1200.0, 30000.0, 40000.0], ['S_PAJAROS3', 90, 11000.0, 2900.0, 40000.0, 30000.0]]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # the herd: on the grass by the riverbed
            l['pos'][0], l['pos'][2] = 52000.0, 26500.0

    def tracks(self):
        rng = np.random.default_rng(self.seed + 4)
        return [chaikin([(48500, 0), (48000, 14000), (49500, 26000), (48500, 38000), (46500, 49000), (45800, 53500)], rng, 800.0),
                chaikin([(49000, 18000), (53000, 19200)], rng, 200.0),
                chaikin([self.att, (22000, 21500), (33000, 24000), (42000, 26500), (49200, 27000)], rng, 900.0),
                chaikin([(47800, 58000), (54000, 59500), self.dfn], rng, 400.0),
                chaikin([(43500, 57500), (34000, 61000), (20000, 63500), (0, 66000)], rng, 900.0)]

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c28, c26, c57, c58 = composite('28'), composite('26'), composite('57'), composite('58')
        tawny = lambda r, g, b: r > 75 and r - b > 40 and g > 0.62 * r                      # noqa: E731
        gold = lambda r, g, b: r > 120 and r - b > 70 and g > 80                              # noqa: E731
        g1 = synth(shape, c28, pick_boxes(c28, tawny, k=8), rng, flat=26.0)
        g2 = synth(shape, c26, pick_boxes(c26, gold, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 8000.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1400.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 360.0, 3), TEX)
        g2 = g2 * (g1.reshape(-1, 3).mean(0) / g2.reshape(-1, 3).mean(0) * 0.5 + 0.5)[None, None, :]
        w2 = np.clip((noise - 0.4) * 2.2 + (fine - 0.5) * 0.8, 0, 1)
        img = g1 * (1 - w2[..., None]) + g2 * w2[..., None]
        del g1, g2
        img *= np.array([1.04, 1.0, 0.86], np.float32)                # sun-bleached, a touch warmer
        # red laterite showing through in patches (bare earth of the Andalusian map, reddened)
        earth = lambda r, g, b: r > 110 and r - b > 60 and g < 0.8 * r                       # noqa: E731
        red = synth(shape, c26, pick_boxes(c26, earth, k=6, win=256), rng, flat=30.0, patch=256, step=192)
        red = red * np.array([1.04, 0.88, 0.76], np.float32)
        w_e = np.clip((up(fbm(Xw, Zw, rng, 3500.0, 4)) - 0.64) * 2.5 + (hf - 0.5) * 0.5, 0, 0.35)
        img = img * (1 - w_e[..., None]) + red * w_e[..., None]
        # termite mounds: small red cones with a sunny side
        for (x, z) in scatter(np.ones((N, N)) * band(GX, GZ, 4000, 6000), 140, rng, min_dist=1800.0):
            c, r = (int(v) for v in lvl_tex.world_to_px(x, z, SIZE, TEX))
            rr = int(rng.uniform(5, 9))
            if rr < c < TEX - rr - 1 and rr < r < TEX - rr - 1:
                yy, xx = np.mgrid[-rr:rr + 1, -rr:rr + 1]
                m = np.clip(1 - np.hypot(xx, yy) / rr, 0, 1)[..., None]
                lit = (1.0 + 0.25 * np.clip((xx - yy) / rr, -1, 1))[..., None]
                img[r - rr:r + rr + 1, c - rr:c + rr + 1] = img[r - rr:r + rr + 1, c - rr:c + rr + 1] * (1 - m * 0.8) + \
                    red[r - rr:r + rr + 1, c - rr:c + rr + 1] * lit * m * 0.8
        del red
        # kopjes: granite boulders (the Tunisian map's rocks) on the domes and steep flanks
        slope = up(ndimage.gaussian_filter(slope_deg(ctx.h)[::-1], 0.7), TEX)
        kop = up(ctx.kop[::-1].astype(np.float32))
        rocky = lambda r, g, b: r < 175 and r - b > 25                                        # noqa: E731
        rock = synth(shape, c57, pick_boxes(c57, rocky, k=6, win=256), rng, flat=0, patch=256, step=160)
        rock *= np.array([0.86, 0.86, 0.9], np.float32)               # greyer granite
        blk = up(fbm(Xw, Zw, rng, 900.0, 3))                            # boulders with grass between them
        w_r = smoothstep(0.3, 0.6, kop + 0.35 * (blk - 0.5) + 0.2 * (hf - 0.5)) * 0.85
        w_r = np.maximum(w_r, smoothstep(22.0, 30.0, slope + 8 * (hf - 0.5)) * 0.85)
        img = img * (1 - w_r[..., None]) + rock * w_r[..., None]
        del rock
        # the dry riverbed: pale sand, darker damp line in the middle, shaded banks
        d = up(polyline_dist(Xw, Zw, self.river())[0])
        sandy = lambda r, g, b: r > 170 and g > 125 and b > 75 and r - b > 55                  # noqa: E731
        sand = synth(shape, c58, pick_boxes(c58, sandy, k=6, win=256), rng, flat=24.0, patch=256, step=192)
        sand = sand * (img.reshape(-1, 3).mean(0) / sand.reshape(-1, 3).mean(0) * np.array([1.12, 1.08, 1.0]))[None, None, :]
        bed = (1 - smoothstep(420.0, 820.0, d + 260 * (fine - 0.5) + 200 * (hf - 0.5))) * 0.8
        img = img * (1 - bed[..., None]) + sand * bed[..., None]
        img *= (1 - 0.07 * (1 - smoothstep(100.0, 520.0, d + 260 * (hf - 0.5) + 200 * (fine - 0.5))))[..., None]
        bank = np.exp(-((d - 1050.0) / 520.0) ** 2) * 0.12 * (0.4 + 1.2 * hf)                # shaded, bushy banks
        img *= (1 - bank)[..., None]
        del sand
        img = self.paint_tracks(img, self.tracks(), (150, 92, 56), noise, hf, alpha=0.55)
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.92 + 0.16 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 7: Siberian taiga (21 Kiev)
class Taiga(Recipe):
    """Snow, belts of dark fir forest on low ridges with clearings between them, the frozen river with its
    tributary and the wooden bridge of the Kiev map, and its palisaded log farm standing as the ostrog on the
    far bank; the attacker comes out of the forest in the south."""
    name = 'taiga'
    key = 'TAIGA'
    folder = 'NBTaiga'
    lvl_name = 'NBTaiga.lvl'
    template = '21'
    seed = 1796
    att = (33000.0, 13500.0)
    dfn = (43500.0, 61500.0)
    default_attrs = dict(type=TT['NIEVE_NO_PROFUNDA'], a=1)
    relocate_sets = ('Arbolesdeentorno.V3D',)
    outside_take = {'Arbolesdeentorno.V3D': 0.3}
    fir_shadows = dict(length=270.0, width=24.0, direction=(-0.998, 0.06), strength=1.0, tint_k=(0.56, 0.52, 0.38))
    provinces = ('URAL', 'SIBERIA', 'W_YENISEI', 'W_YAKUTSK', 'W_OKHOTSK', 'W_KAMCHATKA', 'W_AMUR', 'W_SAKHALIN')
    objective_key = 'EGIPTO'          # 'Control the Village' (the zone holds the ostrog)
    preview_key = 'KIEV'
    obj_loc = 'LOC_Granja'
    pano = (38000.0, 34000.0)
    core_tint = 0.0
    OSTROG = ('GranjaVallas.V3D',)
    # forest belts: (polyline, half width cm) on low ridges; the gaps between them are the clearings and rides
    BELTS = [([(0, 31000), (9000, 33500), (18000, 32000), (26500, 34500)], 3800.0),
             ([(44000, 27500), (52000, 30500), (61000, 27000), (70000, 29500), (75000, 28000)], 3600.0),
             ([(9000, 45000), (12500, 54000), (11000, 63000), (15000, 71000)], 3200.0),
             ([(63500, 69000), (69000, 64000), (75000, 61000)], 3000.0),
             ([(48000, 8000), (56000, 14500), (62000, 22000)], 2600.0),
             ([(2000, 12000), (10000, 8500), (17000, 4000)], 3000.0),
             ([(26000, 47000), (30500, 53500), (27000, 58000)], 2200.0)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_TAIGA_ATACANTE_1':
            'Snow, fir forest without end and a frozen river. Advance through the clearings; the ice will '
            'carry our men, but no horse can charge on it.',
        'LTEXT_TEXTUISECUENCIAS_TAIGA_ATACANTE_2':
            'Beyond the river stands their wooden fort behind its palisade. Take it.',
        'LTEXT_TEXTUISECUENCIAS_TAIGA_DEFENSOR_1':
            'The enemy comes out of the forest to the south. Meet them at the river.',
        'LTEXT_TEXTUISECUENCIAS_TAIGA_DEFENSOR_2':
            'Hold the fort behind its palisade. Out here it is the only shelter for a hundred miles.',
    }

    def core_shapes(self, ctx):
        ctx.ice0 = self.water_geom(ctx, ('TERRENO_HELADO',))
        return [ctx.ice0.buffer(1000.0), self.cons_geom(ctx, self.OSTROG + ('21GranjaBorde.V3D',), 2200.0)]

    def belts(self, X, Z, rng_seed=9):
        rng = np.random.default_rng(self.seed + rng_seed)
        warp = (fbm(X, Z, rng, 7000.0, 3) - 0.5) * 2600.0
        b = np.zeros(X.shape)
        for line, hw in self.BELTS:
            d, _ = polyline_dist(X, Z, line)
            b = np.maximum(b, 1 - smoothstep(hw * 0.7, hw * 1.1, d + warp))
        return b

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        hs = ndimage.gaussian_filter(ctx.h0, 4)
        h = 900.0 + 0.6 * (hs - 900.0)
        h += 350.0 * (fbm(X, Z, rng, 12000.0, 3) - 0.5) + 90.0 * (fbm(X, Z, rng, 2500.0, 2) - 0.5)
        ctx.belt = b = self.belts(X, Z)
        h += ndimage.gaussian_filter(b, 3) * (650.0 + 500.0 * fbm(X, Z, rng, 9000.0, 3))   # the woods on low ridges
        return h

    def regions(self, ctx):
        """The belts as forest (BOSQUE, as the Kiev map's own woods)."""
        wood = (ctx.belt > 0.5) & ~grid_mask(ctx.keep_polys, 1200.0)
        g = mask_polygons(ndimage.binary_opening(wood, iterations=2), simplify=700.0, min_cells=80)
        return [] if g is None else [(g, dict(type=TT['BOSQUE'], a=1))]

    def conditions(self, ctx):
        return self.zone_conditions(ctx, self.OSTROG, 'AreaAldea', 2800.0)

    def tree_prob(self, ctx, name):
        rng = np.random.default_rng(self.seed + 11)
        X, Z = GX, GZ
        sl = slope_deg(ctx.h)
        b = ctx.belt
        p = 0.08 + 3.0 * b + 0.6 * smoothstep(0.68, 0.8, fbm(X, Z, rng, 4000.0, 3)) * (1 - b)
        ok = (sl < 28) & (band(X, Z, 2000, 3500) > 0.5) & ~grid_mask(ctx.keep_polys, 700.0)
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9500
        from shapely.geometry import LineString
        for line in self.tracks():
            ok &= ~grid_mask(LineString(line), 600.0)
        return p * ok

    def tree_min_dist(self, name):
        return 620.0

    def tracks(self):
        rng = np.random.default_rng(self.seed + 3)
        return [chaikin([self.att, (35500, 24000), (38500, 32500), (45500, 39000), (52500, 42800), (56500, 44000)], rng, 500.0),
                chaikin([(58200, 45500), (60000, 50500), (61000, 56500)], rng, 300.0),
                chaikin([self.dfn, (48500, 56500), (52500, 51500), (56500, 46000)], rng, 400.0),
                chaikin([(0, 22000), (12000, 21000), (22000, 17500), self.att], rng, 600.0),
                chaikin([(63500, 60500), (69000, 60000), (75000, 57000)], rng, 300.0)]

    def sounds(self, ctx):
        return [['S_VIENTO', 25, 24000.0, 1200.0, 30000.0, 40000.0], ['S_VIENTO', 25, 20000.0, 1100.0, 60000.0, 20000.0]]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: at the forest edges
            k = getattr(self, '_wk', 0)
            l['pos'][0], l['pos'][2] = [(20000.0, 40000.0), (66000.0, 36000.0), (20000.0, 25000.0)][k % 3]
            self._wk = k + 1

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c21, c39, c19 = composite('21'), composite('39'), composite('19')
        snow = lambda r, g, b: r > 175 and b > 180 and abs(r - b) < 30                        # noqa: E731
        s1 = synth(shape, c21, pick_boxes(c21, snow, k=8), rng, flat=26.0)
        s2 = synth(shape, c39, pick_boxes(c39, snow, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 7000.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.2 + (fine - 0.5) * 0.7, 0, 1)
        img = s1 * (1 - w2[..., None]) + s2 * w2[..., None]
        del s1, s2
        # grey-green ground showing through the thin snow of the clearings (the Kiev and Kursk fields)
        thin = lambda r, g, b: 110 < r < 190 and g >= r - 5 and b < g + 15                   # noqa: E731
        gr = synth(shape, c19, pick_boxes(c19, thin, k=6, win=256), rng, flat=26.0, patch=256, step=192)
        belt = up(ctx.belt[::-1].astype(np.float32))
        w_g = np.clip((up(fbm(Xw, Zw, rng, 4500.0, 3)) - 0.58) * 2.4 + (hf - 0.5) * 0.5, 0, 0.6) * (1 - belt)
        img = img * (1 - w_g[..., None]) + gr * w_g[..., None]
        del gr
        # forest floor: trodden, blue-grey snow under the firs
        img *= (1 - 0.16 * smoothstep(0.2, 0.8, belt + 0.2 * (fine - 0.5)))[..., None] * np.array([1.0, 1.0, 1.03], np.float32)
        # where the firs stand close, the dark blue mass of their crowns (painted like the Kiev map's woods)
        dens = np.zeros((TEX // 4, TEX // 4), np.float32)
        for x, y, z in ctx.trees_xyz:
            c, r = (int(v) // 4 for v in lvl_tex.world_to_px(x, z, SIZE, TEX))
            if 0 <= c < TEX // 4 and 0 <= r < TEX // 4:
                dens[r, c] += 1.0
        dens = up(ndimage.gaussian_filter(dens, 25.0) * (2 * math.pi * 625.0))         # trees per ~2000 m2
        massy = lambda r, g, b: r < 100 and b > r + 12 and b < 150                             # noqa: E731
        mass = synth(shape, c21, pick_boxes(c21, massy, k=5, win=192), rng, flat=0, patch=192, step=128)
        w_m = smoothstep(4.0, 9.0, dens + 3.0 * (hf - 0.5) + 2.0 * (fine - 0.5)) * 0.75
        img = img * (1 - w_m[..., None]) + mass * w_m[..., None]
        del mass
        img = self.paint_tracks(img, self.tracks(), (150, 146, 140), noise, hf, alpha=0.45, rut=0.18)
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.95 + 0.08 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ original models of other maps (third batch)
IDENT = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def add_object(ob, typ, model, inst=None):
    """Append a library class for an original model shipped in the map folder and one instance of it, both at the
    END of their lists (the construction indices of the victory conditions stay valid). Decor / tree sets sit at
    the origin like the originals' (identity matrix); an ice / water instance brings its own record."""
    ob['library'].append(dict(type=typ, model=model, res=[0, 0]))
    o = dict(type=typ, cls=0, matrix=list(IDENT), flags=0, res=[0, 0]) if inst is None else inst
    o['cls'] = len(ob['library']) - 1
    ob['instances'].append(o)
    return o


def ship_borrowed(mdir, scen, src, new):
    """Copy an original model of another map into a map folder (as `new`, unless written already, e.g. a
    relocated tree set) with the textures it names that the folder lacks. A texture of the same name already in
    the folder wins (a borrowed lake then mirrors the template's own sky: AguaReflexionLagos.tga)."""
    sdir = os.path.join(scen_dir(scen), 'Models')
    if find_file(mdir, new) is None:
        shutil.copyfile(find_file(sdir, src), os.path.join(mdir, new))
    for f in sorted(refs_of(find_file(sdir, src))):
        p = find_file(sdir, f)
        if p and find_file(mdir, f) is None:
            shutil.copyfile(p, os.path.join(mdir, os.path.basename(p)))


def node_extent(tv, o):
    """(height cm, u0, u1, v0, v1) of one V3D mesh node: its vertex heights and first UV set (the atlas cell of a
    canopy). Vertex = position, [normal if fmt & 0x10], uv..."""
    import struct
    vh = o['m2'] - 64 + 252
    flag, size, fmt, stride, nv = struct.unpack_from('<5I', tv, vh)
    uo = 24 if fmt & 0x10 else 12
    ys = [struct.unpack_from('<f', tv, vh + 20 + k * stride + 4)[0] for k in range(nv)]
    uv = [struct.unpack_from('<2f', tv, vh + 20 + k * stride + uo) for k in range(nv)]
    return (max(ys) - min(ys), min(a for a, b in uv), max(a for a, b in uv), min(b for a, b in uv),
            max(b for a, b in uv))


def deshadow(img, mask, win=41, pct=80, lo=0.72, hi=0.93):
    """Painted tree shadows lifted inside mask (1024 x 1024 north-up raster): pixels much darker than the local
    bright ground (80th percentile of the luminance over ~11 m) take the local colour of the unshadowed ground."""
    f = img.astype(np.float32)
    lum = f.mean(-1)
    small = np.asarray(ndimage.zoom(lum, 0.25, order=1))
    bg = up(ndimage.percentile_filter(small, pct, size=win), img.shape[0])
    s = smoothstep(hi, lo, lum / (bg + 1.0)) * up(ndimage.gaussian_filter(mask.astype(np.float32), 2.0), img.shape[0])
    clear = (1 - smoothstep(0.0, 0.3, s))
    col = np.stack([ndimage.gaussian_filter(f[..., k] * clear, 24) for k in range(3)], -1)
    col /= ndimage.gaussian_filter(clear, 24)[..., None] + 1e-3
    out = f * (1 - s[..., None]) + col * s[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ recipe 8: tropical jungle (02 Escocia)
class Jungle(Recipe):
    """Dense belts of broadleaf jungle (the Scottish map's own leafy trees, its outside woods partly brought in)
    with palms and palm undergrowth at their edges, along the river and in the swamps (Tunisia's palm set, the
    originals' tropical-looking palms); a swampy lowland (mud) by the lake and along the river, crossed by a
    causeway; the river and lake of the Scotland map with its two bridges, and its hamlet at the river mouth
    standing as the trading post in its clearing. The hermitage on the north-eastern hill is gone: the attacker
    comes down from there through the jungle."""
    name = 'jungle'
    key = 'SELVA'
    folder = 'NBSelva'
    lvl_name = 'NBSelva.lvl'
    template = '02'
    seed = 1797
    att = (58500.0, 61000.0)
    dfn = (21500.0, 41000.0)
    remove_models = ('02Ermita.V3D', '02ErmitaHierba.V3D')
    relocate_sets = ('ArbolesB.V3D',)
    outside_take = {'ArbolesB.V3D': 0.45}            # part of the outside woods comes in as jungle
    PALMS = 'PalmerasSelva.V3D'
    borrow = (('57', 'Arbolesdeentorno.V3D', PALMS),)   # 191 palms + 430 palm shrubs (Setarboldesierto atlas)
    provinces = ('W_ACEH', 'W_SOUTH_SUMATRA', 'W_NORTH_BORNEO', 'W_SOUTH_BORNEO', 'W_CELEBES', 'W_MOLUCCAS',
                 'W_MINDANAO', 'W_TIMOR', 'W_NEW_GUINEA', 'W_PAPUA', 'W_MADAGASCAR', 'W_SIERRA_LEONE',
                 'W_IVORY_COAST', 'W_LOANGO', 'W_ZANZIBAR_COAST')
    objective_key = 'EGIPTO'          # 'Control the Village' (the zone holds the trading post)
    preview_key = 'ESCOCIA'
    obj_loc = 'LOC_aldea'
    pano = (36000.0, 38000.0)
    details = ((36000.0, 28500.0), (50000.0, 47000.0))
    core_tint = 0.65
    blend = 3000.0
    VILLAGE = ('_01CasaA.V3D', '_01CasaB.V3D', '_01CasaC.V3D', '_01CasaD.V3D')
    SWAMPS = [(36000, 28500, 8500, 4600, 0.44), (7000, 27500, 6500, 5500, 0.0), (36500, 13500, 6500, 3600, 0.3)]
    JUNGLE_SHARE = 0.4                # of the open land
    texts = {
        'LTEXT_TEXTUISECUENCIAS_SELVA_ATACANTE_1':
            'Jungle closes in on every side, and the swamps by the river swallow men to the knee. '
            'Keep to the tracks and the clearings; the river can only be crossed at the bridges.',
        'LTEXT_TEXTUISECUENCIAS_SELVA_ATACANTE_2':
            'The trading post stands in its clearing at the river mouth. Take it and hold it.',
        'LTEXT_TEXTUISECUENCIAS_SELVA_DEFENSOR_1':
            'The enemy must cut his way through the jungle. Let the swamps and the river break up his columns.',
        'LTEXT_TEXTUISECUENCIAS_SELVA_DEFENSOR_2':
            'Hold the trading post by the river mouth. Whoever holds it holds the river and its trade.',
    }

    def core_shapes(self, ctx):
        ctx.water0 = self.water_geom(ctx, ('RIO_POCO_PROFUNDO',))
        ctx.water_mask = grid_mask(self.water_geom(ctx, ('RIO_POCO_PROFUNDO',), special=False))
        ob = ctx.m.get(lvl.OBJECTLIST)
        ctx.houses = [(o['matrix'][12], o['matrix'][14]) for o in ob['instances']
                      if ob['library'][o['cls']]['model'] in self.VILLAGE]
        return [ctx.water0.buffer(1500.0), self.cons_geom(ctx, self.VILLAGE, 1800.0)]

    def swamp_field(self, X, Z):
        rng = np.random.default_rng(self.seed + 5)
        wob = (fbm(X, Z, rng, 3500.0, 3) - 0.5) * 0.5
        s = np.zeros(X.shape)
        for cx, cz, rx, rz, a in self.SWAMPS:
            s = np.maximum(s, blob(X, Z, cx, cz, rx, rz, a, power=2.0))
        return np.clip(s + wob * (s > 0.02), 0, 1)

    def tracks(self):
        rng = np.random.default_rng(self.seed + 3)
        return [chaikin([self.att, (52000, 54500), (45000, 48000), (37000, 41500), (29500, 35000), (23500, 29000),
                         (19500, 25000)], rng, 600.0),                                 # down to the trading post
                chaikin([self.dfn, (20500, 33000), (19000, 26500)], rng, 300.0),
                chaikin([(21500, 22300), (27500, 23200), (34000, 26200), (41000, 29000), (48000, 32500),
                         (55000, 37500), (61000, 42800)], rng, 400.0),                 # north bank: the causeway
                chaikin([(64800, 39600), (58000, 33000), (51000, 27000), (43000, 19500), (34000, 15200),
                         (24600, 16300)], rng, 500.0),                                 # south bank, bridge to bridge
                chaikin([(23800, 15200), (25500, 7000), (26500, 0)], rng, 300.0),
                chaikin([(62300, 43500), (68000, 49500), (75000, 52500)], rng, 300.0)]

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        big = ndimage.gaussian_filter(ctx.h0, 14)
        h = big + 0.45 * (ndimage.gaussian_filter(ctx.h0, 4) - big)                 # the highland softened to
        h += 160.0 * (fbm(X, Z, rng, 9000.0, 3) - 0.5) + 60.0 * (fbm(X, Z, rng, 2200.0, 2) - 0.5)   # jungle hills
        # the swamps: flats a little below their surroundings
        ctx.swamp = self.swamp_field(X, Z)
        w = smoothstep(0.2, 0.6, ctx.swamp)
        h = h * (1 - w) + (ndimage.gaussian_filter(h, 6) - 60.0) * w
        # the jungle: organic masses, thinned to clearings round the trading post, the deployment areas, the
        # swamps and the river banks (palms there), a little denser on the hills
        rb = np.random.default_rng(self.seed + 9)
        b = fbm(X, Z, rb, 15000.0, 4) + 0.06 * (fbm(X, Z, rb, 4000.0, 2) - 0.5)
        ctx.dw = dw = ndimage.distance_transform_edt(~ctx.water_mask) * CELL
        ctx.dv = dv = np.min([np.hypot(X - x, Z - z) for x, z in ctx.houses], 0)
        b -= 0.55 * (1 - smoothstep(6500.0, 11500.0, dv))
        for cx, cz in (self.att, self.dfn):
            b -= 0.7 * (1 - smoothstep(10000.0, 14000.0, np.hypot(X - cx, Z - cz)))
        b -= 0.45 * smoothstep(0.15, 0.5, ctx.swamp)
        b -= 0.35 * (1 - smoothstep(1800.0, 4500.0, dw))
        b += 0.10 * smoothstep(4400.0, 6500.0, h)
        land = ~ctx.water_mask & (band(X, Z, 2500.0, 2600.0) > 0.5)
        t = float(np.quantile(b[land], 1 - self.JUNGLE_SHARE))
        ctx.belt = smoothstep(t - 0.035, t + 0.035, b)
        return h

    def regions(self, ctx):
        """The jungle as forest (BOSQUE, like the Kiev map's woods), the swamps as mud (BARRIZAL: the paddies of
        the rice map, 19.8 ha on Champagne) with the causeway firm through them."""
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        out = []
        wood = (ctx.belt > 0.5) & ~grid_mask(ctx.keep_polys, 1200.0)
        g = mask_polygons(ndimage.binary_opening(wood, iterations=2), simplify=700.0, min_cells=80)
        if g is not None:
            out.append((g, dict(type=TT['BOSQUE'], a=1)))
        sw = mask_polygons(ctx.swamp > 0.45, simplify=400.0, min_cells=20)
        if sw is not None:
            firm = unary_union([LineString(t).buffer(450.0) for t in self.tracks()])
            out.append((sw.difference(firm).difference(ctx.keep_polys.buffer(400)), dict(type=TT['BARRIZAL'], a=1)))
        return out

    def conditions(self, ctx):
        return self.zone_conditions(ctx, self.VILLAGE, 'AreaAldea', 2600.0)

    def tree_ok(self, ctx):
        if getattr(ctx, 'tree_ok', None) is None:
            from shapely.geometry import LineString
            ok = (slope_deg(ctx.h) < 30) & (band(GX, GZ, 2500, 4500) > 0.5) & ~grid_mask(ctx.keep_polys, 600.0)
            for cx, cz in (self.att, self.dfn):
                ok &= np.hypot(GX - cx, GZ - cz) > 9500
            for line in self.tracks():
                ok &= ~grid_mask(LineString(line), 550.0)
            ctx.tree_ok = ok
        return ctx.tree_ok

    def tree_prob(self, ctx, name):                                    # broadleaf: the jungle belts
        return (0.03 + 3.0 * ctx.belt) * self.tree_ok(ctx)

    def palm_prob(self, ctx, kind):
        soft = ndimage.gaussian_filter(ctx.belt, 2.5)
        edge = np.clip(soft * (1 - soft) * 4.0, 0, 1)
        bank = np.exp(-((ctx.dw - 2600.0) / 1300.0) ** 2)
        ring = np.exp(-((ctx.dv - 8000.0) / 2500.0) ** 2)
        sw = smoothstep(0.1, 0.5, ctx.swamp)
        if kind == 'palm':
            p = 0.05 + 1.6 * edge + 2.4 * bank + 1.4 * sw * (1 - smoothstep(0.75, 0.95, ctx.swamp)) + 1.2 * ring + 0.25 * ctx.belt
        else:                                                          # palm shrubs: undergrowth
            p = 0.05 + 2.0 * edge + 0.7 * ctx.belt + 1.2 * sw + 0.8 * bank
        return p * self.tree_ok(ctx)

    def tree_min_dist(self, name):
        return 500.0

    def relocate(self, ctx, name, tv):
        """The borrowed palm set: palms (trunk + crown) and palm shrubs are placed apart; the rest as usual."""
        if name != self.PALMS:
            return Recipe.relocate(self, ctx, name, tv)
        T = lvl_v3d.trees(tv)
        ctx.palms_xyz = []
        for kind, group, md in (('palm', [tc for tc in T if tc[1]], 650.0), ('shrub', [tc for tc in T if not tc[1]], 330.0)):
            pts = scatter(self.palm_prob(ctx, kind), len(group), ctx.rng, min_dist=md)
            for (trunk, canopies), (x, z) in zip(group, pts):
                x0, y0, z0 = lvl_v3d.translation(tv, trunk['m2'])
                y = ctx.H(x, z) - 15.0
                lvl_v3d.move_tree(tv, trunk, canopies, x - x0, y - y0, z - z0)
                if kind == 'palm':
                    ctx.palms_xyz.append((x, y, z))
            for trunk, canopies in group[len(pts):]:
                lvl_v3d.move_tree(tv, trunk, canopies, 0.0, -20000.0, 0.0)
            print('  %s %s: %d placed, %d sunk' % (name, kind, len(pts), len(group) - len(pts)))
        allp = np.array([lvl_v3d.translation(tv, t['m2']) for t, c in T])
        lvl_v3d.set_global_bbox(tv, [float(allp[:, 0].min() - 800), float(allp[:, 1].min() - 50), float(allp[:, 2].min() - 800)],
                                [float(allp[:, 0].max() + 800), float(allp[:, 1].max() + 2500), float(allp[:, 2].max() + 800)])

    def build(self):
        ctx = super().build()
        ob = ctx.m.get(lvl.OBJECTLIST)
        for scen, src, new in self.borrow:                            # the palms: a decor set of their own
            tv = bytearray(open(find_file(os.path.join(scen_dir(scen), 'Models'), src), 'rb').read())
            self.relocate(ctx, new, tv)
            ctx.sets[new] = tv
            add_object(ob, lvl.TO_DECORADO, new)
        return ctx

    def write(self):
        mm = super().write()
        for scen, src, new in self.borrow:
            ship_borrowed(os.path.join(BM, self.folder, 'Models'), scen, src, new)
        return mm

    def sounds(self, ctx):
        return [['S_PAJAROS1', 100, 11000.0, 2900.0, 45000.0, 50000.0], ['S_PAJAROS2', 100, 10000.0, 2800.0, 12000.0, 50000.0],
                ['S_PAJAROS3', 90, 11000.0, 2900.0, 62000.0, 22000.0], ['S_PAJAROS1', 100, 10000.0, 2800.0, 38000.0, 10000.0]]

    WILD = [(46000.0, 40000.0), (9000.0, 45000.0), (31000.0, 7000.0), (66000.0, 28000.0)]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: in the clearings
            k = getattr(self, '_wk', 0)
            l['pos'][0], l['pos'][2] = self.WILD[k % len(self.WILD)]
            self._wk = k + 1

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c40, c16, c24, c04 = (composite(s) for s in ('40', '16', '24', '04'))
        green = lambda r, g, b: g > b + 25 and r - g < 12 and 55 < g < 115                  # noqa: E731
        g1 = synth(shape, c40, pick_boxes(c40, green, k=8), rng, flat=26.0)
        g2 = synth(shape, c16, pick_boxes(c16, green, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 6500.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.4 + (fine - 0.5) * 0.7, 0, 1)
        img = g1 * (1 - w2[..., None]) + g2 * w2[..., None]
        del g1, g2
        img *= np.array([0.96, 1.12, 0.86], np.float32)               # humid green
        # jungle floor: dark, mossy, mottled (the Hungary map's wood shade)
        dark = lambda r, g, b: g > b + 8 and g < 62 and r < 72                                # noqa: E731
        floor = synth(shape, c16, pick_boxes(c16, dark, k=6), rng, flat=0, patch=256, step=192)
        floor *= np.array([0.8, 0.95, 0.74], np.float32)
        belt = up(ndimage.gaussian_filter(ctx.belt, 1.2)[::-1].astype(np.float32))     # soft wood edges
        w_f = smoothstep(0.25, 0.65, belt + (fine - 0.5) * 0.3 + (hf - 0.5) * 0.15) * 0.9
        img = img * (1 - w_f[..., None]) + floor * w_f[..., None]
        img *= (1 - 0.18 * w_f)[..., None]
        del floor
        # where the trees stand close, the dark mass of their crowns (painted like the originals' woods)
        dens = np.zeros((TEX // 4, TEX // 4), np.float32)
        for x, y, z in ctx.trees_xyz:
            c, r = (int(v) // 4 for v in lvl_tex.world_to_px(x, z, SIZE, TEX))
            if 0 <= c < TEX // 4 and 0 <= r < TEX // 4:
                dens[r, c] += 1.0
        dens = up(ndimage.gaussian_filter(dens, 25.0) * (2 * math.pi * 625.0))
        massy = lambda r, g, b: g < 62 and g > b + 4 and r < g + 4                             # noqa: E731
        mass = synth(shape, c24, pick_boxes(c24, massy, k=5, win=192), rng, flat=0, patch=192, step=128)
        mass *= np.array([0.86, 1.02, 0.8], np.float32)
        w_m = smoothstep(3.0, 8.0, dens + 3.0 * (hf - 0.5) + 2.0 * (fine - 0.5)) * 0.8
        img = img * (1 - w_m[..., None]) + mass * w_m[..., None]
        del mass
        # river banks: lusher
        dw = up(ctx.dw[::-1].astype(np.float32))
        img *= (1 - 0.08 * np.exp(-((dw - 2400.0) / 1200.0) ** 2))[..., None]
        # the swamps: dark olive mud (the Wales map's mud patch), pools of murky water (the lake's own water
        # surface, darkened), lighter reed tufts round them
        c, r = (int(v) for v in lvl_tex.world_to_px(67900.0, 42400.0, SIZE, TEX))
        mud = synth(shape, c04, [(c - 128, r - 128, c + 128, r + 128), (c - 200, r - 60, c + 56, r + 196)], rng,
                    flat=20.0, patch=256, step=192)
        mud *= np.array([0.92, 0.96, 0.82], np.float32)
        wt_ = lvl_tex.read_dds(find_file(os.path.join(scen_dir('02'), 'Models'), 'agualagoescocia.tga'))[..., :3]
        water = np.tile(wt_.astype(np.float32), (TEX // wt_.shape[0], TEX // wt_.shape[1], 1))
        water = water * 0.15 + np.array([40, 44, 14], np.float32) * 0.85            # murky, shaded
        sw = up(self.swamp_field(Xw, Zw).astype(np.float32))
        w_s = smoothstep(0.3, 0.6, sw + 0.25 * (fine - 0.5) + 0.15 * (hf - 0.5)) * 0.85
        img = img * (1 - w_s[..., None]) + mud * w_s[..., None]
        pools = smoothstep(0.62, 0.7, up(fbm(Xw, Zw, rng, 1500.0, 3)) + 0.3 * (sw - 0.5)) * smoothstep(0.65, 0.85, sw)
        img = img * (1 - 0.8 * pools[..., None]) + water * (0.8 * pools[..., None])
        reed = np.clip(pools * (1 - pools) * 4.0, 0, 1) * smoothstep(0.55, 0.8, hf) * 0.35
        img = img * (1 - reed[..., None]) + np.array([120, 124, 70], np.float32) * reed[..., None]
        del mud, water
        # tracks: red-brown laterite
        img = self.paint_tracks(img, self.tracks(), (138, 112, 76), noise, hf, width=(5.0, 12.0), alpha=0.55)
        # the palms' frond shadows (the moved broadleaf trees get canopy shadows in finish_texture)
        tpx = [tuple(lvl_tex.world_to_px(x, z, SIZE, TEX)) for x, y, z in ctx.palms_xyz]
        img *= palm_shadows((TEX, TEX), tpx, rng, length=80.0, strength=0.3)[..., None]
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.92 + 0.16 * noise)[..., None]
        return self.finish_texture(ctx, img)


# ------------------------------------------------------------------ recipe 9: Arctic tundra (39 Finlandia)
class Tundra(Recipe):
    """Flat snowy tundra with low wind-scoured ridges and a few stunted trees and shrubs (the Finland map's own
    small trees; its tall firs are gone); the frozen streams of the Finland map, and a frozen lake beside the
    settlement: the Minsk map's Laguna (its ice, basin and shore moved over, levelled to the tundra). The log farm
    and the wooden church of the Finland map are the settlement; the forest clumps and the far field fence are
    gone. The attacker comes from the south-east across the frozen streams."""
    name = 'tundra'
    key = 'TUNDRA'
    folder = 'NBTundra'
    lvl_name = 'NBTundra.lvl'
    template = '39'
    seed = 1798
    att = (64000.0, 13000.0)
    dfn = (14000.0, 57500.0)
    remove_models = ('BosqueA.V3D', 'BosqueB.V3D', 'BosqueC.V3D', 'VallaNieve02.V3D')
    default_attrs = dict(type=TT['NIEVE_NO_PROFUNDA'], a=1)
    fir_shadows = dict(length=120.0, width=15.0, direction=(-0.998, 0.06), strength=0.85, tint_k=(0.56, 0.52, 0.38))
    provinces = ('W_CHUKOTKA',)
    objective_key = 'EGIPTO'          # 'Control the Village' (the zone holds the farm and the church)
    preview_key = 'FINLANDIA'
    obj_loc = 'LOC_Granja'
    pano = (36000.0, 40000.0)
    details = ((40000.0, 52000.0), (52000.0, 26000.0))
    core_tint = 0.0
    tex_core = (100.0, 700.0)
    SETTLEMENT = ('39Granja.V3D', '39Iglesia.V3D')
    LAKE_SRC = ('17', '17Laguna.V3D')
    LAKE_AT = (40000.0, 52000.0)      # new position of the ice instance (Minsk: 49645, 26964)
    STUNTED = 1450.0                  # trees up to this crown height stay (cm)
    # low ridges (eskers, moraines): polyline, half width, height (cm)
    RIDGES = [([(36000, 4000), (42000, 13000), (47000, 22000)], 2600.0, 420.0),
              ([(52000, 30000), (60000, 37000), (68000, 46000)], 2400.0, 380.0),
              ([(14500, 45500), (20000, 46800), (25500, 48500)], 2200.0, 340.0),
              ([(4000, 20000), (10000, 26000), (14000, 34000)], 2400.0, 400.0),
              ([(55000, 62000), (62000, 65500)], 2000.0, 300.0)]
    texts = {
        'LTEXT_TEXTUISECUENCIAS_TUNDRA_ATACANTE_1':
            'Snow and ice to the horizon, a few stunted trees and low ridges. Cross the frozen streams quickly: '
            'on the ice no horse can charge.',
        'LTEXT_TEXTUISECUENCIAS_TUNDRA_ATACANTE_2':
            'The log settlement and its chapel by the frozen lake are our objective. Take them.',
        'LTEXT_TEXTUISECUENCIAS_TUNDRA_DEFENSOR_1':
            'The enemy must cross the frozen streams in the open. Let the cold and our fire do the work.',
        'LTEXT_TEXTUISECUENCIAS_TUNDRA_DEFENSOR_2':
            'Hold the settlement and its chapel. Out here they are the only shelter from the cold.',
    }

    def lake(self):
        """The borrowed lake: Minsk's ice instance, its TERRENO_HELADO sector moved to LAKE_AT, Minsk's heights."""
        if not hasattr(self, '_lake'):
            from shapely.geometry import Point
            import shapely.affinity as aff
            m17 = lvl.load(scen_lvl(self.LAKE_SRC[0]))
            ob = m17.get(lvl.OBJECTLIST)
            inst = next(o for o in ob['instances'] if ob['library'][o['cls']]['model'] == self.LAKE_SRC[1])
            sm = m17.get(lvl.SECTORMAP)
            P = lvl_nav.sector_polygons(sm)
            o0 = Point(inst['matrix'][12], inst['matrix'][14])
            poly = min((P[s['id']] for s in sm['sectors'] if s['type'] == TT['TERRENO_HELADO']), key=o0.distance)
            dx, dz = self.LAKE_AT[0] - o0.x, self.LAKE_AT[1] - o0.y
            self._lake = dict(inst=inst, poly=aff.translate(poly, dx, dz), h=m17.heights().astype(float), dx=dx, dz=dz)
        return self._lake

    def core_shapes(self, ctx):
        from shapely.ops import unary_union
        ctx.ice0 = self.water_geom(ctx, ('TERRENO_HELADO',), special=False)     # (the clumps' interiors are
        ctx.ice_mask = grid_mask(ctx.ice0)                                         # 'special' sectors)
        # the forest clumps' interiors (INTERIOR sectors their constructions do not list) go with the clumps: kept
        # out of the core, or the closing step would keep the one by the western stream
        m = ctx.m
        sm0 = m.get(lvl.SECTORMAP)
        P = lvl_nav.sector_polygons(sm0)
        ob = m.get(lvl.OBJECTLIST)
        owned = set()
        for o in ob['instances']:
            if o['type'] == lvl.TO_CONSTRUCCION:
                owned |= set(m.construction_sectors(o))
        woods = unary_union([P[s['id']] for s in sm0['sectors'] if s['type'] == TT['INTERIOR'] and s['id'] not in owned])
        return [ctx.ice0.buffer(1000.0).difference(woods.buffer(50.0)).union(ctx.ice0),
                self.cons_geom(ctx, self.SETTLEMENT + ('VallaNieve01.V3D',), 2200.0)]

    def tex_core_geom(self, ctx):                                     # the ice and the farmyard: the banks (with
        from shapely.ops import unary_union                           # the sunk firs' shadows) and the fields are
        return unary_union([ctx.ice0, self.cons_geom(ctx, self.SETTLEMENT, 900.0)])    # repainted

    def finish_texture(self, ctx, img):
        """As Recipe.finish_texture, with the firs' shadows painted across the frozen streams lifted from the
        template's painting first (those firs are sunk)."""
        orig = composite(self.template)
        ice = raster(ctx.ice0.buffer(800.0), 1024)
        _COMP[self.template] = deshadow(deshadow(orig, ice), ice, win=81)      # strokes, then the wide masses
        try:
            return Recipe.finish_texture(self, ctx, img)
        finally:
            _COMP[self.template] = orig

    def ridge_lines(self):
        return [(chaikin(line, rounds=3), hw, hh) for line, hw, hh in self.RIDGES]

    def design(self, ctx):
        rng = np.random.default_rng(self.seed)
        X, Z = GX, GZ
        hs = ndimage.gaussian_filter(ctx.h0, 5)
        h = 380.0 + 0.3 * (hs - 380.0)
        h += 140.0 * (fbm(X, Z, rng, 11000.0, 3) - 0.5) + 45.0 * (fbm(X, Z, rng, 2600.0, 2) - 0.5)
        ctx.ridge = np.zeros((N, N))
        for line, hw, hh in self.ridge_lines():
            d, _ = polyline_dist(X, Z, line)
            r = 1 - smoothstep(0.0, hw, d + 600.0 * (fbm(X, Z, rng, 5000.0, 2) - 0.5))
            h += hh * r ** 1.6 * (0.75 + 0.5 * fbm(X, Z, rng, 6000.0, 2))
            ctx.ridge = np.maximum(ctx.ridge, r)
        # the borrowed lake: Minsk's basin and shore, levelled so that its shore meets the tundra here
        L = self.lake()
        src = ndimage.map_coordinates(L['h'], [(GZ - L['dz']) / CELL, (GX - L['dx']) / CELL], order=1, mode='nearest')
        inside = grid_mask(L['poly'])
        dist = ndimage.distance_transform_edt(~inside) * CELL
        ring = (dist > 1500.0) & (dist < 3500.0)
        self.lake_dy = float(np.median(h[ring]) - np.median(src[ring]))
        w = 1 - smoothstep(2500.0, 6000.0, dist)
        ctx.lake_dist = dist
        return h * (1 - w) + (src + self.lake_dy) * w

    def regions(self, ctx):
        return [(self.lake()['poly'], dict(type=TT['TERRENO_HELADO'], a=1))]

    def conditions(self, ctx):
        return self.zone_conditions(ctx, self.SETTLEMENT, 'AreaAldea', 2600.0)

    def tracks(self):
        rng = np.random.default_rng(self.seed + 3)
        return [chaikin([(25800, 62500), (28000, 58500), (29600, 55000)], rng, 300.0),          # to the lake shore
                chaikin([(22500, 61500), (24000, 52000), (27000, 42500), (31000, 33500), (34500, 28500)], rng, 500.0),
                chaikin([self.att, (55000, 16500), (46000, 20000), (39500, 23000)], rng, 600.0)]

    def stunted(self, tv, trunk, canopies):
        return max(node_extent(tv, o)[0] for o in (canopies or [trunk])) <= self.STUNTED

    def tree_prob(self, ctx, name):
        rng = np.random.default_rng(self.seed + 11)
        from shapely.geometry import LineString
        X, Z = GX, GZ
        dice = ndimage.distance_transform_edt(~ctx.ice_mask) * CELL
        p = (0.12 + 1.2 * np.exp(-((dice - 3800.0) / 2000.0) ** 2) + 0.8 * np.exp(-((ctx.lake_dist - 4200.0) / 1800.0) ** 2)
             + 0.6 * np.clip(ctx.ridge * (1 - ctx.ridge) * 4.0, 0, 1) + 0.5 * smoothstep(0.62, 0.75, fbm(X, Z, rng, 5000.0, 3)))
        ok = (slope_deg(ctx.h) < 25) & (band(X, Z, 2500, 4500) > 0.5) & ~grid_mask(ctx.keep_polys, 800.0)
        ok &= ctx.lake_dist > 700.0
        for cx, cz in (self.att, self.dfn):
            ok &= np.hypot(X - cx, Z - cz) > 9500
        for line in self.tracks():
            ok &= ~grid_mask(LineString(line), 600.0)
        return p * ok

    def relocate(self, ctx, name, tv):
        """Only the stunted trees and shrubs stay, sparsely spread; the tall firs inside the map (kept core
        included: the tundra has none) and about half of those of the outside scenery are sunk."""
        T = lvl_v3d.trees(tv)
        small, sink = [], []
        for t, c in T:
            x, y, z = lvl_v3d.translation(tv, t['m2'])
            if self.stunted(tv, t, c):
                small.append((t, c))
            elif (0 <= x <= SIZE and 0 <= z <= SIZE) or ctx.rng.random() < 0.45:
                sink.append((t, c))
        pts = scatter(self.tree_prob(ctx, name), len(small), ctx.rng, min_dist=1400.0)
        for (trunk, canopies), (x, z) in zip(small, pts):
            x0, y0, z0 = lvl_v3d.translation(tv, trunk['m2'])
            y = ctx.H(x, z) - 15.0
            lvl_v3d.move_tree(tv, trunk, canopies, x - x0, y - y0, z - z0)
            ctx.trees_xyz.append((x, y, z))
        for trunk, canopies in sink + small[len(pts):]:
            lvl_v3d.move_tree(tv, trunk, canopies, 0.0, -20000.0, 0.0)
        allp = np.array([lvl_v3d.translation(tv, t['m2']) for t, c in T])
        lvl_v3d.set_global_bbox(tv, [float(allp[:, 0].min() - 800), float(allp[:, 1].min() - 50), float(allp[:, 2].min() - 800)],
                                [float(allp[:, 0].max() + 800), float(allp[:, 1].max() + 2500), float(allp[:, 2].max() + 800)])
        print('  %s: %d stunted placed, %d sunk, %d kept outside' % (name, len(pts), len(sink) + len(small) - len(pts),
                                                                    len(T) - len(small) - len(sink)))

    def build(self):
        import copy
        ctx = super().build()
        L = self.lake()                                               # the ice of the lake, at the end of the list
        o = copy.deepcopy(L['inst'])
        o['matrix'] = list(o['matrix'])
        o['matrix'][12] += L['dx']
        o['matrix'][13] += self.lake_dy
        o['matrix'][14] += L['dz']
        add_object(ctx.m.get(lvl.OBJECTLIST), lvl.TO_HIELO, self.LAKE_SRC[1], o)
        ins = grid_mask(L['poly'].buffer(-1500.0))
        ring = (ctx.lake_dist > 1200.0) & (ctx.lake_dist < 3000.0)
        print('  lake: ice at %.0f cm (dy %.0f), basin %.0f..%.0f, shore median %.0f' % (
            o['matrix'][13], self.lake_dy, ctx.h[ins].min(), ctx.h[ins].max(), np.median(ctx.h[ring])))
        return ctx

    def write(self):
        mm = super().write()
        ship_borrowed(os.path.join(BM, self.folder, 'Models'), self.LAKE_SRC[0], self.LAKE_SRC[1], self.LAKE_SRC[1])
        return mm

    def sounds(self, ctx):
        return [['S_VIENTO', 25, 24000.0, 1200.0, 40000.0, 30000.0], ['S_VIENTO', 25, 22000.0, 1100.0, 20000.0, 50000.0],
                ['S_VIENTO', 25, 20000.0, 1100.0, 60000.0, 55000.0]]

    WILD = [(50000.0, 24000.0), (56000.0, 30000.0), (9000.0, 28000.0), (24000.0, 40000.0), (60000.0, 62000.0),
            (19000.0, 14000.0)]

    def place_location(self, ctx, l):
        if l['type'] == 1:                                             # wildlife: out on the tundra
            k = getattr(self, '_wk', 0)
            l['pos'][0], l['pos'][2] = self.WILD[k % len(self.WILD)]
            self._wk = k + 1

    def texture(self, ctx):
        rng = np.random.default_rng(self.seed + 2)
        shape = (TEX, TEX)
        c39, c21, c14 = composite('39'), composite('21'), composite('14')
        snow = lambda r, g, b: r > 175 and b > 180 and abs(r - b) < 30                        # noqa: E731
        s1 = synth(shape, c39, pick_boxes(c39, snow, k=8), rng, flat=26.0)
        s2 = synth(shape, c21, pick_boxes(c21, snow, k=8), rng, flat=26.0)
        rows, cols = np.mgrid[0:TEX:4, 0:TEX:4].astype(np.float32)
        Xw, Zw = cols / TEX * SIZE, SIZE - rows / TEX * SIZE
        noise = up(fbm(Xw, Zw, rng, 7000.0, 4))
        fine = up(fbm(Xw, Zw, rng, 1300.0, 3))
        hf = up(fbm(Xw[::2, ::2], Zw[::2, ::2], rng, 350.0, 3), TEX)
        w2 = np.clip((noise - 0.42) * 2.2 + (fine - 0.5) * 0.7, 0, 1)
        img = s1 * (1 - w2[..., None]) + s2 * w2[..., None]
        del s1, s2
        # tundra showing through thin, wind-blown snow: the Bohemia map's grey-brown ground, on the ridge crests
        # and other high spots (scoured) and in loose patches; hollows keep the deep snow
        ground = lambda r, g, b: 90 < r < 175 and r >= b - 4 and abs(r - g) < 22 and r - b < 45   # noqa: E731
        gr = synth(shape, c14, pick_boxes(c14, ground, k=6, win=256), rng, flat=26.0, patch=256, step=192)
        hz = up(ctx.h[::-1], TEX)
        hrel = hz - up(ndimage.gaussian_filter(ctx.h, 8)[::-1], TEX)
        ridge = up(ctx.ridge[::-1].astype(np.float32))
        w_g = np.clip((up(fbm(Xw, Zw, rng, 4500.0, 3)) - 0.6) * 2.2 + hrel / 260.0 + 0.55 * smoothstep(0.55, 0.9, ridge)
                      + (hf - 0.5) * 0.6 + (fine - 0.5) * 0.3, 0, 0.75)
        img = img * (1 - w_g[..., None]) + gr * w_g[..., None]
        del gr
        # wind streaks in the snow (sastrugi), faint
        streak = up(fbm(Xw * 0.25, Zw, rng, 2400.0, 3))
        img *= (1 - 0.05 * smoothstep(0.55, 0.75, streak))[..., None]
        # the borrowed lake: Minsk's own painting of its basin and shore, moved with it
        L = self.lake()
        import shapely.affinity as aff
        c17 = deshadow(composite(self.LAKE_SRC[0]),                    # (without Minsk's fir shadows)
                       raster(aff.translate(L['poly'], -L['dx'], -L['dz']).buffer(3000.0), 1024)).astype(np.float32)
        dc, dr = int(round(L['dx'] / SIZE * TEX)), int(round(-L['dz'] / SIZE * TEX))
        lk = raster(L['poly'], 1024)
        dl = up((ndimage.distance_transform_edt(~lk) * (SIZE / 1024)).astype(np.float32))
        w_l = 1 - smoothstep(500.0, 1700.0, dl + 300.0 * (hf - 0.5))
        rr, cc = np.nonzero(w_l > 0)
        r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
        src = c17[r0 - dr:r1 - dr, c0 - dc:c1 - dc]
        wl = w_l[r0:r1, c0:c1, None]
        img[r0:r1, c0:c1] = img[r0:r1, c0:c1] * (1 - wl) + src * wl
        del c17
        img = self.paint_tracks(img, self.tracks(), (156, 152, 146), noise, hf, alpha=0.35, rut=0.16)
        img *= self.baked_light(ctx, 0.8)[..., None]
        img *= (0.96 + 0.06 * noise)[..., None]
        return self.finish_texture(ctx, img)


RECIPES = {'desert': Desert, 'india': India, 'steppe': Steppe, 'eastasia': EastAsia, 'japan': Japan,
           'savanna': Savanna, 'taiga': Taiga, 'jungle': Jungle, 'tundra': Tundra}


def make(name):
    r = RECIPES[name]()
    print('[%s] template %s -> %s' % (name, r.template, r.folder))
    ctx = r.build()
    sm = ctx.m.get(lvl.SECTORMAP)
    import collections
    inv = {v: k for k, v in TT.items()}
    print('  sectors', len(sm['sectors']), dict(collections.Counter(inv.get(s['type'], hex(s['type'])) for s in sm['sectors'])),
          'links', len(sm['links']), 'graph', len(ctx.m.get(lvl.GRAFOIA)['nodes']))
    ctx.tex = r.texture(ctx)
    mm = r.write()
    r.previews(mm)
    p = os.path.join(BM, r.folder, r.lvl_name)
    raw = open(p, 'rb').read()
    assert lvl.Lvl(raw).pack() == raw
    return r


if __name__ == '__main__':
    for nm in (sys.argv[1:] or list(RECIPES)):
        make(nm)

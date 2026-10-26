"""Common label grid for the border extension: reproduces world_provinces.main() up to the final labels.

Saves build/extend/grid.npz with: land, ex (existing mesh index, -1 none), ex_names, final (new province index,
-1 none), lon, lat, adm (admin-1 index), ctry (country index), xs, zs, and the proposal ids in order.
"""
import os, sys, json, math
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, TOOLS)
import world_provinces as WP, gen_world as GW
ROOT = WP.ROOT
OUT = os.path.join(ROOT, 'build', 'extend')


def existing_labels(nx, nz):
    """world_provinces.existing_labels, but the new sea zones (S + capital, added to the mod model after the
    world provinces were built) are skipped too: they overlap islands and must not count as existing land."""
    import struct
    from PIL import Image, ImageDraw
    from igmod import V3D
    d = open(os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'Gestion', 'Mapa', 'MapaGestionVolumenes.V3D'), 'rb').read()
    v = V3D(d)
    names = []
    img = Image.new('I', (nx, nz), -1); dr = ImageDraw.Draw(img)
    for st, en, name in v.blocks:
        if name[:1] in 'WS' and name[1:2].isupper():
            continue
        k = len(names)
        b = d[st:en]; f = V3D.mesh_fields(b)
        tx, _, tz = struct.unpack_from('<3f', b, f['body'] + 64 + 48)
        pts = [struct.unpack_from('<3f', b, f['vdata'] + 28 * i) for i in range(f['nv'])]
        pts = [((x + tx - WP.X0) / WP.STEP, (WP.Z1 - (z + tz)) / WP.STEP) for x, _, z in pts]
        idx = struct.unpack_from('<%dH' % f['ni'], b, f['ih'] + 16)
        for t in range(0, len(idx), 3):
            dr.polygon([pts[i] for i in idx[t:t + 3]], fill=k, outline=k)
        names.append(name)
    return np.asarray(img, np.int32), names


def compute():
    P = WP.proposal()
    land, gx, gy, lon, lat, xs, zs = WP.land_grid()
    nz, nx = land.shape
    ex, ex_names = existing_labels(nx, nz)
    old = (gx < WP.OLD_G[0]) & (gy < WP.OLD_G[1])
    free = land & (ex < 0) & ~old
    fy, fx = np.nonzero(free)
    seeds = []
    for p in P:
        if p['id'] in WP.SEED_FIX:
            p['lon'], p['lat'] = WP.SEED_FIX[p['id']]
        d = (lon[fy, fx] - p['lon']) ** 2 * math.cos(math.radians(p['lat'])) ** 2 + (lat[fy, fx] - p['lat']) ** 2
        k = int(np.argmin(d))
        seeds.append((fy[k], fx[k], math.sqrt(d[k])))
    lab, ncomp = ndimage.label(ndimage.binary_erosion(land, iterations=1))
    if ncomp:
        _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
        comp = np.where(land, lab[iy, ix], 0)
    else:
        comp = np.zeros_like(land, int)
    ctry_r = np.load(os.path.join(ROOT, 'build', 'countries_lonlat.npy'))
    ci = np.clip(((lon - GW.LON0) / GW.RES).astype(int), 0, ctry_r.shape[1] - 1)
    cj = np.clip(((GW.LAT1 - lat) / GW.RES).astype(int), 0, ctry_r.shape[0] - 1)
    ctry = ctry_r[cj, ci].astype(int)
    if (ctry[land] < 0).any():
        m = ctry < 0
        _, (iy, ix) = ndimage.distance_transform_edt(m, return_indices=True)
        ctry = np.where(m, ctry[iy, ix], ctry)
    sy = np.array([s[0] for s in seeds]); sx = np.array([s[1] for s in seeds])
    s_comp = comp[sy, sx]; s_ctry = ctry[sy, sx]
    own = np.empty(len(fx), int)
    keys = comp[fy, fx] * 1000 + ctry[fy, fx]
    for key in np.unique(keys):
        c, k = divmod(int(key), 1000)
        idx = np.nonzero(keys == key)[0]
        for cand in (np.nonzero((s_comp == c) & (s_ctry == k))[0], np.nonzero(s_comp == c)[0],
                     np.nonzero(s_ctry == k)[0], np.arange(len(seeds))):
            if len(cand):
                break
        tree = cKDTree(np.stack([sx[cand], sy[cand]], 1))
        _, j = tree.query(np.stack([fx[idx], fy[idx]], 1))
        own[idx] = cand[j]
    adm_r = np.load(os.path.join(ROOT, 'build', 'admin1_lonlat.npy'))
    adm = adm_r[cj, ci].astype(int)
    cell_adm = adm[fy, fx]
    seed_unit = adm[sy, sx]
    for u in np.unique(cell_adm):
        if u < 0:
            continue
        idx = np.nonzero(cell_adm == u)[0]
        inside = np.nonzero(seed_unit == u)[0]
        if len(inside) == 1:
            own[idx] = inside[0]
        elif len(inside) > 1:
            tree = cKDTree(np.stack([sx[inside], sy[inside]], 1))
            _, j = tree.query(np.stack([fx[idx], fy[idx]], 1))
            own[idx] = inside[j]
        else:
            votes = np.bincount(own[idx])
            own[idx] = int(np.argmax(votes))
    units = json.load(open(os.path.join(ROOT, 'build', 'admin1_units.json'), encoding='utf8'))
    code_ix = {u['code']: i for i, u in enumerate(units)}
    pid_ix = {p['id']: k for k, p in enumerate(P)}
    for code, prov in WP.ADMIN_OVERRIDE.items():
        own[cell_adm == code_ix[code]] = pid_ix[prov]
    label = -np.ones((nz, nx), np.int32)
    label[fy, fx] = own
    final = -np.ones_like(label)
    for k, (yy, xx, dist) in enumerate(seeds):
        m = label == k
        lab, n = ndimage.label(m)
        if not n or lab[yy, xx] == 0:
            continue
        final[lab == lab[yy, xx]] = k
    orphan = (label >= 0) & (final < 0)
    for _ in range(40):
        if not orphan.any():
            break
        grown = ndimage.grey_dilation(np.where(final >= 0, final + 1, 0), size=3) - 1
        take = orphan & (grown >= 0)
        final[take] = grown[take]
        orphan = (label >= 0) & (final < 0)
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, 'grid.npz'), land=land, ex=ex, final=final, lon=lon, lat=lat, adm=adm,
                        ctry=ctry, xs=xs, zs=zs, old=old, seeds=np.array([(s[0], s[1]) for s in seeds]),
                        seed_err=np.array([s[2] for s in seeds]))
    json.dump(dict(ex_names=ex_names, P=P), open(os.path.join(OUT, 'grid_meta.json'), 'w', encoding='utf8'))
    return land, ex, ex_names, final, lon, lat, adm, ctry, xs, zs, old, seeds, P


def load():
    g = np.load(os.path.join(OUT, 'grid.npz'))
    meta = json.load(open(os.path.join(OUT, 'grid_meta.json'), encoding='utf8'))
    return g, meta


if __name__ == '__main__':
    compute()
    print('ok')

"""Build and cache the sea/land/existing grid used for sea-zone generation."""
import os, sys, json
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import world_provinces as WP, meshgen as MG
ROOT = WP.ROOT
OUT = os.path.join(ROOT, 'build', 'sea')
os.makedirs(OUT, exist_ok=True)
land, gx, gy, lon, lat, xs, zs = WP.land_grid()
nz, nx = land.shape
_orig = os.path.join(ROOT, 'mod', 'Game', 'GameModes', 'Gestion', 'Mapa', 'MapaGestionVolumenes.V3D')
if not os.path.exists(_orig):
    import builtins
    _open = builtins.open
    def _o(f, *a, **k):
        if f == _orig:
            f = os.path.join(ROOT, 'data', 'Game', 'GameModes', 'Gestion', 'Mapa', 'MapaGestionVolumenes.V3D')
        return _open(f, *a, **k)
    builtins.open = _o
ex, names = WP.existing_labels(nx, nz)
np.savez_compressed(os.path.join(OUT, 'grid.npz'), land=land, ex=ex, lon=lon, lat=lat, xs=xs, zs=zs)
json.dump(names, open(os.path.join(OUT, 'ex_names.json'), 'w'))
old = (gx < WP.OLD_G[0]) & (gy < WP.OLD_G[1])
img = np.zeros((nz, nx, 3), np.uint8)
img[:] = (90, 120, 150)            # free sea
img[land] = (200, 190, 160)
img[ex >= 0] = (120, 120, 120)
img[(ex >= 0) & ~land] = (60, 60, 130)
img[old & (ex < 0) & ~land] = (150, 60, 60)   # painted old art, free, sea by geography
img[old & (ex < 0) & land] = (150, 120, 60)
Image.fromarray(img).save(os.path.join(OUT, 'grid_check.png'))
print(land.shape, 'names', len(names), names[:5])

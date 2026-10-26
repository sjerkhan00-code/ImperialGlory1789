"""Checks for build/sea/sea_zones.json: route, coast coverage, overlaps, polygon validity."""
import os, sys, json, collections
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import meshgen as MG, world_provinces as WP
ROOT = WP.ROOT; OUT = os.path.join(ROOT, 'build', 'sea')
Z = json.load(open(os.path.join(OUT, 'sea_zones.json')))
provs = json.load(open(os.path.join(ROOT, 'build', 'world_provinces.json'), encoding='utf8'))
# 1. polygons
for k, v in Z.items():
    assert MG.is_simple(v['poly']), k
    assert len(v['poly']) <= 300, (k, len(v['poly']))
    assert abs(MG.area(v['poly'])) > 0
print('polygons ok; vertices min/max/mean', min(len(v['poly']) for v in Z.values()), max(len(v['poly']) for v in Z.values()), round(sum(len(v['poly']) for v in Z.values()) / len(Z)))
# 2. symmetric adjacency
for k, v in Z.items():
    for n in v['neighbours_sea']:
        if n in Z:
            assert k in Z[n]['neighbours_sea'], (k, n)
print('adjacency symmetric')
# 3. overlap test by rasterizing at 20 units
S = 20.0
nx = int((WP.X1 - WP.X0) / S); nz = int((WP.Z1 - WP.Z0) / S)
cnt = np.zeros((nz, nx), np.int16)
for k, v in Z.items():
    im = Image.new('1', (nx, nz), 0)
    ImageDraw.Draw(im).polygon([((x - WP.X0) / S, (WP.Z1 - z) / S) for x, z in v['poly']], fill=1)
    cnt += np.asarray(im, np.int16)
print('overlapping pixels (20u):', int((cnt > 1).sum()), 'of', int((cnt > 0).sum()))
# overlap with land provinces
g = np.load(os.path.join(OUT, 'grid.npz')); land = g['land']
zl = np.load(os.path.join(OUT, 'zone_labels.npy'))
print('zone cells on land (grid):', int(((zl >= 0) & land).sum()), '(corridor + filled islets)')
# 4. route check
start = ['CostaMarroqui', 'OceanoAtlantico']
adj = collections.defaultdict(set)
for k, v in Z.items():
    for n in v['neighbours_sea']:
        adj[k].add(n); adj[n].add(k)
seen = set(start); q = list(start)
while q:
    a = q.pop()
    for b in adj[a]:
        if b not in seen:
            seen.add(b); q.append(b)
targets = ['canary', 'senegambia', 'guinea', 'goodhope', 'mozambique', 'zanzibar', 'aden', 'redsea', 'gulf', 'malabar', 'bengal', 'malacca', 'scs_n', 'ecs', 'japan_sea', 'okhotsk', 'kamchatka', 'bering', 'philippine', 'newguinea', 'tasman', 'nsw', 'nz_e', 'nz_w']
print('reachable from the old Atlantic:', {t: (t in seen) for t in targets})
print('unreachable zones:', sorted(set(Z) - seen))
# shortest route Cape -> India
def path(a, b):
    prev = {a: None}; q = collections.deque([a])
    while q:
        u = q.popleft()
        if u == b: break
        for w in sorted(adj[u]):
            if w not in prev:
                prev[w] = u; q.append(w)
    out = []; u = b
    while u is not None:
        out.append(u); u = prev[u]
    return out[::-1]
print('route Morocco -> Bombay:', ' > '.join(path('CostaMarroqui', 'malabar')))
print('route Morocco -> Canton:', ' > '.join(path('CostaMarroqui', 'scs_n')))
print('route Morocco -> Botany Bay:', ' > '.join(path('CostaMarroqui', 'nsw')))
# 5. coastal coverage: new provinces with sea-adjacent cells must touch a zone
free = ~land
plab, pkeys = __import__('sea_zones').province_labels(*land.shape[::-1], provs)
from scipy import ndimage
touched = {p for v in Z.values() for p in v['coastal_land']}
coastal = set()
ring = ndimage.binary_dilation(free, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
for i, key in enumerate(pkeys):
    m = plab == i
    if (m & ring).sum() >= 3:
        coastal.add(key)
print('coastal new provinces:', len(coastal), 'without a sea zone:', sorted(coastal - touched))
print('zones with no coastal land (open ocean):', sorted(k for k, v in Z.items() if not v['coastal_land']))
print('zones touching original provinces:', {k: v['coastal_land'] for k, v in Z.items() if any(p not in provs for p in v['coastal_land'])})
print('zones next to original sea zones:', {k: [n for n in v['neighbours_sea'] if n not in Z] for k, v in Z.items() if any(n not in Z for n in v['neighbours_sea'])})
print('enclosed islands:', {k: v['enclosed_land'] for k, v in Z.items() if v.get('enclosed_land')})
areas = sorted((v['area_units2'], k) for k, v in Z.items())
print('smallest zones', areas[:5]); print('largest zones', areas[-5:])

import os, sys, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import meshgen as MG, render_map as RM
from igmod import Mng
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
mng = Mng(open(os.path.join(ROOT, 'data/Game/GameModes/DefModeloGestion.mng'), 'rb').read())
recs = Mng.parse_provinces(mng.section(4))
byidx = {r['idx']: r for r in recs}
outl = RM.province_outlines(os.path.join(ROOT, 'data/Game/GameModes/Gestion/Mapa/MapaGestionVolumenes.V3D'))
print('COLS', MG.COLS, 'ROWS', MG.ROWS, 'TILE', MG.TILE_W, MG.TILE_H)
print('mesh names sample', list(outl)[:10], len(outl))
print('rec sample', {k: v for k, v in recs[0].items()})
def bbox(name):
    pts = [p for e in outl[name] for p in e]
    xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
    return (min(xs), max(xs), min(zs), max(zs))
seas = [r for r in recs if r['sea']]
print('n provinces', len(recs), 'n sea', len(seas))
for r in seas:
    nm = r['volumes'] or r['name']
    key = next((k for k in outl if k == r['name'] or k == r['volumes'] or k == r['model']), None)
    bb = bbox(key) if key else None
    print(r['idx'], repr(r['name']), repr(r['ltext']), r['volumes'], r['model'], bb and [round(v) for v in bb], 'nb', [byidx[n]['name'] for n in r['nb'] if n in byidx])

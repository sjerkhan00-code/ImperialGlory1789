"""Draw Chechenya's border (new north line + rim shading) into the old tiles -> build/oldarea/tiles."""
import os, json, numpy as np
from PIL import Image
from shapely.geometry import Polygon
import common as C, geo, ink

polys = {int(k): [tuple(p) for p in v] for k, v in json.load(open(os.path.join(C.OUT, 'provinces.json'))).items()}
ch = polys[11]
# the new north line = vertices after the coast end (15266,5149) back to the west end
i = next(k for k, p in enumerate(ch) if abs(p[0] - 15266.2) < 1 and abs(p[1] - 5149.0) < 1)
north = ch[i:] + ch[:1]
cv = ink.Canvas(deframed=True)
cv.draw_ink([north])
cv.draw_rim(ch, [north])                                   # Chechenya's side
kursk = geo.original_polys()['Kursk'].difference(Polygon(ch))
kursk = max(kursk.geoms, key=lambda g: g.area) if kursk.geom_type == 'MultiPolygon' else kursk
cv.draw_rim(list(kursk.exterior.coords), [north])          # Kursk's side of the new line
print(cv.save(os.path.join(C.OUT, 'tiles')))
# before / after crop
x0, y0 = C.w2p(14300, 5500); x1, y1 = C.w2p(16000, 4400)
b = Image.fromarray(C.comp(True)[int(y0):int(y1), int(x0):int(x1)])
a = Image.fromarray(np.clip(cv.img[int(y0):int(y1), int(x0):int(x1)], 0, 255).astype(np.uint8))
W = Image.new('RGB', (a.width * 2 + 12, a.height), (255, 255, 255)); W.paste(b, (0, 0)); W.paste(a, (a.width + 12, 0))
W.save(os.path.join(C.OUT, 'chechenya_before_after.png')); print(W.size)

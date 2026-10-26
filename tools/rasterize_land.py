"""Rasterise world-atlas land-50m (Natural Earth, public domain) into build/land_lonlat.png.
Raster: lon -40..190 (east of 180 continues past the date line), lat 82..-56, 0.04 degrees per pixel."""
import json, os
from PIL import Image, ImageDraw
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LON0, LAT1, RES = -40.0, 82.0, 0.04


def main():
    d = json.load(open(os.path.join(ROOT, 'build', 'land-50m.json')))
    sx, sy = d['transform']['scale']; tx, ty = d['transform']['translate']
    arcs = []
    for a in d['arcs']:
        x = y = 0; pts = []
        for dx, dy in a:
            x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    def ring(idx):
        out = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out
    W = int(230 / RES); H = int(138 / RES)
    im = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(im)
    for g in d['objects']['land']['geometries']:
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        for poly in polys:
            for k, r in enumerate(poly):
                pts = ring(r)
                lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
                if min(lats) < -60:
                    continue                                   # Antarctica
                wrap = max(lons) > 100 and min(lons) < -100    # crosses the date line (Chukotka, Fiji ...)
                px = [(((lon + 360 if wrap and lon < -100 else lon) - LON0) / RES, (LAT1 - lat) / RES) for lon, lat in pts]
                dr.polygon(px, fill=255 if k == 0 else 0)
    im.save(os.path.join(ROOT, 'build', 'land_lonlat.png'))
    im.resize((W // 8, H // 8)).save(os.path.join(ROOT, 'build', 'land_lonlat_small.png'))
    print('raster', W, H)


if __name__ == '__main__':
    main()


def countries():
    """build/countries_lonlat.npy: int16 country index per pixel (same raster as land_lonlat.png), -1 = sea."""
    import numpy as np
    d = json.load(open(os.path.join(ROOT, 'build', 'countries-50m.json')))
    sx, sy = d['transform']['scale']; tx, ty = d['transform']['translate']
    arcs = []
    for a in d['arcs']:
        x = y = 0; pts = []
        for dx, dy in a:
            x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    def ring(idx):
        out = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out
    W = int(230 / RES); H = int(138 / RES)
    im = Image.new('I', (W, H), -1); dr = ImageDraw.Draw(im)
    names = []
    for k, g in enumerate(d['objects']['countries']['geometries']):
        names.append(g.get('properties', {}).get('name', str(k)))
        if g['type'] not in ('Polygon', 'MultiPolygon'):
            continue
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        for poly in polys:
            for r_i, r in enumerate(poly):
                pts = ring(r)
                lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
                if min(lats) < -60:
                    continue
                wrap = max(lons) > 100 and min(lons) < -100
                px = [(((lon + 360 if wrap and lon < -100 else lon) - LON0) / RES, (LAT1 - lat) / RES) for lon, lat in pts]
                dr.polygon(px, fill=k if r_i == 0 else -1)
    arr = np.asarray(im, dtype=np.int32).astype(np.int16)
    np.save(os.path.join(ROOT, 'build', 'countries_lonlat.npy'), arr)
    json.dump(names, open(os.path.join(ROOT, 'build', 'countries_names.json'), 'w'))
    print('countries', len(names))


def admin1():
    """build/admin1_lonlat.npy: int32 index of the Natural Earth admin-1 unit per pixel (-1 = none),
    build/admin1_units.json: [{name, admin (country), adm1_code}] in index order."""
    import numpy as np
    d = json.load(open(os.path.join(ROOT, 'build', 'ne_admin1.geojson'), encoding='utf8'))
    W = int(230 / RES); H = int(138 / RES)
    im = Image.new('I', (W, H), -1); dr = ImageDraw.Draw(im)
    units = []
    for k, f in enumerate(d['features']):
        pr = f['properties']
        units.append(dict(name=pr.get('name') or pr.get('name_en') or '', admin=pr.get('admin', ''),
                          code=pr.get('adm1_code', ''), iso=pr.get('iso_a2', '')))
        g = f['geometry']
        if not g:
            continue
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        for poly in polys:
            for r_i, ring in enumerate(poly):
                lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
                if max(lats) < -56 or min(lats) > 82:
                    continue
                if max(lons) < -25:
                    continue                                   # the Americas
                wrap = max(lons) > 100 and min(lons) < -100
                px = [(((lon + 360 if wrap and lon < 0 else lon) - LON0) / RES, (LAT1 - lat) / RES) for lon, lat in ring]
                if max(p[0] for p in px) < 0 or min(p[0] for p in px) > W:
                    continue
                dr.polygon(px, fill=k if r_i == 0 else -1)
    np.save(os.path.join(ROOT, 'build', 'admin1_lonlat.npy'), np.asarray(im, dtype=np.int32))
    json.dump(units, open(os.path.join(ROOT, 'build', 'admin1_units.json'), 'w'))
    print('admin-1 units', len(units))

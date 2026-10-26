"""Previews for islands.py: province outlines (red), existing extension pieces (green) and the island pieces it
adds (magenta fill) on the map art.  python preview.py [added.json] -> build/preview/islands_*_{before,after}.png"""
import os, sys, json
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import islands as I

CROPS = {'seasia': (26000, 39000, -6200, 1500), 'japan': (33000, 38500, 600, 5600), 'overview': (-1000, 48000, -13500, 13443)}


def main():
    fn = sys.argv[1] if len(sys.argv) > 1 else os.path.join(I.OUT, 'added.json')
    added = json.load(open(fn, encoding='utf8'))
    W = json.load(open(os.path.join(I.BUILD, 'world_provinces.json'), encoding='utf8'))
    # 'before' outlines: the provinces before trimming (optional 2nd argument: a backup of world_provinces.json)
    W0 = json.load(open(sys.argv[2], encoding='utf8')) if len(sys.argv) > 2 else W
    E = I.remove_added(json.load(open(os.path.join(I.BUILD, 'extend', 'extensions.json'), encoding='utf8')))
    img = Image.open(os.path.join(I.OUT, 'art_half.png')).convert('RGB')
    out = os.path.join(I.BUILD, 'preview')
    os.makedirs(out, exist_ok=True)
    for name, (x0, x1, z0, z1) in CROPS.items():
        a, b = I.w2px(x0, z1); c, d = I.w2px(x1, z0)
        a, b = max(0, int(a)), max(0, int(b)); c, d = min(img.width, int(c)), min(img.height, int(d))
        sc = 1.0 if name != 'overview' else 0.35
        for tag in ('before', 'after'):
            im = img.crop((a, b, c, d))
            im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
            dr = ImageDraw.Draw(im, 'RGBA')
            P = lambda q: ((I.w2px(*q)[0] - a) * sc, (I.w2px(*q)[1] - b) * sc)
            if tag == 'after':
                for k, v in added.items():
                    for pl in v:
                        dr.polygon([P(q) for q in pl], fill=(255, 0, 255, 110), outline=(255, 0, 255, 255))
            for k, v in E.items():
                for pl in v:
                    dr.line([P(q) for q in pl] + [P(pl[0])], fill=(0, 170, 0, 255), width=1)
            for k, v in (W if tag == 'after' else W0).items():
                pts = [P(q) for q in v['poly']]
                dr.line(pts + pts[:1], fill=(220, 0, 0, 255), width=1)
            im.save(os.path.join(out, 'islands_%s_%s.png' % (name, tag)))
    print('previews in', out)


if __name__ == '__main__':
    main()

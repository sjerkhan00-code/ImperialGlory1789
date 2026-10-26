"""Prototype previews (PNG only, nothing installed): the three showcase units built with the real per-nation
recipes of cultures.py, each next to the original texture and rendered front and 3/4 with the same renderer.

    python tools/art/units/prototypes.py [key ...]      # writes build/units/proto_*.png and preview_*.png
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cultures as C
import retex as R
import uvdump

PROTOS = [('qing_fusilero', 'Qing Green Standard infantry', 'QING', '07Otomano/Infanteria/Fusilero.dds', 'Infanteria/Fusilero'),
          ('ashigaru', 'Japanese ashigaru', 'JAPAN', '23Tunez/Infanteria/Fusilero.dds', 'Infanteria/Fusilero'),
          ('ashanti_warrior', 'Ashanti warrior', 'ASHANTI', '22Marruecos/Infanteria/Miliciano1.dds', 'Infanteria/Miliciano'),
          ('mysore_tiger', 'Mysore tiger sepoy', 'MYSORE', '08Egipto/Infanteria/Fusilero.dds', 'Infanteria/Fusilero')]

if __name__ == '__main__':
    only = sys.argv[1:]
    for key, title, nation, tex, base in PROTOS:
        if only and key not in only:
            continue
        model = C.ARAB_TEX[base]
        src = uvdump.load_tex(os.path.join(C.DATA, 'Models', tex.replace('/', os.sep))).convert('RGB')
        img = C.retex(model, src, C.RECIPES[nation])
        img.save(os.path.join(C.ROOT, 'build', 'units', 'proto_%s.png' % key))
        R.preview(model, src, img, os.path.join(C.ROOT, 'build', 'units', 'preview_%s.png' % key), title=title)
        print('wrote', key)

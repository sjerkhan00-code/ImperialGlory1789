"""Extract the original game paks (standard zip archives) for the build: paks/data.pak -> data/, paks/Data1.pak ->
data1/, paks/Text.pak -> text/. The paks are only read. Copy them from your own Imperial Glory v1.1 game folder into
paks/ first.

    python tools/extract_paks.py
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAKS = [('data.pak', 'data'), ('Data1.pak', 'data1'), ('Text.pak', 'text')]


def main():
    for pak, out in PAKS:
        src = os.path.join(ROOT, 'paks', pak)
        if not os.path.isfile(src):
            sys.exit('extract_paks: %s missing; copy it from your Imperial Glory v1.1 folder into paks/' % src)
        dst = os.path.join(ROOT, out)
        with zipfile.ZipFile(src) as z:
            z.extractall(dst)
            print('  %-10s -> %-6s %d entries' % (pak, out + '/', len(z.infolist())))


if __name__ == '__main__':
    main()

"""Nexus release package of the PUBLIC build: build/public/release/ImperialGlory1789/.

    python tools/make_release.py [--zip] [--bundle-dgvoodoo] [--stock-copy PATH]

Run it after `python tools/make_map.py --public --allow-stale-art` (+ `validate_build.py --public`).

What it does
- Runs nations.patch_exe (public variant, IG_PUBLIC=1) on the original exe into a scratch file, i.e. the SAME put()
  calls as the build, and records every byte range those calls wrote: offset, the accepted original bytes, the new
  bytes, and the patch numbers (taken from the '# NN)' comment above each put call in nations.py). The result must be
  byte-identical to build/public/ImperialGlory_ModNations.exe, otherwise the public build is stale and the tool stops.
- Writes patches.json next to install.ps1 (the offline installer reads it, manifest.json and the payload folder).
- Writes manifest.json + payload/ (loose files 0001.dat ...: no archive inside the Nexus zip), from which the installer builds Data2.pak (see 'Data2.pak WITHOUT original game
  files' below). The package itself contains no Data2.pak.
- Self-test: applies patches.json exactly like install.ps1 does to BOTH known ImperialGlory.exe variants (in memory) and
  checks that each result equals the public exe.

The two known ImperialGlory.exe v1.1 variants (5,337,088 bytes each; identical except the fullscreen table)
- stock Steam:   MD5 d2c8a4580bbcfb34a37dae3214b198ea (the MD5 the Nexus mod 'All 24 Nations' requires)
- our original:  MD5 e8db9ab5441318ecc6b158f4f8fc780c (re_tools/target/ImperialGlory.exe = the user's Steam install),
  which carries an earlier hex edit of the fullscreen mode table at VA 0x8c878c (patch 31's range).
  Evidence (2026-10-22): writing STOCK_TABLE (640x480, 800x600, 1024x768, 1152x864, 1280x1024, 1600x1200; the stock list
  from the Steam forum, engine_guide.md 2.9) over our table gives exactly MD5 d2c8a458..., the full Steam MD5 read from
  the All 24 Nations patcher.ps1. So the stock exe is reconstructed byte for byte, and the table range accepts both
  contents. Patch 31 overwrites all 48 table bytes, so both inputs give the same output.
- That table range also carries 'replace_any': it is pure data and fully overwritten, so the installer accepts ANY
  prior table there (e.g. a widescreen hex edit) and then relies on the MD5 of the patched result: equal to the public
  exe = verified; different = an unknown exe, the user is warned and must confirm. Every other range must match.
- 'patches' of a range = the nearest '# NN)' comment above its put() calls (informational; 41-43 and 44-46 group under
  43 / 46 because their hooks are placed after the last comment).

Data2.pak WITHOUT original game files (2026-10-22; the package must not contain files of the original game)
- The package has no Data2.pak. install.ps1 builds it on the player's PC from the player's own data.pak / Data1.pak /
  Text.pak plus manifest.json and payload/ (written here). Every entry of build/public/Data2.pak is one of
    dir    a directory entry;
    copy   byte-identical to an original pak entry: the manifest names the pak + entry, size, MD5 (459 entries, 120 MB);
    delta  an IGD1 delta (tools/igdelta.py) against an original entry (same path, same file name, or for non-image
           files the original with most shared 16-byte blocks), used only when the delta is < DELTA_MAX of the file;
    new    the mod's own file, shipped in payload/.
- Source choice for 'copy' / same-path bases: Data1.pak before data.pak (the game's lookup order), unshadowed first.
- The manifest also carries every zip header field of the reference pak (DOS time, external attributes; the constant
  version / flag / method fields are asserted), so the installer writes the same entry names, order and headers.
  .NET Framework's DeflateStream (CompressionLevel.Optimal) = zlib level 6 = Python zipfile's default (verified
  2026-10-22 on 8 entries up to 9.7 MB): the built pak is then byte-identical to build/public/Data2.pak (pak MD5
  check); on a machine where it is not, every entry is still verified by MD5 after a read-back.
- Self-test: simulate_install() builds the pak like install.ps1 from paks/ (the master copies of the originals) and
  must reproduce build/public/Data2.pak byte for byte; game_reader_check() then reads it the way the exe's pak reader
  does (central directory name+extra lengths, local header sizes, method 0/8).
- Deltas are cached in build/release_cache/ (keyed by entry name + MD5), so reruns take seconds instead of minutes.
"""
import os, sys, json, hashlib, struct, shutil, re, tempfile, time, zipfile, zlib, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ['IG_PUBLIC'] = '1'                       # before nations.py is imported: the public variant
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import nations as NT                                # noqa: E402
import igdelta                                      # noqa: E402
from igmod import Mng, parse_players                # noqa: E402

RELEASE_VERSION = '1.0.0'
MOD_NAME = 'Imperial Glory 1789'
PUB = os.path.join(ROOT, 'build', 'public')
OUT = os.path.join(PUB, 'release', 'ImperialGlory1789')
PUBLIC_EXE = os.path.join(PUB, 'ImperialGlory_ModNations.exe')
PUBLIC_PAK = os.path.join(PUB, 'Data2.pak')
PUBLIC_MNG = os.path.join(PUB, 'mod', 'Game', 'GameModes', 'DefModeloGestion.mng')
ORIG_CANDIDATES = [os.path.join(ROOT, 're_tools', 'target', 'ImperialGlory.exe'),
                   os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Steam', 'steamapps',
                                'common', 'Imperial Glory', 'ImperialGlory.exe')]   # only read

EXE_SIZE = 5337088
EDITED_MD5 = 'e8db9ab5441318ecc6b158f4f8fc780c'
STOCK_MD5 = 'd2c8a4580bbcfb34a37dae3214b198ea'
TABLE_VA = 0x8c878c
STOCK_TABLE = [(640, 480), (800, 600), (1024, 768), (1152, 864), (1280, 1024), (1600, 1200)]
VARIANTS = [{'md5': STOCK_MD5, 'name': 'ImperialGlory.exe v1.1, stock Steam'},
            {'md5': EDITED_MD5, 'name': 'ImperialGlory.exe v1.1 with an edited fullscreen resolution table'}]
DGVOODOO_ZIP = os.path.join(ROOT, 'third_party', 'dgvoodoo2_87_5', 'dgVoodoo2_87_5.zip')

# Data2.pak rebuilt by the installer (see the docstring)
PAKS_DIR = os.path.join(ROOT, 'paks')               # master copies of the original paks (only read)
SOURCE_PAKS = ['Data1.pak', 'data.pak', 'Text.pak']  # the game's lookup order among the originals (newest first)
MANIFEST = 'manifest.json'
PAYLOAD = 'payload'      # folder of loose files 0001.dat ... (2026-10-23: no zip inside the Nexus zip; Nexus quarantines nested archives)
DELTA_MAX = 0.70                                    # ship a delta only when it is smaller than this share of the file
IMAGE_EXT = ('.dds', '.tga', '.bmp')                # no content search for these (same path / same name only)
CACHE_DIR = os.path.join(ROOT, 'build', 'release_cache', 'igd1_b%d_s%d_m%d' % (igdelta.B, igdelta.STRIDE,
                                                                               igdelta.MIN_COPY))
ZIP_CONST = {'version_made': 20, 'system_made': 0, 'version_needed': 20, 'flags': 0, 'method': 8}


def md5(b):
    return hashlib.md5(b).hexdigest()


def md5_file(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 22), b''):
            h.update(blk)
    return h.hexdigest()


def find_original():
    for p in ORIG_CANDIDATES:
        if os.path.isfile(p):
            d = open(p, 'rb').read()
            if len(d) == EXE_SIZE and md5(d) == EDITED_MD5:
                return p, d
    sys.exit('make_release: no original ImperialGlory.exe with MD5 %s found in %s' % (EDITED_MD5, ORIG_CANDIDATES))


def patch_numbers():
    """Line -> patch number: the last '# NN)' comment at or above each line inside patch_exe."""
    src = open(NT.__file__, encoding='utf-8').read().splitlines()
    first = NT.patch_exe.__code__.co_firstlineno
    marks = [(i, int(m.group(1))) for i, l in enumerate(src, 1) if i >= first
             for m in [re.match(r'\s*#\s*(\d+)\)', l)] if m]
    def at(line):
        n = None
        for i, k in marks:
            if i > line:
                break
            n = k
        return n
    return at


def run_patch_exe(orig_path, mng_path):
    """nations.patch_exe exactly as make_map --public calls it; returns (patched bytes, changes, caller line per put)."""
    mm = Mng(open(mng_path, 'rb').read())
    pid_of = {p['ltext'][len('LTEXT_JUGADOR_'):]: p['idx'] for p in parse_players(mm.section(2))}
    NT.AI_SKIP_IDS[:] = [pid_of[k] for k in NT.AI_SKIP]          # = make_map's exe step
    pe_code, lines = NT.patch_exe.__code__, []

    def prof(frame, event, arg):                       # the line in patch_exe that led to each put() call
        if event == 'call' and frame.f_code.co_name == 'put' \
                and frame.f_code.co_varnames[:3] == ('off', 'new', 'expect'):
            f = frame.f_back
            while f is not None and f.f_code is not pe_code:
                f = f.f_back
            if f is not None:
                lines.append(f.f_lineno)
    tmp = tempfile.NamedTemporaryFile(suffix='.exe', delete=False)
    tmp.close()
    try:
        sys.setprofile(prof)
        try:
            changes = NT.patch_exe(orig_path, tmp.name, mng_path)
        finally:
            sys.setprofile(None)
        out = open(tmp.name, 'rb').read()
    finally:
        os.remove(tmp.name)
    assert len(lines) == len(changes), ('put() calls not matched to changes', len(lines), len(changes))
    return out, changes, lines


def build_ranges(orig, out, changes, lines):
    at = patch_numbers()
    mask = bytearray(len(orig))
    for off, old, new in changes:
        mask[off:off + len(new)] = b'\1' * len(new)
    diff = [i for i in range(len(orig)) if orig[i] != out[i]] if len(orig) == len(out) else None
    assert diff is not None, 'patch_exe changed the file size'
    assert all(mask[i] for i in diff), 'bytes changed outside put()'
    stock = bytearray(orig)
    t = TABLE_VA - NT.EXE_BASE
    stock[t:t + 0x30] = b''.join(struct.pack('<II', w, hh) for w, hh in STOCK_TABLE)
    assert md5(stock) == STOCK_MD5, 'stock exe reconstruction does not give the Steam MD5'
    ranges, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        nums = sorted({at(ln) for (off, old, new), ln in zip(changes, lines)
                       if off < j and off + len(new) > i and at(ln) is not None})
        acc = [orig[i:j].hex()]
        if bytes(stock[i:j]) != orig[i:j]:
            acc.append(bytes(stock[i:j]).hex())
        rg = {'off': i, 'va': '0x%06x' % (i + NT.EXE_BASE), 'len': j - i, 'patches': nums,
              'expect': acc, 'new': out[i:j].hex()}
        if i == t and j - i == 0x30:
            rg['replace_any'] = True        # pure data, fully overwritten: any prior table (e.g. a widescreen edit)
        ranges.append(rg)
        i = j
    multi = [r for r in ranges if len(r['expect']) > 1]
    assert len(multi) == 1 and 31 in multi[0]['patches'], ('only patch 31 may accept two originals', multi)
    assert [r['va'] for r in ranges if r.get('replace_any')] == [multi[0]['va']] == ['0x%06x' % TABLE_VA]
    return ranges, bytes(stock)


def apply_like_installer(exe, spec):
    """The installer's patch step (install.ps1 Invoke-Patch) in Python: returns (bytes or None, failed ranges)."""
    if len(exe) != spec['input']['size']:
        return None, ['size']
    d, bad = bytearray(exe), []
    for r in spec['ranges']:
        cur = bytes(d[r['off']:r['off'] + r['len']]).hex()
        if cur not in r['expect'] and not r.get('replace_any'):
            bad.append(r['va'])
    if bad:
        return None, bad
    for r in spec['ranges']:
        d[r['off']:r['off'] + r['len']] = bytes.fromhex(r['new'])
    return bytes(d), []


# ------------------------------------------------------------------ Data2.pak built from the player's original paks
def deflate6(b):
    """Raw deflate exactly as Python zipfile (level 6) and .NET DeflateStream(Optimal) write it; empty -> 03 00."""
    c = zlib.compressobj(6, zlib.DEFLATED, -15, 8, zlib.Z_DEFAULT_STRATEGY)
    return c.compress(b) + c.flush()


def read_central(path):
    """Raw central directory records of a zip (no ZIP64), in file order."""
    d = open(path, 'rb').read()
    e = d.rfind(b'PK\5\6', max(0, len(d) - 0x10016))
    assert e >= 0, path
    n, cdsize, cdoff = struct.unpack_from('<HII', d, e + 10)
    out, p = [], cdoff
    for _ in range(n):
        f = struct.unpack_from('<IBBHHHHHIIIHHHHHII', d, p)
        assert f[0] == 0x02014b50, (path, p)
        name = d[p + 46:p + 46 + f[11]]
        out.append({'made': f[1], 'system': f[2], 'needed': f[3], 'flags': f[4], 'method': f[5], 'time': f[6],
                    'date': f[7], 'crc': f[8], 'csize': f[9], 'usize': f[10], 'name': name.decode('ascii'),
                    'extra': f[12], 'comment': f[13], 'disk': f[14], 'iattr': f[15], 'eattr': f[16], 'off': f[17]})
        p += 46 + f[11] + f[12] + f[13]
    assert p == cdoff + cdsize
    return out, d


class Originals:
    """Entries of the original paks (master copies in paks/): MD5 of every file, lookups by path / file name / type."""

    def __init__(self, d=PAKS_DIR):
        self.z, self.info, self.files = {}, {}, {}
        self.by_md5 = collections.defaultdict(list)
        self.by_key = collections.defaultdict(list)
        self.by_base = collections.defaultdict(list)
        self.by_ext = collections.defaultdict(list)
        self._lru, self._lru_bytes = collections.OrderedDict(), 0
        self._vote = {}
        for pk in SOURCE_PAKS:
            p = os.path.join(d, pk)
            z = zipfile.ZipFile(p)
            self.z[pk] = z
            for i in z.infolist():
                if i.is_dir() or any(ord(ch) > 127 for ch in i.filename):   # 2 non-ASCII names in data.pak: unused
                    continue
                m = md5(z.read(i))
                ref = (pk, i.filename)
                self.files[ref] = (m, i.file_size)
                self.by_md5[m].append(ref)
                k = i.filename.replace('\\', '/').upper()
                self.by_key[k].append(ref)
                self.by_base[k.rsplit('/', 1)[-1]].append(ref)
                self.by_ext[os.path.splitext(k)[1]].append(ref)
            self.info[pk] = {'size': os.path.getsize(p), 'md5': md5_file(p), 'entries': len(z.infolist())}
        # a pak entry is shadowed when a pak earlier in SOURCE_PAKS has the same name (the game never reads it)
        self.shadowed = {ref for refs in self.by_key.values() for ref in refs
                         if any(SOURCE_PAKS.index(o[0]) < SOURCE_PAKS.index(ref[0]) for o in refs)}

    def rank(self, ref, name):
        return (ref in self.shadowed, SOURCE_PAKS.index(ref[0]), ref[1].upper() != name.upper(), ref[1])

    def read(self, ref):
        b = self._lru.pop(ref, None)
        if b is None:
            b = self.z[ref[0]].read(ref[1])
            self._lru_bytes += len(b)
            while self._lru and self._lru_bytes > (256 << 20):
                self._lru_bytes -= len(self._lru.popitem(last=False)[1])
        self._lru[ref] = b
        return b

    def vote(self, tgt, ext, top=3):
        """Originals of type `ext` sharing the most (file-unique, 16-aligned) 16-byte blocks with tgt."""
        if ext not in self._vote:
            idx, refs = {}, [r for r in self.by_ext[ext] if self.files[r][1] <= (4 << 20)]
            for fid, r in enumerate(refs):
                b = self.read(r)
                for i in range(0, len(b) - 15, 16):
                    v = idx.setdefault(b[i:i + 16], fid)
                    if v != fid:
                        idx[b[i:i + 16]] = -1
            self._vote[ext] = (idx, refs)
        idx, refs = self._vote[ext]
        c, get = collections.Counter(), idx.get
        for j in range(len(tgt) - 15):
            v = get(tgt[j:j + 16])
            if v is not None and v >= 0:
                c[v] += 1
        return [refs[f] for f, k in c.most_common(top)]


def aligned_score(a, b):
    """Share of 64-byte chunks equal at the same offset (from the start or from the end): images keep their layout."""
    n = min(len(a), len(b))
    if n < 64:
        return 0.0
    h = sum(a[i:i + 64] == b[i:i + 64] for i in range(0, n - 63, 64))
    t = sum(a[len(a) - i - 64:len(a) - i] == b[len(b) - i - 64:len(b) - i] for i in range(0, n - 63, 64))
    return max(h, t) / (n // 64)


def find_delta(org, name, tgt):
    """(source ref, delta) of the best base among the candidate originals, or None."""
    key = name.upper()
    ext = os.path.splitext(key)[1]
    limit = int(DELTA_MAX * len(tgt))
    best, seen = None, set()

    def trial(refs):
        nonlocal best
        for r in refs:
            m = org.files[r][0]
            if m in seen:
                continue
            seen.add(m)
            d = igdelta.make(org.read(r), tgt, limit=limit)
            if d is not None and len(d) < DELTA_MAX * len(tgt) and (best is None or len(d) < len(best[1])):
                best = (r, d)
    trial(sorted(org.by_key.get(key, []), key=lambda r: org.rank(r, name)))           # same path
    if best and len(best[1]) < 0.05 * len(tgt):
        return best
    same_name = [r for r in org.by_base.get(key.rsplit('/', 1)[-1], []) if r[1].upper() != key]
    if same_name:                                                                       # same file name elsewhere
        by_score = sorted(same_name, key=lambda r: (-aligned_score(org.read(r), tgt), org.rank(r, name)))[:3]
        by_size = sorted(same_name, key=lambda r: (abs(org.files[r][1] - len(tgt)), org.rank(r, name)))[:1]
        trial(by_score + by_size)
    if best is None and ext.lower() not in IMAGE_EXT and len(tgt) <= (4 << 20):           # most shared content
        trial(org.vote(tgt, ext))
    return best


def build_pak_package(org, out_dir):
    """Classify every entry of build/public/Data2.pak; write manifest.json + payload/ into out_dir."""
    cen, ref_bytes = read_central(PUBLIC_PAK)
    ref_md5 = md5(ref_bytes)
    for c in cen:
        assert (c['made'], c['system'], c['needed'], c['flags'], c['method']) == tuple(ZIP_CONST.values()), c
        assert c['extra'] == c['comment'] == c['disk'] == c['iattr'] == 0, c
    assert [c['off'] for c in cen] == sorted(c['off'] for c in cen), 'central order != data order'
    assert len({c['name'].upper() for c in cen}) == len(cen)
    zr = zipfile.ZipFile(PUBLIC_PAK)
    os.makedirs(CACHE_DIR, exist_ok=True)
    entries, payload, count, size = [], [], collections.Counter(), collections.Counter()
    t0, hits = time.time(), 0
    for c in cen:
        name = c['name']
        e = {'name': name}
        if name.endswith('/'):
            assert c['usize'] == 0
            e.update(kind='dir', time=c['time'] | c['date'] << 16, attr=c['eattr'])
            entries.append(e)
            count['dir'] += 1
            continue
        data = zr.read(name)
        m = md5(data)
        assert len(data) == c['usize'] and zlib.crc32(data) == c['crc']
        common = {'size': len(data), 'md5': m, 'crc': c['crc'], 'time': c['time'] | c['date'] << 16, 'attr': c['eattr']}
        if m in org.by_md5:
            r = min(org.by_md5[m], key=lambda r: org.rank(r, name))
            e.update(kind='copy', pak=r[0], **{'from': r[1]})
        else:
            ck = md5((name.upper() + '|' + m).encode())
            cj = os.path.join(CACHE_DIR, ck + '.json')
            res = None
            if os.path.isfile(cj):
                cv = json.load(open(cj))
                if cv['kind'] == 'new':
                    res = 'new'
                else:
                    r = tuple(cv['from'])
                    d = open(os.path.join(CACHE_DIR, ck + '.igd'), 'rb').read()
                    if r in org.files and org.files[r][0] == cv['from_md5'] and md5(igdelta.apply(org.read(r), d)) == m:
                        res = (r, d)
                hits += res is not None
            if res is None:
                res = find_delta(org, name, data) or 'new'
                if res == 'new':
                    json.dump({'kind': 'new'}, open(cj, 'w'))
                else:
                    open(os.path.join(CACHE_DIR, ck + '.igd'), 'wb').write(res[1])
                    json.dump({'kind': 'delta', 'from': list(res[0]), 'from_md5': org.files[res[0]][0]}, open(cj, 'w'))
            pn = '%s/%04d.dat' % (PAYLOAD, len(payload) + 1)   # short flat names: no long paths when extracted
            if res == 'new':
                e.update(kind='new', payload=pn, psize=len(data), pmd5=m)
                payload.append((pn, data))
            else:
                r, d = res
                assert igdelta.apply(org.read(r), d) == data          # round trip
                e.update(kind='delta', pak=r[0], **{'from': r[1]}, from_size=org.files[r][1],
                         from_md5=org.files[r][0], payload=pn, psize=len(d), pmd5=md5(d))
                payload.append((pn, d))
                size['delta_bytes'] += len(d)
        e.update(common)
        entries.append(e)
        count[e['kind']] += 1
        size[e['kind']] += len(data)
    t1 = time.time()
    pp = os.path.join(out_dir, PAYLOAD)
    if os.path.isdir(pp):                                    # generated output of this tool: rewritten every run
        shutil.rmtree(pp)
    os.makedirs(pp)
    for pn, b in payload:
        open(os.path.join(out_dir, pn), 'wb').write(b)
    used = sorted({e['pak'] for e in entries if 'pak' in e}, key=SOURCE_PAKS.index)
    man = {
        'format': 1,
        'kind': 'ig1789-data2-manifest',
        'mod': MOD_NAME,
        'version': RELEASE_VERSION,
        'generated': time.strftime('%Y-%m-%d %H:%M'),
        'generator': 'tools/make_release.py (from build/public/Data2.pak and the original paks)',
        'pak': {'name': 'Data2.pak', 'size': len(ref_bytes), 'md5': ref_md5, 'entries': len(entries),
                'files': len(entries) - count['dir']},
        'zip': dict(ZIP_CONST),
        'delta_format': 'IGD1 (tools/igdelta.py)',
        'sources': {pk: org.info[pk] for pk in used},
        'requires': {'Data1.pak': 'official v1.1 patch data (without it the game ignores Data2.pak)'},
        'payload': {'dir': PAYLOAD, 'files': len(payload), 'size': sum(len(b) for _, b in payload)},
        'counts': dict(count),
    }
    head = json.dumps(man, indent=1)[:-2]                     # one entry per line: compact and still readable
    body = ',\n'.join('  ' + json.dumps(e, separators=(',', ':')) for e in entries)
    with open(os.path.join(out_dir, MANIFEST), 'w', newline='\n') as f:
        f.write(head + ',\n "entries": [\n' + body + '\n ]\n}\n')
    man = json.load(open(os.path.join(out_dir, MANIFEST)))
    print('  Data2.pak entries: %s; classify %.1f s (%d cached), payload %.1f s'
          % (dict(count), t1 - t0, hits, time.time() - t1))
    print('  bytes: copy %d (from the player\'s paks), delta %d -> %d delta bytes, new %d'
          % (size['copy'], size['delta'], size['delta_bytes'], size['new']))
    return man, ref_bytes


def simulate_install(man, package_dir, paks_dir):
    """install.ps1's Build-Pak in Python (deflate6 = .NET Optimal): the Data2.pak bytes it writes."""
    zs, look = {}, {}
    for pk in man['sources']:
        zs[pk] = zipfile.ZipFile(os.path.join(paks_dir, pk))
        look[pk] = {i.filename.replace('\\', '/').upper(): i.filename for i in zs[pk].infolist()}

    def payload(e):                                      # the installer checks each payload file's size and MD5
        b = open(os.path.join(package_dir, e['payload']), 'rb').read()
        assert len(b) == e['psize'] and md5(b) == e['pmd5'], ('payload file', e['payload'])
        return b
    zc = man['zip']
    out, cd = bytearray(), []
    for e in man['entries']:
        if e['kind'] == 'dir':
            data, crc = b'', 0
        else:
            if e['kind'] in ('copy', 'delta'):
                src = zs[e['pak']].read(look[e['pak']][e['from'].upper()])
            if e['kind'] == 'copy':
                data = src
            elif e['kind'] == 'delta':
                assert md5(src) == e['from_md5'], ('original differs', e['pak'], e['from'])
                data = igdelta.apply(src, payload(e))
            else:
                data = payload(e)
            assert len(data) == e['size'] and md5(data) == e['md5'], ('entry MD5', e['name'])
            crc = e['crc']
        comp = deflate6(data)
        nm = e['name'].encode('ascii')
        t, a = e['time'], e['attr']
        cd.append(struct.pack('<IBBHHHIIIIHHHHHII', 0x02014b50, zc['version_made'], zc['system_made'],
                              zc['version_needed'], zc['flags'], zc['method'], t, crc, len(comp), len(data),
                              len(nm), 0, 0, 0, 0, a, len(out)) + nm)
        out += struct.pack('<IHHHIIIIHH', 0x04034b50, zc['version_needed'], zc['flags'], zc['method'], t, crc,
                           len(comp), len(data), len(nm), 0) + nm + comp
    cdo = len(out)
    for r in cd:
        out += r
    out += struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, len(cd), len(cd), len(out) - cdo, cdo, 0)
    return bytes(out)


def game_reader_check(d):
    """Read a pak the way the exe's reader does (FUN_00448a80 central dir: name+extra lengths; the entry reader at
    0x449xxx: local header sizes and method 0/8); inflate and CRC-check every entry. Returns the entry count."""
    e = d.rfind(b'PK\5\6', max(0, len(d) - 0xffff))
    n, cdsize, cdoff = struct.unpack_from('<HII', d, e + 10)
    p = cdoff
    for _ in range(n):
        f = struct.unpack_from('<IBBHHHHHIIIHHHHHII', d, p)
        assert f[0] == 0x02014b50 and 0 < f[11] < 256
        lh = struct.unpack_from('<IHHHHHIIIHH', d, f[17])
        assert lh[0] == 0x04034b50 and lh[3] in (0, 8) and lh[3] == f[5], 'local header'
        assert (lh[6], lh[7], lh[8]) == (f[8], f[9], f[10]), 'local crc/sizes'
        assert lh[9] + lh[10] == f[11] + f[12] and d[f[17] + 30:f[17] + 30 + lh[9]] == d[p + 46:p + 46 + f[11]]
        s = f[17] + 30 + lh[9] + lh[10]
        raw = d[s:s + f[9]]
        data = raw if lh[3] == 0 else zlib.decompressobj(-15).decompress(raw)
        assert len(data) == f[10] and zlib.crc32(data) == f[8], 'inflate'
        p += 46 + f[11] + f[12] + f[13]
    assert p == cdoff + cdsize
    return n


def pak_step():
    """manifest.json + payload/ (the installer builds Data2.pak from them) and their self-tests."""
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    org = Originals()
    print('  indexed the original paks in %.1f s' % (time.time() - t0))
    man, ref_pak = build_pak_package(org, OUT)
    pak_md5 = man['pak']['md5']
    old_pak = os.path.join(OUT, 'Data2.pak')             # the old package shipped the whole pak: never again
    if os.path.isfile(old_pak):
        if md5_file(old_pak) == pak_md5:                 # a plain copy of build/public/Data2.pak
            os.remove(old_pak)
            print('  removed the old full Data2.pak copy from the package (build/public/Data2.pak stays)')
        else:                                            # an older build's copy: keep it, outside the package
            keep = os.path.join(os.path.dirname(OUT), 'Data2.pak.old_' + time.strftime('%Y%m%d_%H%M%S'))
            os.replace(old_pak, keep)
            print('  moved an older Data2.pak out of the package to', keep)
    old_zip = os.path.join(OUT, 'payload.zip')           # the package before 2026-10-23 had a zip inside the zip
    if os.path.isfile(old_zip):
        keep = os.path.join(os.path.dirname(OUT), 'payload.zip.old_' + time.strftime('%Y%m%d_%H%M%S'))
        os.replace(old_zip, keep)
        print('  moved the old payload.zip out of the package to', keep)
    t1 = time.time()
    sim = simulate_install(man, OUT, PAKS_DIR)
    assert sim == ref_pak, 'simulated install does not reproduce build/public/Data2.pak'
    print('  self-test install simulation from paks/: Data2.pak byte-identical to build/public/Data2.pak '
          '(MD5 %s, %.1f s)' % (md5(sim), time.time() - t1))
    print('  self-test game pak reader: %d entries read back (local headers, sizes, inflate, CRC)'
          % game_reader_check(sim))
    del sim
    for e in man['entries']:                             # no original file is shipped, not even renamed
        if e['kind'] == 'new':
            assert e['md5'] not in org.by_md5, e['name']
    pfiles = sorted(os.listdir(os.path.join(OUT, PAYLOAD)))
    assert len(pfiles) == man['payload']['files'], 'stale files in the payload folder'
    for fn in pfiles:
        assert md5(open(os.path.join(OUT, PAYLOAD, fn), 'rb').read()) not in org.by_md5, ('original file in the payload', fn)
    print('  self-test payload: none of its %d files equals an original game file' % len(pfiles))
    print('Data2.pak (built by the installer) %d bytes, MD5 %s; payload folder %d files %d bytes, manifest.json %d bytes'
          % (man['pak']['size'], man['pak']['md5'], man['payload']['files'], man['payload']['size'],
             os.path.getsize(os.path.join(OUT, MANIFEST))))
    tot = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(OUT) for f in fn)
    print('package folder %s: %d bytes' % (OUT, tot))
    return man


def main():
    args = sys.argv[1:]
    for p in (PUBLIC_EXE, PUBLIC_PAK, PUBLIC_MNG):
        if not os.path.isfile(p):
            sys.exit('make_release: %s missing; run make_map.py --public first' % p)
    if '--pak-only' in args:                           # Data2 part only; patches.json stays as it is
        if not os.path.isfile(os.path.join(OUT, 'patches.json')):
            sys.exit('make_release: --pak-only needs an existing patches.json')
        pak_step()
        return
    orig_path, orig = find_original()
    out, changes, lines = run_patch_exe(orig_path, PUBLIC_MNG)
    pub = open(PUBLIC_EXE, 'rb').read()
    if out != pub:
        sys.exit('make_release: patch_exe output differs from %s: the public build is stale, rebuild it' % PUBLIC_EXE)
    ranges, stock = build_ranges(orig, out, changes, lines)
    man = pak_step()
    spec = {
        'format': 1,
        'mod': MOD_NAME,
        'version': RELEASE_VERSION,
        'generated': time.strftime('%Y-%m-%d %H:%M'),
        'generator': 'tools/make_release.py (from nations.patch_exe, public variant)',
        'input': {'name': 'ImperialGlory.exe', 'size': EXE_SIZE, 'variants': VARIANTS},
        'output': {'name': 'ImperialGlory_ModNations.exe', 'size': len(pub), 'md5': md5(pub)},
        'ranges': ranges,                                # Data2.pak: see manifest.json
    }
    with open(os.path.join(OUT, 'patches.json'), 'w', newline='\n') as f:
        json.dump(spec, f, indent=1)
        f.write('\n')
    # self-test: the installer algorithm on both known originals
    spec2 = json.load(open(os.path.join(OUT, 'patches.json')))
    for name, src in (('edited', orig), ('stock', stock)):
        res, bad = apply_like_installer(src, spec2)
        assert res == pub and not bad, ('self-test failed for the %s exe' % name, bad)
        print('  self-test %-6s exe (MD5 %s) -> output MD5 %s: identical to the public exe' % (name, md5(src), md5(res)))
    odd = bytearray(stock)                             # any other fullscreen table (e.g. a widescreen hex edit)
    t = TABLE_VA - NT.EXE_BASE
    odd[t:t + 0x30] = struct.pack('<12I', 640, 480, 1280, 720, 1366, 768, 1920, 1080, 2560, 1440, 1600, 1200)
    res, bad = apply_like_installer(bytes(odd), spec2)
    assert res == pub and not bad, ('self-test failed for a custom table', bad)
    print('  self-test custom table exe -> identical to the public exe (the installer accepts it by the output MD5)')
    tamp = bytearray(orig)                             # a code byte changed: must be refused
    r0 = [r for r in spec2['ranges'] if not r.get('replace_any')][0]
    tamp[r0['off']] ^= 0xff
    assert apply_like_installer(bytes(tamp), spec2)[1] == [r0['va']]
    print('  self-test tampered exe -> refused at', r0['va'])
    if '--stock-copy' in args:                         # a reconstructed stock exe for installer dry runs (scratch only)
        dst = args[args.index('--stock-copy') + 1]
        assert os.path.abspath(dst) not in [os.path.abspath(p) for p in ORIG_CANDIDATES]
        open(dst, 'wb').write(stock)
        print('  wrote reconstructed stock exe', dst)
    if '--bundle-dgvoodoo' in args:                    # optional: the UNMODIFIED dgVoodoo2 zip (credit: Dege)
        od = os.path.join(OUT, 'optional', 'dgVoodoo2')
        os.makedirs(od, exist_ok=True)
        shutil.copyfile(DGVOODOO_ZIP, os.path.join(od, os.path.basename(DGVOODOO_ZIP)))
        print('  bundled', os.path.basename(DGVOODOO_ZIP), 'unmodified in', od)
    nb = sum(r['len'] for r in ranges)
    print('wrote %s: %d ranges, %d bytes, %d put() calls; output MD5 %s'
          % (os.path.join(OUT, 'patches.json'), len(ranges), nb, len(changes), md5(pub)))
    if '--zip' in args:
        zp = os.path.join(PUB, 'release', 'ImperialGlory1789_v%s.zip' % RELEASE_VERSION)
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            for dp, dns, fns in os.walk(OUT):
                for fn in sorted(fns):
                    full = os.path.join(dp, fn)
                    rel = os.path.relpath(full, os.path.dirname(OUT)).replace('\\', '/')
                    assert not fn.lower().endswith(('.zip', '.pak', '.7z', '.rar')), ('archive inside the release zip', rel)
                    z.write(full, rel, zipfile.ZIP_DEFLATED, compresslevel=9)
        print('wrote', zp, os.path.getsize(zp), 'bytes')


if __name__ == '__main__':
    main()

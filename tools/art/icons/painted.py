"""The game's own painted troop art, recoloured for the new nations (used by make_icons.py).

Instead of rendering the 3D unit models, every troop of a new nation gets the ORIGINAL art of the same troop type
(the 256x256 VentanaInfo portrait painting, the 72x102 pool card and 32x45 mini in their four states, the 57x91
battle button in its two states), taken from the original set whose battle figure the troop actually uses
(source_for):

  * the Arab set - OTOMANO portraits, PlantillaTropasArabes cards/minis, ARABE_* battle buttons, and the Egyptian
    Mameluke (EGIPTO Cab_Elite) for the elite horse - for every troop on the Arab-derived unit files (Arab, Asia,
    India, Africa, Pacific: their battle figures are the Arab bodies GenericoA3/A4/H2/E2/G2/G3/D4);
  * the GENERICO / NEUTRAL set for troops on the European bodies (GenericoA..H; since 2026-10-21 the reskin slots
    have their own files: only the militia body of Japan, Qing, the Eastern and Southern Kingdoms uses it);
  * camel-less unit files (Asia, Africa, Pacific) ride horses in battle, so their 'camel' troops show the Arab
    horse lancer / hussar (or the Mameluke when the nation has no elite horse of its own).

Each image is recoloured cloth-only (recolour): a figure mask (difference to the empty card / medallion / the
recovered portrait backdrop), colour classes in CIELAB (light cloth, warm tan/ochre cloth, dark cloth, the orange
European coat; skin is excluded by hue), roles per source (RULES: coat / skirt / trousers / hat, the turban found
as the top light-cloth blob) and a luminance-preserving transfer to the nation's recipe colours
(tools/art/units/cultures.py RECIPES): the target colour's lightness plus the painting's own light/shade relief,
the target chroma (less in the shadows) plus a little of the original's colour variation.  Skin, metal, horses,
camels, background, frames and alpha are untouched.  The other states (selected / pressed / disabled) reuse the
NORMAL state's roles (shifted to match) and keep their own brightness; the disabled state stays grey.

Painted overrides: build/chatgpt_portraits/<NATION>_<TROOP>.png (files starting with '_' are ignored) replace the
recoloured original of that troop everywhere (portrait, cards, minis, battle buttons): the painting is cropped around
the figure's head and upper body, toned toward the original (saturation, mean luminance of the original's inner
area) and set into the original's own frame, keeping the original's frame, plaque, alpha and state effects.
"""
import os, re
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

STATES = ('NORMAL', 'SELECCIONADO', 'PULSADO', 'DISABLE')

# ------------------------------------------------------------------ CIELAB (D65)
_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_MI = np.linalg.inv(_M)
_WP = np.array([0.95047, 1.0, 1.08883])


def to_lab(rgb):
    c = np.asarray(rgb, np.float64)[..., :3] / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ _M.T / _WP
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def to_rgb(lab):
    lab = np.asarray(lab, np.float64)
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], -1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _WP
    c = np.clip(xyz @ _MI.T, 0, None)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
    return np.clip(c * 255, 0, 255)


# ------------------------------------------------------------------ the original art
_ENTRY = re.compile(r'\.KEY\s+(\S+)\s+\.PARAMS\s*\[\s*\.FILE\s+"([^"]+)"\s+\.SX\s+(\d+)\s+\.SY\s+(\d+)\s+\.U\s+(\d+)\s+\.V\s+(\d+)')
_FONDO = re.compile(r'\.(SOLTADO|PULSADO)\s*\[\s*\.FILE\s+"([^"]+)"\s+\.U\s+(\d+)\s+\.V\s+(\d+)')

# source id -> (VentanaInfo folder, portrait file, pool key prefix, battle button key prefix)
SOURCES = {}
for _t, _f in (('FUSILERO', 'Fusilero'), ('MILICIA', 'Milicia'), ('TIRADOR', 'Tirador'), ('CAB_HUSAR', 'Cab_Husar'),
               ('CAB_LANCERO', 'Cab_Lancero'), ('CAM_LANCERO', 'Cam_Lancero'), ('CAM_TIRADOR', 'Cam_Tirador')):
    SOURCES['ARAB_' + _t] = ('OTOMANO', _f, 'OTOMANO_' + _t, 'ARABE_' + _t)
SOURCES['ARAB_CAB_ELITE'] = ('EGIPTO', 'Cab_Elite', 'EGIPTO_CAB_ELITE', 'ARABE_CAB_ELITE')
for _t, _f in (('FUSILERO', 'Fusilero'), ('MILICIA', 'Milicia'), ('TIRADOR', 'Tirador'), ('CAZADOR', 'Cazador'),
               ('GRANADERO', 'Granadero'), ('ELITE', 'Elite'), ('CAB_HUSAR', 'Cab_Husar'), ('CAB_LANCERO', 'Cab_Lancero'),
               ('CAB_DRAGON', 'Cab_Dragon'), ('CAB_CORACERO', 'Cab_Coracero')):
    SOURCES['GEN_' + _t] = ('GENERICO', _f, 'NEUTRAL_' + _t, 'NEUTRAL_' + _t)
# the Spanish guerrilla (head cloth, shirt, breeches; green hills behind): the art of troops on its body GenericoD3
SOURCES['ESPANYA_ELITE'] = ('ESPANYA', 'Elite', 'ESPANYA_ELITE', 'ESPANYA_ELITE')

# explicit choices that win over the rule in source_for: {(country, troop): source id}
# Japan's horse rides the Mameluke body (GenericoD4, its round hat read as a jingasa): the Mameluke painting fits it
CHOICE = {('JAPAN', 'CAB_HUSAR'): 'ARAB_CAB_ELITE', ('JAPAN', 'MILICIA'): 'GEN_MILICIA_CLOTH',
          ('JAPAN', 'CAB_LANCERO'): 'ARAB_CAB_LANCERO_HOOD',
          ('QING', 'MILICIA'): 'GEN_MILICIA_CLOTH', ('QING', 'CAB_LANCERO'): 'ARAB_CAB_LANCERO_HOOD',
          # the regional peoples' own unit files (cultures.EASTERN, KAZAKH_FILE, SAHEL_FILE, SOUTH_FILE, 2026-10-21): the
          # painting of the body each troop now uses (Mameluke body -> the Mameluke, lancer body -> the hooded lancer,
          # long-robed marksman body -> the Arab marksman, militia body -> the generic militia with its coat)
          ('INDEPENDENT', 'MILICIA'): 'GEN_MILICIA_CLOTH', ('INDEPENDENT', 'CAB_HUSAR'): 'ARAB_CAB_ELITE',
          ('INDEPENDENT', 'CAM_TIRADOR'): 'ARAB_CAB_ELITE', ('INDEPENDENT', 'CAB_LANCERO'): 'ARAB_CAB_LANCERO_HOOD',
          ('INDEPENDENT', 'CAM_LANCERO'): 'ARAB_CAB_LANCERO_HOOD',
          ('HANNOVER', 'GRANADERO'): 'ARAB_TIRADOR', ('HANNOVER', 'CAB_DRAGON'): 'ARAB_CAB_ELITE',
          ('HANNOVER', 'CAB_CORACERO'): 'ARAB_CAB_LANCERO_HOOD',
          ('SAJONIA', 'GRANADERO'): 'ARAB_TIRADOR', ('SAJONIA', 'CAB_DRAGON'): 'ARAB_CAB_ELITE',
          ('SAJONIA', 'CAB_CORACERO'): 'ARAB_CAB_LANCERO_HOOD',
          ('MOLDAVIA', 'MILICIA'): 'GEN_MILICIA_CLOTH', ('MOLDAVIA', 'CAB_DRAGON'): 'ARAB_CAB_ELITE',
          ('MOLDAVIA', 'CAB_LANCERO'): 'ARAB_CAB_LANCERO_HOOD', ('MOLDAVIA', 'CAB_CORACERO'): 'ARAB_CAB_LANCERO_HOOD'}


def source_for(country, troop, model, roster):
    """The original art that fits a troop best, decided by the battle body it uses (see the module docstring)."""
    if (country, troop) in CHOICE:
        return CHOICE[(country, troop)]
    body = os.path.splitext(os.path.basename(model))[0]
    if troop == 'CAB_ELITE':
        return 'ARAB_CAB_ELITE'                      # the Mameluke: the Arab set's elite horse
    if body == 'GenericoD3':
        return 'ESPANYA_ELITE'                       # the guerrilla body (Japan's musket troops): the guerrilla painting
    if re.fullmatch(r'Generico[A-H]', body) and 'GEN_' + troop in SOURCES:
        return 'GEN_' + troop                        # European bodies -> the generic European paintings
    if troop == 'ELITE' and body in ('GenericoA3', 'GenericoA4'):
        # a guard on an Arab infantry body (signature elites, cultures.SIGNATURE: Japan, Persia): that body's painting
        return 'ARAB_FUSILERO' if body == 'GenericoA3' else 'ARAB_TIRADOR'
    if troop == 'CAM_LANCERO' and body != 'GenericoG3':
        return 'ARAB_CAB_LANCERO'                    # camel-less unit file: a horse lancer in battle
    if troop == 'CAM_TIRADOR' and body != 'GenericoA4':
        return 'ARAB_CAB_HUSAR' if 'CAB_ELITE' in roster else 'ARAB_CAB_ELITE'
    return 'ARAB_' + troop


class Originals:
    """Index of the original troop art: portraits, pool cards / minis (by .sb key) and battle buttons."""
    def __init__(self, data, load_tga, icons_rel, battle_rel):
        self.data, self.load = data, load_tga
        self.vi = os.path.join(data, icons_rel, 'VentanaInfo')
        nd = os.path.join(data, icons_rel, 'Neutrales')
        self.pool = {}
        for fn in ('UIDefs_PoolTropasIcons.sb', 'UIDefs_PoolTropasBtnIconsSmall.sb'):
            txt = open(os.path.join(nd, fn), 'rb').read().decode('latin1')
            for k, f, sx, sy, u, v in _ENTRY.findall(txt):
                self.pool[k] = (f, int(sx), int(sy), int(u), int(v))
        self.btn = {}
        for sub in ('Especiales', 'Default'):
            txt = open(os.path.join(data, battle_rel, sub, 'UIDefs_BtnTropas.sb'), 'rb').read().decode('latin1')
            for blk in re.split(r'(?=\.KEY\s)', txt):
                k = re.match(r'\.KEY\s+(\S+)', blk)
                fs = {s: (f, int(u), int(v)) for s, f, u, v in _FONDO.findall(blk)}
                if k and 'SOLTADO' in fs and 'PULSADO' in fs:
                    self.btn[k.group(1)] = (fs['SOLTADO'], fs['PULSADO'])
        self._img = {}

    def image(self, rel):
        if rel not in self._img:
            self._img[rel] = self.load(os.path.join(self.data, rel.replace('/', os.sep)))
        return self._img[rel]

    def portrait_path(self, src):
        d, f = SOURCES[src][:2]
        return os.path.join(self.vi, d, f + '.tga')

    def portrait(self, src):
        return self.load(self.portrait_path(src))

    def card(self, src, state):
        f, sx, sy, u, v = self.pool['%s_IMG_%s' % (SOURCES[src][2], STATES[state])]
        return self.image(f).crop((u, v, u + sx, v + sy))

    def mini(self, src, state):
        f, sx, sy, u, v = self.pool['%s_BTN_%s_SMALL' % (SOURCES[src][2], STATES[state])]
        return self.image(f).crop((u, v, u + sx, v + sy))

    def button(self, src, pressed):
        f, u, v = self.btn[SOURCES[src][3] + '_BTN_INFO_TROPA'][1 if pressed else 0]
        return self.image(f).crop((u, v, u + 57, v + 91))


# ------------------------------------------------------------------ figure masks
def _clean(m, min_px):
    lab, n = ndimage.label(m)
    if n == 0:
        return m
    sz = ndimage.sum(m, lab, range(1, n + 1))
    return np.isin(lab, 1 + np.nonzero(sz >= min_px)[0])


# portrait folders whose backdrop painting is shared with portraits in other folders (the plate is found from those
# too): the lone Spanish guerrilla stands before the hills of the generic infantry portraits
PLATE_DIRS = {'ESPANYA': ('GENERICO', 'PORTUGAL')}


def portrait_plate(vi_dir, fname, load_tga, tol=12, extra=()):
    """(backdrop RGB float 172x157, known bool) of a portrait: the per-pixel mode of the portraits of the same
    folder (and of the `extra` folders) that share its backdrop (most of the inner border agrees), as in
    make_icons.Art.backdrop; where fewer than three agree (or two in a small group) the backdrop is a smooth fill
    from the known pixels around."""
    def ld(d, f):
        return np.asarray(load_tga(os.path.join(d, f)))[:172, :157, :3].astype(np.float32)
    me = ld(vi_dir, fname)
    border = np.zeros((172, 157), bool); border[6:14, 6:151] = border[158:166, 6:151] = True
    border[6:166, 6:14] = border[6:166, 143:151] = True
    group = [me]
    for d in (vi_dir,) + tuple(extra):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith('.tga') and not (d == vi_dir and f == fname):
                o = ld(d, f)
                if (np.abs(o - me).max(-1)[border] <= tol).mean() > 0.5:
                    group.append(o)
    st = np.stack(group)
    agree = np.stack([np.abs(st - st[i]).max(-1) <= tol for i in range(len(st))])    # N x N x H x W
    votes = agree.sum(1)
    best = votes.argmax(0)
    win = np.take_along_axis(agree, best[None, None], 1)[:, 0]
    plate = (st * win[..., None]).sum(0) / np.maximum(win.sum(0)[..., None], 1)
    known = votes.max(0) >= (3 if len(group) >= 3 else 2)      # two figures may agree by chance
    known = ~ndimage.binary_dilation(~known, iterations=4)        # fill only from pixels well inside the known area
    known[:6, :] = known[-6:, :] = known[:, :6] = known[:, -6:] = True       # the frame
    plate[6:166, 6:151] = pull_push(plate[6:166, 6:151], known[6:166, 6:151])  # covered everywhere: smooth fill
    return plate, known


def pull_push(img, known):
    """Smooth hole fill (pyramid pull-push): img H x W x 3 float, known H x W bool -> filled copy."""
    h, w = known.shape
    if known.all():
        return img.copy()
    if h <= 2 or w <= 2 or not known.any():
        out = img.copy(); out[~known] = img[known].mean(0) if known.any() else 0
        return out
    hh, ww = (h + 1) // 2, (w + 1) // 2
    pad = np.zeros((hh * 2, ww * 2, 3), np.float32); pk = np.zeros((hh * 2, ww * 2), np.float32)
    pad[:h, :w] = img * known[..., None]; pk[:h, :w] = known
    s = pad.reshape(hh, 2, ww, 2, 3).sum((1, 3)); n = pk.reshape(hh, 2, ww, 2).sum((1, 3))
    filled = pull_push(s / np.maximum(n, 1)[..., None], n > 0)
    up = np.asarray(Image.fromarray(np.clip(filled, 0, 255).astype(np.uint8)).resize((ww * 2, hh * 2), Image.BILINEAR), np.float32)[:h, :w]
    out = img.copy(); out[~known] = up[~known]
    return out


def _near_bg_dist(a, plate, known, r=10, step=2):
    """Per pixel: the smallest colour distance to a known backdrop pixel within r (step-sampled shifts)."""
    h, w = known.shape
    best = np.full((h, w), 1e9, np.float32)
    P = np.pad(plate, ((r, r), (r, r), (0, 0)), mode='edge'); K = np.pad(known, r)
    for dy in range(-r, r + 1, step):
        for dx in range(-r, r + 1, step):
            ps = P[r + dy:r + dy + h, r + dx:r + dx + w]; ks = K[r + dy:r + dy + h, r + dx:r + dx + w]
            d = np.abs(a - ps).max(-1)
            d[~ks] = 1e9
            np.minimum(best, d, out=best)
    return best


def figure_mask(img, empty, region=None, tol=16, median=3, min_px=12, known=None, close=1, fill_holes=0.0):
    """Pixels of img that are not the empty background (bool).  region: bool mask where figures may be."""
    a = np.asarray(img.convert('RGB') if isinstance(img, Image.Image) else img, np.float32)[..., :3]
    b = np.asarray(empty.convert('RGB') if isinstance(empty, Image.Image) else empty, np.float32)[..., :3]
    df = np.abs(a - b).max(-1)
    if median:
        df = np.asarray(Image.fromarray(np.clip(df, 0, 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(median)), np.float32)
    m = df > tol
    if known is not None:            # where the backdrop is only a fill: background if it matches the known
        near = _near_bg_dist(a, b, known, r=10)  # backdrop close by (sky / hills / sand around the figures)
        m &= known | ((df > tol * 1.3) & (near > tol))
    if close:
        m = ndimage.binary_closing(np.pad(m, close), iterations=close)[close:-close, close:-close]
    if region is not None:
        m &= region
    m = _clean(m, min_px)
    if fill_holes:                   # small enclosed gaps of the figure (folds that matched the backdrop)
        holes, n = ndimage.label(ndimage.binary_fill_holes(m) & ~m)
        if n:
            size = ndimage.sum(np.ones_like(m), holes, np.arange(1, n + 1))
            m |= np.isin(holes, 1 + np.nonzero(size <= fill_holes * m.size)[0])
    return m


# ------------------------------------------------------------------ cloth classification
# roles per source.  classes: W light cloth, G shaded light cloth, T warm tan/ochre cloth, K dark cloth,
# O orange European coat, B brown European cloth.  coat: classes; skirt / trousers: (classes, from, to) as fractions
# of the body height (top..bottom of the figure without thin weapons); hat: the light-cloth blob at the top (turban),
# its height as a share of the body; rider: cloth only above this share (the mount is kept); head: cloth only below
# it (face and shako kept); xw: half width of the cloth window around the head (share of the body height);
# cut: {kind: [(x0, y0, x1, y1)]} boxes never recoloured (a backdrop leak of one painting).
RULES = {
    'ARAB_FUSILERO':  dict(coat='WT', skirt=('WTG', 0.56, 0.80), trousers=('KG', 0.80, 1.0), hat=0.085),
    'ARAB_MILICIA':   dict(coat='WT', trousers=('TKG', 0.62, 1.0), hat=0.075, xw=0.22,
                           cut={'portrait': [(30, 50, 75, 100)]}),
    'ARAB_TIRADOR':   dict(coat='WT', hat=0.085),
    'ARAB_CAB_HUSAR': dict(coat='W', rider=0.62, hat=0.06),
    'ARAB_CAB_LANCERO': dict(coat='W', rider=0.62, hat=0.06),
    'ARAB_CAM_LANCERO': dict(coat='W', rider=0.55, hat=0.05),
    'ARAB_CAM_TIRADOR': dict(coat='W', rider=0.45, hat=0.05),
    'ARAB_CAB_ELITE': dict(coat='WT', rider=0.55, hat=0.06),
}
for _t in ('FUSILERO', 'TIRADOR', 'CAZADOR', 'GRANADERO', 'ELITE'):
    RULES['GEN_' + _t] = dict(coat='O', trousers=('WG', 0.16, 1.0), head=0.16, xw=0.5)
# the guerrilla: light shirt and jacket, red breeches (R), the blue head cloth (U) as the hat; hatcls: the hat's classes
# hatall: every hat-class pixel in the hat box (the flaps of a head cloth), not only the blob at the top
RULES['ESPANYA_ELITE'] = dict(coat='WGT', trousers=('RKB', 0.54, 1.0), hat=0.15, hatcls='UW', hatall=True, xw=0.3,
                              noskin=('trousers',), skinL=55)
# portrait sources whose backdrop is only known around the figure (the plate comes from other paintings, PLATE_DIRS):
# where it is unknown, whatever differs from the fill by more than the value is figure (the guerrilla's shirt is as
# grey as the hills behind it, the lancer's white robe as pale as the sky)
UNKNOWN_IS_FIGURE = {'ESPANYA_ELITE': 12, 'ARAB_CAB_LANCERO_HOOD': 12}
# the generic militia with its brown coat recoloured too (Japan's levy): skin only where it is light (skinL), so the
# brown coat is cloth and the hands stay skin
SOURCES['GEN_MILICIA_CLOTH'] = SOURCES['GEN_MILICIA']
RULES['GEN_MILICIA_CLOTH'] = dict(coat='OB', trousers=('TBK', 0.55, 1.0), head=0.18, skinL=50)
# the Arab horse lancer with the whole head cloth as the hat (Japan: the black helmet and neck guard of its body)
SOURCES['ARAB_CAB_LANCERO_HOOD'] = SOURCES['ARAB_CAB_LANCERO']
RULES['ARAB_CAB_LANCERO_HOOD'] = dict(coat='W', rider=0.62, hat=0.10, hatall=True)
RULES['GEN_MILICIA'] = dict(coat='', trousers=('T', 0.55, 1.0), head=0.18)   # brown coat ~ skin hue: kept
for _t in ('CAB_HUSAR', 'CAB_LANCERO', 'CAB_DRAGON', 'CAB_CORACERO'):
    RULES['GEN_' + _t] = dict(coat='O', rider=0.62, head=0.10)


def _classes(lab, fig):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.hypot(a, b); h = np.degrees(np.arctan2(b, a))
    skin = (h < 68) & (C > 11) & (L > 12) & (a > 3) & (C < 40)
    W = fig & (L > 54) & (C < 25) & ~skin
    T = fig & (h >= 68) & (h <= 108) & (C >= 11) & (L >= 16) & (L <= 84) & ~skin & ~W
    K = fig & (L < 32) & (C < 16)
    O = fig & (h >= 38) & (h <= 80) & ((C >= 30) | ((C >= 17) & (L < 46)))      # orange coat, also in shade
    B = fig & (h >= 50) & (h <= 85) & (C >= 14) & (L < 60) & ~O
    G = fig & (C < 12) & (L > 28) & (L <= 54)                  # shaded light cloth
    sure_skin = fig & (h < 65) & (C > 12) & (L > 15) & (a > 4) & (C < 40) & ~O
    U = fig & (h >= -140) & (h <= -40) & (C >= 10) & (L >= 12)                 # blue cloth
    R = fig & (h >= -20) & (h <= 50) & (C >= 12) & (L >= 8) & (L <= 72)        # red cloth (use below the hands)
    return dict(W=W, T=T, K=K, O=O, B=B, G=G, U=U, R=R, skin=sure_skin)


def _solid(m, fig, skin, r, max_hole):
    """A garment mask without its speckle holes: closed by r, small enclosed holes that are not skin filled."""
    if not m.any():
        return m
    if r:
        m = ndimage.binary_closing(np.pad(m, r), iterations=r)[r:-r, r:-r] & fig
    filled = ndimage.binary_fill_holes(m)
    holes, n = ndimage.label(filled & ~m)
    if n:
        idx = np.arange(1, n + 1)
        size = ndimage.sum(np.ones_like(m), holes, idx)
        sk = ndimage.sum(skin, holes, idx)
        inside = ndimage.sum(fig, holes, idx)
        keep = idx[(size <= max_hole) & (sk <= 0.25 * size) & (inside >= 0.6 * size)]
        m = m | (np.isin(holes, keep) & fig)
    return m & ~skin


def body_box(fig, scale):
    """(top, bottom, left, right, x of the top part) of the figure without its thin parts (lances, muskets)."""
    k = max(1, int(round(2 * scale)))
    core = ndimage.binary_opening(fig, structure=np.ones((2 * k + 1, 2 * k + 1), bool))
    if not core.any():
        core = fig
    ys, xs = np.nonzero(core)
    if len(ys) == 0:
        return 0, fig.shape[0] - 1, 0, fig.shape[1] - 1, fig.shape[1] // 2
    top, bot = ys.min(), ys.max()
    head = ys <= top + 0.12 * (bot - top)
    return top, bot, xs.min(), xs.max(), int(np.median(xs[head]))


def classify(img, fig, rule, scale, kind=None):
    """{role: bool mask} for one image (RGB(A)), its figure mask and a RULES entry.  scale ~ 1 for the 157x172
    portrait painting, smaller for cards / minis / buttons (thin-structure removal and zone sizes follow it)."""
    rgb = np.asarray(img.convert('RGB'), np.float64)
    sigma = 1.0 if scale >= 0.9 else 0.8 if scale >= 0.5 else 0.5
    lab = to_lab(ndimage.gaussian_filter(rgb, (sigma, sigma, 0)))     # classes from the smoothed painting
    cls = _classes(lab, fig)
    if scale >= 0.9:                 # drop thin light / warm structures (blades, shafts, straps)
        for c in ('W', 'T', 'O'):
            core = ndimage.binary_opening(cls[c], structure=np.ones((3, 3), bool))
            cls[c] &= ndimage.binary_dilation(core, iterations=1)
    top, bot, left, right, xtop = body_box(fig, scale)
    H = max(1, bot - top)
    yy = (np.arange(fig.shape[0])[:, None] - top) / H * np.ones((1, fig.shape[1]))
    zone = np.ones(fig.shape, bool)
    if 'rider' in rule:
        zone &= yy <= rule['rider']
    if 'head' in rule:
        zone &= yy >= rule['head']
    roles = {}
    coat = np.zeros(fig.shape, bool)
    for c in rule.get('coat', ''):
        coat |= cls[c]
    coat &= zone
    hat = np.zeros(fig.shape, bool)
    xc = None
    if rule.get('hat'):
        W = np.zeros(fig.shape, bool)
        for c in rule.get('hatcls', 'W'):
            W |= cls[c]
        W &= zone
        rows = np.nonzero(W.sum(1) >= max(1, round(2 * scale)))[0]
        if len(rows):
            t = rows[0]
            hh = max(2, int(round(rule['hat'] * H)))
            xc = int(np.median(np.nonzero(W[t:t + max(2, hh // 2)])[1]))
            hw = max(3, int(round(hh * 1.2)))
            box = np.zeros(fig.shape, bool); box[t:t + hh, max(0, xc - hw):xc + hw + 1] = True
            lab_, n = ndimage.label(W & box)
            if rule.get('hatall'):
                hat = W & box
            elif n:                  # the blob(s) touching the top row of the box
                ids = set(lab_[t][lab_[t] > 0].tolist()) or set(range(1, n + 1))
                hat = np.isin(lab_, list(ids))
    roles['hat'] = hat
    # cloth only near the man: a window around the head (keeps out the mount's head, banners, stray background)
    if xc is None:
        xc = xtop
    xw = rule.get('xw', 0.17 if 'rider' in rule else 0.36)
    near = np.abs(np.arange(fig.shape[1])[None, :] - xc) <= xw * H
    coat &= near
    zone &= near
    coat &= ~hat
    if 'skirt' in rule:
        cs, y0, y1 = rule['skirt']
        m = np.zeros(fig.shape, bool)
        for c in cs:
            m |= cls[c]
        m &= zone & (yy >= y0) & (yy < y1) & ~hat
        roles['skirt'] = m; coat &= ~m
    if 'trousers' in rule:
        cs, y0, y1 = rule['trousers']
        m = np.zeros(fig.shape, bool)
        for c in cs:
            m |= cls[c]
        m &= zone & (yy >= y0) & (yy <= y1 + 0.02) & ~hat
        roles['trousers'] = m; coat &= ~m
    roles['coat'] = coat
    for x0, y0, x1, y1 in rule.get('cut', {}).get(kind, ()):     # known backdrop leaks of one painting
        for m in roles.values():
            m[y0:y1, x0:x1] = False
    # solid garments: speckle holes (folds, highlights the classes missed) closed, skin kept out
    r = 2 if scale >= 0.9 else 1 if scale >= 0.5 else 0
    max_hole = max(4, int(0.015 * fig.size))
    sk0 = cls['skin'] & (lab[..., 0] >= rule['skinL']) if 'skinL' in rule else cls['skin']
    skin = ndimage.binary_dilation(sk0) if scale >= 0.5 else sk0
    done = np.zeros(fig.shape, bool)
    for k in ('hat', 'trousers', 'skirt', 'coat'):
        if k in roles:          # noskin: roles whose cloth may have the hue of skin (red breeches)
            sk = np.zeros_like(skin) if k in rule.get('noskin', ()) else skin
            roles[k] = _solid(roles[k], fig & zone | roles[k], sk, r, max_hole) & ~done
            for x0, y0, x1, y1 in rule.get('cut', {}).get(kind, ()):
                roles[k][y0:y1, x0:x1] = False
            done |= roles[k]
    return roles


def shift_roles(roles, dx, dy):
    """The role masks moved by (dx, dy) pixels."""
    out = {}
    for k, m in roles.items():
        o = np.zeros_like(m)
        h, w = m.shape
        ys0, ys1 = max(0, dy), min(h, h + dy); xs0, xs1 = max(0, dx), min(w, w + dx)
        o[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
        out[k] = o
    return out


def best_shift(ref_fig, fig, r=3):
    """(dx, dy) that lays ref_fig best onto fig (pressed states move the figure)."""
    best, bs = -1, (0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = shift_roles({'m': ref_fig}, dx, dy)['m']
            v = (s & fig).sum() / max(1, (s | fig).sum())
            if v > best:
                best, bs = v, (dx, dy)
    return bs


# ------------------------------------------------------------------ colour transfer
ROLE_KEY = {'coat': 'coat', 'skirt': 'skirt', 'trousers': 'trousers', 'hat': 'hat',     # role -> recipe colour
            'skin': 'skin'}               # skin only for recipes with card_skin (Painter.skin_mask)
CHROMA = 0.9                         # recipe chroma share (the paintings are muted)


def recolour(img, roles, recipe, ref=None, grey=False, feather=0.6):
    """Recolour the role masks of an RGBA image toward the recipe colours.
    ref: {role: L reference of the NORMAL state} so other states keep their own brightness offset.
    grey: the disabled state - only the lightness changes."""
    a = np.asarray(img.convert('RGBA'), np.float64)
    lab = to_lab(a[..., :3])
    out = lab.copy()
    weight = np.zeros(lab.shape[:2])
    refs = {}
    for role, m in roles.items():
        if not m.any():
            continue
        tgt = to_lab(np.array(recipe[ROLE_KEY[role]], np.float64))
        Ls = lab[..., 0][m]
        Lref = float(np.median(Ls)); aref, bref = np.median(lab[..., 1][m]), np.median(lab[..., 2][m])
        refs[role] = Lref
        TL = tgt[0] - max(0.0, tgt[0] - 84) * 0.5                      # headroom for the highlights of white cloth
        TL += (Lref - ref[role]) * 0.8 if ref and role in ref else 0.0
        g = float(np.clip((tgt[0] + 18) / (Lref + 18), 0.45, 1.7)) ** 0.75
        Ln = np.clip(TL + (lab[..., 0] - Lref) * g, 1, 99)
        f = np.clip((Ln + 8) / (tgt[0] + 8), 0.45, 1.15)
        if grey:                     # the disabled state stays (nearly) grey
            an, bn = lab[..., 1] * 0.5, lab[..., 2] * 0.5
        else:                        # target chroma, a little muted like the paintings, plus their own variation
            an = tgt[1] * f * CHROMA + (lab[..., 1] - aref) * 0.3
            bn = tgt[2] * f * CHROMA + (lab[..., 2] - bref) * 0.3
        sel = m
        out[..., 0][sel] = Ln[sel]; out[..., 1][sel] = an[sel]; out[..., 2][sel] = bn[sel]
        weight[sel] = 1.0
    if feather:                      # soft edges inside the masks (outside them out == the original anyway)
        weight = np.maximum(ndimage.gaussian_filter(weight, feather), weight * 0.7)
    rgb = to_rgb(out)
    w = np.clip(weight, 0, 1)[..., None]
    res = a.copy()
    res[..., :3] = a[..., :3] * (1 - w) + rgb * w
    return Image.fromarray(np.clip(np.round(res), 0, 255).astype(np.uint8), 'RGBA'), refs


# ------------------------------------------------------------------ painted overrides (build/chatgpt_portraits)
PORTRAIT_INNER = (6, 6, 151, 166)          # x0, y0, x1, y1 (exclusive) of the painting inside the portrait frame
BTN_DISC = (26.0, 38.5, 20.5)              # centre x, centre y, radius of the battle button's round window
# crop of a half-length painting per kind: (crop height / painting height, head x as a fraction of the crop width,
# margin above the head top as a fraction of the crop height)
CROP = {'portrait': (1.0, 0.5, 0.03), 'card': (0.80, 0.42, 0.05), 'mini': (0.62, 0.42, 0.04), 'button': (0.60, 0.5, 0.07)}


def scan_overrides(folder):
    """{(COUNTRY, TROOP): path} of build/chatgpt_portraits/<COUNTRY>_<TROOP>.png (files starting with '_' skipped)."""
    out = {}
    if folder and os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.startswith('_') or not f.lower().endswith('.png'):
                continue
            m = re.match(r'([A-Z]+)_([A-Z_]+)\.png$', f, re.I)
            if m:
                out[(m.group(1).upper(), m.group(2).upper())] = os.path.join(folder, f)
    return out


def head_focus(img):
    """(head x, head top y) in pixels of a painted figure on a light, smooth parchment ground: the first rows from
    the top with a solid run of figure pixels (colour far from the parchment or textured like fur / hair)."""
    w0, h0 = img.size
    sw = 200; sh = max(1, round(sw * h0 / w0))
    lab = to_lab(np.asarray(img.convert('RGB').resize((sw, sh), Image.LANCZOS), np.float64))
    e = max(2, int(sw * 0.05))
    ground = np.concatenate([lab[:max(2, int(sh * 0.05))].reshape(-1, 3), lab[:sh // 2, :e].reshape(-1, 3),
                             lab[:sh // 2, -e:].reshape(-1, 3)])
    ref = np.median(ground, 0)
    d = np.sqrt(((lab - ref) ** 2).sum(-1))
    L = lab[..., 0]
    std = np.sqrt(np.maximum(ndimage.uniform_filter(L * L, 5) - ndimage.uniform_filter(L, 5) ** 2, 0))
    gstd = np.median(std[:max(2, int(sh * 0.05))])
    fig = (d > 22) | (std > max(6.0, 2.5 * gstd))
    fig = ndimage.median_filter(fig.astype(np.uint8), 5) > 0
    c0, c1 = int(sw * 0.06), int(sw * 0.94)
    rows = np.nonzero(fig[:, c0:c1].sum(1) >= 0.07 * sw)[0]
    top = int(rows[0]) if len(rows) else 0
    ys, xs = np.nonzero(fig[top:top + max(3, int(0.12 * sh)), c0:c1])
    hx = float(np.median(xs)) + c0 if len(xs) else sw / 2
    return hx / sw * w0, top / sh * h0


def crop_painting(img, focus, kind, size):
    """Cut the painting for a window of size (w, h) around the head, per CROP; resized with LANCZOS."""
    W, H = img.size
    fh, fx, fm = CROP[kind]
    tw, th = size
    ch = fh * H; cw = ch * tw / th
    if cw > W:                       # wider than the painting: fit the width instead
        cw = W; ch = cw * th / tw
    hx, top = focus
    x0 = min(max(0.0, hx - fx * cw), W - cw)
    y0 = min(max(0.0, top - fm * ch), max(0.0, H - ch))
    return img.convert('RGB').crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch))).resize(size, Image.LANCZOS)


def tone(rgb, mask, target_L, sat=0.85):
    """Toward the originals: chroma x sat, mean lightness under mask moved to target_L."""
    lab = to_lab(np.asarray(rgb, np.float64)[..., :3])
    mL = float(lab[..., 0][mask].mean()) if mask.any() else float(lab[..., 0].mean())
    lab[..., 0] = np.clip(lab[..., 0] + (target_L - mL), 0, 100)
    lab[..., 1:] *= sat
    return to_rgb(lab)


def _lum(a):
    a = np.asarray(a, np.float64)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


# ------------------------------------------------------------------ the painter used by make_icons
class Painter:
    """Recoloured originals (and painted overrides) for every kind of troop art.
    kinds: 'portrait' (256x256, one state), 'card' (72x102, 4 states), 'mini' (32x45, 4 states),
    'button' (57x91, 2 states: released / pressed)."""
    SCALE = {'portrait': 1.0, 'card': 0.65, 'mini': 0.3, 'button': 0.4}
    NSTATES = {'portrait': 1, 'card': 4, 'mini': 4, 'button': 2}

    def __init__(self, orig, art, override_dir=None):
        self.o, self.art = orig, art
        self.region = {'card': np.asarray(art.card_mask) > 0, 'mini': np.asarray(art.mini_mask) > 0}
        r = np.zeros((91, 57), bool); r[:71] = True; r[56:72, 29:52] = False
        self.region['button'] = r
        r = np.zeros((172, 157), bool); x0, y0, x1, y1 = PORTRAIT_INNER; r[y0:y1, x0:x1] = True
        self.region['portrait'] = r
        yy, xx = np.mgrid[0:91, 0:57]
        cx, cy, rad = BTN_DISC
        self.disc = np.clip(rad + 0.5 - np.hypot(xx - cx, yy - cy), 0, 1)              # soft round window
        self.win = {'card': self._soft(self.region['card']), 'mini': self._soft(self.region['mini']),
                    'button': self.disc}
        self.overrides = scan_overrides(override_dir)
        self._an, self._plates, self._ov = {}, {}, {}

    @staticmethod
    def _soft(m):
        return np.clip(ndimage.gaussian_filter(m.astype(np.float64), 0.6) * 1.15, 0, 1) * m

    # -- originals
    def original(self, kind, src, state=0):
        if kind == 'portrait':
            return self.o.portrait(src).crop((0, 0, 157, 172))
        if kind == 'card':
            return self.o.card(src, state)
        if kind == 'mini':
            return self.o.mini(src, state)
        return self.o.button(src, state == 1)

    def empty(self, kind, src, state=0):
        if kind == 'portrait':
            if src not in self._plates:
                d, f = SOURCES[src][:2]
                self._plates[src] = portrait_plate(os.path.join(self.o.vi, d), f + '.tga', self.o.load,
                                                   extra=[os.path.join(self.o.vi, x) for x in PLATE_DIRS.get(d, ())])
            return self._plates[src]
        return {'card': self.art.card, 'mini': self.art.mini, 'button': self.art.btn}[kind][state]

    def figure(self, kind, src, state):
        img = self.original(kind, src, state)
        if kind == 'portrait':
            plate, known = self.empty(kind, src)
            m = figure_mask(img, plate, self.region[kind], tol=20, median=5, min_px=40, known=known, close=2,
                            fill_holes=0.008)
            if src in UNKNOWN_IS_FIGURE:
                df = np.abs(np.asarray(img.convert('RGB'), np.float32) - plate).max(-1)
                add = ndimage.binary_opening(~known & self.region[kind] & (df > UNKNOWN_IS_FIGURE[src]), iterations=2)
                m = ndimage.binary_opening(m | add)
            return m
        return figure_mask(img, self.empty(kind, src, state), self.region[kind], tol=14, median=0,
                           min_px={'card': 6, 'mini': 3, 'button': 4}[kind])

    def analysis(self, kind, src):
        """([(roles, figure mask, shift)] per state - roles found on the NORMAL state, shifted to each state -,
        the NORMAL state's lightness reference per role)."""
        key = (kind, src)
        if key not in self._an:
            figs = [self.figure(kind, src, k) for k in range(self.NSTATES[kind])]
            img0 = self.original(kind, src, 0)
            roles0 = classify(img0, figs[0], RULES[src], self.SCALE[kind], kind)
            lab0 = to_lab(np.asarray(img0.convert('RGB'), np.float64))
            ref = {r: float(np.median(lab0[..., 0][m])) for r, m in roles0.items() if m.any()}
            per = [(roles0, figs[0], (0, 0))]
            for k in range(1, len(figs)):
                dx, dy = best_shift(figs[0], figs[k])
                rk = shift_roles(roles0, dx, dy)
                grow = ndimage.binary_dilation(figs[k], iterations=1)
                per.append(({r: m & grow for r, m in rk.items()}, figs[k], (dx, dy)))
            self._an[key] = (per, ref)
        return self._an[key]

    def skin_mask(self, kind, src):
        """([skin mask per state], NORMAL-state lightness) of the painted figure: the face and hands (the 'skin' class,
        the rule's skinL, riders above the mount, inside the cloth window, off the garments), shifted per state like
        the roles. Only for recipes with card_skin (cultures._st), so no other troop's art changes."""
        key = ('skin', kind, src)
        if key not in self._an:
            per, ref = self.analysis(kind, src)
            img0 = self.original(kind, src, 0)
            fig, rule, scale = per[0][1], RULES[src], self.SCALE[kind]
            rgb = np.asarray(img0.convert('RGB'), np.float64)
            sigma = 1.0 if scale >= 0.9 else 0.8 if scale >= 0.5 else 0.5
            lab = to_lab(ndimage.gaussian_filter(rgb, (sigma, sigma, 0)))
            sk = _classes(lab, fig)['skin']
            if 'skinL' in rule:
                sk &= lab[..., 0] >= rule['skinL']
            top, bot, left, right, xtop = body_box(fig, scale)
            H = max(1, bot - top)
            yy = (np.arange(fig.shape[0])[:, None] - top) / H * np.ones((1, fig.shape[1]))
            if 'rider' in rule:
                sk &= yy <= rule['rider']
            xw = rule.get('xw', 0.17 if 'rider' in rule else 0.36)
            sk &= np.abs(np.arange(fig.shape[1])[None, :] - xtop) <= xw * H * 1.2
            for m in per[0][0].values():
                sk &= ~m
            sk = _clean(sk, 2 if scale >= 0.5 else 1)
            masks = [sk]
            for k in range(1, len(per)):
                dx, dy = per[k][2]
                masks.append(shift_roles({'s': sk}, dx, dy)['s'] & ndimage.binary_dilation(per[k][1], iterations=1))
            L0 = to_lab(rgb)[..., 0]            # unsmoothed, as recolour measures the NORMAL state
            self._an[key] = (masks, float(np.median(L0[sk])) if sk.any() else 50.0)
        return self._an[key]

    def recoloured(self, kind, src, state, recipe):
        img = self.original(kind, src, state)
        per, ref = self.analysis(kind, src)
        grey = kind in ('card', 'mini') and state == 3
        roles = per[state][0]
        if recipe.get('card_skin') and recipe.get('skin'):
            masks, sref = self.skin_mask(kind, src)
            roles, ref = dict(roles, skin=masks[state]), dict(ref, skin=sref)
        out, _ = recolour(img, roles, recipe, ref=ref if state else None, grey=grey)
        return out

    # -- painted overrides
    def has_override(self, country, troop):
        return (country, troop) in self.overrides

    def _override_img(self, country, troop):
        k = (country, troop)
        if k not in self._ov:
            im = Image.open(self.overrides[k]).convert('RGB')
            self._ov[k] = (im, head_focus(im))
        return self._ov[k]

    def painted(self, kind, src, state, country, troop):
        """The override painting set into the original's frame (frame, plaque, alpha and state effects kept)."""
        im, focus = self._override_img(country, troop)
        # the original's frame: the original state image itself (cards, minis, portraits keep their figure inside the
        # window); for the battle buttons the original figure stands out of the medallion, so the empty medallion
        base = self.empty(kind, src, state) if kind == 'button' else self.original(kind, src, state)
        if kind == 'portrait':
            x0, y0, x1, y1 = PORTRAIT_INNER
            pic = crop_painting(im, focus, kind, (x1 - x0, y1 - y0))
            orig = np.asarray(base.convert('RGB'), np.float64)[y0:y1, x0:x1]
            rgb = tone(np.asarray(pic, np.float64), np.ones(orig.shape[:2], bool),
                       float(to_lab(orig)[..., 0].mean()), 0.85)
            a = np.asarray(base.convert('RGBA')).copy()
            a[y0:y1, x0:x1, :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
            return Image.fromarray(a, 'RGBA')
        win = self.win[kind]
        H, W = win.shape
        ys, xs = np.nonzero(win > 0)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        pic = np.asarray(crop_painting(im, focus, kind, (bx1 - bx0, by1 - by0)), np.float64)
        pic = np.pad(pic, ((by0, H - by1), (bx0, W - bx1), (0, 0)), mode='edge')
        m = win > 0.5
        o0 = np.asarray(self.original(kind, src, 0).convert('RGB'), np.float64)
        e0 = np.asarray(self.empty(kind, src, 0).convert('RGB'), np.float64)
        pic = tone(pic, m, float(to_lab(o0)[..., 0][m].mean()), 0.85)
        # the card's own light: a soft share of the empty card's gradient and rim
        le = _lum(e0)
        v = np.clip(le / max(1.0, float(le[m].mean())), 0.4, 1.6) ** (0.25 if kind != 'button' else 0.15)
        pic = pic * v[..., None]
        # state effects, taken from the empty templates (the frame itself comes from the original state image)
        if kind == 'button' and state == 1:     # pressed: the orange glow along the medallion's rim
            e1 = np.asarray(self.empty(kind, src, 1).convert('RGB'), np.float64)
            yy, xx = np.mgrid[0:H, 0:W]
            rim = np.clip((np.hypot(xx - BTN_DISC[0], yy - BTN_DISC[1]) - (BTN_DISC[2] - 5)) / 3, 0, 1)
            glow = ndimage.gaussian_filter(np.clip(e1 - e0, 0, None), (1, 1, 0)) * 1.6
            pic = pic + glow * rim[..., None]
        elif kind in ('card', 'mini') and state:
            ek = np.asarray(self.empty(kind, src, state).convert('RGB'), np.float64)
            if state == 2:                 # pressed: the originals move the figure like this
                dx, dy = self.analysis(kind, src)[0][2][2]
                pic = ndimage.shift(pic, (dy, dx, 0), order=0, mode='nearest')
            if state == 3:
                tint = ek[m].mean(0) / max(1.0, float(_lum(ek)[m].mean()))
                pic = (_lum(pic) * 0.88)[..., None] * tint[None, None, :]
            else:
                sk = ndimage.gaussian_filter(ek, (1.2, 1.2, 0)); s0 = ndimage.gaussian_filter(e0, (1.2, 1.2, 0))
                pic = pic * np.clip(sk / np.maximum(s0, 1), 0.6, 1.8)
        a = np.asarray(base.convert('RGBA'), np.float64).copy()
        if kind in ('card', 'mini'):     # bits of the original figure outside the window (pressed state): frame art
            ek = np.asarray(self.empty(kind, src, state).convert('RGBA'), np.float64)
            stray = (np.abs(a[..., :3] - ek[..., :3]).max(-1) > 12) & (win < 0.5) & (ek[..., 3] > 0)
            a[..., :3][stray] = ek[..., :3][stray]
        w = win[..., None]
        a[..., :3] = a[..., :3] * (1 - w) + np.clip(pic, 0, 255) * w
        out = Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), 'RGBA')
        if kind == 'mini' and state == 2:
            out.alpha_composite(self.art.tick)
        return out

    # -- the art for one troop
    def make(self, kind, src, state, country, troop, recipe):
        if self.has_override(country, troop):
            img = self.painted(kind, src, state, country, troop)
        else:
            img = self.recoloured(kind, src, state, recipe)
        if kind == 'portrait':       # 256x256: the 157x172 painting at the top-left corner, black elsewhere, opaque
            out = Image.new('RGBA', (256, 256), (0, 0, 0, 255))
            out.paste(img.convert('RGB'), (0, 0))        # (some original portraits carry a stray alpha channel)
            return out
        return img

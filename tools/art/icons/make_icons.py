"""Troop portraits, management icons and battle buttons for the new nations, in Imperial Glory's own style.

For every nation of the 1789 world map (country keys with a recipe in tools/art/units/cultures.py) and every
troop type in its roster (DefModeloGestion.mng section 7 of the last build, plus tools/nations.py EXTRA_TROOPS) that
has its own art (PORTRAIT_FILE), the game's OWN
painted art of the same troop type is taken from the original set whose battle figure the troop uses and
recoloured cloth-only to the nation's recipe colours (tools/art/icons/painted.py: the Arab set - Ottoman
portraits, PlantillaTropasArabes cards, ARABE_* battle buttons, the Egyptian Mameluke for the elite horse - for the
Arab-derived unit files, the GENERICO / NEUTRAL set for troops on the European bodies).  A painting in
build/chatgpt_portraits/<COUNTRY>_<TROOP>.png replaces the recoloured original of that troop everywhere (set into
the original frame).  Written:

  (a) Game/UI/ModeloGestion/Iconos/Tropas/VentanaInfo/<COUNTRY>/<Troop>.tga      256x256 info-window portraits
  (b) Game/UI/ModeloGestion/Iconos/Tropas/Neutrales/PlantillaTropasMod<N>.tga      72x102 cells, 4 states
      Game/UI/ModeloGestion/Iconos/Tropas/Neutrales/PlantillaTropasMod<N>Mini.tga  32x45 cells, 4 states
      + UIDefs_PoolTropasIcons.sb / UIDefs_PoolTropasBtnIcons.sb / UIDefs_PoolTropasBtnIconsSmall.sb
        (the original files with the <COUNTRY>_<TROOP>_IMG_* / _BTN_* / _BTN_*_SMALL entries appended)
  (c) Game/UI/ModeloBatalla/InterfazPaises/Especiales/EspecialesMod<N>.tga         57x91 cells, 2 states
      + UIDefs_BtnTropas.sb (the original file with <COUNTRY>_<TROOP>_BTN_INFO_TROPA entries appended)

Nothing is installed: everything mirrors the game paths under build/icons/out/.  A contact sheet comparing the
originals with the new icons is written to build/icons/sheet.png.

    python tools/art/icons/make_icons.py [COUNTRY ...]           # default: every nation
    python tools/art/icons/make_icons.py --render [COUNTRY ...]  # the previous method: rendered 3D unit models
"""
import math, os, re, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, os.path.join(TOOLS, 'art', 'units')); sys.path.insert(0, TOOLS); sys.path.insert(0, HERE)
import uvdump
import cultures as CU
import nations as NT
from igmod import Mng, split_records
import tga as TGA
import painted as PT

DATA = os.path.join(ROOT, 'data')
MOD = os.path.join(ROOT, 'mod')
UNITS_OUT = os.path.join(ROOT, 'build', 'units', 'out')
OUT = os.path.join(ROOT, 'build', 'icons', 'out')
OVERRIDES = os.path.join(ROOT, 'build', 'chatgpt_portraits')     # painted <COUNTRY>_<TROOP>.png replacing the art
ICONS = 'Game/UI/ModeloGestion/Iconos/Tropas/'
BATTLE = 'Game/UI/ModeloBatalla/InterfazPaises/'

# troops that get their own icon art per nation (officers and guns keep the NEUTRAL / GENERICO art, like the
# game's own Arab nations); the portrait file names are the game's own (VentanaInfo/GENERICO, /EGIPTO)
PORTRAIT_FILE = {'FUSILERO': 'Fusilero', 'MILICIA': 'Milicia', 'TIRADOR': 'Tirador', 'CAZADOR': 'Cazador',
                 'GRANADERO': 'Granadero', 'ELITE': 'Elite', 'CAB_HUSAR': 'Cab_Husar', 'CAB_LANCERO': 'Cab_Lancero',
                 'CAB_DRAGON': 'Cab_Dragon', 'CAB_CORACERO': 'Cab_Coracero', 'CAB_ELITE': 'Cab_Elite',
                 'CAM_LANCERO': 'Cam_Lancero', 'CAM_TIRADOR': 'Cam_Tirador'}
# the Milicia unit has no .TEX in the unit files (the game picks Miliciano1..3 at random)
DEFAULT_TEX = {'MILICIA': 'Infanteria\\Miliciano1.dds'}
# portrait backdrop per nation: the game's desert painting (Arab portraits) or its green hills (European ones)
GREEN = {'MOLDAVIA', 'CHECHNYA', 'QING', 'JAPAN', 'JOSEON', 'BURMA', 'SIAM', 'VIETNAM'}
YAW, PITCH = -0.6, 0.12          # the originals: figure turned to the viewer's left, seen slightly from above
LIGHT = (-0.5, 0.8, -0.45)


# ------------------------------------------------------------------ small image helpers
def load_tga(path):
    w, h, rows = TGA.read_tga(path)
    return Image.frombytes('RGBA', (w, h), b''.join(bytes(r) for r in rows))


def save_tga(path, img):
    """32-bit uncompressed TGA, bottom-up like the game's own files (numpy, fast)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    a = np.asarray(img.convert('RGBA'))
    bgra = a[::-1, :, [2, 1, 0, 3]]
    hdr = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, a.shape[1], a.shape[0], 32, 8)
    footer = b'\0' * 8 + b'TRUEVISION-XFILE.\0'            # TGA 2.0 footer, as on the game's own files
    open(path, 'wb').write(hdr + np.ascontiguousarray(bgra).tobytes() + footer)


def alpha_composite(dst, src, xy, mask=None):
    """Paste src (RGBA) at xy onto dst (RGBA, in place) with src alpha, optionally multiplied by a mask of dst."""
    layer = Image.new('RGBA', dst.size, (0, 0, 0, 0))
    layer.paste(src, xy)
    if mask is not None:
        a = np.asarray(layer.getchannel('A'), dtype=np.float32) * (np.asarray(mask, dtype=np.float32) / 255.0)
        layer.putalpha(Image.fromarray(a.astype(np.uint8)))
    dst.alpha_composite(layer)
    return dst


def adjust(img, gain=1.0, grey=0.0):
    """Brightness gain and optional desaturation of an RGBA layer (alpha untouched)."""
    a = np.asarray(img.convert('RGBA'), dtype=np.float32)
    rgb = a[..., :3]
    if grey:
        lum = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]
        rgb = rgb * (1 - grey) + lum * grey
    a[..., :3] = np.clip(rgb * gain, 0, 255)
    return Image.fromarray(a.astype(np.uint8))


# ------------------------------------------------------------------ renderer (retex.render with an alpha channel)
class Figure:
    """A rendered unit: RGBA image cropped to the figure, plus where the ground line, the body axis and the head
    are, so the compositions can scale by body height (weapons and lances do not count) and centre the body."""
    def __init__(self, img, ppu, ground, axis, head_units, cavalry):
        self.img, self.ppu, self.ground, self.axis, self.head, self.cavalry = img, ppu, ground, axis, head_units, cavalry

    def scaled(self, head_px):
        """(image, ground row, axis column) with the head at head_px above the ground."""
        s = head_px / (self.head * self.ppu)
        w, h = self.img.size
        im = self.img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        return im, self.ground * s, self.axis * s


def render(model, textures, height=440, yaw=YAW, pitch=PITCH, light=LIGHT, ss=3, ambient=0.5, diffuse=0.7):
    """Orthographic Gouraud-lit render of the rest pose with a transparent background -> Figure.
    Lighting and bilinear texturing are those of tools/art/units/retex.py (mount first for cavalry)."""
    ms = [m for m in uvdump.meshes(model) if m['uv'] and m['tris'] and m['pos'] and len(m['pos']) == len(m['uv'])]
    allp = np.array([p for m in ms for p in m['pos']], np.float32)
    lo, hi = allp.min(0), allp.max(0)
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    ext = max(hi[0] - lo[0], hi[2] - lo[2], hi[1] - lo[1]) * 1.15
    H = height * ss; W = int(H * 1.3)
    sc = (H - 8 * ss) / ext
    cy, sy_ = math.cos(yaw), math.sin(yaw); cp, sp = math.cos(pitch), math.sin(pitch)
    img = np.zeros((H, W, 3), np.float32); cov = np.zeros((H, W), np.float32)
    zb = np.full((H, W), -1e9, np.float32)
    L = np.array(light, np.float32); L /= np.linalg.norm(L)
    for mi, m in enumerate(ms):
        tex = np.asarray(textures[min(mi, len(textures) - 1)].convert('RGB'), np.float32); th, tw = tex.shape[:2]
        P = np.array(m['pos'], np.float32) - [cx, 0, cz]
        x = P[:, 0] * cy + P[:, 2] * sy_; z = -P[:, 0] * sy_ + P[:, 2] * cy; y = P[:, 1] - lo[1]
        y2 = y * cp - z * sp; z2 = y * sp + z * cp
        V = np.stack([x, y2, z2], 1)
        T = np.array(m['tris'], np.int64)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        vn = np.zeros_like(V)
        for k in range(3):
            np.add.at(vn, T[:, k], fn)
        vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-6
        shade = ambient + diffuse * np.abs(vn @ L)
        sx = W / 2 + V[:, 0] * sc; sy = H - 4 * ss - V[:, 1] * sc
        UV = np.array(m['uv'], np.float32)
        for a, b, c in T:
            xs = np.array([sx[a], sx[b], sx[c]]); ys = np.array([sy[a], sy[b], sy[c]])
            x0, x1 = max(0, int(xs.min())), min(W - 1, int(xs.max()) + 1)
            y0, y1 = max(0, int(ys.min())), min(H - 1, int(ys.max()) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            det = (xs[1] - xs[0]) * (ys[2] - ys[0]) - (xs[2] - xs[0]) * (ys[1] - ys[0])
            if abs(det) < 1e-6:
                continue
            gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            px, py = gx + 0.5, gy + 0.5
            l1 = ((xs[1] - px) * (ys[2] - py) - (xs[2] - px) * (ys[1] - py)) / det
            l2 = ((xs[2] - px) * (ys[0] - py) - (xs[0] - px) * (ys[2] - py)) / det
            l0 = 1 - l1 - l2
            inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
            if not inside.any():
                continue
            z = l0 * V[a, 2] + l1 * V[b, 2] + l2 * V[c, 2]
            sub = zb[y0:y1 + 1, x0:x1 + 1]
            win = inside & (z > sub)
            if not win.any():
                continue
            u = (l0 * UV[a, 0] + l1 * UV[b, 0] + l2 * UV[c, 0]) * tw - 0.5
            v = (l0 * UV[a, 1] + l1 * UV[b, 1] + l2 * UV[c, 1]) * th - 0.5
            iu = np.floor(u).astype(np.int64); iv = np.floor(v).astype(np.int64)
            fu = (u - iu)[..., None]; fv = (v - iv)[..., None]
            iu0 = iu % tw; iu1 = (iu + 1) % tw; iv0 = iv % th; iv1 = (iv + 1) % th
            col = (tex[iv0, iu0] * (1 - fu) * (1 - fv) + tex[iv0, iu1] * fu * (1 - fv)
                   + tex[iv1, iu0] * (1 - fu) * fv + tex[iv1, iu1] * fu * fv)
            sh = (l0 * shade[a] + l1 * shade[b] + l2 * shade[c])[..., None]
            col = np.clip(col * sh, 0, 255)
            tgt = img[y0:y1 + 1, x0:x1 + 1]
            tgt[win] = col[win]
            sub[win] = z[win]
            cov[y0:y1 + 1, x0:x1 + 1][win] = 1
    # the originals are brighter and warmer than a plain render: lift the midtones a little
    img = 255.0 * (img / 255.0) ** 0.9
    img[..., 0] *= 1.03; img[..., 2] *= 0.97
    pm = (np.clip(img, 0, 255) * cov[..., None]).reshape(H // ss, ss, W // ss, ss, 3).mean((1, 3))
    al = cov.reshape(H // ss, ss, W // ss, ss).mean((1, 3))
    rgb = pm / np.maximum(al[..., None], 1e-3)
    out = np.concatenate([np.clip(rgb, 0, 255), np.clip(al * 255, 0, 255)[..., None]], -1).astype(np.uint8)
    im = Image.fromarray(out, 'RGBA')
    bb = im.getchannel('A').getbbox() or (0, 0, im.width, im.height)
    cavalry = len(ms) > 1
    body = np.array(ms[-1]['pos'], np.float32)[:, 1] - lo[1]      # the rider for cavalry, the soldier otherwise
    head = float(np.percentile(body, 90 if cavalry else 98))        # head top: lances / bayonets are above it
    return Figure(im.crop(bb), sc / ss, (H - 4 * ss) / ss - bb[1], W / 2 / ss - bb[0], head, cavalry)


# ------------------------------------------------------------------ nations, rosters, unit definitions
def db_rosters():
    """{country key: [troop keys]} from the built campaign database."""
    m = Mng(open(os.path.join(MOD, 'Game', 'GameModes', 'DefModeloGestion.mng'), 'rb').read())
    countries = Mng.parse_enum(m.table(1)); troops_en = Mng.parse_enum(m.table(5))
    out = {}
    for r in split_records(m.section(7), 'troop'):
        cid = struct.unpack_from('<I', r, NT._owner_field(r, 23, 13))[0]
        out.setdefault(countries.get(cid), []).append(troops_en[struct.unpack_from('<I', r, 0)[0]])
    # the extra troop types tools/nations.py adds (EXTRA_TROOPS), also before a build has put them in the database
    for key, extra in NT.EXTRA_TROOPS.items():
        roster = out.setdefault(key, [])
        roster += [t for t, _ in extra if t not in roster]
    return out


def nation_info():
    """[(country key, model folder, template models folder, unit file name)]"""
    return [(key, mfolder, tfolder, CU.UNIT_FILE_OF[key]) for key, rkey, mfolder, ffolder, tfolder in CU.nation_list()]


def recipes():
    """{country key: its colour recipe (tools/art/units/cultures.py RECIPES; the reskins use their design key)}"""
    return {key: CU.RECIPES[rkey] for key, rkey, mfolder, ffolder, tfolder in CU.nation_list()}


def recipe_for(rec, key, troop):
    """The colours of one troop's art: the signature elite's own uniform (cultures.SIGNATURE), a troop's own
    (cultures.TROOP_RECIPES), else the nation's."""
    return CU.troop_recipe(key, troop, rec[key])


def unit_text(fname):
    for d in (os.path.join(UNITS_OUT, 'Game', 'GameModes', 'Batalla'), os.path.join(DATA, 'Game', 'GameModes', 'Batalla')):
        p = os.path.join(d, fname)
        if os.path.exists(p):
            return open(p, 'rb').read().decode('latin1').replace('\r', '')
    raise FileNotFoundError(fname)


def unit_def(txt, troop):
    """(model .V3D abs path, [texture rel paths: mount first]) for a troop block of a unit file, or None."""
    m = re.search(r'^\.%s\b.*?\n\]' % troop, txt, re.M | re.S)
    if not m:
        return None
    blk = m.group()
    grx = re.search(r'\.GRX\s+"([^"]+)"', blk)
    if not grx:
        return None
    model = os.path.join(DATA, grx.group(1).replace('\\', os.sep))
    tex = re.search(r'\.TEX\s+"([^"]+)"', blk); tex2 = re.search(r'\.TEX2\s+"([^"]+)"', blk)
    texs = [t.group(1) for t in (tex, tex2) if t]
    if not texs and troop in DEFAULT_TEX:
        texs = [DEFAULT_TEX[troop]]
    return model, texs


def find_tex(rel, mfolder, tfolder):
    rel = rel.replace('\\', os.sep)
    for d in (os.path.join(UNITS_OUT, 'Models', mfolder), os.path.join(DATA, 'Models', mfolder),
              os.path.join(DATA, 'Models', tfolder), os.path.join(DATA, 'Models', '07Otomano'),
              os.path.join(DATA, 'Models', '08Egipto'), os.path.join(DATA, 'Models', '21Moldavia')):
        p = os.path.join(d, rel)
        if os.path.exists(p):
            return p
    return None


def pull_push(img, known):
    """Smooth hole fill (pyramid pull-push): img H x W x 3 float, known H x W bool -> filled copy."""
    h, w = known.shape
    if known.all():
        return img.copy()
    if h <= 2 or w <= 2 or not known.any():
        fill = img[known].mean(0) if known.any() else np.zeros(3)
        out = img.copy(); out[~known] = fill
        return out
    hh, ww = (h + 1) // 2, (w + 1) // 2
    pad = np.zeros((hh * 2, ww * 2, 3), np.float32); pk = np.zeros((hh * 2, ww * 2), np.float32)
    pad[:h, :w] = img * known[..., None]; pk[:h, :w] = known
    s = pad.reshape(hh, 2, ww, 2, 3).sum((1, 3)); n = pk.reshape(hh, 2, ww, 2).sum((1, 3))
    down = s / np.maximum(n, 1)[..., None]
    filled = pull_push(down, n > 0)
    up = np.asarray(Image.fromarray(np.clip(filled, 0, 255).astype(np.uint8)).resize((ww * 2, hh * 2), Image.BILINEAR), np.float32)[:h, :w]
    out = img.copy(); out[~known] = up[~known]
    return out


# ------------------------------------------------------------------ the game's own art, taken from its atlases
class Art:
    def __init__(self):
        n = os.path.join(DATA, ICONS.replace('/', os.sep), 'Neutrales')
        gen = load_tga(os.path.join(n, 'PlantillaTropasGenerico.tga'))
        mini = load_tga(os.path.join(n, 'PlantillaTropasGenericoMini.tga'))
        # the empty card of the Generico atlas (column 3 of the artillery row) in its four states
        self.card = [gen.crop((u, v, u + 72, v + 102)) for u, v in ((220, 207), (731, 207), (220, 516), (731, 516))]
        self.mini = [mini.crop((u, v, u + 32, v + 45)) for u, v in ((100, 93), (331, 93), (100, 231), (331, 231))]
        # the green tick the Mini atlas draws on the pressed state
        a = np.asarray(self.mini[2]).astype(int)
        tick = (a[..., 1] > a[..., 0] + 40) & (a[..., 1] > a[..., 2] + 40)
        tick_mask = Image.fromarray((tick * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
        self.tick = self.mini[2].copy(); self.tick.putalpha(tick_mask)
        # figure clip masks: inside the frame, above the bottom bar, never over the number plaque
        self.card_mask = Image.new('L', (72, 102), 0)
        d = ImageDraw.Draw(self.card_mask); d.rounded_rectangle([5, 6, 66, 84], radius=2, fill=255)
        d.rectangle([42, 0, 71, 23], fill=0)
        self.mini_mask = Image.new('L', (32, 45), 0)
        d = ImageDraw.Draw(self.mini_mask); d.rectangle([2, 3, 29, 37], fill=255); d.rectangle([19, 0, 31, 10], fill=0)
        # the empty medallion of the battle buttons (Especiales atlas, columns 3.. of rows 3/4)
        esp = load_tga(os.path.join(DATA, BATTLE.replace('/', os.sep), 'Especiales', 'Especiales.tga'))
        self.btn = [esp.crop((175, 183, 232, 274)), esp.crop((175, 274, 232, 365))]
        self.bg = {'desert': self.backdrop(['OTOMANO', 'EGIPTO', 'MARRUECOS', 'TUNEZ', 'TRIPOLITANIA']),
                   'green': self.backdrop(['AUSTRIA'], 4, 10, 9)}

    @staticmethod
    def backdrop(dirs, min_votes=12, tol=8, grow=9):
        """The painted 157x172 portrait backdrop (frame included) recovered from the game's own portraits: the
        per-pixel median of all portraits of a set removes the figures where they do not overlap; the always
        covered centre is filled by mirroring the clean strips on either side (it ends up behind the new figure)."""
        ims = []
        for d in dirs:
            p = os.path.join(DATA, ICONS.replace('/', os.sep), 'VentanaInfo', d)
            for f in sorted(os.listdir(p)):
                if f.lower().endswith('.tga'):
                    ims.append(np.asarray(load_tga(os.path.join(p, f)))[:172, :157, :3].astype(np.float32))
        st = np.stack(ims)                                           # N x 172 x 157 x 3
        # background pixels are identical in every portrait of a set, figure pixels differ: per pixel, take the
        # largest cluster of agreeing samples (the mode); pixels with no agreeing samples are covered everywhere
        diff = np.stack([np.abs(st - st[i]).max(-1) <= tol for i in range(len(st))])   # N x N x 172 x 157
        votes = diff.sum(1)                                              # N x 172 x 157
        best = votes.argmax(0)
        agree = np.take_along_axis(diff, best[None, None], 1)[:, 0]      # N x 172 x 157: samples agreeing with the winner
        out = (st * agree[..., None]).sum(0) / np.maximum(agree.sum(0)[..., None], 1)
        bad = votes.max(0) < min_votes
        bad = np.asarray(Image.fromarray((bad * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(grow))) > 0
        bad[:4, :] = bad[-4:, :] = bad[:, :4] = bad[:, -4:] = False     # the frame is always clean
        out[4:168, 4:153] = pull_push(out[4:168, 4:153], ~bad[4:168, 4:153])   # the frame stays out of the fill
        im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGB')
        soft = np.asarray(im.filter(ImageFilter.GaussianBlur(1.4))).astype(np.float32)
        mix = np.asarray(Image.fromarray((bad * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32)[..., None] / 255.0
        return Image.fromarray(np.clip(out * (1 - mix) + soft * mix, 0, 255).astype(np.uint8), 'RGB')


# ------------------------------------------------------------------ compositions
def shadow(size, cx, cy, rx, ry, strength=110):
    sh = Image.new('L', size, 0)
    ImageDraw.Draw(sh).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=strength)
    sh = sh.filter(ImageFilter.GaussianBlur(ry * 0.6))
    layer = Image.new('RGBA', size, (26, 18, 10, 0)); layer.putalpha(sh)
    return layer


def place(fig, head_px, cx, ground_y):
    """(scaled image, paste xy) with the body axis at cx and the ground line at ground_y."""
    im, g, ax = fig.scaled(head_px)
    return im, (round(cx - ax), round(ground_y - g))


def portrait(art, fig, kind):
    """256x256 info-window portrait: the 157x172 painting at the top-left corner, black elsewhere."""
    out = Image.new('RGBA', (256, 256), (0, 0, 0, 255))
    pic = art.bg[kind].convert('RGBA')
    im, xy = place(fig, 128 if fig.cavalry else 140, 80 if fig.cavalry else 78, 158)
    pic.alpha_composite(shadow(pic.size, 80, 156, 52 if fig.cavalry else 22, 7 if fig.cavalry else 5))
    pic.alpha_composite(im, xy)
    out.paste(pic, (0, 0))
    return out


def card_figure(fig):
    """Figure layer of a 72x102 card: infantry head-to-thigh, cavalry rider with the mount's head, like the originals."""
    layer = Image.new('RGBA', (72, 102), (0, 0, 0, 0))
    im, xy = place(fig, 118 if fig.cavalry else 124, 37 if fig.cavalry else 34, 127 if fig.cavalry else 134)
    alpha_composite(layer, im, xy)
    return layer


def card(art, layer, state):
    base = art.card[state].copy()
    gain, grey = ((1.0, 0.0), (1.08, 0.0), (1.04, 0.0), (0.9, 1.0))[state]
    alpha_composite(base, adjust(layer, gain, grey), (0, 0), art.card_mask)
    return base


def mini(art, layer, state):
    base = art.mini[state].copy()
    gain, grey = ((1.0, 0.0), (1.08, 0.0), (1.04, 0.0), (0.9, 1.0))[state]
    small = adjust(layer, gain, grey).resize((32, 45), Image.LANCZOS)
    alpha_composite(base, small, (0, 0), art.mini_mask)
    if state == 2:
        base.alpha_composite(art.tick)
    return base


def button(art, fig, pressed):
    """57x91 battle troop button: the figure stands on the medallion; the pressed state glows orange around it."""
    base = art.btn[1 if pressed else 0].copy()
    im, xy = place(fig, 60 if fig.cavalry else 62, 29, 67)
    if pressed:
        a = Image.new('L', base.size, 0); a.paste(im.getchannel('A'), xy)
        glow = a.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.6))
        g = Image.new('RGBA', base.size, (255, 150, 40, 0)); g.putalpha(glow)
        base.alpha_composite(g)
    alpha_composite(base, im, xy)
    return base


# ------------------------------------------------------------------ .sb text
def pool_entry(key, file_rel, sx, sy, u, v):
    return ('[\r\n .KEY %s\r\n .PARAMS [ .FILE "%s" .SX %d .SY %d .U %d .V %d .ALPHA TRUE ]\r\n]\r\n\r\n'
            % (key, file_rel, sx, sy, u, v))


BTN_TEMPLATE = '''[
 .KEY %s
 .PARAMS
 [
  .COMPORTAMIENTO MANUAL
  .FONDO
  [
    .SX 57 .SY 91 .ALPHA TRUE
    .SOLTADO    [ .FILE "%s" .U %d .V %d ]
    .PULSADO    [ .FILE "%s" .U %d .V %d ]
  ]

  .IDSELECTSOUND "S_UI_BORDENDIRECTA_PULSADO"

  .INDICADORES_ACTIVIDAD [ %%Game/UI/ModeloBatalla/InterfazPaises/UIDefs_IndicadoresActividad.sb ]
  .INFO_PORCENTAJE       [ %%Game/UI/ModeloBatalla/InterfazPaises/UIDefs_BtnTropaInfoPorcentajeParams.sb ]
  .BARRA_FATIGA [ %%Game/UI/ModeloBatalla/InterfazPaises/UIDefs_BarraFatiga.sb  ]
  .BARRA_EXPERIENCIA  "Game/UI/ModeloBatalla/InterfazPaises/UIDefs_BarraExperiencia.sb"
  .BOTON_GRUPO [ %%Game/UI/ModeloBatalla/InterfazPaises/UIDefs_BtnGrupo.sb ]
 ]
]

'''.replace('\n', '\r\n')


def write_text(rel, text):
    p = os.path.join(OUT, rel.replace('/', os.sep)); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(text.encode('latin1'))


# ------------------------------------------------------------------ build
def collect(only=None, rendered=False):
    """[(country, troop, info)] for every troop with its own art.  info: 'model' (battle body), 'src' (the original
    art it gets, painted.source_for), 'fig' (a render of the unit, only with rendered=True; one per model+textures)."""
    rosters = db_rosters()
    items, renders = [], {}
    for key, mfolder, tfolder, ufile in nation_info():
        if only and key not in only:
            continue
        txt = unit_text(ufile)
        roster = rosters.get(key, [])
        for troop in roster:
            if troop not in PORTRAIT_FILE:
                continue
            ud = unit_def(txt, troop)
            if not ud:
                print('  %-11s %-12s no unit block in %s (keeps the NEUTRAL / GENERICO art)' % (key, troop, ufile)); continue
            model, texs = ud
            paths = [find_tex(t, mfolder, tfolder) for t in texs]
            if not texs or None in paths:
                print('  %-11s %-12s texture missing %s (keeps the NEUTRAL / GENERICO art)' % (key, troop, texs)); continue
            info = {'model': model, 'src': PT.source_for(key, troop, model, roster), 'fig': None}
            if rendered:
                sig = (model, tuple(paths))
                if sig not in renders:
                    renders[sig] = render(model, [uvdump.load_tex(p) for p in paths])
                info['fig'] = renders[sig]
            items.append((key, troop, info))
            print('  %-11s %-12s %-14s -> %s' % (key, troop, os.path.basename(model), info['src']))
    print('%d troop icons%s' % (len(items), ', %d distinct renders' % len(renders) if rendered else ''))
    return items


class PaintedArt:
    """The game's own painted troop art recoloured to the nation's colours (or a painted override)."""
    def __init__(self, art):
        orig = PT.Originals(DATA, load_tga, ICONS.replace('/', os.sep), BATTLE.replace('/', os.sep))
        self.p = PT.Painter(orig, art, OVERRIDES)
        self.rec = recipes()
        for (c, t), path in sorted(self.p.overrides.items()):
            print('  painted override %-11s %-12s %s' % (c, t, os.path.relpath(path, ROOT)))

    def portrait(self, key, troop, info):
        return self.p.make('portrait', info['src'], 0, key, troop, recipe_for(self.rec, key, troop))

    def card(self, key, troop, info, state):
        return self.p.make('card', info['src'], state, key, troop, recipe_for(self.rec, key, troop))

    def mini(self, key, troop, info, state):
        return self.p.make('mini', info['src'], state, key, troop, recipe_for(self.rec, key, troop))

    def button(self, key, troop, info, pressed):
        return self.p.make('button', info['src'], 1 if pressed else 0, key, troop, recipe_for(self.rec, key, troop))


class RenderedArt:
    """The previous method (--render): the unit model rendered onto the game's empty card / medallion / backdrop."""
    def __init__(self, art):
        self.art, self._layers = art, {}

    def _layer(self, info):
        k = id(info['fig'])
        if k not in self._layers:
            self._layers[k] = card_figure(info['fig'])
        return self._layers[k]

    def portrait(self, key, troop, info):
        return portrait(self.art, info['fig'], 'green' if key in GREEN else 'desert')

    def card(self, key, troop, info, state):
        return card(self.art, self._layer(info), state)

    def mini(self, key, troop, info, state):
        return mini(self.art, self._layer(info), state)

    def button(self, key, troop, info, pressed):
        return button(self.art, info['fig'], pressed)


def build(maker, items):
    # (a) portraits
    for key, troop, info in items:
        save_tga(os.path.join(OUT, ICONS.replace('/', os.sep), 'VentanaInfo', key, PORTRAIT_FILE[troop] + '.tga'),
                 maker.portrait(key, troop, info))

    # (b) management icon atlases + pool entries: 14 columns x 2 groups of 4 state rows per 1024x1024 atlas
    per_atlas = 28
    sb_icons, sb_btn, sb_small = '', '', ''
    for ai in range(0, len(items), per_atlas):
        n = ai // per_atlas + 1
        big = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0)); small = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        big_rel = ICONS + 'Neutrales/PlantillaTropasMod%d.tga' % n
        small_rel = ICONS + 'Neutrales/PlantillaTropasMod%dMini.tga' % n
        for i, (key, troop, info) in enumerate(items[ai:ai + per_atlas]):
            col, grp = i % 14, i // 14
            for state, name in enumerate(('NORMAL', 'SELECCIONADO', 'PULSADO', 'DISABLE')):
                u, v = 1 + col * 73, 1 + (grp * 4 + state) * 103
                big.paste(maker.card(key, troop, info, state), (u, v))
                mu, mv = 1 + col * 33, 1 + (grp * 4 + state) * 46
                small.paste(maker.mini(key, troop, info, state), (mu, mv))
                k = '%s_%s' % (key, troop)
                sb_icons += pool_entry('%s_IMG_%s' % (k, name), big_rel, 72, 102, u, v)
                sb_btn += pool_entry('%s_BTN_%s' % (k, name), big_rel, 72, 102, u, v)
                sb_small += pool_entry('%s_BTN_%s_SMALL' % (k, name), small_rel, 32, 45, mu, mv)
        save_tga(os.path.join(OUT, big_rel.replace('/', os.sep)), big)
        save_tga(os.path.join(OUT, small_rel.replace('/', os.sep)), small)
    hdr = '\r\n################# Nations of the 1789 world map (generated by tools/art/icons/make_icons.py)\r\n\r\n'
    ndir = os.path.join(DATA, ICONS.replace('/', os.sep), 'Neutrales')
    for fn, add in (('UIDefs_PoolTropasIcons.sb', sb_icons), ('UIDefs_PoolTropasBtnIcons.sb', sb_btn),
                    ('UIDefs_PoolTropasBtnIconsSmall.sb', sb_small)):
        orig = open(os.path.join(ndir, fn), 'rb').read().decode('latin1')
        if not orig.endswith('\n'):
            orig += '\r\n'
        write_text(ICONS + 'Neutrales/' + fn, orig + hdr + add)

    # (c) battle buttons: 17 columns x 5 row pairs per 1024x1024 atlas
    per_btn = 85
    sb_info = ''
    for ai in range(0, len(items), per_btn):
        n = ai // per_btn + 1
        atlas = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
        rel = BATTLE + 'Especiales/EspecialesMod%d.tga' % n
        for i, (key, troop, info) in enumerate(items[ai:ai + per_btn]):
            col, pair = i % 17, i // 17
            u, v0, v1 = 1 + col * 58, 1 + pair * 2 * 92, 1 + (pair * 2 + 1) * 92
            atlas.paste(maker.button(key, troop, info, False), (u, v0))
            atlas.paste(maker.button(key, troop, info, True), (u, v1))
            sb_info += BTN_TEMPLATE % ('%s_%s_BTN_INFO_TROPA' % (key, troop), rel, u, v0, rel, u, v1)
        save_tga(os.path.join(OUT, rel.replace('/', os.sep)), atlas)
    orig = open(os.path.join(DATA, BATTLE.replace('/', os.sep), 'Especiales', 'UIDefs_BtnTropas.sb'), 'rb').read().decode('latin1')
    if not orig.endswith('\n'):
        orig += '\r\n'
    write_text(BATTLE + 'Especiales/UIDefs_BtnTropas.sb', orig + hdr.replace('#################', '#') + sb_info)


def sheet(maker, items, out_png, nations=None):
    """Contact sheet: per troop type, the original art the new nations start from (card, mini, button, portrait)
    beside every nation's version."""
    o = PT.Originals(DATA, load_tga, ICONS.replace('/', os.sep), BATTLE.replace('/', os.sep))
    order = ['FUSILERO', 'MILICIA', 'TIRADOR', 'CAB_HUSAR', 'CAB_LANCERO', 'CAM_LANCERO', 'CAM_TIRADOR', 'CAB_ELITE',
             'CAZADOR', 'GRANADERO', 'ELITE', 'CAB_DRAGON', 'CAB_CORACERO']
    by = {}
    for key, troop, info in items:
        by.setdefault(troop, {})[key] = info
    troops = [t for t in order if t in by]
    nations = nations or sorted({k for k, _, _ in items})
    cw, ch = 72 + 32 + 57 + 157 + 12, 172 + 14
    W = (len(nations) + 1) * cw + 8; H = len(troops) * ch + 20
    sh = Image.new('RGB', (W, H), (28, 28, 30)); dr = ImageDraw.Draw(sh)
    dr.text((8, 4), 'original (Arab / generic set)', fill=(255, 230, 120))
    for j, k in enumerate(nations):
        dr.text((8 + (j + 1) * cw, 4), k, fill=(255, 230, 120))

    def cellset(cardimg, miniimg, btnimg, port):
        c = Image.new('RGBA', (cw, ch), (28, 28, 30, 255))
        c.alpha_composite(cardimg, (0, 14)); c.alpha_composite(miniimg, (76, 14)); c.alpha_composite(btnimg, (112, 14))
        c.alpha_composite(port.crop((0, 0, 157, 172)).convert('RGBA'), (173, 14))
        return c
    for i, t in enumerate(troops):
        y = 20 + i * ch
        dr.text((8, y), t, fill=(200, 200, 200))
        src = 'ARAB_' + t if 'ARAB_' + t in PT.SOURCES else 'GEN_' + t
        sh.paste(cellset(o.card(src, 0), o.mini(src, 0), o.button(src, False), o.portrait(src)).convert('RGB'), (8, y))
        for j, k in enumerate(nations):
            info = by[t].get(k)
            if info is None:
                continue
            cs = cellset(maker.card(k, t, info, 0), maker.mini(k, t, info, 0), maker.button(k, t, info, False),
                         maker.portrait(k, t, info))
            sh.paste(cs.convert('RGB'), (8 + (j + 1) * cw, y))
    sh.save(out_png)


if __name__ == '__main__':
    args = sys.argv[1:]
    rendered = '--render' in args
    only = set(a for a in args if not a.startswith('--')) or None
    art = Art()
    items = collect(only, rendered)
    maker = RenderedArt(art) if rendered else PaintedArt(art)
    build(maker, items)
    sheet(maker, items, os.path.join(ROOT, 'build', 'icons', 'sheet.png'))
    print('written under', OUT)

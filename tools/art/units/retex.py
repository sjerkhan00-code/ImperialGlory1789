"""Retexture toolkit for Imperial Glory unit textures (prototype stage, writes only PNG previews).

A unit texture is a 256x256 atlas; the model's UV islands tell which pixels belong to which body part, and the
rest-pose vertex heights tell what the island is (head / torso / legs ...).  Recolouring keeps the painted folds
and shading: each pixel's luminance is kept and only the base colour is swapped, so the result stays in the game's
own hand-painted style.  A small software rasteriser renders the model with the texture for previews.

    python tools/art/units/retex.py islands <model.V3D>            # list UV islands with height and size
    python tools/art/units/retex.py render  <model.V3D> <tex> <out.png>
"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import uvdump

S = 256


# ------------------------------------------------------------------ UV islands
def islands(model, mesh_index=None):
    """-> list of dict(mask 'L' image, tris, cy (mean rest height), cx, bbox) for the (textured) meshes of a model."""
    ms = [m for m in uvdump.meshes(model) if m['uv'] and m['tris']]
    if mesh_index is not None:
        ms = [ms[mesh_index]]
    out = []
    for m in ms:
        n = len(m['uv'])
        parent = list(range(n))
        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a
        for a, b, c in m['tris']:
            for x, y in ((a, b), (b, c)):
                ra, rb = find(x), find(y)
                if ra != rb:
                    parent[ra] = rb
        # vertices at the same UV (seam duplicates) are joined too, so an island is one continuous patch
        byuv = {}
        for i, (u, v) in enumerate(m['uv']):
            k = (round(u * S * 2), round(v * S * 2))
            if k in byuv:
                ra, rb = find(i), find(byuv[k])
                if ra != rb:
                    parent[ra] = rb
            else:
                byuv[k] = i
        groups = {}
        for t in m['tris']:
            groups.setdefault(find(t[0]), []).append(t)
        for root, tris in groups.items():
            mask = Image.new('L', (S, S), 0)
            dr = ImageDraw.Draw(mask)
            vs = set()
            for t in tris:
                dr.polygon([(m['uv'][k][0] * S, m['uv'][k][1] * S) for k in t], fill=255, outline=255)
                vs.update(t)
            pos = [m['pos'][k] for k in vs] if m['pos'] else [(0, 0, 0)]
            bb = mask.getbbox()
            out.append(dict(mesh=m['name'], mask=mask, tris=tris, n=len(tris), cy=sum(p[1] for p in pos) / len(pos),
                            cx=sum(p[0] for p in pos) / len(pos), ymin=min(p[1] for p in pos), ymax=max(p[1] for p in pos),
                            bbox=bb, area=sum(1 for px in mask.getdata() if px)))
    out.sort(key=lambda i: -i['area'])
    return out


def union(masks, grow=2):
    m = Image.new('L', (S, S), 0)
    for k in masks:
        m = Image.composite(Image.new('L', (S, S), 255), m, k)
    if grow:
        m = m.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return m


def box_mask(x0, y0, x1, y1):
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
    return m


# ------------------------------------------------------------------ colour operations
def _lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def _np(img):
    import numpy as np
    return np.asarray(img.convert('RGB'), dtype=np.float32)


def _mk(mask):
    import numpy as np
    return np.asarray(mask, dtype=np.float32) / 255.0


def tint(img, mask, rgb, base=None, contrast=1.0, mix=1.0):
    """Replace the base colour under mask by rgb, keeping the painted light/shade.
    base: luminance that maps to rgb exactly (default: the mean luminance under the mask)."""
    import numpy as np
    a = _np(img); m = _mk(mask)
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    if base is None:
        base = float((lum * m).sum() / max(m.sum(), 1)) if m.any() else 128.0
    base = max(base, 1.0)
    f = ((lum - base) * contrast + base) / base
    n = np.clip(f[..., None] * np.array(rgb, np.float32), 0, 255)
    w = (mix * m)[..., None]
    out = n * w + a * (1 - w)
    return Image.fromarray(out.astype(np.uint8))


def hsv_mask(img, mask, h=(0, 360), s=(0, 1), v=(0, 1), feather=1):
    """Pixels under mask whose HSV lies in the given ranges (hue in degrees, wraps if h[0] > h[1])."""
    import numpy as np
    a = _np(img) / 255.0
    hsv = np.asarray(img.convert('RGB').convert('HSV'), dtype=np.float32)
    hh = hsv[..., 0] * 360.0 / 255.0; ss = hsv[..., 1] / 255.0; vv = hsv[..., 2] / 255.0
    hok = (hh >= h[0]) & (hh <= h[1]) if h[0] <= h[1] else (hh >= h[0]) | (hh <= h[1])
    ok = hok & (ss >= s[0]) & (ss <= s[1]) & (vv >= v[0]) & (vv <= v[1]) & (np.asarray(mask) > 0)
    out = Image.fromarray((ok * 255).astype(np.uint8))
    if feather:
        out = out.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.BoxBlur(feather))
        out = Image.composite(out, Image.new('L', (S, S), 0), mask)
    return out


def desaturate(img, mask, amount=1.0):
    import numpy as np
    a = _np(img); m = _mk(mask)[..., None] * amount
    lum = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114)[..., None]
    return Image.fromarray((a * (1 - m) + lum * m).astype(np.uint8))


def paint(img, mask, rgba):
    """Flat colour (with alpha) under mask, on top of the texture."""
    layer = Image.new('RGBA', (S, S), rgba)
    m = Image.eval(mask, lambda v: v * rgba[3] // 255)
    out = img.convert('RGBA')
    out.paste(layer, (0, 0), m)
    return out.convert('RGB')


def glyph(img, text, font_path, size, xy, fill, anchor='mm', stroke=0, stroke_fill=None):
    out = img.convert('RGB')
    f = ImageFont.truetype(font_path, size)
    ImageDraw.Draw(out).text(xy, text, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=stroke_fill)
    return out


def disc(img, xy, r, fill, outline=None, width=1):
    out = img.convert('RGB')
    ImageDraw.Draw(out).ellipse([xy[0] - r, xy[1] - r, xy[0] + r, xy[1] + r], fill=fill, outline=outline, width=width)
    return out


def stripes(img, mask, colours, period, angle=0.0, mix=0.85):
    """Woven / striped cloth pattern under mask (kente, tartan, lamellar rows), modulated by the texture's shading."""
    import numpy as np
    a = _np(img); m = _mk(mask)[..., None] * mix
    ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)
    t = (xs * math.cos(angle) + ys * math.sin(angle)) / period
    idx = np.floor(t).astype(np.int64) % len(colours)
    pal = np.array(colours, np.float32)[idx]
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    mm = _mk(mask)
    base = float((lum * mm).sum() / max(mm.sum(), 1)) or 128.0     # the region's own mean maps to the pattern colours
    n = np.clip(pal * (lum / base)[..., None], 0, 255)
    return Image.fromarray((n * m + a * (1 - m)).astype(np.uint8))


# ------------------------------------------------------------------ preview renderer
def render(model, textures, size=(220, 420), yaw=0.0, pitch=0.0, light=(-0.45, 0.75, -0.5), ss=3, bg=(118, 132, 70),
           ambient=0.42, diffuse=0.68):
    """Supersampled orthographic render of the rest pose with Gouraud lighting and bilinear texturing.
    textures: one PIL image per textured mesh (mount first for cavalry).  yaw: 0 = front; pitch > 0 looks down."""
    import numpy as np
    ms = [m for m in uvdump.meshes(model) if m['uv'] and m['tris'] and m['pos'] and len(m['pos']) == len(m['uv'])]
    allp = np.array([p for m in ms for p in m['pos']], np.float32)
    lo, hi = allp.min(0), allp.max(0)
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    W, H = size[0] * ss, size[1] * ss
    sc = (H - 24 * ss) / (hi[1] - lo[1])
    cy, sy_ = math.cos(yaw), math.sin(yaw); cp, sp = math.cos(pitch), math.sin(pitch)
    img = np.empty((H, W, 3), np.float32); img[:] = bg
    # ground: a slightly darker band and a soft shadow blob under the figure
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    img *= (1 - 0.12 * np.clip((yy - H * 0.78) / (H * 0.22), 0, 1))[..., None]
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
        sx = W / 2 + V[:, 0] * sc; sy = H - 12 * ss - V[:, 1] * sc
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
    out = img.reshape(size[1], ss, size[0], ss, 3).mean((1, 3))
    return Image.fromarray(out.astype(np.uint8))


def preview(model, orig_tex, new_tex, out_png, title='', mesh_textures=None):
    """Side by side: original texture, new texture, and front/back renders with each.  mesh_textures: for
    two-mesh models, (orig list, new list) of textures per mesh."""
    o, n = orig_tex.convert('RGB'), new_tex.convert('RGB')
    to, tn = (mesh_textures if mesh_textures else ([o], [n]))
    views = []
    for texs in (to, tn):
        views.append(render(model, texs, yaw=0.0))                  # yaw 0 is the front view
        views.append(render(model, texs, yaw=0.55, pitch=0.26))     # 3/4 view, slightly from above, like the game camera
    gap = 6
    W = 2 * S * 2 + gap * 5 + sum(v.width for v in views)
    H = max(S * 2, views[0].height) + 24
    sheet = Image.new('RGB', (W, H), (20, 20, 22))
    dr = ImageDraw.Draw(sheet)
    x = 0
    sheet.paste(o.resize((S * 2, S * 2), Image.NEAREST), (x, 24)); dr.text((x + 2, 4), 'original texture', fill=(255, 255, 0)); x += S * 2 + gap
    sheet.paste(n.resize((S * 2, S * 2), Image.NEAREST), (x, 24)); dr.text((x + 2, 4), 'retexture: ' + title, fill=(255, 255, 0)); x += S * 2 + gap
    for v, lab in zip(views, ('orig front', 'orig 3/4', 'new front', 'new 3/4')):
        sheet.paste(v, (x, 24)); dr.text((x + 2, 4), lab, fill=(255, 255, 0)); x += v.width + gap
    sheet.save(out_png)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'islands':
        for i, isl in enumerate(islands(sys.argv[2])):
            print('%2d %-18s tris %3d  area %5d  bbox %-22s  y %5.0f..%5.0f (mean %5.0f)  x %5.0f'
                  % (i, isl['mesh'], isl['n'], isl['area'], isl['bbox'], isl['ymin'], isl['ymax'], isl['cy'], isl['cx']))
    elif cmd == 'render':
        render(sys.argv[2], [uvdump.load_tex(sys.argv[3])]).save(sys.argv[4])

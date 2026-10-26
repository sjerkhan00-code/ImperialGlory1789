"""Thin-plate-spline warp between the game map and the user's prototype picture.

Coordinates: game points are pixels in build/game_map_2048.png (the 16 original tiles, 512 px each, north up);
prototype points are pixels in prototype.png (2000 x 1325). The spline maps game pixel -> prototype pixel, so any
point of the (extended) game map can be filled from the prototype. Outside the control points it continues as
the best affine fit, which is what carries the new regions (Africa, India, East Asia, Australia).
"""
import numpy as np

# (game x, game y, prototype x, prototype y), picked on matching coastline features
POINTS = [
    (272, 952, 262, 440),     # NW Spain (Finisterre)
    (420, 800, 364, 382),     # Brittany (Brest)
    (262, 1292, 285, 572),    # Strait of Gibraltar
    (225, 1360, 250, 600),    # Morocco, Atlantic coast below Tangier
    (140, 1405, 232, 630),    # Morocco coast
    (120, 1460, 212, 660),    # Morocco coast
    (95, 1485, 198, 672),     # Morocco coast at the old map frame
    (705, 1370, 541, 587),    # Sicily, west tip
    (875, 1340, 585, 570),    # heel of Italy
    (800, 1352, 560, 604),    # toe of Italy
    (930, 1500, 642, 597),    # Peloponnese, south tip
    (1045, 1270, 717, 530),   # Bosporus
    (1183, 1125, 787, 465),   # Crimea, south tip
    (1372, 1185, 848, 511),   # Black Sea, east end
    (1520, 862, 945, 416),    # Caspian, north tip
    (1590, 1300, 935, 565),   # Caspian, south end
    (1210, 1520, 767, 612),   # Cyprus
    (1250, 1690, 792, 632),   # Levant, south (Gaza)
    (1205, 1752, 757, 687),   # Gulf of Suez, north tip
    (1245, 1827, 780, 714),   # Sinai tip
    (1300, 1927, 795, 737),   # Red Sea at the old map frame
    (1622, 1635, 927, 672),   # Persian Gulf, head
    (1747, 1782, 945, 722),   # Qatar
    (1890, 1742, 991, 715),   # Strait of Hormuz (Musandam)
    (1962, 1792, 1010, 728),  # Gulf of Oman at the old map frame
    (640, 1450, 505, 590),    # Cape Bon
    (890, 1700, 605, 680),    # Gulf of Sidra, south
    (960, 230, 665, 147),     # Gulf of Bothnia, north end
    (1105, 445, 702, 205),    # Gulf of Finland, east end
]


def _U(r2):
    with np.errstate(divide='ignore', invalid='ignore'):
        v = r2 * np.log(r2)
    v[r2 == 0] = 0
    return v


class TPS:
    def __init__(self, src, dst, smooth=0.0):
        src = np.asarray(src, float); dst = np.asarray(dst, float)
        n = len(src)
        K = _U(((src[:, None, :] - src[None, :, :]) ** 2).sum(-1)) + smooth * np.eye(n)
        P = np.hstack([np.ones((n, 1)), src])
        A = np.zeros((n + 3, n + 3)); A[:n, :n] = K; A[:n, n:] = P; A[n:, :n] = P.T
        b = np.zeros((n + 3, 2)); b[:n] = dst
        self.w = np.linalg.solve(A, b)
        self.src = src

    def __call__(self, pts):
        pts = np.asarray(pts, float)
        U = _U(((pts[:, None, :] - self.src[None, :, :]) ** 2).sum(-1))
        n = len(self.src)
        return U @ self.w[:n] + self.w[n] + pts @ self.w[n + 1:]


def game_to_proto(smooth=0.0):
    g = [(a, b) for a, b, _, _ in POINTS]
    p = [(c, d) for _, _, c, d in POINTS]
    return TPS(g, p, smooth)


def proto_to_game(smooth=0.0):
    g = [(a, b) for a, b, _, _ in POINTS]
    p = [(c, d) for _, _, c, d in POINTS]
    return TPS(p, g, smooth)


def similarity_fit():
    """Least-squares uniform scale + rotation + translation, game px -> prototype px."""
    g = np.array([(a, b) for a, b, _, _ in POINTS], float)
    p = np.array([(c, d) for _, _, c, d in POINTS], float)
    # complex form: p = a*g + b with a = s*e^(i theta)
    gc = g[:, 0] + 1j * g[:, 1]; pc = p[:, 0] + 1j * p[:, 1]
    A = np.vstack([gc, np.ones_like(gc)]).T
    sol, *_ = np.linalg.lstsq(A, pc, rcond=None)
    return sol[0], sol[1]


OLD_RECT = (0.0, 0.0, 1955.0, 1925.0)     # the old map art, g px


def blended_game_to_proto(near=150.0, far=900.0, smooth=2.0):
    """TPS close to the old map (so coasts meet the game art), a similarity transform far away (so new continents
    keep a natural shape). Returns f(points Nx2) -> Nx2."""
    tps = game_to_proto(smooth)
    a, b = similarity_fit()
    x0, y0, x1, y1 = OLD_RECT
    def f(pts):
        pts = np.asarray(pts, float)
        dx = np.maximum(0, np.maximum(x0 - pts[:, 0], pts[:, 0] - x1))
        dy = np.maximum(0, np.maximum(y0 - pts[:, 1], pts[:, 1] - y1))
        d = np.hypot(dx, dy)
        w = np.clip((d - near) / (far - near), 0, 1)
        w = w * w * (3 - 2 * w)
        s = a * (pts[:, 0] + 1j * pts[:, 1]) + b
        sim = np.stack([s.real, s.imag], 1)
        return tps(pts) * (1 - w)[:, None] + sim * w[:, None]
    return f


# real longitude/latitude of the same features, in the order of POINTS
LONLAT = [
    (-9.3, 42.9), (-4.8, 48.4), (-5.6, 36.0), (-6.1, 35.2), (-7.6, 33.6), (-9.3, 32.3), (-9.9, 30.6),
    (12.4, 38.0), (18.4, 39.8), (15.65, 37.95), (22.5, 36.4), (29.0, 41.1), (33.4, 44.4), (41.6, 41.6),
    (49.0, 46.9), (51.5, 36.7), (33.2, 35.0), (34.4, 31.4), (32.55, 29.97), (34.25, 27.73), (35.3, 26.0),
    (48.0, 29.9), (51.2, 26.15), (56.3, 26.4), (57.5, 25.0), (11.05, 37.08), (19.5, 30.3), (24.15, 65.8),
    (30.2, 59.9),
]
COS0 = np.cos(np.radians(30.0))          # far-field projection: x = lon * cos(30), y = -lat


def blended_game_to_lonlat(near=150.0, far=900.0, smooth=2.0):
    """game g px -> (lon, lat). TPS near the old map, a similarity transform (in lon*cos30 / lat) far away."""
    assert len(LONLAT) == len(POINTS)
    g = np.array([(a, b) for a, b, _, _ in POINTS], float)
    ll = np.array(LONLAT, float)
    proj = np.stack([ll[:, 0] * COS0, -ll[:, 1]], 1)
    tps = TPS(g, proj, smooth)
    gc = g[:, 0] + 1j * g[:, 1]; pc = proj[:, 0] + 1j * proj[:, 1]
    sol, *_ = np.linalg.lstsq(np.vstack([gc, np.ones_like(gc)]).T, pc, rcond=None)
    a, b = sol
    x0, y0, x1, y1 = OLD_RECT
    def f(pts):
        pts = np.asarray(pts, float)
        dx = np.maximum(0, np.maximum(x0 - pts[:, 0], pts[:, 0] - x1))
        dy = np.maximum(0, np.maximum(y0 - pts[:, 1], pts[:, 1] - y1))
        w = np.clip((np.hypot(dx, dy) - near) / (far - near), 0, 1)
        w = w * w * (3 - 2 * w)
        s = a * (pts[:, 0] + 1j * pts[:, 1]) + b
        p = tps(pts) * (1 - w)[:, None] + np.stack([s.real, s.imag], 1) * w[:, None]
        return np.stack([p[:, 0] / COS0, -p[:, 1]], 1)
    f.similarity = (a, b)
    return f


# prototype pixel -> real (lon, lat) for the far regions, picked on the prototype's coasts
PROTO_FAR = [
    (137, 840, -17.5, 14.7), (225, 960, -7.7, 4.4), (380, 962, 6.0, 4.3), (415, 980, 9.5, 4.0),
    (942, 885, 51.3, 11.8), (865, 887, 43.4, 12.6), (907, 1145, 49.3, -12.0), (885, 1280, 45.1, -25.6),
    (822, 1130, 40.7, -15.0), (860, 1005, 39.7, -4.0),
    (1100, 745, 70.9, 20.7), (1157, 897, 77.5, 8.1), (1190, 915, 80.6, 5.9), (1280, 730, 88.3, 21.7), (1120, 805, 72.8, 19.0),
    (1465, 730, 109.5, 19.2), (1410, 857, 104.8, 8.6), (1387, 935, 103.8, 1.3), (1307, 892, 95.3, 5.6),
    (1482, 1037, 114.4, -8.7), (1520, 867, 116.9, 7.0), (1565, 742, 120.6, 18.5), (1605, 880, 125.4, 5.6), (1565, 685, 121.0, 23.7),
    (1615, 560, 126.5, 34.4), (1650, 592, 130.7, 31.0), (1730, 530, 139.9, 34.9), (1782, 435, 145.5, 43.4), (1739, 316, 142.7, 54.3),
    (1980, 177, 190.0, 66.0), (1840, 367, 156.7, 51.0),
    (1746, 1047, 142.5, -10.7), (1487, 1160, 113.6, -21.8), (1500, 1240, 115.1, -34.4), (1740, 1297, 146.4, -39.1),
    (1822, 1230, 151.2, -33.9), (1717, 1102, 140.8, -17.5),
]


def proto_to_lonlat(smooth=8.0):
    """prototype px -> (lon, lat), from all prototype features with known real coordinates."""
    src = [(c, d) for _, _, c, d in POINTS] + [(a, b) for a, b, _, _ in PROTO_FAR]
    dst = list(LONLAT) + [(c, d) for _, _, c, d in PROTO_FAR]
    return TPS(src, dst, smooth)


def game_to_lonlat():
    """game g px -> (lon, lat) through the prototype's layout: g -> prototype px -> real coordinates."""
    g2p = blended_game_to_proto()
    p2l = proto_to_lonlat()
    def f(pts):
        p = g2p(pts)
        return p, p2l(p)
    return f

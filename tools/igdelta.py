"""IGD1: a tiny binary delta format (pure Python here; install.ps1 has the matching applier, Expand-Delta).

The Nexus package must not contain original game files, so a modified original file ships as a delta against the
player's own copy (data.pak / Data1.pak / Text.pak).

Format (little endian):
    'IGD1'  u32 source length  u32 target length
    ops:    0x01 COPY    u32 source offset, u32 length      -> source[offset:offset+length]
            0x02 INSERT  u32 length, <length raw bytes>     -> the new bytes themselves
            0x00 END     (must be the last byte of the delta)
The source / target MD5s live in the release manifest, not in the delta.

The encoder is a greedy block matcher: every STRIDE-th B-byte window of the source goes into a dict; the target is
scanned byte by byte (first trying to continue at the alignment of the previous match), each hit is extended backwards
over the pending literal bytes and forwards as far as the bytes agree, and becomes a COPY when it is >= MIN_COPY bytes.
"""
import struct

MAGIC = b'IGD1'
B = 16          # window (key) length
STRIDE = 4      # source index stride: every match >= B + STRIDE - 1 bytes is found
MIN_COPY = 16   # shortest COPY worth an op (a COPY op costs 9 bytes)


def _match_len(a, i, b, j):
    n = min(len(a) - i, len(b) - j)
    k, step = 0, 4096
    while step:
        while k + step <= n and a[i + k:i + k + step] == b[j + k:j + k + step]:
            k += step
        step //= 8
    return k


def index(src):
    idx = {}
    for i in range(0, len(src) - B + 1, STRIDE):
        idx.setdefault(src[i:i + B], i)
    return idx


def make_ops(src, tgt, limit=None, idx=None):
    """List of ops ((1, off, len) / (2, bytes)), or None as soon as the literal bytes exceed `limit`."""
    if idx is None:
        idx = index(src)
    get = idx.get
    ops, j, lit, n, last, nlit, ns = [], 0, 0, len(tgt), None, 0, len(src)
    lim = (n + 1) if limit is None else limit
    while j <= n - B:
        key = tgt[j:j + B]
        s = None
        if last is not None:
            c = j + last
            if 0 <= c <= ns - B and src[c:c + B] == key:
                s = c
        if s is None:
            s = get(key)
            if s is None:
                j += 1
                if nlit + (j - lit) > lim:
                    return None
                continue
        t = j
        while t > lit and s > 0 and src[s - 1] == tgt[t - 1]:
            s -= 1
            t -= 1
        k = _match_len(src, s, tgt, t)
        if k < MIN_COPY:
            j += 1
            continue
        if t > lit:
            ops.append((2, tgt[lit:t]))
            nlit += t - lit
        ops.append((1, s, k))
        j = t + k
        lit = j
        last = s - t
    if lit < n:
        ops.append((2, tgt[lit:]))
        nlit += n - lit
    if nlit > lim:
        return None
    return ops


def encode(ops, src_len, tgt_len):
    out = [MAGIC, struct.pack('<II', src_len, tgt_len)]
    for op in ops:
        if op[0] == 1:
            out.append(struct.pack('<BII', 1, op[1], op[2]))
        else:
            out.append(struct.pack('<BI', 2, len(op[1])))
            out.append(op[1])
    out.append(b'\0')
    return b''.join(out)


def make(src, tgt, limit=None, idx=None):
    """Encoded delta, or None (see make_ops)."""
    ops = make_ops(src, tgt, limit, idx)
    return None if ops is None else encode(ops, len(src), len(tgt))


def stats(d):
    """(copy ops, insert ops, copied bytes, inserted bytes) of an encoded delta."""
    p, r = 12, [0, 0, 0, 0]
    while d[p]:
        if d[p] == 1:
            r[0] += 1
            r[2] += struct.unpack_from('<I', d, p + 5)[0]
            p += 9
        else:
            n = struct.unpack_from('<I', d, p + 1)[0]
            r[1] += 1
            r[3] += n
            p += 5 + n
    return tuple(r)


def apply(src, d):
    """Rebuild the target; raises ValueError on any inconsistency (same checks as install.ps1 Expand-Delta)."""
    if d[:4] != MAGIC or len(d) < 13:
        raise ValueError('not an IGD1 delta')
    sl, tl = struct.unpack_from('<II', d, 4)
    if sl != len(src):
        raise ValueError('source length %d != %d' % (len(src), sl))
    out, p, w = bytearray(tl), 12, 0
    while True:
        if p >= len(d):
            raise ValueError('delta truncated')
        op = d[p]
        p += 1
        if op == 0:
            break
        if op == 1:
            o, n = struct.unpack_from('<II', d, p)
            p += 8
            if o + n > sl or w + n > tl:
                raise ValueError('COPY out of range')
            out[w:w + n] = src[o:o + n]
        elif op == 2:
            n, = struct.unpack_from('<I', d, p)
            p += 4
            if p + n > len(d) or w + n > tl:
                raise ValueError('INSERT out of range')
            out[w:w + n] = d[p:p + n]
            p += n
        else:
            raise ValueError('bad op %d' % op)
        w += n
    if w != tl or p != len(d):
        raise ValueError('delta length mismatch')
    return bytes(out)

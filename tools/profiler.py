"""Sampling profiler for the running game (read-only on memory; each sample pauses one thread for a few microseconds
with SuspendThread/ResumeThread to read its registers, as any sampling profiler does).

    python tools/profiler.py [seconds=60] [interval_ms=10]

Prints the hottest functions (by EIP) and the hottest call chains (return addresses found on the stack), mapped to
the Ghidra function names of re_tools/all.c. Writes the raw samples to build/profile_<time>.json.
"""
import ctypes, ctypes.wintypes as W, struct, sys, time, json, os, re, bisect, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memread import Proc, pid_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
THREAD_ACCESS = 0x0002 | 0x0008 | 0x0040           # suspend/resume, get context, query information
WOW64_CONTEXT_FULL = 0x10007
EXE_BASE = 0x400000


class THREADENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ThreadID', W.DWORD), ('th32OwnerProcessID', W.DWORD),
                ('tpBasePri', W.LONG), ('tpDeltaPri', W.LONG), ('dwFlags', W.DWORD)]


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te); out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def cpu_time(h):
    c, e, kt, ut = (W.FILETIME() for _ in range(4))
    k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
    return ((kt.dwHighDateTime << 32 | kt.dwLowDateTime) + (ut.dwHighDateTime << 32 | ut.dwLowDateTime)) / 1e7


def context(h):
    buf = ctypes.create_string_buffer(716)
    struct.pack_into('<I', buf, 0, WOW64_CONTEXT_FULL)
    if k32.SuspendThread(h) == 0xFFFFFFFF:
        return None
    try:
        ok = k32.Wow64GetThreadContext(h, buf)
    finally:
        k32.ResumeThread(h)
    if not ok:
        return None
    ebp, eip = struct.unpack_from('<II', buf, 180)
    esp, = struct.unpack_from('<I', buf, 196)
    return eip, esp, ebp


def load_functions():
    starts = []
    for line in open(os.path.join(ROOT, 're_tools', 'all.c'), encoding='latin1'):
        if line.startswith('//==== FUN_'):
            starts.append(int(re.search(r'@ ([0-9a-f]+)', line).group(1), 16))
    starts.sort()
    return starts


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    interval = (float(sys.argv[2]) if len(sys.argv) > 2 else 10) / 1000
    pid = pid_of()
    p = Proc(pid)
    exe = open(os.path.join(r'C:\Program Files (x86)\Steam\steamapps\common\Imperial Glory', 'ImperialGlory_ModNations.exe'), 'rb').read()
    starts = load_functions()
    fname = lambda a: 'FUN_%08x' % starts[bisect.bisect_right(starts, a) - 1] if EXE_BASE < a < EXE_BASE + len(exe) else 'ext_%08x' % (a & 0xFFFF0000)
    def is_ret(v):
        o = v - EXE_BASE
        if not (0x1000 <= o < len(exe)):
            return False
        return exe[o - 5] == 0xE8 or (exe[o - 6] == 0xFF and (exe[o - 5] & 0x38) == 0x10) or \
            (exe[o - 2] == 0xFF and (exe[o - 1] & 0x38) == 0x10) or (exe[o - 3] == 0xFF and (exe[o - 2] & 0x38) == 0x10)
    # the busiest thread over one second = the game thread doing the AI turn
    handles = {t: k32.OpenThread(THREAD_ACCESS, False, t) for t in threads_of(pid)}
    t0 = {t: cpu_time(h) for t, h in handles.items()}
    time.sleep(1.0)
    busy = sorted(handles, key=lambda t: cpu_time(handles[t]) - t0[t], reverse=True)
    tid = busy[0]; h = handles[tid]
    print('threads', len(handles), 'busiest', tid, 'cpu share over 1 s: %.0f%%' % (100 * (cpu_time(h) - t0[tid])))
    flat, chains, raw = collections.Counter(), collections.Counter(), []
    end = time.time() + seconds; n = 0
    while time.time() < end:
        c = context(h)
        if c:
            eip, esp, ebp = c
            stk = p.read(esp, 0x800) or b''
            rets = [v for v in struct.unpack('<%dI' % (len(stk) // 4), stk) if is_ret(v)][:8]
            flat[fname(eip)] += 1
            chains[(fname(eip),) + tuple(fname(r) for r in rets[:4])] += 1
            raw.append([eip] + rets)
            n += 1
        time.sleep(interval)
    print('%d samples in %.0f s' % (n, seconds))
    print('\nhottest functions (share of samples):')
    for f, k in flat.most_common(15):
        print('  %5.1f%%  %s' % (100.0 * k / n, f))
    print('\nhottest call chains (function <- callers):')
    for ch, k in chains.most_common(12):
        print('  %5.1f%%  %s' % (100.0 * k / n, ' <- '.join(ch)))
    out = os.path.join(ROOT, 'build', 'profile_%s.json' % time.strftime('%H%M%S'))
    json.dump({'tid': tid, 'samples': raw}, open(out, 'w'))
    print('\nraw samples:', out)


if __name__ == '__main__':
    main()

"""Read-only log of AI turn durations while the game is played: the game thread's CPU load marks the AI phase
(busy) vs the player's turn (idle); the route-table owner (exe patch 14 keeps it at 0x942f08) tells which AI object
is planning. Writes build/turnlog.txt.   python tools/turnlog.py [minutes=20]"""
import sys, os, struct, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profiler as PR
from memread import Proc, pid_of
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 20
pid = pid_of(); p = Proc(pid)
hs = {t: PR.k32.OpenThread(PR.THREAD_ACCESS, False, t) for t in PR.threads_of(pid)}
t0 = {t: PR.cpu_time(h) for t, h in hs.items()}; time.sleep(2)
tid = max(hs, key=lambda t: PR.cpu_time(hs[t]) - t0[t]); h = hs[tid]
log = open(os.path.join(ROOT, 'build', 'turnlog.txt'), 'a', buffering=1)
def say(s):
    line = time.strftime('%H:%M:%S ') + s; print(line, flush=True); log.write(line + '\n')
say('--- logging thread %d for %.0f min' % (tid, minutes))
busy_since = None; seg_obj = None; seg_start = None; segs = []
last_cpu, last_t = PR.cpu_time(h), time.time(); end = time.time() + minutes * 60
while time.time() < end:
    time.sleep(0.5)
    try:
        cpu, now = PR.cpu_time(h), time.time()
        load = (cpu - last_cpu) / (now - last_t); last_cpu, last_t = cpu, now
        obj, cnt = struct.unpack('<II', p.read(0x942f08, 8))
    except Exception:
        say('game closed'); break
    if busy_since is None and load > 0.85:
        busy_since = now; segs = []; seg_obj, seg_start = obj, now
    elif busy_since is not None:
        if obj != seg_obj:
            segs.append((seg_obj, now - seg_start)); seg_obj, seg_start = obj, now
        if load < 0.5:
            segs.append((seg_obj, now - seg_start))
            longest = sorted(segs, key=lambda s: -s[1])[:3]
            say('AI phase %.0f s; longest AI objects: %s' % (now - busy_since, ', '.join('%x %.0fs' % s for s in longest)))
            busy_since = None
say('--- end')

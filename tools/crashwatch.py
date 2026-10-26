"""Launch the game under a minimal debugger and record the state when it crashes.

Writes build/crash_<time>.txt with registers, the faulting instruction and a heuristic call stack
(stack words that are return addresses: the bytes before them are a CALL). Read-only: it never
changes the game's memory or code. Usage: python -I crashwatch.py <exe>
"""
import ctypes, ctypes.wintypes as w, sys, os, time, struct

k32 = ctypes.windll.kernel32
DEBUG_ONLY_THIS_PROCESS = 2
EXCEPTION_DEBUG_EVENT, CREATE_PROCESS_DEBUG_EVENT, EXIT_PROCESS_DEBUG_EVENT, LOAD_DLL_DEBUG_EVENT = 1, 3, 5, 6
DBG_CONTINUE, DBG_EXCEPTION_NOT_HANDLED = 0x00010002, 0x80010001
STATUS_WX86_BREAKPOINT, STATUS_BREAKPOINT, ACCESS_VIOLATION = 0x4000001F, 0x80000003, 0xC0000005


class STARTUPINFO(ctypes.Structure):
    _fields_ = [('cb', w.DWORD), ('lpReserved', w.LPWSTR), ('lpDesktop', w.LPWSTR), ('lpTitle', w.LPWSTR),
                ('dwX', w.DWORD), ('dwY', w.DWORD), ('dwXSize', w.DWORD), ('dwYSize', w.DWORD),
                ('dwXCountChars', w.DWORD), ('dwYCountChars', w.DWORD), ('dwFillAttribute', w.DWORD),
                ('dwFlags', w.DWORD), ('wShowWindow', w.WORD), ('cbReserved2', w.WORD), ('lpReserved2', ctypes.c_void_p),
                ('hStdInput', w.HANDLE), ('hStdOutput', w.HANDLE), ('hStdError', w.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', w.HANDLE), ('hThread', w.HANDLE), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD)]


class EXCEPTION_RECORD(ctypes.Structure):
    _fields_ = [('ExceptionCode', w.DWORD), ('ExceptionFlags', w.DWORD), ('ExceptionRecord', ctypes.c_void_p),
                ('ExceptionAddress', ctypes.c_void_p), ('NumberParameters', w.DWORD), ('ExceptionInformation', ctypes.c_size_t * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [('ExceptionRecord', EXCEPTION_RECORD), ('dwFirstChance', w.DWORD)]


class _U(ctypes.Union):
    _fields_ = [('exc', EXCEPTION_DEBUG_INFO), ('raw', ctypes.c_byte * 176)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [('dwDebugEventCode', w.DWORD), ('dwProcessId', w.DWORD), ('dwThreadId', w.DWORD), ('u', _U)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = ([('ContextFlags', w.DWORD)] + [(n, w.DWORD) for n in 'Dr0 Dr1 Dr2 Dr3 Dr6 Dr7'.split()]
                + [('FloatSave', ctypes.c_byte * 112)]
                + [(n, w.DWORD) for n in 'SegGs SegFs SegEs SegDs Edi Esi Ebx Edx Ecx Eax Ebp Eip SegCs EFlags Esp SegSs'.split()]
                + [('Ext', ctypes.c_byte * 512)])


def main(exe):
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'build')
    code = open(exe, 'rb').read()
    si = STARTUPINFO(); si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()
    if not k32.CreateProcessW(exe, None, None, None, False, DEBUG_ONLY_THIS_PROCESS, None, os.path.dirname(exe),
                              ctypes.byref(si), ctypes.byref(pi)):
        print('CreateProcess failed', k32.GetLastError()); return
    print('started pid', pi.dwProcessId, '- play until the crash; this window waits.')
    ev = DEBUG_EVENT()
    threads = {}

    def rd(addr, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        if k32.ReadProcessMemory(pi.hProcess, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) and got.value == n:
            return buf.raw
        return None

    while True:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 0xFFFFFFFF):
            break
        cont = DBG_CONTINUE
        if ev.dwDebugEventCode == EXCEPTION_DEBUG_EVENT:
            info = ev.u.exc
            exc = info.ExceptionRecord.ExceptionCode
            if exc in (STATUS_WX86_BREAKPOINT, STATUS_BREAKPOINT):
                cont = DBG_CONTINUE
            elif exc == ACCESS_VIOLATION:
                cont = DBG_EXCEPTION_NOT_HANDLED
                h = k32.OpenThread(0x1FFFFF, False, ev.dwThreadId)
                ctx = WOW64_CONTEXT(); ctx.ContextFlags = 0x10007
                k32.Wow64GetThreadContext(h, ctypes.byref(ctx))
                eip = ctx.Eip
                lines = ['access violation (%s chance) at 0x%08x, %s address 0x%08x' % (
                    'first' if info.dwFirstChance else 'second', eip,
                    'write' if info.ExceptionRecord.ExceptionInformation[0] == 1 else 'read',
                    info.ExceptionRecord.ExceptionInformation[1])]
                lines.append(' '.join('%s=%08x' % (n, getattr(ctx, n)) for n in 'Eax Ebx Ecx Edx Esi Edi Ebp Esp'.split()))
                stack = rd(ctx.Esp, 0x1000) or b''
                frames = []
                for k in range(0, len(stack) - 3, 4):
                    v = struct.unpack_from('<I', stack, k)[0]
                    if 0x401000 <= v < 0x8ae000:
                        o = v - 0x400000
                        if code[o - 5] == 0xE8 or code[o - 6] == 0xFF or code[o - 2] == 0xFF or code[o - 3] == 0xFF:
                            frames.append('  [esp+0x%03x] 0x%08x' % (k, v))
                lines.append('call stack (return addresses on the stack):')
                lines += frames[:40]
                txt = '\n'.join(lines)
                print(txt)
                if not info.dwFirstChance or (0x401000 <= eip < 0x8ae000):
                    p = os.path.join(out_dir, 'crash_%s.txt' % time.strftime('%H%M%S'))
                    open(p, 'w').write(txt + '\n')
                    print('saved', p)
                k32.CloseHandle(h)
            else:
                cont = DBG_EXCEPTION_NOT_HANDLED
        elif ev.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT:
            print('game exited'); k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE); break
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)


if __name__ == '__main__':
    main(sys.argv[1])

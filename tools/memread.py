"""Read-only inspection of the running game's memory (ReadProcessMemory only, nothing is written)."""
import ctypes, ctypes.wintypes as W, struct, subprocess, sys

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p), ('AllocationProtect', W.DWORD),
                ('PartitionId', W.WORD), ('RegionSize', ctypes.c_size_t), ('State', W.DWORD), ('Protect', W.DWORD), ('Type', W.DWORD)]


def pid_of(name='ImperialGlory_ModNations.exe'):
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ' + name, '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    return int(out.split(',')[1].strip('"'))


class Proc:
    def __init__(self, pid=None):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid or pid_of())
        assert self.h

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def u32(self, a):
        b = self.read(a, 4)
        return struct.unpack('<I', b)[0] if b else None

    def regions(self):
        a, m = 0, MBI()
        while a < 0xFFFF0000:
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(a), ctypes.byref(m), ctypes.sizeof(m)):
                break
            if m.State == 0x1000 and m.Protect in (0x04, 0x02, 0x40, 0x20) and not (m.Protect & 0x100):
                yield m.BaseAddress or 0, m.RegionSize
            a = (m.BaseAddress or 0) + m.RegionSize

    def find_u32(self, value):
        pat = struct.pack('<I', value); res = []
        for base, size in self.regions():
            if base < 0x10000:
                continue
            for off in range(0, size, 1 << 22):
                n = min(1 << 22, size - off)
                b = self.read(base + off, n)
                if not b:
                    continue
                i = b.find(pat)
                while i >= 0:
                    if i % 4 == 0:
                        res.append(base + off + i)
                    i = b.find(pat, i + 1)
        return res

    def cstr(self, a, n=64):
        b = self.read(a, n)
        if not b:
            return None
        b = b.split(b'\0')[0]
        return b.decode('latin1') if b and all(32 <= c < 127 for c in b) else None

"""Patch 5: scrollable Select Empire list (hand-assembled x86, checked with capstone).

The dialog builds one row per playable nation (rows vector [dlg+0xec]..[dlg+0xf0], 0x54 bytes each) and
places row i at BANDERA_Y + i*SEPARACION. This patch shows VISIBLE rows at a time:
  * two new buttons 'BTUP' / 'BTDN' (UIDefs_SelectEmpire.sb, also bound to the up/down arrow keys) send a
    button message (type 25 or 95, id at [msg+4]) that is caught at the start of the dialog's OnMessage;
  * scroll(dlg, dir) moves every row control with its own SetPosition, so rows outside the window go
    off-screen (+6000 px) and the rest move up by scroll*SEPARACION;
  * the dialog's Show (vtable slot 15) is wrapped so the layout is applied whenever the dialog opens.
State lives in unused, zero-filled memory after the end of .data (page tail, not in the file).
"""
import struct

VISIBLE = 5
HIDE = 6000
# +0x28 (BANDERA_INFO) is the info-panel emblem, not a list control, so it must not move
ROW_CONTROLS = (0x1c, 0x20, 0x24, 0x2c, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x48)
SHOW_FONDO_PUSH = 0x7cbe1a   # Show hides the row strip (FONDO, +0x24) with push 0; show it with the dialog (push ebx)
STATE = 0x942c00          # +0 rows begin seen last, +4 scroll, +0x10 applied offset per row (64 dwords)
ID_UP, ID_DN = 0x42545550, 0x4254444E      # 'BTUP', 'BTDN'
ONMSG_HOOK, ONMSG_BACK, ONMSG_EPILOGUE = 0x7c9ee9, 0x7c9eef, 0x7ca083
SHOW_SLOT, SHOW_ORIG = 0x8dc990 + 15 * 4, 0x7cbda0


class Asm:
    def __init__(self, base):
        self.base, self.b, self.lab, self.fix = base, bytearray(), {}, []

    def here(self):
        return self.base + len(self.b)

    def __call__(self, hexstr, *imm):
        self.b += bytes.fromhex(hexstr)
        for v in imm:
            self.b += struct.pack('<I', v & 0xffffffff)
        return self

    def byte(self, v):
        self.b += struct.pack('<b' if v < 0 else '<B', v)

    def L(self, name):
        self.lab[name] = self.here()

    def rel32(self, op_hex, target):              # op + rel32 to a label name or an absolute address
        self.b += bytes.fromhex(op_hex)
        self.fix.append((len(self.b), target))
        self.b += b'\0\0\0\0'

    def done(self):
        for pos, t in self.fix:
            tgt = self.lab[t] if isinstance(t, str) else t
            struct.pack_into('<i', self.b, pos, tgt - (self.base + pos + 4))
        return bytes(self.b)


def build(base):
    """Returns (code bytes at base, dict of entry addresses)."""
    a = Asm(base)
    S, C = STATE + 4, STATE + 0x10

    # ---- move(ctrl, delta): keeps x, adds delta to y. SetPosition may add a class specific offset, so it
    # is measured first: set (x0,y0), read (x1,y1), then set (2*x0-x1, 2*y0-y1+delta).
    a.L('move')
    a('56 57 53 55')                       # push esi, edi, ebx, ebp
    a('8B 74 24 14')                       # mov esi, [esp+0x14]  ctrl
    a('85 F6'); a.rel32('0F 84', 'move_done')
    a('8B 06 89 F1 FF 50 38 89 C7')        # x0 -> edi
    a('8B 06 89 F1 FF 50 3C 89 C3')        # y0 -> ebx
    a('53 57 8B 06 89 F1 FF 50 34')        # SetPosition(x0, y0)
    a('8B 06 89 F1 FF 50 38 89 C5')        # x1 -> ebp
    a('8B 06 89 F1 FF 50 3C')              # y1 -> eax
    a('89 DA 29 C2 01 DA 03 54 24 18')     # edx = y0 - y1 + y0 + delta
    a('89 F9 29 E9 01 F9')                 # ecx = x0 - x1 + x0
    a('52 51 8B 06 89 F1 FF 50 34')        # SetPosition(ecx, edx)
    a.L('move_done')
    a('5D 5B 5F 5E C2 08 00')

    # ---- scroll(dlg, dir), stdcall
    a.L('scroll')
    a('53 56 57 55')
    a('8B 74 24 14')                       # esi = dlg
    a('8B 86 EC 00 00 00')                 # eax = rows begin
    a('3B 05', STATE)
    a.rel32('0F 84', 'same_rows')
    a('A3', STATE)                         # new rows: forget scroll and offsets
    a('BF', S); a('B9', 3 + 64); a('31 C0 F3 AB')
    a.L('same_rows')
    a('8B 86 F0 00 00 00 2B 86 EC 00 00 00')   # eax = end - begin
    a('31 D2 B9', 0x54); a('F7 F1')        # eax = rows
    a('83 F8 40 76 05 B8', 64)             # at most 64
    a('89 C3')                             # ebx = rows
    a('8D 50'); a.byte(-VISIBLE)           # lea edx, [eax-VISIBLE]
    a('85 D2 7D 02 31 D2')                 # edx = max scroll
    a('A1', S); a('03 44 24 18')           # eax = scroll + dir
    a('39 D0 7E 02 89 D0')                 # min(edx)
    a('85 C0 7D 02 31 C0')                 # max(0)
    a('A3', S)
    a('89 C5 0F AF AE 08 01 00 00 F7 DD')  # ebp = -scroll * SEPARACION
    a('31 FF')                             # edi = i = 0
    a.L('loop')
    a('39 DF'); a.rel32('0F 8D', 'end')
    a('89 E9')                             # ecx = shift
    a('3B 3D', S); a.rel32('0F 8C', 'hide')
    a('A1', S); a('83 C0'); a.byte(VISIBLE); a('39 C7'); a.rel32('0F 8C', 'keep')
    a.L('hide')
    a('B9', HIDE)
    a.L('keep')
    a('89 C8 2B 04 BD', C)                 # eax = target - applied[i]
    a('89 0C BD', C)                       # applied[i] = target
    a('85 C0'); a.rel32('0F 84', 'next')
    a('6B D7 54 03 96 EC 00 00 00')        # edx = row
    a('01 42 50')                          # row+0x50 (stored y of the flag) += delta
    a('50 52')                             # [esp] = row, [esp+4] = delta
    for off in ROW_CONTROLS:
        a('8B 14 24 8B 4A'); a.byte(off)   # ecx = [row+off]
        a('FF 74 24 04 51')                # push delta; push ctrl
        a.rel32('E8', 'move')
    a('5A 58')
    a.L('next')
    a('47'); a.rel32('E9', 'loop')
    a.L('end')
    a('5D 5F 5E 5B C2 08 00')

    # ---- OnMessage hook (replaces "add eax,-4; cmp eax,0x7b"; ecx = dlg, edi = msg, eax = type)
    a.L('onmsg')
    a('83 F8 19'); a.rel32('0F 84', 'is_btn')
    a('83 F8 5F'); a.rel32('0F 85', 'orig')
    a.L('is_btn')
    a('8B 57 04')
    a('81 FA', ID_UP); a.rel32('0F 84', 'up')
    a('81 FA', ID_DN); a.rel32('0F 84', 'down')
    a.L('orig')
    a('83 C0 FC 83 F8 7B'); a.rel32('E9', ONMSG_BACK)
    a.L('up')
    a('6A FF'); a.rel32('E9', 'go')
    a.L('down')
    a('6A 01')
    a.L('go')
    a('89 CE 56'); a.rel32('E8', 'scroll')      # mov esi, ecx; push esi; call scroll(dlg, dir)
    a.rel32('E9', ONMSG_EPILOGUE)               # base handler + pops + ret 4

    # ---- Show wrapper (thiscall, 1 arg)
    a.L('show')
    a('51 FF 74 24 08'); a.rel32('E8', SHOW_ORIG)   # push ecx; push vis; call Show
    a('59')                                       # pop ecx
    a('80 7C 24 04 00'); a.rel32('0F 84', 'show_ret')
    a('6A 00 51'); a.rel32('E8', 'scroll')        # scroll(dlg, 0) = re-apply layout
    a.L('show_ret')
    a('C2 04 00')
    code = a.done()
    return code, {k: a.lab[k] for k in ('move', 'scroll', 'onmsg', 'show')}


def apply(put, base, exe_base):
    """put(file_offset, new, expect) from nations.patch_exe."""
    code, ent = build(base)
    put(base - exe_base, code)
    put(ONMSG_HOOK - exe_base, b'\xE9' + struct.pack('<i', ent['onmsg'] - (ONMSG_HOOK + 5)) + b'\x90',
        bytes.fromhex('83c0fc83f87b'))
    put(SHOW_SLOT - exe_base, struct.pack('<I', ent['show']), struct.pack('<I', SHOW_ORIG))
    put(SHOW_FONDO_PUSH - exe_base, bytes.fromhex('5390'), bytes.fromhex('6a00'))
    return code, ent


if __name__ == '__main__':
    import capstone
    code, ent = build(0x881600)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    names = {v: k for k, v in ent.items()}
    for i in md.disasm(code, 0x881600):
        if i.address in names:
            print('%s:' % names[i.address])
        print('  %08x  %-6s %s' % (i.address, i.mnemonic, i.op_str))
    print(len(code), 'bytes')

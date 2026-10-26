"""Optional exe patch: table-driven country -> 'ARABE' battle-button prefix (style of tools/nations.py patch_exe).

How the game picks the battle troop buttons (FUN_005bca70, verified in re_tools/all.c and with capstone):

    name = intern(country.name)                      # the country key of the troop's owner, e.g. "QING"
    if name in (EGIPTO, OTOMANO, TUNEZ, TRIPOLITANIA, MARRUECOS):   # five hard-coded compares, 0x5bcac2..0x5bcb42
        name = "ARABE"
    key = name + "_" + troop.key + "_BTN_INFO_TROPA"
    if not defined(key):                             # FUN_0053df10(4, key) -> 0   (0x5bcc7f..)
        key = "NEUTRAL_" + troop.key + "_BTN_INFO_TROPA"
    (callers: if still undefined -> "DEFAULT_BTN_INFO_TROPA")

So a new nation needs NO exe patch as long as <COUNTRY>_<TROOP>_BTN_INFO_TROPA keys exist in a loaded
UIDefs_BtnTropas.sb (make_icons.py generates them per nation).  This patch is only useful if one prefers the
original ARABE buttons (Especiales.tga) for some nations instead of generating their own art: it replaces the five
compares by a loop over a 0-terminated table of country-name strings in the int3 cave at VA 0x882A00.

    python tools/art/icons/btn_prefix_patch.py [--apply] [COUNTRY ...]
        prints the patch (file offset, old bytes, new bytes) and a disassembly of the cave;
        --apply writes build/icons/ImperialGlory_BtnPrefix.exe (a patched copy of build/ImperialGlory_ModNations.exe)
"""
import os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(ROOT, 'build', 'ImperialGlory_ModNations.exe')
DST = os.path.join(ROOT, 'build', 'icons', 'ImperialGlory_BtnPrefix.exe')
EXE_BASE = 0x400000                       # .text is mapped 1:1 (raw 0x1000 == VA 0x401000)

ORIGINAL_ARAB = ['EGIPTO', 'OTOMANO', 'TUNEZ', 'TRIPOLITANIA', 'MARRUECOS']
# nations whose troops use the Arab unit set and could reasonably share the ARABE buttons
DEFAULT_NEW = ['PERSIA', 'ARABIA', 'TURKESTAN', 'DURRANI', 'OMAN', 'INDEPENDENT', 'CHECHNYA', 'SAJONIA', 'HANNOVER']

HOOK = 0x5bcac2                           # push "EGIPTO" / mov edi,eax / call intern  (12 bytes, start of the chain)
BACK = 0x5bcb58                           # test bl,0x10: the release / "ARABE" code after the chain
INTERN, RELEASE = 0x530800, 0x530890      # FUN_00530800 intern(const char*) -> handle, FUN_00530890 release(handle)
CAVE, TABLE, STRINGS = 0x882a00, 0x882a80, 0x882b80
CAVE_END = 0x883000                       # the int3 run 0x882a00..0x883000 is free in ImperialGlory_ModNations.exe


def patch(src_path, names):
    d = bytearray(open(src_path, 'rb').read())
    changes = []

    def put(off, new, expect=None):
        old = bytes(d[off:off + len(new)])
        if expect is not None:
            assert old == expect, (hex(off), old.hex(), expect.hex())
        d[off:off + len(new)] = new
        changes.append((off, old, bytes(new)))

    assert set(d[CAVE - EXE_BASE:CAVE_END - EXE_BASE]) == {0xCC}, 'cave not free'
    strs, table, p = b'', b'', STRINGS
    for n in names:
        s = n.encode() + b'\0'
        table += struct.pack('<I', p); strs += s; p += len(s)
    table += struct.pack('<I', 0)
    assert TABLE + len(table) <= STRINGS and STRINGS + len(strs) <= CAVE_END

    code = bytearray(); labels = {}; fix = []

    def emit(b): code.extend(b)

    def here(): return CAVE + len(code)

    def rel32(target): return struct.pack('<i', target - (here() + 4))
    emit(b'\x8B\xF8')                                       # mov edi, eax          (edi = interned country name)
    emit(b'\x83\xC4\x04')                                   # add esp, 4            (drop the arg of the intern call)
    emit(b'\xC7\x44\x24\x14\x00\x00\x00\x00')               # mov [esp+0x14], 0     (no "EGIPTO" handle to release)
    emit(b'\xBD' + struct.pack('<I', TABLE))                # mov ebp, table
    labels['loop'] = here()
    emit(b'\x8B\x45\x00\x85\xC0')                           # mov eax,[ebp]; test eax,eax
    emit(b'\x0F\x84'); fix.append((len(code), 'nomatch')); emit(b'\0\0\0\0')   # jz nomatch
    emit(b'\x50\xE8'); emit(rel32(INTERN)); emit(b'\x83\xC4\x04')              # push eax; call intern; add esp,4
    emit(b'\x39\xF8\x0F\x94\xC3')                           # cmp eax, edi; sete bl
    emit(b'\x85\xC0\x74\x09')                               # test eax,eax; jz +9
    emit(b'\x50\xE8'); emit(rel32(RELEASE)); emit(b'\x83\xC4\x04')             # push eax; call release; add esp,4
    emit(b'\x84\xDB')                                       # test bl, bl
    emit(b'\x0F\x85'); fix.append((len(code), 'match')); emit(b'\0\0\0\0')     # jnz match
    emit(b'\x83\xC5\x04')                                   # add ebp, 4
    emit(b'\xE9'); emit(rel32(labels['loop']))              # jmp loop
    labels['match'] = here()
    emit(b'\xC6\x44\x24\x13\x01\xEB\x05')                   # mov byte [esp+0x13],1; jmp done   (-> "ARABE")
    labels['nomatch'] = here()
    emit(b'\xC6\x44\x24\x13\x00')                           # mov byte [esp+0x13],0             (-> own name)
    emit(b'\x31\xDB')                                       # done: xor ebx,ebx   (no pending handle releases)
    emit(b'\x8B\x6C\x24\x68')                               # mov ebp, [esp+0x68] (as the original match path)
    emit(b'\xE9'); emit(rel32(BACK))                        # jmp back
    for pos_, lab in fix:
        struct.pack_into('<i', code, pos_, labels[lab] - (CAVE + pos_ + 4))
    assert CAVE + len(code) <= TABLE
    put(CAVE - EXE_BASE, bytes(code))
    put(TABLE - EXE_BASE, table)
    put(STRINGS - EXE_BASE, strs)
    # hook: the 12 bytes 'push 0x8c4664; mov edi,eax; call 0x530800' become 'jmp cave' + int3 padding
    old = bytes.fromhex('6864468c00') + bytes.fromhex('8bf8') + b'\xE8' + struct.pack('<i', INTERN - (HOOK + 7 + 5))
    put(HOOK - EXE_BASE, b'\xE9' + struct.pack('<i', CAVE - (HOOK + 5)) + b'\xCC' * 7, old)
    return d, changes


def disasm(d, va, n):
    try:
        import capstone
    except ImportError:
        return ['(capstone not installed)']
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    off = va - EXE_BASE
    return ['%08x  %-24s %s %s' % (i.address, bytes(i.bytes).hex(), i.mnemonic, i.op_str) for i in md.disasm(bytes(d[off:off + n]), va)]


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    names = ORIGINAL_ARAB + (args or DEFAULT_NEW)
    d, changes = patch(SRC, names)
    print('countries routed to the ARABE buttons:', ' '.join(names))
    for off, old, new in changes:
        print('file 0x%06x (VA 0x%06x): %d bytes\n   old %s\n   new %s' % (off, off + EXE_BASE, len(new), old.hex(), new.hex()))
    print('\ncave disassembly:')
    print('\n'.join(disasm(d, CAVE, 0x80)))
    print('\nhook disassembly:')
    print('\n'.join(disasm(d, HOOK, 12)))
    if '--apply' in sys.argv:
        os.makedirs(os.path.dirname(DST), exist_ok=True)
        open(DST, 'wb').write(d)
        print('written', DST)

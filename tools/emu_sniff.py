#!/usr/bin/env python3
"""Run the resident content sniffer sub_030697e0(ext, handle) of a firmware image under Unicorn.

  emu_sniff.py FW.IMG EXT file...   ->  prints the extension the sniffer leaves for each file

The sniffer reads the first sectors through the function pointers at 0x03004538 (read) and
0x0300453c (seek), served here from the file; sub_03061da8 (yield) is stubbed.
"""
import struct
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_BLOCK
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from rknanofw import overlays                                     # noqa: E402

READ, SEEK, YIELD, RET, EXT, STACK = 0x03100000, 0x03100010, 0x03061da8, 0x03100020, 0x03100100, 0x03140000


def sniff(img, ext, path, codec=1):
    d = open(img, "rb").read()
    c, base, ents = overlays(d)
    cl, ce, cs, dl, de, ds, be, bs = ents[0]
    f = open(path, "rb").read()
    pos = [0]
    u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    u.mem_map(0x03000000, 0x00200000)
    u.mem_write(ce, c[cl - base:cl - base + cs])
    u.mem_write(de, c[dl - base:dl - base + ds])
    for a in (READ, SEEK, RET):
        u.mem_write(a, b"\x70\x47")                                  # bx lr
    u.mem_write(YIELD, b"\x70\x47")
    u.mem_write(0x03004538, struct.pack("<I", READ | 1))
    u.mem_write(0x0300453c, struct.pack("<I", SEEK | 1))
    u.mem_write(0x0304af7c, struct.pack("<I", codec))

    def rd(u, a, s, _):
        buf, n = u.reg_read(UC_ARM_REG_R0), u.reg_read(UC_ARM_REG_R1)
        blob = f[pos[0]:pos[0] + n]
        u.mem_write(buf, blob)
        pos[0] += len(blob)
        u.reg_write(UC_ARM_REG_R0, len(blob))

    def sk(u, a, s, _):
        pos[0] = u.reg_read(UC_ARM_REG_R0)
        u.reg_write(UC_ARM_REG_R0, 0)
    u.hook_add(UC_HOOK_BLOCK, rd, begin=READ, end=READ)
    u.hook_add(UC_HOOK_BLOCK, sk, begin=SEEK, end=SEEK)
    u.mem_write(EXT, ext.encode() + b"\0")
    u.reg_write(UC_ARM_REG_R0, EXT)
    u.reg_write(UC_ARM_REG_R1, 3)
    u.reg_write(UC_ARM_REG_SP, STACK)
    u.reg_write(UC_ARM_REG_LR, RET | 1)
    u.emu_start(0x030697e0 | 1, RET, count=50_000_000)
    return bytes(u.mem_read(EXT, 3)).decode("latin1")


if __name__ == "__main__":
    for p in sys.argv[3:]:
        print(f"{sniff(sys.argv[1], sys.argv[2], p)}  {p}")

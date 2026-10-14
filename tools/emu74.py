#!/usr/bin/env python3
"""Run the codec plug-in of overlay 74 *as stored in a firmware image* under Unicorn.

  emu74.py FW.IMG file.opus out.raw [--seconds N] [--seek MS seek.raw] [--stub-io]

The HiFi-core memory map is reproduced: code at 0, data at 0x01020000 (copied from the
image), runtime-zeroed BSS, garbage in the RAM the runtime does not clear, SP = 0x01022000.
CodecFunc[1] is called exactly like the runtime does. By default the runtime's own file layer
runs (FILE_OPS set up by 0x2940, 2 x 512-byte buffer during OPEN, resized by 0x29ba after it,
event flags at 0x0103cb18); only the requests to the main core (0x206 seek, 0x26c read) are
served from the .opus file. --stub-io replaces FILE_OPS by direct Python stubs instead. A stack watermark checks the 8 KB stack and the
parameter block below it; any unmapped access aborts the run. Only block hooks are used:
Unicorn 2.1 mis-executes Thumb IT blocks when code or memory-write hooks are installed.
"""
import struct
import sys
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_BLOCK
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from rknanofw import overlays                                     # noqa: E402

CODE, DATA, DATA_END = 0x0, 0x01020000, 0x01060000
STACK_TOP, STACK_FLOOR = 0x01022000, 0x01020090
BSS_ZERO = (0x010267c0, 0x01047632)                                # cleared by the runtime
FILE_OPS, FILE_HANDLE, FILE_SIZE = 0x010220e4, 0x01022108, 0x01022224
STUBS, RET = 0x0001F000, 0x0001F100
OUTV = 0x0105FE00                                                  # a1/a2 output words
import os
FILL = int(os.environ.get("EMU_FILL", "0xa5"), 0)

SUB = dict(GETBITRATE=3, GETSAMPLERATE=4, GETCHANNELS=5, GETLENGTH=6, GETTIME=7, OPEN=8,
           GETBUFFER=10, DECODE=12, SEEK=14, CLOSE=15, GETBPS=17)


RT_SEEK, RT_READ, RT_DELAY, RT_PRINTF = 0x206, 0x26c, 0xb6c, 0x902   # runtime -> system requests
FILEPOS = 0x01022228                                               # u32[h]: system-side file position
CODEC_TYPE = 0x01022214


class Emu:
    def __init__(self, img, opus):
        d = open(img, "rb").read()
        c, base, ents = overlays(d)
        cl, ce, cs, dl, de, ds, _, _ = ents[74]
        self.f = open(opus, "rb").read()
        self.pos = 0
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        u.mem_map(CODE, 0x20000)
        u.mem_map(DATA, DATA_END - DATA)
        u.mem_write(DATA, bytes([FILL]) * (DATA_END - DATA))          # RAM content is unknown
        u.mem_write(CODE, c[cl - base:cl - base + cs])
        u.mem_write(DATA, c[dl - base:dl - base + ds])
        u.mem_write(BSS_ZERO[0], bytes(BSS_ZERO[1] - BSS_ZERO[0]))
        if "--elf" in sys.argv:                                     # test an ELF without patching
            from rknanofw import elf_sections
            for nm, addr, blob in elf_sections(sys.argv[sys.argv.index("--elf") + 1]):
                u.mem_write(addr, blob)
        self.cf = struct.unpack("<I", u.mem_read(0x0102347c, 4))[0]
        u.mem_write(RET, b"\xfe\xe7")
        u.mem_write(FILE_HANDLE, b"\x03")
        u.mem_write(FILE_SIZE, struct.pack("<I", len(self.f)))
        self.runtime_io = "--stub-io" not in sys.argv
        if self.runtime_io:
            # The runtime's own FILE_OPS (double-buffered reader, event flags at 0x0103cb18) run
            # unchanged; only its two requests to the main core are served here.
            for a, fn in ((RT_SEEK, self._sys_seek), (RT_READ, self._sys_read),
                          (RT_DELAY, None), (RT_PRINTF, self._printf)):
                u.mem_write(a, b"\x70\x47")                          # bx lr
                if fn:
                    u.hook_add(UC_HOOK_BLOCK, fn, begin=a, end=a)
        else:
            # FILE_OPS: open, read, seek, tell, -, length, close, eof -> stubs (bx lr)
            names = ["open", "read", "seek", "tell", "none", "length", "close", "eof"]
            for i, n in enumerate(names):
                a = STUBS + 8 * i
                u.mem_write(a, b"\x70\x47")                          # bx lr
                u.mem_write(FILE_OPS + 4 * i, struct.pack("<I", a | 1))
                u.hook_add(UC_HOOK_BLOCK, self._stub(n), begin=a, end=a)  # no UC_HOOK_CODE: it breaks Thumb IT blocks
        # Stack watermark (a UC_HOOK_MEM_WRITE would also break Thumb IT blocks in Unicorn 2.1)
        self.param = bytes(u.mem_read(DATA, STACK_FLOOR - DATA))
        u.mem_write(STACK_FLOOR, b"\x5a" * (STACK_TOP - STACK_FLOOR))

    def _regs(self):
        return [self.u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]

    def _setpos(self, h, v):
        self.u.mem_write(FILEPOS + 4 * h, struct.pack("<I", v))

    def _sys_seek(self, u, addr, size, data):                     # 0x206(off, whence, h)
        off, whence, h = self._regs()
        h &= 0xff
        if whence != 0 or off > len(self.f):
            raise RuntimeError(f"system seek({off:#x}, {whence}, {h})")
        self.pos = off
        self._setpos(h, off)
        u.reg_write(UC_ARM_REG_R0, 0)
        if os.environ.get("EMU_TRACE"):
            print(f"  sys seek {off:#x}")

    def _sys_read(self, u, addr, size, data):                     # 0x26c(buf, size, h)
        buf, n, h = self._regs()
        h &= 0xff
        n = min(n, len(self.f) - self.pos)
        u.mem_write(buf, self.f[self.pos:self.pos + n])
        self.pos += n
        self._setpos(h, self.pos)
        u.reg_write(UC_ARM_REG_R0, n)
        if os.environ.get("EMU_TRACE"):
            print(f"  sys read {buf:#x} {n:#x} -> pos {self.pos:#x}")

    def _printf(self, u, addr, size, data):
        a = u.reg_read(UC_ARM_REG_R0)
        print("  [runtime]", bytes(u.mem_read(a, 64)).split(b"\0")[0].decode("latin1"))

    def fn(self, addr, *args):
        """Call a runtime function of module 74 (Thumb address without the low bit)."""
        u = self.u
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(r, v)
        u.reg_write(UC_ARM_REG_SP, STACK_TOP)
        u.reg_write(UC_ARM_REG_LR, RET | 1)
        u.emu_start(addr | 1, RET)
        return u.reg_read(UC_ARM_REG_R0)

    def rt_prepare(self):
        """Message 0x65 + main-loop case 1: codec type, reserve, 2 x 512-byte file buffer."""
        if not self.runtime_io:
            return
        self.u.mem_write(CODEC_TYPE, struct.pack("<I", 1))
        self._setpos(3, 0)
        self.fn(0x3c6, 1, 44100)
        self.fn(0x2940, 3, 0x15c00)

    def rt_after_open(self):
        """What the runtime does after a successful OPEN (0x17be..0x17cc)."""
        if not self.runtime_io:
            return
        self.fn(0x3c6, 1, 48000)
        self.fn(0x29ba, 3, struct.unpack("<I", self.u.mem_read(0x01026af8, 4))[0])

    def rt_idle(self):
        """Main loop: refill the drained file buffer when event 0x115 is set (0x18ac)."""
        if self.runtime_io and self.fn(0x2d4c, 0x115):
            self.fn(0x24ec, 3)

    def stack_report(self):
        st = bytes(self.u.mem_read(STACK_FLOOR, STACK_TOP - STACK_FLOOR))
        used = len(st) - next((i for i, b in enumerate(st) if b != 0x5A), len(st))
        intact = bytes(self.u.mem_read(DATA, STACK_FLOOR - DATA)) == self.param
        return used, intact

    def _stub(self, name):
        def cb(u, addr, size, data):
            r0, r1, r2 = (u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
            if r2 != 3 and name in ("read", "seek"):
                raise RuntimeError(f"{name}: bad handle {r2}")
            ret = 0
            if name == "read":
                n = min(r1, len(self.f) - self.pos)
                u.mem_write(r0, self.f[self.pos:self.pos + n])
                self.pos += n
                ret = n
            elif name == "seek":
                if r1 != 0 or r0 > len(self.f):
                    ret = 0xFFFFFFFF
                else:
                    self.pos = r0
            elif name == "length":
                ret = len(self.f)
            elif name == "tell":
                ret = self.pos
            else:
                raise RuntimeError(f"unexpected FILE_OPS call: {name}")
            if os.environ.get("EMU_TRACE"):
                print(f"  {name}(0x{r0:x}, 0x{r1:x}, {r2}) pos->{self.pos} = 0x{ret & 0xffffffff:x}")
            u.reg_write(UC_ARM_REG_R0, ret)
        return cb

    def call(self, subfn, a1=OUTV, a2=OUTV + 4, a3=0):
        u = self.u
        u.mem_write(OUTV, bytes(8))
        for r, v in ((UC_ARM_REG_R0, subfn), (UC_ARM_REG_R1, a1), (UC_ARM_REG_R2, a2),
                     (UC_ARM_REG_R3, a3), (UC_ARM_REG_SP, STACK_TOP), (UC_ARM_REG_LR, RET | 1)):
            u.reg_write(r, v)
        u.emu_start(self.cf, RET)
        return u.reg_read(UC_ARM_REG_R0)

    def word(self, i=0):
        return struct.unpack("<I", self.u.mem_read(OUTV + 4 * i, 4))[0]

    def get(self, name):
        self.call(SUB[name])
        return self.word()

    def buffer(self):
        self.call(SUB["GETBUFFER"])
        p, n = self.word(0), self.word(1)
        return bytes(self.u.mem_read(p, n * 4)), p


def play(e, out, max_frames):
    frames = 0
    pcm, p = e.buffer()
    ptrs = {p}
    while True:
        out.write(pcm)
        frames += len(pcm) // 4
        if max_frames and frames >= max_frames:
            break
        e.rt_idle()
        if e.call(SUB["DECODE"]) != 1:
            break
        pcm, p = e.buffer()
        ptrs.add(p)
    return frames, ptrs


def main():
    a = sys.argv
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 0
    e = Emu(a[1], a[2])
    print(f"CodecFunc[1] = 0x{e.cf:08x}")
    e.rt_prepare()
    if e.call(SUB["OPEN"]) != 1:
        sys.exit("OPEN failed")
    e.rt_after_open()
    print("rate", e.get("GETSAMPLERATE"), "ch", e.get("GETCHANNELS"), "bps", e.get("GETBPS"),
          "bitrate", e.get("GETBITRATE"), "length_ms", e.get("GETLENGTH"))
    with open(a[3], "wb") as out:
        frames, ptrs = play(e, out, int(secs * 48000))
    print(f"frames {frames} ({frames / 48000:.3f} s) time_ms {e.get('GETTIME')} "
          f"pcm buffers {[hex(x) for x in sorted(ptrs)]}")
    if "--seek" in a:
        ms = int(a[a.index("--seek") + 1])
        e.rt_idle()
        if e.call(SUB["SEEK"], a1=ms) != 1:
            sys.exit("SEEK failed")
        e.call(SUB["DECODE"])
        with open(a[a.index("--seek") + 2], "wb") as out:
            play(e, out, 48000 * 3)
        print(f"seek {ms} ms -> time_ms {e.get('GETTIME')}")
    print(f"CLOSE -> {e.call(SUB['CLOSE'], a1=1)}")
    used, intact = e.stack_report()
    print(f"stack high-water: {used} bytes (limit {STACK_TOP - STACK_FLOOR}), "
          f"parameter block {'intact' if intact else 'OVERWRITTEN'}")
    if not intact or used >= STACK_TOP - STACK_FLOOR:
        sys.exit("stack overflow")


if __name__ == "__main__":
    main()

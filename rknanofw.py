#!/usr/bin/env python3
"""Unpacker for Rockchip RKnano firmware images (SNOWSKY ECHO MINI, HIFIECxx.IMG).

Usage:
  rknanofw.py info    FW.IMG
  rknanofw.py extract FW.IMG OUTDIR      # raw parts, overlay ELFs, images, UI strings
  rknanofw.py crc     FW.IMG [--fix]     # verify / recompute trailing Rockchip CRC32
  rknanofw.py patch-opus FW.IMG opus74.elf OUT.IMG [--days N|--keep-date] [--marker TXT]  # WMA -> Ogg Opus
          [--vorbis vorbis77.elf]                 # + full-precision Vorbis in overlay 77
          [--ogg-clock-mp3]                       # Ogg Vorbis clock profiles = MP3's
  rknanofw.py redate  FW.IMG DAYS OUT.IMG  # shift build date (header + its copy), fix CRC

Format (reverse engineered from V3.9.0):
  0x000  u16 BCD year, u16 BCD month/day      (build date, also used as fw version)
  0x00c  u32 0x76543210, "Rockchip", "RKnano SDK 1.0" @0x30
  0x054  4 x {u32 offset, u32 length}         code images (only #4 @0x6c used)
  0x074  u32 count, 2 x {offset,length}       bitmap fonts (12px @0x78, 16px @0x80)
  0x0c8  u32 count, {offset,length}           codepage -> unicode tables
  0x0f4  u32 count, {offset,length}           multilingual UI text
  0x148  u32 count, {offset,length}           ROCK26IMAGERES image pack
  0x1f4  u32 firmware length (flash reserve), "RKnanoFW" @0x1f8
  0x200  code image: u32 load base (0x03050000), u32 n, n x overlay descriptors
         {codeLoad, codeExec, codeLen, dataLoad, dataExec, dataLen, bssExec, bssLen}
  EOF-4  u32 Rockchip CRC32 (poly 0x04C10DB7, init 0, MSB-first) of everything before
"""
import os
import struct
import sys

HDR_PARTS = [("code", 0x6C), ("font12", 0x78), ("font16", 0x80),
             ("codepage", 0xCC), ("uitext", 0xF8), ("images", 0x14C)]

# Overlay roles identified from strings / call sites (see REPORT.md)
OVERLAY_NAMES = {
    0: "resident_system", 1: "boot_fwcheck_update", 5: "browser_title", 9: "reboot_flag",
    10: "usb_msc", 11: "usb_core", 12: "usb_ctrl", 15: "mp3_parse_mad", 18: "id3_cover_ogg",
    22: "record_ui", 23: "fm_radio", 27: "picture_cover", 28: "record", 31: "media_library",
    32: "record2", 33: "audio_control", 34: "audio_file_open", 39: "file_browser", 40: "main_ui",
    42: "srv_mp3", 43: "srv_wma", 44: "srv_wma_empty", 51: "srv_aac", 52: "srv_wav", 53: "srv_ogg",
    54: "srv_flac", 55: "srv_alac", 56: "srv_ape", 57: "srv_dff", 58: "srv_dsf", 63: "recorder_wav",
    73: "codec_mp3", 74: "codec_wma", 75: "codec_aac_m4a", 76: "codec_wav", 77: "codec_ogg",
    78: "codec_flac", 79: "codec_alac", 80: "codec_ape", 81: "codec_dff_dst", 82: "codec_dsf",
    85: "dictionary",
}

_T = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04C10DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
    _T.append(c)


def rkcrc(data, crc=0):
    t = _T
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ t[((crc >> 24) ^ b) & 0xFF]
    return crc


def parts(d):
    out = {}
    for name, o in HDR_PARTS:
        out[name] = struct.unpack_from("<2I", d, o)   # {offset, length}
    return out


def overlays(d):
    off, size = parts(d)["code"]
    c = d[off:off + size]
    base, n = struct.unpack_from("<2I", c, 0)
    ents = [struct.unpack_from("<8I", c, 8 + 32 * i) for i in range(n)]
    return c, base, ents


def build_elf(c, base, ents, idxs, path):
    segs = []
    for i in idxs:
        cl, ce, cs, dl, de, ds, be, bs = ents[i]
        if cs:
            # HiFi-core codecs are written at 0x01000000 but execute at 0 (vector: SP 0x01022000)
            va = 0 if 0x01000000 <= ce < 0x01020000 else ce
            segs.append((va, c[cl - base:cl - base + cs], 5, 0))
        if ds:
            segs.append((de, c[dl - base:dl - base + ds], 6, 0))
        if bs:
            segs.append((be, b"", 6, bs))
    if not segs:
        return False
    entry = struct.unpack_from("<I", segs[0][1], 4)[0] if len(segs[0][1]) > 8 else segs[0][0] | 1
    off = 52 + 32 * len(segs)
    body, ph = b"", b""
    for va, data, fl, extra in segs:
        body += b"\0" * (-(off + len(body)) % 4)
        ph += struct.pack("<8I", 1, off + len(body), va, va, len(data), len(data) + extra, fl, 4)
        body += data
    eh = b"\x7fELF\x01\x01\x01" + b"\0" * 9 + struct.pack(
        "<HHIIIIIHHHHHH", 2, 40, 1, entry, 52, 0, 0x05000200, 52, 32, len(segs), 40, 0, 0)
    with open(path, "wb") as f:
        f.write(eh + ph + body)
    return True


def extract_images(d, outdir):
    from PIL import Image
    off, size = parts(d)["images"]
    r = d[off:off + size]
    os.makedirs(outdir, exist_ok=True)
    n = struct.unpack_from("<I", r, 16)[0]
    for i in range(n):
        w, h, x, y, sz, o = struct.unpack_from("<HHHHII", r, 32 + 16 * i)
        if sz != w * h * 2:
            continue
        px = struct.unpack(">%dH" % (w * h), r[o:o + sz])  # RGB565 big-endian
        im = Image.new("RGB", (w, h))
        im.putdata([((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31) for v in px])
        im.save(os.path.join(outdir, f"img_{i:04d}_{w}x{h}_at{x}_{y}.png"))
    return n


def extract_text(d, path):
    off, size = parts(d)["uitext"]
    m = d[off:off + size]
    nl, start = struct.unpack_from("<HH", m, 0)
    offs = [start] + list(struct.unpack_from("<%dI" % (nl - 1), m, 6))
    rec = 258
    per = (offs[1] - offs[0]) // rec
    with open(path, "w", encoding="utf-8") as f:
        f.write("lang\tid\ttext\n")
        for li, s in enumerate(offs):
            for k in range(per):
                t = m[s + k * rec + 0x3A:s + (k + 1) * rec].decode("utf-16le", "replace").split("\0")[0]
                f.write(f"{li}\t{k}\t{t}\n")
    return nl, per


# ---------------------------------------------------------------------------
# Opus patch: replace the WMA decoder (overlay 74) by opus/build/arm/opus74.elf
# ---------------------------------------------------------------------------
OPUS_OVL = 74
# Areas of overlay 74 freed by removing the WMA library (HiFi view), see REPORT.md section 9
OPUS_FREE = [(0x00002ec4, 0x00010138), (0x000110a4, 0x00012800), (0x00012858, 0x000162c0),
             (0x0102347c, 0x010267c0)]
EXT_OLD, EXT_NEW = b"MP1MP2MP3WMAWAV", b"MP1MP2MP3OPUWAV"
# Optional full-precision Vorbis decoder: replaces the Rockchip Tremor build (_LOW_ACCURACY_) of
# overlay 77 by vorbis/build/arm/vorbis77.elf. Freed areas (HiFi view, docs/REPORT.md section 20):
# library code, library data (zeros, then tables); kept for the runtime: 0x01029888-0x010298a0
# (PCM buffer pointers at 0x01029898) and 0x0102d148-0x0102d184 (variables, CodecFunc table).
VORBIS_OVL = 77
VORBIS_FREE = [(0x000029d0, 0x0000e054), (0x01023480, 0x01029888), (0x010298a0, 0x0102d148),
               (0x0102d16c, 0x0102d170)]                  # CodecFunc[CODEC_OGG]
# Resident content sniffer sub_030697e0 (run before playback) rewrites the extension from the
# file header: "OggS" -> "OGG", which sends .opus files to the Vorbis codec ("Format Not
# Supported!"). The "OggS" case at 0x03069cd2 is replaced: if byte 0x1d of the page is 'p'
# ("OpusHead") write "OPU", otherwise write "OGG" as before. The extension must be written:
# the cover extractor (overlay 18, sub_030814de) passes an uninitialised buffer.
#   ldrb r0,[r4,#1]; cmp r0,#'g'; bne 0x3069d14; movs r0,#'O'; strb r0,[r5]
#   ldrb r1,[r4,#0x1d]; movs r0,#'G'; cmp r1,#'p'; bne 0x3069d02   ("GG" tail of the DFF case)
#   movs r0,#'P'; strb r0,[r5,#1]; movs r0,#'U'; b 0x3069d36         (3rd-letter tail)
SNIFF_ADDR = 0x03069cd2
SNIFF_OLD = bytes.fromhex("6078672801bfa0786728e078532818d14f2028704720687024e0")
SNIFF_NEW = bytes.fromhex("607867281dd14f202870617f472070290ed1502068705520" "24e0")
# Other code patches: (overlay, exec address, original bytes, new bytes, description).
OVL_PATCHES = [
    # Overlay 27 (playing screen) builds "WMA|48KHZ|16bit|0126kbps" from CurrentCodec in two
    # twin functions (0x0307af7e, 0x0307bca8). Case 1 wrote "WMA"; it now jumps to 3 unused
    # branches just before (dead code) and writes the 4 letters "OPUS" (sb = 'P', r5 = sp).
    (27, 0x0307afd6, "74d0", "71d0", "label case 1 -> 0x0307b0bc"),
    (27, 0x0307b0bc, "01e007e00fe0adf80070adf80260adf80440aae7",
                     "4f232b80a5f802905523ab805323eb800423abe7", "label 'OPUS' (screen 1)"),
    (27, 0x0307bd32, "74d0", "71d0", "label case 1 -> 0x0307be18"),
    (27, 0x0307be18, "01e007e00fe0adf80070adf80260adf80440aae7",
                     "4f232b80a5f802905523ab805323eb800423abe7", "label 'OPUS' (screen 2)"),
    # Tags. The resident dispatcher sub_0306df9c(handle, out, ext) picks a tag reader from the
    # extension index with a TBB table; entry 4 (WMA, now OPU) pointed to the ASF readers.
    # It now points to the Ogg case (0x0306e0ce -> sub_0306bf94).
    (0, 0x0306dffa, "18", "6c", "tag dispatcher: OPU -> Ogg reader"),
    # sub_0306bf94 accepted only "vorbis" (7 bytes) before the Vorbis comment parser
    # sub_0306bd02. Rewritten 0x0306c052..0x0306c0bc (same size, same paths) to also accept
    # "OpusTags": skip the 8th byte and pass packet length - 8. Source: opus/patches/oggtags.s
    (0, 0x0306c052, "9df80001032805d1062276a144a8e9f797fc98b100243a460121e01fedf710ff9df804110020002904dd2a5c401c14448142fadc3a460121204622e000219df804210846002a09dd2b5cff2b02d0d8b2014403e0ff31401c9042f5dbcb1f324641463846fff724fe12e0",
                    "9df8000107244f2824d0032819d1062275a144a8e9f794fc98b900219df8042108462b5cff2b01d0194403e0ff3101309042f6db0b1b324641463846fff738fe26e03a4601210620c043edf7f9fe9df804110ae09df813015428f2d1012001213a46edf7edfe0824d7e7", "Ogg tag reader: accept OpusTags"),
    # Cover art (overlay 18, sub_030814de): TBB on extension index - 3; entry 1 (WMA, now OPU)
    # pointed to the MP4 case. It now points to the Ogg case (0x0308168e).
    (18, 0x03081517, "4c", "bc", "cover dispatcher: OPU -> Ogg reader"),
    # Same "vorbis"-only check in the Ogg cover reader before the picture parser
    # sub_03080f3a; rewritten 0x03081a72..0x03081adc. Source: opus/patches/oggcover.s
    (18, 0x03081a72, "9df81c01032805d106224aa144a8d3f787ff98b100243a460121e01fd8f700fa9df808110020002904dd2a5c401c14448142fadc3a460121204622e000219df808210846002a09dd2b5cff2b02d0d8b2014403e0ff31401c9042f5dbca1f234631463846fff730fae7e6",
                     "9df81c014f2823d0032818d1062249a144a8d3f785ff90b9072041429df8082100202b5cc9180130ff2b01d19042f8db0a46234631463846fff746fafde63a4601210620c043d8f7ebf99df808110ce09df813015428f2d1012001213a46d8f7dff90820d9e700bf00bf", "Ogg cover reader: accept OpusTags"),
]


def elf_sections(path):
    """Allocated PROGBITS sections of an ELF32 little-endian file: [(name, addr, bytes)]."""
    e = open(path, "rb").read()
    shoff, = struct.unpack_from("<I", e, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", e, 0x2e)
    sh = [struct.unpack_from("<10I", e, shoff + i * shentsize) for i in range(shnum)]
    strtab = sh[shstrndx]
    out = []
    for name, typ, flags, addr, off, size, *_ in sh:
        if typ == 1 and flags & 2 and size:                    # PROGBITS + SHF_ALLOC
            nm = e[strtab[4] + name:].split(b"\0")[0].decode()
            out.append((nm, addr, e[off:off + size]))
    return out


# The loader compares the 0x200-byte header with its copy at offset "fw length" (0x1f4)
# ("fw1 compare error"): both must always be changed together.
def HDR_COPY(d):
    return struct.unpack_from("<I", d, 0x1f4)[0]


def set_date(d, days):
    """Shift the BCD build date (u16 year, u8 day, u8 month) in the header and its copy.
    The fw1/fw2 check (overlay 1, 0x0307b1b4) compares (year << 16) | (month << 8 | day), so a
    month or year change keeps the order."""
    import datetime
    bcd = lambda v: int("%x" % v)
    y, day, month = struct.unpack_from("<HBB", d, 0)
    dt = datetime.date(bcd(y), bcd(month), bcd(day)) + datetime.timedelta(days=days)
    for base in (0, HDR_COPY(d)):
        struct.pack_into("<HBB", d, base, int(str(dt.year), 16), int("%02d" % dt.day, 16),
                         int("%02d" % dt.month, 16))


UI_FORMAT_ERR = 68                                            # "Format Not Supported!" (event 0x55)


def mark_text(d, sid, suffix, allowed):
    """Append suffix to UI string sid in every language (proves which image is running)."""
    off, size = parts(bytes(d))["uitext"]
    nl, start = struct.unpack_from("<HH", d, off)
    offs = [start] + list(struct.unpack_from("<%dI" % (nl - 1), d, off + 6))
    for s in offs:
        a = off + s + sid * 258 + 0x3A
        t = bytes(d[a:a + 258 - 0x3A]).decode("utf-16le").split("\0")[0]
        new = (t.rstrip() + suffix).encode("utf-16le") + b"\0\0"
        if len(new) > 258 - 0x3A:
            sys.exit(f"UI string {sid} too long after marking")
        d[a:a + len(new)] = new
        allowed.update(range(a, a + len(new)))


def write_module(d, ents, base, ovl, shape, free, elf, cf_off, allowed, label):
    """Wipe the freed areas of HiFi overlay 'ovl' and write the sections of 'elf' into them."""
    cl, ce, cs, dl, de, ds, _, _ = ents[ovl]
    if (ce, cs, de, ds) != shape:
        sys.exit(f"overlay {ovl} does not look like the V3.9.0 module")
    code_off = 0x200 + cl - base                              # file offset of HiFi address 0
    data_off = 0x200 + dl - base                              # file offset of 0x01020000

    def foff(addr, n):
        for lo, hi in free:
            if lo <= addr and addr + n <= hi:
                return (code_off + addr) if addr < 0x01000000 else (data_off + addr - de)
        sys.exit(f"section at 0x{addr:08x}+0x{n:x} outside the freed areas of overlay {ovl}")

    for lo, hi in free:                                       # wipe the old library first
        o = foff(lo, hi - lo)
        d[o:o + hi - lo] = bytes(hi - lo)
        allowed.update(range(o, o + hi - lo))
    for nm, addr, blob in elf_sections(elf):
        o = foff(addr, len(blob))
        d[o:o + len(blob)] = blob
        print(f"  {nm:10s} 0x{addr:08x} +0x{len(blob):05x} -> file 0x{o:08x}")
    cf = struct.unpack_from("<I", d, data_off + cf_off)[0]
    if cf & 1 == 0 or not free[0][0] <= cf & ~1 < free[0][1]:
        sys.exit(f"{label} = 0x{cf:08x} is not a Thumb code pointer into the new code")
    print(f"  {label} = 0x{cf:08x}")


# Clock profiles (resident code): FREQ_EnterModule(id) sums the {PLL, sys core, sys HCLK, PCLK,
# HiFi core, HiFi HCLK} rows of all active modules (table of 36 x 7 words, row = {id, 6 x Hz}).
# Ogg Vorbis selects ids 14-17 (only used by the OGG enter/exit selectors of overlays 33/34; id 18
# is shared with APE and left alone). --ogg-clock-mp3 gives them the MP3 row (id 5).
FREQ_TABLE = 0x0307627c
FREQ_OGG_IDS = (14, 15, 16, 17)
FREQ_OGG_OLD = {14: (300, 80, 80, 80, 400, 400), 15: (300, 80, 80, 80, 400, 400),
                16: (300, 80, 80, 80, 400, 400), 17: (480, 200, 200, 80, 480, 480)}
FREQ_MP3 = (300, 150, 150, 75, 300, 300)


def patch_ogg_clock(d, ents, base, allowed):
    r = ents[0]
    for i in FREQ_OGG_IDS:
        o = 0x200 + r[0] - base + FREQ_TABLE + 28 * i - r[1]
        row = struct.unpack_from("<7I", d, o)
        if row != (i,) + tuple(m * 1000000 for m in FREQ_OGG_OLD[i]):
            sys.exit(f"clock profile {i} does not match V3.9.0: {row}")
        struct.pack_into("<6I", d, o + 4, *(m * 1000000 for m in FREQ_MP3))
        allowed.update(range(o + 4, o + 28))
    print(f"  clock profiles {FREQ_OGG_IDS} (Ogg Vorbis) = MP3 {FREQ_MP3} MHz")


def patch_opus(src, elf, dst, days=1, marker=None, vorbis=None, ogg_clock_mp3=False):
    d = bytearray(open(src, "rb").read())
    if rkcrc(d[:-4]) != struct.unpack("<I", d[-4:])[0]:
        sys.exit("input CRC mismatch")
    c, base, ents = overlays(bytes(d))
    allowed = set()
    write_module(d, ents, base, OPUS_OVL, (0x01000000, 0x162c0, 0x01020000, 0x67c0), OPUS_FREE,
                 elf, 0x347c, allowed, "CodecFunc[WMA]")
    if vorbis:
        write_module(d, ents, base, VORBIS_OVL, (0x01000000, 0xf5d8, 0x01020000, 0xd184),
                     VORBIS_FREE, vorbis, 0xd16c, allowed, "CodecFunc[OGG]")
    if ogg_clock_mp3:
        patch_ogg_clock(d, ents, base, allowed)

    hits = [i for i in range(len(d)) if d.startswith(EXT_OLD, i)]
    if len(hits) != 5:
        sys.exit(f"expected 5 extension tables, found {len(hits)}")
    for i in hits:
        d[i:i + len(EXT_NEW)] = EXT_NEW
        allowed.update(range(i, i + len(EXT_NEW)))
    print(f"  extension tables WMA->OPU at {', '.join(hex(i) for i in hits)}")

    r = ents[0]                                               # resident code
    o = 0x200 + r[0] - base + SNIFF_ADDR - r[1]
    if bytes(d[o:o + len(SNIFF_OLD)]) != SNIFF_OLD:
        sys.exit("content sniffer at 0x03069cd2 does not match V3.9.0")
    d[o:o + len(SNIFF_NEW)] = SNIFF_NEW
    allowed.update(range(o, o + len(SNIFF_NEW)))
    print(f"  content sniffer: OggS+OpusHead -> OPU, other OggS -> OGG (file 0x{o:x})")

    for ovl, addr, old, new, what in OVL_PATCHES:
        cl, ce, cn = ents[ovl][:3]
        o = 0x200 + cl - base + addr - ce
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        if not ce <= addr <= addr + len(old) <= ce + cn or bytes(d[o:o + len(old)]) != old:
            sys.exit(f"overlay {ovl} at 0x{addr:08x} does not match V3.9.0 ({what})")
        d[o:o + len(new)] = new
        allowed.update(range(o, o + len(new)))
        print(f"  overlay {ovl} 0x{addr:08x}: {what}")

    if marker:
        mark_text(d, UI_FORMAT_ERR, marker, allowed)
        print(f"  UI string {UI_FORMAT_ERR} marked with {marker!r}")

    if days:
        set_date(d, days)
        allowed.update(range(0, 4))
        allowed.update(range(HDR_COPY(d), HDR_COPY(d) + 4))
    if d[:0x200] != d[HDR_COPY(d):HDR_COPY(d) + 0x200]:
        sys.exit("header copy at the end of the firmware does not match the header")
    d[-4:] = struct.pack("<I", rkcrc(bytes(d[:-4])))
    allowed.update(range(len(d) - 4, len(d)))

    orig = open(src, "rb").read()
    bad = [i for i in range(len(d)) if d[i] != orig[i] and i not in allowed]
    if bad:
        sys.exit(f"{len(bad)} bytes changed outside the allowed areas, first at 0x{bad[0]:x}")
    open(dst, "wb").write(d)
    y, md = struct.unpack_from("<HH", d, 0)
    print(f"wrote {dst}: {sum(1 for i in range(len(d)) if d[i] != orig[i])} bytes changed, "
          f"date {y:04x}-{md >> 8:02x}-{md & 0xff:02x}, CRC 0x{rkcrc(bytes(d[:-4])):08x}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, fw = sys.argv[1], sys.argv[2]
    if cmd == "redate":                                       # rknanofw.py redate IN DAYS OUT
        d = bytearray(open(fw, "rb").read())
        set_date(d, int(sys.argv[3]))
        d[-4:] = struct.pack("<I", rkcrc(bytes(d[:-4])))
        open(sys.argv[4], "wb").write(d)
        print(f"wrote {sys.argv[4]}: date {struct.unpack_from('<H', d, 0)[0]:04x}-"
              f"{d[3]:02x}-{d[2]:02x}, CRC 0x{rkcrc(bytes(d[:-4])):08x}")
        return
    if cmd == "patch-opus":
        a = sys.argv
        patch_opus(fw, a[3], a[4], 0 if "--keep-date" in a else int(a[a.index("--days") + 1]) if "--days" in a else 1,
                   a[a.index("--marker") + 1] if "--marker" in a else None,
                   a[a.index("--vorbis") + 1] if "--vorbis" in a else None, "--ogg-clock-mp3" in a)
        return
    d = open(fw, "rb").read()
    if cmd == "crc":
        calc, stored = rkcrc(d[:-4]), struct.unpack("<I", d[-4:])[0]
        print(f"stored 0x{stored:08x} computed 0x{calc:08x} {'OK' if calc == stored else 'MISMATCH'}")
        if "--fix" in sys.argv and calc != stored:
            open(fw, "wb").write(d[:-4] + struct.pack("<I", calc))
            print("fixed")
        return
    y, md = struct.unpack_from("<HH", d, 0)
    print(f"build date {y:04x}-{md >> 8:02x}-{md & 0xff:02x}  fw length 0x{struct.unpack_from('<I', d, 0x1f4)[0]:x}")
    for k, (o, s) in parts(d).items():
        print(f"  {k:9s} off 0x{o:08x} len 0x{s:08x}")
    c, base, ents = overlays(d)
    print(f"overlay table: base 0x{base:08x}, {len(ents)} entries")
    for i, e in enumerate(ents):
        if e[2] or e[5]:
            print("  %2d %-20s code X%08x+%-6x data X%08x+%-5x bss X%08x+%x" % (
                i, OVERLAY_NAMES.get(i, ""), e[1], e[2], e[4], e[5], e[6], e[7]))
    if cmd != "extract":
        return
    out = sys.argv[3]
    os.makedirs(os.path.join(out, "parts"), exist_ok=True)
    for k, (o, s) in parts(d).items():
        open(os.path.join(out, "parts", k + ".bin"), "wb").write(d[o:o + s])
    os.makedirs(os.path.join(out, "elf"), exist_ok=True)
    for i, e in enumerate(ents):
        if not e[2] or e[1] == 0:          # empty or pure data table (exec 0)
            continue
        idx = [i] if i in (0,) or e[1] >= 0x01000000 and e[1] < 0x02000000 else [0, i]
        build_elf(c, base, ents, idx, os.path.join(out, "elf", f"ovl{i:02d}_{OVERLAY_NAMES.get(i, 'module')}.elf"))
    print("UI text:", extract_text(d, os.path.join(out, "ui_strings.tsv")))
    try:
        print("images:", extract_images(d, os.path.join(out, "images")))
    except ImportError:
        print("Pillow missing: images skipped")


if __name__ == "__main__":
    main()

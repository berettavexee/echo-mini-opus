#!/usr/bin/env python3
"""Apply / create an ECHO MINI firmware binary patch (no firmware content is distributed).

  apply_patch.py apply  HIFIEC39.IMG HIFIEC50.ecpatch OUT.IMG
  apply_patch.py create ORIGINAL.IMG PATCHED.IMG OUT.ecpatch

Format "ECPATCH1": magic, SHA-256 of the input, SHA-256 of the output, output size (u32),
record count (u32), then records (offset u32, length u32, new bytes). Only the bytes that
differ are stored; both hashes are checked, so the patch only applies to the exact
original image and always yields the exact expected result.
"""
import hashlib
import struct
import sys

MAGIC = b"ECPATCH1"


def create(src, dst, out):
    a, b = open(src, "rb").read(), open(dst, "rb").read()
    assert len(a) == len(b), "images must have the same size"
    recs, i = [], 0
    while i < len(a):
        if a[i] != b[i]:
            j = i
            while j < len(a) and a[j] != b[j]:
                j += 1
            recs.append((i, b[i:j]))
            i = j
        else:
            i += 1
    with open(out, "wb") as f:
        f.write(MAGIC + hashlib.sha256(a).digest() + hashlib.sha256(b).digest())
        f.write(struct.pack("<II", len(b), len(recs)))
        for off, data in recs:
            f.write(struct.pack("<II", off, len(data)) + data)
    print(f"{out}: {len(recs)} records, {sum(len(d) for _, d in recs)} bytes")


def apply(src, patch, out):
    p = open(patch, "rb").read()
    if p[:8] != MAGIC:
        sys.exit("not an ECPATCH1 file")
    h_in, h_out = p[8:40], p[40:72]
    size, n = struct.unpack_from("<II", p, 72)
    d = bytearray(open(src, "rb").read())
    if hashlib.sha256(d).digest() != h_in:
        sys.exit("input image does not match (expected the original HIFIEC39.IMG, V3.9.0, 8 GB model)")
    pos = 80
    for _ in range(n):
        off, ln = struct.unpack_from("<II", p, pos)
        d[off:off + ln] = p[pos + 8:pos + 8 + ln]
        pos += 8 + ln
    if len(d) != size or hashlib.sha256(d).digest() != h_out:
        sys.exit("result hash mismatch, nothing written")
    open(out, "wb").write(d)
    print(f"wrote {out} (SHA-256 {h_out.hex()})")


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("apply", "create"):
        sys.exit(__doc__)
    {"apply": apply, "create": create}[sys.argv[1]](*sys.argv[2:])

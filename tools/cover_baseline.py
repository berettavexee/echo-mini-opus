#!/usr/bin/env python3
"""Re-encode progressive JPEG covers of .ogg files as baseline JPEG.

The ECHO MINI firmware does not display progressive JPEG (SOF2) covers.
Only the METADATA_BLOCK_PICTURE comments are rewritten; audio and other
tags are kept. Dry run by default; pass --apply to modify the files.

    python3 cover_baseline.py DIR_OR_FILE... [--apply] [--quality 92]
"""
import argparse, base64, io, os, sys
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import Picture
from PIL import Image


def sof(data):
    """Return the JPEG SOF marker (0xC0 baseline, 0xC2 progressive) or None."""
    if data[:2] != b'\xff\xd8':
        return None
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        m = data[i + 1]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            return m
        if m == 0xDA:
            break
        i += 2 + int.from_bytes(data[i + 2:i + 4], 'big')
    return None


def fix(path, apply, quality):
    f = OggVorbis(path)
    blocks = f.get('metadata_block_picture', [])
    out, changed = [], 0
    for b in blocks:
        p = Picture(base64.b64decode(b))
        if sof(p.data) == 0xC2:
            im = Image.open(io.BytesIO(p.data))
            if im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=quality, progressive=False,
                    optimize=True, subsampling='4:2:0')
            assert sof(buf.getvalue()) == 0xC0
            p.data, p.mime = buf.getvalue(), 'image/jpeg'
            p.width, p.height = im.size
            changed += 1
            b = base64.b64encode(p.write()).decode('ascii')
        out.append(b)
    if changed:
        print(('FIXED ' if apply else 'would fix ') + path)
        if apply:
            f['metadata_block_picture'] = out
            f.save()
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--quality', type=int, default=92)
    a = ap.parse_args()
    n = 0
    for root in a.paths:
        files = [root] if os.path.isfile(root) else [
            os.path.join(d, x) for d, _, xs in os.walk(root) for x in sorted(xs)]
        for path in files:
            if path.lower().endswith('.ogg'):
                try:
                    n += fix(path, a.apply, a.quality)
                except Exception as e:
                    print(f'ERROR {path}: {e}', file=sys.stderr)
    print(f'{n} cover(s) {"converted" if a.apply else "to convert (dry run, add --apply)"}')


if __name__ == '__main__':
    main()

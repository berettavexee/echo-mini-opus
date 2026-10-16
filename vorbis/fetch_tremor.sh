#!/bin/sh
# Fetch Tremor (Xiph integer Vorbis decoder, BSD), branch lowmem at 89a7534 (2019-08-09),
# then apply the player patch (floor 0 compiled out, header scratch buffers on the heap,
# CLIP_TO_15 as one ssat) into tremor-lowmem/.
set -e
cd "$(dirname "$0")"
[ -d tremor-lowmem ] && { echo "tremor-lowmem already present"; exit 0; }
git clone -q https://gitlab.xiph.org/xiph/tremor.git tremor-lowmem
git -C tremor-lowmem checkout -q 89a7534
patch -s -d tremor-lowmem -p1 < patches/tremor-echo.diff
echo "ready: tremor-lowmem (89a7534 + patches/tremor-echo.diff)"

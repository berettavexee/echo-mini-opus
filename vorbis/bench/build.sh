#!/bin/bash
# build.sh NAME "DEFS" -> out/NAME/lib objs ; run.sh NAME file.ogg
set -e
B=$(cd $(dirname $0) && pwd); T=$B/../tremor-lowmem; OUT=$B/out/$1; mkdir -p $OUT
CF="-mcpu=cortex-m3 -mthumb -Os -ffunction-sections -fdata-sections -w -I$T $2"
for f in bitwise codebook dsp floor0 floor1 floor_lookup framing info mapping0 mdct misc res012 vorbisfile; do arm-none-eabi-gcc $CF -c $T/$f.c -o $OUT/$f.o & done; wait
arm-none-eabi-gcc $CF -DBENCH_SECONDS=${BENCH_SECONDS:-30} -c $B/vbench.c -o $OUT/vbench.o
echo "$2" > $OUT/defs

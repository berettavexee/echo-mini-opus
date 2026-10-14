#!/bin/bash
# prof.sh NAME file.opus SECONDS -> per-function instruction profile
B=$(cd $(dirname $0) && pwd); P=$(cd $B/../../opus && pwd); OUT=$B/out/$1; F="$2"; T=$(mktemp -d -p $B)
D="-DOPUS_BUILD -DFIXED_POINT -DCUSTOM_SUPPORT -I$B/src/include -I$P/port -I$P"
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -Os $D -DBENCH_SECONDS=$3 -w -c $P/bench/bench_main.c -o $T/bm.o
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -DOPUS_FILE="\"$F\"" -c "$P/bench/incbin.S" -o $T/inc.o
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -T "$P/bench/bench.ld" \
  -o $T/b.elf $(cat $OUT/lib.list) $OUT/opus_codec_bench.o $OUT/rt.o $T/bm.o $T/inc.o -lgcc
timeout 900 qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none \
  -semihosting-config enable=on,target=native -icount shift=0 -kernel $T/b.elf -d in_asm,exec,nochain -D $T/log >/dev/null
arm-none-eabi-nm -n --defined-only $T/b.elf | awk '$2~/[tT]/{print $1,$3}' > $T/syms
python3 $B/prof.py $T/log $T/syms
rm -rf $T

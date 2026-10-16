#!/bin/bash
# run.sh NAME file.ogg [dump.raw]
B=$(cd $(dirname $0) && pwd); OUT=$B/out/$1; T=$(mktemp -d -p $B)
CF="-mcpu=cortex-m3 -mthumb -Os -ffunction-sections -fdata-sections -w -I$B/../tremor-lowmem $(cat $OUT/defs)"
VB=$OUT/vbench.o
if [ -n "$3" ]; then arm-none-eabi-gcc $CF -DBENCH_SECONDS=${BENCH_SECONDS:-30} -DBENCH_DUMP="\"$3\"" -c $B/vbench.c -o $T/vb.o; VB=$T/vb.o; fi
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -DOGG_FILE="\"$2\"" -c $B/incbin.S -o $T/inc.o
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -T $B/bench.ld -o $T/b.elf $OUT/[a-uw-z]*.o $OUT/vorbisfile.o $VB $T/inc.o -lgcc 2>&1 | grep -v "^$" | head -5
timeout 900 qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none -semihosting-config enable=on,target=native -icount shift=0 -kernel $T/b.elf
rm -rf $T

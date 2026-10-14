#!/bin/bash
# bench.sh NAME file.opus -> prints bench line
B=$(cd $(dirname $0) && pwd); P=$(cd $B/../../opus && pwd); OUT=$B/out/$1; F="$2"; T=$(mktemp -d -p $B)
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -DOPUS_FILE="\"$F\"" -c "$P/bench/incbin.S" -o $T/inc.o
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -T "$P/bench/bench.ld" \
  -o $T/b.elf $(cat $OUT/lib.list) $OUT/opus_codec_bench.o $OUT/rt.o $OUT/bench_main.o $T/inc.o -lgcc
timeout 600 qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none \
  -semihosting-config enable=on,target=native -icount shift=0 -kernel $T/b.elf
rm -rf $T

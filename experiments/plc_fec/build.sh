#!/bin/bash
# build.sh NAME "EXTRA DEFS"  -> out/NAME/{opus74.elf,lib objs}
set -e
B=$(cd $(dirname $0) && pwd); P=$(cd $B/../../opus && pwd); SRC=$B/src
# patched copy of libopus: src = opus/opus-1.5.2 + no_plc_fec.diff (macros ECHO_NO_FEC, ECHO_NO_PLC, ECHO_DEC48K_ONLY)
[ -d $SRC ] || { cp -r $P/opus-1.5.2 $SRC && patch -d $SRC -p1 < $B/no_plc_fec.diff; }
 OUT=$B/out/$1; EXTRA="$2"
mkdir -p $OUT
cd $SRC
CELT=$(make -s -f - print <<<'include celt_sources.mk
include silk_sources.mk
include opus_sources.mk
print: ; @echo $(CELT_SOURCES) $(SILK_SOURCES) $(SILK_SOURCES_FIXED) $(OPUS_SOURCES)')
DEFS="-DOPUS_BUILD -DFIXED_POINT -DDISABLE_FLOAT_API -DNONTHREADSAFE_PSEUDOSTACK -DCUSTOM_SUPPORT -DGLOBAL_STACK_SIZE=16384 -DDEC_MEM_SIZE=26624 $EXTRA"
INCS="-I$SRC/include -I$SRC/celt -I$SRC/silk -I$SRC/silk/fixed -I$SRC -I$P/port -I$P"
CF="-mcpu=cortex-m3 -mthumb -Os -std=gnu99 -ffunction-sections -fdata-sections -fno-common $DEFS $INCS -w"
echo "$CELT" | tr ' ' '\n' | xargs -P16 -I{} sh -c 'mkdir -p $(dirname '$OUT'/{}); arm-none-eabi-gcc '"$CF"' -c {} -o '$OUT'/{}.o'
arm-none-eabi-gcc $CF -c "$P/port/opus_codec.c" -o $OUT/opus_codec.o
arm-none-eabi-gcc $CF -DHOST_TEST -c "$P/port/opus_codec.c" -o $OUT/opus_codec_bench.o
arm-none-eabi-gcc $CF -c "$P/port/rt.c" -o $OUT/rt.o
arm-none-eabi-gcc $CF -DBENCH_SECONDS=${BENCH_SECONDS:-30} -c "$P/bench/bench_main.c" -o $OUT/bench_main.o
LIB=$(echo "$CELT" | tr ' ' '\n' | sed "s|^|$OUT/|;s|$|.o|")
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -Wl,--enable-non-contiguous-regions \
  -Wl,-Map=$OUT/opus74.map -T "$P/port/echomini74.ld" -Wl,--entry=OpusCodec -o $OUT/opus74.elf $LIB $OUT/opus_codec.o $OUT/rt.o -lgcc
echo "$LIB" > $OUT/lib.list
arm-none-eabi-size -A $OUT/opus74.elf | awk '/text1|text2|rodata3|rodataD|\.bss|noinit/{print "  "$1, $2}'

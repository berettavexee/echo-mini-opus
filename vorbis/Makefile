# Full-precision Ogg Vorbis plug-in for the ECHO MINI HiFi core (module 77, Rockchip Tremor replaced).
#   ./fetch_tremor.sh                      Tremor lowmem 89a7534 + patches/tremor-echo.diff
# Tremor's own Ogg layer (framing.c, vorbisfile.c) is not used: port77/vorbis_codec.c reads Ogg.
#   make arm   -> build/arm/vorbis77.elf   (Cortex-M3, linked into the freed areas of module 77)
#   make bench OGG_FILE=/abs/file.ogg [BENCH_SECONDS=30] [SEEK_MS=0] [BENCH_DUMP=/abs/out.s16]
#   make size
TREMOR  ?= tremor-lowmem
BUILD   ?= build
LIB_SRCS := $(addprefix $(TREMOR)/,bitwise.c codebook.c dsp.c floor1.c floor_lookup.c \
            info.c mapping0.c mdct.c misc.c res012.c)
PORT_SRCS := port77/vorbis_codec.c port77/rt.c
# ARM_ASM=1 (default, HIFIEC56): _ARM_ASSEM_ = Tremor's ARM inline assembly (smull/smlal), ECHO_SSAT =
# CLIP_TO_15 as one ssat. Its conditional instructions need IT blocks in Thumb-2: -mimplicit-it=thumb
# lets gas insert them. ARM_ASM=0 builds plain C, bit-identical to Tremor on a PC (HIFIEC54).
ARM_ASM ?= 1
DEFS := -DECHO_NO_FLOOR0 -DECHO_HEAP_ALLOCA $(if $(filter 1,$(ARM_ASM)),-D_ARM_ASSEM_ -DECHO_SSAT) \
        -DHEAP_SIZE=88*1024 $(EXTRA_DEFS)
INCS := -I$(TREMOR) -I../opus -Iport77
ARM_CC := arm-none-eabi-gcc
ARM_CFLAGS := -mcpu=cortex-m3 -mthumb -Os -std=gnu99 -ffunction-sections -fdata-sections \
              -fno-common -fstack-usage -Wa,-mimplicit-it=thumb $(DEFS) $(INCS) -w
ARM_LDFLAGS := -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections \
               -Wl,--enable-non-contiguous-regions -Wl,-Map=$(BUILD)/arm/vorbis77.map \
               -T port77/echomini77.ld -Wl,--entry=VorbisCodec
ARM_OBJS := $(patsubst %.c,$(BUILD)/arm/%.o,$(LIB_SRCS) $(PORT_SRCS))

arm: $(BUILD)/arm/vorbis77.elf
$(BUILD)/arm/vorbis77.elf: $(ARM_OBJS) port77/echomini77.ld
	$(ARM_CC) $(ARM_LDFLAGS) -o $@ $(ARM_OBJS) -lgcc
$(BUILD)/arm/%.o: %.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@
size: $(BUILD)/arm/vorbis77.elf
	arm-none-eabi-size -A $<

# ---------- QEMU bench of the whole plug-in (HOST_TEST: file and PCM buffers in the bench) ----------
BENCH_SECONDS ?= 30
SEEK_MS ?= 0
BDEFS := -DBENCH_SECONDS=$(BENCH_SECONDS) -DSEEK_MS=$(SEEK_MS) $(if $(BENCH_DUMP),-DBENCH_DUMP='"$(BENCH_DUMP)"')
BENCH_LIB := $(patsubst %.c,$(BUILD)/arm/%.o,$(LIB_SRCS) port77/rt.c)
bench: $(BENCH_LIB)
	@mkdir -p $(BUILD)/bench
	$(ARM_CC) $(ARM_CFLAGS) -DHOST_TEST -c port77/vorbis_codec.c -o $(BUILD)/bench/vorbis_codec.o
	$(ARM_CC) $(ARM_CFLAGS) $(BDEFS) -c bench/bench77.c -o $(BUILD)/bench/bench77.o
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -DOGG_FILE='"$(OGG_FILE)"' -c bench/incbin.S -o $(BUILD)/bench/incbin.o
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -T bench/bench.ld \
	  -o $(BUILD)/bench/bench.elf $(BENCH_LIB) $(BUILD)/bench/vorbis_codec.o $(BUILD)/bench/bench77.o $(BUILD)/bench/incbin.o -lgcc
	qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none \
	  -semihosting-config enable=on,target=native -icount shift=0 -kernel $(BUILD)/bench/bench.elf
clean:
	rm -rf $(BUILD)
.PHONY: arm size bench clean
$(ARM_OBJS): Makefile

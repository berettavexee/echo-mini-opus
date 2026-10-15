# Ogg Opus plug-in for the ECHO MINI HiFi core (module 74 in place of WMA).
#   make host   -> build/host/opustest  (PC validation against opusdec)
#   make arm    -> build/arm/opus74.elf (Cortex-M3, linked into the free areas of module 74)
#   make size   -> per-region usage
#   make arm OPUS=opus-1.5.2-var BUILD=build-var LTO=1 EXTRA_DEFS="$(VARIANT_DEFS)"
#               -> optimised build (HIFIEC52): libopus + patches/libopus-decoder-only.diff, LTO,
#                  ARM inline asm, decoder-only stubs, 32-bit divisions, no diagnostic code
#   make variant  -> shortcut for the line above

OPUS    ?= opus-1.5.2
BUILD   ?= build
PORT    ?= port
ARM_EXTRA ?=
LTO     ?= 0
ifeq ($(LTO),1)
ARM_EXTRA += -flto
endif
include $(OPUS)/celt_sources.mk
include $(OPUS)/silk_sources.mk
include $(OPUS)/opus_sources.mk

LIB_SRCS := $(addprefix $(OPUS)/,$(CELT_SOURCES) $(SILK_SOURCES) $(SILK_SOURCES_FIXED) $(OPUS_SOURCES))
PORT_SRCS := $(PORT)/opus_codec.c

GLOBAL_STACK_SIZE ?= 16384
DEC_MEM_SIZE      ?= 26624

DEFS := $(EXTRA_DEFS) -DOPUS_BUILD -DFIXED_POINT -DDISABLE_FLOAT_API -DNONTHREADSAFE_PSEUDOSTACK \
        -DCUSTOM_SUPPORT -DGLOBAL_STACK_SIZE=$(GLOBAL_STACK_SIZE) -DDEC_MEM_SIZE=$(DEC_MEM_SIZE)
INCS := -I$(OPUS)/include -I$(OPUS)/celt -I$(OPUS)/silk -I$(OPUS)/silk/fixed -I$(OPUS) -I$(PORT) -I.

# ---------- host ----------
HOST_CC     := cc
HOST_CFLAGS := -O2 -g -std=gnu99 $(DEFS) -DHOST_TEST $(INCS) -w
HOST_OBJS   := $(patsubst %.c,$(BUILD)/host/%.o,$(LIB_SRCS) $(PORT_SRCS) $(PORT)/host_main.c)

host: $(BUILD)/host/opustest
$(BUILD)/host/opustest: $(HOST_OBJS)
	$(HOST_CC) -o $@ $^ -lm
$(BUILD)/host/%.o: %.c
	@mkdir -p $(dir $@)
	$(HOST_CC) $(HOST_CFLAGS) -c $< -o $@

# ---------- ARM Cortex-M3 ----------
ARM_CC     := arm-none-eabi-gcc
ARM_CFLAGS := -mcpu=cortex-m3 -mthumb -Os -std=gnu99 -ffunction-sections -fdata-sections \
              -fno-common -fstack-usage $(ARM_EXTRA) $(DEFS) $(INCS) -w
ARM_LDFLAGS := -mcpu=cortex-m3 -mthumb $(ARM_EXTRA) -nostartfiles -nostdlib -Wl,--gc-sections \
               -Wl,--enable-non-contiguous-regions -Wl,-Map=$(BUILD)/arm/opus74.map \
               -T $(PORT)/echomini74.ld -Wl,--entry=OpusCodec
ARM_OBJS   := $(patsubst %.c,$(BUILD)/arm/%.o,$(LIB_SRCS) $(PORT_SRCS) $(PORT)/rt.c)

arm: $(BUILD)/arm/opus74.elf
ifeq ($(LTO),1)
# ld segfaults when LTO is combined with --enable-non-contiguous-regions: run the LTO code
# generation as a partial link into a plain object first (no --gc-sections here, so that the
# 'used' CodecFunc pointer survives), then do the normal scripted link on that object.
$(BUILD)/arm/lto.o: $(ARM_OBJS)
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -Os -flto -flto-partition=one -ffunction-sections -fdata-sections \
	  -nostartfiles -nostdlib -r -flinker-output=nolto-rel -o $@ $(ARM_OBJS)
LINK_OBJS := $(BUILD)/arm/lto.o
LINK_FLAGS := $(filter-out -flto,$(ARM_LDFLAGS))
else
LINK_OBJS := $(ARM_OBJS)
LINK_FLAGS := $(ARM_LDFLAGS)
endif
$(BUILD)/arm/opus74.elf: $(LINK_OBJS) $(PORT)/echomini74.ld
	$(ARM_CC) $(LINK_FLAGS) -o $@ $(LINK_OBJS) -lgcc
$(BUILD)/arm/%.o: %.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

size: $(BUILD)/arm/opus74.elf
	arm-none-eabi-size -A $<

clean:
	rm -rf build

.PHONY: host arm size clean

VARIANT_DEFS := -DOPUS_ARM_INLINE_ASM -DECHO_DECODER_ONLY -DECHO_DIV32 -DECHO_STRIP_DIAG
variant:
	$(MAKE) arm OPUS=opus-1.5.2-var BUILD=build-var LTO=1 EXTRA_DEFS="$(VARIANT_DEFS)"
.PHONY: variant

# ---------- QEMU benchmark (mps2-an385, Cortex-M3) ----------
#   make bench OPUS_FILE=/abs/path/file.opus
BENCH_SECONDS ?= 20
BENCH_LIB  := $(patsubst %.c,$(BUILD)/arm/%.o,$(LIB_SRCS)) $(BUILD)/arm/$(PORT)/rt.o
$(BUILD)/bench/opus_codec.o: $(PORT)/opus_codec.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -DHOST_TEST -c $< -o $@
$(BUILD)/bench/bench_main.o: bench/bench_main.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -DBENCH_SECONDS=$(BENCH_SECONDS) -c $< -o $@
$(BUILD)/bench/incbin.o: bench/incbin.S $(OPUS_FILE)
	@mkdir -p $(dir $@)
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -DOPUS_FILE='"$(OPUS_FILE)"' -c $< -o $@
$(BUILD)/bench/bench.elf: $(BENCH_LIB) $(BUILD)/bench/opus_codec.o $(BUILD)/bench/bench_main.o $(BUILD)/bench/incbin.o bench/bench.ld
	$(ARM_CC) -mcpu=cortex-m3 -mthumb $(ARM_EXTRA) -nostartfiles -nostdlib -Wl,--gc-sections -T bench/bench.ld \
	  -o $@ $(filter %.o,$^) -lgcc
bench: $(BUILD)/bench/bench.elf
	qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none \
	  -semihosting-config enable=on,target=native -icount shift=0 -kernel $<
.PHONY: bench

# Rebuild when flags (GLOBAL_STACK_SIZE, DEC_MEM_SIZE, ...) change
$(HOST_OBJS) $(ARM_OBJS): Makefile

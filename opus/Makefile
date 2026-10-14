# Ogg Opus plug-in for the ECHO MINI HiFi core (module 74 in place of WMA).
#   make host   -> build/host/opustest  (PC validation against opusdec)
#   make arm    -> build/arm/opus74.elf (Cortex-M3, linked into the free areas of module 74)
#   make size   -> per-region usage

OPUS    := opus-1.5.2
include $(OPUS)/celt_sources.mk
include $(OPUS)/silk_sources.mk
include $(OPUS)/opus_sources.mk

LIB_SRCS := $(addprefix $(OPUS)/,$(CELT_SOURCES) $(SILK_SOURCES) $(SILK_SOURCES_FIXED) $(OPUS_SOURCES))
PORT_SRCS := port/opus_codec.c

GLOBAL_STACK_SIZE ?= 16384
DEC_MEM_SIZE      ?= 26624

DEFS := $(EXTRA_DEFS) -DOPUS_BUILD -DFIXED_POINT -DDISABLE_FLOAT_API -DNONTHREADSAFE_PSEUDOSTACK \
        -DCUSTOM_SUPPORT -DGLOBAL_STACK_SIZE=$(GLOBAL_STACK_SIZE) -DDEC_MEM_SIZE=$(DEC_MEM_SIZE)
INCS := -I$(OPUS)/include -I$(OPUS)/celt -I$(OPUS)/silk -I$(OPUS)/silk/fixed -I$(OPUS) -Iport -I.

# ---------- host ----------
HOST_CC     := cc
HOST_CFLAGS := -O2 -g -std=gnu99 $(DEFS) -DHOST_TEST $(INCS) -w
HOST_OBJS   := $(patsubst %.c,build/host/%.o,$(LIB_SRCS) $(PORT_SRCS) port/host_main.c)

host: build/host/opustest
build/host/opustest: $(HOST_OBJS)
	$(HOST_CC) -o $@ $^ -lm
build/host/%.o: %.c
	@mkdir -p $(dir $@)
	$(HOST_CC) $(HOST_CFLAGS) -c $< -o $@

# ---------- ARM Cortex-M3 ----------
ARM_CC     := arm-none-eabi-gcc
ARM_CFLAGS := -mcpu=cortex-m3 -mthumb -Os -std=gnu99 -ffunction-sections -fdata-sections \
              -fno-common -fstack-usage $(DEFS) $(INCS) -w
ARM_LDFLAGS := -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections \
               -Wl,--enable-non-contiguous-regions -Wl,-Map=build/arm/opus74.map \
               -T port/echomini74.ld -Wl,--entry=OpusCodec
ARM_OBJS   := $(patsubst %.c,build/arm/%.o,$(LIB_SRCS) $(PORT_SRCS) port/rt.c)

arm: build/arm/opus74.elf
build/arm/opus74.elf: $(ARM_OBJS) port/echomini74.ld
	$(ARM_CC) $(ARM_LDFLAGS) -o $@ $(ARM_OBJS) -lgcc
build/arm/%.o: %.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

size: build/arm/opus74.elf
	arm-none-eabi-size -A $<

clean:
	rm -rf build

.PHONY: host arm size clean

# ---------- QEMU benchmark (mps2-an385, Cortex-M3) ----------
#   make bench OPUS_FILE=/abs/path/file.opus
BENCH_SECONDS ?= 20
BENCH_LIB  := $(patsubst %.c,build/arm/%.o,$(LIB_SRCS)) build/arm/port/rt.o
build/bench/opus_codec.o: port/opus_codec.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -DHOST_TEST -c $< -o $@
build/bench/bench_main.o: bench/bench_main.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -DBENCH_SECONDS=$(BENCH_SECONDS) -c $< -o $@
build/bench/incbin.o: bench/incbin.S $(OPUS_FILE)
	@mkdir -p $(dir $@)
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -DOPUS_FILE='"$(OPUS_FILE)"' -c $< -o $@
build/bench/bench.elf: $(BENCH_LIB) build/bench/opus_codec.o build/bench/bench_main.o build/bench/incbin.o bench/bench.ld
	$(ARM_CC) -mcpu=cortex-m3 -mthumb -nostartfiles -nostdlib -Wl,--gc-sections -T bench/bench.ld \
	  -o $@ $(filter %.o,$^) -lgcc
bench: build/bench/bench.elf
	qemu-system-arm -machine mps2-an385 -nographic -monitor none -serial none \
	  -semihosting-config enable=on,target=native -icount shift=0 -kernel $<
.PHONY: bench

# Rebuild when flags (GLOBAL_STACK_SIZE, DEC_MEM_SIZE, ...) change
$(HOST_OBJS) $(ARM_OBJS): Makefile

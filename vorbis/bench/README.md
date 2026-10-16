# Vorbis benchmarks (QEMU `mps2-an385`, Cortex-M3, `-icount shift=0`)

Run `../fetch_tremor.sh` first. Paths given to the scripts must be absolute.

**Whole plug-in** (`bench77.c`, the `HOST_TEST` build of `port77/vorbis_codec.c`):
```
make -C .. bench OGG_FILE=/abs/f.ogg [BENCH_SECONDS=30] [SEEK_MS=0] [BENCH_DUMP=/abs/out.s16] [ARM_ASM=0]
```
Prints instructions per second of audio, heap peak and stack use; `BENCH_DUMP` writes the PCM.

**Tremor alone, low vs full accuracy** (`vbench.c`, Tremor with its own `vorbisfile` layer; this is
how the stock decoder was characterised, `docs/REPORT.md` section 19):
```
./build.sh full ""                    # full accuracy
./build.sh low "-D_LOW_ACCURACY_"     # as in the stock firmware
./run.sh full /abs/f.ogg [/abs/dump.s16]
```

`ARM_ASM=0` (with a separate `BUILD=build-c`) builds plain C Tremor, whose output is bit-identical
to Tremor on a PC; the default build uses Tremor's ARM assembly (`docs/REPORT.md` section 21).
After a seek, the first buffer the bench dumps is the one prepared before the seek: skip 512 frames.

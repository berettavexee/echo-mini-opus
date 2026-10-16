# Replacing a low-accuracy Vorbis decoder in a closed DAP firmware: notes for developers

This page is the Vorbis companion to `OPUS_PORTING.md`. It is for developers who want to do
similar work on another player. It explains how the ECHO MINI's stock Ogg Vorbis decoder was found to run
at reduced accuracy, how it was replaced in place by a full-precision build of Tremor, which
choices were made and why, and how each step was validated without a debugger. Players only need
`README.md` and `INSTALL.md`.

The ECHO MINI-specific facts (addresses, overlay numbers) are in `REPORT.md`, sections 19 to 21.
This page focuses on the method and on what should transfer to other devices.

## 1. Why replace a decoder that works
The stock decoder plays every file, so nothing looks wrong on the device. The problem only shows
up in measurements: about **38–43 dB** of SNR against a floating-point decoder, i.e. roughly 7
effective bits, where a correct integer decoder reaches 60–84 dB. The quantisation noise may be
audible in quiet passages and fade-outs.

**How to recognise it.** Many embedded players use Xiph's **Tremor** (integer Vorbis decoder),
often its `lowmem` branch, and vendors like to build it with `_LOW_ACCURACY_` to save RAM and
cycles. That mode is easy to spot in a binary, because it needs its own tables:
- the 8-bit trigonometric tables `sincos_lookup0` (1,026 bytes) and `sincos_lookup1` (1,024
  bytes), which only exist in `_LOW_ACCURACY_` builds;
- the 32-bit window tables (`vwin*`, up to 16 KB each) are then also stored at reduced width.

Build Tremor once in each mode on a PC, dump these tables, and search the firmware for them byte
for byte. On the ECHO MINI they are in module 77's data (`REPORT.md` §19). The module list (13
source files matching Tremor `lowmem`: `bitwise`, `codebook`, …, `vorbisfile`) confirms the
identification.

**Measure before deciding.** Decode a few files with Tremor in both modes and with ffmpeg's float
decoder, and compute the SNR (`REPORT.md` §19). On a Cortex-M3, full accuracy costs only about
3 % more instructions but **three times more constants** (13.7 KB → 44.3 KB). Memory is the real
constraint, not CPU.

## 2. Strategy: replace the library, keep the runtime
Same approach as for Opus (`OPUS_PORTING.md` §1), but easier: the codec stays the same, so no
extension table, content sniffer, tag reader or format label has to change. Only the library
behind `CodecFunc[CODEC_OGG]` is replaced, and the module's runtime (reset, mailbox ISRs, file
layer, main loop) is kept byte for byte.

The interface is the one already reversed for module 74 (`opus/codec_abi.h`), with a few
per-module differences that must be checked rather than assumed:
- **PCM hand-over.** The runtime reserves two 8 KB PCM buffers at the end of its own file
  buffer and passes their addresses through a small structure. The codec writes 512 stereo
  frames per DECODE call.
- **Mono is duplicated** on both channels, but CHANNELS still reports 1.
- **Times are in ms**, the bitrate in bit/s.
- **Runtime variables move between modules.** In module 77 the file size lives 4 bytes further
  than in module 74. An emulator copied from the Opus one read the wrong word and made files with
  cover art fail to open in emulation only. Re-derive every runtime address per module.

## 3. Finding the free memory
Same method as for Opus (`OPUS_PORTING.md` §2): walk the call graph from the runtime roots
without the old decoder's entry point, then classify the data the same way.

| Resource | Available in module 77 | Used by the Vorbis plug-in |
|---|---|---|
| Code | ~46 KB (`0x29d0`–`0xe054`) | 15.4 KB |
| Constants and initialised data | ~40 KB, in two areas | 42 KB (spilling into the code area) |
| Zeroed BSS | ~110 KB (the old library's BSS) | 110 KB, including an 88 KB heap |
| Stack | **8 KB** | ≤ 868 B measured |

> ⚠️ **A runtime structure in the middle of the library's data.** Between the old library's
> zero-initialised data and its tables sat a 24-byte runtime structure (`0x01029888`–`0x010298a0`)
> holding the two PCM buffer pointers. It is written at run time by the runtime, so it looks like
> any other library data in a static dump. It was found because runtime code (`0x3c6`) stores to
> it. Search for every runtime access, not only for the obvious
> blocks at the start and end of a region. The linker script (`vorbis/port77/echomini77.ld`)
> splits the data into two regions around it.

> ⚠️ **Event flags at the end of the BSS.** As in module 74 (`OPUS_PORTING.md` §2), the runtime
> keeps its event flags right after the library's BSS. The plug-in's BSS region stops just
> before them.

## 4. Building Tremor for a small Cortex-M3 slot
Base: Tremor `lowmem`, last commit `89a7534` (2019). It includes two out-of-bounds write fixes
that the vendor's older build lacked. Configuration (`vorbis/Makefile`):

- **Full accuracy**: just do not define `_LOW_ACCURACY_`.
- **Only the decoder core**: `bitwise`, `codebook`, `dsp`, `floor1`, `floor_lookup`, `info`,
  `mapping0`, `mdct`, `misc`, `res012`. Tremor's own Ogg layer (`framing.c`, `vorbisfile.c`) is not
  linked (see §5). The plug-in uses the low-level API: `vorbis_dsp_headerin`,
  `vorbis_dsp_synthesis`, `vorbis_dsp_pcmout`, `vorbis_dsp_read`.
- **`ECHO_NO_FLOOR0`** (`vorbis/patches/tremor-echo.diff`): floor 0 is rejected. No encoder has
  produced it since 2001, and it drags in the LSP code and tables.
- **`ECHO_HEAP_ALLOCA`**: while unpacking the codebooks, Tremor puts scratch arrays of up to
  8 × entries bytes on the stack with `alloca`. With real files this reached **7.7 KB of the 8 KB
  stack**, during OPEN only, so normal playback tests would not have shown it. The patch moves them
  to the heap and frees them at the end of each codebook. Peak stack: 868 bytes.
- **A private heap** (`port77/rt.c`): a first-fit allocator in an 88 KB BSS array, **reset at
  every OPEN and CLOSE**, so that a failed open or a file switch can never leak. Measured peak:
  20–33 KB.
- A minimal runtime (`memcpy`, `memset`, `strlen`, `__errno`, …) instead of a C library, and
  `-mcpu=cortex-m3 -mthumb -Os -ffunction-sections -fdata-sections --gc-sections`.

**Constants larger than any single region.** The full-precision tables (44 KB, with `vwin8192`
alone 16 KB) do not fit in the old library's data areas. As for Opus, `ld
--enable-non-contiguous-regions` lets `.rodata` spill from the freed code area into both data
areas. On Cortex-M, constants are read through the data bus either way.

## 5. The Ogg layer
Tremor's `vorbisfile` keeps the whole comment header in memory. Files from music services embed
the cover art in base64 there (`METADATA_BLOCK_PICTURE`, 70–80 KB on the test albums), so the heap
peaked at **118–188 KB** on exactly the files users care about. The plug-in therefore reuses the
Opus plug-in's Ogg reader (`vorbis/port77/vorbis_codec.c`):

- **Headers.** The identification and setup headers go to `vorbis_dsp_headerin`. The comment
  header is **streamed page by page and dropped**, and only its first 7 bytes are checked.
  Tremor gets a 16-byte empty comment header instead. Tags and cover art are read by the main
  firmware from the file, not by the codec, so nothing is lost.
- **Duration** from the last page's granule position; bitrate from the file size and duration.
- **Seeking**: bisection on page granule positions, restart of the decoder state at the chosen
  page, then exact realignment: the output is dropped until a packet carrying a granule gives
  the absolute position, then trimmed to the target. The result is **sample-accurate**.
- **Robustness**: up to 64 consecutive undecodable packets are skipped before end of stream. The
  stock wrapper instead reopened the file, up to 200 times.

## 6. Validation without a debugger
Same tool chain as for Opus (`OPUS_PORTING.md` §6), with one advantage: Tremor is portable C,
so the ARM build can be compared bit for bit with Tremor on the PC.

| Level | Tool | What it proves |
|---|---|---|
| Accuracy | Tremor on the PC, both modes, vs ffmpeg's float decoder | The stock mode's SNR (38–43 dB) and the full-precision target (60–84 dB). |
| Codec alone | `vorbis/bench/` (QEMU `mps2-an385`), Tremor with `vorbisfile` | ARM output = PC output; instruction cost of each mode; heap peak with real files. |
| Whole plug-in | `make -C vorbis bench` (QEMU, `HOST_TEST` build) | Bit-identical to PC Tremor; seek sample-accurate; heap peak; instructions per second of audio and per call. |
| Firmware code under emulation | `tools/emu77.py` (Unicorn) | The **patched image's** module 77 runs with the real runtime file layer and PCM buffers: bit-identical output, seek, stack peak, every file of a real library opens. |
| Device | marker in a UI string (`[7]`, `[8]`) | Which image is running. |

Cover art turned out to be a separate issue: the firmware's image decoder never displays
**progressive JPEGs**, whatever the audio format. `tools/cover_baseline.py` re-encodes such covers
in `.ogg` files as baseline JPEG, rewriting only the picture block. Check the cover's JPEG type
before suspecting the codec.

## 7. Optimisation (HIFIEC56)
Measured with the QEMU bench (`REPORT.md` §21), in instructions per second of audio:

| Change | Code | CPU | Output |
|---|---|---|---|
| Own Ogg layer instead of `vorbisfile` (HIFIEC54) | — | −2.3 to −2.6 % vs the stock-like build, despite full accuracy; OPEN 2–5× cheaper | bit-identical to PC Tremor |
| `-D_ARM_ASSEM_` (Tremor's `asm_arm.h`: `smull`/`smlal` for `MULT32`/`MULT31`, chained for the MDCT rotations `XPROD31`/`XNPROD31`) | +0.2 KB | −4.5 to −5.5 % | last-bit rounding changes; same SNR (±0.1 dB) |
| `ECHO_SSAT`: `CLIP_TO_15` as one `ssat #16` (ARMv7-M) instead of 5 conditional instructions | −0.1 KB | a further −2.2 to −2.8 % | identical to `_ARM_ASSEM_` alone |

Notes:
- `asm_arm.h` was written for ARMv4 (ARM mode). Its conditional instructions (`movpl`, `rsbmi`, …)
  need IT blocks in Thumb-2. `-Wa,-mimplicit-it=thumb` lets the assembler insert them. Its
  `lsp_loop_asm` only serves floor 0, which is compiled out.
- With assembly, the output is no longer bit-identical to C Tremor (`MULT31` becomes
  `(x·y >> 32) << 1` instead of `x·y >> 31`). The QEMU build of the same sources is therefore the
  reference for the emulated image, and the SNR against float is the reference for quality.

CPU budget: about 23–25 M instructions per second of audio at 44.1/48 kHz, 41 M at 96 kHz,
against about 25–27 M for the stock decoder. The stock clock scenario of module 77 is kept.

## 8. Checklist for another device
1. Identify the Vorbis library (module names, strings), then the accuracy mode by searching the
   firmware for Tremor's `_LOW_ACCURACY_` tables.
2. Measure the SNR of both modes on real files before deciding. The gain is in fidelity, not in
   features.
3. Delimit runtime vs library code and data by call-graph walking. Look for runtime structures
   in the middle of library data and for event flags at the end of the BSS.
4. Check the per-module runtime details (PCM hand-over, frames per call, mono handling, units,
   variable addresses) instead of copying them from another codec module.
5. Build Tremor `lowmem` at full accuracy with only the decoder core, no floor 0, codebook scratch
   on the heap, and a private heap reset at every OPEN/CLOSE. Check the stack during OPEN, not only
   during playback.
6. Write your own Ogg layer that streams and drops the comment header. Implement seeking that is
   exact to the sample.
7. Compare bit for bit with PC Tremor (C build: `make -C vorbis ARM_ASM=0`), then emulate the patched module with the real
   runtime and every file of a real music library.
8. Optionally enable `_ARM_ASSEM_` (plus `ssat` on ARMv7-M), and validate quality by SNR.
9. Prepare a visible version marker and a back-to-stock image that the loader will accept
   **before** flashing.

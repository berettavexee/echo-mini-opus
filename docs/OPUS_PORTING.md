# Porting Opus to a closed DAP firmware: notes for developers

This page is for developers who want to do similar work on another player, whether another
SNOWSKY/FiiO model, another Rockchip RKnano device or a different vendor. It explains how the Opus
decoder was fitted into the ECHO MINI firmware, which choices were made and why, what went wrong
on real hardware, and how each step was validated without a debugger. Players only need
`README.md` and `INSTALL.md`.

The ECHO MINI-specific facts (addresses, overlay numbers, protocol details) are in `REPORT.md`.
This page focuses on the method and on what should transfer to other devices.

## 1. Strategy: replace a codec, don't add one
Adding a new codec to a closed firmware means new UI entries, new extension handling, new
dispatch cases and new memory, which is a lot of patching in code you do not own. Replacing an
existing codec reuses all of that:

- **Pick a codec you can sacrifice** whose slot has enough room. On the ECHO MINI, WMA (module
  74) had about 75 KB of code and tables, more than 130 KB of BSS, and a system-side server
  (module 43) with nothing WMA-specific in it.
- **Keep the codec's runtime byte for byte.** Each codec module had its own copy of the runtime:
  reset, mailbox ISRs, buffered file layer, main loop. Only the library behind a single function
  pointer (`CodecFunc[1]`) is replaced. The system side never knows.
- **Rename the extension** in the extension tables (`WMA` → `OPU`: the firmware uses 3-letter
  extensions, just as `.flac` becomes `FLA`). Every lookup that used to reach WMA now reaches Opus.

What made this possible here, and what to look for elsewhere:
1. Codecs are separately loaded overlays with a scatter-loading table (`{load, exec, len}` per
   overlay), so a module can be rewritten in place without moving anything else.
2. The decoder interface is a single function `Codec(subfn, a1, a2, a3)` with numbered
   sub-functions (open, decode, get buffer, seek, close, info getters), which looks like the
   Rockchip SDK convention. `opus/codec_abi.h` documents it. Other RK-based players very likely
   use the same scheme.
3. File access goes through a function table (`read`, `seek`, `tell`, `length`), so the
   decoder never touches the file system.

## 2. Finding the free memory
Do not assume that everything belonging to the old codec is free. The method used here:

1. **Walk the call graph from the runtime roots** (reset, main loop, ISRs, exception handlers),
   excluding the old decoder's entry point (`tools/reach74.py`). Whatever is reached is runtime
   and must stay; the rest of the code region can be overwritten.
2. **Classify data the same way.** Data reached by the runtime stays (vectors, file-I/O table,
   info block, file buffer). The old library's tables, initialised data and BSS can be freed.
3. **Look for RAM the old codec never used.** Here 95 KB beyond the WMA BSS turned out to be real
   RAM (the WAV module uses it), while the area just above it was hardware registers.

The resulting budget (`REPORT.md` §9):

| Resource | Available | Used by the Opus plug-in |
|---|---|---|
| Code | ~53 KB + ~6 KB (two disjoint areas) | 54 KB (unmodified libopus) / 45 KB (optimised) |
| Constants | ~15 KB of former tables + ~13 KB of initialised data | 21 KB |
| Zeroed BSS | ~43 KB | 27 KB: decoder state, 16 KB pseudo-stack, 8 KB packet buffer |
| Non-zeroed RAM | ~95 KB | 86 KB: two 30 KB PCM buffers, decoder memory |
| Stack | **8 KB** | ≤ 3.8 KB measured |

> ⚠️ **Lesson learnt the hard way (HIFIEC42).** The call graph does not show data the runtime
> touches through computed addresses. The runtime kept an **array of event flags** right at the
> start of the "free" WMA BSS. The plug-in's state landed on it, and every file read silently
> corrupted the stream position, so every file failed to open on hardware while everything
> passed in emulation. Look for writes from runtime code into the area you plan to use, and leave
> a margin at region boundaries.

## 3. Building libopus for a small Cortex-M3 slot
Configuration (`opus/Makefile`):

- `-DFIXED_POINT -DDISABLE_FLOAT_API`: Cortex-M3 has no FPU.
- `-DNONTHREADSAFE_PSEUDOSTACK -DGLOBAL_STACK_SIZE=16384`: libopus's scratch memory goes to a
  static 16 KB BSS array instead of the stack, which only has 8 KB here. Peak use measured on a
  PC: 8.2 KB.
- `-DCUSTOM_SUPPORT` with `port/custom_support.h`: no `malloc`. The decoder is placed in a
  static buffer with `opus_decoder_get_size()` / `opus_decoder_init()`.
- `-mcpu=cortex-m3 -mthumb -Os -ffunction-sections -fdata-sections` + `--gc-sections`: only the
  decoder survives the link, and the encoder sources can stay in the source list.
- A tiny `port/rt.c` (`memcpy`, `memmove`, `memset`, word-optimised) instead of a C library.
- Stereo state: 26.6 KB. Decoder output is always 48 kHz, 16-bit, stereo (mono is duplicated).

**Linking into two disjoint code areas.** The freed code is split in two (WMA library and WMA
tables), and so are the constants. `ld --enable-non-contiguous-regions` lets one output section
spill from one memory region into the next (`port/echomini74.ld`). Constants can live in data
RAM: on Cortex-M they are read through the data bus anyway.

**Large buffers** go to a `.noinit` section placed in RAM the runtime does not zero. Only the
small state needs zero-initialisation.

## 4. The Ogg layer
libopus only decodes packets; the container is your job. `port/opus_codec.c` contains a minimal
Ogg demuxer (about 400 lines in total with the codec glue):

- **Page reader** with lacing, a `MAX_PACKET` of 8 KB and continued packets.
- **Headers**: `OpusHead` (channel count, pre-skip, output gain applied with `OPUS_SET_GAIN`),
  then `OpusTags`, which the decoder only skips.
- **Pre-skip and end trimming** from the last page's granule position, which also gives the
  duration. The bitrate is computed from the file size and the duration.
- **Seeking by bisection** on page granule positions, then 80 ms of pre-roll
  decoding (`PREROLL`), discarded, so the decoder converges (RFC 7845 §6.1).
- **Buffering**: about 40 ms of PCM (`TARGET_FRAMES` = 1920 frames) per decode call, in a double
  buffer, matching what the runtime expects from the old codec.

> ⚠️ **Real-world files are not test files (HIFIEC44).** Files from music services embed cover
> art (`METADATA_BLOCK_PICTURE`, base64) and lyrics in `OpusTags`, which can reach **50–60 KB
> over 15 Ogg pages**. A demuxer that requires the tags packet to fit in its buffer fails on
> exactly the files users care about. Per RFC 7845 the second packet *is* the comment header:
> accept it even when it is too large to read, and skip it.

## 5. What the decoder alone does not cover
Getting sound out is only half of the work. Several firmware features keyed on the old codec had
to be patched separately (`REPORT.md` §12, §15, §17):

- **Content sniffing.** Before playback, the firmware rewrites the extension from the file's
  magic bytes (`OggS` → `OGG`), which sent every `.opus` file to the Vorbis decoder. Look for such
  a sniffer whenever a file "is not supported" although the decoder was never called.
- **Tags and cover art.** The tag and cover readers are dispatched by extension index and lived
  outside the codec module. Here the Ogg Vorbis comment reader could be reused: `OpusTags`
  differs from `\x03vorbis` only by its magic, so the patch just accepts the second magic and
  skips one byte.
- **Format label.** The playback screen builds `WMA|48KHZ|…` from the codec index, so it needed
  its own patch to show "OPUS".
- **Uninitialised inputs.** The cover extractor calls the sniffer on an uninitialised buffer and
  relies on it to *always* write an extension. A sniffer fix that "leaves the extension alone"
  worked for playback but broke cover art.

All these patches are in-place rewrites of the same size, using dead branches or
reshuffled instructions, because the system overlays have no free space.

## 6. Validation without a debugger
There was no JTAG and no serial console, only flashing and looking at the screen. Each test on
the device was therefore prepared so that a single try gives an answer.

| Level | Tool | What it proves |
|---|---|---|
| PC | `make host` + `port/host_main.c` vs `opusdec` | Demuxer, pre-skip, trimming, seek to the exact sample; the SNR is the expected gap between fixed and floating point. |
| Firmware code under emulation | `tools/emu74.py` (Unicorn) | The **patched image's** module 74 runs at its real addresses with the real runtime file layer. PCM is bit-identical to the reference, the stack peak is measured, and the parameter block is checked. |
| CPU cost | `make bench` (QEMU `mps2-an385`, `-icount shift=0`) | Exact instruction counts per second of audio and per call; reproducible, so you can compare builds. |
| Other firmware paths | `tools/emu_sniff.py`, `emu_tags.py`, `emu_cover.py`, `emu_cover_display.py`, `emu_label.py` | Run the real resident/overlay code for the sniffer, tags, cover and label, with file I/O stubbed. |
| Device | a **diagnostic build** (`OPUS_DIAG`) | An open failure becomes N beeps (N = failing step) instead of an error message, and a marker appended to a UI string proves which image is running. |

> ⚠️ **Emulation shortcuts hide bugs.** The cover bug of HIFIEC48 passed emulation because the
> test injected the sniffer's output instead of running it. Run the real code path whenever
> possible.

> ⚠️ **Tooling pitfall.** Unicorn 2.1 mis-executes Thumb `IT` blocks while a `UC_HOOK_CODE` or
> `UC_HOOK_MEM_WRITE` hook is active. Use block hooks only, and measure the stack with a canary
> fill.

## 7. Optimisation (HIFIEC52)
Measured with the QEMU bench (`REPORT.md` §18):

| Change | Code | CPU | Output |
|---|---|---|---|
| `-DOPUS_ARM_INLINE_ASM` (libopus's ARMv4 `smull`/`smlal` macros; the ARMv5E/DSP ones need a Cortex-M4) | −2.8 KB | **−1 to −15 %** (−6 to −9 % on music) | CELT rounding changes, same SNR against float; SILK bit-identical |
| LTO | −1.1 KB | ≈ −0.5 % (CELT), +1.5 % (SILK) | bit-identical |
| Decoder-only stubs: an early `return` in 15 encoder-only functions and the SILK down-sampling resampler | −3.9 KB | — | bit-identical |
| 32-bit divisions in the plug-in, diagnostic code compiled out | −1.1 KB (drops `__aeabi_ldivmod` and friends) | — | bit-identical |

Notes:
- The encoder-only functions are linked because `celt/bands.c` and `celt/rate.c` serve both
  encoder and decoder and choose the path with a run-time flag; `--gc-sections` cannot see that.
- **`ld` crashes (segfault) when LTO is combined with `--enable-non-contiguous-regions`.** The
  workaround is a partial LTO link to a plain object (`-r -flinker-output=nolto-rel`), followed by
  the normal scripted link. Do not use `--gc-sections` in the partial link, or the `used` function
  pointer section disappears.
- Removing packet-loss concealment and FEC was also evaluated (`experiments/plc_fec/`): it saves
  10.6 KB, but gives no measurable CPU gain for music. libopus-encoded files never trigger the
  PLC, not even at mode transitions, which carry redundancy frames. It was not adopted.

CPU budget: about 24–33 M instructions per second of audio for typical music, up to 56 M for
2.5 ms frames at 256 kb/s. The ECHO MINI kept the WMA clock scenario and plays every test file
without dropouts.

## 8. Checklist for another device
1. Identify the firmware container, its checksum and any signature, and how the loader picks an
   image (here: name pattern, then build-date comparison between two flash copies).
2. Find the overlay/module table and the codec modules; pick one to sacrifice.
3. Reverse the codec interface (sub-functions, info block, PCM hand-over, file I/O table) from the
   old decoder and from its system-side server.
4. Delimit the runtime vs library code and data by call-graph walking. Look for runtime writes
   into "free" BSS.
5. Build libopus fixed-point with a static pseudo-stack and no `malloc`, and link it into the freed
   regions. Check stack depth (`-fstack-usage`, `tools/stackdepth.py`).
6. Write the Ogg layer for real files: large `OpusTags`, pre-skip, end trimming, seek pre-roll.
7. Emulate the patched module with the real runtime before flashing, and benchmark it.
8. Patch the extension tables, then look for content sniffers, tag/cover readers and format labels
   keyed on the old codec.
9. Prepare a diagnostic build, a visible version marker, and a back-to-stock image that the loader
   will accept (newer date) **before** the first flash.

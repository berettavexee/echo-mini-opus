# Building from source

Players do not need this page: the binary patches in `patch/` give the same images (see
`INSTALL.md`). This page is for developers who want to rebuild the images, change the decoders or
validate them off the device.

## Requirements
`gcc-arm-none-eabi` 14.2 (Debian/Ubuntu), `make`, `curl`, `git`, Python 3, and `qemu-system-arm`
for the benchmarks.

## Build the images
```
./opus/fetch_libopus.sh            # official libopus 1.5.2 (SHA-256 checked) + the patched copy opus-1.5.2-var
./vorbis/fetch_tremor.sh           # Tremor lowmem 89a7534 + vorbis/patches/tremor-echo.diff

# HIFIEC58 (recommended)
make -C opus variant               # -> opus/build-var/arm/opus74.elf
make -C vorbis arm                 # -> vorbis/build/arm/vorbis77.elf
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build-var/arm/opus74.elf HIFIEC58.IMG --days 18 --marker " [9]" \
        --vorbis vorbis/build/arm/vorbis77.elf --ogg-clock-mp3
sha256sum HIFIEC58.IMG             # ffb9361c95d4093fda79d6d4df60946c63329622db92fa79691b8dd40c5947f6

# HIFIEC56 (stock Ogg clock profile)
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build-var/arm/opus74.elf HIFIEC56.IMG --days 16 --marker " [8]" \
        --vorbis vorbis/build/arm/vorbis77.elf
sha256sum HIFIEC56.IMG             # 01ac8b5c51a9e058d9b0cd78df4b1163c224416dd711b846e58a88f35b7f9f26

# HIFIEC52 (Opus only)
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build-var/arm/opus74.elf HIFIEC52.IMG --days 12 --marker " [6]"
sha256sum HIFIEC52.IMG             # 0aa16307000b12f9bbdc2c3a8df8f005cb90f5133741f810a2c6d0b4c21ba858

# HIFIEC50 (unmodified libopus)
make -C opus arm                   # -> opus/build/arm/opus74.elf
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build/arm/opus74.elf HIFIEC50.IMG --days 10 --marker " [5]"
sha256sum HIFIEC50.IMG             # 4958e56c4feea92909e8e86db33f330b0c47cf11fa3be8eaae0ac19ae86e8296
```
With this toolchain, the resulting images are bit-identical to the ones produced by the patches.
Another GCC version will give a different image, probably working but untested.

- `--days N` moves the build date forward, so that the loader accepts the image (it only installs
  a firmware newer than the one in place).
- `--marker TXT` appends a marker to the "Format Not Supported!" message, to identify the
  installed build on the device.
- What `make variant` changes in libopus, and why: `docs/OPUS_PORTING.md`, section 7.
- `make -C vorbis ARM_ASM=0` builds the Vorbis plug-in in plain C, without Tremor's ARM assembly:
  its output is bit-identical to Tremor on a PC (this is the `HIFIEC54` build).
- `--ogg-clock-mp3` gives Ogg Vorbis the MP3 clock profile (`docs/REPORT.md`, section 22).

## Off-device validation
```
python3 -m venv venv && venv/bin/pip install -r requirements.txt
make -C opus host                                                      # reference decoder for the PC
venv/bin/python tools/emu74.py HIFIEC58.IMG f.opus out.raw --seconds 10 # emulated module 74 (Opus), PCM output
venv/bin/python tools/emu_tags.py HIFIEC58.IMG OPU f.opus               # tags as read by the firmware
venv/bin/python tools/emu_cover_display.py HIFIEC58.IMG f.opus          # sniffer, then cover, then JPEG header
venv/bin/python tools/emu_label.py HIFIEC58.IMG 1 126000 48000 16       # -> OPUS|48KHZ|16bit|0126kbps
make -C opus bench OPUS_FILE=/absolute/path/f.opus                      # QEMU: Opus CPU cost
venv/bin/python tools/emu77.py HIFIEC58.IMG f.ogg out.raw --seconds 10  # emulated module 77 (Vorbis)
make -C vorbis bench OGG_FILE=/absolute/path/f.ogg                      # QEMU: Vorbis CPU cost, heap peak
```
The emulators run the code of the patched image itself, at its real addresses, with the real
codec runtime. How each step was validated: `docs/OPUS_PORTING.md` §6 and
`docs/TREMOR_PORTING.md` §6.

## Repository layout
| Path | Role |
|---|---|
| `patch/` | Binary patches `HIFIEC39 → HIFIEC58` (recommended), `→ HIFIEC56`, `→ HIFIEC52` and `→ HIFIEC50` (unmodified libopus), back-to-stock patches (`HIFIEC59`, `HIFIEC57`, `HIFIEC53`, `HIFIEC51`), and the `apply_patch.py` tool. |
| `rknanofw.py` | RKnano firmware tool: `info`, `extract`, `crc`, `redate`, `patch-opus [--vorbis] [--ogg-clock-mp3]` (builds the image from the compiled plug-ins). |
| `opus/port/` | The Opus plug-in: `opus_codec.c` (Ogg demuxing, seeking, firmware codec interface), a minimal runtime, and the linker script targeting the WMA module areas. |
| `opus/codec_abi.h` | The firmware's codec-module interface, reconstructed by reverse engineering. |
| `opus/patches/*.s` | Assembly sources of the firmware fixes (OpusTags tags and cover art). |
| `opus/patches/libopus-decoder-only.diff` | The decoder-only patch applied to libopus (`make variant`). |
| `opus/bench/` | QEMU benchmark (`mps2-an385`, Cortex-M3): instructions per second of audio. |
| `vorbis/` | The full-precision Ogg Vorbis plug-in for module 77: `port77/vorbis_codec.c` (Ogg reader, seeking, codec interface), runtime and linker script, the Tremor patch `patches/tremor-echo.diff`, and QEMU benchmarks (`bench/`). |
| `tools/` | Unicorn emulators running the real firmware code (Opus and Vorbis decoding, tags, cover art, label, content sniffer), disassembly helpers, and `cover_baseline.py`. |
| `docs/OPUS_PORTING.md` | Developer notes: how Opus was fitted into the firmware, optimised and validated, and a checklist for porting it to another player. |
| `docs/TREMOR_PORTING.md` | Developer notes: how the low-accuracy stock Vorbis decoder was identified and replaced by full-precision Tremor, and a checklist for other players. |
| `docs/REPORT.md` | Technical reverse-engineering report: file format, overlays, codec interface, memory, clock profiles, fixes, tests. |
| `docs/IMAGE_HISTORY.md` | History of the test images and of the defects found on hardware. |
| `experiments/plc_fec/` | Evaluation (not adopted) of removing PLC and FEC from libopus. |

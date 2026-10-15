# Ogg Opus for the SNOWSKY ECHO MINI

This project adds **Ogg Opus (`.opus`)** playback to the SNOWSKY ECHO MINI digital audio player.
It patches the official **V3.9.0** firmware (`HIFIEC39.IMG`, **8 GB model**) and replaces the WMA
decoder, which goes away, with libopus 1.5.2.

<p align="center">
  <img src="docs/images/echo-mini-playing-opus.jpg" width="600"
       alt="ECHO MINI playing an Opus file: Daft Punk - High Life, with cover art, tags and the OPUS|48KHZ|16bit|0129kbps line">
</p>

**Status: validated on the device** (images `HIFIEC50` and `HIFIEC52`, October 2026). What works:
- playback and seeking;
- tags and the "OPUS" label on the playback screen;
- cover art.

MP3, FLAC and Ogg Vorbis keep working as before.

> ⚠️ **Disclaimer.** This is unofficial firmware patch. Flashing it may brick the device, and no
> low-level recovery procedure (MaskROM mode) is documented for this model. Use at your own risk.
> This project is neither affiliated with nor endorsed by SNOWSKY.
> This is a one man project, mostly done with AI, tested on one device. You have been warned.

## What changes compared with the stock firmware
- `.opus` files are recognised and listed.
- Decoding uses libopus 1.5.2 (fixed-point build), with 48 kHz, 16-bit, stereo output.
- **WMA is no longer supported**: `.wma` files no longer appear, and a renamed WMA file is
  cleanly rejected.
- The playback screen shows "OPUS|48KHZ|16bit|…kbps".
- Tags (title, artist, album, genre, track number) and cover art (`METADATA_BLOCK_PICTURE`) are
  read.
- An Ogg Opus file named `.ogg` is also played as Opus.
- The "Format Not Supported!" message carries a marker ("[6]" or "[5]") that identifies the
  installed build.

### Two builds
| Image | Decoder | Notes |
|---|---|---|
| **`HIFIEC52`** (recommended) | libopus 1.5.2 **with a small decoder-only patch**, built with LTO and libopus's ARM inline assembly | Same features. 8.8 KB less code and 2–13 % fewer instructions per second of audio. Same audio fidelity (identical SNR against the floating-point reference). Marker "[6]". |
| `HIFIEC50` | libopus 1.5.2 **unmodified** | Reference build. Marker "[5]". |

The `HIFIEC52` changes to libopus only disable encoder code that a player never runs. Developers
interested in how the decoder was fitted into the firmware, optimised and validated will find
the details in **[docs/OPUS_PORTING.md](docs/OPUS_PORTING.md)**.

### Known limits
- **8 GB model only** (`HIFIECxx.IMG`). The 512 MB model (`MINIVxx.IMG`) is not supported.
- The firmware looks for tags and cover art only in the **first Ogg page**, about 4 KB. A field
  placed further away is ignored, typically after long lyrics (`LYRICS`). The stock firmware has the
  same limit for Ogg Vorbis. Workaround: remove the lyrics without re-encoding:
  `ffmpeg -i in.opus -c copy -metadata LYRICS= out.opus`.
- The firmware's image decoder rejects **progressive JPEGs**, whatever the audio format.

## Installation
See **[INSTALL.md](INSTALL.md)**. In short: get the official `HIFIEC39.IMG`, then:
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC52.ecpatch HIFIEC52.IMG
```
Then copy `HIFIEC52.IMG` **alone** to the root of the internal storage and reboot.

## Repository layout
| Path | Role |
|---|---|
| `patch/` | Binary patches `HIFIEC39 → HIFIEC52` (recommended) and `→ HIFIEC50` (unmodified libopus), back-to-stock patches (`HIFIEC53`, `HIFIEC51`), and the `apply_patch.py` tool. |
| `rknanofw.py` | RKnano firmware tool: `info`, `extract`, `crc`, `redate`, `patch-opus` (builds the image from the compiled plug-in). |
| `opus/port/` | The codec plug-in: `opus_codec.c` (Ogg demuxing, seeking, firmware codec interface), a minimal runtime, and the linker script targeting the WMA module areas. |
| `opus/codec_abi.h` | The firmware's codec-module interface, reconstructed by reverse engineering. |
| `opus/patches/*.s` | Assembly sources of the firmware fixes (OpusTags tags and cover art). |
| `opus/patches/libopus-decoder-only.diff` | The decoder-only patch applied to libopus for `HIFIEC52`. |
| `opus/bench/` | QEMU benchmark (`mps2-an385`, Cortex-M3): instructions per second of audio. |
| `tools/` | Unicorn emulators running the real firmware code (decoding, tags, cover art, label, content sniffer), and disassembly helpers. |
| `docs/OPUS_PORTING.md` | Developer notes: how Opus was fitted into the firmware, optimised and validated, and a checklist for porting it to another player. |
| `docs/REPORT.md` | Technical reverse-engineering report: file format, overlays, codec interface, memory, fixes, tests. |
| `docs/IMAGE_HISTORY.md` | History of the test images and of the defects found on hardware. |
| `experiments/plc_fec/` | Evaluation (not adopted) of removing PLC and FEC from libopus. |

## Building from source
Requirements: `gcc-arm-none-eabi` 14.2 (Debian/Ubuntu), `make`, `curl`, Python 3.
```
./opus/fetch_libopus.sh            # official libopus 1.5.2 (SHA-256 checked) + the patched copy opus-1.5.2-var

# HIFIEC52 (recommended)
make -C opus variant               # -> opus/build-var/arm/opus74.elf
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build-var/arm/opus74.elf HIFIEC52.IMG --days 12 --marker " [6]"
sha256sum HIFIEC52.IMG             # 0aa16307000b12f9bbdc2c3a8df8f005cb90f5133741f810a2c6d0b4c21ba858

# HIFIEC50 (unmodified libopus)
make -C opus arm                   # -> opus/build/arm/opus74.elf
python3 rknanofw.py patch-opus HIFIEC39.IMG opus/build/arm/opus74.elf HIFIEC50.IMG --days 10 --marker " [5]"
sha256sum HIFIEC50.IMG             # 4958e56c4feea92909e8e86db33f330b0c47cf11fa3be8eaae0ac19ae86e8296
```
With this toolchain, the resulting images are bit-identical to the ones produced by the patches.
What `make variant` changes, and why, is explained in `docs/OPUS_PORTING.md`, section 7. Another
GCC version will give a different image, probably working but untested.

Off-device validation:
```
python3 -m venv venv && venv/bin/pip install -r requirements.txt
make -C opus host                                                      # reference decoder for the PC
venv/bin/python tools/emu74.py HIFIEC52.IMG f.opus out.raw --seconds 10 # emulated module 74, PCM output
venv/bin/python tools/emu_tags.py HIFIEC52.IMG OPU f.opus               # tags as read by the firmware
venv/bin/python tools/emu_cover_display.py HIFIEC52.IMG f.opus          # sniffer, then cover, then JPEG header
venv/bin/python tools/emu_label.py HIFIEC52.IMG 1 126000 48000 16       # -> OPUS|48KHZ|16bit|0126kbps
make -C opus bench OPUS_FILE=/absolute/path/f.opus                      # QEMU: CPU cost
```

## License
- This project's code: BSD-3-Clause (`LICENSE`).
- libopus: BSD-3-Clause, see `THIRD_PARTY.md` and `LICENSES/libopus-COPYING`. The decoder-only
  patch is distributed under the same license.
- The SNOWSKY firmware is not distributed.

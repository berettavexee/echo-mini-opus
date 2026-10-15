# HIFIEC39.IMG reverse engineering (SNOWSKY ECHO MINI V3.9.0, 8 GB model)

Tool: `rknanofw.py` (`info`, `extract`, `crc [--fix]`, `redate`, `patch-opus`).

> **Note for this repository.** This report is the working log of the reverse-engineering effort,
> written as the work progressed. Paths `re/…` refer to the repository root. The `out/`
> (extraction) and `out_fw/` (images) directories are **not** distributed: no image or extract of
> the Snowsky firmware is included. Use `patch/` to produce the image from your own copy of
> `HIFIEC39.IMG`. Image names (`HIFIEC40` … `HIFIEC51`) are the successive test builds; only
> `HIFIEC50` and the recovery image `HIFIEC51` can be reproduced.

## 1. Identification
- SoC: **Rockchip RKnano**; the header says "RKnano SDK 1.0". Code is Thumb-2 for Cortex-M, on two cores.
- Build date: 2026-08-24 (BCD in bytes 0..3). The loader also compares this field to decide which of fw1 or fw2 is newer.
- Size: 32 MiB + 4 bytes. The last 4 bytes hold a **Rockchip CRC32** (polynomial 0x04C10DB7, init 0, MSB first) over the rest of the file. Verified: 0x5DE004A2 (OK).
- Binwalk finds no signature in this file; the format was decoded by hand.

## 2. File layout
| Part | Offset | Size | Contents |
|---|---|---|---|
| Header | 0x000 | 0x200 | Date, `Rockchip`, `RKnano SDK 1.0`, part table, firmware length @0x1F4, `RKnanoFW` @0x1F8 |
| code | 0x200 | 0x187C14 | Table of 91 overlays and the ARM code/data |
| font12 | 0x187E14 | 0x201C06 | 12 px bitmap font, 65,536 glyphs of about 32 bytes (width byte 0x80\|w) |
| font16 | 0x389A1A | 0x211C06 | 16 px bitmap font |
| codepage | 0x59B620 | 0x1CA34A | Codepage → Unicode conversion tables (128 KiB blocks) |
| uitext | 0x76596A | 0x2573A8 | 21 languages × 453 entries of 258 bytes (UTF-16LE text at +0x3A) |
| images | 0x9BCD12 | 0x16069E8 | `ROCK26IMAGERES`: 1617 **big-endian** RGB565 images, each with a {w,h,x,y,size,offset} entry; 320×170 screen |

## 3. Overlay table (ARM scatter-loading)
The code part starts with the load base `0x03050000`, n=91, then n entries
`{codeLoad, codeExec, codeLen, dataLoad, dataExec, dataLen, bssExec, bssLen}`.
A "Load" address maps to a file offset as `Load - 0x03050000 + 0x200`.

Memory map (execution addresses):
- `0x03004000`: resident data and vector table in IRAM (SP=0x03004000, reset=0x03056169)
- `0x03005AFC–0x0301E74C`: resident BSS
- `0x03050000–0x0307666C`: **resident code**, 157 KiB (kernel, drivers, FAT/exFAT, USB, FS)
- `0x03079xxx–0x03093xxx`: **system overlays**. These modules share the same memory area and are swapped depending on context.
- `0x01000000` (code) and `0x01020000` (data): **codecs running on the second core** ("HiFi"). The cores talk through IPC with timeouts: `HifiFileRead`, `AudioFileInput2`, etc.
- `0x0309FFF0`: warm-reboot flag `"NanoCRebootFlag"`.

Codecs identified by their strings:

| # | Codec |
|---|---|
| 73 | MP3 (libMad) |
| 74 | WMA |
| 75 | AAC/M4A (MovFile) |
| 76 | WAV |
| 77 | OGG Vorbis |
| 78 | FLAC |
| 79 | ALAC |
| 80 | APE (max version 4120) |
| 81 | DFF (DSDIFF/DST) |
| 82 | DSF |

Named system overlays: 1 = firmware check/update, 10–12 = USB MSC, 23 = FM radio, 31 = media library, 33 = audio control, 39 = file browser, 40 = main UI (135 KiB), 63 = WAV recorder.

Entries 65–71 have execution address 0: they are data tables read in place, not code. Overlays 41–59 are small interchangeable modules of about 0x2BC bytes without strings; their role is not identified.

## 4. Boot (resident code)
- The resident reset vector (`0x0306296E`) sets up clocks and GPIOs (`sub_03052d70` / `sub_03056a94`).
- It then calls overlay 1, checks that the RTC time is valid (month ≤ 12, day ≤ 31, hour ≤ 23, minute ≤ 59), and starts the UI tasks.
- `sub_03079eac` (overlay 1) reads the `NanoCRebootFlag` at the end of SRAM to tell a warm reboot from a cold boot, then clears it; otherwise the device powers off.

## 5. Firmware update (overlay 1)
`sub_0307a15e`:
1. It first looks for `ECHOMINI.IMG` at the root. If found, the version code is 0xF5 and message 0x19B is posted, which triggers the update.
2. Otherwise it tries **`HIFIEC00.IMG` to `HIFIEC97.IMG`** (a 0..97 loop writes the two digits). The first file found is used.
   **There is no version comparison at this stage**: an older firmware is accepted if present (static inference, to be confirmed in the loader).
3. It sets the volume label `ECHO MINI`.

`sub_0307b03c` checks the two copies stored in flash (fw1 and fw2):
- It checks the `RKnanoFW` signature at header +0x1F8.
- The fw2 copy is at `(length@0x1F4 + 0x104000)/512`, rounded to 0x800 sectors.
- It compares the header date of both copies (messages `fw1valid/fw2valid`, `fw2 compare error`).

Writing the firmware to flash most likely happens in the NanoC loader after reboot. That loader is not in this file.

## 6. Audio codec handling
This flow was reconstructed by static analysis. Function names are inferred from behaviour.

### 6.1 Codec selection by extension (overlay 34, `0x0308abc4`)
1. `sub_030593b2` opens the current file, described by the structure at `0x0301d900`. The handle is stored at `0x03004554`.
2. `0x0308aadc(ext, table)` looks the extension up in `"MP1MP2MP3WMAWAVAPEFLAAACM4AOGGMP43GPDFFDSF"` at `0x030057f1` in the resident data. It compares 3 characters at a time; the 1-based index is computed as `pos*0xAB>>9`. A `switch` then writes **`CurrentCodec`** to `0x0304af7c`:

| Extension | MP1 MP2 MP3 | WMA | AAC M4A MP4 3GP | WAV | OGG | APE | FLA | DFF | DSF | other |
|---|---|---|---|---|---|---|---|---|---|---|
| CurrentCodec | 0 | 1 | 2 (AAC), or 7 (ALAC) if `0x0304af80`==13 | 3 | 4 | 5 | 6 | 8 | 9 | 0xFF → `"ERROR!!! CurrentCodec == 0x%02x"` |

3. `sub_030697e0` is called between two identifications, except for WAV. It probably parses the file header (inference; see section 12).

### 6.2 Loading and start (overlay 33, `0x03086b3a`)
`switch(CurrentCodec)` with 10 cases. Each case:
- loads the system-side *server* overlay with `sub_0306913c(idx, 7)`;
- adjusts clocks and power (`sub_03052c24` / `sub_03052c94`);
- calls `sub_0306e478(idx_codec)`.

| CurrentCodec | 0 MP3 | 1 WMA | 2 AAC | 3 WAV | 4 OGG | 5 APE | 6 FLAC | 7 ALAC | 8 DFF | 9 DSF |
|---|---|---|---|---|---|---|---|---|---|---|
| Server overlay (`0x0308b29c`) | 42 | 43 (+44, empty) | 51 | 52 | 53 | 56 | 54 | 55 | 57 | 58 |
| Codec overlay (second core) | 73 | 74 | 75 | 76 | 77 | 80 | 78 | 79 | 81 | 82 |

`sub_0306e478(idx)` is resident and starts the second core:
1. It holds the second core in reset (`sub_03052c94(0x32,1)`).
2. It copies the codec overlay with `sub_0306913c(idx,7)`: code to `0x01000000`, data to `0x01020000`.
3. It copies 0x90 bytes of parameters from `0x03006630` to `0x01020000`.
4. It sets `0x03004138` to 0 and releases the reset.
5. It waits for the codec to write `0x03004138`, at most 200,000 iterations.

The second core sees the codec code at **address 0**. Its vector table has SP=`0x01022000`; for FLAC, reset=`0x2849`. The `ovl73..82` ELFs are generated with that base.

The recorder (overlay 63) reuses `sub_0306e478(76)` to load the WAV module.

### 6.3 Inter-core communication: hardware mailbox `0x40110000`
- Codec side: `sub_4fb0(cmd, mbox, channel)` writes the command (+0x30/0x38/0x40/0x48) and `sub_4fdc` writes the data word (+0x34/…). Arguments go through a shared area at `0x0102226c`. The codec then waits for the answer, at most 3,000,000 iterations, after which it prints `"…: timeout!!"`.
- System side: accessors at `0x0306e874`–`0x0306ea50` (`0x0306ea24` = command, `0x0306e9f8` = data, `0x0306e8ec` = read).
- **File server** (ISR `0x03087aec`, overlay 33). Files are read by the system on behalf of the codec, which has no direct file-system access. The codec receives an already open handle: opening happens on the system side, step 6.1.

| Command | 0x69 | 0x6b | 0x6d | 0x6f | 0x71 | 0x73 |
|---|---|---|---|---|---|---|
| Operation | HifiFileSeek | HifiFileRead | HifiFileWrite | unidentified | unidentified | HifiFileClose |
| Function called | `sub_03059e92` | `sub_0305999a` | `sub_0305d40c` | reply only | reply only | `sub_03059880` |

- **Codec state and control** (ISR `0x030878b4`, commands 0..0x10). Examples: 1 = sample-rate change request (`FreqChange`), 0x0f = FLAC fast seek, 0x11 = FLAC seek info. The exact meaning of the other commands is unconfirmed.
- Server overlays 42–58 expose an `f(cmd 0..15)` API: they send a command to the codec and then wait for an acknowledge flag (`0x0304a878`, `0x0304a888`, `0x0304af28`…).

### 6.4 Open points
- The PCM output path (I2S/DAC, resampling, equaliser) was not traced.
- The meaning of control commands 2..0x10 is not established.
- The 0x90 parameter bytes were not decoded.
- The origin of `0x0304af80` (code 13 for ALAC in MP4) remains an inference.

## 7. Limits and open questions
- Mostly static analysis (Hopper via REA, plus scripts), complemented by Unicorn emulation of the real firmware code and hardware tests from section 12 onwards.
- The firmware has no symbols. Functions are named `sub_xxx`, and overlay roles are inferred from strings.
- Hopper coverage is partial: 825 functions were found in the resident code, using a symbol table built from `BL` targets.
- Not analysed: the overlay dispatcher, button logic (A/B/C modes), equaliser, media-library database and the NanoC loader.
- The header has **no cryptographic signature**, only the CRC. `crc --fix` rebuilds a valid CRC after a change. Flashing a modified image can brick the device.

## 8. Codec module interface (analysis of module 74 WMA / server 43)
The details used by the implementation are in `opus/codec_abi.h`.

**Second-core side (module 74)**
- `0x2aa8`: reset. Disables IRQs, sets VTOR to `0x01022000` (vector table in the data section), then jumps to the real entry `0x15b6`.
- `0x15b6`: runtime. Clears its BSS (`0x010267c0`, 0x20e72 bytes) and installs mailbox IRQs 0x1a (`0x139c`, control) and 0x1b (`0x142c`, files). It sends message 1 ("ready") and enters its main loop (`wfi` while no command is pending).
- The main loop turns commands into calls to `CodecFunc[CurrentCodec](subfn,…)`, table at `0x01023478`:
  - OPEN: subfn 8, then 4, 5, 3, 6, 0x11 and 0xa; message 3 (OK) or 2 (failure);
  - DECODE: subfn 0xc, then 7 and 0xa; message 5 or 6;
  - SEEK: subfn 0xe; message 0xc;
  - CLOSE: subfn 0xf; message 0xe.
- **The WMA decoder is a single function** `0x2ec4(subfn, a1, a2, a3)`, registered in `CodecFunc[1]`. Its sub-functions are numbered as in the Rockchip SDKs: 0 name … 8 open, 0xa buffer, 0xc decode, 0xe seek, 0xf close, 0x11 bps.
- The decoder reads the file only through the pointer table at `0x010220e4`: `read(buf, size, h)`, `seek(off, whence, h)`, `tell`, `length`, `close`, `eof`. The handle is at `0x01022108`.
- Output is double-buffered. Interleaved 16-bit stereo PCM is returned by subfn 0xa (pointer and frame count).
- A 0x30-byte info structure at `0x010269c0`: time, length, bitrate, bps, samplerate, channels, pcm, frames. The system copies it to `0x0304af28`.

**System side (module 43)**
- `0x0308b2a8 CodecCtrl(cmd 0..17, out, …)`:
  - cases 3–7 and 17: read one field of the info structure;
  - case 8: open (command 1 to the codec, wait on flag `0x0304a878`);
  - case 10: fetch PCM. Copies the second-core buffer by DMA (`sub_030609ac`) to the ping-pong buffers `0x0303d47c` / `0x0303447c` and starts another decode with command 4;
  - case 12: command 4; case 14: seek (command 0xb); case 15: stop (command 0xd).
- Server 43 contains **nothing WMA-specific**. An Opus module that follows the same protocol can reuse it as is.

**Consequences for Opus (replacing WMA)**
- Keep the module-74 runtime byte for byte at the same addresses.
- Replace the WMA library by libopus plus an `OpusCodec(subfn,…)` function, and point `CodecFunc[1]` (`0x0102347c`) at it.
- Space available for code:
  - about 53 KB in `0x2ec4`–`0x10138`;
  - about 21 KB of WMA tables in `0x110a4`–`0x162c0`;
  - beyond that, up to 0x20000 if code RAM really is 128 KB (unverified).
- Space available for data: an existing BSS of about 135 KB, of which the runtime's share had to be delimited (section 9).
- To be confirmed at this stage: the exact runtime/library boundary (notably `0x10076`, `0x100e4`, `0x1010a`), the runtime's own data/BSS variables, the time/length unit (ms?), and the role of `0x3c6(samplerate)`.

## 9. Module 74 memory budget for Opus
Method: recursive call-graph walk from the runtime roots (reset `0x2aa8`, main `0x15b6`, ISRs `0x139c`/`0x142c`, handler `0x9a`), excluding the WMA entry `0x2ec4`. Script: `tools/reach74.py`.

**Code to keep (runtime)**
- `0x0000`–`0x2ec4`: runtime and compiler helpers (memcpy `0x1bc6`, memclr `0x1c14`, 64-bit division `0x1acc`…), also used by the library.
- `0x10138`–`~0x110a4`: `CodecFunc` wrappers, mailbox driver, printf.
- `0x12800`–`0x12858`: 88 bytes read by the runtime printf; kept as a precaution.

**Code that can be freed (WMA)**
- `0x2ec4`–`0x10138`: about 53.6 KB.
- `0x110a4`–`0x162c0`, except `0x12800`–`0x12858`: about 21 KB.

**Data**
| Area | Contents | Status |
|---|---|---|
| `0x01020000`–`0x01020090` | parameter block sent by the system | runtime |
| `0x01020090`–`0x01022000` | stack (8 KB, initial SP `0x01022000`) | runtime |
| `0x01022000`–`0x01023478` | vectors, file I/O table, variables, `CodecFunc` | runtime (WMA variables in `0x01022fc0`–`0x01023128`) |
| `0x0102347c`–`0x010267c0` | 13 KB of initialised WMA tables | can be freed, except the `CodecFunc[1]` pointer |
| `0x010267c0`–`0x01026b18` | info, file-buffer control | runtime |
| `0x01026b18`–`0x0103cb18` | file read buffer (0x16000 = 88 KB) | runtime |
| `0x0103cb18`–`0x01047632` | WMA BSS (about 43 KB) | can be freed (but see section 13) |
| `0x01047632`–`0x0105f2bc` | unused by WMA, used by the WAV module (#76) | **the RAM exists**, about 95 KB more |

- `0x01060000` and above holds hardware registers: DMA at `0x01070000`, other blocks at `0x01060040` and `0x0106b000`. Not RAM.
- Budget for Opus:
  - code: about 74 KB in place, plus 13 KB of initialised data;
  - BSS: about 138 KB (`0x0103cb18`–`0x0105f2bc`);
  - stack: only 8 KB, so libopus must be built with `NONTHREADSAFE_PSEUDOSTACK` and its scratch placed in BSS.
- The Cortex-M3 can execute code in `0x0102xxxx` (architectural "Code" region), so some code could live in the data section. Architectural inference, untested.

## 10. Opus port: build and budget
Files in `opus/`:
- `Makefile`;
- `port/opus_codec.c`: the `OpusCodec` plug-in with a minimal Ogg demuxer, pre-skip, end trimming, bisection seek and PCM double buffering;
- `port/echomini74.ld`: links into the freed areas of module 74;
- `port/custom_support.h`: no malloc; static pseudo-stack;
- `port/rt.c`: `mem*` functions;
- `port/host_main.c`: PC harness.

Sources: official libopus 1.5.2 (SHA-256 `65c1d2f7…7ce1`, checked against xiph's published list), fixed point (`FIXED_POINT`, `DISABLE_FLOAT_API`, `NONTHREADSAFE_PSEUDOSTACK`).

**PC validation** (`make host`, 5 files produced by opusenc: stereo 20 ms, 60 ms, 2.5 ms at 256 kb/s, 500 kb/s, mono 32 kb/s), against `opusdec` 1.6.1:
- identical sample counts in every case: pre-skip and end trimming are correct;
- 62–63 dB SNR, the expected gap between fixed and floating point;
- seek to 30 s exact to the sample (offset 0);
- stereo decoder state: 26,580 bytes; pseudo-stack: 8,228 bytes at most.

**ARM build** (`make arm`, gcc 14.2, `-mcpu=cortex-m3 -Os`, `--gc-sections`):

| Section | Size | Area (module 74) | Free |
|---|---|---|---|
| code `.text` | 53,876 B | T1 `0x2ec4`–`0x10138` | 0 (T2 `0x110a4`–`0x12800`, 5,980 B, kept in reserve) |
| constants | 14,928 + 5,886 B | T3 `0x12858`–`0x162c0` + D `0x01023480`– | about 7 KB |
| `CodecFunc[1]` | `0x2ec5` | `0x0102347c` | — |
| `.bss` (state, 16 KB pseudo-stack, 8 KB packet) | 27,003 B | `0x0103cb18`–`0x01047630` (cleared by the runtime) | 16.8 KB |
| `.noinit` (2 × 30 KB PCM buffers, decoder) | 88,064 B | `0x01047640`–`0x0105f2bc` | 9.3 KB |

- **Stack**: static worst case of 3,204 bytes (`tools/stackdepth.py`), plus about 1 KB for the `quant_partition` recursion: about 4.2 KB of the 7.9 KB available (`0x01020090`–`0x01022000`).
- **Nothing overflows the freed areas**, the runtime is untouched and the file keeps its size: module 74 can be rewritten in place.

**Not verified at this stage:**
- CPU load (second-core clock unknown; measured later under QEMU, section 11);
- sub-functions 0xb/0xd and messages 7/9/0xcb/0xcd (ignored);
- the time/length unit (ms assumed, confirmed in section 11);
- real DMA behaviour with 1,920-frame buffers (WMA returns 2,048).

## 11. First testable Opus firmware (`out_fw/`)
- **`HIFIEC40.IMG`**: V3.9.0 with WMA replaced by Ogg Opus. Produced by `rknanofw.py patch-opus`, which:
  - erases the WMA library from module 74 and writes `opus74.elf` there, checking the areas;
  - replaces `WMA` by `OPU` in the 5 extension lists;
  - moves the date forward by one day (2026-08-25), **in the header and in its copy at `0x1fc4000`**;
  - recomputes the CRC;
  - checks that every modified byte lies in an allowed area (84,533 bytes modified).
- **`STOCK_RECOVERY/HIFIEC41.IMG`**: stock V3.9.0 dated 2026-08-26 (`rknanofw.py redate`), to roll back.
- **`test_opus/`**: 9 test files (not distributed). Checklist and procedure in `docs/IMAGE_HISTORY.md`.

**New findings**
- The header copy at the end of the firmware (offset = length at `0x1f4`) is compared with the header by the fw1/fw2 check of overlay 1. Any header change must be mirrored in the copy.
- The overlay loader (`sub_03069046`) does not check any per-module checksum.
- System-side seek is in **ms**: `0x03089684(ms)` is called with ±1000 and 1500 ms offsets, followed by DECODE. The `CodecCtrl[CurrentCodec]` table is at `0x03046480`.
- Clocks: the scenario table is at `0x03076298` (`{id, PLL, …}`), and the ID is chosen per codec at `0x0308685c`. WMA uses ID 7 or 8 `{200,150,150,75,300,300}`.
- The WMA tag readers (overlay 38 for the media library, `0x0308a1b2` in overlay 33) first compare the ASF GUID and give up otherwise. `.OPU` files are therefore safe, but have no tags at this stage.

**Validation (Unicorn emulation of module 74 of the final image, `tools/emu74.py`)**
- Bit-identical to the reference decoder (`OPUS_FAST_INT64=0`) on 7 files, with exact frame counts and exact seek.
- Stack: 3.7 KB at most; parameter block intact.
- QEMU `mps2-an385` bench: about 33 M instructions per second of audio (stereo, 20 ms), 56 M in the worst case (2.5 ms, 256 kb/s).
- Tooling pitfall: Unicorn 2.1 mis-executes Thumb `IT` blocks as soon as a `UC_HOOK_CODE` or `UC_HOOK_MEM_WRITE` is active. Only block hooks and a canary fill for the stack are used.

## 12. First hardware test and the content sniffer
- `HIFIEC40` flashed on the device: the player boots, MP3 and FLAC play, but `.opus` files give "Format Not Supported!" (UI string 68).
- Cause: after the selection by extension, overlay 34 (`0x0308ac32`) calls the **resident content sniffer `sub_030697e0(ext, handle)`**, then selects again by extension. The sniffer reads the first sectors (read pointer `0x03004538`, seek pointer `0x0300453c`), skips an ID3v2 tag, looks for a signature in the first 0x400 bytes and rewrites `ext`:

| Signature | ASF `30 26 b2` | MPEG sync `FFEx` | `ftyp` (with `alac` → ALAC) | `RIFF` | `fLaC` | `MAC` | `OggS` | `FRM8` | `DSD ` |
|---|---|---|---|---|---|---|---|---|---|
| Extension written | WMA | MP3 or AAC (ADTS) | AAC / M4A | WAV | FLA | APE | OGG | DFF | DSF |

- A `.opus` file therefore became `OGG` and was sent to the Vorbis decoder (module 77).
- First fix (`rknanofw.py`, `SNIFF_*`): in the `OggS` case (`0x03069cd2`, 26 bytes), if byte `0x1d` is `p` (`OpusHead`), leave through `0x03069d56` (rewind to 0, extension untouched). Not through `0x03069d14`, which continues scanning and could mistake Opus data for an MP3 sync. *(This "leave untouched" behaviour turned out to break cover art; replaced in section 17.)*
- Verification: `tools/emu_sniff.py` runs the image's function under Unicorn.
- No other search for `OggS` exists outside the Vorbis decoder.
- Image: `HIFIEC42.IMG` (2026-08-27). Recovery: `STOCK_RECOVERY/HIFIEC43.IMG` (2026-08-28).

## 13. Second hardware test (HIFIEC42): memory overlap and a diagnostic image
- Result: "Format Not Supported!" for every `.opus`, one after the other (the player skips to the next file).
- Event `0x55`, which shows string 68, is raised in two places of overlay 33:
  - `0x03087110`, when identification fails (`0x0308abc4` returns -1);
  - `0x03087234`, when `0x03086a26` returns -1. That happens if OPEN fails (codec message 2), or if the system rejects the stream info: duration, sample rate, bitrate and bits per sample must be non-zero, with at most 2 channels, a rate other than 8000 and 384000, and bps ≥ 16 for APE/FLAC.
- Actual sequence of the module-74 runtime:
  - message 0x65 (handle, size, position, codec type → `0x01022214`);
  - case 1: `0x3c6(type, 44100)` then `0x2940(h, 0x15c00)`, which installs `FILE_OPS` and a **2 × 512-byte** file buffer;
  - OPEN (`0x10138`), then reads of sample rate, channels, bitrate and duration;
  - `0x3c6(type, rate)` reserves 0x8000 bytes at the end of the buffer for type 1;
  - `0x29ba(h, 0x8000)` resizes the buffer to 2 × 0x7000 while keeping the logical position;
  - message 3.
- `seek` returns 0 if the target is inside the buffer. Otherwise it returns the result of `sub_03059e92`: 0 on success, 0xff on error.
- **Bug found**: `0x2d30`/`0x2d4c` manage an array of event flags at `0x0103cb18` (flag 0x115 is the word at `0x0103cb38`). The WMA library started at `0x0103cb54`. The plug-in had placed `global_stack`, `scratch_ptr` and its state `s` from `0x0103cb18` on, so flag 0x115 landed in `s.last_granule`. Fix: the BSS starts at `0x0103cb58`.
- `tools/emu74.py` now runs the runtime's file layer (`0x2940`, `0x2544`, `0x277e`, `0x29ba`, `0x24ec`, flags) and only simulates requests `0x206` and `0x26c` to the system. `--stub-io` restores the old mode.
- This mode did not explain the failure: with HIFIEC42, OPEN also succeeded in emulation. The hardware cause was therefore not yet established.
- Diagnostic image `HIFIEC44` (`-DOPUS_DIAG`, `--marker " [2]"`):
  - an OPEN failure becomes 60 s of beeps (N beeps = step N of `open_stream`);
  - string 68 ends with "[2]", proving that the new image is running.
- Verification: bit-identical on 7 files in emulation with the real file layer; a renamed Vorbis file does produce 4 beeps.

## 14. Third hardware test (HIFIEC44): first sound, then the large OpusTags header
**Observed on the device.** The `test_opus/` files play, and the sound seems "a bit noisy". Files from an album downloaded with streamrip (ffmpeg/libopus) beep, i.e. `OPEN` fails in the plug-in.

This is the first proof that the whole chain works on hardware: sniffer, module-74 loading, mailbox, file layer, decoding and PCM output. The BSS/flags overlap (section 13) was therefore very probably the cause of the HIFIEC42 failure.

**Cause of the beeps.** These files have a 50–60 KB `OpusTags` packet containing `METADATA_BLOCK_PICTURE` (35 KB) and `LYRICS`, spread over about 15 pages. Reproduced in emulation with HIFIEC44.
- `next_packet()` returns -1 for any packet larger than `MAX_PACKET` (8 KB).
- The `open_stream()` loop waited for a packet starting with `OpusTags`, so it consumed the whole stream and then returned step 7.

**Fix.** The second packet is the comment header (RFC 7845, §5.2). It is accepted even when it is too large to be read (-1).

**HIFIEC46** (2026-08-30, marker "[3]", still a diagnostic build):
- all 14 tracks open;
- durations match ffprobe;
- seeking to 60 s succeeds;
- signal-to-noise ratio of 60 dB against `opusdec` (floating point with dithering);
- the bit-exact regression gives the same result as with HIFIEC44.

Recovery image: `STOCK_RECOVERY/HIFIEC47.IMG` (08-31).

**Hardware result for HIFIEC46 (2026-10-14).** Everything works and the sound is clean, including the album with cover art and lyrics. The "noise" was in the test files themselves: it is audible on a PC too. **The Opus port is validated on hardware.**

## 15. Tags, cover art and format label (HIFIEC48)
**Observed with HIFIEC46.** Metadata showed "Unknown", and the format line read `WMA|48KHZ|16bit|0126kbps`.

| Function | Where | Before | Patch |
|---|---|---|---|
| Format label | overlay 27, `0x0307af7e` and `0x0307bca8`, built letter by letter (`strh` of immediates) from `CurrentCodec` | case 1 = "WMA" | `beq` redirected to 3 dead branches (`0x0307b0bc`, `0x0307be18`) rewritten to "OPUS" (4 letters) |
| Tag dispatcher | resident `sub_0306df9c(handle, out, ext)`: extension index in `0x0300581c`, then `tbb` | entry 4 → `0x0306e026` (ASF readers of overlays 33/38) | byte `0x0306dffa`: `0x18` → `0x6c`, i.e. the Ogg case `0x0306e0ce` |
| Ogg tag reader | `sub_0306bf94`: Ogg pages, then 1 type byte and 6 bytes, then `\x03vorbis`, then the parser `sub_0306bd02(h, out, arg, len)` | Vorbis only | `0x0306c052`–`0x0306c0bc` rewritten at equal size (`opus/patches/oggtags.s`): also accepts `OpusTags` (skips the `s`, length - 8) |
| Cover dispatcher | overlay 18, `sub_030814de`: sniffer, then index - 3, then `tbb` | entry 1 → the MP4 case | byte `0x03081517`: `0x4c` → `0xbc` (Ogg case) |
| Ogg cover reader | overlay 18, `0x030819b8`: same structure, then `sub_03080f3a(h, out, len, granule)` | Vorbis only | `0x03081a72`–`0x03081adc` rewritten (`opus/patches/oggcover.s`), keeping `r4` (granule) |

**Callers and dependencies.** `sub_0306df9c` is called by playback (overlay 33, `0x03087010`) and by the browser (overlay 39, `0x0307b636`). The comment parser is codec-independent: it looks for keys (TITLE, ARTIST, ALBUM, GENRE, TRACKNUMBER…), converts UTF-8 values with `sub_0306a0c0`, and stops at the length limit.

**Date (overlay 1, `0x0307b1b4`).** The fw1/fw2 choice compares `ldrh[0] << 16 | ldrh[2]`, i.e. `year << 16 | month << 8 | day` in BCD. `set_date` now handles month roll-over. HIFIEC48 is dated 2026-09-01 and the recovery image HIFIEC49 09-02.

**Emulation checks (Unicorn, real code; only file read, seek, create and write are simulated):**
- `tools/emu_label.py`: the label becomes `OPUS|48KHZ|16bit|0126kbps`; other codecs unchanged;
- `tools/emu_tags.py`: tags are read on all 14 tracks of the album;
- an Ogg Vorbis file gives the same result as with the stock image;
- `tools/emu_cover.py`: the extracted FLAC picture block is bit-identical to the reference (13 of 14 tracks), and the Vorbis cover is unchanged.

In these emulations the codepage conversion (tables in flash, `0x03069df4`) is replaced by latin-1. For the cover, the sniffer output was injected; it was checked separately with `emu_sniff.py` (this shortcut hid the bug of section 17).

**Known limit.** Both parsers bound the field search to the packet length **within the first page**. For the cover, only the picture data itself can cross pages. With ffmpeg's 4,080-byte pages, a field starting after about 4 KB is ignored: this is track 14 of the album, because of 5.3 KB of `LYRICS`. Stock firmware behaves the same for Ogg Vorbis. Fixing it would need more code in overlays that have no free space.

The plug-in is built without `OPUS_DIAG`: an open failure returns the normal error. Marker "[4]" is appended to UI string 68.

**Hardware result (2026-10-14):** playback, tags and the "OPUS" label work; cover art does not (section 17).

## 16. Evaluation: removing PLC and FEC from libopus (QEMU)

**Method.** The `mps2-an385` bench (Cortex-M3) runs with `-icount shift=0`, so instruction counts are exact and reproducible. Each variant is built with the plug-in's options (`-Os`, `--gc-sections`, linker script `echomini74.ld`). The patch `experiments/plc_fec/no_plc_fec.diff` adds three macros:
- `ECHO_NO_FEC`: removes SILK LBRR decoding and Opus's `decode_fec` branch. LBRR data is still parsed in order to skip it, as the bitstream requires.
- `ECHO_NO_PLC`: `celt_decode_lost` is replaced by silence. SILK no longer uses `silk_PLC`, `silk_CNG` or `silk_PLC_glue_frames`.
- `ECHO_DEC48K_ONLY` (bonus, not PLC): removes the SILK down-sampling resampler (`down_FIR`), never used since output is always 48 kHz.

Scripts and raw results are in `experiments/plc_fec/`. `prof.sh` builds a per-function profile from `-d in_asm,exec,nochain`, and `toc.py` counts the modes and transitions of a `.opus` file.

**Code size** (`.text1` + `.text2`, baseline 54,072 bytes):

| Variant | Code | Saving |
|---|---|---|
| FEC only | 53,756 | −316 B |
| PLC only | 43,756 | −10,316 B |
| PLC + FEC | 43,440 | −10,632 B (−19.7 %) |
| 48 k resampler only | 51,876 | −2,196 B (+ −260 B of data) |
| all three | 41,244 | −12,828 B (−23.7 %) |

RAM does not change, since `dec_mem` has a fixed size. The functions removed with CELT PLC are `pitch_downsample`, `pitch_search`, `_celt_autocorr`, `_celt_lpc`, `celt_iir`, `celt_fir`, `xcorr`, `prefilter_and_fold` and `celt_decode_lost`. SILK PLC removal drops `silk_PLC` and `silk_CNG`.

**CPU** (instructions per second of audio, "all three" vs baseline):
- CELT, including Daft Punk and the 128 k music: −0.01 to −0.02 %.
- 2.5 ms and mono 32 k test files: −0.07 % and −0.14 %.
- Hybrid: −0.3 %.
- SILK 12 k: −0.9 %.

During normal playback, only the state updates of `silk_PLC(…, 0)` and `silk_CNG` run. The per-call peak (`max_call_insns`) drops by less than 0.1 %.

**Audio output.** PCM is bit-identical (FNV hash) on all files, including three encodes at 16, 24 and 32 kb/s with 8 to 10 CELT↔hybrid transitions each. The libopus encoder codes these transitions with redundancy frames, which bypass the PLC.

With PLC removed, behaviour would change in only three cases:
- a 1-byte DTX packet;
- a zero-length packet;
- a transition without redundancy, from an encoder other than libopus.

These would give silence instead of concealment. Corrupt packets are already dropped by `fill()` without calling the PLC.

**Conclusion.** No measurable CPU gain for music. The space saving is real: about 10.6 KB for PLC + FEC, 12.8 KB with the resampler. It is only worth it if space is needed in module 74, which currently has about 5.8 KB free for code and 24 bytes in `rodata3`. **Decision (2026-10-14): the patch is not applied.** libopus stays unmodified, as the maintenance cost of local changes is not justified.

## 17. Missing cover art on hardware (HIFIEC48), fixed in HIFIEC50
**Observed (2026-10-14).** HIFIEC48 plays the files and shows tags and the "OPUS" label, but no cover art.

**Display chain.** Overlay 27, `0x0307b7bc` (called at `0x0307ca00`, unless `[r7+0x44]` is 1, which seems related to A-B repeat):
1. Open the file, then `sub_030814de(handle, &type)` (overlay 18).
2. `sub_03081b06(handle, type)`: reopens the temporary file (the handle must be ≤ 8), loads overlay 19 and calls `0x03084604` for the JPEG header.
3. If width and height are ≤ 1000, draw with `0x03081c54`.

**Cause.** `sub_030814de` calls the sniffer `sub_030697e0(sp+0x20c, handle)` on an **uninitialised** buffer. Since HIFIEC42, the sniffer returned without writing anything for OpusHead. Playback is unaffected: it passes the real extension, which the sniffer leaves alone. The cover extractor, however, looked random bytes up in `0x0300581c` and gave up. The `emu_cover.py` emulation injected the sniffer output at `0x03081500`, which hid the defect.

**Fix** (`SNIFF_NEW` in `rknanofw.py`, 26 bytes, same size). The OggS case writes "OPU" if `[r4+0x1d] == 'p'`, and "OGG" otherwise. `r1` is free at that point of the loop, which allows reusing two existing tails: `0x03069d02` ("GG", DFF case) and `0x03069d36` (3rd letter). Side effect: an Ogg Opus file named `.ogg` is now played as Opus.

**Verification.** `tools/emu_cover_display.py` runs the real sniffer on an uninitialised buffer, then the extraction, then the overlay-19 JPEG header:
- HIFIEC48: failure, the defect is reproduced;
- HIFIEC50: 500×500 accepted for 21 of 22 tracks (Daft Punk track 14: the 4 KB limit).

The JPEG decoder rejects progressive JPEGs, whatever the audio format, Vorbis included.

**WMA.** The sniffer's ASF case (`0x0306990e`, which writes "WMA") is deliberately kept. "WMA" no longer exists in any of the 5 extension tables, so an ASF file is cleanly rejected instead of being sent to the Opus decoder.

**Images.**
- `HIFIEC50.IMG`: 2026-09-03, marker "[5]", SHA-256 `4958e56c…8296`.
- Back to stock: `STOCK_RECOVERY/HIFIEC51.IMG` (09-04).

**Hardware result (2026-10-14): cover art is displayed** on both test albums (Daft Punk, Lebanon Hanover). HIFIEC50 is the validated release.

## 18. Optimised build (LTO, ARM inline assembly, unused code removed) — HIFIEC52
**Setup.**
- `opus/fetch_libopus.sh` also creates `opus/opus-1.5.2-var`: the official sources plus `opus/patches/libopus-decoder-only.diff`.
- The Makefile takes `OPUS=`, `PORT=`, `BUILD=` and `LTO=1`; `make variant` builds `opus/build-var/arm/opus74.elf`. The default build is unchanged (HIFIEC50 is still reproduced bit for bit).
- **LTO**: `ld` crashes (segfault) when LTO is combined with `--enable-non-contiguous-regions`. The Makefile therefore runs the LTO code generation as a partial link (`-r -flinker-output=nolto-rel`, without `--gc-sections` so that `.codecfunc` survives), then the usual scripted link.

| Step (cumulative) | Code | Constants | Total |
|---|---|---|---|
| HIFIEC50 | 54,072 | 20,910 | 74,982 |
| + LTO + `OPUS_ARM_INLINE_ASM` (libopus's `fixed_armv4.h` / `macros_armv4.h`: `smull`/`smlal`, valid on Cortex-M3) | 50,316 | 20,915 | 71,231 |
| + `ECHO_DECODER_ONLY` (15 encoder-only functions and `down_FIR` return immediately; resampler down-sampling branches removed) | 46,456 | 20,655 | 67,111 |
| + `ECHO_DIV32` (bitrate and current time computed with 32-bit divisions) | 46,424 | 20,655 | 67,079 |
| + `ECHO_STRIP_DIAG` (beep code only with `OPUS_DIAG`): `__aeabi_(u)ldivmod` and `__udivmoddi4` are gone | **45,316** | **20,559** | **65,875** (−9,107, −12 %) |

Separately: LTO alone −1,056 B, ARM inline assembly alone −2,792 B.

The encoder-only functions are linked in the first place because `bands.c` and `rate.c` share code between encoder and decoder and pick the path with a run-time flag. They are: the range encoder `ec_enc_*` (11), `alg_quant` (and through it `op_pvq_search`), `encode_pulses`, `stereo_itheta` and `intensity_stereo`.

**CPU** (QEMU `mps2-an385`, instructions per second of audio, 30 s per file):
- full build: −1.8 % (2.5 ms frames) to −13 % (SILK), −7.7 % on a Daft Punk track;
- the worst case per call drops by 2 to 12 %;
- nearly all of the gain comes from the ARM inline assembly: LTO alone gives −0.5 % on CELT and +1.5 % on SILK.

**Accuracy.**
- LTO and the stubs do not change the PCM (bit-identical).
- The ARM inline assembly changes CELT rounding; SILK stays bit-identical. Against the floating-point `opusdec` reference, the SNR is **the same** to within 0.01 dB (69.3 to 74.5 dB depending on the file).
- The complete image (`patch-opus`, all areas respected) run through `tools/emu74.py` (the real module-74 runtime): PCM identical to QEMU, stack ≤ 3.8 KB, same durations.
- The reported bitrate is now truncated to the kbit/s (142,505 → 142,000). The screen shows the same value, because the firmware already truncates (`emu_label.py`: `0142kbps` in both cases).

**Hardware result (2026-10-15).** `HIFIEC52` (2026-09-05, marker "[6]") flashed; all 5 tests pass:
- the "[6]" marker is shown;
- both albums play, with tags and cover art;
- fast forward and seeking work;
- no dropouts, including on the 2.5 ms-frame file;
- MP3, FLAC and OGG are unchanged.

**HIFIEC52 is validated on hardware.** Back to stock: `HIFIEC53` (2026-09-06).

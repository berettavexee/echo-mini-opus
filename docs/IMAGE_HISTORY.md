# ECHO MINI V3.9.0 with Ogg Opus: history of the test images

> **Note for this repository.** This is the log of the successive test images flashed on the
> device, newest first. The `.IMG` files it mentions are **not** distributed. Only `HIFIEC50`,
> `HIFIEC52` and the recovery images `HIFIEC51`/`HIFIEC53` can be reproduced, from your own `HIFIEC39.IMG`, with `patch/` or
> by rebuilding (see `INSTALL.md`). The test files of `test_opus/` are not distributed either.

**Status (2026-10-15): `HIFIEC52` (recommended) and `HIFIEC50` are validated on the device** (Opus playback, tags, "OPUS" label
and cover art on two albums; MP3 and FLAC unchanged). Images `HIFIEC40` to `HIFIEC48` each had a
defect, fixed since (see below). This firmware is unofficial and flashing it carries a risk of
bricking the device.

| Image | Date | Role | Result on hardware |
|---|---|---|---|
| `HIFIEC40` | 2026-08-25 | first Opus build | `.opus` → "Format Not Supported!" (content sniffer) |
| `HIFIEC42` | 2026-08-27 | sniffer fix | still "Format Not Supported!" (BSS overlapping runtime flags) |
| `HIFIEC44` | 2026-08-29 | memory fix, diagnostic build "[2]" | first sound; files with large tags beep |
| `HIFIEC46` | 2026-08-30 | large `OpusTags` fix, diagnostic "[3]" | **playback validated** |
| `HIFIEC48` | 2026-09-01 | tags, cover, "OPUS" label, normal build "[4]" | tags and label OK, no cover art |
| **`HIFIEC50`** | **2026-09-03** | cover fix, "[5]" | **everything validated** |
| **`HIFIEC52`** | **2026-09-05** | optimised decoder (LTO, ARM inline asm, decoder-only libopus), "[6]" | **everything validated** |
| `HIFIEC41/43/45/47/49/51/53` | | stock firmware re-dated, to roll back | — |

## HIFIEC52: optimised decoder
Same firmware patches as `HIFIEC50`; only the decoder plug-in changes. It is built with LTO and libopus's ARM inline assembly, with the encoder-only libopus code and the plug-in's diagnostic code removed and its 64-bit divisions replaced. The result is 8.8 KB less code and 2–13 % fewer instructions per second of audio, with the same audio fidelity. Details and measurements: `docs/REPORT.md`, section 18.

**Hardware result (2026-10-15):** the "[6]" marker is shown; both albums play with tags and cover art; fast forward and seeking work; no dropouts (including the 2.5 ms-frame file); MP3, FLAC and OGG unchanged.

## HIFIEC50: cover art for Opus files
**Observed with HIFIEC48 (2026-10-14).** Playback, tags and the label work, but no cover art is shown (Lebanon Hanover and Daft Punk albums).

**Cause.** The cover extractor (overlay 18, `sub_030814de`) does not trust the file extension. It calls the content sniffer `sub_030697e0` on an **uninitialised** stack buffer, then looks the result up in the extension table. The HIFIEC42 fix made the sniffer return *without writing anything* for an OpusHead stream. That is enough for playback, which passes the real extension, but the cover extractor read random bytes and gave up. The HIFIEC48 emulation injected the sniffer result, which hid the problem.

**Fix.** The sniffer's "OggS" case (`0x03069cd2`, 26 bytes, same size) now writes "OPU" if byte 0x1d of the page is "p" (OpusHead), and "OGG" otherwise. It reuses two existing tails: "GG" (DFF case, `0x03069d02`) and the 3rd letter (`0x03069d36`). Welcome side effect: an Ogg Opus file named `.ogg` is now played as Opus.

**Verification.** `tools/emu_cover_display.py` runs the real sniffer on a buffer filled with arbitrary bytes, then the extraction, then the JPEG open (overlay 19).
- HIFIEC48: the sniffer leaves the random bytes and no cover is produced; the defect is reproduced.
- HIFIEC50: "OPU", then a 500×500 JPEG accepted, for 21 of 22 tracks. Daft Punk track 14 is still subject to the 4 KB limit.
- The only other bytes changed relative to HIFIEC48 are the date, the "[5]" marker and the CRC.

**Hardware result:** cover art displayed on both albums.

**Stock firmware limit.** The JPEG decoder rejects **progressive** JPEGs, whatever the audio format. To convert a cover to a baseline JPEG:
```
ffmpeg -i cover.jpg -q:v 2 cover_baseline.jpg
```
then embed that image back into the audio file.

## HIFIEC48: tags, cover art and format label
With `HIFIEC46`, metadata showed "Unknown" and the format line read `WMA|48KHZ|16bit|0126kbps`.

**Format label.** The playback screen (overlay 27) builds this label letter by letter from `CurrentCodec`, in two twin functions (`0x0307af7e` and `0x0307bca8`). Case 1 wrote "WMA". It now jumps to three unused branches just before (dead code), which write "OPUS".

**Tags.** The resident dispatcher `sub_0306df9c(file, out, ext)` picks the tag reader by extension index. Entry 4 (formerly WMA, now OPU) led to the ASF readers. It now leads to the Ogg reader `sub_0306bf94`. That reader only accepted `\x03vorbis`: the range `0x0306c052`–`0x0306c0bc` was rewritten at equal size (`opus/patches/oggtags.s`). It also accepts `OpusTags`, skips its 8th byte, then calls the same Vorbis comment parser.

**Cover art.** Same principle in overlay 18. The OPU entry of the `sub_030814de` table now leads to the Ogg case, and the `vorbis` check at `0x03081a72`–`0x03081adc` is rewritten (`opus/patches/oggcover.s`).

**Date.** `HIFIEC48` is dated September 1st. The fw1/fw2 check of overlay 1 (`0x0307b1b4`) compares `(year << 16) | (month << 8 | day)`, so a month roll-over keeps the order.

**Verified in emulation**, with the real firmware code and only file access simulated:
- the label becomes `OPUS|48KHZ|16bit|0126kbps`; MP3, OGG, FLAC, ALAC and DSF are unchanged (`tools/emu_label.py`);
- title, artist, album, genre and track number are read on all 14 tracks of the Daft Punk album (`tools/emu_tags.py`);
- the cover is extracted bit-identically on 13 of 14 tracks (`tools/emu_cover.py`);
- an Ogg Vorbis file with tags and cover gives exactly the same result as the stock firmware;
- decoding stays bit-identical, and the album opens and seeks correctly;
- a fake `.opus` (renamed Vorbis) is detected as OGG and rejected normally, without beeps.

**Limit.** The firmware parsers only read tag fields within the **first Ogg page** of the tag block. For the cover, only the picture data can spill over to the next pages. streamrip/ffmpeg files use 4,080-byte pages: any field starting after about 4 KB of tags is ignored.
- On the album, this is track 14 "Too Long": its 5.3 KB of lyrics push the track number and the cover beyond that limit.
- Ogg Vorbis has the same limit in the stock firmware.
- Workaround: drop the `LYRICS` tag without re-encoding: `ffmpeg -i in.opus -c copy -metadata LYRICS= out.opus`.

## HIFIEC46: files with cover art or lyrics (validated on the device)
Result of `HIFIEC44` on the device: the `test_opus/` files play, but an album downloaded with streamrip beeps.

**Cause.** These files embed the cover (`METADATA_BLOCK_PICTURE`, about 35 KB) and lyrics in the `OpusTags` header, which then spans about fifteen Ogg pages (50–60 KB), whereas the plug-in's packet buffer is 8 KB. The packet reader correctly skipped this oversized packet, but `open_stream` no longer recognised it as `OpusTags`. It then scanned the whole file for the tags and failed at step 7.

**Fix.** Per RFC 7845, the second packet is always the comment header. It is now accepted even when it exceeds the buffer, and skipped without being read.

**Verified in emulation** on the 14 tracks of the album, with the runtime's real file layer:
- all 14 tracks open;
- durations match ffprobe;
- a seek to 1:00 lands at the right place;
- the difference from `opusdec` is about 60 dB below the signal;
- the 7 reference files remain bit-identical.

Beeps and marker have the same meaning as below, with "[3]" instead of "[2]".

**Hardware result:** everything plays, sound is clean. The slight noise heard on the test files is in the files themselves (audible on a PC too).

## HIFIEC44: diagnostic build (superseded)
After `HIFIEC42`, the player still showed "Format Not Supported!" for every `.opus`. This image fixes a bug and makes the failure locatable in a single try.

**Bug fixed.** The second-core runtime keeps its event flags at `0x0103cb18`–`0x0103cb54`. This area was believed free, and the plug-in had put the libopus stack pointer and its state (including the end-of-stream position) there. Every file read set flag 0x115 inside that state. The plug-in BSS now starts at `0x0103cb58`.

**Reading the test result** (with `01_sine1k_stereo.opus`, then one of your files):

| What the player does | Meaning |
|---|---|
| "Format Not Supported!" **without** "[2]" | The old image is still running. Check that no other `HIFIECxx.IMG` is at the root. |
| "Format Not Supported! **[2]**" | The Opus decoder is not reached, or the system rejects its stream info. The failure is on the system side (identification, loading). |
| N beeps of 150 ms, then 1 s of silence, for 60 s | The decoder is reached, but opening fails at step N (see below). |
| The expected sound | It works. |

Steps signalled by the beeps:
1. file seen as empty (size < 47 bytes);
2. seek to the start failed;
3. no packet read;
4. first packet is not `OpusHead`;
5. more than 2 channels;
6. decoder initialisation;
7. `OpusTags` header missing;
8. seek to the start of audio failed;
9. no sample decoded.

## HIFIEC42: the content sniffer
Before playback, the resident code `sub_030697e0` reads the file header and **rewrites the extension** from its content (`RIFF` → WAV, `fLaC` → FLA, `OggS` → OGG, etc.). A `.opus` file starts with `OggS`: it was renamed `OGG` and sent to the Vorbis decoder, which rejected it ("Format Not Supported!").

The fix changes 26 bytes at `0x03069cd2` (file offset `0x4349e`). If the first Ogg page contains `OpusHead` (byte `0x1d` = `p`), the function returned without touching the extension (`OPU`); otherwise it wrote `OGG` as before. *(Replaced in HIFIEC50 by an explicit "OPU" write, see above.)*

Verified by running the image's function under Unicorn (`tools/emu_sniff.py`):
- the stock code gives `OGG` for `.opus` files, reproducing the bug;
- the patched code gives `OPU` for the 9 test files and for an Opus file produced by ffmpeg;
- Vorbis still gives `OGG`, MP3 (with or without ID3) `MP3`, and FLAC `FLA`.

## What changes compared with the stock firmware
- **`.opus`** files are recognised. The firmware uses 3-letter extensions (`OPU`), just as `.flac` becomes `FLA`.
- Opus decoding uses fixed-point libopus 1.5.2 and always outputs 48 kHz, 16-bit stereo (mono is duplicated on both channels).
- WMA is no longer recognised. "WMA" is removed from the 5 extension tables (replaced by OPU), so `.wma` files no longer appear in the browser. The content sniffer still recognises an ASF header and then writes "WMA", but that extension no longer matches any entry: a WMA file renamed `.opus` is cleanly rejected ("Format Not Supported!") instead of being sent to the Opus decoder. This case is deliberately kept.
- Opus tags (title, artist, album, genre, track) are shown since `HIFIEC48` and cover art since `HIFIEC50`, subject to the 4 KB limit described above. The format shown is "OPUS".
- The clock scenario remains WMA's: `{200,150,150,75,300,300}`. Opus decoding needs about 33 M instructions per second of audio, and up to 56 M in the worst case (2.5 ms frames). No dropouts were heard on the device.

## What was verified without hardware
- Module 74 of the patched image was emulated with Unicorn at its real addresses (code at 0, data at `0x01020000`, uninitialised RAM filled with garbage). Output is **bit-identical** to the reference libopus decoder (same arithmetic) on the 7 test files (stereo, mono, 2.5/20/60 ms frames, 24 to 500 kb/s), with exact frame counts and exact seek.
- The stack peaks at 3.7 KB of the 7.9 KB available. The parameter block is never overwritten.
- The image itself:
  - modified bytes stay within the intended areas (module 74, 5 extension lists, sniffer, tag/cover/label patches, date, UI marker, CRC);
  - the header copy at `0x1fc4000` matches the header;
  - the Rockchip CRC is valid.

## Device test checklist
1. Does the player boot normally after the update?
2. `01_sine1k_stereo.opus`: pure 1 kHz tone, no crackles; displayed duration 0:10.
3. `02_left_then_right.opus`: 5 s on the **left** only, then 5 s on the **right** only.
4. `03_music_128k_tags.opus`: displayed duration 1:00, with its tags.
5. `09_long_5min.opus`: fast forward/rewind, jump to the middle, resume after pause, next and previous track.
6. `05_frames2_5ms_256k.opus` (heaviest case) and `08_high_500k.opus`: listen for dropouts.
7. `06_mono_32k.opus` and `07_hybrid_24k.opus`: correct playback.
8. Refresh the media library with these files present: it must neither crash nor hang.
9. Check that MP3, FLAC, OGG and the other formats still play, with their cover art.

## Back to the stock firmware
See `INSTALL.md`, section 4. If the player no longer boots at all, there is no documented recovery procedure (Rockchip MaskROM mode not studied for this model).

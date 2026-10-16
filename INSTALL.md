# Installation

## 1. Get the official firmware
Download firmware **V3.9.0** from SNOWSKY's website. The archive contains `HIFIEC39.IMG`
(8 GB model). Check that it is the expected file:
```
sha256sum HIFIEC39.IMG
# 59b6230df42607384345992532ba8ae8f7967c6dfb51dc2f9f100447ee8cd17e
```
The patches refuse any other file.

## 2. Produce the image
Recommended build (`HIFIEC58`, optimised Opus decoder, full-precision Ogg Vorbis, Ogg clock profile = MP3):
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC58.ecpatch HIFIEC58.IMG
# -> SHA-256 ffb9361c95d4093fda79d6d4df60946c63329622db92fa79691b8dd40c5947f6
```
Or the same with the stock Ogg clock profile (`HIFIEC56`):
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC56.ecpatch HIFIEC56.IMG
# -> SHA-256 01ac8b5c51a9e058d9b0cd78df4b1163c224416dd711b846e58a88f35b7f9f26
```
Or the same Opus decoder with the stock Vorbis decoder (`HIFIEC52`):
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC52.ecpatch HIFIEC52.IMG
# -> SHA-256 0aa16307000b12f9bbdc2c3a8df8f005cb90f5133741f810a2c6d0b4c21ba858
```
Or the reference build with an unmodified libopus (`HIFIEC50`):
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC50.ecpatch HIFIEC50.IMG
# -> SHA-256 4958e56c4feea92909e8e86db33f330b0c47cf11fa3be8eaae0ac19ae86e8296
```
You can also rebuild any of these images from source (see `README.md`): the result is identical.

## 3. Flash
1. Connect the player over USB.
2. Delete any `HIFIECxx.IMG` file from the root of the internal storage: the loader takes the
   first one it finds.
3. Copy the image (`HIFIEC58.IMG`, `HIFIEC56.IMG`, `HIFIEC52.IMG` or `HIFIEC50.IMG`) **alone** to the root of the internal storage.
4. Remove the microSD (TF) card.
5. Safely eject the player, then reboot it: the update starts by itself.
6. Refresh the media library so that it re-reads the tags.

The loader keeps two copies of the firmware and boots the **newer** one, so an image is only
installed if it is dated after the firmware already in place:

| Image | Date | Role |
|---|---|---|
| `HIFIEC50` | 2026-09-03 | Opus, unmodified libopus |
| `HIFIEC51` | 2026-09-04 | stock firmware, to roll back from `HIFIEC50` |
| `HIFIEC52` | 2026-09-05 | Opus, optimised decoder |
| `HIFIEC53` | 2026-09-06 | stock firmware, to roll back from `HIFIEC52` |
| `HIFIEC56` | 2026-09-09 | Opus (optimised) + full-precision Vorbis |
| `HIFIEC57` | 2026-09-10 | stock firmware, to roll back from `HIFIEC56` |
| `HIFIEC58` | 2026-09-11 | `HIFIEC56` + Ogg clock profile = MP3 (recommended) |
| `HIFIEC59` | 2026-09-12 | stock firmware, to roll back from `HIFIEC58` (or from any image above) |

`HIFIEC58` can be installed over the stock firmware or over any image above. Going back to an
older image requires moving its date forward first (see section 4).

## 4. Back to the stock firmware
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC59_stock_recovery.ecpatch HIFIEC59.IMG
# -> SHA-256 1ad95e0200b43c5e3b9b1536de71cba8ee2164187fc1eea8944a5629229a4300
```
`HIFIEC59.IMG` is the stock firmware, with no change other than its date moved to 2026-09-12 (and
the CRC recomputed), so that it is considered newer than all the images above. Install it the same
way, **alone** at the root. (`HIFIEC57_stock_recovery.ecpatch`, `HIFIEC53_stock_recovery.ecpatch` and
`HIFIEC51_stock_recovery.ecpatch`, dated 2026-09-10, 2026-09-06 and 2026-09-04, only work after
`HIFIEC56`, `HIFIEC52` and `HIFIEC50` respectively.)

A future official firmware dated before 2026-09-12 might be ignored. In that case, or to switch
back to an older image, move its date forward with:
```
python3 rknanofw.py redate FW.IMG DAYS OUT.IMG
```

If the player no longer boots at all, see the **Recovery** section of the README (community
MaskROM procedure, [livetrack.club/debrick](https://livetrack.club/debrick), not tested by this
project).

## 5. Check
- An `.opus` file plays, with its tags, cover art and the `OPUS|48KHZ|16bit|…` line.
- MP3, FLAC and OGG files still play, with their cover art (baseline JPEG only, see the README).
- Seeking works, in `.opus` and `.ogg` files.
- On failure, the message reads "Format Not Supported! [9]" (`HIFIEC58`), "… [8]" (`HIFIEC56`), "… [6]" (`HIFIEC52`) or
  "… [5]" (`HIFIEC50`).

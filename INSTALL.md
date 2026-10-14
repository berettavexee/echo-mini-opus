# Installation

## 1. Get the official firmware
Download firmware **V3.9.0** from SNOWSKY's website. The archive contains `HIFIEC39.IMG`
(8 GB model). Check that it is the expected file:
```
sha256sum HIFIEC39.IMG
# 59b6230df42607384345992532ba8ae8f7967c6dfb51dc2f9f100447ee8cd17e
```
The patch refuses any other file.

## 2. Produce the image
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC50.ecpatch HIFIEC50.IMG
# -> SHA-256 4958e56c4feea92909e8e86db33f330b0c47cf11fa3be8eaae0ac19ae86e8296
```
You can also rebuild it from source (see `README.md`): the result is identical.

## 3. Flash
1. Connect the player over USB.
2. Delete any `HIFIECxx.IMG` file from the root of the internal storage: the loader takes the
   first one it finds.
3. Copy `HIFIEC50.IMG` **alone** to the root of the internal storage.
4. Remove the microSD (TF) card.
5. Safely eject the player, then reboot it: the update starts by itself.
6. Refresh the media library so that it re-reads the tags.

The image is dated 2026-09-03. The loader keeps two copies of the firmware and boots the newer
one, so the installed image must be dated after the firmware already in place.

## 4. Back to the stock firmware
```
python3 patch/apply_patch.py apply HIFIEC39.IMG patch/HIFIEC51_stock_recovery.ecpatch HIFIEC51.IMG
```
`HIFIEC51.IMG` is the stock firmware, with no change other than its date moved to 2026-09-04 (and
the CRC recomputed), so that it is considered newer than `HIFIEC50`. Install it the same way,
**alone** at the root.

A future official firmware dated before 2026-09-04 might be ignored. In that case, move its date
forward with `python3 rknanofw.py redate FW.IMG DAYS OUT.IMG`.

## 5. Check
- An `.opus` file plays, with its tags, cover art and the `OPUS|48KHZ|16bit|…` line.
- MP3, FLAC and OGG files still play, with their cover art.
- Seeking works.
- On failure, the message reads "Format Not Supported! [5]".

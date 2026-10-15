# Third-party components

## libopus 1.5.2 — BSD-3-Clause
Copyright 2001-2023 Xiph.Org, Skype Limited, Octasic, Jean-Marc Valin, Timothy B. Terriberry,
CSIRO, Gregory Maxwell, Mark Borgerding, Erik de Castro Lopo, Mozilla, Amazon.

Not included in the repository: `opus/fetch_libopus.sh` downloads the official archive
(`https://downloads.xiph.org/releases/opus/opus-1.5.2.tar.gz`, SHA-256
`65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1`).

- `HIFIEC50` uses it **unmodified**.
- `HIFIEC52` uses it with `opus/patches/libopus-decoder-only.diff` (a modified version): 61 added
  lines that, behind `ECHO_DECODER_ONLY`, make 15 encoder-only functions and the SILK
  down-sampling resampler return immediately. The patch is distributed under libopus's
  BSD-3-Clause license.

The compiled libopus code is contained in `patch/HIFIEC50.ecpatch` and `patch/HIFIEC52.ecpatch`;
its license (copied to `LICENSES/libopus-COPYING`) applies to that part of the patches.

## SNOWSKY ECHO MINI firmware
The `HIFIEC39.IMG` firmware is the property of SNOWSKY. It is **not** distributed here, nor are
the modified images or extracts of its code or resources. The binary patch only contains the
bytes written by this project (Opus decoder, fixes, date and checksum); it only applies to an
official copy of `HIFIEC39.IMG`, verified by SHA-256.

This project is neither affiliated with nor endorsed by SNOWSKY.

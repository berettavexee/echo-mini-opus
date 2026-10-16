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

The compiled libopus code is contained in `patch/HIFIEC50.ecpatch`, `patch/HIFIEC52.ecpatch` and
`patch/HIFIEC56.ecpatch`, `patch/HIFIEC58.ecpatch`;
its license (copied to `LICENSES/libopus-COPYING`) applies to that part of the patches.

## Tremor (branch `lowmem`, commit `89a7534`) — BSD-3-Clause
Copyright (c) 2002, Xiph.org Foundation.

Not included in the repository: `vorbis/fetch_tremor.sh` clones
`https://gitlab.xiph.org/xiph/tremor.git` and checks out commit `89a7534` (2019-08-09).

`HIFIEC56` and `HIFIEC58` use it with `vorbis/patches/tremor-echo.diff` (a modified version): behind
`ECHO_NO_FLOOR0`, floor type 0 is rejected; behind `ECHO_HEAP_ALLOCA`, the codebook scratch buffers
are allocated on the heap instead of the stack; behind `ECHO_SSAT`, `CLIP_TO_15` uses the ARMv7-M
`ssat` instruction. Tremor's own ARM assembly (`_ARM_ASSEM_`) is enabled. Tremor's Ogg layer (`framing.c`, `vorbisfile.c`) is
not used. The patch is distributed under Tremor's BSD-3-Clause license.

The compiled Tremor code is contained in `patch/HIFIEC56.ecpatch`, `patch/HIFIEC58.ecpatch`; its license (copied to
`LICENSES/tremor-COPYING`) applies to that part of the patch.

## SNOWSKY ECHO MINI firmware
The `HIFIEC39.IMG` firmware is the property of SNOWSKY. It is **not** distributed here, nor are
the modified images or extracts of its code or resources. The binary patch only contains the
bytes written by this project (Opus and Vorbis decoders, fixes, date and checksum); it only applies to an
official copy of `HIFIEC39.IMG`, verified by SHA-256.

This project is neither affiliated with nor endorsed by SNOWSKY.

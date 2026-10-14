# Evaluation: removing PLC and FEC from libopus (not adopted)

Measured under QEMU (`mps2-an385`, Cortex-M3, `-icount shift=0`); details and conclusions in
`docs/REPORT.md`, section 16. The patch `no_plc_fec.diff` is **not** applied to the firmware:
negligible CPU gain (≤ 0.02 % on CELT music), about 10.6 KB of code saved, and the maintenance
cost of a modified libopus was judged not worth it.

```
mkdir files && cp /path/to/*.opus files/          # test files (not provided)
./build.sh base ""                                 # then: ./build.sh all "-DECHO_NO_FEC -DECHO_NO_PLC -DECHO_DEC48K_ONLY"
./runall.sh base                                   # instructions per second of audio + PCM hash
./prof.sh base files/x.opus 3                      # per-function profile (QEMU trace)
python3 toc.py files/*.opus                        # SILK/hybrid/CELT modes and transitions
```
`res_*.txt`: raw results obtained during the evaluation.

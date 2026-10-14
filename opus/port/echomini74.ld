/* Link the Opus plug-in into the areas of module 74 freed by removing the WMA decoder.
 * HiFi-core view: code at 0, data at 0x01020000. See re/REPORT.md section 9. */
MEMORY
{
    T1 (rx)  : ORIGIN = 0x00002ec4, LENGTH = 0x00010138 - 0x00002ec4  /* WMA library            */
    T2 (rx)  : ORIGIN = 0x000110a4, LENGTH = 0x00012800 - 0x000110a4  /* WMA tables (part 1)    */
    T3 (rx)  : ORIGIN = 0x00012858, LENGTH = 0x000162c0 - 0x00012858  /* WMA tables (part 2)    */
    CF (r)   : ORIGIN = 0x0102347c, LENGTH = 4                         /* CodecFunc[CODEC_WMA]   */
    D  (rw)  : ORIGIN = 0x01023480, LENGTH = 0x010267c0 - 0x01023480  /* WMA initialised data   */
    BZ (rw)  : ORIGIN = 0x0103cb58, LENGTH = 0x01047630 - 0x0103cb58  /* zeroed by the runtime; 0x0103cb18..54 = runtime event flags */
    BN (rw)  : ORIGIN = 0x01047640, LENGTH = 0x0105f2bc - 0x01047640  /* not zeroed (WAV uses it)*/
}

SECTIONS
{
    .codecfunc : { KEEP(*(.codecfunc)) } > CF

    /* --enable-non-contiguous-regions spills code over T1 -> T2 and constants over T3 -> D.
     * Constants are read through the data bus, so the data RAM is fine for them. */
    .text1 : { *(.text.OpusCodec) *(.text .text.*) } > T1
    .text2 : { *(.text .text.*) } > T2
    .rostr : { *(.rodata*.str1.*) } > D           /* mergeable strings: no spilling */
    .rodata3 : { *(.rodata .rodata.*) } > T3
    .rodataD : { *(.rodata .rodata.*) } > D

    .data  : { *(.data .data.*) } > D
    .bss (NOLOAD)    : { *(.bss .bss.* COMMON) } > BZ
    .noinit (NOLOAD) : { *(.noinit .noinit.*) } > BN

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}

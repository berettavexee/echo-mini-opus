/* Link the Vorbis plug-in into the areas of module 77 freed by removing the Rockchip Tremor
 * build. HiFi-core view: code at 0, data at 0x01020000. See docs/REPORT.md section 20. */
MEMORY
{
    T1 (rx)  : ORIGIN = 0x000029d0, LENGTH = 0x0000e054 - 0x000029d0  /* Ogg library code          */
    CF (r)   : ORIGIN = 0x0102d16c, LENGTH = 4                         /* CodecFunc[CODEC_OGG]      */
    D1 (rw)  : ORIGIN = 0x01023480, LENGTH = 0x01029888 - 0x01023480  /* library data (zeros)      */
    D2 (rw)  : ORIGIN = 0x010298a0, LENGTH = 0x0102d148 - 0x010298a0  /* library data (tables)     */
    BZ (rw)  : ORIGIN = 0x010434e0, LENGTH = 0x0105e998 - 0x010434e0  /* library BSS, zeroed by the
                                                                          runtime; 0x0105e998.. = event flags */
}
/* Kept for the runtime: 0x01029888-0x010298a0 (0x01029898 = PCM buffer pointers written by 0x3c6),
 * 0x0102d148-0x0102d184 (runtime variables, CodecFunc table at 0x0102d15c). */

SECTIONS
{
    .codecfunc : { KEEP(*(.codecfunc)) } > CF

    .text1   : { *(.text.VorbisCodec) *(.text .text.*) } > T1
    .rostr   : { *(.rodata*.str1.*) } > D2              /* mergeable strings: no spilling */
    .rodataT : { *(.rodata .rodata.*) } > T1            /* constants spill T1 -> D1 -> D2 */
    .rodata1 : { *(.rodata .rodata.*) } > D1
    .rodata2 : { *(.rodata .rodata.*) } > D2

    .data  : { *(.data .data.*) } > D2
    .bss (NOLOAD) : { *(.bss .bss.* COMMON) } > BZ

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) }
}

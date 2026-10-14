/* MPS2-AN385 (Cortex-M3): 4 MB SSRAM1 at 0, 4 MB SSRAM2/3 at 0x20000000 */
MEMORY { ROM (rx) : ORIGIN = 0x00000000, LENGTH = 4M
         RAM (rw) : ORIGIN = 0x20000000, LENGTH = 4M }
SECTIONS {
  .vectors : { KEEP(*(.vectors)) } > ROM
  .text    : { *(.text .text.*) *(.rodata .rodata.*) } > ROM
  .data    : { _sdata = .; *(.data .data.*) _edata = .; } > RAM AT > ROM
  _sidata = LOADADDR(.data);
  .bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON .noinit .noinit.*) _ebss = .; } > RAM
  _estack = ORIGIN(RAM) + LENGTH(RAM);
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) }
}

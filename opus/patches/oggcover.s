@ Replaces 0x03081a72..0x03081adc of the Ogg cover-art reader (overlay 18, case OGG at 0x030819b8).
@ Entry: 7 bytes of the page's first packet read: type at [sp+0x11c], next 6 bytes at [sp+0x110];
@ lacing values at r5 (= sp), segment count at [sp+0x108]; r7 = file handle, r6 = output,
@ r4 = granule (low word) of this page, passed through as the 4th argument.
@ "\x03vorbis" -> picture parser with packet length - 7; "OpusTags" -> skip 's', length - 8;
@ anything else -> rewind 7 bytes and skip the page (unchanged behaviour).
        .syntax unified
        .thumb
        .equ    base, _start - 0x03081a72
        .equ    ret_r0, base + 0x030818ac
        .equ    contpage, base + 0x03081adc
_start:
        ldrb.w  r0, [sp, #0x11c]
        cmp     r0, #0x4f               @ 'O'
        beq     opus
        cmp     r0, #3
        bne     skip
        movs    r2, #6
        .short  0xa149                  @ adr r1, 0x03081ba8 ("vorbis")
        add     r0, sp, #0x110
        bl      memcmp_
        cbnz    r0, skip
        movs    r0, #7                  @ header bytes already consumed
parse:  rsbs    r1, r0, #0              @ r1 = packet length on this page - header
        ldrb.w  r2, [sp, #0x108]
        movs    r0, #0
lp:     ldrb    r3, [r5, r0]
        adds    r1, r1, r3
        adds    r0, #1
        cmp     r3, #0xff
        bne     done
        cmp     r0, r2
        blt     lp
done:   mov     r2, r1
        mov     r3, r4
        mov     r1, r6
        mov     r0, r7
        bl      picparse
        b.n     ret_r0
skip:   mov     r2, r7
        movs    r1, #1
        movs    r0, #6
        mvns    r0, r0                  @ -7
        bl      fseek_
        ldrb.w  r1, [sp, #0x108]
        b.n     contpage
opus:   ldrb.w  r0, [sp, #0x113]        @ 'T' (OpusTags) or 'H' (OpusHead)
        cmp     r0, #0x54
        bne     skip
        movs    r0, #1                  @ skip the final 's'
        movs    r1, #1
        mov     r2, r7
        bl      fseek_
        movs    r0, #8
        b       parse
        nop
        nop

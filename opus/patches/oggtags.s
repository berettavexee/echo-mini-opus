@ Replaces 0x0306c052..0x0306c0bc of the resident Ogg Vorbis tag reader sub_0306bf94.
@ Entry state: 7 bytes of the first packet on this page were read: type byte at [sp+0x100],
@ next 6 bytes at [sp+0x110]; lacing values at r5 (= sp), segment count at [sp+0x104];
@ r7 = file handle, r8 = tag output, r6 = parser argument.
@ Vorbis "\x03vorbis" -> parse (header length 7), Opus "OpusTags" -> skip 's', parse (length 8),
@ anything else -> rewind 7 bytes and skip the page (unchanged behaviour).
        .syntax unified
        .thumb
        .global _start
        .equ vorbis_str, _start + (0x0306c238 - 0x0306c052)
        .equ ret0, _start + (0x0306c0e2 - 0x0306c052)
        .equ contpage, _start + (0x0306c0bc - 0x0306c052)
_start:
        ldrb.w  r0, [sp, #0x100]
        movs    r4, #7
        cmp     r0, #0x4f               @ 'O'
        beq     opus
        cmp     r0, #3
        bne     skip
        movs    r2, #6
        .short  0xa175                  @ adr r1, 0x0306c238 ("vorbis")
        add     r0, sp, #0x110
        bl      memcmp_
        cbnz    r0, skip
parse:  movs    r1, #0                  @ packet length on this page
        ldrb.w  r2, [sp, #0x104]
        mov     r0, r1
lp:     ldrb    r3, [r5, r0]
        cmp     r3, #0xff
        beq     full
        add     r1, r3
        b       done
full:   adds    r1, #0xff
        adds    r0, #1
        cmp     r0, r2
        blt     lp
done:   subs    r3, r1, r4
        mov     r2, r6
        mov     r1, r8
        mov     r0, r7
        bl      vparse
        b.n     ret0
skip:   mov     r2, r7
        movs    r1, #1
        movs    r0, #6
        mvns    r0, r0                  @ -7
        bl      fseek_
        ldrb.w  r1, [sp, #0x104]
        b.n     contpage
opus:   ldrb.w  r0, [sp, #0x113]        @ "pusTag": 'T' for OpusTags, 'H' for OpusHead
        cmp     r0, #0x54
        bne     skip
        movs    r0, #1                  @ skip the final 's'
        movs    r1, #1
        mov     r2, r7
        bl      fseek_
        movs    r4, #8
        b       parse
end:

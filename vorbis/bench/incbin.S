    .section .rodata.oggfile, "a"
    .global ogg_file, ogg_file_end
    .balign 4
ogg_file:
    .incbin OGG_FILE
ogg_file_end:

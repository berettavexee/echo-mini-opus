    .section .rodata.opusfile, "a"
    .global opus_file, opus_file_end
    .balign 4
opus_file:
    .incbin OPUS_FILE
opus_file_end:

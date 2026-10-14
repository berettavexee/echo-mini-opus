/* PC harness: drives OpusCodec() exactly like the HiFi runtime does.
 *   opustest in.opus out.raw [seek_ms seek.raw]
 * Writes 48 kHz stereo s16le, reports info fields and pseudo-stack high-water mark. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "opus.h"
#include "codec_abi.h"

int OpusCodec(int subfn, void *a1, void *a2, void *a3);
extern char echomini_opus_scratch[];

static FILE *in;
uint32_t host_read(void *buf, uint32_t n) { return (uint32_t)fread(buf, 1, n, in); }
int      host_seek(uint32_t off)          { return fseek(in, (long)off, SEEK_SET); }
uint32_t host_size(void) { long p = ftell(in), e; fseek(in, 0, SEEK_END); e = ftell(in); fseek(in, p, SEEK_SET); return (uint32_t)e; }

static uint32_t get(int subfn) { uint32_t v = 0; OpusCodec(subfn, &v, 0, 0); return v; }

static long play(FILE *out, long max_frames)
{
    long total = 0;
    int16_t *p; uint32_t n;
    OpusCodec(SUBFN_GETBUFFER, &p, &n, 0);                   /* buffer sent with "open OK"/seek */
    do {
        fwrite(p, 4, n, out);
        total += n;
        if (max_frames && total >= max_frames) break;
        if (OpusCodec(SUBFN_DECODE, 0, 0, 0) != 1) break;    /* runtime: message 6 = end */
        OpusCodec(SUBFN_GETBUFFER, &p, &n, 0);
    } while (1);
    return total;
}

int main(int argc, char **argv)
{
    FILE *out;
    long frames;
    size_t hw;
    if (argc < 3) { fprintf(stderr, "usage: %s in.opus out.raw [seek_ms seek.raw]\n", argv[0]); return 2; }
    in = fopen(argv[1], "rb");
    if (!in) { perror(argv[1]); return 1; }
    memset(echomini_opus_scratch, 0xA5, GLOBAL_STACK_SIZE);

    if (OpusCodec(SUBFN_OPEN_DEC, 0, 0, 0) != 1) { fprintf(stderr, "open failed\n"); return 1; }
    printf("decoder_size=%d rate=%u ch=%u bps=%u bitrate=%u length_ms=%u\n",
           opus_decoder_get_size(2), get(SUBFN_GETSAMPLERATE), get(SUBFN_GETCHANNELS),
           get(SUBFN_GETBPS), get(SUBFN_GETBITRATE), get(SUBFN_GETLENGTH));
    out = fopen(argv[2], "wb");
    frames = play(out, 0);
    fclose(out);
    printf("decoded_frames=%ld (%.3f s) time_ms=%u\n", frames, frames / 48000.0, get(SUBFN_GETTIME));

    if (argc >= 5) {
        uint32_t ms = (uint32_t)atoi(argv[3]);
        if (OpusCodec(SUBFN_SEEK, (void *)(uintptr_t)ms, 0, 0) != 1) { fprintf(stderr, "seek failed\n"); return 1; }
        OpusCodec(SUBFN_DECODE, 0, 0, 0);                    /* main core asks for data after 0xc */
        printf("after seek(%u): time_ms=%u\n", ms, get(SUBFN_GETTIME));
        out = fopen(argv[4], "wb");
        frames = play(out, 48000 * 5);
        fclose(out);
    }
    for (hw = GLOBAL_STACK_SIZE; hw > 0 && (unsigned char)echomini_opus_scratch[hw - 1] == 0xA5; hw--) ;
    printf("pseudostack_highwater=%zu\n", hw);
    OpusCodec(SUBFN_CLOSE, (void *)1, 0, 0);
    return 0;
}

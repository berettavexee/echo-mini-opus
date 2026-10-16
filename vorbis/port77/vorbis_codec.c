/*
 * Ogg Vorbis decoder plug-in for the ECHO MINI HiFi core (replaces the Rockchip Tremor build of
 * module 77, which uses _LOW_ACCURACY_ 8-bit tables). Full-precision Tremor "lowmem" core
 * (headers, synthesis, PCM output); Tremor's own Ogg layer (framing.c, vorbisfile.c) is not used.
 * The Ogg reader below streams the comment packet (tags, cover art: often 70+ KB) without
 * storing it and gives Tremor an empty comment header instead.
 *
 * Entry point: VorbisCodec(subfn, a1, a2, a3), registered in CodecFunc[CODEC_OGG] (0x0102d16c).
 * Behaviour of the stock module (docs/REPORT.md section 20):
 *   - the PCM goes to two 8 KB buffers that the runtime reserves at the end of its file buffer
 *     (pointers at 0x01029898, set by 0x3c6), at an offset of SRC_Num_Forehead samples
 *     (0x01022104);
 *   - each DECODE produces 512 stereo frames (mono is duplicated, CHANNELS still reports 1);
 *   - times are in ms, the bitrate in bit/s.
 * The same file builds for the QEMU bench (HOST_TEST).
 */
#include <stdint.h>
#include <string.h>
#include "ivorbiscodec.h"
#include "codec_internal.h"
#include "codec_abi.h"

#define BLOCK_FRAMES 512                       /* frames per DECODE, as the stock module */
#define MAX_PACKET   16384                     /* setup header ~4 KB, audio packets < 2 KB */
#define SCAN_CHUNK   2048
#define MAX_ERRORS   64                        /* consecutive undecodable packets before EOS */

/* ---------------- platform ---------------- */
#ifdef HOST_TEST
uint32_t host_read(void *buf, uint32_t n);
int      host_seek(uint32_t off);
uint32_t host_size(void);
#define F_READ(b, n)  host_read((b), (n))
#define F_SEEK(o)     host_seek(o)
#define F_SIZE()      host_size()
static int16_t host_pcm[2][BLOCK_FRAMES * 2];
#define PCM_BUF(i)    (host_pcm[i])
#else
#define F_READ(b, n)  FILE_OPS->read((b), (n), FILE_HANDLE)
#define F_SEEK(o)     FILE_OPS->seek((int32_t)(o), 0, FILE_HANDLE)
#define F_SIZE()      FILE_OPS->length(FILE_HANDLE)
/* Output buffers owned by the runtime of module 77 (written by 0x3c6 at 0x404). */
#define OGG_PCM_OUT       ((int16_t *volatile *)0x01029898)
#define SRC_NUM_FOREHEAD  (*(volatile uint32_t *)0x01022104)
#define PCM_BUF(i)        (OGG_PCM_OUT[i] + SRC_NUM_FOREHEAD)
#endif

void rt_heap_reset(void);

/* ---------------- state ---------------- */
static uint8_t pkt[MAX_PACKET] __attribute__((aligned(8)));
static uint8_t scan[SCAN_CHUNK + 27] __attribute__((aligned(8)));
static int16_t mono[BLOCK_FRAMES];
static vorbis_info      vi;
static vorbis_comment   vc;
static vorbis_dsp_state *vd;

static struct {
    int      open, eos, sel, errors;
    uint32_t serial, file_size, data_start, page_pos;
    uint32_t rate, channels, bitrate, length_ms;
    int64_t  last_granule;
    int64_t  pos;                              /* stream position of the next output frame   */
    int64_t  discard;                          /* frames to drop after a seek                 */
    int64_t  target;                           /* seek target (frames)                        */
    int      resync;                           /* after a seek: position unknown until a granule */
    int64_t  packetno;
    /* Ogg page reader */
    uint8_t  lace[255];
    int      nsegs, seg;
    int64_t  page_granule;
    uint8_t  page_flags;
    /* last packet returned by next_packet() */
    int64_t  pkt_granule;
    int      pkt_eos;
} s;

/* ---------------- Ogg reading ---------------- */
static int rd(void *b, uint32_t n)
{
    uint32_t got = F_READ(b, n);
    s.page_pos += got;
    return got == n;
}

static uint32_t le32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static int64_t  le64(const uint8_t *p) { return (int64_t)((uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32); }

/* Read the next page header of our stream (resynchronising on "OggS" if needed). */
static int next_page(void)
{
    uint8_t h[27];
    for (;;) {
        if (!rd(h, 27))
            return 0;
        while (memcmp(h, "OggS", 4) != 0 || h[4] != 0) {        /* resync byte by byte */
            memmove(h, h + 1, 26);
            if (!rd(h + 26, 1))
                return 0;
        }
        s.nsegs = h[26];
        s.seg = 0;
        if (!rd(s.lace, s.nsegs))
            return 0;
        if (!s.serial)
            s.serial = le32(h + 14);
        if (le32(h + 14) == s.serial)
            break;
        {                                                        /* foreign stream: skip page */
            int i, len = 0;
            for (i = 0; i < s.nsegs; i++)
                len += s.lace[i];
            while (len > 0) {
                int c = len > SCAN_CHUNK ? SCAN_CHUNK : len;
                if (!rd(scan, c))
                    return 0;
                len -= c;
            }
        }
    }
    s.page_granule = le64(h + 6);
    s.page_flags = h[5];
    return 1;
}

/* Next complete packet: returns its length (0 = end of stream, -1 = longer than MAX_PACKET:
 * the first MAX_PACKET bytes are in pkt[], the rest was streamed without being stored).
 * Sets pkt_granule (page granule if the packet is the last one completed on its page, else -1)
 * and pkt_eos. */
static int next_packet(void)
{
    int len = 0, too_big = 0, i;
    for (;;) {
        if (s.seg >= s.nsegs) {
            if (!next_page())
                return 0;
            if (len == 0 && (s.page_flags & 1)) {                /* continuation of a lost packet */
                while (s.seg < s.nsegs) {
                    int l = s.lace[s.seg++];
                    if (!rd(scan, l)) return 0;
                    if (l < 255) break;
                }
                continue;
            }
        }
        while (s.seg < s.nsegs) {
            int l = s.lace[s.seg++];
            if (len + l <= MAX_PACKET) {
                if (!rd(pkt + len, l)) return 0;
            } else {
                if (!rd(scan, l)) return 0;
                too_big = 1;
            }
            len += l;
            if (l < 255) {
                int last = 1;
                for (i = s.seg; i < s.nsegs; i++)
                    if (s.lace[i] < 255) { last = 0; break; }
                s.pkt_granule = last ? s.page_granule : -1;
                s.pkt_eos = last && (s.page_flags & 4);
                return too_big ? -1 : len;
            }
        }
    }
}

/* Scan forward from 'off' for the first page of our stream; returns its offset or -1. */
static int32_t find_page(uint32_t off, int64_t *granule)
{
    uint32_t scan0 = off;
    int keep = 0;
    if (F_SEEK(off) != 0) return -1;
    for (;;) {
        int n = (int)F_READ(scan + keep, SCAN_CHUNK), total, i;
        if (n <= 0) return -1;
        total = keep + n;
        for (i = 0; i + 27 <= total; i++) {
            if (scan[i] == 'O' && !memcmp(scan + i, "OggS", 4) && scan[i + 4] == 0 &&
                le32(scan + i + 14) == s.serial) {
                *granule = le64(scan + i + 6);
                return (int32_t)(scan0 + i);
            }
        }
        keep = total < 26 ? total : 26;                          /* header across chunks */
        memmove(scan, scan + total - keep, keep);
        scan0 += total - keep;
    }
}

/* Granule of the last page in the file (end of stream). */
static int64_t last_granule(void)
{
    uint32_t back = 65536;
    for (;;) {
        uint32_t off = s.file_size > back ? s.file_size - back : s.data_start;
        int64_t g, best = -1;
        int32_t p = (int32_t)off;
        while ((p = find_page((uint32_t)p, &g)) >= 0) {
            if (g != -1) best = g;
            p += 27;
        }
        if (best >= 0 || off <= s.data_start)
            return best;
        back *= 2;
    }
}

static int restart_at(uint32_t off)
{
    if (F_SEEK(off) != 0) return 0;
    s.page_pos = off;
    s.nsegs = s.seg = 0;
    return 1;
}

/* ---------------- 32-bit time conversions ---------------- */
static uint32_t frames_to_ms(int64_t f)
{
    uint32_t v;
    if (f <= 0 || !s.rate) return 0;
    if (f > 0xFFFFFFFF) f = 0xFFFFFFFF;
    v = (uint32_t)f;
    return v / s.rate * 1000 + v % s.rate * 1000 / s.rate;
}

static int64_t ms_to_frames(uint32_t ms) { return (int64_t)(ms / 1000) * s.rate + (ms % 1000) * s.rate / 1000; }

/* ---------------- decoding ---------------- */
static int header_in(int len, int b_o_s)
{
    ogg_buffer     ob;
    ogg_reference  ref;
    ogg_packet     op;
    memset(&ob, 0, sizeof(ob));
    memset(&ref, 0, sizeof(ref));
    memset(&op, 0, sizeof(op));
    ob.data = pkt;
    ob.size = len;
    ob.refcount = 1;
    ref.buffer = &ob;
    ref.length = len;
    op.packet = &ref;
    op.bytes = len;
    op.b_o_s = b_o_s;
    op.granulepos = -1;
    op.packetno = s.packetno++;
    return vorbis_dsp_headerin(&vi, &vc, &op);
}

/* Decode one audio packet; returns 0 at end of stream. */
static int feed_packet(void)
{
    ogg_buffer     ob;
    ogg_reference  ref;
    ogg_packet     op;
    int len = next_packet();
    if (len == 0)
        return 0;
    if (len < 0) {                                /* oversized audio packet: corrupt, skip */
        s.packetno++;
        return ++s.errors <= MAX_ERRORS;
    }
    memset(&ob, 0, sizeof(ob));
    memset(&ref, 0, sizeof(ref));
    memset(&op, 0, sizeof(op));
    ob.data = pkt;
    ob.size = len;
    ob.refcount = 1;
    ref.buffer = &ob;
    ref.length = len;
    op.packet = &ref;
    op.bytes = len;
    op.e_o_s = s.pkt_eos;
    op.granulepos = s.pkt_granule;
    op.packetno = s.packetno++;
    if (vorbis_dsp_synthesis(vd, &op, 1) != 0)
        return ++s.errors <= MAX_ERRORS;
    s.errors = 0;
    if (s.resync && op.granulepos != -1) {        /* the frames now available end at the granule */
        s.pos = op.granulepos - vorbis_dsp_pcmout(vd, 0, 0);
        s.discard = s.target > s.pos ? s.target - s.pos : 0;
        s.resync = 0;
    }
    return 1;
}

/* Produce 'frames' interleaved frames of the stream's channel count; returns frames produced. */
static uint32_t produce(int16_t *dst, uint32_t frames)
{
    uint32_t got = 0;
    while (got < frames) {
        int n = vorbis_dsp_pcmout(vd, 0, 0);
        if (n > 0) {
            if (s.resync) {                       /* before the first granule: position unknown */
                vorbis_dsp_read(vd, n);
                continue;
            }
            if (s.discard > 0) {                  /* seek: drop frames before the target */
                int d = s.discard < n ? (int)s.discard : n;
                vorbis_dsp_read(vd, d);
                s.discard -= d;
                s.pos += d;
                continue;
            }
            if ((uint32_t)n > frames - got)
                n = (int)(frames - got);
            n = vorbis_dsp_pcmout(vd, dst + got * s.channels, n);
            vorbis_dsp_read(vd, n);
            got += (uint32_t)n;
            s.pos += n;
            continue;
        }
        if (s.eos || !feed_packet()) {
            s.eos = 1;
            break;
        }
    }
    return got;
}

static int decode_block(int idx)
{
    int16_t *out = PCM_BUF(idx);
    uint32_t got, i;
    if (s.eos)
        return 0;
    if (s.channels == 2) {
        got = produce(out, BLOCK_FRAMES);
        if (got < BLOCK_FRAMES)
            memset(out + 2 * got, 0, (BLOCK_FRAMES - got) * 4);
    } else {
        got = produce(mono, BLOCK_FRAMES);
        if (got < BLOCK_FRAMES)
            memset(mono + got, 0, (BLOCK_FRAMES - got) * 2);
        for (i = 0; i < BLOCK_FRAMES; i++)
            out[2 * i] = out[2 * i + 1] = mono[i];
    }
    return got > 0;
}

static void close_stream(void)
{
    if (vd)
        vorbis_dsp_destroy(vd);
    vd = 0;
    vorbis_info_clear(&vi);
    vorbis_comment_clear(&vc);
    memset(&s, 0, sizeof(s));
    rt_heap_reset();
}

/* Empty comment header given to Tremor in place of the file's own (never stored). */
static const uint8_t empty_comment[16] = { 3, 'v', 'o', 'r', 'b', 'i', 's', 0, 0, 0, 0, 0, 0, 0, 0, 1 };

#ifdef VORBIS_DEBUG
volatile int vorbis_fail_line;
#define FAIL() do { vorbis_fail_line = __LINE__; goto fail; } while (0)
#else
#define FAIL() goto fail
#endif

static int open_stream(void)
{
    int len;
    close_stream();
    vorbis_info_init(&vi);
    vorbis_comment_init(&vc);
    s.file_size = F_SIZE();
    if (s.file_size < 58 || !restart_at(0))
        FAIL();
    /* 1. identification header */
    len = next_packet();
    if (len < 30 || pkt[0] != 1 || memcmp(pkt + 1, "vorbis", 6) || header_in(len, 1) != 0)
        FAIL();
    if (vi.channels < 1 || vi.channels > 2)
        FAIL();
    /* 2. comment header: streamed, only its first 7 bytes are checked */
    len = next_packet();
    if (len == 0 || pkt[0] != 3 || memcmp(pkt + 1, "vorbis", 6))
        FAIL();
    memcpy(pkt, empty_comment, sizeof(empty_comment));
    if (header_in(sizeof(empty_comment), 0) != 0)
        FAIL();
    /* 3. setup header (codebooks): must fit in pkt[] */
    len = next_packet();
    if (len <= 0 || pkt[0] != 5 || header_in(len, 0) != 0)
        FAIL();
    /* audio starts on the next page boundary */
    while (s.seg < s.nsegs) {
        int l = s.lace[s.seg++];
        if (!rd(scan, l))
            FAIL();
    }
    s.data_start = s.page_pos;
    s.rate = (uint32_t)vi.rate;
    s.channels = (uint32_t)vi.channels;
    s.last_granule = last_granule();
    s.length_ms = frames_to_ms(s.last_granule);
    if (vi.bitrate_nominal > 0)
        s.bitrate = (uint32_t)vi.bitrate_nominal;
    else if (s.length_ms)
        s.bitrate = ((s.file_size - s.data_start) / s.length_ms * 8 +
                     (s.file_size - s.data_start) % s.length_ms * 8 / s.length_ms) * 1000;
    if (!s.bitrate)
        s.bitrate = 128000;
    if (!restart_at(s.data_start))
        FAIL();
    vd = vorbis_dsp_create(&vi);
    if (!vd)
        FAIL();
    s.open = 1;
    s.sel = 0;
    if (!decode_block(0))                      /* first block, handed out right after OPEN */
        FAIL();
    return 1;
fail:
    close_stream();
    return 0;
}

/* Page-bisection seek: decoding restarts at the last page whose granule is <= target. Its
 * packets end before the target, so their output is dropped until the page granule gives the
 * exact position (as vorbisfile does); then the frames before the target are dropped. */
static int seek_ms(uint32_t ms)
{
    int64_t target = ms_to_frames(ms), g;
    uint32_t lo = s.data_start, hi = s.file_size, best = s.data_start;
    int i;
    for (i = 0; i < 24 && hi > lo + 4096; i++) {
        uint32_t mid = lo + (hi - lo) / 2;
        int32_t p = find_page(mid, &g);
        if (p < 0 || g == -1 || g > target) hi = mid;
        else { lo = (uint32_t)p + 27; best = (uint32_t)p; }
    }
    if (!restart_at(best))
        return 0;
    vorbis_dsp_restart(vd);
    s.target = target;
    s.eos = 0;
    s.errors = 0;
    if (best == s.data_start) {                   /* from the start: normal granule handling */
        s.packetno = 3;
        s.pos = 0;
        s.discard = target;
        s.resync = 0;
    } else {
        s.packetno += 2;                          /* discontinuity for Tremor's granule tracking */
        s.resync = 1;
    }
    return 1;
}

/* ---------------- codec entry ---------------- */
int VorbisCodec(int subfn, void *a1, void *a2, void *a3)
{
    (void)a3;
    switch (subfn) {
    case SUBFN_GETNAME:       *(const char **)a1 = "Ogg Vorbis";  return 1;
    case SUBFN_GETBITRATE:    *(uint32_t *)a1 = s.bitrate;        return 1;
    case SUBFN_GETSAMPLERATE: *(uint32_t *)a1 = s.rate;           return 1;
    case SUBFN_GETCHANNELS:   *(uint32_t *)a1 = s.channels;       return 1;
    case SUBFN_GETBPS:        *(uint32_t *)a1 = 16;               return 1;
    case SUBFN_GETLENGTH:     *(uint32_t *)a1 = s.length_ms;      return 1;
    case SUBFN_GETTIME:       *(uint32_t *)a1 = frames_to_ms(s.pos); return 1;
    case SUBFN_OPEN_DEC:
        return open_stream();
    case SUBFN_GETBUFFER:
        *(int16_t **)a1 = PCM_BUF(s.sel);
        *(uint32_t *)a2 = BLOCK_FRAMES;
        return 1;
    case SUBFN_DECODE: {
        int nx = s.sel ^ 1;
        if (!s.open || !decode_block(nx))
            return 0;                             /* end of stream -> message 6 */
        s.sel = nx;
        return 1;
    }
    case SUBFN_SEEK:
        if (!s.open)
            return 0;
        if (!seek_ms((uint32_t)(uintptr_t)a1) && !seek_ms(0))
            return 0;
        return 1;
    case SUBFN_CLOSE:
        close_stream();
        return 1;
    default:
        return 0;
    }
}

#ifndef HOST_TEST
/* CodecFunc[CODEC_OGG] slot at 0x0102d16c (see echomini77.ld). */
__attribute__((section(".codecfunc"), used))
const codec_fn echomini_codecfunc_ogg = (codec_fn)VorbisCodec;
#endif

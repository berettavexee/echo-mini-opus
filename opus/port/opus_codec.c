/*
 * Ogg Opus decoder plug-in for the ECHO MINI HiFi core (replaces the WMA decoder, module 74).
 * Entry point: OpusCodec(subfn, a1, a2, a3), registered in CodecFunc[CODEC_WMA].
 * The ABI is described in ../codec_abi.h. The same file builds on a PC (HOST_TEST) for validation.
 */
#include <stdint.h>
#include <string.h>
#include "opus.h"
#include "codec_abi.h"

/* ---------------- platform: file access ---------------- */
#ifdef HOST_TEST
uint32_t host_read(void *buf, uint32_t n);
int      host_seek(uint32_t off);
uint32_t host_size(void);
#define F_READ(b, n)  host_read((b), (n))
#define F_SEEK(o)     host_seek(o)
#define F_SIZE()      host_size()
#define NOINIT
#else
#define F_READ(b, n)  FILE_OPS->read((b), (n), FILE_HANDLE)
#define F_SEEK(o)     FILE_OPS->seek((int32_t)(o), 0, FILE_HANDLE)
#define F_SIZE()      FILE_OPS->length(FILE_HANDLE)
/* Large buffers go to RAM the runtime does not zero (see echomini74.ld). */
#define NOINIT __attribute__((section(".noinit")))
#endif

/* ---------------- sizes ---------------- */
#define MAX_FRAME      5760            /* 120 ms at 48 kHz, largest Opus packet  */
#define TARGET_FRAMES  1920            /* ~40 ms handed to the main core per call */
#define BUF_FRAMES     (TARGET_FRAMES + MAX_FRAME)
#define MAX_PACKET     8192
#define PREROLL        3840            /* 80 ms decoder convergence after a seek  */
#define SCAN_CHUNK     2048

#ifndef GLOBAL_STACK_SIZE
#define GLOBAL_STACK_SIZE 120000
#endif
char echomini_opus_scratch[GLOBAL_STACK_SIZE] __attribute__((aligned(8)));
NOINIT static int16_t pcm[2][BUF_FRAMES * 2] __attribute__((aligned(8)));
#ifndef DEC_MEM_SIZE
#define DEC_MEM_SIZE 32768
#endif
NOINIT static uint8_t dec_mem[DEC_MEM_SIZE] __attribute__((aligned(8)));
static uint8_t pkt[MAX_PACKET] __attribute__((aligned(8)));
static uint8_t scan[SCAN_CHUNK + 27] __attribute__((aligned(8)));

/* ---------------- state (zero-initialised .bss) ---------------- */
static struct {
    OpusDecoder *dec;
    uint32_t serial, file_size, data_start;
    int      pre_skip;
    int64_t  last_granule;          /* granule of the final page = end of stream          */
    int64_t  pos;                   /* 48 kHz position of the next decoded sample          */
    int64_t  discard_until;         /* drop output before this position (pre-skip, seek)   */
    uint32_t length_ms, bitrate;
    int      ready;                 /* buffer index handed out by GETBUFFER                */
    uint32_t frames[2];
    int      eos;
#if defined(OPUS_DIAG) || !defined(ECHO_STRIP_DIAG)
    int      diag;                  /* != 0: diagnostic beeps instead of audio (see diag_open) */
#endif
    /* Ogg page reader */
    uint8_t  lace[255];
    int      nsegs, seg;
    uint32_t page_pos;              /* file offset of the next byte to read                */
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

/* Read the next page header (resynchronising on "OggS" if needed). */
static int next_page(int64_t *granule, uint8_t *flags)
{
    uint8_t h[27];
    if (!rd(h, 27))
        return 0;
    while (memcmp(h, "OggS", 4) != 0 || h[4] != 0) {        /* resync byte by byte */
        memmove(h, h + 1, 26);
        if (!rd(h + 26, 1))
            return 0;
    }
    if (s.serial && le32(h + 14) != s.serial) {               /* foreign stream: skip page */
        int n = h[26], i, len = 0;
        if (!rd(s.lace, n)) return 0;
        for (i = 0; i < n; i++) len += s.lace[i];
        while (len > 0) {
            int c = len > SCAN_CHUNK ? SCAN_CHUNK : len;
            if (!rd(scan, c)) return 0;
            len -= c;
        }
        return next_page(granule, flags);
    }
    if (granule) *granule = le64(h + 6);
    if (flags) *flags = h[5];
    if (!s.serial) s.serial = le32(h + 14);
    s.nsegs = h[26];
    s.seg = 0;
    return rd(s.lace, s.nsegs);
}

/* Return the next complete packet length (0 = end of stream, -1 = oversized packet skipped). */
static int next_packet(void)
{
    int len = 0, too_big = 0;
    for (;;) {
        if (s.seg >= s.nsegs) {
            uint8_t fl;
            if (!next_page(NULL, &fl))
                return 0;
            if (len == 0 && (fl & 1)) {                        /* continuation of a lost packet */
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
            if (l < 255)
                return too_big ? -1 : len;
        }
    }
}

/* Scan forward from 'off' for the first page of our stream; returns its offset or -1. */
static int32_t find_page(uint32_t off, int64_t *granule)
{
    uint32_t scan0 = off;                  /* file offset of scan[0] */
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
        keep = total < 26 ? total : 26;    /* a header may straddle the chunk boundary */
        memmove(scan, scan + total - keep, keep);
        scan0 += total - keep;
    }
}

/* Granule of the last page in the file (end of stream). */
static int64_t last_granule(void)
{
    uint32_t back = 65536;
    while (1) {
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

/* Position the reader on the page starting at 'off'. */
static int restart_at(uint32_t off)
{
    if (F_SEEK(off) != 0) return 0;
    s.page_pos = off;
    s.nsegs = s.seg = 0;
    return 1;
}

/* ---------------- decoding ---------------- */
/* Returns 0 on success, or the failing step (1..9) that the diagnostic mode beeps out. */
static int open_stream(void)
{
    int n, ch, family;
    int64_t g;
    memset(&s, 0, sizeof(s));
    s.file_size = F_SIZE();
    if (s.file_size < 47) return 1;
    if (!restart_at(0)) return 2;

    n = next_packet();                                         /* identification header */
    if (n <= 0) return 3;
    if (n < 19 || memcmp(pkt, "OpusHead", 8) != 0 || (pkt[8] >> 4) != 0)
        return 4;
    ch = pkt[9];
    s.pre_skip = pkt[10] | pkt[11] << 8;
    family = pkt[18];
    if (ch < 1 || ch > 2 || family > 1)                        /* stereo/mono only */
        return 5;
    if ((uint32_t)opus_decoder_get_size(2) > sizeof(dec_mem))
        return 6;
    s.dec = (OpusDecoder *)dec_mem;
    if (opus_decoder_init(s.dec, 48000, 2) != OPUS_OK)
        return 6;
    {
        int16_t gain = (int16_t)(pkt[16] | pkt[17] << 8);      /* Q7.8 dB output gain */
        if (gain) opus_decoder_ctl(s.dec, OPUS_SET_GAIN(gain));
    }
    /* Comment header: always the second packet (RFC 7845). With cover art and lyrics it can
     * span dozens of pages and exceed MAX_PACKET; next_packet() then skips it and returns -1. */
    n = next_packet();
    if (n == 0 || (n > 0 && (n < 8 || memcmp(pkt, "OpusTags", 8) != 0)))
        return 7;
    /* Audio starts on the next page boundary. */
    while (s.seg < s.nsegs) {
        int l = s.lace[s.seg++];
        if (!rd(scan, l)) return 7;
    }
    s.data_start = s.page_pos;

    g = last_granule();
    s.last_granule = g > s.pre_skip ? g : 0;
    if (s.last_granule) {
        uint32_t samples = (uint32_t)(s.last_granule - s.pre_skip);
        s.length_ms = samples / 48;
#ifdef ECHO_DIV32
        /* kbit/s = bytes * 8 / ms, in 32 bits (no 64-bit division): q*8 + r*8/ms, r < ms.
         * Same kbps as the exact value, which is all the player displays. */
        if (s.length_ms) {
            uint32_t bytes = s.file_size - s.data_start;
            uint32_t q = bytes / s.length_ms, r = bytes % s.length_ms;
            s.bitrate = (q * 8 + r * 8 / s.length_ms) * 1000;
        }
#else
        s.bitrate = samples ? (uint32_t)((uint64_t)(s.file_size - s.data_start) * 8 * 48000 / samples) : 0;
#endif
    }
    if (!s.bitrate) s.bitrate = 128000;

    if (!restart_at(s.data_start)) return 8;
    s.pos = 0;
    s.discard_until = s.pre_skip;
    return 0;
}

#if defined(OPUS_DIAG) || !defined(ECHO_STRIP_DIAG)
/* ---------------- diagnostic mode ----------------
 * When OPEN fails on the device, the main core would only show "Format Not Supported!".
 * Instead the file "plays" 60 s of beeps: N beeps of 150 ms (1 kHz) then 1 s of silence,
 * N = failing step of open_stream() (9 = no audio decoded by the first fill). */
#define DIAG_LEN_MS 60000
static const int16_t sine48[48] = {  /* 1 kHz at 48 kHz, -10 dBFS */
    0,1305,2588,3827,5000,6088,7071,7934,8660,9239,9659,9914,10000,9914,9659,9239,8660,7934,7071,6088,5000,3827,2588,1305,0,-1305,-2588,-3827,-5000,-6088,-7071,-7934,-8660,-9239,-9659,-9914,-10000,-9914,-9659,-9239,-8660,-7934,-7071,-6088,-5000,-3827,-2588,-1305};

static uint32_t diag_fill(int idx)
{
    uint32_t i, period = (uint32_t)s.diag * 14400 + 48000;    /* N x (150+150 ms) + 1 s */
    int16_t *out = pcm[idx];
    if (s.pos >= (int64_t)DIAG_LEN_MS * 48) return 0;
    for (i = 0; i < TARGET_FRAMES; i++, s.pos++) {
        uint32_t t = (uint32_t)(s.pos % period);
        int16_t v = (t < (uint32_t)s.diag * 14400 && t % 14400 < 7200) ? sine48[t % 48] : 0;
        out[2 * i] = out[2 * i + 1] = v;
    }
    return TARGET_FRAMES;
}

static int diag_open(int step)
{
    memset(&s, 0, sizeof(s));
    s.diag = step;
    s.length_ms = DIAG_LEN_MS;
    s.bitrate = 1536000;
    s.ready = 0;
    s.frames[0] = diag_fill(0);
    return 1;
}
#endif

/* Decode into pcm[idx] until TARGET_FRAMES frames are ready. Returns frames produced. */
static uint32_t fill(int idx)
{
    uint32_t have = 0;
    while (have < TARGET_FRAMES && !s.eos) {
        int16_t *out = pcm[idx] + have * 2;
        int len = next_packet(), n, skip = 0;
        if (len == 0) { s.eos = 1; break; }
        if (len < 0) continue;
        n = opus_decode(s.dec, pkt, len, out, MAX_FRAME, 0);
        if (n < 0) continue;                                   /* corrupt packet: drop it */
        if (s.pos < s.discard_until) {                         /* pre-skip / seek pre-roll */
            int64_t d = s.discard_until - s.pos;
            skip = d > n ? n : (int)d;
        }
        if (s.last_granule && s.pos + n > s.last_granule) {    /* end trimming */
            int64_t keep = s.last_granule - s.pos;
            n = keep < 0 ? 0 : (int)keep;
            s.eos = 1;
            if (skip > n) skip = n;
        }
        s.pos += n > skip ? n : skip;
        if (skip) memmove(out, out + skip * 2, (size_t)(n - skip) * 4);
        have += (uint32_t)(n - skip);
    }
    return have;
}

static int seek_ms(uint32_t ms)
{
    int64_t target = (int64_t)ms * 48 + s.pre_skip, g;
    int64_t want = target - PREROLL;
    uint32_t lo = s.data_start, hi = s.file_size, best = s.data_start;
    int64_t best_g = 0;
    int i;
    if (want < 0) want = 0;
    /* Bisection on page granules: last page whose granule <= want. */
    for (i = 0; i < 24 && hi > lo + 4096; i++) {
        uint32_t mid = lo + (hi - lo) / 2;
        int32_t p = find_page(mid, &g);
        if (p < 0 || g == -1 || g > want) hi = mid;
        else { lo = (uint32_t)p + 27; best = (uint32_t)p; best_g = g; }
    }
    /* Packets after the page at 'best' start at best_g; skip that page's own packets. */
    if (!restart_at(best)) return 0;
    if (best != s.data_start) {
        uint8_t fl;
        int64_t pg;
        if (!next_page(&pg, &fl)) return 0;
        while (s.seg < s.nsegs) { int l = s.lace[s.seg++]; if (!rd(scan, l)) return 0; }
        s.pos = best_g;
    } else {
        s.pos = 0;
    }
    opus_decoder_ctl(s.dec, OPUS_RESET_STATE);
    s.discard_until = target > s.pre_skip ? target : s.pre_skip;
    s.eos = 0;
    return 1;
}

static uint32_t now_ms(void)
{
#if defined(OPUS_DIAG) || !defined(ECHO_STRIP_DIAG)
    int64_t p = s.diag ? s.pos : s.pos - s.pre_skip;
#else
    int64_t p = s.pos - s.pre_skip;
#endif
#ifdef ECHO_DIV32
    if (p <= 0) return 0;
    if (p > 0xFFFFFFFF) return 0xFFFFFFFFu / 48;               /* > 24.8 h: saturate */
    return (uint32_t)p / 48;
#else
    return p > 0 ? (uint32_t)(p / 48) : 0;
#endif
}

#ifdef OPUS_DIAG
#define DIAG_OPEN(step) diag_open(step)
#else
#define DIAG_OPEN(step) 0
#endif

/* ---------------- codec entry ---------------- */
int OpusCodec(int subfn, void *a1, void *a2, void *a3)
{
    (void)a3;
    switch (subfn) {
    case SUBFN_GETNAME:       *(const char **)a1 = "Ogg Opus"; return 1;
    case SUBFN_GETARTIST:
    case SUBFN_GETTITLE:      return 0;
    case SUBFN_GETBITRATE:    *(uint32_t *)a1 = s.bitrate;   return 1;
    case SUBFN_GETSAMPLERATE: *(uint32_t *)a1 = 48000;       return 1;
    case SUBFN_GETCHANNELS:   *(uint32_t *)a1 = 2;           return 1;
    case SUBFN_GETLENGTH:     *(uint32_t *)a1 = s.length_ms; return 1;
    case SUBFN_GETTIME:       *(uint32_t *)a1 = now_ms();    return 1;
    case SUBFN_GETBPS:        *(uint32_t *)a1 = 16;          return 1;
    case SUBFN_OPEN_DEC: {
        int step = open_stream();
        if (step) return DIAG_OPEN(step);
        s.ready = 0;
        s.frames[0] = fill(0);                                 /* first buffer, sent with "open OK" */
        if (!s.frames[0]) return DIAG_OPEN(9);
        return 1;
    }
    case SUBFN_GETBUFFER:
        *(int16_t **)a1 = pcm[s.ready];
        *(uint32_t *)a2 = s.frames[s.ready];
        return 1;
    case SUBFN_DECODE: {
        int nx = s.ready ^ 1;
#if defined(OPUS_DIAG) || !defined(ECHO_STRIP_DIAG)
        uint32_t f = s.diag ? diag_fill(nx) : fill(nx);
#else
        uint32_t f = fill(nx);
#endif
        if (!f) return 0;                                      /* end of stream -> message 6 */
        s.frames[nx] = f;
        s.ready = nx;
        return 1;
    }
    case SUBFN_SEEK:
#if defined(OPUS_DIAG) || !defined(ECHO_STRIP_DIAG)
        if (s.diag) { s.pos = (int64_t)(uint32_t)(uintptr_t)a1 * 48; return 1; }
#endif
        if (!seek_ms((uint32_t)(uintptr_t)a1)) return 0;
        return 1;
    case SUBFN_CLOSE:
        return 1;
    case SUBFN_OPEN_ENC:
    case SUBFN_SETBUFFER:
    case SUBFN_ENCODE:
    default:
        return 0;
    }
}

#ifndef HOST_TEST
/* CodecFunc[CODEC_WMA] slot at 0x0102347c (see echomini74.ld). */
__attribute__((section(".codecfunc"), used))
const codec_fn echomini_codecfunc_wma = (codec_fn)OpusCodec;
#endif

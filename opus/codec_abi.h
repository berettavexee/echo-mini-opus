/*
 * ECHO MINI V3.9.0 (HIFIEC39.IMG): HiFi-core codec module ABI.
 * Reverse engineered from module 74 (WMA) and its main-core server, module 43.
 * Addresses are valid for module 74 only: each module is linked separately.
 * Names are inferred from behaviour. Values marked (?) are unconfirmed.
 */
#ifndef ECHOMINI_CODEC_ABI_H
#define ECHOMINI_CODEC_ABI_H
#include <stdint.h>

/* ---- CurrentCodec (main 0x0304af7c, HiFi 0x01022214) ---- */
enum { CODEC_MP3, CODEC_WMA, CODEC_AAC, CODEC_WAV, CODEC_OGG, CODEC_APE,
       CODEC_FLAC, CODEC_ALAC, CODEC_DFF, CODEC_DSF, CODEC_NONE = 0xFF };

/* ---- Decoder entry: int Codec(int subfn, void *a1, void *a2, void *a3) ----
 * Registered in CodecFunc[CurrentCodec] (module 74: table 0x01023478, slot 1 @0x0102347c).
 * Return 1 = success, 0 = failure (the wrappers return -1 when CurrentCodec == 0xFF). */
typedef int (*codec_fn)(int subfn, void *a1, void *a2, void *a3);
#define SUBFN_GETNAME        0   /* *(char**)a1 = name                 (main never asks)    */
#define SUBFN_GETARTIST      1
#define SUBFN_GETTITLE       2
#define SUBFN_GETBITRATE     3   /* *(u32*)a1 -> info.bitrate (open must return !=0)        */
#define SUBFN_GETSAMPLERATE  4   /* *(u32*)a1 -> info.samplerate; runtime then calls 0x3c6(rate) (?) */
#define SUBFN_GETCHANNELS    5   /* *(u32*)a1 -> info.channels, must be <= 2                */
#define SUBFN_GETLENGTH      6   /* *(u32*)a1 -> info.length (ms ?)                          */
#define SUBFN_GETTIME        7   /* *(u32*)a1 -> info.time, called after every decode       */
#define SUBFN_OPEN_DEC       8   /* open the file already selected (handle *(u8*)0x01022108) */
#define SUBFN_OPEN_ENC       9   /* WMA returns 1                                            */
#define SUBFN_GETBUFFER     10   /* *(int16_t**)a1 = PCM, *(u32*)a2 = frame count           */
#define SUBFN_SETBUFFER     11   /* WMA returns 0                                            */
#define SUBFN_DECODE        12   /* decode one block; 0 = end/error -> message 6             */
#define SUBFN_ENCODE        13   /* (?) encoder path; WMA re-uses it for something else      */
#define SUBFN_SEEK          14   /* a1 = time (ms ?)                                         */
#define SUBFN_CLOSE         15   /* a1 = 1                                                   */
#define SUBFN_GETBPS        17   /* *(u32*)a1 -> info.bps (16)                               */

/* ---- Info block: HiFi 0x010269c0 (0x30 bytes), copied to main 0x0304af28 ---- */
typedef struct {
    uint32_t time;        /* +0x00 SUBFN_GETTIME        (server case 7)  */
    uint32_t length;      /* +0x04 SUBFN_GETLENGTH      (server case 6)  */
    uint32_t bitrate;     /* +0x08 SUBFN_GETBITRATE     (server case 3)  */
    uint32_t bps;         /* +0x0c SUBFN_GETBPS         (server case 17) */
    uint32_t samplerate;  /* +0x10 SUBFN_GETSAMPLERATE  (server case 4)  */
    uint32_t channels;    /* +0x14 SUBFN_GETCHANNELS    (server case 5)  */
    uint32_t _18;
    int16_t *pcm;         /* +0x1c SUBFN_GETBUFFER                       */
    uint32_t pcm_frames;  /* +0x20 interleaved stereo frames             */
    uint32_t main_ready;  /* +0x24 set by main ISR (buffer available)    */
    uint32_t main_req;    /* +0x28 main: decode requested                */
    uint32_t main_eof;    /* +0x2c main: end/error                       */
} codec_info_t;
/* The main core copies the PCM by DMA: words = (pcm_frames * bps) >> 4. */

/* ---- File access: function table at 0x010220e4 (filled by the runtime) ---- */
typedef struct {
    int      (*open)(void);                                   /* +0x00 HifiFileOpen  0x1b0  */
    uint32_t (*read)(void *buf, uint32_t size, uint32_t h);   /* +0x04 buffered read 0x2544 */
    int      (*seek)(int32_t off, int whence, uint32_t h);    /* +0x08 0 = OK        0x277e */
    uint32_t (*tell)(uint32_t h);                             /* +0x0c               0x26ea */
    void      *_10;
    uint32_t (*length)(uint32_t h);                           /* +0x14 size          0x01f8 */
    int      (*close)(uint32_t h);                            /* +0x18 HifiFileClose 0x033e */
    int      (*eof)(uint32_t h);                              /* +0x1c               0x2724 */
} file_ops_t;
#define FILE_OPS     ((volatile file_ops_t *)0x010220e4)
#define FILE_HANDLE  (*(volatile uint8_t  *)0x01022108)
#define FILE_SIZE    (*(volatile uint32_t *)0x01022224)

/* ---- Runtime helpers called directly by the WMA library ---- */
#define RT_PRINTF   0x00000902   /* debug printf                     */
#define RT_MEMCPY   0x00001bc6   /* (dst, src, n)                    */
#define RT_MEMCLR   0x00001c14   /* (dst, n)                         */
#define RT_UDIV64   0x00001acc   /* 64-bit division helper (?)       */

/* ---- Mailbox 0x40110000: main -> HiFi (mbox0 ch1), translated by IRQ 0x1a (0x139c) ----
 *  A2B 1 -> OPEN    A2B 4 -> DECODE    A2B 0xb(arg) -> SEEK    A2B 0xd -> CLOSE
 *  A2B 7, 9, 0xcb, 0xcd -> internal 4, 5, 0xe, 0xd: no-ops / buffer refresh
 * HiFi -> main (ch1, main ISR 0x030878b4); data = &info:
 *  2 open failed   3 open OK + info   5 block decoded + info   6 end/error
 *  0xc seek done   0xe close done
 * File requests (ch2, main ISR 0x03087aec): 0x69 seek, 0x6b read, 0x6d write, 0x73 close */

/* ---- Memory map of module 74 (HiFi view) ----
 * code  0x00000000-0x000162c0  runtime 0x0-0x2ec4 | WMA lib 0x2ec4-~0x10138
 *                              | runtime tail 0x10138-~0x110a4 | rodata (WMA tables) to 0x162c0
 * data  0x01020000-0x010267c0  (0x90-byte parameter block at 0x01020000,
 *                               vector table at 0x01022000, SP = 0x01022000)
 * bss   0x010267c0-0x01047632  zeroed by the runtime itself (0x20e72 bytes)
 * File: 0x1ca80 bytes available in place (load 0x031537c0-0x03170240). */
#endif

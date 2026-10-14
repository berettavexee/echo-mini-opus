/* Bare-metal Cortex-M3 benchmark of OpusCodec() under QEMU -icount shift=0
 * (1 instruction = 1 ns of virtual time; CMSDK timer0 counts at 25 MHz => 1 tick = 40 instructions). */
#include <stdint.h>
#include <string.h>
#include "codec_abi.h"

int OpusCodec(int subfn, void *a1, void *a2, void *a3);
extern const uint8_t opus_file[], opus_file_end[];
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

/* ---- semihosting ---- */
static int semi(int op, const void *arg)
{
    register int r0 __asm__("r0") = op;
    register const void *r1 __asm__("r1") = arg;
    __asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}
static void puts_(const char *s) { semi(0x04, s); }
#ifdef BENCH_DUMP
static int dumpfd = -1;
static void dump(const void *b, uint32_t n)
{
    uint32_t a[3];
    if (dumpfd < 0) { a[0] = (uint32_t)BENCH_DUMP; a[1] = 4; a[2] = strlen(BENCH_DUMP); dumpfd = semi(0x01, a); }
    a[0] = (uint32_t)dumpfd; a[1] = (uint32_t)b; a[2] = n; semi(0x05, a);
}
#endif
static void putu(uint64_t v)
{
    char b[24]; int i = 23; b[i] = 0;
    do { b[--i] = '0' + v % 10; v /= 10; } while (v);
    puts_(b + i);
}

/* ---- file mock ---- */
static uint32_t fpos;
uint32_t host_size(void) { return (uint32_t)(opus_file_end - opus_file); }
int host_seek(uint32_t off) { if (off > host_size()) return -1; fpos = off; return 0; }
uint32_t host_read(void *buf, uint32_t n)
{
    uint32_t left = host_size() - fpos;
    if (n > left) n = left;
    memcpy(buf, opus_file + fpos, n);
    fpos += n;
    return n;
}

/* ---- CMSDK APB timer 0 ---- */
#define T0 ((volatile uint32_t *)0x40000000)   /* CTRL, VALUE, RELOAD */
static void timer_start(void) { T0[0] = 0; T0[2] = 0xFFFFFFFF; T0[1] = 0xFFFFFFFF; T0[0] = 1; }
static uint32_t timer_ticks(void) { return 0xFFFFFFFF - T0[1]; }

#ifndef BENCH_SECONDS
#define BENCH_SECONDS 20
#endif

int main(void)
{
    uint32_t fnv = 2166136261u, n, t_open, t_dec = 0, t_max = 0, calls = 0;
    uint64_t frames = 0;
    int16_t *pcm;
    uint32_t i;

    timer_start();
    if (OpusCodec(SUBFN_OPEN_DEC, 0, 0, 0) != 1) { puts_("open failed\n"); return 1; }
    t_open = timer_ticks();
    OpusCodec(SUBFN_GETBUFFER, &pcm, &n, 0);
    for (;;) {
        const uint8_t *p = (const uint8_t *)pcm;
        uint32_t t0, dt;
        for (i = 0; i < n * 4; i++) { fnv ^= p[i]; fnv *= 16777619u; }
#ifdef BENCH_DUMP
        dump(p, n * 4);
#endif
        frames += n;
        if (frames >= 48000ull * BENCH_SECONDS) break;
        t0 = timer_ticks();
        if (OpusCodec(SUBFN_DECODE, 0, 0, 0) != 1) break;
        dt = timer_ticks() - t0;
        t_dec += dt; calls++;
        if (dt > t_max) t_max = dt;
        OpusCodec(SUBFN_GETBUFFER, &pcm, &n, 0);
    }
    puts_("frames="); putu(frames);
    puts_(" open_insns="); putu((uint64_t)t_open * 40);
    puts_(" decode_insns="); putu((uint64_t)t_dec * 40);
    puts_(" calls="); putu(calls);
    puts_(" max_call_insns="); putu((uint64_t)t_max * 40);
    puts_(" insns_per_audio_second="); putu((uint64_t)t_dec * 40 * 48000 / (frames ? frames : 1));
    puts_(" pcm_fnv="); putu(fnv);
    puts_("\n");
    return 0;
}

/* ---- startup ---- */
void Reset_Handler(void)
{
    uint32_t *s = &_sidata, *d = &_sdata;
    while (d < &_edata) *d++ = *s++;
    for (d = &_sbss; d < &_ebss; ) *d++ = 0;
    {
        static const uint32_t args[2] = { 0x20026, 0 };          /* ADP_Stopped_ApplicationExit */
        int rc = main();
        (void)rc;
        semi(0x18, (const void *)0x20026);
        (void)args;
    }
    for (;;) ;
}
static void Fault_Handler(void) { puts_("FAULT\n"); semi(0x18, (const void *)0x20024); for (;;) ; }
__attribute__((section(".vectors"), used))
static const void *vectors[16] = { &_estack, Reset_Handler, Fault_Handler, Fault_Handler,
                                   Fault_Handler, Fault_Handler, Fault_Handler };

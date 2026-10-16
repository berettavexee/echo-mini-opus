/* QEMU benchmark of VorbisCodec() (whole plug-in, HOST_TEST build): mps2-an385, -icount shift=0
 * (1 instruction = 1 ns; CMSDK timer0 at 25 MHz => 1 tick = 40 instructions). */
#include <stdint.h>
#include <string.h>
#include "codec_abi.h"
int VorbisCodec(int subfn, void *a1, void *a2, void *a3);
extern const uint8_t ogg_file[], ogg_file_end[];
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern uint32_t rt_heap_peak;
static int semi(int op, const void *arg)
{
    register int r0 __asm__("r0") = op;
    register const void *r1 __asm__("r1") = arg;
    __asm__ volatile("bkpt 0xab" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}
static void puts_(const char *s) { semi(0x04, s); }
static void putu(uint64_t v) { char b[24]; int i = 23; b[i] = 0; do { b[--i] = '0' + v % 10; v /= 10; } while (v); puts_(b + i); }
#ifdef BENCH_DUMP
static int dumpfd = -1;
static void dump(const void *b, uint32_t n)
{ uint32_t a[3]; if (dumpfd < 0) { a[0] = (uint32_t)BENCH_DUMP; a[1] = 4; a[2] = strlen(BENCH_DUMP); dumpfd = semi(0x01, a); }
  a[0] = dumpfd; a[1] = (uint32_t)b; a[2] = n; semi(0x05, a); }
#endif
#ifdef RT_TRACE
static void puth(uint32_t v){char b[11];int i;b[0]='0';b[1]='x';for(i=0;i<8;i++)b[2+i]="0123456789abcdef"[(v>>(28-4*i))&15];b[10]=0;puts_(b);}
void rt_trace(uint32_t n,uint32_t cur,void*ra){ if(n>=1024){puts_("alloc ");putu(n);puts_(" cur ");putu(cur);puts_(" ra ");puth((uint32_t)ra);puts_("\n");} }
#endif
static uint32_t fpos;
uint32_t host_size(void) { return (uint32_t)(ogg_file_end - ogg_file); }
uint32_t host_tell(void) { return fpos; }
int host_seek(uint32_t off) { if (off > host_size()) return -1; fpos = off; return 0; }
uint32_t host_read(void *buf, uint32_t n) { uint32_t l = host_size() - fpos; if (n > l) n = l; memcpy(buf, ogg_file + fpos, n); fpos += n; return n; }
#define T0 ((volatile uint32_t *)0x40000000)
static uint32_t ticks(void) { return 0xFFFFFFFF - T0[1]; }
#ifndef BENCH_SECONDS
#define BENCH_SECONDS 30
#endif
#ifndef SEEK_MS
#define SEEK_MS 0
#endif
int main(void)
{
    uint32_t fnv = 2166136261u, n, rate, ch, len, t0, dt, t_dec = 0, t_max = 0, t_open, i;
    uint64_t frames = 0;
    int16_t *pcm;
    T0[0] = 0; T0[2] = 0xFFFFFFFF; T0[1] = 0xFFFFFFFF; T0[0] = 1;
    t0 = ticks();
    if (VorbisCodec(SUBFN_OPEN_DEC, 0, 0, 0) != 1) { puts_("open failed\n"); return 1; }
    t_open = ticks() - t0;
    VorbisCodec(SUBFN_GETSAMPLERATE, &rate, 0, 0);
    VorbisCodec(SUBFN_GETCHANNELS, &ch, 0, 0);
    VorbisCodec(SUBFN_GETLENGTH, &len, 0, 0);
    if (SEEK_MS) VorbisCodec(SUBFN_SEEK, (void *)(uintptr_t)SEEK_MS, 0, 0);
    VorbisCodec(SUBFN_GETBUFFER, &pcm, &n, 0);
    for (;;) {
        const uint8_t *p = (const uint8_t *)pcm;
        for (i = 0; i < n * 4; i++) { fnv ^= p[i]; fnv *= 16777619u; }
#ifdef BENCH_DUMP
        dump(p, n * 4);
#endif
        frames += n;
        if (frames >= (uint64_t)rate * BENCH_SECONDS) break;
        t0 = ticks();
        if (VorbisCodec(SUBFN_DECODE, 0, 0, 0) != 1) break;
        dt = ticks() - t0; t_dec += dt; if (dt > t_max) t_max = dt;
        VorbisCodec(SUBFN_GETBUFFER, &pcm, &n, 0);
    }
    { uint32_t tm; VorbisCodec(SUBFN_GETTIME, &tm, 0, 0);
      puts_("rate="); putu(rate); puts_(" ch="); putu(ch); puts_(" length_ms="); putu(len); puts_(" time_ms="); putu(tm); }
    puts_(" frames="); putu(frames);
    puts_(" open_insns="); putu((uint64_t)t_open * 40);
    puts_(" insns_per_audio_second="); putu((uint64_t)t_dec * 40 * rate / (frames ? frames : 1));
    puts_(" max_call_insns="); putu((uint64_t)t_max * 40);
    puts_(" heap_peak="); putu(rt_heap_peak);
    puts_(" pcm_fnv="); putu(fnv); puts_("\n");
    VorbisCodec(SUBFN_CLOSE, 0, 0, 0);
    return 0;
}
void Reset_Handler(void)
{
    uint32_t *s = &_sidata, *d = &_sdata;
    while (d < &_edata) *d++ = *s++;
    for (d = &_sbss; d < &_ebss; ) *d++ = 0;
    main();
    semi(0x18, (const void *)0x20026);
    for (;;) ;
}
static void Fault_Handler(void) { puts_("FAULT\n"); semi(0x18, (const void *)0x20024); for (;;) ; }
__attribute__((section(".vectors"), used))
static const void *vectors[16] = { &_estack, Reset_Handler, Fault_Handler, Fault_Handler, Fault_Handler, Fault_Handler, Fault_Handler };

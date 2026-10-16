/* Bare-metal Cortex-M3 benchmark of Tremor (lowmem) under QEMU -icount shift=0. */
#include <stdint.h>
#include <stddef.h>
#include "ivorbiscodec.h"
#include "ivorbisfile.h"
extern const uint8_t ogg_file[], ogg_file_end[];
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
/* ---- minimal libc ---- */
void *memcpy(void *d, const void *s, size_t n){uint8_t*a=d;const uint8_t*b=s;while(n--)*a++=*b++;return d;}
void *memmove(void *d, const void *s, size_t n){uint8_t*a=d;const uint8_t*b=s;if(a<b)while(n--)*a++=*b++;else{a+=n;b+=n;while(n--)*--a=*--b;}return d;}
void *memset(void *d, int c, size_t n){uint8_t*a=d;while(n--)*a++=(uint8_t)c;return d;}
int memcmp(const void *x,const void *y,size_t n){const uint8_t*a=x,*b=y;for(;n;n--,a++,b++)if(*a!=*b)return *a-*b;return 0;}
void *memchr(const void*s,int c,size_t n){const uint8_t*p=s;for(;n;n--,p++)if(*p==(uint8_t)c)return (void*)p;return 0;}
size_t strlen(const char*s){size_t n=0;while(s[n])n++;return n;}
char *strcpy(char*d,const char*s){char*r=d;while((*d++=*s++));return r;}
char *strcat(char*d,const char*s){strcpy(d+strlen(d),s);return d;}
/* ---- heap: first-fit with coalescing-free simple list, peak tracking ---- */
#ifndef HEAP_SIZE
#define HEAP_SIZE (192*1024)
#endif
static uint8_t heap[HEAP_SIZE] __attribute__((aligned(8)));
typedef struct blk { uint32_t size; uint32_t used; } blk;   /* header, size includes header */
static uint32_t heap_top, cur_use, peak_use;
static blk *first(void){ return (blk*)heap; }
void *malloc(size_t n){
  uint32_t need=((n+7)&~7u)+sizeof(blk); uint8_t *p=heap;
  while(p<heap+heap_top){ blk*b=(blk*)p; if(!b->used&&b->size>=need){ if(b->size>=need+16){blk*r=(blk*)(p+need);r->size=b->size-need;r->used=0;b->size=need;} b->used=1; cur_use+=b->size; if(cur_use>peak_use)peak_use=cur_use; return p+sizeof(blk);} p+=b->size; }
  if(heap_top+need>HEAP_SIZE) return 0;
  blk*b=(blk*)(heap+heap_top); b->size=need; b->used=1; heap_top+=need; cur_use+=need; if(cur_use>peak_use)peak_use=cur_use; return (uint8_t*)b+sizeof(blk);
}
void free(void*p){ if(!p)return; blk*b=(blk*)((uint8_t*)p-sizeof(blk)); b->used=0; cur_use-=b->size;
  /* merge with following free blocks */
  for(uint8_t*q=heap;q<heap+heap_top;){ blk*x=(blk*)q; if(!x->used){ while(q+x->size<heap+heap_top && !((blk*)(q+x->size))->used) x->size+=((blk*)(q+x->size))->size; if(q+x->size==heap+heap_top){heap_top=q-heap;break;} } q+=x->size; } }
void *calloc(size_t a,size_t b){ void*p=malloc(a*b); if(p)memset(p,0,a*b); return p; }
void *realloc(void*p,size_t n){ if(!p)return malloc(n); blk*b=(blk*)((uint8_t*)p-sizeof(blk)); uint32_t old=b->size-sizeof(blk); if(old>=n) return p; void*q=malloc(n); if(q){memcpy(q,p,old);free(p);} return q; }
/* ---- semihosting ---- */
static int semi(int op,const void*arg){register int r0 __asm__("r0")=op;register const void*r1 __asm__("r1")=arg;__asm__ volatile("bkpt 0xab":"+r"(r0):"r"(r1):"memory");return r0;}
static void puts_(const char*s){semi(0x04,s);}
static void putu(uint64_t v){char b[24];int i=23;b[i]=0;do{b[--i]='0'+v%10;v/=10;}while(v);puts_(b+i);}
#ifdef BENCH_DUMP
static int dumpfd=-1;
static void dump(const void*b,uint32_t n){uint32_t a[3];if(dumpfd<0){a[0]=(uint32_t)BENCH_DUMP;a[1]=4;a[2]=strlen(BENCH_DUMP);dumpfd=semi(0x01,a);}a[0]=dumpfd;a[1]=(uint32_t)b;a[2]=n;semi(0x05,a);}
#endif
/* ---- memory file callbacks ---- */
static uint32_t fpos;
static size_t rd(void*p,size_t sz,size_t nm,void*ds){uint32_t left=(uint32_t)(ogg_file_end-ogg_file)-fpos,n=sz*nm;if(n>left)n=left;memcpy(p,ogg_file+fpos,n);fpos+=n;return n/(sz?sz:1);}
static int sk(void*ds,ogg_int64_t off,int wh){int64_t b=wh==0?0:wh==1?fpos:(ogg_file_end-ogg_file);int64_t t=b+off;if(t<0||t>(ogg_file_end-ogg_file))return -1;fpos=(uint32_t)t;return 0;}
static int cl(void*ds){return 0;}
static long tl(void*ds){return fpos;}
/* ---- timer: CMSDK timer0, 25 MHz, 1 tick = 40 insns at icount 0 ---- */
#define T0 ((volatile uint32_t*)0x40000000)
static uint32_t ticks(void){return 0xFFFFFFFF-T0[1];}
#ifndef BENCH_SECONDS
#define BENCH_SECONDS 30
#endif
static OggVorbis_File vf;
static char pcm[4096];
int main(void){
  T0[0]=0;T0[2]=0xFFFFFFFF;T0[1]=0xFFFFFFFF;T0[0]=1;
  ov_callbacks cb={rd,sk,cl,tl};
  uint32_t t0=ticks();
  if(ov_open_callbacks(&vf,&vf,0,0,cb)<0){puts_("open failed\n");return 1;}
  uint32_t t_open=ticks()-t0, t_dec=0, t_max=0, fnv=2166136261u; uint64_t bytes=0; int sec;
  vorbis_info *vi=ov_info(&vf,-1); uint32_t rate=vi->rate, ch=vi->channels;
  uint32_t open_peak=peak_use;
  for(;;){ uint32_t a=ticks(); long n=ov_read(&vf,pcm,sizeof pcm,&sec); uint32_t dt=ticks()-a;
    if(n<=0)break; t_dec+=dt; if(dt>t_max)t_max=dt;
    for(long i=0;i<n;i++){fnv^=(uint8_t)pcm[i];fnv*=16777619u;}
#ifdef BENCH_DUMP
    dump(pcm,n);
#endif
    bytes+=n; if(bytes>=(uint64_t)rate*ch*2*BENCH_SECONDS)break; }
  uint64_t frames=bytes/(2*ch);
  puts_("rate=");putu(rate);puts_(" ch=");putu(ch);puts_(" frames=");putu(frames);
  puts_(" open_insns=");putu((uint64_t)t_open*40);
  puts_(" insns_per_audio_second=");putu((uint64_t)t_dec*40*rate/(frames?frames:1));
  puts_(" max_call_insns=");putu((uint64_t)t_max*40);
  puts_(" heap_peak=");putu(peak_use);puts_(" heap_after_open=");putu(open_peak);
  puts_(" pcm_fnv=");putu(fnv);puts_("\n");
  return 0;
}
void Reset_Handler(void){uint32_t*s=&_sidata,*d=&_sdata;while(d<&_edata)*d++=*s++;for(d=&_sbss;d<&_ebss;)*d++=0;main();semi(0x18,(const void*)0x20026);for(;;);}
static void Fault_Handler(void){puts_("FAULT\n");semi(0x18,(const void*)0x20024);for(;;);}
int errno; int *__errno(void){return &errno;}
__attribute__((section(".vectors"),used)) static const void *vectors[16]={&_estack,Reset_Handler,Fault_Handler,Fault_Handler,Fault_Handler,Fault_Handler,Fault_Handler};

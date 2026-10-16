/* Minimal freestanding runtime for the Vorbis plug-in of module 77 (no newlib):
 * mem/str functions used by Tremor and a first-fit heap that is reset at every OPEN/CLOSE. */
#include <stddef.h>
#include <stdint.h>

void *memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    if ((((uintptr_t)d | (uintptr_t)s) & 3) == 0) {
        uint32_t *dw = (uint32_t *)d;
        const uint32_t *sw = (const uint32_t *)s;
        for (; n >= 16; n -= 16) {
            dw[0] = sw[0]; dw[1] = sw[1]; dw[2] = sw[2]; dw[3] = sw[3];
            dw += 4; sw += 4;
        }
        for (; n >= 4; n -= 4)
            *dw++ = *sw++;
        d = (uint8_t *)dw;
        s = (const uint8_t *)sw;
    }
    while (n--)
        *d++ = *s++;
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    if (d <= s || d >= s + n)
        return memcpy(dst, src, n);
    d += n;
    s += n;
    while (n--)
        *--d = *--s;
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    uint8_t *d = dst;
    if (((uintptr_t)d & 3) == 0) {
        uint32_t v = (uint8_t)c * 0x01010101u;
        uint32_t *dw = (uint32_t *)d;
        for (; n >= 4; n -= 4)
            *dw++ = v;
        d = (uint8_t *)dw;
    }
    while (n--)
        *d++ = (uint8_t)c;
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *x = a, *y = b;
    for (; n; n--, x++, y++)
        if (*x != *y)
            return *x - *y;
    return 0;
}

void *memchr(const void *p, int c, size_t n)
{
    const uint8_t *s = p;
    for (; n; n--, s++)
        if (*s == (uint8_t)c)
            return (void *)s;
    return 0;
}

size_t strlen(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

/* ---- heap ---- */
#ifndef HEAP_SIZE
#define HEAP_SIZE (100 * 1024)
#endif
typedef struct { uint32_t size, used; } blk_t;          /* size includes the header */
static uint8_t heap[HEAP_SIZE] __attribute__((aligned(8)));
static uint32_t heap_top;
uint32_t rt_heap_peak, rt_heap_cur;

void rt_heap_reset(void) { heap_top = 0; rt_heap_cur = 0; }

void *malloc(size_t n)
{
    uint32_t need = (uint32_t)((n + 7) & ~(size_t)7) + sizeof(blk_t);
    uint8_t *p = heap;
    blk_t *b;
    while (p < heap + heap_top) {
        b = (blk_t *)p;
        if (!b->used && b->size >= need) {
            if (b->size >= need + 16) {
                blk_t *r = (blk_t *)(p + need);
                r->size = b->size - need;
                r->used = 0;
                b->size = need;
            }
            goto take;
        }
        p += b->size;
    }
    if (heap_top + need > HEAP_SIZE)
        return 0;
    b = (blk_t *)(heap + heap_top);
    b->size = need;
    heap_top += need;
take:
    b->used = 1;
    rt_heap_cur += b->size;
#ifdef RT_TRACE
    { extern void rt_trace(uint32_t, uint32_t, void *); rt_trace((uint32_t)n, rt_heap_cur, __builtin_return_address(0)); }
#endif
    if (rt_heap_cur > rt_heap_peak)
        rt_heap_peak = rt_heap_cur;
    return (uint8_t *)b + sizeof(blk_t);
}

void free(void *ptr)
{
    blk_t *b;
    uint8_t *p;
    if (!ptr)
        return;
    b = (blk_t *)((uint8_t *)ptr - sizeof(blk_t));
    b->used = 0;
    rt_heap_cur -= b->size;
    /* coalesce free neighbours, trim the top */
    for (p = heap; p < heap + heap_top; ) {
        blk_t *x = (blk_t *)p;
        if (!x->used) {
            while (p + x->size < heap + heap_top && !((blk_t *)(p + x->size))->used)
                x->size += ((blk_t *)(p + x->size))->size;
            if (p + x->size == heap + heap_top) {
                heap_top = (uint32_t)(p - heap);
                break;
            }
        }
        p += x->size;
    }
}

void *calloc(size_t a, size_t b)
{
    void *p = malloc(a * b);
    if (p)
        memset(p, 0, a * b);
    return p;
}

void *realloc(void *ptr, size_t n)
{
    blk_t *b;
    uint32_t old;
    void *q;
    if (!ptr)
        return malloc(n);
    b = (blk_t *)((uint8_t *)ptr - sizeof(blk_t));
    old = b->size - sizeof(blk_t);
    if (old >= n)
        return ptr;
    q = malloc(n);
    if (q) {
        memcpy(q, ptr, old);
        free(ptr);
    }
    return q;
}

/* vorbisfile checks errno after a short read: never set here (a short read means end of file). */
static int rt_errno;
int *__errno(void) { return &rt_errno; }

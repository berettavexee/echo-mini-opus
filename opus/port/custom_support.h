/* libopus allocation overrides for the ECHO MINI HiFi core (no malloc, 8 KB stack).
 * Included by os_support.h when CUSTOM_SUPPORT is defined. */
#ifndef ECHOMINI_CUSTOM_SUPPORT_H
#define ECHOMINI_CUSTOM_SUPPORT_H
#include <stddef.h>

/* NONTHREADSAFE_PSEUDOSTACK scratch: static, sized by GLOBAL_STACK_SIZE. */
extern char echomini_opus_scratch[];
#define OVERRIDE_OPUS_ALLOC_SCRATCH
static inline void *opus_alloc_scratch(size_t size)
{
    (void)size;
    return echomini_opus_scratch;
}

/* The decoder state is a static buffer (opus_decoder_init); nothing else may allocate. */
#define OVERRIDE_OPUS_ALLOC
static inline void *opus_alloc(size_t size)
{
    (void)size;
    return NULL;
}

#define OVERRIDE_OPUS_FREE
static inline void opus_free(void *ptr)
{
    (void)ptr;
}
#endif

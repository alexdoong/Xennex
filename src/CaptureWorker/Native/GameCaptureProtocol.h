#pragma once
#include <windows.h>
#include <stdint.h>

#define XGC_MAGIC 0x31434758u
#define XGC_VERSION 1u
#define XGC_HEADER_BYTES 128u
#define XGC_MAX_PIXELS (32u * 1024u * 1024u)
enum { XGC_WAITING = 0, XGC_HOOKED = 1, XGC_FRAMES = 2, XGC_STOPPED = 3, XGC_ERROR = -1 };
#pragma pack(push, 8)
typedef struct {
    uint32_t magic, version, header_bytes, pixel_capacity;
    volatile LONG status, error;
    uint32_t width, height, stride, format;
    volatile LONG64 frame_id, capture_qpc, skipped, captured;
    uint8_t reserved[56];
} XgcHeader;
typedef struct {
    uint32_t version, target_pid, owner_pid, fps;
    uint64_t hwnd, mapping, mutex, stop;
} XgcConfig;
#pragma pack(pop)
_Static_assert(sizeof(XgcHeader) == XGC_HEADER_BYTES, "IPC header size");
_Static_assert(sizeof(XgcConfig) == 48, "IPC config size");

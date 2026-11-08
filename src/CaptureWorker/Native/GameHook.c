// Xennex OpenGL capture prototype. No code from OBS is incorporated here.
#define WIN32_LEAN_AND_MEAN
#include "GameCaptureProtocol.h"
#include <GL/gl.h>
#include <stddef.h>
#include <string.h>
#include "MinHook.h"

typedef void (APIENTRY *GenBuffersFn)(GLsizei, GLuint*);
typedef void (APIENTRY *BindBufferFn)(GLenum, GLuint);
typedef void (APIENTRY *BufferDataFn)(GLenum, ptrdiff_t, const void*, GLenum);
typedef void* (APIENTRY *MapBufferRangeFn)(GLenum, ptrdiff_t, ptrdiff_t, GLbitfield);
typedef GLboolean (APIENTRY *UnmapBufferFn)(GLenum);
typedef void (APIENTRY *DeleteBuffersFn)(GLsizei, const GLuint*);
typedef void* (APIENTRY *FenceSyncFn)(GLenum, GLbitfield);
typedef GLenum (APIENTRY *ClientWaitSyncFn)(void*, GLbitfield, uint64_t);
typedef void (APIENTRY *DeleteSyncFn)(void*);
typedef void (APIENTRY *BindFramebufferFn)(GLenum, GLuint);
typedef BOOL (WINAPI *SwapFn)(HDC);
typedef BOOL (WINAPI *SwapLayerFn)(HDC, UINT);
typedef BOOL (WINAPI *DeleteContextFn)(HGLRC);
static GenBuffersFn gen_buffers;
static BindBufferFn bind_buffer;
static BufferDataFn buffer_data;
static MapBufferRangeFn map_buffer;
static UnmapBufferFn unmap_buffer;
static DeleteBuffersFn delete_buffers;
static FenceSyncFn fence_sync;
static ClientWaitSyncFn wait_sync;
static DeleteSyncFn delete_sync;
static BindFramebufferFn bind_framebuffer;
static SwapFn real_swap, real_wgl_swap;
static SwapLayerFn real_layer;
static DeleteContextFn real_delete_context;
static XgcConfig config;
static XgcHeader* header;
static HANDLE frame_mutex, stop_event, owner;
static HANDLE start_gate;
static volatile LONG initialized, enabled, capture_busy, cleaning, cleaned;
static volatile LONG context_invalid;
static BOOL hooks_created;
static __thread int recursion;
static HGLRC capture_context;
static GLuint pbos[3];
static void* fences[3];
static int64_t submitted[3];
static unsigned slot, width, height;
static LARGE_INTEGER frequency;
static int64_t next_frame;
static BOOL reset_buffers;

enum { PIXEL_PACK_BUFFER = 0x88EB, PIXEL_PACK_BUFFER_BINDING = 0x88ED,
    STREAM_READ = 0x88E1, MAP_READ_BIT = 1, SYNC_GPU_COMMANDS_COMPLETE = 0x9117,
    ALREADY_SIGNALED = 0x911A, CONDITION_SATISFIED = 0x911C,
    READ_FRAMEBUFFER = 0x8CA8, READ_FRAMEBUFFER_BINDING = 0x8CAA, BGRA = 0x80E1 };

static PROC gl_proc(const char* name) {
    PROC p = wglGetProcAddress(name);
    if (!p || p == (PROC)1 || p == (PROC)2 || p == (PROC)3 || p == (PROC)-1) return NULL;
    return p;
}
static BOOL load_gl(void) {
#define XGC_GL_LOAD(field, type, name) field = (type)gl_proc(name); if (!field) return FALSE
    XGC_GL_LOAD(gen_buffers, GenBuffersFn, "glGenBuffers");
    XGC_GL_LOAD(bind_buffer, BindBufferFn, "glBindBuffer");
    XGC_GL_LOAD(buffer_data, BufferDataFn, "glBufferData");
    XGC_GL_LOAD(map_buffer, MapBufferRangeFn, "glMapBufferRange");
    XGC_GL_LOAD(unmap_buffer, UnmapBufferFn, "glUnmapBuffer");
    XGC_GL_LOAD(delete_buffers, DeleteBuffersFn, "glDeleteBuffers");
    XGC_GL_LOAD(fence_sync, FenceSyncFn, "glFenceSync");
    XGC_GL_LOAD(wait_sync, ClientWaitSyncFn, "glClientWaitSync");
    XGC_GL_LOAD(delete_sync, DeleteSyncFn, "glDeleteSync");
    XGC_GL_LOAD(bind_framebuffer, BindFramebufferFn, "glBindFramebuffer");
#undef XGC_GL_LOAD
    return TRUE;
}
static void fail(LONG error) {
    InterlockedExchange(&header->error, error);
    InterlockedExchange(&header->status, XGC_ERROR);
    InterlockedExchange(&enabled, 0);
}
static void free_gl(void) {
    for (int i = 0; i < 3; i++) {
        if (fences[i]) { delete_sync(fences[i]); fences[i] = NULL; }
    }
    if (pbos[0]) delete_buffers(3, pbos);
    ZeroMemory(pbos, sizeof(pbos));
    width = height = 0;
}
typedef struct { GLint pack, alignment, row_length, skip_rows, skip_pixels, read_fbo, read_buffer; } GlState;
static void save_gl(GlState* state) {
    glGetIntegerv(PIXEL_PACK_BUFFER_BINDING, &state->pack);
    glGetIntegerv(GL_PACK_ALIGNMENT, &state->alignment);
    glGetIntegerv(GL_PACK_ROW_LENGTH, &state->row_length);
    glGetIntegerv(GL_PACK_SKIP_ROWS, &state->skip_rows);
    glGetIntegerv(GL_PACK_SKIP_PIXELS, &state->skip_pixels);
    glGetIntegerv(READ_FRAMEBUFFER_BINDING, &state->read_fbo);
    glGetIntegerv(GL_READ_BUFFER, &state->read_buffer);
}
static void restore_gl(const GlState* state) {
    bind_framebuffer(READ_FRAMEBUFFER, (GLuint)state->read_fbo);
    glReadBuffer((GLenum)state->read_buffer);
    bind_buffer(PIXEL_PACK_BUFFER, (GLuint)state->pack);
    glPixelStorei(GL_PACK_ALIGNMENT, state->alignment);
    glPixelStorei(GL_PACK_ROW_LENGTH, state->row_length);
    glPixelStorei(GL_PACK_SKIP_ROWS, state->skip_rows);
    glPixelStorei(GL_PACK_SKIP_PIXELS, state->skip_pixels);
}
static void drain_ready(uint64_t bytes) {
    BOOL ready[3] = { FALSE, FALSE, FALSE }; int newest = -1;
    for (int i = 0; i < 3; i++) {
        if (!fences[i]) continue;
        GLenum result = wait_sync(fences[i], 0, 0);
        if (result == 0x911D) { fail(1006); return; } // GL_WAIT_FAILED
        ready[i] = result == ALREADY_SIGNALED || result == CONDITION_SATISFIED;
        if (ready[i] && (newest < 0 || submitted[i] > submitted[newest])) newest = i;
    }
    if (newest < 0) return;
    DWORD locked = WaitForSingleObject(frame_mutex, 0);
    if (locked == WAIT_OBJECT_0 || locked == WAIT_ABANDONED) {
        bind_buffer(PIXEL_PACK_BUFFER, pbos[newest]);
        void* pixels = map_buffer(PIXEL_PACK_BUFFER, 0, (ptrdiff_t)bytes, MAP_READ_BIT);
        if (pixels) {
            memcpy((uint8_t*)header + XGC_HEADER_BYTES, pixels, (size_t)bytes);
            unmap_buffer(PIXEL_PACK_BUFFER);
            header->width = width; header->height = height; header->stride = width * 4; header->format = 1;
            header->capture_qpc = submitted[newest];
            InterlockedIncrement64(&header->captured); InterlockedIncrement64(&header->frame_id);
            InterlockedExchange(&header->status, XGC_FRAMES);
        } else fail(1007);
        ReleaseMutex(frame_mutex);
    } else InterlockedIncrement64(&header->skipped);
    for (int i = 0; i < 3; i++) {
        if (!ready[i]) continue;
        delete_sync(fences[i]); fences[i] = NULL;
        if (i != newest) InterlockedIncrement64(&header->skipped);
    }
}
static void capture(HDC dc) {
    HWND window = WindowFromDC(dc), selected = (HWND)(uintptr_t)config.hwnd;
    if (window != selected && !IsChild(selected, window)) return;
    HGLRC current = wglGetCurrentContext();
    if (!current) return;
    if (InterlockedCompareExchange(&context_invalid, 0, 0)) { fail(1008); return; }
    if (!capture_context) {
        if (!load_gl()) { fail(1001); return; }
        capture_context = current;
    }
    // Never delete GL object names in a different game's context.
    if (capture_context != current) { fail(1002); return; }
    GlState state; save_gl(&state);
    if (reset_buffers) { free_gl(); reset_buffers = FALSE; }
    if (InterlockedCompareExchange(&cleaning, 0, 0)) {
        free_gl(); restore_gl(&state); InterlockedExchange(&cleaned, 1); return;
    }
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    RECT bounds;
    if (!GetClientRect(window, &bounds)) { restore_gl(&state); return; }
    unsigned w = bounds.right - bounds.left, h = bounds.bottom - bounds.top;
    uint64_t bytes = (uint64_t)w * h * 4;
    if (w < 2 || h < 2 || w > 8192 || h > 8192 || bytes > header->pixel_capacity) { fail(1003); restore_gl(&state); return; }
    if (width != w || height != h) {
        free_gl(); gen_buffers(3, pbos); width = w; height = h; slot = 0;
        for (int i = 0; i < 3; i++) { bind_buffer(PIXEL_PACK_BUFFER, pbos[i]); buffer_data(PIXEL_PACK_BUFFER, (ptrdiff_t)bytes, NULL, STREAM_READ); }
    }
    // Drain at render cadence, not target capture cadence: avoid keeping every
    // image for three target frames (100ms at 30FPS) merely to cycle the ring.
    drain_ready(bytes);
    if (!InterlockedCompareExchange(&enabled, 0, 0) || now.QuadPart < next_frame) { restore_gl(&state); return; }
    int64_t period = frequency.QuadPart / config.fps;
    if (!next_frame) next_frame = now.QuadPart;
    next_frame += period;
    if (next_frame < now.QuadPart) next_frame = now.QuadPart + period;
    unsigned i = slot;
    for (int count = 0; count < 3 && fences[i]; count++) i = (i + 1) % 3;
    if (fences[i]) { InterlockedIncrement64(&header->skipped); restore_gl(&state); return; }
    slot = (i + 1) % 3;
    bind_framebuffer(READ_FRAMEBUFFER, 0); glReadBuffer(GL_BACK);
    bind_buffer(PIXEL_PACK_BUFFER, pbos[i]);
    glPixelStorei(GL_PACK_ALIGNMENT, 4); glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    glPixelStorei(GL_PACK_SKIP_ROWS, 0); glPixelStorei(GL_PACK_SKIP_PIXELS, 0);
    glReadPixels(0, 0, w, h, BGRA, GL_UNSIGNED_BYTE, 0);
    fences[i] = fence_sync(SYNC_GPU_COMMANDS_COMPLETE, 0);
    submitted[i] = now.QuadPart;
    if (!fences[i]) fail(1004);
    restore_gl(&state);
}
static void enter_capture(HDC dc) {
    if (recursion != 1 || InterlockedCompareExchange(&capture_busy, 1, 0)) return;
    if (InterlockedCompareExchange(&enabled, 0, 0) || InterlockedCompareExchange(&cleaning, 0, 0)) capture(dc);
    InterlockedExchange(&capture_busy, 0);
}
static BOOL WINAPI hooked_swap(HDC dc) {
    recursion++; enter_capture(dc); BOOL result = real_swap(dc); recursion--; return result;
}
static BOOL WINAPI hooked_wgl(HDC dc) {
    recursion++; enter_capture(dc); BOOL result = real_wgl_swap(dc); recursion--; return result;
}
static BOOL WINAPI hooked_layer(HDC dc, UINT planes) {
    recursion++; if (planes & WGL_SWAP_MAIN_PLANE) enter_capture(dc);
    BOOL result = real_layer(dc, planes); recursion--; return result;
}
static BOOL WINAPI hooked_delete_context(HGLRC context) {
    // Context handle values can be reused. Never mistake a new context's GL
    // object names for our old PBOs after destruction of the selected context.
    if (context == capture_context) InterlockedExchange(&context_invalid, 1);
    return real_delete_context(context);
}
static DWORD WINAPI lifetime(void* unused) {
    (void)unused;
    WaitForSingleObject(start_gate, INFINITE); CloseHandle(start_gate);
    HANDLE handles[] = { stop_event, owner };
    WaitForMultipleObjects(2, handles, FALSE, INFINITE);
    InterlockedExchange(&enabled, 0); InterlockedExchange(&cleaning, 1);
    ULONGLONG cleanup_deadline = GetTickCount64() + 1000;
    while (!InterlockedCompareExchange(&cleaned, 0, 0) && GetTickCount64() < cleanup_deadline) Sleep(5);
    if (!InterlockedCompareExchange(&cleaned, 0, 0)) InterlockedExchange(&context_invalid, 1);
    InterlockedExchange(&cleaning, 0);
    MH_DisableHook(MH_ALL_HOOKS);
    while (InterlockedCompareExchange(&capture_busy, 0, 0)) Sleep(1);
    if (InterlockedCompareExchange(&cleaned, 0, 0)) capture_context = NULL;
    // A thread can still be returning from the original SwapBuffers. Keep the
    // DLL and trampolines resident (disabled) until process exit; never unmap
    // instructions that such a caller may still execute. Reuse on next session.
    InterlockedExchange(&header->status, XGC_STOPPED);
    UnmapViewOfFile(header);
    CloseHandle((HANDLE)(uintptr_t)config.mapping); CloseHandle(frame_mutex); CloseHandle(stop_event); CloseHandle(owner);
    InterlockedExchange(&initialized, 0);
    return 0;
}
static DWORD initialize_session(void* argument) {
    // If cleanup could not run in the old context, reject reuse until game exit.
    if (InterlockedCompareExchange(&context_invalid, 0, 0)) return ERROR_INVALID_STATE;
    config = *(XgcConfig*)argument;
    DWORD window_pid = 0; GetWindowThreadProcessId((HWND)(uintptr_t)config.hwnd, &window_pid);
    if (config.version != XGC_VERSION || config.target_pid != GetCurrentProcessId() || window_pid != config.target_pid ||
        config.owner_pid == config.target_pid || config.fps < 1 || config.fps > 120) return ERROR_INVALID_PARAMETER;
    header = MapViewOfFile((HANDLE)(uintptr_t)config.mapping, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 0);
    if (!header) return GetLastError();
    if (header->magic != XGC_MAGIC || header->version != XGC_VERSION || header->header_bytes != XGC_HEADER_BYTES ||
        !header->pixel_capacity || header->pixel_capacity > XGC_MAX_PIXELS) { UnmapViewOfFile(header); return ERROR_INVALID_DATA; }
    owner = OpenProcess(SYNCHRONIZE, FALSE, config.owner_pid);
    if (!owner) { UnmapViewOfFile(header); return GetLastError(); }
    frame_mutex = (HANDLE)(uintptr_t)config.mutex; stop_event = (HANDLE)(uintptr_t)config.stop;
    HMODULE gl = GetModuleHandleW(L"opengl32.dll"), gdi = GetModuleHandleW(L"gdi32.dll");
    if (!gl || !gdi) { CloseHandle(owner); UnmapViewOfFile(header); return ERROR_NOT_SUPPORTED; }
    if (!hooks_created) {
        if (MH_Initialize() != MH_OK) { CloseHandle(owner); UnmapViewOfFile(header); return ERROR_NOT_SUPPORTED; }
        int installed = 0;
        if (MH_CreateHook((void*)GetProcAddress(gdi, "SwapBuffers"), (void*)hooked_swap, (void**)&real_swap) == MH_OK) installed++;
        if (MH_CreateHook((void*)GetProcAddress(gl, "wglSwapBuffers"), (void*)hooked_wgl, (void**)&real_wgl_swap) == MH_OK) installed++;
        if (MH_CreateHook((void*)GetProcAddress(gl, "wglSwapLayerBuffers"), (void*)hooked_layer, (void**)&real_layer) == MH_OK) installed++;
        if (MH_CreateHook((void*)GetProcAddress(gl, "wglDeleteContext"), (void*)hooked_delete_context, (void**)&real_delete_context) != MH_OK) {
            MH_Uninitialize(); CloseHandle(owner); UnmapViewOfFile(header); return ERROR_NOT_SUPPORTED;
        }
        if (!installed) { MH_Uninitialize(); CloseHandle(owner); UnmapViewOfFile(header); return ERROR_NOT_SUPPORTED; }
        hooks_created = TRUE;
    }
    QueryPerformanceFrequency(&frequency);
    next_frame = 0; reset_buffers = TRUE; InterlockedExchange(&cleaned, 0);
    start_gate = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!start_gate) { CloseHandle(owner); UnmapViewOfFile(header); return GetLastError(); }
    HANDLE thread = CreateThread(NULL, 0, lifetime, NULL, 0, NULL);
    if (!thread) { CloseHandle(start_gate); CloseHandle(owner); UnmapViewOfFile(header); return GetLastError(); }
    if (MH_EnableHook(MH_ALL_HOOKS) == MH_OK) {
        InterlockedExchange(&enabled, 1); InterlockedExchange(&header->status, XGC_HOOKED);
    } else { fail(1005); SetEvent(stop_event); }
    SetEvent(start_gate);
    CloseHandle(thread);
    return ERROR_SUCCESS;
}
__declspec(dllexport) DWORD WINAPI XennexGameInitialize(void* argument) {
    if (!argument) return ERROR_INVALID_PARAMETER;
    if (InterlockedCompareExchange(&context_invalid, 0, 0)) return ERROR_INVALID_STATE;
    if (InterlockedCompareExchange(&initialized, 1, 0)) return ERROR_ALREADY_INITIALIZED;
    DWORD result = initialize_session(argument);
    if (result) InterlockedExchange(&initialized, 0);
    return result;
}
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void* reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(instance);
    return TRUE;
}

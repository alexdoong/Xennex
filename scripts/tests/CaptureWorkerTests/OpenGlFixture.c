// Own OpenGL fixture: hidden by default, visible only for an explicit WGC probe.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <GL/gl.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static HGLRC context;
static HDC dc;
static void pack_state(void) {
    glReadBuffer(GL_FRONT); glPixelStorei(GL_PACK_ALIGNMENT, 8);
    glPixelStorei(GL_PACK_ROW_LENGTH, 800); glPixelStorei(GL_PACK_SKIP_ROWS, 2); glPixelStorei(GL_PACK_SKIP_PIXELS, 3);
}

static LRESULT CALLBACK procedure(HWND window, UINT message, WPARAM w, LPARAM l) {
    if (message == WM_CLOSE) { DestroyWindow(window); return 0; }
    if (message == WM_DESTROY) { PostQuitMessage(0); return 0; }
    if (message == WM_APP) { SetWindowPos(window, NULL, 0, 0, (int)w, (int)l, SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER); return 0; }
    if (message == WM_APP + 1) {
        wglMakeCurrent(NULL, NULL);
        if (!wglDeleteContext(context)) ExitProcess(8);
        context = wglCreateContext(dc);
        if (!context || !wglMakeCurrent(dc, context)) ExitProcess(9);
        pack_state(); return 0;
    }
    return DefWindowProcW(window, message, w, l);
}
int main(int argc, char **argv) {
    BOOL paced_fixture = argc == 2 && strcmp(argv[1], "--wgc-paced-fixture") == 0;
    BOOL wgc_fixture = paced_fixture || (argc == 2 && strcmp(argv[1], "--wgc-fixture") == 0);
    WNDCLASSW cls = {0}; cls.style = CS_OWNDC; cls.lpfnWndProc = procedure;
    cls.hInstance = GetModuleHandleW(NULL); cls.lpszClassName = L"XennexOwnOpenGlFixture";
    if (!RegisterClassW(&cls)) return 1;
    HWND window = CreateWindowW(cls.lpszClassName, L"Xennex own OpenGL fixture", wgc_fixture ? WS_POPUP : WS_OVERLAPPEDWINDOW,
        0, 0, wgc_fixture ? 1280 : 660, wgc_fixture ? 720 : 520, NULL, NULL, cls.hInstance, NULL);
    if (!window) return 2;
    if (wgc_fixture && !SetWindowPos(window, HWND_TOPMOST, 0, 0, 1280, 720, SWP_NOACTIVATE | SWP_SHOWWINDOW)) return 10;
    dc = GetDC(window);
    PIXELFORMATDESCRIPTOR descriptor = {0}; descriptor.nSize = sizeof(descriptor); descriptor.nVersion = 1;
    descriptor.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    descriptor.iPixelType = PFD_TYPE_RGBA; descriptor.cColorBits = 32;
    int format = ChoosePixelFormat(dc, &descriptor);
    if (!format || !SetPixelFormat(dc, format, &descriptor)) return 3;
    context = wglCreateContext(dc);
    if (!context || !wglMakeCurrent(dc, context)) return 4;
    typedef BOOL (WINAPI *Interval)(int);
    Interval interval = (Interval)wglGetProcAddress("wglSwapIntervalEXT");
    if (interval) interval(0);
    HANDLE timer = CreateWaitableTimerExW(NULL, NULL, 2, TIMER_ALL_ACCESS);
    if (!timer) return 5;
    pack_state();
    printf("%lu %llu\n", GetCurrentProcessId(), (unsigned long long)(uintptr_t)window); fflush(stdout);
    ULONGLONG deadline = GetTickCount64() + 45000;
    unsigned frame = 0; BOOL run = TRUE;
    while (run && GetTickCount64() < deadline) {
        MSG message;
        while (PeekMessageW(&message, NULL, 0, 0, PM_REMOVE)) {
            if (message.message == WM_QUIT) run = FALSE;
            TranslateMessage(&message); DispatchMessageW(&message);
        }
        if (!run) break;
        RECT client; GetClientRect(window, &client);
        int width = client.right, height = client.bottom;
        glViewport(0, 0, width, height); glDisable(GL_SCISSOR_TEST);
        glClearColor(1, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
        glEnable(GL_SCISSOR_TEST); glScissor(0, height / 2, width, height - height / 2);
        glClearColor(0, 0, 1, 1); glClear(GL_COLOR_BUFFER_BIT);
        if (wgc_fixture) {
            glScissor(0, height / 2, width / 2, height / 2); glClearColor(1, 0, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
            glScissor(width / 2, height / 2, width / 2, height / 2); glClearColor(0, 1, 0, 1); glClear(GL_COLOR_BUFFER_BIT);
            glScissor(0, 0, width / 2, height / 2); glClearColor(0, 0, 1, 1); glClear(GL_COLOR_BUFFER_BIT);
            glScissor(width / 2, 0, width / 2, height / 2); glClearColor(1, 1, 1, 1); glClear(GL_COLOR_BUFFER_BIT);
        }
        glScissor((frame++ * 7) % (width - 20), height / 2 - 10, 20, 20);
        glClearColor(0, 1, 0, 1); glClear(GL_COLOR_BUFFER_BIT); glDisable(GL_SCISSOR_TEST);
        SwapBuffers(dc);
        GLint alignment, rows, skip_rows, skip_pixels, read_buffer;
        glGetIntegerv(GL_PACK_ALIGNMENT, &alignment); glGetIntegerv(GL_PACK_ROW_LENGTH, &rows);
        glGetIntegerv(GL_PACK_SKIP_ROWS, &skip_rows); glGetIntegerv(GL_PACK_SKIP_PIXELS, &skip_pixels);
        glGetIntegerv(GL_READ_BUFFER, &read_buffer);
        if (alignment != 8 || rows != 800 || skip_rows != 2 || skip_pixels != 3 || read_buffer != GL_FRONT) return 6;
        LARGE_INTEGER delay; delay.QuadPart = paced_fixture ? -83333 : -10000;
        if (!SetWaitableTimer(timer, &delay, 0, NULL, NULL, FALSE) || WaitForSingleObject(timer, 1000) != WAIT_OBJECT_0) return 7;
    }
    wglMakeCurrent(NULL, NULL); wglDeleteContext(context); ReleaseDC(window, dc);
    CloseHandle(timer);
    return 0;
}

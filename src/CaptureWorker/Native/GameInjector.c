#define WIN32_LEAN_AND_MEAN
#include "GameCaptureProtocol.h"
#include <tlhelp32.h>
#include <stdio.h>
#include <wchar.h>

static BOOL same_user(HANDLE process) {
    HANDLE current = NULL, target = NULL;
    BYTE a[512], b[512]; DWORD used;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &current)) return FALSE;
    if (!OpenProcessToken(process, TOKEN_QUERY, &target)) { CloseHandle(current); return FALSE; }
    BOOL result = GetTokenInformation(current, TokenUser, a, sizeof(a), &used) &&
        GetTokenInformation(target, TokenUser, b, sizeof(b), &used) && EqualSid(((TOKEN_USER*)a)->User.Sid, ((TOKEN_USER*)b)->User.Sid);
    CloseHandle(current); CloseHandle(target); return result;
}
static BOOL number(const wchar_t* value, uint64_t* result) {
    wchar_t* end;
    if (!value || !*value || *value == L'-') return FALSE;
    *result = wcstoull(value, &end, 10); return *end == 0;
}
static uintptr_t module_base(DWORD pid, const wchar_t* path) {
    for (int attempt = 0; attempt < 20; attempt++) {
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
        if (snapshot == INVALID_HANDLE_VALUE) { Sleep(10); continue; }
        MODULEENTRY32W module = {0}; module.dwSize = sizeof(module);
        if (Module32FirstW(snapshot, &module)) do {
            if (_wcsicmp(path, module.szExePath) == 0) { CloseHandle(snapshot); return (uintptr_t)module.modBaseAddr; }
        } while (Module32NextW(snapshot, &module));
        CloseHandle(snapshot); Sleep(10);
    }
    return 0;
}
static BOOL conflicting_module(DWORD pid, const wchar_t* path) {
    const wchar_t* name = wcsrchr(path, L'\\');
    if (!name) return TRUE;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (snapshot == INVALID_HANDLE_VALUE) return TRUE;
    MODULEENTRY32W entry = {0}; entry.dwSize = sizeof(entry); BOOL conflict = FALSE;
    if (Module32FirstW(snapshot, &entry)) do {
        if (!_wcsicmp(entry.szModule, name + 1) && _wcsicmp(entry.szExePath, path)) { conflict = TRUE; break; }
    } while (Module32NextW(snapshot, &entry));
    CloseHandle(snapshot); return conflict;
}
static DWORD remote_call(HANDLE process, uintptr_t function, void* argument, DWORD* result) {
    HANDLE thread = CreateRemoteThread(process, NULL, 0, (LPTHREAD_START_ROUTINE)function, argument, 0, NULL);
    if (!thread) return GetLastError();
    DWORD wait = WaitForSingleObject(thread, 10000);
    DWORD error = wait == WAIT_OBJECT_0 && GetExitCodeThread(thread, result) ? 0 : ERROR_TIMEOUT;
    // Never terminate a remote thread: it may hold the loader lock.
    CloseHandle(thread); return error;
}
static int finish(HANDLE process, const uint64_t* values, DWORD error, BOOL transferred) {
    // Until a successful initialize, duplicated IPC handles belong to this helper.
    // On timeout ownership is unknown: never close handles the DLL may still use.
    if (!transferred) for (int i = 3; i <= 5; i++) {
        HANDLE local = NULL;
        if (DuplicateHandle(process, (HANDLE)(uintptr_t)values[i], GetCurrentProcess(), &local, 0, FALSE,
            DUPLICATE_CLOSE_SOURCE | DUPLICATE_SAME_ACCESS)) CloseHandle(local);
    }
    CloseHandle(process); return (int)error;
}
int wmain(int argc, wchar_t** argv) {
    // PID, absolute DLL, owner PID, HWND, remote map/mutex/stop handles, FPS.
    if (argc != 9) { fwprintf(stderr, L"Invalid game capture arguments.\n"); return ERROR_INVALID_PARAMETER; }
    uint64_t values[7];
    int indices[] = {1, 3, 4, 5, 6, 7, 8};
    for (int i = 0; i < 7; i++) if (!number(argv[indices[i]], &values[i])) return ERROR_INVALID_PARAMETER;
    DWORD pid = (DWORD)values[0];
    if (!pid || values[0] != pid || pid == GetCurrentProcessId() || !values[1] || values[6] < 1 || values[6] > 120) return ERROR_INVALID_PARAMETER;
    wchar_t path[32768];
    if (wcslen(argv[2]) < 4 || argv[2][1] != L':' || argv[2][2] != L'\\' ||
        !GetFullPathNameW(argv[2], ARRAYSIZE(path), path, NULL) ||
        GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return ERROR_BAD_PATHNAME;
    // This helper only loads its matching Xennex DLL beside itself.
    wchar_t expected[32768];
    if (!GetModuleFileNameW(NULL, expected, ARRAYSIZE(expected))) return ERROR_BAD_PATHNAME;
    wchar_t* separator = wcsrchr(expected, L'\\');
    if (!separator) return ERROR_BAD_PATHNAME;
#ifdef _WIN64
    wcscpy(separator + 1, L"Xennex.GameHook64.dll");
#else
    wcscpy(separator + 1, L"Xennex.GameHook32.dll");
#endif
    if (_wcsicmp(path, expected)) return ERROR_ACCESS_DENIED;
    DWORD window_pid = 0; GetWindowThreadProcessId((HWND)(uintptr_t)values[2], &window_pid);
    if (window_pid != pid) return ERROR_INVALID_WINDOW_HANDLE;
    HANDLE process = OpenProcess(PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ | PROCESS_DUP_HANDLE, FALSE, pid);
    if (!process) {
        DWORD error = GetLastError();
        HANDLE cleanup = OpenProcess(PROCESS_DUP_HANDLE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (cleanup && same_user(cleanup)) return finish(cleanup, values, error, FALSE);
        if (cleanup) CloseHandle(cleanup);
        return error;
    }
    if (!same_user(process)) { CloseHandle(process); return ERROR_ACCESS_DENIED; }
    if (conflicting_module(pid, path)) return finish(process, values, ERROR_ALREADY_EXISTS, FALSE);
    BOOL wow_self = FALSE, wow_target = FALSE;
    if (!IsWow64Process(GetCurrentProcess(), &wow_self) || !IsWow64Process(process, &wow_target)) return finish(process, values, ERROR_ACCESS_DENIED, FALSE);
    if (wow_self != wow_target) return finish(process, values, ERROR_BAD_EXE_FORMAT, FALSE);
    // Resolve remote functions from the actual remote module, not an assumed ASLR address.
    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    FARPROC loader = GetProcAddress(kernel, "LoadLibraryW");
    HMODULE loader_module = NULL;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)loader, &loader_module)) {
        return finish(process, values, ERROR_PROC_NOT_FOUND, FALSE);
    }
    wchar_t loader_path[MAX_PATH]; GetModuleFileNameW(loader_module, loader_path, MAX_PATH);
    uintptr_t remote_loader_module = module_base(pid, loader_path);
    if (!remote_loader_module) return finish(process, values, ERROR_MOD_NOT_FOUND, FALSE);
    uintptr_t remote_dll = module_base(pid, path);
    SIZE_T path_bytes = (wcslen(path) + 1) * sizeof(wchar_t), written;
    DWORD result = 0, error = 0;
    if (!remote_dll) {
    void* remote_path = VirtualAllocEx(process, NULL, path_bytes, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote_path) return finish(process, values, GetLastError(), FALSE);
    if (!WriteProcessMemory(process, remote_path, path, path_bytes, &written) || written != path_bytes) {
        DWORD e = GetLastError(); VirtualFreeEx(process, remote_path, 0, MEM_RELEASE); return finish(process, values, e, FALSE);
    }
    error = remote_call(process, remote_loader_module + (uintptr_t)loader - (uintptr_t)loader_module, remote_path, &result);
    // On timeout keep the tiny argument allocation alive; freeing it could corrupt the active loader.
    if (!error) VirtualFreeEx(process, remote_path, 0, MEM_RELEASE);
    remote_dll = !error ? module_base(pid, path) : 0;
    if (!remote_dll) return finish(process, values, error ? error : ERROR_DLL_INIT_FAILED, FALSE);
    }
    HMODULE local = LoadLibraryExW(path, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!local) return finish(process, values, ERROR_DLL_INIT_FAILED, FALSE);
    FARPROC initialize = GetProcAddress(local, "XennexGameInitialize");
    if (!initialize) initialize = GetProcAddress(local, "XennexGameInitialize@4");
    if (!initialize) initialize = GetProcAddress(local, "_XennexGameInitialize@4");
    if (!initialize) { FreeLibrary(local); return finish(process, values, ERROR_PROC_NOT_FOUND, FALSE); }
    uintptr_t function = remote_dll + (uintptr_t)initialize - (uintptr_t)local;
    FreeLibrary(local);
    XgcConfig config = { XGC_VERSION, pid, (uint32_t)values[1], (uint32_t)values[6], values[2], values[3], values[4], values[5] };
    void* remote_config = VirtualAllocEx(process, NULL, sizeof(config), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remote_config) return finish(process, values, ERROR_NOT_ENOUGH_MEMORY, FALSE);
    if (!WriteProcessMemory(process, remote_config, &config, sizeof(config), &written) || written != sizeof(config)) {
        VirtualFreeEx(process, remote_config, 0, MEM_RELEASE); return finish(process, values, ERROR_WRITE_FAULT, FALSE);
    }
    error = remote_call(process, function, remote_config, &result);
    if (!error) VirtualFreeEx(process, remote_config, 0, MEM_RELEASE);
    if (result) fwprintf(stderr, L"Game capture initialization failed: %lu\n", result);
    return finish(process, values, error ? error : result, error || !result);
}

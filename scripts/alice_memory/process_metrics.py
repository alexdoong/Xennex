"""Process RSS/peak working set; these measurements are not tensor byte counts."""
from __future__ import annotations

import ctypes
import os
import sys
import time


def memory_usage() -> dict:
    if sys.platform == "win32":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "Process memory measurement failed.")
        return {"rss_bytes": counters.WorkingSetSize, "peak_rss_bytes": counters.PeakWorkingSetSize,
                "method": "Windows process working set", "pid": os.getpid()}
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {"rss_bytes": None, "peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024,
            "method": "getrusage peak RSS; current RSS unavailable", "pid": os.getpid()}


def physical_memory() -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Physical RAM admission requires the validated Windows probe.")
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total", "available", "total_page", "available_page",
                       "total_virtual", "available_virtual", "available_extended")]]
    status = Status()
    status.length = ctypes.sizeof(status)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(Status),)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError(ctypes.get_last_error(), "Physical RAM measurement failed.")
    return {"total_bytes": status.total, "used_bytes": status.total - status.available,
            "measured_monotonic": time.monotonic()}


def quantiles(values: list[float]) -> dict:
    ordered = sorted(values)
    return {name: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]
            for name, fraction in (("p50", .5), ("p95", .95), ("p99", .99))}


class Budget:
    def __init__(self, steps: int, seconds: float) -> None:
        if type(steps) is not int or not 1 <= steps <= 100_000:
            raise ValueError("Step budget must be between 1 and 100000.")
        if not isinstance(seconds, (int, float)) or not 0 < seconds <= 3600:
            raise ValueError("Wall-clock budget must be between 0 and 3600 seconds.")
        self.steps, self.seconds = steps, seconds
        self.started = time.perf_counter()

    def check(self, completed: int) -> None:
        if completed > self.steps or time.perf_counter() - self.started > self.seconds:
            raise TimeoutError("Alice experiment reached its explicit execution budget.")

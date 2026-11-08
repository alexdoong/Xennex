using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal sealed class EncoderPollTimer : IDisposable
{
    private readonly SafeWaitHandle timer;
    internal EncoderPollTimer()
    {
        timer = CreateWaitableTimerEx(IntPtr.Zero, null, 2, 0x100002);
        if (timer.IsInvalid) { timer.Dispose(); throw new Win32Exception(); }
    }
    internal void Wait()
    {
        long due = -10000; // Private1ms wait; no busy spin or global timer-resolution setting.
        if (!SetWaitableTimer(timer, ref due, 0, IntPtr.Zero, IntPtr.Zero, false) || WaitForSingleObject(timer, 1000) != 0)
            throw new Win32Exception();
    }
    public void Dispose() => timer.Dispose();
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern SafeWaitHandle CreateWaitableTimerEx(IntPtr attributes, string? name, uint flags, uint access);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWaitableTimer(SafeWaitHandle timer, ref long due, int period, IntPtr callback, IntPtr argument, [MarshalAs(UnmanagedType.Bool)] bool resume);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern uint WaitForSingleObject(SafeWaitHandle handle, uint timeout);
}

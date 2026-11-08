using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace Xennex.CaptureWorker;

internal static class GameCapture
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern SafeWaitHandle CreateWaitableTimerEx(IntPtr attributes, string? name, uint flags, uint access);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool SetWaitableTimer(SafeWaitHandle timer, ref long due, int period, IntPtr callback, IntPtr argument, bool resume);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(SafeWaitHandle handle, uint timeout);
    internal static async Task RunAsync(int pid, long hwnd, long startTicks, int fps, int maxWidth, int maxHeight, int quality,
        Func<bool> running, Action<byte[]> publish, Action<string> status, Action<FrameStageSample> measure)
    {
        using var game = Process.GetProcessById(pid);
        using var session = await NativeGameSession.OpenAsync(pid, hwnd, startTicks, fps, Path.Combine(AppContext.BaseDirectory, "GameCapture")).ConfigureAwait(false);
        using var encoder = new GameFrameEncoder(quality);
        using var timer = CreateWaitableTimerEx(IntPtr.Zero, null, 2, 0x1F0003);
        if (timer.IsInvalid) throw new System.ComponentModel.Win32Exception();
        var idle = Stopwatch.StartNew(); bool waiting = true;
        status("starting");
        while (running() && !game.HasExited)
        {
            if (session.TryRead(out var frame))
            {
                publish(encoder.Encode(frame, maxWidth, maxHeight)); measure(encoder.LastSample); idle.Restart();
                if (waiting) { status("ready"); waiting = false; }
            }
            else
            {
                if (idle.Elapsed > TimeSpan.FromSeconds(20)) throw new InvalidOperationException("O jogo não produziu quadros OpenGL por20s. Confira o jogo ou selecione outro método de captura.");
                if (!waiting && idle.Elapsed > TimeSpan.FromSeconds(3)) { status("waiting"); waiting = true; }
                long due = -10000; // Private high-resolution 1ms timer; no global timer-resolution change.
                if (!SetWaitableTimer(timer, ref due, 0, IntPtr.Zero, IntPtr.Zero, false) || WaitForSingleObject(timer, 1000) != 0)
                    throw new System.ComponentModel.Win32Exception();
            }
        }
    }
}

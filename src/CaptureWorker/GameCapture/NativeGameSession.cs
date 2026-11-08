using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace Xennex.CaptureWorker;

internal readonly record struct GameFrame(int Width, int Height, byte[] Pixels, long Id, long Timestamp);

// One selected process, one anonymous surface. No retry, monitor fallback or network endpoint.
internal sealed class NativeGameSession : IDisposable
{
    internal const int HeaderSize = 128, Capacity = 32 * 1024 * 1024;
    readonly MemoryMappedFile mapping = MemoryMappedFile.CreateNew(null, HeaderSize + Capacity);
    readonly Mutex mutex = new();
    readonly EventWaitHandle stop = new(false, EventResetMode.ManualReset);
    readonly MemoryMappedViewAccessor view;
    byte[] pixels = Array.Empty<byte>();
    long lastId;
    bool disposed;
    [DllImport("kernel32.dll", SetLastError = true)] static extern SafeProcessHandle OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool DuplicateHandle(IntPtr source, IntPtr handle, SafeProcessHandle target, out IntPtr duplicate, uint access, bool inherit, uint options);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool IsWow64Process(SafeProcessHandle process, out bool wow);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);

    NativeGameSession()
    {
        view = mapping.CreateViewAccessor();
        view.Write(0, 0x31434758u); view.Write(4, 1u); view.Write(8, (uint)HeaderSize); view.Write(12, (uint)Capacity);
    }

    internal static async Task<NativeGameSession> OpenAsync(int pid, long hwnd, long startTicks, int fps, string directory)
    {
        if (pid <= 0 || pid == Environment.ProcessId || hwnd == 0 || fps < 1 || fps > 120) throw new ArgumentException("Invalid selected game");
        GetWindowThreadProcessId(new IntPtr(hwnd), out uint actualPid);
        using var selected = Process.GetProcessById(pid);
        if (actualPid != pid || selected.HasExited || (startTicks != 0 && selected.StartTime.ToUniversalTime().Ticks != startTicks))
            throw new InvalidOperationException("O processo/janela escolhido mudou; selecione o jogo novamente.");
        using var target = OpenProcess(0x1040, false, pid);
        if (target.IsInvalid || !IsWow64Process(target, out bool wow)) throw new Win32Exception();
        string bits = Environment.Is64BitOperatingSystem && !wow ? "64" : "32";
        directory = Path.GetFullPath(directory);
        string dll = Path.Combine(directory, $"Xennex.GameHook{bits}.dll"), helperPath = Path.Combine(directory, $"Xennex.GameInjector{bits}.exe");
        VerifyBinary(dll); VerifyBinary(helperPath); // Before any target-process modification.
        var session = new NativeGameSession();
        var handles = new IntPtr[3]; bool launched = false;
        try
        {
            handles[0] = Duplicate(session.mapping.SafeMemoryMappedFileHandle.DangerousGetHandle(), target);
            handles[1] = Duplicate(session.mutex.SafeWaitHandle.DangerousGetHandle(), target);
            handles[2] = Duplicate(session.stop.SafeWaitHandle.DangerousGetHandle(), target);
            var start = new ProcessStartInfo(helperPath) { UseShellExecute = false, CreateNoWindow = true };
            foreach (string value in new[] { pid.ToString(), dll, Environment.ProcessId.ToString(), hwnd.ToString(), handles[0].ToString(), handles[1].ToString(), handles[2].ToString(), fps.ToString() }) start.ArgumentList.Add(value);
            using var helper = Process.Start(start) ?? throw new InvalidOperationException("Game helper did not start");
            launched = true;
            // Helper bounds its remote calls. Never terminate a remote game thread.
            await helper.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(25)).ConfigureAwait(false);
            if (helper.ExitCode != 0) throw new InvalidOperationException($"Captura de jogo não iniciou (código {helper.ExitCode}). Se houve timeout, mudança do contexto gráfico ou outra versão carregada, reinicie o jogo antes de tentar novamente.");
            return session;
        }
        catch
        {
            session.Dispose();
            if (!launched) foreach (var handle in handles) CloseRemote(target, handle);
            throw;
        }
    }

    internal static void VerifyBinary(string path)
    {
        if (!File.Exists(path) || (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new InvalidOperationException("Binário de captura ausente ou caminho indireto.");
        using var pin = typeof(NativeGameSession).Assembly.GetManifestResourceStream("Xennex.PublisherThumbprint") ?? throw new InvalidOperationException("Publisher pin missing");
        using var reader = new StreamReader(pin);
        string expected = reader.ReadToEnd().Trim();
        using var certificate = new X509Certificate2(X509Certificate.CreateFromSignedFile(path));
        if (!certificate.Thumbprint.Equals(expected, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Publicador da captura inválido.");
        uint status = Xennex.Build.AuthenticodeVerification.Check(path);
        if (status != 0 && status != 0x800B0109) throw new InvalidOperationException($"Assinatura da captura inválida (0x{status:X8}).");
    }

    internal static int ValidateFrame(int width, int height, int stride, int format)
    {
        if (width < 2 || height < 2 || width > 8192 || height > 8192 || stride != (long)width * 4 || format != 1 || (long)stride * height > Capacity)
            throw new InvalidDataException("Invalid game capture frame");
        return stride * height;
    }

    internal bool TryRead(out GameFrame frame)
    {
        frame = default;
        if (disposed) return false;
        int status = view.ReadInt32(16);
        if (status == -1) throw new InvalidOperationException("Captura OpenGL falhou (" + view.ReadInt32(20) + "). Se o contexto gráfico mudou, reinicie o jogo.");
        if (status == 3) throw new InvalidOperationException("O hook de captura foi encerrado.");
        bool held;
        try { held = mutex.WaitOne(0); }
        catch (AbandonedMutexException) { held = true; }
        if (!held) return false;
        try
        {
            long id = view.ReadInt64(40);
            if (id <= lastId) return false;
            int width = view.ReadInt32(24), height = view.ReadInt32(28);
            int count = ValidateFrame(width, height, view.ReadInt32(32), view.ReadInt32(36));
            if (pixels.Length != count) pixels = new byte[count];
            view.ReadArray(HeaderSize, pixels, 0, count);
            lastId = id; frame = new GameFrame(width, height, pixels, id, view.ReadInt64(48)); return true;
        }
        finally { mutex.ReleaseMutex(); }
    }

    static IntPtr Duplicate(IntPtr handle, SafeProcessHandle target)
    {
        if (!DuplicateHandle(GetCurrentProcess(), handle, target, out var result, 0, false, 2)) throw new Win32Exception();
        return result;
    }
    static void CloseRemote(SafeProcessHandle target, IntPtr handle)
    {
        if (handle != IntPtr.Zero && DuplicateHandle(target.DangerousGetHandle(), handle, new SafeProcessHandle(GetCurrentProcess(), false), out var local, 0, false, 3))
            using (new SafeFileHandle(local, true)) { }
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        stop.Set(); view.Dispose(); mapping.Dispose(); mutex.Dispose(); stop.Dispose(); pixels = Array.Empty<byte>();
        // DLL owns its duplicate handles and notices this process ending as well.
    }
}

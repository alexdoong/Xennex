using System.Runtime.InteropServices;

internal static class NativeProbeLibraries
{
    private static readonly Dictionary<string, IntPtr> loaded = new();
    static NativeProbeLibraries()
    {
        NativeLibrary.SetDllImportResolver(typeof(NativeProbeLibraries).Assembly, (name, _, _) =>
        {
            string? relative = name switch {
                "xennex-prototype-rtc" => Path.Combine("NativeWebRtc", "bin", "libdatachannel.dll"),
                "xennex-prototype-amf" => Path.Combine("NativeAmf", "Xennex.AmfProbe.dll"),
                _ => null,
            };
            if (relative == null) return IntPtr.Zero;
            lock (loaded)
            {
                if (!loaded.TryGetValue(name, out IntPtr pointer)) loaded[name] = pointer = NativeLibrary.Load(
                    Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", relative)));
                return pointer; // Modules intentionally live for the isolated process lifetime.
            }
        });
    }
    internal static void Ensure() { if (IntPtr.Size != 8) throw new PlatformNotSupportedException("Native probes require x64."); }
}

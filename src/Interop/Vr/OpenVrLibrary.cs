using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using Valve.VR;

namespace Xennex.Interop.Vr;

internal static class OpenVrLibrary
{
    private static readonly object Gate = new();
    private static bool _registered;
    private static IntPtr _library;

    public static void Register()
    {
        lock (Gate)
        {
            if (_registered) return;
            NativeLibrary.SetDllImportResolver(typeof(OpenVR).Assembly, Resolve);
            _registered = true;
        }
    }

    private static IntPtr Resolve(string name, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (name != "openvr_api") return IntPtr.Zero;
        lock (Gate)
        {
            if (_library != IntPtr.Zero) return _library;
            var registration = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "openvr", "openvrpaths.vrpath");
            if (!File.Exists(registration) || new FileInfo(registration).Length > 65536)
                throw new InvalidOperationException("Instale e abra o SteamVR antes de abrir a Biblioteca no VR.");
            using var json = JsonDocument.Parse(File.ReadAllText(registration));
            if (!json.RootElement.TryGetProperty("runtime", out var runtimes) || runtimes.ValueKind != JsonValueKind.Array)
                throw new InvalidOperationException("O runtime SteamVR não está registrado.");
            foreach (var runtime in runtimes.EnumerateArray())
            {
                var root = runtime.GetString();
                if (string.IsNullOrWhiteSpace(root) || !Path.IsPathFullyQualified(root)) continue;
                var path = Path.Combine(Path.GetFullPath(root), "bin", "win64", "openvr_api.dll");
                if (!File.Exists(path)) continue;
                _library = NativeLibrary.Load(path);
                return _library;
            }
            throw new InvalidOperationException("A DLL do SteamVR registrado não foi encontrada. Repare a instalação do SteamVR.");
        }
    }
}

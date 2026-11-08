using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using Vortice.MediaFoundation;

if (args.Contains("--contract-tests")) { ProbeContracts.Run(); return; }
if (args.Contains("--describe-video-api"))
{
    var names = new[] { "ID3D11VideoDevice", "ID3D11VideoContext", "ID3D11VideoContext1", "VideoProcessorContentDescription", "VideoProcessorInputViewDescription", "VideoProcessorOutputViewDescription", "VideoProcessorStream", "VideoProcessorColorSpace" };
    foreach (var type in typeof(Vortice.Direct3D11.ID3D11Device).Assembly.GetTypes().Where(type => names.Contains(type.Name)))
    {
        Console.WriteLine(type.FullName);
        foreach (var member in type.GetMembers(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Where(member => !type.Name.StartsWith("ID3D11") || member.Name.Contains("VideoProcessor"))) Console.WriteLine("  " + member);
    }
    return;
}
if (args.Contains("--describe-api"))
{
    var names = new[] { "IMFActivate", "IMFTransform", "IMFMediaType", "RegisterTypeInfo", "IMFDXGIDeviceManager", "IMFAttributes", "IMFSample", "IMFMediaBuffer", "IMFMediaEvent", "OutputDataBuffer", "OutputStreamInfo" };
    foreach (var type in typeof(MediaFactory).Assembly.GetTypes().Where(type => names.Contains(type.Name) || type.Name.Contains("AttributeKeys") || type.Name.Contains("Guids")))
    {
        Console.WriteLine(type.FullName);
        foreach (var member in type.GetMembers(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
            .Where(member => names.Contains(type.Name) || member.Name.Contains("Enum") || member.Name.Contains("Friendly") || member.Name.Contains("Async") || member.Name.Contains("Activate") || member.Name.Contains("Type") || member.Name.Contains("Encoder") || member.Name.Contains("Luid") || member.Name.Contains("D3D")))
            Console.WriteLine("  " + member);
    }
    return;
}
if (!args.Contains("--probe") && !args.Contains("--encode"))
{
    Console.Error.WriteLine("Use --probe for opt-in local hardware encoder inventory. No desktop/camera capture. Profiles are not tested yet.");
    Environment.ExitCode = 2;
    return;
}
int com = NativeMethods.CoInitializeEx(IntPtr.Zero, 0);
Marshal.ThrowExceptionForHR(com);
try
{
    MediaFactory.MFStartup().CheckError();
    try
    {
        if (args.Contains("--encode"))
        {
            int candidateArgument = Array.IndexOf(args, "--candidate");
            uint candidate = candidateArgument >= 0 && candidateArgument + 1 < args.Length ? uint.Parse(args[candidateArgument + 1]) : 0;
            int Number(string key, int fallback) { int index = Array.IndexOf(args, key); return index >= 0 && index + 1 < args.Length ? int.Parse(args[index + 1]) : fallback; }
            long LongNumber(string key) { int index = Array.IndexOf(args, key); return index >= 0 && index + 1 < args.Length ? long.Parse(args[index + 1]) : 0; }
            if (args.Contains("--cpu-control") && args.Contains("--bgra")) throw new ArgumentException("CPU control and BGRA conversion are separate experiments.");
            var input = args.Contains("--cpu-control") ? ProbeInput.CpuControl : args.Contains("--bgra") ? ProbeInput.BgraTexture : ProbeInput.Nv12Texture;
            var options = new EncoderProbeOptions((uint)Number("--adapter", 0), candidate, Number("--width", 640), Number("--height", 360),
                Number("--fps", 30), Number("--frames", 8), input, args.Contains("--color"), WgcHwnd: LongNumber("--wgc-fixture-hwnd"), WgcPid: Number("--wgc-fixture-pid", 0),
                Backend: args.Contains("--amf") ? ProbeBackend.Amf : ProbeBackend.MediaFoundation);
            if (args.Contains("--native-rtc")) { NativeRtcProbe.Run(options, args.Contains("--drop-initial-idr")); return; }
            var encoded = NativeEncoderProbe.Run(options);
            Console.WriteLine(JsonSerializer.Serialize(new { Schema = "xennex-native-gpu-encode-v1", Result = encoded }, new JsonSerializerOptions { WriteIndented = true }));
            return;
        }
        var report = new { Schema = "xennex-native-encoder-inventory-v1", Status = "inventory-only",
            Note = "Enumerated/activated hardware transforms do not prove a working profile, GPU texture input, encoding, zero-copy or WebRTC delivery.",
            Adapters = EncoderInventory.Read() };
        Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
    }
    finally { MediaFactory.MFShutdown().CheckError(); }
}
finally { NativeMethods.CoUninitialize(); }

internal static class NativeMethods
{
    [DllImport("ole32.dll")] internal static extern int CoInitializeEx(IntPtr reserved, uint flags);
    [DllImport("ole32.dll")] internal static extern void CoUninitialize();
}

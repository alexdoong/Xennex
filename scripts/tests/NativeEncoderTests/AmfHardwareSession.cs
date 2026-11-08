using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Vortice.Direct3D11;

internal sealed class AmfHardwareSession : SafeHandleZeroOrMinusOneIsInvalid
{
    private const string Library = "xennex-prototype-amf";
    private AmfHardwareSession(IntPtr pointer) : base(true) => SetHandle(pointer);
    internal static AmfHardwareSession Create(ID3D11Device device, EncoderProbeOptions options)
    {
        NativeProbeLibraries.Ensure();
        Check(Open(device.NativePointer, options.Width, options.Height, options.Fps, 6000000, (int)H264Level.For(options.Width, options.Height, options.Fps), out IntPtr pointer));
        return new(pointer);
    }
    internal EncoderRateControl Settings()
    {
        Check(GetSettings(this, out uint numerator, out uint denominator, out uint bitrate, out uint mode));
        if (bitrate != 6000000 || mode != 1 || numerator == 0 || denominator == 0) throw new NotSupportedException("AMF did not retain requested CBR/profile timing.");
        ulong version = RuntimeVersion(this);
        string runtime = $"{version >> 48}.{version >> 32 & 65535}.{version >> 16 & 65535}.{version & 65535}";
        return new(6000000, bitrate, mode, $"{numerator}/{denominator}", $"{numerator}/{denominator}", null, "AMF", runtime);
    }
    internal bool TrySubmit(ID3D11Texture2D texture, long timestamp, int fps, bool keyframe) => Check(Submit(this, texture.NativePointer, timestamp, 10000000L / fps, keyframe ? 1 : 0)) == 0;
    internal bool TryDrain() => Check(Drain(this)) == 0;
    internal (byte[] Bytes, long Timestamp)? Poll(out bool ended)
    {
        int result = Check(PollPacket(this, out IntPtr pointer, out int length, out long timestamp));
        ended = result == 2;
        if (result != 0) return null;
        try
        {
            if (pointer == IntPtr.Zero || length is <= 0 or > 16777216 || timestamp < 0) throw new InvalidOperationException("AMF returned an invalid bounded packet.");
            var bytes = new byte[length]; Marshal.Copy(pointer, bytes, 0, length);
            return (bytes, timestamp);
        }
        finally { ReleasePacket(this); }
    }
    protected override bool ReleaseHandle() { Close(handle); return true; }
    private static int Check(int result) => result < 0 ? throw new InvalidOperationException($"AMF operation failed ({result}).") : result;
    [DllImport(Library, EntryPoint = "xennex_amf_open", CallingConvention = CallingConvention.Cdecl)] private static extern int Open(IntPtr device, int width, int height, int fps, int bitrate, int level, out IntPtr encoder);
    [DllImport(Library, EntryPoint = "xennex_amf_close", CallingConvention = CallingConvention.Cdecl)] private static extern void Close(IntPtr encoder);
    [DllImport(Library, EntryPoint = "xennex_amf_submit", CallingConvention = CallingConvention.Cdecl)] private static extern int Submit(AmfHardwareSession encoder, IntPtr texture, long timestamp, long duration, int keyframe);
    [DllImport(Library, EntryPoint = "xennex_amf_poll", CallingConvention = CallingConvention.Cdecl)] private static extern int PollPacket(AmfHardwareSession encoder, out IntPtr bytes, out int length, out long timestamp);
    [DllImport(Library, EntryPoint = "xennex_amf_release_packet", CallingConvention = CallingConvention.Cdecl)] private static extern void ReleasePacket(AmfHardwareSession encoder);
    [DllImport(Library, EntryPoint = "xennex_amf_drain", CallingConvention = CallingConvention.Cdecl)] private static extern int Drain(AmfHardwareSession encoder);
    [DllImport(Library, EntryPoint = "xennex_amf_runtime_version", CallingConvention = CallingConvention.Cdecl)] private static extern ulong RuntimeVersion(AmfHardwareSession encoder);
    [DllImport(Library, EntryPoint = "xennex_amf_settings", CallingConvention = CallingConvention.Cdecl)] private static extern int GetSettings(AmfHardwareSession encoder, out uint numerator, out uint denominator, out uint bitrate, out uint mode);
}

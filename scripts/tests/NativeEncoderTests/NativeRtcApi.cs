using System.Runtime.InteropServices;
using System.Text;

// Pinned libdatachannel v0.24.6 C API. Prototype only, Windows x64/cdecl.
internal static class NativeRtcApi
{
    private const string Library = "xennex-prototype-rtc";
    internal static void Load()
    {
        if (IntPtr.Size != 8) throw new PlatformNotSupportedException("Native transport probe requires x64.");
        NativeProbeLibraries.Ensure();
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct Configuration
    {
        internal IntPtr IceServers;
        internal int IceServersCount;
        internal IntPtr ProxyServer, BindAddress;
        internal int CertificateType, TransportPolicy;
        internal byte EnableIceTcp, EnableIceUdpMux, DisableAutoNegotiation, ForceMediaTransport;
        internal ushort PortBegin, PortEnd;
        internal int Mtu, MaxMessageSize;
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct Packetizer
    {
        internal uint Ssrc;
        internal IntPtr Cname;
        internal byte PayloadType;
        internal uint ClockRate;
        internal ushort SequenceNumber;
        internal uint Timestamp;
        internal ushort MaxFragmentSize;
        internal int NalSeparator, ObuPacketization;
        internal byte PlayoutDelayId;
        internal ushort PlayoutDelayMin, PlayoutDelayMax;
        internal byte ColorSpaceId, ChromaHorz, ChromaVert, ColorRange, Primaries, Transfer, Matrix;
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] internal delegate void StateCallback(int id, int state, IntPtr user);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] internal delegate void OpenCallback(int id, IntPtr user);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] internal delegate void LogCallback(int level, IntPtr message);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern void rtcInitLogger(int level, LogCallback? callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcCreatePeerConnection(in Configuration config);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcDeletePeerConnection(int pc);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcDeleteTrack(int track);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern void rtcCleanup();
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern void rtcSetUserPointer(int id, IntPtr pointer);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetGatheringStateChangeCallback(int pc, StateCallback? callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetStateChangeCallback(int pc, StateCallback? callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetIceStateChangeCallback(int pc, StateCallback? callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetOpenCallback(int track, OpenCallback? callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)] internal static extern int rtcAddTrack(int pc, string sdp);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetH264Packetizer(int track, in Packetizer packetizer);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcChainRtcpSrReporter(int track);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcChainRtcpNackResponder(int track, uint packets);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcChainPliHandler(int track, OpenCallback callback);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)] internal static extern int rtcSetLocalDescription(int pc, string type);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)] internal static extern int rtcSetRemoteDescription(int pc, string sdp, string type);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl, CharSet = CharSet.Ansi)] internal static extern int rtcGetLocalDescription(int pc, StringBuilder? sdp, int capacity);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSetTrackRtpTimestamp(int track, uint timestamp);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] internal static extern int rtcSendMessage(int track, byte[] bytes, int length);
    internal static int Check(int result) => result < 0 ? throw new InvalidOperationException($"Native RTC operation failed ({result}).") : result;
}

using System.Runtime.InteropServices;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using static NativeRtcApi;

internal static class NativeRtcProbe
{
    internal static void Run(EncoderProbeOptions options, bool dropInitialIdr = false)
    {
        options = options with { ConstrainedBaseline = true };
        options.Validate();
        // Discover the actual encoder profile from an independently validated warm-up.
        byte[]? initial = null;
        NativeEncoderProbe.Run(options with { Frames = 8 }, (packet, _) => initial ??= packet);
        string profile = H264AnnexB.Profile(H264AnnexB.Units(initial!));
        Load();
        LogCallback onLog = (_, pointer) =>
        {
            string text = Marshal.PtrToStringUTF8(pointer) ?? "";
            var diagnostic = System.Text.RegularExpressions.Regex.Match(text, @"(?:SSL|X509|CTR_DRBG|PK|ECDSA|BIGNUM|ENTROPY) - [A-Za-z /()'-]{1,180}");
            if (diagnostic.Success) Console.Error.WriteLine("Synthetic TLS diagnostic: " + diagnostic.Value);
        };
        rtcInitLogger(3, onLog);
        // ICE excludes loopback candidates. Bind only this test's encrypted peer
        // transport to one active interface; no local privileged server is exposed.
        string localAddress = NetworkInterface.GetAllNetworkInterfaces()
            .Where(item => item.OperationalStatus == OperationalStatus.Up && item.NetworkInterfaceType is NetworkInterfaceType.Ethernet or NetworkInterfaceType.Wireless80211)
            .OrderByDescending(item => item.GetIPProperties().GatewayAddresses.Count > 0)
            .SelectMany(item => item.GetIPProperties().UnicastAddresses)
            .Select(item => item.Address).FirstOrDefault(item => item.AddressFamily == AddressFamily.InterNetwork && !System.Net.IPAddress.IsLoopback(item))?.ToString()
            ?? throw new NotSupportedException("No active IPv4 interface for synthetic ICE interoperability.");
        IntPtr address = Marshal.StringToCoTaskMemUTF8(localAddress), cname = Marshal.StringToCoTaskMemUTF8("synthetic-encoder");
        int pc = -1, track = -1;
        using var gathered = new ManualResetEventSlim();
        using var opened = new ManualResetEventSlim();
        StateCallback onGathered = (_, state, _) => { if (state == 2) gathered.Set(); };
        OpenCallback onOpen = (_, _) => opened.Set();
        StateCallback onState = (_, state, _) => Console.Error.WriteLine($"Synthetic native peer state: {state}");
        StateCallback onIce = (_, state, _) => Console.Error.WriteLine($"Synthetic native ICE state: {state}");
        int pliReceived = 0, pliPending = 0;
        OpenCallback onPli = (_, _) => { Interlocked.Increment(ref pliReceived); Interlocked.Exchange(ref pliPending, 1); };
        try
        {
            var config = new Configuration { BindAddress = address, DisableAutoNegotiation = 1, ForceMediaTransport = 1 };
            pc = Check(rtcCreatePeerConnection(config));
            rtcSetUserPointer(pc, (IntPtr)1);
            Check(rtcSetStateChangeCallback(pc, onState));
            Check(rtcSetIceStateChangeCallback(pc, onIce));
            Check(rtcSetGatheringStateChangeCallback(pc, onGathered));
            const uint ssrc = 246810;
            string media = $"m=video 9 UDP/TLS/RTP/SAVPF 96\r\nc=IN IP4 0.0.0.0\r\na=mid:video\r\na=sendonly\r\na=rtcp-mux\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1;profile-level-id={profile};level-asymmetry-allowed=1\r\na=rtcp-fb:96 nack\r\na=rtcp-fb:96 nack pli\r\na=ssrc:{ssrc} cname:synthetic-encoder\r\na=ssrc:{ssrc} msid:synthetic-stream synthetic-video\r\n";
            track = Check(rtcAddTrack(pc, media));
            rtcSetUserPointer(track, (IntPtr)1);
            Check(rtcSetOpenCallback(track, onOpen));
            var packetizer = new Packetizer { Ssrc = ssrc, Cname = cname, PayloadType = 96, ClockRate = 90000, NalSeparator = 3, MaxFragmentSize = 1100 };
            Check(rtcSetH264Packetizer(track, packetizer));
            Check(rtcChainRtcpSrReporter(track));
            Check(rtcChainRtcpNackResponder(track, 512));
            Check(rtcChainPliHandler(track, onPli));
            Check(rtcSetLocalDescription(pc, "offer"));
            if (!gathered.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("Native ICE gathering timed out.");
            int length = Check(rtcGetLocalDescription(pc, null, 0));
            if (length is < 1 or > 65536) throw new InvalidOperationException("Native SDP size exceeded.");
            var description = new StringBuilder(length);
            Check(rtcGetLocalDescription(pc, description, description.Capacity));
            int candidates = description.ToString().Split('\n').Count(line => line.StartsWith("a=candidate:", StringComparison.Ordinal));
            Console.Error.WriteLine($"Synthetic native ICE candidates: {candidates}");
            if (candidates == 0) throw new NotSupportedException("Native ICE did not gather a candidate on the selected interface.");
            // SDP exists only in the parent/child pipe. Test runner must never persist it.
            Console.WriteLine(JsonSerializer.Serialize(new { Type = "offer", Sdp = description.ToString() }));
            string answer = ReadBoundedLine();
            using var message = JsonDocument.Parse(answer);
            if (message.RootElement.GetProperty("Type").GetString() != "answer") throw new ArgumentException("Expected test browser answer.");
            string sdp = message.RootElement.GetProperty("Sdp").GetString() ?? throw new ArgumentException("Missing answer.");
            Check(rtcSetRemoteDescription(pc, sdp, "answer"));
            if (!opened.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("Native media track did not open.");
            Console.WriteLine(JsonSerializer.Serialize(new { Type = "streaming", DurationMs = options.Frames * 1000 / options.Fps }));
            int sent = 0, encoded = 0, idrObserved = 0, skipped = 0;
            long lastKeyframe = 0;
            byte[] parameters = Array.Empty<byte>();
            var nalBytes = new Dictionary<int, long>();
            var result = NativeEncoderProbe.Run(options, (bytes, timestamp) =>
            {
                var units = H264AnnexB.Units(bytes);
                foreach (var unit in units) { int type = unit[0] & 31; nalBytes[type] = nalBytes.GetValueOrDefault(type) + unit.Length; }
                encoded++;
                if (encoded == 1 && H264AnnexB.Profile(units) != profile)
                    throw new NotSupportedException("Encoder profile changed after negotiation.");
                if (encoded == 1) parameters = units.Where(unit => (unit[0] & 31) is 7 or 8).SelectMany(unit => new byte[] { 0, 0, 0, 1 }.Concat(unit)).ToArray();
                bool idr = units.Any(unit => (unit[0] & 31) == 5);
                if (idr) idrObserved++;
                if (dropInitialIdr && encoded == 1) { skipped++; return; }
                if (idr && !(units.Any(unit => (unit[0] & 31) == 7) && units.Any(unit => (unit[0] & 31) == 8))) bytes = parameters.Concat(bytes).ToArray();
                Check(rtcSetTrackRtpTimestamp(track, checked((uint)(timestamp * 9 / 1000))));
                Check(rtcSendMessage(track, bytes, bytes.Length));
                sent++;
            }, () =>
            {
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                if (Volatile.Read(ref pliPending) == 0 || (now - lastKeyframe) * 1000.0 / System.Diagnostics.Stopwatch.Frequency < 500) return false;
                if (Interlocked.Exchange(ref pliPending, 0) == 0) return false;
                lastKeyframe = now;
                return true;
            });
            Thread.Sleep(500);
            Console.WriteLine(JsonSerializer.Serialize(new { Type = "result", Schema = "xennex-native-rtc-probe-v1", Sent = sent, Profile = profile, Encoder = result,
                PliReceived = pliReceived, IdrObserved = idrObserved, SkippedInitialIdr = skipped, NalPayloadBytes = nalBytes }));
        }
        finally
        {
            if (track >= 0) { rtcSetOpenCallback(track, null); rtcDeleteTrack(track); }
            if (pc >= 0) { rtcSetGatheringStateChangeCallback(pc, null); rtcSetStateChangeCallback(pc, null); rtcSetIceStateChangeCallback(pc, null); rtcDeletePeerConnection(pc); }
            rtcCleanup();
            rtcInitLogger(0, null);
            GC.KeepAlive(onGathered); GC.KeepAlive(onOpen);
            GC.KeepAlive(onState); GC.KeepAlive(onIce);
            GC.KeepAlive(onLog);
            GC.KeepAlive(onPli);
            Marshal.FreeCoTaskMem(address); Marshal.FreeCoTaskMem(cname);
        }
    }

    private static string ReadBoundedLine()
    {
        var task = Task.Run(() =>
        {
            var text = new StringBuilder();
            while (text.Length < 65536)
            {
                int next = Console.In.Read();
                if (next == '\n') return text.ToString();
                if (next < 0) throw new EndOfStreamException("Browser answer pipe closed.");
                text.Append((char)next);
            }
            throw new ArgumentException("Browser answer exceeded bounded input.");
        });
        if (!task.Wait(TimeSpan.FromSeconds(15))) throw new TimeoutException("Browser answer timed out.");
        return task.GetAwaiter().GetResult();
    }
}

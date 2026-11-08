using System.Diagnostics;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;

internal static class AmfTextureProbe
{
    internal static TextureEncodeResult Run(EncoderProbeOptions options, Action<byte[], long>? onPacket = null, Func<bool>? requestKeyframe = null)
    {
        options.Validate();
        if (options.Input != ProbeInput.BgraTexture) throw new NotSupportedException("AMF probe accepts only the bounded BGRA conversion path.");
        using var factory = Vortice.DXGI.DXGI.CreateDXGIFactory1<IDXGIFactory1>();
        factory.EnumAdapters1(options.Adapter, out var adapter).CheckError();
        using (adapter)
        {
            D3D11.D3D11CreateDevice(adapter, DriverType.Unknown, DeviceCreationFlags.BgraSupport | DeviceCreationFlags.VideoSupport,
                new[] { FeatureLevel.Level_11_0 }, out ID3D11Device device, out ID3D11DeviceContext context).CheckError();
            using (device)
            using (context)
            using (var multithread = context.QueryInterface<ID3D11Multithread>())
            {
                multithread.SetMultithreadProtected(true);
                using var converter = new GpuBgraConverter(device, context, options);
                using var encoder = AmfHardwareSession.Create(device, options);
                var settings = encoder.Settings();
                using var wgc = options.WgcHwnd != 0 ? new WgcProbeSource(device, options) : null;
                using var timer = new EncoderPollTimer();
                var clock = Stopwatch.StartNew();
                var cadence = new Xennex.Services.CaptureFrameCadence(options.Fps);
                var packets = new List<byte[]>();
                var inputTimes = new List<double>();
                long? firstCapture = null;
                double? firstCreation = null;
                (ID3D11Texture2D Texture, long Timestamp, bool Keyframe)? pending = null;
                int submitted = 0, encoded = 0, totalBytes = 0, forced = 0;
                bool draining = false, annexB = false;
                double firstOutput = -1;
                while (clock.ElapsedMilliseconds < 10000)
                {
                    var output = encoder.Poll(out bool ended);
                    if (output is { } packet)
                    {
                        if ((long)totalBytes + packet.Bytes.Length > 67108864) throw new InvalidOperationException("AMF bitstream exceeded total memory bound.");
                        converter.Complete(packet.Timestamp);
                        packets.Add(packet.Bytes); totalBytes += packet.Bytes.Length; encoded++;
                        firstOutput = firstOutput < 0 ? clock.Elapsed.TotalMilliseconds : firstOutput;
                        annexB |= packet.Bytes.AsSpan().IndexOf(new byte[] { 0, 0, 1 }) >= 0;
                        onPacket?.Invoke(packet.Bytes, packet.Timestamp);
                    }
                    if (ended || draining && encoded == options.Frames) break;
                    if (pending == null && submitted < options.Frames && converter.HasFree && cadence.ShouldCapture(clock.Elapsed.TotalMilliseconds))
                    {
                        using var captured = wgc?.TryAcquire();
                        if (wgc != null && captured == null) { timer.Wait(); continue; }
                        double at = clock.Elapsed.TotalMilliseconds;
                        firstCreation ??= at;
                        if (captured != null) firstCapture ??= captured.Timestamp;
                        long timestamp = captured == null ? (long)((at - firstCreation.Value) * 10000) : captured.Timestamp - firstCapture!.Value;
                        bool requested = requestKeyframe?.Invoke() == true;
                        if (requested) forced++;
                        pending = (converter.ConvertFrame(submitted, timestamp, captured?.Texture), timestamp, submitted == 0 || requested);
                    }
                    if (pending is { } input && encoder.TrySubmit(input.Texture, input.Timestamp, options.Fps, input.Keyframe))
                    {
                        inputTimes.Add(clock.Elapsed.TotalMilliseconds);
                        submitted++; pending = null;
                    }
                    if (submitted == options.Frames && pending == null && !draining) draining = encoder.TryDrain();
                    timer.Wait();
                }
                if (submitted != options.Frames || encoded != options.Frames)
                    throw new InvalidOperationException($"Incomplete AMF encode: {submitted}/{options.Frames} input, {encoded}/{options.Frames} output.");
                double elapsed = clock.Elapsed.TotalMilliseconds;
                using var mediaType = H264TextureProbe.VideoType("H264", options.Width, options.Height, options.Fps);
                var validation = SoftwareH264Decoder.Decode(packets, mediaType, options);
                double[] intervals = inputTimes.Zip(inputTimes.Skip(1), (before, after) => after - before).OrderBy(value => value).ToArray();
                return new("AMFVideoEncoderVCE_AVC", options.Adapter, options.Width, options.Height, options.Fps, submitted, encoded, totalBytes, firstOutput,
                    elapsed, (inputTimes.Count - 1) * 1000 / (inputTimes[^1] - inputTimes[0]), intervals[(int)Math.Ceiling(intervals.Length * .95) - 1],
                    annexB, wgc != null ? "amf-wgc-fixture-gpu-to-nv12" : "amf-bgra-gpu-to-nv12", validation,
                    wgc != null ? "encoded-and-decoded-owned-fixture" : "encoded-and-decoded-synthetic", forced, settings);
            }
        }
    }
}

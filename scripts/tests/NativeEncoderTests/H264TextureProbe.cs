using System.Diagnostics;
using System.Runtime.InteropServices;
using Vortice.Direct3D;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Vortice.MediaFoundation;
using static Vortice.MediaFoundation.MediaFactory;

internal sealed record TextureEncodeResult(string Encoder, uint Adapter, int Width, int Height, int TargetFps,
    int Submitted, int Encoded, int Bytes, double FirstOutputMs, double ElapsedMs, double ActualInputFps, double InputIntervalP95Ms,
    bool AnnexB, string InputMemory, SoftwareDecodeResult Validation, string Status, int ForcedKeyframes, EncoderRateControl RateControl);

internal static class H264TextureProbe
{
    private static readonly Guid TextureIid = new("6F15AAF2-D208-4E89-9AB4-489535D34F9C");

    internal static TextureEncodeResult Run(EncoderProbeOptions options, Action<byte[], long>? onPacket = null, Func<bool>? requestKeyframe = null)
    {
        options.Validate();
        using var factory = Vortice.DXGI.DXGI.CreateDXGIFactory1<IDXGIFactory1>();
        factory.EnumAdapters1(options.Adapter, out var adapter).CheckError();
        using (adapter)
        using (var attributes = MFCreateAttributes(1))
        {
            attributes.SetBlob(EncoderInventory.AdapterLuidAttribute, BitConverter.GetBytes(adapter.Description1.Luid)).CheckError();
            IntPtr list = IntPtr.Zero; uint count = 0;
            try
            {
                var output = new RegisterTypeInfo { GuidMajorType = MediaTypeGuids.Video, GuidSubtype = EncoderInventory.Subtype("H264") };
                MFTEnum2(TransformCategoryGuids.VideoEncoder, 0x04 | 0x40, null, output, attributes, out list, out count);
                if (count == 0) throw new NotSupportedException("No hardware H.264 transform enumerated for this adapter.");
                if (options.Candidate >= count) throw new ArgumentOutOfRangeException(nameof(options.Candidate));
                IntPtr pointer = Marshal.ReadIntPtr(list, (int)options.Candidate * IntPtr.Size);
                Marshal.WriteIntPtr(list, (int)options.Candidate * IntPtr.Size, IntPtr.Zero);
                using var activation = new IMFActivate(pointer);
                try
                {
                    string name = activation.GetString(TransformAttributeKeys.MftFriendlyNameAttribute);
                    using var encoder = activation.ActivateObject<IMFTransform>();
                    return Encode(encoder, adapter, name, options, onPacket, requestKeyframe);
                }
                finally { activation.ShutdownObject(); }
            }
            finally
            {
                if (list != IntPtr.Zero)
                {
                    for (int i = 0; i < count; i++)
                    {
                        IntPtr pointer = Marshal.ReadIntPtr(list, i * IntPtr.Size);
                        if (pointer != IntPtr.Zero) Marshal.Release(pointer);
                    }
                    Marshal.FreeCoTaskMem(list);
                }
            }
        }
    }

    private static TextureEncodeResult Encode(IMFTransform encoder, IDXGIAdapter1 adapter, string name, EncoderProbeOptions options, Action<byte[], long>? onPacket, Func<bool>? requestKeyframe)
    {
        int width = options.Width, height = options.Height, fps = options.Fps, frameCount = options.Frames;
        bool cpuControl = options.Input == ProbeInput.CpuControl, convertBgra = options.Input == ProbeInput.BgraTexture;
        using var attributes = encoder.Attributes;
        if (attributes.GetUInt32(TransformAttributeKeys.D3D11Aware, out uint aware).Failure || aware == 0)
            throw new NotSupportedException("Transform did not advertise D3D11 texture input.");
        attributes.Set(TransformAttributeKeys.TransformAsyncUnlock, 1u).CheckError();
        attributes.Set(SinkWriterAttributeKeys.LowLatency, 1u).CheckError();
        D3D11.D3D11CreateDevice(adapter, DriverType.Unknown, DeviceCreationFlags.BgraSupport | DeviceCreationFlags.VideoSupport,
            new[] { FeatureLevel.Level_11_0 }, out ID3D11Device device, out ID3D11DeviceContext context).CheckError();
        using (device)
        using (context)
        using (var multithread = context.QueryInterface<ID3D11Multithread>())
        using (var manager = MFCreateDXGIDeviceManager())
        using (var outputType = VideoType("H264", width, height, fps))
        using (var inputType = VideoType("NV12", width, height, fps))
        {
            multithread.SetMultithreadProtected(true);
            manager.ResetDevice(device).CheckError();
            encoder.ProcessMessage(TMessageType.MessageSetD3DManager, (UIntPtr)manager.NativePointer);
            outputType.Set(MediaTypeAttributeKeys.AvgBitrate, 6000000u).CheckError();
            outputType.Set(MediaTypeAttributeKeys.Mpeg2Profile, options.ConstrainedBaseline ? 256u : 66u).CheckError();
            outputType.Set(MediaTypeAttributeKeys.Mpeg2Level, H264Level.For(width, height, fps)).CheckError();
            inputType.Set(MediaTypeAttributeKeys.DefaultStride, (uint)width).CheckError();
            inputType.Set(MediaTypeAttributeKeys.SampleSize, (uint)(width * height * 3 / 2)).CheckError();
            inputType.Set(MediaTypeAttributeKeys.FixedSizeSamples, 1u).CheckError();
            inputType.Set(MediaTypeAttributeKeys.AllSamplesIndependent, 1u).CheckError();
            var controlRequests = HardwareEncoderControl.Apply(encoder, 6000000);
            encoder.SetOutputType(0, outputType, 0);
            encoder.SetInputType(0, inputType, 0);
            var rateControl = HardwareEncoderControl.Snapshot(encoder, 6000000, controlRequests);
            if ((encoder.GetOutputStreamInfo(0).Flags & 0x300) == 0)
                throw new NotSupportedException("This prototype requires an MFT that provides output samples.");
            using var events = encoder.QueryInterface<IMFMediaEventGenerator>();
            using var pollTimer = new EncoderPollTimer();
            using var converter = convertBgra ? new GpuBgraConverter(device, context, options) : null;
            using var wgc = options.WgcHwnd != 0 ? new WgcProbeSource(device, options) : null;
            using var light = !convertBgra ? Texture(device, width, height, 200) : null;
            using var dark = !convertBgra ? Texture(device, width, height, 40) : null;
            context.Flush();
            encoder.ProcessMessage(TMessageType.MessageNotifyBeginStreaming, UIntPtr.Zero);
            encoder.ProcessMessage(TMessageType.MessageNotifyStartOfStream, UIntPtr.Zero);
            var clock = Stopwatch.StartNew();
            var cadence = new Xennex.Services.CaptureFrameCadence(fps);
            var inputTimes = new List<double>();
            int submitted = 0, encoded = 0, totalBytes = 0, credits = 0, observedEvents = 0;
            double firstOutput = -1;
            bool draining = false, annexB = false;
            var packets = new List<byte[]>();
            int forcedKeyframes = 0;
            long? firstCaptureTimestamp = null;
            try
            {
                while (clock.ElapsedMilliseconds < 10000)
                {
                    using var item = TryEvent(events);
                    if (item != null)
                    {
                        if (observedEvents++ < 64) Console.Error.WriteLine($"MFT event: {item.EventType}");
                        item.Status.CheckError();
                        if (item.EventType == MediaEventTypes.TransformNeedInput) credits++;
                        if (item.EventType == MediaEventTypes.TransformHaveOutput)
                        {
                            IMFSample? produced = null;
                            try
                            {
                                Marshal.ThrowExceptionForHR(TransformOutput.Read(encoder, null, out produced));
                                if (produced == null) throw new InvalidOperationException("MFT signaled output without a sample.");
                                byte[] bytes = Bytes(produced);
                                if (bytes.Length == 0) throw new InvalidOperationException("MFT returned empty output.");
                                converter?.Complete(produced.SampleTime);
                                if ((long)totalBytes + bytes.Length > 67108864) throw new InvalidOperationException("Synthetic bitstream exceeded the total memory bound.");
                                packets.Add(bytes);
                                firstOutput = firstOutput < 0 ? clock.Elapsed.TotalMilliseconds : firstOutput;
                                annexB |= bytes.AsSpan().IndexOf(new byte[] { 0, 0, 1 }) >= 0;
                                totalBytes += bytes.Length; encoded++;
                                onPacket?.Invoke(bytes, produced.SampleTime);
                            }
                            finally { produced?.Dispose(); }
                        }
                        if (item.EventType == MediaEventTypes.TransformDrainComplete) break;
                    }
                    if (credits > 0 && submitted < frameCount && (converter?.HasFree ?? true) && cadence.ShouldCapture(clock.Elapsed.TotalMilliseconds))
                    {
                        using var capturedFrame = wgc?.TryAcquire();
                        if (wgc != null && capturedFrame == null) { pollTimer.Wait(); continue; }
                        double at = clock.Elapsed.TotalMilliseconds;
                        inputTimes.Add(at);
                        if (capturedFrame != null) firstCaptureTimestamp ??= capturedFrame.Timestamp;
                        long timestamp = capturedFrame == null ? (long)((at - inputTimes[0]) * 10000) : capturedFrame.Timestamp - firstCaptureTimestamp!.Value;
                        using var sample = MFCreateSample();
                        using var surface = cpuControl ? CpuBuffer(width, height, submitted % 2 == 0 ? (byte)200 : (byte)40)
                            : MFCreateDXGISurfaceBuffer(TextureIid, converter?.ConvertFrame(submitted, timestamp, capturedFrame?.Texture) ?? (submitted % 2 == 0 ? light! : dark!), 0, false);
                        surface.CurrentLength = width * height * 3 / 2;
                        sample.AddBuffer(surface);
                        sample.SampleTime = timestamp;
                        sample.SampleDuration = 10000000L / fps;
                        if (requestKeyframe?.Invoke() == true) { HardwareEncoderControl.Force(encoder); forcedKeyframes++; }
                        encoder.ProcessInput(0, sample, 0); context.Flush(); submitted++; credits--;
                    }
                    if (submitted == frameCount && !draining)
                    {
                        draining = true;
                        encoder.ProcessMessage(TMessageType.MessageNotifyEndOfStream, UIntPtr.Zero);
                        encoder.ProcessMessage(TMessageType.MessageCommandDrain, UIntPtr.Zero);
                    }
                    pollTimer.Wait();
                }
                if (submitted != frameCount || encoded != frameCount) throw new InvalidOperationException($"Incomplete synthetic encode: {submitted}/{frameCount} input, {encoded}/{frameCount} output.");
                double elapsed = clock.Elapsed.TotalMilliseconds;
                using var encodedType = encoder.GetOutputCurrentType(0);
                var validation = SoftwareH264Decoder.Decode(packets, encodedType, options);
                var intervals = inputTimes.Zip(inputTimes.Skip(1), (before, after) => after - before).OrderBy(value => value).ToArray();
                double actualFps = (inputTimes.Count - 1) * 1000 / (inputTimes[^1] - inputTimes[0]);
                return new(name, options.Adapter, width, height, fps, submitted, encoded, totalBytes, firstOutput, elapsed, actualFps, intervals[(int)Math.Ceiling(intervals.Length * .95) - 1], annexB,
                    cpuControl ? "cpu-control" : wgc != null ? "wgc-fixture-gpu-to-nv12" : convertBgra ? "bgra-gpu-to-nv12" : "d3d11-texture", validation,
                    wgc != null ? "encoded-and-decoded-owned-fixture" : "encoded-and-decoded-synthetic", forcedKeyframes, rateControl);
            }
            finally
            {
                encoder.ProcessMessage(TMessageType.MessageCommandFlush, UIntPtr.Zero);
                encoder.ProcessMessage(TMessageType.MessageNotifyEndStreaming, UIntPtr.Zero);
                encoder.ProcessMessage(TMessageType.MessageSetD3DManager, UIntPtr.Zero);
            }
        }
    }

    private static IMFMediaEvent? TryEvent(IMFMediaEventGenerator source)
    {
        try { return source.GetEvent(1); }
        catch (Exception error) when (error.HResult == unchecked((int)0xC00D3E80)) { return null; }
    }

    internal static IMFMediaType VideoType(string fourcc, int width, int height, int fps)
    {
        var type = MFCreateMediaType();
        try
        {
            type.Set(MediaTypeAttributeKeys.MajorType, MediaTypeGuids.Video).CheckError();
            type.Set(MediaTypeAttributeKeys.Subtype, EncoderInventory.Subtype(fourcc)).CheckError();
            type.Set(MediaTypeAttributeKeys.FrameSize, ((ulong)width << 32) | (uint)height).CheckError();
            type.Set(MediaTypeAttributeKeys.FrameRate, ((ulong)fps << 32) | 1u).CheckError();
            type.Set(MediaTypeAttributeKeys.PixelAspectRatio, (1UL << 32) | 1u).CheckError();
            type.Set(MediaTypeAttributeKeys.InterlaceMode, 2u).CheckError();
            type.SetEnumValue(MediaTypeAttributeKeys.VideoPrimaries, VideoPrimaries.Bt709).CheckError();
            type.SetEnumValue(MediaTypeAttributeKeys.TransferFunction, VideoTransferFunction.Func709).CheckError();
            type.SetEnumValue(MediaTypeAttributeKeys.YuvMatrix, VideoTransferMatrix.Bt709).CheckError();
            type.SetEnumValue(MediaTypeAttributeKeys.VideoNominalRange, NominalRange.Range16_235).CheckError();
            return type;
        }
        catch { type.Dispose(); throw; }
    }

    private static unsafe ID3D11Texture2D Texture(ID3D11Device device, int width, int height, byte luma)
    {
        byte[] data = new byte[width * height * 3 / 2];
        data.AsSpan(0, width * height).Fill(luma);
        data.AsSpan(width * height).Fill(128);
        var description = new Texture2DDescription { Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.NV12, SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Default,
            BindFlags = BindFlags.RenderTarget | BindFlags.ShaderResource };
        fixed (byte* pointer = data)
            return device.CreateTexture2D(description, new SubresourceData((IntPtr)pointer, (uint)width, (uint)data.Length));
    }

    internal static byte[] Bytes(IMFSample sample)
    {
        using var buffer = sample.ConvertToContiguousBuffer();
        buffer.Lock(out IntPtr pointer, out _, out int length);
        try
        {
            if (length is < 0 or > 16777216) throw new InvalidOperationException("Encoded sample exceeded the probe bound.");
            byte[] result = new byte[length]; Marshal.Copy(pointer, result, 0, length); return result;
        }
        finally { buffer.Unlock(); }
    }

    private static IMFMediaBuffer CpuBuffer(int width, int height, byte luma)
    {
        byte[] bytes = new byte[width * height * 3 / 2];
        bytes.AsSpan(0, width * height).Fill(luma); bytes.AsSpan(width * height).Fill(128);
        var buffer = MFCreateMemoryBuffer(bytes.Length);
        try
        {
            buffer.Lock(out IntPtr pointer, out _, out _);
            try { Marshal.Copy(bytes, 0, pointer, bytes.Length); }
            finally { buffer.Unlock(); }
            buffer.CurrentLength = bytes.Length;
            return buffer;
        }
        catch { buffer.Dispose(); throw; }
    }
}

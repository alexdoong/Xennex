using System.Runtime.InteropServices;
using Vortice.MediaFoundation;
using static Vortice.MediaFoundation.MediaFactory;

internal sealed record SoftwareDecodeResult(string Decoder, int Frames, double[] Luma, bool AlternatingPattern, bool ColorChannelsVerified);

internal static class SoftwareH264Decoder
{
    private const int NeedInput = unchecked((int)0xC00D6D72);
    private const int StreamChange = unchecked((int)0xC00D6D61);

    internal static SoftwareDecodeResult Decode(IReadOnlyList<byte[]> packets, IMFMediaType encodedType, EncoderProbeOptions options)
    {
        int width = options.Width, height = options.Height, fps = options.Fps;
        IntPtr list = IntPtr.Zero; uint count = 0;
        try
        {
            var input = new RegisterTypeInfo { GuidMajorType = MediaTypeGuids.Video, GuidSubtype = EncoderInventory.Subtype("H264") };
            MFTEnumEx(TransformCategoryGuids.VideoDecoder, 0x01 | 0x40, input, null, out list, out count);
            if (count == 0) throw new NotSupportedException("Independent synchronous software H.264 decoder unavailable.");
            IntPtr pointer = Marshal.ReadIntPtr(list); Marshal.WriteIntPtr(list, IntPtr.Zero);
            using var activation = new IMFActivate(pointer);
            try
            {
                string name = activation.GetString(TransformAttributeKeys.MftFriendlyNameAttribute);
                using var decoder = activation.ActivateObject<IMFTransform>();
                decoder.SetInputType(0, encodedType, 0);
                SetOutput(decoder);
                decoder.ProcessMessage(TMessageType.MessageNotifyBeginStreaming, UIntPtr.Zero);
                decoder.ProcessMessage(TMessageType.MessageNotifyStartOfStream, UIntPtr.Zero);
                var means = new List<double>();
                try
                {
                    for (int index = 0; index < packets.Count; index++)
                    {
                        using var sample = MFCreateSample();
                        using var buffer = MFCreateMemoryBuffer(packets[index].Length);
                        buffer.Lock(out IntPtr bytes, out _, out _);
                        try { Marshal.Copy(packets[index], 0, bytes, packets[index].Length); }
                        finally { buffer.Unlock(); }
                        buffer.CurrentLength = packets[index].Length;
                        sample.AddBuffer(buffer); sample.SampleTime = index * 10000000L / fps; sample.SampleDuration = 10000000L / fps;
                        decoder.ProcessInput(0, sample, 0);
                        DrainAvailable(decoder, options, means, packets.Count);
                    }
                    decoder.ProcessMessage(TMessageType.MessageNotifyEndOfStream, UIntPtr.Zero);
                    decoder.ProcessMessage(TMessageType.MessageCommandDrain, UIntPtr.Zero);
                    DrainAvailable(decoder, options, means, packets.Count);
                    bool pattern = means.Count == packets.Count && (options.ColorPattern || means.Select((value, index) => Math.Abs(value - (index % 2 == 0 ? 200 : 40)) <= 12).All(value => value));
                    if (!pattern) throw new InvalidOperationException($"Decoded synthetic pattern mismatch; frames {means.Count}/{packets.Count}.");
                    return new(name, means.Count, means.ToArray(), options.WgcHwnd == 0, options.ColorPattern);
                }
                finally
                {
                    decoder.ProcessMessage(TMessageType.MessageCommandFlush, UIntPtr.Zero);
                    decoder.ProcessMessage(TMessageType.MessageNotifyEndStreaming, UIntPtr.Zero);
                }
            }
            finally { activation.ShutdownObject(); }
        }
        finally
        {
            if (list != IntPtr.Zero)
            {
                for (int i = 0; i < count; i++) { IntPtr pointer = Marshal.ReadIntPtr(list, i * IntPtr.Size); if (pointer != IntPtr.Zero) Marshal.Release(pointer); }
                Marshal.FreeCoTaskMem(list);
            }
        }
    }

    private static void SetOutput(IMFTransform decoder)
    {
        for (int index = 0; index < 32; index++)
        {
            using var type = decoder.GetOutputAvailableType(0, index);
            if (type.GetGUID(MediaTypeAttributeKeys.Subtype) != EncoderInventory.Subtype("NV12")) continue;
            decoder.SetOutputType(0, type, 0); return;
        }
        throw new NotSupportedException("Decoder did not offer NV12.");
    }

    private static void DrainAvailable(IMFTransform decoder, EncoderProbeOptions options, List<double> means, int expectedFrames)
    {
        int width = options.Width, height = options.Height;
        for (int attempt = 0; attempt < expectedFrames + 8; attempt++)
        {
            var info = decoder.GetOutputStreamInfo(0);
            using var supplied = (info.Flags & 0x300) == 0 ? MFCreateSample() : null;
            if (supplied != null)
            {
                int size = Math.Max(info.Size, checked(width * height * 4));
                if (size > 33554432) throw new InvalidOperationException("Decoder output exceeded the probe bound.");
                using var memory = MFCreateMemoryBuffer(size); supplied.AddBuffer(memory);
            }
            int result = TransformOutput.Read(decoder, supplied, out var produced);
            using (produced)
            {
                if (result == NeedInput) return;
                if (result == StreamChange) { SetOutput(decoder); continue; }
                Marshal.ThrowExceptionForHR(result);
                var sample = supplied ?? produced ?? throw new InvalidOperationException("Decoder returned no output sample.");
                byte[] bytes = H264TextureProbe.Bytes(sample);
                if (bytes.Length < width * height) throw new InvalidOperationException("Decoded image is smaller than expected.");
                if (options.ColorPattern) VerifyColors(decoder, bytes, options, options.WgcHwnd == 0 && means.Count % 2 != 0);
                means.Add(bytes.Take(64).Average(value => (double)value));
                if (means.Count > expectedFrames) throw new InvalidOperationException("Decoder produced too many frames.");
            }
        }
        throw new InvalidOperationException($"Decoder output did not reach a bounded wait for input; decoded {means.Count}/{expectedFrames}.");
    }

    private static void VerifyColors(IMFTransform decoder, byte[] bytes, EncoderProbeOptions options, bool alternate)
    {
        using var format = decoder.GetOutputCurrentType(0);
        int stride = format.GetUInt32(MediaTypeAttributeKeys.DefaultStride, out uint pitch).Success ? checked((int)pitch) : options.Width;
        if (stride < options.Width || (long)stride * options.Height * 3 / 2 > bytes.Length) throw new InvalidOperationException("Invalid decoded NV12 layout.");
        int[][] expected = { new[] { 63, 102, 240 }, new[] { 173, 42, 26 }, new[] { 32, 240, 118 }, new[] { 235, 128, 128 } };
        for (int quadrant = 0; quadrant < 4; quadrant++)
        {
            int x = options.Width * (quadrant % 2 == 0 ? 1 : 3) / 4;
            int y = options.Height * (quadrant < 2 ? 1 : 3) / 4;
            int chroma = stride * options.Height + y / 2 * stride + (x & ~1);
            var target = expected[alternate ? 3 - quadrant : quadrant];
            if (Math.Abs(bytes[y * stride + x] - target[0]) > 12 || Math.Abs(bytes[chroma] - target[1]) > 12 || Math.Abs(bytes[chroma + 1] - target[2]) > 12)
                throw new InvalidOperationException("GPU conversion/encoded color channels do not match the BT.709 test pattern.");
        }
    }
}

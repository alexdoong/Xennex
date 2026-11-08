using System.Runtime.InteropServices;
using Vortice.MediaFoundation;

internal sealed record EncoderControlRequests(int LowLatencyHresult, int BufferHresult, uint RequestedBufferBytes);
internal sealed record EncoderRateControl(uint RequestedBps, uint ReportedBps, uint Mode, string InputFrameRate, string OutputFrameRate, EncoderControlRequests? AdditionalRequests, string Api = "ICodecAPI", string? RuntimeVersion = null);

internal static class HardwareEncoderControl
{
    private static readonly Guid CodecApi = new("901db4c7-31ce-41a2-85dc-8fa0bf41b8da");
    private static readonly Guid ForceKeyframe = new("398c1b98-8353-475a-9ef2-8f265d260345");
    private static readonly Guid RateMode = new("1c0608e9-370c-4710-8a58-cb6181c42423");
    private static readonly Guid MeanBitrate = new("f7222374-2144-4815-b550-a37f8e12ee52");
    private static readonly Guid LowLatency = new("9C27891A-ED7A-40E1-88E8-B22727A024EE");
    private static readonly Guid BufferSize = new("0db96574-b6a4-4c8b-8106-3773de0310cd");

    internal static EncoderControlRequests Apply(IMFTransform encoder, uint bitrate)
    {
        Write(encoder, RateMode, 0); // eAVEncCommonRateControlMode_CBR.
        Write(encoder, MeanBitrate, bitrate);
        uint buffer = bitrate / 8 / 4; // Quarter-second CBR buffer, Windows API uses bytes.
        return new(WriteRaw(encoder, LowLatency, ushort.MaxValue, 11), WriteRaw(encoder, BufferSize, buffer), buffer);
    }
    internal static EncoderRateControl Snapshot(IMFTransform encoder, uint bitrate, EncoderControlRequests requests)
    {
        using var input = encoder.GetInputCurrentType(0);
        using var output = encoder.GetOutputCurrentType(0);
        var result = new EncoderRateControl(bitrate, Read(encoder, MeanBitrate), Read(encoder, RateMode), FrameRate(input), FrameRate(output), requests);
        if (result.ReportedBps != bitrate || result.Mode != 0) throw new NotSupportedException("Hardware MFT did not retain requested CBR settings.");
        return result;
    }
    internal static void Force(IMFTransform encoder) => Write(encoder, ForceKeyframe, 1);
    private static string FrameRate(IMFMediaType type)
    {
        type.GetUInt64(MediaTypeAttributeKeys.FrameRate, out ulong rate).CheckError();
        return $"{rate >> 32}/{(uint)rate}";
    }

    private static IntPtr Query(IMFTransform encoder)
    {
        Guid id = CodecApi;
        Marshal.ThrowExceptionForHR(Marshal.QueryInterface(encoder.NativePointer, ref id, out IntPtr pointer));
        return pointer;
    }
    private static void Write(IMFTransform encoder, Guid property, uint value) => Marshal.ThrowExceptionForHR(WriteRaw(encoder, property, value));
    private static unsafe int WriteRaw(IMFTransform encoder, Guid property, uint value, ushort variantType = 19)
    {
        IntPtr pointer = Query(encoder);
        try
        {
            byte* variant = stackalloc byte[24];
            new Span<byte>(variant, 24).Clear();
            *(ushort*)variant = variantType;
            *(uint*)(variant + 8) = value;
            // Windows SDK ICodecAPI::SetValue is slot9 after IUnknown and six getters.
            var setValue = (delegate* unmanaged[Stdcall]<IntPtr, Guid*, byte*, int>)(*(IntPtr**)pointer)[9];
            return setValue(pointer, &property, variant);
        }
        finally { Marshal.Release(pointer); }
    }
    private static unsafe uint Read(IMFTransform encoder, Guid property)
    {
        IntPtr pointer = Query(encoder);
        byte* variant = stackalloc byte[24];
        new Span<byte>(variant, 24).Clear();
        try
        {
            var getValue = (delegate* unmanaged[Stdcall]<IntPtr, Guid*, byte*, int>)(*(IntPtr**)pointer)[8];
            Marshal.ThrowExceptionForHR(getValue(pointer, &property, variant));
            if (*(ushort*)variant != 19) throw new NotSupportedException("Hardware MFT returned a non-UINT32 control value.");
            return *(uint*)(variant + 8);
        }
        finally { VariantClear((IntPtr)variant); Marshal.Release(pointer); }
    }
    [DllImport("oleaut32.dll")] private static extern int VariantClear(IntPtr variant);
}

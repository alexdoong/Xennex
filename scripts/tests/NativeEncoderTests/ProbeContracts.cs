internal static class ProbeContracts
{
    internal static void Run()
    {
        var baseline = new EncoderProbeOptions(0, 1, 640, 360, 30, 8, ProbeInput.BgraTexture, true);
        baseline.Validate();
        (baseline with { Backend = ProbeBackend.Amf }).Validate();
        (baseline with { Width = 3840, Height = 2160, Fps = 120, Frames = 120 }).Validate();
        var invalid = new[] {
            baseline with { Width = int.MinValue }, baseline with { Width = 1919 }, baseline with { Height = 1081 },
            baseline with { Width = 4096, Height = 2160 }, baseline with { Width = int.MaxValue },
            baseline with { Adapter = 16 }, baseline with { Candidate = 32 }, baseline with { Fps = 0 },
            baseline with { Fps = 121 }, baseline with { Frames = 0 }, baseline with { Frames = 241 },
            baseline with { Fps = 1, Frames = 240 }, baseline with { Input = ProbeInput.CpuControl },
            baseline with { Input = (ProbeInput)999 },
            baseline with { Backend = (ProbeBackend)999 },
            baseline with { Backend = ProbeBackend.Amf, Input = ProbeInput.Nv12Texture, ColorPattern = false },
            baseline with { WgcHwnd = 1 }, baseline with { WgcPid = 1 },
            baseline with { WgcHwnd = 1, WgcPid = 1 }, baseline with { WgcHwnd = -1, WgcPid = 1 },
        };
        foreach (var profile in invalid)
        {
            bool rejected = false;
            try { profile.Validate(); } catch (ArgumentException) { rejected = true; }
            if (!rejected) throw new InvalidOperationException("Unsafe encoder profile was admitted before device/resource creation.");
        }
        if (EncoderInventory.Subtype("H264") != new Guid("34363248-0000-0010-8000-00aa00389b71"))
            throw new InvalidOperationException("Incorrect Media Foundation subtype GUID layout.");
        if (TransformOutput.NativeBufferSize != (IntPtr.Size == 8 ? 32 : 16))
            throw new InvalidOperationException("Incorrect MFT_OUTPUT_DATA_BUFFER ABI layout.");
        if (IntPtr.Size == 8 && (System.Runtime.InteropServices.Marshal.SizeOf<NativeRtcApi.Configuration>() != 56 ||
            System.Runtime.InteropServices.Marshal.SizeOf<NativeRtcApi.Packetizer>() != 64))
            throw new InvalidOperationException("Incorrect pinned native WebRTC x64 C ABI layout.");
        byte[] first = { 0, 0, 0, 1, 0x67, 0x42, 0xc0, 0x1f, 0, 0, 1, 0x68, 1, 0, 0, 0, 1, 0x65, 2 };
        if (H264AnnexB.Profile(H264AnnexB.Units(first)) != "42c01f") throw new InvalidOperationException("Actual H.264 SPS profile parsing failed.");
        if (H264Level.For(1280, 720, 30) != 31 || H264Level.For(1280, 720, 60) != 32 ||
            H264Level.For(1920, 1080, 60) != 42 || H264Level.For(1920, 1080, 120) != 51 ||
            H264Level.For(3840, 2160, 120) != 60) throw new InvalidOperationException("H.264 frame-size/rate level bound mismatch.");
        foreach (byte[] malformed in new[] { Array.Empty<byte>(), new byte[] { 1, 2, 3 }, new byte[] { 0, 0, 1, 0x65, 1 } })
        {
            bool rejected = false;
            try { H264AnnexB.Profile(H264AnnexB.Units(malformed)); } catch (Exception error) when (error is ArgumentException or NotSupportedException) { rejected = true; }
            if (!rejected) throw new InvalidOperationException("Invalid bitstream admitted to the transport probe.");
        }
        Console.WriteLine("PASS: native encoder profile/resource/duration bounds, explicit color input, MF subtype and COM output ABI; no GPU/capture used.");
    }
}

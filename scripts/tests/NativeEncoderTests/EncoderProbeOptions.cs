internal enum ProbeInput { Nv12Texture, BgraTexture, CpuControl }
internal enum ProbeBackend { MediaFoundation, Amf }
internal sealed record EncoderProbeOptions(uint Adapter, uint Candidate, int Width, int Height, int Fps, int Frames, ProbeInput Input, bool ColorPattern, bool ConstrainedBaseline = false, long WgcHwnd = 0, int WgcPid = 0, ProbeBackend Backend = ProbeBackend.MediaFoundation)
{
    internal void Validate()
    {
        if (Adapter > 15 || Candidate > 31 || Width is < 16 or > 4096 || Height is < 16 or > 2160 ||
            Width % 2 != 0 || Height % 2 != 0 || (long)Width * Height > 3840L * 2160 ||
            Fps is < 1 or > 120 || Frames is < 8 or > 240 || Frames > Fps * 8 ||
            !Enum.IsDefined(Input) || !Enum.IsDefined(Backend) || Backend == ProbeBackend.Amf && Input != ProbeInput.BgraTexture || ColorPattern && Input != ProbeInput.BgraTexture ||
            WgcHwnd < 0 || WgcPid < 0 || (WgcHwnd == 0) != (WgcPid == 0) ||
            WgcHwnd != 0 && (!ColorPattern || Input != ProbeInput.BgraTexture || Width != 1280 || Height != 720))
            throw new ArgumentException("Probe profile exceeds dimension, duration, sample or input-format bounds.");
    }
}

internal static class NativeEncoderProbe
{
    internal static TextureEncodeResult Run(EncoderProbeOptions options, Action<byte[], long>? onPacket = null, Func<bool>? keyframe = null) =>
        options.Backend == ProbeBackend.Amf ? AmfTextureProbe.Run(options, onPacket, keyframe) : H264TextureProbe.Run(options, onPacket, keyframe);
}

internal static class H264Level
{
    // Conservative Annex A frame-size/macroblock-rate bounds, bitrate fixed at6Mbps.
    internal static uint For(int width, int height, int fps)
    {
        if (width <= 0 || height <= 0 || fps <= 0) throw new ArgumentOutOfRangeException(nameof(width));
        long frame = ((long)width + 15) / 16 * (((long)height + 15) / 16);
        long rate = checked(frame * fps);
        (uint Level, int Frame, int Rate)[] bounds = {
            (31, 3600, 108000), (32, 5120, 216000), (40, 8192, 245760),
            (42, 8704, 522240), (51, 36864, 983040), (52, 36864, 2073600), (60, 139264, 4177920),
        };
        foreach (var item in bounds) if (frame <= item.Frame && rate <= item.Rate) return item.Level;
        throw new NotSupportedException("Synthetic dimensions/frame rate exceed the bounded H.264 levels.");
    }
}

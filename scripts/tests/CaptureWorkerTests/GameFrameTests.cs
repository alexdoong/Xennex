using System.Drawing;
using Xennex.CaptureWorker;

internal static class GameFrameTests
{
    internal static void Run()
    {
        if (NativeGameSession.ValidateFrame(3840, 2160, 15360, 1) != 33177600) throw new Exception("4K frame bound");
        foreach (var value in new[] { (0, 2, 0, 1), (int.MaxValue, 2, 8, 1), (8192, 8192, 32768, 1), (32, 32, 128, 0), (32, 32, 124, 1) })
        {
            try { NativeGameSession.ValidateFrame(value.Item1, value.Item2, value.Item3, value.Item4); throw new Exception("Malformed game frame accepted"); }
            catch (InvalidDataException) { }
        }
        byte[] pixels = new byte[32 * 32 * 4];
        for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) pixels[(y * 32 + x) * 4 + (y < 16 ? 2 : 0)] = 255;
        using var encoder = new GameFrameEncoder(95);
        foreach (int limit in new[] { 32, 16, 64 })
        {
            byte[] jpeg = encoder.Encode(new GameFrame(32, 32, pixels, 1, 1), limit, limit);
            using var stream = new MemoryStream(jpeg); using var image = new Bitmap(stream);
            int expected = Math.Min(32, limit);
            Color top = image.GetPixel(expected / 2, expected / 4), bottom = image.GetPixel(expected / 2, expected * 3 / 4);
            if (image.Width != expected || image.Height != expected || top.B < 200 || top.R > 50 || bottom.R < 200 || bottom.B > 50)
                throw new Exception("JPEG orientation, BGRA or sizing incorrect");
        }
    }
}

using System;
using System.Buffers.Binary;
using System.IO;

namespace Xennex.Services.Assets.Metadata;

internal static class ImageDimensionsReader
{
    public static (int width, int height) Read(string path)
    {
        try
        {
            using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            var header = new byte[Math.Min(stream.Length, 256 * 1024)];
            var length = stream.Read(header);
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext switch
            {
                ".png" when length >= 24 && header[0] == 137 && header[1] == 80 =>
                    Valid(BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(16)), BinaryPrimitives.ReadInt32BigEndian(header.AsSpan(20))),
                ".gif" when length >= 10 && header[0] == 71 && header[1] == 73 =>
                    Valid(BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(6)), BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(8))),
                ".bmp" when length >= 26 && header[0] == 66 && header[1] == 77 =>
                    Valid(BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(18)), Math.Abs(BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(22)))),
                ".jpg" or ".jpeg" => Jpeg(header),
                ".webp" => WebP(header),
                _ => (0, 0)
            };
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or OverflowException) { return (0, 0); }
    }

    private static (int width, int height) Valid(int width, int height) =>
        width is > 0 and <= 100000 && height is > 0 and <= 100000 ? (width, height) : (0, 0);

    private static (int width, int height) Jpeg(byte[] bytes)
    {
        if (bytes.Length < 4 || bytes[0] != 0xff || bytes[1] != 0xd8) return (0, 0);
        var offset = 2;
        while (offset + 9 < bytes.Length)
        {
            if (bytes[offset] != 0xff) break;
            var marker = bytes[offset + 1];
            if (marker is 0xd9 or 0xda) break;
            if (marker is 0x01 or >= 0xd0 and <= 0xd7) { offset += 2; continue; }
            var size = BinaryPrimitives.ReadUInt16BigEndian(bytes.AsSpan(offset + 2));
            if (size < 2 || offset + 2 + size > bytes.Length) break;
            if (marker is >= 0xc0 and <= 0xc3 or >= 0xc5 and <= 0xc7 or >= 0xc9 and <= 0xcb or >= 0xcd and <= 0xcf)
                return Valid(BinaryPrimitives.ReadUInt16BigEndian(bytes.AsSpan(offset + 7)),
                    BinaryPrimitives.ReadUInt16BigEndian(bytes.AsSpan(offset + 5)));
            offset += 2 + size;
        }
        return (0, 0);
    }

    private static (int width, int height) WebP(byte[] bytes)
    {
        if (bytes.Length < 30 || bytes[0] != 82 || bytes[1] != 73 || bytes[2] != 70 || bytes[3] != 70 ||
            bytes[8] != 87 || bytes[9] != 69 || bytes[10] != 66 || bytes[11] != 80) return (0, 0);
        var kind = System.Text.Encoding.ASCII.GetString(bytes, 12, 4);
        if (kind == "VP8X") return Valid(1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16),
            1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16));
        if (kind == "VP8L" && bytes[20] == 0x2f)
            return Valid(1 + bytes[21] + ((bytes[22] & 0x3f) << 8),
                1 + (bytes[22] >> 6) + (bytes[23] << 2) + ((bytes[24] & 0x0f) << 10));
        if (kind == "VP8 " && bytes[23] == 0x9d && bytes[24] == 0x01 && bytes[25] == 0x2a)
            return Valid(BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(26)) & 0x3fff,
                BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(28)) & 0x3fff);
        return (0, 0);
    }
}

using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;

namespace Xennex.Services.Assets.Metadata;

internal static class PngMetadataReader
{
    private static readonly byte[] Signature = { 137, 80, 78, 71, 13, 10, 26, 10 };
    private const int MaxChunk = 1024 * 1024;
    private const int MaxTotal = 2 * 1024 * 1024;

    public static string Read(string path)
    {
        if (!string.Equals(Path.GetExtension(path), ".png", StringComparison.OrdinalIgnoreCase)) return "";
        try
        {
            using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            Span<byte> header = stackalloc byte[8];
            if (stream.Read(header) != 8 || !header.SequenceEqual(Signature)) return "";
            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var budget = 0;
            while (stream.Position + 12 <= stream.Length)
            {
                if (stream.Read(header) != 8) break;
                var size = BinaryPrimitives.ReadUInt32BigEndian(header[..4]);
                var kind = Encoding.ASCII.GetString(header[4..]);
                if (size > stream.Length - stream.Position - 4 || size > int.MaxValue) break;
                if (kind is "tEXt" or "iTXt" or "zTXt")
                {
                    if (size > MaxChunk || budget + size > MaxTotal) break;
                    var bytes = new byte[size];
                    stream.ReadExactly(bytes);
                    budget += (int)size;
                    if (values.Count < 40) Parse(kind, bytes, values);
                }
                else stream.Seek(size, SeekOrigin.Current);
                stream.Seek(4, SeekOrigin.Current);
                if (kind == "IEND") break;
            }
            return values.Count == 0 ? "" : JsonSerializer.Serialize(new { source = "PNG text chunks", fields = values });
        }
        catch (Exception error) when (error is IOException or ArgumentException or InvalidDataException or EndOfStreamException or JsonException)
        {
            return "";
        }
    }

    private static void Parse(string kind, byte[] bytes, Dictionary<string, string> values)
    {
        var separator = Array.IndexOf(bytes, (byte)0);
        if (separator < 1 || separator > 79) return;
        var key = Encoding.Latin1.GetString(bytes, 0, separator);
        var value = kind switch
        {
            "tEXt" => Encoding.UTF8.GetString(bytes, separator + 1, bytes.Length - separator - 1),
            "zTXt" when separator + 2 < bytes.Length && bytes[separator + 1] == 0 =>
                Inflate(bytes.AsSpan(separator + 2)),
            "iTXt" => ReadInternational(bytes, separator + 1),
            _ => ""
        };
        if (value.Length > 0 && value.Length <= MaxChunk) values[key] = value;
    }

    private static string ReadInternational(byte[] bytes, int start)
    {
        if (start + 4 >= bytes.Length) return "";
        var compressed = bytes[start];
        if (compressed > 1 || bytes[start + 1] != 0) return "";
        var languageEnd = Array.IndexOf(bytes, (byte)0, start + 2);
        if (languageEnd < 0) return "";
        var translatedEnd = Array.IndexOf(bytes, (byte)0, languageEnd + 1);
        if (translatedEnd < 0) return "";
        var content = bytes.AsSpan(translatedEnd + 1);
        return compressed == 1 ? Inflate(content) : Encoding.UTF8.GetString(content);
    }

    private static string Inflate(ReadOnlySpan<byte> bytes)
    {
        using var input = new MemoryStream(bytes.ToArray(), false);
        using var zlib = new ZLibStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        var buffer = new byte[8192];
        while (true)
        {
            var read = zlib.Read(buffer);
            if (read == 0) break;
            if (output.Length + read > MaxChunk) return "";
            output.Write(buffer, 0, read);
        }
        return Encoding.UTF8.GetString(output.ToArray());
    }
}

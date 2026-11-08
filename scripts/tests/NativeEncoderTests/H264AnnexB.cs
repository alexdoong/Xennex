internal static class H264AnnexB
{
    internal static IReadOnlyList<byte[]> Units(byte[] packet)
    {
        if (packet.Length is 0 or > 16777216) throw new ArgumentException("Invalid bounded Annex B packet.");
        var units = new List<byte[]>();
        int start = -1;
        for (int i = 0; i + 2 < packet.Length; i++)
        {
            if (packet[i] != 0 || packet[i + 1] != 0) continue;
            int length = packet[i + 2] == 1 ? 3 : i + 3 < packet.Length && packet[i + 2] == 0 && packet[i + 3] == 1 ? 4 : 0;
            if (length == 0) continue;
            if (start >= 0 && i > start) units.Add(packet[start..i]);
            if (units.Count > 512) throw new ArgumentException("Annex B unit count exceeded.");
            start = i + length;
            i += length - 1;
        }
        if (start >= 0 && start < packet.Length) units.Add(packet[start..]);
        if (units.Count == 0) throw new ArgumentException("No Annex B unit found.");
        return units;
    }

    internal static string Profile(IReadOnlyList<byte[]> units)
    {
        byte[]? sps = units.FirstOrDefault(unit => (unit[0] & 31) == 7);
        if (sps == null || sps.Length < 4 || !units.Any(unit => (unit[0] & 31) == 8) || !units.Any(unit => (unit[0] & 31) == 5))
            throw new NotSupportedException("First frame must contain SPS, PPS and IDR for browser interoperability.");
        return Convert.ToHexString(sps.AsSpan(1, 3)).ToLowerInvariant();
    }
}

using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Vortice.DXGI;
using Vortice.MediaFoundation;
using static Vortice.MediaFoundation.MediaFactory;

internal sealed record EncoderCandidate(uint Adapter, string AdapterName, string Codec, string Name,
    bool HardwareEnumerated, bool Activated, bool? D3D11Aware, bool? Asynchronous, uint? HardwareDeviceId, bool? BindingMatches, string ProfileStatus, string? Error);
internal sealed record AdapterProbe(uint Adapter, string Name, string Codec, string Status, IReadOnlyList<EncoderCandidate> Candidates);

internal static class EncoderInventory
{
    // Windows SDK mfapi.h: the raw 8-byte adapter LUID, not a vendor/model inference.
    internal static readonly Guid AdapterLuidAttribute = new("1D39518C-E220-4DA8-A07F-BA172552D6B1");
    private const uint HardwareSorted = 0x04 | 0x40;

    internal static IReadOnlyList<AdapterProbe> Read()
    {
        var results = new List<AdapterProbe>();
        using var factory = Vortice.DXGI.DXGI.CreateDXGIFactory1<IDXGIFactory1>();
        for (uint index = 0; index < 16 && factory.EnumAdapters1(index, out var adapter).Success; index++)
        {
            using (adapter)
            {
                var description = adapter.Description1;
                if ((description.Flags & AdapterFlags.Software) != 0) continue;
                foreach (var codec in new[] { ("H.264", "H264"), ("HEVC", "HEVC"), ("AV1", "AV01") })
                    results.Add(ReadAdapter(index, description.Description, description.Luid, codec.Item1, codec.Item2));
            }
        }
        return results;
    }

    internal static Guid Subtype(string fourcc)
    {
        if (fourcc.Length != 4 || fourcc.Any(c => c > 127)) throw new ArgumentException("A media subtype needs four ASCII characters.");
        int value = fourcc[0] | fourcc[1] << 8 | fourcc[2] << 16 | fourcc[3] << 24;
        return new Guid(value, 0, 0x10, 0x80, 0, 0, 0xaa, 0, 0x38, 0x9b, 0x71);
    }

    private static AdapterProbe ReadAdapter(uint index, string name, long luid, string codec, string fourcc)
    {
        IntPtr list = IntPtr.Zero;
        uint count = 0;
        var candidates = new List<EncoderCandidate>();
        try
        {
            using var attributes = MFCreateAttributes(1);
            attributes.SetBlob(AdapterLuidAttribute, BitConverter.GetBytes(luid)).CheckError();
            var output = new RegisterTypeInfo { GuidMajorType = MediaTypeGuids.Video, GuidSubtype = Subtype(fourcc) };
            MFTEnum2(TransformCategoryGuids.VideoEncoder, HardwareSorted, null, output, attributes, out list, out count);
            for (int i = 0; i < Math.Min(count, 32); i++)
            {
                IntPtr pointer = Marshal.ReadIntPtr(list, i * IntPtr.Size);
                // Transfer this one reference to the wrapper; remaining references are released in finally.
                Marshal.WriteIntPtr(list, i * IntPtr.Size, IntPtr.Zero);
                using var activation = new IMFActivate(pointer);
                candidates.Add(ReadCandidate(index, name, luid, codec, activation));
            }
            return new(index, name, codec, candidates.Count == 0 ? "not-enumerated" : "enumerated", candidates);
        }
        catch (Exception error)
        {
            return new(index, name, codec, $"unknown:0x{error.HResult:X8}", candidates);
        }
        finally
        {
            if (list != IntPtr.Zero)
            {
                for (int i = 0; i < count; i++)
                {
                    IntPtr pointer = Marshal.ReadIntPtr(list, i * IntPtr.Size);
                    if (pointer != IntPtr.Zero) Marshal.Release(pointer);
                }
                Marshal.FreeCoTaskMem(list);
            }
        }
    }

    private static EncoderCandidate ReadCandidate(uint index, string adapter, long luid, string codec, IMFActivate activation)
    {
        string name = "Unnamed transform";
        bool activated = false;
        uint? deviceId = null;
        bool? binding = null;
        try
        {
            name = activation.GetString(TransformAttributeKeys.MftFriendlyNameAttribute);
            try
            {
                string hardware = activation.GetString(TransformAttributeKeys.MftEnumHardwareUrlAttribute);
                var match = Regex.Match(hardware, @"dev_([a-f0-9]{4})", RegexOptions.IgnoreCase);
                if (match.Success) deviceId = Convert.ToUInt32(match.Groups[1].Value, 16);
            }
            catch { /* Not every driver reports a PCI device path. Never export its raw path. */ }
            try { binding = activation.GetBlob(AdapterLuidAttribute).AsSpan().SequenceEqual(BitConverter.GetBytes(luid)); }
            catch { /* Absence is unknown, not an adapter match. */ }
            using var transform = activation.ActivateObject<IMFTransform>();
            activated = true;
            using var attributes = transform.Attributes;
            bool? d3d11 = Flag(attributes, TransformAttributeKeys.D3D11Aware);
            bool? asynchronous = Flag(attributes, TransformAttributeKeys.TransformAsync);
            return new(index, adapter, codec, name, true, true, d3d11, asynchronous, deviceId, binding, "not-tested", null);
        }
        catch (Exception error)
        {
            return new(index, adapter, codec, name, true, activated, null, null, deviceId, binding, "not-tested", $"0x{error.HResult:X8}");
        }
        finally { activation.ShutdownObject(); }
    }

    private static bool? Flag(IMFAttributes attributes, Guid key)
    {
        return attributes.GetUInt32(key, out uint value).Success ? value != 0 : null;
    }
}

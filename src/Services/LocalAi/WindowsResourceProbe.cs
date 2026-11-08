using System;
using System.Runtime.InteropServices;
using Xennex.Models.LocalAi;

namespace Xennex.Services.LocalAi;

public interface IResourceProbe { ResourceSnapshot Read(); }

/// <summary>Global physical RAM and dedicated memory for the largest DXGI hardware adapter.</summary>
public sealed class WindowsResourceProbe : IResourceProbe
{
    private AdapterDescription? adapter;
    private static double GiB(ulong bytes) => bytes / 1073741824.0;
    private readonly object sync = new();
    public ResourceSnapshot Read() { lock (sync) return ReadSnapshot(); }
    private ResourceSnapshot ReadSnapshot()
    {
        var result = new ResourceSnapshot();
        try
        {
            var memory = new MemoryStatus { Length = (uint)Marshal.SizeOf<MemoryStatus>() };
            if (GlobalMemoryStatusEx(ref memory))
            { result.RamTotalGb = GiB(memory.TotalPhysical); result.RamUsedGb = GiB(memory.TotalPhysical - memory.AvailablePhysical); }
            else result.Warning = "O Windows não retornou a leitura de RAM.";
            adapter ??= FindAdapter();
            if (!adapter.HasValue) { result.Warning += " GPU dedicada não identificada."; return result; }
            result.GpuName = adapter.Value.Description;
            result.VramTotalGb = GiB(adapter.Value.DedicatedVideoMemory.ToUInt64());
            result.VramUsedGb = ReadDedicatedUsage(adapter.Value);
            if (!result.VramUsedGb.HasValue) result.Warning += " Contador de VRAM indisponível; trabalhos GPU aguardam.";
        }
        catch (Exception error) { AppLog.Error("LocalAi.Telemetry", error); result.Warning = "Não foi possível obter toda a telemetria de memória."; }
        return result;
    }

    private static AdapterDescription? FindAdapter()
    {
        var iid = new Guid("770aae78-f26f-4dba-a829-253c83d1b387"); // IDXGIFactory1
        IntPtr factory = IntPtr.Zero;
        AdapterDescription? selected = null;
        try
        {
            Marshal.ThrowExceptionForHR(CreateDXGIFactory1(ref iid, out factory));
            var enumerate = Method<EnumAdapters>(factory, 12);
            for (uint i = 0; i < 32; i++)
            {
                int hr = enumerate(factory, i, out var item);
                if (hr == unchecked((int)0x887A0002)) break;
                Marshal.ThrowExceptionForHR(hr);
                try
                {
                    Marshal.ThrowExceptionForHR(Method<GetDescription>(item, 10)(item, out var description));
                    if ((description.Flags & 2) == 0 && description.DedicatedVideoMemory.ToUInt64() > (selected?.DedicatedVideoMemory.ToUInt64() ?? 0)) selected = description;
                }
                finally { Marshal.Release(item); }
            }
        }
        finally { if (factory != IntPtr.Zero) Marshal.Release(factory); }
        return selected;
    }

    private static double? ReadDedicatedUsage(AdapterDescription gpu)
    {
        IntPtr query = IntPtr.Zero, buffer = IntPtr.Zero;
        try
        {
            if (PdhOpenQueryW(null, IntPtr.Zero, out query) != 0) return null;
            // Adapter counter includes external applications; per-process counters would double-count shared allocations.
            if (PdhAddEnglishCounterW(query, @"\GPU Adapter Memory(*)\Dedicated Usage", IntPtr.Zero, out var counter) != 0 || PdhCollectQueryData(query) != 0) return null;
            uint bytes = 0, count = 0;
            uint status = PdhGetFormattedCounterArrayW(counter, 0x400, ref bytes, out count, IntPtr.Zero);
            if (status != 0x800007D2 || bytes == 0 || bytes > 1024 * 1024) return null;
            buffer = Marshal.AllocHGlobal((int)bytes);
            if (PdhGetFormattedCounterArrayW(counter, 0x400, ref bytes, out count, buffer) != 0) return null;
            string luid = $"luid_0x{gpu.LuidHigh:x8}_0x{gpu.LuidLow:x8}_";
            long total = 0; bool matched = false;
            int size = Marshal.SizeOf<CounterItem>();
            if ((ulong)count * (uint)size > bytes) return null;
            for (int i = 0; i < count; i++)
            {
                var item = Marshal.PtrToStructure<CounterItem>(IntPtr.Add(buffer, i * size));
                string name = Marshal.PtrToStringUni(item.Name) ?? "";
                if (!name.StartsWith(luid, StringComparison.OrdinalIgnoreCase) || item.Status > 1 || item.Value < 0) continue;
                total += item.Value; matched = true;
            }
            return matched ? GiB((ulong)total) : null;
        }
        finally
        {
            if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
            if (query != IntPtr.Zero) PdhCloseQuery(query);
        }
    }

    private static T Method<T>(IntPtr instance, int slot) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(instance), slot * IntPtr.Size));
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int EnumAdapters(IntPtr self, uint index, out IntPtr adapter);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int GetDescription(IntPtr self, out AdapterDescription description);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct AdapterDescription
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Description;
        public uint VendorId, DeviceId, SubSysId, Revision;
        public UIntPtr DedicatedVideoMemory, DedicatedSystemMemory, SharedSystemMemory;
        public uint LuidLow, LuidHigh, Flags;
    }
    [StructLayout(LayoutKind.Sequential)] private struct MemoryStatus
    {
        public uint Length, Load;
        public ulong TotalPhysical, AvailablePhysical, TotalPageFile, AvailablePageFile, TotalVirtual, AvailableVirtual, AvailableExtendedVirtual;
    }
    [StructLayout(LayoutKind.Explicit, Size = 24)] private struct CounterItem
    {
        [FieldOffset(0)] public IntPtr Name;
        [FieldOffset(8)] public uint Status;
        [FieldOffset(16)] public long Value;
    }
    [DllImport("kernel32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GlobalMemoryStatusEx(ref MemoryStatus status);
    [DllImport("dxgi.dll")] private static extern int CreateDXGIFactory1(ref Guid iid, out IntPtr factory);
    [DllImport("pdh.dll", CharSet = CharSet.Unicode)] private static extern uint PdhOpenQueryW(string source, IntPtr data, out IntPtr query);
    [DllImport("pdh.dll", CharSet = CharSet.Unicode)] private static extern uint PdhAddEnglishCounterW(IntPtr query, string path, IntPtr data, out IntPtr counter);
    [DllImport("pdh.dll")] private static extern uint PdhCollectQueryData(IntPtr query);
    [DllImport("pdh.dll")] private static extern uint PdhCloseQuery(IntPtr query);
    [DllImport("pdh.dll", CharSet = CharSet.Unicode)] private static extern uint PdhGetFormattedCounterArrayW(IntPtr counter, uint format, ref uint bytes, out uint count, IntPtr buffer);
}

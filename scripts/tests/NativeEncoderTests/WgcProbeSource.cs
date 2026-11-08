using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Vortice.Direct3D11;
using Vortice.DXGI;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using WinRT;

// Captures only the owned fixture identified by executable, window class and PID.
internal sealed class WgcProbeSource : IDisposable
{
    private IDirect3DDevice? winrtDevice;
    private GraphicsCaptureItem? item;
    private Direct3D11CaptureFramePool? pool;
    private GraphicsCaptureSession? session;
    private readonly EncoderProbeOptions options;
    internal WgcProbeSource(ID3D11Device device, EncoderProbeOptions options)
    {
        this.options = options;
        ValidateFixture(options);
        try
        {
            using var dxgi = device.QueryInterface<IDXGIDevice>();
            Marshal.ThrowExceptionForHR(CreateDirect3D11DeviceFromDXGIDevice(dxgi.NativePointer, out IntPtr inspectable));
            try { winrtDevice = MarshalInspectable<IDirect3DDevice>.FromAbi(inspectable); }
            finally { Marshal.Release(inspectable); }
            item = CreateItem((IntPtr)options.WgcHwnd);
            if (item.Size.Width != options.Width || item.Size.Height != options.Height)
                throw new InvalidOperationException("Owned fixture capture dimensions differ from the exact test profile.");
            pool = Direct3D11CaptureFramePool.CreateFreeThreaded(winrtDevice, DirectXPixelFormat.B8G8R8A8UIntNormalized, 2, item.Size);
            session = pool.CreateCaptureSession(item);
            session.IsCursorCaptureEnabled = false;
            session.StartCapture();
        }
        catch { Dispose(); throw; }
    }

    internal unsafe CapturedFrame? TryAcquire()
    {
        Direct3D11CaptureFrame? latest = null;
        try
        {
            for (int count = 0; count < 4; count++)
            {
                var next = pool!.TryGetNextFrame();
                if (next == null) break;
                latest?.Dispose(); latest = next;
            }
            if (latest == null) return null;
            if (latest.ContentSize.Width != options.Width || latest.ContentSize.Height != options.Height)
                throw new InvalidOperationException("Owned WGC fixture resized; ending probe without changing source.");
            long timestamp = latest.SystemRelativeTime.Ticks;
            Guid accessId = new("A9B3D012-3DF2-4EE3-B8D1-8695F457D3C1"), textureId = new("6F15AAF2-D208-4E89-9AB4-489535D34F9C");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(((IWinRTObject)latest.Surface).NativeObject.ThisPtr, ref accessId, out IntPtr access));
            IntPtr texture = IntPtr.Zero;
            ID3D11Texture2D? resource = null;
            try
            {
                var getInterface = (delegate* unmanaged[Stdcall]<IntPtr, Guid*, IntPtr*, int>)(*(IntPtr**)access)[3];
                Marshal.ThrowExceptionForHR(getInterface(access, &textureId, &texture));
                if (texture == IntPtr.Zero) throw new InvalidOperationException("WGC returned a null GPU texture.");
                resource = new ID3D11Texture2D(texture); texture = IntPtr.Zero;
                var result = new CapturedFrame(latest, resource, timestamp);
                resource = null;
                latest = null;
                return result;
            }
            finally { resource?.Dispose(); if (texture != IntPtr.Zero) Marshal.Release(texture); Marshal.Release(access); }
        }
        finally { latest?.Dispose(); }
    }

    internal sealed record CapturedFrame(Direct3D11CaptureFrame Frame, ID3D11Texture2D Texture, long Timestamp) : IDisposable
    {
        public void Dispose() { Texture.Dispose(); Frame.Dispose(); }
    }
    public void Dispose()
    {
        session?.Dispose(); session = null;
        pool?.Dispose(); pool = null;
        if (item is IWinRTObject nativeItem) nativeItem.NativeObject.Dispose(); item = null;
        winrtDevice?.Dispose(); winrtDevice = null;
    }
    private static void ValidateFixture(EncoderProbeOptions options)
    {
        using var process = Process.GetProcessById(options.WgcPid);
        string expected = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "NativeEncoderFixtures", "Xennex.OpenGlFixture64.exe"));
        var name = new StringBuilder(256);
        GetWindowThreadProcessId((IntPtr)options.WgcHwnd, out uint owner);
        GetClassName((IntPtr)options.WgcHwnd, name, name.Capacity);
        if (owner != options.WgcPid || name.ToString() != "XennexOwnOpenGlFixture" ||
            !string.Equals(process.MainModule?.FileName, expected, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("WGC probe accepts only its own explicitly supplied fixture.");
    }
    private static unsafe GraphicsCaptureItem CreateItem(IntPtr hwnd)
    {
        const string name = "Windows.Graphics.Capture.GraphicsCaptureItem";
        Marshal.ThrowExceptionForHR(WindowsCreateString(name, name.Length, out IntPtr text));
        IntPtr factory = IntPtr.Zero, itemPointer = IntPtr.Zero;
        try
        {
            Guid factoryId = new("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"), itemId = new("79C3F95B-31F7-4EC2-A464-632EF5D30760");
            Marshal.ThrowExceptionForHR(RoGetActivationFactory(text, ref factoryId, out factory));
            var create = (delegate* unmanaged[Stdcall]<IntPtr, IntPtr, Guid*, IntPtr*, int>)(*(IntPtr**)factory)[3];
            Marshal.ThrowExceptionForHR(create(factory, hwnd, &itemId, &itemPointer));
            return MarshalInspectable<GraphicsCaptureItem>.FromAbi(itemPointer);
        }
        finally { if (itemPointer != IntPtr.Zero) Marshal.Release(itemPointer); if (factory != IntPtr.Zero) Marshal.Release(factory); WindowsDeleteString(text); }
    }
    [DllImport("d3d11.dll")] private static extern int CreateDirect3D11DeviceFromDXGIDevice(IntPtr dxgiDevice, out IntPtr device);
    [DllImport("api-ms-win-core-winrt-string-l1-1-0.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern int WindowsCreateString(string text, int length, out IntPtr value);
    [DllImport("api-ms-win-core-winrt-string-l1-1-0.dll")] private static extern int WindowsDeleteString(IntPtr value);
    [DllImport("api-ms-win-core-winrt-l1-1-0.dll")] private static extern int RoGetActivationFactory(IntPtr name, ref Guid iid, out IntPtr factory);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder name, int capacity);
}

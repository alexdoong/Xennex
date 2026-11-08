using System.Runtime.InteropServices;
using Vortice.MediaFoundation;

/** Own sample references explicitly: an output supplied by the caller must not acquire a second COM wrapper owner. */
internal static class TransformOutput
{
    internal static int NativeBufferSize => Marshal.SizeOf<NativeOutput>();
    [StructLayout(LayoutKind.Sequential)]
    private struct NativeOutput { public uint Stream; public IntPtr Sample; public uint Status; public IntPtr Events; }

    internal static unsafe int Read(IMFTransform transform, IMFSample? supplied, out IMFSample? produced)
    {
        var output = new NativeOutput { Sample = supplied?.NativePointer ?? IntPtr.Zero };
        uint status = 0;
        IntPtr* table = *(IntPtr**)transform.NativePointer;
        var call = (delegate* unmanaged[Stdcall]<IntPtr, uint, uint, NativeOutput*, uint*, int>)table[25];
        int result = call(transform.NativePointer, 0, 1, &output, &status);
        if (output.Events != IntPtr.Zero) Marshal.Release(output.Events);
        produced = null;
        if (supplied != null)
        {
            if (output.Sample != IntPtr.Zero && output.Sample != supplied.NativePointer)
            {
                Marshal.Release(output.Sample);
                throw new InvalidOperationException("Transform replaced a caller-owned output sample.");
            }
            return result;
        }
        if (output.Sample != IntPtr.Zero) produced = new IMFSample(output.Sample);
        return result;
    }
}

using Vortice.Direct3D11;
using Vortice.DXGI;

internal sealed class GpuBgraConverter : IDisposable
{
    private readonly List<IDisposable> resources = new();
    private readonly ID3D11DeviceContext context;
    private readonly ID3D11VideoContext videoContext;
    private readonly ID3D11VideoDevice videoDevice;
    private readonly ID3D11VideoProcessorEnumerator enumerator;
    private readonly ID3D11VideoProcessor processor;
    private readonly ID3D11VideoProcessorInputView[] inputs;
    private readonly ID3D11Texture2D[] targets;
    private readonly ID3D11VideoProcessorOutputView[] outputs;
    private readonly bool[] busy = new bool[4];
    private readonly Queue<(int Slot, long Timestamp)> pending = new();
    internal bool HasFree => busy.Any(value => !value);

    internal GpuBgraConverter(ID3D11Device device, ID3D11DeviceContext context, EncoderProbeOptions options)
    {
        this.context = context;
        int width = options.Width, height = options.Height, fps = options.Fps;
        try
        {
            videoDevice = Own(device.QueryInterface<ID3D11VideoDevice>());
            videoContext = Own(context.QueryInterface<ID3D11VideoContext>());
            var content = new VideoProcessorContentDescription { InputFrameFormat = VideoFrameFormat.Progressive,
                InputFrameRate = new Rational((uint)fps, 1), OutputFrameRate = new Rational((uint)fps, 1),
                InputWidth = (uint)width, InputHeight = (uint)height, OutputWidth = (uint)width, OutputHeight = (uint)height, Usage = VideoUsage.PlaybackNormal };
            enumerator = Own(videoDevice.CreateVideoProcessorEnumerator(content));
            enumerator.CheckVideoProcessorFormat(Format.B8G8R8A8_UNorm, out var inputSupport).CheckError();
            enumerator.CheckVideoProcessorFormat(Format.NV12, out var outputSupport).CheckError();
            if ((inputSupport & VideoProcessorFormatSupport.Input) == 0 || (outputSupport & VideoProcessorFormatSupport.Output) == 0)
                throw new NotSupportedException("This adapter does not advertise BGRA input and NV12 output for video processing.");
            processor = Own(videoDevice.CreateVideoProcessor(enumerator, 0));
            inputs = new ID3D11VideoProcessorInputView[options.WgcHwnd == 0 ? 2 : 0];
            for (int index = 0; index < inputs.Length; index++)
            {
                var source = Own(Source(device, options, index != 0));
                inputs[index] = Own(videoDevice.CreateVideoProcessorInputView(source, enumerator,
                    new VideoProcessorInputViewDescription { ViewDimension = VideoProcessorInputViewDimension.Texture2D }));
            }
            targets = new ID3D11Texture2D[4]; outputs = new ID3D11VideoProcessorOutputView[4];
            var description = new Texture2DDescription { Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
                Format = Format.NV12, SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Default,
                BindFlags = BindFlags.RenderTarget | BindFlags.ShaderResource };
            for (int index = 0; index < targets.Length; index++)
            {
                targets[index] = Own(device.CreateTexture2D(description));
                outputs[index] = Own(videoDevice.CreateVideoProcessorOutputView(targets[index], enumerator,
                    new VideoProcessorOutputViewDescription { ViewDimension = VideoProcessorOutputViewDimension.Texture2D }));
            }
            var rect = new Vortice.RawRect(0, 0, width, height);
            videoContext.VideoProcessorSetStreamFrameFormat(processor, 0, VideoFrameFormat.Progressive);
            videoContext.VideoProcessorSetStreamSourceRect(processor, 0, true, rect);
            videoContext.VideoProcessorSetStreamDestRect(processor, 0, true, rect);
            videoContext.VideoProcessorSetOutputTargetRect(processor, true, rect);
            videoContext.VideoProcessorSetStreamColorSpace(processor, 0,
                new VideoProcessorColorSpace { RGB_Range = 0, YCbCr_Matrix = 1, Nominal_Range = 2 });
            videoContext.VideoProcessorSetOutputColorSpace(processor,
                new VideoProcessorColorSpace { RGB_Range = 0, YCbCr_Matrix = 1, Nominal_Range = 1 });
        }
        catch { Dispose(); throw; }
    }

    internal ID3D11Texture2D ConvertFrame(int index, long timestamp, ID3D11Texture2D? captured = null)
    {
        int slot = Array.FindIndex(busy, value => !value);
        if (slot < 0) throw new InvalidOperationException("GPU conversion queue is full.");
        if (captured == null && inputs.Length == 0) throw new InvalidOperationException("WGC conversion requires the explicitly acquired fixture frame.");
        using var captureView = captured == null ? null : videoDevice.CreateVideoProcessorInputView(captured, enumerator,
            new VideoProcessorInputViewDescription { ViewDimension = VideoProcessorInputViewDimension.Texture2D });
        videoContext.VideoProcessorBlt(processor, outputs[slot], 0,
            new[] { new VideoProcessorStream { Enable = true, InputSurface = captureView ?? inputs[index % 2] } }).CheckError();
        context.Flush(); busy[slot] = true; pending.Enqueue((slot, timestamp));
        return targets[slot];
    }

    internal void Complete(long timestamp)
    {
        if (!pending.TryDequeue(out var item) || item.Timestamp != timestamp)
            throw new InvalidOperationException("Encoder output order/timestamp did not match the surface lease.");
        busy[item.Slot] = false;
    }

    private T Own<T>(T resource) where T : IDisposable { resources.Add(resource); return resource; }
    public void Dispose()
    {
        for (int index = resources.Count - 1; index >= 0; index--)
        {
            try { resources[index].Dispose(); }
            catch (Exception error) { Console.Error.WriteLine($"GPU converter cleanup:0x{error.HResult:X8}"); }
        }
        resources.Clear(); pending.Clear();
    }

    private static unsafe ID3D11Texture2D Source(ID3D11Device device, EncoderProbeOptions options, bool alternate)
    {
        int width = options.Width, height = options.Height;
        byte[] pixels = new byte[checked(width * height * 4)];
        for (int pixel = 0; pixel < width * height; pixel++)
        {
            int offset = pixel * 4; pixels[offset + 3] = 255;
            if (!options.ColorPattern)
            {
                pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = alternate ? (byte)28 : (byte)214;
                continue;
            }
            int quadrant = (pixel / width >= height / 2 ? 2 : 0) + (pixel % width >= width / 2 ? 1 : 0);
            if (alternate) quadrant = 3 - quadrant;
            pixels[offset] = quadrant is 2 or 3 ? (byte)255 : (byte)0;
            pixels[offset + 1] = quadrant is 1 or 3 ? (byte)255 : (byte)0;
            pixels[offset + 2] = quadrant is 0 or 3 ? (byte)255 : (byte)0;
        }
        var description = new Texture2DDescription { Width = (uint)width, Height = (uint)height, MipLevels = 1, ArraySize = 1,
            Format = Format.B8G8R8A8_UNorm, SampleDescription = new SampleDescription(1, 0), Usage = ResourceUsage.Default,
            BindFlags = BindFlags.RenderTarget | BindFlags.ShaderResource };
        fixed (byte* pointer = pixels) return device.CreateTexture2D(description, new SubresourceData((IntPtr)pointer, (uint)(width * 4), (uint)pixels.Length));
    }
}

using System;
using System.IO;
using System.Runtime.InteropServices;
using Vortice.Direct3D11;
using Vortice.D3DCompiler;
using Vortice.DXGI;

namespace Xennex.CaptureWorker;

// Dedicated capture context only. All textures are reused until the geometry changes.
internal sealed class GpuFrameScaler : IDisposable
{
    private readonly ID3D11Device device;
    private readonly ID3D11DeviceContext context;
    private ID3D11ComputeShader? shader;
    private ID3D11SamplerState? sampler;
    private ID3D11Buffer? constants;
    private ID3D11Texture2D? input, output;
    private ID3D11ShaderResourceView? sourceView;
    private ID3D11UnorderedAccessView? targetView;

    [StructLayout(LayoutKind.Sequential)]
    private struct Settings
    {
        public uint InputWidth, InputHeight, OutputWidth, OutputHeight;
        public uint Rotation, SamplesX, SamplesY, Reserved;
    }
    internal GpuFrameScaler(ID3D11Device device, ID3D11DeviceContext context)
    { this.device = device; this.context = context; }

    internal ID3D11Texture2D Transform(ID3D11Texture2D texture, FrameSize size, ModeRotation rotation)
    {
        EnsureShader();
        var description = texture.Description;
        if (input == null || input.Description.Width != description.Width || input.Description.Height != description.Height ||
            output == null || output.Description.Width != size.Width || output.Description.Height != size.Height)
            CreateTextures(description, size);
        uint orientedWidth = rotation is ModeRotation.Rotate90 or ModeRotation.Rotate270 ? description.Height : description.Width;
        uint orientedHeight = rotation is ModeRotation.Rotate90 or ModeRotation.Rotate270 ? description.Width : description.Height;
        var settings = new Settings
        {
            InputWidth = description.Width, InputHeight = description.Height,
            OutputWidth = (uint)size.Width, OutputHeight = (uint)size.Height,
            Rotation = rotation switch { ModeRotation.Rotate90 => 1u, ModeRotation.Rotate180 => 2u, ModeRotation.Rotate270 => 3u, _ => 0u },
            SamplesX = (uint)Math.Clamp((int)Math.Ceiling((double)orientedWidth / size.Width), 1, 4),
            SamplesY = (uint)Math.Clamp((int)Math.Ceiling((double)orientedHeight / size.Height), 1, 4),
        };
        context.CopyResource(input!, texture);
        context.UpdateSubresource(in settings, constants!);
        try
        {
            context.CSSetShader(shader!);
            context.CSSetConstantBuffer(0, constants!);
            context.CSSetSampler(0, sampler!);
            context.CSSetShaderResource(0, sourceView!);
            context.CSSetUnorderedAccessView(0, targetView!);
            context.Dispatch((uint)(size.Width + 7) / 8, (uint)(size.Height + 7) / 8, 1);
        }
        finally
        {
            context.CSSetShaderResource(0, null);
            context.CSSetUnorderedAccessView(0, null);
            context.CSSetShader(null);
            context.CSSetConstantBuffer(0, null);
            context.CSSetSampler(0, null);
        }
        return output!;
    }
    private void EnsureShader()
    {
        if (shader != null) return;
        using var stream = typeof(GpuFrameScaler).Assembly.GetManifestResourceStream("Xennex.GpuScale.hlsl") ?? throw new InvalidOperationException("Shader de captura ausente.");
        using var reader = new StreamReader(stream);
        var code = Compiler.Compile(reader.ReadToEnd(), "Main", "GpuScale.hlsl", "cs_5_0", ShaderFlags.OptimizationLevel3);
        try
        {
            shader = device.CreateComputeShader(code.Span);
            constants = device.CreateBuffer(new BufferDescription { ByteWidth = 32, BindFlags = BindFlags.ConstantBuffer, Usage = ResourceUsage.Default });
            sampler = device.CreateSamplerState(new SamplerDescription
            {
                Filter = Filter.MinMagMipLinear,
                AddressU = TextureAddressMode.Clamp, AddressV = TextureAddressMode.Clamp, AddressW = TextureAddressMode.Clamp,
                MaxLOD = float.MaxValue, MaxAnisotropy = 1, ComparisonFunc = ComparisonFunction.Never,
            });
        }
        catch { Dispose(); throw; }
    }
    private void CreateTextures(Texture2DDescription description, FrameSize size)
    {
        ReleaseTextures();
        try
        {
            var source = new Texture2DDescription
            {
                Width = description.Width, Height = description.Height, MipLevels = 1, ArraySize = 1,
                Format = Format.B8G8R8A8_UNorm, SampleDescription = new SampleDescription(1, 0),
                BindFlags = BindFlags.ShaderResource, Usage = ResourceUsage.Default,
            };
            input = device.CreateTexture2D(source); sourceView = device.CreateShaderResourceView(input);
            source.Width = (uint)size.Width; source.Height = (uint)size.Height;
            source.Format = Format.R8G8B8A8_UNorm; source.BindFlags = BindFlags.UnorderedAccess;
            output = device.CreateTexture2D(source); targetView = device.CreateUnorderedAccessView(output);
        }
        catch { ReleaseTextures(); throw; }
    }
    private void ReleaseTextures()
    { targetView?.Dispose(); sourceView?.Dispose(); input?.Dispose(); output?.Dispose(); targetView = null; sourceView = null; input = output = null; }
    public void Dispose()
    { ReleaseTextures(); shader?.Dispose(); sampler?.Dispose(); constants?.Dispose(); shader = null; sampler = null; constants = null; }
}

Texture2D<float4> Source : register(t0);
SamplerState LinearClamp : register(s0);
RWTexture2D<float4> Output : register(u0);
cbuffer Settings : register(b0)
{
    uint InputWidth, InputHeight, OutputWidth, OutputHeight;
    uint Rotation, SamplesX, SamplesY, Reserved;
};

float2 SourceUV(float2 uv)
{
    if (Rotation == 1) return float2(uv.y, 1.0 - uv.x);
    if (Rotation == 2) return 1.0 - uv;
    if (Rotation == 3) return float2(1.0 - uv.y, uv.x);
    return uv;
}

[numthreads(8, 8, 1)]
void Main(uint3 pixel : SV_DispatchThreadID)
{
    if (pixel.x >= OutputWidth || pixel.y >= OutputHeight) return;
    float4 color = 0;
    // Bounded area sampling avoids simple nearest/bilinear aliasing on large reductions.
    [unroll] for (uint y = 0; y < 4; y++)
    {
        [unroll] for (uint x = 0; x < 4; x++)
        {
            if (x < SamplesX && y < SamplesY)
            {
                float2 offset = (float2(x, y) + 0.5) / float2(SamplesX, SamplesY);
                float2 uv = (float2(pixel.xy) + offset) / float2(OutputWidth, OutputHeight);
                color += Source.SampleLevel(LinearClamp, SourceUV(uv), 0);
            }
        }
    }
    // RGBA UAV is supported by D3D11; store B,G,R,A bytes for the existing BGRA JPEG input.
    Output[pixel.xy] = (color / (SamplesX * SamplesY)).bgra;
}

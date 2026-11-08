// Own C ABI adapter around public AMF interfaces. Driver runtime is never bundled.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include "core/Factory.h"
#include "core/Buffer.h"
#include "components/VideoEncoderVCE.h"

_Static_assert(sizeof(void*) == 8 && sizeof(AMFVariantStruct) == 24, "Pinned Windows x64 AMF C ABI");

typedef struct Encoder {
    HMODULE module;
    AMFContext *context;
    AMFComponent *component;
    AMFBuffer *packet;
    amf_uint64 runtime;
} Encoder;

#define EXPORT __declspec(dllexport)
EXPORT void __cdecl xennex_amf_close(Encoder *encoder) {
    if (!encoder) return;
    if (encoder->packet) encoder->packet->pVtbl->Release(encoder->packet);
    if (encoder->component) {
        encoder->component->pVtbl->Terminate(encoder->component);
        encoder->component->pVtbl->Release(encoder->component);
    }
    if (encoder->context) {
        encoder->context->pVtbl->Terminate(encoder->context);
        encoder->context->pVtbl->Release(encoder->context);
    }
    if (encoder->module) FreeLibrary(encoder->module);
    free(encoder);
}
static AMF_RESULT set_int(AMFComponent *component, const wchar_t *key, amf_int64 value) {
    AMFVariantStruct variant = {0}; variant.type = AMF_VARIANT_INT64; variant.int64Value = value;
    return component->pVtbl->SetProperty(component, key, variant);
}
static AMF_RESULT set_bool(AMFComponent *component, const wchar_t *key, amf_bool value) {
    AMFVariantStruct variant = {0}; variant.type = AMF_VARIANT_BOOL; variant.boolValue = value;
    return component->pVtbl->SetProperty(component, key, variant);
}

// Failures identify the fixed stage numerically; no driver strings or pixels logged.
EXPORT int __cdecl xennex_amf_open(void *device, int width, int height, int fps, int bitrate, int level, Encoder **output) {
    if (!output) return -1;
    *output = NULL;
    if (!device || width < 16 || width > 4096 || height < 16 || height > 2160 ||
        width % 2 || height % 2 || (int64_t)width * height > 3840LL * 2160 || fps < 1 || fps > 120 ||
        bitrate < 100000 || bitrate > 100000000 || level < 31 || level > 60) return -2;
    Encoder *encoder = (Encoder*)calloc(1, sizeof(Encoder));
    if (!encoder) return -3;
    int failure = -4;
    AMF_RESULT result;
#define STEP(stage, expression) do { result = (expression); if (result != AMF_OK) { failure = -((stage) * 1000 + (int)result); goto failed; } } while (0)
    encoder->module = LoadLibraryExW(L"amfrt64.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!encoder->module) goto failed;
    AMFInit_Fn initialize = (AMFInit_Fn)GetProcAddress(encoder->module, AMF_INIT_FUNCTION_NAME);
    AMFQueryVersion_Fn version = (AMFQueryVersion_Fn)GetProcAddress(encoder->module, AMF_QUERY_VERSION_FUNCTION_NAME);
    if (!initialize || !version) { failure = -5; goto failed; }
    STEP(1, version(&encoder->runtime));
    AMFFactory *factory = NULL;
    STEP(2, initialize(AMF_MAKE_FULL_VERSION(1, 4, 0, 0), &factory));
    STEP(3, factory->pVtbl->CreateContext(factory, &encoder->context));
    STEP(4, encoder->context->pVtbl->InitDX11(encoder->context, device, AMF_DX11_0));
    STEP(5, factory->pVtbl->CreateComponent(factory, encoder->context, AMFVideoEncoderVCE_AVC, &encoder->component));
    STEP(6, set_int(encoder->component, AMF_VIDEO_ENCODER_USAGE, AMF_VIDEO_ENCODER_USAGE_ULTRA_LOW_LATENCY));
    STEP(7, set_int(encoder->component, AMF_VIDEO_ENCODER_PROFILE, AMF_VIDEO_ENCODER_PROFILE_CONSTRAINED_BASELINE));
    STEP(8, set_int(encoder->component, AMF_VIDEO_ENCODER_PROFILE_LEVEL, level));
    AMFVariantStruct size = {0}; size.type = AMF_VARIANT_SIZE; size.sizeValue.width = width; size.sizeValue.height = height;
    STEP(9, encoder->component->pVtbl->SetProperty(encoder->component, AMF_VIDEO_ENCODER_FRAMESIZE, size));
    AMFVariantStruct rate = {0}; rate.type = AMF_VARIANT_RATE; rate.rateValue.num = fps; rate.rateValue.den = 1;
    STEP(10, encoder->component->pVtbl->SetProperty(encoder->component, AMF_VIDEO_ENCODER_FRAMERATE, rate));
    STEP(11, set_int(encoder->component, AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD, AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD_CBR));
    STEP(12, set_int(encoder->component, AMF_VIDEO_ENCODER_TARGET_BITRATE, bitrate));
    STEP(13, set_int(encoder->component, AMF_VIDEO_ENCODER_VBV_BUFFER_SIZE, bitrate / 4)); // AMF uses bits.
    STEP(14, set_bool(encoder->component, AMF_VIDEO_ENCODER_ENFORCE_HRD, 1));
    STEP(15, set_bool(encoder->component, AMF_VIDEO_ENCODER_FILLER_DATA_ENABLE, 0));
    STEP(16, set_int(encoder->component, AMF_VIDEO_ENCODER_B_PIC_PATTERN, 0));
    STEP(18, set_int(encoder->component, AMF_VIDEO_ENCODER_INPUT_COLOR_PROFILE, AMF_VIDEO_CONVERTER_COLOR_PROFILE_709));
    STEP(19, set_int(encoder->component, AMF_VIDEO_ENCODER_OUTPUT_COLOR_PROFILE, AMF_VIDEO_CONVERTER_COLOR_PROFILE_709));
    STEP(20, set_int(encoder->component, AMF_VIDEO_ENCODER_OUTPUT_COLOR_PRIMARIES, AMF_COLOR_PRIMARIES_BT709));
    STEP(21, set_int(encoder->component, AMF_VIDEO_ENCODER_OUTPUT_TRANSFER_CHARACTERISTIC, AMF_COLOR_TRANSFER_CHARACTERISTIC_BT709));
    STEP(22, set_int(encoder->component, AMF_VIDEO_ENCODER_OUTPUT_MATRIX_COEFF, AMF_COLOR_MATRIX_COEFF_BT_709));
    STEP(17, encoder->component->pVtbl->Init(encoder->component, AMF_SURFACE_NV12, width, height));
    *output = encoder;
    return 0;
failed:
    xennex_amf_close(encoder);
    return failure;
#undef STEP
}

EXPORT int __cdecl xennex_amf_submit(Encoder *encoder, void *texture, int64_t timestamp, int64_t duration, int keyframe) {
    if (!encoder || !texture || timestamp < 0 || duration <= 0) return -1;
    AMFSurface *surface = NULL;
    AMF_RESULT result = encoder->context->pVtbl->CreateSurfaceFromDX11Native(encoder->context, texture, &surface, NULL);
    if (result != AMF_OK) { if (surface) surface->pVtbl->Release(surface); return -100 - (int)result; }
    surface->pVtbl->SetPts(surface, timestamp); surface->pVtbl->SetDuration(surface, duration);
    if (keyframe) {
        AMFVariantStruct type = {0}; type.type = AMF_VARIANT_INT64; type.int64Value = AMF_VIDEO_ENCODER_PICTURE_TYPE_IDR;
        result = surface->pVtbl->SetProperty(surface, AMF_VIDEO_ENCODER_FORCE_PICTURE_TYPE, type);
        if (result != AMF_OK) goto done;
        AMFVariantStruct flag = {0}; flag.type = AMF_VARIANT_BOOL; flag.boolValue = 1;
        result = surface->pVtbl->SetProperty(surface, AMF_VIDEO_ENCODER_INSERT_SPS, flag);
        if (result != AMF_OK) goto done;
        result = surface->pVtbl->SetProperty(surface, AMF_VIDEO_ENCODER_INSERT_PPS, flag);
        if (result != AMF_OK) goto done;
    }
    result = encoder->component->pVtbl->SubmitInput(encoder->component, (AMFData*)surface);
done:
    surface->pVtbl->Release(surface);
    return result == AMF_OK ? 0 : result == AMF_INPUT_FULL ? 1 : -200 - (int)result;
}
EXPORT int __cdecl xennex_amf_poll(Encoder *encoder, const void **bytes, int *length, int64_t *timestamp) {
    if (!encoder || !bytes || !length || !timestamp || encoder->packet) return -1;
    *bytes = NULL; *length = 0; *timestamp = 0;
    AMFData *data = NULL;
    AMF_RESULT result = encoder->component->pVtbl->QueryOutput(encoder->component, &data);
    if (result == AMF_EOF) { if (data) data->pVtbl->Release(data); return 2; }
    if (result == AMF_REPEAT || (result == AMF_OK && !data)) { if (data) data->pVtbl->Release(data); return 1; }
    if (result != AMF_OK) { if (data) data->pVtbl->Release(data); return -300 - (int)result; }
    AMFGuid id = IID_AMFBuffer();
    result = data->pVtbl->QueryInterface(data, &id, (void**)&encoder->packet);
    data->pVtbl->Release(data);
    if (result != AMF_OK) return -400 - (int)result;
    if (encoder->packet->pVtbl->GetMemoryType(encoder->packet) != AMF_MEMORY_HOST) {
        result = encoder->packet->pVtbl->Convert(encoder->packet, AMF_MEMORY_HOST);
        if (result != AMF_OK) return -500 - (int)result;
    }
    amf_size size = encoder->packet->pVtbl->GetSize(encoder->packet);
    if (!size || size > 16777216) return -600;
    *bytes = encoder->packet->pVtbl->GetNative(encoder->packet);
    if (!*bytes) return -601;
    *length = (int)size; *timestamp = encoder->packet->pVtbl->GetPts(encoder->packet);
    return 0;
}
EXPORT void __cdecl xennex_amf_release_packet(Encoder *encoder) {
    if (encoder && encoder->packet) { encoder->packet->pVtbl->Release(encoder->packet); encoder->packet = NULL; }
}
EXPORT int __cdecl xennex_amf_drain(Encoder *encoder) {
    if (!encoder) return -1;
    AMF_RESULT result = encoder->component->pVtbl->Drain(encoder->component);
    return result == AMF_OK ? 0 : result == AMF_INPUT_FULL ? 1 : -700 - (int)result;
}
EXPORT uint64_t __cdecl xennex_amf_runtime_version(Encoder *encoder) { return encoder ? encoder->runtime : 0; }
EXPORT int __cdecl xennex_amf_settings(Encoder *encoder, uint32_t *numerator, uint32_t *denominator, uint32_t *bitrate, uint32_t *mode) {
    if (!encoder || !numerator || !denominator || !bitrate || !mode) return -1;
    AMFVariantStruct value = {0};
    AMF_RESULT result = encoder->component->pVtbl->GetProperty(encoder->component, AMF_VIDEO_ENCODER_FRAMERATE, &value);
    if (result != AMF_OK || value.type != AMF_VARIANT_RATE || !value.rateValue.den) { AMFVariantClear(&value); return -2; }
    *numerator = value.rateValue.num; *denominator = value.rateValue.den; AMFVariantClear(&value);
    result = encoder->component->pVtbl->GetProperty(encoder->component, AMF_VIDEO_ENCODER_TARGET_BITRATE, &value);
    if (result != AMF_OK || value.type != AMF_VARIANT_INT64 || value.int64Value < 100000 || value.int64Value > 100000000) { AMFVariantClear(&value); return -3; }
    *bitrate = (uint32_t)value.int64Value; AMFVariantClear(&value);
    result = encoder->component->pVtbl->GetProperty(encoder->component, AMF_VIDEO_ENCODER_RATE_CONTROL_METHOD, &value);
    if (result != AMF_OK || value.type != AMF_VARIANT_INT64 || value.int64Value < 0 || value.int64Value > 10) { AMFVariantClear(&value); return -4; }
    *mode = (uint32_t)value.int64Value; AMFVariantClear(&value);
    return 0;
}

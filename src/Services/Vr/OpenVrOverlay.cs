using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Valve.VR;
using Xennex.Interop.Vr;

namespace Xennex.Services.Vr;

internal sealed class OpenVrOverlay : IVrOverlay
{
    private CVROverlay _overlay;
    private ulong _dashboard, _thumbnail, _floating;
    private bool _initialized, _presented;
    private float _distance = 1.5f;
    private readonly VrPointerInput _dashboardInput = new(), _floatingInput = new();
    private readonly string _key = "xennex.gallery." + Environment.ProcessId;

    public void Connect()
    {
        var servers = Process.GetProcessesByName("vrserver");
        var running = servers.Length != 0;
        foreach (var server in servers) server.Dispose();
        if (!running) throw new InvalidOperationException("Abra o SteamVR e conecte o headset primeiro.");
        OpenVrLibrary.Register();
        var error = EVRInitError.None;
        var system = OpenVR.Init(ref error, EVRApplicationType.VRApplication_Overlay);
        if (error != EVRInitError.None || system == null)
            throw new InvalidOperationException($"O SteamVR não conectou: {error}. Verifique o headset e atualize o SteamVR.");
        _initialized = true;
        _overlay = OpenVR.Overlay ?? throw new InvalidOperationException("A API de overlays do SteamVR não está disponível.");
        Check(_overlay.CreateDashboardOverlay(_key, "Xennex · Biblioteca", ref _dashboard, ref _thumbnail));
        Check(_overlay.CreateOverlay(_key + ".pinned", "Xennex · Biblioteca fixada", ref _floating));
        Configure(_dashboard);
        Configure(_floating);
        Check(_overlay.SetOverlayFlag(_floating, VROverlayFlags.MakeOverlaysInteractiveIfVisible, true));
        var icon = new byte[128 * 128 * 4];
        for (var i = 0; i < icon.Length; i += 4) { icon[i] = 190; icon[i + 1] = 64; icon[i + 2] = 152; icon[i + 3] = 255; }
        Upload(_thumbnail, icon, 128, 128);
    }

    private void Configure(ulong handle)
    {
        Check(_overlay.SetOverlayWidthInMeters(handle, 2f));
        Check(_overlay.SetOverlayInputMethod(handle, VROverlayInputMethod.Mouse));
        var scale = new HmdVector2_t { v0 = VrGallerySession.Width, v1 = VrGallerySession.Height };
        Check(_overlay.SetOverlayMouseScale(handle, ref scale));
        Check(_overlay.SetOverlayFlag(handle, VROverlayFlags.ProtectedContent, true));
    }

    public void Present(byte[] rgba)
    {
        if (rgba.Length != VrGallerySession.Width * VrGallerySession.Height * 4)
            throw new ArgumentException("Tamanho do quadro VR inválido.");
        Upload(_dashboard, rgba, VrGallerySession.Width, VrGallerySession.Height);
        Upload(_floating, rgba, VrGallerySession.Width, VrGallerySession.Height);
        if (_presented) return;
        _overlay.ShowDashboard(_key);
        _presented = true;
    }

    private void Upload(ulong handle, byte[] rgba, uint width, uint height)
    {
        var pinned = GCHandle.Alloc(rgba, GCHandleType.Pinned);
        try { Check(_overlay.SetOverlayRaw(handle, pinned.AddrOfPinnedObject(), width, height, 4)); }
        finally { pinned.Free(); }
    }

    public void SetPinned(bool pinned)
    {
        if (!pinned) { Check(_overlay.HideOverlay(_floating)); _overlay.ShowDashboard(_key); return; }
        Recenter();
        Check(_overlay.ShowOverlay(_floating));
    }

    public void Recenter()
    {
        var poses = new TrackedDevicePose_t[OpenVR.k_unMaxTrackedDeviceCount];
        OpenVR.System.GetDeviceToAbsoluteTrackingPose(ETrackingUniverseOrigin.TrackingUniverseStanding, 0, poses);
        if (!poses[0].bDeviceIsConnected || !poses[0].bPoseIsValid)
            throw new InvalidOperationException("O headset não tem uma posição válida. Vista o headset e tente novamente.");
        var transform = poses[0].mDeviceToAbsoluteTracking;
        transform.m3 -= transform.m2 * _distance;
        transform.m7 -= transform.m6 * _distance;
        transform.m11 -= transform.m10 * _distance;
        Check(_overlay.SetOverlayTransformAbsolute(_floating, ETrackingUniverseOrigin.TrackingUniverseStanding, ref transform));
    }

    public void SetSize(float widthMeters, float distanceMeters)
    {
        if (!float.IsFinite(widthMeters) || !float.IsFinite(distanceMeters) || widthMeters is < .75f or > 3 || distanceMeters is < .75f or > 3)
            throw new ArgumentException("Tamanho ou distância VR inválidos.");
        Check(_overlay.SetOverlayWidthInMeters(_dashboard, widthMeters));
        Check(_overlay.SetOverlayWidthInMeters(_floating, widthMeters));
        var moved = _distance != distanceMeters;
        _distance = distanceMeters;
        if (moved && _overlay.IsOverlayVisible(_floating)) Recenter();
    }

    public IEnumerable<string> PollActions(Func<float, float, string> hit)
    {
        var vrEvent = new VREvent_t();
        var size = (uint)Marshal.SizeOf<VREvent_t>();
        foreach (var handle in new[] { _dashboard, _floating })
        {
            // Bound each poll so a flooded event queue cannot prevent cancellation.
            for (var count = 0; count < 64 && _overlay.PollNextOverlayEvent(handle, ref vrEvent, size); count++)
            {
                if (vrEvent.eventType == (uint)EVREventType.VREvent_Quit) { yield return "close"; yield break; }
                var action = (handle == _dashboard ? _dashboardInput : _floatingInput).Accept(vrEvent, hit);
                if (action.Length > 0) yield return action;
            }
        }
        if (!OpenVR.IsHmdPresent()) yield return "close";
    }

    private static void Check(EVROverlayError error)
    {
        if (error != EVROverlayError.None) throw new InvalidOperationException("O painel SteamVR falhou: " + error);
    }

    public void Dispose()
    {
        if (!_initialized) return;
        // Destroying the dashboard also destroys its thumbnail; the runtime rejects
        // independently destroying a dashboard thumbnail (ThumbnailCantBeDestroyed).
        foreach (var handle in new[] { _floating, _dashboard })
        {
            if (handle == 0 || _overlay == null) continue;
            try { Check(_overlay.DestroyOverlay(handle)); }
            catch (Exception error) { AppLog.Error("VR overlay cleanup", error); }
        }
        OpenVR.Shutdown();
        _initialized = false;
    }
}

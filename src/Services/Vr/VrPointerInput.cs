using System;
using System.Collections.Generic;
using Valve.VR;

namespace Xennex.Services.Vr;

// SteamVR button events need not repeat the coordinates from MouseMove.
internal sealed class VrPointerInput
{
    private readonly Dictionary<uint, (float X, float Y)> _positions = new();
    private readonly Dictionary<uint, string> _pressed = new();

    public string Accept(VREvent_t input, Func<float, float, string> hit)
    {
        var device = input.data.mouse.cursorIndex;
        if (input.eventType is (uint)EVREventType.VREvent_OverlayHidden or (uint)EVREventType.VREvent_FocusLeave)
        { _positions.Clear(); _pressed.Clear(); return ""; }
        if (input.eventType == (uint)EVREventType.VREvent_MouseMove)
        {
            var x = input.data.mouse.x; var y = VrGallerySession.Height - input.data.mouse.y;
            if (float.IsFinite(x) && float.IsFinite(y)) _positions[device] = (x, y);
            else { _positions.Remove(device); _pressed.Remove(device); }
            return "";
        }
        if ((input.data.mouse.button & (uint)EVRMouseButton.Left) == 0 || !_positions.TryGetValue(device, out var position)) return "";
        if (input.eventType == (uint)EVREventType.VREvent_MouseButtonDown)
        { _pressed[device] = hit(position.X, position.Y); return ""; }
        if (input.eventType != (uint)EVREventType.VREvent_MouseButtonUp || !_pressed.Remove(device, out var action)) return "";
        return action.Length > 0 && action == hit(position.X, position.Y) ? action : "";
    }
}

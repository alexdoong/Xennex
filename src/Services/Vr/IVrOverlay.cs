using System;
using System.Collections.Generic;

namespace Xennex.Services.Vr;

internal interface IVrOverlay : IDisposable
{
    void Connect();
    void Present(byte[] rgba);
    void SetPinned(bool pinned);
    void Recenter();
    void SetSize(float widthMeters, float distanceMeters);
    IEnumerable<string> PollActions(Func<float, float, string> hit);
}

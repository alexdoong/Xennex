using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xennex.Models.Assets;
using Xennex.Services.Vr;

internal static class Program
{
    private static readonly string First = new('1', 32), Second = new('2', 32);
    private static AssetItem Resolve(string id) => new() { Id = id, Name = id == First ? "Synthetic first.png" : "Synthetic second.png", IsImage = true, Available = true };
    private static string Request => JsonSerializer.Serialize(new { assetIds = new[] { First, Second }, initialId = First });
    private static MemoryStream Image(string id)
    {
        var stream = new MemoryStream();
        using var image = new Bitmap(32, 24);
        using (var graphics = Graphics.FromImage(image)) graphics.Clear(id == First ? Color.DeepSkyBlue : Color.Orange);
        image.Save(stream, System.Drawing.Imaging.ImageFormat.Png);
        stream.Position = 0;
        return stream;
    }

    private static void Check(bool condition, string name) { if (!condition) throw new Exception(name); }
    private static void Reject(Action action) { try { action(); } catch (ArgumentException) { return; } throw new Exception("Invalid request accepted"); }
    private static AssetVrState State(AssetVrService service) => JsonSerializer.Deserialize<AssetVrState>(service.GetState(), new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
    private static async Task Until(Func<bool> condition)
    {
        for (var i = 0; i < 100; i++) { if (condition()) return; await Task.Delay(20); }
        throw new Exception("VR worker timeout");
    }

    public static async Task Main(string[] args)
    {
        var request = new AssetVrRequest { AssetIds = new() { First, Second } };
        var session = new VrGallerySession(request, Resolve);
        Reject(() => new VrGallerySession(new AssetVrRequest { AssetIds = new() { "../private.png" } }, Resolve));
        Reject(() => new VrGallerySession(new AssetVrRequest { AssetIds = new() { First, First } }, Resolve));
        Reject(() => new VrGallerySession(new AssetVrRequest { AssetIds = new() { First }, InitialId = Second }, Resolve));
        Reject(() => new VrGallerySession(request, id => new AssetItem { Id = id, IsImage = true }));
        Reject(() => session.Apply("execute"));
        session.Apply("previous"); Check(session.Index == 0, "Previous boundary");
        session.Apply("next"); session.Apply("next"); Check(session.Index == 1, "Next boundary");
        for (var i = 0; i < 50; i++) session.Apply("zoomIn"); Check(session.Zoom == 4, "Maximum zoom");
        for (var i = 0; i < 50; i++) session.Apply("zoomOut"); Check(session.Zoom == .5f, "Minimum zoom");
        session.Apply("previous"); Check(session.Zoom == 1, "New image resets zoom");
        Check(VrPanelLayout.Hit(session, 40, 710) == "" && VrPanelLayout.Hit(session, 180, 710) == "next", "Disabled previous and enabled next");
        session.Apply("next");
        Check(VrPanelLayout.Hit(session, 40, 710) == "previous" && VrPanelLayout.Hit(session, 180, 710) == "", "Last image disables Next");
        session.Apply("previous");
        Check(VrPanelLayout.Hit(session, 160, 710) == "" && VrPanelLayout.Hit(session, float.NaN, 710) == "" && VrPanelLayout.Hit(session, 1250, 710) == "", "Click gaps and invalid coordinates");
        await VrNavigationTests.Run(args.Contains("--native"));
        var pixels = VrPanelRenderer.Render(session, Image);
        Check(pixels.Length == 1280 * 800 * 4, "Bounded RGBA frame");
        Check(pixels[0] == 19 && pixels[1] == 18 && pixels[2] == 29 && pixels[3] == 255, "RGBA byte order");

        var fake = new FakeOverlay();
        using var service = new AssetVrService(Resolve, Image, () => fake, (_, _) => pixels);
        await service.Start(Request);
        Check(State(service).State == "running", "Initial state");
        try { await service.Start(Request); throw new Exception("Duplicate start accepted"); } catch (InvalidOperationException) { }
        service.Control("next"); await Until(() => State(service).Index == 1);
        fake.Actions.Enqueue("zoomIn"); await Until(() => State(service).Zoom > 1);
        service.Control("pin"); await Until(() => State(service).Pinned);
        Check(fake.Pinned, "Native pin dispatched");
        service.Control("sizeUp"); await Until(() => State(service).WidthMeters == 2.25f);
        Check(fake.WidthMeters == 2.25f, "Native panel width dispatched");
        service.Control("nearer"); await Until(() => State(service).DistanceMeters == 1.25f);
        Check(fake.DistanceMeters == 1.25f, "Native panel distance dispatched");
        service.Control("close"); await Until(() => State(service).State == "stopped");
        await service.Stop(); Check(fake.Disposals == 1, "Close releases overlay");
        await service.Start(Request); await service.Stop(); Check(fake.Disposals == 2, "Restart releases overlay");

        var broken = new FakeOverlay { Fail = true };
        using var failed = new AssetVrService(Resolve, Image, () => broken, (_, _) => pixels);
        try { await failed.Start(Request); throw new Exception("Failed connection accepted"); } catch (InvalidOperationException) { }
        await failed.Stop(); Check(State(failed).State == "failed" && broken.Disposals == 1, "Connection failure cleans up and reports");
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var slow = new FakeOverlay();
        using var cancelled = new AssetVrService(Resolve, Image, () => slow, (_, _) => { entered.Set(); release.Wait(); return pixels; });
        var opening = cancelled.Start(Request); Check(entered.Wait(2000), "Render started");
        var stopping = cancelled.Stop(); release.Set(); await stopping;
        try { await opening; throw new Exception("Cancelled start reported success"); } catch (OperationCanceledException) { }
        Check(State(cancelled).State == "stopped" && slow.Disposals == 1, "Cancellation releases overlay");
        Console.WriteLine("VR tests: selection, hit testing, RGBA rendering, lifecycle, failure and cancellation passed.");

        if (!args.Contains("--native")) return;
        using var native = new AssetVrService(Resolve, Image, () => new OpenVrOverlay(), VrPanelRenderer.Render);
        Console.WriteLine("Opening synthetic SteamVR panel for three seconds...");
        await native.Start(Request);
        native.Control("next"); await Until(() => State(native).Index == 1);
        native.Control("pin"); await Until(() => State(native).Pinned);
        native.Control("sizeUp"); await Until(() => State(native).WidthMeters == 2.25f);
        native.Control("nearer"); await Until(() => State(native).DistanceMeters == 1.25f);
        native.Control("recenter");
        native.Control("pin"); await Until(() => !State(native).Pinned);
        await Task.Delay(3000);
        await native.Stop(); Check(State(native).State == "stopped", "Native cleanup");
        await native.Start(Request); await native.Stop();
        Console.WriteLine("SteamVR native smoke passed: connection, texture upload, navigation, pinning, recentering, cleanup and restart.");
    }

    private sealed class FakeOverlay : IVrOverlay
    {
        public readonly System.Collections.Concurrent.ConcurrentQueue<string> Actions = new();
        public bool Fail, Pinned;
        public int Disposals;
        public float WidthMeters, DistanceMeters;
        public void Connect() { if (Fail) throw new InvalidOperationException("Synthetic connection failure"); }
        public void Present(byte[] rgba) { }
        public void SetPinned(bool pinned) => Pinned = pinned;
        public void Recenter() { }
        public void SetSize(float widthMeters, float distanceMeters) { WidthMeters = widthMeters; DistanceMeters = distanceMeters; }
        public IEnumerable<string> PollActions(Func<float, float, string> hit) { while (Actions.TryDequeue(out var action)) yield return action; }
        public void Dispose() => Disposals++;
    }
}

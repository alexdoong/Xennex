using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Valve.VR;
using Microsoft.Data.Sqlite;
using Xennex.Models.Assets;
using Xennex.Services.Assets;
using Xennex.Services.Vr;

internal static class VrNavigationTests
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNameCaseInsensitive = true };
    private static void Check(bool condition, string name) { if (!condition) throw new Exception(name); }
    private static VREvent_t Event(EVREventType type, float x = 0, float y = 0, uint cursor = 0) => new()
    {
        eventType = (uint)type,
        data = new VREvent_Data_t { mouse = new VREvent_Mouse_t { x = x, y = y, button = 1, cursorIndex = cursor } }
    };

    public static async Task Run(bool native)
    {
        var pointer = new VrPointerInput();
        string Hit(float x, float y) => x is > 165 and < 288 && y is > 694 and < 756 ? "next" : "";
        pointer.Accept(Event(EVREventType.VREvent_MouseMove, 190, 90), Hit);
        pointer.Accept(Event(EVREventType.VREvent_MouseButtonDown), Hit);
        Check(pointer.Accept(Event(EVREventType.VREvent_MouseButtonUp), Hit) == "next", "Trigger release without coordinates uses last laser position");
        Check(pointer.Accept(Event(EVREventType.VREvent_MouseButtonUp), Hit) == "", "Duplicate release ignored");
        pointer.Accept(Event(EVREventType.VREvent_MouseButtonDown), Hit);
        pointer.Accept(Event(EVREventType.VREvent_MouseMove, 0, 0), Hit);
        Check(pointer.Accept(Event(EVREventType.VREvent_MouseButtonUp), Hit) == "", "Dragging out cancels click");
        pointer.Accept(Event(EVREventType.VREvent_MouseMove, 190, 90, 1), Hit);
        pointer.Accept(Event(EVREventType.VREvent_MouseButtonDown, cursor: 1), Hit);
        pointer.Accept(Event(EVREventType.VREvent_MouseMove, 0, 0, 2), Hit);
        Check(pointer.Accept(Event(EVREventType.VREvent_MouseButtonUp, cursor: 1), Hit) == "next", "Independent controller cursors");
        pointer.Accept(Event(EVREventType.VREvent_MouseButtonDown, cursor: 1), Hit);
        pointer.Accept(Event(EVREventType.VREvent_OverlayHidden), Hit);
        Check(pointer.Accept(Event(EVREventType.VREvent_MouseButtonUp, cursor: 1), Hit) == "", "Hidden overlay discards stale click");

        var directory = Path.Combine(Path.GetTempPath(), "XennexVrTests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var art = Path.Combine(directory, "art"); Directory.CreateDirectory(art);
            Directory.CreateDirectory(Path.Combine(art, "nested"));
            using (var image = new Bitmap(16, 16))
            {
                using var graphics = Graphics.FromImage(image);
                for (var i = 0; i < 125; i++)
                {
                    graphics.Clear(i % 2 == 0 ? Color.DeepSkyBlue : Color.Orange);
                    image.Save(Path.Combine(art, $"image-{i:000}.png"), System.Drawing.Imaging.ImageFormat.Png);
                }
                image.Save(Path.Combine(art, "nested", "inside.png"), System.Drawing.Imaging.ImageFormat.Png);
            }
            using (var tall = new Bitmap(16, 2048))
            {
                using var graphics = Graphics.FromImage(tall); graphics.Clear(Color.MediumPurple);
                tall.Save(Path.Combine(art, "image-000.png"), System.Drawing.Imaging.ImageFormat.Png);
            }
            File.WriteAllText(Path.Combine(art, "readme.txt"), "Synthetic document");
            using var assets = new AssetLibraryService(Path.Combine(directory, "data"));
            using var added = JsonDocument.Parse(assets.AddRoot(art));
            var rootId = added.RootElement.GetProperty("root").GetProperty("id").GetString();
            var jobId = added.RootElement.GetProperty("jobId").GetString();
            for (var i = 0; i < 200; i++)
            {
                var job = JsonSerializer.Deserialize<AssetJob>(assets.GetJob(jobId), Json);
                if (job.State == "completed") break;
                Check(job.State != "failed", "Synthetic indexing failed: " + job.Error);
                await Task.Delay(30);
            }
            AssetPage Query(AssetQuery query) => JsonSerializer.Deserialize<AssetPage>(assets.Query(JsonSerializer.Serialize(query)), Json);
            IReadOnlyList<AssetRoot> Roots() => JsonSerializer.Deserialize<List<AssetRoot>>(assets.GetRoots(), Json);
            AssetItem Resolve(string id) => JsonSerializer.Deserialize<AssetItem>(assets.GetDetails(id), Json);
            var session = new VrGallerySession(new AssetVrRequest { Mode = "library", Query = new AssetQuery { RootId = rootId } }, Resolve, Query, Roots);
            Check(session.Total == 126 && session.Items.Count == 12 && session.View == "gallery", "Whole catalog paginated beyond 100 images");
            using (var stream = assets.OpenMedia(session.Items[0].Id, "thumb").content)
            using (var thumbnail = Image.FromStream(stream))
                Check(thumbnail.Width <= 360 && thumbnail.Height <= 360, "Tall thumbnails bound both dimensions before decode");
            session.Apply("next"); session.Apply("open:11");
            Check(session.View == "image" && session.Snapshot("running").Index == 23, "Open thumbnail on second page");
            var last = session.Current.Id; session.Apply("next");
            Check(session.Snapshot("running").Index == 24 && session.Current.Id != last, "Viewer crosses page boundary");
            session.Apply("previous"); Check(session.Snapshot("running").Index == 23, "Viewer returns across page boundary");
            session.Apply("back"); Check(session.View == "gallery" && session.Snapshot("running").Index == 12, "Back restores browsing page");
            session.Apply("roots"); Check(session.Roots.Count == 1, "Registered roots available inside headset");
            session.Apply("open:0"); Check(session.View == "explorer" && !session.Items.Any(item => item.Name == "inside.png"), "Explorer lists immediate children");
            var folderIndex = session.Items.ToList().FindIndex(item => item.IsDirectory);
            Check(folderIndex >= 0, "Folder is navigable");
            session.Apply("open:" + folderIndex); Check(session.Items.Count == 1 && session.Items[0].Name == "inside.png", "Enter nested folder");
            session.Apply("open:0"); Check(session.View == "image" && !session.CanNext && !session.CanPrevious, "One image has no misleading next button");
            session.Apply("back"); session.Apply("up"); Check(session.Location == "art", "Parent directory restored");
            session.Apply("gallery"); session.Apply("favorites"); Check(session.Total == 0 && session.Current == null, "Empty favorites is safe");
            var pixels = VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content);
            Check(pixels.Length == 1280 * 800 * 4, "Empty gallery rendering");
            session.Apply("favorites"); session.Apply("sort"); Check(session.Sort == "date", "Sort toggles inside VR");
            session.Apply("roots");
            pixels = VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content);
            SavePreview("roots", pixels);
            session.Apply("open:0"); session.Apply("gallery");
            pixels = VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content, id => assets.OpenMedia(id, "thumb").content);
            SavePreview("gallery", pixels);
            Check(pixels.Length == 1280 * 800 * 4, "Thumbnail gallery renders from authorized catalog streams");
            Check(VrPanelLayout.Hit(session, 50, 180) == "open:0", "Thumbnail hit target");
            Check(!VrGallerySession.IsAction("open:12") && !VrGallerySession.IsAction("open:../secret"), "Bounded slot commands");
            session.Apply("open:0");
            var chosen = session.Current.Id;
            session.Apply("panel");
            Check(session.View == "panel" && !session.CanNext && !session.CanPrevious, "Size options suspend image paging");
            Check(VrPanelLayout.Hit(session, 750, 320) == "sizeUp", "Size controls clickable inside VR");
            session.Apply("sizeUp"); Check(session.WidthMeters == 2.25f, "Panel width is independent of image zoom");
            SavePreview("panel", VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content));
            for (var i = 0; i < 20; i++) { session.Apply("sizeUp"); session.Apply("nearer"); }
            Check(session.WidthMeters == 3 && session.DistanceMeters == .75f, "VR panel size and distance bounded");
            for (var i = 0; i < 20; i++) { session.Apply("sizeDown"); session.Apply("farther"); }
            Check(session.WidthMeters == .75f && session.DistanceMeters == 3, "Opposite size bounds");
            session.Apply("back"); Check(session.View == "image" && session.Current.Id == chosen, "Size options preserve current image");
            SavePreview("viewer", VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content));
            session.Apply("back"); session.Apply("explorer");
            SavePreview("explorer", VrPanelRenderer.Render(session, id => assets.OpenMedia(id, "preview").content, id => assets.OpenMedia(id, "thumb").content));
            if (native)
            {
                Console.WriteLine("Opening synthetic paginated library in SteamVR...");
                using var vr = new AssetVrService(assets);
                await vr.Start(JsonSerializer.Serialize(new AssetVrRequest { Mode = "library", Query = new AssetQuery { RootId = rootId } }));
                vr.Control("open:0"); await WaitView(vr, "image");
                vr.Control("sizeUp"); vr.Control("farther");
                vr.Control("next"); await Task.Delay(100);
                vr.Control("back"); await WaitView(vr, "gallery");
                vr.Control("roots"); await WaitView(vr, "roots");
                vr.Control("open:0"); await WaitView(vr, "explorer");
                await vr.Stop();
                Console.WriteLine("SteamVR catalog smoke passed: gallery, image sequence, roots, explorer and cleanup.");
            }
            Console.WriteLine("VR navigation: missing release coordinates, controller isolation, catalog >100, paging, folders, favorites and thumbnails passed.");
        }
        finally
        {
            SqliteConnection.ClearAllPools();
            var full = Path.GetFullPath(directory);
            if (!full.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase) ||
                !Path.GetFileName(full).StartsWith("XennexVrTests-", StringComparison.Ordinal)) throw new InvalidOperationException("Unexpected test directory.");
            Directory.Delete(full, true);
        }
    }

    private static async Task WaitView(AssetVrService service, string view)
    {
        for (var i = 0; i < 100; i++)
        {
            var state = JsonSerializer.Deserialize<AssetVrState>(service.GetState(), Json);
            if (state.State == "failed") throw new Exception(state.Error);
            if (state.View == view) return;
            await Task.Delay(30);
        }
        throw new Exception("SteamVR view timeout: " + view);
    }

    private static void SavePreview(string name, byte[] rgba)
    {
        var path = Path.Combine(Directory.GetCurrentDirectory(), "bin", "vr-ui");
        Directory.CreateDirectory(path);
        var pixels = (byte[])rgba.Clone();
        for (var i = 0; i < pixels.Length; i += 4) (pixels[i], pixels[i + 2]) = (pixels[i + 2], pixels[i]);
        using var bitmap = new Bitmap(1280, 800, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
        var data = bitmap.LockBits(new Rectangle(0, 0, 1280, 800), System.Drawing.Imaging.ImageLockMode.WriteOnly, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
        try { System.Runtime.InteropServices.Marshal.Copy(pixels, 0, data.Scan0, pixels.Length); }
        finally { bitmap.UnlockBits(data); }
        bitmap.Save(Path.Combine(path, name + ".png"), System.Drawing.Imaging.ImageFormat.Png);
    }
}

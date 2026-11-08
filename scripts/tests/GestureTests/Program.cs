using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using Xennex.Services;
using Xennex.Services.Gestures;

static class Program
{
    static int assertions;
    static void Assert(bool condition, string message) { assertions++; if (!condition) throw new Exception(message); }
    static void Reject(Action action, string message)
    {
        bool rejected = false;
        try { action(); } catch (Exception) { rejected = true; }
        Assert(rejected, message);
    }
    static void Wait(Func<bool> condition)
    {
        for (int i = 0; i < 200; i++) { if (condition()) return; Thread.Sleep(25); }
        throw new Exception("Worker protocol timed out");
    }
    static JsonObject Sample() => JsonNode.Parse("{\"duration\":1,\"frames\":[" +
        "[" + string.Join(",", Enumerable.Repeat("[0.1,0.2,0]", 21)) + "]]}").AsObject();
    static void Main(string[] args)
    {
        string root = Path.Combine(AppContext.BaseDirectory, "fixtures-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var store = new GestureProfileStore(Path.Combine(root, "fresh"));
            var profile = store.Read();
            Assert(profile["gestures"].AsArray().Count == 6, "Default gestures");
            Assert((string)profile["gestures"][2]["action"]["value"] == "win+left", "Default swipe");
            var custom = GestureProfileStore.Binding("custom", "Custom", "pose", "shortcut", "ctrl+m");
            profile["gestures"].AsArray().Add(custom);
            store.Save(profile.ToJsonString());
            string staleUi = store.Read().ToJsonString();
            store.AddSample("custom", Sample());
            store.Save(staleUi);
            Assert(store.Read()["gestures"].AsArray().Last()["samples"].AsArray().Count == 1, "Stale UI lost sample");
            for (int i = 1; i < 8; i++) store.AddSample("custom", Sample());
            Reject(() => store.AddSample("custom", Sample()), "More than 8 samples accepted");
            Assert(store.Read()["gestures"].AsArray().Last()["samples"].AsArray().Count == 8, "Failed write corrupted data");
            store.ClearSamples("custom");
            Assert(store.Read()["gestures"].AsArray().Last()["samples"].AsArray().Count == 0, "Clear samples");
            Assert(File.Exists(store.FilePath + ".bak"), "Atomic write backup");

            profile = store.Read();
            profile["gestures"][0]["action"]["type"] = "shortcut";
            profile["gestures"][0]["action"]["value"] = "ctrl+ctrl";
            Reject(() => store.Save(profile.ToJsonString()), "Duplicate shortcut keys accepted");
            Assert((string)store.Read()["gestures"][0]["action"]["type"] == "pointer", "Invalid save changed disk");
            profile = store.Read();
            profile["gestures"][2]["action"]["type"] = "drag_mouse";
            Reject(() => store.Save(profile.ToJsonString()), "Continuous action accepted for swipe");
            profile = store.Read(); profile["smoothing"] = 9;
            Reject(() => store.Save(profile.ToJsonString()), "Invalid range accepted");

            string oldDir = Path.Combine(root, "legacy");
            Directory.CreateDirectory(oldDir);
            string oldJson = "{\"KEYBOARD:windows+arrowleft\":[" + string.Join(",", Enumerable.Repeat("[0.1,0.2]", 21)) + "]}";
            File.WriteAllText(Path.Combine(oldDir, "gestures.json"), oldJson);
            File.WriteAllText(Path.Combine(oldDir, "swipe_config.json"), "{\"SwipeRight\":\"KEYBOARD:ctrl+right\"}");
            var imported = new GestureProfileStore(oldDir).Read();
            var last = imported["gestures"].AsArray().Last();
            Assert((bool)last["enabled"] == false, "Imported actions must start disabled");
            Assert((string)last["action"]["value"] == "win+left", "Legacy key aliases");
            Assert((string)imported["gestures"][3]["action"]["value"] == "ctrl+right", "Legacy swipe");
            Assert(File.ReadAllText(Path.Combine(oldDir, "gestures.json")) == oldJson, "Original data modified");
            string badDir = Path.Combine(root, "malformed");
            Directory.CreateDirectory(badDir);
            File.WriteAllText(Path.Combine(badDir, "gestures.json"), "{broken");
            var recovered = new GestureProfileStore(badDir).Read();
            Assert(recovered["gestures"].AsArray().Count == 6 && recovered["migrationNotice"] != null, "Malformed legacy blocks feature");
            File.WriteAllText(store.FilePath, "{broken");
            Reject(() => store.Read(), "Corrupt current profile silently replaced");
            Assert(File.ReadAllText(store.FilePath) == "{broken", "Current profile data lost");

            // Real supervisor + fake worker subprocess; no camera or desktop commands.
            if (args.Length != 1) throw new Exception("Pass an isolated Python executable.");
            Environment.SetEnvironmentVariable("XENNEX_GESTURE_PYTHON", Path.GetFullPath(args[0]));
            var service = new HandMotionService();
            try
            {
                var config = JsonNode.Parse(service.GetConfig());
                var gestures = config["gestures"].AsArray();
                if (!gestures.Any(g => (string)g["id"] == "test-custom"))
                    gestures.Add(GestureProfileStore.Binding("test-custom", "Test", "pose", "none"));
                service.SaveConfig(config.ToJsonString());
                service.ClearSamples("test-custom");
                service.Start();
                Wait(() => JsonNode.Parse(service.GetStatus())["message"]?.GetValue<string>() == "Fake camera ready");
                Assert(service.IsRunning, "Worker did not start");
                Assert((bool)JsonNode.Parse(service.GetStatus())["armed"] == false, "Worker starts armed");
                service.SetControl(true);
                Wait(() => (bool)JsonNode.Parse(service.GetStatus())["armed"]);
                service.RecordSample("test-custom");
                Wait(() => JsonNode.Parse(service.GetConfig())["gestures"].AsArray().First(g => (string)g["id"] == "test-custom")["samples"].AsArray().Count == 1);
                Assert((bool)JsonNode.Parse(service.GetStatus())["armed"] == false, "Recording leaves control armed");
                service.Stop();
                Assert(!service.IsRunning, "Stop did not end worker");
                service.Start();
                Wait(() => JsonNode.Parse(service.GetStatus())["message"]?.GetValue<string>() == "Fake camera ready");
                Assert((bool)JsonNode.Parse(service.GetStatus())["armed"] == false, "Restart retained armed state");
            }
            finally { service.Stop(); }
            Console.WriteLine($"PASS: {assertions} profile, migration and supervisor checks.");
        }
        finally
        {
            if (!Path.GetFullPath(root).StartsWith(Path.GetFullPath(AppContext.BaseDirectory), StringComparison.OrdinalIgnoreCase))
                throw new Exception("Unsafe fixture cleanup path");
            Directory.Delete(root, true);
        }
    }
}
namespace Xennex.Services
{
    public static class AppLog { public static void Error(string source, Exception error) { /* Expected rejection tests. */ } }
}

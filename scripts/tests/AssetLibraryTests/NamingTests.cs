using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Xennex.Models.Assets;
using Xennex.Services.Assets;

internal static class NamingTests
{
    private static T Read<T>(string json) => JsonSerializer.Deserialize<T>(json,
        new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;

    private static AssetJob Wait(AssetLibraryService service, string id)
    {
        for (var attempt = 0; attempt < 1000; attempt++)
        {
            var job = Read<AssetJob>(service.GetJob(id));
            if (job.State is "completed" or "failed" or "partial" or "cancelled") return job;
            Thread.Sleep(20);
        }
        throw new Exception("Naming fixture job timed out");
    }

    public static void Run(string directory, Action<bool, string> check)
    {
        var first = Path.Combine(directory, "naming-first");
        var second = Path.Combine(directory, "naming-second");
        var target = Path.Combine(directory, "naming-target");
        foreach (var folder in new[] { first, second, target, Path.Combine(target, "empty"), Path.Combine(target, "denia900") }) Directory.CreateDirectory(folder);
        foreach (var path in new[] { Path.Combine(first, "same.png"), Path.Combine(first, "beta.jpg"),
            Path.Combine(first, "cycle1.png"), Path.Combine(first, "cycle2.png"), Path.Combine(second, "same.png"),
            Path.Combine(target, "same.png"), Path.Combine(target, "denia001.png"), Path.Combine(target, "denia009.jpg"),
            Path.Combine(target, "other999.png") }) File.WriteAllText(path, "fixture-" + Path.GetFileName(path));
        using var service = new AssetLibraryService(Path.Combine(directory, "naming-catalog"));
        string Add(string path)
        {
            using var added = JsonDocument.Parse(service.AddRoot(path));
            check(Wait(service, added.RootElement.GetProperty("jobId").GetString()!).State == "completed", "Naming fixture root indexed");
            return added.RootElement.GetProperty("root").GetProperty("id").GetString()!;
        }
        var aRoot = Add(first); var bRoot = Add(second); var destination = Add(target);
        string Id(string root, string name) => Read<AssetPage>(service.Query(JsonSerializer.Serialize(
            new AssetQuery { RootId = root }))).Items.Single(item => item.Name == name).Id;
        var a = Id(aRoot, "same.png"); var b = Id(bRoot, "same.png"); var beta = Id(aRoot, "beta.jpg");
        AssetFilePlan Plan(AssetFileRequest request) => Read<AssetFilePlan>(service.PlanFileOperation(JsonSerializer.Serialize(request)));
        AssetFileRequest Request(string type, params string[] ids) => new() { Type = type, AssetIds = ids.ToList(), DestinationRootId = destination };
        void Apply(AssetFilePlan plan) => check(Wait(service, service.ExecuteFileOperation(plan.Id)).State == "completed", "Naming fixture operation completed");

        var automatic = Plan(Request("copy", a, b));
        check(automatic.Items[0].DestinationPath.EndsWith("same (2).png") && automatic.Items[1].DestinationPath.EndsWith("same (3).png"),
            "Automatic collision names are reserved across the entire batch");
        var ask = Request("move", a, b); ask.ConflictPolicy = "ask";
        var unresolved = Plan(ask);
        check(!unresolved.CanExecute && unresolved.Items.All(item => item.Conflict), "Unresolved disk conflicts block confirmation");
        try { service.ExecuteFileOperation(unresolved.Id); throw new Exception("Unresolved plan executed"); }
        catch (InvalidOperationException) { check(true, "Unresolved plans cannot be taken for execution"); }
        ask.DestinationFolder = "empty";
        var internalCollision = Plan(ask);
        check(internalCollision.Items.Count(item => item.Conflict) == 1 && !internalCollision.CanExecute, "Same names inside a batch are detected in an empty destination");
        ask.DestinationFolder = "";
        ask.Choices.Add(new AssetFileChoice { AssetId = a, Name = "custom.png" });
        ask.Choices.Add(new AssetFileChoice { AssetId = b, Action = "skip" });
        service.Edit(JsonSerializer.Serialize(new AssetEdit { Id = a, AddTag = "Keep", Notes = "Preserve" }));
        var resolved = Plan(ask);
        check(resolved.CanExecute && resolved.Items[1].Skipped, "Individual rename and skip resolve a batch");
        Apply(resolved);
        check(File.Exists(Path.Combine(target, "custom.png")) && !File.Exists(Path.Combine(first, "same.png")) &&
            File.Exists(Path.Combine(second, "same.png")) && File.ReadAllText(Path.Combine(target, "same.png")) == "fixture-same.png",
            "Move renames one file, keeps skipped source and never overwrites existing destination");

        var singleConflict = Request("rename", a); singleConflict.NewName = "same.png";
        check(Path.GetFileName(Plan(singleConflict).Items.Single().DestinationPath) == "same (2).png",
            "Single rename honors the automatic conflict policy");
        singleConflict.ConflictPolicy = "skip";
        check(!Plan(singleConflict).CanExecute, "Single rename honors the skip conflict policy");

        var numbered = Request("copy", b, beta); numbered.ConflictPolicy = "ask";
        numbered.Naming = new AssetNamingRule { BaseName = "denia", Digits = 3 };
        var sequence = Plan(numbered);
        check(sequence.StartNumber == 10 && Path.GetFileName(sequence.Items[0].DestinationPath) == "denia010.png" &&
            Path.GetFileName(sequence.Items[1].DestinationPath) == "denia011.jpg", "Sequence continues from largest matching number across extensions and preserves supplied order");
        numbered.Choices.Add(new AssetFileChoice { AssetId = b, Action = "skip" });
        check(Path.GetFileName(Plan(numbered).Items[1].DestinationPath) == "denia010.jpg", "Explicitly skipped items do not consume a number");
        numbered.Choices.Clear();
        Apply(sequence);
        numbered.Naming.Scope = "conflicts";
        var conflictsOnly = Plan(numbered);
        check(Path.GetFileName(conflictsOnly.Items[0].DestinationPath) == "denia012.png" &&
            Path.GetFileName(conflictsOnly.Items[1].DestinationPath) == "beta.jpg", "Rule can rename only conflicting names");
        numbered.Naming = new AssetNamingRule { BaseName = "denia", Pattern = "{base}_{number}", AutoContinue = false, StartNumber = 0, Digits = 2 };
        check(Path.GetFileName(Plan(numbered).Items[0].DestinationPath) == "denia_00.png", "Manual start, literal separator and padding are preserved");
        foreach (var pattern in new[] { "../{base}{number}", "{base}{number}{unknown}", "{base}", "{number}{number}{base}" })
        {
            numbered.Naming.Pattern = pattern;
            try { Plan(numbered); throw new Exception("Invalid template accepted"); }
            catch (ArgumentException) { check(true, "Unsafe or ambiguous template rejected: " + pattern); }
        }
        var skipped = Request("copy", b); skipped.ConflictPolicy = "skip";
        var allSkipped = Plan(skipped);
        check(!allSkipped.CanExecute && allSkipped.Items.Single().Skipped, "Skipping all collisions produces no executable plan");
        var create = Request("createFolder", a); create.NewName = "new-folder";
        check(Plan(create).Items.Count == 1, "Create folder does not accidentally act on a retained selection");

        var rename = Request("rename", b, a); rename.ConflictPolicy = "ask";
        rename.Naming = new AssetNamingRule { BaseName = "ren", AutoContinue = false, StartNumber = 50, Digits = 2 };
        Apply(Plan(rename));
        check(File.Exists(Path.Combine(second, "ren50.png")) && File.Exists(Path.Combine(target, "ren51.png")), "Batch rename follows chosen order in each original folder");
        check(Read<AssetItem>(service.GetDetails(a)).Tags.Contains("Keep") && Read<AssetItem>(service.GetDetails(a)).Notes == "Preserve",
            "Catalog identity, tags and notes survive batch naming and moves");
        var history = Read<AssetOperation[]>(service.GetRecentFileOperations()).First(item => item.AssetId == b && item.Kind == "rename");
        service.UndoFileOperation(history.Id).GetAwaiter().GetResult();
        check(File.Exists(Path.Combine(second, "same.png")), "One batch rename can be undone through existing journal");

        var cycles = Request("rename", Id(aRoot, "cycle1.png"), Id(aRoot, "cycle2.png")); cycles.ConflictPolicy = "ask";
        cycles.Choices.Add(new AssetFileChoice { AssetId = cycles.AssetIds[0], Name = "cycle2.png" });
        cycles.Choices.Add(new AssetFileChoice { AssetId = cycles.AssetIds[1], Name = "cycle1.png" });
        check(!Plan(cycles).CanExecute, "Occupied source names cannot be cyclically swapped");
        var race = Request("move", beta, b); race.ConflictPolicy = "ask";
        race.Choices.Add(new AssetFileChoice { AssetId = beta, Name = "race-first.jpg" });
        race.Choices.Add(new AssetFileChoice { AssetId = b, Name = "race-last.png" });
        var stale = Plan(race);
        File.WriteAllText(Path.Combine(target, "race-last.png"), "external-change");
        check(Wait(service, service.ExecuteFileOperation(stale.Id)).State == "failed", "New destination collision invalidates execution");
        check(File.Exists(Path.Combine(first, "beta.jpg")) && !File.Exists(Path.Combine(target, "race-first.jpg")),
            "Batch preflight catches a late conflict before moving the first file");
    }
}

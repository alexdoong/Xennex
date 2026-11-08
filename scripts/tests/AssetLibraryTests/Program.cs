using System;
using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using Microsoft.Data.Sqlite;
using Xennex.Models.Assets;
using Xennex.Services.Assets;

if (args.Length == 2 && args[0] == "--prepare-native")
{
    var target = Path.GetFullPath(args[1]);
    var expected = Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "bin")) + Path.DirectorySeparatorChar;
    if (!target.StartsWith(expected, StringComparison.OrdinalIgnoreCase) ||
        !Path.GetFileName(target).StartsWith("AssetNativeSmoke-", StringComparison.Ordinal))
        throw new ArgumentException("Native test target must be a dedicated bin/AssetNativeSmoke-* directory.");
    var fixture = Path.Combine(target, "fixture-art");
    Directory.CreateDirectory(fixture);
    File.WriteAllBytes(Path.Combine(fixture, "native-art.png"),
        Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1EAAAAASUVORK5CYII="));
    using var prepared = new AssetLibraryService(Path.Combine(target, "Data", "assets"));
    var added = JsonDocument.Parse(prepared.AddRoot(fixture)).RootElement;
    var id = added.GetProperty("jobId").GetString()!;
    for (var attempt = 0; attempt < 100; attempt++)
    {
        if (JsonDocument.Parse(prepared.GetJob(id)).RootElement.GetProperty("state").GetString() == "completed")
        {
            Console.WriteLine("Native asset fixture prepared");
            return;
        }
        Thread.Sleep(50);
    }
    throw new Exception("Native asset fixture timed out");
}

if (args.Length == 1 && args[0] == "--benchmark")
{
    var target = Path.Combine(Path.GetTempPath(), "XennexAssetBench-" + Guid.NewGuid().ToString("N"));
    var originalsPath = Path.Combine(target, "originals");
    Directory.CreateDirectory(originalsPath);
    try
    {
        var pixel = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1EAAAAASUVORK5CYII=");
        for (var index = 0; index < 10000; index++)
        {
            var folder = Path.Combine(originalsPath, "grupo-" + index / 1000);
            Directory.CreateDirectory(folder);
            var path = Path.Combine(folder, $"arte-{index:D5}" + (index % 10 == 0 ? ".png" : ".txt"));
            File.WriteAllBytes(path, index % 10 == 0 ? pixel : new byte[] { 65 });
        }
        using var library = new AssetLibraryService(Path.Combine(target, "catalog"));
        var timer = Stopwatch.StartNew();
        var added = JsonDocument.Parse(library.AddRoot(originalsPath)).RootElement;
        var jobId = added.GetProperty("jobId").GetString()!;
        while (timer.Elapsed < TimeSpan.FromMinutes(2))
        {
            var job = JsonDocument.Parse(library.GetJob(jobId)).RootElement;
            var state = job.GetProperty("state").GetString();
            if (state == "completed") break;
            if (state is "failed" or "partial") throw new Exception("Benchmark scan failed: " + state);
            Thread.Sleep(100);
        }
        if (JsonDocument.Parse(library.GetJob(jobId)).RootElement.GetProperty("state").GetString() != "completed")
            throw new Exception("Benchmark scan timed out");
        Console.WriteLine($"10k mixed files indexed in {timer.Elapsed.TotalSeconds:F2}s");
        var times = new double[50];
        var query = JsonSerializer.Serialize(new AssetQuery { RootId = added.GetProperty("root").GetProperty("id").GetString()!,
            Search = "arte-09", IncludeDescendants = true, ImagesOnly = true });
        for (var index = 0; index < times.Length; index++)
        {
            timer.Restart();
            library.Query(query);
            times[index] = timer.Elapsed.TotalMilliseconds;
        }
        Array.Sort(times);
        Console.WriteLine($"Search p95 {times[47]:F1} ms; private memory {Process.GetCurrentProcess().PrivateMemorySize64 / 1048576} MiB");
    }
    finally
    {
        SqliteConnection.ClearAllPools();
        var full = Path.GetFullPath(target);
        if (full.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase) &&
            Path.GetFileName(full).StartsWith("XennexAssetBench-", StringComparison.Ordinal) && Directory.Exists(full))
            Directory.Delete(full, true);
    }
    return;
}

var directory = Path.Combine(Path.GetTempPath(), "XennexAssetTests-" + Guid.NewGuid().ToString("N"));
var catalog = Path.Combine(directory, "catalog");
var originals = Path.Combine(directory, "originals");
Directory.CreateDirectory(originals);
var checks = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); checks++; }
T Decode<T>(string json) => JsonSerializer.Deserialize<T>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
void AwaitIndex(AssetLibraryService service, string id)
{
    for (var attempt = 0; attempt < 100; attempt++)
    {
        var job = Decode<AssetJob>(service.GetJob(id));
        if (job.State == "completed") return;
        if (job.State is "failed" or "partial" or "cancelled") throw new Exception("Index: " + job.State + " " + job.Error);
        Thread.Sleep(50);
    }
    throw new Exception("Index timed out");
}
AssetPage Query(AssetLibraryService service, AssetQuery query) => Decode<AssetPage>(service.Query(JsonSerializer.Serialize(query)));
try
{
    Directory.CreateDirectory(Path.Combine(originals, "Personagens"));
    var file = Path.Combine(originals, "Personagens", "Denia.png");
    var basePng = Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jN1EAAAAASUVORK5CYII=");
    var comfyPrompt = """
        {"1":{"class_type":"CLIPTextEncode","inputs":{"text":"Denia, ComfySeed4242, blue hair"}},
         "2":{"class_type":"CLIPTextEncode","inputs":{"text":"blurry, bad anatomy"}},
         "3":{"class_type":"KSampler","inputs":{"positive":["1",0],"negative":["2",0],"seed":42}}}
        """;
    var data = Encoding.UTF8.GetBytes("prompt\0" + comfyPrompt);
    var chunk = new byte[data.Length + 12];
    BinaryPrimitives.WriteInt32BigEndian(chunk.AsSpan(0, 4), data.Length);
    Encoding.ASCII.GetBytes("tEXt").CopyTo(chunk, 4);
    data.CopyTo(chunk, 8);
    uint crc = 0xffffffff;
    foreach (var octet in chunk.AsSpan(4, data.Length + 4))
    {
        crc ^= octet;
        for (var bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ ((crc & 1) != 0 ? 0xedb88320u : 0u);
    }
    BinaryPrimitives.WriteUInt32BigEndian(chunk.AsSpan(data.Length + 8), ~crc);
    File.WriteAllBytes(file, basePng[..^12].Concat(chunk).Concat(basePng[^12..]).ToArray());
    File.WriteAllText(Path.Combine(originals, "notas.txt"), "preservar");
    string rootId, assetId;
    using (var service = new AssetLibraryService(catalog))
    {
        var added = JsonDocument.Parse(service.AddRoot(originals)).RootElement;
        rootId = added.GetProperty("root").GetProperty("id").GetString()!;
        AwaitIndex(service, added.GetProperty("jobId").GetString()!);
        var explorer = Query(service, new AssetQuery { RootId = rootId });
        Check(explorer.Total == 2 && explorer.Items.Any(item => item.IsDirectory), "Explorer contains folder and text");
        var destinationFolders = Query(service, new AssetQuery { RootId = rootId, DirectoriesOnly = true });
        Check(destinationFolders.Total == 1 && destinationFolders.Items.Single().IsDirectory, "Destination picker lists folders only");
        var gallery = Query(service, new AssetQuery { RootId = rootId, ImagesOnly = true, IncludeDescendants = true });
        Check(gallery.Total == 1 && gallery.Items[0].Name == "Denia.png", "Gallery finds nested image");
        Check(gallery.Items[0].Width == 1 && gallery.Items[0].Height == 1, "Image dimensions indexed");
        Check(gallery.Items[0].HasMetadata && gallery.Items[0].Metadata == "", "Gallery marks metadata without transferring its full text");
        Check(Query(service, new AssetQuery { RootId = rootId, MetadataOnly = true, IncludeDescendants = true }).Total == 1,
            "Metadata filter finds indexed images across folders");
        Check(Decode<AssetItem>(service.GetDetails(gallery.Items[0].Id)).Metadata.Contains("ComfySeed4242"), "PNG generation text indexed");
        AwaitIndex(service, service.StartIndex(rootId));
        Check(Decode<AssetItem>(service.GetDetails(gallery.Items[0].Id)).Metadata.Contains("ComfySeed4242"),
            "Unchanged rescan preserves cached metadata without loading it per file");
        Check(Query(service, new AssetQuery { RootId = rootId, Search = "ComfySeed4242", IncludeDescendants = true }).Total == 1, "Metadata searchable");
        var smart = new AssetQuery { RootId = rootId, IncludeDescendants = true, MinWidth = 1,
            Rule = new AssetRule { Mode = "all", Children = new()
            {
                new AssetRule { Mode = "predicate", Field = "metadata", Comparison = "contains", Value = "ComfySeed4242" },
                new AssetRule { Mode = "not", Children = new() { new AssetRule { Mode = "predicate", Field = "name", Comparison = "contains", Value = "outra" } } }
            } } };
        Check(Query(service, smart).Total == 1, "Smart query ALL and NOT");
        Check(Query(service, new AssetQuery { Rule = new AssetRule { Mode = "any", Children = new()
        {
            new AssetRule { Mode = "predicate", Field = "name", Comparison = "contains", Value = "Denia" },
            new AssetRule { Mode = "predicate", Field = "name", Comparison = "contains", Value = "inexistente" }
        } } }).Total == 1, "Smart query ANY");
        var savedQuery = Decode<SavedAssetQuery>(service.SaveQuery("Comfy", JsonSerializer.Serialize(smart)));
        Check(savedQuery.Query.MinWidth == 1 && Decode<SavedAssetQuery[]>(service.GetSavedQueries()).Length == 1, "Saved query persists");
        assetId = gallery.Items[0].Id;
        Check(service.ResolvePath(assetId) == file, "Opaque id resolves inside root");
        Check(service.MediaUrl(assetId, "thumb").Contains(assetId), "Media URL uses opaque id");
        var edit = service.Edit(JsonSerializer.Serialize(new AssetEdit { Id = assetId, Favorite = true, AddTag = "Personagem ✨", Notes = "Build A" }));
        Check(Decode<AssetItem>(edit).Tags.Contains("Personagem ✨"), "Unicode tag persists");
        var filtered = Query(service, new AssetQuery { RootId = rootId, Tag = "Personagem ✨", FavoritesOnly = true, IncludeDescendants = true });
        Check(filtered.Total == 1, "Tag and favorite filter");
        service.Edit(JsonSerializer.Serialize(new AssetEdit { Id = assetId, AddTag = "Denia" }));
        var overview = Decode<AssetTagOverviewPage>(service.GetTagOverview("{\"source\":\"all\",\"limit\":100}"));
        Check(overview.Items.Any(item => item.Term == "Denia" && item.Manual == 1 && item.Positive == 1),
            "Tag overview combines manual and positive sources");
        Check(overview.Items.Any(item => item.Term == "blurry" && item.Negative == 1 && item.Positive == 0),
            "Tag overview separates negative prompt terms");
        Check(Query(service, new AssetQuery { RootId = rootId, ImagesOnly = true, IncludeDescendants = true,
            Term = "blurry", TermSource = "negative" }).Total == 1, "Negative prompt term filters gallery");
        Check(Query(service, new AssetQuery { RootId = rootId, ImagesOnly = true, IncludeDescendants = true,
            Term = "blurry", TermSource = "positive" }).Total == 0, "Prompt source filter does not mix polarities");
        service.EditBatch(JsonSerializer.Serialize(new AssetBatchEdit { Ids = new() { assetId }, AddTag = "Lote" }));
        Check(Decode<AssetItem>(service.GetDetails(assetId)).Tags.Contains("Lote"), "Batch edit uses shared catalog");
        var collection = Decode<AssetCollection>(service.AddCollection("Variações"));
        service.SetCollectionItem(collection.Id, assetId, true);
        Check(Query(service, new AssetQuery { CollectionId = collection.Id, IncludeDescendants = true }).Total == 1, "Collection stores reference");
        var backup = Path.Combine(directory, "backup.db");
        service.Backup(backup);
        Check(File.Exists(backup) && new FileInfo(backup).Length > 0, "SQLite backup created");
        var restoreDir = Path.Combine(directory, "restore");
        Directory.CreateDirectory(restoreDir);
        File.Copy(backup, Path.Combine(restoreDir, "library.db"));
        using (var restored = new AssetLibraryService(restoreDir))
        {
            AwaitIndex(restored, restored.StartIndex(rootId));
            Check(Decode<AssetItem>(restored.GetDetails(assetId)).Tags.Contains("Lote"), "Backup opens with tags intact");
        }

        string Apply(AssetFileRequest request)
        {
            var plan = Decode<AssetFilePlan>(service.PlanFileOperation(JsonSerializer.Serialize(request)));
            AwaitIndex(service, service.ExecuteFileOperation(plan.Id));
            return plan.Items[0].DestinationPath;
        }
        Apply(new AssetFileRequest { Type = "createFolder", DestinationRootId = rootId, NewName = "Exportações" });
        Check(Directory.Exists(Path.Combine(originals, "Exportações")), "Create folder");
        var copied = Apply(new AssetFileRequest { Type = "copy", AssetIds = new() { assetId }, DestinationRootId = rootId, DestinationFolder = "Exportações" });
        Check(File.Exists(copied) && File.Exists(file), "Copy preserves original");
        var copy = Query(service, new AssetQuery { RootId = rootId, Folder = "Exportações", ImagesOnly = true }).Items.Single();
        Check(copy.Id != assetId, "Copy gets separate identity");
        service.EditBatch(JsonSerializer.Serialize(new AssetBatchEdit { Ids = new() { assetId, copy.Id }, AddTag = "Seleção", CollectionId = collection.Id, CollectionPresent = true }));
        Check(Decode<AssetItem>(service.GetDetails(assetId)).Tags.Contains("Seleção") &&
              Decode<AssetItem>(service.GetDetails(copy.Id)).Tags.Contains("Seleção"), "Batch tag reaches both images");
        Check(Query(service, new AssetQuery { CollectionId = collection.Id, IncludeDescendants = true }).Total == 2, "Batch adds both images to collection");
        try
        {
            service.EditBatch(JsonSerializer.Serialize(new AssetBatchEdit { Ids = new() { assetId, new string('f', 32) }, AddTag = "Não aplicar", CollectionId = collection.Id, CollectionPresent = false }));
            throw new Exception("Unknown batch item accepted");
        }
        catch (ArgumentException) { }
        Check(!Decode<AssetItem>(service.GetDetails(assetId)).Tags.Contains("Não aplicar") &&
              Query(service, new AssetQuery { CollectionId = collection.Id, IncludeDescendants = true }).Total == 2,
              "Invalid batch rolls back tag and collection changes");
        service.EditBatch(JsonSerializer.Serialize(new AssetBatchEdit { Ids = new() { assetId, copy.Id }, RemoveTag = "Seleção", CollectionId = collection.Id, CollectionPresent = false }));
        Check(!Decode<AssetItem>(service.GetDetails(copy.Id)).Tags.Contains("Seleção") &&
              Query(service, new AssetQuery { CollectionId = collection.Id, IncludeDescendants = true }).Total == 0,
              "Batch removes tag and collection membership");
        var duplicate = Apply(new AssetFileRequest { Type = "copy", AssetIds = new() { assetId }, DestinationRootId = rootId, DestinationFolder = "Exportações" });
        Check(Path.GetFileName(duplicate) == "Denia (2).png" && File.Exists(duplicate), "Name collision creates separate copy");
        Apply(new AssetFileRequest { Type = "rename", AssetIds = new() { copy.Id }, NewName = "Variação.png" });
        Check(File.Exists(Path.Combine(originals, "Exportações", "Variação.png")), "Rename on disk");
        Check(Decode<AssetItem>(service.GetDetails(copy.Id)).Name == "Variação.png", "Rename preserves identity");
        Apply(new AssetFileRequest { Type = "move", AssetIds = new() { copy.Id }, DestinationRootId = rootId });
        Check(File.Exists(Path.Combine(originals, "Variação.png")), "Move to root");
        Check(Decode<AssetItem>(service.GetDetails(copy.Id)).RelativePath == "Variação.png", "Move preserves identity");
        var moveRecord = Decode<AssetOperation[]>(service.GetRecentFileOperations()).First(value => value.Kind == "move" && value.AssetId == copy.Id);
        service.UndoFileOperation(moveRecord.Id).GetAwaiter().GetResult();
        Check(File.Exists(Path.Combine(originals, "Exportações", "Variação.png")), "Undo returns file to original folder");
        Check(Decode<AssetItem>(service.GetDetails(copy.Id)).RelativePath == "Exportações/Variação.png", "Undo preserves identity");
        Apply(new AssetFileRequest { Type = "move", AssetIds = new() { copy.Id }, DestinationRootId = rootId });
        var folderAsset = Query(service, new AssetQuery { RootId = rootId }).Items.Single(item => item.Name == "Personagens");
        Apply(new AssetFileRequest { Type = "rename", AssetIds = new() { folderAsset.Id }, NewName = "Figuras" });
        file = Path.Combine(originals, "Figuras", "Denia.png");
        Check(File.Exists(file), "Folder renamed on disk");
        Check(Decode<AssetItem>(service.GetDetails(assetId)).RelativePath == "Figuras/Denia.png", "Folder rename preserves child identity");
        var copiedFolder = Apply(new AssetFileRequest { Type = "copy", AssetIds = new() { folderAsset.Id }, DestinationRootId = rootId });
        Check(File.Exists(Path.Combine(copiedFolder, "Denia.png")), "Folder copy includes nested art");
        try { service.PlanFileOperation(JsonSerializer.Serialize(new AssetFileRequest { Type = "createFolder", DestinationRootId = rootId, DestinationFolder = "../outside", NewName = "bad" })); throw new Exception("Traversal accepted"); }
        catch (ArgumentException) { checks++; }
        try { service.PlanFileOperation(JsonSerializer.Serialize(new AssetFileRequest { Type = "createFolder", DestinationRootId = rootId, NewName = "CON" })); throw new Exception("Reserved name accepted"); }
        catch (ArgumentException) { checks++; }
        try { service.PlanFileOperation(JsonSerializer.Serialize(new AssetFileRequest { Type = "createFolder", DestinationRootId = rootId, NewName = "COM9.txt" })); throw new Exception("Reserved port name accepted"); }
        catch (ArgumentException) { checks++; }
        try { service.PlanFileOperation(JsonSerializer.Serialize(new AssetFileRequest { Type = "copy", AssetIds = new() { folderAsset.Id, assetId }, DestinationRootId = rootId })); throw new Exception("Nested selection accepted"); }
        catch (ArgumentException) { checks++; }
        try { Query(service, new AssetQuery { Rule = new AssetRule { Mode = "predicate", Field = "sql", Comparison = "eq", Value = "1" } }); throw new Exception("Unknown rule accepted"); }
        catch (ArgumentException) { checks++; }
        service.SetIndexPaused(true);
        var pausedJob = service.StartIndex(rootId);
        Thread.Sleep(150);
        Check(Decode<AssetJob>(service.GetJob(pausedJob)).Seen == 0, "Paused scan does not consume directory");
        service.SetIndexPaused(false);
        AwaitIndex(service, pausedJob);
    }
    string recoveryId;
    using (var reloaded = new AssetLibraryService(catalog))
    {
        AwaitIndex(reloaded, reloaded.StartIndex(rootId));
        Check(Decode<AssetItem>(reloaded.GetDetails(assetId)).Notes == "Build A", "Catalog survives restart");
        Check(Decode<AssetRoot[]>(reloaded.GetRoots()).Single().Id == rootId, "Root identity survives restart");
        File.WriteAllText(Path.Combine(originals, "recover.txt"), "recovery fixture");
        AwaitIndex(reloaded, reloaded.StartIndex(rootId));
        recoveryId = Query(reloaded, new AssetQuery { RootId = rootId }).Items.Single(item => item.Name == "recover.txt").Id;
    }
    var recoverySource = Path.Combine(originals, "recover.txt");
    var recoveryTarget = Path.Combine(originals, "recovered.txt");
    var recoverySize = new FileInfo(recoverySource).Length;
    var recoveryModified = new DateTimeOffset(File.GetLastWriteTimeUtc(recoverySource)).ToUnixTimeMilliseconds();
    File.Move(recoverySource, recoveryTarget);
    using (var connection = new SqliteConnection($"Data Source={Path.Combine(catalog, "library.db")}"))
    {
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "INSERT INTO file_operations(id,kind,asset_id,source_root,destination_root,source_relative,destination_relative,state,created_utc,size,modified_utc) VALUES(@id,'rename',@asset,@root,@root,'recover.txt','recovered.txt','running',@created,@size,@modified)";
        command.Parameters.AddWithValue("@id", Guid.NewGuid().ToString("N"));
        command.Parameters.AddWithValue("@asset", recoveryId);
        command.Parameters.AddWithValue("@root", rootId);
        command.Parameters.AddWithValue("@created", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
        command.Parameters.AddWithValue("@size", recoverySize);
        command.Parameters.AddWithValue("@modified", recoveryModified);
        command.ExecuteNonQuery();
    }
    using (var recovered = new AssetLibraryService(catalog))
    {
        AwaitIndex(recovered, recovered.StartIndex(rootId));
        Check(Decode<AssetItem>(recovered.GetDetails(recoveryId)).RelativePath == "recovered.txt", "Interrupted rename preserves identity on restart");
    }
    var relocated = Path.Combine(directory, "relocated");
    Directory.Move(originals, relocated);
    file = Path.Combine(relocated, "Figuras", "Denia.png");
    using (var offline = new AssetLibraryService(catalog))
    {
        Check(!Decode<AssetRoot[]>(offline.GetRoots()).Single().Online, "Offline root is retained");
        var preview = Decode<AssetRelinkPlan>(offline.PlanRelink(rootId, relocated));
        Check(preview.Matched > 0 && preview.Missing == 0, "Relink previews relative matches");
        AwaitIndex(offline, offline.ConfirmRelink(preview.Id));
        Check(offline.ResolvePath(assetId) == file, "Relink preserves stable asset id");
        Check(Decode<AssetItem>(offline.GetDetails(assetId)).Tags.Contains("Lote"), "Relink preserves tags");
    }
    Check(File.Exists(file), "Original image preserved");
    NamingTests.Run(directory, Check);
    Console.WriteLine($"AssetLibraryTests: {checks} checks passed");
}
finally
{
    SqliteConnection.ClearAllPools();
    var full = Path.GetFullPath(directory);
    if (full.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase) &&
        Path.GetFileName(full).StartsWith("XennexAssetTests-", StringComparison.Ordinal) && Directory.Exists(full))
        Directory.Delete(full, true);
}

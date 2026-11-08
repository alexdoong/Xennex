using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media.Imaging;
using Xennex.Models.Assets;
using Xennex.Services.Assets.Metadata;

namespace Xennex.Services.Assets;

public sealed class AssetLibraryService : IDisposable
{
    private readonly AssetStore store;
    private readonly AssetFileService files;
    private readonly string dataDirectory;
    private readonly string cacheDirectory;
    private readonly ConcurrentDictionary<string, AssetJob> jobs = new();
    private readonly ConcurrentDictionary<string, AssetRelinkPlan> relinkPlans = new();
    private readonly ConcurrentDictionary<string, CancellationTokenSource> cancellations = new();
    private readonly Dictionary<string, FileSystemWatcher> watchers = new();
    private readonly Dictionary<string, Timer> debounce = new();
    private readonly object watcherGate = new();
    private readonly object cacheGate = new();
    private readonly SemaphoreSlim scanGate = new(1, 1);
    private volatile bool paused;
    private int thumbnailsWritten;
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
    private static readonly HashSet<string> Images = new(StringComparer.OrdinalIgnoreCase) { ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif" };

    public AssetLibraryService(string directory = null)
    {
        directory ??= Path.Combine(AppContext.BaseDirectory, "Data", "assets");
        dataDirectory = Path.GetFullPath(directory);
        store = new AssetStore(directory);
        files = new AssetFileService(store, ResolveEntryPath);
        cacheDirectory = Path.Combine(directory, "cache");
        Directory.CreateDirectory(cacheDirectory);
        foreach (var root in store.Roots()) if (root.Online) { Watch(root); StartIndex(root.Id); }
    }

    private static string Serialize(object value) => JsonSerializer.Serialize(value, Json);

    public string GetRoots() => Serialize(store.Roots());
    public bool IsIndexPaused() => paused;
    public void SetIndexPaused(bool value) => paused = value;
    public string GetCollections() => Serialize(store.Collections());
    public string GetSavedQueries() => Serialize(store.SavedQueries());
    public string GetTags() => Serialize(store.AllTags());
    public string GetTagOverview(string json)
    {
        if (json == null || json.Length > 512) throw new ArgumentException("Consulta de tags inválida.");
        var query = JsonSerializer.Deserialize<AssetTagOverviewQuery>(json, Json) ?? throw new ArgumentException("Consulta de tags inválida.");
        if (query.Search?.Length > 100 || query.Source is not ("all" or "manual" or "positive" or "negative"))
            throw new ArgumentException("Filtro de tags inválido.");
        query.Offset = Math.Max(0, query.Offset);
        query.Limit = Math.Clamp(query.Limit, 1, 200);
        return Serialize(store.TagOverview(query));
    }
    public string GetJob(string id)
    {
        if (!jobs.TryGetValue(id, out var job)) return Serialize(new AssetJob { Id = id, State = "missing" });
        lock (job) return Serialize(job);
    }
    public string GetRecentFileOperations() => Serialize(files.Recent());
    public System.Threading.Tasks.Task UndoFileOperation(string id) => System.Threading.Tasks.Task.Run(() =>
    {
        files.Undo(id);
        foreach (var root in store.Roots()) if (root.Online) StartIndex(root.Id);
    });

    public string AddRoot(string path)
    {
        var full = ValidateRootPath(path);
        var root = store.AddRoot(full);
        Watch(root);
        return Serialize(new { root, jobId = StartIndex(root.Id) });
    }

    private string ValidateRootPath(string path)
    {
        var full = Path.GetFullPath(path ?? "");
        if (!string.Equals(Path.GetPathRoot(full), full, StringComparison.OrdinalIgnoreCase))
            full = full.TrimEnd(Path.DirectorySeparatorChar);
        if (!Directory.Exists(full)) throw new DirectoryNotFoundException("A pasta não está disponível.");
        var prefix = Path.EndsInDirectorySeparator(full) ? full : full + Path.DirectorySeparatorChar;
        if (dataDirectory.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(full, dataDirectory, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Escolha uma pasta fora dos dados internos do Xennex.");
        AssetPathPolicy.ValidateDirectoryAncestors(full);
        return full;
    }

    public string PlanRelink(string rootId, string newPath)
    {
        var root = store.Root(rootId) ?? throw new ArgumentException("Pasta desconhecida.");
        var full = ValidateRootPath(newPath);
        if (store.Roots().Any(item => item.Id != rootId && string.Equals(item.Path, full, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("Esta pasta já está cadastrada.");
        var paths = store.RelativePaths(rootId);
        var matched = 0;
        foreach (var relative in paths)
        {
            var candidate = Path.GetFullPath(Path.Combine(full, relative.Replace('/', Path.DirectorySeparatorChar)));
            if (!candidate.StartsWith(full + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue;
            if (!File.Exists(candidate) && !Directory.Exists(candidate)) continue;
            if ((File.GetAttributes(candidate) & FileAttributes.ReparsePoint) == 0) matched++;
        }
        var plan = new AssetRelinkPlan { Id = Guid.NewGuid().ToString("N"), RootId = rootId,
            OldPath = root.Path, NewPath = full, Matched = matched, Missing = paths.Count - matched,
            ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(5).ToUnixTimeMilliseconds() };
        relinkPlans[plan.Id] = plan;
        return Serialize(plan);
    }

    public string ConfirmRelink(string planId)
    {
        if (!relinkPlans.TryRemove(planId, out var plan) || plan.ExpiresUtc < DateTimeOffset.UtcNow.ToUnixTimeMilliseconds())
            throw new InvalidOperationException("Prévia expirada. Escolha a pasta novamente.");
        ValidateRootPath(plan.NewPath);
        var root = store.Root(plan.RootId) ?? throw new ArgumentException("Pasta desconhecida.");
        if (!string.Equals(root.Path, plan.OldPath, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("A pasta cadastrada mudou desde a prévia.");
        lock (watcherGate)
        {
            if (watchers.Remove(plan.RootId, out var watcher)) watcher.Dispose();
            if (debounce.Remove(plan.RootId, out var timer)) timer.Dispose();
        }
        store.RelinkRoot(plan.RootId, plan.NewPath);
        Watch(store.Root(plan.RootId));
        return StartIndex(plan.RootId);
    }

    public string Query(string json)
    {
        if (json == null || json.Length > 8192) throw new ArgumentException("Consulta inválida.");
        var query = JsonSerializer.Deserialize<AssetQuery>(json, Json) ?? throw new ArgumentException("Consulta inválida.");
        if (query.Search?.Length > 200 || query.Folder?.Length > 1024 || query.Tag?.Length > 80 ||
            query.Term?.Length > 100 || query.TermSource is not ("all" or "manual" or "positive" or "negative"))
            throw new ArgumentException("Filtro muito longo ou origem da tag inválida.");
        if (new[] { query.MinWidth, query.MinHeight, query.MaxWidth, query.MaxHeight }.Any(value => value is < 0 or > 100000))
            throw new ArgumentException("Dimensão inválida.");
        query.Limit = Math.Clamp(query.Limit, 1, 200);
        query.Offset = Math.Max(0, query.Offset);
        return Serialize(store.Query(query));
    }

    public string GetDetails(string id) => Serialize(store.Asset(id) ?? throw new ArgumentException("Arquivo desconhecido."));

    public string Edit(string json)
    {
        if (json == null || json.Length > 12000) throw new ArgumentException("Edição inválida.");
        var edit = JsonSerializer.Deserialize<AssetEdit>(json, Json) ?? throw new ArgumentException("Edição inválida.");
        if (edit.Notes?.Length > 8000) throw new ArgumentException("Nota muito longa.");
        var tag = edit.AddTag?.Trim();
        if (tag?.Length > 80 || edit.RemoveTag?.Length > 80) throw new ArgumentException("Tag muito longa.");
        if (tag != null && tag.Length == 0) tag = null;
        store.Edit(edit.Id, edit.Favorite, edit.Notes, tag, edit.RemoveTag);
        return GetDetails(edit.Id);
    }

    public void EditBatch(string json)
    {
        if (json == null || json.Length > 14000) throw new ArgumentException("Edição em lote inválida.");
        var edit = JsonSerializer.Deserialize<AssetBatchEdit>(json, Json) ?? throw new ArgumentException("Edição em lote inválida.");
        if (edit.Ids == null || edit.Ids.Count is < 1 or > 100 || edit.Ids.Any(id => string.IsNullOrWhiteSpace(id) || id.Length > 80) ||
            edit.AddTag?.Length > 80 || edit.RemoveTag?.Length > 80 || edit.CollectionId?.Length > 80 ||
            (edit.CollectionPresent.HasValue && string.IsNullOrWhiteSpace(edit.CollectionId)))
            throw new ArgumentException("Seleção, tag ou coleção inválida.");
        edit.AddTag = edit.AddTag?.Trim();
        edit.RemoveTag = edit.RemoveTag?.Trim();
        store.EditBatch(edit);
    }

    public string AddCollection(string name)
    {
        name = name?.Trim();
        if (string.IsNullOrEmpty(name) || name.Length > 90) throw new ArgumentException("Nome da coleção inválido.");
        return Serialize(store.AddCollection(name));
    }

    public string SaveQuery(string name, string json)
    {
        name = name?.Trim();
        if (string.IsNullOrEmpty(name) || name.Length > 90 || json == null || json.Length > 12000)
            throw new ArgumentException("Busca salva inválida.");
        Query(json); // Runs the same whitelist and bounded rule validation as an ordinary search.
        var query = JsonSerializer.Deserialize<AssetQuery>(json, Json) ?? throw new ArgumentException("Busca inválida.");
        query.Offset = 0;
        query.Limit = 100;
        return Serialize(store.SaveQuery(name, query));
    }

    public void SetCollectionItem(string collectionId, string assetId, bool present) => store.SetCollectionItem(collectionId, assetId, present);

    public string StartIndex(string rootId)
    {
        var root = store.Root(rootId) ?? throw new ArgumentException("Pasta desconhecida.");
        if (!root.Online) throw new DirectoryNotFoundException("A pasta está offline.");
        var existing = jobs.Values.FirstOrDefault(j => j.RootId == rootId && j.State is "queued" or "running");
        if (existing != null) return existing.Id;
        var job = new AssetJob { Id = Guid.NewGuid().ToString("N"), RootId = rootId };
        var source = new CancellationTokenSource();
        jobs[job.Id] = job;
        cancellations[job.Id] = source;
        _ = Task.Run(() =>
        {
            var entered = false;
            try { scanGate.Wait(source.Token); entered = true; Scan(root, job, source.Token); }
            catch (OperationCanceledException) { job.State = "cancelled"; }
            finally
            {
                if (entered) scanGate.Release();
                if (cancellations.TryRemove(job.Id, out var held)) held.Dispose();
            }
        });
        return job.Id;
    }

    public void CancelIndex(string id)
    {
        if (cancellations.TryGetValue(id, out var source)) source.Cancel();
    }

    private void Scan(AssetRoot root, AssetJob job, CancellationToken token)
    {
        job.State = "running";
        var complete = true;
        try
        {
            var folders = new Stack<string>();
            folders.Push(root.Path);
            while (folders.Count > 0)
            {
                token.ThrowIfCancellationRequested();
                while (paused) { token.ThrowIfCancellationRequested(); Thread.Sleep(100); }
                var folder = folders.Pop();
                IEnumerable<string> entries;
                try { entries = Directory.EnumerateFileSystemEntries(folder).ToList(); }
                catch (Exception error) when (error is FileNotFoundException or DirectoryNotFoundException)
                {
                    continue; // Entry disappeared while enumerating; the completed scan records its absence.
                }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException)
                {
                    AppLog.Error("Assets.ScanFolder", error);
                    complete = false;
                    continue;
                }
                foreach (var path in entries)
                {
                    token.ThrowIfCancellationRequested();
                    while (paused) { token.ThrowIfCancellationRequested(); Thread.Sleep(100); }
                    try
                    {
                        var attributes = File.GetAttributes(path);
                        if ((attributes & FileAttributes.ReparsePoint) != 0) continue;
                        var isDirectory = (attributes & FileAttributes.Directory) != 0;
                        var info = new FileInfo(path);
                        var relative = Path.GetRelativePath(root.Path, path).Replace('\\', '/');
                        var size = isDirectory ? 0 : info.Length;
                        var modified = new DateTimeOffset(info.LastWriteTimeUtc).ToUnixTimeMilliseconds();
                        var hint = store.ScanHint(root.Id, relative);
                        var unchanged = hint != null && hint.Size == size && hint.ModifiedUtc == modified;
                        var dimensions = unchanged ? (hint.Width, hint.Height) :
                            !isDirectory && Images.Contains(Path.GetExtension(path)) ? ImageDimensionsReader.Read(path) : (0, 0);
                        store.Upsert(new AssetItem
                        {
                            Id = Guid.NewGuid().ToString("N"), RootId = root.Id,
                            RelativePath = relative, Name = Path.GetFileName(path),
                            IsDirectory = isDirectory, IsImage = !isDirectory && Images.Contains(Path.GetExtension(path)),
                            Size = size, ModifiedUtc = modified,
                            Width = dimensions.Item1, Height = dimensions.Item2,
                            Metadata = unchanged ? "" : !isDirectory && size <= 100 * 1024 * 1024 ? PngMetadataReader.Read(path) : ""
                        }, job.Id);
                        job.Seen++;
                        if (isDirectory) folders.Push(path);
                    }
                    catch (Exception error) when (error is FileNotFoundException or DirectoryNotFoundException)
                    {
                        continue; // Rename/delete raced with enumeration.
                    }
                    catch (Exception error) when (error is IOException or UnauthorizedAccessException)
                    {
                        AppLog.Error("Assets.ScanEntry", error);
                        complete = false;
                    }
                }
            }
            if (complete) store.FinishScan(root.Id, job.Id);
            job.State = complete ? "completed" : "partial";
        }
        catch (OperationCanceledException) { job.State = "cancelled"; }
        catch (Exception error)
        {
            AppLog.Error("Assets.Scan", error);
            job.Error = error.Message;
            job.State = "failed";
        }
    }

    private void Watch(AssetRoot root)
    {
        lock (watcherGate)
        {
            if (watchers.ContainsKey(root.Id)) return;
            try
            {
                var watcher = new FileSystemWatcher(root.Path)
                {
                    IncludeSubdirectories = true, NotifyFilter = NotifyFilters.FileName | NotifyFilters.DirectoryName | NotifyFilters.LastWrite | NotifyFilters.Size
                };
                void Changed(object sender, FileSystemEventArgs args) => ScheduleScan(root.Id);
                watcher.Changed += Changed;
                watcher.Created += Changed;
                watcher.Deleted += Changed;
                watcher.Renamed += (_, _) => ScheduleScan(root.Id);
                watcher.Error += (_, _) => ScheduleScan(root.Id);
                watcher.EnableRaisingEvents = true;
                watchers[root.Id] = watcher;
            }
            catch (Exception error) { AppLog.Error("Assets.Watch", error); }
        }
    }

    private void ScheduleScan(string rootId)
    {
        lock (watcherGate)
        {
            if (!debounce.TryGetValue(rootId, out var timer))
            {
                timer = new Timer(_ =>
                {
                    try { StartIndex(rootId); }
                    catch (Exception error) { AppLog.Error("Assets.Rescan", error); }
                });
                debounce[rootId] = timer;
            }
            timer.Change(900, Timeout.Infinite);
        }
    }

    public string ResolvePath(string id)
    {
        var item = store.Asset(id) ?? throw new FileNotFoundException("Arquivo desconhecido.");
        if (!item.Available || item.IsDirectory) throw new FileNotFoundException("Arquivo indisponível.");
        return ResolveEntryPath(id);
    }

    private string ResolveEntryPath(string id)
    {
        var item = store.Asset(id) ?? throw new FileNotFoundException("Item desconhecido.");
        if (!item.Available) throw new FileNotFoundException("Item indisponível.");
        var root = store.Root(item.RootId) ?? throw new DirectoryNotFoundException();
        AssetPathPolicy.ValidateDirectoryAncestors(root.Path);
        var basePath = Path.GetFullPath(root.Path);
        if (!Path.EndsInDirectorySeparator(basePath)) basePath += Path.DirectorySeparatorChar;
        var candidate = Path.GetFullPath(Path.Combine(root.Path, item.RelativePath.Replace('/', Path.DirectorySeparatorChar)));
        if (!candidate.StartsWith(basePath, StringComparison.OrdinalIgnoreCase)) throw new UnauthorizedAccessException("Caminho fora da biblioteca.");
        var current = Path.GetFullPath(root.Path);
        foreach (var segment in item.RelativePath.Split('/'))
        {
            if (segment is "" or "." or "..") throw new UnauthorizedAccessException("Caminho inválido.");
            current = Path.Combine(current, segment);
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new UnauthorizedAccessException("Atalho de arquivo bloqueado.");
        }
        return candidate;
    }

    public string MediaUrl(string id, string variant)
    {
        var item = store.Asset(id) ?? throw new FileNotFoundException("Arquivo desconhecido.");
        if (!item.IsImage) throw new ArgumentException("Prévia indisponível.");
        if (variant is not ("thumb" or "preview")) throw new ArgumentException("Variante inválida.");
        return $"https://xennex-media.invalid/__asset/{id}/{variant}?v={item.ModifiedUtc}";
    }

    public (Stream content, string contentType) OpenMedia(string id, string variant)
    {
        var path = ResolvePath(id);
        if (!Images.Contains(Path.GetExtension(path))) throw new ArgumentException("Formato não suportado.");
        var info = new FileInfo(path);
        if (info.Length > 100 * 1024 * 1024) throw new IOException("Imagem grande demais para a prévia.");
        if (variant == "thumb")
        {
            var item = store.Asset(id);
            var cached = Path.Combine(cacheDirectory, id + "-" + item.ModifiedUtc + ".png");
            if (!File.Exists(cached))
            {
                CreateThumbnail(path, cached);
                if (Interlocked.Increment(ref thumbnailsWritten) % 32 == 0) PruneCache();
            }
            return (File.Open(cached, FileMode.Open, FileAccess.Read, FileShare.ReadWrite), "image/png");
        }
        var mime = Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".png" => "image/png", ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp",
            ".gif" => "image/gif", _ => "image/bmp"
        };
        return (File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite), mime);
    }

    private static void CreateThumbnail(string path, string destination)
    {
        using var source = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        var dimensions = BitmapDecoder.Create(source, BitmapCreateOptions.DelayCreation, BitmapCacheOption.None).Frames[0];
        var ratio = Math.Min(1d, 360d / Math.Max(dimensions.PixelWidth, dimensions.PixelHeight));
        source.Position = 0;
        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.DecodePixelWidth = Math.Max(1, (int)(dimensions.PixelWidth * ratio));
        image.DecodePixelHeight = Math.Max(1, (int)(dimensions.PixelHeight * ratio));
        image.StreamSource = source;
        image.EndInit();
        image.Freeze();
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(image));
        var temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = File.Create(temporary)) encoder.Save(stream);
            try { File.Move(temporary, destination); }
            catch (IOException) when (File.Exists(destination)) { }
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private void PruneCache()
    {
        lock (cacheGate)
        {
            try
            {
                var files = new DirectoryInfo(cacheDirectory).EnumerateFiles("*.png")
                    .OrderBy(file => file.LastWriteTimeUtc).ToList();
                long bytes = files.Sum(file => file.Length);
                const long limit = 1024L * 1024 * 1024;
                foreach (var file in files)
                {
                    if (bytes <= limit) break;
                    try { var length = file.Length; file.Delete(); bytes -= length; }
                    catch (IOException) { /* A WebView may still be reading this thumbnail. */ }
                }
            }
            catch (Exception error) { AppLog.Error("Assets.Cache", error); }
        }
    }

    public void Backup(string destination) => store.Backup(destination);

    public string PlanFileOperation(string json)
    {
        if (json == null || json.Length > 65536) throw new ArgumentException("Operação inválida.");
        var request = JsonSerializer.Deserialize<AssetFileRequest>(json, Json) ?? throw new ArgumentException("Operação inválida.");
        return Serialize(files.Plan(request));
    }

    public string ExecuteFileOperation(string planId)
    {
        var plan = files.Take(planId);
        var job = new AssetJob { Id = Guid.NewGuid().ToString("N"), State = "queued" };
        var source = new CancellationTokenSource();
        jobs[job.Id] = job;
        cancellations[job.Id] = source;
        _ = Task.Run(() =>
        {
            job.State = "running";
            try
            {
                files.Execute(plan, source.Token, (count, operationId) =>
                {
                    lock (job) { job.Seen = count; job.OperationIds.Add(operationId); }
                });
                job.State = "scanning";
                var indexIds = new List<string>();
                foreach (var rootId in plan.Items.SelectMany(item => new[] { item.SourceRootId, item.DestinationRootId }).Where(id => id != "").Distinct())
                    try { indexIds.Add(StartIndex(rootId)); } catch (DirectoryNotFoundException) { }
                while (indexIds.Any(id => jobs.TryGetValue(id, out var scan) && scan.State is "queued" or "running"))
                {
                    source.Token.ThrowIfCancellationRequested();
                    Thread.Sleep(100);
                }
                job.State = indexIds.Any(id => jobs.TryGetValue(id, out var scan) && scan.State is "failed" or "partial") ? "partial" : "completed";
            }
            catch (OperationCanceledException) { job.State = "cancelled"; }
            catch (Exception error) { AppLog.Error("Assets.FileOperation", error); job.Error = error.Message; job.State = "failed"; }
            finally { if (cancellations.TryRemove(job.Id, out var held)) held.Dispose(); }
        });
        return job.Id;
    }

    public void Dispose()
    {
        lock (watcherGate)
        {
            foreach (var timer in debounce.Values) timer.Dispose();
            foreach (var watcher in watchers.Values) watcher.Dispose();
            debounce.Clear();
            watchers.Clear();
        }
        foreach (var source in cancellations.Values) source.Cancel();
    }
}

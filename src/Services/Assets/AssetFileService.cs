using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using Microsoft.VisualBasic.FileIO;
using Xennex.Models.Assets;

namespace Xennex.Services.Assets;

internal sealed class AssetFileService
{
    private readonly AssetStore store;
    private readonly Func<string, string> resolveAsset;
    private readonly ConcurrentDictionary<string, AssetFilePlan> plans = new();

    public AssetFileService(AssetStore store, Func<string, string> resolveAsset)
    {
        this.store = store;
        this.resolveAsset = resolveAsset;
        store.MarkInterruptedOperations();
        RecoverInterrupted();
    }

    internal static void ValidateName(string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Length > 240 || name is "." or ".." ||
            name.EndsWith(' ') || name.EndsWith('.') || name.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
            name.Contains('/') || name.Contains('\\')) throw new ArgumentException("Nome de arquivo inválido.");
        var baseName = name.Split('.')[0].ToUpperInvariant();
        if (baseName is "CON" or "PRN" or "AUX" or "NUL" ||
            baseName.Length == 4 && (baseName.StartsWith("COM", StringComparison.Ordinal) ||
                baseName.StartsWith("LPT", StringComparison.Ordinal)) && baseName[3] is >= '1' and <= '9')
            throw new ArgumentException("Nome reservado do Windows.");
    }

    private string Destination(string rootId, string folder)
    {
        var root = store.Root(rootId) ?? throw new ArgumentException("Pasta de destino desconhecida.");
        if (!root.Online) throw new DirectoryNotFoundException("Destino offline.");
        var current = Path.GetFullPath(root.Path);
        if (!string.Equals(Path.GetPathRoot(current), current, StringComparison.OrdinalIgnoreCase))
            current = current.TrimEnd(Path.DirectorySeparatorChar);
        AssetPathPolicy.ValidateDirectoryAncestors(current);
        foreach (var segment in (folder ?? "").Split('/', StringSplitOptions.RemoveEmptyEntries))
        {
            ValidateName(segment);
            current = Path.Combine(current, segment);
            if (!Directory.Exists(current) || (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new DirectoryNotFoundException("Escolha uma pasta existente dentro do acervo.");
        }
        return current;
    }

    public AssetFilePlan Plan(AssetFileRequest request)
    {
        if (request == null || request.AssetIds == null || request.AssetIds.Count > 100 ||
            request.Type is not ("createFolder" or "rename" or "copy" or "move" or "recycle") ||
            request.ConflictPolicy is not ("ask" or "rename" or "skip") || request.Choices == null ||
            request.Choices.Count > 100 || request.AssetIds.Distinct().Count() != request.AssetIds.Count)
            throw new ArgumentException("Operação inválida.");
        var singleRename = request.Type == "rename" && request.AssetIds.Count == 1 && request.Naming == null && request.Choices.Count == 0;
        if (request.Type == "createFolder" || singleRename) ValidateName(request.NewName);
        if (request.Type != "createFolder" && request.AssetIds.Count == 0) throw new ArgumentException("Selecione arquivos.");
        if (request.Naming != null && request.Type is not ("rename" or "copy" or "move"))
            throw new ArgumentException("Esta operação não aceita regra de nomes.");
        if (request.Choices.Any(choice => choice == null || !request.AssetIds.Contains(choice.AssetId) ||
            choice.Action is not ("skip" or "rename")) || request.Choices.Select(choice => choice.AssetId).Distinct().Count() != request.Choices.Count)
            throw new ArgumentException("Decisões por arquivo inválidas.");
        var plan = new AssetFilePlan { Id = Guid.NewGuid().ToString("N"), Type = request.Type,
            ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(5).ToUnixTimeMilliseconds() };
        var destinationFolder = request.Type is "createFolder" or "copy" or "move"
            ? Destination(request.DestinationRootId, request.DestinationFolder) : "";
        if (request.Type == "createFolder")
        {
            var target = Path.Combine(destinationFolder, request.NewName);
            if (File.Exists(target) || Directory.Exists(target)) throw new IOException("Já existe um item com esse nome.");
            plan.Items.Add(new AssetFilePlanItem { DestinationRootId = request.DestinationRootId,
                DestinationRelativePath = Combine(request.DestinationFolder, request.NewName), DestinationPath = target, IsDirectory = true });
            return SavePlan(plan);
        }
        var sources = request.AssetIds.Select(id => (Asset: store.Asset(id) ?? throw new FileNotFoundException("Item desconhecido."),
            Path: resolveAsset(id))).ToList();
        if (request.Naming != null && sources.Any(item => item.Asset.IsDirectory))
            throw new ArgumentException("A numeração em lote está disponível para arquivos. Selecione pastas separadamente.");
        var sequence = request.Naming == null ? null : new AssetNamingSequence(request.Naming,
            request.Type == "rename" ? sources.Select(item => Path.GetDirectoryName(item.Path)!) : new[] { destinationFolder });
        plan.StartNumber = sequence?.StartNumber;
        var reserved = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in sources)
        {
            var asset = entry.Asset;
            var source = entry.Path;
            var targetRoot = request.Type is "copy" or "move" ? request.DestinationRootId : asset.RootId;
            var targetFolder = request.Type == "rename" ? Path.GetDirectoryName(source)! : destinationFolder;
            var targetName = singleRename ? request.NewName : asset.Name;
            if (singleRename && string.Equals(asset.Name, targetName, StringComparison.Ordinal))
                throw new ArgumentException("Escolha um nome diferente.");
            var choice = request.Choices.FirstOrDefault(value => value.AssetId == asset.Id);
            var skipped = choice?.Action == "skip";
            var conflict = false;
            var note = skipped ? "Ignorado por sua escolha." : "";
            if (choice?.Action == "rename") { ValidateName(choice.Name); targetName = choice.Name; }
            var originalOccupied = request.Type != "recycle" && Occupied(Path.Combine(targetFolder, targetName), reserved,
                request.Type is "rename" or "move" ? source : "");
            if (!skipped && choice == null && sequence != null && (request.Naming.Scope == "all" || originalOccupied))
                targetName = sequence.Next(asset.Name);
            var target = request.Type == "recycle" ? "" : Path.Combine(targetFolder, targetName);
            if (!skipped && (request.Type is "rename" or "move") && string.Equals(source, target, StringComparison.Ordinal))
            { skipped = true; note = "Já está com este nome neste destino."; }
            if (!skipped && request.Type != "recycle" && Occupied(target, reserved, request.Type is "rename" or "move" ? source : ""))
            {
                (target, skipped, conflict, note) = ResolveConflict(target, reserved, request.ConflictPolicy);
            }
            if (asset.IsDirectory && target.StartsWith(source + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Não é possível mover uma pasta para dentro dela mesma.");
            if (asset.IsDirectory && request.Type == "move" && !SameVolume(source, target))
                throw new NotSupportedException("Mover pastas entre unidades ainda não é seguro; copie e confira antes de enviar a origem à Lixeira.");
            if (!skipped && request.Type != "recycle") reserved.Add(target);
            plan.Items.Add(new AssetFilePlanItem { AssetId = asset.Id, SourceRootId = asset.RootId,
                DestinationRootId = targetRoot, SourceRelativePath = asset.RelativePath,
                DestinationRelativePath = request.Type == "recycle" ? "" :
                    request.Type == "rename" ? Combine(AssetStore.Parent(asset.RelativePath), Path.GetFileName(target)) :
                    Combine(request.DestinationFolder, Path.GetFileName(target)),
                SourcePath = source, DestinationPath = target, IsDirectory = asset.IsDirectory,
                Size = asset.Size, ModifiedUtc = asset.ModifiedUtc, Conflict = conflict, Skipped = skipped, Note = note });
        }
        var selectedDirectories = plan.Items.Where(item => item.IsDirectory).Select(item => item.SourcePath + Path.DirectorySeparatorChar).ToArray();
        if (plan.Items.Any(item => selectedDirectories.Any(directory =>
                item.SourcePath.StartsWith(directory, StringComparison.OrdinalIgnoreCase))))
            throw new ArgumentException("Selecione a pasta ou os itens dentro dela, não ambos na mesma operação.");
        return SavePlan(plan);
    }

    private AssetFilePlan SavePlan(AssetFilePlan plan)
    {
        plan.CanExecute = !plan.Items.Any(item => item.Conflict) && plan.Items.Any(item => !item.Skipped);
        foreach (var expired in plans.Where(value => value.Value.ExpiresUtc < DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()))
            plans.TryRemove(expired.Key, out _);
        if (plan.CanExecute) plans[plan.Id] = plan;
        return plan;
    }

    private static bool Occupied(string path, HashSet<string> reserved, string ownSource = "") =>
        reserved.Contains(path) || (!string.Equals(path, ownSource, StringComparison.OrdinalIgnoreCase) &&
            (File.Exists(path) || Directory.Exists(path)));

    private static (string Target, bool Skipped, bool Conflict, string Note) ResolveConflict(string target,
        HashSet<string> reserved, string policy) => policy switch
    {
        "rename" => (AvailableName(target, reserved), false, false, "Nome ocupado; renomeado automaticamente."),
        "skip" => (target, true, false, "Ignorado porque o nome está ocupado."),
        _ => (target, false, true, "Nome ocupado no destino ou por outro item do lote. Escolha outro nome ou ignore este item.")
    };

    private static string Combine(string folder, string name) => string.IsNullOrEmpty(folder) ? name : folder + "/" + name;
    private static bool SameVolume(string source, string destination) =>
        string.Equals(Path.GetPathRoot(source), Path.GetPathRoot(destination), StringComparison.OrdinalIgnoreCase);
    private static string AvailableName(string path, HashSet<string> reserved)
    {
        if (!Occupied(path, reserved)) return path;
        var folder = Path.GetDirectoryName(path)!;
        var extension = Path.GetExtension(path);
        var stem = Path.GetFileNameWithoutExtension(path);
        for (var number = 2; number <= 1000; number++)
        {
            var candidate = Path.Combine(folder, $"{stem} ({number}){extension}");
            if (!Occupied(candidate, reserved)) return candidate;
        }
        throw new IOException("Não foi possível escolher um nome livre.");
    }

    public AssetFilePlan Take(string id)
    {
        if (!plans.TryRemove(id, out var plan) || plan.ExpiresUtc < DateTimeOffset.UtcNow.ToUnixTimeMilliseconds())
            throw new InvalidOperationException("Plano expirado. Revise a operação novamente.");
        return plan;
    }

    public void Execute(AssetFilePlan plan, CancellationToken token, Action<int, string> progress)
    {
        if (!plan.CanExecute || plan.Items.Any(item => item.Conflict)) throw new InvalidOperationException("Resolva os conflitos antes de executar.");
        var active = plan.Items.Where(item => !item.Skipped).ToList();
        foreach (var item in active) { token.ThrowIfCancellationRequested(); ValidateAtExecution(item, plan.Type); }
        for (var index = 0; index < active.Count; index++)
        {
            token.ThrowIfCancellationRequested();
            var item = active[index];
            var journalId = Guid.NewGuid().ToString("N");
            ValidateAtExecution(item, plan.Type);
            store.BeginFileOperation(journalId, plan.Type, item);
            try
            {
                Apply(plan.Type, item, token);
                if (plan.Type is "rename" or "move") store.MoveRecords(item);
                if (plan.Type == "recycle") store.MarkUnavailable(item);
                store.FinishFileOperation(journalId, "completed");
                progress(index + 1, journalId);
            }
            catch (Exception error)
            {
                store.FinishFileOperation(journalId, "failed", error.Message);
                throw;
            }
        }
    }

    public IReadOnlyList<AssetOperation> Recent() => store.RecentOperations();

    private void RecoverInterrupted()
    {
        foreach (var operation in store.RecentOperations(10000).Where(item => item.State == "interrupted"))
        {
            try
            {
                var sourceRoot = store.Root(operation.SourceRootId);
                var targetRoot = store.Root(operation.DestinationRootId);
                var source = sourceRoot == null || operation.SourceRelativePath == "" ? "" :
                    Path.Combine(sourceRoot.Path, operation.SourceRelativePath.Replace('/', Path.DirectorySeparatorChar));
                var target = targetRoot == null || operation.DestinationRelativePath == "" ? "" :
                    Path.Combine(targetRoot.Path, operation.DestinationRelativePath.Replace('/', Path.DirectorySeparatorChar));
                var sourcePresent = File.Exists(source) || Directory.Exists(source);
                var targetPresent = File.Exists(target) || Directory.Exists(target);
                if (operation.Kind is "rename" or "move" && !sourcePresent && File.Exists(target))
                {
                    var info = new FileInfo(target);
                    if (info.Length != operation.Size ||
                        new DateTimeOffset(info.LastWriteTimeUtc).ToUnixTimeMilliseconds() != operation.ModifiedUtc) continue;
                    Destination(operation.DestinationRootId, AssetStore.Parent(operation.DestinationRelativePath));
                    store.MoveRecords(new AssetFilePlanItem { AssetId = operation.AssetId,
                        SourceRootId = operation.SourceRootId, DestinationRootId = operation.DestinationRootId,
                        SourceRelativePath = operation.SourceRelativePath, DestinationRelativePath = operation.DestinationRelativePath });
                    store.FinishFileOperation(operation.Id, "completed");
                    continue;
                }
                if (operation.Kind is "rename" or "move" && sourcePresent && !targetPresent)
                {
                    store.FinishFileOperation(operation.Id, "not_applied");
                    continue;
                }
                if (operation.Kind == "copy" && sourcePresent && targetPresent)
                {
                    store.FinishFileOperation(operation.Id, "completed");
                    continue;
                }
                if (operation.Kind == "createFolder" && Directory.Exists(target))
                {
                    store.FinishFileOperation(operation.Id, "completed");
                    continue;
                }
                if (operation.Kind == "recycle" && !sourcePresent)
                {
                    store.MarkUnavailable(new AssetFilePlanItem { AssetId = operation.AssetId,
                        SourceRootId = operation.SourceRootId, SourceRelativePath = operation.SourceRelativePath });
                    store.FinishFileOperation(operation.Id, "completed");
                }
            }
            catch (Exception error) { AppLog.Error("Assets.Recover", error); }
        }
    }

    public void Undo(string id)
    {
        var operation = store.RecentOperations().FirstOrDefault(item => item.Id == id)
            ?? throw new ArgumentException("Operação não encontrada.");
        if (operation.State != "completed" || operation.Kind is not ("rename" or "move"))
            throw new InvalidOperationException("Esta operação não pode ser desfeita automaticamente.");
        var asset = store.Asset(operation.AssetId) ?? throw new FileNotFoundException("Item não encontrado.");
        if (asset.IsDirectory || asset.RootId != operation.DestinationRootId ||
            asset.RelativePath != operation.DestinationRelativePath)
            throw new InvalidOperationException("O item mudou desde a operação.");
        ValidateName(Path.GetFileName(operation.SourceRelativePath));
        ValidateName(Path.GetFileName(operation.DestinationRelativePath));
        var source = Path.Combine(Destination(operation.DestinationRootId, AssetStore.Parent(operation.DestinationRelativePath)),
            Path.GetFileName(operation.DestinationRelativePath));
        var target = Path.Combine(Destination(operation.SourceRootId, AssetStore.Parent(operation.SourceRelativePath)),
            Path.GetFileName(operation.SourceRelativePath));
        if (!SameVolume(source, target) || !File.Exists(source) || File.Exists(target) || Directory.Exists(target) ||
            (File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0)
            throw new IOException("Origem ou destino mudou. Confira os arquivos manualmente.");
        var info = new FileInfo(source);
        if (info.Length != operation.Size || new DateTimeOffset(info.LastWriteTimeUtc).ToUnixTimeMilliseconds() != operation.ModifiedUtc)
            throw new IOException("O arquivo foi alterado. Não será movido automaticamente.");
        File.Move(source, target);
        store.MoveRecords(new AssetFilePlanItem
        {
            AssetId = operation.AssetId, SourceRootId = operation.DestinationRootId,
            DestinationRootId = operation.SourceRootId,
            SourceRelativePath = operation.DestinationRelativePath,
            DestinationRelativePath = operation.SourceRelativePath
        });
        store.FinishFileOperation(id, "undone");
    }

    private void ValidateAtExecution(AssetFilePlanItem item, string type)
    {
        if (type != "createFolder")
        {
            if (resolveAsset(item.AssetId) != item.SourcePath) throw new IOException("A origem mudou. Revise a operação.");
            var modified = item.IsDirectory ? Directory.GetLastWriteTimeUtc(item.SourcePath) : File.GetLastWriteTimeUtc(item.SourcePath);
            if (!item.IsDirectory && (new FileInfo(item.SourcePath).Length != item.Size ||
                new DateTimeOffset(modified).ToUnixTimeMilliseconds() != item.ModifiedUtc))
                throw new IOException("O arquivo mudou desde a prévia. Revise a operação.");
        }
        if (type == "recycle") return;
        var folder = Destination(item.DestinationRootId, AssetStore.Parent(item.DestinationRelativePath));
        if (!string.Equals(folder, Path.GetDirectoryName(item.DestinationPath), StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException("Destino mudou.");
        if (File.Exists(item.DestinationPath) || Directory.Exists(item.DestinationPath))
        {
            if (type == "rename" && string.Equals(item.SourcePath, item.DestinationPath, StringComparison.OrdinalIgnoreCase)) return;
            throw new IOException("O nome de destino ficou ocupado. Revise a operação.");
        }
    }

    private static void Apply(string type, AssetFilePlanItem item, CancellationToken token)
    {
        if (type == "createFolder") { Directory.CreateDirectory(item.DestinationPath); return; }
        if (type == "recycle")
        {
            if (item.IsDirectory) FileSystem.DeleteDirectory(item.SourcePath, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin);
            else FileSystem.DeleteFile(item.SourcePath, UIOption.OnlyErrorDialogs, RecycleOption.SendToRecycleBin);
            return;
        }
        if (type == "copy") { Copy(item, token); return; }
        if (item.IsDirectory) { Directory.Move(item.SourcePath, item.DestinationPath); return; }
        if (SameVolume(item.SourcePath, item.DestinationPath)) { File.Move(item.SourcePath, item.DestinationPath); return; }
        Copy(item, token);
        token.ThrowIfCancellationRequested();
        if (!Hash(item.SourcePath).SequenceEqual(Hash(item.DestinationPath)))
            throw new IOException("Falha ao conferir a cópia. A origem foi preservada.");
        File.Delete(item.SourcePath);
    }

    private static void Copy(AssetFilePlanItem item, CancellationToken token)
    {
        var stage = item.DestinationPath + ".xennex-" + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            if (item.IsDirectory)
            {
                CopyTree(item.SourcePath, stage, token);
                Directory.Move(stage, item.DestinationPath);
                return;
            }
            File.Copy(item.SourcePath, stage);
            token.ThrowIfCancellationRequested();
            if (!Hash(item.SourcePath).SequenceEqual(Hash(stage))) throw new IOException("Falha ao conferir a cópia.");
            File.Move(stage, item.DestinationPath);
        }
        finally
        {
            if (File.Exists(stage)) File.Delete(stage);
            if (Directory.Exists(stage)) Directory.Delete(stage, true);
        }
    }

    private static void CopyTree(string source, string destination, CancellationToken token)
    {
        if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0) throw new UnauthorizedAccessException("Atalho de pasta bloqueado.");
        Directory.CreateDirectory(destination);
        foreach (var entry in Directory.EnumerateFileSystemEntries(source))
        {
            token.ThrowIfCancellationRequested();
            if ((File.GetAttributes(entry) & FileAttributes.ReparsePoint) != 0) throw new UnauthorizedAccessException("Atalho dentro da pasta bloqueado.");
            var target = Path.Combine(destination, Path.GetFileName(entry));
            if (Directory.Exists(entry)) { CopyTree(entry, target, token); continue; }
            File.Copy(entry, target);
            if (!Hash(entry).SequenceEqual(Hash(target))) throw new IOException("Falha ao conferir arquivo copiado.");
        }
    }

    private static byte[] Hash(string path)
    {
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return SHA256.HashData(stream);
    }
}

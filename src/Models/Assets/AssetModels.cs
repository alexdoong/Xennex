using System;
using System.Collections.Generic;

namespace Xennex.Models.Assets;

public sealed class AssetRoot
{
    public string Id { get; set; } = "";
    public string Path { get; set; } = "";
    public bool Online { get; set; }
}

public sealed class AssetItem
{
    public string Id { get; set; } = "";
    public string RootId { get; set; } = "";
    public string RelativePath { get; set; } = "";
    public string Name { get; set; } = "";
    public bool IsDirectory { get; set; }
    public bool IsImage { get; set; }
    public bool Available { get; set; }
    public long Size { get; set; }
    public long ModifiedUtc { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }
    public bool Favorite { get; set; }
    public string Notes { get; set; } = "";
    public string Metadata { get; set; } = "";
    public bool HasMetadata { get; set; }
    public List<string> Tags { get; set; } = new();
}

public sealed class AssetQuery
{
    public string RootId { get; set; } = "";
    public string Folder { get; set; } = "";
    public string Search { get; set; } = "";
    public string Tag { get; set; } = "";
    public string Term { get; set; } = "";
    public string TermSource { get; set; } = "all";
    public string CollectionId { get; set; } = "";
    public bool FavoritesOnly { get; set; }
    public bool ImagesOnly { get; set; }
    public bool MetadataOnly { get; set; }
    public bool DirectoriesOnly { get; set; }
    public bool IncludeDescendants { get; set; }
    public string Sort { get; set; } = "name";
    public int Offset { get; set; }
    public int Limit { get; set; } = 100;
    public int MinWidth { get; set; }
    public int MinHeight { get; set; }
    public int MaxWidth { get; set; }
    public int MaxHeight { get; set; }
    public AssetRule Rule { get; set; }
}

public sealed class AssetTagOverviewQuery
{
    public string Search { get; set; } = "";
    public string Source { get; set; } = "all";
    public int Offset { get; set; }
    public int Limit { get; set; } = 100;
}

public sealed class AssetTagOverviewItem
{
    public string Term { get; set; } = "";
    public int Manual { get; set; }
    public int Positive { get; set; }
    public int Negative { get; set; }
}

public sealed class AssetTagOverviewPage
{
    public List<AssetTagOverviewItem> Items { get; set; } = new();
    public int Total { get; set; }
    public int NextOffset { get; set; }
}

public sealed class AssetRule
{
    public string Mode { get; set; } = "all";
    public string Field { get; set; } = "";
    public string Comparison { get; set; } = "";
    public string Value { get; set; } = "";
    public List<AssetRule> Children { get; set; } = new();
}

public sealed class SavedAssetQuery
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public AssetQuery Query { get; set; } = new();
}

public sealed class AssetPage
{
    public List<AssetItem> Items { get; set; } = new();
    public int Total { get; set; }
    public int NextOffset { get; set; }
}

public sealed class AssetJob
{
    public string Id { get; set; } = "";
    public string RootId { get; set; } = "";
    public string State { get; set; } = "queued";
    public int Seen { get; set; }
    public string Error { get; set; } = "";
    public List<string> OperationIds { get; set; } = new();
}

public sealed class AssetOperation
{
    public string Id { get; set; } = "";
    public string Kind { get; set; } = "";
    public string AssetId { get; set; } = "";
    public string SourceRootId { get; set; } = "";
    public string DestinationRootId { get; set; } = "";
    public string SourceRelativePath { get; set; } = "";
    public string DestinationRelativePath { get; set; } = "";
    public string State { get; set; } = "";
    public string Error { get; set; } = "";
    public long CreatedUtc { get; set; }
    public long Size { get; set; }
    public long ModifiedUtc { get; set; }
}

public sealed class AssetRelinkPlan
{
    public string Id { get; set; } = "";
    public string RootId { get; set; } = "";
    public string OldPath { get; set; } = "";
    public string NewPath { get; set; } = "";
    public int Matched { get; set; }
    public int Missing { get; set; }
    public long ExpiresUtc { get; set; }
}

public sealed class AssetCollection
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
}

public sealed class AssetEdit
{
    public string Id { get; set; } = "";
    public bool? Favorite { get; set; }
    public string Notes { get; set; }
    public string AddTag { get; set; }
    public string RemoveTag { get; set; }
}

public sealed class AssetBatchEdit
{
    public List<string> Ids { get; set; } = new();
    public bool? Favorite { get; set; }
    public string AddTag { get; set; }
    public string RemoveTag { get; set; }
    public string CollectionId { get; set; }
    public bool? CollectionPresent { get; set; }
}

public sealed class AssetFileRequest
{
    public string Type { get; set; } = "";
    public List<string> AssetIds { get; set; } = new();
    public string DestinationRootId { get; set; } = "";
    public string DestinationFolder { get; set; } = "";
    public string NewName { get; set; } = "";
    public string ConflictPolicy { get; set; } = "rename";
    public AssetNamingRule Naming { get; set; }
    public List<AssetFileChoice> Choices { get; set; } = new();
}

public sealed class AssetNamingRule
{
    public string BaseName { get; set; } = "";
    public string Pattern { get; set; } = "{base}{number}";
    public string Scope { get; set; } = "all";
    public bool AutoContinue { get; set; } = true;
    public int StartNumber { get; set; } = 1;
    public int Digits { get; set; } = 1;
}

public sealed class AssetFileChoice
{
    public string AssetId { get; set; } = "";
    public string Action { get; set; } = "rename";
    public string Name { get; set; } = "";
}

public sealed class AssetFilePlan
{
    public string Id { get; set; } = "";
    public string Type { get; set; } = "";
    public List<AssetFilePlanItem> Items { get; set; } = new();
    public long ExpiresUtc { get; set; }
    public string Error { get; set; } = "";
    public bool CanExecute { get; set; } = true;
    public int? StartNumber { get; set; }
}

public sealed class AssetFilePlanItem
{
    public string AssetId { get; set; } = "";
    public string SourceRootId { get; set; } = "";
    public string DestinationRootId { get; set; } = "";
    public string SourceRelativePath { get; set; } = "";
    public string DestinationRelativePath { get; set; } = "";
    public string SourcePath { get; set; } = "";
    public string DestinationPath { get; set; } = "";
    public bool IsDirectory { get; set; }
    public long Size { get; set; }
    public long ModifiedUtc { get; set; }
    public bool Conflict { get; set; }
    public bool Skipped { get; set; }
    public string Note { get; set; } = "";
}

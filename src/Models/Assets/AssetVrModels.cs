using System.Collections.Generic;

namespace Xennex.Models.Assets;

public sealed class AssetVrRequest
{
    public List<string> AssetIds { get; set; } = new();
    public string InitialId { get; set; } = "";
    public string Mode { get; set; } = "selection";
    public string View { get; set; } = "gallery";
    public AssetQuery Query { get; set; } = new();
}

public sealed class AssetVrState
{
    public string State { get; set; } = "stopped";
    public string Error { get; set; } = "";
    public int Count { get; set; }
    public int Index { get; set; }
    public string Name { get; set; } = "";
    public float Zoom { get; set; } = 1;
    public bool Pinned { get; set; }
    public string View { get; set; } = "image";
    public string Location { get; set; } = "";
    public bool CanPrevious { get; set; }
    public bool CanNext { get; set; }
    public float WidthMeters { get; set; } = 2;
    public float DistanceMeters { get; set; } = 1.5f;
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Xennex.Models.Assets;

namespace Xennex.Services.Vr;

internal sealed class VrGallerySession
{
    public const int Width = 1280, Height = 800, PageSize = 12;
    private readonly Func<AssetQuery, AssetPage> _query;
    private readonly Func<IReadOnlyList<AssetRoot>> _roots;
    private readonly Action _checkCancellation;
    private AssetQuery _filter;
    private AssetQuery _returnQuery;
    private string _returnView = "gallery";
    private string _panelView = "gallery";
    private int _rootOffset, _rootTotal;
    private string _rootName = "Acervo";
    public IReadOnlyList<AssetItem> Items { get; private set; }
    public IReadOnlyList<AssetRoot> Roots { get; private set; } = Array.Empty<AssetRoot>();
    public int Total { get; private set; }
    public int Index { get; private set; }
    public float Zoom { get; private set; } = 1;
    public bool Pinned { get; private set; }
    public float WidthMeters { get; private set; } = 2;
    public float DistanceMeters { get; private set; } = 1.5f;
    public bool IsLibrary { get; }
    public string View { get; private set; } = "image";
    public string Notice { get; set; } = "";
    public AssetItem Current => Items.Count > 0 ? Items[Index] : null;
    public bool Favorites => _filter?.FavoritesOnly == true;
    public string Sort => _filter?.Sort ?? "name";
    public string Location => IsLibrary ? (View == "roots" ? "Acervos cadastrados" : (string.IsNullOrEmpty(_filter.RootId) ? "Todos os acervos" : _rootName) +
        (string.IsNullOrEmpty(_filter.Folder) ? "" : " / " + _filter.Folder)) : "Seleção do desktop";
    public bool CanPrevious => View != "panel" && (View == "roots" ? _rootOffset > 0 : Index > 0 && View == "image" || IsLibrary && _filter.Offset > 0);
    public bool CanNext => View != "panel" && (View == "roots" ? _rootOffset + Roots.Count < _rootTotal : View == "image" ?
        Index + 1 < Items.Count || IsLibrary && _filter.Offset + Items.Count < Total : _filter.Offset + Items.Count < Total);
    public static readonly string[] Actions = { "previous", "next", "zoomOut", "fit", "zoomIn", "pin", "recenter", "close",
        "gallery", "explorer", "roots", "up", "favorites", "sort", "refresh", "back", "panel", "sizeUp", "sizeDown", "nearer", "farther" };

    public VrGallerySession(AssetVrRequest request, Func<string, AssetItem> resolve,
        Func<AssetQuery, AssetPage> query = null, Func<IReadOnlyList<AssetRoot>> roots = null, Action checkCancellation = null)
    {
        if (request == null || request.Mode is not ("selection" or "library") || request.View is not ("gallery" or "explorer"))
            throw new ArgumentException("Modo VR inválido.");
        _query = query; _roots = roots;
        _checkCancellation = checkCancellation ?? (() => { });
        IsLibrary = request.Mode == "library";
        if (IsLibrary)
        {
            if (query == null || roots == null || request.Query == null) throw new ArgumentException("Catálogo VR indisponível.");
            _filter = Clone(request.Query); _filter.Offset = 0; _filter.Limit = PageSize;
            var root = _roots().FirstOrDefault(item => item.Id == _filter.RootId);
            if (root != null) _rootName = RootName(root);
            View = request.View; ConfigureView(); Load(); return;
        }
        if (request.AssetIds == null || request.AssetIds.Count is < 1 or > 100 ||
            request.AssetIds.Distinct().Count() != request.AssetIds.Count || request.AssetIds.Any(id => id == null || id.Length != 32 || !id.All(Uri.IsHexDigit)))
            throw new ArgumentException("Selecione de 1 a 100 imagens da Biblioteca.");
        if (!string.IsNullOrEmpty(request.InitialId) && !request.AssetIds.Contains(request.InitialId)) throw new ArgumentException("A imagem inicial não está na seleção.");
        Items = request.AssetIds.Select(resolve).ToArray();
        if (Items.Any(item => item == null || !item.IsImage || !item.Available || item.IsDirectory)) throw new ArgumentException("O VR aceita somente imagens disponíveis da Biblioteca.");
        Total = Items.Count;
        Index = Math.Max(0, request.AssetIds.IndexOf(request.InitialId));
    }

    public static bool IsAction(string action) => Actions.Contains(action) || action != null && action.StartsWith("open:", StringComparison.Ordinal) &&
        int.TryParse(action.AsSpan(5), out var index) && index is >= 0 and < PageSize;

    public void Apply(string action)
    {
        if (!IsAction(action)) throw new ArgumentException("Comando VR inválido.");
        Notice = "";
        if (action == "panel") { if (View != "panel") { _panelView = View; View = "panel"; } else View = _panelView; return; }
        if (action == "back" && View == "panel") { View = _panelView; return; }
        if (action is "sizeUp" or "sizeDown") { WidthMeters = Math.Clamp(WidthMeters + (action == "sizeUp" ? .25f : -.25f), .75f, 3); return; }
        if (action is "nearer" or "farther") { DistanceMeters = Math.Clamp(DistanceMeters + (action == "farther" ? .25f : -.25f), .75f, 3); return; }
        if (action == "pin") { Pinned = !Pinned; return; }
        if (action is "close" or "recenter") return;
        if (action is "zoomOut" or "zoomIn" or "fit")
        {
            if (View == "image") Zoom = action == "fit" ? 1 : Math.Clamp(Zoom + (action == "zoomIn" ? .25f : -.25f), .5f, 4);
            return;
        }
        if (action is "previous" or "next") { Move(action == "next" ? 1 : -1); return; }
        if (!IsLibrary) return;
        if (View == "panel") View = _panelView;
        if (action.StartsWith("open:", StringComparison.Ordinal)) { Open(int.Parse(action.AsSpan(5))); return; }
        if (action == "roots") { View = "roots"; _rootOffset = 0; LoadRoots(); return; }
        if (action == "back" && View == "image") { _filter = _returnQuery; View = _returnView; Load(); return; }
        if (action == "refresh")
        {
            if (View == "roots") { LoadRoots(); return; }
            var id = View == "image" ? Current?.Id : null;
            var zoom = Zoom;
            Load();
            var index = id == null ? -1 : Items.ToList().FindIndex(item => item.Id == id);
            if (index >= 0) { Index = index; Zoom = zoom; }
            return;
        }
        if (View == "image") { _filter = _returnQuery; View = _returnView; }
        if (action is "gallery" or "explorer") View = action;
        if (action is "up" or "back")
        {
            if (string.IsNullOrEmpty(_filter.Folder)) { View = "roots"; _rootOffset = 0; LoadRoots(); return; }
            _filter.Folder = _filter.Folder.Contains('/') ? _filter.Folder[.._filter.Folder.LastIndexOf('/')] : "";
        }
        if (action == "favorites") _filter.FavoritesOnly = !_filter.FavoritesOnly;
        if (action == "sort") _filter.Sort = _filter.Sort == "date" ? "name" : "date";
        if (View == "roots") View = "gallery";
        _filter.Offset = 0; ConfigureView(); Load();
    }

    private void ConfigureView()
    {
        _filter.ImagesOnly = View != "explorer"; _filter.DirectoriesOnly = false;
        _filter.IncludeDescendants = View == "gallery";
    }

    private void Load()
    {
        _checkCancellation();
        var page = _query(Clone(_filter)); Items = page.Items; Total = page.Total; Index = 0; Zoom = 1;
        if (Items.Count == 0 && _filter.Offset > 0) { _filter.Offset = 0; page = _query(Clone(_filter)); Items = page.Items; Total = page.Total; }
    }

    private void LoadRoots()
    {
        var roots = _roots(); _rootTotal = roots.Count;
        if (_rootOffset >= _rootTotal) _rootOffset = 0;
        Roots = roots.Skip(_rootOffset).Take(PageSize).ToArray();
    }

    private void Open(int index)
    {
        if (View == "image") return;
        if (View == "roots")
        {
            if (index >= Roots.Count) return;
            if (!Roots[index].Online) { Notice = "Este acervo está offline."; return; }
            _rootName = RootName(Roots[index]);
            _filter = new AssetQuery { RootId = Roots[index].Id, Limit = PageSize }; View = "explorer";
            ConfigureView(); Load(); return;
        }
        if (index >= Items.Count) return;
        var item = Items[index];
        if (!item.Available) { Notice = "Arquivo indisponível. Atualize o índice no desktop."; return; }
        if (item.IsDirectory)
        {
            _filter.RootId = item.RootId; _filter.Folder = item.RelativePath; _filter.Offset = 0; Load(); return;
        }
        if (!item.IsImage) { Notice = "Este arquivo não tem prévia de imagem. Use o desktop para abri-lo."; return; }
        _returnQuery = Clone(_filter); _returnView = View;
        if (View == "gallery") { Index = index; Zoom = 1; View = "image"; return; }
        // The viewer uses only images; the original listing is kept for Back.
        _filter.ImagesOnly = true; _filter.Offset = 0;
        var targetId = item.Id;
        do { Load(); Index = Items.ToList().FindIndex(candidate => candidate.Id == targetId); if (Index >= 0) break; _filter.Offset += PageSize; }
        while (_filter.Offset < Total);
        if (Index < 0) { Index = 0; _filter = _returnQuery; View = _returnView; Load(); Notice = "A imagem mudou no catálogo. Atualize a página."; return; }
        View = "image";
    }

    private void Move(int direction)
    {
        if (direction < 0 ? !CanPrevious : !CanNext) return;
        if (View == "roots") { _rootOffset += direction * PageSize; LoadRoots(); return; }
        if (View == "image" && Index + direction >= 0 && Index + direction < Items.Count) { Index += direction; Zoom = 1; return; }
        if (!IsLibrary) return;
        _filter.Offset = Math.Max(0, _filter.Offset + direction * PageSize); Load();
        if (View == "image" && direction < 0) Index = Math.Max(0, Items.Count - 1);
    }

    private static AssetQuery Clone(AssetQuery query) => JsonSerializer.Deserialize<AssetQuery>(JsonSerializer.Serialize(query));
    private static string RootName(AssetRoot root) => Path.GetFileName(root.Path.TrimEnd('\\', '/'));

    public AssetVrState Snapshot(string state, string error = "") => new()
    {
        State = state, Error = error, Count = View == "roots" ? _rootTotal : Total,
        Index = View == "roots" ? _rootOffset : (IsLibrary ? _filter.Offset : 0) + Index,
        Name = View == "image" ? Current?.Name ?? "" : Notice, Zoom = Zoom, Pinned = Pinned,
        View = View, Location = Location, CanPrevious = CanPrevious, CanNext = CanNext,
        WidthMeters = WidthMeters, DistanceMeters = DistanceMeters
    };
}

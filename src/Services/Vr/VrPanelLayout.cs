using System.Collections.Generic;
using System.Drawing;

namespace Xennex.Services.Vr;

internal sealed record VrControl(string Action, string Label, RectangleF Bounds, bool Enabled = true);

internal static class VrPanelLayout
{
    public static RectangleF Tile(int index) => new(32 + index % 4 * 304, 164 + index / 4 * 170, 292, 158);

    public static IEnumerable<VrControl> Controls(VrGallerySession session)
    {
        if (session.IsLibrary)
        {
            var top = new[] { ("gallery", "Galeria"), ("explorer", "Explorador"), ("roots", "Acervos"), ("up", "Pasta acima"),
                ("favorites", session.Favorites ? "Todas as artes" : "Favoritos"), ("sort", session.Sort == "date" ? "Mais recentes" : "Por nome"), ("refresh", "Atualizar"), ("panel", "Tamanho") };
            for (var i = 0; i < top.Length; i++) yield return new(top[i].Item1, top[i].Item2, new RectangleF(32 + i * 152, 104, 140, 48));
        }
        else yield return new("panel", "Tamanho do painel", new RectangleF(1030, 16, 218, 48));
        if (session.View == "panel")
        {
            var sizing = new[] { ("sizeDown", "Diminuir largura"), ("sizeUp", "Aumentar largura"), ("nearer", "Mais perto"), ("farther", "Mais longe") };
            for (var i = 0; i < sizing.Length; i++) yield return new(sizing[i].Item1, sizing[i].Item2, new RectangleF(170 + i % 2 * 480, 280 + i / 2 * 120, 440, 86));
        }
        var bottom = new[] { ("previous", session.View == "image" ? "Anterior" : "Página anterior"),
            ("next", session.View == "image" ? "Próxima" : "Próxima página"), ("zoomOut", "Zoom −"), ("fit", "Ajustar"), ("zoomIn", "Zoom +"),
            ("pin", session.Pinned ? "Dashboard" : "Fixar"), ("recenter", "Centralizar"), ("back", "Voltar"), ("close", "Fechar") };
        for (var i = 0; i < bottom.Length; i++)
        {
            var enabled = bottom[i].Item1 switch { "previous" => session.CanPrevious, "next" => session.CanNext,
                "zoomOut" or "zoomIn" or "fit" => session.View == "image", "back" => session.IsLibrary || session.View == "panel", _ => true };
            yield return new(bottom[i].Item1, bottom[i].Item2, new RectangleF(32 + i * 135, 694, 123, 62), enabled);
        }
    }

    public static string Hit(VrGallerySession session, float x, float y)
    {
        if (!float.IsFinite(x) || !float.IsFinite(y)) return "";
        foreach (var control in Controls(session))
            if (control.Enabled && control.Bounds.Contains(x, y)) return control.Action;
        if (session.View is "image" or "panel") return "";
        var count = session.View == "roots" ? session.Roots.Count : session.Items.Count;
        for (var i = 0; i < count; i++) if (Tile(i).Contains(x, y)) return "open:" + i;
        return "";
    }
}

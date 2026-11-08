using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Media.Imaging;
using PixelFormats = System.Windows.Media.PixelFormats;

namespace Xennex.Services.Vr;

internal static class VrPanelRenderer
{
    public static byte[] Render(VrGallerySession session, Func<string, Stream> openImage) => Render(session, openImage, openImage);

    public static byte[] Render(VrGallerySession session, Func<string, Stream> openImage, Func<string, Stream> openThumbnail)
    {
        using var panel = new Bitmap(VrGallerySession.Width, VrGallerySession.Height, PixelFormat.Format32bppArgb);
        using (var graphics = Graphics.FromImage(panel))
        using (var foreground = new SolidBrush(Color.FromArgb(235, 234, 244)))
        using (var subtle = new SolidBrush(Color.FromArgb(179, 180, 198)))
        using (var accent = new SolidBrush(Color.FromArgb(151, 76, 190)))
        using (var button = new SolidBrush(Color.FromArgb(40, 38, 57)))
        using (var titleFont = new Font("Segoe UI", 23, FontStyle.Bold))
        using (var bodyFont = new Font("Segoe UI", 13))
        using (var format = new StringFormat { Trimming = StringTrimming.EllipsisCharacter, FormatFlags = StringFormatFlags.NoWrap })
        {
            graphics.Clear(Color.FromArgb(19, 18, 29));
            graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
            graphics.DrawString("Xennex · Biblioteca", titleFont, foreground, 32, 16);
            var snapshot = session.Snapshot("running");
            var status = session.View == "image" ? $"{snapshot.Index + 1} / {snapshot.Count} · {session.Current?.Name}" :
                session.View == "panel" ? "Tamanho e distância do painel" :
                $"{(session.View == "explorer" ? "Explorador" : session.View == "roots" ? "Acervos" : "Galeria")} · {session.Location} · {snapshot.Count} itens · Página {snapshot.Index / VrGallerySession.PageSize + 1}";
            graphics.DrawString(status, bodyFont, subtle, new RectangleF(32, 61, 1216, 30), format);
            graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
            if (session.View == "image" && session.Current != null)
                DrawImage(graphics, session.Current.Id, openImage, session.IsLibrary ? new RectangleF(32, 164, 1216, 506) : new RectangleF(32, 108, 1216, 562), 1600, session.Zoom, bodyFont, subtle);
            else if (session.View == "panel")
            {
                graphics.DrawString($"Largura {session.WidthMeters:0.00} m · Distância {session.DistanceMeters:0.00} m", titleFont, foreground, 170, 180);
                graphics.DrawString("A distância vale para o painel fixado. Voltar retoma sua imagem ou pasta.", bodyFont, subtle, 170, 550);
            }
            else if (session.View != "image")
            {
                var count = session.View == "roots" ? session.Roots.Count : session.Items.Count;
                for (var i = 0; i < count; i++)
                {
                    var bounds = VrPanelLayout.Tile(i);
                    graphics.FillRectangle(button, bounds);
                    var item = session.View == "roots" ? null : session.Items[i];
                    var label = item?.Name ?? Path.GetFileName(session.Roots[i].Path.TrimEnd('\\', '/'));
                    if (item?.IsImage == true && item.Available)
                        DrawImage(graphics, item.Id, openThumbnail, new RectangleF(bounds.X + 8, bounds.Y + 6, bounds.Width - 16, 112), 360, 1, bodyFont, subtle);
                    else
                    {
                        var description = item == null ? (session.Roots[i].Online ? "ACERVO" : "ACERVO OFFLINE") : item.IsDirectory ? "PASTA" : "ARQUIVO";
                        graphics.DrawString(description, titleFont, subtle, bounds.X + 14, bounds.Y + 26);
                    }
                    graphics.DrawString(label, bodyFont, foreground, new RectangleF(bounds.X + 12, bounds.Bottom - 34, bounds.Width - 24, 26), format);
                }
                if (count == 0) graphics.DrawString("Nenhum item nesta visão. Use Acervos ou mude para Explorador.", bodyFont, subtle, 100, 370);
            }
            using var centered = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            foreach (var control in VrPanelLayout.Controls(session))
            {
                graphics.FillRectangle(control.Action == session.View || control.Action == "pin" && session.Pinned ? accent : button, control.Bounds);
                graphics.DrawString(control.Label, bodyFont, control.Enabled ? foreground : subtle, control.Bounds, centered);
                if (!control.Enabled) { using var dim = new SolidBrush(Color.FromArgb(130, 19, 18, 29)); graphics.FillRectangle(dim, control.Bounds); }
            }
            var hint = session.Notice.Length > 0 ? session.Notice : session.View == "panel" ? "Ajuste o painel e use Voltar para retomar a navegação." :
                session.View == "image" ? $"Gatilho: clicar · Zoom {session.Zoom * 100:0}% · Anterior/Próxima: trocar imagem" : "Gatilho: abrir imagem ou pasta · Anterior/Próxima: mudar página";
            graphics.DrawString(hint, bodyFont, subtle, new RectangleF(32, 768, 1216, 26), format);
        }
        var data = panel.LockBits(new Rectangle(0, 0, panel.Width, panel.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        var pixels = new byte[panel.Width * panel.Height * 4];
        try { Marshal.Copy(data.Scan0, pixels, 0, pixels.Length); }
        finally { panel.UnlockBits(data); }
        for (var pixel = 0; pixel < pixels.Length; pixel += 4) (pixels[pixel], pixels[pixel + 2]) = (pixels[pixel + 2], pixels[pixel]);
        return pixels;
    }

    private static void DrawImage(Graphics graphics, string id, Func<string, Stream> open, RectangleF area, int limit, float zoom, Font font, Brush fallback)
    {
        try
        {
            using var stream = open(id);
            using var image = Decode(stream, limit);
            var state = graphics.Save();
            try
            {
                graphics.SetClip(area);
                var scale = Math.Min(area.Width / image.Width, area.Height / image.Height) * zoom;
                var width = image.Width * scale; var height = image.Height * scale;
                graphics.DrawImage(image, area.X + (area.Width - width) / 2, area.Y + (area.Height - height) / 2, width, height);
            }
            finally { graphics.Restore(state); }
        }
        catch (Exception error) when (error is IOException or ArgumentException or NotSupportedException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
        {
            AppLog.Error("VR image preview", error);
            graphics.DrawString("Prévia indisponível", font, fallback, area);
        }
    }

    private static Bitmap Decode(Stream stream, int limit)
    {
        var decoded = new BitmapImage();
        var dimensions = BitmapDecoder.Create(stream, BitmapCreateOptions.DelayCreation, BitmapCacheOption.None).Frames[0];
        var ratio = Math.Min(1d, (double)limit / Math.Max(dimensions.PixelWidth, dimensions.PixelHeight));
        stream.Position = 0;
        decoded.BeginInit(); decoded.CacheOption = BitmapCacheOption.OnLoad;
        decoded.DecodePixelWidth = Math.Max(1, (int)(dimensions.PixelWidth * ratio));
        decoded.DecodePixelHeight = Math.Max(1, (int)(dimensions.PixelHeight * ratio));
        decoded.StreamSource = stream; decoded.EndInit(); decoded.Freeze();
        var converted = new FormatConvertedBitmap(decoded, PixelFormats.Bgra32, null, 0);
        var source = new Bitmap(converted.PixelWidth, converted.PixelHeight, PixelFormat.Format32bppArgb);
        var data = source.LockBits(new Rectangle(0, 0, source.Width, source.Height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
        try { converted.CopyPixels(System.Windows.Int32Rect.Empty, data.Scan0, data.Stride * source.Height, data.Stride); }
        catch { source.UnlockBits(data); source.Dispose(); throw; }
        source.UnlockBits(data);
        return source;
    }
}

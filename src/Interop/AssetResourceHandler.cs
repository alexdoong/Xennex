using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;
using Xennex.Services;
using Xennex.Services.Assets;

namespace Xennex.Interop;

internal static class AssetResourceHandler
{
    public static void Attach(CoreWebView2 view, AssetLibraryService library)
    {
        // WebView2 does not fire WebResourceRequested for SetVirtualHostNameToFolderMapping.
        // Keep media on a separate, unmapped host and answer every request locally.
        view.AddWebResourceRequestedFilter("https://xennex-media.invalid/*", CoreWebView2WebResourceContext.All);
        view.WebResourceRequested += async (_, args) =>
        {
            if (!Uri.TryCreate(args.Request.Uri, UriKind.Absolute, out var uri) ||
                uri.Scheme != "https" || uri.Host != "xennex-media.invalid") return;
            using var deferral = args.GetDeferral();
            Stream content = null;
            try
            {
                if (uri.Segments.Length != 4 || uri.Segments[1] != "__asset/")
                    throw new ArgumentException("Recurso inválido.");
                var id = uri.Segments[2].TrimEnd('/');
                var variant = uri.Segments[3].TrimEnd('/');
                if (!Guid.TryParseExact(id, "N", out var assetGuid) || assetGuid == Guid.Empty || variant is not ("thumb" or "preview"))
                    throw new ArgumentException("Recurso inválido.");
                var result = await Task.Run(() => library.OpenMedia(id, variant));
                content = result.content;
                args.Response = view.Environment.CreateWebResourceResponse(content, 200, "OK",
                    $"Content-Type: {result.contentType}\r\nCache-Control: private, max-age=3600\r\nX-Content-Type-Options: nosniff");
                content = null;
            }
            catch (Exception error)
            {
                AppLog.Error("Assets.Media", error);
                content?.Dispose();
                args.Response = view.Environment.CreateWebResourceResponse(null, 404, "Not Found", "Cache-Control: no-store");
            }
        };
    }
}

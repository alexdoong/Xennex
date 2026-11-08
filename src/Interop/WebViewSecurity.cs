using System;
using System.Diagnostics;
using Microsoft.Web.WebView2.Core;
using Xennex.Services;
using Xennex.Services.Security;

namespace Xennex.Interop
{
    internal static class WebViewSecurity
    {
        public static void Configure(CoreWebView2 view)
        {
            view.NavigationStarting += (_, request) => { request.Cancel = !LocalRequestPolicy.IsAppDocument(request.Uri); };
            view.FrameNavigationStarting += (_, request) => { request.Cancel = true; };
            view.NewWindowRequested += (_, request) =>
            {
                request.Handled = true;
                if (!request.IsUserInitiated || !Uri.TryCreate(request.Uri, UriKind.Absolute, out var uri) ||
                    (uri.Scheme != "https" && uri.Scheme != "http")) return;
                try { Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true }); }
                catch (Exception error) { AppLog.Error("ExternalLink", error); }
            };
            view.PermissionRequested += (_, request) =>
            {
                bool trusted = Uri.TryCreate(request.Uri, UriKind.Absolute, out var uri) &&
                    uri.Scheme == "https" && uri.Host == "appassets" && uri.IsDefaultPort && uri.UserInfo == "";
                request.State = trusted ? CoreWebView2PermissionState.Default : CoreWebView2PermissionState.Deny;
                if (trusted && (request.PermissionKind == CoreWebView2PermissionKind.Camera ||
                    request.PermissionKind == CoreWebView2PermissionKind.Microphone || (int)request.PermissionKind == 14))
                    request.State = CoreWebView2PermissionState.Allow;
            };
        }
    }
}

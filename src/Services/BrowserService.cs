using System;
using System.Diagnostics;

namespace Xennex.Services
{
    public static class BrowserService
    {
        public static void Open(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                AppLog.Error("Browser", ex);
            }
        }
    }
}

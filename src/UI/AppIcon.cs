using System;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media.Imaging;
using Xennex.Services;

namespace Xennex.UI
{
    internal static class AppIcon
    {
        public static BitmapSource LoadWindowIcon()
        {
            try
            {
                string executable = Environment.ProcessPath;
                if (string.IsNullOrEmpty(executable)) return null;
                using var icon = System.Drawing.Icon.ExtractAssociatedIcon(executable);
                if (icon == null) return null;
                var image = Imaging.CreateBitmapSourceFromHIcon(
                    icon.Handle, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
                image.Freeze();
                return image;
            }
            catch (Exception ex)
            {
                AppLog.Error("WindowIcon", ex);
                return null;
            }
        }
    }
}

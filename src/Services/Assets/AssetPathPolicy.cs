using System;
using System.IO;

namespace Xennex.Services.Assets;

internal static class AssetPathPolicy
{
    public static void ValidateDirectoryAncestors(string path)
    {
        var current = new DirectoryInfo(Path.GetFullPath(path));
        if (!current.Exists) throw new DirectoryNotFoundException("Pasta indisponível.");
        while (current != null)
        {
            if ((current.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new UnauthorizedAccessException("Pastas vinculadas não são suportadas na Biblioteca.");
            current = current.Parent;
        }
    }
}

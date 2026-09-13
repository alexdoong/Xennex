using System;
using System.Diagnostics;
using System.IO;

namespace Xennex.Services
{
    /// <summary>Local diagnostics; logging failures must never hide the original error.</summary>
    public static class AppLog
    {
        private static readonly object Sync = new();

        public static void Error(string source, Exception error)
        {
            string message = $"{DateTime.Now:O} [{source}] {error}";
            Trace.TraceError(message);
            Console.Error.WriteLine(message);
            try
            {
                lock (Sync)
                {
                    string directory = Path.Combine(AppContext.BaseDirectory, "logs");
                    Directory.CreateDirectory(directory);
                    File.AppendAllText(Path.Combine(directory, "xennex.log"), message + Environment.NewLine);
                }
            }
            catch (Exception logError)
            {
                Trace.TraceError($"Could not write Xennex log: {logError.Message}");
            }
        }
    }
}

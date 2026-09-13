using Xennex.Services;

namespace Xennex.Models
{
    public class UpdateCheckResult
    {
        public bool Success { get; set; }
        public bool HasUpdate { get; set; }
        public string CurrentVersion { get; set; } = UpdateService.CurrentVersion;
        public string LatestVersion { get; set; } = "";
        public string ReleaseTitle { get; set; } = "";
        public string ReleaseNotes { get; set; } = "";
        public string HtmlUrl { get; set; } = "";
        public string DownloadUrl { get; set; } = "";
        public long AssetSize { get; set; }
        public string ErrorMessage { get; set; } = "";
    }

}

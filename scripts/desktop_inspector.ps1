<#
.SYNOPSIS
    Desktop UI Inspector & Window Capture Utility for Antigravity AI Agent.
    Allows capturing precise screenshots of WPF, Win32, and Desktop windows (like Xennex, Codex)
    for visual verification and regression testing.

.PARAMETER Target
    Target window title pattern, process name, 'active' (for foreground window), or 'desktop' (for full screen).
    Default is 'Xennex'.

.PARAMETER OutputPath
    Destination file path for the captured PNG image. If omitted, saves to artifacts folder.

.PARAMETER CaptureMode
    'Auto' (tries PrintWindow with PW_RENDERFULLCONTENT, falls back to CopyFromScreen),
    'PrintWindow' (direct window DC capture), or 'ScreenCopy' (desktop bounds capture).

.PARAMETER JsonOutput
    Outputs machine-readable JSON containing window coordinates, state, and image path.
#>

[CmdletBinding()]
param(
    [string]$Target = "Xennex",
    [string]$OutputPath = "",
    [ValidateSet("Auto", "PrintWindow", "ScreenCopy")]
    [string]$CaptureMode = "Auto",
    [switch]$BringToFront,
    [switch]$JsonOutput
)

Add-Type -AssemblyName System.Drawing, System.Windows.Forms

# Win32 P/Invoke definition
$win32TypeDef = @"
using System;
using System.Runtime.InteropServices;

public class Win32Inspector {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBkgnd, uint nFlags);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    public const uint PW_RENDERFULLCONTENT = 0x00000002;
    public const int SW_RESTORE = 9;
}
"@

if (-not ([System.Management.Automation.PSTypeName]'Win32Inspector').Type) {
    Add-Type -TypeDefinition $win32TypeDef -ReferencedAssemblies "System.Drawing.dll"
}

# Resolve Default Output Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $artifactDir = Join-Path ([System.IO.Path]::GetTempPath()) 'Xennex\Screenshots'
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $cleanTarget = ($Target -replace '[^a-zA-Z0-9_-]', '_').Trim('_')
    $OutputPath = Join-Path $artifactDir "screenshot_${cleanTarget}_${timestamp}.png"
}

$outputDir = [System.IO.Path]::GetDirectoryName($OutputPath)
if (-not [string]::IsNullOrEmpty($outputDir) -and -not (Test-Path $outputDir)) {
    New-Item -Path $outputDir -ItemType Directory -Force | Out-Null
}

function Capture-FullScreen([string]$savePath) {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)
    $bmp.Save($savePath, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bmp.Dispose()
    return @{
        Success = $true
        Mode = "FullScreen"
        Width = $bounds.Width
        Height = $bounds.Height
        OutputPath = $savePath
    }
}

if ($Target -eq "desktop") {
    $result = Capture-FullScreen -savePath $OutputPath
    if ($JsonOutput) { $result | ConvertTo-Json; exit 0 }
    Write-Output "Full screen captured to: $OutputPath"
    exit 0
}

# Resolve Target Window HWND
$targetHwnd = [IntPtr]::Zero
$windowTitle = ""

if ($Target -eq "active" -or $Target -eq "foreground") {
    $targetHwnd = [Win32Inspector]::GetForegroundWindow()
    $sb = New-Object System.Text.StringBuilder 256
    [void][Win32Inspector]::GetWindowText($targetHwnd, $sb, 256)
    $windowTitle = $sb.ToString()
} else {
    # Search by process or window title
    $processes = Get-Process | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero }

    # 1. Match by Process Name
    $proc = $processes | Where-Object { $_.ProcessName -like "*$Target*" } | Select-Object -First 1
    if (-not $proc) {
        # 2. Match by Window Title
        $proc = $processes | Where-Object { $_.MainWindowTitle -like "*$Target*" } | Select-Object -First 1
    }

    if ($proc) {
        $targetHwnd = $proc.MainWindowHandle
        $windowTitle = $proc.MainWindowTitle
    }
}

if ($targetHwnd -eq [IntPtr]::Zero) {
    # Window not found, fallback to desktop capture with warning
    $errObj = @{
        Success = $false
        Error = "Window matching '$Target' not found among running processes."
        RunningWindows = ($processes | Select-Object -Property ProcessName, MainWindowTitle | Select-Object -First 15)
    }
    if ($JsonOutput) { $errObj | ConvertTo-Json; exit 1 }
    Write-Error "Window matching '$Target' not found."
    exit 1
}

# Handle Minimized State
if ([Win32Inspector]::IsIconic($targetHwnd)) {
    if ($BringToFront) {
        [void][Win32Inspector]::ShowWindow($targetHwnd, [Win32Inspector]::SW_RESTORE)
        Start-Sleep -Milliseconds 300
    }
}

if ($BringToFront) {
    [void][Win32Inspector]::SetForegroundWindow($targetHwnd)
    Start-Sleep -Milliseconds 200
}

# Get Window Dimensions
$rect = New-Object Win32Inspector+RECT
[void][Win32Inspector]::GetWindowRect($targetHwnd, [ref]$rect)
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top

if ($width -le 0 -or $height -le 0) {
    $width = 800
    $height = 600
}

$captured = $false
$bmp = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)

if ($CaptureMode -eq "PrintWindow" -or $CaptureMode -eq "Auto") {
    $hdc = $graphics.GetHdc()
    try {
        $pwSuccess = [Win32Inspector]::PrintWindow($targetHwnd, $hdc, [Win32Inspector]::PW_RENDERFULLCONTENT)
        if ($pwSuccess) {
            $captured = $true
        }
    } finally {
        $graphics.ReleaseHdc($hdc)
    }
}

# Fallback to CopyFromScreen if PrintWindow returned black or failed
if (-not $captured -or $CaptureMode -eq "ScreenCopy") {
    try {
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, [System.Drawing.Size]::new($width, $height), [System.Drawing.CopyPixelOperation]::SourceCopy)
        $captured = $true
    } catch {
        # Fallback to full screen if window coordinates were offscreen
        $graphics.Dispose()
        $bmp.Dispose()
        $result = Capture-FullScreen -savePath $OutputPath
        $result["Warning"] = "Failed window screen copy, captured full desktop."
        if ($JsonOutput) { $result | ConvertTo-Json; exit 0 }
        Write-Output "Captured desktop fallback to $OutputPath"
        exit 0
    }
}

$bmp.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()

$result = @{
    Success = $true
    Target = $Target
    WindowTitle = $windowTitle
    Handle = $targetHwnd.ToInt64()
    Bounds = @{
        Left = $rect.Left
        Top = $rect.Top
        Width = $width
        Height = $height
    }
    OutputPath = $OutputPath
    Timestamp = (Get-Date -Format "o")
}

if ($JsonOutput) {
    $result | ConvertTo-Json
} else {
    Write-Output "Successfully captured '$windowTitle' ($width x $height) to: $OutputPath"
}
exit 0

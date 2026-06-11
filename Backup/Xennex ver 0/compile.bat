@echo off
title Wacom & Audio Latency Controller Builder
echo ===================================================
echo Building Wacom & Audio Latency Controller...
echo ===================================================
echo.

set CSC_PATH="C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if not exist %CSC_PATH% (
    echo [ERROR] C# Compiler not found at %CSC_PATH%
    echo Make sure .NET Framework 4.5+ is installed.
    pause
    exit /b 1
)

echo Compiling Program.cs...
%CSC_PATH% /target:winexe /out:WacomRealController.exe /r:System.Windows.Forms.dll,System.Drawing.dll,System.dll,System.ServiceProcess.dll,System.Core.dll Program.cs

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ===================================================
    echo [SUCCESS] Compilation successful!
    echo Created WacomRealController.exe
    echo ===================================================
) else (
    echo.
    echo [ERROR] Compilation failed! Check the errors above.
)
echo.
pause

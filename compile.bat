@echo off
title Wacom ^& Audio Latency Controller Builder
echo ===================================================
echo Building Wacom ^& Audio Latency Controller...
echo ===================================================
echo.

:: Check if dotnet CLI is installed and available
where dotnet >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found .NET SDK! Building project with dotnet...
    dotnet build -c Release
    goto end_build
)

:: Try to find modern Visual Studio compiler (Roslyn) first
set CSC_PATH="C:\Program Files\Microsoft Visual Studio\18\Insiders\MSBuild\Current\Bin\Roslyn\csc.exe"

if not exist %CSC_PATH% (
    :: Fallback to default system compiler (only supports C# 5)
    set CSC_PATH="C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)

if not exist %CSC_PATH% (
    echo [ERROR] .NET SDK or C# Compiler not found!
    echo Please install the .NET SDK 8.0+ to compile this project.
    echo You can install it by running: winget install Microsoft.DotNet.SDK.8
    pause
    exit /b 1
)

echo [WARNING] .NET SDK not found. Attempting direct fallback compilation...
echo Using compiler: %CSC_PATH%
echo Compiling source files recursively...
%CSC_PATH% /target:winexe /out:WacomRealController.exe /r:System.Windows.Forms.dll,System.Drawing.dll,System.dll,System.ServiceProcess.dll,System.Core.dll /recurse:src\*.cs

:end_build
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

@echo off
title Wacom & Audio Latency Controller Builder
echo ===================================================
echo Building Wacom & Audio Latency Controller...
echo ===================================================
echo.

:: Try to find modern Visual Studio compiler (Roslyn) first
set CSC_PATH="C:\Program Files\Microsoft Visual Studio\18\Insiders\MSBuild\Current\Bin\Roslyn\csc.exe"

if not exist %CSC_PATH% (
    :: Fallback to default system compiler (only supports C# 5)
    set CSC_PATH="C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)

if not exist %CSC_PATH% (
    echo [ERROR] C# Compiler not found!
    echo Make sure Visual Studio or .NET Framework 4.5+ is installed.
    pause
    exit /b 1
)

echo Using compiler: %CSC_PATH%
echo Compiling source files recursively...
%CSC_PATH% /target:winexe /out:WacomRealController.exe /r:System.Windows.Forms.dll,System.Drawing.dll,System.dll,System.ServiceProcess.dll,System.Core.dll /recurse:src\*.cs

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

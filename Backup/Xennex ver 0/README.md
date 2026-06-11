# Wacom & Audio Latency Controller

A lightweight, standalone Windows desktop dashboard to manage Wacom tablet drivers and the **REAL** (Reduce Audio Latency) process. 

Designed to look modern and premium, this app replaces ugly command prompts with a dark-mode graphical controller that sits in your system tray and monitors driver/latency status in real-time.

## Features

- **Wacom Driver Control**: One-click buttons to disable and enable Wacom drivers (runs operations with admin privilege UAC elevation).
- **REAL.exe Controller**: Starts the audio latency reduction engine in a completely hidden background process (no console windows shown).
- **Real-Time Logs**: Redirects output from `REAL.exe` and displays it in a scrollable console window within the app.
- **Auto-Location**: Automatically scans for `REAL.exe` in the workspace or subfolders and configures the path.
- **System Tray Integration**: Hides to the system tray on close or minimize. Right-click the tray icon to start/stop engines, change driver states, or exit.
- **Highly Resource-Efficient**: Coded in native C# WinForms/GDI+ with double-buffering and explicit handle disposal to prevent GDI resource or RAM leaks.

## How to Build

No Visual Studio, SDKs, or compiler tools need to be downloaded or configured. The app compiles using the C# compiler (`csc.exe`) built directly into Windows.

1. Double-click `compile.bat`.
2. Upon success, `WacomRealController.exe` will be generated in the folder.
3. Run `WacomRealController.exe` to launch the dashboard.

## File Structure

- `Program.cs` - The C# source code for the dashboard.
- `compile.bat` - The automated compiler script.
- `DisableWacomDrivers.bat` - Batch script to disable/reset drivers (admin mode).
- `EnableWacomDrivers.bat` - Batch script to enable/reset drivers (admin mode).
- `config.txt` - Stores the absolute path to your `REAL.exe` executable (generated automatically).

## Deployment & Git

This folder is structured as a standalone project. To push it to your Git:
1. Open terminal inside the `WacomRealController` directory.
2. Run `git init`.
3. Create your remote repository and push!

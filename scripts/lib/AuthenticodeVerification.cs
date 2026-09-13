using System;
using System.Runtime.InteropServices;
namespace Xennex.Build {
 public static class AuthenticodeVerification {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  struct FileInfo { public uint Size; [MarshalAs(UnmanagedType.LPWStr)] public string Path; public IntPtr Handle, Subject; }
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  struct TrustData {
   public uint Size; public IntPtr PolicyCallback, ClientData; public uint UiChoice, Revocation, UnionChoice;
   public IntPtr File; public uint StateAction; public IntPtr StateData, Url; public uint ProviderFlags, UiContext; public IntPtr SignatureSettings;
  }
  [DllImport("wintrust.dll", ExactSpelling = true, CharSet = CharSet.Unicode)]
  static extern uint WinVerifyTrust(IntPtr window, [In] ref Guid action, ref TrustData data);
  public static uint Check(string path) {
   var file = new FileInfo { Size = (uint)Marshal.SizeOf(typeof(FileInfo)), Path = path };
   IntPtr pointer = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(FileInfo)));
   Marshal.StructureToPtr(file, pointer, false);
   var data = new TrustData { Size = (uint)Marshal.SizeOf(typeof(TrustData)), UiChoice = 2, UnionChoice = 1, File = pointer, StateAction = 1 };
   var action = new Guid("00AAC56B-CD44-11D0-8CC2-00C04FC295EE");
   try { return WinVerifyTrust(new IntPtr(-1), ref action, ref data); }
   finally {
    data.StateAction = 2; WinVerifyTrust(new IntPtr(-1), ref action, ref data);
    Marshal.DestroyStructure(pointer, typeof(FileInfo)); Marshal.FreeHGlobal(pointer);
   }
  }
 }
}

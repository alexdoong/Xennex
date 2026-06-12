using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Windows.Forms;

namespace WacomRealController
{
    public class MainForm : Form
    {
        // ── Services ───────────────────────────────────────────────────────────
        private readonly ConfigService configService = new ConfigService();
        private readonly WacomService wacomService = new WacomService();
        private readonly RealEngineService realEngineService = new RealEngineService();

        // ── Core UI ────────────────────────────────────────────────────────────
        private Panel  pnlHeader, pnlNavigation, pnlContent;
        private Label  lblTitle, lblSubtitle;
        private Button btnMinimize, btnClose, btnSidebarToggle, btnPin;
        private Button btnTabOsu, btnTabWuWa, btnTabSettings;

        // ── Tab Controls ───────────────────────────────────────────────────────
        private OsuTab      osuTab;
        private WuWaTab     wuWaTab;
        private SettingsTab settingsTab;
        private PullTab     pullTab;

        // ── Tray ──────────────────────────────────────────────────────────────
        private NotifyIcon   notifyIcon;
        private ContextMenu  trayMenu;
        private Icon         appIcon;

        // ── App State ────────────────────────────────────────────────────────
        private bool isSidebarMode   = false;
        private bool isPinned        = false;   // auto-hide ON by default in sidebar
        private bool isSlidOut       = false;
        private bool isFirstMinimize = true;
        private int  currentTab      = 0;
        private bool ignoreHoverUntilMouseLeave = false;

        private bool  formDragging   = false;
        private Point dragStartPoint = Point.Empty;
        private Rectangle previousBounds = new Rectangle(100, 100, 820, 560);
        private const int SLIDE_SPEED = 22;

        private System.Windows.Forms.Timer statusTimer;
        private System.Windows.Forms.Timer slideTimer;

        public MainForm()
        {
            this.SuspendLayout();
            BuildUI();
            this.ResumeLayout(false);

            SetupStyles();
            
            // Load configs
            configService.LoadConfig();

            configService.OnConfigChanged += () => {
                if (isSidebarMode)
                {
                    this.BeginInvoke((MethodInvoker)delegate {
                        var scr = GetTargetSidebarScreen();
                        int startOffset = configService.Config.HideSidebarPullTab ? 0 : 26;
                        this.Width = 280 + startOffset;
                        this.Height = 680;
                        this.Top = scr.WorkingArea.Top + (scr.WorkingArea.Height - this.Height) / 2;

                        LayoutControls();
                        if (isSlidOut)
                        {
                            this.Left = scr.WorkingArea.Right - startOffset;
                            
                            if (configService.Config.HideSidebarPullTab)
                            {
                                if (this.Region != null) { this.Region.Dispose(); this.Region = null; }
                            }
                            else
                            {
                                if (this.Region != null) this.Region.Dispose();
                                this.Region = new Region(new Rectangle(0, pullTab.Top, pullTab.Width, pullTab.Height));
                            }
                        }
                    });
                }
            };

            SetActiveTab(0);
            LayoutControls();

            statusTimer = new System.Windows.Forms.Timer { Interval = 2000 };
            statusTimer.Tick += (s, e) => {
                if (osuTab != null) osuTab.CheckStatus();
            };
            statusTimer.Start();

            slideTimer = new System.Windows.Forms.Timer { Interval = 16 };
            slideTimer.Tick += SlideTimer_Tick;
            slideTimer.Start();

            if (settingsTab.StartRealOnBoot && File.Exists(configService.Config.RealExePath))
                realEngineService.Start(configService.Config.RealExePath);
        }

        private void BuildUI()
        {
            this.Name            = "MainForm";
            this.Text            = "Xennex";
            this.Size            = new Size(820, 560);
            this.MinimumSize     = new Size(360, 480);
            this.FormBorderStyle = FormBorderStyle.None;
            this.StartPosition   = FormStartPosition.CenterScreen;
            this.BackColor       = Color.FromArgb(14, 14, 16);
            this.appIcon         = CreateAppIcon();
            this.Icon            = this.appIcon;
            this.SizeChanged    += (s, e) => LayoutControls();

            BuildHeader();
            BuildNavigation();

            // Instantiate tabs
            osuTab = new OsuTab(wacomService, realEngineService, configService);
            wuWaTab = new WuWaTab(configService);
            settingsTab = new SettingsTab(configService, osuTab.AppendLog);

            pullTab = new PullTab();
            pullTab.Visible = false;
            pullTab.Click += (s, e) => ToggleRevealState();

            pnlContent = new Panel
            {
                Location = new Point(60, 65),
                Size     = new Size(760, 495),
                BackColor = Color.FromArgb(14, 14, 16)
            };
            
            // Set Dock to Fill for children controls so they size with pnlContent
            osuTab.Dock = DockStyle.Fill;
            wuWaTab.Dock = DockStyle.Fill;
            settingsTab.Dock = DockStyle.Fill;

            pnlContent.Controls.AddRange(new Control[] { osuTab, wuWaTab, settingsTab });

            this.Controls.AddRange(new Control[] { pnlHeader, pnlNavigation, pnlContent, pullTab });
            BuildTray();
        }

        private void BuildHeader()
        {
            pnlHeader = new Panel
            {
                Location  = new Point(0, 0),
                Size      = new Size(820, 65),
                BackColor = Color.FromArgb(20, 20, 22)
            };
            pnlHeader.MouseDown += Header_MouseDown;
            pnlHeader.MouseMove += Header_MouseMove;
            pnlHeader.MouseUp   += Header_MouseUp;

            lblTitle = new Label
            {
                Text      = "XENNEX",
                Font      = new Font("Segoe UI", 11.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(244, 244, 245),
                Location  = new Point(20, 12),
                AutoSize  = true
            };
            WireHeaderDrag(lblTitle);

            lblSubtitle = new Label
            {
                Text      = "osu! tools · Wuthering Waves",
                Font      = new Font("Segoe UI", 8F),
                ForeColor = Color.FromArgb(141, 141, 150),
                Location  = new Point(20, 36),
                AutoSize  = true
            };
            WireHeaderDrag(lblSubtitle);

            btnSidebarToggle = Btn("⬛ Sidebar", new Point(530, 17), new Size(95, 30),
                Color.FromArgb(39, 39, 42), Color.FromArgb(228, 228, 231));
            btnSidebarToggle.Font   = new Font("Segoe UI", 8F, FontStyle.Bold);
            btnSidebarToggle.Click += (s, e) => ToggleSidebarMode();

            btnPin = Btn("📌", new Point(635, 17), new Size(30, 30),
                Color.FromArgb(39, 39, 42), Color.FromArgb(228, 228, 231));
            btnPin.Font    = new Font("Segoe UI", 10F);
            btnPin.Visible = false;
            btnPin.Click  += (s, e) => TogglePinMode();
            ToolTip ttPin = new ToolTip();
            ttPin.SetToolTip(btnPin, "Toggle Auto-Hide");

            btnMinimize = Btn("—", new Point(675, 0), new Size(45, 65),
                Color.Transparent, Color.FromArgb(200, 200, 200));
            btnMinimize.Font   = new Font("Segoe UI", 10F, FontStyle.Bold);
            btnMinimize.Click += (s, e) => this.WindowState = FormWindowState.Minimized;

            btnClose = Btn("×", new Point(720, 0), new Size(45, 65),
                Color.Transparent, Color.FromArgb(200, 200, 200));
            btnClose.Font   = new Font("Segoe UI", 14F, FontStyle.Bold);
            btnClose.FlatAppearance.MouseOverBackColor = Color.FromArgb(196, 43, 28);
            btnClose.Click += (s, e) =>
            {
                if (isSidebarMode)
                {
                    ToggleSidebarMode();
                }

                if (settingsTab != null && settingsTab.CloseToTray) MinimizeToTray();
                else ShutdownApp();
            };

            pnlHeader.Controls.AddRange(new Control[] {
                lblTitle, lblSubtitle, btnSidebarToggle, btnPin, btnMinimize, btnClose });
        }

        private void WireHeaderDrag(Control c)
        {
            c.MouseDown += Header_MouseDown;
            c.MouseMove += Header_MouseMove;
            c.MouseUp   += Header_MouseUp;
        }

        private void BuildNavigation()
        {
            pnlNavigation = new Panel
            {
                Location  = new Point(0, 65),
                Size      = new Size(60, 495),
                BackColor = Color.FromArgb(18, 18, 20)
            };
            pnlNavigation.Paint += Navigation_Paint;

            btnTabOsu = NavBtn("🎯", 15); btnTabOsu.Click += (s, e) => SetActiveTab(0);
            new ToolTip().SetToolTip(btnTabOsu, "osu! Utilities");

            btnTabWuWa = NavBtn("🌊", 75); btnTabWuWa.Click += (s, e) => SetActiveTab(1);
            new ToolTip().SetToolTip(btnTabWuWa, "Wuthering Waves");

            btnTabSettings = NavBtn("⚙", 135); btnTabSettings.Click += (s, e) => SetActiveTab(2);
            new ToolTip().SetToolTip(btnTabSettings, "Settings");

            pnlNavigation.Controls.AddRange(new Control[] { btnTabOsu, btnTabWuWa, btnTabSettings });
        }

        private Button NavBtn(string emoji, int top)
        {
            var b = Btn(emoji, new Point(10, top), new Size(40, 40),
                Color.FromArgb(28, 28, 31), Color.FromArgb(161, 161, 170));
            b.Font = new Font("Segoe UI", 14F);
            return b;
        }

        private void BuildTray()
        {
            trayMenu = new ContextMenu();
            trayMenu.MenuItems.Add("Restore", (s, e) => RestoreFromTray());
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Start REAL", (s, e) => realEngineService.Start(configService.Config.RealExePath));
            trayMenu.MenuItems.Add("Stop REAL",  (s, e) => realEngineService.Stop());
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Enable Wacom",  (s, e) => wacomService.EnableDrivers());
            trayMenu.MenuItems.Add("Disable Wacom", (s, e) => wacomService.DisableDrivers());
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Exit", (s, e) => ShutdownApp());

            notifyIcon = new NotifyIcon
            {
                Icon        = this.appIcon,
                ContextMenu = trayMenu,
                Text        = "Xennex",
                Visible     = false
            };
            notifyIcon.DoubleClick += (s, e) => RestoreFromTray();
        }

        private void SetupStyles()
        {
            this.DoubleBuffered = true;
            this.SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.ResizeRedraw, true);
            this.Paint += (s, e) =>
            {
                if (!isSidebarMode)
                {
                    using (var pen = new Pen(Color.FromArgb(60, 139, 92, 246), 1))
                        e.Graphics.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
                }
            };
        }

        private void Navigation_Paint(object sender, PaintEventArgs e)
        {
            int y = 15 + currentTab * 60;
            Color c = currentTab == 0 ? Color.FromArgb(139, 92, 246) :
                      currentTab == 1 ? Color.FromArgb(6, 182, 212) :
                                        Color.FromArgb(244, 244, 245);
            using (var b = new SolidBrush(c))
                e.Graphics.FillRectangle(b, 0, y + 5, 3, 30);
        }

        private void LayoutControls()
        {
            if (pnlHeader == null) return;
            int w = ClientSize.Width, h = ClientSize.Height;
            int tabW = (isSidebarMode && !configService.Config.HideSidebarPullTab) ? 26 : 0;
            int pad = isSidebarMode ? 0 : 4;

            if (pullTab != null)
            {
                pullTab.Visible = isSidebarMode && !configService.Config.HideSidebarPullTab;
                pullTab.Location = new Point(0, (h - pullTab.Height) / 2);
            }

            pnlHeader.Location = new Point(tabW + pad, pad);
            pnlHeader.Width = w - tabW - (pad * 2);

            int hw = pnlHeader.Width;
            btnClose.Location    = new Point(hw - 45, 0);
            btnMinimize.Location = new Point(hw - 90, 0);

            if (isSidebarMode)
            {
                lblTitle.Text         = "XENNEX";
                lblSubtitle.Visible   = false;
                btnSidebarToggle.Text = "← Back";
                
                int pinx = Math.Max(100, hw - 125);
                btnPin.Location = new Point(pinx, 17);
                btnPin.Visible  = true;

                int sbx = Math.Max(70, pinx - 80);
                btnSidebarToggle.Location = new Point(sbx, 17);
                btnSidebarToggle.Size     = new Size(70, 30);
            }
            else
            {
                lblTitle.Text         = "XENNEX";
                lblSubtitle.Visible   = true;
                btnSidebarToggle.Text = "⬛ Sidebar";
                btnPin.Visible = false;
                
                int sbx = Math.Max(150, hw - 200);
                btnSidebarToggle.Location = new Point(sbx, 17);
                btnSidebarToggle.Size     = new Size(95, 30);
            }

            pnlNavigation.Location = new Point(tabW + pad, 65 + pad);
            pnlNavigation.Height   = h - 65 - (pad * 2);
            pnlContent.Location    = new Point(tabW + 60 + pad, 65 + pad);
            pnlContent.Size        = new Size(w - tabW - 60 - (pad * 2), h - 65 - (pad * 2));
        }

        private void SetActiveTab(int idx)
        {
            currentTab = idx;
            if (osuTab != null) osuTab.Visible = (idx == 0);
            if (wuWaTab != null) wuWaTab.Visible = (idx == 1);
            if (settingsTab != null) settingsTab.Visible = (idx == 2);

            Color inactiveBack = Color.FromArgb(28, 28, 31);
            Color inactiveFore = Color.FromArgb(161, 161, 170);
            btnTabOsu.BackColor      = inactiveBack; btnTabOsu.ForeColor      = inactiveFore;
            btnTabWuWa.BackColor     = inactiveBack; btnTabWuWa.ForeColor     = inactiveFore;
            btnTabSettings.BackColor = inactiveBack; btnTabSettings.ForeColor = inactiveFore;

            if (idx == 0) { btnTabOsu.ForeColor      = Color.FromArgb(139, 92, 246); btnTabOsu.BackColor      = Color.FromArgb(40, 38, 50); }
            if (idx == 1) { btnTabWuWa.ForeColor      = Color.FromArgb(6, 182, 212);  btnTabWuWa.BackColor     = Color.FromArgb(30, 45, 50); }
            if (idx == 2) { btnTabSettings.ForeColor  = Color.White;                   btnTabSettings.BackColor = Color.FromArgb(40, 40, 45); }

            pnlNavigation.Invalidate();
        }

        private void ToggleSidebarMode()
        {
            isSidebarMode = !isSidebarMode;

            if (isSidebarMode)
            {
                previousBounds = this.Bounds;
                var scr = GetTargetSidebarScreen();
                int startOffset = configService.Config.HideSidebarPullTab ? 0 : 26;
                // sw = content width 280 + tab width (26 or 0)
                int sw  = 280 + startOffset;
                this.ShowInTaskbar = false;
                this.Width  = sw;
                this.Height = 680;
                this.Left   = scr.WorkingArea.Right - startOffset; // start collapsed
                this.Top    = scr.WorkingArea.Top + (scr.WorkingArea.Height - this.Height) / 2; // vertically centered
                isPinned    = false;
                isSlidOut   = true;
                this.TopMost = true; // Always on top
                ignoreHoverUntilMouseLeave = false;
                if (pullTab != null) pullTab.IsCollapsed = true;

                if (configService.Config.HideSidebarPullTab)
                {
                    if (this.Region != null) { this.Region.Dispose(); this.Region = null; }
                }
                else
                {
                    if (this.Region != null) this.Region.Dispose();
                    this.Region = GetPullTabRegion();
                }
            }
            else
            {
                isSlidOut = false;
                this.ShowInTaskbar = true;
                this.TopMost = false;
                this.Bounds = previousBounds;
                if (this.Region != null) { this.Region.Dispose(); this.Region = null; }
            }
            LayoutControls();
        }

        private void TogglePinMode()
        {
            isPinned    = !isPinned;
            btnPin.Text = isPinned ? "🔒" : "📌";
            configService.Config.CloseToTray = settingsTab.CloseToTray;
            configService.Config.AutoStart = settingsTab.StartRealOnBoot;
            configService.SaveConfig();

            if (isPinned)
            {
                isSlidOut  = false;
                this.Left  = Screen.FromControl(this).WorkingArea.Right - this.Width;
            }
        }

        private void ToggleRevealState()
        {
            if (!isSidebarMode) return;
            isSlidOut = !isSlidOut;
            if (isSlidOut)
            {
                ignoreHoverUntilMouseLeave = true;
            }
            else
            {
                ignoreHoverUntilMouseLeave = false;
            }
        }

        private Screen GetTargetSidebarScreen()
        {
            int idx = configService.Config.SidebarMonitorIndex;
            var screens = Screen.AllScreens;
            if (idx >= 0 && idx < screens.Length)
            {
                return screens[idx];
            }
            return Screen.PrimaryScreen;
        }

        private Region GetPullTabRegion()
        {
            var path = new GraphicsPath();
            int r = 8;
            int w = pullTab.Width;
            int h = pullTab.Height;
            int y = pullTab.Top;

            path.AddLine(w, y, w, y);
            path.AddLine(w, y + h, w, y + h);
            path.AddArc(0, y + h - 2 * r - 1, 2 * r, 2 * r, 90, 90);
            path.AddArc(0, y, 2 * r, 2 * r, 180, 90);
            path.CloseFigure();
            return new Region(path);
        }

        private void SlideTimer_Tick(object sender, EventArgs e)
        {
            if (!isSidebarMode) return;

            // Fullscreen application active detection to avoid gaming interference
            if (Win32.IsForegroundWindowFullScreen())
            {
                if (this.Visible)
                {
                    this.Visible = false;
                    this.TopMost = false;
                }
                return;
            }
            else
            {
                if (!this.Visible)
                {
                    this.Visible = true;
                    this.TopMost = true;
                }
                if (!this.TopMost)
                {
                    this.TopMost = true;
                }
            }

            var   scr       = GetTargetSidebarScreen();
            int   destShow  = scr.WorkingArea.Right - this.Width;
            int   destHide  = scr.WorkingArea.Right - (configService.Config.HideSidebarPullTab ? 0 : 26);
            Point mouse     = Cursor.Position;

            bool containsMouse = this.Bounds.Contains(mouse);
            if (!containsMouse)
            {
                ignoreHoverUntilMouseLeave = false;
            }

            bool mouseOver = false;
            if (!ignoreHoverUntilMouseLeave)
            {
                if (isSlidOut)
                {
                    if (configService.Config.HideSidebarPullTab)
                    {
                        // Hover checking when pull-tab is hidden: check a narrow 10px strip at the edge of the screen
                        var edgeRect = new Rectangle(scr.WorkingArea.Right - 10, scr.WorkingArea.Top, 10, scr.WorkingArea.Height);
                        mouseOver = edgeRect.Contains(mouse);
                    }
                    else
                    {
                        // Hover checking when pull-tab is visible: check only the pull-tab's screen area
                        var pullTabScreenRect = new Rectangle(
                            scr.WorkingArea.Right - 26,
                            scr.WorkingArea.Top + (scr.WorkingArea.Height - pullTab.Height) / 2,
                            26,
                            pullTab.Height
                        );
                        mouseOver = pullTabScreenRect.Contains(mouse);
                    }
                }
                else
                {
                    mouseOver = containsMouse;
                }
            }

            int dest = (isPinned || mouseOver) ? destShow : destHide;

            if (this.Left < dest)
            {
                if (this.Region != null) { this.Region.Dispose(); this.Region = null; }

                this.Left = Math.Min(dest, this.Left + SLIDE_SPEED);
                if (this.Left == destHide)
                {
                    isSlidOut = true;
                    if (pullTab != null) pullTab.IsCollapsed = true;

                    if (!configService.Config.HideSidebarPullTab)
                    {
                        this.Region = GetPullTabRegion();
                    }
                }
            }
            else if (this.Left > dest)
            {
                if (this.Region != null) { this.Region.Dispose(); this.Region = null; }

                this.Left = Math.Max(dest, this.Left - SLIDE_SPEED);
                if (this.Left == destShow)
                {
                    isSlidOut = false;
                    if (pullTab != null) pullTab.IsCollapsed = false;
                }
            }
        }

        private void MinimizeToTray()
        {
            this.Hide();
            notifyIcon.Visible = true;
            if (isFirstMinimize)
            {
                notifyIcon.ShowBalloonTip(2000, "Utility Hub", "Running in tray. Double-click to open.", ToolTipIcon.Info);
                isFirstMinimize = false;
            }
        }

        private void RestoreFromTray()
        {
            this.Show();
            this.WindowState   = FormWindowState.Normal;
            notifyIcon.Visible = false;
            this.Activate();
        }

        private void ShutdownApp()
        {
            realEngineService.Stop();
            this.Close();
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= 0x02000000; // WS_EX_COMPOSITED (Prevents flickering and black lines for all child controls)
                if (!isSidebarMode)
                {
                    cp.Style |= 0x00C00000; // WS_CAPTION (Required for Windows native resizing and Aero Snap to work correctly)
                    cp.Style |= 0x00040000; // WS_THICKFRAME
                    cp.Style |= 0x00020000; // WS_MINIMIZEBOX
                }
                return cp;
            }
        }

        protected override void WndProc(ref Message m)
        {
            const int WM_NCHITTEST = 0x84;
            const int WM_NCCALCSIZE = 0x83;
            const int HTLEFT=10, HTRIGHT=11, HTTOP=12, HTTOPLEFT=13, HTTOPRIGHT=14,
                      HTBOTTOM=15, HTBOTTOMLEFT=16, HTBOTTOMRIGHT=17;

            if (m.Msg == WM_NCCALCSIZE && m.WParam.ToInt32() == 1)
            {
                m.Result = IntPtr.Zero;
                return;
            }

            if (m.Msg == WM_NCHITTEST)
            {
                var pos = this.PointToClient(new Point(m.LParam.ToInt32()));
                int b = 4;
                bool L = pos.X <= b, R = pos.X >= Width-b, T = pos.Y <= b, Bo = pos.Y >= Height-b;
                if (isSidebarMode) { if (L) { m.Result=(IntPtr)HTLEFT; return; } }
                else
                {
                    if (L&&T){m.Result=(IntPtr)HTTOPLEFT;return;} if(R&&T){m.Result=(IntPtr)HTTOPRIGHT;return;}
                    if(L&&Bo){m.Result=(IntPtr)HTBOTTOMLEFT;return;} if(R&&Bo){m.Result=(IntPtr)HTBOTTOMRIGHT;return;}
                    if(L){m.Result=(IntPtr)HTLEFT;return;} if(R){m.Result=(IntPtr)HTRIGHT;return;}
                    if(T){m.Result=(IntPtr)HTTOP;return;} if(Bo){m.Result=(IntPtr)HTBOTTOM;return;}
                }
            }
            base.WndProc(ref m);
        }

        private void Header_MouseDown(object sender, MouseEventArgs e)
        { if (e.Button==MouseButtons.Left){ formDragging=true; dragStartPoint=new Point(e.X,e.Y);} }

        private void Header_MouseMove(object sender, MouseEventArgs e)
        { if (formDragging&&!isSidebarMode) { var p=PointToScreen(e.Location); this.Location=new Point(p.X-dragStartPoint.X,p.Y-dragStartPoint.Y);} }

        private void Header_MouseUp(object sender, MouseEventArgs e)
        { formDragging=false; }

        private Icon CreateAppIcon()
        {
            using (var bmp = new Bitmap(32,32))
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.FromArgb(14,14,16));
                using (var br = new SolidBrush(Color.FromArgb(6,182,212))) g.FillEllipse(br,10,10,12,12);
                using (var pen = new Pen(Color.FromArgb(139,92,246),2))    g.DrawEllipse(pen,4,4,24,24);
                IntPtr h = bmp.GetHicon();
                return Icon.FromHandle(h);
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing && settingsTab != null && settingsTab.CloseToTray)
            {
                e.Cancel = true;
                if (isSidebarMode) ToggleSidebarMode();
                MinimizeToTray();
                return;
            }

            if (wuWaTab != null) wuWaTab.SaveBuild();
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            if (this.Region != null) { this.Region.Dispose(); this.Region = null; }
            realEngineService.Stop();
            statusTimer?.Stop(); statusTimer?.Dispose();
            slideTimer?.Stop();  slideTimer?.Dispose();
            notifyIcon.Visible = false; notifyIcon.Dispose();
            if (appIcon != null) { Win32.DestroyIcon(appIcon.Handle); appIcon.Dispose(); }
            base.OnFormClosed(e);
        }

        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
    }
}

using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace WacomRealController
{
    public class SettingsTab : Panel
    {
        private readonly ConfigService configService;
        private readonly Action<string> logAppender;

        private Panel   pnlSettingsPathCard, pnlSettingsBehaviorCard, pnlSettingsInfoCard;
        private Label   lblSettingsPathTitle, lblSettingsBehaviorTitle, lblSettingsInfoTitle;
        private Label   lblInfoOS, lblInfoNet, lblInfoApp;
        private TextBox txtSettingsPath;
        private Button  btnSettingsBrowse, btnSettingsAutoDetect;
        private CheckBox chkCloseToTray, chkStartRealOnBoot, chkHideSidebarPullTab;
        private Label    lblMonitor;
        private ComboBox cmbMonitor;

        public bool CloseToTray => chkCloseToTray.Checked;
        public bool StartRealOnBoot => chkStartRealOnBoot.Checked;

        public SettingsTab(ConfigService configService, Action<string> logAppender)
        {
            this.configService = configService;
            this.logAppender = logAppender;

            this.BackColor = Color.Transparent;
            this.AutoScroll = true;
            this.SizeChanged += (s, e) => LayoutTab(this.Width, this.Height);

            BuildSettingsTab();
            LoadConfig();
        }

        private void BuildSettingsTab()
        {
            pnlSettingsPathCard = Card();
            lblSettingsPathTitle = TitleLabel("REAL.exe Location", Color.FromArgb(244, 244, 245));
            txtSettingsPath = new TextBox
            {
                ReadOnly    = true,
                Location    = new Point(20, 50),
                Size        = new Size(350, 25),
                BackColor   = Color.FromArgb(9, 9, 11),
                ForeColor   = Color.FromArgb(228, 228, 231),
                BorderStyle = BorderStyle.FixedSingle,
                Font        = new Font("Segoe UI", 9F)
            };
            btnSettingsBrowse = Btn("Browse...", new Point(380, 48), new Size(90, 26),
                Color.FromArgb(39, 39, 42), Color.White);
            btnSettingsBrowse.Click += (s, e) => SelectRealExePath();
            btnSettingsAutoDetect = Btn("Auto-Detect", new Point(480, 48), new Size(100, 26),
                Color.FromArgb(139, 92, 246), Color.White);
            btnSettingsAutoDetect.Click += (s, e) => { configService.AutoDetectReal(); LoadConfig(); };
            pnlSettingsPathCard.Controls.AddRange(new Control[] {
                lblSettingsPathTitle, txtSettingsPath, btnSettingsBrowse, btnSettingsAutoDetect });

            pnlSettingsBehaviorCard = Card();
            lblSettingsBehaviorTitle = TitleLabel("Behavior", Color.FromArgb(244, 244, 245));
            chkCloseToTray = Chk("Close button minimizes to tray instead of exiting", true);
            chkCloseToTray.Location = new Point(20, 45);
            chkCloseToTray.CheckedChanged += (s, e) => SaveConfig();
            chkStartRealOnBoot = Chk("Auto-launch REAL engine on dashboard open", false);
            chkStartRealOnBoot.Location = new Point(20, 75);
            chkStartRealOnBoot.CheckedChanged += (s, e) => SaveConfig();

            lblMonitor = new Label
            {
                Text = "Sidebar Monitor:",
                Font = new Font("Segoe UI", 9F),
                ForeColor = Color.FromArgb(209, 213, 219),
                Location = new Point(20, 110),
                AutoSize = true
            };

            cmbMonitor = new ComboBox
            {
                Location = new Point(140, 107),
                Size = new Size(250, 25),
                DropDownStyle = ComboBoxStyle.DropDownList,
                BackColor = Color.FromArgb(22, 28, 42),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9F)
            };
            PopulateMonitors();
            cmbMonitor.SelectedIndexChanged += (s, e) => {
                configService.Config.SidebarMonitorIndex = cmbMonitor.SelectedIndex;
                configService.SaveConfig();
            };

            chkHideSidebarPullTab = Chk("Hide sidebar pull tab (hover screen edge to open)", false);
            chkHideSidebarPullTab.Location = new Point(20, 145);
            chkHideSidebarPullTab.CheckedChanged += (s, e) => SaveConfig();

            pnlSettingsBehaviorCard.Controls.AddRange(new Control[] {
                lblSettingsBehaviorTitle, chkCloseToTray, chkStartRealOnBoot, lblMonitor, cmbMonitor, chkHideSidebarPullTab });

            pnlSettingsInfoCard = Card();
            lblSettingsInfoTitle = TitleLabel("Diagnostics", Color.FromArgb(244, 244, 245));
            lblInfoOS  = InfoLabel("OS: " + Environment.OSVersion.VersionString, new Point(20, 45));
            lblInfoNet = InfoLabel(".NET: " + Environment.Version.ToString(), new Point(20, 70));
            lblInfoApp = InfoLabel("Version: v1.3.0 (Multi-Hub)", new Point(20, 95));
            pnlSettingsInfoCard.Controls.AddRange(new Control[] {
                lblSettingsInfoTitle, lblInfoOS, lblInfoNet, lblInfoApp });

            this.Controls.AddRange(new Control[] {
                pnlSettingsPathCard, pnlSettingsBehaviorCard, pnlSettingsInfoCard });
        }

        private void LoadConfig()
        {
            configService.LoadConfig();
            txtSettingsPath.Text = configService.Config.RealExePath;
            chkCloseToTray.Checked = configService.Config.CloseToTray;
            chkStartRealOnBoot.Checked = configService.Config.AutoStart;
            chkHideSidebarPullTab.Checked = configService.Config.HideSidebarPullTab;
            PopulateMonitors();
        }

        private void PopulateMonitors()
        {
            if (cmbMonitor == null) return;
            cmbMonitor.Items.Clear();
            var screens = Screen.AllScreens;
            for (int i = 0; i < screens.Length; i++)
            {
                var scr = screens[i];
                string name = string.Format("Monitor {0} ({1}x{2}){3}", 
                    i + 1, 
                    scr.Bounds.Width, 
                    scr.Bounds.Height, 
                    scr.Primary ? " [Primary]" : "");
                cmbMonitor.Items.Add(name);
            }
            if (configService.Config.SidebarMonitorIndex >= 0 && configService.Config.SidebarMonitorIndex < screens.Length)
            {
                cmbMonitor.SelectedIndex = configService.Config.SidebarMonitorIndex;
            }
            else
            {
                cmbMonitor.SelectedIndex = 0;
            }
        }

        private void SaveConfig()
        {
            configService.Config.CloseToTray = chkCloseToTray.Checked;
            configService.Config.AutoStart = chkStartRealOnBoot.Checked;
            configService.Config.HideSidebarPullTab = chkHideSidebarPullTab.Checked;
            configService.SaveConfig();
        }

        private void SelectRealExePath()
        {
            using (var ofd = new OpenFileDialog { Filter = "Exe|*.exe", Title = "Find REAL.exe" })
            {
                if (ofd.ShowDialog() != DialogResult.OK) return;
                configService.Config.RealExePath = ofd.FileName;
                txtSettingsPath.Text = configService.Config.RealExePath;
                configService.SaveConfig();
                logAppender?.Invoke("[Controller] Path set: " + configService.Config.RealExePath);
            }
        }

        private void LayoutTab(int w, int h)
        {
            if (pnlSettingsPathCard == null) return;

            int contentW = w;
            if (this.VScroll && this.VerticalScroll.Visible) 
                contentW -= SystemInformation.VerticalScrollBarWidth;
                
            int cardW = Math.Max(160, contentW - 40);

            if (contentW < 450)
            {
                // Stacked layout
                pnlSettingsPathCard.Location = new Point(20, 20);
                pnlSettingsPathCard.Size     = new Size(cardW, 130);
                pnlSettingsBehaviorCard.Location = new Point(20, 165);
                pnlSettingsBehaviorCard.Size     = new Size(cardW, 180);
                pnlSettingsInfoCard.Location = new Point(20, 360);
                pnlSettingsInfoCard.Size     = new Size(cardW, 140); 

                txtSettingsPath.Width      = cardW - 40;
                int bw = (cardW - 50) / 2;
                btnSettingsBrowse.Location = new Point(20, 85);
                btnSettingsBrowse.Size     = new Size(bw, 26);
                btnSettingsAutoDetect.Location = new Point(30 + bw, 85);
                btnSettingsAutoDetect.Size     = new Size(bw, 26);
                
                this.AutoScrollMinSize = new Size(0, pnlSettingsInfoCard.Bottom + 20);
            }
            else
            {
                // Side-by-side layout
                pnlSettingsPathCard.Location = new Point(20, 20);
                pnlSettingsPathCard.Size     = new Size(cardW, 100);
                pnlSettingsBehaviorCard.Location = new Point(20, 140);
                pnlSettingsBehaviorCard.Size     = new Size(cardW, 180);
                pnlSettingsInfoCard.Location = new Point(20, 340);
                pnlSettingsInfoCard.Size     = new Size(cardW, Math.Max(140, h - 355));

                txtSettingsPath.Width      = cardW - 230;
                btnSettingsBrowse.Location = new Point(cardW - 200, 48);
                btnSettingsBrowse.Size     = new Size(90, 26);
                btnSettingsAutoDetect.Location = new Point(cardW - 100, 48);
                btnSettingsAutoDetect.Size     = new Size(100, 26);
                
                this.AutoScrollMinSize = new Size(0, pnlSettingsInfoCard.Bottom + 20);
            }
            
            cmbMonitor.Width = Math.Min(250, cardW - 140);
            if (cmbMonitor.Width < 50) cmbMonitor.Width = 50;
        }

        // Helpers wrapper
        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
        private Panel Card() => UIHelpers.Card();
        private Label TitleLabel(string text, Color color) => UIHelpers.TitleLabel(text, color);
        private Label InfoLabel(string text, Point loc) => UIHelpers.InfoLabel(text, loc);
        private CheckBox Chk(string text, bool chkd) => UIHelpers.Chk(text, chkd);
    }
}

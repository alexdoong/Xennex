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
        private CheckBox chkCloseToTray, chkStartRealOnBoot;

        public bool CloseToTray => chkCloseToTray.Checked;
        public bool StartRealOnBoot => chkStartRealOnBoot.Checked;

        public SettingsTab(ConfigService configService, Action<string> logAppender)
        {
            this.configService = configService;
            this.logAppender = logAppender;

            this.BackColor = Color.Transparent;
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
            pnlSettingsBehaviorCard.Controls.AddRange(new Control[] {
                lblSettingsBehaviorTitle, chkCloseToTray, chkStartRealOnBoot });

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
        }

        private void SaveConfig()
        {
            configService.Config.CloseToTray = chkCloseToTray.Checked;
            configService.Config.AutoStart = chkStartRealOnBoot.Checked;
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
            pnlSettingsPathCard.Location = new Point(20, 20);
            pnlSettingsPathCard.Size     = new Size(w - 40, 100);
            pnlSettingsBehaviorCard.Location = new Point(20, 140);
            pnlSettingsBehaviorCard.Size     = new Size(w - 40, 120);
            pnlSettingsInfoCard.Location = new Point(20, 280);
            pnlSettingsInfoCard.Size     = new Size(w - 40, h - 295);

            int pw = pnlSettingsPathCard.Width;
            txtSettingsPath.Width      = pw - 230;
            btnSettingsBrowse.Location = new Point(pw - 200, 48);
            btnSettingsAutoDetect.Location = new Point(pw - 100, 48);
        }

        // Helpers wrapper
        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
        private Panel Card() => UIHelpers.Card();
        private Label TitleLabel(string text, Color color) => UIHelpers.TitleLabel(text, color);
        private Label InfoLabel(string text, Point loc) => UIHelpers.InfoLabel(text, loc);
        private CheckBox Chk(string text, bool chkd) => UIHelpers.Chk(text, chkd);
    }
}

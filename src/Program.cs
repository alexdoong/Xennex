using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace WacomRealController
{
    // ─── Program Entry ────────────────────────────────────────────────────────

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    // ─── Main Form ────────────────────────────────────────────────────────────

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

        // ── osu! Tab ───────────────────────────────────────────────────────────
        private Panel  pnlTabOsuContent;
        private Panel  pnlWacomCard, pnlRealCard, pnlLogsCard;
        private Panel  pnlWacomStatusDot, pnlRealStatusDot;
        private Label  lblWacomTitle, lblWacomStatus;
        private Label  lblRealTitle, lblRealStatus;
        private Label  lblLogsTitle;
        private Button btnDisableWacom, btnEnableWacom;
        private Button btnStartReal, btnStopReal;
        private Button btnToggleConsole, btnCopyLogs, btnClearLogs;
        private TextBox txtLogs;

        // ── WuWa Tab ───────────────────────────────────────────────────────────
        private Panel  pnlTabWuWaContent;
        private Panel  pnlCharCard;          // left: character art + name
        private Panel  pnlStatsCard;         // right top: stats table
        private Panel  pnlWeaponCard;        // right mid: weapon info
        private Panel[] pnlEcho = new Panel[5];  // bottom: echo slots
        private Panel  pnlEchoRow;

        // Character card inner controls
        private PictureBox pbCharImage;
        private Label  lblCharName, lblCharLevel, lblCharElement, lblCharSeq;
        private Button btnCharUpload, btnCharEditDone;
        private Button btnImgZoomIn, btnImgZoomOut, btnImgReset;
        private bool   charEditMode = false;
        private bool   imgDragging  = false;
        private Point  imgDragStart;

        // Stats card inner controls
        private TextBox[] txtStats = new TextBox[7];
        private Label[]   lblStatNames = new Label[7];
        private static readonly string[] StatNames = { "HP", "ATK", "DEF", "Crit Rate", "Crit DMG", "Energy Regen", "Skill DMG" };

        // Weapon card inner controls
        private PictureBox pbWeaponIcon;
        private TextBox txtWeaponName, txtWeaponLevel;
        private Label   lblWeaponRarity, lblWeaponRefinement;
        private Button  btnWeaponRarityUp, btnWeaponRarityDn, btnWeaponRefUp, btnWeaponRefDn;
        private Button  btnWeaponUpload;

        // Echo slot inner controls – stored flat for easy access
        private PictureBox[] pbEchoIcon    = new PictureBox[5];
        private TextBox[]    txtEchoMain   = new TextBox[5];
        private TextBox[][]  txtEchoSub    = new TextBox[5][];  // [slot][stat]
        private Button[][]   btnEchoQuality = new Button[5][];  // [slot][stat]
        private Button[]     btnEchoUpload = new Button[5];

        // WuWa build state reference
        private WuWaBuild wuBuild => configService.Build;
        private Image     charImage   = null;
        private Image[]   echoImages  = new Image[5];
        private Image     weaponImage = null;

        // ── Settings Tab ───────────────────────────────────────────────────────
        private Panel   pnlTabSettingsContent;
        private Panel   pnlSettingsPathCard, pnlSettingsBehaviorCard, pnlSettingsInfoCard;
        private Label   lblSettingsPathTitle, lblSettingsBehaviorTitle, lblSettingsInfoTitle;
        private Label   lblInfoOS, lblInfoNet, lblInfoApp;
        private TextBox txtSettingsPath;
        private Button  btnSettingsBrowse, btnSettingsAutoDetect;
        private CheckBox chkCloseToTray, chkStartRealOnBoot;

        // ── Tray ──────────────────────────────────────────────────────────────
        private NotifyIcon   notifyIcon;
        private ContextMenu  trayMenu;
        private Icon         appIcon;

        // ── App State ────────────────────────────────────────────────────────
        private bool isRealRunning   = false;
        private bool isWacomActive   = false;
        private bool isSidebarMode   = false;
        private bool isPinned        = false;   // auto-hide ON by default in sidebar
        private bool isSlidOut       = false;
        private bool isFirstMinimize = true;
        private int  currentTab      = 0;

        private bool  formDragging   = false;
        private Point dragStartPoint = Point.Empty;
        private Rectangle previousBounds = new Rectangle(100, 100, 820, 560);
        private const int SLIDE_SPEED = 22;

        private System.Windows.Forms.Timer statusTimer;
        private System.Windows.Forms.Timer slideTimer;

        // ═════════════════════════════════════════════════════════════════════
        //  CONSTRUCTOR
        // ═════════════════════════════════════════════════════════════════════

        public MainForm()
        {
            configService.OnLogReceived += AppendLog;
            wacomService.OnLogReceived += AppendLog;
            realEngineService.OnLogReceived += AppendLog;

            realEngineService.OnStatusChanged += CheckStatus;
            wacomService.OnStatusChanged += CheckStatus;

            realEngineService.OnConsoleAvailable += (avail) =>
            {
                btnToggleConsole.Enabled = avail;
                btnToggleConsole.Text = (avail && realEngineService.IsConsoleVisible) ? "Hide Console" : "Show Console";
            };

            this.SuspendLayout();
            BuildUI();
            this.ResumeLayout(false);

            SetupStyles();
            LoadConfig();
            LoadWuWaBuild();
            CheckStatus();
            SetActiveTab(0);
            LayoutControls();

            statusTimer = new System.Windows.Forms.Timer { Interval = 2000 };
            statusTimer.Tick += (s, e) => CheckStatus();
            statusTimer.Start();

            slideTimer = new System.Windows.Forms.Timer { Interval = 16 };
            slideTimer.Tick += SlideTimer_Tick;
            slideTimer.Start();

            if (chkStartRealOnBoot.Checked && File.Exists(configService.Config.RealExePath))
                StartLatencyReduction();
        }

        // ═════════════════════════════════════════════════════════════════════
        //  UI CONSTRUCTION
        // ═════════════════════════════════════════════════════════════════════

        private void BuildUI()
        {
            this.Name            = "MainForm";
            this.Text            = "Utility Hub";
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
            BuildOsuTab();
            BuildWuWaTab();
            BuildSettingsTab();

            pnlContent = new Panel
            {
                Location = new Point(60, 65),
                Size     = new Size(760, 495),
                BackColor = Color.FromArgb(14, 14, 16)
            };
            pnlContent.Controls.AddRange(new Control[] { pnlTabOsuContent, pnlTabWuWaContent, pnlTabSettingsContent });

            this.Controls.AddRange(new Control[] { pnlHeader, pnlNavigation, pnlContent });
            BuildTray();
        }

        // ── Header ────────────────────────────────────────────────────────────

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
                Text      = "UTILITY HUB",
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
                if (chkCloseToTray != null && chkCloseToTray.Checked) MinimizeToTray();
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

        // ── Navigation ────────────────────────────────────────────────────────

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

        // ── osu! Tab ─────────────────────────────────────────────────────────

        private void BuildOsuTab()
        {
            pnlTabOsuContent = new Panel { Location = Point.Empty, BackColor = Color.Transparent };

            pnlWacomCard = Card();
            lblWacomTitle = TitleLabel("Wacom Tablet Drivers", Color.FromArgb(167, 139, 250));
            pnlWacomStatusDot = StatusDotPanel(() => isWacomActive);
            lblWacomStatus = InfoLabel("Status: Checking...", new Point(44, 50));
            btnDisableWacom = Btn("Disable Drivers", Point.Empty, new Size(10, 35),
                Color.FromArgb(39, 39, 42), Color.FromArgb(244, 244, 245));
            btnDisableWacom.Click += (s, e) => RunBatchFile("DisableWacomDrivers.bat");
            btnEnableWacom = Btn("Enable Drivers", Point.Empty, new Size(10, 35),
                Color.FromArgb(139, 92, 246), Color.White);
            btnEnableWacom.Click += (s, e) => RunBatchFile("EnableWacomDrivers.bat");
            pnlWacomCard.Controls.AddRange(new Control[] {
                lblWacomTitle, pnlWacomStatusDot, lblWacomStatus, btnDisableWacom, btnEnableWacom });

            pnlRealCard = Card();
            lblRealTitle = TitleLabel("Audio Latency (REAL)", Color.FromArgb(96, 165, 250));
            pnlRealStatusDot = StatusDotPanel(() => isRealRunning);
            lblRealStatus = InfoLabel("Status: Stopped", new Point(44, 50));
            btnStartReal = Btn("Start Engine", Point.Empty, new Size(10, 35),
                Color.FromArgb(37, 99, 235), Color.White);
            btnStartReal.Click += (s, e) => StartLatencyReduction();
            btnStopReal = Btn("Stop Engine", Point.Empty, new Size(10, 35),
                Color.FromArgb(39, 39, 42), Color.FromArgb(244, 244, 245));
            btnStopReal.Click += (s, e) => StopRealProcess();
            pnlRealCard.Controls.AddRange(new Control[] {
                lblRealTitle, pnlRealStatusDot, lblRealStatus, btnStartReal, btnStopReal });

            pnlLogsCard = Card();
            lblLogsTitle = InfoLabel("Engine Output", new Point(20, 12));
            lblLogsTitle.Font      = new Font("Segoe UI", 9F, FontStyle.Bold);
            lblLogsTitle.ForeColor = Color.FromArgb(113, 113, 122);
            txtLogs = new TextBox
            {
                Multiline    = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical,
                BackColor    = Color.FromArgb(9, 9, 11),
                ForeColor    = Color.FromArgb(16, 185, 129),
                BorderStyle  = BorderStyle.None,
                Font         = new Font("Consolas", 9F)
            };
            btnToggleConsole = Btn("Show Console", Point.Empty, new Size(130, 28),
                Color.FromArgb(39, 39, 42), Color.FromArgb(228, 228, 231));
            btnToggleConsole.Font    = new Font("Segoe UI", 8F);
            btnToggleConsole.Enabled = false;
            btnToggleConsole.Click  += (s, e) => ToggleConsoleWindow();
            btnCopyLogs = Btn("Copy", Point.Empty, new Size(70, 28),
                Color.FromArgb(39, 39, 42), Color.FromArgb(228, 228, 231));
            btnCopyLogs.Click += (s, e) => { if (!string.IsNullOrEmpty(txtLogs.Text)) Clipboard.SetText(txtLogs.Text); };
            btnClearLogs = Btn("Clear", Point.Empty, new Size(70, 28),
                Color.FromArgb(39, 39, 42), Color.FromArgb(228, 228, 231));
            btnClearLogs.Click += (s, e) => txtLogs.Clear();
            pnlLogsCard.Controls.AddRange(new Control[] {
                lblLogsTitle, txtLogs, btnToggleConsole, btnCopyLogs, btnClearLogs });

            pnlTabOsuContent.Controls.AddRange(new Control[] { pnlWacomCard, pnlRealCard, pnlLogsCard });
        }

        // ── WuWa Tab ─────────────────────────────────────────────────────────

        private void BuildWuWaTab()
        {
            pnlTabWuWaContent = new Panel { Location = Point.Empty, BackColor = Color.Transparent };

            BuildCharCard();
            BuildWeaponCard();
            BuildStatsCard();
            BuildEchoRow();

            pnlTabWuWaContent.Controls.AddRange(new Control[] {
                pnlCharCard, pnlWeaponCard, pnlStatsCard, pnlEchoRow });
        }

        private void BuildCharCard()
        {
            pnlCharCard = new Panel { BackColor = Color.FromArgb(10, 14, 26) };
            pnlCharCard.Paint += CharCard_Paint;

            pbCharImage = new PictureBox
            {
                SizeMode  = PictureMode.Zoom,
                BackColor = Color.Transparent,
                Cursor    = Cursors.Hand
            };
            pbCharImage.Click      += CharImage_Click;
            pbCharImage.MouseDown  += CharImage_MouseDown;
            pbCharImage.MouseMove  += CharImage_MouseMove;
            pbCharImage.MouseUp    += CharImage_MouseUp;

            lblCharName = new Label
            {
                Text      = wuBuild.ResonatorName,
                Font      = new Font("Segoe UI", 14F, FontStyle.Bold),
                ForeColor = Color.White,
                BackColor = Color.Transparent,
                AutoSize  = true
            };
            lblCharName.DoubleClick += (s, e) => PromptEditCharName();

            lblCharLevel = new Label
            {
                Text      = "Lv." + wuBuild.Level,
                Font      = new Font("Segoe UI", 9F),
                ForeColor = Color.FromArgb(209, 213, 219),
                BackColor = Color.Transparent,
                AutoSize  = true
            };

            lblCharElement = new Label
            {
                Text      = wuBuild.Element,
                Font      = new Font("Segoe UI", 9F, FontStyle.Bold),
                ForeColor = GetElementColor(wuBuild.Element),
                BackColor = Color.Transparent,
                AutoSize  = true
            };

            lblCharSeq = new Label
            {
                Text      = "S" + wuBuild.Sequence,
                Font      = new Font("Segoe UI", 9F, FontStyle.Bold),
                ForeColor = Color.FromArgb(251, 191, 36),
                BackColor = Color.Transparent,
                AutoSize  = true
            };

            btnCharUpload = Btn("📷 Upload Image", new Point(10, 10), new Size(140, 30),
                Color.FromArgb(30, 30, 40), Color.FromArgb(209, 213, 219));
            btnCharUpload.Font    = new Font("Segoe UI", 8.5F);
            btnCharUpload.Visible = false;
            btnCharUpload.Click  += (s, e) => UploadCharImage();

            btnImgZoomIn = Btn("+", new Point(155, 10), new Size(30, 30),
                Color.FromArgb(30, 30, 40), Color.White);
            btnImgZoomIn.Visible = false;
            btnImgZoomIn.Click  += (s, e) => { wuBuild.ImageScale = Math.Min(4f, wuBuild.ImageScale + 0.1f); pnlCharCard.Invalidate(); };

            btnImgZoomOut = Btn("−", new Point(190, 10), new Size(30, 30),
                Color.FromArgb(30, 30, 40), Color.White);
            btnImgZoomOut.Visible = false;
            btnImgZoomOut.Click  += (s, e) => { wuBuild.ImageScale = Math.Max(0.2f, wuBuild.ImageScale - 0.1f); pnlCharCard.Invalidate(); };

            btnImgReset = Btn("↺", new Point(225, 10), new Size(30, 30),
                Color.FromArgb(30, 30, 40), Color.White);
            btnImgReset.Visible = false;
            btnImgReset.Click  += (s, e) => { wuBuild.ImagePanX = 0; wuBuild.ImagePanY = 0; wuBuild.ImageScale = 1f; pnlCharCard.Invalidate(); };

            btnCharEditDone = Btn("✔ Done", new Point(260, 10), new Size(70, 30),
                Color.FromArgb(16, 185, 129), Color.White);
            btnCharEditDone.Font    = new Font("Segoe UI", 8.5F, FontStyle.Bold);
            btnCharEditDone.Visible = false;
            btnCharEditDone.Click  += (s, e) => SetCharEditMode(false);

            pnlCharCard.Controls.AddRange(new Control[] {
                pbCharImage, lblCharName, lblCharLevel, lblCharElement, lblCharSeq,
                btnCharUpload, btnImgZoomIn, btnImgZoomOut, btnImgReset, btnCharEditDone });
        }

        private void BuildWeaponCard()
        {
            pnlWeaponCard = new Panel { BackColor = Color.FromArgb(16, 20, 30) };
            pnlWeaponCard.Paint += WeaponCard_Paint;

            pbWeaponIcon = new PictureBox
            {
                Size      = new Size(56, 56),
                SizeMode  = PictureMode.Zoom,
                BackColor = Color.FromArgb(30, 30, 45),
                Cursor    = Cursors.Hand
            };
            pbWeaponIcon.Click += (s, e) => UploadWeaponImage();

            txtWeaponName = EditBox(wuBuild.WeaponName, new Point(70, 8), new Size(200, 24));
            txtWeaponName.TextChanged += (s, e) => { wuBuild.WeaponName = txtWeaponName.Text; };

            lblWeaponRarity = new Label
            {
                Text      = new string('★', wuBuild.WeaponRarity),
                Font      = new Font("Segoe UI", 12F),
                ForeColor = Color.FromArgb(251, 191, 36),
                BackColor = Color.Transparent,
                AutoSize  = true
            };

            btnWeaponRarityUp = SmallBtn("+"); btnWeaponRarityUp.Click += (s, e) => ChangeWeaponRarity(1);
            btnWeaponRarityDn = SmallBtn("−"); btnWeaponRarityDn.Click += (s, e) => ChangeWeaponRarity(-1);

            lblWeaponRefinement = new Label
            {
                Text      = "R" + wuBuild.WeaponRefinement,
                Font      = new Font("Segoe UI", 9F, FontStyle.Bold),
                ForeColor = Color.FromArgb(167, 139, 250),
                BackColor = Color.Transparent,
                AutoSize  = true
            };
            btnWeaponRefUp = SmallBtn("+"); btnWeaponRefUp.Click += (s, e) => ChangeWeaponRef(1);
            btnWeaponRefDn = SmallBtn("−"); btnWeaponRefDn.Click += (s, e) => ChangeWeaponRef(-1);

            txtWeaponLevel = EditBox(wuBuild.WeaponLevel, Point.Empty, new Size(70, 22));
            txtWeaponLevel.TextChanged += (s, e) => { wuBuild.WeaponLevel = txtWeaponLevel.Text; };

            btnWeaponUpload = Btn("Upload Icon", new Point(0, 70), new Size(90, 24),
                Color.FromArgb(30, 30, 45), Color.FromArgb(180, 180, 200));
            btnWeaponUpload.Font   = new Font("Segoe UI", 7.5F);
            btnWeaponUpload.Click += (s, e) => UploadWeaponImage();

            pnlWeaponCard.Controls.AddRange(new Control[] {
                pbWeaponIcon, txtWeaponName, lblWeaponRarity, btnWeaponRarityUp, btnWeaponRarityDn,
                lblWeaponRefinement, btnWeaponRefUp, btnWeaponRefDn, txtWeaponLevel, btnWeaponUpload });
        }

        private void BuildStatsCard()
        {
            pnlStatsCard = new Panel { BackColor = Color.FromArgb(16, 20, 30) };
            pnlStatsCard.Paint += StatsCard_Paint;

            string[] defaults = {
                wuBuild.StatHP, wuBuild.StatATK, wuBuild.StatDEF,
                wuBuild.StatCritRate, wuBuild.StatCritDMG,
                wuBuild.StatEnergyRegen, wuBuild.StatSklDMG
            };

            for (int i = 0; i < 7; i++)
            {
                int idx = i;
                lblStatNames[i] = new Label
                {
                    Text      = StatNames[i],
                    Font      = new Font("Segoe UI", 9F),
                    ForeColor = Color.FromArgb(161, 161, 170),
                    BackColor = Color.Transparent,
                    AutoSize  = true
                };

                txtStats[i] = new TextBox
                {
                    Text        = defaults[i],
                    Font        = new Font("Segoe UI", 9.5F, FontStyle.Bold),
                    ForeColor   = Color.White,
                    BackColor   = Color.FromArgb(22, 28, 42),
                    BorderStyle = BorderStyle.None,
                    TextAlign   = HorizontalAlignment.Right
                };
                txtStats[i].TextChanged += (s, e) => SaveStatFromIndex(idx);
            }

            for (int i = 0; i < 7; i++)
                pnlStatsCard.Controls.AddRange(new Control[] { lblStatNames[i], txtStats[i] });
        }

        private void BuildEchoRow()
        {
            pnlEchoRow = new Panel { BackColor = Color.Transparent };

            for (int i = 0; i < 5; i++)
            {
                int idx = i;
                txtEchoSub[i]    = new TextBox[5];
                btnEchoQuality[i] = new Button[5];

                pnlEcho[i] = new Panel { BackColor = Color.FromArgb(14, 18, 28) };
                pnlEcho[i].Paint += (s, e) => EchoCard_Paint(s, e);

                pbEchoIcon[i] = new PictureBox
                {
                    SizeMode  = PictureMode.Zoom,
                    BackColor = Color.FromArgb(24, 28, 42),
                    Cursor    = Cursors.Hand
                };
                pbEchoIcon[i].Click += (s, e) => UploadEchoImage(idx);

                txtEchoMain[i] = new TextBox
                {
                    Text        = wuBuild.Echoes[i].MainStatName + " " + wuBuild.Echoes[i].MainStatValue,
                    Font        = new Font("Segoe UI", 7.5F, FontStyle.Bold),
                    ForeColor   = Color.FromArgb(251, 191, 36),
                    BackColor   = Color.FromArgb(14, 18, 28),
                    BorderStyle = BorderStyle.None
                };
                txtEchoMain[i].TextChanged += (s, e) => { wuBuild.Echoes[idx].MainStatName = txtEchoMain[idx].Text; };

                for (int j = 0; j < 5; j++)
                {
                    int si = j;
                    txtEchoSub[i][j] = new TextBox
                    {
                        Text        = wuBuild.Echoes[i].Substats[j].Name + " " + wuBuild.Echoes[i].Substats[j].Value,
                        Font        = new Font("Segoe UI", 7.5F),
                        ForeColor   = Color.FromArgb(209, 213, 219),
                        BackColor   = Color.FromArgb(14, 18, 28),
                        BorderStyle = BorderStyle.None
                    };
                    txtEchoSub[i][j].TextChanged += (s, e) =>
                    {
                        string[] parts = txtEchoSub[idx][si].Text.Split(' ');
                        wuBuild.Echoes[idx].Substats[si].Name  = parts.Length > 0 ? parts[0] : "";
                        wuBuild.Echoes[idx].Substats[si].Value = parts.Length > 1 ? parts[1] : "";
                    };

                    btnEchoQuality[i][j] = new Button
                    {
                        Size      = new Size(14, 14),
                        FlatStyle = FlatStyle.Flat,
                        BackColor = QualityColor(wuBuild.Echoes[i].Substats[j].Quality),
                        Text      = "",
                        Cursor    = Cursors.Hand
                    };
                    btnEchoQuality[i][j].FlatAppearance.BorderSize = 0;
                    int qi = j;
                    btnEchoQuality[i][j].Click += (s, e) => CycleEchoQuality(idx, qi);
                }

                btnEchoUpload[i] = new Button
                {
                    Text      = "📷",
                    Size      = new Size(22, 22),
                    FlatStyle = FlatStyle.Flat,
                    BackColor = Color.FromArgb(24, 28, 42),
                    ForeColor = Color.FromArgb(180, 180, 200),
                    Font      = new Font("Segoe UI", 9F),
                    Cursor    = Cursors.Hand
                };
                btnEchoUpload[i].FlatAppearance.BorderSize = 0;
                btnEchoUpload[i].Click += (s, e) => UploadEchoImage(idx);

                var controls = new List<Control> { pbEchoIcon[i], txtEchoMain[i], btnEchoUpload[i] };
                for (int j = 0; j < 5; j++) { controls.Add(txtEchoSub[i][j]); controls.Add(btnEchoQuality[i][j]); }
                pnlEcho[i].Controls.AddRange(controls.ToArray());
                pnlEchoRow.Controls.Add(pnlEcho[i]);
            }
        }

        // ── Settings Tab ─────────────────────────────────────────────────────

        private void BuildSettingsTab()
        {
            pnlTabSettingsContent = new Panel { Location = Point.Empty, BackColor = Color.Transparent };

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
            btnSettingsAutoDetect.Click += (s, e) => LoadConfig();
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

            pnlTabSettingsContent.Controls.AddRange(new Control[] {
                pnlSettingsPathCard, pnlSettingsBehaviorCard, pnlSettingsInfoCard });
        }

        private void BuildTray()
        {
            trayMenu = new ContextMenu();
            trayMenu.MenuItems.Add("Restore", (s, e) => RestoreFromTray());
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Start REAL", (s, e) => StartLatencyReduction());
            trayMenu.MenuItems.Add("Stop REAL",  (s, e) => StopRealProcess());
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Enable Wacom",  (s, e) => RunBatchFile("EnableWacomDrivers.bat"));
            trayMenu.MenuItems.Add("Disable Wacom", (s, e) => RunBatchFile("DisableWacomDrivers.bat"));
            trayMenu.MenuItems.Add("-");
            trayMenu.MenuItems.Add("Exit", (s, e) => ShutdownApp());

            notifyIcon = new NotifyIcon
            {
                Icon        = this.appIcon,
                ContextMenu = trayMenu,
                Text        = "Utility Hub",
                Visible     = false
            };
            notifyIcon.DoubleClick += (s, e) => RestoreFromTray();
        }

        // ─── UI Factory Wrappers ───────────────────────────────────────────────
        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
        private Button SmallBtn(string text) => UIHelpers.SmallBtn(text);
        private Panel Card() => UIHelpers.Card();
        private Label TitleLabel(string text, Color color) => UIHelpers.TitleLabel(text, color);
        private Label InfoLabel(string text, Point loc) => UIHelpers.InfoLabel(text, loc);
        private Panel StatusDotPanel(Func<bool> activeGetter) => UIHelpers.StatusDotPanel(activeGetter);
        private TextBox EditBox(string text, Point loc, Size sz) => UIHelpers.EditBox(text, loc, sz);
        private CheckBox Chk(string text, bool chkd) => UIHelpers.Chk(text, chkd);
        private Color LightenColor(Color c, int amt) => UIHelpers.LightenColor(c, amt);
        private Color GetElementColor(string element) => UIHelpers.GetElementColor(element);

        // ═════════════════════════════════════════════════════════════════════
        //  STYLES & PAINTING
        // ═════════════════════════════════════════════════════════════════════

        private void SetupStyles()
        {
            this.DoubleBuffered = true;
            this.SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
            this.Paint += (s, e) =>
            {
                using (var pen = new Pen(Color.FromArgb(60, 139, 92, 246), 1))
                    e.Graphics.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
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

        private void CharCard_Paint(object sender, PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            // Background gradient
            using (var br = new LinearGradientBrush(pnlCharCard.ClientRectangle,
                Color.FromArgb(8, 12, 22), Color.FromArgb(18, 26, 45), LinearGradientMode.Vertical))
                g.FillRectangle(br, pnlCharCard.ClientRectangle);

            // Draw character image manually if in edit or when PictureBox not covering full area
            if (charImage != null && charEditMode)
            {
                Rectangle imgBounds = GetCharImageDrawRect(pnlCharCard.Width, pnlCharCard.Height - 120);
                g.DrawImage(charImage, imgBounds);

                // Drag hint
                using (var brush = new SolidBrush(Color.FromArgb(120, 0, 0, 0)))
                    g.FillRectangle(brush, 0, 45, pnlCharCard.Width, imgBounds.Height);
                using (var font = new Font("Segoe UI", 10F, FontStyle.Bold))
                using (var b = new SolidBrush(Color.FromArgb(200, 255, 255, 255)))
                {
                    var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                    g.DrawString("Drag to reposition  ·  +/- to zoom", font, b,
                         new RectangleF(0, 45, pnlCharCard.Width, imgBounds.Height), sf);
                }
            }
            else if (charImage == null)
            {
                // Click to configure placeholder
                using (var font = new Font("Segoe UI", 10F))
                using (var b = new SolidBrush(Color.FromArgb(80, 255, 255, 255)))
                {
                    var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                    g.DrawString("Click to configure image", font, b,
                        new RectangleF(0, 40, pnlCharCard.Width, pnlCharCard.Height - 120), sf);
                }
            }

            // Bottom overlay gradient
            int overlayH = 100;
            Rectangle overlayRect = new Rectangle(0, pnlCharCard.Height - overlayH, pnlCharCard.Width, overlayH);
            using (var br = new LinearGradientBrush(overlayRect,
                Color.Transparent, Color.FromArgb(220, 8, 12, 22), LinearGradientMode.Vertical))
                g.FillRectangle(br, overlayRect);

            // Element glow border
            Color elemColor = GetElementColor(wuBuild.Element);
            using (var pen = new Pen(Color.FromArgb(80, elemColor.R, elemColor.G, elemColor.B), 2))
                g.DrawRectangle(pen, 1, 1, pnlCharCard.Width - 2, pnlCharCard.Height - 2);
        }

        private void WeaponCard_Paint(object sender, PaintEventArgs e)
        {
            using (var pen = new Pen(Color.FromArgb(251, 191, 36, 60), 1))
                e.Graphics.DrawRectangle(pen, 0, 0, pnlWeaponCard.Width - 1, pnlWeaponCard.Height - 1);
        }

        private void StatsCard_Paint(object sender, PaintEventArgs e)
        {
            using (var pen = new Pen(Color.FromArgb(39, 39, 55), 1))
                e.Graphics.DrawRectangle(pen, 0, 0, pnlStatsCard.Width - 1, pnlStatsCard.Height - 1);
        }

        private void EchoCard_Paint(object sender, PaintEventArgs e)
        {
            var p = (Panel)sender;
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (var pen = new Pen(Color.FromArgb(6, 182, 212, 50), 1))
                e.Graphics.DrawRectangle(pen, 0, 0, p.Width - 1, p.Height - 1);
        }

        // ═════════════════════════════════════════════════════════════════════
        //  LAYOUT
        // ═════════════════════════════════════════════════════════════════════

        private void LayoutControls()
        {
            if (pnlHeader == null) return;
            int w = ClientSize.Width, h = ClientSize.Height;

            pnlHeader.Width = w;

            // Header button positions based on width
            btnClose.Location    = new Point(w - 45, 0);
            btnMinimize.Location = new Point(w - 90, 0);

            if (isSidebarMode)
            {
                // Compact sidebar header: just back + title + pin + close/min
                lblTitle.Text         = "HUB";
                lblSubtitle.Visible   = false;
                btnSidebarToggle.Text = "← Back";
                btnSidebarToggle.Location = new Point(w - 170, 17);
                btnSidebarToggle.Size     = new Size(70, 30);
                btnPin.Location = new Point(w - 95, 17);
                btnPin.Visible  = true;
            }
            else
            {
                lblTitle.Text         = "UTILITY HUB";
                lblSubtitle.Visible   = true;
                btnSidebarToggle.Text = "⬛ Sidebar";
                btnSidebarToggle.Location = new Point(w - 265, 17);
                btnSidebarToggle.Size     = new Size(95, 30);
                btnPin.Visible = false;
            }

            pnlNavigation.Location = new Point(0, 65);
            pnlNavigation.Height   = h - 65;
            pnlContent.Location    = new Point(60, 65);
            pnlContent.Size        = new Size(w - 60, h - 65);

            pnlTabOsuContent.Size      = pnlContent.Size;
            pnlTabWuWaContent.Size     = pnlContent.Size;
            pnlTabSettingsContent.Size = pnlContent.Size;

            LayoutOsuTab(pnlContent.Width, pnlContent.Height);
            LayoutWuWaTab(pnlContent.Width, pnlContent.Height);
            LayoutSettingsTab(pnlContent.Width, pnlContent.Height);
        }

        private void LayoutOsuTab(int w, int h)
        {
            int cardW = (w - 60) / 2;

            pnlWacomCard.Location = new Point(20, 20);
            pnlWacomCard.Size     = new Size(cardW, 145);
            pnlRealCard.Location  = new Point(20 + cardW + 20, 20);
            pnlRealCard.Size      = new Size(cardW, 145);
            pnlLogsCard.Location  = new Point(20, 185);
            pnlLogsCard.Size      = new Size(w - 40, h - 185 - 15);

            // Wacom card internals
            int bw = (cardW - 50) / 2;
            btnDisableWacom.Location = new Point(20, 95); btnDisableWacom.Size = new Size(bw, 35);
            btnEnableWacom.Location  = new Point(20 + bw + 10, 95); btnEnableWacom.Size = new Size(bw, 35);

            // REAL card internals
            btnStartReal.Location = new Point(20, 95); btnStartReal.Size = new Size(bw, 35);
            btnStopReal.Location  = new Point(20 + bw + 10, 95); btnStopReal.Size = new Size(bw, 35);

            // Logs card internals
            int lw = pnlLogsCard.Width, lh = pnlLogsCard.Height;
            txtLogs.Location = new Point(20, 38);
            txtLogs.Size     = new Size(lw - 40, lh - 80);
            int btnY         = lh - 36;
            btnToggleConsole.Location = new Point(20, btnY);
            btnCopyLogs.Location      = new Point(lw - 155, btnY);
            btnClearLogs.Location     = new Point(lw - 80, btnY);
        }

        private void LayoutWuWaTab(int w, int h)
        {
            // Character card: fixed 280 wide, full height minus echo row
            int echoH      = 195;
            int topH       = h - echoH - 15;
            int charW      = Math.Min(280, (int)(w * 0.34));
            int rightX     = charW + 20;
            int rightW     = w - rightX - 15;
            int weaponH    = 115;

            pnlCharCard.Location  = new Point(15, 5);
            pnlCharCard.Size      = new Size(charW, topH);

            pnlWeaponCard.Location = new Point(rightX, 5);
            pnlWeaponCard.Size     = new Size(rightW, weaponH);

            pnlStatsCard.Location  = new Point(rightX, 5 + weaponH + 10);
            pnlStatsCard.Size      = new Size(rightW, topH - weaponH - 10);

            pnlEchoRow.Location    = new Point(15, topH + 10);
            pnlEchoRow.Size        = new Size(w - 30, echoH);

            LayoutCharCardInternals(charW, topH);
            LayoutWeaponCardInternals(rightW, weaponH);
            LayoutStatsCardInternals(rightW, pnlStatsCard.Height);
            LayoutEchoRow(w - 30, echoH);
        }

        private void LayoutCharCardInternals(int w, int h)
        {
            // Image fills most of the card
            int imgH = h - 90;
            pbCharImage.Location  = new Point(0, 40);
            pbCharImage.Size      = new Size(w, imgH);
            pbCharImage.Visible   = (charImage != null && !charEditMode);

            // Edit mode buttons at top
            btnCharUpload.Visible  = charEditMode;
            btnImgZoomIn.Visible   = charEditMode;
            btnImgZoomOut.Visible  = charEditMode;
            btnImgReset.Visible    = charEditMode;
            btnCharEditDone.Visible = charEditMode;

            // Name/level overlay at bottom
            lblCharName.Location    = new Point(12, h - 80);
            lblCharLevel.Location   = new Point(12, h - 55);
            lblCharElement.Location = new Point(12, h - 35);
            lblCharSeq.Location     = new Point(w - 35, h - 35);

            pnlCharCard.Invalidate();
        }

        private void LayoutWeaponCardInternals(int w, int h)
        {
            pbWeaponIcon.Location = new Point(12, 12);
            pbWeaponIcon.Size     = new Size(58, 58);
            txtWeaponName.Location = new Point(78, 10);
            txtWeaponName.Width    = w - 90;
            lblWeaponRarity.Location = new Point(78, 38);
            btnWeaponRarityUp.Location = new Point(78 + lblWeaponRarity.Width + 4, 38);
            btnWeaponRarityDn.Location = new Point(78 + lblWeaponRarity.Width + 24, 38);
            lblWeaponRefinement.Location = new Point(78, 62);
            btnWeaponRefUp.Location = new Point(78 + 28, 62);
            btnWeaponRefDn.Location = new Point(78 + 48, 62);
            txtWeaponLevel.Location = new Point(78 + 70, 62);
            btnWeaponUpload.Location = new Point(12, h - 30);
        }

        private void LayoutStatsCardInternals(int w, int h)
        {
            int rowH  = (h - 20) / 7;
            int valW  = 100;
            for (int i = 0; i < 7; i++)
            {
                lblStatNames[i].Location = new Point(12, 10 + i * rowH + (rowH - 14) / 2);
                txtStats[i].Location     = new Point(w - valW - 12, 8 + i * rowH);
                txtStats[i].Width        = valW;
            }
        }

        private void LayoutEchoRow(int w, int h)
        {
            int echoW  = (w - 4 * 8) / 5;
            int iconSz = Math.Min(56, h - 120);

            for (int i = 0; i < 5; i++)
            {
                pnlEcho[i].Location = new Point(i * (echoW + 8), 0);
                pnlEcho[i].Size     = new Size(echoW, h);

                pbEchoIcon[i].Location = new Point(8, 8);
                pbEchoIcon[i].Size     = new Size(iconSz, iconSz);

                txtEchoMain[i].Location = new Point(8 + iconSz + 4, 8);
                txtEchoMain[i].Width    = echoW - iconSz - 20;

                btnEchoUpload[i].Location = new Point(8, iconSz + 10);

                for (int j = 0; j < 5; j++)
                {
                    int subY = iconSz + 12 + j * 22 - (j > 0 ? 2 : 0);
                    btnEchoQuality[i][j].Location = new Point(6, subY + 4);
                    txtEchoSub[i][j].Location     = new Point(24, subY);
                    txtEchoSub[i][j].Width        = echoW - 30;
                }
            }
        }

        private void LayoutSettingsTab(int w, int h)
        {
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

        // ═════════════════════════════════════════════════════════════════════
        //  TAB NAVIGATION
        // ═════════════════════════════════════════════════════════════════════

        private void SetActiveTab(int idx)
        {
            currentTab = idx;
            pnlTabOsuContent.Visible      = (idx == 0);
            pnlTabWuWaContent.Visible     = (idx == 1);
            pnlTabSettingsContent.Visible = (idx == 2);

            Color inactiveBack = Color.FromArgb(28, 28, 31);
            Color inactiveFore = Color.FromArgb(161, 161, 170);
            btnTabOsu.BackColor      = inactiveBack; btnTabOsu.ForeColor      = inactiveFore;
            btnTabWuWa.BackColor     = inactiveBack; btnTabWuWa.ForeColor     = inactiveFore;
            btnTabSettings.BackColor = inactiveBack; btnTabSettings.ForeColor = inactiveFore;

            if (idx == 0) { btnTabOsu.ForeColor      = Color.FromArgb(139, 92, 246); btnTabOsu.BackColor      = Color.FromArgb(40, 38, 50); }
            if (idx == 1) { btnTabWuWa.ForeColor      = Color.FromArgb(6, 182, 212);  btnTabWuWa.BackColor     = Color.FromArgb(30, 45, 50); }
            if (idx == 2) { btnTabSettings.ForeColor  = Color.White;                   btnTabSettings.BackColor = Color.FromArgb(40, 40, 45); }

            pnlNavigation.Invalidate();
            LayoutControls();
        }

        // ═════════════════════════════════════════════════════════════════════
        //  SIDEBAR SLIDE LOGIC
        // ═════════════════════════════════════════════════════════════════════

        private void ToggleSidebarMode()
        {
            isSidebarMode = !isSidebarMode;

            if (isSidebarMode)
            {
                previousBounds = this.Bounds;
                var scr = Screen.FromControl(this);
                int sw  = Math.Max(340, this.Width < 420 ? this.Width : 340);
                this.Width  = sw;
                this.Height = scr.WorkingArea.Height;
                this.Left   = scr.WorkingArea.Right - sw;   // start fully visible
                this.Top    = scr.WorkingArea.Top;
                isPinned    = false; // auto-hide by default
                btnPin.Text = "📌";
                isSlidOut   = false;
            }
            else
            {
                isSlidOut = false;
                this.Bounds = previousBounds;
                btnPin.Visible = false;
            }
            LayoutControls();
        }

        private void TogglePinMode()
        {
            isPinned    = !isPinned;
            btnPin.Text = isPinned ? "🔒" : "📌";
            SaveConfig();

            if (isPinned)
            {
                isSlidOut  = false;
                this.Left  = Screen.FromControl(this).WorkingArea.Right - this.Width;
            }
        }

        private void SlideTimer_Tick(object sender, EventArgs e)
        {
            if (!isSidebarMode) return;

            var   scr       = Screen.FromControl(this);
            int   destShow  = scr.WorkingArea.Right - this.Width;
            int   destHide  = scr.WorkingArea.Right - 10;  // 10px tab handle visible
            Point mouse     = Cursor.Position;

            // Zone = either the full visible form OR the 10px edge strip when hidden
            bool mouseOver;
            if (isSlidOut)
                mouseOver = mouse.X >= scr.WorkingArea.Right - 12;
            else
                mouseOver = this.Bounds.Contains(mouse);

            int dest = (isPinned || mouseOver) ? destShow : destHide;

            if (this.Left < dest)
            {
                this.Left = Math.Min(dest, this.Left + SLIDE_SPEED);
                if (this.Left == destHide) isSlidOut = true;
            }
            else if (this.Left > dest)
            {
                this.Left = Math.Max(dest, this.Left - SLIDE_SPEED);
                if (this.Left == destHide) isSlidOut = true;
                if (this.Left == destShow) isSlidOut = false;
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        //  STATUS MONITORING
        // ═════════════════════════════════════════════════════════════════════

        private void CheckStatus()
        {
            bool newWacom = wacomService.QueryWacomActive();
            if (newWacom != isWacomActive)
            {
                isWacomActive = newWacom;
                lblWacomStatus.Text = isWacomActive ? "Status: ENABLED (ON)" : "Status: DISABLED (OFF)";
                pnlWacomStatusDot.Invalidate();
                AppendLog("[Wacom] " + (isWacomActive ? "ENABLED" : "DISABLED"));
            }

            bool newReal = realEngineService.IsRunning;
            if (newReal != isRealRunning)
            {
                isRealRunning = newReal;
                lblRealStatus.Text = isRealRunning ? "Status: RUNNING" : "Status: Stopped";
                pnlRealStatusDot.Invalidate();
                if (!isRealRunning)
                {
                    btnToggleConsole.Text    = "Show Console";
                    btnToggleConsole.Enabled = false;
                }
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        //  osu! PROCESS CONTROL
        // ═════════════════════════════════════════════════════════════════════

        private void RunBatchFile(string filename)
        {
            try
            {
                wacomService.RunBatchFile(filename);
            }
            catch (Exception ex)
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, filename);
                MessageBox.Show("Could not execute batch file:\n" + path + "\n" + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void StartLatencyReduction()
        {
            try
            {
                realEngineService.Start(configService.Config.RealExePath);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Could not start latency reduction engine. Set correct path in Settings.\n\n" + ex.Message, "REAL.exe Required",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void StopRealProcess()
        {
            realEngineService.Stop();
        }

        private void ToggleConsoleWindow()
        {
            realEngineService.ToggleConsoleWindow();
            btnToggleConsole.Text = realEngineService.IsConsoleVisible ? "Hide Console" : "Show Console";
        }

        // ═════════════════════════════════════════════════════════════════════
        //  WuWa CHARACTER BUILDER
        // ═════════════════════════════════════════════════════════════════════

        private void SetCharEditMode(bool edit)
        {
            charEditMode = edit;
            pbCharImage.Visible = !edit && charImage != null;
            LayoutCharCardInternals(pnlCharCard.Width, pnlCharCard.Height);
            pnlCharCard.Invalidate();
        }

        private void CharImage_Click(object sender, EventArgs e)
        {
            if (!charEditMode) SetCharEditMode(true);
        }

        private void CharImage_MouseDown(object sender, MouseEventArgs e)
        {
            if (charEditMode && e.Button == MouseButtons.Left)
            { imgDragging = true; imgDragStart = e.Location; }
        }

        private void CharImage_MouseMove(object sender, MouseEventArgs e)
        {
            if (imgDragging)
            {
                wuBuild.ImagePanX += e.X - imgDragStart.X;
                wuBuild.ImagePanY += e.Y - imgDragStart.Y;
                imgDragStart = e.Location;
                pnlCharCard.Invalidate();
            }
        }

        private void CharImage_MouseUp(object sender, MouseEventArgs e) { imgDragging = false; }

        private void UploadCharImage()
        {
            using (var ofd = new OpenFileDialog { Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp;*.webp", Title = "Select Character Image" })
            {
                if (ofd.ShowDialog() != DialogResult.OK) return;
                try
                {
                    if (charImage != null) { charImage.Dispose(); charImage = null; }
                    charImage            = Image.FromFile(ofd.FileName);
                    wuBuild.CharImagePath = ofd.FileName;
                    wuBuild.ImagePanX    = 0; wuBuild.ImagePanY = 0; wuBuild.ImageScale = 1f;
                    pbCharImage.Image    = charImage;
                    pnlCharCard.Invalidate();
                }
                catch (Exception ex) { MessageBox.Show("Could not load image:\n" + ex.Message); }
            }
        }

        private void UploadWeaponImage()
        {
            using (var ofd = new OpenFileDialog { Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp", Title = "Select Weapon Icon" })
            {
                if (ofd.ShowDialog() != DialogResult.OK) return;
                try
                {
                    if (weaponImage != null) { weaponImage.Dispose(); weaponImage = null; }
                    weaponImage           = Image.FromFile(ofd.FileName);
                    wuBuild.WeaponImagePath = ofd.FileName;
                    pbWeaponIcon.Image    = weaponImage;
                }
                catch (Exception ex) { MessageBox.Show("Could not load image:\n" + ex.Message); }
            }
        }

        private void UploadEchoImage(int idx)
        {
            using (var ofd = new OpenFileDialog { Filter = "Images|*.png;*.jpg;*.jpeg;*.bmp", Title = "Select Echo Icon" })
            {
                if (ofd.ShowDialog() != DialogResult.OK) return;
                try
                {
                    if (echoImages[idx] != null) { echoImages[idx].Dispose(); echoImages[idx] = null; }
                    echoImages[idx]           = Image.FromFile(ofd.FileName);
                    wuBuild.Echoes[idx].ImagePath = ofd.FileName;
                    pbEchoIcon[idx].Image     = echoImages[idx];
                }
                catch (Exception ex) { MessageBox.Show("Could not load image:\n" + ex.Message); }
            }
        }

        private void PromptEditCharName()
        {
            using (var frm = new Form { Size = new Size(320, 140), StartPosition = FormStartPosition.CenterParent,
                                        Text = "Edit Character", FormBorderStyle = FormBorderStyle.FixedDialog })
            {
                var tb = new TextBox { Text = wuBuild.ResonatorName, Dock = DockStyle.Top };
                var ok = new Button  { Text = "OK", DialogResult = DialogResult.OK, Dock = DockStyle.Bottom };
                frm.Controls.AddRange(new Control[] { tb, ok });
                frm.AcceptButton = ok;
                if (frm.ShowDialog() == DialogResult.OK)
                {
                    wuBuild.ResonatorName = tb.Text;
                    lblCharName.Text      = tb.Text;
                }
            }
        }

        private void ChangeWeaponRarity(int delta)
        {
            wuBuild.WeaponRarity  = Math.Max(1, Math.Min(5, wuBuild.WeaponRarity + delta));
            lblWeaponRarity.Text  = new string('★', wuBuild.WeaponRarity);
            pnlWeaponCard.Invalidate();
        }

        private void ChangeWeaponRef(int delta)
        {
            wuBuild.WeaponRefinement = Math.Max(1, Math.Min(5, wuBuild.WeaponRefinement + delta));
            lblWeaponRefinement.Text = "R" + wuBuild.WeaponRefinement;
        }

        private void CycleEchoQuality(int echoIdx, int statIdx)
        {
            int q = wuBuild.Echoes[echoIdx].Substats[statIdx].Quality;
            q = (q + 1) % 5;  // 0=unrated, 1=great, 2=good, 3=ok, 4=bad
            wuBuild.Echoes[echoIdx].Substats[statIdx].Quality = q;
            btnEchoQuality[echoIdx][statIdx].BackColor = QualityColor(q);
            new ToolTip().SetToolTip(btnEchoQuality[echoIdx][statIdx], QualityLabel(q));
        }

        private void SaveStatFromIndex(int idx)
        {
            string v = txtStats[idx].Text;
            switch (idx)
            {
                case 0: wuBuild.StatHP  = v; break;
                case 1: wuBuild.StatATK = v; break;
                case 2: wuBuild.StatDEF = v; break;
                case 3: wuBuild.StatCritRate   = v; break;
                case 4: wuBuild.StatCritDMG    = v; break;
                case 5: wuBuild.StatEnergyRegen = v; break;
                case 6: wuBuild.StatSklDMG = v; break;
            }
        }

        private Rectangle GetCharImageDrawRect(int panelW, int panelH)
        {
            if (charImage == null) return Rectangle.Empty;
            float aspect = (float)charImage.Width / charImage.Height;
            int dw = (int)(panelH * aspect * wuBuild.ImageScale);
            int dh = (int)(panelH * wuBuild.ImageScale);
            int dx = (panelW - dw) / 2 + wuBuild.ImagePanX;
            int dy = (panelH - dh) / 2 + wuBuild.ImagePanY;
            return new Rectangle(dx, dy + 40, dw, dh);
        }

        private Color QualityColor(int q)
        {
            switch (q)
            {
                case 1: return Color.FromArgb(251, 191, 36);  // great – gold
                case 2: return Color.FromArgb(16, 185, 129);  // good  – green
                case 3: return Color.FromArgb(99, 172, 229);  // ok    – blue
                case 4: return Color.FromArgb(239, 68, 68);   // bad   – red
                default: return Color.FromArgb(55, 55, 70);   // unrated – gray
            }
        }

        private string QualityLabel(int q)
        {
            switch (q)
            {
                case 1: return "⭐ Great roll!";
                case 2: return "✔ Good roll";
                case 3: return "~ Ok roll";
                case 4: return "✗ Bad roll";
                default: return "Unrated – click to evaluate";
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        //  WuWa BUILD PERSISTENCE
        // ═════════════════════════════════════════════════════════════════════

        private void SaveWuWaBuild()
        {
            configService.SaveWuWaBuild();
        }

        private void LoadWuWaBuild()
        {
            configService.LoadWuWaBuild((charPath, weaponPath, echoPaths) =>
            {
                try
                {
                    if (charPath != null && File.Exists(charPath)) charImage = Image.FromFile(charPath);
                    if (weaponPath != null && File.Exists(weaponPath)) weaponImage = Image.FromFile(weaponPath);
                    foreach (var kvp in echoPaths)
                    {
                        if (File.Exists(kvp.Value))
                            echoImages[kvp.Key] = Image.FromFile(kvp.Value);
                    }
                }
                catch { }
            });
            ApplyWuWaBuildToUI();
        }

        private void ApplyWuWaBuildToUI()
        {
            lblCharName.Text    = wuBuild.ResonatorName;
            lblCharLevel.Text   = "Lv." + wuBuild.Level;
            lblCharElement.Text = wuBuild.Element;
            lblCharElement.ForeColor = GetElementColor(wuBuild.Element);
            lblCharSeq.Text     = "S" + wuBuild.Sequence;

            if (charImage != null)   pbCharImage.Image   = charImage;
            if (weaponImage != null) pbWeaponIcon.Image  = weaponImage;
            for (int i = 0; i < 5; i++)
                if (echoImages[i] != null) pbEchoIcon[i].Image = echoImages[i];

            txtWeaponName.Text  = wuBuild.WeaponName;
            txtWeaponLevel.Text = wuBuild.WeaponLevel;
            lblWeaponRarity.Text = new string('★', wuBuild.WeaponRarity);
            lblWeaponRefinement.Text = "R" + wuBuild.WeaponRefinement;

            string[] statVals = {
                wuBuild.StatHP, wuBuild.StatATK, wuBuild.StatDEF,
                wuBuild.StatCritRate, wuBuild.StatCritDMG,
                wuBuild.StatEnergyRegen, wuBuild.StatSklDMG
            };
            for (int i = 0; i < 7; i++) txtStats[i].Text = statVals[i];

            for (int i = 0; i < 5; i++)
            {
                txtEchoMain[i].Text = wuBuild.Echoes[i].MainStatName + " " + wuBuild.Echoes[i].MainStatValue;
                for (int j = 0; j < 5; j++)
                {
                    txtEchoSub[i][j].Text = wuBuild.Echoes[i].Substats[j].Name + " " + wuBuild.Echoes[i].Substats[j].Value;
                    btnEchoQuality[i][j].BackColor = QualityColor(wuBuild.Echoes[i].Substats[j].Quality);
                }
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        //  CONFIG PERSISTENCE
        // ═════════════════════════════════════════════════════════════════════

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
                AppendLog("[Controller] Path set: " + configService.Config.RealExePath);
            }
        }

        // ═════════════════════════════════════════════════════════════════════
        //  LOGGING
        // ═════════════════════════════════════════════════════════════════════

        private void AppendLog(string msg)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(AppendLog), msg); return; }
            string line = string.Format("[{0}] {1}", DateTime.Now.ToString("HH:mm:ss"), msg);
            txtLogs.AppendText(line + Environment.NewLine);
            if (txtLogs.TextLength > 80000) txtLogs.Text = txtLogs.Text.Substring(40000);
            txtLogs.SelectionStart = txtLogs.TextLength;
            txtLogs.ScrollToCaret();
        }

        // ═════════════════════════════════════════════════════════════════════
        //  TRAY
        // ═════════════════════════════════════════════════════════════════════

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

        private void ShutdownApp() { realEngineService.Stop(); this.Close(); }

        // ═════════════════════════════════════════════════════════════════════
        //  WINDOW MANAGEMENT
        // ═════════════════════════════════════════════════════════════════════

        protected override void WndProc(ref Message m)
        {
            const int WM_NCHITTEST = 0x84;
            const int HTLEFT=10,HTRIGHT=11,HTTOP=12,HTTOPLEFT=13,HTTOPRIGHT=14,
                      HTBOTTOM=15,HTBOTTOMLEFT=16,HTBOTTOMRIGHT=17;

            if (m.Msg == WM_NCHITTEST)
            {
                var pos = this.PointToClient(new Point(m.LParam.ToInt32()));
                int b = 6;
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

        // ═════════════════════════════════════════════════════════════════════
        //  CLEANUP
        // ═════════════════════════════════════════════════════════════════════

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            SaveWuWaBuild();
            base.OnFormClosing(e);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            realEngineService.Stop();
            statusTimer?.Stop(); statusTimer?.Dispose();
            slideTimer?.Stop();  slideTimer?.Dispose();
            notifyIcon.Visible = false; notifyIcon.Dispose();
            if (charImage  != null) charImage.Dispose();
            if (weaponImage != null) weaponImage.Dispose();
            for (int i=0;i<5;i++) if (echoImages[i]!=null) echoImages[i].Dispose();
            if (appIcon != null) { Win32.DestroyIcon(appIcon.Handle); appIcon.Dispose(); }
            base.OnFormClosed(e);
        }
    }

    // Missing PictureMode alias (C#5 compat)
    internal static class PictureMode
    {
        public static PictureBoxSizeMode Zoom => PictureBoxSizeMode.Zoom;
    }
}

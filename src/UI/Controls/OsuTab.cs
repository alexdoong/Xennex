using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace WacomRealController
{
    public class OsuTab : Panel
    {
        private readonly WacomService wacomService;
        private readonly RealEngineService realEngineService;
        private readonly ConfigService configService;

        private Panel  pnlWacomCard, pnlRealCard, pnlLogsCard;
        private Panel  pnlWacomStatusDot, pnlRealStatusDot;
        private Label  lblWacomTitle, lblWacomStatus;
        private Label  lblRealTitle, lblRealStatus;
        private Label  lblLogsTitle;
        private Button btnDisableWacom, btnEnableWacom;
        private Button btnStartReal, btnStopReal;
        private Button btnToggleConsole, btnCopyLogs, btnClearLogs;
        private TextBox txtLogs;

        private bool isWacomActive = false;
        private bool isRealRunning = false;

        public OsuTab(WacomService wacomService, RealEngineService realEngineService, ConfigService configService)
        {
            this.wacomService = wacomService;
            this.realEngineService = realEngineService;
            this.configService = configService;

            this.BackColor = Color.Transparent;
            this.SizeChanged += (s, e) => LayoutTab(this.Width, this.Height);

            BuildOsuTab();

            // Register events
            this.wacomService.OnLogReceived += AppendLog;
            this.realEngineService.OnLogReceived += AppendLog;

            this.wacomService.OnStatusChanged += CheckStatus;
            this.realEngineService.OnStatusChanged += CheckStatus;

            this.realEngineService.OnConsoleAvailable += (avail) =>
            {
                btnToggleConsole.Enabled = avail;
                btnToggleConsole.Text = (avail && realEngineService.IsConsoleVisible) ? "Hide Console" : "Show Console";
            };

            CheckStatus();
        }

        private void BuildOsuTab()
        {
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

            this.Controls.AddRange(new Control[] { pnlWacomCard, pnlRealCard, pnlLogsCard });
        }

        public void CheckStatus()
        {
            if (this.InvokeRequired) { this.BeginInvoke(new Action(CheckStatus)); return; }
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

        public void AppendLog(string msg)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(AppendLog), msg); return; }
            string line = string.Format("[{0}] {1}", DateTime.Now.ToString("HH:mm:ss"), msg);
            txtLogs.AppendText(line + Environment.NewLine);
            if (txtLogs.TextLength > 80000) txtLogs.Text = txtLogs.Text.Substring(40000);
            txtLogs.SelectionStart = txtLogs.TextLength;
            txtLogs.ScrollToCaret();
        }

        private void LayoutTab(int w, int h)
        {
            if (pnlWacomCard == null) return;

            if (w < 400)
            {
                // Stacked layout (Sidebar Mode)
                pnlWacomCard.Location = new Point(20, 15);
                pnlWacomCard.Size     = new Size(w - 40, 130);
                pnlRealCard.Location  = new Point(20, 160);
                pnlRealCard.Size      = new Size(w - 40, 130);
                pnlLogsCard.Location  = new Point(20, 305);
                pnlLogsCard.Size      = new Size(w - 40, h - 305 - 15);

                int cardW = w - 40;
                int bw = (cardW - 50) / 2;
                btnDisableWacom.Location = new Point(20, 80); btnDisableWacom.Size = new Size(bw, 35);
                btnEnableWacom.Location  = new Point(20 + bw + 10, 80); btnEnableWacom.Size = new Size(bw, 35);

                btnStartReal.Location = new Point(20, 80); btnStartReal.Size = new Size(bw, 35);
                btnStopReal.Location  = new Point(20 + bw + 10, 80); btnStopReal.Size = new Size(bw, 35);
            }
            else
            {
                // Side-by-side layout (Windowed Mode)
                int cardW = (w - 60) / 2;
                pnlWacomCard.Location = new Point(20, 20);
                pnlWacomCard.Size     = new Size(cardW, 145);
                pnlRealCard.Location  = new Point(20 + cardW + 20, 20);
                pnlRealCard.Size      = new Size(cardW, 145);
                pnlLogsCard.Location  = new Point(20, 185);
                pnlLogsCard.Size      = new Size(w - 40, h - 185 - 15);

                int bw = (cardW - 50) / 2;
                btnDisableWacom.Location = new Point(20, 95); btnDisableWacom.Size = new Size(bw, 35);
                btnEnableWacom.Location  = new Point(20 + bw + 10, 95); btnEnableWacom.Size = new Size(bw, 35);

                btnStartReal.Location = new Point(20, 95); btnStartReal.Size = new Size(bw, 35);
                btnStopReal.Location  = new Point(20 + bw + 10, 95); btnStopReal.Size = new Size(bw, 35);
            }

            // Logs card internals
            int lw = pnlLogsCard.Width, lh = pnlLogsCard.Height;
            txtLogs.Location = new Point(20, 38);
            txtLogs.Size     = new Size(lw - 40, lh - 80);
            int btnY         = lh - 36;
            btnToggleConsole.Location = new Point(20, btnY);
            btnCopyLogs.Location      = new Point(lw - 155, btnY);
            btnClearLogs.Location     = new Point(lw - 80, btnY);
        }

        // Helpers wrapper
        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
        private Panel Card() => UIHelpers.Card();
        private Label TitleLabel(string text, Color color) => UIHelpers.TitleLabel(text, color);
        private Label InfoLabel(string text, Point loc) => UIHelpers.InfoLabel(text, loc);
        private Panel StatusDotPanel(Func<bool> activeGetter) => UIHelpers.StatusDotPanel(activeGetter);
    }
}

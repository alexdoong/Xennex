using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Windows.Forms;

namespace WacomRealController
{
    public class WuWaTab : Panel
    {
        private readonly ConfigService configService;

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

        // WuWa build state
        private WuWaBuild wuBuild => configService.Build;
        private Image     charImage   = null;
        private Image[]   echoImages  = new Image[5];
        private Image     weaponImage = null;

        public WuWaTab(ConfigService configService)
        {
            this.configService = configService;

            this.BackColor = Color.Transparent;
            this.SizeChanged += (s, e) => LayoutTab(this.Width, this.Height);

            BuildWuWaTab();
            LoadWuWaBuild();
        }

        private void BuildWuWaTab()
        {
            BuildCharCard();
            BuildWeaponCard();
            BuildStatsCard();
            BuildEchoRow();

            this.Controls.AddRange(new Control[] {
                pnlCharCard, pnlWeaponCard, pnlStatsCard, pnlEchoRow });
        }

        private void BuildCharCard()
        {
            pnlCharCard = new Panel { BackColor = Color.FromArgb(10, 14, 26) };
            pnlCharCard.Paint += CharCard_Paint;

            pbCharImage = new PictureBox
            {
                SizeMode  = PictureBoxSizeMode.Zoom,
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
                ForeColor = UIHelpers.GetElementColor(wuBuild.Element),
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
                SizeMode  = PictureBoxSizeMode.Zoom,
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
                    SizeMode  = PictureBoxSizeMode.Zoom,
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

        public void SaveBuild()
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
            lblCharElement.ForeColor = UIHelpers.GetElementColor(wuBuild.Element);
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

        private void LayoutTab(int w, int h)
        {
            if (pnlCharCard == null) return;
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
            Color elemColor = UIHelpers.GetElementColor(wuBuild.Element);
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

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                if (charImage != null) charImage.Dispose();
                if (weaponImage != null) weaponImage.Dispose();
                for (int i = 0; i < 5; i++)
                    if (echoImages[i] != null) echoImages[i].Dispose();
            }
            base.Dispose(disposing);
        }

        // Helpers wrapper
        private Button Btn(string text, Point loc, Size sz, Color back, Color fore) => UIHelpers.Btn(text, loc, sz, back, fore);
        private Button SmallBtn(string text) => UIHelpers.SmallBtn(text);
        private Panel Card() => UIHelpers.Card();
        private Label TitleLabel(string text, Color color) => UIHelpers.TitleLabel(text, color);
        private Label InfoLabel(string text, Point loc) => UIHelpers.InfoLabel(text, loc);
        private TextBox EditBox(string text, Point loc, Size sz) => UIHelpers.EditBox(text, loc, sz);
    }
}

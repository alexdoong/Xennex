using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace WacomRealController
{
    public static class UIHelpers
    {
        public static readonly Dictionary<string, Color> ElementColors = new Dictionary<string, Color>
        {
            { "Glacio",  Color.FromArgb( 56, 189, 248) },
            { "Fusion",  Color.FromArgb(251, 146,  60) },
            { "Electro", Color.FromArgb(192, 132, 252) },
            { "Aero",    Color.FromArgb( 52, 211, 153) },
            { "Spectro", Color.FromArgb(250, 204,  21) },
            { "Havoc",   Color.FromArgb(244,  63,  94) },
        };

        public static Color GetElementColor(string element)
        {
            Color c;
            return ElementColors.TryGetValue(element, out c) ? c : Color.FromArgb(200, 200, 200);
        }

        public static Color LightenColor(Color c, int amt)
        {
            if (c == Color.Transparent) return Color.FromArgb(50, 50, 55);
            return Color.FromArgb(c.A, Math.Min(255, c.R + amt), Math.Min(255, c.G + amt), Math.Min(255, c.B + amt));
        }

        public static Button Btn(string text, Point loc, Size sz, Color back, Color fore)
        {
            var b = new Button
            {
                Text      = text, Location = loc, Size = sz,
                FlatStyle = FlatStyle.Flat,
                BackColor = back, ForeColor = fore,
                Font      = new Font("Segoe UI", 9F, FontStyle.Bold),
                Cursor    = Cursors.Hand
            };
            b.FlatAppearance.BorderSize = 0;
            b.FlatAppearance.MouseOverBackColor = LightenColor(back, 18);
            return b;
        }

        public static Button SmallBtn(string text)
        {
            var b = Btn(text, Point.Empty, new Size(18, 18),
                Color.FromArgb(35, 35, 50), Color.FromArgb(200, 200, 220));
            b.Font = new Font("Segoe UI", 7.5F, FontStyle.Bold);
            return b;
        }

        public static Panel Card()
        {
            var p = new Panel { BackColor = Color.FromArgb(22, 22, 26) };
            p.Paint += (s, e) =>
            {
                using (var pen = new Pen(Color.FromArgb(39, 39, 42), 1))
                    e.Graphics.DrawRectangle(pen, 0, 0, p.Width - 1, p.Height - 1);
            };
            return p;
        }

        public static Label TitleLabel(string text, Color color)
            => new Label { Text = text, Font = new Font("Segoe UI", 10.5F, FontStyle.Bold),
                           ForeColor = color, Location = new Point(20, 15), AutoSize = true };

        public static Label InfoLabel(string text, Point loc)
            => new Label { Text = text, Font = new Font("Segoe UI", 8.5F),
                           ForeColor = Color.FromArgb(161, 161, 170), Location = loc, AutoSize = true };

        public static Panel StatusDotPanel(Func<bool> activeGetter)
        {
            var p = new Panel { Location = new Point(20, 50), Size = new Size(16, 16), BackColor = Color.Transparent };
            p.Paint += (s, e) =>
            {
                bool active = activeGetter();
                Color c = active ? Color.FromArgb(16, 185, 129) : Color.FromArgb(239, 68, 68);
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                using (var b = new SolidBrush(Color.FromArgb(40, c)))  e.Graphics.FillEllipse(b, 0, 0, 15, 15);
                using (var b = new SolidBrush(c))                       e.Graphics.FillEllipse(b, 3, 3, 9, 9);
            };
            return p;
        }

        public static TextBox EditBox(string text, Point loc, Size sz)
            => new TextBox
            {
                Text = text, Location = loc, Size = sz,
                Font = new Font("Segoe UI", 9.5F, FontStyle.Bold),
                ForeColor = Color.White, BackColor = Color.FromArgb(22, 28, 42),
                BorderStyle = BorderStyle.None
            };

        public static CheckBox Chk(string text, bool chkd)
            => new CheckBox
            {
                Text = text, Checked = chkd, AutoSize = true,
                Font = new Font("Segoe UI", 9F), FlatStyle = FlatStyle.Flat,
                ForeColor = Color.FromArgb(209, 213, 219)
            };
    }
}

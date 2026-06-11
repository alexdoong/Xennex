using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace WacomRealController
{
    public class PullTab : Panel
    {
        private bool isHovered = false;
        private bool isCollapsed = true;

        public bool IsCollapsed
        {
            get => isCollapsed;
            set
            {
                if (isCollapsed != value)
                {
                    isCollapsed = value;
                    this.Invalidate();
                }
            }
        }

        public PullTab()
        {
            this.Size = new Size(26, 90);
            this.BackColor = Color.Transparent;
            this.Cursor = Cursors.Hand;
            this.DoubleBuffered = true;

            this.MouseEnter += (s, e) => { isHovered = true; this.Invalidate(); };
            this.MouseLeave += (s, e) => { isHovered = false; this.Invalidate(); };
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;

            int w = this.Width;
            int h = this.Height;

            // Draw a rounded tab protruding on the left (rounded top-left, bottom-left, flat on the right)
            using (var path = new GraphicsPath())
            {
                int r = 8; // radius of corners
                // Top-right (flat)
                path.AddLine(w, 0, w, 0);
                // Bottom-right (flat)
                path.AddLine(w, h, w, h);
                // Bottom-left (rounded)
                path.AddArc(0, h - 2 * r - 1, 2 * r, 2 * r, 90, 90);
                // Top-left (rounded)
                path.AddArc(0, 0, 2 * r, 2 * r, 180, 90);
                path.CloseFigure();

                // Colors: glassmorphic dark grey, highlights when hovered
                Color backColor = isHovered 
                    ? Color.FromArgb(220, 139, 92, 246)  // light purple
                    : Color.FromArgb(200, 20, 20, 22);  // dark grey
                
                using (var brush = new SolidBrush(backColor))
                {
                    g.FillPath(brush, path);
                }

                // Border
                Color borderColor = isHovered 
                    ? Color.FromArgb(255, 167, 139, 250) 
                    : Color.FromArgb(100, 63, 63, 70);
                using (var pen = new Pen(borderColor, 1.5f))
                {
                    g.DrawPath(pen, path);
                }
            }

            // Draw arrow chevron pointing left (<) or right (>)
            // Collapsed -> points Left (<) to pull it in
            // Expanded -> points Right (>) to push it out
                        using (var pen = new Pen(Color.FromArgb(228, 228, 231), 2f))
            {
                pen.LineJoin = LineJoin.Miter;
                int ax = w / 2 + (isCollapsed ? 1 : -1);
                int ay = h / 2;
                int size = 4;

                if (isCollapsed)
                {
                    // Draw <
                    g.DrawLine(pen, ax + size - 1, ay - size, ax - size + 1, ay);
                    g.DrawLine(pen, ax - size + 1, ay, ax + size - 1, ay + size);
                }
                else
                {
                    // Draw >
                    g.DrawLine(pen, ax - size + 1, ay - size, ax + size - 1, ay);
                    g.DrawLine(pen, ax + size - 1, ay, ax - size + 1, ay + size);
                }
            }
        }
    }
}

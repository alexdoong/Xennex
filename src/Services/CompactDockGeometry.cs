using System;
using System.Drawing;

namespace Xennex.Services
{
    // All coordinates here are physical desktop pixels, including negative monitor origins.
    public readonly record struct CompactDockGeometry(
        Rectangle ShownRect,
        Rectangle HiddenRect,
        string EffectiveCollapseEdge,
        int HandleThickness)
    {
        public static string ResolveEffectiveEdge(string position, string collapseEdge)
        {
            if (!string.IsNullOrWhiteSpace(collapseEdge) && collapseEdge != "Auto")
            {
                if (collapseEdge == "Top" || collapseEdge == "Left" || collapseEdge == "Right")
                    return collapseEdge;
            }
            return position switch
            {
                "TopLeft" => "Top",
                "MiddleLeft" => "Left",
                _ => "Right"
            };
        }

        public static CompactDockGeometry CalculateDpi(
            Rectangle work,
            int width,
            int height,
            string position,
            double scaleX,
            double scaleY,
            int inset = 0,
            int verticalPercent = -1,
            string collapseEdge = "Auto")
        {
            string effectiveEdge = ResolveEffectiveEdge(position, collapseEdge);
            int handleThicknessX = Math.Clamp((int)Math.Round(16 * scaleX), 1, width);
            int handleThicknessY = Math.Clamp((int)Math.Round(16 * scaleY), 1, height);

            bool isLeftPos = position == "TopLeft" || position == "MiddleLeft";
            int gap = Math.Clamp((int)Math.Round(inset * scaleX), 0, Math.Max(0, work.Width - width));
            int percent = verticalPercent < 0 ? (position == "TopLeft" ? 0 : 50) : Math.Clamp(verticalPercent, 0, 100);
            int shownX = isLeftPos ? work.Left + gap : work.Right - gap - width;
            int shownY = work.Top + (int)Math.Round(Math.Max(0, work.Height - height) * percent / 100.0);

            Rectangle shownRect = new(shownX, shownY, width, height);
            if (string.IsNullOrWhiteSpace(collapseEdge) || collapseEdge == "Auto")
            {
                int Distance(string edge) => edge == "Top" ? shownRect.Top - work.Top
                    : edge == "Left" ? shownRect.Left - work.Left : work.Right - shownRect.Right;
                // Preset breaks ties, but the nearest real edge determines automatic docking.
                foreach (string edge in new[] { "Top", "Left", "Right" })
                    if (Distance(edge) < Distance(effectiveEdge)) effectiveEdge = edge;
            }
            Rectangle hiddenRect;

            if (effectiveEdge == "Top")
            {
                // Collapse upward to the top edge of the monitor, maintaining X
                hiddenRect = new Rectangle(shownX, work.Top, width, handleThicknessY);
            }
            else if (effectiveEdge == "Left")
            {
                // Collapse to the left edge of the working area
                hiddenRect = new Rectangle(work.Left, shownY, handleThicknessX, height);
            }
            else // "Right"
            {
                // Collapse to the right edge of the working area
                hiddenRect = new Rectangle(work.Right - handleThicknessX, shownY, handleThicknessX, height);
            }

            int handle = effectiveEdge == "Top" ? handleThicknessY : handleThicknessX;
            return new(shownRect, hiddenRect, effectiveEdge, handle);
        }

        public static CompactDockGeometry Calculate(
            Rectangle work,
            int width,
            int height,
            string position,
            double scale,
            int inset = 0,
            int verticalPercent = -1,
            string collapseEdge = "Auto") =>
            CalculateDpi(work, width, height, position, scale, scale, inset, verticalPercent, collapseEdge);

        public Rectangle GetInterpolatedRect(double progress)
        {
            double t = Math.Clamp(progress, 0.0, 1.0);
            int x = (int)Math.Round(HiddenRect.X + t * (ShownRect.X - HiddenRect.X));
            int y = (int)Math.Round(HiddenRect.Y + t * (ShownRect.Y - HiddenRect.Y));
            int right = (int)Math.Round(HiddenRect.Right + t * (ShownRect.Right - HiddenRect.Right));
            int bottom = (int)Math.Round(HiddenRect.Bottom + t * (ShownRect.Bottom - HiddenRect.Bottom));
            int w = Math.Max(1, right - x);
            int h = Math.Max(1, bottom - y);
            return new Rectangle(x, y, w, h);
        }

        public int ShownLeft => ShownRect.Left;
        public int HiddenLeft => HiddenRect.Left;
        public int Top => ShownRect.Top;
        public int HandleWidth => EffectiveCollapseEdge == "Top" ? ShownRect.Width : HandleThickness;
        public int LeftForWidth(int fullWidth, int visibleWidth)
        {
            if (EffectiveCollapseEdge == "Top") return ShownRect.Left;
            return ShownLeft == HiddenLeft ? ShownLeft : ShownLeft + fullWidth - visibleWidth;
        }
    }
}

using System;
using System.Windows;
using Xennex.UI;

namespace WacomRealController
{
    public class Program
    {
        [STAThread]
        public static void Main()
        {
            var app = new Application();
            app.Run(new MainWindow());
        }
    }
}

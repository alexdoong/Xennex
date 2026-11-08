using System;
using System.Threading;
using System.Windows.Threading;

namespace Xennex.Services
{
    /// <summary>Signals the existing process without depending on a visible window handle.</summary>
    internal sealed class SingleInstanceCoordinator : IDisposable
    {
        private const string MutexName = @"Local\Xennex.SingleInstance";
        private const string ActivationName = @"Local\Xennex.Activate";
        private readonly Mutex _mutex;
        private readonly EventWaitHandle _activation;
        private readonly ManualResetEvent _stopping = new(false);
        private Thread _listener;
        private bool _disposed;

        public bool IsPrimary { get; }

        public SingleInstanceCoordinator()
        {
            _mutex = new Mutex(true, MutexName, out bool createdNew);
            IsPrimary = createdNew;
            _activation = new EventWaitHandle(false, EventResetMode.AutoReset, ActivationName);
        }

        public void SignalPrimary() => _activation.Set();

        public void StartListening(Dispatcher dispatcher, Action restore)
        {
            if (!IsPrimary || _listener != null) return;
            _listener = new Thread(() => Listen(dispatcher, restore))
            {
                IsBackground = true,
                Name = "Xennex instance activation"
            };
            _listener.Start();
        }

        private void Listen(Dispatcher dispatcher, Action restore)
        {
            WaitHandle[] handles = { _activation, _stopping };
            while (WaitHandle.WaitAny(handles) == 0)
            {
                try
                {
                    if (!dispatcher.HasShutdownStarted) dispatcher.BeginInvoke(restore);
                }
                catch (Exception ex) { AppLog.Error("Activation", ex); }
            }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _stopping.Set();
            _listener?.Join(TimeSpan.FromSeconds(1));
            _activation.Dispose();
            _stopping.Dispose();
            if (IsPrimary) _mutex.ReleaseMutex();
            _mutex.Dispose();
        }
    }
}

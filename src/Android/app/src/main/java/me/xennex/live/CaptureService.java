package me.xennex.live;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.drawable.Icon;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.util.Log;

public final class CaptureService extends Service {
    private static final String CHANNEL_ID = "capture";
    private static final int NOTIFICATION_ID = 1;

    static volatile String status = "Pronto para compartilhar.";
    static volatile boolean running;

    private HandlerThread thread;
    private Handler worker;
    private AndroidCapture capture;
    private AndroidRoomClient room;
    private volatile boolean closing;
    private volatile boolean endedWithMessage;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        thread = new HandlerThread("XennexSession");
        thread.start();
        worker = new Handler(thread.getLooper());

        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Compartilhamento de tela",
            NotificationManager.IMPORTANCE_LOW
        );
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || "stop".equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (running) {
            return START_NOT_STICKY;
        }
        Intent permission = extractProjectionIntent(intent);
        String code = RoomAddress.normalize(intent.getStringExtra("room"));
        String name = intent.getStringExtra("name");
        if (permission == null || code.isEmpty() || name == null || name.length() > 40) {
            stopSelf();
            return START_NOT_STICKY;
        }

        Notification notification = buildForegroundNotification();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }

        running = true;
        status = "Preparando captura e conexão…";
        worker.post(() -> startSession(permission, code, name));
        return START_NOT_STICKY;
    }

    private Notification buildForegroundNotification() {
        int flags = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT;
        Intent stopIntent = new Intent(this, CaptureService.class).setAction("stop");
        PendingIntent stop = PendingIntent.getService(this, 1, stopIntent, flags);
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), flags);

        Notification.Action stopAction = new Notification.Action.Builder((Icon) null, "Parar", stop).build();
        return new Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("Xennex está compartilhando a tela")
            .setContentText("Toque em Parar para encerrar.")
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(stopAction)
            .build();
    }

    private void startSession(Intent permission, String code, String name) {
        if (closing) {
            return;
        }
        try {
            capture = new AndroidCapture(
                this,
                worker,
                permission,
                () -> worker.post(() -> finish("A captura foi encerrada pelo Android."))
            );
            room = new AndroidRoomClient(
                worker,
                capture.factory,
                capture.track,
                code,
                name,
                message -> status = message,
                this::finish
            );
            room.start();
        } catch (RuntimeException error) {
            Log.e("XennexCapture", "Falha ao iniciar sessao: " + error.getClass().getSimpleName());
            finish("Não foi possível preparar a transmissão. Abra o app e tente novamente.");
        }
    }

    private static Intent extractProjectionIntent(Intent intent) {
        if (Build.VERSION.SDK_INT >= 33) {
            return intent.getParcelableExtra("projection", Intent.class);
        }
        return extractLegacyProjectionIntent(intent);
    }

    @SuppressWarnings("deprecation")
    private static Intent extractLegacyProjectionIntent(Intent intent) {
        return intent.getParcelableExtra("projection");
    }

    private void finish(String message) {
        endedWithMessage = true;
        status = message;
        stopSelf();
    }

    @Override
    public void onDestroy() {
        closing = true;
        if (!endedWithMessage) {
            status = "Transmissão encerrada.";
        }
        worker.post(() -> {
            try {
                if (room != null) {
                    room.close();
                }
            } finally {
                try {
                    if (capture != null) {
                        capture.close();
                    }
                } finally {
                    running = false;
                    thread.quitSafely();
                }
            }
        });
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
}

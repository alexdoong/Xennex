package me.xennex.live;

import android.content.Context;
import android.content.Intent;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.media.projection.MediaProjection;
import android.os.Build;
import android.os.Handler;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.Display;
import android.view.WindowManager;
import org.webrtc.DefaultVideoDecoderFactory;
import org.webrtc.DefaultVideoEncoderFactory;
import org.webrtc.EglBase;
import org.webrtc.PeerConnectionFactory;
import org.webrtc.ScreenCapturerAndroid;
import org.webrtc.SurfaceTextureHelper;
import org.webrtc.VideoSource;
import org.webrtc.VideoTrack;

/** Owns projection/GPU resources independently from the Activity's visibility. */
final class AndroidCapture implements AutoCloseable {
    private static final int TARGET_FPS = 30;

    private EglBase egl;
    private SurfaceTextureHelper texture;
    private ScreenCapturerAndroid capturer;
    private VideoSource source;
    private DisplayManager displays;
    private DisplayManager.DisplayListener displayListener;
    private int captureWidth;
    private int captureHeight;
    private volatile boolean closed;

    PeerConnectionFactory factory;
    VideoTrack track;

    AndroidCapture(Context context, Handler owner, Intent permission, Runnable revoked) {
        try {
            PeerConnectionFactory.InitializationOptions initOptions =
                PeerConnectionFactory.InitializationOptions.builder(context).createInitializationOptions();
            PeerConnectionFactory.initialize(initOptions);

            egl = EglBase.create();
            factory = PeerConnectionFactory.builder()
                .setVideoEncoderFactory(new DefaultVideoEncoderFactory(egl.getEglBaseContext(), true, true))
                .setVideoDecoderFactory(new DefaultVideoDecoderFactory(egl.getEglBaseContext()))
                .createPeerConnectionFactory();
            source = factory.createVideoSource(true);
            texture = SurfaceTextureHelper.create("XennexScreen", egl.getEglBaseContext());
            capturer = new ScreenCapturerAndroid(permission, new MediaProjection.Callback() {
                @Override
                public void onStop() {
                    if (!closed) {
                        revoked.run();
                    }
                }

                @Override
                public void onCapturedContentResize(int width, int height) {
                    owner.post(() -> resize(width, height));
                }
            });
            capturer.initialize(texture, context, source.getCapturerObserver());

            int[] rawSize = readScreenBounds(context, null);
            int[] dimensions = CaptureSize.fit(rawSize[0], rawSize[1]);
            captureWidth = dimensions[0];
            captureHeight = dimensions[1];

            source.adaptOutputFormat(captureWidth, captureHeight, TARGET_FPS);
            capturer.startCapture(captureWidth, captureHeight, TARGET_FPS);
            track = factory.createVideoTrack("xennex-screen", source);

            if (Build.VERSION.SDK_INT < 34) {
                registerLegacyRotationListener(context, owner);
            }
        } catch (RuntimeException error) {
            close();
            throw error;
        }
    }

    private void registerLegacyRotationListener(Context context, Handler owner) {
        displays = context.getSystemService(DisplayManager.class);
        if (displays == null) {
            return;
        }
        displayListener = new DisplayManager.DisplayListener() {
            @Override
            public void onDisplayAdded(int id) {}

            @Override
            public void onDisplayRemoved(int id) {}

            @Override
            public void onDisplayChanged(int id) {
                if (id != Display.DEFAULT_DISPLAY || closed) {
                    return;
                }
                Display display = displays.getDisplay(id);
                if (display == null) {
                    return;
                }
                int[] current = readScreenBounds(context, display);
                resize(current[0], current[1]);
            }
        };
        displays.registerDisplayListener(displayListener, owner);
    }

    private static int[] readScreenBounds(Context context, Display explicitDisplay) {
        WindowManager wm = context.getSystemService(WindowManager.class);
        if (Build.VERSION.SDK_INT >= 30 && wm != null) {
            Rect bounds = wm.getMaximumWindowMetrics().getBounds();
            return new int[]{bounds.width(), bounds.height()};
        }
        return readLegacyDisplayMetrics(wm, explicitDisplay);
    }

    @SuppressWarnings("deprecation")
    private static int[] readLegacyDisplayMetrics(WindowManager wm, Display explicitDisplay) {
        Display display = explicitDisplay != null ? explicitDisplay : (wm != null ? wm.getDefaultDisplay() : null);
        if (display == null) {
            return new int[]{720, 1280};
        }
        DisplayMetrics metrics = new DisplayMetrics();
        display.getRealMetrics(metrics);
        return new int[]{metrics.widthPixels, metrics.heightPixels};
    }

    private void resize(int width, int height) {
        if (closed || width < 1 || height < 1) {
            return;
        }
        int[] size = CaptureSize.fit(width, height);
        if (captureWidth == size[0] && captureHeight == size[1]) {
            return;
        }
        captureWidth = size[0];
        captureHeight = size[1];
        source.adaptOutputFormat(captureWidth, captureHeight, TARGET_FPS);
        capturer.changeCaptureFormat(captureWidth, captureHeight, TARGET_FPS);
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        if (displays != null && displayListener != null) {
            release(() -> displays.unregisterDisplayListener(displayListener));
        }
        if (capturer != null) {
            release(capturer::stopCapture);
            release(capturer::dispose);
        }
        if (track != null) {
            release(track::dispose);
        }
        if (source != null) {
            release(source::dispose);
        }
        if (texture != null) {
            release(texture::dispose);
        }
        if (factory != null) {
            release(factory::dispose);
        }
        if (egl != null) {
            release(egl::release);
        }
    }

    private static void release(Runnable action) {
        try {
            action.run();
        } catch (RuntimeException error) {
            Log.w("XennexCapture", "Falha ao liberar um recurso de captura: " + error.getClass().getSimpleName());
        }
    }
}

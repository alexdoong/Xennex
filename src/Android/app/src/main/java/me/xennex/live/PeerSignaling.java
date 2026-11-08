package me.xennex.live;

import android.os.Handler;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.json.JSONException;
import org.json.JSONObject;

/** PeerJS signaling only; screen frames never pass through this server. */
final class PeerSignaling implements AutoCloseable {
    private static final int MAX_MESSAGE_CHARS = 131072;
    private static final long MAX_QUEUE_BYTES = 262144;

    private final Handler handler;
    private final Consumer<JSONObject> receive;
    private final Runnable failed;
    private final OkHttpClient http = new OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .build();
    private WebSocket socket;
    private boolean closed;

    PeerSignaling(Handler handler, Consumer<JSONObject> receive, Runnable failed) {
        this.handler = handler;
        this.receive = receive;
        this.failed = failed;
    }

    void start(String id) {
        String url = "wss://0.peerjs.com/peerjs?key=peerjs&id=" + id + "&token=" + UUID.randomUUID();
        Request request = new Request.Builder().url(url).build();
        socket = http.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onMessage(WebSocket ws, String text) {
                if (text.length() > MAX_MESSAGE_CHARS) {
                    ws.cancel();
                    return;
                }
                handler.post(() -> {
                    if (closed) {
                        return;
                    }
                    try {
                        receive.accept(new JSONObject(text));
                    } catch (JSONException ignored) {
                        // Ignore malformed signaling messages.
                    }
                });
            }

            @Override
            public void onFailure(WebSocket ws, Throwable error, Response response) {
                handler.post(() -> {
                    if (!closed) {
                        failed.run();
                    }
                });
            }

            @Override
            public void onClosed(WebSocket ws, int code, String reason) {
                handler.post(() -> {
                    if (!closed) {
                        failed.run();
                    }
                });
            }
        });
    }

    boolean send(JSONObject value) {
        if (closed || socket == null || socket.queueSize() >= MAX_QUEUE_BYTES) {
            return false;
        }
        return socket.send(value.toString());
    }

    @Override
    public void close() {
        closed = true;
        if (socket != null) {
            socket.cancel();
        }
        http.dispatcher().cancelAll();
        http.connectionPool().evictAll();
        http.dispatcher().executorService().shutdown();
    }
}

package me.xennex.live;

import android.os.Handler;
import android.os.SystemClock;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Consumer;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.webrtc.PeerConnectionFactory;
import org.webrtc.VideoTrack;

/** Publisher in an existing v3 room; never creates/elects a coordinator. */
final class AndroidRoomClient implements AutoCloseable {
    private static final String PROTOCOL = "xennex-room-v3";
    private static final int MAX_ANDROID_VIEWERS = 4;
    private static final int AGGREGATE_BITRATE_BPS = 8000000;

    private final Handler handler;
    private final PeerConnectionFactory factory;
    private final VideoTrack track;
    private final String room;
    private final String name;
    private final Consumer<String> status;
    private final Consumer<String> failure;
    private final String self = UUID.randomUUID().toString();
    private final String publication = UUID.randomUUID().toString();
    private final Map<String, PeerLink> viewers = new HashMap<>();
    private final Set<String> members = new HashSet<>();
    private final PeerSignaling signaling;

    private PeerLink hub;
    private boolean closed;
    private boolean registered;
    private boolean admitted;
    private boolean everJoined;
    private long started;
    private long lastReply;
    private long nextAttempt;
    private long lastPulse;

    private final Runnable timer = new Runnable() {
        @Override
        public void run() {
            if (closed) {
                return;
            }
            tick();
            if (!closed) {
                handler.postDelayed(this, 1000);
            }
        }
    };

    AndroidRoomClient(
        Handler handler,
        PeerConnectionFactory factory,
        VideoTrack track,
        String room,
        String name,
        Consumer<String> status,
        Consumer<String> failure
    ) {
        this.handler = handler;
        this.factory = factory;
        this.track = track;
        this.room = room;
        this.name = name;
        this.status = status;
        this.failure = failure;
        this.signaling = new PeerSignaling(
            handler,
            this::signal,
            () -> fail("A sinalização desconectou. Abra o Xennex e entre novamente.")
        );
    }

    void start() {
        started = SystemClock.elapsedRealtime();
        signaling.start(self);
        handler.post(timer);
    }

    private void signal(JSONObject value) {
        if (closed) {
            return;
        }
        String type = value.optString("type");
        if (type.equals("OPEN")) {
            registered = true;
            connect();
            return;
        }
        if (type.equals("ERROR") || type.equals("ID-TAKEN")) {
            fail("Não foi possível registrar a conexão. Tente novamente.");
            return;
        }
        JSONObject payload = value.optJSONObject("payload");
        if (payload == null) {
            return;
        }
        String peer = value.optString("src");
        String connection = payload.optString("connectionId");
        PeerLink link = (hub != null && hub.peer.equals(peer)) ? hub : viewers.get(peer);
        if (link == null || !link.id.equals(connection)) {
            return;
        }
        link.signal(type, payload);
    }

    private void connect() {
        if (closed || !registered || hub != null) {
            return;
        }
        nextAttempt = SystemClock.elapsedRealtime() + 15000;
        status.accept(everJoined ? "Reconectando à sala…" : "Conectando à sala existente…");
        try {
            JSONArray publications = new JSONArray().put(
                Json.object("id", publication, "title", "Tela do Android", "kind", "screen")
            );
            hub = new PeerLink(
                handler,
                factory,
                signaling,
                RoomAddress.coordinator(room),
                null,
                () -> hub.message(Json.object(
                    "type", "join",
                    "protocol", PROTOCOL,
                    "name", name,
                    "publications", publications
                )),
                this::roomMessage,
                this::reconnect
            );
            hub.offer(Json.object("protocol", PROTOCOL));
        } catch (RuntimeException error) {
            fail("Não foi possível preparar a conexão WebRTC neste aparelho.");
        }
    }

    private void roomMessage(String text) {
        JSONObject message;
        try {
            message = new JSONObject(text);
        } catch (JSONException ignored) {
            return;
        }
        String type = message.optString("type");
        if (type.equals("presence")) {
            presence(message);
            return;
        }
        if (type.equals("pong")) {
            if (admitted) {
                lastReply = SystemClock.elapsedRealtime();
            }
            return;
        }
        if (type.equals("migrate")) {
            reconnect();
            return;
        }
        if (type.equals("error")) {
            fail("A sala recusou a entrada ou publicação. Confira o código e a capacidade da sala.");
            return;
        }
        String viewer = message.optString("viewer");
        if (!admitted || !publication.equals(message.optString("publication"))) {
            return;
        }
        if (!members.contains(viewer) || self.equals(viewer)) {
            return;
        }
        if (type.equals("subscribe")) {
            subscribe(viewer);
        }
        if (type.equals("unsubscribe")) {
            removeViewer(viewer);
        }
    }

    private void presence(JSONObject message) {
        Set<String> next = RoomRoster.parse(message, self, publication);
        if (next == null) {
            return;
        }
        members.clear();
        members.addAll(next);
        admitted = true;
        everJoined = true;
        lastReply = SystemClock.elapsedRealtime();
        for (String viewer : new ArrayList<>(viewers.keySet())) {
            if (!members.contains(viewer)) {
                removeViewer(viewer);
            }
        }
        showStatus();
    }

    private void subscribe(String viewer) {
        if (viewers.containsKey(viewer)) {
            return;
        }
        if (viewers.size() >= MAX_ANDROID_VIEWERS) {
            status.accept("Limite desta prévia: 4 espectadores simultâneos no Android.");
            return;
        }
        try {
            PeerLink link = new PeerLink(
                handler,
                factory,
                signaling,
                viewer,
                track,
                () -> {},
                ignored -> {},
                () -> removeViewer(viewer)
            );
            viewers.put(viewer, link);
            link.offer(Json.object(
                "protocol", PROTOCOL,
                "room", room,
                "publication", publication,
                "videoProfile", Json.object("resolution", "720p", "fps", 30, "uploadMbps", 8)
            ));
            updateBudgets();
            showStatus();
        } catch (RuntimeException error) {
            removeViewer(viewer);
            status.accept("Uma transmissão falhou. O espectador pode parar e assistir novamente.");
        }
    }

    private void removeViewer(String viewer) {
        PeerLink link = viewers.remove(viewer);
        if (link != null) {
            link.close();
        }
        updateBudgets();
        if (admitted) {
            showStatus();
        }
    }

    private void updateBudgets() {
        int bitrate = AGGREGATE_BITRATE_BPS / Math.max(1, viewers.size());
        for (PeerLink link : viewers.values()) {
            link.budget(bitrate);
        }
    }

    private void showStatus() {
        status.accept("Na sala " + room + " · tela disponível · " + viewers.size() + " conexões de vídeo · sem áudio");
    }

    private void reconnect() {
        if (closed) {
            return;
        }
        admitted = false;
        members.clear();
        if (hub != null) {
            hub.close();
            hub = null;
        }
        // Do not keep publishing after losing the authority's membership state.
        for (PeerLink link : viewers.values()) {
            link.close();
        }
        viewers.clear();
        nextAttempt = SystemClock.elapsedRealtime() + 1500;
        status.accept("Reconectando à sala; envio de vídeo pausado…");
    }

    private void tick() {
        long now = SystemClock.elapsedRealtime();
        if (!everJoined && now - started > 30000) {
            fail("Não foi possível entrar. Abra a sala no site primeiro e confira a conexão. Captura encerrada.");
            return;
        }
        if (everJoined && now - lastReply > 60000) {
            fail("A sala não respondeu. Captura encerrada; entre novamente pelo app.");
            return;
        }
        if (admitted && now - lastReply > 20000) {
            reconnect();
        }
        if (!admitted && registered && now >= nextAttempt) {
            if (hub != null) {
                reconnect();
            } else {
                connect();
            }
        }
        if (now - lastPulse < 5000) {
            return;
        }
        lastPulse = now;
        signaling.send(Json.object("type", "HEARTBEAT"));
        if (admitted && hub != null) {
            hub.message(Json.object("type", "ping"));
        }
    }

    private void fail(String message) {
        if (closed) {
            return;
        }
        close();
        failure.accept(message);
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        handler.removeCallbacks(timer);
        if (hub != null) {
            hub.message(Json.object("type", "leave"));
            hub.close();
            hub = null;
        }
        for (PeerLink link : viewers.values()) {
            link.close();
        }
        viewers.clear();
        members.clear();
        signaling.close();
    }
}

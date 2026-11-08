package me.xennex.live;

import android.os.Handler;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import org.json.JSONException;
import org.json.JSONObject;
import org.webrtc.DataChannel;
import org.webrtc.IceCandidate;
import org.webrtc.MediaConstraints;
import org.webrtc.MediaStream;
import org.webrtc.PeerConnection;
import org.webrtc.PeerConnectionFactory;
import org.webrtc.RtpParameters;
import org.webrtc.RtpSender;
import org.webrtc.SdpObserver;
import org.webrtc.SessionDescription;
import org.webrtc.VideoTrack;

/** One outgoing PeerJS-compatible connection. All ownership is on the session Handler. */
final class PeerLink implements AutoCloseable {
    private static final int MAX_BUFFER_BYTES = 65536;
    private static final int MAX_SDP_LENGTH = 100000;
    private static final int MAX_CANDIDATE_LENGTH = 4096;
    private static final int MAX_PENDING_CANDIDATES = 128;

    final String id = UUID.randomUUID().toString();
    final String peer;
    final String type;

    private final Handler handler;
    private final PeerSignaling signaling;
    private final Runnable failed;
    private final List<IceCandidate> pending = new ArrayList<>();
    private final Runnable deadline;

    private PeerConnection pc;
    private DataChannel channel;
    private RtpSender sender;
    private int requestedBitrate = 2000000;
    private boolean closed;
    private boolean remoteReady;

    PeerLink(
        Handler handler,
        PeerConnectionFactory factory,
        PeerSignaling signaling,
        String peer,
        VideoTrack video,
        Runnable opened,
        Consumer<String> receive,
        Runnable failed
    ) {
        this.handler = handler;
        this.signaling = signaling;
        this.peer = peer;
        this.failed = failed;
        this.deadline = () -> {
            if (!closed) {
                failed.run();
            }
        };
        this.type = video == null ? "data" : "media";

        PeerConnection.RTCConfiguration config = new PeerConnection.RTCConfiguration(Arrays.asList(
            PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
            PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer()
        ));
        config.sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN;

        pc = factory.createPeerConnection(config, createPeerObserver());
        if (pc == null) {
            throw new IllegalStateException("PeerConnection unavailable");
        }
        if (video != null) {
            sender = pc.addTrack(video, Collections.singletonList("xennex-screen-stream"));
            return;
        }
        channel = pc.createDataChannel(id, new DataChannel.Init());
        if (channel == null) {
            close();
            throw new IllegalStateException("DataChannel unavailable");
        }
        channel.registerObserver(createChannelObserver(opened, receive));
    }

    private PeerConnection.Observer createPeerObserver() {
        return new PeerConnection.Observer() {
            @Override
            public void onSignalingChange(PeerConnection.SignalingState state) {}

            @Override
            public void onIceConnectionChange(PeerConnection.IceConnectionState state) {
                dispatch(() -> handleIceState(state));
            }

            @Override
            public void onIceConnectionReceivingChange(boolean receiving) {}

            @Override
            public void onIceGatheringChange(PeerConnection.IceGatheringState state) {}

            @Override
            public void onIceCandidate(IceCandidate candidate) {
                dispatch(() -> send("CANDIDATE", Json.object(
                    "candidate", Json.object(
                        "candidate", candidate.sdp,
                        "sdpMid", candidate.sdpMid,
                        "sdpMLineIndex", candidate.sdpMLineIndex
                    )
                )));
            }

            @Override
            public void onIceCandidatesRemoved(IceCandidate[] candidates) {}

            @Override
            public void onAddStream(MediaStream stream) {}

            @Override
            public void onRemoveStream(MediaStream stream) {}

            @Override
            public void onDataChannel(DataChannel incoming) {
                handler.post(() -> {
                    incoming.close();
                    incoming.dispose();
                });
            }

            @Override
            public void onRenegotiationNeeded() {}
        };
    }

    private DataChannel.Observer createChannelObserver(Runnable opened, Consumer<String> receive) {
        return new DataChannel.Observer() {
            @Override
            public void onBufferedAmountChange(long amount) {}

            @Override
            public void onStateChange() {
                dispatch(() -> {
                    if (channel.state() == DataChannel.State.OPEN) {
                        opened.run();
                    }
                    if (channel.state() == DataChannel.State.CLOSED) {
                        failed.run();
                    }
                });
            }

            @Override
            public void onMessage(DataChannel.Buffer buffer) {
                if (buffer.data.remaining() > MAX_BUFFER_BYTES) {
                    return;
                }
                byte[] bytes = new byte[buffer.data.remaining()];
                buffer.data.get(bytes);
                String text = new String(bytes, StandardCharsets.UTF_8);
                dispatch(() -> receive.accept(text));
            }
        };
    }

    private void handleIceState(PeerConnection.IceConnectionState state) {
        if (state == PeerConnection.IceConnectionState.FAILED) {
            failed.run();
            return;
        }
        if (state == PeerConnection.IceConnectionState.CONNECTED || state == PeerConnection.IceConnectionState.COMPLETED) {
            handler.removeCallbacks(deadline);
            return;
        }
        if (state == PeerConnection.IceConnectionState.DISCONNECTED) {
            handler.removeCallbacks(deadline);
            handler.postDelayed(deadline, 15000);
        }
    }

    private void dispatch(Runnable task) {
        handler.post(() -> {
            if (!closed) {
                task.run();
            }
        });
    }

    void offer(JSONObject metadata) {
        handler.postDelayed(deadline, 20000);
        pc.createOffer(new SdpObserver() {
            @Override
            public void onCreateSuccess(SessionDescription sdp) {
                dispatch(() -> pc.setLocalDescription(observer(() -> sendOffer(sdp, metadata)), sdp));
            }

            @Override
            public void onSetSuccess() {}

            @Override
            public void onCreateFailure(String error) {
                dispatch(failed);
            }

            @Override
            public void onSetFailure(String error) {
                dispatch(failed);
            }
        }, new MediaConstraints());
    }

    private void sendOffer(SessionDescription sdp, JSONObject metadata) {
        JSONObject sdpJson = Json.object("type", "offer", "sdp", sdp.description);
        if (type.equals("data")) {
            send("OFFER", Json.object(
                "sdp", sdpJson,
                "metadata", metadata,
                "label", id,
                "serialization", "json",
                "reliable", true
            ));
            return;
        }
        send("OFFER", Json.object("sdp", sdpJson, "metadata", metadata));
    }

    private SdpObserver observer(Runnable success) {
        return new SdpObserver() {
            @Override
            public void onCreateSuccess(SessionDescription sdp) {}

            @Override
            public void onSetSuccess() {
                dispatch(success);
            }

            @Override
            public void onCreateFailure(String error) {
                dispatch(failed);
            }

            @Override
            public void onSetFailure(String error) {
                dispatch(failed);
            }
        };
    }

    void signal(String kind, JSONObject payload) {
        if (closed) {
            return;
        }
        if (kind.equals("ANSWER")) {
            handleAnswer(payload);
            return;
        }
        if (kind.equals("CANDIDATE")) {
            handleCandidate(payload);
        }
    }

    private void handleAnswer(JSONObject payload) {
        JSONObject sdp = payload.optJSONObject("sdp");
        if (remoteReady || sdp == null || !sdp.optString("type").equals("answer")) {
            return;
        }
        String description = sdp.optString("sdp");
        if (description.isEmpty() || description.length() > MAX_SDP_LENGTH) {
            return;
        }
        SessionDescription remoteSdp = new SessionDescription(SessionDescription.Type.ANSWER, description);
        pc.setRemoteDescription(observer(() -> {
            remoteReady = true;
            for (IceCandidate candidate : pending) {
                pc.addIceCandidate(candidate);
            }
            pending.clear();
            budget(requestedBitrate);
        }), remoteSdp);
    }

    private void handleCandidate(JSONObject payload) {
        JSONObject value = payload.optJSONObject("candidate");
        if (value == null) {
            return;
        }
        String sdp = value.optString("candidate");
        int index = value.optInt("sdpMLineIndex", -1);
        if (sdp.length() > MAX_CANDIDATE_LENGTH || index < 0 || index > 32) {
            return;
        }
        IceCandidate candidate = new IceCandidate(value.optString("sdpMid"), index, sdp);
        if (remoteReady) {
            pc.addIceCandidate(candidate);
            return;
        }
        if (pending.size() < MAX_PENDING_CANDIDATES) {
            pending.add(candidate);
        }
    }

    private void send(String kind, JSONObject payload) {
        try {
            payload.put("connectionId", id);
            payload.put("type", type);
        } catch (JSONException error) {
            throw new IllegalArgumentException(error);
        }
        JSONObject envelope = Json.object("type", kind, "dst", peer, "payload", payload);
        if (!signaling.send(envelope)) {
            failed.run();
        }
    }

    boolean message(JSONObject value) {
        if (closed || channel == null || channel.state() != DataChannel.State.OPEN) {
            return false;
        }
        if (channel.bufferedAmount() > MAX_BUFFER_BYTES) {
            return false;
        }
        // PeerJS Json serialization uses UTF-8 binary, not a text SCTP message.
        byte[] utf8 = value.toString().getBytes(StandardCharsets.UTF_8);
        return channel.send(new DataChannel.Buffer(ByteBuffer.wrap(utf8), true));
    }

    void budget(int bitrate) {
        requestedBitrate = bitrate;
        if (closed || sender == null) {
            return;
        }
        RtpParameters params = sender.getParameters();
        for (RtpParameters.Encoding encoding : params.encodings) {
            encoding.maxBitrateBps = bitrate;
            encoding.maxFramerate = 30;
        }
        sender.setParameters(params);
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        handler.removeCallbacks(deadline);
        pending.clear();
        if (channel != null) {
            channel.unregisterObserver();
            channel.close();
            channel.dispose();
        }
        if (pc != null) {
            pc.close();
            pc.dispose();
        }
    }
}

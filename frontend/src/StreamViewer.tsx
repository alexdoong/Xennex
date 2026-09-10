import React, { useState, useEffect, useRef } from 'react';
import { Peer, type MediaConnection } from 'peerjs';
import { 
  Volume2, VolumeX, Maximize, Minimize, Pin, RefreshCw, 
  Tv, Wifi, AlertCircle, Sparkles, Activity, ScreenShare,
  Users, Check, Eye, ChevronRight, ChevronLeft, Radio,
  AppWindow
} from 'lucide-react';
import type { DataConnection } from 'peerjs';

export const ICE_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
  { urls: 'stun:stun2.l.google.com:19302' },
  { urls: 'stun:stun3.l.google.com:19302' },
  { urls: 'stun:stun4.l.google.com:19302' },
  { urls: 'stun:openrelay.metered.ca:80' },
  {
    urls: 'turn:openrelay.metered.ca:80',
    username: 'openrelayproject',
    credential: 'openrelayproject'
  },
  {
    urls: 'turn:openrelay.metered.ca:443',
    username: 'openrelayproject',
    credential: 'openrelayproject'
  },
  {
    urls: 'turn:openrelay.metered.ca:443?transport=tcp',
    username: 'openrelayproject',
    credential: 'openrelayproject'
  }
];

interface StreamItem {
  id: string;
  peerId: string;
  title: string;
  stream: MediaStream;
}

interface RoomParticipant {
  peerId: string;
  name: string;
  isHost?: boolean;
  isStreaming?: boolean;
  streamTitle?: string;
  streamPeerId?: string;
}

const StreamViewer: React.FC = () => {
  const searchParams = new URLSearchParams(window.location.search);
  const roomId = (searchParams.get('room') || '').trim();
  const streamTitle = searchParams.get('title') || 'Transmissão P2P';

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const hudTimeoutRef = useRef<number | null>(null);

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(true);
  const [isHostInLobby, setIsHostInLobby] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showHud, setShowHud] = useState(true);
  
  // Theme mode: 'cinema' (floating HUD) vs 'discord' (room hub with participant sidebar)
  const [themeMode, setThemeMode] = useState<'cinema' | 'discord'>(() => {
    return (localStorage.getItem('xennex_viewer_theme') as 'cinema' | 'discord') || 'discord';
  });
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Video controls
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [fitMode, setFitMode] = useState<'contain' | 'cover'>('contain');
  const [isPinned, setIsPinned] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPiP, setIsPiP] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // Multi-Stream & Participants States
  const [streams, setStreams] = useState<StreamItem[]>([]);
  const [participants, setParticipants] = useState<RoomParticipant[]>([]);
  const [activeStreamId, setActiveStreamId] = useState<string>('');
  const [isSharingOwnScreen, setIsSharingOwnScreen] = useState(false);
  
  const myPeerIdRef = useRef<string>('');
  const ownCoPeerRef = useRef<Peer | null>(null);
  const ownStreamRef = useRef<MediaStream | null>(null);
  const dataConnRef = useRef<DataConnection | null>(null);

  // Live Stats
  const [fps, setFps] = useState<number | null>(null);
  const [bitrateKbps, setBitrateKbps] = useState<number | null>(null);
  const [resolution, setResolution] = useState<string>('');
  const [remoteHasAudio, setRemoteHasAudio] = useState<boolean | null>(null);

  const peerRef = useRef<Peer | null>(null);
  const callRef = useRef<MediaConnection | null>(null);

  const api = window.chrome?.webview?.hostObjects?.api;

  const toggleThemeMode = () => {
    setThemeMode(prev => {
      const next = prev === 'cinema' ? 'discord' : 'cinema';
      localStorage.setItem('xennex_viewer_theme', next);
      return next;
    });
  };

  // Auto-hide HUD on idle in cinema mode
  const triggerHud = () => {
    setShowHud(true);
    if (hudTimeoutRef.current) window.clearTimeout(hudTimeoutRef.current);
    hudTimeoutRef.current = window.setTimeout(() => {
      setShowHud(false);
    }, 3500);
  };

  useEffect(() => {
    const handleMouseMove = () => triggerHud();
    window.addEventListener('mousemove', handleMouseMove);
    triggerHud();
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      if (hudTimeoutRef.current) window.clearTimeout(hudTimeoutRef.current);
    };
  }, []);


  const resetAudioGain = () => {
    try { sourceNodeRef.current?.disconnect(); } catch {}
    try { gainNodeRef.current?.disconnect(); } catch {}
    sourceNodeRef.current = null;
    gainNodeRef.current = null;
  };

  const applyVolumeBoost = (targetVolume: number, muted: boolean, targetStream?: MediaStream | null) => {
    const effectiveVol = muted ? 0 : targetVolume;

    // 1. Native video element handles primary WebRTC audio unmuted (with native hardware decoding)
    if (videoRef.current) {
      videoRef.current.muted = muted || effectiveVol === 0;
      videoRef.current.volume = Math.min(1, Math.max(0, effectiveVol));
    }

    // 2. Extra boost (> 100% up to 200%) via Web Audio GainNode without muting video element
    const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
    const stream = targetStream || (videoRef.current?.srcObject as MediaStream | null);

    if (effectiveVol > 1.0 && AudioCtxClass && stream && stream.getAudioTracks().length > 0) {
      try {
        if (!audioCtxRef.current) {
          audioCtxRef.current = new AudioCtxClass();
        }
        const ctx = audioCtxRef.current;
        if (ctx.state === 'suspended') {
          ctx.resume().catch(() => {});
        }

        if (!gainNodeRef.current || !sourceNodeRef.current) {
          try { sourceNodeRef.current?.disconnect(); } catch {}
          try { gainNodeRef.current?.disconnect(); } catch {}

          const src = ctx.createMediaStreamSource(stream);
          const gain = ctx.createGain();
          src.connect(gain);
          gain.connect(ctx.destination);

          sourceNodeRef.current = src;
          gainNodeRef.current = gain;
        }

        if (gainNodeRef.current) {
          // Additional boost over 100%
          gainNodeRef.current.gain.value = Math.max(0, effectiveVol - 1.0);
        }
      } catch (e) {
        console.warn('[StreamViewer] Audio boost error:', e);
      }
    } else if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = 0;
    }
  };

  const togglePictureInPicture = async () => {
    if (!videoRef.current) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
        setIsPiP(false);
      } else if (document.pictureInPictureEnabled && !videoRef.current.disablePictureInPicture) {
        await videoRef.current.requestPictureInPicture();
        setIsPiP(true);
      } else {
        alert('Picture-in-Picture não suportado neste navegador.');
      }
    } catch (err) {
      console.warn('Erro ao alternar Picture-in-Picture:', err);
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onEnterPiP = () => setIsPiP(true);
    const onLeavePiP = () => setIsPiP(false);
    video.addEventListener('enterpictureinpicture', onEnterPiP);
    video.addEventListener('leavepictureinpicture', onLeavePiP);
    return () => {
      video.removeEventListener('enterpictureinpicture', onEnterPiP);
      video.removeEventListener('leavepictureinpicture', onLeavePiP);
    };
  }, []);

  // Helper to create a valid dummy stream with tracks so WebRTC SDP includes audio and video m-lines
  const createDummyStream = (): MediaStream => {
    const canvas = document.createElement('canvas');
    canvas.width = 2;
    canvas.height = 2;
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, 2, 2);
    }
    const canvasStream = canvas.captureStream ? canvas.captureStream(1) : (canvas as any).mozCaptureStream(1);
    const videoTrack = canvasStream.getVideoTracks()[0];

    let audioTrack: MediaStreamTrack | null = null;
    try {
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtxClass) {
        const audioCtx = new AudioCtxClass();
        const osc = audioCtx.createOscillator();
        const dst = audioCtx.createMediaStreamDestination();
        osc.connect(dst);
        osc.start();
        audioTrack = dst.stream.getAudioTracks()[0];
        audioTrack.enabled = false;
      }
    } catch (e) {
      console.warn('AudioContext dummy track creation:', e);
    }

    const tracks: MediaStreamTrack[] = [];
    if (videoTrack) tracks.push(videoTrack);
    if (audioTrack) tracks.push(audioTrack);
    return new MediaStream(tracks);
  };

  const handleIncomingStream = (remoteStream: MediaStream, sourceId: string = roomId, title: string = streamTitle) => {
    console.log('[Viewer] Stream recebido de', sourceId, 'faixas:', remoteStream.getTracks());
    const aTracks = remoteStream.getAudioTracks();
    setRemoteHasAudio(aTracks.length > 0);

    const mainItem: StreamItem = {
      id: sourceId,
      peerId: sourceId,
      title: title || (sourceId === roomId ? 'Host da Sala' : 'Transmissão'),
      stream: remoteStream
    };

    setStreams(prev => {
      if (prev.some(s => s.peerId === sourceId)) {
        return prev.map(s => s.peerId === sourceId ? mainItem : s);
      }
      return [mainItem, ...prev];
    });

    setActiveStreamId(prev => prev || sourceId);
    setIsHostInLobby(false);

    if (videoRef.current && (!activeStreamId || activeStreamId === sourceId)) {
      resetAudioGain();
      applyVolumeBoost(volume, isMuted, remoteStream);
      videoRef.current.srcObject = remoteStream;
      videoRef.current.play().catch(e => {
        console.warn('Autoplay catch, retrying muted:', e);
        if (videoRef.current) {
          videoRef.current.muted = true;
          setIsMuted(true);
          videoRef.current.play().catch(err => console.error('Play failed:', err));
        }
      });
    }
    setIsConnected(true);
    setIsConnecting(false);
    setErrorMessage(null);
  };

  const switchActiveStream = (targetPeerId: string) => {
    setActiveStreamId(targetPeerId);
    const found = streams.find(s => s.peerId === targetPeerId);
    if (found && found.stream && videoRef.current) {
      videoRef.current.srcObject = found.stream;
      videoRef.current.play().catch(() => {});
      const aTracks = found.stream.getAudioTracks();
      setRemoteHasAudio(aTracks.length > 0);
    }
  };

  const callCoStreamer = (targetPeerId: string, title: string) => {
    if (!peerRef.current || !targetPeerId) return;
    if (targetPeerId === myPeerIdRef.current) return;
    console.log('[Viewer] Conectando ao Co-Streamer:', targetPeerId, title);
    const dummy = createDummyStream();
    const call = peerRef.current.call(targetPeerId, dummy);

    const handleIncomingCoStream = (coStream: MediaStream) => {
      console.log('[Viewer] Recebido stream secundário:', targetPeerId);
      const item: StreamItem = {
        id: targetPeerId,
        peerId: targetPeerId,
        title: title || 'Transmissão Secundária',
        stream: coStream
      };

      setStreams(prev => {
        if (prev.some(s => s.peerId === targetPeerId)) {
          return prev.map(s => s.peerId === targetPeerId ? item : s);
        }
        return [...prev, item];
      });

      if (activeStreamId === targetPeerId || !activeStreamId || isHostInLobby) {
        setActiveStreamId(targetPeerId);
        setIsHostInLobby(false);
      }
    };

    call.on('stream', handleIncomingCoStream);

    if (call.peerConnection) {
      call.peerConnection.ontrack = (ev) => {
        if (ev.streams && ev.streams[0]) {
          handleIncomingCoStream(ev.streams[0]);
        }
      };
    }

    call.on('close', () => {
      setStreams(prev => prev.filter(s => s.peerId !== targetPeerId));
    });
  };

  const handleWatchParticipant = (p: RoomParticipant) => {
    const targetId = p.streamPeerId || p.peerId;
    if (!targetId) return;

    if (targetId === roomId) {
      if (streams.some(s => s.peerId === roomId)) {
        switchActiveStream(roomId);
      } else {
        connectToStream();
      }
      return;
    }

    const existing = streams.find(s => s.peerId === targetId);
    if (existing) {
      switchActiveStream(targetId);
      setIsHostInLobby(false);
    } else {
      callCoStreamer(targetId, p.streamTitle || p.name);
      setActiveStreamId(targetId);
      setIsHostInLobby(false);
    }
  };

  const startViewerScreenShare = async () => {
    if (isSharingOwnScreen) {
      stopViewerScreenShare();
      return;
    }

    try {
      const mediaDevices = navigator.mediaDevices || (navigator as any).webkitMediaDevices;
      if (!mediaDevices || !mediaDevices.getDisplayMedia) {
        alert('Compartilhamento de tela não suportado ou bloqueado.');
        return;
      }

      const myStream = await mediaDevices.getDisplayMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 60 } },
        audio: true,
        systemAudio: 'include'
      } as any);

      ownStreamRef.current = myStream;
      myStream.getVideoTracks()[0].onended = () => {
        stopViewerScreenShare();
      };

      const myCoId = `${roomId}_co_${Math.floor(1000 + Math.random() * 9000)}`;
      const coPeer = new Peer(myCoId, {
        config: {
          iceServers: ICE_SERVERS
        }
      });
      ownCoPeerRef.current = coPeer;

      coPeer.on('open', (id) => {
        console.log('[Viewer Co-Stream] Transmissão própria iniciada na sala:', id);
        setIsSharingOwnScreen(true);

        const myItem: StreamItem = {
          id: myCoId,
          peerId: myCoId,
          title: 'Minha Tela',
          stream: myStream
        };
        setStreams(prev => [...prev.filter(s => s.peerId !== myCoId), myItem]);
        setActiveStreamId(myCoId);
        setIsHostInLobby(false);

        // Atualizar lista de participantes
        setParticipants(prev => {
          const myId = myPeerIdRef.current;
          const found = prev.find(p => p.peerId === myId);
          if (found) {
            return prev.map(p => p.peerId === myId ? { ...p, isStreaming: true, streamPeerId: id, streamTitle: 'Minha Tela' } : p);
          } else {
            return [...prev, {
              peerId: myId,
              name: 'Você (Transmissor)',
              isHost: false,
              isStreaming: true,
              streamPeerId: id,
              streamTitle: 'Minha Tela'
            }];
          }
        });

        if (dataConnRef.current && dataConnRef.current.open) {
          const myName = myPeerIdRef.current ? `Espectador (${myPeerIdRef.current.slice(-4)})` : 'Espectador';
          dataConnRef.current.send({
            type: 'start-sharing',
            peerId: myPeerIdRef.current,
            streamPeerId: id,
            streamTitle: `Tela de ${myName}`
          });
          dataConnRef.current.send({
            type: 'register-co-streamer',
            peerId: id,
            title: `Tela de ${myName}`
          });
        }
      });

      coPeer.on('call', (incomingCall) => {
        incomingCall.answer(myStream);
      });

    } catch (err) {
      console.warn('[Viewer] Cancelado ou erro ao compartilhar tela:', err);
    }
  };

  const stopViewerScreenShare = () => {
    if (ownStreamRef.current) {
      ownStreamRef.current.getTracks().forEach(t => t.stop());
      ownStreamRef.current = null;
    }
    if (ownCoPeerRef.current) {
      try { ownCoPeerRef.current.destroy(); } catch {}
      ownCoPeerRef.current = null;
    }
    setIsSharingOwnScreen(false);
    setStreams(prev => prev.filter(s => s.title !== 'Minha Tela'));

    if (dataConnRef.current && dataConnRef.current.open && myPeerIdRef.current) {
      dataConnRef.current.send({
        type: 'stop-sharing',
        peerId: myPeerIdRef.current
      });
    }
  };

  const connectToStream = () => {
    if (!roomId) {
      setErrorMessage('Nenhum código de sala fornecido.');
      setIsConnecting(false);
      return;
    }

    setIsConnecting(true);
    setErrorMessage(null);

    // Cleanup previous peer/call if any
    if (callRef.current) {
      callRef.current.close();
      callRef.current = null;
    }
    if (peerRef.current) {
      peerRef.current.destroy();
      peerRef.current = null;
    }

    try {
      const peer = new Peer({
        config: {
          iceServers: ICE_SERVERS
        }
      });
      peerRef.current = peer;

      peer.on('open', (myId) => {
        myPeerIdRef.current = myId;
        console.log('[Viewer] Conectado ao servidor P2P com ID:', myId);
        
        // Initiate call with dummy stream containing tracks for valid WebRTC SDP m-lines
        const dummyStream = createDummyStream();
        const call = peer.call(roomId, dummyStream);
        callRef.current = call;

        // Listen for standard PeerJS stream event
        call.on('stream', (remoteStream) => {
          handleIncomingStream(remoteStream, roomId, streamTitle);
        });

        if (call.peerConnection) {
          call.peerConnection.ontrack = (ev) => {
            if (ev.streams && ev.streams[0]) {
              handleIncomingStream(ev.streams[0], roomId, streamTitle);
            } else if (ev.track) {
              const ms = new MediaStream([ev.track]);
              handleIncomingStream(ms, roomId, streamTitle);
            }
          };
        }

        // Conectar ao DataChannel do Host da sala para presença em tempo real
        const dataConn = peer.connect(roomId);
        dataConnRef.current = dataConn;

        const sendJoinNotification = () => {
          const myName = `Espectador (${myId.slice(-4)})`;
          dataConn.send({
            type: 'join-room',
            peerId: myId,
            name: myName,
            isStreaming: isSharingOwnScreen
          });
          dataConn.send({ type: 'get-presence' });
        };

        if (dataConn.open) {
          sendJoinNotification();
        } else {
          dataConn.on('open', sendJoinNotification);
        }

        dataConn.on('data', (data: any) => {
          if (!data) return;

          if (data.type === 'room-presence' && Array.isArray(data.participants)) {
            console.log('[Viewer] Presença da sala recebida:', data.participants);
            setParticipants(data.participants);
            const host = data.participants.find((p: any) => p.isHost);
            if (host && !host.isStreaming) {
              setIsHostInLobby(true);
              setIsConnecting(false);
            } else if (host && host.isStreaming) {
              setIsHostInLobby(false);
            }
          } else if (data.type === 'host-video-started') {
            console.log('[Viewer] Host iniciou transmissão de vídeo na sala!');
            setIsHostInLobby(false);
            const dummy = createDummyStream();
            const newCall = peer.call(roomId, dummy);
            callRef.current = newCall;
            newCall.on('stream', (s) => handleIncomingStream(s, roomId, data.streamTitle));
          } else if (data.type === 'host-video-stopped') {
            console.log('[Viewer] Host pausou vídeo (permanece no lobby).');
            setIsHostInLobby(true);
          } else if (data.type === 'room-closed') {
            console.log('[Viewer] Sala fechada pelo host.');
            setIsConnected(false);
            setErrorMessage('O host encerrou a sala.');
          } else if (data.type === 'co-streamer-added') {
            callCoStreamer(data.peerId, data.title);
          } else if ((data.type === 'streamers-list' || data.type === 'streamer-list') && Array.isArray(data.streamers)) {
            data.streamers.forEach((s: any) => {
              const streamId = s.peerId || s.id;
              const title = s.title || s.label;
              if (streamId && streamId !== roomId && streamId !== myPeerIdRef.current) {
                callCoStreamer(streamId, title);
              }
            });
          }
        });

        call.on('close', () => {
          console.log('[Viewer] Chamada fechada.');
          if (!isHostInLobby) {
            setIsHostInLobby(true);
          }
        });

        call.on('error', (err) => {
          console.warn('[Viewer] Aviso na chamada:', err);
        });
      });

      peer.on('disconnected', () => {
        console.warn('[Viewer] Socket desconectado. Reconectando...');
        try { peer.reconnect(); } catch {}
      });

      peer.on('error', (err) => {
        console.error('[Viewer] Peer error:', err);
        if (err.type === 'peer-unavailable') {
          setErrorMessage(`Sala "${roomId}" não encontrada. Verifique se o host está com a sala aberta.`);
          setIsConnecting(false);
          setIsConnected(false);
        }
      });
    } catch (err: any) {
      console.error('[Viewer] Setup error:', err);
      setIsConnecting(false);
      setErrorMessage('Erro ao inicializar WebRTC: ' + err.message);
    }
  };

  useEffect(() => {
    connectToStream();

    return () => {
      stopViewerScreenShare();
      if (dataConnRef.current) try { dataConnRef.current.close(); } catch {}
      if (callRef.current) callRef.current.close();
      if (peerRef.current) peerRef.current.destroy();
    };
  }, [roomId]);

  // Video stats monitor (FPS, Bitrate, Resolution)
  useEffect(() => {
    if (!isConnected || !callRef.current?.peerConnection) return;

    let lastBytes = 0;
    let lastTime = Date.now();

    const interval = window.setInterval(async () => {
      try {
        const pc = callRef.current?.peerConnection;
        if (!pc) return;

        const stats = await pc.getStats();
        stats.forEach((report) => {
          if (report.type === 'inbound-rtp' && report.kind === 'video') {
            if (report.framesPerSecond !== undefined) {
              setFps(Math.round(report.framesPerSecond));
            }
            if (report.frameWidth && report.frameHeight) {
              setResolution(`${report.frameWidth}x${report.frameHeight}`);
            }
            if (report.bytesReceived !== undefined) {
              const now = Date.now();
              const diffTime = (now - lastTime) / 1000;
              if (diffTime > 0 && lastBytes > 0) {
                const diffBytes = report.bytesReceived - lastBytes;
                const kbps = Math.round((diffBytes * 8) / (diffTime * 1000));
                setBitrateKbps(kbps);
              }
              lastBytes = report.bytesReceived;
              lastTime = now;
            }
          }
        });
      } catch {}
    }, 1500);

    return () => window.clearInterval(interval);
  }, [isConnected]);

  // Controls Handlers
    const toggleMute = () => {
    const next = !isMuted;
    setIsMuted(next);
    applyVolumeBoost(volume, next);
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (val === 0) {
      setIsMuted(true);
      applyVolumeBoost(0, true);
    } else {
      if (isMuted) setIsMuted(false);
      applyVolumeBoost(val, false);
    }
  };

  const toggleFitMode = () => {
    setFitMode(prev => prev === 'contain' ? 'cover' : 'contain');
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const toggleAlwaysOnTop = async () => {
    const next = !isPinned;
    setIsPinned(next);
    if (api && api.SetViewerAlwaysOnTop) {
      await api.SetViewerAlwaysOnTop(roomId, next);
    }
  };

  // Render Discord Room Hub Layout
  if (themeMode === 'discord') {
    return (
      <div ref={containerRef} className="stream-hub-layout">
        {/* Main Video Viewport */}
        <div className="stream-hub-main">
          {/* Top Header */}
          <div className="stream-hub-header">
            <div className="hub-room-info">
              <div className="live-pill">
                <span className={isHostInLobby ? "live-dot lobby-dot" : "live-dot"}></span>
                {isHostInLobby ? 'LOBBY' : 'LIVE'}
              </div>
              <span className="hud-title">{streamTitle}</span>
              <span className="hub-room-badge">{roomId}</span>

              {/* Theme switcher toggle */}
              <button 
                className="theme-switch-btn" 
                onClick={toggleThemeMode} 
                title="Alternar para Modo Cinema Imersivo"
              >
                <Tv size={14} />
                <span>Modo Cinema</span>
              </button>

              {/* Multi-Stream Switcher Tabs */}
              {streams.length > 1 && (
                <div className="stream-switcher-bar" style={{ maxWidth: '300px' }}>
                  <span className="switcher-label">Telas ({streams.length}):</span>
                  {streams.map((s) => (
                    <button 
                      key={s.peerId}
                      className={`stream-tab-btn ${activeStreamId === s.peerId ? 'active' : ''}`}
                      onClick={() => switchActiveStream(s.peerId)}
                    >
                      <ScreenShare size={12} />
                      <span>{s.title}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="hud-right">
              {remoteHasAudio !== null && (
                <span 
                  className="hud-stat-badge" 
                  title={remoteHasAudio ? 'Áudio ativo' : 'Sem áudio transmitido'}
                  style={remoteHasAudio ? { color: '#34D399', borderColor: 'rgba(52, 211, 153, 0.3)' } : { color: '#94A3B8' }}
                >
                  {remoteHasAudio ? <Volume2 size={12} /> : <VolumeX size={12} />}
                  {remoteHasAudio ? 'ÁUDIO' : 'SEM SOM'}
                </span>
              )}
              {resolution && (
                <span className="hud-stat-badge">
                  <Sparkles size={12} /> {resolution}
                </span>
              )}
              {fps !== null && (
                <span className="hud-stat-badge">
                  {fps} FPS
                </span>
              )}
              {bitrateKbps !== null && (
                <span className="hud-stat-badge">
                  <Activity size={12} /> {bitrateKbps} kbps
                </span>
              )}

              {/* Controls */}
              <button className="hud-btn" onClick={toggleMute} title={isMuted ? 'Desmutar' : 'Mutar'}>
                {isMuted || volume === 0 ? <VolumeX size={16} color="#EF4444" /> : <Volume2 size={16} />}
              </button>
              <input 
                type="range" 
                min="0" 
                max="2" 
                step="0.05"
                value={isMuted ? 0 : volume}
                onChange={handleVolumeChange}
                className="hud-volume-slider"
                style={{ width: '65px' }}
                title={'Volume: ' + Math.round((isMuted ? 0 : volume) * 100) + '%'}
              />
              <span style={{ fontSize: '11px', fontFamily: 'monospace', minWidth: '34px', color: volume > 1 ? '#A855F7' : '#38BDF8', fontWeight: volume > 1 ? 700 : 500 }}>
                {Math.round((isMuted ? 0 : volume) * 100)}%
              </span>
              <button className="hud-btn" onClick={toggleFitMode} title={fitMode === 'contain' ? 'Ajustar Tela' : 'Manter Proporção'}>
                <span style={{ fontSize: '11px', fontWeight: 600 }}>{fitMode === 'contain' ? '16:9' : 'FILL'}</span>
              </button>
              <button className={'hud-btn ' + (isPiP ? 'active' : '')} onClick={togglePictureInPicture} title={isPiP ? 'Fechar Janela Flutuante (PiP)' : 'Janela Flutuante (Picture-in-Picture)'}>
                <AppWindow size={16} />
              </button>
              <button className={'hud-btn ' + (isPinned ? 'active' : '')} onClick={toggleAlwaysOnTop} title="Fixar no Topo">
                <Pin size={16} />
              </button>
              <button className="hud-btn" onClick={toggleFullscreen} title="Tela Cheia">
                {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
              </button>
              <button 
                className="hud-btn" 
                onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
                title={isSidebarOpen ? "Recolher Participantes" : "Expandir Participantes"}
              >
                {isSidebarOpen ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
              </button>
            </div>
          </div>

          {/* Video Container */}
          <div className="stream-hub-video-area">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className={`stream-viewer-video ${fitMode}`}
              style={{ display: isHostInLobby ? 'none' : 'block' }}
            />

            {/* Lobby Waiting Overlay */}
            {isHostInLobby && (
              <div className="lobby-waiting-view">
                <div className="lobby-icon-bubble">
                  <Radio size={32} color="#F59E0B" />
                  <span className="pulse-dot lobby-dot"></span>
                </div>
                <h3>Sala Aberta: <span className="room-code-tag">{roomId}</span></h3>
                <p>O Host está conectado na sala preparando a transmissão.<br />O vídeo e o som começarão automaticamente assim que ele iniciar!</p>
                <div className="lobby-stats-badge">
                  <Users size={14} />
                  <span>{participants.length} participante(s) aguardando na sala</span>
                </div>
              </div>
            )}

            {/* Connecting Overlay */}
            {isConnecting && (
              <div className="stream-viewer-overlay-loading">
                <div className="loading-radar-ring"></div>
                <Tv size={38} className="loading-icon-pulse" />
                <h3>Conectando à Transmissão P2P</h3>
                <p>Buscando host da sala <span className="room-code-tag">{roomId}</span>...</p>
                <div className="connecting-badge">
                  <Wifi size={14} className="spin-icon" /> Estabelecendo Handshake ICE (STUN/TURN)
                </div>
              </div>
            )}

            {/* Error Overlay */}
            {errorMessage && !isConnecting && (
              <div className="stream-viewer-overlay-error">
                <div className="error-icon-box">
                  <AlertCircle size={42} color="#EF4444" />
                </div>
                <h3>Transmissão Indisponível</h3>
                <p>{errorMessage}</p>
                <div className="error-actions">
                  <button className="btn-retry" onClick={connectToStream}>
                    <RefreshCw size={15} /> Tentar Reconectar
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Discord Sidebar: Participants & Streams List */}
        <div className={`stream-hub-sidebar ${isSidebarOpen ? '' : 'collapsed'}`}>
          <div className="hub-sidebar-top">
            <div className="hub-sidebar-title">
              <Users size={16} />
              <span>Participantes ({participants.length || 1})</span>
            </div>
          </div>

          <div className="hub-participants-scroll">
            {participants.length === 0 ? (
              <div className="participant-card is-streaming">
                <div className="participant-header-row">
                  <div className="participant-avatar-group">
                    <div className="participant-avatar">
                      H
                      <div className="online-dot"></div>
                    </div>
                    <div className="participant-name-col">
                      <span className="participant-name">{streamTitle}</span>
                      <span className="participant-role">Host da Sala</span>
                    </div>
                  </div>
                  <div className="live-indicator">
                    <span className="pulse-dot"></span> AO VIVO
                  </div>
                </div>
                <button 
                  className={`btn-watch-stream ${(!activeStreamId || activeStreamId === roomId) ? 'active-watching' : ''}`}
                  onClick={() => switchActiveStream(roomId)}
                >
                  {(!activeStreamId || activeStreamId === roomId) ? (
                    <><Check size={14} /> Assistindo Tela</>
                  ) : (
                    <><Eye size={14} /> Assistir Tela</>
                  )}
                </button>
              </div>
            ) : (
              participants.map((p) => {
                const targetStreamId = p.streamPeerId || p.peerId;
                const isStreaming = p.isStreaming || (p.isHost && isConnected && !isHostInLobby);
                const isCurrent = activeStreamId === targetStreamId || (!activeStreamId && p.isHost);

                return (
                  <div key={p.peerId} className={`participant-card ${isStreaming ? 'is-streaming' : ''}`}>
                    <div className="participant-header-row">
                      <div className="participant-avatar-group">
                        <div className="participant-avatar">
                          {p.name.charAt(0).toUpperCase()}
                          <div className="online-dot"></div>
                        </div>
                        <div className="participant-name-col">
                          <span className="participant-name">{p.name}</span>
                          <span className="participant-role">
                            {p.isHost ? 'Host da Sala' : (p.peerId === myPeerIdRef.current ? 'Você' : 'Membro')}
                          </span>
                        </div>
                      </div>

                      {isStreaming && (
                        <div className="live-indicator">
                          <span className="pulse-dot"></span> AO VIVO
                        </div>
                      )}
                    </div>

                    {isStreaming && (
                      <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <button 
                          className={'btn-watch-stream ' + (isCurrent ? 'active-watching' : '')}
                          onClick={() => handleWatchParticipant(p)}
                        >
                          {isCurrent ? (
                            <><Check size={14} /> Assistindo Tela</>
                          ) : (
                            <><Eye size={14} /> Assistir Tela</>
                          )}
                        </button>
                        {isCurrent && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 8px', background: 'rgba(0,0,0,0.3)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                            <Volume2 size={12} color={volume > 1 ? "#A855F7" : "#94A3B8"} />
                            <input 
                              type="range" 
                              min="0" 
                              max="2" 
                              step="0.05" 
                              value={isMuted ? 0 : volume} 
                              onChange={handleVolumeChange} 
                              style={{ flex: 1, accentColor: volume > 1 ? '#A855F7' : '#38BDF8', cursor: 'pointer', height: '4px' }} 
                              title={'Volume do Participante: ' + Math.round((isMuted ? 0 : volume) * 100) + '%'}
                            />
                            <span style={{ fontSize: '10px', fontFamily: 'monospace', minWidth: '32px', color: volume > 1 ? '#A855F7' : '#38BDF8', fontWeight: volume > 1 ? 700 : 500 }}>
                              {Math.round((isMuted ? 0 : volume) * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          <div className="hub-sidebar-footer">
            <button 
              className={`btn-hub-share ${isSharingOwnScreen ? 'is-active' : ''}`}
              onClick={startViewerScreenShare}
            >
              <ScreenShare size={16} />
              <span>{isSharingOwnScreen ? 'Parar Compartilhamento' : 'Transmitir Minha Tela'}</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Render Cinema Mode (Floating HUD)
  return (
    <div 
      ref={containerRef}
      className="stream-viewer-container"
      onMouseMove={triggerHud}
    >
      {/* Video Viewport */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        className={`stream-viewer-video ${fitMode}`}
        style={{ display: isHostInLobby ? 'none' : 'block' }}
      />

      {/* Lobby Waiting Overlay */}
      {isHostInLobby && (
        <div className="lobby-waiting-view">
          <div className="lobby-icon-bubble">
            <Radio size={32} color="#F59E0B" />
            <span className="pulse-dot lobby-dot"></span>
          </div>
          <h3>Sala Aberta: <span className="room-code-tag">{roomId}</span></h3>
          <p>O Host está no lobby organizando a transmissão.<br />O vídeo e o som começarão automaticamente assim que ele iniciar!</p>
          <div className="lobby-stats-badge">
            <Users size={14} />
            <span>{participants.length} participante(s) na sala</span>
          </div>
        </div>
      )}

      {/* Connecting & Loading Overlay */}
      {isConnecting && (
        <div className="stream-viewer-overlay-loading">
          <div className="loading-radar-ring"></div>
          <Tv size={38} className="loading-icon-pulse" />
          <h3>Conectando à Transmissão P2P</h3>
          <p>Buscando host da sala <span className="room-code-tag">{roomId}</span>...</p>
          <div className="connecting-badge">
            <Wifi size={14} className="spin-icon" /> Aguardando Handshake WebRTC (STUN/TURN)
          </div>
        </div>
      )}

      {/* Error / Disconnected Overlay */}
      {errorMessage && !isConnecting && (
        <div className="stream-viewer-overlay-error">
          <div className="error-icon-box">
            <AlertCircle size={42} color="#EF4444" />
          </div>
          <h3>Transmissão Indisponível</h3>
          <p>{errorMessage}</p>
          <div className="error-actions">
            <button className="btn-retry" onClick={connectToStream}>
              <RefreshCw size={15} /> Tentar Reconectar
            </button>
          </div>
        </div>
      )}

      {/* Floating HUD Controls (Fade on Idle) */}
      <div className={`stream-viewer-hud ${showHud ? 'visible' : 'hidden'}`}>
        {/* Top Header Bar */}
        <div className="hud-top-bar">
          <div className="hud-left">
            <div className="live-pill">
              <span className={isHostInLobby ? "live-dot lobby-dot" : "live-dot"}></span>
              {isHostInLobby ? 'LOBBY' : 'LIVE'}
            </div>
            <span className="hud-title">{streamTitle}</span>
            <span className="hud-room-badge">{roomId}</span>

            {/* Theme switcher toggle */}
            <button 
              className="theme-switch-btn" 
              onClick={toggleThemeMode} 
              title="Alternar para Modo Sala Discord"
            >
              <Users size={14} />
              <span>Modo Sala ({participants.length || 1})</span>
            </button>

            {/* Multi-Stream Switcher Tabs */}
            {streams.length > 1 && (
              <div className="stream-switcher-bar">
                <span className="switcher-label">Telas ({streams.length}):</span>
                {streams.map((s) => (
                  <button 
                    key={s.peerId}
                    className={`stream-tab-btn ${activeStreamId === s.peerId ? 'active' : ''}`}
                    onClick={() => switchActiveStream(s.peerId)}
                  >
                    <ScreenShare size={12} />
                    <span>{s.title}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="hud-right">
            <button 
              className={`hud-btn highlight-btn ${isSharingOwnScreen ? 'active' : ''}`}
              onClick={startViewerScreenShare}
              title={isSharingOwnScreen ? "Parar de Compartilhar Minha Tela" : "Compartilhar Minha Tela Nesta Sala"}
            >
              <ScreenShare size={14} />
              <span>{isSharingOwnScreen ? "Parar Tela" : "Compartilhar Tela"}</span>
            </button>

            {remoteHasAudio !== null && (
              <span 
                className="hud-stat-badge" 
                title={remoteHasAudio ? 'Áudio do sistema ativo' : 'Sem som compartilhado'}
                style={remoteHasAudio ? { color: '#34D399', borderColor: 'rgba(52, 211, 153, 0.3)' } : { color: '#94A3B8' }}
              >
                {remoteHasAudio ? <Volume2 size={12} /> : <VolumeX size={12} />}
                {remoteHasAudio ? 'ÁUDIO' : 'SEM SOM'}
              </span>
            )}
            {resolution && (
              <span className="hud-stat-badge">
                <Sparkles size={12} /> {resolution}
              </span>
            )}
            {fps !== null && (
              <span 
                className="hud-stat-badge"
                title={fps <= 1 ? "Tela estática (repouso)" : `${fps} FPS em tempo real`}
              >
                {fps} FPS {fps <= 1 && <span style={{ opacity: 0.6, fontSize: '10px' }}>(Repouso)</span>}
              </span>
            )}
            {bitrateKbps !== null && (
              <span className="hud-stat-badge">
                <Activity size={12} /> {bitrateKbps} kbps
              </span>
            )}
            <button 
              className={`hud-btn ${isPinned ? 'active' : ''}`} 
              onClick={toggleAlwaysOnTop}
              title="Fixar no Topo (Always on Top)"
            >
              <Pin size={16} />
            </button>
          </div>
        </div>

        {/* Bottom Control Bar */}
        <div className="hud-bottom-bar">
          <div className="hud-controls-left">
            <button 
              className="hud-btn" 
              onClick={toggleMute}
              title={isMuted ? 'Desmutar' : 'Mutar'}
            >
              {isMuted || volume === 0 ? <VolumeX size={18} color="#EF4444" /> : <Volume2 size={18} />}
            </button>
            <input 
              type="range" 
              min="0" 
              max="2" 
              step="0.05"
              value={isMuted ? 0 : volume}
              onChange={handleVolumeChange}
              className="hud-volume-slider"
              title={'Volume: ' + Math.round((isMuted ? 0 : volume) * 100) + '%'}
            />
            <span style={{ fontSize: '11px', fontFamily: 'monospace', minWidth: '36px', color: volume > 1 ? '#A855F7' : '#38BDF8', fontWeight: volume > 1 ? 700 : 500 }}>
              {Math.round((isMuted ? 0 : volume) * 100)}%
            </span>
          </div>

          <div className="hud-controls-right">
            <button 
              className="hud-btn" 
              onClick={toggleFitMode}
              title={fitMode === 'contain' ? 'Ajustar (Preencher Janela)' : 'Ajustar (Manter Proporção)'}
            >
              <span style={{ fontSize: '11px', fontWeight: 600 }}>
                {fitMode === 'contain' ? '16:9' : 'FILL'}
              </span>
            </button>

            <button 
              className={'hud-btn ' + (isPiP ? 'active' : '')}
              onClick={togglePictureInPicture}
              title={isPiP ? 'Fechar Janela Flutuante (PiP)' : 'Janela Flutuante (Picture-in-Picture)'}
            >
              <AppWindow size={16} />
            </button>

            <button 
              className="hud-btn" 
              onClick={connectToStream}
              title="Recarregar Transmissão"
            >
              <RefreshCw size={16} />
            </button>

            <button 
              className="hud-btn" 
              onClick={toggleFullscreen}
              title={isFullscreen ? 'Sair da Tela Cheia' : 'Tela Cheia'}
            >
              {isFullscreen ? <Minimize size={18} /> : <Maximize size={18} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StreamViewer;

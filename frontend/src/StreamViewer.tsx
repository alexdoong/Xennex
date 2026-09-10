import React, { useState, useEffect, useRef } from 'react';
import { Peer, type MediaConnection } from 'peerjs';
import { 
  Volume2, VolumeX, Maximize, Minimize, Pin, RefreshCw, 
  Tv, Wifi, AlertCircle, Sparkles, Activity, ScreenShare
} from 'lucide-react';
import type { DataConnection } from 'peerjs';

interface StreamItem {
  id: string;
  peerId: string;
  title: string;
  stream: MediaStream;
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showHud, setShowHud] = useState(true);
  
  // Video controls
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [fitMode, setFitMode] = useState<'contain' | 'cover'>('contain');
  const [isPinned, setIsPinned] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Multi-Stream States
  const [streams, setStreams] = useState<StreamItem[]>([]);
  const [activeStreamId, setActiveStreamId] = useState<string>('');
  const [isSharingOwnScreen, setIsSharingOwnScreen] = useState(false);
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

  // Auto-hide HUD on idle
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

  // WebRTC Connection Logic
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

  const handleIncomingStream = (remoteStream: MediaStream) => {
    console.log('[Viewer] Stream principal recebido! Faixas:', remoteStream.getTracks());
    const aTracks = remoteStream.getAudioTracks();
    setRemoteHasAudio(aTracks.length > 0);

    const mainItem: StreamItem = {
      id: roomId,
      peerId: roomId,
      title: streamTitle || 'Transmissão Principal',
      stream: remoteStream
    };

    setStreams(prev => {
      if (prev.some(s => s.peerId === roomId)) {
        return prev.map(s => s.peerId === roomId ? mainItem : s);
      }
      return [mainItem, ...prev];
    });

    setActiveStreamId(prev => prev || roomId);

    if (videoRef.current && (!activeStreamId || activeStreamId === roomId)) {
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
    if (!peerRef.current) return;
    console.log('[Viewer] Conectando ao Co-Streamer:', targetPeerId, title);
    const dummy = createDummyStream();
    const call = peerRef.current.call(targetPeerId, dummy);

    call.on('stream', (coStream) => {
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
    });

    call.on('close', () => {
      setStreams(prev => prev.filter(s => s.peerId !== targetPeerId));
    });
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
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' }
          ]
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

        if (dataConnRef.current && dataConnRef.current.open) {
          dataConnRef.current.send({
            type: 'register-co-streamer',
            peerId: id,
            title: 'Tela de Espectador'
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
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' }
          ]
        }
      });
      peerRef.current = peer;

      peer.on('open', (myId) => {
        console.log('[Viewer] Conectado ao servidor de sinalização P2P com ID:', myId);
        
        // Initiate call with dummy stream containing tracks for valid WebRTC SDP m-lines
        const dummyStream = createDummyStream();
        const call = peer.call(roomId, dummyStream);
        callRef.current = call;

        // Listen for standard PeerJS stream event
        call.on('stream', (remoteStream) => {
          handleIncomingStream(remoteStream);
        });

        // Also hook native WebRTC ontrack for maximum browser compatibility
        if (call.peerConnection) {
          call.peerConnection.ontrack = (ev) => {
            if (ev.streams && ev.streams[0]) {
              handleIncomingStream(ev.streams[0]);
            } else if (ev.track) {
              const ms = new MediaStream([ev.track]);
              handleIncomingStream(ms);
            }
          };
        }

        // Conectar ao DataChannel do Host da sala para receber anúncios de outros streamers
        const dataConn = peer.connect(roomId);
        dataConnRef.current = dataConn;

        dataConn.on('data', (data: any) => {
          if (!data) return;
          if (data.type === 'co-streamer-added') {
            console.log('[Viewer] Novo co-streamer na sala anunciado:', data);
            callCoStreamer(data.peerId, data.title);
          } else if (data.type === 'streamers-list' && Array.isArray(data.streamers)) {
            console.log('[Viewer] Lista de streamers existentes recebida:', data.streamers);
            data.streamers.forEach((s: any) => callCoStreamer(s.peerId, s.title));
          }
        });

        call.on('stream', (remoteStream) => {
          console.log('[Viewer] Stream de vídeo/áudio recebido!');
          if (videoRef.current) {
            videoRef.current.srcObject = remoteStream;
            videoRef.current.play().catch(e => console.warn('Autoplay prevent:', e));
          }
          setIsConnected(true);
          setIsConnecting(false);
          setErrorMessage(null);
        });

        call.on('close', () => {
          console.log('[Viewer] Chamada fechada pelo host.');
          setIsConnected(false);
          setErrorMessage('O host finalizou o compartilhamento de tela.');
        });

        call.on('error', (err) => {
          console.error('[Viewer] Erro na chamada:', err);
          setIsConnected(false);
          setErrorMessage('Erro na transmissão: ' + (err?.message || 'Falha de conexão'));
        });
      });

      peer.on('error', (err) => {
        console.error('[Viewer] Peer error:', err);
        setIsConnecting(false);
        setIsConnected(false);
        if (err.type === 'peer-unavailable') {
          setErrorMessage(`Sala "${roomId}" não encontrada. Verifique se o host está transmitindo.`);
        } else {
          setErrorMessage(`Falha na conexão P2P: ${err.type || err.message}`);
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
      } catch {
        // Stats not available or unsupported
      }
    }, 1500);

    return () => window.clearInterval(interval);
  }, [isConnected]);

  // Controls Handlers
  const toggleMute = () => {
    if (!videoRef.current) return;
    const next = !isMuted;
    setIsMuted(next);
    videoRef.current.muted = next;
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      if (val === 0) {
        setIsMuted(true);
        videoRef.current.muted = true;
      } else if (isMuted) {
        setIsMuted(false);
        videoRef.current.muted = false;
      }
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
      />

      {/* Connecting & Loading Overlay */}
      {isConnecting && (
        <div className="stream-viewer-overlay-loading">
          <div className="loading-radar-ring"></div>
          <Tv size={38} className="loading-icon-pulse" />
          <h3>Conectando à Transmissão P2P</h3>
          <p>Buscando host da sala <span className="room-code-tag">{roomId}</span>...</p>
          <div className="connecting-badge">
            <Wifi size={14} className="spin-icon" /> Aguardando Handshake WebRTC
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
              <span className="live-dot"></span>
              LIVE
            </div>
            <span className="hud-title">{streamTitle}</span>
            <span className="hud-room-badge">{roomId}</span>

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
                title={remoteHasAudio ? 'Áudio do sistema ativo' : 'O host não compartilhou áudio (Janela selecionada ou sem som)'}
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
                title={fps <= 1 ? "Tela estática (economia de banda inteligente do Chromium). Sobe para 60 FPS ao se movimentar." : `${fps} FPS em tempo real`}
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
              max="1" 
              step="0.05"
              value={isMuted ? 0 : volume}
              onChange={handleVolumeChange}
              className="hud-volume-slider"
              title={`Volume: ${Math.round((isMuted ? 0 : volume) * 100)}%`}
            />
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

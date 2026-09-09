import React, { useState, useEffect, useRef } from 'react';
import { Peer, type MediaConnection } from 'peerjs';
import { 
  Tv, Radio, Play, Square, ExternalLink, Copy, Check, Users, 
  Clock, Sparkles, Trash2, Sliders, Zap
} from 'lucide-react';

interface ResolutionOption {
  id: string;
  label: string;
  desc: string;
  width?: number;
  height?: number;
}

interface FpsOption {
  fps: number;
  label: string;
  desc: string;
}

const RESOLUTIONS: ResolutionOption[] = [
  { id: 'source', label: 'Fonte Original', desc: 'Resolução nativa sem redimensionar' },
  { id: '1440p',  label: '1440p (2K)',      desc: '2560 x 1440 (Ultra Nitidez)', width: 2560, height: 1440 },
  { id: '1080p',  label: '1080p (Full HD)', desc: '1920 x 1080 (Padrão)', width: 1920, height: 1080 },
  { id: '720p',   label: '720p (HD)',       desc: '1280 x 720 (Leve & Estável)', width: 1280, height: 720 },
  { id: '480p',   label: '480p (Econômico)', desc: '854 x 480 (Menor consumo de rede)', width: 854, height: 480 }
];

const FPS_OPTIONS: FpsOption[] = [
  { fps: 60, label: '60 FPS', desc: 'Fluidez máxima para jogos' },
  { fps: 30, label: '30 FPS', desc: 'Equilíbrio e economia de banda' },
  { fps: 15, label: '15 FPS', desc: 'Ideal para textos e slides' },
  { fps: 0,  label: 'Ilimitado', desc: 'Taxa máxima do monitor' }
];

const StreamTab: React.FC = () => {
  // Host state - Loaded from persistent localStorage
  const [selectedResolution, setSelectedResolution] = useState<string>(() => {
    return localStorage.getItem('xennex_stream_resolution') || '1080p';
  });

  const [selectedFps, setSelectedFps] = useState<number>(() => {
    const saved = localStorage.getItem('xennex_stream_fps');
    return saved !== null ? parseInt(saved, 10) : 60;
  });

  const [streamTitle, setStreamTitle] = useState<string>(() => {
    return localStorage.getItem('xennex_stream_title') || 'Gameplay / Desktop';
  });

  const [captureAudio, setCaptureAudio] = useState<boolean>(() => {
    const saved = localStorage.getItem('xennex_stream_audio');
    return saved !== null ? saved === 'true' : true;
  });

  const [isStreaming, setIsStreaming] = useState(false);
  const [myRoomId, setMyRoomId] = useState('');
  const [copiedCode, setCopiedCode] = useState(false);
  const [viewerCount, setViewerCount] = useState(0);
  const [uptimeSeconds, setUptimeSeconds] = useState(0);
  const [cloudflareUrl, setCloudflareUrl] = useState<string>(() => {
    return localStorage.getItem('xennex_cloudflare_url') || '';
  });
  const [copiedWebLink, setCopiedWebLink] = useState(false);

  // Viewer state
  const [joinRoomId, setJoinRoomId] = useState('');
  const [joinTitle, setJoinTitle] = useState('');
  const [recentRooms, setRecentRooms] = useState<string[]>([]);

  // Refs
  const localStreamRef = useRef<MediaStream | null>(null);
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const peerRef = useRef<Peer | null>(null);
  const activeCallsRef = useRef<MediaConnection[]>([]);
  const uptimeTimerRef = useRef<number | null>(null);

  const api = window.chrome?.webview?.hostObjects?.api;

  // Persistence handlers
  const handleResolutionChange = (resId: string) => {
    setSelectedResolution(resId);
    localStorage.setItem('xennex_stream_resolution', resId);
  };

  const handleFpsChange = (fpsVal: number) => {
    setSelectedFps(fpsVal);
    localStorage.setItem('xennex_stream_fps', fpsVal.toString());
  };

  const handleTitleChange = (val: string) => {
    setStreamTitle(val);
    localStorage.setItem('xennex_stream_title', val);
  };

  const handleAudioChange = (val: boolean) => {
    setCaptureAudio(val);
    localStorage.setItem('xennex_stream_audio', val.toString());
  };

  // Load recent rooms from storage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('xennex_recent_streams');
      if (saved) {
        setRecentRooms(JSON.parse(saved));
      }
    } catch {}
  }, []);

  const saveRecentRoom = (code: string) => {
    const clean = code.trim().toUpperCase();
    if (!clean) return;
    const updated = [clean, ...recentRooms.filter(r => r !== clean)].slice(0, 5);
    setRecentRooms(updated);
    try {
      localStorage.setItem('xennex_recent_streams', JSON.stringify(updated));
    } catch {}
  };

  const removeRecentRoom = (code: string) => {
    const updated = recentRooms.filter(r => r !== code);
    setRecentRooms(updated);
    try {
      localStorage.setItem('xennex_recent_streams', JSON.stringify(updated));
    } catch {}
  };

  // Uptime ticker
  useEffect(() => {
    if (isStreaming) {
      setUptimeSeconds(0);
      uptimeTimerRef.current = window.setInterval(() => {
        setUptimeSeconds(s => s + 1);
      }, 1000);
    } else {
      if (uptimeTimerRef.current) window.clearInterval(uptimeTimerRef.current);
      setUptimeSeconds(0);
    }
    return () => {
      if (uptimeTimerRef.current) window.clearInterval(uptimeTimerRef.current);
    };
  }, [isStreaming]);

  // Start Screen Broadcast
  const startStream = async () => {
    try {
      // Robust verification of mediaDevices in secure context
      const mediaDevices = navigator.mediaDevices || (navigator as any).webkitMediaDevices;
      if (!mediaDevices || !mediaDevices.getDisplayMedia) {
        alert('O navegador precisa estar em contexto seguro (HTTPS) para capturar a tela.\nCertifique-se de iniciar o aplicativo atualizado.');
        return;
      }

      const res = RESOLUTIONS.find(r => r.id === selectedResolution) || RESOLUTIONS[2];

      const videoConstraints: MediaTrackConstraints = {};
      if (res.width && res.height) {
        videoConstraints.width = { ideal: res.width };
        videoConstraints.height = { ideal: res.height };
      }
      if (selectedFps > 0) {
        videoConstraints.frameRate = { ideal: selectedFps, max: selectedFps };
      }

      const stream = await mediaDevices.getDisplayMedia({
        video: videoConstraints,
        audio: captureAudio ? {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        } : false
      });

      localStreamRef.current = stream;

      // Handle user ending capture from browser/system toolbar
      stream.getVideoTracks()[0].onended = () => {
        stopStream();
      };

      // Set preview
      if (previewVideoRef.current) {
        previewVideoRef.current.srcObject = stream;
        previewVideoRef.current.play().catch(() => {});
      }

      // Generate neat clean Room ID (e.g. XNX-7489)
      const generatedId = 'XNX-' + Math.floor(1000 + Math.random() * 9000);
      setMyRoomId(generatedId);

      // Create Host Peer
      const peer = new Peer(generatedId, {
        config: {
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' }
          ]
        }
      });
      peerRef.current = peer;

      peer.on('open', (id) => {
        console.log('[Host] Sala P2P registrada:', id);
        setIsStreaming(true);
      });

      // Answer incoming viewer calls with screen stream
      peer.on('call', (call) => {
        console.log('[Host] Novo espectador conectando...');
        call.answer(stream);
        activeCallsRef.current.push(call);
        setViewerCount(activeCallsRef.current.length);

        call.on('close', () => {
          activeCallsRef.current = activeCallsRef.current.filter(c => c !== call);
          setViewerCount(activeCallsRef.current.length);
        });

        call.on('error', (err) => {
          console.warn('[Host] Call error from viewer:', err);
          activeCallsRef.current = activeCallsRef.current.filter(c => c !== call);
          setViewerCount(activeCallsRef.current.length);
        });
      });

      peer.on('error', (err) => {
        console.error('[Host] Peer error:', err);
      });

    } catch (err: any) {
      console.error('[Host] Failed to start screen capture:', err);
      if (err.name !== 'NotAllowedError') {
        alert('Não foi possível capturar a tela: ' + err.message);
      }
    }
  };

  // Stop Broadcast
  const stopStream = () => {
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach(track => track.stop());
      localStreamRef.current = null;
    }
    if (previewVideoRef.current) {
      previewVideoRef.current.srcObject = null;
    }
    if (peerRef.current) {
      peerRef.current.destroy();
      peerRef.current = null;
    }
    activeCallsRef.current = [];
    setViewerCount(0);
    setIsStreaming(false);
    setMyRoomId('');
  };

  // Copy Room Code
  const copyRoomCode = () => {
    if (!myRoomId) return;
    navigator.clipboard.writeText(myRoomId);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

      // Copy Web Link for Friends (Cloudflare Pages or Local)
  const copyWebLink = () => {
    if (!myRoomId) return;
    const base = cloudflareUrl.trim().replace(/\/$/, '');
    const fullUrl = base 
      ? `${base}/?room=${myRoomId}` 
      : `http://localhost:59123/watch.html?room=${myRoomId}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedWebLink(true);
    setTimeout(() => setCopiedWebLink(false), 2000);
  };

  // Open in Default Browser (Chrome/Edge)
  const handleOpenInBrowser = () => {
    if (!myRoomId) return;
    const watchUrl = 'http://localhost:59123/watch.html?room=' + myRoomId;
    if (api && api.OpenBrowser) {
      api.OpenBrowser(watchUrl);
    } else {
      window.open('/watch.html?room=' + myRoomId, '_blank');
    }
  };

  // Open Pop-out Viewer Window
  const handleOpenViewer = async (codeToJoin?: string, titleToUse?: string) => {
    const targetRoom = (codeToJoin || joinRoomId).trim().toUpperCase();
    if (!targetRoom) {
      alert('Por favor, informe o código da sala para assistir.');
      return;
    }

    saveRecentRoom(targetRoom);
    const windowTitle = titleToUse || joinTitle.trim() || `Stream - ${targetRoom}`;

    if (api && api.OpenStreamViewer) {
      await api.OpenStreamViewer(targetRoom, windowTitle);
    } else {
      // Fallback for browser testing
      window.open(`/?mode=viewer&room=${targetRoom}&title=${encodeURIComponent(windowTitle)}`, '_blank');
    }
  };

  // Format seconds to mm:ss or hh:mm:ss
  const formatTime = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) {
      return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="stream-tab-container">
      {/* Header */}
      <div className="stream-tab-header">
        <div className="header-badge">
          <Radio size={14} className="pulse-red" />
          <span>WebRTC Peer-to-Peer</span>
        </div>
        <h2>Compartilhamento de Tela & Streams</h2>
        <p>Transmita sua tela com qualidade personalizada e assista em janelas pop-out independentes.</p>
      </div>

      <div className="stream-grid">
        {/* Card 1: Transmitir Minha Tela (Host) */}
        <div className="stream-card host-card">
          <div className="stream-card-header">
            <div className="card-title-group">
              <div className="card-icon-bubble">
                <Tv size={20} color="var(--primary)" />
              </div>
              <div>
                <h3>Transmitir Tela (Host)</h3>
                <span className="card-subtitle">Compartilhe sua tela ou jogos sem servidores intermediários</span>
              </div>
            </div>
            {isStreaming && (
              <div className="live-tag">
                <span className="live-dot"></span> LIVE
              </div>
            )}
          </div>

          <div className="stream-card-body">
            {!isStreaming ? (
              <>
                <div className="form-group">
                  <label>Título da Transmissão</label>
                  <input 
                    type="text" 
                    value={streamTitle} 
                    onChange={e => handleTitleChange(e.target.value)}
                    placeholder="Ex: Osu gameplay, Filmes, Wuthering Waves..."
                    className="stream-input"
                  />
                </div>

                {/* Separate Resolution Selector */}
                <div className="form-group">
                  <div className="setting-label-row">
                    <label>Resolução de Vídeo</label>
                    <span className="setting-hint">Salvo automaticamente</span>
                  </div>
                  <div className="custom-options-grid">
                    {RESOLUTIONS.map(r => (
                      <div 
                        key={r.id}
                        className={`custom-option-pill ${selectedResolution === r.id ? 'active' : ''}`}
                        onClick={() => handleResolutionChange(r.id)}
                      >
                        <div className="option-pill-title">
                          <Sliders size={12} className="pill-icon" />
                          <span>{r.label}</span>
                        </div>
                        <div className="option-pill-desc">{r.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Separate FPS Selector */}
                <div className="form-group">
                  <div className="setting-label-row">
                    <label>Taxa de Quadros (FPS)</label>
                    <span className="setting-hint">Salvo automaticamente</span>
                  </div>
                  <div className="custom-fps-grid">
                    {FPS_OPTIONS.map(f => (
                      <div 
                        key={f.fps}
                        className={`custom-fps-pill ${selectedFps === f.fps ? 'active' : ''}`}
                        onClick={() => handleFpsChange(f.fps)}
                      >
                        <div className="fps-pill-header">
                          <Zap size={13} className="fps-icon" />
                          <span className="fps-pill-num">{f.label}</span>
                        </div>
                        <div className="fps-pill-desc">{f.desc}</div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="form-group-checkbox">
                  <label className="checkbox-label">
                    <input 
                      type="checkbox" 
                      checked={captureAudio} 
                      onChange={e => handleAudioChange(e.target.checked)}
                    />
                    <span>Capturar Áudio do Sistema / Jogos</span>
                  </label>
                </div>

                <button className="btn-start-stream" onClick={startStream}>
                  <Play size={18} fill="currentColor" /> Iniciar Transmissão
                </button>
              </>
            ) : (
              <div className="active-stream-view">
                <div className="preview-container">
                  <video 
                    ref={previewVideoRef} 
                    muted 
                    autoPlay 
                    playsInline 
                    className="preview-video"
                  />
                  <div className="preview-overlay">
                    <span className="preview-label">Seu Preview Local ({selectedResolution.toUpperCase()} @ {selectedFps > 0 ? selectedFps + ' FPS' : 'Nativo'})</span>
                  </div>
                </div>

                <div className="stream-stats-bar">
                  <div className="stat-item">
                    <Clock size={16} />
                    <div>
                      <span className="stat-label">Tempo no Ar</span>
                      <span className="stat-value">{formatTime(uptimeSeconds)}</span>
                    </div>
                  </div>
                  <div className="stat-item">
                    <Users size={16} />
                    <div>
                      <span className="stat-label">Espectadores</span>
                      <span className="stat-value">{viewerCount} conectado(s)</span>
                    </div>
                  </div>
                </div>

                <div className="room-share-box">
                  <div className="room-share-info">
                    <span className="room-label">Código da Sala:</span>
                    <span className="room-code-display">{myRoomId}</span>
                  </div>
                  <button className="btn-copy-code" onClick={copyRoomCode}>
                    {copiedCode ? <Check size={16} color="#10B981" /> : <Copy size={16} />}
                    {copiedCode ? 'Copiado!' : 'Copiar'}
                  </button>
                </div>

                <div className="host-actions">
                  <button 
                    className="btn-open-my-preview"
                    onClick={() => handleOpenViewer(myRoomId, streamTitle + ' (Meu Preview)')}
                  >
                    <ExternalLink size={16} /> Abrir Preview em Janela Pop-out
                  </button>
                  <button 
                    className="btn-open-my-preview"
                    onClick={handleOpenInBrowser}
                    title="Abrir no Google Chrome ou Edge padrão"
                    style={{ background: 'rgba(56, 189, 248, 0.12)', borderColor: 'rgba(56, 189, 248, 0.3)', color: '#38BDF8' }}
                  >
                    <ExternalLink size={16} /> Abrir no Navegador Local (Zen / Chrome / Edge)
                  </button>
                  <button 
                    className="btn-open-my-preview"
                    onClick={copyWebLink}
                    title="Copiar link web completo para enviar aos amigos"
                    style={{ background: 'rgba(168, 85, 247, 0.12)', borderColor: 'rgba(168, 85, 247, 0.3)', color: '#C084FC' }}
                  >
                    {copiedWebLink ? <Check size={16} color="#10B981" /> : <Copy size={16} />}
                    {copiedWebLink ? 'Link Copiado!' : 'Copiar Link para Amigos (Web)'}
                  </button>


                  <button className="btn-stop-stream" onClick={stopStream}>
                    <Square size={16} fill="currentColor" /> Encerrar Transmissão
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Card 2: Assistir Transmissão (Viewer) */}
        <div className="stream-card viewer-card">
          <div className="stream-card-header">
            <div className="card-title-group">
              <div className="card-icon-bubble">
                <ExternalLink size={20} color="#38BDF8" />
              </div>
              <div>
                <h3>Assistir Transmissão (Viewer)</h3>
                <span className="card-subtitle">Abra telas em janelas independentes (Estilo Docks/OBS)</span>
              </div>
            </div>
          </div>

          <div className="stream-card-body">
            <div className="form-group">
              <label>Código da Sala do Amigo</label>
              <div className="input-with-action">
                <input 
                  type="text" 
                  value={joinRoomId} 
                  onChange={e => setJoinRoomId(e.target.value.toUpperCase())}
                  placeholder="Ex: XNX-1234"
                  className="stream-input font-mono"
                  onKeyDown={e => { if (e.key === 'Enter') handleOpenViewer(); }}
                />
                <button 
                  className="btn-paste-code" 
                  onClick={async () => {
                    try {
                      const text = await navigator.clipboard.readText();
                      if (text) setJoinRoomId(text.trim().toUpperCase());
                    } catch {}
                  }}
                  title="Colar da área de transferência"
                >
                  Colar
                </button>
              </div>
            </div>

            <div className="form-group">
              <label>Apelido / Nome da Janela (Opcional)</label>
              <input 
                type="text" 
                value={joinTitle} 
                onChange={e => setJoinTitle(e.target.value)}
                placeholder="Ex: Tela do Pedro, Osu, Live..."
                className="stream-input"
              />
            </div>

            <button className="btn-open-popout" onClick={() => handleOpenViewer()}>
              <ExternalLink size={18} /> Abrir em Janela Separada
            </button>

            {/* Recent rooms history */}
            {recentRooms.length > 0 && (
              <div className="recent-rooms-section">
                <div className="recent-header">
                  <span>Salas Recentes</span>
                </div>
                <div className="recent-list">
                  {recentRooms.map(room => (
                    <div key={room} className="recent-item">
                      <span className="recent-code" onClick={() => handleOpenViewer(room)}>
                        {room}
                      </span>
                      <div className="recent-actions">
                        <button 
                          className="recent-btn open" 
                          onClick={() => handleOpenViewer(room)}
                          title="Abrir nesta janela"
                        >
                          <ExternalLink size={14} />
                        </button>
                        <button 
                          className="recent-btn delete" 
                          onClick={() => removeRecentRoom(room)}
                          title="Remover do histórico"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            
            {/* Cloudflare Pages Web Link Config */}
            <div className="form-group" style={{ marginTop: '8px' }}>
              <label>Link Público Cloudflare Pages (Opcional para Amigos)</label>
              <input 
                type="text" 
                value={cloudflareUrl} 
                onChange={e => {
                  setCloudflareUrl(e.target.value);
                  localStorage.setItem('xennex_cloudflare_url', e.target.value);
                }}
                placeholder="Ex: https://meu-xennex.pages.dev"
                className="stream-input"
              />
              <span style={{ fontSize: '0.72rem', color: '#64748B' }}>
                Deixe em branco para testar localmente, ou coloque sua URL da Cloudflare Pages para amigos.
              </span>
            </div>

            {/* Info highlight */}
            <div className="info-dock-tip">
              <Sparkles size={18} color="#38BDF8" className="tip-icon" />
              <div>
                <strong>Dica Pop-out:</strong> As telas abrem como janelas independentes do Windows. Você pode arrastá-las para qualquer monitor, redimensionar livremente, fixar no topo (📌 Always on Top) e abrir várias telas ao mesmo tempo!
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StreamTab;

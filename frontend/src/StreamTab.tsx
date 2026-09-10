import React, { useState, useEffect, useRef } from 'react';
import { Peer, type MediaConnection } from 'peerjs';
import { 
  Tv, Radio, Play, Square, ExternalLink, Copy, Check, Users, 
  Clock, Sparkles, Trash2, Sliders, Zap, Volume2, VolumeX, Crosshair, RefreshCw,
  Shuffle
} from 'lucide-react';
import type { DataConnection } from 'peerjs';

interface AudioProcessItem {
  Pid: number;
  Name: string;
  Title: string;
  HasActiveAudio: boolean;
  PeakVolume: number;
}

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

  const [customRoomId, setCustomRoomId] = useState<string>(() => {
    return localStorage.getItem('xennex_stream_custom_room') || '';
  });



  const [audioMode, setAudioMode] = useState<'process' | 'system' | 'none'>(() => {
    const saved = localStorage.getItem('xennex_stream_audio_mode');
    return (saved as any) || 'process';
  });

  const [selectedProcessPid, setSelectedProcessPid] = useState<number | null>(() => {
    const saved = localStorage.getItem('xennex_stream_audio_pid');
    return saved ? parseInt(saved, 10) : null;
  });

  const [audioProcesses, setAudioProcesses] = useState<AudioProcessItem[]>([]);
  const [isLoadingProcesses, setIsLoadingProcesses] = useState(false);
  const [capturedProcessName, setCapturedProcessName] = useState<string>('');

  const processAudioSocketRef = useRef<WebSocket | null>(null);
  const processAudioContextRef = useRef<AudioContext | null>(null);

  const [isStreaming, setIsStreaming] = useState(false);
  const [hasCapturedAudio, setHasCapturedAudio] = useState<boolean>(false);
  const [capturedStats, setCapturedStats] = useState<{
    width?: number;
    height?: number;
    fps?: number;
  } | null>(null);
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
  const rawStreamRef = useRef<MediaStream | null>(null);
  const canvasRendererRef = useRef<{ stop: () => void } | null>(null);
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const peerRef = useRef<Peer | null>(null);
  const activeCallsRef = useRef<MediaConnection[]>([]);
  const roomDataConnectionsRef = useRef<DataConnection[]>([]);
  const activeCoStreamersRef = useRef<{ peerId: string; title: string }[]>([]);
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

  const handleRoomCodeChange = (val: string) => {
    const cleaned = val.toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 20);
    setCustomRoomId(cleaned);
    localStorage.setItem('xennex_stream_custom_room', cleaned);
  };

  const generateRandomRoomId = () => {
    const code = 'XNX-' + Math.floor(1000 + Math.random() * 9000);
    setCustomRoomId(code);
    localStorage.setItem('xennex_stream_custom_room', code);
    return code;
  };



  const handleAudioModeChange = (mode: 'process' | 'system' | 'none') => {
    setAudioMode(mode);
    localStorage.setItem('xennex_stream_audio_mode', mode);
  };

  const handleProcessSelect = (pid: number) => {
    setSelectedProcessPid(pid);
    localStorage.setItem('xennex_stream_audio_pid', pid.toString());
  };

  const fetchAudioProcesses = async () => {
    if (!api?.GetAudioProcesses) return;
    setIsLoadingProcesses(true);
    try {
      const json = await api.GetAudioProcesses();
      const list: AudioProcessItem[] = JSON.parse(json);
      setAudioProcesses(list);
      if (list.length > 0) {
        setSelectedProcessPid(prev => {
          if (prev && list.some(p => p.Pid === prev)) return prev;
          const active = list.find(p => p.HasActiveAudio) || list[0];
          return active ? active.Pid : list[0].Pid;
        });
      }
    } catch (e) {
      console.warn('[StreamTab] Erro ao carregar processos:', e);
    } finally {
      setIsLoadingProcesses(false);
    }
  };

  useEffect(() => {
    fetchAudioProcesses();
  }, []);

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
        videoConstraints.frameRate = {
          ideal: selectedFps,
          max: selectedFps
        };
      } else {
        // Modo Ilimitado / High Refresh Rate (120Hz / 144Hz)
        videoConstraints.frameRate = {
          ideal: 144,
          max: 240
        };
      }

      let processAudioTrack: MediaStreamTrack | null = null;

      let targetPid = selectedProcessPid;
      if (!targetPid && audioProcesses.length > 0) {
        const active = audioProcesses.find(p => p.HasActiveAudio) || audioProcesses[0];
        targetPid = active ? active.Pid : audioProcesses[0].Pid;
        setSelectedProcessPid(targetPid);
      }

      if (audioMode === 'process' && targetPid && api?.StartProcessAudioCapture) {
        try {
          console.log('[Host] Solicitando captura de áudio para PID:', targetPid);
          const success = await api.StartProcessAudioCapture(targetPid);
          if (success) {
            const activeProc = audioProcesses.find(p => p.Pid === targetPid);
            const procLabel = activeProc ? (activeProc.Title || activeProc.Name) : `PID ${targetPid}`;
            setCapturedProcessName(procLabel);
            console.log('[Host] Captura de áudio de processo ativada com sucesso para:', procLabel);

            const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
            const audioCtx = new AudioCtx();
            processAudioContextRef.current = audioCtx;
            if (audioCtx.state === 'suspended') {
              await audioCtx.resume();
            }

            const destination = audioCtx.createMediaStreamDestination();
            processAudioTrack = destination.stream.getAudioTracks()[0];

            // Injetar portadora silenciosa (oscilador 0 volume) para garantir que a faixa permaneça ativa no WebRTC mesmo quando o jogo estiver em tela de carregamento/silêncio
            try {
              const silentGain = audioCtx.createGain();
              silentGain.gain.value = 0.00001;
              const osc = audioCtx.createOscillator();
              osc.connect(silentGain);
              silentGain.connect(destination);
              osc.start();
            } catch (carrierErr) {
              console.warn('[Host] Portadora de áudio não inicializada:', carrierErr);
            }

            let nextStartTime = 0;
            let sampleRate = 48000;

            const ws = new WebSocket('ws://127.0.0.1:59123/audiostream');
            ws.binaryType = 'arraybuffer';
            processAudioSocketRef.current = ws;

            ws.onopen = () => {
              console.log('[Host] WebSocket de áudio conectado com sucesso');
            };

            ws.onmessage = (e) => {
              if (typeof e.data === 'string') {
                try {
                  const meta = JSON.parse(e.data);
                  if (meta.sampleRate) sampleRate = meta.sampleRate;
                } catch {}
                return;
              }

              if (e.data instanceof ArrayBuffer && audioCtx.state !== 'closed') {
                const floatData = new Float32Array(e.data);
                const channels = 2;
                const numFrames = floatData.length / channels;
                if (numFrames <= 0) return;

                const buffer = audioCtx.createBuffer(channels, numFrames, sampleRate);
                const ch0 = buffer.getChannelData(0);
                const ch1 = buffer.getChannelData(1);
                for (let i = 0; i < numFrames; i++) {
                  ch0[i] = floatData[i * 2];
                  ch1[i] = floatData[i * 2 + 1];
                }

                const source = audioCtx.createBufferSource();
                source.buffer = buffer;
                source.connect(destination);

                const now = audioCtx.currentTime;
                if (nextStartTime < now || nextStartTime > now + 0.1) {
                  nextStartTime = now + 0.02; // 20ms jitter buffer clamp
                }
                source.start(nextStartTime);
                nextStartTime += buffer.duration;
              }
            };

            ws.onerror = (err) => console.warn('[Host] WebSocket de áudio erro:', err);
            ws.onclose = () => console.log('[Host] WebSocket de áudio desconectado');
          } else {
            console.warn('[Host] Falha ao ativar captura de processo no backend');
            alert('Não foi possível iniciar a captura exclusiva de áudio para este aplicativo. Verifique se o jogo está aberto e com som ativado.');
          }
        } catch (procAudioErr) {
          console.error('[Host] Erro ao iniciar captura de processo:', procAudioErr);
        }
      }

      let stream: MediaStream;
      const requestSystemAudio = audioMode === 'system';
      try {
        stream = await (mediaDevices as any).getDisplayMedia({
          video: {
            ...videoConstraints,
            cursor: 'always'
          },
          audio: requestSystemAudio ? {
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          } : false,
          systemAudio: requestSystemAudio ? 'include' : 'exclude',
          selfBrowserSurface: 'exclude',
          surfaceSwitching: 'include'
        } as any);
      } catch (audioErr: any) {
        if (audioErr.name === 'NotAllowedError') throw audioErr;
        console.warn('[Host] Retrying getDisplayMedia with simple audio constraints', audioErr);
        stream = await (mediaDevices as any).getDisplayMedia({
          video: {
            ...videoConstraints,
            cursor: 'always'
          },
          audio: requestSystemAudio ? true : false,
          systemAudio: requestSystemAudio ? 'include' : 'exclude'
        } as any);
      }

      rawStreamRef.current = stream;

      // Handle user ending capture from browser/system toolbar
      stream.getVideoTracks()[0].onended = () => {
        stopStream();
      };

      const audioTracks = stream.getAudioTracks();
      const hasAudio = audioTracks.length > 0;
      setHasCapturedAudio(hasAudio);

      // Compositor de Canvas estilo OBS:
      // Garante que o stream transmitido tenha EXATAMENTE a resolucao selecionada (ex: 2560x1440 @ 60 FPS),
      // escalonando qualquer janela/tela perfeitamente com loop continuo a 60 FPS!
      let streamToSend = stream;

      if (res.width && res.height) {
        const targetW = res.width;
        const targetH = res.height;
        const targetFps = selectedFps > 0 ? selectedFps : 60;

        const canvas = document.createElement('canvas');
        canvas.width = targetW;
        canvas.height = targetH;
        const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true });

        const hiddenVideo = document.createElement('video');
        hiddenVideo.autoplay = true;
        hiddenVideo.muted = true;
        hiddenVideo.playsInline = true;
        hiddenVideo.srcObject = stream;
        await hiddenVideo.play().catch(() => {});

        let isRendering = true;
        let worker: Worker | null = null;
        let animId: number | null = null;

        const drawFrame = () => {
          if (!isRendering || !ctx) return;
          const vW = hiddenVideo.videoWidth;
          const vH = hiddenVideo.videoHeight;
          if (vW > 0 && vH > 0) {
            const scale = Math.min(targetW / vW, targetH / vH);
            const drawW = Math.round(vW * scale);
            const drawH = Math.round(vH * scale);
            const offX = Math.round((targetW - drawW) / 2);
            const offY = Math.round((targetH - drawH) / 2);

            if (offX > 0 || offY > 0) {
              ctx.fillStyle = '#000000';
              ctx.fillRect(0, 0, targetW, targetH);
            }
            ctx.drawImage(hiddenVideo, offX, offY, drawW, drawH);
          } else {
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, targetW, targetH);
          }
        };

        const scheduleRaf = () => {
          if (!isRendering) return;
          drawFrame();
          animId = requestAnimationFrame(scheduleRaf);
        };
        scheduleRaf();

        try {
          const workerBlob = new Blob([
            `let t=null;onmessage=e=>{if(e.data==='s'){t=setInterval(()=>postMessage(1),${Math.round(1000 / targetFps)})}else if(t){clearInterval(t)}}`
          ], { type: 'application/javascript' });
          worker = new Worker(URL.createObjectURL(workerBlob));
          worker.onmessage = () => {
            if (isRendering) drawFrame();
          };
          worker.postMessage('s');
        } catch (wErr) {
          console.warn('[Host] Worker timer fallback:', wErr);
        }

        const canvasStream = (canvas as any).captureStream ? (canvas as any).captureStream(targetFps) : (canvas as any).mozCaptureStream(targetFps);
        
        if (processAudioTrack) {
          canvasStream.addTrack(processAudioTrack);
          setHasCapturedAudio(true);
        } else if (audioMode === 'system') {
          audioTracks.forEach(track => canvasStream.addTrack(track));
          setHasCapturedAudio(audioTracks.length > 0);
        } else {
          setHasCapturedAudio(false);
        }

        streamToSend = canvasStream;

        canvasRendererRef.current = {
          stop: () => {
            isRendering = false;
            if (animId) cancelAnimationFrame(animId);
            if (worker) {
              worker.postMessage('stop');
              worker.terminate();
            }
            hiddenVideo.srcObject = null;
            canvasStream.getTracks().forEach((t: MediaStreamTrack) => t.stop());
          }
        };

        setCapturedStats({
          width: targetW,
          height: targetH,
          fps: targetFps
        });
      } else {
        if (processAudioTrack) {
          streamToSend = new MediaStream([stream.getVideoTracks()[0], processAudioTrack]);
          setHasCapturedAudio(true);
        }
        const trackSettings = stream.getVideoTracks()[0]?.getSettings();
        setCapturedStats({
          width: trackSettings?.width,
          height: trackSettings?.height,
          fps: trackSettings?.frameRate ? Math.round(trackSettings.frameRate) : (selectedFps || 60)
        });
      }

      const outVideoTrack = streamToSend.getVideoTracks()[0];
      if (outVideoTrack && 'contentHint' in outVideoTrack) {
        outVideoTrack.contentHint = 'detail';
      }

      localStreamRef.current = streamToSend;

      // Set preview
      if (previewVideoRef.current) {
        previewVideoRef.current.srcObject = streamToSend;
        previewVideoRef.current.play().catch(() => {});
      }

      // Definir código de sala desejado (ou gerar aleatório caso vazio)
      const targetRoom = customRoomId.trim().toUpperCase() || generateRandomRoomId();
      setMyRoomId(targetRoom);

      // Tentar registrar como Host Principal da Sala
      const peer = new Peer(targetRoom, {
        config: {
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' }
          ]
        }
      });
      peerRef.current = peer;

      peer.on('open', (id) => {
        console.log('[Host Hub] Sala P2P registrada como Host Principal:', id);
        setIsStreaming(true);
      });

      // Gerenciar conexões de dados da sala (Coordenação Multi-Stream Discord Style)
      peer.on('connection', (conn) => {
        roomDataConnectionsRef.current.push(conn);

        conn.on('open', () => {
          if (activeCoStreamersRef.current.length > 0) {
            conn.send({
              type: 'streamers-list',
              streamers: activeCoStreamersRef.current
            });
          }
        });

        conn.on('data', (data: any) => {
          if (data && data.type === 'register-co-streamer') {
            console.log('[Host Hub] Novo Co-Streamer registrado na sala:', data);
            activeCoStreamersRef.current = [
              ...activeCoStreamersRef.current.filter(s => s.peerId !== data.peerId),
              { peerId: data.peerId, title: data.title }
            ];

            roomDataConnectionsRef.current.forEach(c => {
              if (c.open && c.peer !== conn.peer) {
                c.send({
                  type: 'co-streamer-added',
                  peerId: data.peerId,
                  title: data.title
                });
              }
            });
          }
        });

        conn.on('close', () => {
          roomDataConnectionsRef.current = roomDataConnectionsRef.current.filter(c => c !== conn);
        });
      });

      // Answer incoming viewer calls with screen stream
      peer.on('call', (call) => {
        console.log('[Host] Novo espectador conectando...');
        call.answer(localStreamRef.current || stream);
        activeCallsRef.current.push(call);
        setViewerCount(activeCallsRef.current.length);

        // Otimizacao WebRTC RTCRtpSender para 60 FPS e Bitrate Elevado (15 a 25 Mbps) com retry robusto
        const tuneSenders = async () => {
          try {
            const pc = (call as any).peerConnection as RTCPeerConnection;
            if (!pc) return false;
            let success = false;
            for (const sender of pc.getSenders()) {
              if (sender.track && sender.track.kind === 'video') {
                const params = sender.getParameters();
                if (!params.encodings || params.encodings.length === 0) {
                  params.encodings = [{}];
                }
                const targetBitrate = selectedFps === 0 ? 25_000_000 : (selectedFps >= 60 ? 15_000_000 : 8_000_000);
                params.encodings[0].maxBitrate = targetBitrate;
                params.encodings[0].maxFramerate = selectedFps > 0 ? selectedFps : 144;
                params.encodings[0].networkPriority = 'high';
                params.encodings[0].scaleResolutionDownBy = 1.0;
                params.degradationPreference = 'maintain-resolution';
                await sender.setParameters(params);
                success = true;
              } else if (sender.track && sender.track.kind === 'audio') {
                try {
                  const aParams = sender.getParameters();
                  if (!aParams.encodings || aParams.encodings.length === 0) {
                    aParams.encodings = [{}];
                  }
                  aParams.encodings[0].maxBitrate = 256_000;
                  aParams.encodings[0].networkPriority = 'high';
                  await sender.setParameters(aParams);
                } catch (aErr) {
                  console.warn('[Host] Audio sender tune:', aErr);
                }
              }
            }
            return success;
          } catch (e) {
            return false;
          }
        };

        let tuneAttempts = 0;
        const tuneTimer = window.setInterval(async () => {
          tuneAttempts++;
          const ok = await tuneSenders();
          if (ok || tuneAttempts >= 12) {
            window.clearInterval(tuneTimer);
          }
        }, 400);

        const pc = (call as any).peerConnection as RTCPeerConnection;
        if (pc) {
          pc.addEventListener('connectionstatechange', () => {
            if (pc.connectionState === 'connected') tuneSenders();
          });
          pc.addEventListener('iceconnectionstatechange', () => {
            if (pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') tuneSenders();
          });
        }

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

      peer.on('error', (err: any) => {
        if (err.type === 'unavailable-id') {
          console.log(`[Host] Sala "${targetRoom}" já existe. Entrando automaticamente como Co-Streamer...`);
          try { peer.destroy(); } catch {}

          const coId = `${targetRoom}_co_${Math.floor(1000 + Math.random() * 9000)}`;
          const coPeer = new Peer(coId, {
            config: {
              iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' }
              ]
            }
          });
          peerRef.current = coPeer;

          coPeer.on('open', (myCoPeerId) => {
            console.log('[Co-Streamer] Conectado à sala como transmissor adicional:', myCoPeerId);
            setIsStreaming(true);
            setMyRoomId(targetRoom);

            const hubConn = coPeer.connect(targetRoom);
            hubConn.on('open', () => {
              hubConn.send({
                type: 'register-co-streamer',
                peerId: myCoPeerId,
                title: streamTitle || 'Gameplay Secundária'
              });
            });
          });

          coPeer.on('call', (incomingCall) => {
            console.log('[Co-Streamer] Atendendo espectador na transmissão secundária...');
            incomingCall.answer(localStreamRef.current || stream);
            activeCallsRef.current.push(incomingCall);
            setViewerCount(activeCallsRef.current.length);
          });
        } else {
          console.error('[Host] Peer error:', err);
        }
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
    if (canvasRendererRef.current) {
      try { canvasRendererRef.current.stop(); } catch {}
      canvasRendererRef.current = null;
    }
    if (rawStreamRef.current) {
      try { rawStreamRef.current.getTracks().forEach(track => track.stop()); } catch {}
      rawStreamRef.current = null;
    }
    if (localStreamRef.current) {
      try { localStreamRef.current.getTracks().forEach(track => track.stop()); } catch {}
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
    setCapturedStats(null);
    setHasCapturedAudio(false);
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
                {/* Custom Room Code Chooser */}
                <div className="form-group">
                  <div className="setting-label-row">
                    <label>Código / Nome da Sala</label>
                    <span className="setting-hint">Escolha a sala para transmitir</span>
                  </div>
                  <div className="room-chooser-input-group">
                    <input 
                      type="text" 
                      value={customRoomId} 
                      onChange={e => handleRoomCodeChange(e.target.value)}
                      placeholder="Ex: XENPHI, LOBBY, SALA-1..."
                      className="stream-input"
                      maxLength={20}
                    />
                    <button 
                      type="button" 
                      className="btn-random-room"
                      onClick={generateRandomRoomId}
                      title="Gerar código aleatório (ex: XNX-1234)"
                    >
                      <Shuffle size={14} />
                      <span>Aleatório</span>
                    </button>
                  </div>
                  <div className="room-chooser-hint">
                    💡 <strong>Salas Multi-Stream (Estilo Discord):</strong> Se a sala já estiver aberta por um amigo, você entrará automaticamente como segundo streamer e todos na sala verão ambas as telas!
                  </div>
                </div>

                <div className="form-group">
                  <label>Título da Sua Transmissão</label>
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

                {/* Custom Audio Capture Modes (Discord & OBS Style) */}
                <div className="form-group">
                  <div className="setting-label-row">
                    <label>Modo de Captura de Áudio</label>
                    <span className="setting-hint">Discord / OBS Style</span>
                  </div>
                  
                  <div className="custom-audio-modes-grid">
                    <div 
                      className={`custom-option-pill ${audioMode === 'process' ? 'active' : ''}`}
                      onClick={() => handleAudioModeChange('process')}
                    >
                      <div className="option-pill-title">
                        <Crosshair size={13} className="pill-icon" />
                        <span>Aplicativo / Jogo</span>
                      </div>
                      <div className="option-pill-desc">Som isolado do jogo (Sem chamadas/Discord)</div>
                    </div>

                    <div 
                      className={`custom-option-pill ${audioMode === 'system' ? 'active' : ''}`}
                      onClick={() => handleAudioModeChange('system')}
                    >
                      <div className="option-pill-title">
                        <Volume2 size={13} className="pill-icon" />
                        <span>Todo o Sistema</span>
                      </div>
                      <div className="option-pill-desc">Todos os sons do Windows e chamadas</div>
                    </div>

                    <div 
                      className={`custom-option-pill ${audioMode === 'none' ? 'active' : ''}`}
                      onClick={() => handleAudioModeChange('none')}
                    >
                      <div className="option-pill-title">
                        <VolumeX size={13} className="pill-icon" />
                        <span>Sem Áudio</span>
                      </div>
                      <div className="option-pill-desc">Transmissão completamente muda</div>
                    </div>
                  </div>

                  {audioMode === 'process' && (
                    <div className="process-audio-panel">
                      <div className="process-select-header">
                        <label className="sub-label">Selecione o Jogo ou Aplicativo:</label>
                        <button 
                          type="button" 
                          className="btn-refresh-processes" 
                          onClick={fetchAudioProcesses}
                          disabled={isLoadingProcesses}
                          title="Escanear aplicativos e jogos abertos"
                        >
                          <RefreshCw size={12} className={isLoadingProcesses ? 'spin-icon' : ''} />
                          <span>Atualizar Lista</span>
                        </button>
                      </div>

                      <div className="process-select-wrapper">
                        <select 
                          className="process-select"
                          value={selectedProcessPid || ''}
                          onChange={e => handleProcessSelect(parseInt(e.target.value, 10))}
                        >
                          {audioProcesses.length === 0 ? (
                            <option value="">Nenhum aplicativo com som encontrado</option>
                          ) : (
                            audioProcesses.map(p => (
                              <option key={p.Pid} value={p.Pid}>
                                {p.HasActiveAudio ? '🔊 [Com Áudio] ' : '🎮 '}
                                {p.Title && p.Title !== p.Name ? `${p.Title} (${p.Name}.exe)` : `${p.Name}.exe`}
                              </option>
                            ))
                          )}
                        </select>
                      </div>

                      <div className="process-hint-card">
                        🎯 <strong>Áudio Exclusivo (Discord Style):</strong> Os espectadores ouvirão <strong>somente</strong> o som deste jogo. Suas conversas no Discord, notificações do Windows e cliques do mouse/teclado <strong>não</strong> vazam na live!
                      </div>
                    </div>
                  )}

                  {audioMode === 'system' && (
                    <div className="system-audio-hint">
                      💡 <strong>Áudio Global do Sistema:</strong> No seletor do Windows que abrir, selecione a aba <strong>"Tela inteira"</strong> e marque a opção <strong>"Compartilhar áudio do sistema"</strong> no canto inferior esquerdo.
                    </div>
                  )}
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
                    <span className="preview-label">
                      {capturedStats?.width && capturedStats?.height 
                        ? `${capturedStats.width}x${capturedStats.height} @ ${capturedStats.fps || selectedFps} FPS` 
                        : `${selectedResolution.toUpperCase()} @ ${selectedFps > 0 ? selectedFps + ' FPS' : 'Nativo'}`}
                      {hasCapturedAudio ? (
                        capturedProcessName ? ` • 🎯 Áudio: ${capturedProcessName}` : ' • 🔊 Áudio Sistema'
                      ) : ' • 🔇 Sem Áudio'}
                    </span>
                  </div>
                </div>

                {audioMode === 'system' && !hasCapturedAudio && (
                  <div style={{
                    background: 'rgba(245, 158, 11, 0.12)',
                    border: '1px solid rgba(245, 158, 11, 0.35)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    margin: '10px 0',
                    fontSize: '0.8rem',
                    lineHeight: '1.4',
                    color: '#FDE68A'
                  }}>
                    ⚠️ <strong>Áudio do sistema não detectado:</strong> No Windows, para que os espectadores ouçam o som dos seus jogos, selecione a aba <strong>"Tela inteira"</strong> e marque a caixinha <strong>"Compartilhar áudio do sistema"</strong> no canto inferior esquerdo. Se você selecionou uma "Janela", o Windows bloqueia a captura de áudio.
                  </div>
                )}

                {capturedStats && capturedStats.height && capturedStats.height < 1080 && selectedResolution !== '720p' && selectedResolution !== '480p' && (
                  <div style={{
                    background: 'rgba(56, 189, 248, 0.1)',
                    border: '1px solid rgba(56, 189, 248, 0.25)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    margin: '8px 0',
                    fontSize: '0.78rem',
                    color: '#BAE6FD'
                  }}>
                    💡 <strong>Janela ({capturedStats.width}x{capturedStats.height}) Capturada:</strong> Para transmitir na resolução original do seu monitor (2K/1080p), selecione a aba <strong>"Tela inteira"</strong> ao iniciar a transmissão.
                  </div>
                )}

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

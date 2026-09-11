import React, { useState, useEffect, useRef } from 'react';
import { Peer, type MediaConnection } from 'peerjs';
import { 
  Tv, Radio, Play, Square, Pause, ExternalLink, Copy, Check, Users, 
  Clock, Sparkles, Trash2, Sliders, Zap, Volume2, VolumeX, Crosshair, RefreshCw,
  Shuffle, LogIn, Eye
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

interface AudioProcessItem {
  Pid: number;
  Hwnd?: number;
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

const DEFAULT_CLOUDFLARE_URL = 'https://xennex-live.alexdoong11.workers.dev';

const RESOLUTIONS: ResolutionOption[] = [
  { id: 'source', label: 'Fonte Original', desc: 'Resolução nativa sem redimensionar' },
  { id: '1440p',  label: '1440p (2K)',      desc: '2560 x 1440 (Ultra Nitidez)', width: 2560, height: 1440 },
  { id: '1080p',  label: '1080p (Full HD)', desc: '1920 x 1080 (Padrão)', width: 1920, height: 1080 },
  { id: '720p',   label: '720p (HD)',       desc: '1280 x 720 (Economia de Banda)', width: 1280, height: 720 },
  { id: '480p',   label: '480p (SD)',       desc: '854 x 480 (Conexões Lentas)', width: 854, height: 480 }
];

const FPS_OPTIONS: FpsOption[] = [
  { fps: 60, label: '60 FPS', desc: 'Máxima fluidez para jogos competitivos' },
  { fps: 45, label: '45 FPS', desc: 'Equilíbrio excelente entre fluidez e bitrate' },
  { fps: 30, label: '30 FPS', desc: 'Uso moderado de banda e processamento' },
  { fps: 0,  label: 'Nativo', desc: 'Taxa original fornecida pelo Windows' }
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

  // Persistent Room and Streaming States
  const [isRoomOpen, setIsRoomOpen] = useState(false);
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
  const [isDiscordPickerOpen, setIsDiscordPickerOpen] = useState(false);
  const [pickerTab, setPickerTab] = useState<'apps' | 'screens'>('apps');
  const [selectedProcessHwnd, setSelectedProcessHwnd] = useState<number>(0);
  const nativeCaptureSocketRef = useRef<WebSocket | null>(null);
  const nativeCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [pickerSearch, setPickerSearch] = useState('');
  const [participantsList, setParticipantsList] = useState<{ peerId: string; name: string; isHost: boolean; isStreaming: boolean; streamTitle?: string; streamPeerId?: string }[]>([]);
  const [uptimeSeconds, setUptimeSeconds] = useState(0);
  const [cloudflareUrl, setCloudflareUrl] = useState<string>(() => {
    const stored = localStorage.getItem('xennex_cloudflare_url'); if (stored && !stored.includes('localhost') && !stored.includes('127.0.0.1')) { return stored; } localStorage.setItem('xennex_cloudflare_url', DEFAULT_CLOUDFLARE_URL); return DEFAULT_CLOUDFLARE_URL;
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
  const participantsRef = useRef<{ peerId: string; name: string; isHost: boolean; isStreaming: boolean; streamTitle?: string; streamPeerId?: string }[]>([]);
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

  const handleTitleChange = (title: string) => {
    setStreamTitle(title);
    localStorage.setItem('xennex_stream_title', title);
  };

  const handleCustomRoomChange = (code: string) => {
    const formatted = code.toUpperCase().trim();
    setCustomRoomId(formatted);
    localStorage.setItem('xennex_stream_custom_room', formatted);
  };

  const generateRandomRoomId = () => {
    const num = Math.floor(1000 + Math.random() * 9000);
    const code = `XNX-${num}`;
    setCustomRoomId(code);
    localStorage.setItem('xennex_stream_custom_room', code);
    return code;
  };

  const handleCloudflareUrlChange = (url: string) => {
    let clean = url.trim();
    if (clean && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      clean = 'https://' + clean;
    }
    setCloudflareUrl(clean);
    localStorage.setItem('xennex_cloudflare_url', clean);
  };

  const handleAudioModeChange = (mode: 'process' | 'system' | 'none') => {
    setAudioMode(mode);
    localStorage.setItem('xennex_stream_audio_mode', mode);
    if (mode === 'process') {
      fetchAudioProcesses();
    }
  };

  const handleProcessSelect = (pid: number) => {
    setSelectedProcessPid(pid);
    localStorage.setItem('xennex_stream_audio_pid', pid.toString());
    const proc = audioProcesses.find(p => p.Pid === pid);
    if (proc) {
      setCapturedProcessName(proc.Name);
      setSelectedProcessHwnd(proc.Hwnd || 0);
    }
  };

  // Fetch audio processes from C# backend
  const fetchAudioProcesses = async () => {
    if (!api || !api.GetAudioProcesses) return;
    try {
      setIsLoadingProcesses(true);
      const json = await api.GetAudioProcesses();
      const list: AudioProcessItem[] = JSON.parse(json);
      setAudioProcesses(list);
      
      if (selectedProcessPid) {
        const found = list.find(p => p.Pid === selectedProcessPid);
        if (found) {
          setCapturedProcessName(found.Name);
          setSelectedProcessHwnd(found.Hwnd || 0);
        } else if (list.length > 0) {
          const firstWithSound = list.find(p => p.HasActiveAudio) || list[0];
          setSelectedProcessPid(firstWithSound.Pid);
          setSelectedProcessHwnd(firstWithSound.Hwnd || 0);
          setCapturedProcessName(firstWithSound.Name);
        }
      } else if (list.length > 0) {
        const firstWithSound = list.find(p => p.HasActiveAudio) || list[0];
        setSelectedProcessPid(firstWithSound.Pid);
        setSelectedProcessHwnd(firstWithSound.Hwnd || 0);
        setCapturedProcessName(firstWithSound.Name);
      }
    } catch (err) {
      console.warn('Erro ao listar processos de áudio:', err);
    } finally {
      setIsLoadingProcesses(false);
    }
  };

  // Capture isolated process audio via localhost WebSocket
  const startProcessAudioCapture = async (pid: number): Promise<MediaStreamTrack | null> => {
    if (!api || !api.StartProcessAudioCapture) return null;
    try {
      console.log('[ProcessAudio] Iniciando captura WASAPI para PID:', pid);
      const success = await api.StartProcessAudioCapture(pid);
      if (!success) {
        console.warn("[ProcessAudio] Falha ao iniciar captura no backend (StartProcessAudioCapture retornou false)");
        return null;
      }
      console.log("[ProcessAudio] Conectando ao WebSocket local na porta 59123/audiostream");
      const ws = new WebSocket("ws://127.0.0.1:59123/audiostream");
      ws.binaryType = 'arraybuffer';
      processAudioSocketRef.current = ws;

      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioContextClass({ sampleRate: 48000 });
      if (audioCtx.state === 'suspended') {
        try { await audioCtx.resume(); } catch {}
      }
      processAudioContextRef.current = audioCtx;

      const mediaStreamDest = audioCtx.createMediaStreamDestination();

      // Digital gain boost for rich, audible game sound
      const hostGainNode = audioCtx.createGain();
      hostGainNode.gain.value = 1.4;
      hostGainNode.connect(mediaStreamDest);

      // Keep AudioContext alive and prevent Chromium from throttling
      try {
        const dummyOsc = audioCtx.createOscillator();
        const dummyGain = audioCtx.createGain();
        dummyGain.gain.value = 0.00001;
        dummyOsc.connect(dummyGain);
        dummyGain.connect(mediaStreamDest);
        dummyOsc.start();
      } catch (e) {}

      let nextPlayTime = audioCtx.currentTime + 0.03;

      ws.onmessage = async (event) => {
        if (!(event.data instanceof ArrayBuffer)) return;
        const rawBytes = event.data;
        if (rawBytes.byteLength === 0) return;

        if (audioCtx.state === 'suspended') {
          try { await audioCtx.resume(); } catch {}
        }

        const floatArray = new Float32Array(rawBytes);
        const numChannels = 2;
        const numFrames = floatArray.length / numChannels;

        const audioBuffer = audioCtx.createBuffer(numChannels, numFrames, 48000);
        const leftChannel = audioBuffer.getChannelData(0);
        const rightChannel = audioBuffer.getChannelData(1);

        for (let i = 0; i < numFrames; i++) {
          leftChannel[i] = floatArray[i * 2];
          rightChannel[i] = floatArray[i * 2 + 1];
        }

        const sourceNode = audioCtx.createBufferSource();
        sourceNode.buffer = audioBuffer;
        sourceNode.connect(hostGainNode);
        sourceNode.onended = () => {
          try { sourceNode.disconnect(); } catch {}
        };

        const curTime = audioCtx.currentTime;
        if (nextPlayTime < curTime || nextPlayTime > curTime + 0.20) {
          nextPlayTime = curTime + 0.02;
        }
        sourceNode.start(nextPlayTime);
        nextPlayTime += audioBuffer.duration;
      };

      ws.onerror = (err) => {
        console.warn('[ProcessAudio] Erro no WebSocket de áudio:', err);
      };

      ws.onclose = () => {
        console.log('[ProcessAudio] WebSocket de áudio encerrado.');
      };

      return mediaStreamDest.stream.getAudioTracks()[0] || null;
    } catch (e) {
      console.error('[ProcessAudio] Exceção ao capturar áudio do processo:', e);
      return null;
    }
  };

  // Helper to create a valid dummy stream with tracks for valid WebRTC SDP m-lines
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
    } catch (e) {}

    const tracks: MediaStreamTrack[] = [];
    if (videoTrack) tracks.push(videoTrack);
    if (audioTrack) tracks.push(audioTrack);
    return new MediaStream(tracks);
  };

  // Broadcast Room Presence to all connected data channels
  const broadcastRoomPresence = () => {
    const isHostLive = participantsRef.current.some(p => p.isHost && p.isStreaming);
    const payload = {
      type: 'room-presence',
      isHostStreaming: isHostLive,
      participants: participantsRef.current
    };
    roomDataConnectionsRef.current.forEach(c => {
      if (c.open) {
        try { c.send(payload); } catch {}
      }
    });
    setParticipantsList([...participantsRef.current]);
  };

  // Initialize or attach to a Persistent Room
  const initPersistentRoom = (targetRoom: string): Promise<Peer> => {
    return new Promise((resolve, reject) => {
      if (peerRef.current && myRoomId === targetRoom && !peerRef.current.destroyed) {
        setIsRoomOpen(true);
        resolve(peerRef.current);
        return;
      }

      setMyRoomId(targetRoom);
      setIsRoomOpen(true);
      saveRecentRoom(targetRoom);

      if (peerRef.current) {
        try { peerRef.current.destroy(); } catch {}
        peerRef.current = null;
      }

      const peer = new Peer(targetRoom, {
        config: {
          iceServers: ICE_SERVERS
        }
      });
      peerRef.current = peer;

      peer.on('open', (id) => {
        console.log('[Host Hub] Sala P2P registrada e pronta no servidor:', id);
        setMyRoomId(id);
        setIsRoomOpen(true);
        saveRecentRoom(id);
        localStorage.setItem('xennex_last_room', id);

        participantsRef.current = [{
          peerId: id,
          name: 'Host Principal',
          isHost: true,
          isStreaming: isStreaming,
          streamTitle: isStreaming ? (capturedProcessName || streamTitle) : '',
          streamPeerId: id
        }];

        resolve(peer);
      });

      peer.on('disconnected', () => {
        console.warn('[Host Hub] Conexão com sinalização oscilou. Reconectando socket...');
        try {
          peer.reconnect();
        } catch (e) {
          console.error('[Host Hub] Erro ao reconectar socket:', e);
        }
      });

      peer.on('connection', (conn) => {
        roomDataConnectionsRef.current.push(conn);

        const sendCurrentState = () => {
          try {
            conn.send({
              type: 'room-presence',
              participants: participantsRef.current
            });
            if (activeCoStreamersRef.current.length > 0) {
              conn.send({
                type: 'streamers-list',
                streamers: activeCoStreamersRef.current
              });
            }
          } catch (e) {}
        };

        if (conn.open) {
          sendCurrentState();
        } else {
          conn.on('open', sendCurrentState);
        }

        conn.on('data', (data: any) => {
          if (!data || typeof data !== 'object') return;

          if (data.type === 'join-room') {
            const pId = data.peerId || conn.peer;
            const pName = data.name || `Espectador (${pId.slice(-4)})`;
            console.log('[Host Hub] Participante entrou na sala:', pName, pId);
            
            const existing = participantsRef.current.find(p => p.peerId === pId);
            if (!existing) {
              participantsRef.current.push({
                peerId: pId,
                name: pName,
                isHost: false,
                isStreaming: !!data.isStreaming,
                streamTitle: data.streamTitle,
                streamPeerId: data.streamPeerId
              });
            } else {
              existing.name = pName;
            }
            broadcastRoomPresence();
          } 
          else if (data.type === 'update-name' && data.name) {
            const pId = data.peerId || conn.peer;
            const p = participantsRef.current.find(x => x.peerId === pId);
            if (p) {
              p.name = data.name;
              broadcastRoomPresence();
            }
          } 
          else if (data.type === 'get-presence') {
            sendCurrentState();
          }
          else if (data.type === 'start-sharing' || data.type === 'register-co-streamer') {
            const sId = data.streamPeerId || data.peerId || data.streamer?.id;
            const title = data.streamTitle || data.title || data.streamer?.label || 'Gameplay Secundária';
            console.log('[Host Hub] Transmissão adicional registrada na sala:', sId, title);

            activeCoStreamersRef.current = [
              ...activeCoStreamersRef.current.filter(s => s.peerId !== sId),
              { peerId: sId, title }
            ];

            const p = participantsRef.current.find(x => x.peerId === (data.peerId || conn.peer));
            if (p) {
              p.isStreaming = true;
              p.streamPeerId = sId;
              p.streamTitle = title;
            }
            broadcastRoomPresence();

            roomDataConnectionsRef.current.forEach(c => {
              if (c.open && c.peer !== conn.peer) {
                try {
                  c.send({
                    type: 'co-streamer-added',
                    peerId: sId,
                    title
                  });
                } catch (e) {}
              }
            });
          }
          else if (data.type === 'stop-sharing') {
            const p = participantsRef.current.find(x => x.peerId === (data.peerId || conn.peer));
            if (p) {
              p.isStreaming = false;
              p.streamPeerId = '';
            }
            broadcastRoomPresence();
          }
        });

        conn.on('close', () => {
          roomDataConnectionsRef.current = roomDataConnectionsRef.current.filter(c => c !== conn);
          participantsRef.current = participantsRef.current.filter(p => p.peerId !== conn.peer);
          activeCoStreamersRef.current = activeCoStreamersRef.current.filter(s => s.peerId !== conn.peer);
          broadcastRoomPresence();
        });
      });

      peer.on('call', (incomingCall) => {
        console.log('[Host Hub] Espectador solicitando vídeo...');
        const streamToAnswer = localStreamRef.current || createDummyStream();
        incomingCall.answer(streamToAnswer);
        activeCallsRef.current.push(incomingCall);
        setViewerCount(activeCallsRef.current.length);
        tuneCallSenders(incomingCall);

        incomingCall.on('close', () => {
          activeCallsRef.current = activeCallsRef.current.filter(c => c !== incomingCall);
          setViewerCount(activeCallsRef.current.length);
        });

        incomingCall.on('error', () => {
          activeCallsRef.current = activeCallsRef.current.filter(c => c !== incomingCall);
          setViewerCount(activeCallsRef.current.length);
        });
      });

      peer.on('error', (err: any) => {
        console.warn('[Host Hub] Peer error:', err);
        if (err.type === 'unavailable-id') {
          const fallback = `${targetRoom}_${Math.floor(100 + Math.random() * 900)}`;
          console.log(`[Host Hub] ID ${targetRoom} em uso, usando fallback ${fallback}`);
          initPersistentRoom(fallback).then(resolve).catch(reject);
        } else {
          reject(err);
        }
      });
    });
  };


  // Senders tuning to enforce fixed resolution, 60fps, and high bitrate (30Mbps for 2K)
  const tuneCallSenders = (call: MediaConnection) => {
    const tune = () => {
      try {
        const pc = (call as any).peerConnection as RTCPeerConnection;
        if (!pc) return;

        const resObj = RESOLUTIONS.find(r => r.id === selectedResolution);
        const targetW = resObj?.width || 1920;
        const targetH = resObj?.height || 1080;
        const targetFps = selectedFps > 0 ? selectedFps : 60;
        const is2KOrHigher = targetW >= 2560 || targetH >= 1440;

        // Dynamic bitrate budgeting to ensure crystal clear 60 FPS without compression artifacts:
        // 2K/1440p 60fps -> 30 Mbps (min 12 Mbps)
        // 1080p 60fps -> 18 Mbps (min 6 Mbps)
        // 720p 60fps -> 10 Mbps (min 4 Mbps)
        const targetBitrate = is2KOrHigher ? 30_000_000 : (targetFps >= 60 ? 18_000_000 : 10_000_000);
        const minBitrate = is2KOrHigher ? 12_000_000 : 6_000_000;

        pc.getSenders().forEach((sender) => {
          if (sender.track && sender.track.kind === 'video') {
            const params = sender.getParameters();
            if (!params.encodings || params.encodings.length === 0) {
              params.encodings = [{}];
            }

            params.encodings[0].maxBitrate = targetBitrate;
            (params.encodings[0] as any).minBitrate = minBitrate;
            params.encodings[0].maxFramerate = targetFps;
            params.encodings[0].scaleResolutionDownBy = 1.0; // Strictly NEVER scale down resolution
            params.encodings[0].networkPriority = 'high';
            params.encodings[0].priority = 'high';

            // Garante que o WebRTC NUNCA reduza a resolução escolhida (2K/1080p mantidos sempre)
            params.degradationPreference = 'maintain-resolution';

            sender.setParameters(params).catch(() => {});
          }
        });
      } catch (e) {
        console.warn('[Host] tuneSenders error:', e);
      }
    };

    tune();
    const pc = (call as any).peerConnection as RTCPeerConnection;
    if (pc) {
      pc.addEventListener('connectionstatechange', () => {
        if (pc.connectionState === 'connected') {
          tune();
        }
      });
    }
  };

  // Connect to native GPU CaptureWorker WebSocket
  const connectNativeVideoWebSocket = async (targetFps: number, width?: number, height?: number): Promise<MediaStream | null> => {
    return new Promise((resolve) => {
      try {
        const targetW = width || 1920;
        const targetH = height || 1080;
        const canvas = document.createElement('canvas');
        canvas.width = targetW;
        canvas.height = targetH;
        nativeCanvasRef.current = canvas;
        const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true });

        const ws = new WebSocket('ws://127.0.0.1:59124/videostream/');
        ws.binaryType = 'arraybuffer';
        nativeCaptureSocketRef.current = ws;

        let hasFirstFrame = false;
        let isRendering = false;

        ws.onmessage = async (event) => {
          if (!(event.data instanceof ArrayBuffer) || !ctx) return;
          if (isRendering) return;

          isRendering = true;
          try {
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const bitmap = await createImageBitmap(blob);
            
            // STRICT: Always render to the chosen target resolution, never shrink canvas
            ctx.drawImage(bitmap, 0, 0, targetW, targetH);
            bitmap.close();

            if (!hasFirstFrame) {
              hasFirstFrame = true;
              console.log(`[NativeVideo] Primeiro frame GPU recebido com sucesso! (${targetW}x${targetH} @ ${targetFps} FPS)`);
              const canvasStream = canvas.captureStream ? canvas.captureStream(targetFps) : (canvas as any).mozCaptureStream(targetFps);
              const vTrack = canvasStream.getVideoTracks()[0];
              if (vTrack) {
                if ('contentHint' in vTrack) {
                  vTrack.contentHint = 'motion';
                }
                vTrack.applyConstraints({
                  width: { exact: targetW },
                  height: { exact: targetH },
                  frameRate: { exact: targetFps }
                }).catch(() => {
                  vTrack.applyConstraints({
                    width: { ideal: targetW },
                    height: { ideal: targetH },
                    frameRate: { ideal: targetFps, min: targetFps }
                  }).catch(() => {});
                });
              }
              resolve(canvasStream);
            }
          } catch (e) {
            console.warn('[NativeVideo] Erro ao desenhar frame no canvas:', e);
          } finally {
            isRendering = false;
          }
        };

        ws.onerror = (err) => {
          console.warn('[NativeVideo] Erro no WebSocket nativo:', err);
          if (!hasFirstFrame) resolve(null);
        };

        ws.onclose = () => {
          console.log('[NativeVideo] WebSocket nativo fechado.');
        };

        setTimeout(() => {
          if (!hasFirstFrame) {
            console.warn('[NativeVideo] Timeout aguardando primeiro frame do CaptureWorker.');
            resolve(null);
          }
        }, 6000);
      } catch (err) {
        console.error('[NativeVideo] Exceção:', err);
        resolve(null);
      }
    });
  };

  // Helper to activate room, send tracks, and start preview
  const finalizeStreamStart = async (streamToSend: MediaStream, targetRoomOverride?: string) => {
    rawStreamRef.current = streamToSend;
    localStreamRef.current = streamToSend;

    // Ensure room is active and open
    const targetRoom = targetRoomOverride || myRoomId || customRoomId.trim().toUpperCase() || generateRandomRoomId();
    await initPersistentRoom(targetRoom);

    setIsStreaming(true);
    startUptimeTimer();

    // Update room presence
    participantsRef.current = participantsRef.current.map(p => 
      p.isHost ? {
        ...p,
        isStreaming: true,
        streamTitle: capturedProcessName || streamTitle || 'Transmissão Principal',
        streamPeerId: targetRoom
      } : p
    );
    broadcastRoomPresence();

    // Notify viewers and update existing active calls with new tracks
    roomDataConnectionsRef.current.forEach(c => {
      if (c.open) {
        try {
          c.send({
            type: 'host-video-started',
            roomId: targetRoom,
            streamTitle: capturedProcessName || streamTitle
          });
        } catch (e) {}
      }
    });

    activeCallsRef.current.forEach(call => {
      try {
        const pc = call.peerConnection;
        if (pc) {
          const senders = pc.getSenders();
          const vTrack = streamToSend.getVideoTracks()[0];
          const aTrack = streamToSend.getAudioTracks()[0];
          
          let audioReplaced = false;
          senders.forEach(sender => {
            if (sender.track && sender.track.kind === 'video' && vTrack) {
              sender.replaceTrack(vTrack).catch(() => {});
            } else if (sender.track && sender.track.kind === 'audio' && aTrack) {
              sender.replaceTrack(aTrack).catch(() => {});
              audioReplaced = true;
            }
          });

          if (!audioReplaced && aTrack) {
            try { pc.addTrack(aTrack, streamToSend); } catch {}
          }
        }
        tuneCallSenders(call);
      } catch (e) {}
    });

    if (previewVideoRef.current) {
      previewVideoRef.current.srcObject = streamToSend;
      previewVideoRef.current.play().catch(() => {});
    }
  };

  // Start Screen Capture & Broadcast into Open Room
  const startStream = async (targetRoomOverride?: string) => {
    try {
      // 1. Verificar se podemos usar Captura Nativa WGC GPU (Zero-Dialog)
      const canUseNative = !!(api && typeof api.StartNativeWindowCapture === 'function');

      if (canUseNative) {
        let hwndToCapture = 0;
        if (pickerTab === 'apps') {
          const matchedProc = audioProcesses.find(p => p.Pid === selectedProcessPid);
          hwndToCapture = selectedProcessHwnd || matchedProc?.Hwnd || 0;
        } else {
          // Telas Inteiras -> Monitor Primário
          hwndToCapture = 0;
        }

        console.log('[Host] Ativando Captura Nativa WGC GPU (Zero-Dialog) para HWND:', hwndToCapture);
        const targetFps = selectedFps > 0 ? selectedFps : 60;
        const resObj = RESOLUTIONS.find(r => r.id === selectedResolution);
        const nativeStarted = await api.StartNativeWindowCapture(hwndToCapture, selectedProcessPid || 0, targetFps, selectedResolution || '1080p');

        if (nativeStarted) {
          const targetW = resObj?.width || 1920;
          const targetH = resObj?.height || 1080;
          const nativeVideoStream = await connectNativeVideoWebSocket(targetFps, targetW, targetH);
          if (nativeVideoStream) {
            let processAudioTrack: MediaStreamTrack | null = null;
            if (audioMode === 'process' && selectedProcessPid) {
              processAudioTrack = await startProcessAudioCapture(selectedProcessPid);
            } else if (audioMode === 'system') {
              processAudioTrack = await startProcessAudioCapture(0);
            }

            const tracks: MediaStreamTrack[] = [nativeVideoStream.getVideoTracks()[0]];
            if (processAudioTrack) {
              tracks.push(processAudioTrack);
              setHasCapturedAudio(true);
            }

            const streamToSend = new MediaStream(tracks);

            setCapturedStats({
              width: resObj?.width || 1920,
              height: resObj?.height || 1080,
              fps: targetFps
            });

            await finalizeStreamStart(streamToSend, targetRoomOverride);
            console.log('[Host] Transmissão Nativa GPU iniciada com sucesso! Zero diálogos.');
            return;
          }
        }
        console.warn('[Host] Falha ao conectar ao CaptureWorker nativo, usando fallback de navegador...');
      }

      const mediaDevices = navigator.mediaDevices || (navigator as any).webkitMediaDevices;
      if (!mediaDevices || !mediaDevices.getDisplayMedia) {
        alert('Seu navegador ou ambiente WebView não suporta compartilhamento de tela.');
        return;
      }

      // Check audio
      let processAudioTrack: MediaStreamTrack | null = null;
      if (audioMode === 'process' && selectedProcessPid) {
        processAudioTrack = await startProcessAudioCapture(selectedProcessPid);
      }

      const captureOptions: any = {
        video: {
          cursor: 'always'
        },
        audio: audioMode === 'system' ? {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        } : false
      };

      if (audioMode === 'system') {
        captureOptions.systemAudio = 'include';
      }

      let stream: MediaStream;
      try {
        stream = await mediaDevices.getDisplayMedia(captureOptions);
      } catch (audioErr: any) {
        if (audioErr.name === 'NotAllowedError') throw audioErr;
        console.warn('[Host] Captura de áudio estrita falhou, tentando fallback:', audioErr);
        captureOptions.audio = audioMode === 'system';
        stream = await mediaDevices.getDisplayMedia(captureOptions);
      }

      rawStreamRef.current = stream;
      setHasCapturedAudio(stream.getAudioTracks().length > 0 || !!processAudioTrack);

      stream.getVideoTracks()[0].onended = () => {
        pauseVideoStream();
      };

      // Handle resolution scaling
      const selectedResObj = RESOLUTIONS.find(r => r.id === selectedResolution);
      let streamToSend = stream;

      if (selectedResObj && selectedResObj.width && selectedResObj.height) {
        const targetW = selectedResObj.width;
        const targetH = selectedResObj.height;
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
          }
          requestAnimationFrame(drawFrame);
        };
        drawFrame();

        const canvasStream = canvas.captureStream ? canvas.captureStream(targetFps) : (canvas as any).mozCaptureStream(targetFps);

        const tracksToBundle: MediaStreamTrack[] = [canvasStream.getVideoTracks()[0]];
        if (processAudioTrack) {
          tracksToBundle.push(processAudioTrack);
          setHasCapturedAudio(true);
        } else if (stream.getAudioTracks().length > 0) {
          tracksToBundle.push(stream.getAudioTracks()[0]);
          setHasCapturedAudio(true);
        }

        streamToSend = new MediaStream(tracksToBundle);
        canvasRendererRef.current = {
          stop: () => {
            isRendering = false;
            hiddenVideo.pause();
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
        const tracksToBundle: MediaStreamTrack[] = [stream.getVideoTracks()[0]];
        if (processAudioTrack) {
          tracksToBundle.push(processAudioTrack);
          setHasCapturedAudio(true);
        } else if (stream.getAudioTracks().length > 0) {
          tracksToBundle.push(stream.getAudioTracks()[0]);
          setHasCapturedAudio(true);
        }

        streamToSend = new MediaStream(tracksToBundle);
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

      await finalizeStreamStart(streamToSend, targetRoomOverride);
      console.log('[Host] Transmissão Browser iniciada.');

    } catch (err: any) {
      console.error('[Host] Falha ao capturar tela:', err);
      if (err.name !== 'NotAllowedError') {
        alert('Não foi possível capturar a tela: ' + err.message);
      }
    }
  };

  // Pause Video Only (Room Remains Active & Online in Lobby Mode)
  const pauseVideoStream = () => {
    if (api && api.StopNativeWindowCapture) {
      try { api.StopNativeWindowCapture(); } catch {}
    }
    if (nativeCaptureSocketRef.current) {
      try { nativeCaptureSocketRef.current.close(); } catch {}
      nativeCaptureSocketRef.current = null;
    }
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
    if (processAudioSocketRef.current) {
      try { processAudioSocketRef.current.close(); } catch {}
      processAudioSocketRef.current = null;
    }

    setIsStreaming(false);
    setCapturedStats(null);
    setHasCapturedAudio(false);

    // Update presence: Host in lobby
    participantsRef.current = participantsRef.current.map(p => 
      p.isHost ? { ...p, isStreaming: false, streamTitle: '' } : p
    );
    broadcastRoomPresence();

    roomDataConnectionsRef.current.forEach(c => {
      if (c.open) {
        try {
          c.send({
            type: 'host-video-stopped',
            roomId: myRoomId
          });
        } catch (e) {}
      }
    });
  };

  // Close Room Completely (Explicit destruction)
  const closeRoom = (targetRoomId?: string) => {
    const rId = targetRoomId || myRoomId;
    if (!rId) return;

    pauseVideoStream();

    roomDataConnectionsRef.current.forEach(c => {
      if (c.open) {
        try { c.send({ type: 'room-closed', roomId: rId }); } catch {}
        try { c.close(); } catch {}
      }
    });
    roomDataConnectionsRef.current = [];

    activeCallsRef.current.forEach(call => {
      try { call.close(); } catch {}
    });
    activeCallsRef.current = [];

    if (peerRef.current) {
      try { peerRef.current.destroy(); } catch {}
      peerRef.current = null;
    }

    if (uptimeTimerRef.current) {
      window.clearInterval(uptimeTimerRef.current);
      uptimeTimerRef.current = null;
    }

    setIsRoomOpen(false);
    setMyRoomId('');
    setViewerCount(0);
    setUptimeSeconds(0);
    participantsRef.current = [];
    activeCoStreamersRef.current = [];
  };

  // Copy Room Code
  const copyRoomCode = () => {
    if (!myRoomId) return;
    navigator.clipboard.writeText(myRoomId);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  // Copy Web Link for Friends
  const copyWebLink = () => {
    if (!myRoomId) return;
    const baseUrl = (cloudflareUrl.trim() || DEFAULT_CLOUDFLARE_URL);
    const fullUrl = `${baseUrl.replace(/\/+$/, '')}${baseUrl.includes('?') ? '&' : '?'}room=${myRoomId}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedWebLink(true);
    setTimeout(() => setCopiedWebLink(false), 2000);
  };

  const startUptimeTimer = () => {
    setUptimeSeconds(0);
    if (uptimeTimerRef.current) window.clearInterval(uptimeTimerRef.current);
    uptimeTimerRef.current = window.setInterval(() => {
      setUptimeSeconds(prev => {
        const next = prev + 1;
        // Periodic check every 3s to guarantee WebRTC never downgrades 2K/60fps
        if (next % 3 === 0 && activeCallsRef.current.length > 0) {
          activeCallsRef.current.forEach(c => {
            try { tuneCallSenders(c); } catch {}
          });
        }
        return next;
      });
    }, 1000);
  };

  const formatUptime = (totalSeconds: number) => {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

    const handleOpenPicker = () => {
    fetchAudioProcesses();
    setIsDiscordPickerOpen(true);
  };

  const handleConfirmPickerStream = () => {
    setIsDiscordPickerOpen(false);
    const lastRoom = localStorage.getItem('xennex_last_room') || '';
    const roomToUse = myRoomId || customRoomId.trim().toUpperCase() || lastRoom || generateRandomRoomId();
    startStream(roomToUse);
  };

  const handleOpenViewer = async (targetRoom?: string, title?: string) => {
    const rId = targetRoom || joinRoomId.trim().toUpperCase();
    if (!rId) {
      alert('Por favor, digite o código da sala.');
      return;
    }

    saveRecentRoom(rId);

    if (api && api.OpenStreamViewer) {
      try {
        await api.OpenStreamViewer(rId, title || joinTitle || 'Transmissão P2P');
      } catch (err) {
        console.error('Falha ao abrir popout nativo:', err);
      }
    } else {
      window.open(`/watch.html?room=${rId}&title=${encodeURIComponent(title || joinTitle || 'Transmissão')}`, '_blank');
    }
  };

  const handleOpenInBrowser = async () => {
    if (!myRoomId) return;
    const baseUrl = (cloudflareUrl.trim() || DEFAULT_CLOUDFLARE_URL);
    const fullUrl = `${baseUrl.replace(/\/+$/, '')}${baseUrl.includes('?') ? '&' : '?'}room=${myRoomId}`;
    if (api && api.OpenBrowser) {
      await api.OpenBrowser(fullUrl);
    } else {
      window.open(fullUrl, '_blank');
    }
  };

  const saveRecentRoom = (rId: string) => {
    if (!rId) return;
    setRecentRooms(prev => {
      const next = [rId, ...prev.filter(r => r !== rId)].slice(0, 5);
      localStorage.setItem('xennex_recent_rooms', JSON.stringify(next));
      return next;
    });
  };

  const deleteRecentRoom = (rId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setRecentRooms(prev => {
      const next = prev.filter(r => r !== rId);
      localStorage.setItem('xennex_recent_rooms', JSON.stringify(next));
      return next;
    });
  };

  useEffect(() => {
    const saved = localStorage.getItem('xennex_recent_rooms');
    if (saved) {
      try { setRecentRooms(JSON.parse(saved)); } catch {}
    }
    if (audioMode === 'process') {
      fetchAudioProcesses();
    }

    return () => {
      closeRoom();
    };
  }, []);

  useEffect(() => {
    if (isStreaming && previewVideoRef.current && localStreamRef.current) {
      if (previewVideoRef.current.srcObject !== localStreamRef.current) {
        previewVideoRef.current.srcObject = localStreamRef.current;
        previewVideoRef.current.play().catch(() => {});
      }
    }
  }, [isStreaming]);

  return (
    <div className="stream-tab-container">
      {/* Top Header */}
      <div className="stream-tab-header">
        <div className="header-badge">
          <Radio size={14} className="pulse-dot" />
          <span>XENNEX P2P HUB</span>
        </div>
        <h2>Transmissão & Salas P2P</h2>
        <p className="tab-subtitle">
          Crie salas persistentes para seus amigos assistirem diretamente pelo navegador ou transmita em altíssima resolução com áudio exclusivo.
        </p>
      </div>

      {/* Main Grid: 2 Cards (Host & Viewer) */}
      <div className="stream-grid">
        
        {/* Card 1: Transmissor (Host) */}
        <div className="stream-card host-card">
          <div className="stream-card-header">
            <div className="card-title-group">
              <div className="card-icon-bubble">
                <Tv size={20} color="#C084FC" />
              </div>
              <div>
                <h3>Transmitir Tela (Host)</h3>
                <span className="card-subtitle">Crie uma sala aberta para seus amigos assistirem</span>
              </div>
            </div>

            {(isRoomOpen || isStreaming) && (
              <div className="card-live-tag">
                <span className={isStreaming ? "live-dot" : "live-dot lobby-dot"}></span>
                {isStreaming ? 'AO VIVO' : 'LOBBY ABERTO'}
              </div>
            )}
          </div>

          <div className="stream-card-body">
            {/* Se uma sala já estiver aberta no app, exibe o painel de gerenciamento ativo */}
            {(isRoomOpen || isStreaming) && (
              <div className="open-room-management-box">
                <div className="open-room-header-row">
                  <div className="open-room-info">
                    <span className="open-room-status-pill">
                      <span className={isStreaming ? "status-dot live" : "status-dot lobby"}></span>
                      {isStreaming ? 'Transmissão em Andamento' : 'Sala Aberta • Aguardando Vídeo'}
                    </span>
                    <div className="open-room-code-display">
                      <span className="room-code-label">Código da Sala:</span>
                      <strong className="room-code-value">{myRoomId}</strong>
                    </div>
                  </div>

                  <div className="open-room-stats">
                    <div className="stat-bubble" title="Espectadores conectados">
                      <Users size={14} />
                      <span>{viewerCount}</span>
                    </div>
                    {isStreaming && (
                      <div className="stat-bubble" title="Tempo no ar">
                        <Clock size={14} />
                        <span>{formatUptime(uptimeSeconds)}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Preview de Vídeo Ativo */}
                {isStreaming && (
                  <div className="preview-container" style={{ margin: '12px 0' }}>
                    <video 
                      ref={el => {
                        previewVideoRef.current = el;
                        if (el && localStreamRef.current && el.srcObject !== localStreamRef.current) {
                          el.srcObject = localStreamRef.current;
                          el.play().catch(() => {});
                        }
                      }} 
                      muted 
                      autoPlay 
                      playsInline 
                      className="preview-video"
                    />
                    <div className="preview-overlay">
                      <span className="preview-label">
                        {capturedStats?.width && capturedStats?.height 
                          ? `${capturedStats.width}x${capturedStats.height} @ ${capturedStats.fps || selectedFps} FPS` 
                          : `${(selectedResolution || '1080p').toUpperCase()} @ ${selectedFps > 0 ? selectedFps + ' FPS' : 'Nativo'}`}
                        {hasCapturedAudio ? (
                          capturedProcessName ? ` • 🎯 Áudio: ${capturedProcessName}` : ' • 🔊 Áudio Sistema'
                        ) : ' • 🔇 Sem Áudio'}
                      </span>
                    </div>
                  </div>
                )}

                {/* Ações de Controle da Sala Aberta */}
                {/* Participantes Conectados na Sala */}
                {participantsList.length > 1 && (
                  <div className="room-participants-host-box">
                    <div className="participants-host-header">
                      <Users size={14} />
                      <span>Participantes Conectados ({participantsList.length})</span>
                    </div>
                    <div className="participants-host-list">
                      {participantsList.map(p => (
                        <div key={p.peerId} className="participant-host-item">
                          <div className="participant-host-name">
                            <span className={p.isStreaming ? "p-dot live" : "p-dot"}></span>
                            <span className="p-name">{p.name} {p.isHost ? '(Host)' : ''}</span>
                            {p.isStreaming && <span className="host-streaming-badge">AO VIVO</span>}
                          </div>
                          {p.isStreaming && !p.isHost && p.streamPeerId && (
                            <button 
                              className="btn-host-watch-stream"
                              onClick={() => handleOpenViewer(p.streamPeerId!, p.streamTitle || p.name)}
                              title="Assistir tela transmitida por este amigo"
                            >
                              <Eye size={13} />
                              <span>Assistir Tela</span>
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="open-room-actions-grid">
                  {!isStreaming ? (
                    <button className="btn-start-stream" onClick={handleOpenPicker}>
                      <Play size={16} fill="currentColor" /> Iniciar Transmissão nesta Sala
                    </button>
                  ) : (
                    <button className="btn-pause-stream" onClick={pauseVideoStream}>
                      <Pause size={16} /> Parar Vídeo (Manter Sala Aberta)
                    </button>
                  )}

                  <button className="btn-close-room" onClick={() => closeRoom(myRoomId)}>
                    <Square size={16} /> Fechar Sala
                  </button>
                </div>

                <div className="open-room-links-row">
                  <button className="btn-room-link-action" onClick={copyWebLink}>
                    {copiedWebLink ? <Check size={14} color="#10B981" /> : <Copy size={14} />}
                    <span>{copiedWebLink ? 'Link Copiado!' : 'Copiar Link para Amigos (Web)'}</span>
                  </button>

                  <button className="btn-room-link-action" onClick={copyRoomCode}>
                    {copiedCode ? <Check size={14} color="#10B981" /> : <Copy size={14} />}
                    <span>{copiedCode ? 'Código Copiado!' : 'Copiar Código'}</span>
                  </button>

                  <button className="btn-room-link-action" onClick={() => handleOpenViewer(myRoomId, streamTitle)}>
                    <ExternalLink size={14} />
                    <span>Abrir Pop-out</span>
                  </button>

                  <button className="btn-room-link-action" onClick={handleOpenInBrowser}>
                    <ExternalLink size={14} />
                    <span>Abrir no Navegador</span>
                  </button>
                </div>
              </div>
            )}

            {/* Configurações da Transmissão */}
            {!isStreaming && (
              <>
                {/* Título da Live */}
                <div className="form-group">
                  <label>Título da Transmissão</label>
                  <input 
                    type="text" 
                    value={streamTitle} 
                    onChange={e => handleTitleChange(e.target.value)}
                    placeholder="Ex: Jogando Peak com os Amigos"
                    className="stream-input"
                  />
                </div>

                {/* Custom Room ID Chooser */}
                <div className="form-group">
                  <label>Código da Sala Personalizado</label>
                  <div className="room-chooser-input-group">
                    <input 
                      type="text" 
                      value={customRoomId} 
                      onChange={e => handleCustomRoomChange(e.target.value)}
                      placeholder="Ex: XNX-PEAK ou Deixe vazio para gerar aleatório"
                      className="stream-input font-mono"
                      maxLength={16}
                    />
                    <button 
                      type="button" 
                      className="btn-random-room" 
                      onClick={generateRandomRoomId}
                      title="Gerar código aleatório"
                    >
                      <Shuffle size={14} />
                      <span>Gerar</span>
                    </button>
                  </div>
                  <div className="room-chooser-hint">
                    💡 Seus amigos usarão esse código para entrar na sala diretamente pela web.
                  </div>
                </div>

                {/* Cloudflare Pages URL */}
                <div className="form-group">
                  <label>Link Público Cloudflare Pages (Opcional)</label>
                  <input 
                    type="text" 
                    value={cloudflareUrl} 
                    onChange={e => handleCloudflareUrlChange(e.target.value)}
                    placeholder="Ex: https://sua-pagina.pages.dev"
                    className="stream-input font-mono"
                  />
                </div>

                {/* Resolution Selector */}
                <div className="form-group">
                  <div className="setting-label-row">
                    <label>Resolução da Transmissão</label>
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
                          <Sliders size={13} className="pill-icon" />
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
                        🎯 <strong>Áudio Exclusivo (Discord Style):</strong> Os espectadores ouvirão <strong>somente</strong> o som deste jogo. Suas conversas no Discord e notificações do Windows <strong>não</strong> vazam na live!
                      </div>
                    </div>
                  )}

                  {audioMode === 'system' && (
                    <div className="system-audio-hint">
                      💡 <strong>Áudio Global do Sistema:</strong> No seletor do Windows que abrir, selecione a aba <strong>"Tela inteira"</strong> e marque a opção <strong>"Compartilhar áudio do sistema"</strong> no canto inferior esquerdo.
                    </div>
                  )}
                </div>

                {!isRoomOpen && !isStreaming ? (
                  <div className="host-launch-buttons-row">
                    <button className="btn-start-stream" onClick={handleOpenPicker}>
                      <Play size={18} fill="currentColor" /> Iniciar Transmissão Imediata
                    </button>
                    <button 
                      className="btn-create-lobby" 
                      onClick={() => initPersistentRoom(customRoomId.trim().toUpperCase() || generateRandomRoomId())}
                      title="Abre a sala no servidor para os amigos já entrarem no lobby"
                    >
                      <Radio size={16} /> Abrir Sala sem Vídeo (Lobby)
                    </button>
                  </div>
                ) : null}
              </>
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
              <label>Apelido da Janela (Opcional)</label>
              <input 
                type="text" 
                value={joinTitle} 
                onChange={e => setJoinTitle(e.target.value)}
                placeholder="Ex: Monitor Gameplay Principal"
                className="stream-input"
              />
            </div>

            <button 
              className="btn-open-popout" 
              onClick={() => handleOpenViewer()}
              disabled={!joinRoomId.trim()}
            >
              <LogIn size={18} /> Entrar na Sala
            </button>

            {/* Recent Rooms List */}
            {recentRooms.length > 0 && (
              <div className="recent-rooms-section">
                <span className="recent-header">Salas Recentes</span>
                <div className="recent-list">
                  {recentRooms.map(r => (
                    <div key={r} className="recent-item" onClick={() => handleOpenViewer(r)}>
                      <span className="recent-code">{r}</span>
                      <div className="recent-actions">
                        <button 
                          className="recent-btn open" 
                          onClick={(e) => { e.stopPropagation(); handleOpenViewer(r); }}
                          title="Entrar nesta sala"
                        >
                          <ExternalLink size={14} />
                        </button>
                        <button 
                          className="recent-btn delete" 
                          onClick={(e) => deleteRecentRoom(r, e)}
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

            <div className="info-dock-tip">
              <Sparkles size={16} color="#38BDF8" className="tip-icon" />
              <span>
                <strong>Modo Pop-out & Multi-stream:</strong> Cada janela de transmissão é independente. Você pode assistir e transmitir na mesma sala, fixar janelas no topo e alternar entre o Modo Cinema e o Modo Sala Discord.
              </span>
            </div>
          </div>
        </div>

      </div>
    
      {/* Modal Estilo Discord: Partilhar a sua tela */}
      {isDiscordPickerOpen && (
        <div className="discord-picker-overlay" onClick={() => setIsDiscordPickerOpen(false)}>
          <div className="discord-picker-modal" onClick={e => e.stopPropagation()}>
            <div className="discord-picker-header">
              <h3>Compartilhar a sua tela</h3>
              <button className="discord-picker-close" onClick={() => setIsDiscordPickerOpen(false)}>✕</button>
            </div>

            {/* Navigation Tabs (Aplicações vs Ecrãs) */}
            <div className="discord-picker-tabs">
              <button 
                className={`discord-picker-tab ${pickerTab === 'apps' ? 'active' : ''}`}
                onClick={() => setPickerTab('apps')}
              >
                🎮 Aplicações & Jogos
              </button>
              <button 
                className={`discord-picker-tab ${pickerTab === 'screens' ? 'active' : ''}`}
                onClick={() => setPickerTab('screens')}
              >
                🖥️ Telas Inteiras
              </button>
            </div>

            {/* Content Tab 1: Aplicações & Jogos */}
            {pickerTab === 'apps' && (
              <div className="discord-picker-body">
                <div className="discord-picker-search-row">
                  <input 
                    type="text" 
                    placeholder="Pesquisar jogo ou janela aberta..." 
                    value={pickerSearch}
                    onChange={e => setPickerSearch(e.target.value)}
                    className="discord-picker-search"
                  />
                  <button 
                    className="discord-picker-refresh-btn" 
                    onClick={fetchAudioProcesses} 
                    title="Atualizar lista de janelas"
                  >
                    <RefreshCw size={14} className={isLoadingProcesses ? "spin" : ""} />
                  </button>
                </div>

                <div className="discord-apps-grid">
                  {audioProcesses
                    .filter(p => !pickerSearch || p.Name.toLowerCase().includes(pickerSearch.toLowerCase()) || p.Title.toLowerCase().includes(pickerSearch.toLowerCase()))
                    .map(p => {
                      const isSelected = selectedProcessPid === p.Pid && audioMode === 'process';
                      return (
                        <div 
                          key={p.Pid} 
                          className={`discord-app-card ${isSelected ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedProcessPid(p.Pid);
                            setSelectedProcessHwnd(p.Hwnd || 0);
                            setCapturedProcessName(p.Name);
                            setAudioMode('process');
                          }}
                        >
                          <div className="discord-app-card-top">
                            <div className="discord-app-icon-bubble">
                              {p.Name.slice(0, 2).toUpperCase()}
                            </div>
                            {p.HasActiveAudio && (
                              <span className="discord-audio-badge" title="Emitindo áudio no momento">
                                🔊 Áudio Ativo
                              </span>
                            )}
                          </div>
                          <div className="discord-app-title" title={p.Title || p.Name}>
                            {p.Title || p.Name}
                          </div>
                          <div className="discord-app-proc">
                            {p.Name} • PID: {p.Pid}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* Content Tab 2: Telas Inteiras */}
            {pickerTab === 'screens' && (
              <div className="discord-picker-body">
                <div className="discord-screens-grid">
                  <div 
                    className={`discord-screen-card ${audioMode === 'system' ? 'selected' : ''}`}
                    onClick={() => {
                      setAudioMode('system');
                      setSelectedProcessPid(null);
                    }}
                  >
                    <div className="discord-screen-preview-mock">
                      <Tv size={36} color="#A855F7" />
                      <span>Monitor Principal</span>
                    </div>
                    <div className="discord-screen-title">Tela Inteira (Sistema Completo)</div>
                    <div className="discord-screen-subtitle">Captura a área de trabalho inteira e o som do Windows</div>
                  </div>
                </div>
              </div>
            )}

            {/* Configurações Rápidas no Modal */}
            <div className="discord-picker-settings">
              <div className="picker-setting-row">
                <span className="picker-setting-label">Qualidade da Transmissão</span>
                <div className="picker-resolutions-pill">
                  {RESOLUTIONS.map(r => (
                    <button 
                      key={r.id} 
                      className={`picker-res-btn ${selectedResolution === r.id ? 'active' : ''}`}
                      onClick={() => handleResolutionChange(r.id)}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="picker-setting-row">
                <span className="picker-setting-label">Taxa de Quadros (FPS)</span>
                <div className="picker-resolutions-pill">
                  {[30, 60].map(fps => (
                    <button 
                      key={fps} 
                      className={`picker-res-btn ${selectedFps === fps ? 'active' : ''}`}
                      onClick={() => handleFpsChange(fps)}
                    >
                      {fps} FPS
                    </button>
                  ))}
                </div>
              </div>

              <div className="picker-setting-row">
                <span className="picker-setting-label">Captura de Áudio</span>
                <div className="picker-audio-choice">
                  {selectedProcessPid && audioMode === 'process' ? (
                    <span className="picker-audio-active-badge">
                      🎯 Áudio Exclusivo do Jogo/App: <strong>{capturedProcessName || 'Processo'} (PID {selectedProcessPid})</strong>
                    </span>
                  ) : (
                    <span className="picker-audio-active-badge system">
                      🔊 Áudio do Sistema Windows
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="discord-picker-footer">
              <button className="btn-secondary" onClick={() => setIsDiscordPickerOpen(false)}>
                Cancelar
              </button>
              <button className="btn-primary btn-discord-go-live" onClick={handleConfirmPickerStream}>
                {api ? '🚀 Transmitir Direto (Nativo)' : '🚀 Entrar em Direto'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default StreamTab;

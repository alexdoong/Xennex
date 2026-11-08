import { useState } from 'react';
import { Radio, ScreenShare, Square, Maximize2, Copy, LogIn } from 'lucide-react';
import { useStreamContext } from './StreamContext';
import CaptureProgress from './CaptureProgress';
import { DEFAULT_QUALITY } from './quality';
import { newRoomCode, normalizeRoom } from './protocol';
import type { AppTab } from '../../layout/navigation';

type Props = {
  openFullWindow: (tab?: AppTab) => void;
};

export default function StreamCompact({ openFullWindow }: Props) {
  const { state, client, locals, stop, share, capturing, capturePhase, cancel, captureError, warning, leave } = useStreamContext();
  const [roomInput, setRoomInput] = useState('');
  const [copied, setCopied] = useState(false);

  const connected = state.phase === 'connected';
  const inRoom = connected || state.phase === 'reconnecting';

  const copyCode = async () => {
    if (!state.room) return;
    try {
      await navigator.clipboard.writeText(state.room);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  };

  const handleStartScreen = async () => {
    await share({ source: 'monitor', audio: 'system', quality: DEFAULT_QUALITY }, 'Compartilhamento de tela');
  };

  const handleJoin = () => {
    const target = normalizeRoom(roomInput);
    if (!target) return;
    try { client.start(target, '', false); }
    catch {}
  };

  const handleCreate = () => {
    const target = newRoomCode();
    try { client.start(target, '', true); }
    catch {}
  };

  return (
    <div className="compact-module-view compact-stream">
      <div className="compact-stream-status">
        <span className="compact-status-badge" data-connected={inRoom}>
          <Radio size={14} />
          {inRoom ? `Sala ativa: ${state.room}` : 'Sem transmissão ativa'}
        </span>
        {inRoom && (
          <button className="title-btn" onClick={copyCode} title="Copiar código da sala">
            <Copy size={14} />
          </button>
        )}
      </div>
      {copied && <p className="compact-hint">Código copiado!</p>}
      {capturing && <CaptureProgress phase={capturePhase} cancel={cancel}/>}
      {(captureError || warning) && <p className="compact-hint" role="status">{captureError || warning}</p>}

      {inRoom ? (
        <div className="compact-stream-actions">
          {locals.length > 0 ? (
            <div className="compact-stream-locals">
              <p>Compartilhando agora:</p>
              {locals.map(l => (
                <div key={l.id} className="compact-local-track">
                  <span>{l.title}</span>
                  <button className="btn danger btn-sm" onClick={() => void stop(l.id)}>
                    <Square size={13} /> Parar
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <button className="btn primary w-full" disabled={capturing || !connected} onClick={() => void handleStartScreen()}>
              <ScreenShare size={15} /> Compartilhar tela
            </button>
          )}

          <div className="compact-stream-buttons">
            <button className="btn secondary w-full" onClick={() => void leave()}>
              Sair da sala
            </button>
          </div>
        </div>
      ) : (
        <div className="compact-stream-join">
          <label>Código da sala
            <input
              type="text"
              value={roomInput}
              placeholder="Digite o código da sala…"
              onChange={e => setRoomInput(e.target.value)}
            />
          </label>
          <div className="compact-btn-row">
            <button
              className="btn primary"
              disabled={!roomInput.trim()}
              onClick={handleJoin}
            >
              <LogIn size={14} /> Entrar
            </button>
            <button
              className="btn secondary"
              onClick={handleCreate}
            >
              Criar sala
            </button>
          </div>
        </div>
      )}

      <button
        className="compact-expand-link"
        onClick={() => openFullWindow('stream')}
      >
        <Maximize2 size={13} />
        <span>Abrir mosaico de vídeo e participantes</span>
      </button>
    </div>
  );
}

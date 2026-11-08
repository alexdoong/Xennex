import { useEffect, useRef, useState } from 'react';
import { ShieldCheck, RefreshCw, X } from 'lucide-react';
import type { RoomClient, RoomSnapshot } from './RoomClient';
import { normalizeRoom } from './protocol';
import { requestTurnLease, turnEndpoint } from './turnFallback';

interface Props { client: RoomClient; state: RoomSnapshot; code: string; name: string; base: string; onPending(value: boolean): void }
export default function TurnFallbackPanel({ client, state, code, name, base, onPending }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [access, setAccess] = useState('');
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | undefined>(undefined);
  const alternative = state.transport === 'alternative' && ['connected', 'reconnecting'].includes(state.phase);
  useEffect(() => {
    if (state.phase === 'idle' || state.phase === 'closed' || (state.phase === 'connected' && state.transport === 'direct')) {
      setAccess(''); setExpanded(false); setMessage('');
    }
    return () => { controller.current?.abort(); };
  }, [state.phase, state.transport]);
  useEffect(() => () => { controller.current?.abort(); onPending(false); }, [onPending]);
  const connect = async () => {
    if (controller.current) return;
    const target = normalizeRoom(code);
    if (!alternative && !target) { setMessage('Informe o código da sala antes de tentar a alternativa.'); return; }
    const session = client.sessionId;
    const abort = new AbortController(); controller.current = abort;
    setPending(true); onPending(true); setMessage('');
    try {
      const lease = await requestTurnLease(turnEndpoint(base, import.meta.env.VITE_TURN_ENDPOINT || ''), access, abort.signal);
      if (abort.signal.aborted || session !== client.sessionId) return;
      if (alternative) {
        if (!client.renewTurn(lease)) throw new Error('A renovação não pôde ser confirmada. Os vídeos e a sala continuam abertos.');
        setMessage('Acesso renovado.'); setExpanded(false);
      } else {
        if (client.getSnapshot().phase !== 'error') return;
        client.start(target, name, false, lease);
        setExpanded(false);
      }
    } catch (error) {
      if (session === client.sessionId && !abort.signal.aborted) setMessage(error instanceof Error ? error.message : 'Não foi possível obter a conexão alternativa.');
    } finally {
      if (controller.current === abort) { controller.current = undefined; setPending(false); onPending(false); }
    }
  };
  if (state.phase !== 'error' && !alternative) return null;
  return <div className="room-fallback" aria-label="Conexão alternativa">
    <div className="room-fallback-heading"><ShieldCheck size={20}/><div><strong>{alternative ? 'Alternativa disponível neste participante' : 'Não conseguiu entrar na sala?'}</strong>
      <small>{alternative ? `Acesso válido até ${new Date(state.turnExpiresAt).toLocaleString()}. O caminho usado aparece em Qualidade.` : 'Tente uma conexão alternativa. Ela precisa estar habilitada pelo dono da sala.'}</small></div>
      <button type="button" disabled={pending} aria-expanded={expanded} onClick={() => setExpanded(value => alternative ? true : !value)}>{alternative ? <RefreshCw size={16}/> : <ShieldCheck size={16}/>} {alternative ? 'Renovar acesso' : 'Tentar conexão alternativa'}</button></div>
    {expanded && <div className="room-fallback-form">
      <label>Código de acesso à conexão alternativa<input type="password" autoComplete="off" maxLength={256} value={access} disabled={pending} onChange={event => setAccess(event.target.value)} /></label>
      <small>Use o código privado fornecido pelo dono da sala. Ele fica somente nesta aba. A alternativa pode usar retransmissão; os demais participantes não mudam de modo.</small>
      <div><button type="button" className="room-primary" disabled={pending || access.trim().length < 24} onClick={() => void connect()}>{pending ? 'Solicitando acesso…' : alternative ? 'Confirmar renovação' : 'Conectar com alternativa'}</button>
        {pending && <button type="button" onClick={() => controller.current?.abort()}><X size={16}/>Cancelar alternativa</button>}</div>
    </div>}
    {message && <p role="status">{message}</p>}
  </div>;
}
